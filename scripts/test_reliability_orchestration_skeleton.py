#!/usr/bin/env python3
"""
scripts/test_reliability_orchestration_skeleton.py

Phase 3A: Validated Agent Orchestration Skeleton — Test Suite (81 assertions).

Usage:
    python3 scripts/test_reliability_orchestration_skeleton.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Add repo root to sys.path before any project imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from pydantic import ValidationError

from lib.reliability.orchestration import (
    OrchestrationInputBundle,
    OrchestrationIssue,
    OrchestrationReport,
    OrchestrationStageResult,
    build_minimal_mock_agent_result,
    build_orchestration_report,
    make_orchestration_id,
    make_orchestration_issue_id,
    orchestration_report_tool_result_from_report,
    register_tool_results_in_evidence_store,
    run_critic_stage,
    run_staleness_stage,
    run_validated_orchestration,
    run_validation_aggregation_stage,
    run_validation_stage,
    summarize_orchestration_report,
)
from lib.reliability.schemas import (
    AgentConfidence,
    AgentResult,
    Assumption,
    EvidenceRef,
    Finding,
    Risk,
    ToolResult,
    ValidationReport,
)
from lib.reliability.validation_aggregator import ValidationAggregate

# ---------------------------------------------------------------------------
# Test counters and helpers
# ---------------------------------------------------------------------------

_PASS = 0
_FAIL = 0


def check(name: str, condition: bool, msg: str = "") -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        detail = f": {msg}" if msg else ""
        print(f"  FAIL  {name}{detail}")


def check_raises(name: str, exc_type, fn, *args, **kwargs) -> None:
    global _PASS, _FAIL
    try:
        fn(*args, **kwargs)
        _FAIL += 1
        print(f"  FAIL  {name}: expected {exc_type.__name__}, no exception raised")
    except exc_type:
        _PASS += 1
        print(f"  PASS  {name}")
    except Exception as exc:
        _FAIL += 1
        print(f"  FAIL  {name}: expected {exc_type.__name__}, got {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AS_OF = "2026-05-22"
_RUN_ID = "TEST_20260522_000000_abcd1234"


def _make_tool_result(idx: int = 0, run_id: str = _RUN_ID) -> ToolResult:
    return ToolResult(
        evidence_id=f"ev_mock_{run_id}_{idx}",
        tool_name=f"mock_tool_{idx}",
        run_id=run_id,
        outputs={"value": float(idx * 10), "label": f"output_{idx}"},
    )


def _make_valid_agent_result(
    tool_results: list[ToolResult],
    run_id: str = _RUN_ID,
) -> AgentResult:
    """Build an agent result with evidence refs pointing to given tool_results."""
    findings = [
        Finding(
            text=f"[TEST] Finding from tool '{tr.tool_name}'.",
            evidence=[EvidenceRef(
                evidence_id=tr.evidence_id,
                tool_name=tr.tool_name,
            )],
            confidence=0.8,
        )
        for tr in tool_results
    ]
    return AgentResult(
        agent_name="test_agent",
        run_id=run_id,
        findings=findings or [Finding(text="[TEST] No tool results.", evidence=[])],
        assumptions=[
            Assumption(name="test_assumption", rationale="Testing.", source="agent")
        ],
        risks=[Risk(name="test_risk", description="Testing risk.", severity="low")],
        confidence=AgentConfidence(
            level="low",
            rationale="Test only.",
            score=0.2,
        ),
    )


def _make_minimal_bundle(
    tool_results: list[ToolResult] | None = None,
    agent_result: AgentResult | None = None,
) -> OrchestrationInputBundle:
    return OrchestrationInputBundle(
        bundle_id="bundle_test_001",
        as_of=_AS_OF,
        mode="mock",
        tool_results=tool_results or [],
        agent_result=agent_result,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests() -> None:
    print("\n--- Test Group 1: OrchestrationIssue ---")

    # 1. OrchestrationIssue accepts valid issue
    check(
        "01_orchestration_issue_valid",
        OrchestrationIssue(
            issue_id="iss_001",
            issue_type="validation_issue",
            stage="validation",
            severity="warning",
            message="Test issue message.",
        ).message == "Test issue message.",
    )

    # 2. OrchestrationIssue rejects empty issue_id
    check_raises(
        "02_orchestration_issue_rejects_empty_id",
        ValidationError,
        OrchestrationIssue,
        issue_id="",
        issue_type="other",
        message="Some message.",
    )

    # 3. OrchestrationIssue rejects empty message
    check_raises(
        "03_orchestration_issue_rejects_empty_message",
        ValidationError,
        OrchestrationIssue,
        issue_id="iss_003",
        issue_type="other",
        message="",
    )

    print("\n--- Test Group 2: OrchestrationStageResult ---")

    # 4. OrchestrationStageResult accepts valid stage result
    sr = OrchestrationStageResult(
        stage="validation",
        status="pass",
        summary="Validation passed.",
    )
    check("04_stage_result_valid", sr.stage == "validation" and sr.status == "pass")

    print("\n--- Test Group 3: OrchestrationInputBundle ---")

    # 5. OrchestrationInputBundle accepts minimal bundle
    bundle = OrchestrationInputBundle(bundle_id="b_001", as_of=_AS_OF)
    check("05_input_bundle_minimal", bundle.bundle_id == "b_001")

    # 6. OrchestrationInputBundle rejects empty bundle_id
    check_raises(
        "06_input_bundle_rejects_empty_id",
        ValidationError,
        OrchestrationInputBundle,
        bundle_id="",
        as_of=_AS_OF,
    )

    # 7. OrchestrationInputBundle rejects empty as_of
    check_raises(
        "07_input_bundle_rejects_empty_as_of",
        ValidationError,
        OrchestrationInputBundle,
        bundle_id="b_007",
        as_of="",
    )

    print("\n--- Test Group 4: OrchestrationReport ---")

    # 8. OrchestrationReport accepts minimal report and normalizes status/recommendation
    report_clean = OrchestrationReport(
        orchestration_id="orch_001",
        as_of=_AS_OF,
    )
    check(
        "08_report_minimal_normalizes",
        report_clean.status == "pass" and report_clean.recommendation == "accept",
        f"status={report_clean.status!r} recommendation={report_clean.recommendation!r}",
    )

    # Test normalization with a validation_aggregate that has fail status
    from lib.reliability.validation_aggregator import (
        AggregatedValidationItem,
        make_validation_item_id,
    )
    crit_item = AggregatedValidationItem(
        item_id=make_validation_item_id("agent_result", "Critical error.", object_id="x"),
        domain="agent_result",
        severity="critical",
        item_type="evidence_binding",
        message="Critical error.",
        blocking=True,
    )
    fail_agg = ValidationAggregate(
        aggregate_id="agg_fail",
        as_of=_AS_OF,
        items=[crit_item],
    )
    report_fail = OrchestrationReport(
        orchestration_id="orch_002",
        as_of=_AS_OF,
        validation_aggregate=fail_agg,
    )
    check(
        "08b_report_fail_normalization",
        report_fail.status == "fail" and report_fail.recommendation == "reject",
        f"status={report_fail.status!r}",
    )

    # 9. OrchestrationReport rejects empty orchestration_id
    check_raises(
        "09_report_rejects_empty_id",
        ValidationError,
        OrchestrationReport,
        orchestration_id="",
        as_of=_AS_OF,
    )

    # 10. OrchestrationReport rejects empty as_of
    check_raises(
        "10_report_rejects_empty_as_of",
        ValidationError,
        OrchestrationReport,
        orchestration_id="orch_010",
        as_of="",
    )

    print("\n--- Test Group 5: Helper ID Functions ---")

    # 11. make_orchestration_issue_id deterministic
    id1 = make_orchestration_issue_id(
        "validation_issue", "validation", "Test message.", related_id="r1"
    )
    id2 = make_orchestration_issue_id(
        "validation_issue", "validation", "Test message.", related_id="r1"
    )
    check("11_issue_id_deterministic", id1 == id2, f"id1={id1!r} id2={id2!r}")

    # 12. make_orchestration_issue_id changes when inputs change
    id3 = make_orchestration_issue_id(
        "validation_issue", "validation", "Different message.", related_id="r1"
    )
    check(
        "12_issue_id_changes_on_input_change",
        id1 != id3,
        f"id1={id1!r} id3={id3!r}",
    )

    # 13. make_orchestration_id deterministic
    oid1 = make_orchestration_id("bundle_001", _AS_OF, "mock")
    oid2 = make_orchestration_id("bundle_001", _AS_OF, "mock")
    check("13_orchestration_id_deterministic", oid1 == oid2, f"oid1={oid1!r}")

    print("\n--- Test Group 6: register_tool_results_in_evidence_store ---")

    # 14. register_tool_results_in_evidence_store adds ToolResults
    tr1 = _make_tool_result(0)
    tr2 = _make_tool_result(1)
    with tempfile.TemporaryDirectory() as tmp:
        store14 = register_tool_results_in_evidence_store([tr1, tr2], run_dir=Path(tmp))
        check(
            "14_register_adds_tool_results",
            len(store14.evidence_ids()) == 2,
            f"count={len(store14.evidence_ids())}",
        )

    # 15. Duplicate evidence IDs are surfaced safely (no crash)
    tr_dup_a = _make_tool_result(0)
    tr_dup_b = _make_tool_result(0)  # same idx → same evidence_id
    check(
        "15_duplicate_evidence_ids_safe",
        tr_dup_a.evidence_id == tr_dup_b.evidence_id,
        "fixtures must have same evidence_id for this test",
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store15 = register_tool_results_in_evidence_store(
                [tr_dup_a, tr_dup_b], run_dir=Path(tmp)
            )
        # Should have 1, not 2 (duplicate skipped)
        check(
            "15b_duplicate_skipped_not_crash",
            len(store15.evidence_ids()) == 1,
            f"expected 1, got {len(store15.evidence_ids())}",
        )
    except Exception as exc:
        check("15b_duplicate_skipped_not_crash", False, f"raised: {exc}")

    print("\n--- Test Group 7: build_minimal_mock_agent_result ---")

    # 16. build_minimal_mock_agent_result creates valid AgentResult with evidence refs
    tr_for_mock = _make_tool_result(0)
    ar_mock = build_minimal_mock_agent_result([tr_for_mock], _AS_OF)
    check(
        "16_mock_agent_result_valid",
        (
            ar_mock.agent_name == "mock_orchestration_agent"
            and len(ar_mock.findings) == 1
            and len(ar_mock.findings[0].evidence) == 1
            and ar_mock.findings[0].evidence[0].evidence_id == tr_for_mock.evidence_id
        ),
    )

    print("\n--- Test Group 8: Stage Helpers ---")

    # 17. run_validation_stage calls existing validator successfully
    from lib.reliability.evidence_store import EvidenceStore
    with tempfile.TemporaryDirectory() as tmp:
        store17 = EvidenceStore(Path(tmp))
        tr17 = _make_tool_result(0)
        store17.add_tool_result(tr17)
        ar17 = _make_valid_agent_result([tr17])
        val_report17 = run_validation_stage(ar17, store17)
        check(
            "17_run_validation_stage_success",
            val_report17 is not None and hasattr(val_report17, "passed"),
        )

    # 18. run_validation_aggregation_stage returns ValidationAggregate
    val_report18 = ValidationReport(
        passed=True,
        run_id=_RUN_ID,
        target_name="test_target",
    )
    agg18 = run_validation_aggregation_stage(val_report18)
    check(
        "18_validation_aggregation_returns_aggregate",
        isinstance(agg18, ValidationAggregate) and hasattr(agg18, "status"),
    )

    # 19. run_staleness_stage returns StalenessReport
    from lib.reliability.staleness import StalenessReport
    tr19 = _make_tool_result(0)
    stale19 = run_staleness_stage([tr19], _AS_OF)
    check(
        "19_staleness_stage_returns_report",
        isinstance(stale19, StalenessReport) and hasattr(stale19, "status"),
    )

    # 20. run_critic_stage returns CriticResult
    from lib.reliability.critic import CriticResult
    critic20 = run_critic_stage(as_of=_AS_OF)
    check(
        "20_critic_stage_returns_critic_result",
        isinstance(critic20, CriticResult) and hasattr(critic20, "status"),
    )

    print("\n--- Test Group 9: build_orchestration_report ---")

    # 21. build_orchestration_report includes validation/staleness/critic outputs
    bundle21 = _make_minimal_bundle([_make_tool_result(0)])
    tr21 = _make_tool_result(0)
    stale21 = run_staleness_stage([tr21], _AS_OF)
    critic21 = run_critic_stage(as_of=_AS_OF)
    report21 = build_orchestration_report(
        orchestration_id="orch_021",
        as_of=_AS_OF,
        input_bundle=bundle21,
        staleness_report=stale21,
        critic_result=critic21,
    )
    check(
        "21_build_report_includes_outputs",
        (
            report21.staleness_report is stale21
            and report21.critic_result is critic21
            and report21.orchestration_id == "orch_021"
        ),
    )

    print("\n--- Test Group 10: run_validated_orchestration ---")

    # 22. run_validated_orchestration works end-to-end on clean synthetic input
    tr22a = _make_tool_result(0, run_id="AAPL_20260522_000000_clean001")
    tr22b = _make_tool_result(1, run_id="AAPL_20260522_000000_clean001")
    bundle22 = OrchestrationInputBundle(
        bundle_id="bundle_clean_022",
        as_of=_AS_OF,
        mode="mock",
        tool_results=[tr22a, tr22b],
    )
    try:
        report22 = run_validated_orchestration(bundle22)
        check(
            "22_end_to_end_clean_input",
            (
                isinstance(report22, OrchestrationReport)
                and report22.status != "error"
                and len(report22.stage_results) > 0
            ),
            f"status={report22.status!r}",
        )
    except Exception as exc:
        check("22_end_to_end_clean_input", False, f"raised: {exc}")

    # 23. run_validated_orchestration does not mutate input bundle
    bundle23 = OrchestrationInputBundle(
        bundle_id="bundle_immutable_023",
        as_of=_AS_OF,
        mode="mock",
        tool_results=[_make_tool_result(0, run_id="IMMUT_023")],
    )
    original_bundle_id = bundle23.bundle_id
    original_as_of = bundle23.as_of
    original_mode = bundle23.mode
    original_tr_count = len(bundle23.tool_results)
    _ = run_validated_orchestration(bundle23)
    check(
        "23_no_mutation_of_input_bundle",
        (
            bundle23.bundle_id == original_bundle_id
            and bundle23.as_of == original_as_of
            and bundle23.mode == original_mode
            and len(bundle23.tool_results) == original_tr_count
        ),
    )

    # 24. run_validated_orchestration handles missing ToolResults safely
    bundle24 = OrchestrationInputBundle(
        bundle_id="bundle_empty_024",
        as_of=_AS_OF,
        mode="mock",
        tool_results=[],
    )
    try:
        report24 = run_validated_orchestration(bundle24)
        check(
            "24_handles_missing_tool_results",
            (
                isinstance(report24, OrchestrationReport)
                and report24.status in ("pass", "pass_with_warnings", "fail")
            ),
            f"status={report24.status!r}",
        )
    except Exception as exc:
        check("24_handles_missing_tool_results", False, f"raised: {exc}")

    print("\n--- Test Group 11: orchestration_report_tool_result_from_report ---")

    # 25. orchestration_report_tool_result_from_report returns valid ToolResult
    bundle25 = _make_minimal_bundle([_make_tool_result(0, run_id="TR25_001")])
    report25 = run_validated_orchestration(bundle25)
    tr_wrap25 = orchestration_report_tool_result_from_report(_RUN_ID, report25)
    check(
        "25_orch_tool_result_valid",
        (
            isinstance(tr_wrap25, ToolResult)
            and tr_wrap25.tool_name == "orchestration_report"
            and tr_wrap25.run_id == _RUN_ID
        ),
    )

    # 26. Orchestration ToolResult has stable tool_name and target
    tr_wrap26 = orchestration_report_tool_result_from_report(
        _RUN_ID, report25, target="orchestration"
    )
    check(
        "26_tool_result_stable_name_target",
        (
            tr_wrap26.tool_name == "orchestration_report"
            and tr_wrap26.inputs.get("target") == "orchestration"
        ),
    )

    # 27. Orchestration ToolResult evidence_id deterministic for same run_id/report
    id_a = orchestration_report_tool_result_from_report(_RUN_ID, report25).evidence_id
    id_b = orchestration_report_tool_result_from_report(_RUN_ID, report25).evidence_id
    check(
        "27_evidence_id_deterministic",
        id_a == id_b,
        f"id_a={id_a!r} id_b={id_b!r}",
    )

    print("\n--- Test Group 12: summarize_orchestration_report ---")

    # 28. summarize_orchestration_report returns expected summary keys
    summary28 = summarize_orchestration_report(report25)
    required_keys = {
        "orchestration_id",
        "status",
        "recommendation",
        "mode",
        "stage_count",
        "issue_count",
        "critical_count",
        "warning_count",
        "info_count",
        "validation_status",
        "staleness_status",
        "critic_status",
        "top_messages",
    }
    missing = required_keys - set(summary28.keys())
    check(
        "28_summary_has_expected_keys",
        len(missing) == 0,
        f"missing keys: {missing}",
    )

    print("\n--- Test Group 13: Serialization Roundtrips ---")

    # 29. OrchestrationReport serialization roundtrip
    report29 = OrchestrationReport(
        orchestration_id="orch_029",
        as_of=_AS_OF,
        mode="dry_run",
        issues=[
            OrchestrationIssue(
                issue_id="iss_029",
                issue_type="other",
                message="Roundtrip test issue.",
            )
        ],
    )
    try:
        dumped29 = report29.model_dump()
        restored29 = OrchestrationReport.model_validate(dumped29)
        check(
            "29_report_serialization_roundtrip",
            restored29.orchestration_id == "orch_029"
            and restored29.mode == "dry_run"
            and len(restored29.issues) == 1,
        )
    except Exception as exc:
        check("29_report_serialization_roundtrip", False, f"raised: {exc}")

    # 30. OrchestrationIssue serialization roundtrip
    issue30 = OrchestrationIssue(
        issue_id="iss_030",
        issue_type="validation_issue",
        stage="critic",
        severity="warning",
        message="Roundtrip test.",
        related_id="rel_030",
        metadata={"key": "value"},
    )
    try:
        dumped30 = issue30.model_dump()
        restored30 = OrchestrationIssue.model_validate(dumped30)
        check(
            "30_issue_serialization_roundtrip",
            restored30.issue_id == "iss_030"
            and restored30.metadata.get("key") == "value",
        )
    except Exception as exc:
        check("30_issue_serialization_roundtrip", False, f"raised: {exc}")

    print("\n--- Test Group 14: Safety / Isolation Checks ---")

    # 31. No live app modules are imported by the orchestration module
    bad_modules = [
        m for m in sys.modules
        if any(
            m == bad or m.startswith(bad + ".")
            for bad in ("app", "pages", "lib.llm_orchestrator", "streamlit")
        )
    ]
    check(
        "31_no_live_app_modules",
        len(bad_modules) == 0,
        f"found live modules: {bad_modules[:5]}",
    )

    # 32. No external network/API library imported by orchestration module
    net_modules = [
        m for m in sys.modules
        if any(
            m == bad or m.startswith(bad + ".")
            for bad in ("requests", "httpx", "urllib3", "aiohttp", "boto3")
        )
    ]
    check(
        "32_no_network_modules",
        len(net_modules) == 0,
        f"found network modules: {net_modules[:5]}",
    )

    # 33. No Claude/LLM API is imported
    llm_modules = [
        m for m in sys.modules
        if any(
            m == bad or m.startswith(bad + ".")
            for bad in ("anthropic", "openai", "langchain", "llama_index")
        )
    ]
    check(
        "33_no_llm_api_modules",
        len(llm_modules) == 0,
        f"found LLM modules: {llm_modules[:5]}",
    )

    # 34. Existing validate_agent_result behavior remains unchanged
    from lib.reliability.validators import validate_agent_result
    from lib.reliability.evidence_store import EvidenceStore
    with tempfile.TemporaryDirectory() as tmp:
        store34 = EvidenceStore(Path(tmp))
        tr34 = _make_tool_result(0, run_id="VALIDATE34")
        store34.add_tool_result(tr34)
        ar34 = _make_valid_agent_result([tr34], run_id="VALIDATE34")
        vr34 = validate_agent_result(ar34, store34)
        check(
            "34_validate_agent_result_unchanged",
            hasattr(vr34, "passed") and isinstance(vr34.passed, bool),
        )

    # 35. Existing evaluation harness still passes (regression)
    try:
        from lib.reliability.evaluation import run_reliability_evals
        evals_dir = Path(_REPO_ROOT) / "evals"
        if evals_dir.is_dir():
            score35 = run_reliability_evals(
                cases_dir=str(evals_dir / "cases"),
                expected_dir=str(evals_dir / "expected"),
            )
            check(
                "35_eval_harness_regression",
                score35.total_cases > 0
                and score35.passed_cases == score35.total_cases
                and score35.missed_count == 0,
                (
                    f"total={score35.total_cases} "
                    f"passed={score35.passed_cases} "
                    f"missed={score35.missed_count}"
                ),
            )
        else:
            check("35_eval_harness_regression", False, "evals/ directory not found")
    except Exception as exc:
        check("35_eval_harness_regression", False, f"raised: {exc}")

    print("\n--- Test Group 15: Precomputed Artifact Passthrough ---")

    # 36. Precomputed validation_aggregate is preserved in final report
    val_rpt36 = ValidationReport(passed=True, run_id=_RUN_ID, target_name="precomp_target_36")
    pre_agg36 = run_validation_aggregation_stage(val_rpt36)
    pre_agg_id36 = pre_agg36.aggregate_id
    bundle36 = OrchestrationInputBundle(
        bundle_id="bundle_precomp_036",
        as_of=_AS_OF,
        mode="mock",
        tool_results=[_make_tool_result(0, run_id="PRECOMP_036")],
        validation_aggregate=pre_agg36,
    )
    try:
        report36 = run_validated_orchestration(bundle36)
        check(
            "36_precomputed_validation_aggregate_preserved",
            (
                report36.validation_aggregate is not None
                and report36.validation_aggregate.aggregate_id == pre_agg_id36
            ),
            f"expected {pre_agg_id36!r}",
        )
        agg_stage36 = next(
            (sr for sr in report36.stage_results if sr.stage == "validation_aggregation"),
            None,
        )
        check(
            "36b_precomputed_agg_stage_source_metadata",
            agg_stage36 is not None and agg_stage36.metadata.get("source") == "precomputed",
            f"metadata={agg_stage36.metadata if agg_stage36 else 'no stage'}",
        )
    except Exception as exc:
        check("36_precomputed_validation_aggregate_preserved", False, f"raised: {exc}")
        check("36b_precomputed_agg_stage_source_metadata", False, f"raised: {exc}")

    # 37. Precomputed staleness_report is preserved in final report
    pre_stale37 = run_staleness_stage([_make_tool_result(0, run_id="PRECOMP_037")], _AS_OF)
    pre_stale_id37 = pre_stale37.report_id
    bundle37 = OrchestrationInputBundle(
        bundle_id="bundle_precomp_037",
        as_of=_AS_OF,
        mode="mock",
        tool_results=[_make_tool_result(0, run_id="PRECOMP_037")],
        staleness_report=pre_stale37,
    )
    try:
        report37 = run_validated_orchestration(bundle37)
        check(
            "37_precomputed_staleness_report_preserved",
            (
                report37.staleness_report is not None
                and report37.staleness_report.report_id == pre_stale_id37
            ),
            f"expected {pre_stale_id37!r}",
        )
        stale_stage37 = next(
            (sr for sr in report37.stage_results if sr.stage == "staleness"), None
        )
        check(
            "37b_precomputed_staleness_stage_source_metadata",
            stale_stage37 is not None and stale_stage37.metadata.get("source") == "precomputed",
            f"metadata={stale_stage37.metadata if stale_stage37 else 'no stage'}",
        )
    except Exception as exc:
        check("37_precomputed_staleness_report_preserved", False, f"raised: {exc}")
        check("37b_precomputed_staleness_stage_source_metadata", False, f"raised: {exc}")

    # 38. Precomputed critic_result is preserved in final report
    pre_critic38 = run_critic_stage(as_of=_AS_OF)
    pre_critic_id38 = pre_critic38.critic_id
    bundle38 = OrchestrationInputBundle(
        bundle_id="bundle_precomp_038",
        as_of=_AS_OF,
        mode="mock",
        tool_results=[_make_tool_result(0, run_id="PRECOMP_038")],
        critic_result=pre_critic38,
    )
    try:
        report38 = run_validated_orchestration(bundle38)
        check(
            "38_precomputed_critic_result_preserved",
            (
                report38.critic_result is not None
                and report38.critic_result.critic_id == pre_critic_id38
            ),
            f"expected {pre_critic_id38!r}",
        )
        critic_stage38 = next(
            (sr for sr in report38.stage_results if sr.stage == "critic"), None
        )
        check(
            "38b_precomputed_critic_stage_source_metadata",
            critic_stage38 is not None and critic_stage38.metadata.get("source") == "precomputed",
            f"metadata={critic_stage38.metadata if critic_stage38 else 'no stage'}",
        )
    except Exception as exc:
        check("38_precomputed_critic_result_preserved", False, f"raised: {exc}")
        check("38b_precomputed_critic_stage_source_metadata", False, f"raised: {exc}")

    # 39. Bundle without precomputed artifacts uses computed source for all three stages
    bundle39 = OrchestrationInputBundle(
        bundle_id="bundle_compute_039",
        as_of=_AS_OF,
        mode="mock",
        tool_results=[_make_tool_result(0, run_id="COMPUTE_039")],
    )
    try:
        report39 = run_validated_orchestration(bundle39)
        agg39 = next((sr for sr in report39.stage_results if sr.stage == "validation_aggregation"), None)
        stale39 = next((sr for sr in report39.stage_results if sr.stage == "staleness"), None)
        critic39 = next((sr for sr in report39.stage_results if sr.stage == "critic"), None)
        check(
            "39_no_precomputed_artifacts_all_sources_computed",
            (
                agg39 is not None and agg39.metadata.get("source") == "computed"
                and stale39 is not None and stale39.metadata.get("source") == "computed"
                and critic39 is not None and critic39.metadata.get("source") == "computed"
            ),
            f"agg={agg39.metadata.get('source') if agg39 else None!r} "
            f"stale={stale39.metadata.get('source') if stale39 else None!r} "
            f"critic={critic39.metadata.get('source') if critic39 else None!r}",
        )
    except Exception as exc:
        check("39_no_precomputed_artifacts_all_sources_computed", False, f"raised: {exc}")

    print("\n--- Test Group 16: ToolResult Payload Contract ---")

    # 40. orchestration_report_tool_result_from_report payload includes "report" key
    bundle40 = _make_minimal_bundle([_make_tool_result(0, run_id="TR40_001")])
    report40 = run_validated_orchestration(bundle40)
    tr_wrap40 = orchestration_report_tool_result_from_report(_RUN_ID, report40)
    check(
        "40_tool_result_payload_includes_report",
        isinstance(tr_wrap40.outputs, dict) and "report" in tr_wrap40.outputs,
        f"keys={list(tr_wrap40.outputs.keys()) if isinstance(tr_wrap40.outputs, dict) else 'not a dict'}",
    )

    # 41. payload["report"]["orchestration_id"] matches report.orchestration_id
    check(
        "41_payload_report_orchestration_id_matches",
        (
            isinstance(tr_wrap40.outputs.get("report"), dict)
            and tr_wrap40.outputs["report"].get("orchestration_id") == report40.orchestration_id
        ),
        f"expected {report40.orchestration_id!r}",
    )

    # 42. payload includes "summary" key
    check(
        "42_tool_result_payload_includes_summary",
        "summary" in tr_wrap40.outputs,
        f"keys={list(tr_wrap40.outputs.keys()) if isinstance(tr_wrap40.outputs, dict) else 'not a dict'}",
    )

    # 43. payload includes "calculation_version" key
    check(
        "43_tool_result_payload_includes_calculation_version",
        "calculation_version" in tr_wrap40.outputs,
        f"keys={list(tr_wrap40.outputs.keys()) if isinstance(tr_wrap40.outputs, dict) else 'not a dict'}",
    )

    # 44. evidence_id remains deterministic for same run_id and report (stable ID payload)
    id44a = orchestration_report_tool_result_from_report(_RUN_ID, report40).evidence_id
    id44b = orchestration_report_tool_result_from_report(_RUN_ID, report40).evidence_id
    check(
        "44_stable_id_payload_evidence_id_deterministic",
        id44a == id44b,
        f"id_a={id44a!r} id_b={id44b!r}",
    )

    print("\n--- Test Group 9: Phase 3A export smoke test (lib.reliability) ---")

    import lib.reliability as _pkg

    _EXPECTED_PHASE3A_SYMBOLS = [
        "OrchestrationInputBundle",
        "OrchestrationIssue",
        "OrchestrationReport",
        "OrchestrationStageResult",
        "make_orchestration_id",
        "make_orchestration_issue_id",
        "register_tool_results_in_evidence_store",
        "build_minimal_mock_agent_result",
        "run_validation_stage",
        "run_validation_aggregation_stage",
        "run_staleness_stage",
        "run_critic_stage",
        "build_orchestration_report",
        "run_validated_orchestration",
        "orchestration_report_tool_result_from_report",
        "summarize_orchestration_report",
    ]

    # 45. All Phase 3A symbols are accessible from lib.reliability namespace
    for sym in _EXPECTED_PHASE3A_SYMBOLS:
        check(
            f"45_lib_reliability_has_{sym}",
            hasattr(_pkg, sym),
            f"lib.reliability.{sym} not found",
        )

    # 46. All Phase 3A symbols are listed in lib.reliability.__all__
    for sym in _EXPECTED_PHASE3A_SYMBOLS:
        check(
            f"46_lib_reliability_all_contains_{sym}",
            sym in _pkg.__all__,
            f"{sym!r} missing from lib.reliability.__all__",
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 64)
    print("Phase 3A: Validated Agent Orchestration Skeleton Tests")
    print("=" * 64)

    run_tests()

    total = _PASS + _FAIL
    print(f"\nResults: {_PASS}/{total} passed, {_FAIL} failed")

    if _FAIL > 0:
        print("\nSome tests FAILED.")
        sys.exit(1)

    print("\nAll tests passed.")
    sys.exit(0)
