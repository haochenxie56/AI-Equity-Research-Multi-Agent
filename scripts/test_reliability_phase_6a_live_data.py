#!/usr/bin/env python3
"""
scripts/test_reliability_phase_6a_live_data.py

Phase 6A — Live Data Integration test suite.

This test runs **entirely without real API calls**: yfinance is patched to fail
and FRED / Finnhub keys are forced empty so every fetch falls back to its
fixture path. It therefore exercises the fail-closed behavior, the dataclass
contracts, the deterministic regime classification, and the page integration
without touching the network.

Coverage:
  * lib/macro_data.py and lib/macro_regime.py exist and import cleanly.
  * MacroDataResult / MacroRegimeResult dataclasses have the required fields.
  * classify_regime returns a valid regime, and "degraded" when coverage < 0.5.
  * horizon_bias carries short/mid/long with valid values.
  * fetch_all_macro is callable (mocked) and fail-closed.
  * Every fetch_* function in lib/macro_data.py has a try/except (AST check).
  * The page imports the new modules, defines MACRO_LIVE_MODE, renders LIVE /
    FIXTURE badges, and still carries the fixture fallback path.
  * No positive approved_for_execution authorization and no broker/order/
    execution token in any Phase 6A code file.
  * data_source field exists on every metric group of MacroDataResult.

Usage:
    python3 -B scripts/test_reliability_phase_6a_live_data.py
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import os
import sys
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


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


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

MACRO_DATA_PATH = os.path.join(_REPO_ROOT, "lib", "macro_data.py")
MACRO_REGIME_PATH = os.path.join(_REPO_ROOT, "lib", "macro_regime.py")
PAGE_PATH = os.path.join(_REPO_ROOT, "pages", "8_Macro_Dashboard.py")
DOC_PATH = os.path.join(
    _REPO_ROOT, "docs", "reliability_phase_6a_live_data_integration.md"
)

_MACRO_DATA_SRC = _read(MACRO_DATA_PATH)
_MACRO_REGIME_SRC = _read(MACRO_REGIME_PATH)
_PAGE_SRC = _read(PAGE_PATH)


# ---------------------------------------------------------------------------
# Section 1 — Files exist and import without error
# ---------------------------------------------------------------------------

check("1.1 lib/macro_data.py exists", os.path.isfile(MACRO_DATA_PATH))
check("1.2 lib/macro_regime.py exists", os.path.isfile(MACRO_REGIME_PATH))
check("1.3 pages/8_Macro_Dashboard.py exists", os.path.isfile(PAGE_PATH))

_md = None
_mr = None
try:
    _md = importlib.import_module("lib.macro_data")
    check("1.4 lib.macro_data imports without error", True)
except Exception as exc:  # noqa: BLE001
    check("1.4 lib.macro_data imports without error", False, repr(exc))

try:
    _mr = importlib.import_module("lib.macro_regime")
    check("1.5 lib.macro_regime imports without error", True)
except Exception as exc:  # noqa: BLE001
    check("1.5 lib.macro_regime imports without error", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 2 — MacroDataResult dataclass + per-group data_source field
# ---------------------------------------------------------------------------

if _md is not None:
    MacroDataResult = getattr(_md, "MacroDataResult", None)
    check("2.1 MacroDataResult exists", MacroDataResult is not None)
    check(
        "2.2 MacroDataResult is a dataclass",
        MacroDataResult is not None and dataclasses.is_dataclass(MacroDataResult),
    )
    if MacroDataResult is not None and dataclasses.is_dataclass(MacroDataResult):
        _fields = {f.name for f in dataclasses.fields(MacroDataResult)}
        for required in (
            "timestamp",
            "data_coverage",
            "vix",
            "rates",
            "credit",
            "dollar",
            "etf_returns",
            "economic_releases",
            "sentiment",
        ):
            check(
                f"2.3 MacroDataResult has field {required!r}",
                required in _fields,
            )

    # Each metric-group dataclass carries a data_source field.
    _GROUP_CLASSES = [
        "VixResult",
        "RatesResult",
        "CreditResult",
        "DollarResult",
        "EtfReturnsResult",
        "EconomicReleasesResult",
        "SentimentResult",
    ]
    for cls_name in _GROUP_CLASSES:
        cls = getattr(_md, cls_name, None)
        ok = (
            cls is not None
            and dataclasses.is_dataclass(cls)
            and "data_source" in {f.name for f in dataclasses.fields(cls)}
        )
        check(f"2.4 {cls_name} has data_source field", ok)


# ---------------------------------------------------------------------------
# Section 3 — MacroRegimeResult dataclass fields
# ---------------------------------------------------------------------------

if _mr is not None:
    MacroRegimeResult = getattr(_mr, "MacroRegimeResult", None)
    check("3.1 MacroRegimeResult exists", MacroRegimeResult is not None)
    check(
        "3.2 MacroRegimeResult is a dataclass",
        MacroRegimeResult is not None and dataclasses.is_dataclass(MacroRegimeResult),
    )
    if MacroRegimeResult is not None and dataclasses.is_dataclass(MacroRegimeResult):
        _rfields = {f.name for f in dataclasses.fields(MacroRegimeResult)}
        for required in (
            "regime",
            "confidence",
            "horizon_bias",
            "key_signals",
            "opportunity_posture",
            "data_coverage",
        ):
            check(
                f"3.3 MacroRegimeResult has field {required!r}",
                required in _rfields,
            )


# ---------------------------------------------------------------------------
# Helpers to build synthetic MacroDataResult instances (no network)
# ---------------------------------------------------------------------------


def _build_macro_data(coverage: float, source: str):
    """Construct a MacroDataResult with all groups using the given source."""
    assert _md is not None
    return _md.MacroDataResult(
        vix=_md.VixResult(15.0, -1.0, 70.0, source),
        rates=_md.RatesResult(4.2, 3.6, 0.6, 2.3, source),
        credit=_md.CreditResult(3.0, source),
        dollar=_md.DollarResult(120.0, -2.5, source),
        etf_returns=_md.EtfReturnsResult({"SPY": 2.0, "IWM": 1.5}, {}, source),
        economic_releases=_md.EconomicReleasesResult(
            150.0, "2026-05-01", 300.0, "2026-05-01", 250.0, "2026-05-01", source
        ),
        sentiment=_md.SentimentResult(70.0, "greed", [], [], source),
        timestamp="2026-05-29T00:00:00+00:00",
        data_coverage=coverage,
    )


# ---------------------------------------------------------------------------
# Section 4 — classify_regime behavior
# ---------------------------------------------------------------------------

if _md is not None and _mr is not None:
    classify_regime = getattr(_mr, "classify_regime", None)
    check("4.1 classify_regime is callable", callable(classify_regime))

    _VALID_REGIMES = {"risk_on", "risk_off", "transition", "degraded"}
    _VALID_BIAS = {"favorable", "neutral", "cautious", "unfavorable"}

    if callable(classify_regime):
        # High-coverage, risk-on leaning synthetic data.
        res_on = classify_regime(_build_macro_data(1.0, "live"))
        check(
            "4.2 classify_regime returns MacroRegimeResult",
            isinstance(res_on, _mr.MacroRegimeResult),
        )
        check(
            "4.3 regime is a valid value",
            res_on.regime in _VALID_REGIMES,
            detail=str(res_on.regime),
        )
        check(
            "4.4 high-coverage risk-on synthetic classifies non-degraded",
            res_on.regime != "degraded",
            detail=str(res_on.regime),
        )

        # horizon_bias has short/mid/long with valid values.
        hb = res_on.horizon_bias
        check("4.5 horizon_bias is a dict", isinstance(hb, dict))
        for k in ("short", "mid", "long"):
            check(f"4.6 horizon_bias has key {k!r}", isinstance(hb, dict) and k in hb)
            check(
                f"4.7 horizon_bias[{k!r}] is a valid value",
                isinstance(hb, dict) and hb.get(k) in _VALID_BIAS,
                detail=str(hb.get(k) if isinstance(hb, dict) else hb),
            )

        # confidence valid.
        check(
            "4.8 confidence is valid",
            res_on.confidence in {"high", "medium", "low"},
            detail=str(res_on.confidence),
        )

        # Degraded rule: coverage < 0.5 -> regime == "degraded".
        res_deg = classify_regime(_build_macro_data(0.3, "fixture"))
        check(
            "4.9 coverage < 0.5 forces regime == 'degraded'",
            res_deg.regime == "degraded",
            detail=str(res_deg.regime),
        )
        check(
            "4.10 degraded horizon_bias is all neutral",
            res_deg.horizon_bias == {"short": "neutral", "mid": "neutral", "long": "neutral"},
            detail=str(res_deg.horizon_bias),
        )
        check(
            "4.11 degraded carries key_signals + data_coverage copied",
            bool(res_deg.key_signals) and abs(res_deg.data_coverage - 0.3) < 1e-9,
        )

        # Just-at-threshold coverage (0.5) is NOT degraded by the rule.
        res_thr = classify_regime(_build_macro_data(0.5, "live"))
        check(
            "4.12 coverage == 0.5 is not forced degraded",
            res_thr.regime != "degraded",
            detail=str(res_thr.regime),
        )


# ---------------------------------------------------------------------------
# Section 5 — fetch_all_macro callable + fail-closed (mocked, no network)
# ---------------------------------------------------------------------------

if _md is not None:
    check("5.1 fetch_all_macro is callable", callable(getattr(_md, "fetch_all_macro", None)))

    _FETCH_FUNCS = [
        "fetch_vix",
        "fetch_rates",
        "fetch_credit",
        "fetch_dollar",
        "fetch_etf_returns",
        "fetch_economic_releases",
        "fetch_market_sentiment",
        "fetch_all_macro",
    ]

    def _clear_caches() -> None:
        for name in _FETCH_FUNCS:
            fn = getattr(_md, name, None)
            if fn is not None and hasattr(fn, "clear"):
                try:
                    fn.clear()
                except Exception:  # noqa: BLE001
                    pass

    class _BoomYf:
        def __getattr__(self, name):  # any yfinance access raises
            raise RuntimeError("network disabled in test")

    # Force every source to its fixture fallback: no API keys + yfinance raises.
    _orig_fred = _md.FRED_API_KEY
    _orig_finn = _md.FINNHUB_API_KEY
    try:
        _md.FRED_API_KEY = ""
        _md.FINNHUB_API_KEY = ""
        with mock.patch.object(_md, "yf", _BoomYf()):
            _clear_caches()
            result = _md.fetch_all_macro()
        check(
            "5.2 fetch_all_macro returns MacroDataResult (mocked)",
            isinstance(result, _md.MacroDataResult),
        )
        check(
            "5.3 fail-closed: every group falls back to fixture",
            all(
                getattr(getattr(result, g), "data_source", None) == "fixture"
                for g in (
                    "vix",
                    "rates",
                    "credit",
                    "dollar",
                    "etf_returns",
                    "economic_releases",
                    "sentiment",
                )
            ),
        )
        check(
            "5.4 fail-closed coverage is 0.0 when all groups fixture",
            abs(result.data_coverage - 0.0) < 1e-9,
            detail=str(result.data_coverage),
        )
        check("5.5 fetch_all_macro sets a timestamp", bool(result.timestamp))
    finally:
        _md.FRED_API_KEY = _orig_fred
        _md.FINNHUB_API_KEY = _orig_finn
        _clear_caches()


# ---------------------------------------------------------------------------
# Section 6 — Every fetch_* function has a try/except (AST inspection)
# ---------------------------------------------------------------------------

try:
    _tree = ast.parse(_MACRO_DATA_SRC)
    _fetch_defs = [
        node
        for node in _tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("fetch_")
    ]
    check("6.1 at least 8 fetch_* functions defined", len(_fetch_defs) >= 8,
          detail=str([f.name for f in _fetch_defs]))
    for fdef in _fetch_defs:
        has_try = any(isinstance(n, ast.Try) for n in ast.walk(fdef))
        check(f"6.2 {fdef.name} contains a try/except", has_try)
except SyntaxError as exc:
    check("6.0 lib/macro_data.py parses as valid Python", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 7 — Caching with st.cache_data TTL=900 present
# ---------------------------------------------------------------------------

check(
    "7.1 lib/macro_data.py uses st.cache_data",
    "st.cache_data" in _MACRO_DATA_SRC,
)
check(
    "7.2 cache TTL is 900 seconds",
    "900" in _MACRO_DATA_SRC and ("ttl=_CACHE_TTL" in _MACRO_DATA_SRC or "ttl=900" in _MACRO_DATA_SRC),
)


# ---------------------------------------------------------------------------
# Section 8 — Page integration (string-based; never imports/renders the page)
# ---------------------------------------------------------------------------

check(
    "8.1 page imports from lib.macro_data",
    "from lib.macro_data import" in _PAGE_SRC,
)
check(
    "8.2 page imports from lib.macro_regime",
    "from lib.macro_regime import" in _PAGE_SRC,
)
check(
    "8.3 page calls fetch_all_macro()",
    "fetch_all_macro()" in _PAGE_SRC,
)
check(
    "8.4 page calls classify_regime(",
    "classify_regime(" in _PAGE_SRC,
)
check(
    "8.5 page defines MACRO_LIVE_MODE feature flag",
    "MACRO_LIVE_MODE" in _PAGE_SRC,
)
check(
    "8.6 MACRO_LIVE_MODE defaults to True",
    "MACRO_LIVE_MODE = True" in _PAGE_SRC,
)
check(
    "8.7 page renders a LIVE badge",
    "LIVE" in _PAGE_SRC,
)
check(
    "8.8 page renders a FIXTURE badge",
    "FIXTURE" in _PAGE_SRC,
)
check(
    "8.9 page shows a data coverage indicator",
    "macro_live_coverage_label" in _PAGE_SRC,
)
check(
    "8.10 page shows a data freshness indicator",
    "macro_live_freshness_label" in _PAGE_SRC,
)
check(
    "8.11 page shows a per-group fixture fallback warning",
    "macro_live_fallback_note" in _PAGE_SRC,
)
# Fixture fallback path preserved (page still uses the Phase 5O fixture builder).
check(
    "8.12 fixture fallback values still present (fixture scenario builder)",
    "build_macro_dashboard_view_by_scenario" in _PAGE_SRC,
)
check(
    "8.13 page retains fail-closed (no fallback to live) language",
    "no fallback to live" in _PAGE_SRC.lower(),
)


# ---------------------------------------------------------------------------
# Section 9 — No positive approved_for_execution authorization (Phase 6A files)
# ---------------------------------------------------------------------------

_PHASE_6A_CODE = {
    "lib/macro_data.py": _MACRO_DATA_SRC,
    "lib/macro_regime.py": _MACRO_REGIME_SRC,
    "pages/8_Macro_Dashboard.py": _PAGE_SRC,
}

_POSITIVE_AUTH_FORMS = [
    "approved_for_execution=True",
    "approved_for_execution = True",
    'approved_for_execution":True',
    'approved_for_execution": True',
    "approved_for_execution: True",
    "approved for execution = True",
]
for fname, src in _PHASE_6A_CODE.items():
    for form in _POSITIVE_AUTH_FORMS:
        check(
            f"9.x {fname} has no positive auth form: {form!r}",
            form not in src,
        )


# ---------------------------------------------------------------------------
# Section 10 — No broker/order/execution capability tokens (Phase 6A files)
# ---------------------------------------------------------------------------

_FORBIDDEN_EXEC_TOKENS = [
    "broker_client",
    "broker_api",
    "BrokerClient",
    "broker_route",
    "broker_payload",
    "order_router",
    "submit_order",
    "place_order",
    "execute_trade",
    "order_ticket",
    "execution_id",
    "quantity_to_execute",
    "order_type",
    "time_in_force",
    "account_id",
    "fill_price",
]
for fname, src in _PHASE_6A_CODE.items():
    for tok in _FORBIDDEN_EXEC_TOKENS:
        check(
            f"10.x {fname} has no broker/order/execution token: {tok!r}",
            tok not in src,
        )


# ---------------------------------------------------------------------------
# Section 11 — Only free data sources are referenced; no paid token
# ---------------------------------------------------------------------------

# The VIX-derived fear/greed proxy substitution must be documented in code.
check(
    "11.1 VIX-derived fear/greed proxy documented in lib/macro_data.py",
    "fear" in _MACRO_DATA_SRC.lower()
    and "percentile" in _MACRO_DATA_SRC.lower()
    and "VIX" in _MACRO_DATA_SRC,
)
# FRED key sourced from FRED_API_KEY env var.
check(
    "11.2 FRED key read from FRED_API_KEY env var",
    'os.getenv("FRED_API_KEY"' in _MACRO_DATA_SRC,
)
# Finnhub key reuses the existing FINNHUB_API_KEY env var.
check(
    "11.3 Finnhub key read from existing FINNHUB_API_KEY env var",
    'os.getenv("FINNHUB_API_KEY"' in _MACRO_DATA_SRC,
)
# No new Finnhub endpoints beyond the two allowed in Phase 6A.
check(
    "11.4 only the allowed Finnhub endpoints are referenced",
    "stock/social-sentiment" in _MACRO_DATA_SRC
    and "/api/v1/news" in _MACRO_DATA_SRC,
)


# ---------------------------------------------------------------------------
# Section 12 — Reliability doc exists with required sections
# ---------------------------------------------------------------------------

_DOC = _read(DOC_PATH)
check("12.1 reliability_phase_6a_live_data_integration.md exists", bool(_DOC.strip()))
_DOC_SECTIONS = [
    "Purpose",
    "What Phase 6A changes",
    "What Phase 6A does not change",
    "Data sources used",
    "CNN Fear & Greed",
    "Fail-closed behavior",
    "Feature flag",
    "Fixture fallback guarantee",
    "Files created or modified",
    "Validation summary",
    "Next phase recommendation",
    "Guardrails",
    "Acceptance criteria",
]
for sec in _DOC_SECTIONS:
    check(f"12.x reliability doc contains section: {sec!r}", sec in _DOC)


# ---------------------------------------------------------------------------
# Section 13 — Resilience regressions (mocked HTTP; no real network)
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, raise_exc=None):
        self.status_code = status_code
        self._json = json_data
        self._raise = raise_exc

    def raise_for_status(self):
        if self._raise is not None:
            raise self._raise

    def json(self):
        return self._json


if _md is not None:
    # 13.1 — Finnhub free-tier reality: /stock/social-sentiment returns HTTP 403
    # (premium), but the free /news feed still yields a LIVE sentiment reading.
    def _sentiment_get(url, params=None, timeout=None, **kw):
        if "social-sentiment" in url:
            return _FakeResp(403, raise_exc=RuntimeError("403 premium"))
        if "news" in url:
            return _FakeResp(
                200,
                json_data=[
                    {"headline": "Stocks surge to record as growth rebounds"},
                    {"headline": "Markets rally on strong earnings beat"},
                ],
            )
        return _FakeResp(200, json_data={})

    _orig_finn = _md.FINNHUB_API_KEY
    try:
        _md.FINNHUB_API_KEY = "testkey"
        with mock.patch.object(_md.requests, "get", _sentiment_get):
            if hasattr(_md.fetch_market_sentiment, "clear"):
                _md.fetch_market_sentiment.clear()
            s = _md.fetch_market_sentiment()
        check(
            "13.1 social 403 (premium) still yields LIVE sentiment via free news",
            s.data_source == "live" and bool(s.news_headlines),
            detail=f"data_source={s.data_source}, headlines={len(s.news_headlines)}",
        )
    finally:
        _md.FINNHUB_API_KEY = _orig_finn
        if hasattr(_md.fetch_market_sentiment, "clear"):
            _md.fetch_market_sentiment.clear()

    # 13.2 — FRED HTTP 429 (rate limit) is retried with back-off, then succeeds.
    _fred_calls = {"n": 0}

    def _fred_get(url, params=None, timeout=None, **kw):
        _fred_calls["n"] += 1
        if _fred_calls["n"] == 1:
            return _FakeResp(429)  # first hit is rate-limited
        return _FakeResp(
            200,
            json_data={
                "observations": [
                    {"date": "2026-05-28", "value": "4.45"},
                    {"date": "2026-05-27", "value": "4.40"},
                ]
            },
        )

    _orig_fred = _md.FRED_API_KEY
    try:
        _md.FRED_API_KEY = "testkey"
        with mock.patch.object(_md.requests, "get", _fred_get):
            obs = _md._fred_observations("DGS10", limit=10, retries=3)
        check(
            "13.2 FRED 429 is retried and then returns observations",
            len(obs) >= 1 and _fred_calls["n"] >= 2,
            detail=f"obs={len(obs)}, calls={_fred_calls['n']}",
        )
    finally:
        _md.FRED_API_KEY = _orig_fred


# ---------------------------------------------------------------------------
# Section 14 — Localization + structured signals (Chinese-mode requirements)
# ---------------------------------------------------------------------------

try:
    import ui_utils as _uu  # noqa: E402
    _EN = _uu.TRANSLATIONS.get("en", {})
    _ZH = _uu.TRANSLATIONS.get("zh", {})
    check("14.0 ui_utils TRANSLATIONS has en + zh", bool(_EN) and bool(_ZH))
except Exception as exc:  # noqa: BLE001
    _EN, _ZH = {}, {}
    check("14.0 ui_utils imports", False, repr(exc))


def _has_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in (s or ""))


# 14.1–14.3 — structured signals parallel to the English key_signals.
if _md is not None and _mr is not None:
    _rr = _mr.classify_regime(_build_macro_data(1.0, "live"))
    check(
        "14.1 MacroRegimeResult exposes a non-empty signals list",
        isinstance(getattr(_rr, "signals", None), list) and bool(_rr.signals),
    )
    check(
        "14.2 signals are parallel to key_signals (same length)",
        len(_rr.signals) == len(_rr.key_signals),
    )
    check(
        "14.3 each signal is a {code, values} record",
        all(isinstance(s, dict) and "code" in s and "values" in s for s in _rr.signals),
    )
    # Degraded path also emits a structured signal.
    _rd = _mr.classify_regime(_build_macro_data(0.3, "fixture"))
    check(
        "14.3b degraded regime emits a 'degraded' structured signal",
        any(s.get("code") == "degraded" for s in (_rd.signals or [])),
    )

# 14.4–14.7 — required localization keys exist in BOTH languages and the ZH
# value is actually different from EN (i.e. it is localized, not a copy).
_LOC_KEYS = [
    "macro_regimeval_risk_on", "macro_regimeval_risk_off",
    "macro_regimeval_transition", "macro_regimeval_degraded",
    "macro_confval_high", "macro_confval_low",
    "macro_biasval_favorable", "macro_biasval_unfavorable", "macro_biasval_cautious",
    "macro_sig_vix_low", "macro_sig_credit_tight", "macro_sig_breadth_broad",
    "macro_sig_curve_inverted", "macro_sig_degraded",
    "macro_status_calm", "macro_status_tight", "macro_status_greed",
    "macro_status_tightening", "macro_status_elevated",
    "macro_posture_text_risk_on", "macro_posture_text_degraded",
    "macro_live_domain_rates", "macro_live_domain_credit",
    "macro_live_domain_liquidity", "macro_live_domain_risk",
    "macro_live_regime_readout", "macro_live_section_signals",
    "macro_theme_impl_risk_on", "macro_theme_impl_risk_off",
]
for k in _LOC_KEYS:
    check(f"14.4 EN has localization key {k!r}", k in _EN)
    check(f"14.5 ZH has localization key {k!r}", k in _ZH)
    check(
        f"14.6 ZH value is localized (differs from EN) for {k!r}",
        bool(_ZH.get(k)) and _ZH.get(k) != _EN.get(k),
    )

# 14.8 — representative ZH values actually contain Chinese characters.
for k in (
    "macro_regimeval_risk_on", "macro_biasval_favorable", "macro_sig_vix_low",
    "macro_status_calm", "macro_posture_text_risk_on", "macro_theme_impl_risk_on",
):
    check(f"14.8 ZH {k!r} contains Chinese characters", _has_cjk(_ZH.get(k)))

# 14.9 — the page wires localization + dynamic sub-regime + live tab renderers.
for token in (
    "macro_regimeval",
    "macro_biasval",
    "macro_confval",
    "macro_sig_",
    "macro_live_domain_",
    "_render_live_tabs",
    "_render_live_indicators",
    "_status_rates",
    "_status_credit",
    "_status_inflation",
    "_signal_line",
    "_posture_text",
    "_sem_badge",       # localized + semantically-colored value badges
    "_render_hero",     # prominent top regime banner
    "_render_trend",    # collapsible history trend tables
    "_bignum",          # enlarged core metric values
):
    check(f"14.9 page wires localization/dynamic token {token!r}", token in _PAGE_SRC)

# 14.10 — visual upgrade: trend history is sourced from macro_data dataclasses.
if _md is not None:
    for cls_name in ("VixResult", "RatesResult", "CreditResult", "DollarResult",
                     "EconomicReleasesResult"):
        cls = getattr(_md, cls_name, None)
        ok = cls is not None and "history" in {f.name for f in dataclasses.fields(cls)}
        check(f"14.10 {cls_name} exposes a history field", ok)
    # The page renders a collapsible trend header + clean (no "/") tab labels.
    check("14.11 page references the trend header key", "macro_trend_header" in _PAGE_SRC)
    check(
        "14.12 cleaned tab labels carry no '/' separators (EN)",
        all("/" not in _EN.get(k, "") for k in (
            "macro_tab_overview", "macro_tab_liquidity", "macro_tab_credit",
            "macro_tab_risk", "macro_tab_provenance",
        )),
    )


# ---------------------------------------------------------------------------
# Section 15 — Professional financial font system (ui_utils global CSS)
# ---------------------------------------------------------------------------

_UU_SRC = _read(os.path.join(_REPO_ROOT, "ui_utils.py"))
check("15.1 ui_utils defines a _FONT_CSS block", "_FONT_CSS" in _UU_SRC)
check(
    "15.2 loads Google Fonts (Inter + JetBrains Mono)",
    "fonts.googleapis.com" in _UU_SRC
    and "JetBrains Mono" in _UU_SRC
    and "Inter" in _UU_SRC,
)
check(
    "15.3 defines --font-sans and --font-mono CSS variables",
    "--font-sans" in _UU_SRC and "--font-mono" in _UU_SRC,
)
check("15.4 numeric elements use tabular-nums", "tabular-nums" in _UU_SRC)
check(
    "15.5 apply_theme injects the font CSS",
    "_FONT_CSS +" in _UU_SRC or "_FONT_CSS+" in _UU_SRC,
)
check(
    "15.6 metric/number values routed through var(--font-mono)",
    "var(--font-mono)" in _UU_SRC,
)
# Page-8 big numbers reduced to 1.6rem, mono, tabular figures.
check("15.7 page big number is 1.6rem", "1.6rem" in _PAGE_SRC)
check("15.8 page big number is no longer 2.4rem", "2.4rem" not in _PAGE_SRC)
check(
    "15.9 page big number uses mono + tabular figures",
    "var(--font-mono)" in _PAGE_SRC and "tabular-nums" in _PAGE_SRC,
)


# ---------------------------------------------------------------------------
# Section 16 — Plotly trend charts inside the history expanders
# ---------------------------------------------------------------------------

check("16.1 page imports plotly", "import plotly" in _PAGE_SRC)
check(
    "16.2 page defines a line-chart helper",
    "_trend_chart" in _PAGE_SRC and "go.Figure" in _PAGE_SRC and "go.Scatter" in _PAGE_SRC,
)
check(
    "16.3 charts reuse apply_layout + apply_legend for global style",
    "apply_layout(" in _PAGE_SRC and "apply_legend(" in _PAGE_SRC,
)
check(
    "16.4 charts are 200px, no legend, no gridlines",
    "height=200" in _PAGE_SRC
    and "showlegend=False" in _PAGE_SRC
    and "showgrid=False" in _PAGE_SRC,
)
check(
    "16.5 line color follows pos/neg semantic (_line_color)",
    "_line_color" in _PAGE_SRC,
)
check(
    "16.6 each chart passes a unique key (no DuplicateElementId)",
    'key=f"macro_trend_' in _PAGE_SRC,
)
check(
    "16.7 rates charts cover 10Y / 2Y / spread",
    "_RATES_CHARTS" in _PAGE_SRC and '"10Y"' in _PAGE_SRC and '"spread"' in _PAGE_SRC,
)
check("16.8 ETF trend renderer exists", "_render_etf_trend" in _PAGE_SRC)
if _md is not None:
    _etf_cls = getattr(_md, "EtfReturnsResult", None)
    check(
        "16.9 EtfReturnsResult exposes a history field (per-ticker series)",
        _etf_cls is not None
        and "history" in {f.name for f in dataclasses.fields(_etf_cls)},
    )


# ---------------------------------------------------------------------------
# Section 17 — Economic-release trend charts + cleaned (no tech-detail) titles
# ---------------------------------------------------------------------------

check("17.1 economic-release trend renderer exists", "_render_releases_trend" in _PAGE_SRC)
check(
    "17.2 releases derive MoM change / MoM% series", "_releases_change_series" in _PAGE_SRC
)
check(
    "17.3 NFP-change / CPI-MoM / PPI-MoM keys exist in EN + ZH",
    all(
        k in _EN and k in _ZH
        for k in ("macro_live_nfp_chg", "macro_live_cpi_mom", "macro_live_ppi_mom")
    ),
)

# Problem 2 — cleaned group/card titles must carry no data-source / API / fixture
# implementation detail and no leftover parentheses.
_GRP_TITLE_KEYS = [
    "macro_live_grp_vix", "macro_live_grp_rates", "macro_live_grp_credit",
    "macro_live_grp_dollar", "macro_live_grp_etf", "macro_live_grp_releases",
    "macro_live_grp_sentiment",
]
_BANNED_TECH = ["FRED", "Finnhub", "yfinance", "DTWEXBGS", "BAMLH0A0HYM2",
                "social-sentiment", "(", "（", "fixture", "FIXTURE"]
for k in _GRP_TITLE_KEYS:
    for _name, _lm in (("EN", _EN), ("ZH", _ZH)):
        val = _lm.get(k, "")
        check(
            f"17.4 {_name} {k} has no technical detail / parenthesis",
            bool(val) and not any(b in val for b in _BANNED_TECH),
            detail=val,
        )

# A few cleaned captions/notes must drop the dev-only tokens.
for k in ("macro_live_mode_caption", "macro_live_fallback_note", "macro_indicators_not_live"):
    for _name, _lm in (("EN", _EN), ("ZH", _ZH)):
        val = _lm.get(k, "")
        check(
            f"17.5 {_name} {k} drops dev tokens (MACRO_LIVE_MODE / source_type / FRED / Finnhub)",
            bool(val)
            and "MACRO_LIVE_MODE" not in val
            and "source_type" not in val
            and "FRED" not in val
            and "Finnhub" not in val,
            detail=val,
        )


# ---------------------------------------------------------------------------
# Section 18 — Overview intro page restructure (user-facing)
# ---------------------------------------------------------------------------

# Simplified title: no version / demo / opportunity-first developer annotations.
check(
    "18.1 EN macro_page_title simplified to 'Macro Dashboard'",
    _EN.get("macro_page_title") == "Macro Dashboard",
)
check("18.2 ZH macro_page_title simplified to '宏观仪表盘'", _ZH.get("macro_page_title") == "宏观仪表盘")
for bad in ("Demo Preview", "v0.1", "Opportunity-first"):
    check(f"18.3 macro_page_title drops dev annotation {bad!r}", bad not in _EN.get("macro_page_title", ""))

# Merged dynamic data-mode banner keys exist and the page renders them.
check(
    "18.4 merged data-mode banner keys exist (EN+ZH)",
    all(k in _EN and k in _ZH for k in ("macro_banner_live", "macro_banner_degraded")),
)
check(
    "18.5 page renders the merged banner driven by coverage",
    "macro_banner_live" in _PAGE_SRC
    and "macro_banner_degraded" in _PAGE_SRC
    and "data_coverage >= 0.5" in _PAGE_SRC,
)

# Three concise overview blocks + six one-line dimensions.
check(
    "18.6 three overview-block keys exist (EN+ZH)",
    all(
        k in _EN and k in _ZH
        for k in ("macro_ov_state", "macro_ov_dimensions", "macro_ov_sources", "macro_ov_sources_desc")
    ),
)
check(
    "18.7 six analysis-dimension keys exist",
    all(
        k in _EN and k in _ZH
        for k in (
            "macro_ov_dim_rates", "macro_ov_dim_credit", "macro_ov_dim_vol",
            "macro_ov_dim_etf", "macro_ov_dim_econ", "macro_ov_dim_sentiment",
        )
    ),
)
check(
    "18.8 page renders the three overview blocks",
    "macro_ov_state" in _PAGE_SRC
    and "macro_ov_dimensions" in _PAGE_SRC
    and "macro_ov_sources" in _PAGE_SRC,
)

# Single short disclaimer; no developer guardrail bullets leak into it.
_disc = _EN.get("macro_safety_headline", "")
check(
    "18.9 disclaimer is the single short research-only line",
    "not investment advice" in _disc.lower()
    and "No live macro API" not in _disc
    and "approved_for_execution" not in _disc,
)

# Demo walkthrough may remain but is collapsed by default (no expanded=True).
check(
    "18.10 demo walkthrough expander is collapsed by default",
    "_render_demo_walkthrough" in _PAGE_SRC
    and 'st.expander(t("macro_walkthrough_header"), expanded=True)' not in _PAGE_SRC,
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("============================================================")
print(f"Phase 6A Live Data Integration Test Results: {PASS} passed, {FAIL} failed")
print("============================================================")
if _failures:
    for f in _failures:
        print(f)

sys.exit(0 if FAIL == 0 else 1)
