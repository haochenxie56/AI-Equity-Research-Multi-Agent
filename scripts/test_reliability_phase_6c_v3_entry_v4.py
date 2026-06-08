#!/usr/bin/env python3
"""
scripts/test_reliability_phase_6c_v3_entry_v4.py

Phase 6C-A v3 — Entry Strategy v4 test suite (mock-only / offline).

Runs entirely WITHOUT real API calls: ANTHROPIC_API_KEY / FINNHUB_API_KEY are
forced empty, and the yfinance / technical / valuation-anchor fetches plus the
portfolio persistence layer are patched so every computation exercises the
deterministic / fail-closed branches.

It verifies the Entry Strategy v4 architecture in ``lib/valuation_anchor.py`` +
``lib/order_advisor.py`` + ``lib/holdings.py``:

  * Three-tier valuation confidence (high / medium / low) with the analyst-count,
    dispersion, and anchor-spread checks; ``analyst_anchor`` prefers
    ``targetMedianPrice`` over ``targetMeanPrice``.
  * LONG entry-zone high per confidence tier (conservative_anchor × 0.90 high;
    analyst_anchor × 0.85 medium; no zone for low).
  * SHORT add never averages down a losing position; MID add can
    ``average_down_small`` with an intact thesis; LONG add requires thesis intact;
    LONG add valuation-based sizing (``add_partial`` / ``add_tiny``).
  * The Existing Position Risk Overlay (position limit + share-count sizing),
    the ``valuation_percentile ≥ 0.85`` soft warning, ``approved_for_execution``
    always False, PortfolioSettings persistence, and the Trading Desk settings
    expander.

Usage:
    python3 -B scripts/test_reliability_phase_6c_v3_entry_v4.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd  # noqa: E402

import lib.order_advisor as oa  # noqa: E402
import lib.valuation_anchor as va  # noqa: E402
import lib.equity_valuation as eqv  # noqa: E402
import lib.holdings as holds  # noqa: E402


PASS = 0
FAIL = 0
_failures: list = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


def _read(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _dummy_df(n: int = 40) -> pd.DataFrame:
    rows = []
    for i in range(n):
        c = 100.0 + (i % 5)
        rows.append([c * 0.99, c * 1.02, c * 0.97, c, 1_000_000.0])
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])


def _snap(price, *, ema10=None, ema20=None, sma50=None, sma200=None, rsi=None,
          adx=None, vol_ratio=None, nearest_support=None, nearest_resistance=None,
          candle="none", atr=None):
    return {
        "price": price, "EMA_10": ema10, "EMA_20": ema20, "SMA_50": sma50,
        "SMA_200": sma200, "RSI_14": rsi, "ADX": adx,
        "ATR_14": atr if atr is not None else round(price * 0.03, 2),
        "Vol_ratio_20d": vol_ratio,
        "above_SMA200": bool(price > (sma200 or 0)),
        "pct_from_52w_high": -5.0,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "candlestick_pattern": candle,
    }


@contextmanager
def _patched(snap: dict, fva_obj=None):
    # Anchor Intel v2 (U1): order_advisor consumes the unified
    # lib.equity_valuation.compute_app_fair_value (AppFairValue) — patch THAT. The
    # default stand-in is a low-confidence no_anchor band (no LONG zone).
    if fva_obj is None:
        fva_obj = eqv.AppFairValue(ticker="MU", fair_value_low=80.0,
                                   fair_value_mid=85.0, fair_value_high=95.0,
                                   confidence="low", blend_state="no_anchor",
                                   data_source="fixture")
    with mock.patch("ui_utils.load_ohlcv", return_value=_dummy_df()), \
            mock.patch("lib.technical.snapshot", return_value=snap), \
            mock.patch("lib.equity_valuation.compute_app_fair_value",
                       return_value=fva_obj):
        yield


@contextmanager
def _patched_portfolio(holdings_list, cash=0.0,
                       settings: "holds.PortfolioSettings | None" = None):
    settings = settings or holds.PortfolioSettings()
    with mock.patch("lib.holdings.load_holdings", return_value=list(holdings_list)), \
            mock.patch("lib.holdings.load_cash_position", return_value=float(cash)), \
            mock.patch("lib.holdings.load_portfolio_settings", return_value=settings):
        yield


class _H:
    """Minimal holding stand-in (shares > 0 + cost_basis > 0 => 'add' scenario)."""

    def __init__(self, cost_basis, horizon, shares=10.0, ticker="MU"):
        self.ticker = ticker
        self.cost_basis = cost_basis
        self.horizon = horizon
        self.shares = shares
        self.status = "active"


# ---------------------------------------------------------------------------
# Section 1 — FairValueAnchor three-tier confidence
# ---------------------------------------------------------------------------

def _fva_with(info: dict, pe_median, ticker: str, cp: float = 200.0, vp: float = 0.3):
    mock_ticker = mock.MagicMock()
    mock_ticker.info = info
    with mock.patch("yfinance.Ticker", return_value=mock_ticker), \
            mock.patch.object(va, "_median_trailing_pe", return_value=pe_median):
        return va.compute_fair_value_anchor(ticker, cp, vp)


# HIGH: both anchors, count>=5, dispersion<=0.30, spread<=0.30.
_hi = _fva_with(
    {"targetMeanPrice": 125.0, "targetMedianPrice": 120.0, "targetHighPrice": 130.0,
     "targetLowPrice": 110.0, "numberOfAnalystOpinions": 10, "trailingEps": 5.0},
    pe_median=24.0, ticker="CONFHI",
)
check("1.1 FairValueAnchor confidence == high when all conditions met",
      _hi.confidence == "high", detail=f"{_hi.confidence} spread={_hi.anchor_spread} disp={_hi.dispersion}")
check("1.2 analyst_anchor uses targetMedianPrice over targetMeanPrice",
      _hi.analyst_anchor == 120.0, detail=str(_hi.analyst_anchor))
check("1.3 high conservative_anchor == min(analyst, relative)",
      _hi.conservative_anchor == 120.0, detail=str(_hi.conservative_anchor))

# MEDIUM: anchor_spread > 0.30 (analyst 120 vs relative 80), count>=3, dispersion<=0.50.
_med = _fva_with(
    {"targetMeanPrice": 120.0, "targetMedianPrice": 120.0, "targetHighPrice": 132.0,
     "targetLowPrice": 108.0, "numberOfAnalystOpinions": 4, "trailingEps": 5.0},
    pe_median=16.0, ticker="CONFMED",
)
check("1.4 FairValueAnchor confidence == medium when anchor_spread > 0.30",
      _med.confidence == "medium",
      detail=f"{_med.confidence} spread={_med.anchor_spread}")
check("1.5 medium conservative_anchor == analyst_anchor",
      _med.conservative_anchor == 120.0, detail=str(_med.conservative_anchor))

# LOW: analyst_count < 3.
_lo = _fva_with(
    {"targetMeanPrice": 120.0, "targetMedianPrice": 120.0, "targetHighPrice": 130.0,
     "targetLowPrice": 110.0, "numberOfAnalystOpinions": 2, "trailingEps": 5.0},
    pe_median=24.0, ticker="CONFLOW",
)
check("1.6 FairValueAnchor confidence == low when analyst_count < 3",
      _lo.confidence == "low", detail=f"{_lo.confidence} count={_lo.analyst_count}")
check("1.7 low conservative_anchor is None", _lo.conservative_anchor is None,
      detail=str(_lo.conservative_anchor))


# ---------------------------------------------------------------------------
# Section 2 — LONG entry-zone high per confidence tier
# ---------------------------------------------------------------------------

# MIGRATION (Anchor Intel v2 U1): the LONG three-tier now consumes the unified
# AppFairValue (high tier anchor = fair_value_mid, medium tier = analyst_target).
# Entry-zone FORMULAS are unchanged (×0.90 high, ×0.85 medium), so the expected
# numbers are IDENTICAL to the retired FairValueAnchor fixtures — only the object
# type + mocked producer changed: high mid=120 -> 120×0.90 = 108 (was
# conservative_anchor=120 -> 108); medium analyst_target=120 -> 120×0.85 = 102
# (was analyst_anchor=120 -> 102).
_fva_hi = eqv.AppFairValue(ticker="MU", confidence="high", blend_state="blended",
                           fair_value_low=110.0, fair_value_mid=120.0,
                           fair_value_high=140.0, analyst_target=120.0,
                           data_source="fixture")
with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0), fva_obj=_fva_hi), \
        _patched_portfolio([]):
    r = oa.compute_price_levels("MU", None, horizon="long", valuation_percentile=0.3)
check("2.1 LONG high-conf entry_zone_high == fair_value_mid × 0.90 (was conservative×0.90)",
      r.entry_zone_high is not None and abs(r.entry_zone_high - 108.0) < 0.5,
      detail=str(r.entry_zone_high))
check("2.1b LONG high-conf valuation_confidence surfaced",
      r.valuation_confidence == "high", detail=r.valuation_confidence)

_fva_med = eqv.AppFairValue(ticker="MU", confidence="medium", blend_state="blended",
                            fair_value_low=115.0, fair_value_mid=130.0,
                            fair_value_high=150.0, analyst_target=120.0,
                            data_source="fixture")
with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0), fva_obj=_fva_med), \
        _patched_portfolio([]):
    r = oa.compute_price_levels("MU", None, horizon="long", valuation_percentile=0.3)
check("2.2 LONG medium-conf entry_zone_high == analyst_target × 0.85 (was analyst_anchor×0.85)",
      r.entry_zone_high is not None and abs(r.entry_zone_high - 102.0) < 0.5,
      detail=str(r.entry_zone_high))

_fva_low = eqv.AppFairValue(ticker="MU", confidence="low", blend_state="no_anchor",
                            fair_value_mid=85.0, data_source="fixture")
with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0), fva_obj=_fva_low), \
        _patched_portfolio([]):
    r = oa.compute_price_levels("MU", None, horizon="long", valuation_percentile=0.3)
check("2.3 LONG low-conf entry_zone is None",
      r.entry_zone_low is None and r.entry_zone_high is None,
      detail=f"{r.entry_zone_low}-{r.entry_zone_high}")


# ---------------------------------------------------------------------------
# Section 3 — LONG valuation soft warning (>= 0.85) does NOT block at engine level
# ---------------------------------------------------------------------------

_tech_soft = {
    "current_price": 100.0, "atr": 3.0, "ema10": None, "ema20": None, "sma50": None,
    "sma200": 80.0, "nearest_support": None, "fair_value_anchor": 108.0,
    "vol_ratio": 1.0, "fva_obj": _fva_hi, "valuation_percentile": 0.85,
}
_soft_logic = oa._compute_initiate_logic("long", _tech_soft)
check("3.1 valuation_percentile >= 0.85 adds a soft risk_note warning",
      "0.85" in (_soft_logic.get("risk_note") or ""), detail=str(_soft_logic.get("risk_note")))
check("3.2 soft warning does NOT block (zone still present)",
      _soft_logic.get("entry_zone_low") is not None, detail=str(_soft_logic.get("entry_zone_low")))


# ---------------------------------------------------------------------------
# Section 4 — SHORT add (never average down a loser) / proceeds when in profit
# ---------------------------------------------------------------------------

with _patched(_snap(100.0, ema10=100.0, ema20=99.0, rsi=55.0, vol_ratio=1.5,
                    nearest_support=99.0)), _patched_portfolio([]):
    r = oa.compute_price_levels("MU", _H(110.0, "short"), horizon="short")
check("4.1 SHORT add action == wait_or_cut when price < cost_basis",
      r.action == "wait_or_cut", detail=r.action)
check("4.1b SHORT add never produces an entry zone for a loser",
      r.entry_zone_low is None, detail=str(r.entry_zone_low))

with _patched(_snap(100.0, ema10=100.0, ema20=99.0, rsi=55.0, vol_ratio=1.5,
                    nearest_support=99.0)), _patched_portfolio([]):
    r = oa.compute_price_levels("MU", _H(95.0, "short"), horizon="short")
check("4.2 SHORT add proceeds to zone engine when price >= cost_basis",
      r.action != "wait_or_cut" and r.entry_zone_low is not None,
      detail=f"{r.action} zone={r.entry_zone_low}")


# ---------------------------------------------------------------------------
# Section 5 — MID add average_down_small / LONG add thesis + valuation sizing
# ---------------------------------------------------------------------------

with _patched(_snap(100.0, sma50=96.0, sma200=80.0, rsi=55.0, vol_ratio=1.5)), \
        _patched_portfolio([]):
    r = oa.compute_price_levels("MU", _H(110.0, "mid"), horizon="mid",
                                thesis_status="intact",
                                eps_revision_direction="improving")
check("5.1 MID add average_down_small (price<cost, intact, eps not deteriorating)",
      r.action == "average_down_small", detail=r.action)

with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=0.8)), _patched_portfolio([]):
    r = oa.compute_price_levels("MU", _H(120.0, "long"), horizon="long",
                                thesis_status="weakening")
check("5.2 LONG add action == wait when thesis_status != intact", r.action == "wait",
      detail=r.action)

# LONG add add_partial (val_pct < 0.50) — overlay must PASS so the action stays.
_h_lp = _H(95.0, "long", shares=1.0)
with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=0.8)), \
        _patched_portfolio([_h_lp], cash=100_000.0):
    r = oa.compute_price_levels("MU", _h_lp, horizon="long", thesis_status="intact",
                                valuation_percentile=0.30)
check("5.3 LONG add action == add_partial when val_pct < 0.50", r.action == "add_partial",
      detail=r.action)
check("5.4 add position_sizing includes a share-count estimate",
      "shares" in (r.position_sizing or ""), detail=r.position_sizing)
check("5.4b add risk_overlay_passed True when within limits",
      r.risk_overlay_passed is True, detail=r.risk_overlay_note)

# LONG add add_tiny (0.50 <= val_pct < 0.70).
_h_lt = _H(95.0, "long", shares=1.0)
with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=0.8)), \
        _patched_portfolio([_h_lt], cash=100_000.0):
    r = oa.compute_price_levels("MU", _h_lt, horizon="long", thesis_status="intact",
                                valuation_percentile=0.60)
check("5.5 LONG add action == add_tiny when 0.50 <= val_pct < 0.70", r.action == "add_tiny",
      detail=r.action)


# ---------------------------------------------------------------------------
# Section 6 — Risk overlay at the position limit
# ---------------------------------------------------------------------------

_h_max = _H(95.0, "long", shares=200.0)  # 200 × $100 = $20k already; max 15% of $20k
with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=0.8)), \
        _patched_portfolio([_h_max], cash=0.0):
    r = oa.compute_price_levels("MU", _h_max, horizon="long", thesis_status="intact",
                                valuation_percentile=0.30)
check("6.1 risk_overlay_passed == False when portfolio at max limit",
      r.risk_overlay_passed is False, detail=f"{r.risk_overlay_passed} {r.risk_overlay_note}")
check("6.2 overlay block overrides action to hold", r.action == "hold", detail=r.action)
check("6.3 overlay note populated when blocked", bool(r.risk_overlay_note),
      detail=r.risk_overlay_note)


# ---------------------------------------------------------------------------
# Section 7 — approved_for_execution always False
# ---------------------------------------------------------------------------

_approved_ok = True
_cases = [
    (_snap(100.0, sma50=96.0, sma200=80.0, rsi=55.0, vol_ratio=1.5), "mid"),
    (_snap(100.0, ema10=100.0, ema20=99.0, rsi=55.0, vol_ratio=1.5, nearest_support=99.0), "short"),
    (_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0), "long"),
]
for s, hz in _cases:
    with _patched(s, fva_obj=_fva_hi), _patched_portfolio([]):
        r1 = oa.compute_price_levels("MU", None, horizon=hz)
        r2 = oa.compute_price_levels("MU", _H(100.0, hz), horizon=hz)
    if r1.approved_for_execution or r2.approved_for_execution:
        _approved_ok = False
check("7.1 approved_for_execution always False", _approved_ok)


# ---------------------------------------------------------------------------
# Section 8 — PortfolioSettings + cash persistence (fail-closed)
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as _td:
    _p = Path(_td) / "holdings.json"
    with mock.patch.object(holds, "HOLDINGS_PATH", _p), \
            mock.patch.object(holds, "_DATA_DIR", Path(_td)):
        check("8.1 load_portfolio_settings defaults when absent",
              holds.load_portfolio_settings() == holds.PortfolioSettings())
        check("8.2 load_cash_position returns 0.0 when absent",
              holds.load_cash_position() == 0.0)
        _s = holds.PortfolioSettings(max_position_pct=0.20, short_max_loss_pct=0.01,
                                     mid_max_loss_pct=0.04)
        check("8.3 save_portfolio_settings returns True",
              holds.save_portfolio_settings(_s) is True)
        _loaded = holds.load_portfolio_settings()
        check("8.4 portfolio settings round-trip",
              _loaded.max_position_pct == 0.20 and _loaded.short_max_loss_pct == 0.01
              and _loaded.mid_max_loss_pct == 0.04 and _loaded.long_stop == "thesis_break",
              detail=str(_loaded))
        # Holdings + cash preserved across a settings write.
        holds.add_holding(holds.HoldingRecord(ticker="MU", shares=5, cost_basis=100.0))
        holds.save_cash_position(5000.0)
        holds.save_portfolio_settings(holds.PortfolioSettings(max_position_pct=0.10))
        check("8.5 holdings preserved across save_portfolio_settings",
              len(holds.load_holdings()) == 1, detail=str(holds.load_holdings()))
        check("8.6 cash preserved across save_portfolio_settings",
              holds.load_cash_position() == 5000.0, detail=str(holds.load_cash_position()))
        check("8.7 settings preserved across save_cash_position",
              holds.load_portfolio_settings().max_position_pct == 0.10
              and (holds.save_cash_position(6000.0) is True)
              and holds.load_portfolio_settings().max_position_pct == 0.10)


# ---------------------------------------------------------------------------
# Section 9 — page wiring + guardrails
# ---------------------------------------------------------------------------

_PAGE_SRC = _read(os.path.join(_REPO_ROOT, "pages", "9_Trading_Desk.py"))
_OA_SRC = _read(os.path.join(_REPO_ROOT, "lib", "order_advisor.py"))
_VA_SRC = _read(os.path.join(_REPO_ROOT, "lib", "valuation_anchor.py"))
_HOLD_SRC = _read(os.path.join(_REPO_ROOT, "lib", "holdings.py"))

check("9.1 Trading Desk page has a Portfolio Settings expander",
      "td_portfolio_settings" in _PAGE_SRC and "load_portfolio_settings" in _PAGE_SRC
      and "save_portfolio_settings" in _PAGE_SRC)
check("9.2 page does NOT write holdings.json directly",
      "json.dump" not in _PAGE_SRC and "HOLDINGS_PATH" not in _PAGE_SRC
      and "open(" not in _PAGE_SRC and "save_holdings" not in _PAGE_SRC)

_SRCS = {"lib/order_advisor.py": _OA_SRC, "lib/valuation_anchor.py": _VA_SRC,
         "lib/holdings.py": _HOLD_SRC, "pages/9_Trading_Desk.py": _PAGE_SRC}
for name, src in _SRCS.items():
    bad = ("approved_for_execution=True" in src.replace(" ", "")
           or "approved_for_execution = True" in src)
    check(f"9.3 no approved_for_execution=True in {name}", not bad)

_FORBIDDEN = ("place_order", "submit_order", "execute_order", "execute_trade",
              "broker_payload", "order_ticket", "order_payload", "time_in_force",
              "place_trade", "send_order", "route_order")
for name, src in _SRCS.items():
    hits = [tok for tok in _FORBIDDEN if tok in src.lower()]
    check(f"9.4 no execution-capability tokens in {name}", not hits, detail=str(hits))

for name, src in _SRCS.items():
    bad = any(tok in src.lower() for tok in ("sqlite", "psycopg", "chromadb", "pinecone",
                                             "faiss", "import sqlalchemy"))
    check(f"9.5 no DB / vector store in {name}", not bad)


# ---------------------------------------------------------------------------
# Section 10 — Anchor Intelligence v2 r2 (F1): TRUE single cached producer
# ---------------------------------------------------------------------------

# 10.A REAL PATH (DoD): order_advisor drives the ACTUAL unified producer
# lib.equity_valuation.compute_app_fair_value (NOT a stubbed FairValueAnchor). We
# mock only the network transport (_fetch_raw + the cyclical fetcher) + the
# OHLCV/snapshot, then reproduce the REAL Equity-page invocation — WITH the
# cyclical_history_fetcher, exactly as pages/4_Equity.py calls it (the previous
# parity test omitted the fetcher, which is the gap that let D2 through). The
# Trading-Desk anchor must equal the Equity-page anchor for the SAME ticker/price.
_RP_RAW = {
    "fcf_ttm": None, "fcf_source": "", "ebitda": None, "shares": 1.0e9,
    "growth_rate": 0.05, "trailing_eps": 5.0, "forward_eps": 5.5,
    "sector": "Technology", "industry": None,
    "analyst_median": 120.0, "analyst_mean": 122.0,
    "analyst_high": 140.0, "analyst_low": 105.0, "analyst_count": 12,
    "revenue_growth": 0.10, "earnings_growth": 0.08, "profit_margin": 0.20,
    "operating_margin": 0.25, "market_cap": 1.2e11, "enterprise_value": 1.2e11,
    "total_revenue": 2.5e10, "total_debt": 1.0e10, "total_cash": 9.0e9,
    "book_value": 30.0, "price_to_book": 3.0, "price_to_sales": 4.0, "live": True,
}
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_RP_RAW)), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", return_value={}):
    # REAL Equity-page invocation: WITH the cyclical fetcher (pages/4 signature).
    _equity_fv = eqv.compute_app_fair_value(
        "MU", 100.0, cyclical_history_fetcher=eqv.fetch_cyclical_band_history)
    with mock.patch("ui_utils.load_ohlcv", return_value=_dummy_df()), \
            mock.patch("lib.technical.snapshot",
                       return_value=_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0)), \
            _patched_portfolio([]):
        _pl_rp = oa.compute_price_levels("MU", None, horizon="long",
                                         valuation_percentile=0.3)
check("10.1 real path: order_advisor anchor == Equity-page AppFairValue.fair_value_mid",
      _pl_rp.fair_value_anchor is not None
      and abs(_pl_rp.fair_value_anchor - _equity_fv.fair_value_mid) < 0.01,
      detail=f"desk={_pl_rp.fair_value_anchor} equity={_equity_fv.fair_value_mid}")
check("10.2 real path: anchor source is live app_fair_value (unified producer, C5 rename)",
      _pl_rp.data_source == "live" and _pl_rp.fair_value_source == "app_fair_value",
      detail=f"{_pl_rp.data_source}/{_pl_rp.fair_value_source}")
check("10.3 real path: epoch stamp populated (ISO, T-separated)",
      bool(_pl_rp.fair_value_computed_at) and "T" in _pl_rp.fair_value_computed_at,
      detail=_pl_rp.fair_value_computed_at)

# 10.B REAL both-path parity (F1 DoD): the REAL Equity-page invocation (WITH the
# cyclical fetcher) and the REAL Trading-Desk invocation share ONE cached entry
# (st.cache_data keyed on ticker/price/override; the fetcher is underscore-excluded)
# -> identical anchor AND identical computed_at epoch. Fresh ticker so the Equity
# call is the genuine first writer; non-cyclical raw (industry None, no MU override)
# so the fetcher is never invoked (network-free even on the cold first write).
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_RP_RAW)), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", return_value={}):
    _eq_b = eqv.compute_app_fair_value(
        "PARITYX", 100.0, cyclical_history_fetcher=eqv.fetch_cyclical_band_history)
    with mock.patch("ui_utils.load_ohlcv", return_value=_dummy_df()), \
            mock.patch("lib.technical.snapshot",
                       return_value=_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0)), \
            _patched_portfolio([]):
        _pl_b = oa.compute_price_levels("PARITYX", None, horizon="long",
                                        valuation_percentile=0.3)
check("10.4 parity: Trading-Desk anchor == Equity-page anchor (one cached instance)",
      _pl_b.fair_value_anchor is not None
      and abs(_pl_b.fair_value_anchor - _eq_b.fair_value_mid) < 0.01,
      detail=f"desk={_pl_b.fair_value_anchor} equity={_eq_b.fair_value_mid}")
check("10.5 parity: Trading-Desk epoch == Equity-page epoch (same cached producer epoch)",
      bool(_pl_b.fair_value_computed_at)
      and _pl_b.fair_value_computed_at == _eq_b.computed_at,
      detail=f"{_pl_b.fair_value_computed_at} vs {_eq_b.computed_at}")

# 10.C FIRST-WRITER CONSISTENCY (F1): whichever page computes a ticker FIRST
# populates the one shared cache entry; the other surface then reads the identical
# value + epoch (st.cache_data returns a copy, so we assert value+epoch identity —
# the cache-unification contract — not object identity).
# 10.C(i) Trading-Desk-first -> Equity reads the same instance.
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_RP_RAW)), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", return_value={}):
    with mock.patch("ui_utils.load_ohlcv", return_value=_dummy_df()), \
            mock.patch("lib.technical.snapshot",
                       return_value=_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0)), \
            _patched_portfolio([]):
        _pl_td_first = oa.compute_price_levels("FWTKR1", None, horizon="long",
                                               valuation_percentile=0.3)
    _eq_after_td = eqv.compute_app_fair_value(
        "FWTKR1", 100.0, cyclical_history_fetcher=eqv.fetch_cyclical_band_history)
check("10.6 first-writer Trading-Desk: Equity read matches anchor + epoch",
      _pl_td_first.fair_value_anchor is not None
      and abs(_pl_td_first.fair_value_anchor - _eq_after_td.fair_value_mid) < 0.01
      and _pl_td_first.fair_value_computed_at == _eq_after_td.computed_at,
      detail=f"{_pl_td_first.fair_value_anchor}/{_pl_td_first.fair_value_computed_at} "
             f"vs {_eq_after_td.fair_value_mid}/{_eq_after_td.computed_at}")
# 10.C(ii) Equity-first -> Trading Desk reads the same instance.
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_RP_RAW)), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", return_value={}):
    _eq_first = eqv.compute_app_fair_value(
        "FWTKR2", 100.0, cyclical_history_fetcher=eqv.fetch_cyclical_band_history)
    with mock.patch("ui_utils.load_ohlcv", return_value=_dummy_df()), \
            mock.patch("lib.technical.snapshot",
                       return_value=_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0)), \
            _patched_portfolio([]):
        _pl_td_after = oa.compute_price_levels("FWTKR2", None, horizon="long",
                                               valuation_percentile=0.3)
check("10.7 first-writer Equity: Trading-Desk read matches anchor + epoch",
      _pl_td_after.fair_value_anchor is not None
      and abs(_pl_td_after.fair_value_anchor - _eq_first.fair_value_mid) < 0.01
      and _pl_td_after.fair_value_computed_at == _eq_first.computed_at,
      detail=f"{_pl_td_after.fair_value_anchor}/{_pl_td_after.fair_value_computed_at} "
             f"vs {_eq_first.fair_value_mid}/{_eq_first.computed_at}")

# 10.D STRUCTURAL no-network assertion (F1): the network-free ranking / Cockpit
# refresh paths consume lib.anchor_cache and must NOT call the producer (or pass a
# fetcher); only the two page paths (pages/4 + order_advisor._gather_technicals)
# invoke the single cached producer with the cyclical fetcher.
_RANKER_SRC = _read(os.path.join(_REPO_ROOT, "lib", "opportunity_ranker.py"))
_EQV_SRC = _read(os.path.join(_REPO_ROOT, "lib", "equity_valuation.py"))
_COCKPIT_SRC = _read(os.path.join(_REPO_ROOT, "pages", "7_Investment_Cockpit.py"))
_idx0 = _COCKPIT_SRC.find("def _run_refresh")
_idx1 = _COCKPIT_SRC.find("def _run_equity_research")
_REFRESH_SRC = (_COCKPIT_SRC[_idx0:_idx1] if (_idx0 >= 0 and _idx1 > _idx0)
                else _COCKPIT_SRC)
check("10.8 ranker does NOT call the producer / fetcher directly (consumes anchor_cache)",
      "compute_app_fair_value" not in _RANKER_SRC
      and "cyclical_history_fetcher" not in _RANKER_SRC
      and "anchor_cache" in _RANKER_SRC)
check("10.9 Cockpit network-free refresh consumes anchor_cache, not the producer",
      "compute_app_fair_value" not in _REFRESH_SRC
      and ("load_all" in _REFRESH_SRC or "anchor_cache" in _REFRESH_SRC),
      detail=f"idx0={_idx0} idx1={_idx1}")
check("10.10 Trading-Desk page path passes the cyclical fetcher to the producer",
      "cyclical_history_fetcher=fetch_cyclical_band_history" in _OA_SRC)
check("10.11 single cached worker: compute_app_fair_value routes ALL calls via _compute_cached",
      "def _compute_cached" in _EQV_SRC
      and "_cyclical_history_fetcher=cyclical_history_fetcher" in _EQV_SRC)


# ---------------------------------------------------------------------------
# Section 11 — Anchor Intelligence v2 r2 (F2): external band takes the WHOLE card
# ---------------------------------------------------------------------------

# Regression for the review probe: an external/session anchors_irreconcilable band
# with a HEALTHY local instance (local anchor 120, confidence high, conservative
# 120) must NOT leak the local valuation wearing the external timestamp. EVERY
# anchor-derived field must read from the band: no local scalar, confidence low,
# conservative None, epoch from the band, LONG degraded.
#   BEFORE the fix (the leak): fair_value_anchor 120, valuation_confidence "high",
#                              conservative_anchor 120, epoch = external.
#   AFTER  the fix:            fair_value_anchor None, valuation_confidence "low",
#                              conservative_anchor None, epoch = external, no zone.
_healthy_local = eqv.AppFairValue(
    ticker="MU", confidence="high", blend_state="blended",
    fair_value_low=110.0, fair_value_mid=120.0, fair_value_high=140.0,
    analyst_target=120.0, computed_at="2026-06-01T00:00:00+00:00", data_source="live")
_ext_irrec = {
    "blend_state": "anchors_irreconcilable", "confidence": "low",
    "fair_value_low": 0.0, "fair_value_mid": 0.0, "fair_value_high": 0.0,
    "computed_at": "2026-06-07T15:30:00+00:00",
}
with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0),
              fva_obj=_healthy_local), _patched_portfolio([]):
    _pl_f2 = oa.compute_price_levels("MU", None, horizon="long",
                                     valuation_percentile=0.3,
                                     app_fair_value=_ext_irrec)
check("11.1 F2: external irreconcilable -> NO local fair-value scalar leak (anchor None)",
      _pl_f2.fair_value_anchor is None, detail=str(_pl_f2.fair_value_anchor))
check("11.2 F2: confidence from band (low), not the local high",
      _pl_f2.valuation_confidence == "low", detail=_pl_f2.valuation_confidence)
check("11.3 F2: conservative_anchor None (not the local 120)",
      _pl_f2.conservative_anchor is None, detail=str(_pl_f2.conservative_anchor))
check("11.4 F2: epoch from the external band (not the local instance)",
      _pl_f2.fair_value_computed_at == "2026-06-07T15:30:00+00:00",
      detail=_pl_f2.fair_value_computed_at)
check("11.5 F2: LONG degrades to technical-only (no entry zone)",
      _pl_f2.entry_zone_low is None and _pl_f2.entry_zone_high is None,
      detail=f"{_pl_f2.entry_zone_low}-{_pl_f2.entry_zone_high}")

# 11.6 control — a HIGH-confidence external band still drives every field FROM the
# band (confidence high, conservative == band low, epoch from band, anchor == mid).
_ext_high = {
    "blend_state": "blended", "confidence": "high",
    "fair_value_low": 90.0, "fair_value_mid": 105.0, "fair_value_high": 120.0,
    "computed_at": "2026-06-07T16:00:00+00:00",
}
with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0),
              fva_obj=_healthy_local), _patched_portfolio([]):
    _pl_f2h = oa.compute_price_levels("MU", None, horizon="long",
                                      valuation_percentile=0.3,
                                      app_fair_value=_ext_high)
check("11.6 F2 control: high external band drives anchor/confidence/conservative/epoch",
      _pl_f2h.valuation_confidence == "high"
      and _pl_f2h.fair_value_anchor is not None
      and abs(_pl_f2h.fair_value_anchor - 105.0) < 1e-6
      and _pl_f2h.conservative_anchor == 90.0
      and _pl_f2h.fair_value_computed_at == "2026-06-07T16:00:00+00:00",
      detail=f"{_pl_f2h.valuation_confidence}/{_pl_f2h.fair_value_anchor}/"
             f"{_pl_f2h.conservative_anchor}/{_pl_f2h.fair_value_computed_at}")


# ---------------------------------------------------------------------------
# Section 12 — Anchor Intelligence v2 r2 (F3): gate-interaction coverage
# ---------------------------------------------------------------------------

# 12(a) pool-dispersion gate + inter-method irreconcilable BOTH firing. Gate
# ordering: the pool gate caps confidence, the inter-method dispersion gate still
# runs LAST and sets blend_state. Expect: analyst_pool_dispersed caveat present,
# final confidence low, blend_state anchors_irreconcilable.
_fa_both = eqv.build_app_fair_value(
    ticker="GATEA", current_price=100.0,
    dcf_value=350.0, relative_value=None, analyst_target=100.0, analyst_count=8,
    data_source="live", company_type="mature_profitable",
    analyst_pool={"median": 100.0, "mean": 100.0, "high": 300.0, "low": 20.0, "n": 8})
check("12.1 (a) both gates: blend_state anchors_irreconcilable (dcf 350 vs analyst 100 = 3.5x)",
      _fa_both.blend_state == "anchors_irreconcilable",
      detail=f"{_fa_both.blend_state}/disp={_fa_both.anchor_dispersion}")
check("12.2 (a) both gates: final confidence low",
      _fa_both.confidence == "low", detail=_fa_both.confidence)
check("12.3 (a) both gates: analyst_pool_dispersed caveat survives into irreconcilable",
      "analyst_pool_dispersed" in (_fa_both.caveats or []), detail=str(_fa_both.caveats))

# 12(b) pool-capped LOW confidence propagating into order_advisor LONG tiers. A
# pool-dispersed analyst-only band is blended but confidence is forced low by the
# pool gate; the LONG three-tier then has no high/medium tier to apply -> it
# degrades to the unified low-confidence path: NO entry zone, conservative None
# (the same suppressed behavior as B's low-confidence tier, §2.3).
_fa_pool_low = eqv.build_app_fair_value(
    ticker="MU", current_price=100.0,
    dcf_value=None, relative_value=None, analyst_target=105.0, analyst_count=20,
    data_source="live", company_type="mature_profitable",
    analyst_pool={"median": 105.0, "mean": 105.0, "high": 200.0, "low": 30.0, "n": 20})
check("12.4 (b) precond: pool-capped band is blended but confidence low",
      _fa_pool_low.blend_state == "blended" and _fa_pool_low.confidence == "low",
      detail=f"{_fa_pool_low.blend_state}/{_fa_pool_low.confidence}")
with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.0),
              fva_obj=_fa_pool_low), _patched_portfolio([]):
    _pl_pool = oa.compute_price_levels("MU", None, horizon="long",
                                       valuation_percentile=0.3)
check("12.5 (b) LONG suppressed under pool-capped low confidence (no entry zone)",
      _pl_pool.entry_zone_low is None and _pl_pool.entry_zone_high is None,
      detail=f"{_pl_pool.entry_zone_low}-{_pl_pool.entry_zone_high}")
check("12.6 (b) LONG surfaces low confidence + conservative None",
      _pl_pool.valuation_confidence == "low" and _pl_pool.conservative_anchor is None,
      detail=f"{_pl_pool.valuation_confidence}/{_pl_pool.conservative_anchor}")

# 12(c) cyclical single-anchor path + dispersed pool — MU's live combination:
# cyclical ticker, band unavailable (no fetcher) -> analyst-only degrade; pool
# dispersion fires -> confidence low; caveats include cyclical_band_unavailable +
# single_anchor_blend + analyst_pool_dispersed. Fresh price (95.0) so the cache key
# does not collide with §10.A's (MU, 100.0).
_MU_CYC_RAW = {
    "fcf_ttm": 2.0e9, "fcf_source": "", "ebitda": 8.0e9, "shares": 1.1e9,
    "growth_rate": 0.15, "trailing_eps": 5.0, "forward_eps": None,
    "sector": "Technology", "industry": "Semiconductors",
    "analyst_median": 110.0, "analyst_mean": 108.0,
    "analyst_high": 200.0, "analyst_low": 30.0, "analyst_count": 20,
    "revenue_growth": 0.20, "earnings_growth": 0.10, "profit_margin": 0.10,
    "operating_margin": 0.12, "market_cap": 1.1e11, "enterprise_value": 1.2e11,
    "total_revenue": 2.5e10, "total_debt": 1.0e10, "total_cash": 0.9e10,
    "book_value": 30.0, "price_to_book": 3.0, "price_to_sales": 4.0, "live": True,
}
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_MU_CYC_RAW)):
    _mu_cyc = eqv.compute_app_fair_value("MU", 95.0)  # no fetcher -> band unavailable
check("12.7 (c) MU cyclical + no band -> analyst-only single-anchor blend",
      _mu_cyc.company_type == "cyclical"
      and {a["name"] for a in (_mu_cyc.anchors or [])} == {"analyst"},
      detail=f"{_mu_cyc.company_type}/{[a['name'] for a in (_mu_cyc.anchors or [])]}")
check("12.8 (c) MU cyclical dispersed pool -> confidence low",
      _mu_cyc.confidence == "low", detail=_mu_cyc.confidence)
check("12.9 (c) MU caveats: cyclical_band_unavailable + single_anchor_blend + analyst_pool_dispersed",
      {"cyclical_band_unavailable", "single_anchor_blend", "analyst_pool_dispersed"}
      <= set(_mu_cyc.caveats or []), detail=str(_mu_cyc.caveats))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n".join(_failures))
total = PASS + FAIL
print(f"\nPhase 6C-A v3 Entry Strategy v4 — {PASS}/{total} checks passed.")
if FAIL:
    print(f"{FAIL} FAILED.")
    sys.exit(1)
print("ALL PASSED.")
