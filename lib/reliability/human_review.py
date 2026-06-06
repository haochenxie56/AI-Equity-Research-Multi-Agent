"""
lib/reliability/human_review.py

Phase 3F: Human Review / Feedback Schema Skeleton.

Design principles:
  - Standalone, deterministic, offline.
  - No live LLM calls, no live data fetching, no app integration.
  - Consumes DecisionPacket, DebateReport, HorizonSynthesisReport,
    MacroAgentResult, ValidationAggregate, StalenessReport, CriticResult,
    ReliabilityScoreSummary, and ToolResult evidence artifacts.
  - Produces structured review records, feedback items, revision requests,
    and review reports for human analyst consumption.
  - All normalization is rule-based; no free-form LLM reasoning.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell/order instructions, or
    individual security recommendations.
  - Does NOT authorize execution. approved_for_execution is always False.
  - Mock/dry-run only; all outputs are explicitly evidence-aware.

See docs/reliability_phase_3f_human_review_feedback_skeleton.md for design.

Disclaimer: All outputs are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.critic import CriticIssue, CriticResult
from lib.reliability.evaluation import ReliabilityScoreSummary
from lib.reliability.schemas import ToolResult
from lib.reliability.staleness import StalenessFinding, StalenessReport
from lib.reliability.validation_aggregator import (
    AggregatedValidationItem,
    ValidationAggregate,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Literal type aliases (enums)
# ---------------------------------------------------------------------------

HumanReviewStatus = Literal[
    "pending",
    "in_review",
    "approved_for_research_only",
    "changes_requested",
    "rejected",
    "blocked",
    "unknown",
]

HumanReviewDecision = Literal[
    "approve_for_research",
    "request_revision",
    "reject",
    "block",
    "defer",
    "unknown",
]

HumanFeedbackType = Literal[
    "evidence_gap",
    "stale_data",
    "unsupported_claim",
    "missing_risk",
    "missing_assumption",
    "conflicting_evidence",
    "unclear_rationale",
    "excessive_confidence",
    "wording_change",
    "scope_violation",
    "safety_concern",
    "other",
]

HumanFeedbackSeverity = Literal["critical", "warning", "info"]

HumanReviewerRole = Literal[
    "analyst",
    "portfolio_manager",
    "risk_reviewer",
    "compliance_reviewer",
    "system_reviewer",
    "unknown",
]

HumanReviewSourceType = Literal[
    "decision_packet",
    "debate",
    "horizon_synthesis",
    "macro_agent",
    "validation",
    "staleness",
    "critic",
    "evaluation",
    "manual",
    "unknown",
]

HumanReviewRecommendation = Literal[
    "accept_for_research",
    "revise",
    "reject",
    "block",
    "needs_more_evidence",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_HUMAN_REVIEW_TOOL_NAME: str = "human_review_report"
_HUMAN_REVIEW_METRIC_GROUP: str = "human_review_report"

# DecisionGuardrailType → HumanFeedbackType
_GUARDRAIL_TYPE_TO_FEEDBACK_TYPE: dict[str, str] = {
    "insufficient_evidence": "evidence_gap",
    "stale_data": "stale_data",
    "validation_failure": "unsupported_claim",
    "critic_blocker": "unsupported_claim",
    "debate_unresolved": "unclear_rationale",
    "missing_risk": "missing_risk",
    "missing_assumption": "missing_assumption",
    "conflicting_evidence": "conflicting_evidence",
    "overconfidence": "excessive_confidence",
    "execution_forbidden": "safety_concern",
    "human_review_required": "safety_concern",
    "other": "other",
}

# ValidationItemType → HumanFeedbackType
_VALIDATION_TYPE_TO_FEEDBACK_TYPE: dict[str, str] = {
    "schema": "unsupported_claim",
    "evidence_binding": "evidence_gap",
    "missing_data": "evidence_gap",
    "stale_data": "stale_data",
    "duplicate_data": "other",
    "mismatch": "conflicting_evidence",
    "risk_limit": "missing_risk",
    "unsupported": "unsupported_claim",
    "calculation": "unsupported_claim",
    "provenance": "evidence_gap",
    "safety": "safety_concern",
    "other": "other",
}

# StalenessStatus → HumanFeedbackType
_STALENESS_STATUS_TO_FEEDBACK_TYPE: dict[str, str] = {
    "fresh": "other",
    "near_stale": "stale_data",
    "stale": "stale_data",
    "expired": "stale_data",
    "unknown": "evidence_gap",
}

# CriticIssueType → HumanFeedbackType
_CRITIC_TYPE_TO_FEEDBACK_TYPE: dict[str, str] = {
    "missing_risk": "missing_risk",
    "missing_assumption": "missing_assumption",
    "conflicting_evidence": "conflicting_evidence",
    "stale_evidence": "stale_data",
    "unsupported_claim": "unsupported_claim",
    "overconfidence": "excessive_confidence",
    "weak_evidence": "evidence_gap",
    "validation_failure": "unsupported_claim",
    "numeric_claim_issue": "unsupported_claim",
    "scope_violation": "scope_violation",
    "safety_concern": "safety_concern",
    "other": "other",
}

# HumanFeedbackType → revision request description template
_FEEDBACK_TYPE_TO_REVISION_REASON: dict[str, str] = {
    "evidence_gap": "Evidence gap detected — additional supporting evidence is required.",
    "stale_data": "Stale data detected — freshness check and data refresh are required.",
    "unsupported_claim": "Unsupported claim detected — evidence binding correction is required.",
    "missing_risk": "Missing risk detected — risk section must be updated.",
    "missing_assumption": "Missing assumption detected — assumption section must be updated.",
    "conflicting_evidence": "Conflicting evidence detected — resolution of contradictions is required.",
    "unclear_rationale": "Unclear rationale detected — rationale must be clarified.",
    "excessive_confidence": "Excessive confidence detected — confidence calibration is required.",
    "wording_change": "Wording change requested.",
    "scope_violation": "Scope violation detected — content must be brought within research scope.",
    "safety_concern": "Safety concern detected — compliance review is required.",
    "other": "Review issue detected — please address feedback before proceeding.",
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class HumanFeedbackItem(BaseModel):
    """
    One structured feedback item raised during human review.

    Feedback items surface evidence gaps, stale data, unsupported claims,
    missing risks/assumptions, and other review concerns for analyst attention.
    No execution approval language is permitted.
    """

    model_config = ConfigDict(extra="forbid")

    feedback_id: str = Field(min_length=1)
    feedback_type: HumanFeedbackType
    severity: HumanFeedbackSeverity = "warning"
    reviewer_role: HumanReviewerRole = "unknown"
    message: str = Field(min_length=1)
    source_type: HumanReviewSourceType = "unknown"
    related_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    suggested_change: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "HumanFeedbackItem":
        for fn in ("feedback_id", "message"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class HumanRevisionRequest(BaseModel):
    """
    A structured request for revision of a reviewed artifact.

    Revision requests aggregate feedback items into actionable change
    requirements. They do not authorize execution.
    """

    model_config = ConfigDict(extra="forbid")

    revision_request_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    required: bool = True
    source_feedback_ids: list[str] = Field(default_factory=list)
    requested_changes: list[str] = Field(default_factory=list)
    blocked_until_resolved: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "HumanRevisionRequest":
        for fn in ("revision_request_id", "reason"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class HumanReviewItem(BaseModel):
    """
    One review item covering a source artifact or aspect of a DecisionPacket.

    Review items group feedback and revision requests for a specific source
    (e.g., decision packet, debate report, horizon synthesis).
    """

    model_config = ConfigDict(extra="forbid")

    review_item_id: str = Field(min_length=1)
    source_type: HumanReviewSourceType
    source_id: Optional[str] = None
    status: HumanReviewStatus = "pending"
    summary: str = Field(min_length=1)
    feedback_items: list[HumanFeedbackItem] = Field(default_factory=list)
    revision_requests: list[HumanRevisionRequest] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "HumanReviewItem":
        for fn in ("review_item_id", "summary"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class HumanReviewOutcome(BaseModel):
    """
    Structured outcome from a human review pass.

    Outcomes record the reviewer's decision, status, and rationale.
    approved_for_execution is ALWAYS False in Phase 3F — this layer
    does not authorize any form of execution.
    """

    model_config = ConfigDict(extra="forbid")

    outcome_id: str = Field(min_length=1)
    decision: HumanReviewDecision = "unknown"
    status: HumanReviewStatus = "unknown"
    recommendation: HumanReviewRecommendation = "unknown"
    rationale: str = Field(min_length=1)
    reviewer_role: HumanReviewerRole = "unknown"
    approved_for_execution: bool = False
    approved_for_research_only: bool = False
    revision_required: bool = False
    blocked: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "HumanReviewOutcome":
        for fn in ("outcome_id", "rationale"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "HumanReviewOutcome":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3F. "
                "This layer does not authorize execution."
            )
        return self


class HumanReviewReport(BaseModel):
    """
    Aggregated human review report for one DecisionPacket or input bundle.

    Status and recommendation are auto-normalised from feedback items,
    revision requests, and outcome:
      - blocked            if any critical feedback or blocked revision request.
      - changes_requested  if any revision requests present.
      - approved_for_research_only if outcome approves research and no critical blockers.
      - pending / unknown  otherwise.

    approved_for_execution is ALWAYS False. This report is a research artifact.
    """

    model_config = ConfigDict(extra="forbid")

    review_report_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    status: HumanReviewStatus = "unknown"
    recommendation: HumanReviewRecommendation = "unknown"
    review_items: list[HumanReviewItem] = Field(default_factory=list)
    feedback_items: list[HumanFeedbackItem] = Field(default_factory=list)
    revision_requests: list[HumanRevisionRequest] = Field(default_factory=list)
    outcome: Optional[HumanReviewOutcome] = None
    source_ids: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "HumanReviewReport":
        for fn in ("review_report_id", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class HumanReviewInputBundle(BaseModel):
    """
    Input bundle consumed by run_human_review_skeleton().

    Accepts artifacts from Phases 3A–3E via duck typing (Any) for
    decision_packet, debate_report, horizon_synthesis_report, and
    macro_agent_result so that cross-module imports are not required.
    ValidationAggregate, StalenessReport, CriticResult, and
    ReliabilityScoreSummary are typed for evidence-aware processing.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    decision_packet: Optional[Any] = None
    debate_report: Optional[Any] = None
    horizon_synthesis_report: Optional[Any] = None
    macro_agent_result: Optional[Any] = None
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    reliability_score_summary: Optional[ReliabilityScoreSummary] = None
    manual_feedback: list[HumanFeedbackItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "HumanReviewInputBundle":
        for fn in ("bundle_id", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generators
# ---------------------------------------------------------------------------

def make_human_feedback_id(
    feedback_type: str,
    message: str,
    source_type: str = "unknown",
    related_id: Optional[str] = None,
    evidence_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for a HumanFeedbackItem."""
    payload = {
        "feedback_type": feedback_type,
        "message": message,
        "source_type": source_type,
        "related_id": related_id,
        "evidence_id": evidence_id,
        "field_path": field_path,
    }
    h = stable_hash_payload(payload, length=16)
    return f"hf_{h}"


def make_human_review_report_id(
    bundle_id: str,
    as_of: str,
    ticker: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for a HumanReviewReport."""
    payload = {
        "bundle_id": bundle_id,
        "as_of": as_of,
        "ticker": ticker,
    }
    h = stable_hash_payload(payload, length=16)
    return f"hrr_{h}"


# ---------------------------------------------------------------------------
# Helper: feedback converters
# ---------------------------------------------------------------------------

def feedback_from_decision_packet_issue(issue: Any) -> HumanFeedbackItem:
    """
    Convert a DecisionPacketIssue (duck-typed) into HumanFeedbackItem.

    Preserves evidence_id, field_path, related_id.
    Maps guardrail types to feedback types.
    Critical guardrails become critical feedback.
    """
    guardrail_type: str = str(getattr(issue, "guardrail_type", "other"))
    feedback_type: str = _GUARDRAIL_TYPE_TO_FEEDBACK_TYPE.get(guardrail_type, "other")

    severity_raw: str = str(getattr(issue, "severity", "warning"))
    severity = severity_raw if severity_raw in ("critical", "warning", "info") else "warning"

    message: str = str(getattr(issue, "message", "Decision packet issue"))
    if not message.strip():
        message = "Decision packet issue"

    source_type = "decision_packet"
    related_id: Optional[str] = getattr(issue, "related_id", None)
    evidence_id: Optional[str] = getattr(issue, "evidence_id", None)
    field_path: Optional[str] = getattr(issue, "field_path", None)

    feedback_id = make_human_feedback_id(
        feedback_type=feedback_type,
        message=message,
        source_type=source_type,
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )
    return HumanFeedbackItem(
        feedback_id=feedback_id,
        feedback_type=feedback_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        reviewer_role="system_reviewer",
        message=message,
        source_type=source_type,  # type: ignore[arg-type]
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def feedback_from_validation_item(item: AggregatedValidationItem) -> HumanFeedbackItem:
    """
    Convert AggregatedValidationItem into HumanFeedbackItem.

    Preserves evidence_id, field_path, object_id as related_id.
    Maps stale_data, missing_data, evidence_binding, safety, etc.
    """
    feedback_type: str = _VALIDATION_TYPE_TO_FEEDBACK_TYPE.get(item.item_type, "other")
    severity: str = item.severity  # already compatible
    source_type = "validation"
    related_id: Optional[str] = item.object_id
    evidence_id: Optional[str] = item.evidence_id
    field_path: Optional[str] = item.field_path

    feedback_id = make_human_feedback_id(
        feedback_type=feedback_type,
        message=item.message,
        source_type=source_type,
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )
    return HumanFeedbackItem(
        feedback_id=feedback_id,
        feedback_type=feedback_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        reviewer_role="system_reviewer",
        message=item.message,
        source_type=source_type,  # type: ignore[arg-type]
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def feedback_from_staleness_finding(finding: StalenessFinding) -> HumanFeedbackItem:
    """
    Convert StalenessFinding into HumanFeedbackItem.

    stale/expired/near_stale → stale_data.
    unknown timestamp → evidence_gap or stale_data.
    Preserves evidence_id, field_path, object_id.
    """
    feedback_type: str = _STALENESS_STATUS_TO_FEEDBACK_TYPE.get(finding.status, "stale_data")
    severity: str = finding.severity  # already critical / warning / info
    source_type = "staleness"
    related_id: Optional[str] = finding.object_id
    evidence_id: Optional[str] = finding.evidence_id
    field_path: Optional[str] = finding.field_path

    feedback_id = make_human_feedback_id(
        feedback_type=feedback_type,
        message=finding.message,
        source_type=source_type,
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )
    return HumanFeedbackItem(
        feedback_id=feedback_id,
        feedback_type=feedback_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        reviewer_role="system_reviewer",
        message=finding.message,
        source_type=source_type,  # type: ignore[arg-type]
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def feedback_from_critic_issue(issue: CriticIssue) -> HumanFeedbackItem:
    """
    Convert CriticIssue into HumanFeedbackItem.

    Maps missing_risk, missing_assumption, overconfidence, unsupported_claim,
    conflicting_evidence, stale_evidence.
    Preserves evidence_id, field_path, related ID.
    """
    feedback_type: str = _CRITIC_TYPE_TO_FEEDBACK_TYPE.get(issue.issue_type, "other")
    severity: str = issue.severity  # already compatible
    source_type = "critic"
    related_id: Optional[str] = issue.issue_id
    evidence_id: Optional[str] = issue.evidence_id
    field_path: Optional[str] = issue.field_path

    feedback_id = make_human_feedback_id(
        feedback_type=feedback_type,
        message=issue.message,
        source_type=source_type,
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )
    return HumanFeedbackItem(
        feedback_id=feedback_id,
        feedback_type=feedback_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        reviewer_role="system_reviewer",
        message=issue.message,
        source_type=source_type,  # type: ignore[arg-type]
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


# ---------------------------------------------------------------------------
# Helper: collect feedback
# ---------------------------------------------------------------------------

def collect_human_feedback(
    input_bundle: HumanReviewInputBundle,
) -> list[HumanFeedbackItem]:
    """
    Collect feedback from all sources in the input bundle.

    Deterministic order:
      1. DecisionPacket issues.
      2. DecisionPacket guardrails (non-execution/non-review guardrails only).
      3. ValidationAggregate items.
      4. StalenessReport findings.
      5. CriticResult issues.
      6. Manual feedback.

    De-duplicates by feedback_id (first occurrence wins).
    Does not mutate inputs.
    """
    seen: set[str] = set()
    items: list[HumanFeedbackItem] = []

    def _add(item: HumanFeedbackItem) -> None:
        if item.feedback_id not in seen:
            seen.add(item.feedback_id)
            items.append(item)

    # 1. DecisionPacket issues
    dp = input_bundle.decision_packet
    if dp is not None:
        for issue in getattr(dp, "issues", []) or []:
            _add(feedback_from_decision_packet_issue(issue))

        # 2. DecisionPacket guardrails
        for grd in getattr(dp, "guardrails", []) or []:
            triggered = getattr(grd, "triggered", False)
            if not triggered:
                continue
            gtype: str = str(getattr(grd, "guardrail_type", "other"))
            # Skip the always-present meta-guardrails — they become top-level report flags
            if gtype in ("execution_forbidden", "human_review_required"):
                continue
            _add(feedback_from_decision_packet_issue(grd))

    # 3. ValidationAggregate items
    va = input_bundle.validation_aggregate
    if va is not None:
        for item in va.items:
            _add(feedback_from_validation_item(item))

    # 4. StalenessReport findings
    sr = input_bundle.staleness_report
    if sr is not None:
        for finding in sr.findings:
            if finding.status == "fresh":
                continue
            _add(feedback_from_staleness_finding(finding))

    # 5. CriticResult issues
    cr = input_bundle.critic_result
    if cr is not None:
        for issue in cr.issues:
            _add(feedback_from_critic_issue(issue))

    # 6. Manual feedback
    for item in input_bundle.manual_feedback:
        _add(item)

    return items


# ---------------------------------------------------------------------------
# Helper: revision request builder
# ---------------------------------------------------------------------------

def build_revision_requests(
    feedback_items: list[HumanFeedbackItem],
) -> list[HumanRevisionRequest]:
    """
    Create revision requests from critical and warning feedback items.

    - Critical feedback → blocked_until_resolved=True.
    - Evidence gaps → request more evidence.
    - Missing risk → request risk section update.
    - Stale data → request freshness check.
    - Unsupported claim → request evidence binding correction.
    - Deterministic: groups by feedback_type, then creates one revision request per type.
    """
    # Group by feedback_type, ordered by first appearance
    type_order: list[str] = []
    type_items: dict[str, list[HumanFeedbackItem]] = {}
    for item in feedback_items:
        if item.severity not in ("critical", "warning"):
            continue
        if item.feedback_type not in type_items:
            type_order.append(item.feedback_type)
            type_items[item.feedback_type] = []
        type_items[item.feedback_type].append(item)

    revision_requests: list[HumanRevisionRequest] = []

    for ftype in type_order:
        group = type_items[ftype]
        is_critical = any(i.severity == "critical" for i in group)
        source_ids = [i.feedback_id for i in group]
        reason = _FEEDBACK_TYPE_TO_REVISION_REASON.get(ftype, "Review issue detected.")

        # Derive requested_changes from feedback type
        changes: list[str] = []
        if ftype == "evidence_gap":
            changes = ["Provide additional supporting evidence for all unsupported claims."]
        elif ftype == "stale_data":
            changes = ["Refresh stale data sources and update timestamps."]
        elif ftype == "unsupported_claim":
            changes = ["Bind all numeric and metric claims to ToolResult evidence IDs."]
        elif ftype == "missing_risk":
            changes = ["Add missing risks to the Key Risks section."]
        elif ftype == "missing_assumption":
            changes = ["Document missing assumptions in the assumptions section."]
        elif ftype == "conflicting_evidence":
            changes = ["Resolve conflicting evidence before proceeding."]
        elif ftype == "excessive_confidence":
            changes = ["Recalibrate confidence levels to match available evidence."]
        elif ftype == "safety_concern":
            changes = ["Escalate to compliance review before any downstream use."]
        elif ftype == "scope_violation":
            changes = ["Remove or reclassify out-of-scope content."]
        else:
            changes = ["Address feedback items of type '{}'.".format(ftype)]

        rr_id_hash = stable_hash_payload(
            {"ftype": ftype, "source_ids": sorted(source_ids)},
            length=16,
        )
        revision_requests.append(
            HumanRevisionRequest(
                revision_request_id=f"rr_{rr_id_hash}",
                reason=reason,
                required=True,
                source_feedback_ids=source_ids,
                requested_changes=changes,
                blocked_until_resolved=is_critical,
            )
        )

    return revision_requests


# ---------------------------------------------------------------------------
# Helper: review item builder
# ---------------------------------------------------------------------------

def build_review_items(
    input_bundle: HumanReviewInputBundle,
    feedback_items: list[HumanFeedbackItem],
    revision_requests: list[HumanRevisionRequest],
) -> list[HumanReviewItem]:
    """
    Create review items for each source artifact in the input bundle.

    Includes source IDs where available:
      - decision_packet_id from decision_packet
      - debate_id from debate_report
      - synthesis_id from horizon_synthesis_report
      - macro_agent_id from macro_agent_result
      - aggregate_id from validation_aggregate
      - report_id from staleness_report
      - critic_id from critic_result
    """
    review_items: list[HumanReviewItem] = []

    def _item_id(source_type: str, source_id: Optional[str]) -> str:
        h = stable_hash_payload(
            {"source_type": source_type, "source_id": source_id,
             "bundle_id": input_bundle.bundle_id},
            length=16,
        )
        return f"ri_{h}"

    def _status_for(source_feedback: list[HumanFeedbackItem]) -> HumanReviewStatus:
        if any(f.severity == "critical" for f in source_feedback):
            return "blocked"
        if source_feedback:
            return "changes_requested"
        return "pending"

    # 1. DecisionPacket review item
    dp = input_bundle.decision_packet
    if dp is not None:
        dp_id: Optional[str] = getattr(dp, "decision_packet_id", None)
        dp_feedback = [f for f in feedback_items if f.source_type == "decision_packet"]
        dp_revisions = [r for r in revision_requests
                        if any(fid in r.source_feedback_ids
                               for fid in [f.feedback_id for f in dp_feedback])]
        ticker_label = input_bundle.ticker or "subject"
        summary = (
            f"Review of decision packet for {ticker_label}. "
            f"Feedback items: {len(dp_feedback)}. "
            f"Revision requests: {len(dp_revisions)}. "
            f"Research artifact only — no execution authorization."
        )
        review_items.append(
            HumanReviewItem(
                review_item_id=_item_id("decision_packet", dp_id),
                source_type="decision_packet",
                source_id=dp_id,
                status=_status_for(dp_feedback),
                summary=summary,
                feedback_items=dp_feedback,
                revision_requests=dp_revisions,
            )
        )

    # 2. DebateReport review item
    dr = input_bundle.debate_report
    if dr is not None:
        dr_id: Optional[str] = (
            getattr(dr, "debate_id", None) or getattr(dr, "report_id", None)
        )
        debate_feedback: list[HumanFeedbackItem] = []
        debate_revisions: list[HumanRevisionRequest] = []
        ticker_label = input_bundle.ticker or "subject"
        summary = (
            f"Review of debate report for {ticker_label}. "
            f"Feedback items: {len(debate_feedback)}. "
            f"Research artifact only — no execution authorization."
        )
        review_items.append(
            HumanReviewItem(
                review_item_id=_item_id("debate", dr_id),
                source_type="debate",
                source_id=dr_id,
                status="pending",
                summary=summary,
                feedback_items=debate_feedback,
                revision_requests=debate_revisions,
            )
        )

    # 3. HorizonSynthesisReport review item
    hsr = input_bundle.horizon_synthesis_report
    if hsr is not None:
        hsr_id: Optional[str] = (
            getattr(hsr, "synthesis_id", None) or getattr(hsr, "report_id", None)
        )
        hsr_feedback: list[HumanFeedbackItem] = []
        hsr_revisions: list[HumanRevisionRequest] = []
        ticker_label = input_bundle.ticker or "subject"
        summary = (
            f"Review of horizon synthesis report for {ticker_label}. "
            f"Feedback items: {len(hsr_feedback)}. "
            f"Research artifact only — no execution authorization."
        )
        review_items.append(
            HumanReviewItem(
                review_item_id=_item_id("horizon_synthesis", hsr_id),
                source_type="horizon_synthesis",
                source_id=hsr_id,
                status="pending",
                summary=summary,
                feedback_items=hsr_feedback,
                revision_requests=hsr_revisions,
            )
        )

    # 4. MacroAgentResult review item
    mar = input_bundle.macro_agent_result
    if mar is not None:
        mar_id: Optional[str] = (
            getattr(mar, "macro_agent_id", None) or getattr(mar, "agent_id", None)
        )
        mar_feedback: list[HumanFeedbackItem] = []
        mar_revisions: list[HumanRevisionRequest] = []
        ticker_label = input_bundle.ticker or "subject"
        summary = (
            f"Review of macro agent result for {ticker_label}. "
            f"Feedback items: {len(mar_feedback)}. "
            f"Research artifact only — no execution authorization."
        )
        review_items.append(
            HumanReviewItem(
                review_item_id=_item_id("macro_agent", mar_id),
                source_type="macro_agent",
                source_id=mar_id,
                status="pending",
                summary=summary,
                feedback_items=mar_feedback,
                revision_requests=mar_revisions,
            )
        )

    # 5. ValidationAggregate review item
    va = input_bundle.validation_aggregate
    if va is not None:
        va_id: Optional[str] = getattr(va, "aggregate_id", None)
        va_feedback = [f for f in feedback_items if f.source_type == "validation"]
        va_revisions = [r for r in revision_requests
                        if any(fid in r.source_feedback_ids
                               for fid in [f.feedback_id for f in va_feedback])]
        ticker_label = input_bundle.ticker or "subject"
        summary = (
            f"Review of validation aggregate. "
            f"Feedback items: {len(va_feedback)}. "
            f"Critical: {sum(1 for f in va_feedback if f.severity == 'critical')}. "
            f"Research artifact only."
        )
        review_items.append(
            HumanReviewItem(
                review_item_id=_item_id("validation", va_id),
                source_type="validation",
                source_id=va_id,
                status=_status_for(va_feedback),
                summary=summary,
                feedback_items=va_feedback,
                revision_requests=va_revisions,
            )
        )

    # 6. StalenessReport review item
    sr = input_bundle.staleness_report
    if sr is not None:
        sr_id: Optional[str] = getattr(sr, "report_id", None)
        sr_feedback = [f for f in feedback_items if f.source_type == "staleness"]
        sr_revisions = [r for r in revision_requests
                        if any(fid in r.source_feedback_ids
                               for fid in [f.feedback_id for f in sr_feedback])]
        ticker_label = input_bundle.ticker or "subject"
        summary = (
            f"Review of staleness report. "
            f"Feedback items: {len(sr_feedback)}. "
            f"Research artifact only."
        )
        review_items.append(
            HumanReviewItem(
                review_item_id=_item_id("staleness", sr_id),
                source_type="staleness",
                source_id=sr_id,
                status=_status_for(sr_feedback),
                summary=summary,
                feedback_items=sr_feedback,
                revision_requests=sr_revisions,
            )
        )

    # 7. CriticResult review item
    cr = input_bundle.critic_result
    if cr is not None:
        cr_id: Optional[str] = getattr(cr, "critic_id", None)
        cr_feedback = [f for f in feedback_items if f.source_type == "critic"]
        cr_revisions = [r for r in revision_requests
                        if any(fid in r.source_feedback_ids
                               for fid in [f.feedback_id for f in cr_feedback])]
        ticker_label = input_bundle.ticker or "subject"
        summary = (
            f"Review of critic result. "
            f"Feedback items: {len(cr_feedback)}. "
            f"Research artifact only."
        )
        review_items.append(
            HumanReviewItem(
                review_item_id=_item_id("critic", cr_id),
                source_type="critic",
                source_id=cr_id,
                status=_status_for(cr_feedback),
                summary=summary,
                feedback_items=cr_feedback,
                revision_requests=cr_revisions,
            )
        )

    return review_items


# ---------------------------------------------------------------------------
# Helper: outcome determination
# ---------------------------------------------------------------------------

def determine_human_review_outcome(
    feedback_items: list[HumanFeedbackItem],
    revision_requests: list[HumanRevisionRequest],
    reviewer_role: str = "system_reviewer",
) -> HumanReviewOutcome:
    """
    Determine the review outcome from feedback items and revision requests.

    Rules:
    - Critical feedback or blocked revision → decision=block, status=blocked.
    - Warnings only → decision=request_revision, status=changes_requested.
    - Clean → decision=approve_for_research, status=approved_for_research_only,
      approved_for_research_only=True.
    - approved_for_execution is ALWAYS False.
    """
    has_critical = any(f.severity == "critical" for f in feedback_items)
    has_blocked_revision = any(r.blocked_until_resolved for r in revision_requests)
    has_warnings = any(f.severity == "warning" for f in feedback_items)
    has_evidence_gaps = any(f.feedback_type == "evidence_gap" for f in feedback_items)

    # Normalize reviewer_role
    role: str = reviewer_role if reviewer_role in (
        "analyst", "portfolio_manager", "risk_reviewer",
        "compliance_reviewer", "system_reviewer", "unknown"
    ) else "system_reviewer"

    outcome_id_hash = stable_hash_payload(
        {
            "has_critical": has_critical,
            "has_blocked": has_blocked_revision,
            "has_warnings": has_warnings,
            "feedback_count": len(feedback_items),
            "revision_count": len(revision_requests),
        },
        length=16,
    )
    outcome_id = f"hro_{outcome_id_hash}"

    if has_critical or has_blocked_revision:
        # Critical feedback always blocks, regardless of whether a pre-built
        # blocked revision request was supplied.
        decision: HumanReviewDecision = "block"
        status: HumanReviewStatus = "blocked"
        recommendation: HumanReviewRecommendation = "block"
        rationale = (
            "Critical feedback items or blocked revision requests were detected. "
            "This artifact is blocked pending resolution. "
            "Execution is not authorized at any stage."
        )
        blocked = True
        revision_required = True
    elif has_warnings:
        decision = "request_revision"
        status = "changes_requested"
        recommendation = "revise"
        rationale = (
            "Warning-level feedback items were detected. "
            "Revision is recommended before downstream research use. "
            "Execution is not authorized."
        )
        blocked = False
        revision_required = True
    else:
        if has_evidence_gaps:
            decision = "defer"
            status = "pending"
            recommendation = "needs_more_evidence"
            rationale = (
                "Evidence gaps detected; additional evidence required "
                "before this artifact is ready for research approval. "
                "Execution is not authorized."
            )
            blocked = False
            revision_required = False
        else:
            decision = "approve_for_research"
            status = "approved_for_research_only"
            recommendation = "accept_for_research"
            rationale = (
                "No critical or warning feedback detected. "
                "This artifact is approved for research use only. "
                "Execution is NOT authorized and remains forbidden."
            )
            blocked = False
            revision_required = False

    return HumanReviewOutcome(
        outcome_id=outcome_id,
        decision=decision,
        status=status,
        recommendation=recommendation,
        rationale=rationale,
        reviewer_role=role,  # type: ignore[arg-type]
        approved_for_execution=False,  # Always False
        approved_for_research_only=(decision == "approve_for_research"),
        revision_required=revision_required,
        blocked=blocked,
    )


# ---------------------------------------------------------------------------
# Helper: report builder
# ---------------------------------------------------------------------------

def build_human_review_report(
    review_report_id: str,
    as_of: str,
    ticker: Optional[str] = None,
    review_items: Optional[list[HumanReviewItem]] = None,
    feedback_items: Optional[list[HumanFeedbackItem]] = None,
    revision_requests: Optional[list[HumanRevisionRequest]] = None,
    outcome: Optional[HumanReviewOutcome] = None,
    source_ids: Optional[dict[str, str]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> HumanReviewReport:
    """
    Build a HumanReviewReport with normalized status and recommendation.

    Does not mutate inputs.
    Never authorizes execution.
    """
    _review_items = list(review_items or [])
    _feedback_items = list(feedback_items or [])
    _revision_requests = list(revision_requests or [])
    _source_ids = dict(source_ids or {})
    _metadata = dict(metadata or {})

    # Normalize status from feedback and outcome
    has_critical = any(f.severity == "critical" for f in _feedback_items)
    has_blocked_revision = any(r.blocked_until_resolved for r in _revision_requests)
    has_warnings = any(f.severity == "warning" for f in _feedback_items)
    has_evidence_gaps = any(
        f.feedback_type == "evidence_gap" for f in _feedback_items
    )

    if outcome is not None:
        status: HumanReviewStatus = outcome.status
        recommendation: HumanReviewRecommendation = outcome.recommendation
    elif has_critical or has_blocked_revision:
        status = "blocked"
        recommendation = "block"
    elif has_warnings:
        status = "changes_requested"
        recommendation = "revise"
    elif has_evidence_gaps:
        status = "pending"
        recommendation = "needs_more_evidence"
    elif _feedback_items:
        status = "changes_requested"
        recommendation = "revise"
    else:
        status = "pending"
        recommendation = "unknown"

    return HumanReviewReport(
        review_report_id=review_report_id,
        as_of=as_of,
        ticker=ticker,
        status=status,
        recommendation=recommendation,
        review_items=_review_items,
        feedback_items=_feedback_items,
        revision_requests=_revision_requests,
        outcome=outcome,
        source_ids=_source_ids,
        metadata=_metadata,
    )


# ---------------------------------------------------------------------------
# Helper: main skeleton runner
# ---------------------------------------------------------------------------

def run_human_review_skeleton(
    input_bundle: HumanReviewInputBundle,
) -> HumanReviewReport:
    """
    Run a complete offline, deterministic human review pass.

    Steps:
      1. Collect feedback from all input artifacts.
      2. Build revision requests from feedback.
      3. Build review items for each source artifact.
      4. Determine review outcome.
      5. Build and return the HumanReviewReport.

    This is a dry-run/mock pass only.
    No LLM calls. No live API calls. No app imports. No mutation.
    Does not constitute investment advice.
    Does not authorize execution — approved_for_execution is always False.
    """
    feedback_items = collect_human_feedback(input_bundle)
    revision_requests = build_revision_requests(feedback_items)
    review_items = build_review_items(input_bundle, feedback_items, revision_requests)
    outcome = determine_human_review_outcome(
        feedback_items, revision_requests, reviewer_role="system_reviewer"
    )

    # Build source_ids
    source_ids: dict[str, str] = {}
    dp = input_bundle.decision_packet
    if dp is not None:
        dp_id = getattr(dp, "decision_packet_id", None)
        if dp_id:
            source_ids["decision_packet_id"] = str(dp_id)
    dr = input_bundle.debate_report
    if dr is not None:
        dr_id = getattr(dr, "debate_id", None) or getattr(dr, "report_id", None)
        if dr_id:
            source_ids["debate_id"] = str(dr_id)
    hsr = input_bundle.horizon_synthesis_report
    if hsr is not None:
        hsr_id = getattr(hsr, "synthesis_id", None) or getattr(hsr, "report_id", None)
        if hsr_id:
            source_ids["synthesis_id"] = str(hsr_id)
    mar = input_bundle.macro_agent_result
    if mar is not None:
        mar_id = getattr(mar, "macro_agent_id", None) or getattr(mar, "agent_id", None)
        if mar_id:
            source_ids["macro_agent_id"] = str(mar_id)
    va = input_bundle.validation_aggregate
    if va is not None:
        va_id = getattr(va, "aggregate_id", None)
        if va_id:
            source_ids["aggregate_id"] = str(va_id)
    sr = input_bundle.staleness_report
    if sr is not None:
        sr_id = getattr(sr, "report_id", None)
        if sr_id:
            source_ids["report_id"] = str(sr_id)
    cr = input_bundle.critic_result
    if cr is not None:
        cr_id = getattr(cr, "critic_id", None)
        if cr_id:
            source_ids["critic_id"] = str(cr_id)

    review_report_id = make_human_review_report_id(
        bundle_id=input_bundle.bundle_id,
        as_of=input_bundle.as_of,
        ticker=input_bundle.ticker,
    )

    return build_human_review_report(
        review_report_id=review_report_id,
        as_of=input_bundle.as_of,
        ticker=input_bundle.ticker,
        review_items=review_items,
        feedback_items=feedback_items,
        revision_requests=revision_requests,
        outcome=outcome,
        source_ids=source_ids,
    )


# ---------------------------------------------------------------------------
# Helper: ToolResult wrapper
# ---------------------------------------------------------------------------

def summarize_human_review_report(report: HumanReviewReport) -> dict[str, Any]:
    """
    Return a concise summary dict of a HumanReviewReport.

    Fields:
      review_report_id, ticker, status, recommendation,
      feedback_count, revision_request_count, review_item_count,
      critical_count, warning_count, info_count,
      approved_for_research_only, approved_for_execution (always False),
      top_messages (capped at 10)
    """
    critical_count = sum(1 for f in report.feedback_items if f.severity == "critical")
    warning_count = sum(1 for f in report.feedback_items if f.severity == "warning")
    info_count = sum(1 for f in report.feedback_items if f.severity == "info")

    approved_for_research_only = (
        report.outcome.approved_for_research_only
        if report.outcome is not None
        else False
    )

    top_messages = [f.message for f in report.feedback_items[:10]]

    return {
        "review_report_id": report.review_report_id,
        "ticker": report.ticker,
        "status": report.status,
        "recommendation": report.recommendation,
        "feedback_count": len(report.feedback_items),
        "revision_request_count": len(report.revision_requests),
        "review_item_count": len(report.review_items),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "approved_for_research_only": approved_for_research_only,
        "approved_for_execution": False,  # Always False
        "top_messages": top_messages,
    }


def human_review_tool_result_from_report(
    run_id: str,
    report: HumanReviewReport,
    target: Optional[str] = None,
    calculation_version: str = "human_review_skeleton_v1",
) -> ToolResult:
    """
    Wrap a HumanReviewReport as a ToolResult for evidence-aware pipelines.

    - tool_name is stable: "human_review_report".
    - target defaults to report.ticker if present, else "human_review".
    - outputs includes report (full serialized), summary, calculation_version.
    - evidence_id is deterministic and content-sensitive.
    - Does not mutate report.
    - Does not loosen ToolResult schema.
    """
    _target: str = target or report.ticker or "human_review"
    _summary = summarize_human_review_report(report)
    _report_dict = report.model_dump()

    outputs: dict[str, Any] = {
        "report": _report_dict,
        "summary": _summary,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_HUMAN_REVIEW_TOOL_NAME,
        target=_target,
        metric_group=_HUMAN_REVIEW_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_HUMAN_REVIEW_TOOL_NAME,
        run_id=run_id,
        ticker=report.ticker,
        inputs={"as_of": report.as_of, "ticker": report.ticker},
        outputs=outputs,
        description=(
            f"HumanReviewReport for {report.ticker or 'unknown'}: "
            f"status={report.status}, recommendation={report.recommendation}."
        ),
    )
