"""
lib/reliability/evaluation.py

Evaluation harness schemas and helpers for Phase 2K.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no file I/O side effects
    outside of the explicit load/save helpers.
  - Deterministic only — no live data fetching, no API calls.
  - Uses existing reliability components: validate_agent_result,
    run_mock_critic, ValidationAggregate, StalenessReport.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.

See docs/reliability_phase_2k_evaluation_harness.md for full design.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

EvalCaseStatus = Literal["pass", "fail", "error", "skipped"]

EvalDetectionStatus = Literal[
    "detected",
    "missed",
    "false_positive",
    "not_applicable",
]

ReliabilityFailureMode = Literal[
    "unsupported_numeric_claim",
    "hallucinated_evidence_id",
    "stale_news_used_as_fresh",
    "missing_downside_risk",
    "missing_assumption",
    "overconfidence_with_validation_warnings",
    "overconfidence_with_stale_data",
    "horizon_mismatch",
    "unsupported_trade_plan",
    "option_strategy_without_risk_budget",
    "conflicting_evidence",
    "clean_minimal_case",
    "other",
]

# All required failure modes for the harness
REQUIRED_FAILURE_MODES: list[str] = [
    "unsupported_numeric_claim",
    "hallucinated_evidence_id",
    "stale_news_used_as_fresh",
    "missing_downside_risk",
    "missing_assumption",
    "overconfidence_with_validation_warnings",
    "overconfidence_with_stale_data",
    "horizon_mismatch",
    "unsupported_trade_plan",
    "option_strategy_without_risk_budget",
    "conflicting_evidence",
    "clean_minimal_case",
]


# ---------------------------------------------------------------------------
# 1. ReliabilityEvalCase
# ---------------------------------------------------------------------------

class ReliabilityEvalCase(BaseModel):
    """
    One synthetic evaluation case representing a specific failure mode.

    Fields:
        case_id:      Non-empty unique identifier.
        description:  Human-readable description of the case.
        failure_mode: Which reliability failure mode this case exercises.
        inputs:       Raw inputs dict (agent_result, tool_results, etc.).
        metadata:     Arbitrary case metadata (severity_expected, notes, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    failure_mode: ReliabilityFailureMode
    inputs: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("case_id", "description")
    @classmethod
    def _no_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(f"Field must not be whitespace-only; got {v!r}.")
        return v


# ---------------------------------------------------------------------------
# 2. ReliabilityExpectedOutput
# ---------------------------------------------------------------------------

class ReliabilityExpectedOutput(BaseModel):
    """
    Expected detection output for one eval case.

    Fields:
        case_id:               Matches the corresponding ReliabilityEvalCase.
        expected_status:       Expected overall pass/fail status (optional).
        expected_issue_types:  Issue types that must be present to pass.
        allowed_issue_types:   Additional issue types that are acceptable but not required.
        expected_min_critical: Minimum number of critical issues expected.
        expected_min_warnings: Minimum number of warning issues expected.
        expected_detected:     True if the failure should be detected.
        metadata:              Arbitrary metadata (notes, severity_expected, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    expected_status: Optional[str] = None
    expected_issue_types: list[str] = Field(default_factory=list)
    allowed_issue_types: list[str] = Field(default_factory=list)
    expected_min_critical: int = Field(default=0, ge=0)
    expected_min_warnings: int = Field(default=0, ge=0)
    expected_detected: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("case_id")
    @classmethod
    def _no_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(f"case_id must not be whitespace-only; got {v!r}.")
        return v


# ---------------------------------------------------------------------------
# 3. ReliabilityEvalCaseResult
# ---------------------------------------------------------------------------

class ReliabilityEvalCaseResult(BaseModel):
    """
    Result of running one eval case through the reliability harness.

    Fields:
        case_id:               Matches the original ReliabilityEvalCase.
        failure_mode:          Failure mode exercised.
        status:                Whether the case passed, failed, errored, or was skipped.
        detection_status:      Whether the failure was detected, missed, etc.
        detected_issue_types:  Issue types actually produced by the harness.
        critical_count:        Number of critical issues produced.
        warning_count:         Number of warning issues produced.
        info_count:            Number of info issues produced.
        passed_expectation:    True if actual output matched expected output.
        messages:              Human-readable result messages.
        metadata:              Arbitrary result metadata.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    failure_mode: ReliabilityFailureMode
    status: EvalCaseStatus
    detection_status: EvalDetectionStatus
    detected_issue_types: list[str] = Field(default_factory=list)
    critical_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    info_count: int = Field(default=0, ge=0)
    passed_expectation: bool
    messages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 4. ReliabilityScoreSummary
# ---------------------------------------------------------------------------

class ReliabilityScoreSummary(BaseModel):
    """
    Summary of running all eval cases through the reliability harness.

    Fields:
        total_cases:        Total number of cases run.
        passed_cases:       Cases where passed_expectation is True.
        failed_cases:       Cases where status is 'fail'.
        error_cases:        Cases where status is 'error'.
        skipped_cases:      Cases where status is 'skipped'.
        detection_rate:     Fraction of cases with detection_status == 'detected'
                            (over non-not_applicable cases; 0.0 if none).
        false_positive_count: Cases with detection_status == 'false_positive'.
        missed_count:       Cases with detection_status == 'missed'.
        results:            Full list of individual case results.
        metadata:           Arbitrary metadata (run timestamp, harness version, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    total_cases: int = Field(default=0, ge=0)
    passed_cases: int = Field(default=0, ge=0)
    failed_cases: int = Field(default=0, ge=0)
    error_cases: int = Field(default=0, ge=0)
    skipped_cases: int = Field(default=0, ge=0)
    detection_rate: float = Field(default=0.0)
    false_positive_count: int = Field(default=0, ge=0)
    missed_count: int = Field(default=0, ge=0)
    results: list[ReliabilityEvalCaseResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _clamp_detection_rate(self) -> "ReliabilityScoreSummary":
        rate = self.detection_rate
        if rate < 0.0:
            self.detection_rate = 0.0
        elif rate > 1.0:
            self.detection_rate = 1.0
        return self


# ---------------------------------------------------------------------------
# Helper 0: _make_load_error_result
# ---------------------------------------------------------------------------

def _make_load_error_result(case_id: str, message: str) -> "ReliabilityEvalCaseResult":
    """Create a synthetic error result for fixture load failures and contract violations."""
    return ReliabilityEvalCaseResult(
        case_id=case_id,
        failure_mode="other",
        status="error",
        detection_status="not_applicable",
        detected_issue_types=[],
        critical_count=0,
        warning_count=0,
        info_count=0,
        passed_expectation=False,
        messages=[message],
    )


# ---------------------------------------------------------------------------
# Helper 1: load_eval_cases
# ---------------------------------------------------------------------------

def load_eval_cases(cases_dir: str) -> list[ReliabilityEvalCase]:
    """
    Load all ReliabilityEvalCase objects from JSON files in cases_dir.

    Strict (fail-closed): raises ValueError if the directory is missing,
    contains no JSON files, or any file is malformed.

    Args:
        cases_dir: Path to the directory containing case JSON files.

    Returns:
        List of ReliabilityEvalCase, sorted by case_id.

    Raises:
        ValueError: If the directory is missing, empty, or any file is malformed.
    """
    cases_path = Path(cases_dir)
    if not cases_path.is_dir():
        raise ValueError(
            f"Cases directory not found or is not a directory: {cases_dir!r}"
        )
    json_files = sorted(cases_path.glob("*.json"))
    if not json_files:
        raise ValueError(
            f"Cases directory contains no JSON files (empty): {cases_dir!r}"
        )
    cases: list[ReliabilityEvalCase] = []
    for fpath in json_files:
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
            case = ReliabilityEvalCase.model_validate(raw)
            cases.append(case)
        except Exception as exc:
            raise ValueError(
                f"Failed to load case fixture from {fpath}: {exc}"
            ) from exc
    return sorted(cases, key=lambda c: c.case_id)


# ---------------------------------------------------------------------------
# Helper 2: load_expected_outputs
# ---------------------------------------------------------------------------

def load_expected_outputs(expected_dir: str) -> dict[str, ReliabilityExpectedOutput]:
    """
    Load all ReliabilityExpectedOutput objects from JSON files in expected_dir.

    Strict (fail-closed): raises ValueError if the directory is missing,
    contains no JSON files, or any file is malformed.

    Returns:
        Dict mapping case_id → ReliabilityExpectedOutput.

    Raises:
        ValueError: If the directory is missing, empty, or any file is malformed.
    """
    expected_path = Path(expected_dir)
    if not expected_path.is_dir():
        raise ValueError(
            f"Expected outputs directory not found or is not a directory: {expected_dir!r}"
        )
    json_files = sorted(expected_path.glob("*.json"))
    if not json_files:
        raise ValueError(
            f"Expected outputs directory contains no JSON files (empty): {expected_dir!r}"
        )
    expected: dict[str, ReliabilityExpectedOutput] = {}
    for fpath in json_files:
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
            exp = ReliabilityExpectedOutput.model_validate(raw)
            expected[exp.case_id] = exp
        except Exception as exc:
            raise ValueError(
                f"Failed to load expected output fixture from {fpath}: {exc}"
            ) from exc
    return expected


# ---------------------------------------------------------------------------
# Helper 3: run_single_eval_case
# ---------------------------------------------------------------------------

def run_single_eval_case(
    case: ReliabilityEvalCase,
    expected: Optional[ReliabilityExpectedOutput] = None,
) -> ReliabilityEvalCaseResult:
    """
    Run one eval case through the reliability harness and return a structured result.

    Behavior:
        - Deserializes agent_result, tool_results, validation_aggregate,
          staleness_report from case.inputs.
        - Runs validate_agent_result (with EvidenceStore) if agent_result and
          tool_results are provided.
        - Runs run_mock_critic with available inputs.
        - Collects all detected issue_types.
        - Calls compare_actual_to_expected if expected is provided.
        - Returns ReliabilityEvalCaseResult.

    No LLM calls. No API calls. No network. Deterministic.

    Args:
        case:     ReliabilityEvalCase to run.
        expected: Optional expected output for comparison.

    Returns:
        ReliabilityEvalCaseResult.
    """
    from lib.reliability.schemas import AgentResult, ToolResult
    from lib.reliability.validators import validate_agent_result
    from lib.reliability.evidence_store import EvidenceStore
    from lib.reliability.run_context import create_run_context
    from lib.reliability.critic import run_mock_critic, CriticIssue
    from lib.reliability.validation_aggregator import ValidationAggregate
    from lib.reliability.staleness import StalenessReport

    # Fail closed: expected output is mandatory for the fixed eval suite.
    if expected is None:
        return ReliabilityEvalCaseResult(
            case_id=case.case_id,
            failure_mode=case.failure_mode,
            status="error",
            detection_status="not_applicable",
            detected_issue_types=[],
            critical_count=0,
            warning_count=0,
            info_count=0,
            passed_expectation=False,
            messages=[
                f"Missing expected output for case_id={case.case_id!r}. "
                "Expected outputs are mandatory for the fixed eval suite."
            ],
        )

    messages: list[str] = []
    detected_issue_types: list[str] = []
    critical_count = 0
    warning_count = 0
    info_count = 0

    try:
        inputs = case.inputs

        # --- Deserialize inputs ---
        agent_result: Optional[AgentResult] = None
        validation_aggregate: Optional[ValidationAggregate] = None
        staleness_report: Optional[StalenessReport] = None
        tool_results: list[ToolResult] = []

        if "agent_result" in inputs:
            agent_result = AgentResult.model_validate(inputs["agent_result"])

        if "tool_results" in inputs:
            tool_results = [
                ToolResult.model_validate(tr) for tr in inputs["tool_results"]
            ]

        if "validation_aggregate" in inputs:
            validation_aggregate = ValidationAggregate.model_validate(
                inputs["validation_aggregate"]
            )

        if "staleness_report" in inputs:
            staleness_report = StalenessReport.model_validate(
                inputs["staleness_report"]
            )

        # --- Run validate_agent_result if we have agent_result ---
        if agent_result is not None:
            run_ctx = create_run_context(ticker=agent_result.ticker or "EVAL")
            store = EvidenceStore(run_dir=run_ctx.run_dir)
            for tr in tool_results:
                store.add_tool_result(tr)
            val_report = validate_agent_result(agent_result, store)
            if not val_report.passed:
                for issue in val_report.issues:
                    sev = issue.severity
                    code = issue.code or "validation_failure"
                    if sev == "error":
                        critical_count += 1
                        detected_issue_types.append("validation_failure")
                    elif sev == "warning":
                        warning_count += 1
                        detected_issue_types.append("validation_failure")
                    messages.append(f"[validate] {sev}: {issue.message}")

        # --- Run mock critic ---
        critic_run_id = f"eval_{case.case_id}"
        critic_result = run_mock_critic(
            critic_id=critic_run_id,
            as_of="2026-01-15T00:00:00+00:00",
            agent_result=agent_result,
            validation_aggregate=validation_aggregate,
            staleness_report=staleness_report,
        )

        for issue in critic_result.issues:
            detected_issue_types.append(issue.issue_type)
            if issue.severity == "critical":
                critical_count += 1
            elif issue.severity == "warning":
                warning_count += 1
            else:
                info_count += 1
            messages.append(
                f"[critic] {issue.severity}: {issue.issue_type} — {issue.message}"
            )

        # Deduplicate
        detected_issue_types = sorted(set(detected_issue_types))

        # Build raw result
        raw_result = ReliabilityEvalCaseResult(
            case_id=case.case_id,
            failure_mode=case.failure_mode,
            status="pass",
            detection_status="not_applicable",
            detected_issue_types=detected_issue_types,
            critical_count=critical_count,
            warning_count=warning_count,
            info_count=info_count,
            passed_expectation=True,
            messages=messages,
        )

        # Compare to expected if provided
        if expected is not None:
            return compare_actual_to_expected(raw_result, expected)
        return raw_result

    except Exception as exc:
        return ReliabilityEvalCaseResult(
            case_id=case.case_id,
            failure_mode=case.failure_mode,
            status="error",
            detection_status="not_applicable",
            detected_issue_types=[],
            critical_count=0,
            warning_count=0,
            info_count=0,
            passed_expectation=False,
            messages=[f"ERROR running case: {exc}"],
        )


# ---------------------------------------------------------------------------
# Helper 4: compare_actual_to_expected
# ---------------------------------------------------------------------------

def compare_actual_to_expected(
    actual_result: ReliabilityEvalCaseResult,
    expected: ReliabilityExpectedOutput,
) -> ReliabilityEvalCaseResult:
    """
    Compare actual eval result to expected output and return a final result.

    Comparison logic:
        - For clean_minimal_case (expected_detected=False): pass if no critical
          or warning issues.
        - For all other cases: pass if at least one expected_issue_type is
          present in detected_issue_types, or any allowed_issue_type is present.
        - Severity minimums: pass if critical_count >= expected_min_critical
          and warning_count >= expected_min_warnings.
        - Tolerant: does not require exact message matching.

    Args:
        actual_result: ReliabilityEvalCaseResult from run_single_eval_case.
        expected:      ReliabilityExpectedOutput for comparison.

    Returns:
        Updated ReliabilityEvalCaseResult with correct status, detection_status,
        passed_expectation, and messages.
    """
    messages = list(actual_result.messages)
    actual_types = set(actual_result.detected_issue_types)
    expected_types = set(expected.expected_issue_types)
    allowed_types = set(expected.allowed_issue_types)
    all_acceptable = expected_types | allowed_types

    if not expected.expected_detected:
        # Clean case — expect no critical/warning
        has_problem = (
            actual_result.critical_count > 0 or actual_result.warning_count > 0
        )
        if has_problem:
            detection_status: EvalDetectionStatus = "false_positive"
            passed = False
            status: EvalCaseStatus = "fail"
            messages.append(
                f"FAIL: Clean case produced unexpected issues "
                f"(critical={actual_result.critical_count}, "
                f"warning={actual_result.warning_count})."
            )
        else:
            detection_status = "not_applicable"
            passed = True
            status = "pass"
            messages.append("PASS: Clean case produced no critical/warning issues.")
    else:
        # Failure mode case — expect detection
        type_detected = bool(actual_types & all_acceptable) if all_acceptable else False
        # If no specific issue types expected, any non-empty detection counts
        if not expected_types and not allowed_types:
            type_detected = bool(actual_types)

        min_critical_met = actual_result.critical_count >= expected.expected_min_critical
        min_warning_met = actual_result.warning_count >= expected.expected_min_warnings

        if type_detected and min_critical_met and min_warning_met:
            detection_status = "detected"
            passed = True
            status = "pass"
            found = sorted(actual_types & all_acceptable) if all_acceptable else sorted(actual_types)
            messages.append(
                f"PASS: Expected failure mode detected. Issue types: {found}."
            )
        else:
            detection_status = "missed"
            passed = False
            status = "fail"
            reasons = []
            if not type_detected:
                reasons.append(
                    f"expected issue types {sorted(expected_types)} not detected "
                    f"(got {sorted(actual_types)})"
                )
            if not min_critical_met:
                reasons.append(
                    f"critical_count {actual_result.critical_count} < "
                    f"expected_min_critical {expected.expected_min_critical}"
                )
            if not min_warning_met:
                reasons.append(
                    f"warning_count {actual_result.warning_count} < "
                    f"expected_min_warnings {expected.expected_min_warnings}"
                )
            messages.append(f"FAIL: {'; '.join(reasons)}.")

    # Check expected_status if specified
    if expected.expected_status is not None and actual_result.status != "error":
        if expected.expected_status == "fail" and actual_result.critical_count == 0 and actual_result.warning_count == 0:
            # Fine — we just check detection
            pass

    return ReliabilityEvalCaseResult(
        case_id=actual_result.case_id,
        failure_mode=actual_result.failure_mode,
        status=status,
        detection_status=detection_status,
        detected_issue_types=sorted(actual_types),
        critical_count=actual_result.critical_count,
        warning_count=actual_result.warning_count,
        info_count=actual_result.info_count,
        passed_expectation=passed,
        messages=messages,
        metadata=actual_result.metadata,
    )


# ---------------------------------------------------------------------------
# Helper 5: run_reliability_evals
# ---------------------------------------------------------------------------

def run_reliability_evals(
    cases_dir: str,
    expected_dir: str,
) -> ReliabilityScoreSummary:
    """
    Load all cases and expected outputs, run each case, and return a summary.

    Fail-closed: returns a summary with error_cases > 0 if:
    - cases_dir or expected_dir is missing or empty
    - any fixture file is malformed
    - a case has no matching expected output
    - an expected output has no matching case

    Args:
        cases_dir:    Directory containing case JSON files.
        expected_dir: Directory containing expected output JSON files.

    Returns:
        ReliabilityScoreSummary with all case results.
        error_cases > 0 whenever the fixture contract is violated.
    """
    # Load cases — strict: raises ValueError on missing dir, empty dir, malformed JSON
    try:
        cases = load_eval_cases(cases_dir)
    except ValueError as exc:
        return _build_score_summary([
            _make_load_error_result(
                "__cases_load_error__",
                f"Cases load error: {exc}",
            )
        ])

    # Load expected outputs — strict
    try:
        expected_map = load_expected_outputs(expected_dir)
    except ValueError as exc:
        return _build_score_summary([
            _make_load_error_result(
                "__expected_load_error__",
                f"Expected outputs load error: {exc}",
            )
        ])

    results: list[ReliabilityEvalCaseResult] = []

    # Detect orphan expected outputs (expected file exists but no matching case)
    case_id_set = {c.case_id for c in cases}
    for eid in sorted(expected_map):
        if eid not in case_id_set:
            results.append(
                _make_load_error_result(
                    eid,
                    f"Expected output has no matching case: {eid!r}",
                )
            )

    # Run each case — missing expected → error result via run_single_eval_case
    for case in cases:
        expected = expected_map.get(case.case_id)
        result = run_single_eval_case(case, expected=expected)
        results.append(result)

    return _build_score_summary(results)


def _build_score_summary(
    results: list[ReliabilityEvalCaseResult],
) -> ReliabilityScoreSummary:
    """Build ReliabilityScoreSummary from a list of case results."""
    total = len(results)
    passed = sum(1 for r in results if r.passed_expectation)
    failed = sum(1 for r in results if r.status == "fail")
    errors = sum(1 for r in results if r.status == "error")
    skipped = sum(1 for r in results if r.status == "skipped")
    detected = sum(1 for r in results if r.detection_status == "detected")
    missed = sum(1 for r in results if r.detection_status == "missed")
    false_pos = sum(1 for r in results if r.detection_status == "false_positive")

    # Detection rate: detected / (detected + missed), or 0 if none
    denominator = detected + missed
    detection_rate = detected / denominator if denominator > 0 else 0.0

    return ReliabilityScoreSummary(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        error_cases=errors,
        skipped_cases=skipped,
        detection_rate=detection_rate,
        false_positive_count=false_pos,
        missed_count=missed,
        results=results,
    )


# ---------------------------------------------------------------------------
# Helper 6: summarize_reliability_score
# ---------------------------------------------------------------------------

def summarize_reliability_score(summary: ReliabilityScoreSummary) -> dict[str, Any]:
    """
    Return a concise summary dict for printing or logging.

    Args:
        summary: ReliabilityScoreSummary to summarise.

    Returns:
        dict with human-readable summary fields.
    """
    failed_cases = [r.case_id for r in summary.results if not r.passed_expectation]
    missed_cases = [r.case_id for r in summary.results if r.detection_status == "missed"]
    error_cases = [r.case_id for r in summary.results if r.status == "error"]
    return {
        "total_cases": summary.total_cases,
        "passed_cases": summary.passed_cases,
        "failed_cases_count": summary.failed_cases,
        "error_cases_count": summary.error_cases,
        "skipped_cases": summary.skipped_cases,
        "detection_rate": round(summary.detection_rate, 4),
        "false_positive_count": summary.false_positive_count,
        "missed_count": summary.missed_count,
        "failed_case_ids": failed_cases,
        "missed_case_ids": missed_cases,
        "error_case_ids": error_cases,
    }


# ---------------------------------------------------------------------------
# Helper 7: save_reliability_score_summary
# ---------------------------------------------------------------------------

def save_reliability_score_summary(
    summary: ReliabilityScoreSummary,
    output_path: str,
) -> None:
    """
    Save a ReliabilityScoreSummary to a JSON file.

    Args:
        summary:     ReliabilityScoreSummary to save.
        output_path: Path to write the JSON file.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        summary.model_dump_json(indent=2),
        encoding="utf-8",
    )
