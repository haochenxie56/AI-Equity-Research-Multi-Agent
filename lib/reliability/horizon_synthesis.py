"""
lib/reliability/horizon_synthesis.py

Phase 3B: Horizon-aware Synthesis Skeleton.

Design principles:
  - Standalone, deterministic, offline.
  - No live LLM calls, no live data fetching, no app integration.
  - Consumes Phase 0–3A reliability artifacts and produces structured
    per-horizon synthesis outputs (short_term / medium_term / long_term).
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice.
  - Mock/dry-run only; all outputs are explicitly evidence-aware.

See docs/reliability_phase_3b_horizon_aware_synthesis_skeleton.md for design.
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
# Literal type aliases
# ---------------------------------------------------------------------------

HorizonSynthesisStatus = Literal[
    "pass",
    "pass_with_warnings",
    "fail",
    "unknown",
]

HorizonSignalDirection = Literal[
    "bullish",
    "bearish",
    "neutral",
    "mixed",
    "insufficient_evidence",
    "unknown",
]

HorizonConfidenceLevel = Literal[
    "high",
    "medium",
    "low",
    "insufficient_evidence",
    "unknown",
]

HorizonSynthesisRecommendation = Literal[
    "proceed_to_debate",
    "revise",
    "reject",
    "needs_more_evidence",
    "no_action",
    "unknown",
]

HorizonSynthesisIssueType = Literal[
    "missing_evidence",
    "stale_evidence",
    "validation_issue",
    "critic_issue",
    "conflicting_signal",
    "horizon_mismatch",
    "missing_risk",
    "missing_assumption",
    "overconfidence",
    "unsupported_claim",
    "other",
]

HorizonBucket = Literal[
    "short_term",
    "medium_term",
    "long_term",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_HORIZON_TOOL_NAME: str = "horizon_synthesis_report"
_HORIZON_METRIC_GROUP: str = "horizon_synthesis_report"

# Canonical card order
_HORIZON_ORDER: list[str] = ["short_term", "medium_term", "long_term"]

# ValidationItemType → HorizonSynthesisIssueType
_VALIDATION_TYPE_MAP: dict[str, str] = {
    "stale_data": "stale_evidence",
    "missing_data": "missing_evidence",
    "evidence_binding": "unsupported_claim",
    "unsupported": "unsupported_claim",
    "risk_limit": "validation_issue",
    "safety": "critic_issue",
    "schema": "validation_issue",
    "mismatch": "conflicting_signal",
    "duplicate_data": "other",
    "calculation": "validation_issue",
    "provenance": "missing_evidence",
    "other": "other",
}

# CriticIssueType → HorizonSynthesisIssueType
_CRITIC_TYPE_MAP: dict[str, str] = {
    "overconfidence": "overconfidence",
    "missing_risk": "missing_risk",
    "missing_assumption": "missing_assumption",
    "conflicting_evidence": "conflicting_signal",
    "stale_evidence": "stale_evidence",
    "unsupported_claim": "unsupported_claim",
    "weak_evidence": "missing_evidence",
    "validation_failure": "validation_issue",
    "numeric_claim_issue": "unsupported_claim",
    "scope_violation": "other",
    "safety_concern": "critic_issue",
    "other": "other",
}

# Expected evidence domains per horizon bucket
_HORIZON_EXPECTED_DOMAINS: dict[str, list[str]] = {
    "short_term": ["technical", "news", "catalyst"],
    "medium_term": ["earnings", "estimate", "catalyst", "news"],
    "long_term": ["valuation", "fundamental", "macro"],
}

# Domain keywords for coverage inference from tool_names
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "technical": ["technical", "rsi", "macd", "momentum", "sma", "ema", "ohlcv", "volume", "price"],
    "news": ["news", "article", "headline"],
    "catalyst": ["catalyst", "event_catalyst", "earnings_catalyst"],
    "earnings": ["earnings", "eps", "revenue", "quarterly"],
    "estimate": ["estimate", "revision", "forecast", "consensus"],
    "valuation": ["valuation", "dcf", "pe_ratio", "ev_ebitda", "fair_value", "intrinsic"],
    "fundamental": ["fundamental", "financials", "balance_sheet", "income_statement", "cash_flow"],
    "macro": ["macro", "gdp", "inflation", "fed", "interest_rate", "cpi", "unemployment", "sector_rotation"],
}


# ---------------------------------------------------------------------------
# 1. HorizonSynthesisIssue
# ---------------------------------------------------------------------------

class HorizonSynthesisIssue(BaseModel):
    """One structured issue raised during horizon-aware synthesis."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1)
    issue_type: HorizonSynthesisIssueType
    horizon: Optional[HorizonBucket] = None
    severity: Literal["critical", "warning", "info"] = "warning"
    message: str = Field(min_length=1)
    related_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "HorizonSynthesisIssue":
        for field_name in ("issue_id", "message"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 2. HorizonEvidenceSummary
# ---------------------------------------------------------------------------

class HorizonEvidenceSummary(BaseModel):
    """Evidence coverage summary for one horizon bucket."""

    model_config = ConfigDict(extra="forbid")

    horizon: HorizonBucket
    evidence_count: int = Field(default=0, ge=0)
    stale_evidence_count: int = Field(default=0, ge=0)
    validation_issue_count: int = Field(default=0, ge=0)
    critic_issue_count: int = Field(default=0, ge=0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    missing_domains: list[str] = Field(default_factory=list)
    contested_domains: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 3. HorizonSynthesisCard
# ---------------------------------------------------------------------------

class HorizonSynthesisCard(BaseModel):
    """Synthesis output for one investment horizon bucket."""

    model_config = ConfigDict(extra="forbid")

    horizon: HorizonBucket
    status: HorizonSynthesisStatus = "unknown"
    signal_direction: HorizonSignalDirection = "unknown"
    confidence: HorizonConfidenceLevel = "unknown"
    recommendation: HorizonSynthesisRecommendation = "unknown"
    thesis_summary: Optional[str] = None
    supported_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    evidence_summary: Optional[HorizonEvidenceSummary] = None
    issues: list[HorizonSynthesisIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_status_recommendation(self) -> "HorizonSynthesisCard":
        """Derive status and recommendation from issues and evidence coverage."""
        all_issues = list(self.issues)
        has_critical = any(i.severity == "critical" for i in all_issues)
        has_warning = any(i.severity == "warning" for i in all_issues)

        evidence_count = 0
        if self.evidence_summary is not None:
            evidence_count = self.evidence_summary.evidence_count

        if has_critical:
            self.status = "fail"
            self.recommendation = "reject"
        elif has_warning:
            self.status = "pass_with_warnings"
            self.recommendation = "revise"
        elif evidence_count == 0:
            self.status = "unknown"
            self.recommendation = "needs_more_evidence"
        else:
            self.status = "pass"
            self.recommendation = "proceed_to_debate"

        return self


# ---------------------------------------------------------------------------
# 4. HorizonSynthesisReport
# ---------------------------------------------------------------------------

class HorizonSynthesisReport(BaseModel):
    """Auditable horizon-aware synthesis report across all three time buckets."""

    model_config = ConfigDict(extra="forbid")

    synthesis_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    status: HorizonSynthesisStatus = "unknown"
    recommendation: HorizonSynthesisRecommendation = "unknown"
    cards: list[HorizonSynthesisCard] = Field(default_factory=list)
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    orchestration_report_id: Optional[str] = None
    issues: list[HorizonSynthesisIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "HorizonSynthesisReport":
        for field_name in ("synthesis_id", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self

    @model_validator(mode="after")
    def _normalize(self) -> "HorizonSynthesisReport":
        """Sort cards in canonical order and derive report-level status/recommendation."""
        # Sort cards: short_term, medium_term, long_term
        order_map = {h: i for i, h in enumerate(_HORIZON_ORDER)}
        self.cards = sorted(self.cards, key=lambda c: order_map.get(c.horizon, 999))

        # Aggregate issues: report-level + all card issues
        all_issues: list[HorizonSynthesisIssue] = list(self.issues)
        for card in self.cards:
            all_issues.extend(card.issues)

        has_critical = any(i.severity == "critical" for i in all_issues)
        has_warning = any(i.severity == "warning" for i in all_issues)

        any_card_fail = any(card.status == "fail" for card in self.cards)
        any_card_warnings = any(card.status == "pass_with_warnings" for card in self.cards)
        all_cards_pass = bool(self.cards) and all(card.status == "pass" for card in self.cards)
        all_cards_needs_evidence = bool(self.cards) and all(
            card.recommendation == "needs_more_evidence"
            for card in self.cards
        )

        if has_critical or any_card_fail:
            self.status = "fail"
            self.recommendation = "reject"
        elif has_warning or any_card_warnings:
            self.status = "pass_with_warnings"
            self.recommendation = "revise"
        elif all_cards_needs_evidence or not self.cards:
            self.status = "unknown"
            self.recommendation = "needs_more_evidence"
        elif all_cards_pass:
            self.status = "pass"
            self.recommendation = "proceed_to_debate"
        else:
            # Mixed: some pass, some unknown
            self.status = "pass_with_warnings"
            self.recommendation = "revise"

        return self


# ---------------------------------------------------------------------------
# 5. HorizonSynthesisInputBundle
# ---------------------------------------------------------------------------

class HorizonSynthesisInputBundle(BaseModel):
    """Input bundle for one horizon-aware synthesis run."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    agent_result: Optional[AgentResult] = None
    orchestration_report: Optional[Any] = None
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    reliability_score_summary: Optional[ReliabilityScoreSummary] = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "HorizonSynthesisInputBundle":
        for field_name in ("bundle_id", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# Helper 1: make_horizon_synthesis_issue_id
# ---------------------------------------------------------------------------

def make_horizon_synthesis_issue_id(
    issue_type: str,
    horizon: Optional[str],
    message: str,
    related_id: Optional[str] = None,
    evidence_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> str:
    """
    Build a deterministic, stable issue_id for a HorizonSynthesisIssue.

    Same inputs always produce the same ID.
    Different message/related_id/evidence_id/field_path produces a different ID.
    """
    payload = {
        "issue_type": issue_type,
        "horizon": horizon or "",
        "message": message,
        "related_id": related_id or "",
        "evidence_id": evidence_id or "",
        "field_path": field_path or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    return f"{issue_type}:{horizon or 'any'}:{hash_suffix}"


# ---------------------------------------------------------------------------
# Helper 2: make_horizon_synthesis_id
# ---------------------------------------------------------------------------

def make_horizon_synthesis_id(
    bundle_id: str,
    as_of: str,
    ticker: Optional[str] = None,
) -> str:
    """
    Build a deterministic synthesis_id from bundle_id, as_of, and ticker.

    Same inputs always produce the same ID.
    """
    payload = {
        "bundle_id": bundle_id,
        "as_of": as_of,
        "ticker": ticker or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    return f"horizon_synthesis:{hash_suffix}"


# ---------------------------------------------------------------------------
# Private helper: infer covered domains from tool_results
# ---------------------------------------------------------------------------

def _infer_covered_domains(tool_results: list[ToolResult]) -> set[str]:
    """Infer which evidence domains are covered based on tool_name keywords."""
    covered: set[str] = set()
    for tr in tool_results:
        tool_name_lower = tr.tool_name.lower()
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            if any(kw in tool_name_lower for kw in keywords):
                covered.add(domain)
    return covered


# ---------------------------------------------------------------------------
# Helper 3: extract_horizon_evidence_ids
# ---------------------------------------------------------------------------

def extract_horizon_evidence_ids(
    agent_result: Optional[AgentResult] = None,
    tool_results: Optional[list[ToolResult]] = None,
    horizon: Optional[str] = None,
) -> list[str]:
    """
    Deterministically collect evidence IDs from AgentResult and ToolResults.

    If horizon is provided, only ToolResults with matching horizon metadata
    (or no horizon metadata at all) are included.
    AgentResult evidence refs are always included.
    Does not mutate inputs.
    """
    evidence_ids: list[str] = []
    seen: set[str] = set()

    def _add(eid: str) -> None:
        if eid and eid not in seen:
            seen.add(eid)
            evidence_ids.append(eid)

    # From tool_results: include if no horizon metadata or matching horizon
    for tr in (tool_results or []):
        tr_horizon = (
            tr.inputs.get("horizon") or tr.outputs.get("horizon") or ""
        )
        if horizon is None or not tr_horizon or tr_horizon == horizon:
            _add(tr.evidence_id)

    # From agent_result findings: always include (no horizon metadata)
    if agent_result is not None:
        for finding in agent_result.findings:
            for eref in finding.evidence:
                _add(eref.evidence_id)

    return evidence_ids


# ---------------------------------------------------------------------------
# Helper 4: summarize_horizon_evidence
# ---------------------------------------------------------------------------

def summarize_horizon_evidence(
    horizon: HorizonBucket,
    agent_result: Optional[AgentResult] = None,
    tool_results: Optional[list[ToolResult]] = None,
    validation_aggregate: Optional[ValidationAggregate] = None,
    staleness_report: Optional[StalenessReport] = None,
    critic_result: Optional[CriticResult] = None,
) -> HorizonEvidenceSummary:
    """
    Build an evidence coverage summary for a specific horizon bucket.

    Behavior:
        - Counts evidence IDs from agent_result and tool_results.
        - Counts stale findings from staleness_report (all non-fresh).
        - Counts validation items from validation_aggregate.
        - Counts critic issues from critic_result.
        - Infers missing domains from tool_result coverage vs expected domains.
        - Does not fetch data, does not call LLM.
    """
    evidence_ids = extract_horizon_evidence_ids(agent_result, tool_results, horizon)

    stale_count = 0
    if staleness_report is not None:
        stale_count = (
            staleness_report.stale_count
            + staleness_report.expired_count
            + staleness_report.near_stale_count
        )

    val_count = 0
    if validation_aggregate is not None:
        val_count = len(validation_aggregate.items)

    critic_count = 0
    if critic_result is not None:
        critic_count = len(critic_result.issues)

    # Infer domain coverage from tool_result tool_names
    covered = _infer_covered_domains(tool_results or [])
    expected = _HORIZON_EXPECTED_DOMAINS.get(horizon, [])
    missing = [d for d in expected if d not in covered]

    # Heuristic: contested domains exist when conflicting critic issues are present
    contested: list[str] = []
    if critic_result is not None:
        has_conflict = any(
            issue.issue_type == "conflicting_evidence"
            for issue in critic_result.issues
        )
        if has_conflict:
            contested = sorted(covered.intersection(set(expected)))

    return HorizonEvidenceSummary(
        horizon=horizon,
        evidence_count=len(evidence_ids),
        stale_evidence_count=stale_count,
        validation_issue_count=val_count,
        critic_issue_count=critic_count,
        supporting_evidence_ids=list(evidence_ids),
        missing_domains=missing,
        contested_domains=contested,
    )


# ---------------------------------------------------------------------------
# Helper 5: issue_from_validation_item_for_horizon
# ---------------------------------------------------------------------------

def issue_from_validation_item_for_horizon(
    item: AggregatedValidationItem,
    horizon: Optional[HorizonBucket] = None,
) -> HorizonSynthesisIssue:
    """
    Convert an AggregatedValidationItem into a HorizonSynthesisIssue.

    Mapping:
        stale_data       → stale_evidence
        missing_data     → missing_evidence
        evidence_binding → unsupported_claim
        unsupported      → unsupported_claim
        risk_limit       → validation_issue
        safety           → critic_issue
        schema/mismatch  → validation_issue/conflicting_signal
        provenance       → missing_evidence

    Preserves: related_id (item_id), evidence_id, field_path.
    """
    issue_type_str: str = _VALIDATION_TYPE_MAP.get(item.item_type, "other")
    issue_type: HorizonSynthesisIssueType = issue_type_str  # type: ignore[assignment]

    severity: Literal["critical", "warning", "info"] = (
        "critical" if item.severity == "critical"
        else "info" if item.severity == "info"
        else "warning"
    )

    issue_id = make_horizon_synthesis_issue_id(
        issue_type=issue_type_str,
        horizon=horizon,
        message=item.message,
        related_id=item.item_id,
        evidence_id=item.evidence_id,
        field_path=item.field_path,
    )

    return HorizonSynthesisIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        horizon=horizon,
        severity=severity,
        message=item.message,
        related_id=item.item_id,
        evidence_id=item.evidence_id,
        field_path=item.field_path,
    )


# ---------------------------------------------------------------------------
# Helper 6: issue_from_staleness_finding_for_horizon
# ---------------------------------------------------------------------------

def issue_from_staleness_finding_for_horizon(
    finding: StalenessFinding,
    horizon: Optional[HorizonBucket] = None,
) -> HorizonSynthesisIssue:
    """
    Convert a StalenessFinding into a HorizonSynthesisIssue.

    Mapping:
        status == "unknown" → missing_evidence (timestamp missing/unparseable)
        status in ("stale", "near_stale", "expired") → stale_evidence

    Preserves: finding_id as related_id, evidence_id, field_path, object_id.
    """
    issue_type: HorizonSynthesisIssueType = (
        "missing_evidence" if finding.status == "unknown" else "stale_evidence"
    )

    severity: Literal["critical", "warning", "info"] = (
        "critical" if finding.severity == "critical"
        else "info" if finding.severity == "info"
        else "warning"
    )

    issue_id = make_horizon_synthesis_issue_id(
        issue_type=issue_type,
        horizon=horizon,
        message=finding.message,
        related_id=finding.finding_id,
        evidence_id=finding.evidence_id,
        field_path=finding.field_path,
    )

    meta: dict[str, Any] = {}
    if finding.object_id:
        meta["object_id"] = finding.object_id

    return HorizonSynthesisIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        horizon=horizon,
        severity=severity,
        message=finding.message,
        related_id=finding.finding_id,
        evidence_id=finding.evidence_id,
        field_path=finding.field_path,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Helper 7: issue_from_critic_issue_for_horizon
# ---------------------------------------------------------------------------

def issue_from_critic_issue_for_horizon(
    issue: CriticIssue,
    horizon: Optional[HorizonBucket] = None,
) -> HorizonSynthesisIssue:
    """
    Convert a CriticIssue into a HorizonSynthesisIssue.

    Mapping:
        overconfidence     → overconfidence
        missing_risk       → missing_risk
        missing_assumption → missing_assumption
        conflicting_evidence → conflicting_signal
        stale_evidence     → stale_evidence
        unsupported_claim  → unsupported_claim
        weak_evidence      → missing_evidence
        others             → validation_issue / other

    Preserves: issue.issue_id as related_id, evidence_id, field_path.
    """
    issue_type_str: str = _CRITIC_TYPE_MAP.get(issue.issue_type, "other")
    issue_type: HorizonSynthesisIssueType = issue_type_str  # type: ignore[assignment]

    severity: Literal["critical", "warning", "info"] = (
        "critical" if issue.severity == "critical"
        else "info" if issue.severity == "info"
        else "warning"
    )

    issue_id = make_horizon_synthesis_issue_id(
        issue_type=issue_type_str,
        horizon=horizon,
        message=issue.message,
        related_id=issue.issue_id,
        evidence_id=issue.evidence_id,
        field_path=issue.field_path,
    )

    return HorizonSynthesisIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        horizon=horizon,
        severity=severity,
        message=issue.message,
        related_id=issue.issue_id,
        evidence_id=issue.evidence_id,
        field_path=issue.field_path,
    )


# ---------------------------------------------------------------------------
# Helper 8: build_horizon_synthesis_card
# ---------------------------------------------------------------------------

def build_horizon_synthesis_card(
    horizon: HorizonBucket,
    evidence_summary: HorizonEvidenceSummary,
    validation_aggregate: Optional[ValidationAggregate] = None,
    staleness_report: Optional[StalenessReport] = None,
    critic_result: Optional[CriticResult] = None,
    agent_result: Optional[AgentResult] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> HorizonSynthesisCard:
    """
    Build one HorizonSynthesisCard for a specific horizon bucket.

    Behavior:
        - Converts validation/staleness/critic artifacts to issues.
        - Adds missing-domain warning issues for each uncovered expected domain.
        - Derives signal_direction from issue types and evidence count.
        - Derives confidence from evidence count and issue severity.
        - Populates thesis_summary/supported_points/risks/assumptions from
          agent_result when provided (mock language only; no investment advice).
        - Does not call LLM, does not fetch data, does not mutate inputs.
        - status/recommendation are normalized by the model validator.
    """
    issues: list[HorizonSynthesisIssue] = []

    # Convert validation items
    if validation_aggregate is not None:
        for item in validation_aggregate.items:
            issues.append(issue_from_validation_item_for_horizon(item, horizon))

    # Convert non-fresh staleness findings
    if staleness_report is not None:
        for finding in staleness_report.findings:
            if finding.status != "fresh":
                issues.append(issue_from_staleness_finding_for_horizon(finding, horizon))

    # Convert critic issues
    if critic_result is not None:
        for ci in critic_result.issues:
            issues.append(issue_from_critic_issue_for_horizon(ci, horizon))

    # Add warning issues for each missing expected domain
    for domain in evidence_summary.missing_domains:
        missing_msg = (
            f"Missing expected evidence domain '{domain}' for {horizon} synthesis."
        )
        missing_id = make_horizon_synthesis_issue_id(
            issue_type="missing_evidence",
            horizon=horizon,
            message=missing_msg,
        )
        issues.append(HorizonSynthesisIssue(
            issue_id=missing_id,
            issue_type="missing_evidence",
            horizon=horizon,
            severity="warning",
            message=missing_msg,
        ))

    # Signal direction
    has_conflicting = any(i.issue_type == "conflicting_signal" for i in issues)
    if evidence_summary.evidence_count == 0:
        signal_direction: HorizonSignalDirection = "insufficient_evidence"
    elif has_conflicting:
        signal_direction = "mixed"
    else:
        signal_direction = "unknown"

    # Confidence
    has_critical_issues = any(i.severity == "critical" for i in issues)
    has_warning_issues = any(i.severity == "warning" for i in issues)

    if evidence_summary.evidence_count == 0:
        confidence: HorizonConfidenceLevel = "insufficient_evidence"
    elif has_critical_issues:
        confidence = "insufficient_evidence"
    elif evidence_summary.missing_domains or has_warning_issues:
        confidence = "low"
    else:
        confidence = "medium"

    # Thesis summary and supported content (mock language only)
    thesis_summary: Optional[str]
    supported_points: list[str] = []
    risks: list[str] = []
    assumptions: list[str] = []

    if evidence_summary.evidence_count == 0:
        thesis_summary = "Evidence is insufficient for this horizon."
    else:
        thesis_summary = (
            "Existing artifacts support a preliminary synthesis only. "
            "Requires debate/review before decision."
        )
        if agent_result is not None:
            for finding in agent_result.findings[:3]:
                supported_points.append(finding.text[:200])
            for risk in agent_result.risks[:3]:
                risks.append(risk.name)
            for assumption in agent_result.assumptions[:3]:
                assumptions.append(assumption.name)

    missing_evidence_list = list(evidence_summary.missing_domains)

    return HorizonSynthesisCard(
        horizon=horizon,
        signal_direction=signal_direction,
        confidence=confidence,
        thesis_summary=thesis_summary,
        supported_points=supported_points,
        risks=risks,
        assumptions=assumptions,
        missing_evidence=missing_evidence_list,
        evidence_summary=evidence_summary,
        issues=issues,
        metadata=dict(metadata) if metadata else {},
    )


# ---------------------------------------------------------------------------
# Helper 9: build_horizon_synthesis_report
# ---------------------------------------------------------------------------

def build_horizon_synthesis_report(
    synthesis_id: str,
    as_of: str,
    cards: list[HorizonSynthesisCard],
    ticker: Optional[str] = None,
    validation_aggregate: Optional[ValidationAggregate] = None,
    staleness_report: Optional[StalenessReport] = None,
    critic_result: Optional[CriticResult] = None,
    orchestration_report_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> HorizonSynthesisReport:
    """
    Build a normalized HorizonSynthesisReport from provided components.

    Card ordering and status/recommendation normalization are handled by
    the HorizonSynthesisReport model_validator.
    Does not mutate inputs.
    """
    return HorizonSynthesisReport(
        synthesis_id=synthesis_id,
        as_of=as_of,
        ticker=ticker,
        cards=list(cards),
        validation_aggregate=validation_aggregate,
        staleness_report=staleness_report,
        critic_result=critic_result,
        orchestration_report_id=orchestration_report_id,
        issues=[],
        metadata=dict(metadata) if metadata else {},
    )


# ---------------------------------------------------------------------------
# Helper 10: run_horizon_aware_synthesis
# ---------------------------------------------------------------------------

def run_horizon_aware_synthesis(
    input_bundle: HorizonSynthesisInputBundle,
) -> HorizonSynthesisReport:
    """
    End-to-end deterministic horizon-aware synthesis.

    Behavior:
        - Resolves validation_aggregate, staleness_report, critic_result from
          the bundle directly, or falls back to orchestration_report attributes.
        - Builds three horizon cards: short_term, medium_term, long_term.
        - Does not call external APIs.
        - Does not call LLM.
        - Does not import live/app modules.
        - Does not mutate input_bundle.
    """
    as_of = input_bundle.as_of

    # Resolve reliability artifacts: prefer direct bundle fields, then fallback
    validation_aggregate: Optional[ValidationAggregate] = input_bundle.validation_aggregate
    staleness_report: Optional[StalenessReport] = input_bundle.staleness_report
    critic_result: Optional[CriticResult] = input_bundle.critic_result

    orchestration_report_id: Optional[str] = None
    if input_bundle.orchestration_report is not None:
        orch = input_bundle.orchestration_report
        if validation_aggregate is None:
            validation_aggregate = getattr(orch, "validation_aggregate", None)
        if staleness_report is None:
            staleness_report = getattr(orch, "staleness_report", None)
        if critic_result is None:
            critic_result = getattr(orch, "critic_result", None)
        orchestration_report_id = getattr(orch, "orchestration_id", None)

    # Build one card per horizon
    cards: list[HorizonSynthesisCard] = []
    for horizon in _HORIZON_ORDER:
        horizon_bucket: HorizonBucket = horizon  # type: ignore[assignment]
        evidence_summary = summarize_horizon_evidence(
            horizon=horizon_bucket,
            agent_result=input_bundle.agent_result,
            tool_results=list(input_bundle.tool_results),
            validation_aggregate=validation_aggregate,
            staleness_report=staleness_report,
            critic_result=critic_result,
        )
        card = build_horizon_synthesis_card(
            horizon=horizon_bucket,
            evidence_summary=evidence_summary,
            validation_aggregate=validation_aggregate,
            staleness_report=staleness_report,
            critic_result=critic_result,
            agent_result=input_bundle.agent_result,
        )
        cards.append(card)

    synthesis_id = make_horizon_synthesis_id(
        bundle_id=input_bundle.bundle_id,
        as_of=as_of,
        ticker=input_bundle.ticker,
    )

    return build_horizon_synthesis_report(
        synthesis_id=synthesis_id,
        as_of=as_of,
        cards=cards,
        ticker=input_bundle.ticker,
        validation_aggregate=validation_aggregate,
        staleness_report=staleness_report,
        critic_result=critic_result,
        orchestration_report_id=orchestration_report_id,
        metadata=dict(input_bundle.metadata) if input_bundle.metadata else {},
    )


# ---------------------------------------------------------------------------
# Helper 11: horizon_synthesis_tool_result_from_report
# ---------------------------------------------------------------------------

def horizon_synthesis_tool_result_from_report(
    run_id: str,
    report: HorizonSynthesisReport,
    target: Optional[str] = None,
    calculation_version: str = "horizon_synthesis_skeleton_v1",
) -> ToolResult:
    """
    Wrap a HorizonSynthesisReport as a ToolResult for evidence auditability.

    Behavior:
        - tool_name = "horizon_synthesis_report" (stable).
        - target defaults to report.ticker if present, else "horizon_synthesis".
        - evidence_id is deterministic: same run_id + same stable ID payload
          always produces the same evidence_id.
        - payload["report"] = full serialized HorizonSynthesisReport.
        - payload["summary"] = compact summarize_horizon_synthesis_report() dict.
        - payload["calculation_version"] = version tag.
        - Does not mutate report.
        - Does not fake evidence.
    """
    effective_target = target or report.ticker or "horizon_synthesis"

    # Build the full payload first so the evidence_id is content-sensitive.
    # Changing report content under the same synthesis_id/as_of/target/version
    # must change the evidence_id; identical content must produce the same ID.
    payload: dict[str, Any] = {
        "report": report.model_dump(mode="json"),
        "summary": summarize_horizon_synthesis_report(report),
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_HORIZON_TOOL_NAME,
        target=effective_target,
        metric_group=_HORIZON_METRIC_GROUP,
        payload=payload,
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_HORIZON_TOOL_NAME,
        run_id=run_id,
        inputs={
            "synthesis_id": report.synthesis_id,
            "as_of": report.as_of,
            "target": effective_target,
            "calculation_version": calculation_version,
        },
        outputs=payload,
        description=(
            f"HorizonSynthesisReport {report.synthesis_id!r}"
            f" as_of={report.as_of!r}"
            f" status={report.status!r}"
            f" recommendation={report.recommendation!r}"
        ),
    )


# ---------------------------------------------------------------------------
# Helper 12: summarize_horizon_synthesis_report
# ---------------------------------------------------------------------------

def summarize_horizon_synthesis_report(report: HorizonSynthesisReport) -> dict[str, Any]:
    """
    Return a concise summary dict of a HorizonSynthesisReport.

    Keys: synthesis_id, ticker, status, recommendation, card_count,
    issue_count, critical_count, warning_count, info_count,
    horizon_statuses, horizon_recommendations, top_messages (capped at 10).
    """
    all_issues: list[HorizonSynthesisIssue] = list(report.issues)
    for card in report.cards:
        all_issues.extend(card.issues)

    critical_count = sum(1 for i in all_issues if i.severity == "critical")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    info_count = sum(1 for i in all_issues if i.severity == "info")
    top_messages = [i.message for i in all_issues[:10]]

    horizon_statuses = {card.horizon: card.status for card in report.cards}
    horizon_recommendations = {card.horizon: card.recommendation for card in report.cards}

    return {
        "synthesis_id": report.synthesis_id,
        "ticker": report.ticker,
        "status": report.status,
        "recommendation": report.recommendation,
        "card_count": len(report.cards),
        "issue_count": len(all_issues),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "horizon_statuses": horizon_statuses,
        "horizon_recommendations": horizon_recommendations,
        "top_messages": top_messages,
    }
