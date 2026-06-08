"""lib/anchor_backfill.py — Anchor Intelligence v2.3 backfill round (B1/B2/B3).

The append-only archive (:mod:`lib.anchor_archive`) only accumulates from *today*
forward, so :mod:`lib.anchor_migration`'s readout would cold-start with 1–2 months
of empty history. But anchors whose INPUTS are public historical series CAN be
recomputed for past dates. This module adds a **one-time, offline** backfill for
the recomputable anchors ONLY.

HARD INVARIANT — the line that must not be crossed
--------------------------------------------------
Backfill recomputes ONLY anchors whose inputs are genuinely retrievable as
historical series:

* **RECOMPUTABLE (backfilled):** the price/financial-based anchors — the PB/PS
  historical-percentile band (cyclical), the relative anchor (sector P/E ×
  historical EPS), and the DCF — all derivable from historical prices
  (``yfinance`` history) + annual/quarterly fundamentals. These are recomputed by
  REUSING the live assembler :func:`lib.equity_valuation._assemble_fair_value`
  with an *as-of* ``raw`` built solely from dated statements + the as-of price (no
  reimplementation — the v1 cyclical band builder already does as-of PB/PS).
* **NOT RECOMPUTABLE (never fabricated):** the analyst anchor. ``yfinance`` and all
  free sources expose ONLY the CURRENT analyst pool — there is no historical
  analyst-target series anywhere retrievable. Every backfilled record therefore
  sets ``analyst_pool`` to the sentinel
  :data:`lib.anchor_archive.ANALYST_HISTORY_UNAVAILABLE` (never ``None``-that-
  reads-as-zero, never today's pool back-dated, never any invented value). The
  forward-EPS consensus is likewise CURRENT-only, so it too is left absent.

A backfilled record is **PARTIAL by construction** (price/financial anchors
present, analyst absent + flagged) and is tagged
``record_origin="backfill"`` with ``data_vintage`` = the historical as-of date so a
consumer can tell it apart from a live-complete record.

Access-path discipline
-----------------------
* **Offline script only.** Backfill is invoked on demand from
  ``scripts/backfill_anchors.py`` — NEVER at app startup and NEVER on the ranking /
  refresh path (which must stay fast and network-free). The pure core
  (:func:`compute_backfill_records`) does no I/O at all; the impure wrapper
  (:func:`backfill_ticker`) fetches historical prices/fundamentals only.
* **No live analyst endpoint.** The fetch path reads historical prices + dated
  statements + the static ``sector`` label; it NEVER calls any analyst-target API
  (``analyst_price_targets`` / ``recommendations``) — there is nothing historical
  to get.
* **Idempotent (persistent guard).** :func:`backfill_ticker` reads the archive's
  existing ``record_origin=="backfill"`` ``data_vintage`` set for the ticker
  (:func:`lib.anchor_archive.backfilled_vintages`) and skips any as-of date already
  covered, so a double-run adds zero duplicate rows. This is robust across process
  restarts (the in-process append memo is not).
* **Append-only.** Records go to the SAME archive via
  :func:`lib.anchor_archive.append_record`; a prior row is never rewritten.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from lib import anchor_archive as aa
from lib import equity_valuation as eqv

_log = logging.getLogger("anchor_backfill")

# ---------------------------------------------------------------------------
# Visible config block (keep all tunables here)
# ---------------------------------------------------------------------------

# Window: how far back to recompute. 6 months gives U3's 30/90-day windows margin.
BACKFILL_WINDOW_MONTHS = 6
# Cadence: one recompute every N days. WEEKLY bounds the row volume (≈ 26 points
# over the 6-month window) while staying dense enough for the migration windows.
BACKFILL_CADENCE_DAYS = 7
# Price history reach: the cyclical band needs prices back to the OLDEST fiscal
# period (~4y), so the fetch pulls a multi-year weekly history.
_PRICE_FETCH_PERIOD = "5y"
_PRICE_FETCH_INTERVAL = "1wk"
# Approx days/month for the window → start-date arithmetic (deterministic).
_DAYS_PER_MONTH = 30

# Degrade caveats unique to backfill (the live caveats are reused where they fit).
CAVEAT_BACKFILL_INSUFFICIENT_FUNDAMENTALS = "backfill_insufficient_fundamentals"

# --- Filing-lag gate (G1, fix round) — the look-ahead defence -----------------
# A statement is dated by its fiscal-period END, but it is FILED / published weeks
# later (10-K ~60-90d, 10-Q ~40-45d after period end). The free loader has NO
# filing-date metadata (only period-end), so recomputing a past-date anchor with a
# statement that was not yet public on that date is LOOK-AHEAD BIAS — it
# contaminates the whole backfilled history and destroys U3's signal. We cannot
# know the real filing date, so we apply a fixed CONSERVATIVE publication lag: a
# statement counts as available on an as-of date D only when
# ``period_end + filing_lag <= D``. Real filing dates vary; a fixed conservative
# lag systematically removes look-ahead in the ONLY safe direction (it may use a
# statement slightly LATER than the market did, never EARLIER). The default
# yfinance loader fetches ANNUAL statements, so the annual lag governs in practice;
# the quarterly entry is here for any future quarterly feed.
FILING_LAG_DAYS = {"annual": 75, "quarterly": 45}


# ---------------------------------------------------------------------------
# Date helpers (pure)
# ---------------------------------------------------------------------------


def _as_of_dates(end_date: date, *, window_months: int = BACKFILL_WINDOW_MONTHS,
                 cadence_days: int = BACKFILL_CADENCE_DAYS) -> list:
    """Weekly (cadence) as-of dates over the window, oldest→newest.

    The grid is anchored at ``end_date`` (the newest point IS ``end_date`` — today's
    recompute) and steps BACKWARD by ``cadence_days`` until it reaches the window
    start, so the most-recent backfill point lines up exactly with the live series.
    Deterministic given ``end_date`` (no ``date.today()`` inside — the caller
    supplies the anchor date so tests are reproducible).
    """
    if cadence_days <= 0:
        cadence_days = BACKFILL_CADENCE_DAYS
    span_days = max(1, int(window_months) * _DAYS_PER_MONTH)
    start = end_date - timedelta(days=span_days)
    out: list = []
    d = end_date
    while d >= start:
        out.append(d)
        d = d - timedelta(days=cadence_days)
    out.reverse()  # oldest → newest
    return out


# ---------------------------------------------------------------------------
# Statement / price slicing (pure, fail-closed)
# ---------------------------------------------------------------------------


def _to_ts(value):
    """Coerce a value to a tz-naive ``pandas.Timestamp`` (else ``None``)."""
    try:
        import pandas as pd

        ts = pd.Timestamp(value)
    except Exception:  # noqa: BLE001
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts


def _slice_frame_asof(frame, as_of_ts, *, lag_days: int = 0):
    """Keep only the statement columns PUBLIC on/before ``as_of_ts`` (G1 lag gate).

    yfinance statements are indexed by row label with one column per fiscal-period
    Timestamp. A column (fiscal period) qualifies only when its
    publication-lagged availability is on/before the as-of date —
    ``period_end + lag_days <= as_of_ts`` — so a statement filed AFTER the as-of
    date is invisible exactly as it was to the market then (no look-ahead). With
    ``lag_days=0`` this reduces to the plain period-end gate. Returns a
    column-filtered copy, or ``None`` when nothing qualifies (pre-data / pre-IPO /
    not-yet-filed). Fail-closed → ``None``.
    """
    try:
        if frame is None or getattr(frame, "empty", True):
            return None
        lag = timedelta(days=int(lag_days or 0))
        keep = []
        for c in frame.columns:
            cts = _to_ts(c)
            if cts is not None and (cts + lag) <= as_of_ts:
                keep.append(c)
        if not keep:
            return None
        return frame[keep]
    except Exception:  # noqa: BLE001
        return None


def _slice_prices_asof(price_history, as_of_ts):
    """Price rows on/before ``as_of_ts`` (tz-normalized). Fail-closed → ``None``."""
    try:
        if price_history is None or getattr(price_history, "empty", True):
            return None
        px = price_history
        idx = px.index
        if getattr(idx, "tz", None) is not None:
            px = px.copy()
            px.index = idx.tz_localize(None)
        return px[px.index <= as_of_ts]
    except Exception:  # noqa: BLE001
        return None


def _price_asof(price_history_asof) -> Optional[float]:
    """Most-recent Close in an already-as-of-sliced price frame. Fail-closed → None."""
    try:
        if price_history_asof is None or getattr(price_history_asof, "empty", True):
            return None
        if hasattr(price_history_asof, "columns"):
            close = (price_history_asof["Close"] if "Close" in price_history_asof.columns
                     else price_history_asof.iloc[:, 0])
        else:
            close = price_history_asof
        close = close.dropna()
        if len(close) == 0:
            return None
        return eqv._finite_pos(float(close.iloc[-1]))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# As-of raw builder (pure) — historical-derivable fields ONLY
# ---------------------------------------------------------------------------


def _row_at(frame, names, col):
    """Finite value of the first matching row label at fiscal column ``col``."""
    try:
        if frame is None or getattr(frame, "empty", True):
            return None
        for nm in names:
            if nm in frame.index:
                return eqv._finite(frame.loc[nm, col])
    except Exception:  # noqa: BLE001
        return None
    return None


def _newest_cols(frame, n=2):
    """The ``n`` newest fiscal columns of an as-of-sliced frame (newest first)."""
    try:
        if frame is None or getattr(frame, "empty", True):
            return []
        cols = sorted(frame.columns, key=lambda c: (_to_ts(c) or _to_ts("1900-01-01")))
        return list(reversed(cols))[:n]
    except Exception:  # noqa: BLE001
        return []


_EQUITY_ROWS = ("Stockholders Equity", "Common Stock Equity",
                "Total Stockholder Equity", "StockholdersEquity")
_SHARES_ROWS = ("Ordinary Shares Number", "Share Issued",
                "Common Stock Shares Outstanding")
_REVENUE_ROWS = ("Total Revenue", "TotalRevenue", "Revenue")
_NET_INCOME_ROWS = ("Net Income", "Net Income Common Stockholders", "NetIncome")
_OP_INCOME_ROWS = ("Operating Income", "OperatingIncome",
                   "Total Operating Income As Reported")
_EBITDA_ROWS = ("EBITDA", "Normalized EBITDA")
_EPS_ROWS = ("Diluted EPS", "Basic EPS")
_OCF_ROWS = ("Operating Cash Flow", "Total Cash From Operating Activities")
_CAPEX_ROWS = ("Capital Expenditure", "Capital Expenditures")
_DEBT_ROWS = ("Total Debt",)
_CASH_ROWS = ("Cash And Cash Equivalents",
              "Cash Cash Equivalents And Short Term Investments")


def _raw_asof(*, balance_sheet_asof, income_stmt_asof, cashflow_asof,
              price_at_asof: float, sector: Optional[str]) -> dict:
    """Build an as-of ``raw`` dict for :func:`_assemble_fair_value` (pure).

    Populates ONLY historical-derivable fields from the most-recent fiscal period
    on/before the as-of date. ``analyst_*`` and ``forward_eps`` are ALWAYS ``None``
    (CURRENT-only — never back-dated). ``sector`` is the static categorical label.
    Each field fail-closes to ``None``; the assembler then degrades honestly.
    """
    raw: dict = {
        "fcf_ttm": None, "fcf_source": "", "ebitda": None, "shares": None,
        "growth_rate": None, "trailing_eps": None,
        # CURRENT-only inputs — NEVER reconstructable for a past date:
        "forward_eps": None, "analyst_median": None, "analyst_mean": None,
        "analyst_high": None, "analyst_low": None, "analyst_count": 0,
        "sector": sector, "industry": None,
        "revenue_growth": None, "earnings_growth": None,
        "profit_margin": None, "operating_margin": None,
        "market_cap": None, "enterprise_value": None, "total_revenue": None,
        "total_debt": None, "total_cash": None, "book_value": None,
        "price_to_book": None, "price_to_sales": None,
        # Backfill is NOT a live yfinance info fetch — keep data_source honest.
        "live": False,
    }

    bs_cols = _newest_cols(balance_sheet_asof, n=2)
    is_cols = _newest_cols(income_stmt_asof, n=2)
    cf_cols = _newest_cols(cashflow_asof, n=1)

    # --- balance-sheet-derived (most recent fiscal period <= as_of) ---
    equity = shares = None
    if bs_cols:
        c0 = bs_cols[0]
        equity = eqv._finite_pos(_row_at(balance_sheet_asof, _EQUITY_ROWS, c0))
        shares = eqv._finite_pos(_row_at(balance_sheet_asof, _SHARES_ROWS, c0))
        raw["shares"] = shares
        td = _row_at(balance_sheet_asof, _DEBT_ROWS, c0)
        tc = _row_at(balance_sheet_asof, _CASH_ROWS, c0)
        raw["total_debt"] = td
        raw["total_cash"] = tc
        if equity is not None and shares is not None and shares > 0:
            raw["book_value"] = round(equity / shares, 4)  # BVPS

    # --- income-statement-derived ---
    revenue = net_income = None
    if is_cols:
        c0 = is_cols[0]
        revenue = eqv._finite_pos(_row_at(income_stmt_asof, _REVENUE_ROWS, c0))
        net_income = _row_at(income_stmt_asof, _NET_INCOME_ROWS, c0)
        op_income = _row_at(income_stmt_asof, _OP_INCOME_ROWS, c0)
        ebitda = _row_at(income_stmt_asof, _EBITDA_ROWS, c0)
        eps = _row_at(income_stmt_asof, _EPS_ROWS, c0)
        raw["total_revenue"] = revenue
        raw["ebitda"] = ebitda
        # trailing EPS: a stated diluted/basic EPS row, else net_income / shares.
        if eps is not None:
            raw["trailing_eps"] = eps
        elif net_income is not None and shares is not None and shares > 0:
            raw["trailing_eps"] = round(net_income / shares, 4)
        if revenue is not None and revenue > 0:
            if net_income is not None:
                raw["profit_margin"] = round(net_income / revenue, 4)
            if op_income is not None:
                raw["operating_margin"] = round(op_income / revenue, 4)

        # YoY growth from the two most recent fiscal periods <= as_of.
        if len(is_cols) >= 2:
            c1 = is_cols[1]
            rev_prev = eqv._finite_pos(_row_at(income_stmt_asof, _REVENUE_ROWS, c1))
            ni_prev = _row_at(income_stmt_asof, _NET_INCOME_ROWS, c1)
            if rev_prev is not None and revenue is not None and rev_prev > 0:
                raw["revenue_growth"] = round((revenue - rev_prev) / rev_prev, 4)
            if (ni_prev is not None and net_income is not None and ni_prev != 0):
                raw["earnings_growth"] = round((net_income - ni_prev) / abs(ni_prev), 4)

    # --- cashflow-derived FCF (annual OCF − |CapEx|) ---
    if cf_cols:
        c0 = cf_cols[0]
        ocf = _row_at(cashflow_asof, _OCF_ROWS, c0)
        capex = _row_at(cashflow_asof, _CAPEX_ROWS, c0)
        if ocf is not None and capex is not None:
            raw["fcf_ttm"] = ocf - abs(capex)
            raw["fcf_source"] = "backfill: annual OCF − |CapEx|"

    # --- growth_rate: mirror the live min(g | default, cap) selection ---
    g = raw["earnings_growth"]
    if g is None:
        g = raw["revenue_growth"]
    if g is None:
        g = eqv._GROWTH_DEFAULT
    raw["growth_rate"] = min(g, eqv._GROWTH_CAP)

    # --- market cap = as-of price × shares (historical-honest; not back-dated info) ---
    if shares is not None and price_at_asof and price_at_asof > 0:
        raw["market_cap"] = round(price_at_asof * shares, 2)

    return raw


# ---------------------------------------------------------------------------
# Pure core: recompute the recomputable anchors at each as-of date
# ---------------------------------------------------------------------------


def _backfill_one(ticker: str, as_of: date, *, balance_sheet, income_stmt,
                  cashflow, price_history, sector: Optional[str]) -> Optional[dict]:
    """Recompute one as-of record (pure). ``None`` when no as-of price exists.

    Reuses :func:`lib.equity_valuation._assemble_fair_value` (the live assembler)
    with an as-of ``raw`` + an as-of cyclical-band fetcher, then maps the result to
    a PARTIAL archive record (analyst sentinel, ``record_origin="backfill"``,
    historical ``computed_at`` / ``data_vintage``). When no real anchor could be
    built (``blend_state == "no_anchor"`` — insufficient as-of fundamentals) the
    band is ZEROED and the :data:`CAVEAT_BACKFILL_INSUFFICIENT_FUNDAMENTALS` caveat
    is added so a current-price stub never enters the migration series.
    """
    as_of_ts = _to_ts(as_of)
    if as_of_ts is None:
        return None
    # G1 — gate the financial statements by the conservative ANNUAL filing lag (the
    # default loader fetches annual statements). This governs BOTH the DCF/relative
    # inputs (via _raw_asof's _newest_cols) AND the cyclical PB/PS band (the gated
    # frames are handed to build_pb_ps_history below), so no not-yet-public
    # statement can leak into any anchor for this date. Prices carry NO lag (they
    # were public same-day).
    _annual_lag = FILING_LAG_DAYS["annual"]
    bs_a = _slice_frame_asof(balance_sheet, as_of_ts, lag_days=_annual_lag)
    is_a = _slice_frame_asof(income_stmt, as_of_ts, lag_days=_annual_lag)
    cf_a = _slice_frame_asof(cashflow, as_of_ts, lag_days=_annual_lag)
    px_a = _slice_prices_asof(price_history, as_of_ts)

    price = _price_asof(px_a)
    if price is None or price <= 0:
        return None  # no as-of price → cannot anchor anything; never fabricate one

    raw = _raw_asof(balance_sheet_asof=bs_a, income_stmt_asof=is_a,
                    cashflow_asof=cf_a, price_at_asof=price, sector=sector)

    # As-of cyclical-band fetcher: the SAME deterministic builder the live page
    # path uses, fed the as-of-sliced frames (no network — frames are in hand).
    def _asof_cyclical_fetcher(_t):
        return eqv.build_pb_ps_history(bs_a, is_a, px_a, ticker=ticker)

    try:
        fv = eqv._assemble_fair_value(
            ticker, price, None, raw, peers=None,
            cyclical_history_fetcher=_asof_cyclical_fetcher)
    except Exception:  # noqa: BLE001 — fail-closed; skip this date rather than fabricate
        _log.warning("backfill assemble failed for %s @ %s", ticker, as_of,
                     exc_info=True)
        return None

    # Stamp the historical vintage deterministically (NOT "now"): the record is
    # dated to the as-of day so migration ordering + the idempotency guard are
    # correct. computed_at is midnight-UTC of the as-of date.
    vintage = as_of.isoformat()
    fv.computed_at = f"{vintage}T00:00:00+00:00"

    degraded = (getattr(fv, "blend_state", "") == eqv._BLEND_NONE)
    if degraded:
        # No real price/financial anchor entered — do NOT carry the current-price
        # stub band into history. Zero the band + flag (mirrors the irreconcilable
        # 0.0-band honest-degrade); migration's _finite_pos drops a 0.0 mid.
        fv.fair_value_low = 0.0
        fv.fair_value_mid = 0.0
        fv.fair_value_high = 0.0
        cav = list(getattr(fv, "caveats", []) or [])
        if CAVEAT_BACKFILL_INSUFFICIENT_FUNDAMENTALS not in cav:
            cav.append(CAVEAT_BACKFILL_INSUFFICIENT_FUNDAMENTALS)
        fv.caveats = cav

    return aa.record_from_app_fair_value(
        fv, data_vintage=vintage, record_origin=aa.RECORD_ORIGIN_BACKFILL,
        analyst_pool_override=aa.ANALYST_HISTORY_UNAVAILABLE)


def compute_backfill_records(ticker: str, *, balance_sheet, income_stmt,
                             cashflow, price_history, as_of_dates: list,
                             sector: Optional[str] = None) -> list:
    """Recompute partial backfill records for ``as_of_dates`` (PURE — no network).

    For each as-of date, recomputes the recomputable price/financial anchors from
    the dated statements + as-of price and maps the result to a PARTIAL archive
    record (analyst absent + sentinel, ``record_origin="backfill"``). Dates with no
    as-of price are skipped (never fabricated). Returns records oldest→newest.

    Deterministic: identical fixtures + dates always yield identical records — the
    backfill-determinism test relies on this.
    """
    tk = (ticker or "").upper().strip()
    out: list = []
    for as_of in sorted(as_of_dates):
        rec = _backfill_one(tk, as_of, balance_sheet=balance_sheet,
                            income_stmt=income_stmt, cashflow=cashflow,
                            price_history=price_history, sector=sector)
        if rec is not None:
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Impure wrapper: fetch (offline) + append (idempotent, append-only)
# ---------------------------------------------------------------------------


def _default_data_loader(ticker: str) -> dict:
    """Fetch historical statements + a multi-year price history (offline tool).

    Reads ``yfinance`` annual statements, a multi-year weekly price history, and
    ONLY the static ``sector`` label from ``tk.info``. It NEVER calls any
    analyst-target API (``analyst_price_targets`` / ``recommendations``) — there is
    no historical analyst series to retrieve. Fail-closed → empty frames.
    """
    out = {"balance_sheet": None, "income_stmt": None, "cashflow": None,
           "price_history": None, "sector": None}
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        out["balance_sheet"] = getattr(tk, "balance_sheet", None)
        istmt = getattr(tk, "income_stmt", None)
        if istmt is None or getattr(istmt, "empty", True):
            istmt = getattr(tk, "financials", None)
        out["income_stmt"] = istmt
        out["cashflow"] = getattr(tk, "cashflow", None)
        try:
            out["price_history"] = tk.history(
                period=_PRICE_FETCH_PERIOD, interval=_PRICE_FETCH_INTERVAL)
        except Exception:  # noqa: BLE001
            out["price_history"] = None
        # Static sector label ONLY — the analyst-target fields in this same dict
        # are deliberately ignored (CURRENT-only; never archived for a past date).
        info = tk.info if isinstance(getattr(tk, "info", None), dict) else {}
        out["sector"] = info.get("sector")
    except Exception:  # noqa: BLE001 — fail-closed offline tool
        _log.warning("backfill data load failed for %s", ticker, exc_info=True)
    return out


def backfill_ticker(ticker: str, *, window_months: int = BACKFILL_WINDOW_MONTHS,
                    cadence_days: int = BACKFILL_CADENCE_DAYS,
                    end_date: Optional[date] = None,
                    archive_path: Optional[Path] = None,
                    data_loader=None) -> dict:
    """Backfill one ticker's recomputable anchors into the archive (idempotent).

    Offline / on-demand only — NOT on the app-startup, ranking, or refresh path.
    Persistent idempotency (G2): as-of dates already covered by ANY-origin record
    (``live`` OR ``backfill``) for this ticker are skipped — so a re-run adds zero
    duplicate rows AND the ``end_date`` seam never double-counts a real live row
    against a historical backfill of the same date (live wins). Append-only. Returns
    a summary dict.
    """
    tk = (ticker or "").upper().strip()
    if end_date is None:
        end_date = datetime.now(timezone.utc).date()
    summary = {
        "ticker": tk, "end_date": end_date.isoformat(),
        "window_months": window_months, "cadence_days": cadence_days,
        "dates_total": 0, "skipped_already_covered": 0, "skipped_no_price": 0,
        "written": 0, "degraded": 0,
    }
    if not tk:
        return summary

    all_dates = _as_of_dates(end_date, window_months=window_months,
                             cadence_days=cadence_days)
    summary["dates_total"] = len(all_dates)

    # Persistent idempotency guard (read-only, G2): skip as-of dates already covered
    # by a record of EITHER origin (live OR backfill) — live wins at the seam.
    covered = aa.covered_vintages(tk, path=archive_path)
    todo = [d for d in all_dates if d.isoformat() not in covered]
    summary["skipped_already_covered"] = len(all_dates) - len(todo)
    if not todo:
        return summary

    loader = data_loader or _default_data_loader
    data = loader(tk) or {}

    records = compute_backfill_records(
        tk, balance_sheet=data.get("balance_sheet"),
        income_stmt=data.get("income_stmt"), cashflow=data.get("cashflow"),
        price_history=data.get("price_history"), as_of_dates=todo,
        sector=data.get("sector"))
    summary["skipped_no_price"] = len(todo) - len(records)

    for rec in records:
        if CAVEAT_BACKFILL_INSUFFICIENT_FUNDAMENTALS in (rec.get("caveats") or []):
            summary["degraded"] += 1
        if aa.append_record(rec, path=archive_path):
            summary["written"] += 1
    return summary
