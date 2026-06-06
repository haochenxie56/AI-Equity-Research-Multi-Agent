#!/usr/bin/env python3
"""
scripts/test_reliability_phase_6b_v2_dual_track.py

Phase 6B v2 — Dual-Track Candidate Architecture test suite.

This test runs **entirely without real API calls**. yfinance is patched to
fail, the Finnhub key is forced empty, the technical-snapshot helper is patched,
and the LLM narrative function is never invoked with a real key — so every
computation exercises the deterministic / fail-closed paths. It verifies the
dual-track dataclasses, the EPS-inflection logic, the Layer 1 hard filter
(low-RSI tickers are NOT excluded; sub-$2B caps ARE), the Track B standalone
trigger, composite/horizon/entry/narrative scoring, and the page/UI integration.

Usage:
    python3 -B scripts/test_reliability_phase_6b_v2_dual_track.py
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
# Section 1 — Modules import cleanly
# ---------------------------------------------------------------------------

_se = None
_cg = None
try:
    _se = importlib.import_module("lib.signal_engine")
    check("1.1 lib.signal_engine imports without error", True)
except Exception as exc:  # noqa: BLE001
    check("1.1 lib.signal_engine imports without error", False, repr(exc))
try:
    _cg = importlib.import_module("lib.candidate_generator")
    check("1.2 lib.candidate_generator imports without error", True)
except Exception as exc:  # noqa: BLE001
    check("1.2 lib.candidate_generator imports without error", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 2 — New dual-track dataclasses exist with required fields
# ---------------------------------------------------------------------------

if _se is not None:
    _REQUIRED = {
        "NarrativeResult": (
            "theme_tags", "narrative_stage", "macro_alignment",
            "narrative_strength", "reasoning", "data_source",
        ),
        "FundamentalResult": (
            "eps_revision_direction", "valuation_percentile", "margin_trend",
            "quality_composite", "data_source",
        ),
        "EntryQualityResult": (
            "rsi_position", "distance_from_52w_high", "trend_strength",
            "above_sma200", "entry_quality_label",
        ),
        "TrackAResult": (
            "layer1_passed", "layer2_narrative", "layer3_fundamental",
            "track_a_score", "entry_quality",
        ),
        "TrackBResult": (
            "insider_buy_signal", "unusual_news_signal", "analyst_revision_signal",
            "track_b_score", "is_standalone_trigger",
        ),
        "TickerSignalResult": (
            "ticker", "track_a", "track_b", "composite_score", "horizon_fit",
            "signal_summary", "candidate_type",
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
# Section 3 — EPS revision: inflecting_up requires a beat AFTER a prior miss
# ---------------------------------------------------------------------------

if _se is not None and hasattr(_se, "_eps_revision_direction"):
    # Finnhub /stock/earnings rows are most-recent-first.
    # Last quarter beat (10>9) after a prior MISS (8<9) -> inflecting_up.
    inflect = [
        {"actual": 10.0, "estimate": 9.0},   # most recent: BEAT
        {"actual": 8.0, "estimate": 9.0},    # prior: MISS
        {"actual": 7.0, "estimate": 9.0},    # MISS
        {"actual": 6.0, "estimate": 9.0},    # MISS
    ]
    check(
        "3.1 inflecting_up when last quarter beats after a prior miss",
        _se._eps_revision_direction(inflect) == "inflecting_up",
        detail=_se._eps_revision_direction(inflect),
    )
    # All four quarters BEAT -> sustained strength, NOT an inflection.
    all_beats = [
        {"actual": 10.0, "estimate": 9.0},
        {"actual": 9.5, "estimate": 9.0},
        {"actual": 9.2, "estimate": 9.0},
        {"actual": 9.1, "estimate": 9.0},
    ]
    direction_all = _se._eps_revision_direction(all_beats)
    check(
        "3.2 all-beats is NOT inflecting_up (it is sustained 'improving')",
        direction_all != "inflecting_up",
        detail=direction_all,
    )
    check("3.3 all-beats classified as 'improving'", direction_all == "improving",
          detail=direction_all)
    # Two consecutive misses -> deteriorating.
    misses = [
        {"actual": 8.0, "estimate": 9.0},
        {"actual": 8.2, "estimate": 9.0},
    ]
    check("3.4 consecutive misses -> deteriorating",
          _se._eps_revision_direction(misses) == "deteriorating",
          detail=_se._eps_revision_direction(misses))
    # Fewer than 2 usable quarters -> unknown.
    check("3.5 <2 usable quarters -> unknown",
          _se._eps_revision_direction([{"actual": 1.0, "estimate": 0.5}]) == "unknown")


# ---------------------------------------------------------------------------
# Section 4 — Layer 1 hard filter (low RSI passes; sub-$2B fails)
# ---------------------------------------------------------------------------

if _se is not None and hasattr(_se, "passes_layer1"):
    # A depressed, low-RSI but large-cap name must PASS Layer 1 (low RSI / far
    # from 52W high are NOT disqualifiers). RSI is not even an input here.
    ok, reason = _se.passes_layer1(
        "BIGCAP", info={"marketCap": 50_000_000_000, "forwardPE": 12.0,
                        "returnOnEquity": 0.2}, ret_30d=-8.0,
    )
    check("4.1 large-cap low-RSI/depressed ticker passes Layer 1", ok is True,
          detail=reason)
    # Sub-$2B market cap -> excluded.
    ok2, reason2 = _se.passes_layer1("SMALL", info={"marketCap": 1_000_000_000})
    check("4.2 sub-$2B market cap fails Layer 1", ok2 is False and reason2 == "market_cap",
          detail=reason2)
    # Catastrophic 30-day decline -> excluded.
    ok3, reason3 = _se.passes_layer1(
        "BROKE", info={"marketCap": 10_000_000_000}, ret_30d=-65.0)
    check("4.3 >50% 30-day decline fails Layer 1", ok3 is False and reason3 == "price_break",
          detail=reason3)
    # Completely-missing fundamentals -> excluded.
    ok4, reason4 = _se.passes_layer1("EMPTY", info={})
    check("4.4 missing fundamentals fails Layer 1", ok4 is False,
          detail=reason4)
    # Layer 1 must NOT take RSI / ADX / momentum as inputs, and the verdict must
    # be invariant to them (behavioral): two low-RSI snapshots cannot change the
    # outcome because RSI is never an argument.
    try:
        _l1 = next(n for n in ast.parse(_SE_SRC).body
                   if isinstance(n, ast.FunctionDef) and n.name == "passes_layer1")
        _params = {a.arg.lower() for a in _l1.args.args}
        check("4.5 passes_layer1 takes no RSI/ADX/momentum parameter",
              not (_params & {"rsi", "adx", "momentum", "snapshot", "technical_snapshot"}),
              detail=str(sorted(_params)))
    except StopIteration:
        check("4.5 passes_layer1 is defined", False)
    # Same large-cap info passes regardless of any (unconsulted) RSI level.
    okA, _ = _se.passes_layer1("LOWRSI", info={"marketCap": 9_000_000_000, "forwardPE": 9.0}, ret_30d=-3.0)
    check("4.6 low-RSI ticker still passes Layer 1 (RSI not a disqualifier)", okA is True)


# ---------------------------------------------------------------------------
# Section 5 — Track B standalone trigger fires at >= 0.7
# ---------------------------------------------------------------------------

if _se is not None and hasattr(_se, "compute_track_b"):
    # All sub-signals maxed -> composite 1.0 -> standalone trigger.
    tb_hi = _se.compute_track_b("X", insider=1.0, unusual=1.0, analyst=1.0)
    check("5.1 track_b composite in [0,1]",
          isinstance(tb_hi.track_b_score, float) and 0.0 <= tb_hi.track_b_score <= 1.0,
          detail=str(tb_hi.track_b_score))
    check("5.2 standalone trigger fires when track_b_score >= 0.7",
          tb_hi.is_standalone_trigger is True, detail=str(tb_hi.track_b_score))
    # Weighted mean: insider .4, unusual .35, analyst .25.
    tb_mid = _se.compute_track_b("X", insider=0.8, unusual=0.8, analyst=0.0)
    # 0.4*0.8 + 0.35*0.8 + 0 = 0.6 -> below threshold -> no trigger.
    check("5.3 below-threshold composite does not standalone-trigger",
          tb_mid.is_standalone_trigger is False, detail=str(tb_mid.track_b_score))
    check("5.4 TRACK_B_TRIGGER threshold is 0.7", _se.TRACK_B_TRIGGER == 0.7)


# ---------------------------------------------------------------------------
# Section 6 — composite_score in [0,1] for FUNNEL and ALT_SIGNAL
# ---------------------------------------------------------------------------

if _se is not None and hasattr(_se, "compute_composite"):
    f_comp = _se.compute_composite(0.8, 0.5, "FUNNEL")
    check("6.1 FUNNEL composite = 0.7*A + 0.3*B in [0,1]",
          isinstance(f_comp, float) and 0.0 <= f_comp <= 1.0
          and abs(f_comp - (0.7 * 0.8 + 0.3 * 0.5)) < 1e-6,
          detail=str(f_comp))
    a_comp = _se.compute_composite(0.0, 0.9, "ALT_SIGNAL")
    check("6.2 ALT_SIGNAL composite = track_b_score in [0,1]",
          isinstance(a_comp, float) and abs(a_comp - 0.9) < 1e-6, detail=str(a_comp))
    both_comp = _se.compute_composite(1.0, 1.0, "BOTH")
    check("6.3 BOTH composite clamped to [0,1]", 0.0 <= both_comp <= 1.0,
          detail=str(both_comp))


# ---------------------------------------------------------------------------
# Section 7 — horizon_fit keys + valid values
# ---------------------------------------------------------------------------

if _se is not None and hasattr(_se, "compute_horizon_fit"):
    _fund = _se.FundamentalResult(
        eps_revision_direction="inflecting_up", valuation_percentile=0.2,
        margin_trend="expanding", quality_composite=0.7,
    )
    _narr = _se.NarrativeResult(narrative_stage="early", narrative_strength="strong",
                                macro_alignment="aligned")
    _entry = _se.EntryQualityResult(entry_quality_label="good")
    hf = _se.compute_horizon_fit(_fund, _narr, _entry, _se._bias_for_regime("risk_on"))
    _VALID_FIT = {"strong_fit", "possible_fit", "weak_fit", "no_fit"}
    check("7.1 horizon_fit is a dict", isinstance(hf, dict))
    for k in ("short", "mid", "long"):
        check(f"7.2 horizon_fit has key {k!r}", isinstance(hf, dict) and k in hf)
        check(f"7.3 horizon_fit[{k!r}] is valid", isinstance(hf, dict) and hf.get(k) in _VALID_FIT,
              detail=str(hf.get(k) if isinstance(hf, dict) else hf))


# ---------------------------------------------------------------------------
# Section 8 — entry "good" applies ×1.1 BOOST (not penalty) to track_a_score
# ---------------------------------------------------------------------------

if _se is not None:
    check("8.1 entry modifier 'good' is 1.1 (a boost)", _se._ENTRY_MODIFIER["good"] == 1.1)
    check("8.2 entry modifier 'good' > 1.0 (not a penalty)", _se._ENTRY_MODIFIER["good"] > 1.0)
    if hasattr(_se, "compute_track_a_score"):
        _fnd = _se.FundamentalResult(eps_revision_direction="improving",
                                     valuation_percentile=0.3, margin_trend="stable",
                                     quality_composite=0.5)
        _nar = _se.NarrativeResult(narrative_stage="growing", narrative_strength="moderate",
                                   macro_alignment="aligned")
        good = _se.compute_track_a_score(_fnd, _nar, _se.EntryQualityResult(entry_quality_label="good"))
        fair = _se.compute_track_a_score(_fnd, _nar, _se.EntryQualityResult(entry_quality_label="fair"))
        avoid = _se.compute_track_a_score(_fnd, _nar, _se.EntryQualityResult(entry_quality_label="avoid"))
        check("8.3 'good' entry boosts track_a_score above 'fair'", good >= fair,
              detail=f"good={good} fair={fair}")
        check("8.4 'avoid' entry penalizes below 'fair'", avoid <= fair,
              detail=f"avoid={avoid} fair={fair}")
    # Oversold + far-from-52W-high entry quality is "good" (the MU boost case),
    # NOT a penalty.
    if hasattr(_se, "compute_entry_quality"):
        mu = _se.compute_entry_quality("MU", {"RSI_14": 32, "ADX": 18,
                                              "pct_from_52w_high": -40.0,
                                              "above_SMA200": False})
        check("8.5 oversold + far-from-52W-high -> 'good' entry (cycle-bottom boost)",
              mu.entry_quality_label == "good", detail=mu.entry_quality_label)


# ---------------------------------------------------------------------------
# Section 9 — narrative_stage "early" scores higher than "mature"
# ---------------------------------------------------------------------------

if _se is not None and hasattr(_se, "_narrative_score"):
    early = _se._narrative_score(_se.NarrativeResult(narrative_stage="early",
                                                     macro_alignment="neutral",
                                                     narrative_strength="moderate"))
    mature = _se._narrative_score(_se.NarrativeResult(narrative_stage="mature",
                                                      macro_alignment="neutral",
                                                      narrative_strength="moderate"))
    check("9.1 narrative 'early' scores higher than 'mature'", early > mature,
          detail=f"early={early} mature={mature}")
    check("9.2 stage score map: early=1.0 > growing=0.75 > mature=0.3 > cooling=0.1",
          _se._STAGE_SCORE["early"] > _se._STAGE_SCORE["growing"]
          > _se._STAGE_SCORE["mature"] > _se._STAGE_SCORE["cooling"])


# ---------------------------------------------------------------------------
# Section 10 — signal_engine does NOT import llm_orchestrator at MODULE level
# ---------------------------------------------------------------------------

try:
    _tree = ast.parse(_SE_SRC)
    _module_level_imports: list[str] = []
    for node in _tree.body:  # MODULE level only (not ast.walk)
        if isinstance(node, ast.Import):
            _module_level_imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            _module_level_imports.append(node.module or "")
    _mod_llm = any("llm_orchestrator" in (m or "") for m in _module_level_imports)
    check("10.1 signal_engine does NOT import llm_orchestrator at module level",
          not _mod_llm, detail=str(_module_level_imports))
    # It DOES import it inside the LLM function (in-function import present).
    _has_infn_llm = "from lib import llm_orchestrator" in _SE_SRC
    check("10.2 signal_engine imports llm_orchestrator inside the LLM function",
          _has_infn_llm)
    # No module-level ui_utils / pages import either.
    _mod_ui = any(("ui_utils" in (m or "") or (m or "").startswith("pages"))
                  for m in _module_level_imports)
    check("10.3 signal_engine does NOT import ui_utils / pages at module level",
          not _mod_ui, detail=str(_module_level_imports))
except SyntaxError as exc:
    check("10.0 lib/signal_engine.py parses as valid Python", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 11 — fetch functions are fail-closed (try/except) + offline result
# ---------------------------------------------------------------------------

if _se is not None:
    _ast = ast.parse(_SE_SRC)
    _defs = {n.name: n for n in _ast.body if isinstance(n, ast.FunctionDef)}
    for fname in ("fetch_fundamental", "fetch_company_news", "fetch_insider_signal",
                  "fetch_unusual_news_signal", "fetch_analyst_revision_signal",
                  "llm_narrative_match"):
        fdef = _defs.get(fname)
        check(f"11.1 {fname} is defined", fdef is not None)
        if fdef is not None:
            check(f"11.2 {fname} contains a try/except",
                  any(isinstance(n, ast.Try) for n in ast.walk(fdef)))

    # Offline: force no Finnhub key + yfinance failure -> build_ticker_result still
    # produces a valid result with composite in [0,1] and a valid candidate_type.
    _orig_key = _se.FINNHUB_API_KEY
    try:
        _se.FINNHUB_API_KEY = ""
        fund = _se.FundamentalResult()
        narr = _se.neutral_narrative()
        entry = _se.compute_entry_quality("X", {})
        tb = _se.compute_track_b("X", 0.0, 0.0, 0.0)
        res = _se.build_ticker_result("X", fund, narr, entry, tb, "risk_on", layer1_passed=True)
        check("11.3 build_ticker_result returns a TickerSignalResult",
              isinstance(res, _se.TickerSignalResult))
        check("11.4 composite_score in [0,1]",
              isinstance(res.composite_score, float) and 0.0 <= res.composite_score <= 1.0,
              detail=str(res.composite_score))
        check("11.5 candidate_type is one of FUNNEL/ALT_SIGNAL/BOTH",
              res.candidate_type in ("FUNNEL", "ALT_SIGNAL", "BOTH"),
              detail=res.candidate_type)
        # An ALT_SIGNAL-only result (no funnel pass) also has composite in [0,1].
        res_alt = _se.build_ticker_result("Y", fund, narr, entry,
                                          _se.compute_track_b("Y", 1.0, 1.0, 1.0),
                                          "risk_on", layer1_passed=False)
        check("11.6 ALT_SIGNAL result labeled correctly",
              res_alt.candidate_type == "ALT_SIGNAL", detail=res_alt.candidate_type)
        check("11.7 ALT_SIGNAL composite in [0,1]",
              0.0 <= res_alt.composite_score <= 1.0, detail=str(res_alt.composite_score))
    finally:
        _se.FINNHUB_API_KEY = _orig_key


# ---------------------------------------------------------------------------
# Section 12 — candidate_generator dual-track stage functions exist + offline
# ---------------------------------------------------------------------------

if _cg is not None:
    for fn in ("get_universe", "run_layer1_filter", "run_layer2_narrative",
               "run_layer3_fundamental", "run_track_b", "generate_candidates"):
        check(f"12.1 candidate_generator.{fn} is callable",
              callable(getattr(_cg, fn, None)), detail=fn)

    uni = _cg.get_universe()
    check("12.2 get_universe returns a capped list[str]",
          isinstance(uni, list) and all(isinstance(s, str) for s in uni) and len(uni) <= 150,
          detail=str(len(uni)))
    check("12.3 universe includes MU (cycle-bottom candidate is reachable)", "MU" in uni)

    # generate_candidates offline: patch get_universe small + force everything
    # fail-closed (no key, yfinance boom, neutral snapshots) -> returns a list,
    # respecting top_n, never raising.
    if _se is not None:
        _orig_key = _se.FINNHUB_API_KEY
        gc = _cg.generate_candidates
        try:
            if hasattr(gc, "clear"):
                gc.clear()
        except Exception:  # noqa: BLE001
            pass
        try:
            _se.FINNHUB_API_KEY = ""

            class _BoomYf:
                def __getattr__(self, name):
                    raise RuntimeError("network disabled in test")

            with mock.patch.object(_cg, "get_universe", lambda: ["MU", "NVDA", "AAPL"]), \
                    mock.patch.object(_se, "yf", _BoomYf()), \
                    mock.patch.object(_se, "_technical_snapshot", lambda *a, **k: {}), \
                    mock.patch.object(_cg, "_technical_snapshot", lambda *a, **k: {}), \
                    mock.patch.object(_se, "llm_narrative_match",
                                      lambda *a, **k: _se.neutral_narrative()):
                try:
                    if hasattr(gc, "clear"):
                        gc.clear()
                except Exception:  # noqa: BLE001
                    pass
                out = gc("risk_on", top_n=2, llm_n=10)
            check("12.4 generate_candidates returns a list (offline)", isinstance(out, list))
            check("12.5 generate_candidates is fail-closed (no exception)", True)
            check("12.6 every result is a TickerSignalResult with composite in [0,1]",
                  all(isinstance(r, _se.TickerSignalResult)
                      and 0.0 <= r.composite_score <= 1.0 for r in out))
        except Exception as exc:  # noqa: BLE001
            check("12.5 generate_candidates is fail-closed (no exception)", False, repr(exc))
        finally:
            _se.FINNHUB_API_KEY = _orig_key
            try:
                if hasattr(gc, "clear"):
                    gc.clear()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Section 13 — Scanner page integration (feature flag, slider, imports)
# ---------------------------------------------------------------------------

check("13.1 Scanner defines SCANNER_SIGNAL_MODE", "SCANNER_SIGNAL_MODE" in _SCANNER_SRC)
check("13.2 SCANNER_SIGNAL_MODE defaults to True", "SCANNER_SIGNAL_MODE = True" in _SCANNER_SRC)
check("13.3 Scanner has an LLM narrative-depth slider",
      "scn_sig_llm_depth" in _SCANNER_SRC and "st.slider(" in _SCANNER_SRC)
check("13.4 Scanner passes llm_n to generate_candidates",
      "llm_n=" in _SCANNER_SRC and "generate_candidates(" in _SCANNER_SRC)
check("13.5 Scanner renders a candidate Type column",
      "scn_sig_col_type" in _SCANNER_SRC and "candidate_type" in _SCANNER_SRC)
check("13.6 Scanner shows Track A / Track B sub-scores",
      "scn_sig_col_track_a" in _SCANNER_SRC and "scn_sig_col_track_b" in _SCANNER_SRC
      and "track_a" in _SCANNER_SRC and "track_b" in _SCANNER_SRC)
check("13.7 Scanner imports from lib.signal_engine", "from lib.signal_engine import" in _SCANNER_SRC)
check("13.8 Scanner imports from lib.candidate_generator", "from lib.candidate_generator import" in _SCANNER_SRC)
check("13.9 Scanner preserves the manual run_scan logic",
      "def run_scan(" in _SCANNER_SRC and 'st.session_state["scan_results"]' in _SCANNER_SRC)


# ---------------------------------------------------------------------------
# Section 14 — ui_utils carries the new Phase 6B v2 t() keys (EN + ZH)
# ---------------------------------------------------------------------------

_NEW_KEYS = [
    "scn_sig_llm_depth", "scn_sig_llm_help", "scn_sig_llm_est", "scn_sig_col_type",
    "scn_sig_subscores", "scn_sig_col_track_a", "scn_sig_col_track_b",
    "scn_sig_col_insider", "scn_sig_col_unusual", "scn_sig_col_analyst",
]
for key in _NEW_KEYS:
    check(f"14.x ui_utils defines {key!r} in both EN and ZH",
          _UI_SRC.count(f'"{key}"') >= 2, detail=str(_UI_SRC.count(f'"{key}"')))


# ---------------------------------------------------------------------------
# Section 15 — No execution / no broker / no positive approved_for_execution
# ---------------------------------------------------------------------------

_MODIFIED = {
    "lib/signal_engine.py": _SE_SRC,
    "lib/candidate_generator.py": _CG_SRC,
    "pages/3_Scanner.py": _SCANNER_SRC,
    "ui_utils.py": _UI_SRC,
}
_POSITIVE_AUTH_FORMS = [
    "approved_for_execution=True", "approved_for_execution = True",
    'approved_for_execution":True', 'approved_for_execution": True',
    "approved_for_execution: True",
]
for fname, src in _MODIFIED.items():
    for form in _POSITIVE_AUTH_FORMS:
        check(f"15.1 {fname} has no positive auth: {form!r}", form not in src)

_FORBIDDEN_EXEC = [
    "broker_client", "broker_api", "BrokerClient", "broker_route", "broker_payload",
    "order_router", "submit_order", "place_order", "execute_trade", "order_ticket",
    "execution_id", "quantity_to_execute", "time_in_force", "account_id", "fill_price",
]
for fname, src in _MODIFIED.items():
    for tok in _FORBIDDEN_EXEC:
        check(f"15.2 {fname} has no exec token: {tok!r}", tok not in src)


# ---------------------------------------------------------------------------
# Section 16 — Only free sources; no paid (Quiver / Unusual Whales) integration
# ---------------------------------------------------------------------------

check("16.1 signal engine reuses the existing FINNHUB_API_KEY env var",
      'os.getenv("FINNHUB_API_KEY"' in _SE_SRC)
check("16.2 Track B insider uses Finnhub /stock/insider-transactions",
      "stock/insider-transactions" in _SE_SRC)
_PAID_FORMS = ["quiverquant", "api.quiver", "import quiver", "quiver_api",
               "unusualwhales", "unusual-whales", "api.unusualwhales"]
check("16.3 no Quiver / Unusual Whales integration introduced",
      not any(f in _SE_SRC.lower() for f in _PAID_FORMS)
      and not any(f in _CG_SRC.lower() for f in _PAID_FORMS))
check("16.4 LLM narrative cache uses TTL=3600", "_LLM_CACHE_TTL = 3600" in _SE_SRC)
check("16.5 network fetch cache uses TTL=1800", "_CACHE_TTL = 1800" in _SE_SRC)
check("16.6 candidate scoring uses a bounded ThreadPoolExecutor",
      "ThreadPoolExecutor" in _CG_SRC)
check("16.7 generate_candidates shows a st.progress bar", "st.progress(" in _CG_SRC)


# ---------------------------------------------------------------------------
# Section 17 — Doc carries the v2 Dual-Track section
# ---------------------------------------------------------------------------

_DOC = _read(DOC_PATH)
check("17.1 design doc exists", bool(_DOC.strip()))
for kw in ("v2 Dual-Track Architecture", "Track A", "Track B", "inflecting_up",
           "standalone trigger", "entry quality"):
    check(f"17.x doc mentions {kw!r}", kw.lower() in _DOC.lower())


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
for line in _failures:
    print(line)
print()
print(f"Phase 6B v2 — Dual-Track Candidate Architecture: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
