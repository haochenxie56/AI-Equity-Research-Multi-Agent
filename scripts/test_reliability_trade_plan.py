"""
scripts/test_reliability_trade_plan.py

Phase 3R-B: Trade Plan Drafting Agent Skeleton — test suite.

Tests cover:
  - TradePlanPriceZone construction and validation.
  - TradePlanRiskControl construction and validation.
  - TradePlanReviewTrigger construction and validation.
  - TradePlanDraft construction and validation.
  - TradePlanInputBundle construction and validation.
  - TradePlanSummary / TradePlanReport execution guard (approved_for_execution).
  - determine_trade_plan_status:
      no plans → unknown,
      all-unknown action → draft,
      watch/hold → complete,
      no_trade with reason → complete,
      active action with adequate evidence → complete,
      active action without evidence → needs_review,
      high-risk without evidence → needs_review,
      high-risk with adequate evidence → complete,
      human_review_report.status=="blocked" → blocked,
      blocked takes precedence over needs_review.
  - collect_trade_plan_source_ids: collection, deduplication, order, no mutation.
  - summarize_trade_plans: counts, horizons, top_warnings, action_counts.
  - build_trade_plan_report: full pipeline, determinism, warnings, status,
      no mutation of inputs.
  - missing optional prior artifacts create warnings without crashing.
  - generated warnings appear in summary.top_warnings.
  - ToolResult adapter: stable tool_name, deterministic evidence_id, payload.
  - __all__ exports include Phase 3R-B public symbols.
  - No dependency on Streamlit, live LLM, broker/order modules, or network.

Usage:
    python3 scripts/test_reliability_trade_plan.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pydantic

from lib.reliability.trade_plan import (
    _CALCULATION_VERSION,
    _TRADE_PLAN_TOOL_NAME,
    TradePlanDraft,
    TradePlanEvidenceQuality,
    TradePlanInputBundle,
    TradePlanPriceZone,
    TradePlanReport,
    TradePlanRiskControl,
    TradePlanReviewTrigger,
    TradePlanSummary,
    build_trade_plan_report,
    collect_trade_plan_source_ids,
    determine_trade_plan_status,
    make_trade_plan_report_id,
    summarize_trade_plans,
    trade_plan_tool_result_from_report,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0
_failed_tests: list[str] = []


def ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {label}")


def fail(label: str, reason: str) -> None:
    global FAIL
    FAIL += 1
    _failed_tests.append(f"{label}: {reason}")
    print(f"  FAIL  {label} — {reason}")


def check(label: str, condition: bool, reason: str = "") -> None:
    if condition:
        ok(label)
    else:
        fail(label, reason or "condition is False")


# ---------------------------------------------------------------------------
# Shared constants and mock builders
# ---------------------------------------------------------------------------

_AS_OF = "2026-05-24T12:00:00+00:00"
_RUN_ID = "test_run_phase3rb"
_TICKER = "AAPL"


def _make_zone(
    zone_id: str = "zone-1",
    label: str = "Entry Zone",
    trigger_type: str = "price_level",
    lower_bound: float | None = None,
    upper_bound: float | None = None,
    reference_price: float | None = None,
    source_ids: list[str] | None = None,
    warnings: list[str] | None = None,
) -> TradePlanPriceZone:
    return TradePlanPriceZone(
        zone_id=zone_id,
        label=label,
        trigger_type=trigger_type,  # type: ignore[arg-type]
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        reference_price=reference_price,
        source_ids=source_ids or [],
        warnings=warnings or [],
    )


def _make_risk_control(
    rc_id: str = "rc-1",
    stop_reference: float | None = None,
    max_loss_reference: float | None = None,
    risk_level: str = "medium",
    review_required: bool = False,
    source_ids: list[str] | None = None,
) -> TradePlanRiskControl:
    return TradePlanRiskControl(
        risk_control_id=rc_id,
        stop_reference=stop_reference,
        max_loss_reference=max_loss_reference,
        risk_level=risk_level,  # type: ignore[arg-type]
        review_required=review_required,
        source_ids=source_ids or [],
    )


def _make_review_trigger(
    trigger_id: str = "rt-1",
    trigger_type: str = "review_date",
    affected_horizon: str = "medium",
    source_ids: list[str] | None = None,
) -> TradePlanReviewTrigger:
    return TradePlanReviewTrigger(
        trigger_id=trigger_id,
        trigger_type=trigger_type,  # type: ignore[arg-type]
        description="Check on earnings date",
        affected_horizon=affected_horizon,  # type: ignore[arg-type]
        review_required=True,
        source_ids=source_ids or [],
    )


def _make_plan(
    plan_id: str = "plan-1",
    ticker: str = _TICKER,
    action_type: str = "watch",
    horizon: str = "medium",
    evidence_quality: str = "adequate",
    source_ids: list[str] | None = None,
    warnings: list[str] | None = None,
    risk_controls: list[TradePlanRiskControl] | None = None,
    review_triggers: list[TradePlanReviewTrigger] | None = None,
) -> TradePlanDraft:
    return TradePlanDraft(
        plan_id=plan_id,
        ticker=ticker,
        action_type=action_type,  # type: ignore[arg-type]
        horizon=horizon,  # type: ignore[arg-type]
        evidence_quality=evidence_quality,  # type: ignore[arg-type]
        source_ids=source_ids or [],
        warnings=warnings or [],
        risk_controls=risk_controls or [],
        review_triggers=review_triggers or [],
    )


def _make_no_trade(
    plan_id: str = "plan-nt",
    ticker: str = _TICKER,
    reason: str = "Valuation too rich at current levels",
) -> TradePlanDraft:
    return TradePlanDraft(
        plan_id=plan_id,
        ticker=ticker,
        action_type="no_trade",
        no_trade_reason=reason,
    )


def _make_bundle(
    target: str = _TICKER,
    as_of: str = _AS_OF,
    source_ids: list[str] | None = None,
    warnings: list[str] | None = None,
    human_review_report=None,
    decision_packet=None,
    horizon_synthesis=None,
) -> TradePlanInputBundle:
    return TradePlanInputBundle(
        target=target,
        as_of=as_of,
        source_ids=source_ids or [],
        warnings=warnings or [],
        human_review_report=human_review_report,
        decision_packet=decision_packet,
        horizon_synthesis=horizon_synthesis,
    )


class _MockHRBlocked:
    status = "blocked"


class _MockHRComplete:
    status = "complete"


class _MockDecisionPacket:
    status = "complete"


class _MockHorizonSynthesis:
    status = "complete"


# ---------------------------------------------------------------------------
# T01–T12: TradePlanPriceZone
# ---------------------------------------------------------------------------

def test_price_zone() -> None:
    print("\n--- TradePlanPriceZone ---")

    # T01: basic construction
    z = _make_zone()
    check("T01: TradePlanPriceZone basic construction", z.zone_id == "zone-1")
    check("T01b: label preserved", z.label == "Entry Zone")
    check("T01c: trigger_type", z.trigger_type == "price_level")

    # T02: bounds accepted
    z2 = _make_zone(lower_bound=100.0, upper_bound=110.0)
    check("T02: lower_bound accepted", z2.lower_bound == 100.0)
    check("T02b: upper_bound accepted", z2.upper_bound == 110.0)

    # T03: equal bounds accepted
    z3 = _make_zone(lower_bound=100.0, upper_bound=100.0)
    check("T03: equal bounds accepted", z3.lower_bound == z3.upper_bound)

    # T04: lower > upper rejected
    try:
        _make_zone(lower_bound=120.0, upper_bound=110.0)
        fail("T04: lower > upper rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T04: lower > upper rejected")

    # T05: negative lower rejected
    try:
        _make_zone(lower_bound=-1.0)
        fail("T05: negative lower rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T05: negative lower rejected")

    # T06: negative upper rejected
    try:
        _make_zone(upper_bound=-5.0)
        fail("T06: negative upper rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T06: negative upper rejected")

    # T07: negative reference_price rejected
    try:
        _make_zone(reference_price=-5.0)
        fail("T07: negative reference_price rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T07: negative reference_price rejected")

    # T08: whitespace zone_id rejected
    try:
        TradePlanPriceZone(zone_id="   ", label="Valid Label")
        fail("T08: whitespace zone_id rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T08: whitespace zone_id rejected")

    # T09: whitespace label rejected
    try:
        TradePlanPriceZone(zone_id="valid", label="  ")
        fail("T09: whitespace label rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T09: whitespace label rejected")

    # T10: source_ids and warnings preserved
    z4 = _make_zone(source_ids=["ev-001"], warnings=["check data"])
    check("T10: source_ids preserved", "ev-001" in z4.source_ids)
    check("T10b: warnings preserved", "check data" in z4.warnings)

    # T11: zero bounds accepted
    z5 = _make_zone(lower_bound=0.0, upper_bound=0.0)
    check("T11: zero bounds accepted", z5.lower_bound == 0.0)

    # T12: reference_price with no bounds
    z6 = _make_zone(reference_price=150.0)
    check("T12: reference_price standalone", z6.reference_price == 150.0)


# ---------------------------------------------------------------------------
# T20–T27: TradePlanRiskControl
# ---------------------------------------------------------------------------

def test_risk_control() -> None:
    print("\n--- TradePlanRiskControl ---")

    # T20: basic construction
    rc = _make_risk_control()
    check("T20: TradePlanRiskControl basic construction", rc.risk_control_id == "rc-1")
    check("T20b: risk_level default", rc.risk_level == "medium")
    check("T20c: review_required default", rc.review_required is False)

    # T21: high risk with stop reference
    rc2 = _make_risk_control(rc_id="rc-2", stop_reference=95.0, risk_level="high")
    check("T21: stop_reference accepted", rc2.stop_reference == 95.0)
    check("T21b: risk_level=high accepted", rc2.risk_level == "high")

    # T22: negative stop rejected
    try:
        _make_risk_control(stop_reference=-10.0)
        fail("T22: negative stop_reference rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T22: negative stop_reference rejected")

    # T23: negative max_loss rejected
    try:
        _make_risk_control(max_loss_reference=-100.0)
        fail("T23: negative max_loss_reference rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T23: negative max_loss_reference rejected")

    # T24: zero stop accepted
    rc3 = _make_risk_control(stop_reference=0.0)
    check("T24: zero stop_reference accepted", rc3.stop_reference == 0.0)

    # T25: whitespace id rejected
    try:
        TradePlanRiskControl(risk_control_id="  ")
        fail("T25: whitespace risk_control_id rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T25: whitespace risk_control_id rejected")

    # T26: review_required flag
    rc4 = _make_risk_control(review_required=True, risk_level="high")
    check("T26: review_required=True accepted", rc4.review_required is True)

    # T27: source_ids preserved
    rc5 = _make_risk_control(source_ids=["ev-rc-1"])
    check("T27: risk_control source_ids preserved", "ev-rc-1" in rc5.source_ids)


# ---------------------------------------------------------------------------
# T30–T35: TradePlanReviewTrigger
# ---------------------------------------------------------------------------

def test_review_trigger() -> None:
    print("\n--- TradePlanReviewTrigger ---")

    # T30: basic construction
    rt = _make_review_trigger()
    check("T30: TradePlanReviewTrigger basic construction", rt.trigger_id == "rt-1")
    check("T30b: review_required default True", rt.review_required is True)

    # T31: price_level trigger type
    rt2 = _make_review_trigger(trigger_type="price_level")
    check("T31: trigger_type=price_level", rt2.trigger_type == "price_level")

    # T32: earnings trigger with short horizon
    rt3 = _make_review_trigger(trigger_type="earnings", affected_horizon="short")
    check("T32: trigger_type=earnings", rt3.trigger_type == "earnings")
    check("T32b: affected_horizon=short", rt3.affected_horizon == "short")

    # T33: whitespace trigger_id rejected
    try:
        TradePlanReviewTrigger(trigger_id="   ")
        fail("T33: whitespace trigger_id rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T33: whitespace trigger_id rejected")

    # T34: source_ids preserved
    rt4 = _make_review_trigger(source_ids=["ev-rt-1"])
    check("T34: review_trigger source_ids preserved", "ev-rt-1" in rt4.source_ids)

    # T35: thesis_invalidation trigger type
    rt5 = _make_review_trigger(trigger_type="thesis_invalidation")
    check("T35: trigger_type=thesis_invalidation", rt5.trigger_type == "thesis_invalidation")


# ---------------------------------------------------------------------------
# T40–T55: TradePlanDraft
# ---------------------------------------------------------------------------

def test_trade_plan_draft() -> None:
    print("\n--- TradePlanDraft ---")

    # T40: basic watch plan
    p = _make_plan()
    check("T40: TradePlanDraft basic construction", p.plan_id == "plan-1")
    check("T40b: action_type=watch", p.action_type == "watch")
    check("T40c: approved_for_execution=False", p.approved_for_execution is False)

    # T41: hold plan
    p2 = _make_plan(action_type="hold")
    check("T41: action_type=hold accepted", p2.action_type == "hold")

    # T42: enter plan with evidence
    p3 = _make_plan(action_type="enter", evidence_quality="adequate")
    check("T42: action_type=enter with adequate evidence", p3.evidence_quality == "adequate")

    # T43: valid no_trade plan
    p4 = _make_no_trade()
    check("T43: action_type=no_trade with reason", p4.action_type == "no_trade")
    check("T43b: no_trade_reason preserved", "Valuation too rich" in p4.no_trade_reason)

    # T44: no_trade without reason rejected
    try:
        TradePlanDraft(plan_id="p1", ticker=_TICKER, action_type="no_trade")
        fail("T44: no_trade without reason rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T44: no_trade without reason rejected")

    # T45: no_trade with empty reason rejected
    try:
        TradePlanDraft(
            plan_id="p1", ticker=_TICKER, action_type="no_trade", no_trade_reason=""
        )
        fail("T45: no_trade with empty reason rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T45: no_trade with empty reason rejected")

    # T46: no_trade with whitespace reason rejected
    try:
        TradePlanDraft(
            plan_id="p1", ticker=_TICKER, action_type="no_trade", no_trade_reason="   "
        )
        fail("T46: no_trade with whitespace-only reason rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T46: no_trade with whitespace-only reason rejected")

    # T47: approved_for_execution=True rejected
    try:
        TradePlanDraft(
            plan_id="p1", ticker=_TICKER, action_type="watch", approved_for_execution=True
        )
        fail("T47: approved_for_execution=True rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T47: approved_for_execution=True rejected")

    # T48: whitespace ticker rejected
    try:
        TradePlanDraft(plan_id="p1", ticker="  ", action_type="watch")
        fail("T48: whitespace ticker rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T48: whitespace ticker rejected")

    # T49: whitespace plan_id rejected
    try:
        TradePlanDraft(plan_id="  ", ticker=_TICKER, action_type="watch")
        fail("T49: whitespace plan_id rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T49: whitespace plan_id rejected")

    # T50: plan with zones and controls
    entry_zone = _make_zone("ez-1", "Entry", lower_bound=100.0, upper_bound=105.0)
    rc = _make_risk_control("rc-1", stop_reference=95.0, risk_level="medium")
    rt = _make_review_trigger("rt-1", trigger_type="earnings")
    p5 = TradePlanDraft(
        plan_id="p-complex",
        ticker=_TICKER,
        action_type="enter",
        evidence_quality="adequate",
        entry_zones=[entry_zone],
        risk_controls=[rc],
        review_triggers=[rt],
        source_ids=["ev-001"],
    )
    check("T50: plan with zones accepted", len(p5.entry_zones) == 1)
    check("T50b: plan with risk_controls", len(p5.risk_controls) == 1)
    check("T50c: plan with review_triggers", len(p5.review_triggers) == 1)
    check("T50d: entry_zone lower_bound", p5.entry_zones[0].lower_bound == 100.0)

    # T51: all zone lists populated
    p6 = TradePlanDraft(
        plan_id="p-multi",
        ticker=_TICKER,
        action_type="enter",
        evidence_quality="strong",
        entry_zones=[_make_zone("ez-1", "Entry")],
        add_zones=[_make_zone("az-1", "Add")],
        trim_zones=[_make_zone("tz-1", "Trim")],
        target_zones=[_make_zone("tgt-1", "Target")],
    )
    check("T51: add_zones populated", len(p6.add_zones) == 1)
    check("T51b: trim_zones populated", len(p6.trim_zones) == 1)
    check("T51c: target_zones populated", len(p6.target_zones) == 1)

    # T52: unknown action_type accepted
    p7 = TradePlanDraft(plan_id="p-unk", ticker=_TICKER, action_type="unknown")
    check("T52: action_type=unknown accepted", p7.action_type == "unknown")
    check("T52b: approved_for_execution still False", p7.approved_for_execution is False)


# ---------------------------------------------------------------------------
# T60–T65: TradePlanInputBundle
# ---------------------------------------------------------------------------

def test_input_bundle() -> None:
    print("\n--- TradePlanInputBundle ---")

    # T60: minimal bundle
    b = _make_bundle()
    check("T60: TradePlanInputBundle basic construction", b.target == _TICKER)
    check("T60b: as_of preserved", b.as_of == _AS_OF)
    check("T60c: decision_packet defaults None", b.decision_packet is None)
    check("T60d: human_review_report defaults None", b.human_review_report is None)

    # T61: source_ids preserved
    b2 = _make_bundle(source_ids=["ev-001", "ev-002"])
    check("T61: source_ids preserved", len(b2.source_ids) == 2)

    # T62: warnings preserved
    b3 = _make_bundle(warnings=["stale data"])
    check("T62: warnings preserved", "stale data" in b3.warnings)

    # T63: whitespace target rejected
    try:
        TradePlanInputBundle(target="  ", as_of=_AS_OF)
        fail("T63: whitespace target rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T63: whitespace target rejected")

    # T64: accepts duck-typed HR report
    b4 = _make_bundle(human_review_report=_MockHRBlocked())
    check("T64: bundle accepts duck-typed HR report", b4.human_review_report is not None)
    check("T64b: HR status readable", b4.human_review_report.status == "blocked")

    # T65: accepts mock decision_packet and horizon_synthesis
    b5 = _make_bundle(decision_packet=_MockDecisionPacket(), horizon_synthesis=_MockHorizonSynthesis())
    check("T65: decision_packet accepted", b5.decision_packet is not None)
    check("T65b: horizon_synthesis accepted", b5.horizon_synthesis is not None)


# ---------------------------------------------------------------------------
# T70–T74: Execution guard (TradePlanSummary / TradePlanReport)
# ---------------------------------------------------------------------------

def test_execution_guard() -> None:
    print("\n--- Execution guard (approved_for_execution) ---")

    # T70: TradePlanSummary defaults False
    s = TradePlanSummary(target=_TICKER, status="unknown")
    check("T70: TradePlanSummary approved_for_execution defaults False",
          s.approved_for_execution is False)

    # T71: TradePlanSummary rejects True
    try:
        TradePlanSummary(target=_TICKER, status="unknown", approved_for_execution=True)
        fail("T71: TradePlanSummary rejects approved_for_execution=True", "should have raised")
    except pydantic.ValidationError:
        ok("T71: TradePlanSummary rejects approved_for_execution=True")

    # T72: TradePlanSummary whitespace target rejected
    try:
        TradePlanSummary(target="  ", status="unknown")
        fail("T72: TradePlanSummary whitespace target rejected", "should have raised")
    except pydantic.ValidationError:
        ok("T72: TradePlanSummary whitespace target rejected")

    # T73: TradePlanReport rejects approved_for_execution=True
    bundle = _make_bundle()
    summary = TradePlanSummary(target=_TICKER, status="unknown")
    try:
        TradePlanReport(
            report_id="r1",
            target=_TICKER,
            run_id=_RUN_ID,
            status="unknown",
            input_bundle=bundle,
            plans=[],
            summary=summary,
            created_at=_AS_OF,
            approved_for_execution=True,
        )
        fail("T73: TradePlanReport rejects approved_for_execution=True", "should have raised")
    except pydantic.ValidationError:
        ok("T73: TradePlanReport rejects approved_for_execution=True")

    # T74: TradePlanDraft defaults False and rejects True
    p = _make_plan()
    check("T74: TradePlanDraft approved_for_execution defaults False",
          p.approved_for_execution is False)


# ---------------------------------------------------------------------------
# T80–T96: determine_trade_plan_status
# ---------------------------------------------------------------------------

def test_status_determination() -> None:
    print("\n--- determine_trade_plan_status ---")

    # T80: no plans → unknown
    check("T80: no plans → unknown",
          determine_trade_plan_status([]) == "unknown")

    # T81: watch plan → complete
    p_watch = _make_plan(action_type="watch")
    check("T81: watch plan → complete",
          determine_trade_plan_status([p_watch]) == "complete")

    # T82: hold plan → complete
    p_hold = _make_plan(plan_id="p-hold", action_type="hold")
    check("T82: hold plan → complete",
          determine_trade_plan_status([p_hold]) == "complete")

    # T83: no_trade with reason → complete
    p_nt = _make_no_trade()
    check("T83: no_trade with reason → complete",
          determine_trade_plan_status([p_nt]) == "complete")

    # T84: enter with adequate evidence → complete
    p_enter_ok = _make_plan(plan_id="p-enter-ok", action_type="enter", evidence_quality="adequate")
    check("T84: enter + adequate → complete",
          determine_trade_plan_status([p_enter_ok]) == "complete")

    # T85: add with strong evidence → complete
    p_add_ok = TradePlanDraft(
        plan_id="p-add", ticker=_TICKER, action_type="add", evidence_quality="strong"
    )
    check("T85: add + strong → complete",
          determine_trade_plan_status([p_add_ok]) == "complete")

    # T86: enter without evidence → needs_review
    p_enter_bad = TradePlanDraft(
        plan_id="p-enter-bad", ticker=_TICKER, action_type="enter", evidence_quality="unsupported"
    )
    check("T86: enter + unsupported → needs_review",
          determine_trade_plan_status([p_enter_bad]) == "needs_review")

    # T87: trim with weak evidence → needs_review
    p_trim_weak = TradePlanDraft(
        plan_id="p-trim-weak", ticker=_TICKER, action_type="trim", evidence_quality="weak"
    )
    check("T87: trim + weak → needs_review",
          determine_trade_plan_status([p_trim_weak]) == "needs_review")

    # T88: exit with unknown evidence → needs_review
    p_exit_unk = TradePlanDraft(
        plan_id="p-exit-unk", ticker=_TICKER, action_type="exit", evidence_quality="unknown"
    )
    check("T88: exit + unknown evidence → needs_review",
          determine_trade_plan_status([p_exit_unk]) == "needs_review")

    # T89: high-risk control without adequate evidence → needs_review
    rc_high = _make_risk_control(rc_id="rc-high", risk_level="high")
    p_high_risk = TradePlanDraft(
        plan_id="p-high-risk", ticker=_TICKER, action_type="watch",
        evidence_quality="weak", risk_controls=[rc_high]
    )
    check("T89: high risk + weak evidence → needs_review",
          determine_trade_plan_status([p_high_risk]) == "needs_review")

    # T90: high-risk control with adequate evidence → complete
    rc_high2 = _make_risk_control(rc_id="rc-high2", risk_level="high")
    p_high_ok = TradePlanDraft(
        plan_id="p-high-ok", ticker=_TICKER, action_type="watch",
        evidence_quality="adequate", risk_controls=[rc_high2]
    )
    check("T90: high risk + adequate evidence → complete",
          determine_trade_plan_status([p_high_ok]) == "complete")

    # T91: human_review_report.status=="blocked" → blocked
    p_watch2 = _make_plan(plan_id="p-watch2")
    check("T91: HR blocked → blocked",
          determine_trade_plan_status([p_watch2], _MockHRBlocked()) == "blocked")

    # T92: human_review_report.status=="complete" → does not block
    check("T92: HR complete → not blocked",
          determine_trade_plan_status([p_watch2], _MockHRComplete()) != "blocked")

    # T93: human_review_report=None → no block
    check("T93: HR None → not blocked",
          determine_trade_plan_status([p_watch2], None) != "blocked")

    # T94: all unknown action_type → draft
    p_unk = TradePlanDraft(plan_id="p-unk", ticker=_TICKER, action_type="unknown")
    check("T94: all-unknown action → draft",
          determine_trade_plan_status([p_unk]) == "draft")

    # T95: blocked takes precedence over needs_review
    p_no_ev = TradePlanDraft(
        plan_id="p-no-ev", ticker=_TICKER, action_type="enter", evidence_quality="unsupported"
    )
    check("T95: blocked > needs_review precedence",
          determine_trade_plan_status([p_no_ev], _MockHRBlocked()) == "blocked")

    # T96: mix of watch + no_trade → complete
    p_mix1 = _make_plan(plan_id="p-mix1", action_type="watch")
    p_mix2 = _make_no_trade(plan_id="p-mix2")
    check("T96: watch + no_trade mix → complete",
          determine_trade_plan_status([p_mix1, p_mix2]) == "complete")


# ---------------------------------------------------------------------------
# T100–T109: collect_trade_plan_source_ids
# ---------------------------------------------------------------------------

def test_source_id_collection() -> None:
    print("\n--- collect_trade_plan_source_ids ---")

    # T100: empty bundle and no plans → empty
    b = _make_bundle()
    result = collect_trade_plan_source_ids(b, [])
    check("T100: empty bundle + no plans → []", result == [])

    # T101: bundle source_ids included
    b2 = _make_bundle(source_ids=["ev-001", "ev-002"])
    result2 = collect_trade_plan_source_ids(b2, [])
    check("T101: bundle source_ids in result", "ev-001" in result2 and "ev-002" in result2)

    # T102: plan source_ids included
    b3 = _make_bundle()
    p = _make_plan(source_ids=["ev-plan-1"])
    result3 = collect_trade_plan_source_ids(b3, [p])
    check("T102: plan source_ids in result", "ev-plan-1" in result3)

    # T103: zone source_ids included
    z = _make_zone(source_ids=["ev-zone-1"])
    p2 = TradePlanDraft(
        plan_id="p-zone", ticker=_TICKER, action_type="watch", entry_zones=[z]
    )
    result4 = collect_trade_plan_source_ids(_make_bundle(), [p2])
    check("T103: zone source_ids in result", "ev-zone-1" in result4)

    # T104: risk_control source_ids included
    rc = _make_risk_control(source_ids=["ev-rc-1"])
    p3 = TradePlanDraft(
        plan_id="p-rc", ticker=_TICKER, action_type="watch", risk_controls=[rc]
    )
    result5 = collect_trade_plan_source_ids(_make_bundle(), [p3])
    check("T104: risk_control source_ids in result", "ev-rc-1" in result5)

    # T105: review_trigger source_ids included
    rt = _make_review_trigger(source_ids=["ev-rt-1"])
    p4 = TradePlanDraft(
        plan_id="p-rt", ticker=_TICKER, action_type="watch", review_triggers=[rt]
    )
    result6 = collect_trade_plan_source_ids(_make_bundle(), [p4])
    check("T105: review_trigger source_ids in result", "ev-rt-1" in result6)

    # T106: deduplication preserves first-occurrence order
    b4 = _make_bundle(source_ids=["ev-001", "ev-002"])
    p5 = _make_plan(source_ids=["ev-002", "ev-003"])
    result7 = collect_trade_plan_source_ids(b4, [p5])
    check("T106: ev-002 deduplicated", result7.count("ev-002") == 1)
    check("T106b: first-occurrence order preserved",
          result7.index("ev-002") < result7.index("ev-003"))

    # T107: does not mutate bundle
    b5 = _make_bundle(source_ids=["ev-001"])
    original_ids = list(b5.source_ids)
    collect_trade_plan_source_ids(b5, [])
    check("T107: bundle not mutated", b5.source_ids == original_ids)

    # T108: does not mutate plan
    b6 = _make_bundle()
    p6 = _make_plan(source_ids=["ev-plan-1"])
    original_plan_ids = list(p6.source_ids)
    collect_trade_plan_source_ids(b6, [p6])
    check("T108: plan not mutated", p6.source_ids == original_plan_ids)

    # T109: add_zones, trim_zones, target_zones also collected
    az = _make_zone("az", "Add", source_ids=["ev-add"])
    tz = _make_zone("tz", "Trim", source_ids=["ev-trim"])
    tgtz = _make_zone("tgtz", "Target", source_ids=["ev-target"])
    p7 = TradePlanDraft(
        plan_id="p-allzones", ticker=_TICKER, action_type="watch",
        add_zones=[az], trim_zones=[tz], target_zones=[tgtz],
    )
    result8 = collect_trade_plan_source_ids(_make_bundle(), [p7])
    check("T109: add_zone source_ids collected", "ev-add" in result8)
    check("T109b: trim_zone source_ids collected", "ev-trim" in result8)
    check("T109c: target_zone source_ids collected", "ev-target" in result8)


# ---------------------------------------------------------------------------
# T110–T135: build_trade_plan_report
# ---------------------------------------------------------------------------

def test_report_builder() -> None:
    print("\n--- build_trade_plan_report ---")

    # T110: empty plans → status unknown
    b = _make_bundle()
    r = build_trade_plan_report(b, [], _RUN_ID)
    check("T110: empty plans → status=unknown", r.status == "unknown")
    check("T110b: approved_for_execution=False", r.approved_for_execution is False)
    check("T110c: target preserved", r.target == _TICKER)

    # T111: watch plan → complete
    p_watch = _make_plan()
    r2 = build_trade_plan_report(_make_bundle(), [p_watch], _RUN_ID)
    check("T111: watch plan → status=complete", r2.status == "complete")
    check("T111b: summary.plan_count=1", r2.summary.plan_count == 1)

    # T112: no_trade plan → complete
    p_nt = _make_no_trade()
    r3 = build_trade_plan_report(_make_bundle(), [p_nt], _RUN_ID)
    check("T112: no_trade plan → complete", r3.status == "complete")
    check("T112b: summary.no_trade_count=1", r3.summary.no_trade_count == 1)

    # T113: enter without evidence → needs_review
    p_bad = TradePlanDraft(
        plan_id="p-bad", ticker=_TICKER, action_type="enter", evidence_quality="unsupported"
    )
    r4 = build_trade_plan_report(_make_bundle(), [p_bad], _RUN_ID)
    check("T113: enter without evidence → needs_review", r4.status == "needs_review")

    # T114: deterministic report_id
    b5 = _make_bundle()
    r5a = build_trade_plan_report(b5, [], _RUN_ID)
    r5b = build_trade_plan_report(b5, [], _RUN_ID)
    check("T114: report_id deterministic", r5a.report_id == r5b.report_id)

    # T115: report_id starts with tpr_
    check("T115: report_id prefix tpr_", r5a.report_id.startswith("tpr_"))

    # T116: explicit created_at override
    override = "2026-01-01T00:00:00+00:00"
    r6 = build_trade_plan_report(_make_bundle(), [], _RUN_ID, created_at=override)
    check("T116: explicit created_at honored", r6.created_at == override)

    # T117: default created_at == as_of
    r7 = build_trade_plan_report(_make_bundle(), [], _RUN_ID)
    check("T117: default created_at == as_of", r7.created_at == _AS_OF)

    # T118: missing decision_packet creates warning
    r8 = build_trade_plan_report(_make_bundle(), [], _RUN_ID)
    check("T118: missing decision_packet → warning in report.warnings",
          any("decision_packet" in w for w in r8.warnings))

    # T119: missing horizon_synthesis creates warning
    check("T119: missing horizon_synthesis → warning in report.warnings",
          any("horizon_synthesis" in w for w in r8.warnings))

    # T120: missing optional artifacts do not crash
    b_minimal = _make_bundle()
    r9 = build_trade_plan_report(b_minimal, [], _RUN_ID)
    check("T120: missing optional artifacts do not crash", r9 is not None)

    # T121: HR blocked → report blocked
    b_blocked = _make_bundle(human_review_report=_MockHRBlocked())
    p_ok = _make_plan()
    r10 = build_trade_plan_report(b_blocked, [p_ok], _RUN_ID)
    check("T121: HR blocked → report status=blocked", r10.status == "blocked")

    # T122: generated warning appears in top_warnings
    p_no_ev = TradePlanDraft(
        plan_id="p-no-ev", ticker=_TICKER, action_type="enter", evidence_quality="unsupported"
    )
    r11 = build_trade_plan_report(_make_bundle(), [p_no_ev], _RUN_ID)
    check("T122: generated warning in report.warnings",
          any("p-no-ev" in w for w in r11.warnings))
    check("T122b: generated warning in top_warnings",
          len(r11.summary.top_warnings) > 0)

    # T123: inputs not mutated (bundle)
    b6 = _make_bundle(source_ids=["ev-001"])
    p6 = _make_plan(source_ids=["ev-002"])
    orig_bundle_ids = list(b6.source_ids)
    orig_plan_ids = list(p6.source_ids)
    build_trade_plan_report(b6, [p6], _RUN_ID)
    check("T123: bundle not mutated", b6.source_ids == orig_bundle_ids)
    check("T123b: plan not mutated", p6.source_ids == orig_plan_ids)

    # T124: action_counts in summary
    p_w = _make_plan(plan_id="p-w", action_type="watch")
    p_nt2 = _make_no_trade(plan_id="p-nt2")
    r12 = build_trade_plan_report(_make_bundle(), [p_w, p_nt2], _RUN_ID)
    check("T124: action_counts[watch]==1", r12.summary.action_counts.get("watch", 0) == 1)
    check("T124b: action_counts[no_trade]==1", r12.summary.action_counts.get("no_trade", 0) == 1)

    # T125: review_trigger_count
    rt = _make_review_trigger()
    p_rt = TradePlanDraft(
        plan_id="p-rt", ticker=_TICKER, action_type="watch", review_triggers=[rt]
    )
    r13 = build_trade_plan_report(_make_bundle(), [p_rt], _RUN_ID)
    check("T125: summary.review_trigger_count==1", r13.summary.review_trigger_count == 1)

    # T126: high_risk_count
    rc_h = _make_risk_control(rc_id="rc-h", risk_level="high")
    p_hrisk = TradePlanDraft(
        plan_id="p-hrisk", ticker=_TICKER, action_type="watch",
        evidence_quality="adequate", risk_controls=[rc_h]
    )
    r14 = build_trade_plan_report(_make_bundle(), [p_hrisk], _RUN_ID)
    check("T126: summary.high_risk_count==1", r14.summary.high_risk_count == 1)

    # T127: missing_evidence_count
    p_me = TradePlanDraft(
        plan_id="p-me", ticker=_TICKER, action_type="enter", evidence_quality="weak"
    )
    r15 = build_trade_plan_report(_make_bundle(), [p_me], _RUN_ID)
    check("T127: summary.missing_evidence_count==1", r15.summary.missing_evidence_count == 1)

    # T128: multi-plan horizons_covered
    p_s = TradePlanDraft(plan_id="p-s", ticker=_TICKER, action_type="watch", horizon="short")
    p_l = TradePlanDraft(plan_id="p-l", ticker=_TICKER, action_type="watch", horizon="long")
    r16 = build_trade_plan_report(_make_bundle(), [p_s, p_l], _RUN_ID)
    check("T128: short in horizons_covered", "short" in r16.summary.horizons_covered)
    check("T128b: long in horizons_covered", "long" in r16.summary.horizons_covered)

    # T129: different run_ids produce different report_ids
    b7 = _make_bundle()
    r17a = build_trade_plan_report(b7, [], "RUN_001")
    r17b = build_trade_plan_report(b7, [], "RUN_002")
    check("T129: different run_ids → different report_ids", r17a.report_id != r17b.report_id)

    # T130: bundle.warnings appear in report.warnings
    b8 = _make_bundle(warnings=["bundle-level-warning"])
    r18 = build_trade_plan_report(b8, [], _RUN_ID)
    check("T130: bundle.warnings propagated to report.warnings",
          "bundle-level-warning" in r18.warnings)

    # T131: warnings deduplicated in report.warnings
    _dup_w = "TradePlanInputBundle: decision_packet is missing. Trade plan drafts may lack decision rationale."
    b9 = _make_bundle(warnings=[_dup_w])
    r19 = build_trade_plan_report(b9, [], _RUN_ID)
    check("T131: duplicate report.warnings deduplicated",
          r19.warnings.count(_dup_w) == 1)

    # T132: plan with provided decision_packet still warns about horizon_synthesis
    b10 = _make_bundle(decision_packet=_MockDecisionPacket())
    r20 = build_trade_plan_report(b10, [], _RUN_ID)
    check("T132: decision_packet provided → no decision_packet warning",
          not any("decision_packet" in w for w in r20.warnings))
    check("T132b: horizon_synthesis still warns",
          any("horizon_synthesis" in w for w in r20.warnings))

    # T133: status unknown → summary.plan_count==0
    r21 = build_trade_plan_report(_make_bundle(), [], _RUN_ID)
    check("T133: no plans → summary.plan_count==0", r21.summary.plan_count == 0)

    # T134: all-unknown action → draft
    p_unk = TradePlanDraft(plan_id="p-unk", ticker=_TICKER, action_type="unknown")
    r22 = build_trade_plan_report(_make_bundle(), [p_unk], _RUN_ID)
    check("T134: all-unknown action → draft", r22.status == "draft")

    # T135: calculation_version matches constant
    check("T135: calculation_version matches constant",
          r21.calculation_version == _CALCULATION_VERSION)


# ---------------------------------------------------------------------------
# T140–T149: ToolResult adapter
# ---------------------------------------------------------------------------

def test_tool_result_adapter() -> None:
    print("\n--- trade_plan_tool_result_from_report (ToolResult adapter) ---")

    b = _make_bundle()
    p = _make_plan()
    report = build_trade_plan_report(b, [p], _RUN_ID)

    # T140: stable tool_name
    tr = trade_plan_tool_result_from_report(_RUN_ID, report)
    check("T140: tool_name == 'trade_plan_report'", tr.tool_name == _TRADE_PLAN_TOOL_NAME)
    check("T140b: tool_name matches constant", tr.tool_name == "trade_plan_report")

    # T141: deterministic evidence_id
    tr2 = trade_plan_tool_result_from_report(_RUN_ID, report)
    check("T141: evidence_id deterministic", tr.evidence_id == tr2.evidence_id)
    check("T141b: evidence_id non-empty string", isinstance(tr.evidence_id, str) and len(tr.evidence_id) > 0)

    # T142: approved_for_execution=False in summary payload
    check("T142: payload summary approved_for_execution=False",
          tr.outputs["summary"]["approved_for_execution"] is False)

    # T143: no order ticket fields in summary
    forbidden = {"order_id", "broker_order", "account_id", "execution_status"}
    summary_keys = set(tr.outputs.get("summary", {}).keys())
    check("T143: no order ticket fields in summary",
          not forbidden.intersection(summary_keys))

    # T144: target override
    tr3 = trade_plan_tool_result_from_report(_RUN_ID, report, target="MSFT")
    check("T144: target override applied", tr3.inputs["target"] == "MSFT")

    # T145: report not mutated
    original_warnings = list(report.warnings)
    trade_plan_tool_result_from_report(_RUN_ID, report)
    check("T145: report.warnings not mutated", report.warnings == original_warnings)

    # T146: calculation_version in outputs
    check("T146: calculation_version in outputs", "calculation_version" in tr.outputs)
    check("T146b: calculation_version value matches",
          tr.outputs["calculation_version"] == _CALCULATION_VERSION)

    # T147: full report in outputs
    check("T147: 'report' key in outputs", "report" in tr.outputs)
    check("T147b: report.target in payload", tr.outputs["report"]["target"] == _TICKER)

    # T148: summary payload has expected keys
    summary_payload = tr.outputs["summary"]
    for key in ["plan_count", "no_trade_count", "review_trigger_count",
                "high_risk_count", "missing_evidence_count"]:
        check(f"T148: summary has key '{key}'", key in summary_payload)

    # T149: run_id propagated to ToolResult
    check("T149: ToolResult run_id matches", tr.run_id == _RUN_ID)


# ---------------------------------------------------------------------------
# T150–T152: ID helper determinism
# ---------------------------------------------------------------------------

def test_id_helpers() -> None:
    print("\n--- make_trade_plan_report_id determinism ---")

    id1 = make_trade_plan_report_id(_RUN_ID, _TICKER, _AS_OF)
    id2 = make_trade_plan_report_id(_RUN_ID, _TICKER, _AS_OF)
    check("T150: report_id deterministic", id1 == id2)
    check("T150b: report_id has tpr_ prefix", id1.startswith("tpr_"))

    id3 = make_trade_plan_report_id(_RUN_ID, "MSFT", _AS_OF)
    check("T151: different ticker → different report_id", id1 != id3)

    id4 = make_trade_plan_report_id("OTHER_RUN", _TICKER, _AS_OF)
    check("T152: different run_id → different report_id", id1 != id4)


# ---------------------------------------------------------------------------
# T160–T162: __all__ exports
# ---------------------------------------------------------------------------

def test_all_exports() -> None:
    print("\n--- __all__ exports Phase 3R-B symbols ---")

    from lib.reliability import __all__ as exported_all

    phase3rb_symbols = [
        # Literals
        "TradePlanStatus",
        "TradePlanActionType",
        "TradePlanHorizon",
        "TradePlanTriggerType",
        "TradePlanRiskLevel",
        "TradePlanEvidenceQuality",
        # Models
        "TradePlanPriceZone",
        "TradePlanRiskControl",
        "TradePlanReviewTrigger",
        "TradePlanDraft",
        "TradePlanInputBundle",
        "TradePlanSummary",
        "TradePlanReport",
        # Helpers
        "make_trade_plan_report_id",
        "determine_trade_plan_status",
        "collect_trade_plan_source_ids",
        "summarize_trade_plans",
        "build_trade_plan_report",
        "trade_plan_tool_result_from_report",
    ]

    for sym in phase3rb_symbols:
        check(f"T160: __all__ exports {sym}", sym in exported_all)

    # T161: all __all__ symbols are accessible on the package
    import lib.reliability as pkg
    for sym in exported_all:
        check(f"T161: {sym} importable from lib.reliability", hasattr(pkg, sym))

    # T162: direct module import works
    try:
        import lib.reliability.trade_plan  # noqa: F401
        ok("T162: lib.reliability.trade_plan importable")
    except ImportError as e:
        fail("T162: lib.reliability.trade_plan importable", str(e))


# ---------------------------------------------------------------------------
# T170–T176: No forbidden dependencies
# ---------------------------------------------------------------------------

def test_no_forbidden_dependencies() -> None:
    print("\n--- No forbidden dependencies ---")

    import re
    src_path = os.path.join(
        os.path.dirname(__file__), "..", "lib", "reliability", "trade_plan.py"
    )
    with open(src_path) as f:
        src = f.read()

    import_lines = [
        ln.strip() for ln in src.splitlines()
        if ln.strip().startswith("import ") or ln.strip().startswith("from ")
    ]

    check("T170: no streamlit import", "import streamlit" not in src and "from streamlit" not in src)
    check("T171: no anthropic import", "import anthropic" not in src and "from anthropic" not in src)
    check("T172: no app.py import", not any("from app" == ln[:8] or ln.startswith("import app") for ln in import_lines))
    check("T173: no llm_orchestrator import", not any("llm_orchestrator" in ln for ln in import_lines))
    check("T174: no requests/httpx import", "import requests" not in src and "import httpx" not in src)
    check("T175: no broker import", not any("broker" in ln.lower() for ln in import_lines))

    # T176: approved_for_execution=True must not appear in source (assignment form)
    matches = re.findall(r"approved_for_execution\s*=\s*True", src)
    check("T176: no approved_for_execution=True assignment in source", len(matches) == 0)

    # T177: no order_id / broker_order / account_id / execution_status as Pydantic
    # field definitions or dict string keys (words may appear in docstrings, which is ok)
    import re as _re
    for field in ["order_id", "broker_order", "account_id", "execution_status"]:
        # Match patterns like: `field_name: type` or `"field_name":` or `field_name =`
        pattern = (
            rf'(?m)^[ \t]*{_re.escape(field)}\s*[=:]'   # Pydantic field or assignment
            rf'|"{_re.escape(field)}"'                   # dict string key
            rf"|'{_re.escape(field)}'"                   # dict string key (single-quoted)
        )
        matches = _re.findall(pattern, src)
        check(
            f"T177: no '{field}' as field def or dict key in source",
            len(matches) == 0,
            f"Found {len(matches)} occurrence(s) of '{field}' as field/key",
        )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("Phase 3R-B: Trade Plan Drafting Agent Skeleton — Test Suite")
    print("=" * 60)

    test_price_zone()
    test_risk_control()
    test_review_trigger()
    test_trade_plan_draft()
    test_input_bundle()
    test_execution_guard()
    test_status_determination()
    test_source_id_collection()
    test_report_builder()
    test_tool_result_adapter()
    test_id_helpers()
    test_all_exports()
    test_no_forbidden_dependencies()

    print()
    print("=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if _failed_tests:
        print("\nFailed tests:")
        for t in _failed_tests:
            print(f"  {t}")
    print("=" * 60)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
