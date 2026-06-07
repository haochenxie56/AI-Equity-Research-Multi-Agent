"""
lib/reliability/critic.py

Standalone Critic Agent v0.1 foundation for Phase 2J.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no file I/O.
  - Deterministic structural critique of AgentResult-like outputs and
    validation/staleness summaries.
  - Does NOT call Claude API or any external LLM.
  - Does NOT wire into live app, live workflow, or live LLM calls.
  - Does NOT fetch real data.
  - Critic flags risks; it does not fabricate data.
  - Critic consumes evidence summaries, not raw unsupported assumptions.
  - Critic does not replace validators.
  - Critic does not refresh stale data.

See docs/reliability_phase_2j_critic_agent_v0_1.md for full design.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import AgentResult, ToolResult
from lib.reliability.staleness import (
    StalenessFinding,
    StalenessReport,
)
from lib.reliability.validation_aggregator import (
    AggregatedValidationItem,
    ValidationAggregate,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

CriticIssueType = Literal[
    "unsupported_claim",
    "weak_evidence",
    "stale_evidence",
    "validation_failure",
    "missing_risk",
    "missing_assumption",
    "overconfidence",
    "conflicting_evidence",
    "numeric_claim_issue",
    "scope_violation",
    "safety_concern",
    "other",
]

CriticSeverity = Literal["critical", "warning", "info"]

CriticStatus = Literal["pass", "pass_with_warnings", "fail", "unknown"]

CriticTargetType = Literal[
    "agent_result",
    "finding",
    "assumption",
    "risk",
    "evidence_ref",
    "validation_aggregate",
    "staleness_report",
    "tool_result",
    "unknown",
]

CriticRecommendation = Literal[
    "accept",
    "revise",
    "reject",
    "needs_more_evidence",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_CRITIC_TOOL_NAME: str = "critic_result"
_CRITIC_METRIC_GROUP: str = "critic_result"

# Map ValidationItemType → CriticIssueType
_VALIDATION_TYPE_TO_CRITIC_ISSUE: dict[str, str] = {
    "schema": "validation_failure",
    "evidence_binding": "weak_evidence",
    "missing_data": "weak_evidence",
    "stale_data": "stale_evidence",
    "duplicate_data": "other",
    "mismatch": "conflicting_evidence",
    "risk_limit": "validation_failure",
    "unsupported": "unsupported_claim",
    "calculation": "validation_failure",
    "provenance": "weak_evidence",
    "safety": "safety_concern",
    "other": "validation_failure",
}

# Map StalenessStatus → CriticIssueType
_STALENESS_STATUS_TO_CRITIC_ISSUE: dict[str, str] = {
    "fresh": "other",
    "near_stale": "stale_evidence",
    "stale": "stale_evidence",
    "expired": "stale_evidence",
    "unknown": "weak_evidence",
}

# Map ValidationSeverity / StalenessSeverity → CriticSeverity (pass-through)
_SEVERITY_MAP: dict[str, str] = {
    "critical": "critical",
    "warning": "warning",
    "info": "info",
}

# Basic pattern for numeric-looking content in finding text
_NUMERIC_PATTERN = re.compile(r"\b\d{3,}|\b\d+\.?\d*\s*%")


# ---------------------------------------------------------------------------
# 1. CriticIssue
# ---------------------------------------------------------------------------

class CriticIssue(BaseModel):
    """
    One structured issue raised by the critic.

    Fields:
        issue_id:                     Deterministic unique identifier.
        issue_type:                   Classification of the critic issue.
        severity:                     Severity level (default ``"warning"``).
        target_type:                  Type of object being critiqued.
        message:                      Non-empty human-readable description.
        target_id:                    Optional ID of the target object.
        evidence_id:                  Optional associated evidence_id.
        field_path:                   Optional dot-notation path in the source.
        related_validation_item_id:   Optional link to AggregatedValidationItem.
        related_staleness_finding_id: Optional link to StalenessFinding.
        recommendation:               Recommended action (default ``"revise"``).
        metadata:                     Arbitrary key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1)
    issue_type: CriticIssueType
    severity: CriticSeverity = "warning"
    target_type: CriticTargetType = "unknown"
    message: str = Field(min_length=1)
    target_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    related_validation_item_id: Optional[str] = None
    related_staleness_finding_id: Optional[str] = None
    recommendation: CriticRecommendation = "revise"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "CriticIssue":
        for field_name in ("issue_id", "message"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 2. CriticResult
# ---------------------------------------------------------------------------

class CriticResult(BaseModel):
    """
    Structured result from the critic.

    Fields:
        critic_id:       Non-empty unique identifier for this critic run.
        schema_version:  Schema version string.
        as_of:           Non-empty reference date/datetime string.
        status:          Overall critic status (auto-normalised from issues).
        recommendation:  Overall recommendation (auto-normalised from issues).
        issues:          All critic issues (de-duplicated by issue_id, first wins).
        critical_count:  Count of critical issues (auto-normalised).
        warning_count:   Count of warning issues (auto-normalised).
        info_count:      Count of info issues (auto-normalised).
        metadata:        Arbitrary key/value metadata.

    Normalisation (applied by model_validator after construction):
        - Issues de-duplicated by issue_id (first-occurrence wins).
        - critical_count, warning_count, info_count recomputed from issues.
        - status:
            - ``"fail"``               if any critical issue present
            - ``"pass_with_warnings"`` if any warning issue present (no criticals)
            - ``"pass"``               otherwise (including empty issues list)
        - recommendation:
            - ``"reject"``            if any critical issue present
            - ``"revise"``            if any warning issue present (no criticals)
            - ``"accept"``            if no critical or warning issues
    """

    model_config = ConfigDict(extra="forbid")

    critic_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    status: CriticStatus = "unknown"
    recommendation: CriticRecommendation = "unknown"
    issues: list[CriticIssue] = Field(default_factory=list)
    critical_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    info_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "CriticResult":
        for field_name in ("critic_id", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self

    @model_validator(mode="after")
    def _normalize_derived_fields(self) -> "CriticResult":
        """De-duplicate issues by issue_id, then recompute counts, status, recommendation."""
        seen: dict[str, CriticIssue] = {}
        for issue in self.issues:
            if issue.issue_id not in seen:
                seen[issue.issue_id] = issue
        deduped = list(seen.values())
        self.issues = deduped

        self.critical_count = sum(1 for i in deduped if i.severity == "critical")
        self.warning_count = sum(1 for i in deduped if i.severity == "warning")
        self.info_count = sum(1 for i in deduped if i.severity == "info")

        if self.critical_count > 0:
            self.status = "fail"
            self.recommendation = "reject"
        elif self.warning_count > 0:
            self.status = "pass_with_warnings"
            self.recommendation = "revise"
        else:
            self.status = "pass"
            self.recommendation = "accept"

        return self


# ---------------------------------------------------------------------------
# Helper 1: make_critic_issue_id
# ---------------------------------------------------------------------------

def make_critic_issue_id(
    issue_type: str,
    message: str,
    target_id: Optional[str] = None,
    evidence_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> str:
    """
    Build a deterministic, stable issue_id for a CriticIssue.

    Same inputs always produce the same ID.
    Different message, target_id, evidence_id, or field_path produces a
    different ID.

    Args:
        issue_type:  CriticIssueType string used as prefix.
        message:     Issue message text.
        target_id:   Optional target object identifier.
        evidence_id: Optional associated evidence identifier.
        field_path:  Optional dot-notation field path.

    Returns:
        Short deterministic hex string in the form ``"{issue_type}:{hash}"``.

    Examples::

        make_critic_issue_id("weak_evidence", "No refs found.")
        # → "weak_evidence:3a9f0b..."

        make_critic_issue_id("weak_evidence", "No refs found.")
        # → same ID (deterministic)

        make_critic_issue_id("weak_evidence", "Different message.")
        # → different ID
    """
    payload = {
        "issue_type": issue_type,
        "message": message,
        "target_id": target_id or "",
        "evidence_id": evidence_id or "",
        "field_path": field_path or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    return f"{issue_type}:{hash_suffix}"


# ---------------------------------------------------------------------------
# Helper 2: critic_issue_from_validation_item
# ---------------------------------------------------------------------------

def critic_issue_from_validation_item(
    item: AggregatedValidationItem,
) -> CriticIssue:
    """
    Convert one AggregatedValidationItem into a CriticIssue.

    ValidationItemType → CriticIssueType mapping:
        stale_data       → stale_evidence
        evidence_binding → weak_evidence
        missing_data     → weak_evidence
        risk_limit       → validation_failure
        provenance       → weak_evidence
        safety           → safety_concern
        unsupported      → unsupported_claim
        mismatch         → conflicting_evidence
        other            → validation_failure
        schema           → validation_failure
        duplicate_data   → other
        calculation      → validation_failure

    ValidationSeverity → CriticSeverity preserved directly.

    Preserved fields:
        related_validation_item_id = item.item_id
        evidence_id                = item.evidence_id
        field_path                 = item.field_path
        target_id                  = item.object_id (if available)
    """
    issue_type: CriticIssueType = _VALIDATION_TYPE_TO_CRITIC_ISSUE.get(  # type: ignore[assignment]
        item.item_type, "validation_failure"
    )
    severity: CriticSeverity = _SEVERITY_MAP.get(item.severity, "warning")  # type: ignore[assignment]

    recommendation: CriticRecommendation
    if severity == "critical":
        recommendation = "reject"
    elif severity == "warning":
        recommendation = "revise"
    else:
        recommendation = "needs_more_evidence"

    issue_id = make_critic_issue_id(
        issue_type=issue_type,
        message=item.message,
        target_id=item.object_id,
        evidence_id=item.evidence_id,
        field_path=item.field_path,
    )

    return CriticIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        severity=severity,
        target_type="validation_aggregate",
        message=item.message,
        target_id=item.object_id,
        evidence_id=item.evidence_id,
        field_path=item.field_path,
        related_validation_item_id=item.item_id,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Helper 3: critic_issue_from_staleness_finding
# ---------------------------------------------------------------------------

def critic_issue_from_staleness_finding(
    finding: StalenessFinding,
) -> CriticIssue:
    """
    Convert one StalenessFinding into a CriticIssue.

    StalenessStatus → CriticIssueType:
        expired / stale → stale_evidence
        near_stale      → stale_evidence (with at-least-warning severity)
        unknown         → weak_evidence
        fresh           → other (info; caller may filter out)

    Severity:
        near_stale findings are raised at "warning" or higher
        (overrides "info" from the staleness policy).
        All other statuses preserve the finding severity directly.

    Preserved fields:
        related_staleness_finding_id = finding.finding_id
        evidence_id                  = finding.evidence_id
        field_path                   = finding.field_path
        target_id                    = finding.object_id (if available)
    """
    issue_type: CriticIssueType = _STALENESS_STATUS_TO_CRITIC_ISSUE.get(  # type: ignore[assignment]
        finding.status, "stale_evidence"
    )
    severity: CriticSeverity = _SEVERITY_MAP.get(finding.severity, "warning")  # type: ignore[assignment]

    # Near-stale findings should surface as at least a warning in the critic
    if finding.status == "near_stale" and severity == "info":
        severity = "warning"

    recommendation: CriticRecommendation
    if severity == "critical":
        recommendation = "reject"
    elif severity == "warning":
        recommendation = "revise"
    else:
        recommendation = "needs_more_evidence"

    issue_id = make_critic_issue_id(
        issue_type=issue_type,
        message=finding.message,
        target_id=finding.object_id,
        evidence_id=finding.evidence_id,
        field_path=finding.field_path,
    )

    return CriticIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        severity=severity,
        target_type="staleness_report",
        message=finding.message,
        target_id=finding.object_id,
        evidence_id=finding.evidence_id,
        field_path=finding.field_path,
        related_staleness_finding_id=finding.finding_id,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Helper 4: critique_validation_aggregate
# ---------------------------------------------------------------------------

def critique_validation_aggregate(
    validation_aggregate: ValidationAggregate,
) -> list[CriticIssue]:
    """
    Convert every AggregatedValidationItem in a ValidationAggregate to CriticIssues.

    Does not mutate validation_aggregate.

    Args:
        validation_aggregate: ValidationAggregate to convert.

    Returns:
        List of CriticIssues, one per item in validation_aggregate.items.
    """
    return [
        critic_issue_from_validation_item(item)
        for item in validation_aggregate.items
    ]


# ---------------------------------------------------------------------------
# Helper 5: critique_staleness_report
# ---------------------------------------------------------------------------

def critique_staleness_report(staleness_report: StalenessReport) -> list[CriticIssue]:
    """
    Convert every StalenessFinding in a StalenessReport to CriticIssues.

    Does not mutate staleness_report.

    Args:
        staleness_report: StalenessReport to convert.

    Returns:
        List of CriticIssues, one per finding in staleness_report.findings.
    """
    return [
        critic_issue_from_staleness_finding(finding)
        for finding in staleness_report.findings
    ]


# ---------------------------------------------------------------------------
# Helper 6: critique_agent_result_structure
# ---------------------------------------------------------------------------

def critique_agent_result_structure(agent_result: AgentResult) -> list[CriticIssue]:
    """
    Deterministic structural critique of an AgentResult.  No LLM.

    Warns for:
        - No findings in the agent result.
        - Any finding with no evidence_refs.
        - Risk list is empty.
        - Assumption list is empty.
        - High confidence declared while total evidence refs across all findings < 2.
        - Numeric-looking claim in a finding that has no evidence_refs.
        - Duplicate finding messages.

    Does NOT:
        - Modify the AgentResult schema.
        - Call validate_agent_result().
        - Require an EvidenceStore.
        - Mutate agent_result.

    Args:
        agent_result: AgentResult to structurally inspect.

    Returns:
        List of CriticIssues (may be empty if no structural problems found).
    """
    issues: list[CriticIssue] = []
    agent_name = agent_result.agent_name

    def _add(
        issue_type: CriticIssueType,
        severity: CriticSeverity,
        message: str,
        target_type: CriticTargetType = "agent_result",
        target_id: Optional[str] = None,
        field_path: Optional[str] = None,
    ) -> None:
        issue_id = make_critic_issue_id(
            issue_type=issue_type,
            message=message,
            target_id=target_id,
            field_path=field_path,
        )
        issues.append(
            CriticIssue(
                issue_id=issue_id,
                issue_type=issue_type,
                severity=severity,
                target_type=target_type,
                message=message,
                target_id=target_id,
                field_path=field_path,
            )
        )

    # No findings
    if not agent_result.findings:
        _add(
            issue_type="missing_assumption",
            severity="warning",
            message=f"Agent '{agent_name}' has no findings.",
            target_id=agent_name,
            field_path="findings",
        )

    # Findings with no evidence_refs
    for idx, finding in enumerate(agent_result.findings):
        if not finding.evidence:
            _add(
                issue_type="weak_evidence",
                severity="warning",
                message=(
                    f"Finding {idx} in agent '{agent_name}' has no evidence_refs: "
                    f"{finding.text[:80]!r}"
                ),
                target_type="finding",
                target_id=agent_name,
                field_path=f"findings.{idx}.evidence",
            )

    # Empty risks
    if not agent_result.risks:
        _add(
            issue_type="missing_risk",
            severity="warning",
            message=f"Agent '{agent_name}' has no risks declared.",
            target_id=agent_name,
            field_path="risks",
        )

    # Empty assumptions
    if not agent_result.assumptions:
        _add(
            issue_type="missing_assumption",
            severity="warning",
            message=f"Agent '{agent_name}' has no assumptions declared.",
            target_id=agent_name,
            field_path="assumptions",
        )

    # High confidence with sparse evidence (< 2 evidence refs total)
    total_evidence = sum(len(f.evidence) for f in agent_result.findings)
    confidence = agent_result.confidence
    if confidence is not None and confidence.level == "high" and total_evidence < 2:
        _add(
            issue_type="overconfidence",
            severity="warning",
            message=(
                f"Agent '{agent_name}' declares high confidence but has only "
                f"{total_evidence} evidence reference(s) across all findings."
            ),
            target_id=agent_name,
            field_path="confidence",
        )

    # Numeric-looking claims without evidence_refs
    for idx, finding in enumerate(agent_result.findings):
        if not finding.evidence and _NUMERIC_PATTERN.search(finding.text):
            _add(
                issue_type="numeric_claim_issue",
                severity="warning",
                message=(
                    f"Finding {idx} in agent '{agent_name}' contains a numeric "
                    f"claim but has no evidence_refs: {finding.text[:80]!r}"
                ),
                target_type="finding",
                target_id=agent_name,
                field_path=f"findings.{idx}.text",
            )

    # Duplicate finding messages
    seen_texts: set[str] = set()
    for idx, finding in enumerate(agent_result.findings):
        if finding.text in seen_texts:
            _add(
                issue_type="conflicting_evidence",
                severity="info",
                message=(
                    f"Agent '{agent_name}' has a duplicate finding message at "
                    f"index {idx}: {finding.text[:80]!r}"
                ),
                target_type="finding",
                target_id=agent_name,
                field_path=f"findings.{idx}.text",
            )
        seen_texts.add(finding.text)

    return issues


# ---------------------------------------------------------------------------
# Helper 7: detect_overconfidence
# ---------------------------------------------------------------------------

def detect_overconfidence(
    agent_result: AgentResult,
    validation_aggregate: Optional[ValidationAggregate] = None,
    staleness_report: Optional[StalenessReport] = None,
) -> list[CriticIssue]:
    """
    Flag overconfidence when high agent confidence conflicts with validation
    or staleness problems.

    Rules:
        - Returns [] if agent_result has no confidence declared.
        - Returns [] if confidence level is not ``"high"``.
        - If validation_aggregate status is ``"fail"``:
            → critical overconfidence issue.
        - If validation_aggregate status is ``"pass_with_warnings"``:
            → warning overconfidence issue.
        - If staleness_report status is ``"stale"`` or ``"expired"`` or
          ``"near_stale"``, and staleness critical_count > 0:
            → critical overconfidence issue.
        - If staleness_report has stale/expired/near_stale status and no
          critical findings:
            → warning overconfidence issue.
        - Does not mutate any input.

    Args:
        agent_result:         AgentResult whose confidence is inspected.
        validation_aggregate: Optional ValidationAggregate to check against.
        staleness_report:     Optional StalenessReport to check against.

    Returns:
        List of CriticIssues (may be empty).
    """
    issues: list[CriticIssue] = []
    confidence = agent_result.confidence
    if confidence is None or confidence.level != "high":
        return issues

    agent_name = agent_result.agent_name

    # Validation-based overconfidence
    if validation_aggregate is not None:
        va_status = validation_aggregate.status
        if va_status == "fail":
            message = (
                f"Agent '{agent_name}' reports high confidence but "
                f"validation aggregate status is 'fail' "
                f"({validation_aggregate.critical_count} critical issue(s))."
            )
            issue_id = make_critic_issue_id(
                issue_type="overconfidence",
                message=message,
                target_id=agent_name,
                field_path="confidence",
            )
            issues.append(
                CriticIssue(
                    issue_id=issue_id,
                    issue_type="overconfidence",
                    severity="critical",
                    target_type="agent_result",
                    message=message,
                    target_id=agent_name,
                    field_path="confidence",
                    recommendation="reject",
                )
            )
        elif va_status == "pass_with_warnings":
            message = (
                f"Agent '{agent_name}' reports high confidence but "
                f"validation aggregate status is 'pass_with_warnings' "
                f"({validation_aggregate.warning_count} warning(s))."
            )
            issue_id = make_critic_issue_id(
                issue_type="overconfidence",
                message=message,
                target_id=agent_name,
                field_path="confidence",
            )
            issues.append(
                CriticIssue(
                    issue_id=issue_id,
                    issue_type="overconfidence",
                    severity="warning",
                    target_type="agent_result",
                    message=message,
                    target_id=agent_name,
                    field_path="confidence",
                    recommendation="revise",
                )
            )

    # Staleness-based overconfidence
    if staleness_report is not None:
        sr_status = staleness_report.status
        if sr_status in ("stale", "expired", "near_stale"):
            has_critical = staleness_report.critical_count > 0
            severity: CriticSeverity = "critical" if has_critical else "warning"
            recommendation: CriticRecommendation = (
                "reject" if has_critical else "revise"
            )
            message = (
                f"Agent '{agent_name}' reports high confidence but "
                f"staleness report status is '{sr_status}' "
                f"(expired={staleness_report.expired_count}, "
                f"stale={staleness_report.stale_count})."
            )
            issue_id = make_critic_issue_id(
                issue_type="overconfidence",
                message=message,
                target_id=agent_name,
                field_path="confidence",
            )
            issues.append(
                CriticIssue(
                    issue_id=issue_id,
                    issue_type="overconfidence",
                    severity=severity,
                    target_type="agent_result",
                    message=message,
                    target_id=agent_name,
                    field_path="confidence",
                    recommendation=recommendation,
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Helper 8: aggregate_critic_issues
# ---------------------------------------------------------------------------

def aggregate_critic_issues(
    critic_id: str,
    as_of: str,
    issues: list[CriticIssue],
    metadata: Optional[dict[str, Any]] = None,
) -> CriticResult:
    """
    Build a CriticResult by aggregating a list of CriticIssues.

    De-duplication by issue_id and count/status/recommendation normalisation
    are handled by the CriticResult model_validator.

    Does not mutate the input issues list.

    Args:
        critic_id: Non-empty unique identifier for this critic run.
        as_of:     Reference date/datetime string.
        issues:    List of CriticIssue objects.
        metadata:  Optional metadata dict.

    Returns:
        CriticResult with normalised counts, status, and recommendation.
    """
    return CriticResult(
        critic_id=critic_id,
        as_of=as_of,
        issues=list(issues),
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Helper 9: run_mock_critic
# ---------------------------------------------------------------------------

def run_mock_critic(
    critic_id: str,
    as_of: str,
    agent_result: Optional[AgentResult] = None,
    validation_aggregate: Optional[ValidationAggregate] = None,
    staleness_report: Optional[StalenessReport] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> CriticResult:
    """
    Run a deterministic mock critic over the provided inputs.

    No LLM.  No data fetching.  No app integration.

    Calls (only when the corresponding input is provided):
        - critique_agent_result_structure(agent_result)
        - critique_validation_aggregate(validation_aggregate)
        - critique_staleness_report(staleness_report)
        - detect_overconfidence(agent_result, validation_aggregate, staleness_report)

    Aggregates all raised issues into a single CriticResult.

    Args:
        critic_id:            Non-empty identifier for this critic run.
        as_of:                Reference date/datetime string.
        agent_result:         Optional AgentResult to structurally critique.
        validation_aggregate: Optional ValidationAggregate to convert.
        staleness_report:     Optional StalenessReport to convert.
        metadata:             Optional metadata dict.

    Returns:
        CriticResult with all issues aggregated and normalised.
    """
    all_issues: list[CriticIssue] = []

    if agent_result is not None:
        all_issues.extend(critique_agent_result_structure(agent_result))

    if validation_aggregate is not None:
        all_issues.extend(critique_validation_aggregate(validation_aggregate))

    if staleness_report is not None:
        all_issues.extend(critique_staleness_report(staleness_report))

    if agent_result is not None:
        all_issues.extend(
            detect_overconfidence(
                agent_result=agent_result,
                validation_aggregate=validation_aggregate,
                staleness_report=staleness_report,
            )
        )

    return aggregate_critic_issues(
        critic_id=critic_id,
        as_of=as_of,
        issues=all_issues,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Helper 10: critic_result_tool_result_from_result
# ---------------------------------------------------------------------------

def critic_result_tool_result_from_result(
    run_id: str,
    critic_result: CriticResult,
    target: str = "critic",
    calculation_version: str = "critic_v0_1",
) -> ToolResult:
    """
    Wrap a CriticResult as a ToolResult for auditability.

    The tool_name is always ``"critic_result"``.
    The evidence_id is deterministic: same run_id + same critic_result
    payload always produces the same evidence_id.

    Does not mutate critic_result.
    Does not fake evidence.
    Does not loosen the ToolResult schema.

    Args:
        run_id:              Non-empty run identifier.
        critic_result:       CriticResult to wrap.
        target:              Target label (default ``"critic"``).
        calculation_version: Version tag for this critic algorithm.

    Returns:
        ToolResult with critic data in outputs.
    """
    payload: dict[str, Any] = {
        "critic_id": critic_result.critic_id,
        "schema_version": critic_result.schema_version,
        "as_of": critic_result.as_of,
        "status": critic_result.status,
        "recommendation": critic_result.recommendation,
        "issues": [issue.model_dump() for issue in critic_result.issues],
        "critical_count": critic_result.critical_count,
        "warning_count": critic_result.warning_count,
        "info_count": critic_result.info_count,
        "metadata": critic_result.metadata,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_CRITIC_TOOL_NAME,
        target=target,
        metric_group=_CRITIC_METRIC_GROUP,
        payload=payload,
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_CRITIC_TOOL_NAME,
        run_id=run_id,
        schema_version="0.1",
        inputs={
            "critic_id": critic_result.critic_id,
            "as_of": critic_result.as_of,
            "calculation_version": calculation_version,
        },
        outputs=payload,
        description=(
            f"CriticResult for critic_id={critic_result.critic_id!r}; "
            f"status={critic_result.status!r}."
        ),
    )


# ---------------------------------------------------------------------------
# Helper 11: summarize_critic_result
# ---------------------------------------------------------------------------

def summarize_critic_result(result: CriticResult) -> dict[str, Any]:
    """
    Return a concise summary dict for a CriticResult.

    Args:
        result: CriticResult to summarise.

    Returns:
        dict with keys:
            - critic_id
            - status
            - recommendation
            - total_issues
            - critical_count
            - warning_count
            - info_count
            - issue_types_present  (sorted list of unique CriticIssueType values)
            - top_messages         (list of first 10 issue messages)
    """
    issue_types_present = sorted(set(issue.issue_type for issue in result.issues))
    top_messages = [issue.message for issue in result.issues[:10]]

    return {
        "critic_id": result.critic_id,
        "status": result.status,
        "recommendation": result.recommendation,
        "total_issues": len(result.issues),
        "critical_count": result.critical_count,
        "warning_count": result.warning_count,
        "info_count": result.info_count,
        "issue_types_present": issue_types_present,
        "top_messages": top_messages,
    }
