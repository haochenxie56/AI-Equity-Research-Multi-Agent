"""
scripts/test_reliability_macro.py

Isolated test suite for Phase 2C: Macro Data + ToolResult Schema Foundation.

Tests cover:
  A. MacroDataCategory — all required categories accepted
  B. MacroIndicator — numeric value, string value, validation
  C. MacroSnapshot — partial indicators, empty snapshot_id rejection
  D. default_macro_staleness_rules — all categories present
  E. macro_snapshot_from_indicators — construction, no mutation
  F. macro_tool_result_from_snapshot — ToolResult shape, determinism
  G. extract_macro_indicator_paths — deterministic field paths
  H. summarize_macro_snapshot_coverage — present/missing categories
  I. validate_macro_snapshot — advisory warnings
  J. MacroRegimeSignal and MacroRegimeAssessment
  K. Serialization roundtrip
  L. No live app files imported; no network calls

Run:
    python3 scripts/test_reliability_macro.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import ValidationError

from lib.reliability.macro import (
    MacroDataCategory,
    MacroIndicator,
    MacroRegimeAssessment,
    MacroRegimeSignal,
    MacroSnapshot,
    default_macro_staleness_rules,
    extract_macro_indicator_paths,
    macro_snapshot_from_indicators,
    macro_tool_result_from_snapshot,
    summarize_macro_snapshot_coverage,
    validate_macro_snapshot,
)
from lib.reliability.schemas import AgentConfidence, EvidenceRef, ToolResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASS = "\033[32mPASS\033[0m"
_FAIL = "\033[31mFAIL\033[0m"

_passed = 0
_failed = 0


def _check(label: str, condition: bool) -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  {_PASS}  {label}")
    else:
        _failed += 1
        print(f"  {_FAIL}  {label}")


def _assert_raises(label: str, exc_type: type, fn, *args, **kwargs) -> None:
    global _passed, _failed
    try:
        fn(*args, **kwargs)
        _failed += 1
        print(f"  {_FAIL}  {label}  (expected {exc_type.__name__}, got no exception)")
    except exc_type:
        _passed += 1
        print(f"  {_PASS}  {label}")
    except Exception as e:
        _failed += 1
        print(f"  {_FAIL}  {label}  (expected {exc_type.__name__}, got {type(e).__name__}: {e})")


def _section(title: str) -> None:
    print(f"\n[{title}]")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ALL_CATEGORIES = [
    "rates", "yield_curve", "inflation", "growth", "liquidity",
    "credit_spread", "volatility", "market_breadth", "macro_regime",
]

_MAJOR_CATEGORIES = ["rates", "yield_curve", "inflation", "volatility", "market_breadth"]


def _make_indicator(
    name: str = "fed_funds_rate",
    category: str = "rates",
    value=5.25,
    as_of: str = "2026-05-01",
    source: str = "FRED",
) -> MacroIndicator:
    return MacroIndicator(
        name=name, category=category, value=value,
        as_of=as_of, source=source, unit="%",
    )


def _make_full_snapshot() -> MacroSnapshot:
    """A snapshot with all major categories covered."""
    return MacroSnapshot(
        snapshot_id="snap_test_001",
        as_of="2026-05-01",
        indicators=[
            MacroIndicator(name="fed_funds_rate", category="rates",
                           value=5.25, as_of="2026-05-01", source="FRED"),
            MacroIndicator(name="2y10y_spread", category="yield_curve",
                           value=-45, as_of="2026-05-01", source="Bloomberg",
                           unit="bps"),
            MacroIndicator(name="cpi_yoy", category="inflation",
                           value=3.2, as_of="2026-04-01", source="BLS",
                           frequency="monthly"),
            MacroIndicator(name="gdp_growth", category="growth",
                           value=2.1, as_of="2026-03-31", source="BEA",
                           frequency="quarterly"),
            MacroIndicator(name="fed_balance_sheet_trn", category="liquidity",
                           value=7.4, as_of="2026-04-28", source="FRB"),
            MacroIndicator(name="hy_spread_bps", category="credit_spread",
                           value=350, as_of="2026-05-01", source="ICE"),
            MacroIndicator(name="vix", category="volatility",
                           value=18.5, as_of="2026-05-01", source="CBOE"),
            MacroIndicator(name="nyse_advance_decline", category="market_breadth",
                           value="positive", as_of="2026-05-01", source="NYSE"),
            MacroIndicator(name="regime_signal", category="macro_regime",
                           value="risk_on", as_of="2026-05-01", source="internal"),
        ],
    )


def _make_evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="run123:macro_snapshot:macro:macro_snapshot:abc123",
        tool_name="macro_snapshot",
        excerpt="Macro rates data",
    )


# ---------------------------------------------------------------------------
# A. MacroDataCategory — all required categories accepted
# ---------------------------------------------------------------------------

_section("A")
print("MacroDataCategory — all required categories accepted")

for cat in _ALL_CATEGORIES:
    ind = MacroIndicator(name="test", category=cat, value=1.0,
                         as_of="2026-01-01", source="test_source")
    _check(f"A-{cat}: category='{cat}' accepted", ind.category == cat)

# ---------------------------------------------------------------------------
# B. MacroIndicator — numeric value, string value, validation
# ---------------------------------------------------------------------------

_section("B")
print("MacroIndicator — value types and validation")

# Numeric value (float)
_ind_float = MacroIndicator(name="fed_rate", category="rates",
                             value=5.25, as_of="2026-05-01", source="FRED")
_check("B1: accepts float value",         _ind_float.value == 5.25)

# Numeric value (int)
_ind_int = MacroIndicator(name="hy_spread", category="credit_spread",
                           value=350, as_of="2026-05-01", source="ICE")
_check("B2: accepts int value",           _ind_int.value == 350)

# String value
_ind_str = MacroIndicator(name="regime", category="macro_regime",
                           value="expanding", as_of="2026-05-01", source="internal")
_check("B3: accepts string value",        _ind_str.value == "expanding")

# All optional fields work
_ind_full = MacroIndicator(
    name="vix", category="volatility", value=18.5,
    as_of="2026-05-01", source="CBOE",
    unit="index", description="VIX spot level",
    frequency="daily", stale_after_days=2,
    metadata={"note": "close price"},
)
_check("B4: full MacroIndicator constructs successfully", isinstance(_ind_full, MacroIndicator))
_check("B5: unit stored",                _ind_full.unit == "index")
_check("B6: stale_after_days stored",    _ind_full.stale_after_days == 2)
_check("B7: metadata stored",            _ind_full.metadata == {"note": "close price"})

# Invalid category
_assert_raises("B8: invalid category raises ValidationError",
               ValidationError, MacroIndicator,
               name="x", category="bonds", value=5.0,
               as_of="2026-01-01", source="x")

# Empty name
_assert_raises("B9: empty name raises ValidationError",
               ValidationError, MacroIndicator,
               name="", category="rates", value=5.0,
               as_of="2026-01-01", source="FRED")

# Empty as_of
_assert_raises("B10: empty as_of raises ValidationError",
               ValidationError, MacroIndicator,
               name="fed_rate", category="rates", value=5.0,
               as_of="", source="FRED")

# Empty source
_assert_raises("B11: empty source raises ValidationError",
               ValidationError, MacroIndicator,
               name="fed_rate", category="rates", value=5.0,
               as_of="2026-05-01", source="")

# Extra fields forbidden
_assert_raises("B12: extra field raises ValidationError",
               ValidationError, MacroIndicator,
               name="fed_rate", category="rates", value=5.0,
               as_of="2026-05-01", source="FRED", unknown_field="x")

# ---------------------------------------------------------------------------
# C. MacroSnapshot — partial indicators, empty snapshot_id rejection
# ---------------------------------------------------------------------------

_section("C")
print("MacroSnapshot — partial indicators, validation")

# Partial — single indicator
_snap_partial = MacroSnapshot(
    snapshot_id="snap_001",
    as_of="2026-05-01",
    indicators=[_make_indicator()],
)
_check("C1: partial snapshot accepted",   isinstance(_snap_partial, MacroSnapshot))
_check("C2: one indicator stored",        len(_snap_partial.indicators) == 1)
_check("C3: schema_version defaults",     _snap_partial.schema_version == "1.0")
_check("C4: notes empty by default",      _snap_partial.notes == [])
_check("C5: warnings empty by default",   _snap_partial.warnings == [])

# With notes and warnings
_snap_notes = MacroSnapshot(
    snapshot_id="snap_002", as_of="2026-05-01",
    indicators=[_make_indicator()],
    notes=["Preliminary data"], warnings=["yield_curve data stale"],
)
_check("C6: notes stored",               _snap_notes.notes == ["Preliminary data"])
_check("C7: warnings stored",            _snap_notes.warnings == ["yield_curve data stale"])

# Empty snapshot_id rejected
_assert_raises("C8: empty snapshot_id raises ValidationError",
               ValidationError, MacroSnapshot,
               snapshot_id="", as_of="2026-05-01")

# Empty as_of rejected
_assert_raises("C9: empty as_of raises ValidationError",
               ValidationError, MacroSnapshot,
               snapshot_id="snap_x", as_of="")

# Extra fields forbidden
_assert_raises("C10: extra field raises ValidationError",
               ValidationError, MacroSnapshot,
               snapshot_id="x", as_of="2026-05-01", extra_key="y")

# ---------------------------------------------------------------------------
# D. default_macro_staleness_rules
# ---------------------------------------------------------------------------

_section("D")
print("default_macro_staleness_rules — all categories present")

_rules = default_macro_staleness_rules()
_check("D1: returns a dict",             isinstance(_rules, dict))
_check("D2: all 9 categories present",  set(_rules.keys()) == set(_ALL_CATEGORIES))

for cat in _ALL_CATEGORIES:
    _check(f"D3-{cat}: staleness rule for '{cat}' is positive int",
           isinstance(_rules[cat], int) and _rules[cat] > 0)

_check("D4: inflation staleness >= 30", _rules["inflation"] >= 30)
_check("D5: growth staleness >= 30",    _rules["growth"] >= 30)
_check("D6: rates staleness <= 7",      _rules["rates"] <= 7)
_check("D7: function is deterministic",
       default_macro_staleness_rules() == default_macro_staleness_rules())

# ---------------------------------------------------------------------------
# E. macro_snapshot_from_indicators
# ---------------------------------------------------------------------------

_section("E")
print("macro_snapshot_from_indicators — construction, no mutation")

_inds = [_make_indicator("fed_rate", "rates", 5.25, "2026-05-01", "FRED"),
         _make_indicator("vix", "volatility", 18.5, "2026-05-01", "CBOE")]
_orig_ids = [id(ind) for ind in _inds]
_orig_len = len(_inds)

_snap_built = macro_snapshot_from_indicators(
    "snap_built_001", "2026-05-01", _inds,
    notes=["Test note"],
    warnings=["Test warning"],
)

_check("E1: returns MacroSnapshot",          isinstance(_snap_built, MacroSnapshot))
_check("E2: snapshot_id correct",            _snap_built.snapshot_id == "snap_built_001")
_check("E3: as_of correct",                  _snap_built.as_of == "2026-05-01")
_check("E4: indicators count correct",       len(_snap_built.indicators) == 2)
_check("E5: notes stored",                   _snap_built.notes == ["Test note"])
_check("E6: warnings stored",                _snap_built.warnings == ["Test warning"])
_check("E7: input list not mutated",         len(_inds) == _orig_len)
_check("E8: same indicator objects in list", all(id(_snap_built.indicators[i]) == _orig_ids[i]
                                                  for i in range(len(_inds))))

# Default notes/warnings are empty
_snap_no_notes = macro_snapshot_from_indicators("snap_002", "2026-05-01", _inds)
_check("E9: notes default to empty list",     _snap_no_notes.notes == [])
_check("E10: warnings default to empty list", _snap_no_notes.warnings == [])

# ---------------------------------------------------------------------------
# F. macro_tool_result_from_snapshot
# ---------------------------------------------------------------------------

_section("F")
print("macro_tool_result_from_snapshot — ToolResult shape, determinism")

_run_id = "MACRO_20260521_120000_test01"
_snap_for_tr = _make_full_snapshot()
_tr = macro_tool_result_from_snapshot(_run_id, _snap_for_tr)

_check("F1: returns ToolResult",             isinstance(_tr, ToolResult))
_check("F2: tool_name is 'macro_snapshot'",  _tr.tool_name == "macro_snapshot")
_check("F3: run_id correct",                 _tr.run_id == _run_id)
_check("F4: evidence_id is non-empty",       len(_tr.evidence_id) > 0)
_check("F5: 'macro_snapshot' in evidence_id",
       "macro_snapshot" in _tr.evidence_id)
_check("F6: 'macro' in evidence_id (target segment)",
       ":macro:" in _tr.evidence_id)

# Outputs include snapshot fields
_check("F7: outputs include snapshot_id",    "snapshot_id" in _tr.outputs)
_check("F8: outputs include as_of",          "as_of" in _tr.outputs)
_check("F9: outputs include indicators",     "indicators" in _tr.outputs)
_check("F10: outputs snapshot_id correct",   _tr.outputs["snapshot_id"] == "snap_test_001")
_check("F11: outputs include calculation_version",
       "calculation_version" in _tr.outputs)
_check("F12: calculation_version default",
       _tr.outputs["calculation_version"] == "macro_schema_v1")

# Inputs
_check("F13: inputs include snapshot_id",    "snapshot_id" in _tr.inputs)
_check("F14: inputs include as_of",          "as_of" in _tr.inputs)

# Description
_check("F15: description is non-empty",      len(_tr.description) > 0)

# Determinism: same inputs → same evidence_id
_tr2 = macro_tool_result_from_snapshot(_run_id, _snap_for_tr)
_check("F16: evidence_id deterministic for same inputs",
       _tr.evidence_id == _tr2.evidence_id)

# Different snapshot → different evidence_id
_snap_different = macro_snapshot_from_indicators(
    "snap_different", "2026-06-01",
    [_make_indicator("cpi", "inflation", 3.0, "2026-06-01", "BLS")],
)
_tr_diff = macro_tool_result_from_snapshot(_run_id, _snap_different)
_check("F17: different snapshot → different evidence_id",
       _tr.evidence_id != _tr_diff.evidence_id)

# Custom target
_tr_custom = macro_tool_result_from_snapshot(_run_id, _snap_for_tr, target="us_macro")
_check("F18: custom target in evidence_id", ":us_macro:" in _tr_custom.evidence_id)

# ---------------------------------------------------------------------------
# G. extract_macro_indicator_paths
# ---------------------------------------------------------------------------

_section("G")
print("extract_macro_indicator_paths — deterministic field paths")

_paths = extract_macro_indicator_paths(_snap_for_tr)
_check("G1: returns a list",              isinstance(_paths, list))
_check("G2: non-empty for snapshot with indicators",
       len(_paths) > 0)

# Each indicator contributes 5 paths
_n_inds = len(_snap_for_tr.indicators)
_check("G3: correct total path count (5 per indicator)",
       len(_paths) == _n_inds * 5)

# Check specific paths for indicator 0
_check("G4: indicators.0.name present",     "indicators.0.name" in _paths)
_check("G5: indicators.0.category present", "indicators.0.category" in _paths)
_check("G6: indicators.0.value present",    "indicators.0.value" in _paths)
_check("G7: indicators.0.as_of present",    "indicators.0.as_of" in _paths)
_check("G8: indicators.0.source present",   "indicators.0.source" in _paths)

# Determinism
_paths2 = extract_macro_indicator_paths(_snap_for_tr)
_check("G9: function is deterministic",     _paths == _paths2)

# Empty snapshot → empty paths
_paths_empty = extract_macro_indicator_paths(
    MacroSnapshot(snapshot_id="x", as_of="2026-01-01")
)
_check("G10: empty snapshot → empty paths", _paths_empty == [])

# ---------------------------------------------------------------------------
# H. summarize_macro_snapshot_coverage
# ---------------------------------------------------------------------------

_section("H")
print("summarize_macro_snapshot_coverage — present/missing categories")

_summary_full = summarize_macro_snapshot_coverage(_snap_for_tr)

_check("H1: returns a dict",              isinstance(_summary_full, dict))
_check("H2: categories_present key",      "categories_present" in _summary_full)
_check("H3: categories_missing key",      "categories_missing" in _summary_full)
_check("H4: indicator_count key",         "indicator_count" in _summary_full)
_check("H5: stale_rule_categories_available key",
       "stale_rule_categories_available" in _summary_full)
_check("H6: warnings_count key",          "warnings_count" in _summary_full)

_check("H7: indicator_count correct",     _summary_full["indicator_count"] == 9)
_check("H8: all categories present",      len(_summary_full["categories_missing"]) == 0)
_check("H9: categories_present sorted",
       _summary_full["categories_present"] == sorted(_summary_full["categories_present"]))

# Partial snapshot
_snap_partial_h = macro_snapshot_from_indicators(
    "snap_h", "2026-05-01",
    [
        _make_indicator("cpi", "inflation", 3.2, "2026-04-01", "BLS"),
        _make_indicator("gdp", "growth", 2.1, "2026-03-31", "BEA"),
    ],
)
_summary_partial = summarize_macro_snapshot_coverage(_snap_partial_h)
_check("H10: inflation present",          "inflation" in _summary_partial["categories_present"])
_check("H11: growth present",             "growth" in _summary_partial["categories_present"])
_check("H12: rates missing",              "rates" in _summary_partial["categories_missing"])
_check("H13: indicator_count is 2",       _summary_partial["indicator_count"] == 2)
_check("H14: stale rules has 9 entries",
       len(_summary_partial["stale_rule_categories_available"]) == 9)

# ---------------------------------------------------------------------------
# I. validate_macro_snapshot
# ---------------------------------------------------------------------------

_section("I")
print("validate_macro_snapshot — advisory warnings")

# Warn on no indicators
_w_empty = validate_macro_snapshot(MacroSnapshot(snapshot_id="x", as_of="2026-01-01"))
_check("I1: warns on no indicators",
       any("no indicator" in w.lower() for w in _w_empty))

# Warn on duplicate name within same category
_snap_dup = MacroSnapshot(
    snapshot_id="snap_dup", as_of="2026-05-01",
    indicators=[
        MacroIndicator(name="fed_rate", category="rates", value=5.25,
                       as_of="2026-05-01", source="FRED"),
        MacroIndicator(name="fed_rate", category="rates", value=5.30,
                       as_of="2026-05-01", source="Bloomberg"),
        # Different category with same name: OK (not a dup)
        MacroIndicator(name="fed_rate", category="liquidity", value=5.25,
                       as_of="2026-05-01", source="FRED"),
    ] + [
        MacroIndicator(name=cat, category=cat, value=1.0,
                       as_of="2026-05-01", source="test")
        for cat in _MAJOR_CATEGORIES if cat != "rates"
    ],
)
_w_dup = validate_macro_snapshot(_snap_dup)
_check("I2: warns on duplicate name within same category",
       any("duplicate" in w.lower() for w in _w_dup))
_check("I3: same name in different category not flagged as dup",
       sum(1 for w in _w_dup if "duplicate" in w.lower()) == 1)

# Warn on missing major categories
_snap_missing = macro_snapshot_from_indicators(
    "snap_missing", "2026-05-01",
    [_make_indicator("gdp", "growth", 2.0, "2026-05-01", "BEA")],
)
_w_missing = validate_macro_snapshot(_snap_missing)
_check("I4: warns on missing major categories",
       any("rates" in w or "inflation" in w or "volatility" in w or
           "yield_curve" in w or "market_breadth" in w
           for w in _w_missing))
_check("I5: warns on multiple missing major categories",
       sum(1 for w in _w_missing
           if any(c in w for c in _MAJOR_CATEGORIES)) >= 4)

# Warn on stale_after_days <= 0
_snap_stale = macro_snapshot_from_indicators(
    "snap_stale", "2026-05-01",
    [
        MacroIndicator(name="fed_rate", category="rates", value=5.25,
                       as_of="2026-05-01", source="FRED", stale_after_days=0),
    ] + [
        MacroIndicator(name=cat, category=cat, value=1.0,
                       as_of="2026-05-01", source="test")
        for cat in _MAJOR_CATEGORIES if cat != "rates"
    ],
)
_w_stale = validate_macro_snapshot(_snap_stale)
_check("I6: warns on stale_after_days=0",
       any("stale_after_days" in w for w in _w_stale))

# Also test negative stale_after_days
_snap_neg_stale = macro_snapshot_from_indicators(
    "snap_neg_stale", "2026-05-01",
    [
        MacroIndicator(name="cpi", category="inflation", value=3.2,
                       as_of="2026-04-01", source="BLS", stale_after_days=-5),
    ] + [
        MacroIndicator(name=cat, category=cat, value=1.0,
                       as_of="2026-05-01", source="test")
        for cat in _MAJOR_CATEGORIES if cat != "inflation"
    ],
)
_w_neg_stale = validate_macro_snapshot(_snap_neg_stale)
_check("I7: warns on stale_after_days=-5",
       any("stale_after_days" in w for w in _w_neg_stale))

# Warn on blank string value
_snap_blank = macro_snapshot_from_indicators(
    "snap_blank", "2026-05-01",
    [
        MacroIndicator(name="regime", category="macro_regime", value="   ",
                       as_of="2026-05-01", source="internal"),
    ] + [
        MacroIndicator(name=cat, category=cat, value=1.0,
                       as_of="2026-05-01", source="test")
        for cat in _MAJOR_CATEGORIES
    ],
)
_w_blank = validate_macro_snapshot(_snap_blank)
_check("I8: warns on blank string value",
       any("empty or blank" in w.lower() or "blank" in w.lower()
           for w in _w_blank))

# Clean snapshot produces no warnings
_w_clean = validate_macro_snapshot(_snap_for_tr)
_check("I9: clean snapshot produces no warnings", len(_w_clean) == 0)
_check("I10: validate returns a list",
       isinstance(validate_macro_snapshot(MacroSnapshot(snapshot_id="x", as_of="2026-01-01")), list))

# ---------------------------------------------------------------------------
# J. MacroRegimeSignal and MacroRegimeAssessment
# ---------------------------------------------------------------------------

_section("J")
print("MacroRegimeSignal and MacroRegimeAssessment")

# Valid MacroRegimeSignal with all signal values
_valid_signals = [
    "risk_on", "risk_off", "neutral", "tightening", "easing",
    "expansion", "contraction", "high", "low", "mixed", "unknown",
]
for sig in _valid_signals:
    _rs = MacroRegimeSignal(
        regime_name="test_regime", category="rates", signal=sig, rationale="Test."
    )
    _check(f"J1-{sig}: signal='{sig}' accepted", _rs.signal == sig)

# Valid categories for MacroRegimeSignal
_valid_regime_cats = [
    "risk_on_risk_off", "rates", "liquidity", "growth",
    "inflation", "credit", "volatility", "breadth",
]
for rcat in _valid_regime_cats:
    _rs = MacroRegimeSignal(
        regime_name="test", category=rcat, signal="neutral", rationale="Test."
    )
    _check(f"J2-{rcat}: regime category='{rcat}' accepted", _rs.category == rcat)

# EvidenceRef and AgentConfidence accepted
_rs_full = MacroRegimeSignal(
    regime_name="rate_environment",
    category="rates",
    signal="tightening",
    rationale="Fed holding rates at 5.25-5.5%.",
    evidence_refs=[_make_evidence_ref()],
    confidence=AgentConfidence(level="high", rationale="Clear rate decision.", score=0.9),
)
_check("J3: full MacroRegimeSignal constructs successfully",
       isinstance(_rs_full, MacroRegimeSignal))
_check("J4: EvidenceRef accepted",     len(_rs_full.evidence_refs) == 1)
_check("J5: AgentConfidence accepted", _rs_full.confidence is not None)

# Invalid signal rejected
_assert_raises("J6: invalid signal 'bullish' raises ValidationError",
               ValidationError, MacroRegimeSignal,
               regime_name="test", category="rates",
               signal="bullish", rationale="x")
_assert_raises("J7: invalid signal 'hawkish' raises ValidationError",
               ValidationError, MacroRegimeSignal,
               regime_name="test", category="rates",
               signal="hawkish", rationale="x")

# Empty regime_name rejected
_assert_raises("J8: empty regime_name raises ValidationError",
               ValidationError, MacroRegimeSignal,
               regime_name="", category="rates", signal="neutral", rationale="x")

# MacroRegimeAssessment — partial signals
_mra = MacroRegimeAssessment(
    as_of="2026-05-01",
    signals=[_rs_full],
    summary="Rate environment: tightening.",
)
_check("J9: MacroRegimeAssessment constructs successfully",
       isinstance(_mra, MacroRegimeAssessment))
_check("J10: target defaults to 'macro'",  _mra.target == "macro")
_check("J11: schema_version is '1.0'",     _mra.schema_version == "1.0")
_check("J12: signal stored correctly",      len(_mra.signals) == 1)
_check("J13: summary stored",              _mra.summary == "Rate environment: tightening.")

# Empty assessment (partial — no signals)
_mra_empty = MacroRegimeAssessment(as_of="2026-05-01")
_check("J14: empty signals list accepted", len(_mra_empty.signals) == 0)

# Empty as_of rejected
_assert_raises("J15: empty as_of raises ValidationError",
               ValidationError, MacroRegimeAssessment, as_of="")

# Empty target rejected
_assert_raises("J16: empty target raises ValidationError",
               ValidationError, MacroRegimeAssessment, as_of="2026-01-01", target="")

# ---------------------------------------------------------------------------
# K. Serialization roundtrip
# ---------------------------------------------------------------------------

_section("K")
print("Serialization roundtrip — model_dump / model_validate / JSON")

# MacroIndicator roundtrip
_ind_rt = MacroIndicator(
    name="fed_funds_rate", category="rates", value=5.25,
    as_of="2026-05-01", source="FRED", unit="%",
    stale_after_days=2, metadata={"series_id": "DFF"},
)
_ind_dump = _ind_rt.model_dump()
_ind_restored = MacroIndicator.model_validate(_ind_dump)
_check("K1: MacroIndicator roundtrip via model_dump/validate",
       _ind_restored.name == "fed_funds_rate")
_check("K2: value preserved after roundtrip", _ind_restored.value == 5.25)
_check("K3: metadata preserved",             _ind_restored.metadata == {"series_id": "DFF"})

# MacroSnapshot roundtrip
_snap_rt = _make_full_snapshot()
_snap_dump = _snap_rt.model_dump()
_snap_restored = MacroSnapshot.model_validate(_snap_dump)
_check("K4: MacroSnapshot roundtrip via model_dump/validate",
       isinstance(_snap_restored, MacroSnapshot))
_check("K5: indicator count preserved",  len(_snap_restored.indicators) == 9)

_snap_json = _snap_rt.model_dump_json()
_check("K6: model_dump_json returns str",  isinstance(_snap_json, str))
_check("K7: JSON is parseable",           isinstance(json.loads(_snap_json), dict))
_snap_from_json = MacroSnapshot.model_validate_json(_snap_json)
_check("K8: model_validate_json restores correctly",
       _snap_from_json.snapshot_id == "snap_test_001")

# MacroRegimeAssessment roundtrip
_mra_rt = MacroRegimeAssessment(
    as_of="2026-05-01",
    signals=[_rs_full],
    summary="Tightening cycle ongoing.",
    warnings=["Preliminary data"],
)
_mra_dump = _mra_rt.model_dump()
_mra_restored = MacroRegimeAssessment.model_validate(_mra_dump)
_check("K9: MacroRegimeAssessment roundtrip",
       _mra_restored.summary == "Tightening cycle ongoing.")
_check("K10: signals count preserved",   len(_mra_restored.signals) == 1)
_check("K11: schema_version preserved",  _mra_restored.schema_version == "1.0")

# ToolResult from snapshot roundtrip
_tr_rt = macro_tool_result_from_snapshot("run_rt", _snap_rt)
_tr_dump = _tr_rt.model_dump()
_tr_restored = ToolResult.model_validate(_tr_dump)
_check("K12: ToolResult roundtrip",      _tr_restored.tool_name == "macro_snapshot")
_check("K13: evidence_id preserved",     _tr_restored.evidence_id == _tr_rt.evidence_id)

# ---------------------------------------------------------------------------
# L. No live app files imported; no network calls
# ---------------------------------------------------------------------------

_section("L")
print("No live app files imported or modified; no network calls")

_imported_modules = set(sys.modules.keys())
_forbidden = [
    "app",
    "pages",
    "lib.llm_orchestrator",
    "lib.valuation",
    "lib.technical",
    "lib.rotation",
    "lib.data_fetcher",
    "lib.workflow_state",
    "streamlit",
    "requests",
    "urllib.request",
    "httpx",
    "aiohttp",
]
for mod in _forbidden:
    _check(f"L-{mod}: '{mod}' not imported",
           not any(m == mod or m.startswith(mod + ".") for m in _imported_modules))

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

print()
print("=" * 62)
if _failed == 0:
    print(f"\033[32mResults: {_passed} passed, {_failed} failed\033[0m")
else:
    print(f"\033[31mResults: {_passed} passed, {_failed} failed\033[0m")
print("=" * 62)

if _failed > 0:
    sys.exit(1)
