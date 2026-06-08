#!/usr/bin/env python3
"""
scripts/test_reliability_phase_6c_b_cockpit_rebuild.py

Phase 6C-B — Investment Cockpit Rebuild test suite (mock-only / offline).

Runs entirely without real API calls. ANTHROPIC_API_KEY / FINNHUB_API_KEY are
forced empty and yfinance is never reached (the fair-value fetch fails closed or
is patched). Verifies:

  * lib/equity_valuation.py imports cleanly.
  * AppFairValue exposes all required fields.
  * compute_app_fair_value returns AppFairValue with
    fair_value_low <= fair_value_mid <= fair_value_high.
  * confidence == "high" when all three sources are available and spread < 0.40.
  * confidence == "low" when all sources are None.
  * store_equity_research_result writes st.session_state["equity_research_results"][ticker].
  * order_advisor reads equity_research_results when available
    (fair_value_source == "app_computed" when mocked).
  * order_advisor falls back to app_fair_value when equity_research_results absent.
  * pages/1_Overview.py is NOT registered in the ui_utils sidebar.
  * pages/7_Investment_Cockpit.py is the first non-home page in the sidebar.
  * cockpit_selected_tickers is written to session_state on selection.
  * one-click refresh updates cockpit_last_refresh.
  * analyze_equity_fair_value_debate returns endorsed_*_low/high as floats.
  * No approved_for_execution=True anywhere in the created/modified files.
  * fair_value_source badge exists in pages/9_Trading_Desk.py.

Usage:
    python3 -B scripts/test_reliability_phase_6c_b_cockpit_rebuild.py
"""

from __future__ import annotations

import dataclasses
import os
import re
import sys
from unittest import mock

# Force a keyless / offline environment BEFORE importing the libs.
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if os.path.join(_REPO_ROOT, "lib") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "lib"))


PASS = 0
FAIL = 0
_failures: list[str] = []


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


EQUITY_VAL_PATH = os.path.join(_REPO_ROOT, "lib", "equity_valuation.py")
ORDER_PATH = os.path.join(_REPO_ROOT, "lib", "order_advisor.py")
LLM_PATH = os.path.join(_REPO_ROOT, "lib", "llm_orchestrator.py")
UI_UTILS_PATH = os.path.join(_REPO_ROOT, "ui_utils.py")
COCKPIT_PATH = os.path.join(_REPO_ROOT, "pages", "7_Investment_Cockpit.py")
EQUITY_PAGE_PATH = os.path.join(_REPO_ROOT, "pages", "4_Equity.py")
TD_PATH = os.path.join(_REPO_ROOT, "pages", "9_Trading_Desk.py")

_EQV_SRC = _read(EQUITY_VAL_PATH)
_ORDER_SRC = _read(ORDER_PATH)
_LLM_SRC = _read(LLM_PATH)
_UI_SRC = _read(UI_UTILS_PATH)
_COCKPIT_SRC = _read(COCKPIT_PATH)
_EQUITY_PAGE_SRC = _read(EQUITY_PAGE_PATH)
_TD_SRC = _read(TD_PATH)


# ---------------------------------------------------------------------------
# Section 1 — equity_valuation imports + AppFairValue fields
# ---------------------------------------------------------------------------

import lib.equity_valuation as ev  # noqa: E402

check("1.1 lib/equity_valuation.py imports", True)

_REQUIRED_FV_FIELDS = {
    "ticker", "dcf_value", "relative_value", "analyst_target", "analyst_count",
    "fair_value_low", "fair_value_mid", "fair_value_high", "confidence",
    "upside_pct", "methodology", "computed_at", "data_source",
}
_fv_field_names = {f.name for f in dataclasses.fields(ev.AppFairValue)}
check("1.2 AppFairValue has all required fields",
      _REQUIRED_FV_FIELDS <= _fv_field_names,
      str(sorted(_REQUIRED_FV_FIELDS - _fv_field_names)))

check("1.3 AppFairValue has no approved_for_execution field",
      "approved_for_execution" not in _fv_field_names)


# ---------------------------------------------------------------------------
# Section 2 — compute_app_fair_value ordering + confidence tiers
# ---------------------------------------------------------------------------

# Offline (no usable inputs) -> fixture fallback anchored on current_price.
# Patch _fetch_raw so the test is fully mock-only (no network dependence).
_EMPTY_RAW = {
    "fcf_ttm": None, "shares": None, "growth_rate": None, "trailing_eps": None,
    "sector": None, "analyst_median": None, "analyst_mean": None,
    "analyst_count": 0, "live": False,
}
with mock.patch.object(ev, "_fetch_raw", return_value=dict(_EMPTY_RAW)):
    _fv_offline = ev.compute_app_fair_value("OFFLNTEST", 150.0)
check("2.1 compute_app_fair_value returns AppFairValue",
      isinstance(_fv_offline, ev.AppFairValue))
check("2.2 fair_value_low <= mid <= high (offline)",
      _fv_offline.fair_value_low <= _fv_offline.fair_value_mid <= _fv_offline.fair_value_high,
      f"{_fv_offline.fair_value_low}/{_fv_offline.fair_value_mid}/{_fv_offline.fair_value_high}")
check("2.3 offline fixture fallback data_source + low confidence",
      _fv_offline.data_source == "fixture" and _fv_offline.confidence == "low",
      f"{_fv_offline.data_source}/{_fv_offline.confidence}")

# All three sources available, tight spread -> high confidence.
_fv_high = ev.build_app_fair_value(
    "AAA", current_price=100.0, dcf_value=100.0, relative_value=102.0,
    analyst_target=101.0, analyst_count=12, data_source="live")
check("2.4 ordering holds (3 sources)",
      _fv_high.fair_value_low <= _fv_high.fair_value_mid <= _fv_high.fair_value_high)
_spread = ((_fv_high.fair_value_high - _fv_high.fair_value_low) / _fv_high.fair_value_mid)
check("2.5 confidence == high (3 sources, spread < 0.40)",
      _fv_high.confidence == "high", f"conf={_fv_high.confidence} spread={_spread:.3f}")

# No sources -> low confidence, current-price-anchored band.
_fv_low = ev.build_app_fair_value(
    "BBB", current_price=200.0, dcf_value=None, relative_value=None,
    analyst_target=None, data_source="fixture")
check("2.6 confidence == low (all sources None)",
      _fv_low.confidence == "low", f"conf={_fv_low.confidence}")
check("2.7 ordering holds (no sources)",
      _fv_low.fair_value_low <= _fv_low.fair_value_mid <= _fv_low.fair_value_high)

# DCF math sanity: per-share Gordon growth, fail-closed when growth >= WACC.
_dcf_ok = ev._compute_dcf_per_share(
    {"fcf_ttm": 1.0e9, "shares": 1.0e8, "growth_rate": 0.05})
check("2.8 DCF per-share computed for growth < WACC", isinstance(_dcf_ok, float) and _dcf_ok > 0)
_dcf_bad = ev._compute_dcf_per_share(
    {"fcf_ttm": 1.0e9, "shares": 1.0e8, "growth_rate": 0.15})
check("2.9 DCF None when growth >= WACC (Gordon undefined)", _dcf_bad is None)


# ---------------------------------------------------------------------------
# Section 3 — store_equity_research_result writes session_state
# ---------------------------------------------------------------------------

import streamlit as _stmod  # noqa: E402

_orig_session = getattr(_stmod, "session_state", None)
try:
    _stmod.session_state = {}
    ev.store_equity_research_result("test", _fv_high, debate_summary="hello",
                                    analyst_action="buy")
    _stored = _stmod.session_state.get("equity_research_results", {})
    check("3.1 equity_research_results written", "TEST" in _stored,
          str(list(_stored.keys())))
    _rec = _stored.get("TEST", {})
    check("3.2 stored record has fair_value_mid",
          "fair_value_mid" in _rec and isinstance(_rec["fair_value_mid"], float))
    check("3.3 stored record carries confidence + debate_summary",
          _rec.get("confidence") == "high" and _rec.get("debate_summary") == "hello")
    check("3.4 stored record carries analyst_action",
          _rec.get("analyst_action") == "buy")
finally:
    if _orig_session is not None:
        _stmod.session_state = _orig_session


# ---------------------------------------------------------------------------
# Section 4 — order_advisor reads app fair value / falls back to app_fair_value
# ---------------------------------------------------------------------------

import lib.order_advisor as oa  # noqa: E402

check("4.0 PriceLevelResult has fair_value_source field",
      "fair_value_source" in {f.name for f in dataclasses.fields(oa.PriceLevelResult)})


def _live_tech(*_a, **_k) -> dict:
    return {
        "current_price": 100.0, "atr": 3.0, "ema10": 99.0, "ema20": 98.0,
        "sma50": 95.0, "sma200": 80.0, "rsi": 50.0, "adx": 25.0,
        "vol_ratio": 1.2, "volume_trend": "increasing", "candle": "none",
        "nearest_support": 88.0, "nearest_resistance": 120.0,
        "fair_value_anchor": 95.0, "fva_obj": None, "valuation_percentile": 0.4,
        "support_levels": [88.0], "resistance_levels": [120.0],
        "above_sma200": True, "pct_from_52w_high": -5.0, "data_source": "live",
    }


_APP_RESULT = {
    "confidence": "high", "fair_value_low": 95.0, "fair_value_mid": 105.0,
    "fair_value_high": 120.0, "upside_pct": 0.05, "methodology": "x",
}

with mock.patch.object(oa, "_gather_technicals", side_effect=_live_tech), \
        mock.patch.object(oa, "_read_equity_research_result", return_value=_APP_RESULT):
    _pl_app = oa.compute_price_levels("AAA", None, horizon="long")
check("4.1 fair_value_source == app_computed when equity result present",
      _pl_app.fair_value_source == "app_computed", _pl_app.fair_value_source)
check("4.2 app-computed anchor used (fair_value_anchor == app mid)",
      abs((_pl_app.fair_value_anchor or 0) - 105.0) < 1e-6,
      str(_pl_app.fair_value_anchor))
check("4.3 app-computed result still approved_for_execution False",
      _pl_app.approved_for_execution is False)

with mock.patch.object(oa, "_gather_technicals", side_effect=_live_tech), \
        mock.patch.object(oa, "_read_equity_research_result", return_value={}):
    _pl_proxy = oa.compute_price_levels("AAA", None, horizon="long")
# Anchor Intel v2 r2 (C5 rename): the local live producer token is now the
# truthful "app_fair_value" (was the misleading "analyst_proxy").
check("4.4 fair_value_source == app_fair_value when result absent (live data)",
      _pl_proxy.fair_value_source == "app_fair_value", _pl_proxy.fair_value_source)


# ---------------------------------------------------------------------------
# Section 5 — sidebar registration (Overview removed; Cockpit first)
# ---------------------------------------------------------------------------

check("5.1 pages/1_Overview.py NOT a sidebar page_link",
      'page_link("pages/1_Overview.py"' not in _UI_SRC)

# Ordered page_link("pages/...") occurrences -> Cockpit must be first non-home.
_page_links = re.findall(r'page_link\(\s*"(pages/[^"]+)"', _UI_SRC)
check("5.2 pages/7_Investment_Cockpit.py is the first non-home sidebar page",
      bool(_page_links) and _page_links[0] == "pages/7_Investment_Cockpit.py",
      str(_page_links[:3]))
check("5.3 nav_p1 translation key retained (deprecated, not deleted)",
      '"nav_p1"' in _UI_SRC)
check("5.4 cockpit_hub_* keys added to ui_utils",
      '"cockpit_hub_refresh_btn"' in _UI_SRC and '"cockpit_hub_title"' in _UI_SRC)


# ---------------------------------------------------------------------------
# Section 6 — cockpit page wiring (source-level, mock-only)
# ---------------------------------------------------------------------------

check("6.1 cockpit writes cockpit_selected_tickers to session_state",
      'st.session_state["cockpit_selected_tickers"]' in _COCKPIT_SRC)
check("6.2 cockpit one-click refresh sets cockpit_last_refresh",
      'st.session_state["cockpit_last_refresh"]' in _COCKPIT_SRC)
check("6.3 cockpit refresh calls fetch_all_macro + classify_regime",
      "fetch_all_macro" in _COCKPIT_SRC and "classify_regime" in _COCKPIT_SRC)
check("6.4 cockpit refresh calls compute_all_themes",
      "compute_all_themes" in _COCKPIT_SRC)
check("6.5 cockpit refresh calls generate_candidates",
      "generate_candidates" in _COCKPIT_SRC)
check("6.6 cockpit refresh values selected tickers (compute_app_fair_value)",
      "compute_app_fair_value" in _COCKPIT_SRC
      and "store_equity_research_result" in _COCKPIT_SRC)
check("6.7 cockpit does NOT run the Trading Desk thesis monitor",
      "run_thesis_monitor" not in _COCKPIT_SRC)
check("6.8 cockpit reads macro_regime_result / theme_momentum_results",
      "macro_regime_result" in _COCKPIT_SRC
      and "theme_momentum_results" in _COCKPIT_SRC)


# ---------------------------------------------------------------------------
# Section 7 — analyze_equity_fair_value_debate (fail-closed without API key)
# ---------------------------------------------------------------------------

import lib.llm_orchestrator as llm  # noqa: E402

_debate = llm.analyze_equity_fair_value_debate(
    "AAA", _fv_high, thesis_text="t", macro_regime="risk_on", lang="en")
check("7.1 debate returns a dict", isinstance(_debate, dict))
check("7.2 endorsed_fair_value_low is a float",
      isinstance(_debate.get("endorsed_fair_value_low"), float),
      str(type(_debate.get("endorsed_fair_value_low"))))
check("7.3 endorsed_fair_value_high is a float",
      isinstance(_debate.get("endorsed_fair_value_high"), float))
check("7.4 fail-closed endorsed == app low/high (no API key)",
      _debate.get("endorsed_fair_value_low") == _fv_high.fair_value_low
      and _debate.get("endorsed_fair_value_high") == _fv_high.fair_value_high)
check("7.5 debate has bilingual prose + analyst_action",
      "bull_case_en" in _debate and "bull_case_zh" in _debate
      and _debate.get("analyst_action") in ("buy", "hold", "avoid", "wait"))


# ---------------------------------------------------------------------------
# Section 8 — guardrails (no execution capability)
# ---------------------------------------------------------------------------

_NO_EXEC_PATTERNS = ("approved_for_execution=True",
                     "approved_for_execution = True",
                     '"approved_for_execution": true')
for _label, _src in [
    ("equity_valuation", _EQV_SRC), ("order_advisor", _ORDER_SRC),
    ("llm_orchestrator", _LLM_SRC), ("cockpit", _COCKPIT_SRC),
    ("equity_page", _EQUITY_PAGE_SRC), ("trading_desk", _TD_SRC),
    ("ui_utils", _UI_SRC),
]:
    check(f"8.x no approved_for_execution=True in {_label}",
          not any(p in _src for p in _NO_EXEC_PATTERNS))

check("8.9 fair_value_source badge present in Trading Desk",
      "fair_value_source" in _TD_SRC and "td_fair_value_source" in _TD_SRC)
check("8.10 equity page adds AI Valuation Summary section",
      "cockpit_fv_header" in _EQUITY_PAGE_SRC
      and "compute_app_fair_value" in _EQUITY_PAGE_SRC)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n".join(_failures))
print(f"\n{PASS}/{PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
