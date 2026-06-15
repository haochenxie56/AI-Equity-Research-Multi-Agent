#!/usr/bin/env python3
"""
scripts/test_reliability_phase_6b_signal_layer.py

Phase 6B — Stock Selection Signal Layer test suite.

This test runs **entirely without real API calls**: yfinance is patched to fail,
the Finnhub key is forced empty, and the technical-snapshot helper is patched to
return ``{}`` so every signal computation falls back to its deterministic
fixture/neutral path. It exercises the dataclass contracts, the deterministic
entry-quality + horizon-fit + composite logic, the fail-closed behavior, the
keyword-only (non-LLM) narrative attribution, and the page/UI integration —
without touching the network.

Coverage:
  * lib/signal_engine.py and lib/candidate_generator.py exist and import cleanly.
  * FundamentalSignals / NarrativeSignals / EntryQualityScore /
    TickerSignalResult dataclasses exist with the required fields.
  * score_ticker returns a TickerSignalResult with composite_score in [0, 1].
  * compute_entry_quality returns the correct entry_quality_label for boundary
    RSI / ADX values (>= 4 cases).
  * horizon_fit carries short/mid/long with valid values.
  * fetch_fundamental_signals has a try/except (AST check).
  * narrative attribution is keyword-based, NOT LLM (no llm_orchestrator import
    in lib/signal_engine.py).
  * generate_candidates is callable (mocked) and get_universe returns a capped
    list[str].
  * pages/3_Scanner.py defines SCANNER_SIGNAL_MODE and imports the new modules.
  * No positive approved_for_execution authorization and no broker/order/
    execution token in any modified Phase 6B file.
  * ui_utils.py carries the new Phase 6B t() keys (EN + ZH).

Usage:
    python3 -B scripts/test_reliability_phase_6b_signal_layer.py
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

SIGNAL_ENGINE_PATH = os.path.join(_REPO_ROOT, "lib", "signal_engine.py")
CANDIDATE_GEN_PATH = os.path.join(_REPO_ROOT, "lib", "candidate_generator.py")
SCANNER_PATH = os.path.join(_REPO_ROOT, "pages", "3_Scanner.py")
UI_UTILS_PATH = os.path.join(_REPO_ROOT, "ui_utils.py")
DOC_PATH = os.path.join(_REPO_ROOT, "docs", "reliability_phase_6b_signal_layer.md")

_SE_SRC = _read(SIGNAL_ENGINE_PATH)
_CG_SRC = _read(CANDIDATE_GEN_PATH)
_SCANNER_SRC = _read(SCANNER_PATH)
_UI_SRC = _read(UI_UTILS_PATH)


# ---------------------------------------------------------------------------
# Section 1 — Files exist and import without error
# ---------------------------------------------------------------------------

check("1.1 lib/signal_engine.py exists", os.path.isfile(SIGNAL_ENGINE_PATH))
check("1.2 lib/candidate_generator.py exists", os.path.isfile(CANDIDATE_GEN_PATH))

_se = None
_cg = None
try:
    _se = importlib.import_module("lib.signal_engine")
    check("1.3 lib.signal_engine imports without error", True)
except Exception as exc:  # noqa: BLE001
    check("1.3 lib.signal_engine imports without error", False, repr(exc))

try:
    _cg = importlib.import_module("lib.candidate_generator")
    check("1.4 lib.candidate_generator imports without error", True)
except Exception as exc:  # noqa: BLE001
    check("1.4 lib.candidate_generator imports without error", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 2 — Dataclasses + required fields
# ---------------------------------------------------------------------------

if _se is not None:
    _REQUIRED = {
        "FundamentalSignals": (
            "eps_surprise_trend",
            "recommendation_momentum",
            "valuation_percentile",
            "quality_score",
            "data_source",
        ),
        "NarrativeSignals": (
            "theme_tags",
            "narrative_strength",
            "macro_alignment",
            "data_source",
        ),
        "EntryQualityScore": (
            "distance_from_52w_high",
            "rsi_position",
            "trend_strength",
            "above_sma200",
            "entry_quality_label",
        ),
        "TickerSignalResult": (
            "ticker",
            "fundamental",
            "narrative",
            "entry_quality",
            "composite_score",
            "horizon_fit",
            "signal_summary",
        ),
    }
    for cls_name, fields in _REQUIRED.items():
        cls = getattr(_se, cls_name, None)
        is_dc = cls is not None and dataclasses.is_dataclass(cls)
        check(f"2.1 {cls_name} is a dataclass", is_dc, detail=cls_name)
        if is_dc:
            present = {f.name for f in dataclasses.fields(cls)}
            for req in fields:
                check(
                    f"2.2 {cls_name} has field {req!r}",
                    req in present,
                    detail=str(sorted(present)),
                )


# ---------------------------------------------------------------------------
# Helpers — force the signal engine fully offline (no network, no keys)
# ---------------------------------------------------------------------------


class _BoomYf:
    def __getattr__(self, name):  # any yfinance access raises
        raise RuntimeError("network disabled in test")


_FETCH_FUNCS = ["fetch_fundamental_signals", "fetch_narrative_signals"]


def _clear_se_caches() -> None:
    if _se is None:
        return
    for name in _FETCH_FUNCS + ["_technical_snapshot"]:
        fn = getattr(_se, name, None)
        if fn is not None and hasattr(fn, "clear"):
            try:
                fn.clear()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Section 3 — score_ticker returns a valid TickerSignalResult (mocked)
# ---------------------------------------------------------------------------

if _se is not None:
    check("3.1 score_ticker is callable", callable(getattr(_se, "score_ticker", None)))

    _orig_finn = _se.FINNHUB_API_KEY
    try:
        _se.FINNHUB_API_KEY = ""
        with mock.patch.object(_se, "yf", _BoomYf()), mock.patch.object(
            _se, "_technical_snapshot", lambda *a, **k: {}
        ):
            _clear_se_caches()
            res = _se.score_ticker("TEST", "risk_on")
        check(
            "3.2 score_ticker returns TickerSignalResult",
            isinstance(res, _se.TickerSignalResult),
        )
        if isinstance(res, _se.TickerSignalResult):
            check(
                "3.3 composite_score is a float in [0.0, 1.0]",
                isinstance(res.composite_score, float)
                and 0.0 <= res.composite_score <= 1.0,
                detail=str(res.composite_score),
            )
            check("3.4 result carries the ticker", res.ticker == "TEST")
            check(
                "3.5 signal_summary is a list of <= 5 strings",
                isinstance(res.signal_summary, list)
                and len(res.signal_summary) <= 5
                and all(isinstance(s, str) for s in res.signal_summary),
            )
            # Section 5 — horizon_fit keys + valid values.
            hf = res.horizon_fit
            _VALID_FIT = {"strong_fit", "possible_fit", "weak_fit", "no_fit"}
            check("5.1 horizon_fit is a dict", isinstance(hf, dict))
            for k in ("short", "mid", "long"):
                check(f"5.2 horizon_fit has key {k!r}", isinstance(hf, dict) and k in hf)
                check(
                    f"5.3 horizon_fit[{k!r}] is a valid value",
                    isinstance(hf, dict) and hf.get(k) in _VALID_FIT,
                    detail=str(hf.get(k) if isinstance(hf, dict) else hf),
                )
    finally:
        _se.FINNHUB_API_KEY = _orig_finn
        _clear_se_caches()


# ---------------------------------------------------------------------------
# Section 4 — compute_entry_quality boundary RSI / ADX cases (>= 4)
# ---------------------------------------------------------------------------

if _se is not None:
    ceq = getattr(_se, "compute_entry_quality", None)
    check("4.1 compute_entry_quality is callable", callable(ceq))

    if callable(ceq):
        # Case A: above SMA200, healthy RSI (50), strong trend (ADX 30),
        # near highs -> "good".
        a = ceq("X", {"RSI_14": 50, "ADX": 30, "pct_from_52w_high": -5.0,
                      "above_SMA200": True})
        check("4.2 good entry (RSI 50 / ADX 30 / above SMA200)",
              a.entry_quality_label == "good", detail=a.entry_quality_label)
        check("4.2a rsi_position healthy at RSI=50", a.rsi_position == "healthy")
        check("4.2b trend_strength strong at ADX=30", a.trend_strength == "strong")

        # Case B: overbought RSI (80) -> "avoid".
        b = ceq("X", {"RSI_14": 80, "ADX": 30, "pct_from_52w_high": -1.0,
                      "above_SMA200": True})
        check("4.3 overbought RSI=80 -> avoid",
              b.entry_quality_label == "avoid", detail=b.entry_quality_label)
        check("4.3a rsi_position overbought at RSI=80", b.rsi_position == "overbought")

        # Case C: extended RSI band (70) while above SMA200 -> "extended".
        c = ceq("X", {"RSI_14": 70, "ADX": 30, "pct_from_52w_high": -2.0,
                      "above_SMA200": True})
        check("4.4 extended RSI=70 / above SMA200 -> extended",
              c.entry_quality_label == "extended", detail=c.entry_quality_label)
        check("4.4a rsi_position extended at RSI=70", c.rsi_position == "extended")

        # Case D: below SMA200 + weak trend (ADX 10) -> "avoid".
        d = ceq("X", {"RSI_14": 45, "ADX": 10, "pct_from_52w_high": -30.0,
                      "above_SMA200": False})
        check("4.5 below SMA200 + weak ADX=10 -> avoid",
              d.entry_quality_label == "avoid", detail=d.entry_quality_label)
        check("4.5a trend_strength weak at ADX=10", d.trend_strength == "weak")

        # Case E: above SMA200, healthy RSI, weak trend -> falls through to "fair".
        e = ceq("X", {"RSI_14": 50, "ADX": 10, "pct_from_52w_high": -5.0,
                      "above_SMA200": True})
        check("4.6 healthy RSI but weak trend -> fair",
              e.entry_quality_label == "fair", detail=e.entry_quality_label)
        check("4.6a trend_strength moderate at ADX=20",
              _se._trend_strength(20) == "moderate")

        # RSI boundary at 40 (lower edge of healthy) and 75 (upper edge extended).
        check("4.7 rsi_position oversold at RSI=39",
              _se._rsi_position(39) == "oversold")
        check("4.8 rsi_position healthy at RSI=40",
              _se._rsi_position(40) == "healthy")
        check("4.9 rsi_position overbought at RSI=76",
              _se._rsi_position(76) == "overbought")

        # Empty snapshot -> safe neutral default (never crashes).
        z = ceq("X", {})
        check("4.10 empty snapshot returns an EntryQualityScore",
              isinstance(z, _se.EntryQualityScore))


# ---------------------------------------------------------------------------
# Section 6 — fetch_fundamental_signals has a try/except (AST)
# ---------------------------------------------------------------------------

try:
    _tree = ast.parse(_SE_SRC)
    _defs = {
        node.name: node
        for node in _tree.body
        if isinstance(node, ast.FunctionDef)
    }
    for fname in ("fetch_fundamental_signals", "fetch_narrative_signals"):
        fdef = _defs.get(fname)
        check(f"6.1 {fname} is defined", fdef is not None)
        if fdef is not None:
            has_try = any(isinstance(n, ast.Try) for n in ast.walk(fdef))
            check(f"6.2 {fname} contains a try/except", has_try)
except SyntaxError as exc:
    check("6.0 lib/signal_engine.py parses as valid Python", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 7 — Narrative attribution is keyword-based, NOT LLM
# ---------------------------------------------------------------------------

# No LLM import anywhere in the signal engine. (The module docstring legitimately
# *names* llm_orchestrator to document that it is NOT used, so we assert on the
# import/call forms rather than the bare substring.)
_LLM_IMPORT_FORMS = [
    "import llm_orchestrator",
    "from lib.llm_orchestrator",
    "from llm_orchestrator",
    "import lib.llm_orchestrator",
    "llm_orchestrator.",
]
try:
    _se_tree = ast.parse(_SE_SRC)
    _imported_names = []
    for _n in ast.walk(_se_tree):
        if isinstance(_n, ast.Import):
            _imported_names += [a.name for a in _n.names]
        elif isinstance(_n, ast.ImportFrom):
            _imported_names.append(_n.module or "")
    _llm_imported = any("llm_orchestrator" in (m or "") for m in _imported_names)
except SyntaxError:
    _llm_imported = any(f in _SE_SRC for f in _LLM_IMPORT_FORMS)
check(
    "7.1 lib/signal_engine.py does NOT import or call llm_orchestrator",
    not _llm_imported and "llm_orchestrator." not in _SE_SRC,
)
check(
    "7.2 lib/signal_engine.py imports no anthropic/openai LLM client",
    "anthropic" not in _SE_SRC and "import openai" not in _SE_SRC,
)
# The theme taxonomy + keyword rules exist.
check(
    "7.3 fixed theme taxonomy present",
    "THEME_TAXONOMY" in _SE_SRC and "semiconductor" in _SE_SRC,
)
check(
    "7.4 keyword theme rules present (inline-documented)",
    "_THEME_KEYWORDS" in _SE_SRC,
)
# Keyword attribution actually works deterministically (no model).
if _se is not None and hasattr(_se, "_attribute_themes"):
    tags = _se._attribute_themes(["New AI chip beats estimates", "cloud growth surges"])
    check(
        "7.5 keyword attribution maps headlines to themes",
        "semiconductor" in tags and "AI" in tags,
        detail=str(tags),
    )
    check(
        "7.6 news-but-no-keyword maps to 'other'",
        _se._attribute_themes(["Company holds annual shareholder meeting xyz"]) == ["other"]
        or "other" in _se._attribute_themes(["zzz qqq"]),
    )
    check("7.7 no headlines -> empty theme list", _se._attribute_themes([]) == [])


# ---------------------------------------------------------------------------
# Section 8 — get_universe + generate_candidates (mocked, no network)
# ---------------------------------------------------------------------------

if _cg is not None:
    gu = getattr(_cg, "get_universe", None)
    check("8.1 get_universe is callable", callable(gu))
    if callable(gu):
        uni = gu()
        check("8.2 get_universe returns a list", isinstance(uni, list))
        check(
            "8.3 get_universe returns only strings",
            isinstance(uni, list) and all(isinstance(s, str) for s in uni),
        )
        check(
            "8.4 get_universe is capped at <= 150",
            isinstance(uni, list) and len(uni) <= 150,
            detail=str(len(uni) if isinstance(uni, list) else "n/a"),
        )
        check("8.5 get_universe is non-empty (static S&P top-100)", len(uni) > 0)

    check(
        "8.6 generate_candidates is callable",
        callable(getattr(_cg, "generate_candidates", None)),
    )

    # Mock score_ticker + get_universe so generate_candidates runs offline fast.
    # Build REAL (picklable) TickerSignalResult dataclasses so st.cache_data can
    # serialize the cached return value — matching real runtime behavior.
    _SCORE_BY_TICKER = {"AAA": 0.9, "BBB": 0.7, "CCC": 0.5, "DDD": 0.3}

    def _fake_score(tk, regime):
        return _se.TickerSignalResult(
            ticker=tk,
            fundamental=_se.FundamentalSignals(),
            narrative=_se.NarrativeSignals(),
            entry_quality=_se.EntryQualityScore(),
            composite_score=_SCORE_BY_TICKER.get(tk, 0.4),
            horizon_fit={"short": "possible_fit", "mid": "possible_fit",
                         "long": "weak_fit"},
            signal_summary=["s1", "s2"],
        )

    gc = getattr(_cg, "generate_candidates", None)
    if callable(gc):
        try:
            if hasattr(gc, "clear"):
                gc.clear()
        except Exception:  # noqa: BLE001
            pass
        with mock.patch.object(_cg, "get_universe", lambda: ["AAA", "BBB", "CCC", "DDD"]), \
                mock.patch.object(_cg, "score_ticker", _fake_score):
            try:
                if hasattr(gc, "clear"):
                    gc.clear()
            except Exception:  # noqa: BLE001
                pass
            out = gc("risk_on", top_n=3)
        check("8.7 generate_candidates returns a list (mocked)", isinstance(out, list))
        check("8.8 generate_candidates respects top_n", isinstance(out, list) and len(out) <= 3)
        check(
            "8.9 results sorted by composite_score descending",
            isinstance(out, list)
            and all(
                out[i].composite_score >= out[i + 1].composite_score
                for i in range(len(out) - 1)
            ),
        )


# ---------------------------------------------------------------------------
# Section 9 — pages/3_Scanner.py feature flag + imports
# ---------------------------------------------------------------------------

check("9.1 Scanner exists", bool(_SCANNER_SRC.strip()))
check("9.2 Scanner defines SCANNER_SIGNAL_MODE", "SCANNER_SIGNAL_MODE" in _SCANNER_SRC)
check(
    "9.3 SCANNER_SIGNAL_MODE defaults to True",
    "SCANNER_SIGNAL_MODE = True" in _SCANNER_SRC,
)
check(
    "9.4 Scanner imports from lib.signal_engine",
    "from lib.signal_engine import" in _SCANNER_SRC,
)
check(
    "9.5 Scanner imports from lib.candidate_generator",
    "from lib.candidate_generator import" in _SCANNER_SRC,
)
check(
    "9.6 Scanner imports MacroRegimeResult from lib.macro_regime",
    "from lib.macro_regime import MacroRegimeResult" in _SCANNER_SRC,
)
check(
    "9.7 Scanner calls generate_candidates(",
    "generate_candidates(" in _SCANNER_SRC,
)
check(
    "9.8 Scanner stores results in session_state['signal_candidates']",
    'signal_candidates' in _SCANNER_SRC,
)
check(
    "9.9 Scanner has a Generate-Candidates button via t()",
    'scn_sig_generate_btn' in _SCANNER_SRC,
)
check(
    "9.10 Scanner has a Send-to-Manual-Scanner action via t()",
    'scn_sig_send_btn' in _SCANNER_SRC,
)
check(
    "9.11 Scanner preserves the existing manual pool prefill mechanism",
    "_scanner_pool_prefill" in _SCANNER_SRC,
)
check(
    "9.12 Scanner preserves existing manual run_scan logic",
    "def run_scan(" in _SCANNER_SRC and 'st.session_state["scan_results"]' in _SCANNER_SRC,
)


# ---------------------------------------------------------------------------
# Section 10 — No positive approved_for_execution authorization
# ---------------------------------------------------------------------------

_MODIFIED = {
    "lib/signal_engine.py": _SE_SRC,
    "lib/candidate_generator.py": _CG_SRC,
    "pages/3_Scanner.py": _SCANNER_SRC,
    "ui_utils.py": _UI_SRC,
}

_POSITIVE_AUTH_FORMS = [
    "approved_for_execution=True",
    "approved_for_execution = True",
    'approved_for_execution":True',
    'approved_for_execution": True',
    "approved_for_execution: True",
    "approved for execution = True",
]
for fname, src in _MODIFIED.items():
    for form in _POSITIVE_AUTH_FORMS:
        check(
            f"10.x {fname} has no positive auth form: {form!r}",
            form not in src,
        )


# ---------------------------------------------------------------------------
# Section 11 — No broker/order/execution capability tokens
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
for fname, src in _MODIFIED.items():
    for tok in _FORBIDDEN_EXEC_TOKENS:
        check(
            f"11.x {fname} has no broker/order/execution token: {tok!r}",
            tok not in src,
        )


# ---------------------------------------------------------------------------
# Section 12 — Only free data sources; no paid (Quiver) integration
# ---------------------------------------------------------------------------

check(
    "12.1 signal engine reuses the existing FINNHUB_API_KEY env var",
    'os.getenv("FINNHUB_API_KEY"' in _SE_SRC,
)
check(
    "12.2 only the three allowed Finnhub endpoints are referenced",
    "stock/recommendation" in _SE_SRC
    and "stock/earnings" in _SE_SRC
    and "company-news" in _SE_SRC,
)
# No actual Quiver integration (the docs legitimately name it as EXCLUDED, so we
# assert on the package/endpoint forms, not the bare word).
_QUIVER_INTEGRATION_FORMS = ["quiverquant", "api.quiver", "import quiver", "quiver_api"]
check(
    "12.3 no Quiver Quantitative integration introduced",
    not any(f in _SE_SRC.lower() for f in _QUIVER_INTEGRATION_FORMS)
    and not any(f in _CG_SRC.lower() for f in _QUIVER_INTEGRATION_FORMS),
)
check(
    "12.4 fetch functions cached with TTL=1800",
    "ttl=_CACHE_TTL" in _SE_SRC and "1800" in _SE_SRC,
)
check(
    "12.5 candidate scoring uses a bounded ThreadPoolExecutor(max_workers=8)",
    "ThreadPoolExecutor" in _CG_SRC and "max_workers=8" in _CG_SRC,
)
check(
    "12.6 generate_candidates shows a st.progress bar",
    "st.progress(" in _CG_SRC,
)
check(
    "12.7 hardcoded S&P 500 top-100 universe documented with source/date",
    "SP500_TOP_100" in _CG_SRC and "2026-05" in _CG_SRC,
)


# ---------------------------------------------------------------------------
# Section 13 — ui_utils.py carries the new Phase 6B t() keys (EN + ZH)
# ---------------------------------------------------------------------------

_NEW_KEYS = [
    "scn_sig_title",
    "scn_sig_caption",
    "scn_sig_macro_label",
    "scn_sig_generate_btn",
    "scn_sig_send_btn",
    "scn_sig_generating",
    "scn_sig_empty_hint",
    "scn_sig_col_ticker",
    "scn_sig_col_score",
    "scn_sig_col_entry",
    "scn_sig_col_horizon",
    "scn_sig_col_signals",
    "scn_sig_count",
    "scn_sig_disclaimer",
]
for key in _NEW_KEYS:
    # Each key must appear at least twice (once in the "zh" dict, once in "en").
    check(
        f"13.x ui_utils.py defines {key!r} in both EN and ZH",
        _UI_SRC.count(f'"{key}"') >= 2,
        detail=str(_UI_SRC.count(f'"{key}"')),
    )


# ---------------------------------------------------------------------------
# Section 14 — Phase 6B design doc exists with required sections
# ---------------------------------------------------------------------------

_DOC = _read(DOC_PATH)
check("14.1 reliability_phase_6b_signal_layer.md exists", bool(_DOC.strip()))
_DOC_SECTIONS = [
    "Purpose",
    "What Phase 6B changes",
    "What Phase 6B does not change",
    "Signal computation methodology",
    "Data sources",
    "Fail-closed",
    "feature flag",
    "Ticker universe",
    "Files created or modified",
    "Validation summary",
    "Next phase recommendation",
    "Guardrails",
    "Acceptance criteria",
]
for sec in _DOC_SECTIONS:
    check(f"14.x doc contains section/keyword {sec!r}", sec.lower() in _DOC.lower())


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
for line in _failures:
    print(line)
print()
print(f"Phase 6B — Stock Selection Signal Layer: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
