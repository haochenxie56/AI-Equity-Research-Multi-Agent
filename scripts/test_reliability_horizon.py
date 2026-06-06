"""
scripts/test_reliability_horizon.py

Isolated test suite for Phase 2B: Investment Horizon Schema Foundation.

Tests cover:
  A. Default evidence requirements — three horizons, correct categories
  B. HorizonThesis — EvidenceRef integration, validation
  C. HorizonRisk — EvidenceRef, severity literals
  D. HorizonRecommendation — action literals, validation
  E. HorizonTradePlan — instrument literals, validation
  F. HorizonDecisionSet — partial data, empty target rejection
  G. group_horizon_decisions_by_horizon — grouping correctness
  H. summarize_horizon_coverage — present/missing horizons, counts
  I. validate_horizon_decision_set — advisory warnings
  J. Serialization roundtrip
  K. No live app files imported

Run:
    python3 scripts/test_reliability_horizon.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import ValidationError

from lib.reliability.horizon import (
    HorizonDecisionSet,
    HorizonEvidenceRequirement,
    HorizonRecommendation,
    HorizonRisk,
    HorizonThesis,
    HorizonTradePlan,
    default_horizon_evidence_requirements,
    group_horizon_decisions_by_horizon,
    summarize_horizon_coverage,
    validate_horizon_decision_set,
)
from lib.reliability.schemas import AgentConfidence, EvidenceRef

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

def _make_evidence_ref(eid: str = "run123:tool_a:AAPL:dcf:abc123") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=eid,
        tool_name="valuation_model",
        metric="fair_value",
        excerpt="Fair value estimate $180",
    )


def _make_confidence() -> AgentConfidence:
    return AgentConfidence(level="medium", rationale="Moderate conviction", score=0.6)


# ---------------------------------------------------------------------------
# A. Default evidence requirements
# ---------------------------------------------------------------------------

_section("A")
print("Default evidence requirements — three horizons, correct categories")

_reqs = default_horizon_evidence_requirements()
_horizons_in_reqs = {r.horizon for r in _reqs}

_check("A1: returns exactly 3 requirements",             len(_reqs) == 3)
_check("A2: short_term present",                         "short_term" in _horizons_in_reqs)
_check("A3: medium_term present",                        "medium_term" in _horizons_in_reqs)
_check("A4: long_term present",                          "long_term" in _horizons_in_reqs)

_st_req = next(r for r in _reqs if r.horizon == "short_term")
_mt_req = next(r for r in _reqs if r.horizon == "medium_term")
_lt_req = next(r for r in _reqs if r.horizon == "long_term")

_check("A5: short-term categories include 'technical' or 'price_volume'",
       "technical" in _st_req.required_evidence_categories
       or "price_volume" in _st_req.required_evidence_categories)
_check("A6: short-term categories include 'event'",
       "event" in _st_req.required_evidence_categories)

_mt_all = _mt_req.required_evidence_categories + _mt_req.preferred_evidence_categories
_check("A7: medium-term includes at least one of catalyst/earnings/estimate_revision/valuation/sector_rotation",
       any(c in _mt_all for c in
           ["catalyst", "earnings", "estimate_revision", "valuation", "sector_rotation"]))
_check("A8: medium-term required includes valuation",    "valuation" in _mt_req.required_evidence_categories)

_lt_all = _lt_req.required_evidence_categories + _lt_req.preferred_evidence_categories
_check("A9: long-term includes business_quality",        "business_quality" in _lt_req.required_evidence_categories)
_check("A10: long-term includes financials",             "financials" in _lt_req.required_evidence_categories)
_check("A11: long-term includes moat",                   "moat" in _lt_req.required_evidence_categories)
_check("A12: long-term includes management",             "management" in _lt_req.required_evidence_categories)
_check("A13: long-term includes capital_allocation",     "capital_allocation" in _lt_req.required_evidence_categories)

_check("A14: function is deterministic",
       default_horizon_evidence_requirements() == default_horizon_evidence_requirements())

# ---------------------------------------------------------------------------
# B. HorizonThesis — EvidenceRef integration and validation
# ---------------------------------------------------------------------------

_section("B")
print("HorizonThesis — EvidenceRef, AgentConfidence, validation")

_thesis_st = HorizonThesis(
    horizon="short_term",
    thesis="Price is coiling below resistance; breakout setup forming.",
    supporting_points=["RSI reset to 45", "Volume dry-up on pullback"],
    evidence_refs=[_make_evidence_ref()],
    confidence=_make_confidence(),
    invalidation_conditions=["Close below 20-day MA"],
)
_check("B1: HorizonThesis constructs successfully",      isinstance(_thesis_st, HorizonThesis))
_check("B2: horizon echoed correctly",                   _thesis_st.horizon == "short_term")
_check("B3: EvidenceRef accepted",                       len(_thesis_st.evidence_refs) == 1)
_check("B4: AgentConfidence accepted",                   _thesis_st.confidence is not None)
_check("B5: supporting_points stored",                   len(_thesis_st.supporting_points) == 2)
_check("B6: invalidation_conditions stored",             len(_thesis_st.invalidation_conditions) == 1)

# Minimal thesis — all optional fields omitted
_thesis_min = HorizonThesis(horizon="long_term", thesis="Strong economic moat.")
_check("B7: minimal HorizonThesis (only required fields)", isinstance(_thesis_min, HorizonThesis))
_check("B8: empty evidence_refs by default",             _thesis_min.evidence_refs == [])
_check("B9: confidence None by default",                 _thesis_min.confidence is None)

# Empty thesis string rejected
_assert_raises("B10: empty thesis raises ValidationError",
               ValidationError, HorizonThesis, horizon="short_term", thesis="")

# Empty supporting point rejected
_assert_raises("B11: blank supporting point raises ValidationError",
               ValidationError, HorizonThesis,
               horizon="short_term", thesis="Valid thesis.", supporting_points=["   "])

# Invalid horizon rejected
_assert_raises("B12: invalid horizon raises ValidationError",
               ValidationError, HorizonThesis, horizon="ultra_long", thesis="x")

# ---------------------------------------------------------------------------
# C. HorizonRisk — EvidenceRef and severity literals
# ---------------------------------------------------------------------------

_section("C")
print("HorizonRisk — EvidenceRef, severity literals")

_risk = HorizonRisk(
    horizon="medium_term",
    risk_type="earnings_miss",
    description="Company may miss consensus EPS due to supply chain issues.",
    severity="high",
    evidence_refs=[_make_evidence_ref("run1:tool:AAPL:earnings:xyz")],
    invalidation_trigger="Q3 supply chain update confirms resolution",
)
_check("C1: HorizonRisk constructs successfully",        isinstance(_risk, HorizonRisk))
_check("C2: severity 'high' accepted",                   _risk.severity == "high")
_check("C3: EvidenceRef accepted",                       len(_risk.evidence_refs) == 1)
_check("C4: invalidation_trigger stored",                _risk.invalidation_trigger is not None)

for sev in ("low", "medium", "high", "critical"):
    _risk_sev = HorizonRisk(
        horizon="short_term", risk_type="test", description="test risk", severity=sev
    )
    _check(f"C5-{sev}: severity='{sev}' accepted",       _risk_sev.severity == sev)

_assert_raises("C6: empty risk_type raises ValidationError",
               ValidationError, HorizonRisk,
               horizon="short_term", risk_type="", description="x", severity="low")
_assert_raises("C7: empty description raises ValidationError",
               ValidationError, HorizonRisk,
               horizon="short_term", risk_type="macro", description="", severity="low")
_assert_raises("C8: invalid severity raises ValidationError",
               ValidationError, HorizonRisk,
               horizon="short_term", risk_type="x", description="x", severity="extreme")

# ---------------------------------------------------------------------------
# D. HorizonRecommendation — action literals, validation
# ---------------------------------------------------------------------------

_section("D")
print("HorizonRecommendation — action literals")

_valid_actions = [
    "buy", "hold", "trim", "exit", "avoid",
    "wait", "add_on_pullback", "add_on_breakout", "no_action",
]
for action in _valid_actions:
    _rec = HorizonRecommendation(
        horizon="short_term", action=action, rationale="Test rationale."
    )
    _check(f"D1-{action}: action='{action}' accepted",   _rec.action == action)

_assert_raises("D2: invalid action 'strong_buy' raises ValidationError",
               ValidationError, HorizonRecommendation,
               horizon="short_term", action="strong_buy", rationale="x")
_assert_raises("D3: invalid action 'sell' raises ValidationError",
               ValidationError, HorizonRecommendation,
               horizon="short_term", action="sell", rationale="x")
_assert_raises("D4: empty rationale raises ValidationError",
               ValidationError, HorizonRecommendation,
               horizon="short_term", action="buy", rationale="")

_rec_full = HorizonRecommendation(
    horizon="long_term",
    action="buy",
    rationale="Durable moat with attractive valuation.",
    confidence=_make_confidence(),
    evidence_refs=[_make_evidence_ref()],
    entry_condition="Pullback to $165",
    invalidation_trigger="Moat evidence weakens materially",
    review_trigger="Quarterly earnings miss two consecutive quarters",
)
_check("D5: full HorizonRecommendation constructs correctly", isinstance(_rec_full, HorizonRecommendation))
_check("D6: entry_condition stored",                     _rec_full.entry_condition is not None)
_check("D7: invalidation_trigger stored",                _rec_full.invalidation_trigger is not None)

# ---------------------------------------------------------------------------
# E. HorizonTradePlan — instrument literals, validation
# ---------------------------------------------------------------------------

_section("E")
print("HorizonTradePlan — instrument literals")

_valid_instruments = ["stock", "option", "cash", "watchlist", "no_trade", "undetermined"]
for inst in _valid_instruments:
    _plan = HorizonTradePlan(horizon="short_term", preferred_instrument=inst)
    _check(f"E1-{inst}: instrument='{inst}' accepted",   _plan.preferred_instrument == inst)

_assert_raises("E2: invalid instrument 'futures' raises ValidationError",
               ValidationError, HorizonTradePlan,
               horizon="short_term", preferred_instrument="futures")
_assert_raises("E3: invalid instrument 'etf' raises ValidationError",
               ValidationError, HorizonTradePlan,
               horizon="short_term", preferred_instrument="etf")

_plan_default = HorizonTradePlan(horizon="medium_term")
_check("E4: default preferred_instrument is 'undetermined'",
       _plan_default.preferred_instrument == "undetermined")

_plan_full = HorizonTradePlan(
    horizon="medium_term",
    preferred_instrument="stock",
    entry_zone="$160–$165",
    add_zone="$155",
    trim_zone="$185",
    stop_loss="Daily close below $150",
    target_zone="$200–$210",
    max_risk_note="Risk 2% of portfolio",
    time_stop="Re-evaluate after Q4 earnings",
    review_trigger="Price breaks $170 on volume",
    evidence_refs=[_make_evidence_ref()],
)
_check("E5: full HorizonTradePlan constructs correctly", isinstance(_plan_full, HorizonTradePlan))
_check("E6: evidence_refs stored",                       len(_plan_full.evidence_refs) == 1)

# ---------------------------------------------------------------------------
# F. HorizonDecisionSet — partial data, empty target rejection
# ---------------------------------------------------------------------------

_section("F")
print("HorizonDecisionSet — partial horizons accepted, empty target rejected")

# Partial: only short_term thesis
_ds_partial = HorizonDecisionSet(
    target="AAPL",
    theses=[HorizonThesis(horizon="short_term", thesis="Short-term setup.")],
)
_check("F1: partial decision set (one horizon) accepted",  isinstance(_ds_partial, HorizonDecisionSet))
_check("F2: only one thesis stored",                       len(_ds_partial.theses) == 1)
_check("F3: recommendations empty by default",             _ds_partial.recommendations == [])
_check("F4: trade_plans empty by default",                 _ds_partial.trade_plans == [])

# Empty — completely empty set is valid (no required horizons)
_ds_empty = HorizonDecisionSet(target="MSFT")
_check("F5: all-empty HorizonDecisionSet accepted",        isinstance(_ds_empty, HorizonDecisionSet))
_check("F6: schema_version defaults to '1.0'",             _ds_empty.schema_version == "1.0")

# All three horizons
_ds_full = HorizonDecisionSet(
    target="NVDA",
    theses=[
        HorizonThesis(horizon="short_term", thesis="Breakout setup."),
        HorizonThesis(horizon="medium_term", thesis="AI catalyst."),
        HorizonThesis(horizon="long_term", thesis="Dominant compute platform."),
    ],
    risks=[
        HorizonRisk(horizon="short_term", risk_type="overbought",
                    description="RSI > 80", severity="medium"),
    ],
    recommendations=[
        HorizonRecommendation(horizon="long_term", action="buy",
                              rationale="Strong long-term compounding."),
    ],
)
_check("F7: full three-horizon DecisionSet accepted",      isinstance(_ds_full, HorizonDecisionSet))
_check("F8: three theses stored",                          len(_ds_full.theses) == 3)
_check("F9: one risk stored",                              len(_ds_full.risks) == 1)

# Empty target rejected
_assert_raises("F10: empty target raises ValidationError",
               ValidationError, HorizonDecisionSet, target="")

# extra fields forbidden
_assert_raises("F11: extra field raises ValidationError",
               ValidationError, HorizonDecisionSet, target="X", unknown_field="y")

# ---------------------------------------------------------------------------
# G. group_horizon_decisions_by_horizon
# ---------------------------------------------------------------------------

_section("G")
print("group_horizon_decisions_by_horizon — grouping correctness")

_ds_group = HorizonDecisionSet(
    target="TSLA",
    theses=[
        HorizonThesis(horizon="short_term", thesis="Momentum thesis."),
        HorizonThesis(horizon="long_term", thesis="EV platform thesis."),
        HorizonThesis(horizon="long_term", thesis="Energy storage thesis."),
    ],
    risks=[
        HorizonRisk(horizon="medium_term", risk_type="margin", description="Margin risk.", severity="high"),
    ],
    recommendations=[
        HorizonRecommendation(horizon="short_term", action="wait", rationale="Waiting for setup."),
    ],
    trade_plans=[
        HorizonTradePlan(horizon="long_term", preferred_instrument="stock", entry_zone="$200"),
    ],
)

_grouped = group_horizon_decisions_by_horizon(_ds_group)

_check("G1: returns dict with three horizon keys",
       set(_grouped.keys()) == {"short_term", "medium_term", "long_term"})
_check("G2: each value has required sub-keys",
       all(
           all(k in _grouped[h] for k in
               ["theses", "risks", "recommendations", "trade_plans", "evidence_requirements"])
           for h in ["short_term", "medium_term", "long_term"]
       ))
_check("G3: short_term has 1 thesis",                    len(_grouped["short_term"]["theses"]) == 1)
_check("G4: long_term has 2 theses",                     len(_grouped["long_term"]["theses"]) == 2)
_check("G5: medium_term has 1 risk",                     len(_grouped["medium_term"]["risks"]) == 1)
_check("G6: short_term has 1 recommendation",            len(_grouped["short_term"]["recommendations"]) == 1)
_check("G7: long_term has 1 trade_plan",                 len(_grouped["long_term"]["trade_plans"]) == 1)
_check("G8: medium_term has 0 recommendations",          len(_grouped["medium_term"]["recommendations"]) == 0)
_check("G9: horizons with no data have empty lists",
       all(len(_grouped["medium_term"][k]) == 0
           for k in ["theses", "recommendations", "trade_plans"]))

# ---------------------------------------------------------------------------
# H. summarize_horizon_coverage
# ---------------------------------------------------------------------------

_section("H")
print("summarize_horizon_coverage — present/missing horizons, counts")

_summary = summarize_horizon_coverage(_ds_group)

_check("H1: target is correct",                          _summary["target"] == "TSLA")
_check("H2: short_term is present",                      "short_term" in _summary["present_horizons"])
_check("H3: medium_term is present (has risk)",          "medium_term" in _summary["present_horizons"])
_check("H4: long_term is present",                       "long_term" in _summary["present_horizons"])
_check("H5: no missing horizons for this set",           len(_summary["missing_horizons"]) == 0)
_check("H6: total_theses is 3",                          _summary["total_theses"] == 3)
_check("H7: total_risks is 1",                           _summary["total_risks"] == 1)
_check("H8: total_recommendations is 1",                 _summary["total_recommendations"] == 1)
_check("H9: total_trade_plans is 1",                     _summary["total_trade_plans"] == 1)

# Set with missing horizons
_summary_partial = summarize_horizon_coverage(HorizonDecisionSet(
    target="XYZ",
    theses=[HorizonThesis(horizon="short_term", thesis="Only short term.")],
))
_check("H10: only short_term present",
       _summary_partial["present_horizons"] == ["short_term"])
_check("H11: medium_term and long_term are missing",
       set(_summary_partial["missing_horizons"]) == {"medium_term", "long_term"})
_check("H12: counts show 1 thesis for short_term",
       _summary_partial["counts"]["short_term"]["theses"] == 1)
_check("H13: counts show 0 theses for long_term",
       _summary_partial["counts"]["long_term"]["theses"] == 0)

# ---------------------------------------------------------------------------
# I. validate_horizon_decision_set — advisory warnings
# ---------------------------------------------------------------------------

_section("I")
print("validate_horizon_decision_set — advisory warnings")

# Clean: no recommendations or theses → two warnings
_warnings_empty = validate_horizon_decision_set(HorizonDecisionSet(target="XYZ"))
_check("I1: warns on missing recommendations",
       any("no recommendations" in w.lower() for w in _warnings_empty))
_check("I2: warns on missing theses",
       any("no theses" in w.lower() for w in _warnings_empty))

# Recommendation without evidence_refs
_ds_no_evidence = HorizonDecisionSet(
    target="ABC",
    theses=[HorizonThesis(horizon="short_term", thesis="Some thesis.",
                          evidence_refs=[_make_evidence_ref()])],
    recommendations=[
        HorizonRecommendation(horizon="short_term", action="hold", rationale="Cautious.")
    ],
)
_warnings_no_ev = validate_horizon_decision_set(_ds_no_evidence)
_check("I3: warns on recommendation with no evidence_refs",
       any("evidence_refs" in w or "evidence" in w.lower() for w in _warnings_no_ev))

# Thesis without evidence_refs
_ds_thesis_no_ev = HorizonDecisionSet(
    target="DEF",
    theses=[HorizonThesis(horizon="medium_term", thesis="Catalyst thesis.")],
    recommendations=[
        HorizonRecommendation(horizon="medium_term", action="hold",
                              rationale="Hold.", evidence_refs=[_make_evidence_ref()])
    ],
)
_warnings_thesis_ev = validate_horizon_decision_set(_ds_thesis_no_ev)
_check("I4: warns on thesis with no evidence_refs",
       any("thesis" in w.lower() and "evidence" in w.lower()
           for w in _warnings_thesis_ev))

# Active buy action without invalidation or review trigger
_ds_buy_no_trigger = HorizonDecisionSet(
    target="GHI",
    theses=[HorizonThesis(horizon="long_term", thesis="Great business.",
                          evidence_refs=[_make_evidence_ref()])],
    recommendations=[
        HorizonRecommendation(
            horizon="long_term", action="buy",
            rationale="Strong thesis.",
            evidence_refs=[_make_evidence_ref()],
            # No invalidation_trigger, no review_trigger
        )
    ],
)
_warnings_buy = validate_horizon_decision_set(_ds_buy_no_trigger)
_check("I5: warns on buy action without invalidation_trigger or review_trigger",
       any("invalidation" in w.lower() or "review_trigger" in w.lower()
           for w in _warnings_buy))

# add_on_pullback also triggers the warning
_ds_add = HorizonDecisionSet(
    target="JKL",
    theses=[HorizonThesis(horizon="short_term", thesis="Setup.",
                          evidence_refs=[_make_evidence_ref()])],
    recommendations=[
        HorizonRecommendation(horizon="short_term", action="add_on_pullback",
                              rationale="Add on weakness.",
                              evidence_refs=[_make_evidence_ref()])
    ],
)
_warnings_add = validate_horizon_decision_set(_ds_add)
_check("I6: warns on add_on_pullback without trigger",
       any("invalidation" in w.lower() or "review" in w.lower()
           for w in _warnings_add))

# Option trade plan without evidence refs
_ds_option = HorizonDecisionSet(
    target="MNO",
    theses=[HorizonThesis(horizon="short_term", thesis="Breakout.",
                          evidence_refs=[_make_evidence_ref()])],
    recommendations=[
        HorizonRecommendation(horizon="short_term", action="buy",
                              rationale="Play the breakout.",
                              evidence_refs=[_make_evidence_ref()],
                              invalidation_trigger="Fails to hold breakout level")
    ],
    trade_plans=[
        HorizonTradePlan(horizon="short_term", preferred_instrument="option")
        # no evidence_refs
    ],
)
_warnings_option = validate_horizon_decision_set(_ds_option)
_check("I7: warns on option plan without evidence_refs",
       any("option" in w.lower() for w in _warnings_option))

# Duplicate recommendation for same horizon
_ds_dup = HorizonDecisionSet(
    target="PQR",
    theses=[HorizonThesis(horizon="short_term", thesis="Setup.",
                          evidence_refs=[_make_evidence_ref()])],
    recommendations=[
        HorizonRecommendation(horizon="short_term", action="hold",
                              rationale="First.", evidence_refs=[_make_evidence_ref()]),
        HorizonRecommendation(horizon="short_term", action="wait",
                              rationale="Second.", evidence_refs=[_make_evidence_ref()]),
    ],
)
_warnings_dup = validate_horizon_decision_set(_ds_dup)
_check("I8: warns on duplicate recommendations for same horizon",
       any("duplicate" in w.lower() for w in _warnings_dup))

# Clean set — no warnings
_ds_clean = HorizonDecisionSet(
    target="CLEAN",
    theses=[
        HorizonThesis(horizon="long_term", thesis="Excellent business.",
                      evidence_refs=[_make_evidence_ref()])
    ],
    recommendations=[
        HorizonRecommendation(
            horizon="long_term", action="buy",
            rationale="Strong long-term compounder.",
            evidence_refs=[_make_evidence_ref()],
            invalidation_trigger="Moat evidence materially weakens.",
        )
    ],
)
_warnings_clean = validate_horizon_decision_set(_ds_clean)
_check("I9: clean decision set produces no warnings",    len(_warnings_clean) == 0)
_check("I10: validate returns a list",
       isinstance(validate_horizon_decision_set(HorizonDecisionSet(target="X")), list))

# ---------------------------------------------------------------------------
# J. Serialization roundtrip
# ---------------------------------------------------------------------------

_section("J")
print("Serialization roundtrip — model_dump / model_validate")

_ds_rt = HorizonDecisionSet(
    target="AAPL",
    theses=[
        HorizonThesis(
            horizon="short_term",
            thesis="Coiling below resistance.",
            evidence_refs=[_make_evidence_ref()],
            confidence=_make_confidence(),
        ),
        HorizonThesis(horizon="long_term", thesis="Dominant ecosystem."),
    ],
    risks=[
        HorizonRisk(horizon="medium_term", risk_type="guide_down",
                    description="Management may guide down.", severity="medium"),
    ],
    recommendations=[
        HorizonRecommendation(
            horizon="short_term", action="wait",
            rationale="Wait for breakout confirmation.",
            review_trigger="Daily close above $185 on volume",
        ),
        HorizonRecommendation(
            horizon="long_term", action="buy",
            rationale="Accumulate at value.",
            evidence_refs=[_make_evidence_ref()],
            invalidation_trigger="Moat evidence degrades.",
        ),
    ],
    trade_plans=[
        HorizonTradePlan(horizon="short_term", preferred_instrument="stock",
                         entry_zone="$185 breakout", stop_loss="$178"),
    ],
    evidence_requirements=default_horizon_evidence_requirements(),
)

_dumped = _ds_rt.model_dump()
_check("J1: model_dump returns a dict",                  isinstance(_dumped, dict))
_check("J2: target preserved in dump",                   _dumped["target"] == "AAPL")
_check("J3: theses present in dump",                     len(_dumped["theses"]) == 2)
_check("J4: evidence_requirements in dump",              len(_dumped["evidence_requirements"]) == 3)

_restored = HorizonDecisionSet.model_validate(_dumped)
_check("J5: model_validate restores from dump",          isinstance(_restored, HorizonDecisionSet))
_check("J6: target matches after roundtrip",             _restored.target == "AAPL")
_check("J7: theses count matches after roundtrip",       len(_restored.theses) == 2)
_check("J8: risks count matches after roundtrip",        len(_restored.risks) == 1)
_check("J9: recommendations count matches",              len(_restored.recommendations) == 2)

# JSON serialization
_json_str = _ds_rt.model_dump_json()
_check("J10: model_dump_json returns a string",          isinstance(_json_str, str))
_check("J11: JSON is parseable",                         isinstance(json.loads(_json_str), dict))

_restored_from_json = HorizonDecisionSet.model_validate_json(_json_str)
_check("J12: model_validate_json restores correctly",
       _restored_from_json.target == "AAPL")
_check("J13: schema_version preserved in roundtrip",
       _restored_from_json.schema_version == "1.0")

# ---------------------------------------------------------------------------
# K. No live app files imported
# ---------------------------------------------------------------------------

_section("K")
print("No live app files imported or modified")

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
]
for mod in _forbidden:
    _check(f"K-{mod}: '{mod}' not imported",
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
