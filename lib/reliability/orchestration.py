"""
lib/reliability/orchestration.py

Phase 3A: Validated Agent Orchestration Skeleton.

Design principles:
  - Standalone, deterministic, offline.
  - No live LLM calls, no live data fetching, no app integration.
  - Chains Phase 0-2 reliability artifacts end-to-end in dry-run/mock mode.
  - All enums and models use project-standard Pydantic v2 style.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.

See docs/reliability_phase_3a_validated_orchestration_skeleton.md for design.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.critic import CriticResult, run_mock_critic
from lib.reliability.evidence_store import EvidenceStore
from lib.reliability.evaluation import ReliabilityScoreSummary
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
from lib.reliability.staleness import (
    StalenessFinding,
    StalenessReport,
    aggregate_staleness_findings,
    check_tool_result_staleness,
    make_staleness_finding_id,
)
from lib.reliability.validation_aggregator import (
    ValidationAggregate,
    aggregate_validation_items,
    validation_report_to_items,
)
from lib.reliability.validators import validate_agent_result


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

OrchestrationStatus = Literal[
    "pass",
    "pass_with_warnings",
    "fail",
    "error",
    "unknown",
]

OrchestrationStage = Literal[
    "input_collection",
    "evidence_registration",
    "agent_result",
    "validation",
    "validation_aggregation",
    "staleness",
    "critic",
    "evaluation_reference",
    "synthesis",
    "unknown",
]

OrchestrationMode = Literal[
    "mock",
    "dry_run",
    "replay",
]

OrchestrationRecommendation = Literal[
    "accept",
    "revise",
    "reject",
    "needs_more_evidence",
    "unknown",
]

OrchestrationIssueType = Literal[
    "validation_issue",
    "stale_data",
    "critic_issue",
    "missing_input",
    "malformed_input",
    "evidence_error",
    "evaluation_gate_failure",
    "scope_violation",
    "other",
]

_ORCH_TOOL_NAME: str = "orchestration_report"
_ORCH_METRIC_GROUP: str = "orchestration_report"


# ---------------------------------------------------------------------------
# 1. OrchestrationIssue
# ---------------------------------------------------------------------------

class OrchestrationIssue(BaseModel):
    """One structured issue raised during orchestration."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1)
    issue_type: OrchestrationIssueType
    stage: OrchestrationStage = "unknown"
    severity: Literal["critical", "warning", "info"] = "warning"
    message: str = Field(min_length=1)
    related_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "OrchestrationIssue":
        for field_name in ("issue_id", "message"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 2. OrchestrationStageResult
# ---------------------------------------------------------------------------

class OrchestrationStageResult(BaseModel):
    """Result for one orchestration pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    stage: OrchestrationStage
    status: OrchestrationStatus = "unknown"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    summary: Optional[str] = None
    output_ids: list[str] = Field(default_factory=list)
    issues: list[OrchestrationIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 3. OrchestrationInputBundle
# ---------------------------------------------------------------------------

class OrchestrationInputBundle(BaseModel):
    """Input bundle for one orchestration run."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    mode: OrchestrationMode = "mock"
    tool_results: list[ToolResult] = Field(default_factory=list)
    agent_result: Optional[AgentResult] = None
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    reliability_score_summary: Optional[ReliabilityScoreSummary] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "OrchestrationInputBundle":
        for field_name in ("bundle_id", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 4. OrchestrationReport
# ---------------------------------------------------------------------------

class OrchestrationReport(BaseModel):
    """Auditable report produced by one orchestration run."""

    model_config = ConfigDict(extra="forbid")

    orchestration_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    mode: OrchestrationMode = "mock"
    status: OrchestrationStatus = "unknown"
    recommendation: OrchestrationRecommendation = "unknown"
    input_bundle_id: Optional[str] = None
    stage_results: list[OrchestrationStageResult] = Field(default_factory=list)
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    reliability_score_summary: Optional[ReliabilityScoreSummary] = None
    issues: list[OrchestrationIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "OrchestrationReport":
        for field_name in ("orchestration_id", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self

    @model_validator(mode="after")
    def _normalize_status_recommendation(self) -> "OrchestrationReport":
        """Derive status and recommendation from nested reliability outputs."""
        # Gather all issues (stage issues + top-level issues)
        all_issues: list[OrchestrationIssue] = list(self.issues)
        for sr in self.stage_results:
            all_issues.extend(sr.issues)

        has_critical = any(i.severity == "critical" for i in all_issues)
        has_warning = any(i.severity == "warning" for i in all_issues)
        has_error = any(sr.status == "error" for sr in self.stage_results)

        # Check critic_result status
        if self.critic_result is not None:
            if self.critic_result.status == "fail":
                has_critical = True
            elif self.critic_result.status == "pass_with_warnings":
                has_warning = True

        # Check validation_aggregate status
        if self.validation_aggregate is not None:
            if self.validation_aggregate.status == "fail":
                has_critical = True
            elif self.validation_aggregate.status == "pass_with_warnings":
                has_warning = True

        # Check staleness_report: critical severity findings → critical;
        # any non-fresh status with warnings → pass_with_warnings.
        if self.staleness_report is not None:
            if self.staleness_report.critical_count > 0:
                has_critical = True
            elif (
                self.staleness_report.warning_count > 0
                or self.staleness_report.stale_count > 0
                or self.staleness_report.expired_count > 0
                or self.staleness_report.near_stale_count > 0
            ):
                has_warning = True

        if has_error:
            self.status = "error"
            self.recommendation = "unknown"
        elif has_critical:
            self.status = "fail"
            self.recommendation = "reject"
        elif has_warning:
            self.status = "pass_with_warnings"
            self.recommendation = "revise"
        else:
            self.status = "pass"
            self.recommendation = "accept"

        return self


# ---------------------------------------------------------------------------
# Helper 1: make_orchestration_issue_id
# ---------------------------------------------------------------------------

def make_orchestration_issue_id(
    issue_type: str,
    stage: str,
    message: str,
    related_id: Optional[str] = None,
    evidence_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> str:
    """
    Build a deterministic, stable issue_id for an OrchestrationIssue.

    Same inputs always produce the same ID.
    Different message/related_id/evidence_id/field_path produces a different ID.
    """
    payload = {
        "issue_type": issue_type,
        "stage": stage,
        "message": message,
        "related_id": related_id or "",
        "evidence_id": evidence_id or "",
        "field_path": field_path or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    return f"{issue_type}:{stage}:{hash_suffix}"


# ---------------------------------------------------------------------------
# Helper 2: make_orchestration_id
# ---------------------------------------------------------------------------

def make_orchestration_id(
    bundle_id: str,
    as_of: str,
    mode: str = "mock",
) -> str:
    """
    Build a deterministic orchestration_id from bundle_id, as_of, and mode.

    Same inputs always produce the same ID.
    """
    payload = {"bundle_id": bundle_id, "as_of": as_of, "mode": mode}
    hash_suffix = stable_hash_payload(payload, length=16)
    return f"orch:{hash_suffix}"


# ---------------------------------------------------------------------------
# Helper 3: register_tool_results_in_evidence_store
# ---------------------------------------------------------------------------

def register_tool_results_in_evidence_store(
    tool_results: list[ToolResult],
    run_dir: Optional[Path] = None,
) -> EvidenceStore:
    """
    Create an EvidenceStore and register provided ToolResults.

    Behavior:
        - Creates an EvidenceStore at run_dir (or a new temporary directory).
        - Adds each ToolResult to the store.
        - Skips duplicates (same evidence_id) without crashing.
        - Does not fetch data.
        - Does not mutate ToolResults.

    Callers can detect duplicates by comparing len(tool_results) vs
    len(store.evidence_ids()) after the call returns.
    """
    if run_dir is None:
        tmp = tempfile.mkdtemp(prefix="orch_evidence_")
        run_dir = Path(tmp)

    store = EvidenceStore(run_dir)
    for tr in tool_results:
        try:
            store.add_tool_result(tr)
        except ValueError:
            # Duplicate evidence_id — skip silently.
            pass
    return store


# ---------------------------------------------------------------------------
# Helper 4: build_minimal_mock_agent_result
# ---------------------------------------------------------------------------

def build_minimal_mock_agent_result(
    tool_results: list[ToolResult],
    as_of: str,
    metadata: Optional[dict[str, Any]] = None,
) -> AgentResult:
    """
    Build a minimal valid AgentResult for dry-run/mock orchestration.

    Behavior:
        - Cites evidence IDs from provided ToolResults when available.
        - Content is clearly mock/test-only; contains no investment advice.
        - Does not call LLM.
        - Deterministic for same inputs.
    """
    run_id = tool_results[0].run_id if tool_results else "mock_run_id_no_inputs"

    findings: list[Finding] = []
    if tool_results:
        for tr in tool_results:
            findings.append(Finding(
                text=(
                    f"[MOCK] Processed tool result from '{tr.tool_name}' "
                    f"(dry-run only; not for investment use)."
                ),
                evidence=[EvidenceRef(
                    evidence_id=tr.evidence_id,
                    tool_name=tr.tool_name,
                    description="Mock evidence reference for dry-run orchestration.",
                )],
                confidence=0.5,
            ))
    else:
        findings.append(Finding(
            text="[MOCK] No tool results available for dry-run orchestration.",
            evidence=[],
            confidence=0.3,
        ))

    return AgentResult(
        agent_name="mock_orchestration_agent",
        run_id=run_id,
        findings=findings,
        assumptions=[
            Assumption(
                name="mock_mode",
                rationale="Running in mock/dry-run mode; no real data used.",
                source="agent",
                sensitivity="low",
            )
        ],
        risks=[
            Risk(
                name="mock_risk",
                description="Dry-run result; not suitable for real investment decisions.",
                severity="low",
            )
        ],
        confidence=AgentConfidence(
            level="low",
            rationale="Mock agent result for orchestration skeleton validation only.",
            score=0.2,
        ),
    )


# ---------------------------------------------------------------------------
# Helper 5: run_validation_stage
# ---------------------------------------------------------------------------

def run_validation_stage(
    agent_result: AgentResult,
    evidence_store: EvidenceStore,
) -> ValidationReport:
    """
    Run validate_agent_result() on the agent_result against the evidence_store.

    Does not change validator semantics.
    Does not mutate inputs.
    """
    return validate_agent_result(agent_result, evidence_store)


# ---------------------------------------------------------------------------
# Helper 6: run_validation_aggregation_stage
# ---------------------------------------------------------------------------

def run_validation_aggregation_stage(
    validation_report: ValidationReport,
) -> ValidationAggregate:
    """
    Convert a ValidationReport into a ValidationAggregate.

    Uses existing Phase 2H helpers.
    Does not mutate input.
    """
    items = validation_report_to_items(validation_report)
    aggregate_id = (
        f"agg:orch:{stable_hash_payload({'run_id': validation_report.run_id, 'target': validation_report.target_name}, length=16)}"
    )
    as_of = validation_report.created_at
    return aggregate_validation_items(aggregate_id, as_of, items)


# ---------------------------------------------------------------------------
# Helper 7: run_staleness_stage
# ---------------------------------------------------------------------------

def run_staleness_stage(
    tool_results: list[ToolResult],
    as_of: str,
) -> StalenessReport:
    """
    Run staleness checks on provided ToolResults.

    If no ToolResults are provided, returns a report with an unknown/warning finding.
    Does not fetch data.
    """
    if not tool_results:
        finding_id = make_staleness_finding_id(
            domain="unknown",
            timestamp_role="unknown",
            timestamp_value=None,
            as_of=as_of,
            source_name="orchestration_skeleton",
        )
        finding = StalenessFinding(
            finding_id=finding_id,
            domain="unknown",
            status="unknown",
            severity="warning",
            message="No tool results provided; staleness cannot be assessed.",
            as_of=as_of,
            source_name="orchestration_skeleton",
        )
        report_id = (
            f"staleness:no_inputs:{stable_hash_payload({'as_of': as_of}, length=16)}"
        )
        return aggregate_staleness_findings(report_id, as_of, [finding])

    all_findings: list[StalenessFinding] = []
    for tr in tool_results:
        sub_report = check_tool_result_staleness(tr, as_of)
        all_findings.extend(sub_report.findings)

    report_id = (
        f"staleness:orch:{stable_hash_payload({'as_of': as_of, 'count': len(tool_results)}, length=16)}"
    )
    return aggregate_staleness_findings(report_id, as_of, all_findings)


# ---------------------------------------------------------------------------
# Helper 8: run_critic_stage
# ---------------------------------------------------------------------------

def run_critic_stage(
    agent_result: Optional[AgentResult] = None,
    validation_aggregate: Optional[ValidationAggregate] = None,
    staleness_report: Optional[StalenessReport] = None,
    as_of: Optional[str] = None,
) -> CriticResult:
    """
    Run the deterministic mock critic over the provided inputs.

    Uses existing run_mock_critic().
    No LLM calls.
    """
    effective_as_of = as_of or _utcnow()
    critic_id = (
        f"critic:orch:{stable_hash_payload({'as_of': effective_as_of}, length=16)}"
    )
    return run_mock_critic(
        critic_id=critic_id,
        as_of=effective_as_of,
        agent_result=agent_result,
        validation_aggregate=validation_aggregate,
        staleness_report=staleness_report,
    )


# ---------------------------------------------------------------------------
# Helper 9: build_orchestration_report
# ---------------------------------------------------------------------------

def build_orchestration_report(
    orchestration_id: str,
    as_of: str,
    input_bundle: OrchestrationInputBundle,
    validation_aggregate: Optional[ValidationAggregate] = None,
    staleness_report: Optional[StalenessReport] = None,
    critic_result: Optional[CriticResult] = None,
    reliability_score_summary: Optional[ReliabilityScoreSummary] = None,
    stage_results: Optional[list[OrchestrationStageResult]] = None,
    issues: Optional[list[OrchestrationIssue]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> OrchestrationReport:
    """
    Build a normalized OrchestrationReport from provided components.

    Normalizes status/recommendation from nested outputs via model_validator.
    Does not mutate inputs.
    """
    return OrchestrationReport(
        orchestration_id=orchestration_id,
        as_of=as_of,
        mode=input_bundle.mode,
        input_bundle_id=input_bundle.bundle_id,
        stage_results=list(stage_results) if stage_results else [],
        validation_aggregate=validation_aggregate,
        staleness_report=staleness_report,
        critic_result=critic_result,
        reliability_score_summary=reliability_score_summary,
        issues=list(issues) if issues else [],
        metadata=dict(metadata) if metadata else {},
    )


# ---------------------------------------------------------------------------
# Helper 10: run_validated_orchestration
# ---------------------------------------------------------------------------

def run_validated_orchestration(
    input_bundle: OrchestrationInputBundle,
) -> OrchestrationReport:
    """
    End-to-end deterministic orchestration skeleton.

    Pipeline:
        1. input_collection
        2. evidence_registration
        3. agent_result (use provided or build mock)
        4. validation
        5. validation_aggregation
        6. staleness
        7. critic
        8. synthesis (build report)

    Behavior:
        - Does not call external APIs.
        - Does not import live/app modules.
        - Does not call LLM.
        - Does not mutate input_bundle.
        - Catches expected local errors and converts to OrchestrationIssue.
        - Uses a temporary directory for the EvidenceStore; cleaned up on return.
    """
    as_of = input_bundle.as_of
    stage_results: list[OrchestrationStageResult] = []
    top_issues: list[OrchestrationIssue] = []

    # Computed artifacts (populated per stage)
    agent_result: Optional[AgentResult] = None
    validation_report: Optional[ValidationReport] = None
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None

    # -------------------------------------------------------------------------
    # Stage 1: input_collection
    # -------------------------------------------------------------------------
    _s1_start = _utcnow()
    s1_issues: list[OrchestrationIssue] = []

    if not input_bundle.tool_results and input_bundle.agent_result is None:
        s1_issues.append(OrchestrationIssue(
            issue_id=make_orchestration_issue_id(
                "missing_input", "input_collection",
                "No tool_results and no agent_result in input bundle.",
            ),
            issue_type="missing_input",
            stage="input_collection",
            severity="warning",
            message="No tool_results and no agent_result in input bundle; mock will be used.",
        ))

    stage_results.append(OrchestrationStageResult(
        stage="input_collection",
        status="pass",
        started_at=_s1_start,
        completed_at=_utcnow(),
        summary=(
            f"Input bundle '{input_bundle.bundle_id}' received; "
            f"{len(input_bundle.tool_results)} tool_result(s)."
        ),
        issues=s1_issues,
    ))

    # -------------------------------------------------------------------------
    # All subsequent stages share a temporary EvidenceStore on disk.
    # The temp dir is cleaned up when the context manager exits.
    # -------------------------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="orch_phase3a_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # ---------------------------------------------------------------------
        # Stage 2: evidence_registration
        # ---------------------------------------------------------------------
        _s2_start = _utcnow()
        s2_issues: list[OrchestrationIssue] = []
        evidence_store: Optional[EvidenceStore] = None

        try:
            evidence_store = register_tool_results_in_evidence_store(
                input_bundle.tool_results,
                run_dir=tmp_path,
            )
            registered = len(evidence_store.evidence_ids())
            provided = len(input_bundle.tool_results)
            if registered < provided:
                s2_issues.append(OrchestrationIssue(
                    issue_id=make_orchestration_issue_id(
                        "evidence_error", "evidence_registration",
                        f"Duplicate evidence IDs: {provided - registered} skipped.",
                    ),
                    issue_type="evidence_error",
                    stage="evidence_registration",
                    severity="warning",
                    message=(
                        f"Duplicate evidence IDs: {provided - registered} of "
                        f"{provided} tool_result(s) skipped."
                    ),
                ))
            s2_status: OrchestrationStatus = "pass"
        except Exception as exc:
            s2_issues.append(OrchestrationIssue(
                issue_id=make_orchestration_issue_id(
                    "evidence_error", "evidence_registration", str(exc)
                ),
                issue_type="evidence_error",
                stage="evidence_registration",
                severity="critical",
                message=f"Evidence registration failed: {exc}",
            ))
            s2_status = "error"
            # Fallback: empty in-memory-equivalent store in same tmp_path
            evidence_store = EvidenceStore(tmp_path)

        stage_results.append(OrchestrationStageResult(
            stage="evidence_registration",
            status=s2_status,
            started_at=_s2_start,
            completed_at=_utcnow(),
            summary=f"Registered {len(evidence_store.evidence_ids())} tool_result(s).",
            output_ids=sorted(evidence_store.evidence_ids()),
            issues=s2_issues,
        ))

        # ---------------------------------------------------------------------
        # Stage 3: agent_result
        # ---------------------------------------------------------------------
        _s3_start = _utcnow()
        s3_issues: list[OrchestrationIssue] = []
        s3_status: OrchestrationStatus = "pass"

        try:
            if input_bundle.agent_result is not None:
                agent_result = input_bundle.agent_result
                s3_summary = f"Using provided agent_result from '{agent_result.agent_name}'."
            else:
                agent_result = build_minimal_mock_agent_result(
                    input_bundle.tool_results, as_of
                )
                s3_summary = (
                    f"Built mock agent_result from "
                    f"{len(input_bundle.tool_results)} tool_result(s)."
                )
        except Exception as exc:
            s3_issues.append(OrchestrationIssue(
                issue_id=make_orchestration_issue_id(
                    "malformed_input", "agent_result", str(exc)
                ),
                issue_type="malformed_input",
                stage="agent_result",
                severity="critical",
                message=f"Failed to build agent_result: {exc}",
            ))
            s3_status = "error"
            s3_summary = "agent_result stage failed."

        stage_results.append(OrchestrationStageResult(
            stage="agent_result",
            status=s3_status,
            started_at=_s3_start,
            completed_at=_utcnow(),
            summary=s3_summary,
            output_ids=[agent_result.run_id] if agent_result else [],
            issues=s3_issues,
        ))

        # ---------------------------------------------------------------------
        # Stage 4: validation
        # ---------------------------------------------------------------------
        _s4_start = _utcnow()
        s4_issues: list[OrchestrationIssue] = []

        if agent_result is not None:
            try:
                validation_report = run_validation_stage(agent_result, evidence_store)
                s4_status: OrchestrationStatus = (
                    "pass" if validation_report.passed else "fail"
                )
                s4_summary = (
                    f"Validation: passed={validation_report.passed}, "
                    f"{len(validation_report.issues)} issue(s)."
                )
            except Exception as exc:
                s4_issues.append(OrchestrationIssue(
                    issue_id=make_orchestration_issue_id(
                        "validation_issue", "validation", str(exc)
                    ),
                    issue_type="validation_issue",
                    stage="validation",
                    severity="critical",
                    message=f"Validation stage failed: {exc}",
                ))
                s4_status = "error"
                s4_summary = "Validation stage failed."
        else:
            s4_issues.append(OrchestrationIssue(
                issue_id=make_orchestration_issue_id(
                    "missing_input", "validation",
                    "Skipping validation: agent_result unavailable.",
                ),
                issue_type="missing_input",
                stage="validation",
                severity="warning",
                message="Skipping validation: agent_result unavailable.",
            ))
            s4_status = "pass"
            s4_summary = "Validation skipped (no agent_result)."

        stage_results.append(OrchestrationStageResult(
            stage="validation",
            status=s4_status,
            started_at=_s4_start,
            completed_at=_utcnow(),
            summary=s4_summary,
            output_ids=[validation_report.run_id] if validation_report else [],
            issues=s4_issues,
        ))

        # ---------------------------------------------------------------------
        # Stage 5: validation_aggregation
        # ---------------------------------------------------------------------
        _s5_start = _utcnow()
        s5_issues: list[OrchestrationIssue] = []

        if input_bundle.validation_aggregate is not None:
            validation_aggregate = input_bundle.validation_aggregate
            s5_status: OrchestrationStatus = "pass"
            s5_summary = (
                f"ValidationAggregate status={validation_aggregate.status!r} "
                f"(precomputed artifact used)."
            )
            s5_meta: dict[str, Any] = {"source": "precomputed"}
        elif validation_report is not None:
            try:
                validation_aggregate = run_validation_aggregation_stage(
                    validation_report
                )
                s5_status = "pass"
                s5_summary = (
                    f"ValidationAggregate status={validation_aggregate.status!r}."
                )
                s5_meta = {"source": "computed"}
            except Exception as exc:
                s5_issues.append(OrchestrationIssue(
                    issue_id=make_orchestration_issue_id(
                        "validation_issue", "validation_aggregation", str(exc)
                    ),
                    issue_type="validation_issue",
                    stage="validation_aggregation",
                    severity="critical",
                    message=f"Validation aggregation failed: {exc}",
                ))
                s5_status = "error"
                s5_summary = "Validation aggregation failed."
                s5_meta = {"source": "computed"}
        else:
            s5_status = "pass"
            s5_summary = "Validation aggregation skipped (no validation report)."
            s5_meta = {"source": "computed"}

        stage_results.append(OrchestrationStageResult(
            stage="validation_aggregation",
            status=s5_status,
            started_at=_s5_start,
            completed_at=_utcnow(),
            summary=s5_summary,
            output_ids=(
                [validation_aggregate.aggregate_id] if validation_aggregate else []
            ),
            issues=s5_issues,
            metadata=s5_meta,
        ))

        # ---------------------------------------------------------------------
        # Stage 6: staleness
        # ---------------------------------------------------------------------
        _s6_start = _utcnow()
        s6_issues: list[OrchestrationIssue] = []

        if input_bundle.staleness_report is not None:
            staleness_report = input_bundle.staleness_report
            s6_status: OrchestrationStatus = "pass"
            s6_summary = (
                f"StalenessReport status={staleness_report.status!r} "
                f"(precomputed artifact used)."
            )
            s6_meta: dict[str, Any] = {"source": "precomputed"}
        else:
            try:
                staleness_report = run_staleness_stage(input_bundle.tool_results, as_of)
                s6_status = "pass"
                s6_summary = f"StalenessReport status={staleness_report.status!r}."
                s6_meta = {"source": "computed"}
            except Exception as exc:
                s6_issues.append(OrchestrationIssue(
                    issue_id=make_orchestration_issue_id(
                        "stale_data", "staleness", str(exc)
                    ),
                    issue_type="stale_data",
                    stage="staleness",
                    severity="warning",
                    message=f"Staleness stage error: {exc}",
                ))
                s6_status = "pass"
                s6_summary = "Staleness stage encountered an error; continuing."
                s6_meta = {"source": "computed"}

        stage_results.append(OrchestrationStageResult(
            stage="staleness",
            status=s6_status,
            started_at=_s6_start,
            completed_at=_utcnow(),
            summary=s6_summary,
            output_ids=[staleness_report.report_id] if staleness_report else [],
            issues=s6_issues,
            metadata=s6_meta,
        ))

        # ---------------------------------------------------------------------
        # Stage 7: critic
        # ---------------------------------------------------------------------
        _s7_start = _utcnow()
        s7_issues: list[OrchestrationIssue] = []

        if input_bundle.critic_result is not None:
            critic_result = input_bundle.critic_result
            s7_status: OrchestrationStatus = "pass"
            s7_summary = (
                f"CriticResult status={critic_result.status!r}, "
                f"{len(critic_result.issues)} issue(s) "
                f"(precomputed artifact used)."
            )
            s7_meta: dict[str, Any] = {"source": "precomputed"}
        else:
            try:
                critic_result = run_critic_stage(
                    agent_result=agent_result,
                    validation_aggregate=validation_aggregate,
                    staleness_report=staleness_report,
                    as_of=as_of,
                )
                s7_status = "pass"
                s7_summary = (
                    f"CriticResult status={critic_result.status!r}, "
                    f"{len(critic_result.issues)} issue(s)."
                )
                s7_meta = {"source": "computed"}
            except Exception as exc:
                s7_issues.append(OrchestrationIssue(
                    issue_id=make_orchestration_issue_id(
                        "critic_issue", "critic", str(exc)
                    ),
                    issue_type="critic_issue",
                    stage="critic",
                    severity="warning",
                    message=f"Critic stage error: {exc}",
                ))
                s7_status = "pass"
                s7_summary = "Critic stage encountered an error; continuing."
                s7_meta = {"source": "computed"}

        stage_results.append(OrchestrationStageResult(
            stage="critic",
            status=s7_status,
            started_at=_s7_start,
            completed_at=_utcnow(),
            summary=s7_summary,
            output_ids=[critic_result.critic_id] if critic_result else [],
            issues=s7_issues,
            metadata=s7_meta,
        ))

        # ---------------------------------------------------------------------
        # Stage 8: synthesis
        # ---------------------------------------------------------------------
        _s8_start = _utcnow()
        orchestration_id = make_orchestration_id(
            bundle_id=input_bundle.bundle_id,
            as_of=as_of,
            mode=str(input_bundle.mode),
        )

        stage_results.append(OrchestrationStageResult(
            stage="synthesis",
            status="pass",
            started_at=_s8_start,
            completed_at=_utcnow(),
            summary="OrchestrationReport assembled successfully.",
        ))

        report = build_orchestration_report(
            orchestration_id=orchestration_id,
            as_of=as_of,
            input_bundle=input_bundle,
            validation_aggregate=validation_aggregate,
            staleness_report=staleness_report,
            critic_result=critic_result,
            reliability_score_summary=input_bundle.reliability_score_summary,
            stage_results=stage_results,
            issues=top_issues,
        )

    return report


# ---------------------------------------------------------------------------
# Helper 11: orchestration_report_tool_result_from_report
# ---------------------------------------------------------------------------

def orchestration_report_tool_result_from_report(
    run_id: str,
    report: OrchestrationReport,
    target: str = "orchestration",
    calculation_version: str = "validated_orchestration_skeleton_v1",
) -> ToolResult:
    """
    Wrap an OrchestrationReport as a ToolResult for evidence auditability.

    Behavior:
        - tool_name = "orchestration_report" (stable).
        - evidence_id is deterministic for same run_id + (orchestration_id, as_of,
          mode, target, calculation_version); stage timestamps are excluded from
          the ID payload to preserve cross-run determinism.
        - payload["report"] contains the full serialized OrchestrationReport.
        - payload["summary"] contains the compact summarize_orchestration_report() dict.
        - payload["calculation_version"] is the version tag.
        - Does not mutate report.
        - Does not fake evidence.
    """
    # Stable ID payload: only deterministic fields; excludes stage timestamps
    # so the evidence_id remains consistent across repeated runs on same inputs.
    _stable_id_payload = {
        "orchestration_id": report.orchestration_id,
        "as_of": report.as_of,
        "mode": report.mode,
        "target": target,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_ORCH_TOOL_NAME,
        target=target,
        metric_group=_ORCH_METRIC_GROUP,
        payload=_stable_id_payload,
    )

    payload: dict[str, Any] = {
        "report": report.model_dump(mode="json"),
        "summary": summarize_orchestration_report(report),
        "calculation_version": calculation_version,
    }

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_ORCH_TOOL_NAME,
        run_id=run_id,
        inputs={
            "orchestration_id": report.orchestration_id,
            "as_of": report.as_of,
            "mode": report.mode,
            "target": target,
            "calculation_version": calculation_version,
        },
        outputs=payload,
        description=(
            f"OrchestrationReport {report.orchestration_id!r}"
            f" as_of={report.as_of!r}"
            f" status={report.status!r}"
            f" recommendation={report.recommendation!r}"
        ),
    )


# ---------------------------------------------------------------------------
# Helper 12: summarize_orchestration_report
# ---------------------------------------------------------------------------

def summarize_orchestration_report(report: OrchestrationReport) -> dict[str, Any]:
    """
    Return a concise summary dict of an OrchestrationReport.

    Keys: orchestration_id, status, recommendation, mode, stage_count,
    issue_count, critical_count, warning_count, info_count,
    validation_status, staleness_status, critic_status, top_messages.
    """
    all_issues: list[OrchestrationIssue] = list(report.issues)
    for sr in report.stage_results:
        all_issues.extend(sr.issues)

    critical_count = sum(1 for i in all_issues if i.severity == "critical")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    info_count = sum(1 for i in all_issues if i.severity == "info")
    top_messages = [i.message for i in all_issues[:10]]

    return {
        "orchestration_id": report.orchestration_id,
        "status": report.status,
        "recommendation": report.recommendation,
        "mode": report.mode,
        "stage_count": len(report.stage_results),
        "issue_count": len(all_issues),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "validation_status": (
            report.validation_aggregate.status
            if report.validation_aggregate is not None
            else None
        ),
        "staleness_status": (
            report.staleness_report.status
            if report.staleness_report is not None
            else None
        ),
        "critic_status": (
            report.critic_result.status
            if report.critic_result is not None
            else None
        ),
        "top_messages": top_messages,
    }
