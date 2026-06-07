#!/usr/bin/env python3
"""
scripts/test_reliability_phase_6b_v3_horizon_scoring.py

Phase 6B v3 — Horizon-Native Three-Track Signal Scoring test suite.

This test runs **entirely without real API calls**. The Finnhub key is forced
empty, yfinance/technical fetches are never exercised live, and the LLM narrative
function is patched / never invoked with a real key — so every computation
exercises the deterministic / fail-closed paths.

It verifies the new ``CandidateSignal`` dataclass, the three INDEPENDENT horizon
scores (short / mid / long) with their documented weights, the
``horizons_hit`` / ``signal_strength`` derivation, the merged-LLM catalyst
fields + safe defaults, the code-generated ``key_signals`` priority order, the
Cockpit ``st.session_state`` hand-off keys, and the Scanner signal-card wiring.

Usage:
    python3 -B scripts/test_reliability_phase_6b_v3_horizon_scoring.py
"""

from __future__ import annotations

import dataclasses
import importlib
import os
import sys
import types
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
# Section 2 — CandidateSignal dataclass has all required fields
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = (
    "ticker", "short_score", "mid_score", "long_score", "horizons_hit",
    "signal_strength", "catalyst_summary", "catalyst_horizon", "catalyst_recency",
    "already_priced_in", "narrative_stage", "narrative_theme_tags",
    "eps_revision_direction", "valuation_percentile", "entry_quality_label",
    "track_b_score", "candidate_type", "key_signals", "data_coverage",
)

if _se is not None:
    cs = getattr(_se, "CandidateSignal", None)
    is_dc = cs is not None and dataclasses.is_dataclass(cs)
    check("2.1 CandidateSignal is a dataclass", is_dc)
    if is_dc:
        present = {f.name for f in dataclasses.fields(cs)}
        for req in _REQUIRED_FIELDS:
            check(f"2.2 CandidateSignal has field {req!r}", req in present,
                  detail=str(sorted(present)))
    # CandidateSignal subclasses the v2 TickerSignalResult (keeps v2 consumers
    # working — isinstance + composite_score + horizon_fit + candidate_type).
    check("2.3 CandidateSignal subclasses TickerSignalResult",
          cs is not None and issubclass(cs, _se.TickerSignalResult))


# ---------------------------------------------------------------------------
# Section 3 — Three INDEPENDENT horizon scores, each in [0,1], correct weights
# ---------------------------------------------------------------------------

if _se is not None:
    # Weight constants (greppable + AST-stable) match the contract.
    check("3.1 short technical_momentum weight is 0.40", "_SHORT_W_TECH = 0.40" in _SE_SRC)
    check("3.2 mid eps_revision weight is 0.35", "_MID_W_EPS = 0.35" in _SE_SRC)
    check("3.3 long valuation weight is 0.35", "_LONG_W_VALUATION = 0.35" in _SE_SRC)
    check("3.4 short weights sum to 1.0",
          abs(_se._SHORT_W_TECH + _se._SHORT_W_CATALYST + _se._SHORT_W_MOMENTUM - 1.0) < 1e-9)
    check("3.5 mid weights sum to 1.0",
          abs(_se._MID_W_EPS + _se._MID_W_NARRATIVE + _se._MID_W_VALUATION + _se._MID_W_QUALITY - 1.0) < 1e-9)
    check("3.6 long weights sum to 1.0",
          abs(_se._LONG_W_VALUATION + _se._LONG_W_QUALITY + _se._LONG_W_NARRATIVE + _se._LONG_W_MACRO - 1.0) < 1e-9)
    # Thresholds.
    check("3.7 short threshold 0.65", _se._SHORT_THRESHOLD == 0.65)
    check("3.8 mid threshold 0.60", _se._MID_THRESHOLD == 0.60)
    check("3.9 long threshold 0.55", _se._LONG_THRESHOLD == 0.55)

    # End-to-end: a strong "triple" candidate. All three scores high and in [0,1].
    strong_fund = _se.FundamentalResult(
        eps_revision_direction="inflecting_up", valuation_percentile=0.1,
        margin_trend="expanding", quality_composite=0.8,
    )
    strong_narr = _se.NarrativeResult(
        narrative_stage="early", macro_alignment="aligned",
        narrative_strength="strong", theme_tags=["AI"],
        catalyst_summary="Major multi-year contract awarded",
        catalyst_horizon=["short"], catalyst_recency="recent",
        already_priced_in=False, data_source="live",
    )
    strong_entry = _se.EntryQualityResult(entry_quality_label="good",
                                          rsi_position="healthy")
    strong_snap = {"RSI_14": 55, "ADX": 30, "Vol_ratio_20d": 1.5,
                   "above_SMA200": True, "ret_1m": 15.0}
    strong_tb = _se.compute_track_b("X", 0.0, 0.0, 0.0)
    triple = _se.build_candidate_signal(
        "STRONG", strong_fund, strong_narr, strong_entry, strong_tb,
        strong_snap, "risk_on", layer1_passed=True,
    )
    for fld in ("short_score", "mid_score", "long_score"):
        v = getattr(triple, fld)
        check(f"3.10 {fld} in [0,1]", isinstance(v, float) and 0.0 <= v <= 1.0,
              detail=str(v))


# ---------------------------------------------------------------------------
# Section 4 — horizons_hit derivation + signal_strength mapping
# ---------------------------------------------------------------------------

if _se is not None:
    # Threshold-precise: short>=0.65, mid>=0.60, long>=0.55.
    hh = _se.derive_horizons_hit(0.70, 0.50, 0.60)  # short hit, mid miss, long hit
    check("4.1 horizons_hit applies per-horizon thresholds",
          hh == ["short", "long"], detail=str(hh))
    hh_edge = _se.derive_horizons_hit(0.65, 0.60, 0.55)  # all exactly at threshold
    check("4.2 horizons_hit is inclusive at the threshold",
          hh_edge == ["short", "mid", "long"], detail=str(hh_edge))
    hh_below = _se.derive_horizons_hit(0.649, 0.599, 0.549)  # all just below
    check("4.3 horizons_hit empty when all just below threshold",
          hh_below == [], detail=str(hh_below))
    check("4.4 signal_strength 'triple' when 3 horizons hit",
          _se.derive_signal_strength(["short", "mid", "long"]) == "triple")
    check("4.5 signal_strength 'double' when 2 horizons hit",
          _se.derive_signal_strength(["short", "long"]) == "double")
    check("4.6 signal_strength 'single' when 1 horizon hit",
          _se.derive_signal_strength(["mid"]) == "single")
    check("4.7 signal_strength 'none' when 0 horizons hit",
          _se.derive_signal_strength([]) == "none")

    # End-to-end triple.
    check("4.8 strong candidate is a triple signal",
          triple.signal_strength == "triple"
          and set(triple.horizons_hit) == {"short", "mid", "long"},
          detail=f"{triple.signal_strength} {triple.horizons_hit}")

    # End-to-end none: everything weak.
    weak_fund = _se.FundamentalResult(
        eps_revision_direction="deteriorating", valuation_percentile=0.9,
        margin_trend="contracting", quality_composite=0.0,
    )
    weak_narr = _se.NarrativeResult(narrative_stage="cooling",
                                    macro_alignment="misaligned",
                                    narrative_strength="none")
    weak_entry = _se.EntryQualityResult(entry_quality_label="avoid",
                                        rsi_position="overbought")
    weak_snap = {"RSI_14": 80, "ADX": 10, "Vol_ratio_20d": 0.8,
                 "above_SMA200": False, "ret_1m": -12.0}
    weak_tb = _se.compute_track_b("Y", 0.0, 0.0, 0.0)
    none_cand = _se.build_candidate_signal(
        "WEAK", weak_fund, weak_narr, weak_entry, weak_tb, weak_snap,
        "risk_off", layer1_passed=True,
    )
    check("4.9 weak candidate is a 'none' signal",
          none_cand.signal_strength == "none" and none_cand.horizons_hit == [],
          detail=f"{none_cand.signal_strength} s={none_cand.short_score} "
                 f"m={none_cand.mid_score} l={none_cand.long_score}")


# ---------------------------------------------------------------------------
# Section 5 — key_signals priority: triple badge FIRST for a triple hit
# ---------------------------------------------------------------------------

if _se is not None:
    ks = triple.key_signals
    check("5.1 key_signals is a non-empty list (<=5)",
          isinstance(ks, list) and 0 < len(ks) <= 5, detail=str(ks))
    check("5.2 'Triple signal' appears in key_signals for a triple hit",
          any("Triple signal" in str(k) for k in ks), detail=str(ks))
    check("5.3 the triple-signal line is FIRST in key_signals",
          bool(ks) and "Triple signal" in str(ks[0]), detail=str(ks[:1]))
    # A non-triple candidate must NOT carry the triple badge.
    check("5.4 'none' candidate has no 'Triple signal' line",
          not any("Triple signal" in str(k) for k in none_cand.key_signals),
          detail=str(none_cand.key_signals))


# ---------------------------------------------------------------------------
# Section 6 — Catalyst fields default to SAFE values on LLM parse failure
# ---------------------------------------------------------------------------

if _se is not None:
    nn = _se.neutral_narrative()
    check("6.1 neutral_narrative catalyst_summary is empty", nn.catalyst_summary == "")
    check("6.2 neutral_narrative catalyst_horizon is empty list", nn.catalyst_horizon == [])
    check("6.3 neutral_narrative catalyst_recency is 'none'", nn.catalyst_recency == "none")
    check("6.4 neutral_narrative already_priced_in is False", nn.already_priced_in is False)

    # Parse failure path: news present + key present, but the JSON call returns a
    # non-dict (unparseable) -> fail-closed to neutral_narrative (safe catalyst).
    _orig_key = _se.FINNHUB_API_KEY
    try:
        _se.FINNHUB_API_KEY = "x"
        try:
            _se.llm_narrative_match.clear()
        except Exception:  # noqa: BLE001
            pass
        import lib.llm_orchestrator as _llm
        with mock.patch.object(_se, "fetch_company_news",
                               lambda *a, **k: [{"headline": "h", "summary": "s", "datetime": 0}]), \
                mock.patch.object(_se, "_has_llm_api_key", lambda: True), \
                mock.patch.object(_llm, "_get_client", lambda: object()), \
                mock.patch.object(_llm, "_llm_json_call", lambda *a, **k: "not-a-dict"):
            res = _se.llm_narrative_match("ZZZ", "risk_on")
        check("6.5 parse-failure (non-dict) -> safe catalyst defaults",
              res.catalyst_summary == "" and res.catalyst_horizon == []
              and res.catalyst_recency == "none" and res.already_priced_in is False,
              detail=str(res))
    finally:
        _se.FINNHUB_API_KEY = _orig_key
        try:
            _se.llm_narrative_match.clear()
        except Exception:  # noqa: BLE001
            pass

    # Catalyst detection is merged into the SINGLE narrative call (no second LLM
    # function) and the merged prompt requests the catalyst fields.
    check("6.6 catalyst is merged into llm_narrative_match (single LLM call)",
          "catalyst_summary" in _SE_SRC and "catalyst_recency" in _SE_SRC
          and _SE_SRC.count("def llm_narrative_match") == 1)
    check("6.7 already_priced_in warning logic exists in signal_engine.py",
          "already_priced_in" in _SE_SRC)


# ---------------------------------------------------------------------------
# Section 7 — Track B standalone trigger still fires at track_b_score >= 0.7
# ---------------------------------------------------------------------------

if _se is not None:
    check("7.1 TRACK_B_TRIGGER threshold is 0.7", _se.TRACK_B_TRIGGER == 0.7)
    tb_hi = _se.compute_track_b("X", insider=1.0, unusual=1.0, analyst=1.0)
    check("7.2 standalone trigger fires when track_b_score >= 0.7",
          tb_hi.is_standalone_trigger is True, detail=str(tb_hi.track_b_score))
    # An ALT_SIGNAL candidate (did NOT pass funnel) still gets horizon scores and
    # is labeled ALT_SIGNAL, and exposes track_b_score.
    alt = _se.build_candidate_signal(
        "ALTX", _se.FundamentalResult(), _se.neutral_narrative(),
        _se.EntryQualityResult(), tb_hi, {}, "risk_on", layer1_passed=False,
    )
    check("7.3 ALT_SIGNAL labeled when layer1 not passed but Track B triggers",
          alt.candidate_type == "ALT_SIGNAL", detail=alt.candidate_type)
    check("7.4 ALT_SIGNAL still has short/mid/long horizon scores in [0,1]",
          all(0.0 <= getattr(alt, f) <= 1.0 for f in ("short_score", "mid_score", "long_score")))
    check("7.5 ALT_SIGNAL exposes track_b_score", abs(alt.track_b_score - tb_hi.track_b_score) < 1e-9)


# ---------------------------------------------------------------------------
# Section 8 — Cockpit session_state hand-off (triple + all signals)
# ---------------------------------------------------------------------------

if _se is not None and _cg is not None:
    fake_st = types.SimpleNamespace(session_state={})
    with mock.patch.object(_cg, "st", fake_st), \
            mock.patch.object(_cg, "_generate_candidates_cached",
                              lambda *a, **k: [triple, none_cand, alt]):
        out = _cg.generate_candidates("risk_on", top_n=5, llm_n=10)
    ss = fake_st.session_state
    check("8.1 generate_candidates returns the candidate list", isinstance(out, list) and len(out) == 3)
    check("8.2 cockpit_triple_signals written to session_state",
          "cockpit_triple_signals" in ss)
    check("8.3 cockpit_all_signals written to session_state",
          "cockpit_all_signals" in ss)
    trip = ss.get("cockpit_triple_signals", [])
    alls = ss.get("cockpit_all_signals", [])
    check("8.4 only triple-hit candidates in cockpit_triple_signals",
          [r["ticker"] for r in trip] == ["STRONG"]
          and all(r["signal_strength"] == "triple" for r in trip),
          detail=str([r.get("ticker") for r in trip]))
    check("8.5 all candidates in cockpit_all_signals",
          {r["ticker"] for r in alls} == {"STRONG", "WEAK", "ALTX"},
          detail=str([r.get("ticker") for r in alls]))
    if trip:
        rec = trip[0]
        for fld in ("ticker", "short_score", "mid_score", "long_score",
                    "catalyst_summary", "key_signals", "signal_strength", "timestamp"):
            check(f"8.6 triple hand-off record has {fld!r}", fld in rec,
                  detail=str(sorted(rec.keys())))
    # cockpit_all_signals records carry a signal_strength field for every entry.
    check("8.7 every cockpit_all_signals record has a signal_strength field",
          all("signal_strength" in r for r in alls))


# ---------------------------------------------------------------------------
# Section 9 — Sort order: triple first, then double, single, none
# ---------------------------------------------------------------------------

if _se is not None and _cg is not None:
    # _generate_candidates_cached final sort is keyed by strength then avg.
    check("9.1 candidate_generator defines a strength-rank sort key",
          "_strength_rank" in _CG_SRC and "_horizon_avg" in _CG_SRC)
    check("9.2 _strength_rank orders triple>double>single>none",
          _cg._strength_rank("triple") > _cg._strength_rank("double")
          > _cg._strength_rank("single") > _cg._strength_rank("none"))


# ---------------------------------------------------------------------------
# Section 10 — Scanner page wiring (flag, signal cards, gold border, filter)
# ---------------------------------------------------------------------------

check("10.1 Scanner defines SCANNER_SIGNAL_MODE", "SCANNER_SIGNAL_MODE" in _SCANNER_SRC)
check("10.2 SCANNER_SIGNAL_MODE defaults to True", "SCANNER_SIGNAL_MODE = True" in _SCANNER_SRC)
check("10.3 Scanner renders signal cards via st.container(border=True)",
      "st.container(border=True)" in _SCANNER_SRC)
check("10.4 Scanner has triple-hit gold border rendering logic",
      "triple" in _SCANNER_SRC and "#d4a017" in _SCANNER_SRC)
check("10.5 Scanner has horizon filter checkboxes",
      "scn_sig_hz_short" in _SCANNER_SRC and "scn_sig_hz_mid" in _SCANNER_SRC
      and "scn_sig_hz_long" in _SCANNER_SRC and "st.checkbox(" in _SCANNER_SRC)
check("10.6 Scanner filters on horizons_hit",
      "horizons_hit" in _SCANNER_SRC)
check("10.7 Scanner renders the score pills with ✓/○ hit markers",
      "✓" in _SCANNER_SRC and "○" in _SCANNER_SRC)
check("10.8 Scanner shows the summary line",
      "scn_sig_summary" in _SCANNER_SRC)
check("10.9 Scanner preserves the manual run_scan logic",
      "def run_scan(" in _SCANNER_SRC and 'st.session_state["scan_results"]' in _SCANNER_SRC)
check("10.10 Scanner writes triple-hit signals via the generator hand-off",
      "cockpit_triple_signals" in _CG_SRC)


# ---------------------------------------------------------------------------
# Section 11 — ui_utils carries the new Phase 6B v3 t() keys (EN + ZH)
# ---------------------------------------------------------------------------

_NEW_KEYS = [
    "scn_sig_filter_label", "scn_sig_hz_short", "scn_sig_hz_mid", "scn_sig_hz_long",
    "scn_sig_strength_triple", "scn_sig_strength_double", "scn_sig_strength_single",
    "scn_sig_strength_none", "scn_sig_triple_header", "scn_sig_priced_in",
    "scn_sig_details", "scn_sig_summary", "scn_sig_eps", "scn_sig_val",
    "scn_sig_narr_stage", "scn_sig_theme_tags",
]
for key in _NEW_KEYS:
    check(f"11.x ui_utils defines {key!r} in both EN and ZH",
          _UI_SRC.count(f'"{key}"') >= 2, detail=str(_UI_SRC.count(f'"{key}"')))


# ---------------------------------------------------------------------------
# Section 12 — No execution / no positive approved_for_execution in modified files
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
        check(f"12.1 {fname} has no positive auth: {form!r}", form not in src)

_FORBIDDEN_EXEC = [
    "broker_client", "broker_api", "order_router", "submit_order", "place_order",
    "execute_trade", "order_ticket", "execution_id", "quantity_to_execute",
    "time_in_force", "fill_price",
]
for fname, src in _MODIFIED.items():
    for tok in _FORBIDDEN_EXEC:
        check(f"12.2 {fname} has no exec token: {tok!r}", tok not in src)


# ---------------------------------------------------------------------------
# Section 13 — Theme-tag fallback + Chinese-localization plumbing
# ---------------------------------------------------------------------------

if _se is not None:
    import inspect

    # 13a — THEME_BASKETS reverse-lookup fallback. "MU" is an hbm_memory
    # constituent, so an empty-theme_tags candidate gets the basket label.
    fb = _se._theme_tags_for_ticker("MU", "en")
    check("13.1 _theme_tags_for_ticker finds a basket label for MU",
          isinstance(fb, list) and len(fb) >= 1, detail=str(fb))
    fb_zh = _se._theme_tags_for_ticker("MU", "zh")
    check("13.2 _theme_tags_for_ticker returns the zh label in zh mode",
          isinstance(fb_zh, list) and len(fb_zh) >= 1 and fb_zh != fb,
          detail=str(fb_zh))
    check("13.3 unknown ticker -> empty fallback",
          _se._theme_tags_for_ticker("ZZZZ", "en") == [])

    # build_candidate_signal applies the fallback when narrative.theme_tags empty.
    mu_cand = _se.build_candidate_signal(
        "MU", _se.FundamentalResult(), _se.neutral_narrative(),
        _se.EntryQualityResult(), _se.compute_track_b("MU", 0.0, 0.0, 0.0),
        {}, "risk_on", layer1_passed=True, lang="en",
    )
    check("13.4 empty theme_tags -> narrative_theme_tags filled from THEME_BASKETS",
          len(mu_cand.narrative_theme_tags) >= 1, detail=str(mu_cand.narrative_theme_tags))
    # A candidate WITH LLM theme_tags keeps them (no fallback override).
    check("13.5 non-empty LLM theme_tags preserved (no fallback override)",
          triple.narrative_theme_tags == ["AI"], detail=str(triple.narrative_theme_tags))

    # 13b — Chinese-localization plumbing. lang flows through the public API and
    # the en path is a pure pass-through (no network).
    check("13.6 build_candidate_signal accepts a lang parameter",
          "lang" in inspect.signature(_se.build_candidate_signal).parameters)
    check("13.7 score_ticker accepts a lang parameter",
          "lang" in inspect.signature(_se.score_ticker).parameters)
    check("13.8 _localize_texts en pass-through is identity (no translation)",
          tuple(_se._localize_texts(("Catalyst: x", "Entry: good"), "en"))
          == ("Catalyst: x", "Entry: good"))
    check("13.9 catalyst translation merged into score path (translator used)",
          "_translate_batch" in _SE_SRC and "_localize_texts" in _SE_SRC)
    # English candidates are NOT translated (key_signals stay English templates).
    check("13.10 en candidate key_signals stay English (offline)",
          any("Triple signal" in str(k) for k in triple.key_signals))

if _cg is not None:
    import inspect as _inspect2
    check("13.11 generate_candidates accepts a lang parameter",
          "lang" in _inspect2.signature(_cg.generate_candidates).parameters)
    check("13.12 _generate_candidates_cached cache key includes lang",
          "lang" in _inspect2.signature(_cg._generate_candidates_cached).parameters)
    check("13.13 Scanner passes lang to generate_candidates",
          "lang=_lang" in _SCANNER_SRC)


# ---------------------------------------------------------------------------
# Section 14 — LLM-coverage tuning + Layer 1 liquidity filter + FI fix
# ---------------------------------------------------------------------------

if _cg is not None:
    import inspect as _inspect3
    _params = _inspect3.signature(_cg.generate_candidates).parameters
    check("14.1 generate_candidates default llm_n is 50",
          _params["llm_n"].default == 50, detail=str(_params["llm_n"].default))
    check("14.2 generate_candidates clamps llm_n up to 100",
          "min(100" in _CG_SRC, detail="clamp ceiling")
    # Stale Fiserv ticker fixed: FI (404 in yfinance) -> FISV (resolves).
    check("14.3 SP500_TOP_100 no longer contains the broken 'FI' ticker",
          "FI" not in _cg.SP500_TOP_100, detail="FI present")
    check("14.4 SP500_TOP_100 uses the yfinance-resolvable 'FISV' ticker",
          "FISV" in _cg.SP500_TOP_100)

check("14.5 Scanner LLM-depth slider max is 100",
      "max_value=100" in _SCANNER_SRC)

if _se is not None:
    check("14.6 _MIN_DOLLAR_ADV liquidity floor is $10M",
          getattr(_se, "_MIN_DOLLAR_ADV", None) == 10_000_000.0)
    # Thin name: 100k shares * $5 = $0.5M ADV -> excluded on liquidity.
    okL, rL = _se.passes_layer1(
        "THIN", info={"marketCap": 5e9, "forwardPE": 12.0,
                      "averageVolume": 100_000, "currentPrice": 5.0})
    check("14.7 sub-$10M ADV fails Layer 1 on liquidity",
          okL is False and rL == "liquidity", detail=rL)
    # Liquid name: 5M shares * $50 = $250M ADV -> passes.
    okH, _rH = _se.passes_layer1(
        "LIQ", info={"marketCap": 5e9, "forwardPE": 12.0,
                     "averageVolume": 5_000_000, "currentPrice": 50.0})
    check("14.8 ample ADV passes Layer 1", okH is True)
    # Missing volume data -> liquidity check skipped (not excluded on it).
    okM, _rM = _se.passes_layer1(
        "NOVOL", info={"marketCap": 5e9, "forwardPE": 12.0})
    check("14.9 missing volume data does not exclude on liquidity", okM is True)
    # Liquidity must NOT consult RSI / momentum (still an early-opportunity-safe gate).
    okR, _rR = _se.passes_layer1(
        "OVERSOLD", info={"marketCap": 5e9, "forwardPE": 9.0,
                          "averageVolume": 8_000_000, "currentPrice": 40.0},
        ret_30d=-3.0)
    check("14.10 liquid oversold large-cap still passes Layer 1", okR is True)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
for line in _failures:
    print(line)
print()
print(f"Phase 6B v3 — Horizon-Native Signal Scoring: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
