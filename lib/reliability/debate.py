"""
lib/reliability/debate.py

Phase 3D: Debate by Horizon Skeleton.

Design principles:
  - Standalone, deterministic, offline.
  - No live LLM calls, no live data fetching, no app integration.
  - Consumes Phase 3A-3C reliability artifacts and produces structured
    per-horizon debate outputs (short_term / medium_term / long_term).
  - Each horizon round has bull / bear / risk positions.
  - Verdict and status are derived from deterministic rules.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell recommendations, or
    individual security recommendations.
  - Mock/dry-run only; all outputs are explicitly evidence-aware.
  - All rule-based inference is conservative; unknown/no_decision is acceptable.

See docs/reliability_phase_3d_debate_by_horizon_skeleton.md for design.

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

DebateRole = Literal[
    "bull",
    "bear",
    "risk",
    "neutral",
    "unknown",
]

DebateStatus = Literal[
    "pass",
    "pass_with_warnings",
    "fail",
    "insufficient_evidence",
    "unknown",
]

DebateVerdict = Literal[
    "bull_favored",
    "bear_favored",
    "risk_dominant",
    "mixed",
    "insufficient_evidence",
    "no_decision",
    "unknown",
]

DebateRecommendation = Literal[
    "proceed_to_decision_packet",
    "revise",
    "reject",
    "needs_more_evidence",
    "no_action",
    "unknown",
]

DebateIssueType = Literal[
    "unsupported_claim",
    "stale_evidence",
    "missing_evidence",
    "validation_issue",
    "critic_issue",
    "conflicting_evidence",
    "missing_risk",
    "missing_assumption",
    "overconfidence",
    "horizon_mismatch",
    "unresolved_question",
    "other",
]

DebateClaimType = Literal[
    "thesis",
    "counterargument",
    "risk",
    "assumption",
    "evidence_gap",
    "unresolved_question",
    "other",
]

DebateHorizon = Literal[
    "short_term",
    "medium_term",
    "long_term",
]

DebateIssueSeverity = Literal["critical", "warning", "info"]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_DEBATE_TOOL_NAME: str = "debate_report"
_DEBATE_METRIC_GROUP: str = "debate_report"

# DebateIssueType values that count toward risk-dominant verdict
_RISK_DOMINANT_ISSUE_TYPES: frozenset[str] = frozenset({
    "missing_risk",
    "stale_evidence",
    "missing_evidence",
    "overconfidence",
    "conflicting_evidence",
    "missing_assumption",
})

# ValidationItemType → DebateIssueType
_VALIDATION_TYPE_MAP: dict[str, str] = {
    "stale_data": "stale_evidence",
    "missing_data": "missing_evidence",
    "evidence_binding": "unsupported_claim",
    "unsupported": "unsupported_claim",
    "risk_limit": "missing_risk",
    "safety": "critic_issue",
    "schema": "validation_issue",
    "mismatch": "conflicting_evidence",
    "duplicate_data": "other",
    "calculation": "validation_issue",
    "provenance": "missing_evidence",
    "other": "other",
}

# StalenessStatus → DebateIssueType
_STALENESS_STATUS_MAP: dict[str, str] = {
    "stale": "stale_evidence",
    "expired": "stale_evidence",
    "near_stale": "stale_evidence",
    "unknown": "missing_evidence",
    "fresh": "other",
}

# CriticIssueType → DebateIssueType
_CRITIC_TYPE_MAP: dict[str, str] = {
    "missing_risk": "missing_risk",
    "missing_assumption": "missing_assumption",
    "conflicting_evidence": "conflicting_evidence",
    "stale_evidence": "stale_evidence",
    "unsupported_claim": "unsupported_claim",
    "overconfidence": "overconfidence",
    "weak_evidence": "missing_evidence",
    "validation_failure": "validation_issue",
    "numeric_claim_issue": "unsupported_claim",
    "scope_violation": "other",
    "safety_concern": "critic_issue",
    "other": "other",
}

# Fixed round order for run_debate_by_horizon
_HORIZON_ORDER: list[DebateHorizon] = ["short_term", "medium_term", "long_term"]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DebateIssue(BaseModel):
    """One structured issue raised during a debate round or position review."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1)
    issue_type: DebateIssueType
    severity: DebateIssueSeverity = "warning"
    horizon: Optional[DebateHorizon] = None
    role: Optional[DebateRole] = None
    message: str = Field(min_length=1)
    related_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DebateIssue":
        for fn in ("issue_id", "message"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class DebateClaim(BaseModel):
    """One claim made by a debate participant (bull / bear / risk / neutral)."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    claim_type: DebateClaimType
    role: DebateRole
    horizon: DebateHorizon
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    issues: list[DebateIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DebateClaim":
        for fn in ("claim_id", "text"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class DebatePosition(BaseModel):
    """
    Position taken by one debate role (bull / bear / risk) for one horizon.

    No investment recommendation language is permitted.
    """

    model_config = ConfigDict(extra="forbid")

    position_id: str = Field(min_length=1)
    role: DebateRole
    horizon: DebateHorizon
    summary: str = Field(min_length=1)
    claims: list[DebateClaim] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    issues: list[DebateIssue] = Field(default_factory=list)
    confidence: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DebatePosition":
        for fn in ("position_id", "summary"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class DebateRound(BaseModel):
    """
    One full debate round for a specific investment horizon.

    Status and verdict are auto-normalised from issues and position evidence.

    Status normalisation:
      - fail               if any critical issue exists.
      - insufficient_evidence if no position holds supporting evidence IDs.
      - pass_with_warnings if warning issues or evidence_gaps are present.
      - pass               otherwise.

    Verdict normalisation:
      - insufficient_evidence if no position holds evidence IDs.
      - risk_dominant         if ≥ 50 % of issues are risk-type.
      - mixed                 if bull and bear both have claims AND evidence.
      - no_decision           otherwise (conservative default).
    """

    model_config = ConfigDict(extra="forbid")

    round_id: str = Field(min_length=1)
    horizon: DebateHorizon
    bull_position: Optional[DebatePosition] = None
    bear_position: Optional[DebatePosition] = None
    risk_position: Optional[DebatePosition] = None
    unresolved_questions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    issues: list[DebateIssue] = Field(default_factory=list)
    verdict: DebateVerdict = "unknown"
    status: DebateStatus = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DebateRound":
        if not self.round_id.strip():
            raise ValueError("'round_id' must not be whitespace-only.")
        return self

    @model_validator(mode="after")
    def _normalize_round(self) -> "DebateRound":
        has_position_evidence = (
            (self.bull_position is not None and bool(self.bull_position.evidence_ids))
            or (self.bear_position is not None and bool(self.bear_position.evidence_ids))
            or (self.risk_position is not None and bool(self.risk_position.evidence_ids))
        )

        critical_count = sum(1 for i in self.issues if i.severity == "critical")
        warning_count = sum(1 for i in self.issues if i.severity == "warning")

        # --- Status ---
        if critical_count > 0:
            self.status = "fail"
        elif not has_position_evidence:
            self.status = "insufficient_evidence"
        elif warning_count > 0 or bool(self.evidence_gaps):
            self.status = "pass_with_warnings"
        else:
            self.status = "pass"

        # --- Verdict ---
        risk_count = sum(
            1 for i in self.issues if i.issue_type in _RISK_DOMINANT_ISSUE_TYPES
        )
        total_issues = len(self.issues)

        has_bull_claims = self.bull_position is not None and bool(self.bull_position.claims)
        has_bear_claims = self.bear_position is not None and bool(self.bear_position.claims)
        has_bull_evidence = self.bull_position is not None and bool(self.bull_position.evidence_ids)
        has_bear_evidence = self.bear_position is not None and bool(self.bear_position.evidence_ids)

        if not has_position_evidence:
            self.verdict = "insufficient_evidence"
        elif risk_count > 0 and (total_issues == 0 or risk_count >= total_issues * 0.5):
            self.verdict = "risk_dominant"
        elif has_bull_claims and has_bull_evidence and has_bear_claims and has_bear_evidence:
            self.verdict = "mixed"
        else:
            self.verdict = "no_decision"

        return self


class DebateReport(BaseModel):
    """
    Full structured debate report spanning short / medium / long horizons.

    Status, recommendation, and issues are auto-normalised from rounds.

    Normalisation:
      - Aggregates round issues (deduped by issue_id) into report issues.
      - fail               if any round fails or any critical issue exists.
      - insufficient_evidence if all rounds are insufficient / unknown.
      - pass_with_warnings if any round has warnings.
      - pass               otherwise.
      - recommendation follows status.

    No investment advice. No buy/sell language.
    """

    model_config = ConfigDict(extra="forbid")

    debate_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    status: DebateStatus = "unknown"
    recommendation: DebateRecommendation = "unknown"
    rounds: list[DebateRound] = Field(default_factory=list)
    issues: list[DebateIssue] = Field(default_factory=list)
    horizon_synthesis_report_id: Optional[str] = None
    macro_agent_result_id: Optional[str] = None
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    reliability_score_summary: Optional[ReliabilityScoreSummary] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DebateReport":
        for fn in ("debate_id", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _normalize_report(self) -> "DebateReport":
        # Aggregate round issues (deduped by issue_id)
        existing_ids: set[str] = {i.issue_id for i in self.issues}
        extra_issues: list[DebateIssue] = []
        for r in self.rounds:
            for i in r.issues:
                if i.issue_id not in existing_ids:
                    extra_issues.append(i)
                    existing_ids.add(i.issue_id)
        if extra_issues:
            self.issues = list(self.issues) + extra_issues

        all_issues = self.issues
        round_statuses = [r.status for r in self.rounds]

        has_fail = any(s == "fail" for s in round_statuses) or any(
            i.severity == "critical" for i in all_issues
        )
        has_warnings = any(s == "pass_with_warnings" for s in round_statuses) or any(
            i.severity == "warning" for i in all_issues
        )
        all_insufficient = len(round_statuses) > 0 and all(
            s in ("insufficient_evidence", "unknown") for s in round_statuses
        )

        if has_fail:
            self.status = "fail"
            self.recommendation = "reject"
        elif all_insufficient:
            self.status = "insufficient_evidence"
            self.recommendation = "needs_more_evidence"
        elif has_warnings:
            self.status = "pass_with_warnings"
            self.recommendation = "revise"
        else:
            self.status = "pass"
            self.recommendation = "proceed_to_decision_packet"

        return self


class DebateInputBundle(BaseModel):
    """
    Input bundle for the Debate by Horizon skeleton.

    Accepts duck-typed horizon_synthesis_report and macro_agent_result
    so this module does not create a circular import with their modules.
    Does not mutate nested objects.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    horizon_synthesis_report: Optional[Any] = None
    macro_agent_result: Optional[Any] = None
    agent_result: Optional[AgentResult] = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    reliability_score_summary: Optional[ReliabilityScoreSummary] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "DebateInputBundle":
        for fn in ("bundle_id", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


# ---------------------------------------------------------------------------
# Helper: ID generation
# ---------------------------------------------------------------------------

def make_debate_issue_id(
    issue_type: str,
    message: str,
    horizon: Optional[str] = None,
    role: Optional[str] = None,
    related_id: Optional[str] = None,
    evidence_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> str:
    """
    Build a deterministic, stable issue_id for a DebateIssue.

    Same inputs → same ID. Any changed field → different ID.
    """
    payload = {
        "issue_type": issue_type,
        "message": message,
        "horizon": horizon or "",
        "role": role or "",
        "related_id": related_id or "",
        "evidence_id": evidence_id or "",
        "field_path": field_path or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    return f"debate_issue:{issue_type}:{hash_suffix}"


def make_debate_id(
    bundle_id: str,
    as_of: str,
    ticker: Optional[str] = None,
) -> str:
    """Build a deterministic, stable debate_id, position_id, or round_id."""
    payload = {
        "bundle_id": bundle_id,
        "as_of": as_of,
        "ticker": ticker or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    ticker_part = f":{ticker}" if ticker else ""
    return f"debate:{bundle_id}{ticker_part}:{hash_suffix}"


# ---------------------------------------------------------------------------
# Helper: Evidence extraction
# ---------------------------------------------------------------------------

def extract_debate_evidence_ids(
    input_bundle: DebateInputBundle,
    horizon: Optional[str] = None,
) -> list[str]:
    """
    Collect evidence IDs from all available artifacts in the input bundle.

    If horizon is provided, horizon-specific evidence from the synthesis
    report is listed first.
    Deterministic order. Does not invent evidence. Does not mutate inputs.
    """
    ids: list[str] = []
    seen: set[str] = set()

    def _add(eid: Optional[str]) -> None:
        if eid and eid not in seen:
            ids.append(eid)
            seen.add(eid)

    # Horizon-specific evidence first (from HorizonSynthesisReport card)
    if horizon is not None and input_bundle.horizon_synthesis_report is not None:
        hsr = input_bundle.horizon_synthesis_report
        for card in getattr(hsr, "cards", []) or []:
            # Preferred Phase 3B field: card.horizon; fallback: card.bucket
            card_horizon = getattr(card, "horizon", None) or getattr(card, "bucket", None)
            if card_horizon == horizon:
                esummary = getattr(card, "evidence_summary", None)
                # Preferred Phase 3B field: supporting_evidence_ids; fallback: evidence_ids
                card_eids = (
                    getattr(esummary, "supporting_evidence_ids", None)
                    or getattr(esummary, "evidence_ids", None)
                    or []
                )
                for eid in card_eids:
                    _add(eid)

    # ToolResults
    for tr in input_bundle.tool_results:
        _add(tr.evidence_id)

    # AgentResult evidence refs (findings + risks)
    if input_bundle.agent_result is not None:
        ar = input_bundle.agent_result
        for finding in getattr(ar, "findings", []) or []:
            for eref in getattr(finding, "evidence", []) or []:
                _add(getattr(eref, "evidence_id", None))
        for risk in getattr(ar, "risks", []) or []:
            for eref in getattr(risk, "evidence", []) or []:
                _add(getattr(eref, "evidence_id", None))

    # HorizonSynthesisReport all cards
    if input_bundle.horizon_synthesis_report is not None:
        hsr = input_bundle.horizon_synthesis_report
        for card in getattr(hsr, "cards", []) or []:
            esummary = getattr(card, "evidence_summary", None)
            # Preferred Phase 3B field: supporting_evidence_ids; fallback: evidence_ids
            card_eids = (
                getattr(esummary, "supporting_evidence_ids", None)
                or getattr(esummary, "evidence_ids", None)
                or []
            )
            for eid in card_eids:
                _add(eid)

    # MacroAgentResult supporting evidence
    if input_bundle.macro_agent_result is not None:
        mar = input_bundle.macro_agent_result
        regime = getattr(mar, "regime_assessment", None)
        if regime:
            for eid in getattr(regime, "supporting_evidence_ids", []) or []:
                _add(eid)
        for hi in getattr(mar, "horizon_impacts", []) or []:
            for eid in getattr(hi, "evidence_ids", []) or []:
                _add(eid)
        for sb in getattr(mar, "sector_biases", []) or []:
            for eid in getattr(sb, "evidence_ids", []) or []:
                _add(eid)

    return ids


# ---------------------------------------------------------------------------
# Helper: Issue conversion
# ---------------------------------------------------------------------------

def issue_from_validation_item_for_debate(
    item: AggregatedValidationItem,
    horizon: Optional[DebateHorizon] = None,
    role: Optional[DebateRole] = None,
) -> DebateIssue:
    """
    Convert an AggregatedValidationItem into a DebateIssue.

    Preserves evidence_id, field_path, object_id as related_id.
    Maps ValidationItemType → DebateIssueType:
      stale_data           → stale_evidence
      missing_data         → missing_evidence
      evidence_binding     → unsupported_claim
      unsupported          → unsupported_claim
      risk_limit           → missing_risk
      safety               → critic_issue
      schema / calculation → validation_issue
      mismatch             → conflicting_evidence
      provenance           → missing_evidence
    """
    issue_type: str = _VALIDATION_TYPE_MAP.get(item.item_type, "other")

    severity: DebateIssueSeverity
    if item.severity == "critical":
        severity = "critical"
    elif item.severity == "info":
        severity = "info"
    else:
        severity = "warning"

    issue_id = make_debate_issue_id(
        issue_type=issue_type,
        message=item.message,
        horizon=horizon,
        role=role,
        related_id=item.object_id,
        evidence_id=item.evidence_id,
        field_path=item.field_path,
    )
    return DebateIssue(
        issue_id=issue_id,
        issue_type=issue_type,  # type: ignore[arg-type]
        severity=severity,
        horizon=horizon,
        role=role,
        message=item.message,
        related_id=item.object_id,
        evidence_id=item.evidence_id,
        field_path=item.field_path,
    )


def issue_from_staleness_finding_for_debate(
    finding: StalenessFinding,
    horizon: Optional[DebateHorizon] = None,
    role: Optional[DebateRole] = None,
) -> DebateIssue:
    """
    Convert a StalenessFinding into a DebateIssue.

    stale / expired / near_stale → stale_evidence
    unknown timestamp             → missing_evidence
    """
    issue_type: str = _STALENESS_STATUS_MAP.get(finding.status, "other")

    severity: DebateIssueSeverity
    if finding.severity == "critical":
        severity = "critical"
    elif finding.severity == "info":
        severity = "info"
    else:
        severity = "warning"

    issue_id = make_debate_issue_id(
        issue_type=issue_type,
        message=finding.message,
        horizon=horizon,
        role=role,
        related_id=finding.object_id,
        evidence_id=finding.evidence_id,
        field_path=finding.field_path,
    )
    return DebateIssue(
        issue_id=issue_id,
        issue_type=issue_type,  # type: ignore[arg-type]
        severity=severity,
        horizon=horizon,
        role=role,
        message=finding.message,
        related_id=finding.object_id,
        evidence_id=finding.evidence_id,
        field_path=finding.field_path,
    )


def issue_from_critic_issue_for_debate(
    issue: CriticIssue,
    horizon: Optional[DebateHorizon] = None,
    role: Optional[DebateRole] = None,
) -> DebateIssue:
    """
    Convert a CriticIssue into a DebateIssue.

    Preserves evidence_id, field_path, target_id as related_id.
    Maps CriticIssueType → DebateIssueType:
      missing_risk         → missing_risk
      missing_assumption   → missing_assumption
      conflicting_evidence → conflicting_evidence
      stale_evidence       → stale_evidence
      unsupported_claim    → unsupported_claim
      overconfidence       → overconfidence
      weak_evidence        → missing_evidence
      validation_failure   → validation_issue
      numeric_claim_issue  → unsupported_claim
      safety_concern       → critic_issue
    """
    issue_type: str = _CRITIC_TYPE_MAP.get(issue.issue_type, "other")

    severity: DebateIssueSeverity
    if issue.severity == "critical":
        severity = "critical"
    elif issue.severity == "info":
        severity = "info"
    else:
        severity = "warning"

    issue_id = make_debate_issue_id(
        issue_type=issue_type,
        message=issue.message,
        horizon=horizon,
        role=role,
        related_id=issue.target_id,
        evidence_id=issue.evidence_id,
        field_path=issue.field_path,
    )
    return DebateIssue(
        issue_id=issue_id,
        issue_type=issue_type,  # type: ignore[arg-type]
        severity=severity,
        horizon=horizon,
        role=role,
        message=issue.message,
        related_id=issue.target_id,
        evidence_id=issue.evidence_id,
        field_path=issue.field_path,
    )


# ---------------------------------------------------------------------------
# Internal: synthesis card lookup
# ---------------------------------------------------------------------------

def _get_horizon_synthesis_card(
    horizon: DebateHorizon,
    input_bundle: DebateInputBundle,
) -> Optional[Any]:
    """Return the HorizonSynthesisCard matching the given horizon, or None.

    Matches on card.horizon (accepted Phase 3B field) with fallback to card.bucket.
    """
    hsr = input_bundle.horizon_synthesis_report
    if hsr is None:
        return None
    for card in getattr(hsr, "cards", []) or []:
        # Preferred Phase 3B field: card.horizon; backward-compatible fallback: card.bucket
        card_horizon = getattr(card, "horizon", None) or getattr(card, "bucket", None)
        if card_horizon == horizon:
            return card
    return None


# ---------------------------------------------------------------------------
# Helper: Position builders
# ---------------------------------------------------------------------------

def build_bull_position(
    horizon: DebateHorizon,
    input_bundle: DebateInputBundle,
    evidence_ids: list[str],
    issues: Optional[list[DebateIssue]] = None,
) -> DebatePosition:
    """
    Build a deterministic mock bull position for the given horizon.

    Uses horizon synthesis card if available; checks macro result for
    supportive horizon impact. If no evidence, returns an evidence_gap
    claim — not a bullish assertion.
    No buy/sell language. No invented facts.
    """
    position_key = f"{input_bundle.ticker or 'debate'}:bull:{horizon}"
    position_id = make_debate_id(
        bundle_id=input_bundle.bundle_id,
        as_of=input_bundle.as_of,
        ticker=position_key,
    )

    claims: list[DebateClaim] = []
    all_issues: list[DebateIssue] = list(issues or [])
    horizon_card = _get_horizon_synthesis_card(horizon, input_bundle)

    if not evidence_ids:
        claim_id = make_debate_issue_id(
            issue_type="evidence_gap",
            message=f"No evidence for bull case: {horizon}",
            horizon=horizon,
            role="bull",
        )
        claims.append(DebateClaim(
            claim_id=claim_id,
            claim_type="evidence_gap",
            role="bull",
            horizon=horizon,
            text=(
                f"[MOCK DRY-RUN] Bull case ({horizon}): No supporting evidence found. "
                "A thesis cannot be asserted without evidence artifacts. "
                "This output is for research purposes only and does not constitute "
                "investment advice."
            ),
            evidence_ids=[],
            confidence="insufficient_evidence",
        ))
        summary = (
            f"[MOCK DRY-RUN] Bull case ({horizon}): insufficient evidence. "
            "No thesis asserted. Not investment advice."
        )

    elif horizon_card is not None:
        signal_dir = getattr(horizon_card, "signal_direction", "unknown")
        esummary = getattr(horizon_card, "evidence_summary", None)
        # Preferred Phase 3B field: supporting_evidence_ids; fallback: evidence_ids
        card_eids = list(
            (
                getattr(esummary, "supporting_evidence_ids", None)
                or getattr(esummary, "evidence_ids", None)
                or []
            )
            if esummary else []
        )
        claim_eids = card_eids[:5] if card_eids else evidence_ids[:5]

        claim_id = make_debate_issue_id(
            issue_type="thesis",
            message=f"Bull thesis from horizon synthesis ({horizon}): signal={signal_dir}",
            horizon=horizon,
            role="bull",
        )
        if signal_dir == "bullish":
            text = (
                f"[MOCK DRY-RUN] Bull case ({horizon}): Horizon synthesis signals "
                f"{signal_dir!r}. Available evidence is consistent with a constructive "
                "outlook for this horizon based on synthesis artifacts. Not investment advice."
            )
            confidence = "low"
        elif signal_dir == "bearish":
            text = (
                f"[MOCK DRY-RUN] Bull case ({horizon}): Horizon synthesis signals "
                f"{signal_dir!r}. Constructive thesis is unsupported by available "
                "synthesis artifacts. Not investment advice."
            )
            confidence = "insufficient_evidence"
        else:
            text = (
                f"[MOCK DRY-RUN] Bull case ({horizon}): Horizon synthesis signals "
                f"{signal_dir!r}. Mixed or unknown signals; bull thesis is unconfirmed "
                "from available evidence. Not investment advice."
            )
            confidence = "low"

        claims.append(DebateClaim(
            claim_id=claim_id,
            claim_type="thesis",
            role="bull",
            horizon=horizon,
            text=text,
            evidence_ids=claim_eids,
            confidence=confidence,
        ))

        # Check macro horizon impact for supplementary support
        mar = input_bundle.macro_agent_result
        if mar is not None:
            for hi in getattr(mar, "horizon_impacts", []) or []:
                if getattr(hi, "horizon", None) == horizon:
                    impact = getattr(hi, "impact", "unknown")
                    if impact == "supportive":
                        macro_eids = list(getattr(hi, "evidence_ids", []) or [])[:3]
                        macro_cid = make_debate_issue_id(
                            issue_type="thesis",
                            message=f"Macro supportive impact for bull case ({horizon})",
                            horizon=horizon,
                            role="bull",
                        )
                        claims.append(DebateClaim(
                            claim_id=macro_cid,
                            claim_type="thesis",
                            role="bull",
                            horizon=horizon,
                            text=(
                                f"[MOCK DRY-RUN] Macro ({horizon}): impact={impact!r}. "
                                "Macro backdrop is consistent with favorable conditions "
                                "based on available macro artifacts. Not investment advice."
                            ),
                            evidence_ids=macro_eids,
                            confidence="low",
                        ))
                    break

        summary = (
            f"[MOCK DRY-RUN] Bull case ({horizon}): signal={signal_dir!r}, "
            f"{len(claims)} claim(s). Not investment advice."
        )

    else:
        # Evidence available but no synthesis card
        claim_id = make_debate_issue_id(
            issue_type="thesis",
            message=f"Bull thesis from evidence, no synthesis card ({horizon})",
            horizon=horizon,
            role="bull",
        )
        claims.append(DebateClaim(
            claim_id=claim_id,
            claim_type="thesis",
            role="bull",
            horizon=horizon,
            text=(
                f"[MOCK DRY-RUN] Bull case ({horizon}): Evidence available but no "
                "horizon synthesis card. Thesis is unconfirmed; horizon synthesis "
                "required for a structured bull case. Not investment advice."
            ),
            evidence_ids=evidence_ids[:5],
            confidence="low",
        ))
        summary = (
            f"[MOCK DRY-RUN] Bull case ({horizon}): {len(evidence_ids)} evidence ID(s), "
            "no synthesis card. Not investment advice."
        )

    pos_evidence = list(dict.fromkeys(eid for c in claims for eid in c.evidence_ids))
    return DebatePosition(
        position_id=position_id,
        role="bull",
        horizon=horizon,
        summary=summary,
        claims=claims,
        evidence_ids=pos_evidence,
        issues=all_issues,
        confidence="low" if evidence_ids else "insufficient_evidence",
    )


def build_bear_position(
    horizon: DebateHorizon,
    input_bundle: DebateInputBundle,
    evidence_ids: list[str],
    issues: Optional[list[DebateIssue]] = None,
) -> DebatePosition:
    """
    Build a deterministic mock bear/counterargument position.

    Uses critic/staleness/validation issues as counterargument basis.
    Uses horizon synthesis bearish/mixed signals if available.
    If no evidence or critique: highlights lack of support.
    No invented facts. No buy/sell language.
    """
    position_key = f"{input_bundle.ticker or 'debate'}:bear:{horizon}"
    position_id = make_debate_id(
        bundle_id=input_bundle.bundle_id,
        as_of=input_bundle.as_of,
        ticker=position_key,
    )

    claims: list[DebateClaim] = []
    all_issues: list[DebateIssue] = list(issues or [])

    validation_issues = [
        i for i in all_issues
        if i.issue_type in (
            "unsupported_claim", "missing_evidence", "stale_evidence",
            "validation_issue", "conflicting_evidence",
        )
    ]
    critic_issues = [
        i for i in all_issues
        if i.issue_type in ("missing_risk", "missing_assumption", "overconfidence", "critic_issue")
    ]
    all_critique = validation_issues + critic_issues

    if not evidence_ids and not all_critique:
        claim_id = make_debate_issue_id(
            issue_type="evidence_gap",
            message=f"No evidence for bear case: {horizon}",
            horizon=horizon,
            role="bear",
        )
        claims.append(DebateClaim(
            claim_id=claim_id,
            claim_type="evidence_gap",
            role="bear",
            horizon=horizon,
            text=(
                f"[MOCK DRY-RUN] Bear case ({horizon}): No counterfactual evidence or "
                "critique issues found. A counterargument cannot be asserted without "
                "evidence or validation artifacts. Not investment advice."
            ),
            evidence_ids=[],
            confidence="insufficient_evidence",
        ))
        summary = (
            f"[MOCK DRY-RUN] Bear case ({horizon}): insufficient evidence and issues. "
            "No counterargument asserted. Not investment advice."
        )
    else:
        # Counterargument from validation/staleness/critic issues
        if all_critique:
            msgs = "; ".join(i.message for i in all_critique[:3])
            issue_eids = [i.evidence_id for i in all_critique if i.evidence_id][:5]
            claim_eids = issue_eids if issue_eids else evidence_ids[:3]

            claim_id = make_debate_issue_id(
                issue_type="counterargument",
                message=f"Bear counterargument from validation/critic ({horizon})",
                horizon=horizon,
                role="bear",
            )
            claims.append(DebateClaim(
                claim_id=claim_id,
                claim_type="counterargument",
                role="bear",
                horizon=horizon,
                text=(
                    f"[MOCK DRY-RUN] Bear case ({horizon}): Validation/critic artifacts "
                    f"raise concerns: {msgs}. These are structural data-quality issues, "
                    "not price forecasts. Not investment advice."
                ),
                evidence_ids=claim_eids,
                confidence="low",
            ))

        # Use horizon synthesis bearish/mixed signal if available
        horizon_card = _get_horizon_synthesis_card(horizon, input_bundle)
        if horizon_card is not None:
            signal_dir = getattr(horizon_card, "signal_direction", "unknown")
            if signal_dir in ("bearish", "mixed"):
                esummary = getattr(horizon_card, "evidence_summary", None)
                # Preferred Phase 3B field: supporting_evidence_ids; fallback: evidence_ids
                card_eids = list(
                    (
                        getattr(esummary, "supporting_evidence_ids", None)
                        or getattr(esummary, "evidence_ids", None)
                        or []
                    )[:3]
                    if esummary else []
                )
                cid = make_debate_issue_id(
                    issue_type="counterargument",
                    message=f"Bear case from horizon synthesis signal={signal_dir} ({horizon})",
                    horizon=horizon,
                    role="bear",
                )
                claims.append(DebateClaim(
                    claim_id=cid,
                    claim_type="counterargument",
                    role="bear",
                    horizon=horizon,
                    text=(
                        f"[MOCK DRY-RUN] Bear case ({horizon}): Horizon synthesis signals "
                        f"{signal_dir!r}. Available evidence is consistent with caution "
                        "for this horizon. Not investment advice."
                    ),
                    evidence_ids=card_eids if card_eids else evidence_ids[:3],
                    confidence="low",
                ))

        if not claims:
            claim_id = make_debate_issue_id(
                issue_type="counterargument",
                message=f"Bear counterargument from available evidence ({horizon})",
                horizon=horizon,
                role="bear",
            )
            claims.append(DebateClaim(
                claim_id=claim_id,
                claim_type="counterargument",
                role="bear",
                horizon=horizon,
                text=(
                    f"[MOCK DRY-RUN] Bear case ({horizon}): Evidence available but no "
                    "structured counterargument can be derived. Requires critic/validation "
                    "artifacts. Not investment advice."
                ),
                evidence_ids=evidence_ids[:3],
                confidence="low",
            ))

        summary = (
            f"[MOCK DRY-RUN] Bear case ({horizon}): {len(claims)} claim(s), "
            f"{len(all_critique)} critique issue(s). Not investment advice."
        )

    pos_evidence = list(dict.fromkeys(eid for c in claims for eid in c.evidence_ids))
    return DebatePosition(
        position_id=position_id,
        role="bear",
        horizon=horizon,
        summary=summary,
        claims=claims,
        evidence_ids=pos_evidence,
        issues=all_issues,
        confidence="low" if (evidence_ids or all_critique) else "insufficient_evidence",
    )


def build_risk_position(
    horizon: DebateHorizon,
    input_bundle: DebateInputBundle,
    evidence_ids: list[str],
    issues: Optional[list[DebateIssue]] = None,
) -> DebatePosition:
    """
    Build a deterministic risk review position.

    Emphasizes stale data, missing risk, overconfidence, conflicting evidence,
    and missing assumptions from available artifacts.
    If no blocking issues found: states risk review found no blocking issue.
    No trading recommendation.
    """
    position_key = f"{input_bundle.ticker or 'debate'}:risk:{horizon}"
    position_id = make_debate_id(
        bundle_id=input_bundle.bundle_id,
        as_of=input_bundle.as_of,
        ticker=position_key,
    )

    all_issues: list[DebateIssue] = list(issues or [])
    claims: list[DebateClaim] = []

    risk_issues = [i for i in all_issues if i.issue_type in _RISK_DOMINANT_ISSUE_TYPES]
    stale_issues = [i for i in all_issues if i.issue_type == "stale_evidence"]
    overconf_issues = [i for i in all_issues if i.issue_type == "overconfidence"]
    conflict_issues = [i for i in all_issues if i.issue_type == "conflicting_evidence"]
    other_risk_issues = [
        i for i in risk_issues
        if i.issue_type not in ("stale_evidence", "overconfidence", "conflicting_evidence")
    ]

    if not risk_issues:
        claim_id = make_debate_issue_id(
            issue_type="risk",
            message=f"Risk review: no blocking issues found ({horizon})",
            horizon=horizon,
            role="risk",
        )
        claims.append(DebateClaim(
            claim_id=claim_id,
            claim_type="risk",
            role="risk",
            horizon=horizon,
            text=(
                f"[MOCK DRY-RUN] Risk review ({horizon}): No blocking risk issues "
                "identified in the available validation, staleness, or critic artifacts. "
                "This does not imply the investment is risk-free. Not investment advice."
            ),
            evidence_ids=evidence_ids[:3],
            confidence="low",
        ))
        summary = (
            f"[MOCK DRY-RUN] Risk review ({horizon}): No blocking issues in available "
            "artifacts. Not investment advice."
        )
    else:
        if stale_issues:
            msgs = "; ".join(i.message for i in stale_issues[:3])
            stale_eids = [i.evidence_id for i in stale_issues if i.evidence_id][:3]
            cid = make_debate_issue_id(
                issue_type="stale_evidence",
                message=f"Stale evidence risk: {len(stale_issues)} finding(s) ({horizon})",
                horizon=horizon,
                role="risk",
            )
            claims.append(DebateClaim(
                claim_id=cid,
                claim_type="risk",
                role="risk",
                horizon=horizon,
                text=(
                    f"[MOCK DRY-RUN] Risk review ({horizon}): {len(stale_issues)} stale "
                    f"evidence finding(s). Key messages: {msgs}. Stale data reduces "
                    "confidence in any synthesis. Not investment advice."
                ),
                evidence_ids=stale_eids if stale_eids else evidence_ids[:2],
                confidence="low",
            ))

        if overconf_issues:
            msgs = "; ".join(i.message for i in overconf_issues[:3])
            cid = make_debate_issue_id(
                issue_type="overconfidence",
                message=f"Overconfidence risk: {len(overconf_issues)} finding(s) ({horizon})",
                horizon=horizon,
                role="risk",
            )
            claims.append(DebateClaim(
                claim_id=cid,
                claim_type="risk",
                role="risk",
                horizon=horizon,
                text=(
                    f"[MOCK DRY-RUN] Risk review ({horizon}): {len(overconf_issues)} "
                    f"overconfidence finding(s). Key messages: {msgs}. Not investment advice."
                ),
                evidence_ids=evidence_ids[:2],
                confidence="low",
            ))

        if conflict_issues:
            msgs = "; ".join(i.message for i in conflict_issues[:3])
            cid = make_debate_issue_id(
                issue_type="conflicting_evidence",
                message=f"Conflicting evidence: {len(conflict_issues)} finding(s) ({horizon})",
                horizon=horizon,
                role="risk",
            )
            claims.append(DebateClaim(
                claim_id=cid,
                claim_type="risk",
                role="risk",
                horizon=horizon,
                text=(
                    f"[MOCK DRY-RUN] Risk review ({horizon}): {len(conflict_issues)} "
                    f"conflicting evidence finding(s). Key messages: {msgs}. "
                    "Not investment advice."
                ),
                evidence_ids=evidence_ids[:2],
                confidence="low",
            ))

        if other_risk_issues:
            msgs = "; ".join(i.message for i in other_risk_issues[:3])
            cid = make_debate_issue_id(
                issue_type="risk",
                message=f"Other risk issues: {len(other_risk_issues)} finding(s) ({horizon})",
                horizon=horizon,
                role="risk",
            )
            claims.append(DebateClaim(
                claim_id=cid,
                claim_type="risk",
                role="risk",
                horizon=horizon,
                text=(
                    f"[MOCK DRY-RUN] Risk review ({horizon}): {len(other_risk_issues)} "
                    f"other risk finding(s). Key messages: {msgs}. Not investment advice."
                ),
                evidence_ids=evidence_ids[:2],
                confidence="low",
            ))

        summary = (
            f"[MOCK DRY-RUN] Risk review ({horizon}): {len(risk_issues)} risk issue(s) "
            f"({len(stale_issues)} stale, {len(overconf_issues)} overconfidence, "
            f"{len(conflict_issues)} conflicting). Not investment advice."
        )

    pos_evidence = list(dict.fromkeys(eid for c in claims for eid in c.evidence_ids))
    return DebatePosition(
        position_id=position_id,
        role="risk",
        horizon=horizon,
        summary=summary,
        claims=claims,
        evidence_ids=pos_evidence,
        issues=all_issues,
        confidence="low" if evidence_ids else "insufficient_evidence",
    )


# ---------------------------------------------------------------------------
# Helper: Round builder
# ---------------------------------------------------------------------------

def build_debate_round(
    horizon: DebateHorizon,
    input_bundle: DebateInputBundle,
) -> DebateRound:
    """
    Build one debate round for the given investment horizon.

    Steps:
      1. Extract horizon-specific evidence IDs.
      2. Convert validation/staleness/critic issues to DebateIssues.
      3. Build bull / bear / risk positions.
      4. Identify unresolved questions and evidence gaps.
      5. Verdict and status are auto-normalised by DebateRound model_validator.

    Deterministic. No LLM. No external data. Does not mutate input_bundle.
    """
    round_id = make_debate_id(
        bundle_id=input_bundle.bundle_id,
        as_of=input_bundle.as_of,
        ticker=f"{input_bundle.ticker or 'debate'}:round:{horizon}",
    )

    evidence_ids = extract_debate_evidence_ids(input_bundle, horizon=horizon)

    # Convert all artifact issues to DebateIssues
    debate_issues: list[DebateIssue] = []

    if input_bundle.validation_aggregate is not None:
        for item in input_bundle.validation_aggregate.items:
            debate_issues.append(
                issue_from_validation_item_for_debate(item, horizon=horizon)
            )

    if input_bundle.staleness_report is not None:
        for finding in input_bundle.staleness_report.findings:
            debate_issues.append(
                issue_from_staleness_finding_for_debate(finding, horizon=horizon)
            )

    if input_bundle.critic_result is not None:
        for ci in input_bundle.critic_result.issues:
            debate_issues.append(
                issue_from_critic_issue_for_debate(ci, horizon=horizon)
            )

    # Deduplicate by issue_id (first occurrence wins)
    seen_ids: set[str] = set()
    deduped: list[DebateIssue] = []
    for issue in debate_issues:
        if issue.issue_id not in seen_ids:
            seen_ids.add(issue.issue_id)
            deduped.append(issue)

    # Partition issues for positions
    non_risk_types = {"missing_risk", "missing_assumption", "critic_issue"}
    bull_issues = [i for i in deduped if i.issue_type not in non_risk_types]
    bear_issues = [
        i for i in deduped
        if i.issue_type in (
            "unsupported_claim", "missing_evidence", "stale_evidence",
            "validation_issue", "conflicting_evidence",
            "missing_risk", "missing_assumption", "critic_issue",
        )
    ]

    bull = build_bull_position(horizon, input_bundle, evidence_ids, issues=bull_issues)
    bear = build_bear_position(horizon, input_bundle, evidence_ids, issues=bear_issues)
    risk = build_risk_position(horizon, input_bundle, evidence_ids, issues=deduped)

    # Unresolved questions
    unresolved: list[str] = []
    if not evidence_ids:
        unresolved.append(f"No evidence IDs found for {horizon} horizon.")
    if input_bundle.horizon_synthesis_report is None:
        unresolved.append(
            "No HorizonSynthesisReport provided; synthesis quality is unconfirmed."
        )
    if input_bundle.macro_agent_result is None:
        unresolved.append("No MacroAgentResult provided; macro context is unavailable.")

    # Evidence gaps
    evidence_gaps: list[str] = []
    if not evidence_ids:
        evidence_gaps.append(f"No evidence IDs available for {horizon} debate round.")
    critical_issues = [i for i in deduped if i.severity == "critical"]
    for ci in critical_issues[:3]:
        evidence_gaps.append(f"Critical issue: {ci.message}")

    return DebateRound(
        round_id=round_id,
        horizon=horizon,
        bull_position=bull,
        bear_position=bear,
        risk_position=risk,
        unresolved_questions=unresolved,
        evidence_gaps=evidence_gaps,
        issues=deduped,
        # verdict and status auto-normalised by model_validator
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_debate_by_horizon(
    input_bundle: DebateInputBundle,
) -> DebateReport:
    """
    Run the debate across exactly three investment horizons.

    Builds short_term, medium_term, long_term debate rounds in that order.
    Deterministic. Offline. No LLM. No external APIs. Does not mutate inputs.
    """
    debate_id = make_debate_id(
        bundle_id=input_bundle.bundle_id,
        as_of=input_bundle.as_of,
        ticker=input_bundle.ticker,
    )

    # Extract artifact IDs for traceability
    hsr_id: Optional[str] = None
    hsr = input_bundle.horizon_synthesis_report
    if hsr is not None:
        hsr_id = getattr(hsr, "synthesis_id", None) or getattr(hsr, "report_id", None)

    mar_id: Optional[str] = None
    mar = input_bundle.macro_agent_result
    if mar is not None:
        mar_id = getattr(mar, "macro_agent_id", None)

    rounds: list[DebateRound] = [
        build_debate_round(h, input_bundle) for h in _HORIZON_ORDER
    ]

    return DebateReport(
        debate_id=debate_id,
        as_of=input_bundle.as_of,
        ticker=input_bundle.ticker,
        rounds=rounds,
        horizon_synthesis_report_id=hsr_id,
        macro_agent_result_id=mar_id,
        validation_aggregate=input_bundle.validation_aggregate,
        staleness_report=input_bundle.staleness_report,
        critic_result=input_bundle.critic_result,
        reliability_score_summary=input_bundle.reliability_score_summary,
        metadata={"bundle_id": input_bundle.bundle_id},
    )


# ---------------------------------------------------------------------------
# ToolResult wrapper
# ---------------------------------------------------------------------------

def summarize_debate_report(report: DebateReport) -> dict[str, Any]:
    """Return a concise summary dict for a DebateReport (capped at 10 messages)."""
    all_issues = report.issues
    critical_count = sum(1 for i in all_issues if i.severity == "critical")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    info_count = sum(1 for i in all_issues if i.severity == "info")
    horizon_verdicts: dict[str, str] = {r.horizon: r.verdict for r in report.rounds}
    horizon_statuses: dict[str, str] = {r.horizon: r.status for r in report.rounds}
    top_messages = [i.message for i in all_issues[:10]]

    return {
        "debate_id": report.debate_id,
        "ticker": report.ticker,
        "status": report.status,
        "recommendation": report.recommendation,
        "round_count": len(report.rounds),
        "issue_count": len(all_issues),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "horizon_verdicts": horizon_verdicts,
        "horizon_statuses": horizon_statuses,
        "top_messages": top_messages,
    }


def debate_report_tool_result_from_report(
    run_id: str,
    report: DebateReport,
    target: Optional[str] = None,
    calculation_version: str = "debate_by_horizon_skeleton_v1",
) -> ToolResult:
    """
    Wrap a DebateReport into the existing ToolResult model.

    tool_name is stable: "debate_report".
    target defaults to report.ticker if present, else "debate".
    evidence_id is content-sensitive: derived from the full payload hash.
    Does not mutate report. Does not loosen ToolResult schema.
    """
    effective_target = target or report.ticker or "debate"

    result_dict = report.model_dump(mode="json")
    summary = summarize_debate_report(report)
    payload: dict[str, Any] = {
        "report": result_dict,
        "summary": summary,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_DEBATE_TOOL_NAME,
        target=effective_target,
        metric_group=_DEBATE_METRIC_GROUP,
        payload=payload,
    )

    description = (
        f"DebateReport {report.debate_id!r}"
        f" as_of={report.as_of!r}"
        f" status={report.status!r}"
        f" recommendation={report.recommendation!r}"
        f" rounds={len(report.rounds)}"
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_DEBATE_TOOL_NAME,
        run_id=run_id,
        ticker=report.ticker,
        inputs={
            "debate_id": report.debate_id,
            "as_of": report.as_of,
            "target": effective_target,
            "calculation_version": calculation_version,
        },
        outputs=payload,
        description=description,
    )
