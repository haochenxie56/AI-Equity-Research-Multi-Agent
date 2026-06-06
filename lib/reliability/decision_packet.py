"""
lib/reliability/decision_packet.py

Phase 3E: DecisionPacket Schema / Decision Synthesis Skeleton.

Design principles:
  - Standalone, deterministic, offline.
  - No live LLM calls, no live data fetching, no app integration.
  - Consumes Phase 3A–3D reliability artifacts and produces a structured
    DecisionPacket draft for human review.
  - All normalization is rule-based; no free-form LLM reasoning.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell/order instructions, or
    individual security recommendations.
  - Mock/dry-run only; all outputs are explicitly evidence-aware.
  - execution_forbidden guardrail is always included.
  - Human review is always required before any future execution-related use.

See docs/reliability_phase_3e_decision_packet_skeleton.md for design.

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
from lib.reliability.schemas import AgentResult, ToolResult
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

DecisionPacketStatus = Literal[
    "pass",
    "pass_with_warnings",
    "fail",
    "insufficient_evidence",
    "blocked",
    "unknown",
]

DecisionActionType = Literal[
    "no_action",
    "monitor",
    "needs_more_research",
    "prepare_watchlist",
    "prepare_scenario_plan",
    "human_review_required",
    "reject",
    "unknown",
]

DecisionConfidence = Literal[
    "high",
    "medium",
    "low",
    "insufficient_evidence",
    "unknown",
]

DecisionGuardrailType = Literal[
    "insufficient_evidence",
    "stale_data",
    "validation_failure",
    "critic_blocker",
    "debate_unresolved",
    "missing_risk",
    "missing_assumption",
    "conflicting_evidence",
    "overconfidence",
    "execution_forbidden",
    "human_review_required",
    "other",
]

DecisionReviewStatus = Literal[
    "not_reviewed",
    "review_required",
    "reviewed",
    "rejected",
    "approved_for_research_only",
    "unknown",
]

DecisionSourceType = Literal[
    "debate",
    "horizon_synthesis",
    "macro_agent",
    "orchestration",
    "validation",
    "staleness",
    "critic",
    "evaluation",
    "agent_result",
    "tool_result",
    "manual",
    "unknown",
]

DecisionHorizon = Literal[
    "short_term",
    "medium_term",
    "long_term",
    "multi_horizon",
    "unknown",
]

DecisionRecommendation = Literal[
    "accept_for_research",
    "revise",
    "reject",
    "needs_more_evidence",
    "monitor_only",
    "unknown",
]

DecisionIssueSeverity = Literal["critical", "warning", "info"]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_DECISION_PACKET_TOOL_NAME: str = "decision_packet"
_DECISION_PACKET_METRIC_GROUP: str = "decision_packet"

# ValidationItemType → DecisionGuardrailType
_VALIDATION_TYPE_MAP: dict[str, str] = {
    "stale_data": "stale_data",
    "missing_data": "insufficient_evidence",
    "evidence_binding": "validation_failure",
    "unsupported": "validation_failure",
    "risk_limit": "critic_blocker",
    "safety": "human_review_required",
    "schema": "validation_failure",
    "mismatch": "conflicting_evidence",
    "duplicate_data": "other",
    "calculation": "validation_failure",
    "provenance": "insufficient_evidence",
    "other": "other",
}

# StalenessStatus → DecisionGuardrailType
_STALENESS_STATUS_MAP: dict[str, str] = {
    "stale": "stale_data",
    "expired": "stale_data",
    "near_stale": "stale_data",
    "unknown": "insufficient_evidence",
    "fresh": "other",
}

# CriticIssueType → DecisionGuardrailType
_CRITIC_TYPE_MAP: dict[str, str] = {
    "missing_risk": "missing_risk",
    "missing_assumption": "missing_assumption",
    "conflicting_evidence": "conflicting_evidence",
    "stale_evidence": "stale_data",
    "unsupported_claim": "validation_failure",
    "overconfidence": "overconfidence",
    "weak_evidence": "insufficient_evidence",
    "validation_failure": "validation_failure",
    "numeric_claim_issue": "validation_failure",
    "scope_violation": "other",
    "safety_concern": "human_review_required",
    "other": "other",
}

# DebateIssueType → DecisionGuardrailType
_DEBATE_TYPE_MAP: dict[str, str] = {
    "unresolved_question": "debate_unresolved",
    "missing_evidence": "insufficient_evidence",
    "stale_evidence": "stale_data",
    "missing_risk": "missing_risk",
    "missing_assumption": "missing_assumption",
    "conflicting_evidence": "conflicting_evidence",
    "unsupported_claim": "validation_failure",
    "overconfidence": "overconfidence",
    "validation_issue": "validation_failure",
    "critic_issue": "critic_blocker",
    "horizon_mismatch": "other",
    "other": "other",
}

# Always-present prohibited action labels
_PROHIBITED_LIVE_TRADING: list[str] = [
    "live trading",
    "order placement",
    "buy/sell execution",
    "broker submission",
    "portfolio rebalancing without human approval",
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DecisionPacketIssue(BaseModel):
    """
    One structured issue raised during decision packet synthesis.

    Issues surface validation, staleness, critic, and debate problems that
    affect the reliability or completeness of the decision packet.
    """

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1)
    guardrail_type: DecisionGuardrailType
    severity: DecisionIssueSeverity = "warning"
    message: str = Field(min_length=1)
    source_type: DecisionSourceType = "unknown"
    related_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DecisionPacketIssue":
        for fn in ("issue_id", "message"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class DecisionRationale(BaseModel):
    """
    One structured rationale contributing to the decision packet.

    Rationales are research-oriented; they do not constitute investment
    recommendations or buy/sell instructions.
    """

    model_config = ConfigDict(extra="forbid")

    rationale_id: str = Field(min_length=1)
    source_type: DecisionSourceType
    horizon: DecisionHorizon = "unknown"
    summary: str = Field(min_length=1)
    supporting_points: list[str] = Field(default_factory=list)
    opposing_points: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: DecisionConfidence = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DecisionRationale":
        for fn in ("rationale_id", "summary"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class DecisionGuardrail(BaseModel):
    """
    One guardrail evaluated during decision packet synthesis.

    Guardrails flag conditions that must be resolved before any downstream
    use of this packet, including human review requirements.
    """

    model_config = ConfigDict(extra="forbid")

    guardrail_id: str = Field(min_length=1)
    guardrail_type: DecisionGuardrailType
    triggered: bool = False
    severity: DecisionIssueSeverity = "warning"
    message: str = Field(min_length=1)
    related_issue_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DecisionGuardrail":
        for fn in ("guardrail_id", "message"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class DecisionActionDraft(BaseModel):
    """
    Draft research/review action recommended for this decision packet.

    No live trading, order placement, or investment execution is permitted.
    All actions are research and monitoring oriented.
    """

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1)
    action_type: DecisionActionType = "unknown"
    horizon: DecisionHorizon = "unknown"
    description: str = Field(min_length=1)
    allowed_next_steps: list[str] = Field(default_factory=list)
    prohibited_actions: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DecisionActionDraft":
        for fn in ("action_id", "description"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class DecisionReviewRequirement(BaseModel):
    """
    Human review requirement attached to this decision packet.

    Review is always required before any future execution-related use.
    """

    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(min_length=1)
    review_status: DecisionReviewStatus = "review_required"
    required: bool = True
    reason: str = Field(min_length=1)
    reviewer_role: Optional[str] = None
    related_guardrail_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DecisionReviewRequirement":
        for fn in ("review_id", "reason"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class DecisionPacket(BaseModel):
    """
    Structured decision packet produced by deterministic synthesis.

    This is a research/review artifact only. It does not constitute
    investment advice, a buy/sell recommendation, or an order.

    Status and recommendation are auto-normalised from guardrails and issues:
      - blocked/fail  if critical guardrails triggered.
      - insufficient_evidence if evidence/guardrails require more data.
      - pass_with_warnings if only warning guardrails.
      - pass if no critical/warning guardrails and evidence is sufficient.

    Recommendation follows from status:
      - reject              if fail/blocked.
      - needs_more_evidence if insufficient_evidence.
      - revise              if pass_with_warnings.
      - accept_for_research if pass.
      - monitor_only        for no_action/monitor action outputs.
    """

    model_config = ConfigDict(extra="forbid")

    decision_packet_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    status: DecisionPacketStatus = "unknown"
    recommendation: DecisionRecommendation = "unknown"
    confidence: DecisionConfidence = "unknown"
    primary_action: Optional[DecisionActionDraft] = None
    rationales: list[DecisionRationale] = Field(default_factory=list)
    guardrails: list[DecisionGuardrail] = Field(default_factory=list)
    review_requirements: list[DecisionReviewRequirement] = Field(default_factory=list)
    issues: list[DecisionPacketIssue] = Field(default_factory=list)
    source_ids: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DecisionPacket":
        for fn in ("decision_packet_id", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class DecisionPacketInputBundle(BaseModel):
    """
    Input bundle consumed by run_decision_packet_synthesis().

    Accepts artifacts from Phases 3A–3D via duck typing (Any) so that
    direct cross-module imports are not required at runtime.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    debate_report: Optional[Any] = None
    horizon_synthesis_report: Optional[Any] = None
    macro_agent_result: Optional[Any] = None
    orchestration_report: Optional[Any] = None
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    reliability_score_summary: Optional[ReliabilityScoreSummary] = None
    agent_result: Optional[AgentResult] = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DecisionPacketInputBundle":
        for fn in ("bundle_id", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generators
# ---------------------------------------------------------------------------

def make_decision_packet_issue_id(
    guardrail_type: str,
    message: str,
    source_type: str = "unknown",
    related_id: Optional[str] = None,
    evidence_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for a DecisionPacketIssue."""
    payload = {
        "guardrail_type": guardrail_type,
        "message": message,
        "source_type": source_type,
        "related_id": related_id,
        "evidence_id": evidence_id,
        "field_path": field_path,
    }
    h = stable_hash_payload(payload, length=16)
    return f"dpissue_{h}"


def make_decision_packet_id(
    bundle_id: str,
    as_of: str,
    ticker: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for a DecisionPacket."""
    payload = {
        "bundle_id": bundle_id,
        "as_of": as_of,
        "ticker": ticker,
    }
    h = stable_hash_payload(payload, length=16)
    return f"dp_{h}"


# ---------------------------------------------------------------------------
# Helper: evidence ID extraction
# ---------------------------------------------------------------------------

def extract_decision_evidence_ids(input_bundle: DecisionPacketInputBundle) -> list[str]:
    """
    Collect evidence IDs from all artifact types in the input bundle.

    Deterministic order:
      1. ToolResult.evidence_id from tool_results list.
      2. AgentResult EvidenceRef.evidence_id from findings and risks.
      3. DebateReport: claim evidence IDs from each round/position/claim.
      4. HorizonSynthesisReport: card.evidence_summary.supporting_evidence_ids.
      5. MacroAgentResult: regime supporting IDs, impact evidence IDs, bias evidence IDs.

    Does not mutate inputs. Does not invent evidence.
    """
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(eid: str) -> None:
        if eid and eid not in seen:
            seen.add(eid)
            ordered.append(eid)

    # 1. ToolResult evidence IDs
    for tr in input_bundle.tool_results:
        _add(tr.evidence_id)

    # 2. AgentResult EvidenceRef evidence IDs
    if input_bundle.agent_result is not None:
        ar = input_bundle.agent_result
        for finding in getattr(ar, "findings", []) or []:
            for eref in getattr(finding, "evidence", []) or []:
                eid = getattr(eref, "evidence_id", None)
                if eid:
                    _add(eid)
        for risk in getattr(ar, "risks", []) or []:
            for eref in getattr(risk, "evidence", []) or []:
                eid = getattr(eref, "evidence_id", None)
                if eid:
                    _add(eid)

    # 3. DebateReport: claim evidence IDs
    if input_bundle.debate_report is not None:
        dr = input_bundle.debate_report
        for rnd in getattr(dr, "rounds", []) or []:
            for pos_attr in ("bull_position", "bear_position", "risk_position"):
                pos = getattr(rnd, pos_attr, None)
                if pos is None:
                    continue
                for eid in getattr(pos, "evidence_ids", []) or []:
                    _add(eid)
                for claim in getattr(pos, "claims", []) or []:
                    for eid in getattr(claim, "evidence_ids", []) or []:
                        _add(eid)

    # 4. HorizonSynthesisReport: accepted Phase 3B evidence summary first.
    if input_bundle.horizon_synthesis_report is not None:
        hsr = input_bundle.horizon_synthesis_report
        for card in getattr(hsr, "cards", []) or []:
            esummary = getattr(card, "evidence_summary", None)
            eids = (
                getattr(esummary, "supporting_evidence_ids", None)
                or getattr(card, "supporting_evidence_ids", None)
                or getattr(card, "evidence_ids", None)
                or getattr(esummary, "evidence_ids", None)
                or []
            )
            for eid in eids:
                _add(eid)

    # 5. MacroAgentResult: accepted Phase 3C evidence fields first.
    if input_bundle.macro_agent_result is not None:
        mar = input_bundle.macro_agent_result
        regime = getattr(mar, "regime_assessment", None)
        if regime is not None:
            for eid in getattr(regime, "supporting_evidence_ids", []) or []:
                _add(eid)
        for impact in getattr(mar, "horizon_impacts", []) or []:
            eids = (
                getattr(impact, "evidence_ids", None)
                or getattr(impact, "supporting_evidence_ids", None)
                or []
            )
            for eid in eids:
                _add(eid)
        for bias in getattr(mar, "sector_biases", []) or []:
            eids = (
                getattr(bias, "evidence_ids", None)
                or getattr(bias, "supporting_evidence_ids", None)
                or []
            )
            for eid in eids:
                _add(eid)

    return ordered


# ---------------------------------------------------------------------------
# Helper: issue converters
# ---------------------------------------------------------------------------

def issue_from_validation_item_for_decision(
    item: AggregatedValidationItem,
) -> DecisionPacketIssue:
    """Convert AggregatedValidationItem into DecisionPacketIssue."""
    guardrail_type: str = _VALIDATION_TYPE_MAP.get(
        item.item_type, "validation_failure"
    )
    severity: str = item.severity  # critical / warning / info — already compatible
    source_type: str = "validation"
    related_id: Optional[str] = item.object_id
    evidence_id: Optional[str] = item.evidence_id
    field_path: Optional[str] = item.field_path

    issue_id = make_decision_packet_issue_id(
        guardrail_type=guardrail_type,
        message=item.message,
        source_type=source_type,
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )
    return DecisionPacketIssue(
        issue_id=issue_id,
        guardrail_type=guardrail_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        message=item.message,
        source_type=source_type,  # type: ignore[arg-type]
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def issue_from_staleness_finding_for_decision(
    finding: StalenessFinding,
) -> DecisionPacketIssue:
    """Convert StalenessFinding into DecisionPacketIssue."""
    status = finding.status
    if status in ("stale", "expired", "near_stale"):
        guardrail_type = "stale_data"
    else:
        guardrail_type = "insufficient_evidence"

    severity: str = finding.severity  # already critical / warning / info
    source_type = "staleness"
    related_id: Optional[str] = finding.object_id
    evidence_id: Optional[str] = finding.evidence_id
    field_path: Optional[str] = finding.field_path

    issue_id = make_decision_packet_issue_id(
        guardrail_type=guardrail_type,
        message=finding.message,
        source_type=source_type,
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )
    return DecisionPacketIssue(
        issue_id=issue_id,
        guardrail_type=guardrail_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        message=finding.message,
        source_type=source_type,  # type: ignore[arg-type]
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def issue_from_critic_issue_for_decision(
    issue: CriticIssue,
) -> DecisionPacketIssue:
    """Convert CriticIssue into DecisionPacketIssue."""
    guardrail_type: str = _CRITIC_TYPE_MAP.get(issue.issue_type, "other")
    severity: str = issue.severity  # already critical / warning / info
    source_type = "critic"
    related_id: Optional[str] = issue.issue_id
    evidence_id: Optional[str] = issue.evidence_id
    field_path: Optional[str] = issue.field_path

    issue_id = make_decision_packet_issue_id(
        guardrail_type=guardrail_type,
        message=issue.message,
        source_type=source_type,
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )
    return DecisionPacketIssue(
        issue_id=issue_id,
        guardrail_type=guardrail_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        message=issue.message,
        source_type=source_type,  # type: ignore[arg-type]
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def issue_from_debate_issue_for_decision(issue: Any) -> DecisionPacketIssue:
    """Convert a DebateIssue (duck-typed) into DecisionPacketIssue."""
    issue_type_str: str = str(getattr(issue, "issue_type", "other"))
    guardrail_type: str = _DEBATE_TYPE_MAP.get(issue_type_str, "other")

    severity_raw: str = str(getattr(issue, "severity", "warning"))
    severity = severity_raw if severity_raw in ("critical", "warning", "info") else "warning"

    source_type = "debate"
    related_id: Optional[str] = (
        getattr(issue, "related_id", None)
        or getattr(issue, "issue_id", None)
    )
    evidence_id: Optional[str] = getattr(issue, "evidence_id", None)
    field_path: Optional[str] = getattr(issue, "field_path", None)
    message: str = str(getattr(issue, "message", "Debate issue"))
    if not message.strip():
        message = "Debate issue"

    issue_id = make_decision_packet_issue_id(
        guardrail_type=guardrail_type,
        message=message,
        source_type=source_type,
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )
    return DecisionPacketIssue(
        issue_id=issue_id,
        guardrail_type=guardrail_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        message=message,
        source_type=source_type,  # type: ignore[arg-type]
        related_id=related_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


# ---------------------------------------------------------------------------
# Helper: rationale builder
# ---------------------------------------------------------------------------

def build_decision_rationales(
    input_bundle: DecisionPacketInputBundle,
    evidence_ids: list[str],
) -> list[DecisionRationale]:
    """
    Build deterministic research rationales from available artifacts.

    Uses cautious, research-only language. Does not invent facts.
    Does not constitute investment advice.
    """
    rationales: list[DecisionRationale] = []
    ticker_label = input_bundle.ticker or "the subject"

    # 1. DebateReport rationale
    dr = input_bundle.debate_report
    if dr is not None:
        rounds = getattr(dr, "rounds", []) or []
        for rnd in rounds:
            horizon_raw = getattr(rnd, "horizon", "unknown")
            horizon = horizon_raw if horizon_raw in (
                "short_term", "medium_term", "long_term", "multi_horizon", "unknown"
            ) else "unknown"

            bull_pos = getattr(rnd, "bull_position", None)
            bear_pos = getattr(rnd, "bear_position", None)

            supporting: list[str] = []
            opposing: list[str] = []

            if bull_pos is not None:
                bull_summary = getattr(bull_pos, "summary", "")
                if bull_summary:
                    supporting.append(f"[Bull] {bull_summary}")
                for claim in getattr(bull_pos, "claims", []) or []:
                    ct = getattr(claim, "text", "")
                    if ct:
                        supporting.append(ct)

            if bear_pos is not None:
                bear_summary = getattr(bear_pos, "summary", "")
                if bear_summary:
                    opposing.append(f"[Bear] {bear_summary}")
                for claim in getattr(bear_pos, "claims", []) or []:
                    ct = getattr(claim, "text", "")
                    if ct:
                        opposing.append(ct)

            verdict = getattr(rnd, "verdict", "unknown")
            summary = (
                f"Debate round for {horizon} horizon — verdict: {verdict}. "
                f"This is a research summary for {ticker_label}. "
                f"It does not constitute investment advice."
            )

            # Collect evidence IDs for this round
            round_eids: list[str] = []
            for pos_attr in ("bull_position", "bear_position", "risk_position"):
                pos = getattr(rnd, pos_attr, None)
                if pos is None:
                    continue
                for eid in getattr(pos, "evidence_ids", []) or []:
                    if eid not in round_eids:
                        round_eids.append(eid)

            rat_id = stable_hash_payload(
                {"type": "debate", "horizon": horizon, "bundle_id": input_bundle.bundle_id},
                length=16,
            )
            confidence: str = "unknown"
            verdict_str = str(verdict)
            if verdict_str in ("bull_favored", "bear_favored"):
                confidence = "medium"
            elif verdict_str == "insufficient_evidence":
                confidence = "insufficient_evidence"

            rationales.append(
                DecisionRationale(
                    rationale_id=f"rat_debate_{rat_id}",
                    source_type="debate",
                    horizon=horizon,  # type: ignore[arg-type]
                    summary=summary,
                    supporting_points=supporting[:10],
                    opposing_points=opposing[:10],
                    evidence_ids=round_eids,
                    confidence=confidence,  # type: ignore[arg-type]
                )
            )

    # 2. HorizonSynthesisReport rationale
    hsr = input_bundle.horizon_synthesis_report
    if hsr is not None:
        cards = getattr(hsr, "cards", []) or []
        for card in cards:
            horizon_raw = (
                getattr(card, "horizon", None) or getattr(card, "bucket", "unknown")
            )
            horizon = horizon_raw if horizon_raw in (
                "short_term", "medium_term", "long_term", "multi_horizon", "unknown"
            ) else "unknown"

            signal = getattr(card, "signal_direction", "unknown")
            confidence_raw = getattr(card, "confidence_level", "unknown")
            confidence = confidence_raw if confidence_raw in (
                "high", "medium", "low", "insufficient_evidence", "unknown"
            ) else "unknown"

            esummary = getattr(card, "evidence_summary", None)
            card_eids = list(
                getattr(esummary, "supporting_evidence_ids", None)
                or getattr(card, "supporting_evidence_ids", None)
                or getattr(card, "evidence_ids", None)
                or getattr(esummary, "evidence_ids", None)
                or []
            )

            summary = (
                f"Horizon synthesis ({horizon}): signal={signal}, "
                f"confidence={confidence}. "
                f"Research summary for {ticker_label}. "
                f"Not investment advice."
            )

            rat_id = stable_hash_payload(
                {"type": "horizon_synthesis", "horizon": horizon, "bundle_id": input_bundle.bundle_id},
                length=16,
            )
            rationales.append(
                DecisionRationale(
                    rationale_id=f"rat_hsyn_{rat_id}",
                    source_type="horizon_synthesis",
                    horizon=horizon,  # type: ignore[arg-type]
                    summary=summary,
                    supporting_points=[],
                    opposing_points=[],
                    evidence_ids=card_eids,
                    confidence=confidence,  # type: ignore[arg-type]
                )
            )

    # 3. MacroAgentResult rationale
    mar = input_bundle.macro_agent_result
    if mar is not None:
        regime_assessment = getattr(mar, "regime_assessment", None)
        regime = (
            getattr(regime_assessment, "regime", None)
            or getattr(regime_assessment, "regime_type", "unknown")
        )
        risk_appetite = getattr(regime_assessment, "risk_appetite", "unknown")
        mar_eids: list[str] = []
        if regime_assessment is not None:
            for eid in getattr(regime_assessment, "supporting_evidence_ids", []) or []:
                if eid not in mar_eids:
                    mar_eids.append(eid)
        for impact in getattr(mar, "horizon_impacts", []) or []:
            impact_eids = (
                getattr(impact, "evidence_ids", None)
                or getattr(impact, "supporting_evidence_ids", None)
                or []
            )
            for eid in impact_eids:
                if eid not in mar_eids:
                    mar_eids.append(eid)
        for bias in getattr(mar, "sector_biases", []) or []:
            bias_eids = (
                getattr(bias, "evidence_ids", None)
                or getattr(bias, "supporting_evidence_ids", None)
                or []
            )
            for eid in bias_eids:
                if eid not in mar_eids:
                    mar_eids.append(eid)

        summary = (
            f"Macro agent assessment: regime={regime}, risk_appetite={risk_appetite}. "
            f"Research context for {ticker_label}. Not investment advice."
        )
        rat_id = stable_hash_payload(
            {"type": "macro_agent", "bundle_id": input_bundle.bundle_id},
            length=16,
        )
        rationales.append(
            DecisionRationale(
                rationale_id=f"rat_macro_{rat_id}",
                source_type="macro_agent",
                horizon="multi_horizon",
                summary=summary,
                supporting_points=[],
                opposing_points=[],
                evidence_ids=mar_eids,
                confidence="unknown",
            )
        )

    # 4. AgentResult rationale
    ar = input_bundle.agent_result
    if ar is not None:
        findings_text: list[str] = []
        ar_eids: list[str] = []
        for finding in getattr(ar, "findings", []) or []:
            ft = getattr(finding, "text", "")
            if ft:
                findings_text.append(ft)
            for eref in getattr(finding, "evidence", []) or []:
                eid = getattr(eref, "evidence_id", None)
                if eid and eid not in ar_eids:
                    ar_eids.append(eid)

        if not findings_text:
            summary = (
                f"Agent result from {getattr(ar, 'agent_name', 'unknown agent')} "
                f"for {ticker_label}. No findings available. Not investment advice."
            )
        else:
            summary = (
                f"Agent result from {getattr(ar, 'agent_name', 'unknown agent')} "
                f"for {ticker_label}: {findings_text[0][:200]}. Not investment advice."
            )

        rat_id = stable_hash_payload(
            {"type": "agent_result", "bundle_id": input_bundle.bundle_id},
            length=16,
        )
        conf_raw = getattr(getattr(ar, "confidence", None), "level", "unknown")
        confidence = conf_raw if conf_raw in (
            "high", "medium", "low", "insufficient_evidence", "unknown"
        ) else "unknown"

        rationales.append(
            DecisionRationale(
                rationale_id=f"rat_agent_{rat_id}",
                source_type="agent_result",
                horizon="unknown",
                summary=summary,
                supporting_points=findings_text[:5],
                opposing_points=[],
                evidence_ids=ar_eids,
                confidence=confidence,  # type: ignore[arg-type]
            )
        )

    # 5. Fallback: no artifacts provided
    if not rationales:
        rat_id = stable_hash_payload(
            {"type": "fallback", "bundle_id": input_bundle.bundle_id},
            length=16,
        )
        rationales.append(
            DecisionRationale(
                rationale_id=f"rat_fallback_{rat_id}",
                source_type="unknown",
                horizon="unknown",
                summary=(
                    f"Insufficient evidence to build a rationale for {ticker_label}. "
                    f"More research artifacts are required."
                ),
                supporting_points=[],
                opposing_points=["No supporting evidence artifacts were provided."],
                evidence_ids=[],
                confidence="insufficient_evidence",
            )
        )

    return rationales


# ---------------------------------------------------------------------------
# Helper: guardrail builder
# ---------------------------------------------------------------------------

def build_decision_guardrails(
    input_bundle: DecisionPacketInputBundle,
    issues: list[DecisionPacketIssue],
) -> list[DecisionGuardrail]:
    """
    Build deterministic guardrails from available artifacts.

    Always includes execution_forbidden guardrail.
    """
    guardrails: list[DecisionGuardrail] = []

    def _make_gid(gtype: str, label: str) -> str:
        h = stable_hash_payload(
            {"gtype": gtype, "label": label, "bundle_id": input_bundle.bundle_id},
            length=16,
        )
        return f"grd_{h}"

    # Group issues by guardrail_type for related_issue_ids
    issues_by_type: dict[str, list[str]] = {}
    for iss in issues:
        issues_by_type.setdefault(iss.guardrail_type, []).append(iss.issue_id)

    # 1. execution_forbidden — always present and always triggered
    guardrails.append(
        DecisionGuardrail(
            guardrail_id=_make_gid("execution_forbidden", "always"),
            guardrail_type="execution_forbidden",
            triggered=True,
            severity="critical",
            message=(
                "This decision packet does not authorize live trading, order placement, "
                "or any buy/sell execution. It is a research and review artifact only."
            ),
            related_issue_ids=[],
        )
    )

    # 2. human_review_required — always present and always triggered
    hr_issue_ids = issues_by_type.get("human_review_required", [])
    guardrails.append(
        DecisionGuardrail(
            guardrail_id=_make_gid("human_review_required", "always"),
            guardrail_type="human_review_required",
            triggered=True,
            severity="critical",
            message=(
                "Human review is required before any execution-related use of this packet."
            ),
            related_issue_ids=hr_issue_ids,
        )
    )

    # 3. validation_failure guardrail — triggered if any validation issues
    va = input_bundle.validation_aggregate
    if va is not None and (va.critical_count > 0 or va.warning_count > 0):
        vf_ids = issues_by_type.get("validation_failure", [])
        triggered = va.critical_count > 0 or bool(vf_ids)
        severity = "critical" if va.critical_count > 0 else "warning"
        guardrails.append(
            DecisionGuardrail(
                guardrail_id=_make_gid("validation_failure", "validation_aggregate"),
                guardrail_type="validation_failure",
                triggered=triggered,
                severity=severity,  # type: ignore[arg-type]
                message=(
                    f"Validation aggregate has {va.critical_count} critical and "
                    f"{va.warning_count} warning items."
                ),
                related_issue_ids=vf_ids,
            )
        )

    # 4. stale_data guardrail
    sr = input_bundle.staleness_report
    if sr is not None:
        stale_ids = issues_by_type.get("stale_data", [])
        stale_count = getattr(sr, "stale_count", None) or 0
        expired_count = getattr(sr, "expired_count", None) or 0
        total_stale = int(stale_count) + int(expired_count)
        if total_stale > 0 or stale_ids:
            severity = "critical" if int(expired_count) > 0 else "warning"
            guardrails.append(
                DecisionGuardrail(
                    guardrail_id=_make_gid("stale_data", "staleness_report"),
                    guardrail_type="stale_data",
                    triggered=True,
                    severity=severity,  # type: ignore[arg-type]
                    message=(
                        f"Staleness report: {stale_count} stale, {expired_count} expired findings."
                    ),
                    related_issue_ids=stale_ids,
                )
            )

    # 5. critic_blocker guardrail
    cr = input_bundle.critic_result
    if cr is not None:
        critic_status = getattr(cr, "status", "unknown")
        critic_ids = issues_by_type.get("critic_blocker", [])
        critic_crit = getattr(cr, "critical_count", 0) or 0
        if critic_status == "fail" or int(critic_crit) > 0 or critic_ids:
            guardrails.append(
                DecisionGuardrail(
                    guardrail_id=_make_gid("critic_blocker", "critic_result"),
                    guardrail_type="critic_blocker",
                    triggered=True,
                    severity="critical" if int(critic_crit) > 0 else "warning",  # type: ignore[arg-type]
                    message=(
                        f"Critic result status: {critic_status} with {critic_crit} critical issues."
                    ),
                    related_issue_ids=critic_ids,
                )
            )

    # 6. debate_unresolved guardrail
    dr = input_bundle.debate_report
    if dr is not None:
        debate_status = getattr(dr, "status", "unknown")
        debate_rec = getattr(dr, "recommendation", "unknown")
        du_ids = issues_by_type.get("debate_unresolved", [])
        # Trigger if any round is insufficient_evidence / fail, or recommendation is not proceed
        rounds = getattr(dr, "rounds", []) or []
        any_insufficient = any(
            getattr(r, "status", "unknown") in ("fail", "insufficient_evidence")
            for r in rounds
        )
        if any_insufficient or debate_status in ("fail", "insufficient_evidence") or du_ids:
            severity = "critical" if debate_status == "fail" else "warning"
            guardrails.append(
                DecisionGuardrail(
                    guardrail_id=_make_gid("debate_unresolved", "debate_report"),
                    guardrail_type="debate_unresolved",
                    triggered=True,
                    severity=severity,  # type: ignore[arg-type]
                    message=(
                        f"Debate report status: {debate_status}, recommendation: {debate_rec}. "
                        f"Some rounds may have insufficient evidence or unresolved questions."
                    ),
                    related_issue_ids=du_ids,
                )
            )

    # 7. missing_risk guardrail
    mr_ids = issues_by_type.get("missing_risk", [])
    if mr_ids:
        guardrails.append(
            DecisionGuardrail(
                guardrail_id=_make_gid("missing_risk", "issues"),
                guardrail_type="missing_risk",
                triggered=True,
                severity="warning",
                message=f"Missing risk items detected: {len(mr_ids)} issue(s).",
                related_issue_ids=mr_ids,
            )
        )

    # 8. missing_assumption guardrail
    ma_ids = issues_by_type.get("missing_assumption", [])
    if ma_ids:
        guardrails.append(
            DecisionGuardrail(
                guardrail_id=_make_gid("missing_assumption", "issues"),
                guardrail_type="missing_assumption",
                triggered=True,
                severity="warning",
                message=f"Missing assumption items detected: {len(ma_ids)} issue(s).",
                related_issue_ids=ma_ids,
            )
        )

    # 9. conflicting_evidence guardrail
    ce_ids = issues_by_type.get("conflicting_evidence", [])
    if ce_ids:
        guardrails.append(
            DecisionGuardrail(
                guardrail_id=_make_gid("conflicting_evidence", "issues"),
                guardrail_type="conflicting_evidence",
                triggered=True,
                severity="warning",
                message=f"Conflicting evidence detected: {len(ce_ids)} issue(s).",
                related_issue_ids=ce_ids,
            )
        )

    # 10. overconfidence guardrail
    oc_ids = issues_by_type.get("overconfidence", [])
    if oc_ids:
        guardrails.append(
            DecisionGuardrail(
                guardrail_id=_make_gid("overconfidence", "issues"),
                guardrail_type="overconfidence",
                triggered=True,
                severity="warning",
                message=f"Overconfidence detected: {len(oc_ids)} issue(s).",
                related_issue_ids=oc_ids,
            )
        )

    # 11. insufficient_evidence guardrail
    ie_ids = issues_by_type.get("insufficient_evidence", [])
    no_evidence = (
        not input_bundle.tool_results
        and input_bundle.agent_result is None
        and input_bundle.debate_report is None
        and input_bundle.horizon_synthesis_report is None
        and input_bundle.macro_agent_result is None
    )
    if ie_ids or no_evidence:
        guardrails.append(
            DecisionGuardrail(
                guardrail_id=_make_gid("insufficient_evidence", "bundle"),
                guardrail_type="insufficient_evidence",
                triggered=True,
                severity="warning",
                message=(
                    "Insufficient evidence: no supporting artifacts or evidence IDs available."
                    if no_evidence
                    else f"Insufficient evidence items: {len(ie_ids)} issue(s)."
                ),
                related_issue_ids=ie_ids,
            )
        )

    return guardrails


# ---------------------------------------------------------------------------
# Helper: action draft builder
# ---------------------------------------------------------------------------

def build_decision_action_draft(
    status: str,
    recommendation: str,
    guardrails: list[DecisionGuardrail],
    evidence_ids: list[str],
    ticker: Optional[str] = None,
) -> DecisionActionDraft:
    """
    Build a deterministic research/review action draft.

    Allowed action types only — no live trading, orders, or execution.
    """
    h = stable_hash_payload(
        {
            "status": status,
            "recommendation": recommendation,
            "triggered_guardrail_types": sorted(
                g.guardrail_type for g in guardrails if g.triggered
            ),
        },
        length=16,
    )
    action_id = f"action_{h}"

    # Determine action type from status/recommendation
    has_critical = any(
        g.triggered and g.severity == "critical"
        and g.guardrail_type not in ("execution_forbidden", "human_review_required")
        for g in guardrails
    )
    has_insufficient = any(
        g.triggered and g.guardrail_type == "insufficient_evidence"
        for g in guardrails
    )
    has_debate_unresolved = any(
        g.triggered and g.guardrail_type == "debate_unresolved"
        for g in guardrails
    )

    if status in ("fail", "blocked"):
        action_type: str = "reject"
    elif status == "insufficient_evidence" or has_insufficient:
        action_type = "needs_more_research"
    elif has_critical or has_debate_unresolved:
        action_type = "human_review_required"
    elif status == "pass_with_warnings":
        action_type = "prepare_scenario_plan"
    elif status == "pass":
        action_type = "prepare_scenario_plan"
    else:
        action_type = "monitor"

    ticker_label = ticker or "the subject"

    allowed_next_steps = [
        f"Review research artifacts for {ticker_label}.",
        "Escalate to human analyst for review.",
        "Gather additional evidence to address open issues.",
        "Monitor for updated data before proceeding.",
        "Archive this decision packet for audit purposes.",
    ]

    if action_type == "prepare_scenario_plan":
        allowed_next_steps.insert(0, f"Prepare scenario analysis for {ticker_label}.")
    elif action_type == "needs_more_research":
        allowed_next_steps.insert(0, "Collect additional data and re-run synthesis.")
    elif action_type == "reject":
        allowed_next_steps = [
            "Document rejection rationale.",
            "Archive this decision packet for audit purposes.",
            "Do not proceed further without additional review.",
        ]

    description = (
        f"Research/review action for {ticker_label}: "
        f"action_type={action_type}, status={status}. "
        f"This packet does not authorize trading or execution."
    )

    return DecisionActionDraft(
        action_id=action_id,
        action_type=action_type,  # type: ignore[arg-type]
        horizon="unknown",
        description=description,
        allowed_next_steps=allowed_next_steps,
        prohibited_actions=list(_PROHIBITED_LIVE_TRADING),
        requires_human_review=True,
    )


# ---------------------------------------------------------------------------
# Helper: review requirement builder
# ---------------------------------------------------------------------------

def build_review_requirements(
    guardrails: list[DecisionGuardrail],
    issues: list[DecisionPacketIssue],
) -> list[DecisionReviewRequirement]:
    """
    Build human review requirements from triggered guardrails.

    Always includes a baseline review requirement for execution-related use.
    """
    requirements: list[DecisionReviewRequirement] = []

    def _make_rid(gtype: str, label: str) -> str:
        h = stable_hash_payload({"gtype": gtype, "label": label}, length=16)
        return f"rev_{h}"

    # 1. Baseline: always require human review before execution-related use
    requirements.append(
        DecisionReviewRequirement(
            review_id=_make_rid("baseline", "always_required"),
            review_status="review_required",
            required=True,
            reason=(
                "Human review is always required before any execution-related use "
                "of this decision packet. It is a research artifact only."
            ),
            reviewer_role="human_analyst",
            related_guardrail_ids=[
                g.guardrail_id
                for g in guardrails
                if g.guardrail_type in ("execution_forbidden", "human_review_required")
            ],
        )
    )

    # 2. Per triggered guardrail (excluding execution_forbidden and human_review_required
    #    which are already covered by the baseline)
    skip_types = {"execution_forbidden", "human_review_required"}
    for g in guardrails:
        if not g.triggered:
            continue
        if g.guardrail_type in skip_types:
            continue

        reason_map: dict[str, str] = {
            "validation_failure": "Validation failures must be reviewed and resolved.",
            "stale_data": "Stale or expired data must be refreshed before further use.",
            "critic_blocker": "Critic has flagged blocking issues that require review.",
            "debate_unresolved": "Debate has unresolved questions that require human judgment.",
            "missing_risk": "Missing risk items must be assessed by a human analyst.",
            "missing_assumption": "Missing assumptions must be reviewed and documented.",
            "conflicting_evidence": "Conflicting evidence must be reconciled.",
            "overconfidence": "Overconfidence detected; human calibration required.",
            "insufficient_evidence": "Insufficient evidence; additional data collection required.",
            "other": "Guardrail triggered; human review required.",
        }
        reason = reason_map.get(g.guardrail_type, "Guardrail triggered; human review required.")

        requirements.append(
            DecisionReviewRequirement(
                review_id=_make_rid(g.guardrail_type, g.guardrail_id),
                review_status="review_required",
                required=True,
                reason=reason,
                reviewer_role="human_analyst",
                related_guardrail_ids=[g.guardrail_id],
            )
        )

    return requirements


# ---------------------------------------------------------------------------
# Helper: status/recommendation/confidence normalizer
# ---------------------------------------------------------------------------

def _normalize_status_recommendation_confidence(
    guardrails: list[DecisionGuardrail],
    issues: list[DecisionPacketIssue],
    evidence_ids: list[str],
) -> tuple[str, str, str]:
    """
    Derive DecisionPacketStatus, DecisionRecommendation, DecisionConfidence.

    Returns (status, recommendation, confidence).
    """
    triggered = [g for g in guardrails if g.triggered]

    has_critical = any(
        g.severity == "critical"
        and g.guardrail_type not in ("execution_forbidden", "human_review_required")
        for g in triggered
    )
    has_blocking_critical = any(
        g.severity == "critical"
        and g.guardrail_type in ("validation_failure", "critic_blocker")
        for g in triggered
    )
    has_insufficient = any(g.guardrail_type == "insufficient_evidence" for g in triggered)
    has_warnings = any(
        g.severity == "warning"
        and g.guardrail_type not in ("execution_forbidden", "human_review_required")
        for g in triggered
    )

    no_evidence = not evidence_ids

    if has_blocking_critical:
        status = "blocked"
    elif has_critical:
        status = "fail"
    elif no_evidence or has_insufficient:
        status = "insufficient_evidence"
    elif has_warnings:
        status = "pass_with_warnings"
    else:
        status = "pass"

    # Recommendation from status
    action_type = None
    if status in ("fail", "blocked"):
        recommendation = "reject"
    elif status == "insufficient_evidence":
        recommendation = "needs_more_evidence"
    elif status == "pass_with_warnings":
        recommendation = "revise"
    elif status == "pass":
        recommendation = "accept_for_research"
    else:
        recommendation = "unknown"

    # Confidence from evidence and issues
    critical_count = sum(1 for i in issues if i.severity == "critical")
    warning_count = sum(1 for i in issues if i.severity == "warning")

    if no_evidence:
        confidence = "insufficient_evidence"
    elif critical_count > 0:
        confidence = "low"
    elif warning_count > 3:
        confidence = "low"
    elif warning_count > 0:
        confidence = "medium"
    elif status == "pass":
        confidence = "medium"
    else:
        confidence = "unknown"

    return status, recommendation, confidence


# ---------------------------------------------------------------------------
# Main builder: build_decision_packet
# ---------------------------------------------------------------------------

def build_decision_packet(
    decision_packet_id: str,
    as_of: str,
    ticker: Optional[str] = None,
    rationales: Optional[list[DecisionRationale]] = None,
    guardrails: Optional[list[DecisionGuardrail]] = None,
    review_requirements: Optional[list[DecisionReviewRequirement]] = None,
    issues: Optional[list[DecisionPacketIssue]] = None,
    primary_action: Optional[DecisionActionDraft] = None,
    source_ids: Optional[dict[str, str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    evidence_ids: Optional[list[str]] = None,
) -> DecisionPacket:
    """
    Build a normalized DecisionPacket from assembled components.

    Does not mutate inputs.
    """
    _rationales = list(rationales or [])
    _guardrails = list(guardrails or [])
    _review_requirements = list(review_requirements or [])
    _issues = list(issues or [])
    _source_ids = dict(source_ids or {})
    _metadata = dict(metadata or {})
    _evidence_ids = list(evidence_ids or [])

    status, recommendation, confidence = _normalize_status_recommendation_confidence(
        _guardrails, _issues, _evidence_ids
    )

    return DecisionPacket(
        decision_packet_id=decision_packet_id,
        as_of=as_of,
        ticker=ticker,
        status=status,  # type: ignore[arg-type]
        recommendation=recommendation,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        primary_action=primary_action,
        rationales=_rationales,
        guardrails=_guardrails,
        review_requirements=_review_requirements,
        issues=_issues,
        source_ids=_source_ids,
        metadata=_metadata,
    )


# ---------------------------------------------------------------------------
# Main synthesis entry point
# ---------------------------------------------------------------------------

def run_decision_packet_synthesis(
    input_bundle: DecisionPacketInputBundle,
) -> DecisionPacket:
    """
    Run deterministic decision packet synthesis from an input bundle.

    Produces a DecisionPacket that aggregates issues, rationales, guardrails,
    action drafts, and review requirements from all available reliability
    artifacts.

    Offline, deterministic, no LLM, no APIs, no mutation, no investment advice.
    """
    # 1. Extract evidence IDs
    evidence_ids = extract_decision_evidence_ids(input_bundle)

    # 2. Convert validation items → issues
    issues: list[DecisionPacketIssue] = []
    if input_bundle.validation_aggregate is not None:
        for item in input_bundle.validation_aggregate.items:
            issues.append(issue_from_validation_item_for_decision(item))

    # 3. Convert staleness findings → issues
    if input_bundle.staleness_report is not None:
        for finding in input_bundle.staleness_report.findings:
            if finding.status in ("stale", "expired", "near_stale", "unknown"):
                issues.append(issue_from_staleness_finding_for_decision(finding))

    # 4. Convert critic issues → issues
    if input_bundle.critic_result is not None:
        for ci in input_bundle.critic_result.issues:
            issues.append(issue_from_critic_issue_for_decision(ci))

    # 5. Convert debate issues → issues
    if input_bundle.debate_report is not None:
        for rnd in getattr(input_bundle.debate_report, "rounds", []) or []:
            for di in getattr(rnd, "issues", []) or []:
                issues.append(issue_from_debate_issue_for_decision(di))
        for di in getattr(input_bundle.debate_report, "issues", []) or []:
            issues.append(issue_from_debate_issue_for_decision(di))

    # Deduplicate issues by issue_id
    seen_issue_ids: set[str] = set()
    unique_issues: list[DecisionPacketIssue] = []
    for iss in issues:
        if iss.issue_id not in seen_issue_ids:
            seen_issue_ids.add(iss.issue_id)
            unique_issues.append(iss)
    issues = unique_issues

    # 6. Build rationales
    rationales = build_decision_rationales(input_bundle, evidence_ids)

    # 7. Build guardrails
    guardrails = build_decision_guardrails(input_bundle, issues)

    # 8. Normalize status/recommendation/confidence
    status, recommendation, confidence = _normalize_status_recommendation_confidence(
        guardrails, issues, evidence_ids
    )

    # 9. Build action draft
    primary_action = build_decision_action_draft(
        status=status,
        recommendation=recommendation,
        guardrails=guardrails,
        evidence_ids=evidence_ids,
        ticker=input_bundle.ticker,
    )

    # 10. Build review requirements
    review_requirements = build_review_requirements(guardrails, issues)

    # 11. Build source_ids from available artifacts
    source_ids: dict[str, str] = {}
    if input_bundle.debate_report is not None:
        did = getattr(input_bundle.debate_report, "debate_id", None) or "debate"
        source_ids["debate_report"] = str(did)
    if input_bundle.horizon_synthesis_report is not None:
        hid = getattr(input_bundle.horizon_synthesis_report, "synthesis_id", None) or "horizon_synthesis"
        source_ids["horizon_synthesis_report"] = str(hid)
    if input_bundle.macro_agent_result is not None:
        mid = getattr(input_bundle.macro_agent_result, "macro_agent_id", None)
        mid = mid or getattr(input_bundle.macro_agent_result, "result_id", None)
        mid = mid or "macro_agent"
        source_ids["macro_agent_result"] = str(mid)
    if input_bundle.orchestration_report is not None:
        oid = getattr(input_bundle.orchestration_report, "orchestration_id", None)
        oid = oid or getattr(input_bundle.orchestration_report, "report_id", None)
        oid = oid or "orchestration"
        source_ids["orchestration_report"] = str(oid)
    if input_bundle.validation_aggregate is not None:
        source_ids["validation_aggregate"] = input_bundle.validation_aggregate.aggregate_id
    if input_bundle.staleness_report is not None:
        source_ids["staleness_report"] = input_bundle.staleness_report.report_id
    if input_bundle.critic_result is not None:
        source_ids["critic_result"] = input_bundle.critic_result.critic_id
    if input_bundle.reliability_score_summary is not None:
        score_id = getattr(input_bundle.reliability_score_summary, "score_id", None)
        score_id = score_id or getattr(input_bundle.reliability_score_summary, "summary_id", None)
        if score_id:
            source_ids["reliability_score_summary"] = str(score_id)
    if input_bundle.agent_result is not None:
        source_ids["agent_result"] = getattr(input_bundle.agent_result, "run_id", "agent_result")

    # 12. Build decision_packet_id
    packet_id = make_decision_packet_id(
        bundle_id=input_bundle.bundle_id,
        as_of=input_bundle.as_of,
        ticker=input_bundle.ticker,
    )

    return DecisionPacket(
        decision_packet_id=packet_id,
        as_of=input_bundle.as_of,
        ticker=input_bundle.ticker,
        status=status,  # type: ignore[arg-type]
        recommendation=recommendation,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        primary_action=primary_action,
        rationales=rationales,
        guardrails=guardrails,
        review_requirements=review_requirements,
        issues=issues,
        source_ids=source_ids,
        metadata={},
    )


# ---------------------------------------------------------------------------
# ToolResult wrapper
# ---------------------------------------------------------------------------

def summarize_decision_packet(packet: DecisionPacket) -> dict[str, Any]:
    """Return a summary dict for a DecisionPacket."""
    critical_count = sum(1 for i in packet.issues if i.severity == "critical")
    warning_count = sum(1 for i in packet.issues if i.severity == "warning")
    info_count = sum(1 for i in packet.issues if i.severity == "info")

    triggered_guardrails = [
        g.guardrail_type for g in packet.guardrails if g.triggered
    ]

    top_messages = [i.message for i in packet.issues[:10]]

    return {
        "decision_packet_id": packet.decision_packet_id,
        "ticker": packet.ticker,
        "status": packet.status,
        "recommendation": packet.recommendation,
        "confidence": packet.confidence,
        "primary_action_type": (
            packet.primary_action.action_type if packet.primary_action else None
        ),
        "rationale_count": len(packet.rationales),
        "guardrail_count": len(packet.guardrails),
        "review_requirement_count": len(packet.review_requirements),
        "issue_count": len(packet.issues),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "triggered_guardrails": triggered_guardrails,
        "top_messages": top_messages,
    }


def decision_packet_tool_result_from_packet(
    run_id: str,
    packet: DecisionPacket,
    target: Optional[str] = None,
    calculation_version: str = "decision_packet_skeleton_v1",
) -> ToolResult:
    """
    Wrap a DecisionPacket into a ToolResult for evidence-chain storage.

    evidence_id is content-sensitive: same packet payload → same ID.
    tool_name is stable: "decision_packet".
    """
    _target = target or packet.ticker or "decision_packet"

    packet_payload = packet.model_dump()
    summary = summarize_decision_packet(packet)

    outputs: dict[str, Any] = {
        "packet": packet_payload,
        "summary": summary,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_DECISION_PACKET_TOOL_NAME,
        target=_target,
        metric_group=_DECISION_PACKET_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_DECISION_PACKET_TOOL_NAME,
        run_id=run_id,
        ticker=packet.ticker,
        inputs={"bundle_ticker": packet.ticker, "as_of": packet.as_of},
        outputs=outputs,
        description=(
            f"DecisionPacket for {packet.ticker or 'unknown'}: "
            f"status={packet.status}, recommendation={packet.recommendation}."
        ),
    )
