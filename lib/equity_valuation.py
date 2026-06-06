"""lib/equity_valuation.py — Phase 6C-B app-computed fair value (free sources only).

Standalone fair-value computation module used by the Equity Research page
(``pages/4_Equity.py``) and the Investment Cockpit (``pages/7_Investment_Cockpit.py``).
It blends THREE independent, FREE estimates into a low / mid / high fair-value
range that the Trading Desk (``lib/order_advisor.py``) consumes as its primary
valuation anchor when present:

* **DCF** — a deliberately simplified single-stage Gordon-growth model on a
  per-share trailing-twelve-month free-cash-flow base (documented assumptions:
  ``WACC = 10%``, ``growth_rate = min(earningsGrowth | revenueGrowth | 0.05, 0.15)``).
* **Relative** — ``sector_median_pe × trailing_eps`` (a re-rating to the sector
  median multiple).
* **Analyst** — ``targetMedianPrice`` (preferred) else ``targetMeanPrice``.

Guardrails (Phase 6C-B): yfinance only (no paid API, no key); fail-closed with a
``data_source="fixture"`` fallback that degrades to ``current_price``-anchored
band; no broker / order / execution; no DB / vector store; produces no
``approved_for_execution`` field. The fair value is a deterministic,
code-computed reference — the LLM never produces these numbers (it only debates
them; see :func:`lib.llm_orchestrator.analyze_equity_fair_value_debate`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

_log = logging.getLogger("equity_valuation")

# Documented DCF assumptions (Phase 6C-B). Gordon growth requires growth < WACC;
# the growth cap (15%) is above WACC (10%), so when the resolved growth_rate is
# >= WACC the DCF is treated as not computable (dcf_value = None).
_WACC = 0.10            # fixed discount-rate assumption, documented inline
_GROWTH_CAP = 0.15      # cap the growth_rate at 15%
_GROWTH_DEFAULT = 0.05  # fall back to 5% when no growth field is available
_DCF_YEARS = 5          # single-stage horizon exponent

# Mid-value blend weights (only the present sources contribute; weights are
# renormalized over whatever is available).
_W_DCF = 0.35
_W_RELATIVE = 0.35
_W_ANALYST = 0.30

# Anchor consistency gate (Phase "Valuation stop-the-bleed", Task 1). When the
# spread across the available raw anchors (DCF / relative / analyst, after unit
# sanity) exceeds this max/min ratio they are deemed IRRECONCILABLE and are NOT
# blended into a precise band (averaging garbage with signal — e.g. a $3.23
# relative vs a $112.50 analyst target → a meaningless $53.66 mid). Configurable.
ANCHOR_DISPERSION_THRESHOLD = 3.0

# Blend-state vocabulary (AppFairValue.blend_state).
_BLEND_OK = "blended"
_BLEND_IRRECONCILABLE = "anchors_irreconcilable"
_BLEND_NONE = "no_anchor"

_LIVE = "live"
_FIXTURE = "fixture"
_CACHE_TTL = 3600  # 1 hour, keyed on (ticker, current_price)

# Hardcoded sector → median trailing P/E map (free, deterministic). yfinance
# ``info["sector"]`` labels are used as keys; an unknown sector falls back to the
# default median. Curated June 2026, broadly consistent with long-run sector
# multiples; intentionally conservative.
SECTOR_MEDIAN_PE: dict[str, float] = {
    "Technology": 28.0,
    "Communication Services": 19.0,
    "Consumer Cyclical": 22.0,
    "Consumer Defensive": 20.0,
    "Healthcare": 18.0,
    "Financial Services": 13.0,
    "Industrials": 19.0,
    "Energy": 12.0,
    "Basic Materials": 15.0,
    "Real Estate": 30.0,
    "Utilities": 17.0,
}
_DEFAULT_MEDIAN_PE = 19.0


def get_sector_median_pe(sector: Optional[str]) -> float:
    """Return the hardcoded median trailing P/E for ``sector`` (default if unknown)."""
    return SECTOR_MEDIAN_PE.get(sector or "", _DEFAULT_MEDIAN_PE)


@dataclass
class AppFairValue:
    """App-computed fair value for one ticker (deterministic; no LLM).

    All three source estimates (``dcf_value`` / ``relative_value`` /
    ``analyst_target``) are per-share and may be ``None`` when their inputs are
    unavailable. The ``fair_value_low <= fair_value_mid <= fair_value_high``
    invariant always holds. Review-only: no ``approved_for_execution`` field.
    """

    ticker: str = ""
    dcf_value: Optional[float] = None
    relative_value: Optional[float] = None
    analyst_target: Optional[float] = None
    analyst_count: int = 0
    fair_value_low: float = 0.0
    fair_value_mid: float = 0.0
    fair_value_high: float = 0.0
    confidence: str = "low"  # high | medium | low
    upside_pct: float = 0.0
    methodology: str = ""
    computed_at: str = ""
    data_source: str = _FIXTURE  # live | fixture
    dcf_note: str = ""  # DCF source detail, or the reason dcf_value is None
    # --- Anchor consistency gate (Task 1) ---------------------------------
    # "blended" — normal weighted band; "anchors_irreconcilable" — the raw
    # anchors disagreed beyond ANCHOR_DISPERSION_THRESHOLD so NO band was
    # produced (low/mid/high are 0.0, confidence forced low); "no_anchor" — no
    # DCF/relative/analyst input at all (band anchored on current price).
    blend_state: str = _BLEND_OK
    anchor_dispersion: Optional[float] = None  # max/min ratio across raw anchors
    # Side-by-side anchors for honest display when irreconcilable. Each item:
    # {"name": str, "value": float, "basis": str}.
    anchors: list = field(default_factory=list)
    # --- Basis flags (Task 2) ---------------------------------------------
    # relative_basis: "forward" (forwardEps) | "trailing_fallback" (trailingEps).
    # peer_pe_basis: "mixed" when forward EPS is multiplied by a trailing sector
    # median P/E (the hardcoded map is trailing) | "trailing" | "".
    relative_basis: str = ""
    peer_pe_basis: str = ""


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def _finite_pos(x) -> Optional[float]:
    """Return ``x`` as a positive finite float, else ``None`` (rejects NaN / <= 0)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    if xf != xf or xf <= 0:
        return None
    return xf


def _finite(x) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    return None if xf != xf else xf


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Pure assembler (no I/O) — used directly by tests
# ---------------------------------------------------------------------------


def build_app_fair_value(
    ticker: str,
    current_price: float,
    dcf_value: Optional[float],
    relative_value: Optional[float],
    analyst_target: Optional[float],
    analyst_count: int = 0,
    data_source: str = _FIXTURE,
    dcf_source: str = "",
    dcf_note: str = "",
    relative_basis: str = "",
    peer_pe_basis: str = "",
) -> AppFairValue:
    """Assemble an :class:`AppFairValue` from the three source estimates (pure).

    Always returns a well-formed result with
    ``fair_value_low <= fair_value_mid <= fair_value_high``. When all three
    sources are ``None`` the band is anchored on ``current_price``
    (0.85 / 1.00 / 1.15) and confidence is ``low`` (``blend_state="no_anchor"``).

    **Anchor consistency gate (Task 1):** before blending, the spread across the
    available raw anchors is measured (``anchor_dispersion`` = max/min). When two
    or more anchors disagree by more than :data:`ANCHOR_DISPERSION_THRESHOLD`
    they are NOT blended — the band collapses to ``0.0`` (so no consumer mistakes
    it for precision), ``confidence`` is forced ``low``, and ``blend_state`` is
    ``anchors_irreconcilable``. The ``anchors`` list always carries each present
    anchor with its value + basis for honest side-by-side display.
    """
    cp = _finite_pos(current_price) or 0.0
    dcf = _finite_pos(dcf_value)
    rel = _finite_pos(relative_value)
    ana = _finite_pos(analyst_target)
    try:
        a_count = int(analyst_count or 0)
    except (TypeError, ValueError):
        a_count = 0

    # --- Side-by-side anchor list + dispersion (unit-sane positive anchors) -
    anchors: list = []
    if dcf is not None:
        anchors.append({"name": "dcf", "value": round(dcf, 2),
                        "basis": (dcf_source or "dcf")})
    if rel is not None:
        anchors.append({"name": "relative", "value": round(rel, 2),
                        "basis": (relative_basis or "relative")})
    if ana is not None:
        anchors.append({"name": "analyst", "value": round(ana, 2),
                        "basis": f"analyst (n={a_count})"})
    anchor_values = [a["value"] for a in anchors]
    anchor_dispersion: Optional[float] = None
    if len(anchor_values) >= 2:
        lo_a, hi_a = min(anchor_values), max(anchor_values)
        if lo_a > 0:
            anchor_dispersion = round(hi_a / lo_a, 4)
    irreconcilable = (anchor_dispersion is not None
                      and anchor_dispersion > ANCHOR_DISPERSION_THRESHOLD)

    if irreconcilable:
        # Do NOT blend irreconcilable anchors into a fake band. Present each
        # anchor separately (anchors list), force low confidence, suppress the
        # range. Downstream LONG entry logic degrades to "technical only".
        parts = ", ".join(f"{a['name']} ${a['value']:.2f}" for a in anchors)
        methodology = (
            "Anchors irreconcilable (dispersion "
            f"{anchor_dispersion:.1f}× > {ANCHOR_DISPERSION_THRESHOLD:.0f}×): "
            f"{parts}. Not blended — each shown separately. / "
            f"估值锚不一致（离散度 {anchor_dispersion:.1f}× > "
            f"{ANCHOR_DISPERSION_THRESHOLD:.0f}×）：{parts}。不做融合，分别列示。"
        )
        return AppFairValue(
            ticker=(ticker or "").upper().strip(),
            dcf_value=(round(dcf, 2) if dcf is not None else None),
            relative_value=(round(rel, 2) if rel is not None else None),
            analyst_target=(round(ana, 2) if ana is not None else None),
            analyst_count=a_count,
            fair_value_low=0.0,
            fair_value_mid=0.0,
            fair_value_high=0.0,
            confidence="low",
            upside_pct=0.0,
            methodology=methodology,
            computed_at=_now_iso(),
            data_source=data_source,
            dcf_note=dcf_note,
            blend_state=_BLEND_IRRECONCILABLE,
            anchor_dispersion=anchor_dispersion,
            anchors=anchors,
            relative_basis=relative_basis,
            peer_pe_basis=peer_pe_basis,
        )

    # --- fair_value_low: min of discounted non-None sources ----------------
    low_candidates = []
    if dcf is not None:
        low_candidates.append(dcf * 0.85)
    if rel is not None:
        low_candidates.append(rel * 0.90)
    if ana is not None:
        low_candidates.append(ana * 0.80)
    fair_value_low = min(low_candidates) if low_candidates else (cp * 0.85 if cp else 0.0)

    # --- fair_value_mid: weighted average of raw non-None sources ----------
    mid_num = 0.0
    mid_den = 0.0
    if dcf is not None:
        mid_num += dcf * _W_DCF
        mid_den += _W_DCF
    if rel is not None:
        mid_num += rel * _W_RELATIVE
        mid_den += _W_RELATIVE
    if ana is not None:
        mid_num += ana * _W_ANALYST
        mid_den += _W_ANALYST
    fair_value_mid = (mid_num / mid_den) if mid_den > 0 else (cp if cp else 0.0)

    # --- fair_value_high: max of premium non-None sources ------------------
    high_candidates = []
    if dcf is not None:
        high_candidates.append(dcf * 1.10)
    if rel is not None:
        high_candidates.append(rel * 1.05)
    if ana is not None:
        high_candidates.append(ana * 1.05)
    fair_value_high = max(high_candidates) if high_candidates else (cp * 1.15 if cp else 0.0)

    # Defensive ordering guarantee (the math above already preserves it, but
    # round-off / degenerate inputs are clamped here so the invariant is hard).
    fair_value_low = round(fair_value_low, 2)
    fair_value_mid = round(max(fair_value_mid, fair_value_low), 2)
    fair_value_high = round(max(fair_value_high, fair_value_mid), 2)

    # --- confidence --------------------------------------------------------
    source_count = sum(v is not None for v in (dcf, rel, ana))
    spread = ((fair_value_high - fair_value_low) / fair_value_mid) if fair_value_mid > 0 else 1.0
    if source_count == 3 and spread < 0.40:
        confidence = "high"
    elif source_count >= 2 or (source_count >= 1 and spread < 0.60):
        confidence = "medium"
    else:
        confidence = "low"

    upside_pct = ((fair_value_mid - cp) / cp) if cp > 0 else 0.0

    used = []
    if dcf is not None:
        used.append(f"DCF [{dcf_source}]" if dcf_source else "DCF")
    if rel is not None:
        used.append("relative (sector P/E)")
    if ana is not None:
        used.append(f"analyst target (n={a_count})")
    if used:
        methodology = "Fair value blends " + ", ".join(used) + "."
    else:
        methodology = (
            "No DCF / relative / analyst inputs available — band anchored on "
            "current price (low confidence)."
        )
    if dcf is None and dcf_note:
        methodology = methodology + " " + dcf_note

    blend_state = _BLEND_OK if source_count >= 1 else _BLEND_NONE

    return AppFairValue(
        ticker=(ticker or "").upper().strip(),
        dcf_value=(round(dcf, 2) if dcf is not None else None),
        relative_value=(round(rel, 2) if rel is not None else None),
        analyst_target=(round(ana, 2) if ana is not None else None),
        analyst_count=a_count,
        fair_value_low=fair_value_low,
        fair_value_mid=fair_value_mid,
        fair_value_high=fair_value_high,
        confidence=confidence,
        upside_pct=round(upside_pct, 4),
        methodology=methodology,
        computed_at=_now_iso(),
        data_source=data_source,
        dcf_note=dcf_note,
        blend_state=blend_state,
        anchor_dispersion=anchor_dispersion,
        anchors=anchors,
        relative_basis=relative_basis,
        peer_pe_basis=peer_pe_basis,
    )


# ---------------------------------------------------------------------------
# Raw input fetch (yfinance only; fail-closed) — patched by tests
# ---------------------------------------------------------------------------


def _fetch_raw(ticker: str) -> dict:
    """Fetch the raw fair-value inputs for ``ticker`` from yfinance (fail-closed).

    Returns a dict with ``fcf_ttm`` / ``shares`` / ``growth_rate`` /
    ``trailing_eps`` / ``sector`` / ``analyst_median`` / ``analyst_mean`` /
    ``analyst_count`` / ``live``. Any missing piece is ``None`` (or ``0`` for the
    count). Never raises.
    """
    out = {
        "fcf_ttm": None,
        "fcf_source": "",
        "ebitda": None,
        "shares": None,
        "growth_rate": None,
        "trailing_eps": None,
        "forward_eps": None,
        "sector": None,
        "analyst_median": None,
        "analyst_mean": None,
        "analyst_count": 0,
        "live": False,
    }
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        info = tk.info if isinstance(getattr(tk, "info", None), dict) else {}
        if info:
            out["live"] = True

        out["sector"] = info.get("sector")
        out["trailing_eps"] = _finite(info.get("trailingEps"))
        # Forward consensus EPS (preferred basis for the relative anchor, Task 2).
        out["forward_eps"] = _finite(info.get("forwardEps"))
        out["shares"] = _finite_pos(info.get("sharesOutstanding"))
        out["analyst_median"] = _finite_pos(info.get("targetMedianPrice"))
        out["analyst_mean"] = _finite_pos(info.get("targetMeanPrice"))
        try:
            out["analyst_count"] = int(info.get("numberOfAnalystOpinions") or 0)
        except (TypeError, ValueError):
            out["analyst_count"] = 0

        # growth_rate = min(earningsGrowth | revenueGrowth | 0.05, 0.15)
        g = _finite(info.get("earningsGrowth"))
        if g is None:
            g = _finite(info.get("revenueGrowth"))
        if g is None:
            g = _GROWTH_DEFAULT
        out["growth_rate"] = min(g, _GROWTH_CAP)

        out["ebitda"] = _finite(info.get("ebitda"))
        # TTM free cash flow via a documented fallback chain (see
        # :func:`_fcf_with_source`); the chosen source is recorded for the
        # methodology string.
        out["fcf_ttm"], out["fcf_source"] = _fcf_with_source(tk, info)
    except Exception:  # noqa: BLE001 — fail-closed (no live info)
        return out
    return out


def _fcf_with_source(tk, info: dict) -> tuple:
    """Return ``(fcf_ttm, source_label)`` via a documented fallback chain (fail-closed):

    1. cashflow statement — the ``Free Cash Flow`` row (TTM) if present, else
       ``Σ_last4q(operating CF) − |Σ_last4q(CapEx)|``,
    2. yfinance ``freeCashflow`` (used directly if non-None and non-zero),
    3. yfinance ``operatingCashflow`` alone (proxy; no CapEx),
    4. ``ebitda × 0.6`` (rough proxy),
    5. otherwise ``(None, "")``.

    Each level logs success (``logging.info``) or failure (``logging.warning``) so
    it is clear which source actually supplied the FCF.
    """
    # 1. Quarterly cashflow statement (4 quarters → TTM).
    try:
        qcf = getattr(tk, "quarterly_cashflow", None)
        if qcf is not None and not getattr(qcf, "empty", True):
            def _row_sum(names, n=4):
                for nm in names:
                    if nm in qcf.index:
                        vals = []
                        for c in list(qcf.columns)[:n]:
                            v = _finite(qcf.loc[nm, c])
                            if v is not None:
                                vals.append(v)
                        if vals:
                            return sum(vals)
                return None

            # yfinance's cashflow statement usually carries a literal
            # "Free Cash Flow" row — read it directly first.
            fcf_row = _row_sum(["Free Cash Flow", "FreeCashFlow"])
            if fcf_row is not None:
                src = "cashflow statement (Free Cash Flow, TTM)"
                _log.info("FCF source: %s, value: %s", src, fcf_row)
                return fcf_row, src
            ocf = _row_sum(["Operating Cash Flow", "Total Cash From Operating Activities"])
            capex = _row_sum(["Capital Expenditure", "Capital Expenditures"])
            if ocf is not None and capex is not None:
                src = "cashflow statement (OCF − CapEx, TTM)"
                val = ocf - abs(capex)
                _log.info("FCF source: %s, value: %s", src, val)
                return val, src
            _log.warning("FCF level 1 failed: no Free Cash Flow / OCF+CapEx rows in "
                         "quarterly cashflow")
        else:
            _log.warning("FCF level 1 failed: quarterly_cashflow empty/unavailable")
    except Exception as exc:  # noqa: BLE001 — fall through
        _log.warning("FCF level 1 failed: %s", exc)
    # 2. info-level freeCashflow — use directly if non-None and non-zero.
    try:
        fcf = _finite(info.get("freeCashflow"))
        if fcf is not None and fcf != 0:
            src = "yfinance freeCashflow"
            _log.info("FCF source: %s, value: %s", src, fcf)
            return fcf, src
        _log.warning("FCF level 2 failed: freeCashflow None/0")
    except Exception as exc:  # noqa: BLE001
        _log.warning("FCF level 2 failed: %s", exc)
    # 3. operatingCashflow alone (proxy; CapEx unavailable at info level).
    try:
        ocf = _finite(info.get("operatingCashflow"))
        if ocf is not None and ocf != 0:
            src = "operatingCashflow proxy (no CapEx)"
            _log.info("FCF source: %s, value: %s", src, ocf)
            return ocf, src
        _log.warning("FCF level 3 failed: operatingCashflow None/0")
    except Exception as exc:  # noqa: BLE001
        _log.warning("FCF level 3 failed: %s", exc)
    # 4. EBITDA × 0.6 rough proxy.
    try:
        ebitda = _finite(info.get("ebitda"))
        if ebitda is not None and ebitda != 0:
            val = ebitda * 0.6
            src = "EBITDA × 0.6 proxy"
            _log.info("FCF source: %s, value: %s", src, val)
            return val, src
        _log.warning("FCF level 4 failed: ebitda None/0")
    except Exception as exc:  # noqa: BLE001
        _log.warning("FCF level 4 failed: %s", exc)
    # 5. nothing usable.
    _log.warning("FCF level 5: no usable FCF/EBITDA source")
    return None, ""


# ---------------------------------------------------------------------------
# compute_app_fair_value — cached, fail-closed
# ---------------------------------------------------------------------------


def _compute_dcf_per_share(raw: dict) -> Optional[float]:
    """Simplified single-stage Gordon-growth DCF, per share (fail-closed -> None).

    ``dcf = (fcf_per_share × (1 + g)^5) / (WACC − g)``; returns ``None`` when the
    FCF base, shares, or ``WACC − g`` denominator is unavailable / non-positive.
    """
    fcf = _finite(raw.get("fcf_ttm"))
    shares = _finite_pos(raw.get("shares"))
    g = _finite(raw.get("growth_rate"))
    if fcf is None or fcf <= 0 or shares is None or g is None:
        return None
    denom = _WACC - g
    if denom <= 0:  # growth >= WACC -> Gordon growth undefined; not computable
        return None
    fcf_ps = fcf / shares
    if fcf_ps <= 0:
        return None
    value = fcf_ps * ((1.0 + g) ** _DCF_YEARS) / denom
    if value != value or value <= 0:  # NaN / non-positive
        return None
    return round(value, 2)


def _compute_cached(ticker: str, current_price: float,
                    dcf_override: Optional[float] = None) -> AppFairValue:
    """Cached worker (fail-closed). Separated so ``st.cache_data`` can wrap it.

    ``dcf_override`` (per-share, > 0) replaces the internal Gordon-growth DCF —
    used by the Equity page "Update Valuation" action to feed a user-adjusted DCF
    intrinsic value from the Financials tab.
    """
    raw = _fetch_raw(ticker)

    if dcf_override is not None and dcf_override > 0:
        dcf_value = round(float(dcf_override), 2)
        dcf_source = "user DCF (Financials tab)"
        dcf_note = dcf_source
    else:
        dcf_value = _compute_dcf_per_share(raw)
        _fcf_src = raw.get("fcf_source") or ""
        if dcf_value is not None:
            dcf_source = _fcf_src
            dcf_note = f"DCF FCF source: {_fcf_src}" if _fcf_src else ""
        else:
            dcf_source = ""
            if raw.get("fcf_ttm") is None:
                dcf_note = "FCF data unavailable / 现金流数据不可用"
            else:
                dcf_note = (
                    "DCF not computable (shares missing or growth ≥ WACC) / "
                    "DCF 无法计算"
                )

    # relative_value = sector_median_pe × EPS. Prefer FORWARD consensus EPS
    # (Task 2); fall back to trailing EPS with a basis flag. The sector median
    # P/E is a trailing-basis hardcoded map, so a forward-EPS relative is flagged
    # peer_pe_basis="mixed" (forward earnings × trailing multiple).
    relative_value: Optional[float] = None
    relative_basis = ""
    peer_pe_basis = ""
    fwd_eps = _finite_pos(raw.get("forward_eps"))
    eps = _finite_pos(raw.get("trailing_eps"))
    chosen_eps = fwd_eps if fwd_eps is not None else eps
    if chosen_eps is not None:
        relative_value = round(get_sector_median_pe(raw.get("sector")) * chosen_eps, 2)
        relative_basis = "forward" if fwd_eps is not None else "trailing_fallback"
        peer_pe_basis = "mixed" if fwd_eps is not None else "trailing"

    # analyst_target = targetMedianPrice if available else targetMeanPrice
    analyst_target = raw.get("analyst_median") or raw.get("analyst_mean")

    data_source = _LIVE if raw.get("live") else _FIXTURE
    return build_app_fair_value(
        ticker=ticker,
        current_price=current_price,
        dcf_value=dcf_value,
        relative_value=relative_value,
        analyst_target=analyst_target,
        analyst_count=raw.get("analyst_count", 0),
        data_source=data_source,
        dcf_source=dcf_source,
        dcf_note=dcf_note,
        relative_basis=relative_basis,
        peer_pe_basis=peer_pe_basis,
    )


def compute_app_fair_value(ticker: str, current_price: float, *,
                           dcf_override: Optional[float] = None) -> AppFairValue:
    """Compute the :class:`AppFairValue` for ``ticker`` (yfinance only; fail-closed).

    Cached TTL=3600 keyed on ``(ticker, current_price, dcf_override)``. When
    ``dcf_override`` (a per-share intrinsic value, > 0) is supplied it replaces the
    internal DCF (e.g. a user-adjusted DCF from the Financials tab). On ANY
    failure a well-formed ``data_source="fixture"`` result anchored on
    ``current_price`` is returned — this function never raises.
    """
    t = (ticker or "").upper().strip()
    cp = _finite_pos(current_price) or 0.0
    ov: Optional[float] = None
    if dcf_override is not None:
        try:
            ov = float(dcf_override)
            ov = ov if ov > 0 else None
        except (TypeError, ValueError):
            ov = None
    try:
        return _compute_cached(t, round(cp, 4), ov)
    except Exception:  # noqa: BLE001 — fully fail-closed
        return build_app_fair_value(
            ticker=t,
            current_price=cp if cp > 0 else 100.0,
            dcf_value=None,
            relative_value=None,
            analyst_target=None,
            analyst_count=0,
            data_source=_FIXTURE,
        )


def store_equity_research_result(
    ticker: str,
    fair_value: AppFairValue,
    debate_summary: str = "",
    analyst_action: str = "",
) -> None:
    """Write the fair-value summary into ``st.session_state["equity_research_results"]``.

    Review-only hand-off consumed by ``lib/order_advisor.py`` (the Trading Desk
    primary valuation anchor). Fail-closed: a missing Streamlit runtime never
    raises to the caller. The session dict lives only in the browser session;
    additionally the anchor is **written through** to the local
    ``data/anchor_cache.json`` (network-free) so the Investment Cockpit
    long-horizon enrichment can read it later without any fetch.
    """
    t = (ticker or "").upper().strip()
    if not t or fair_value is None:
        return

    # Write-through to the local anchor cache (independent of Streamlit; the
    # Cockpit reads this on its network-free enrichment path). Fail-closed.
    try:
        from lib.anchor_cache import write_app_fair_value

        write_app_fair_value(fair_value)
    except Exception:  # noqa: BLE001 — cache write is best-effort
        pass

    try:
        import streamlit as st

        results = dict(st.session_state.get("equity_research_results", {}) or {})
        results[t] = {
            "fair_value_low": fair_value.fair_value_low,
            "fair_value_mid": fair_value.fair_value_mid,
            "fair_value_high": fair_value.fair_value_high,
            "confidence": fair_value.confidence,
            "methodology": fair_value.methodology,
            "upside_pct": fair_value.upside_pct,
            # Anchor consistency state (Task 1) so the Trading Desk LONG path can
            # degrade explicitly instead of silently using a blended mid.
            "blend_state": getattr(fair_value, "blend_state", "blended"),
            "debate_summary": debate_summary or "",
            "analyst_action": analyst_action or "",
            "computed_at": fair_value.computed_at,
        }
        st.session_state["equity_research_results"] = results
    except Exception:  # noqa: BLE001 — fail-closed (no Streamlit runtime)
        return


# Decorate the cached worker with st.cache_data when Streamlit is importable
# (the body is fail-closed, so offline tests simply execute it once per call).
try:  # pragma: no cover - cache decoration is environment dependent
    import streamlit as _st

    _compute_cached = _st.cache_data(ttl=_CACHE_TTL, show_spinner=False)(_compute_cached)
except Exception:  # noqa: BLE001
    pass
