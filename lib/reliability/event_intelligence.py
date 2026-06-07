"""
lib/reliability/event_intelligence.py

Phase 3R-A: Event Intelligence Agents Skeleton.

Design principles:
  - Standalone, deterministic, offline.
  - No live LLM calls, no live data fetching, no app integration.
  - No broker / order / execution behavior.
  - Consumes ToolResult evidence via source IDs from prior phases.
  - Produces structured event intelligence assessments for:
      CatalystAssessment, NewsImpactAssessment,
      EarningsPlaybookAssessment, EstimateRevisionAssessment.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell recommendations, or
    individual security recommendations.
  - approved_for_execution is ALWAYS False. No pathway to set it True exists.
  - Mock/dry-run only; all outputs are explicitly evidence-aware.
  - Missing optional event categories produce warnings, not crashes.

Relationship to Phase 2G:
  - Phase 2G (catalysts.py) provides data-layer schemas for CatalystEvent,
    EarningsEvent, and EstimateRevision. This module adds agent-level
    assessment schemas that interpret and assess those data-layer artifacts.
  - EventRevisionMetric and EventRevisionDirection are new here (distinct from
    Phase 2G EstimateMetric / RevisionDirection to match agent-level semantics).

Phase 3R-A is part of the Roadmap v4 Phase 3 backfill sequence.
It delivers offline / dry-run agent skeleton implementations for the four
event intelligence domains specified in Roadmap v4 Phase 3D-3G.

See docs/reliability_phase_3r_event_intelligence.md for design.

Disclaimer: All outputs are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import ToolResult


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Literal type aliases (enums)
# ---------------------------------------------------------------------------

EventIntelligenceStatus = Literal[
    "unknown",
    "complete",
    "needs_review",
    "blocked",
]

EventCategory = Literal[
    "catalyst",
    "news",
    "earnings",
    "estimate_revision",
    "macro",
    "regulatory",
    "product",
    "management",
    "legal",
    "other",
    "unknown",
]

EventImpactDirection = Literal[
    "positive",
    "negative",
    "mixed",
    "neutral",
    "unknown",
]

EventImpactMagnitude = Literal[
    "low",
    "medium",
    "high",
    "unknown",
]

EventReviewTrigger = Literal[
    "no_review_needed",
    "monitor",
    "review_before_event",
    "review_after_event",
    "thesis_changing",
    "risk_escalation",
    "unknown",
]

EventEvidenceQuality = Literal[
    "unsupported",
    "weak",
    "adequate",
    "strong",
    "unknown",
]

EarningsPlaybookAction = Literal[
    "hold",
    "reduce",
    "wait",
    "review_after",
    "unknown",
]

EventRevisionMetric = Literal[
    "eps",
    "revenue",
    "margin",
    "rating",
    "price_target",
    "guidance",
    "other",
    "unknown",
]

EventRevisionDirection = Literal[
    "up",
    "down",
    "mixed",
    "unchanged",
    "unknown",
]

EventRevisionValuationImpact = Literal[
    "supports_valuation",
    "risks_valuation",
    "neutral",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_EVENT_INTEL_TOOL_NAME: str = "event_intelligence_report"
_EVENT_INTEL_METRIC_GROUP: str = "event_intelligence_report"
_CALCULATION_VERSION: str = "event_intelligence_report_v1"

# Review triggers that require explicit review (used in status and summary logic)
_REVIEW_REQUIRED_TRIGGERS: frozenset[str] = frozenset({
    "review_before_event",
    "review_after_event",
    "thesis_changing",
    "risk_escalation",
})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CatalystAssessment(BaseModel):
    """
    Agent-level assessment of one catalyst event.

    approved_for_execution is always False — this assessment is research-only
    and does not authorize any execution or trade action.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    event_name: str = Field(min_length=1)
    category: EventCategory = "catalyst"
    event_date: Optional[str] = None
    affected_horizons: list[str] = Field(default_factory=list)
    expected_impact_direction: EventImpactDirection = "unknown"
    expected_impact_magnitude: EventImpactMagnitude = "unknown"
    thesis_link: Optional[str] = None
    review_trigger: EventReviewTrigger = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_quality: EventEvidenceQuality = "unknown"
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "CatalystAssessment":
        for fn in ("event_id", "ticker", "event_name"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "CatalystAssessment":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-A. "
                "This layer does not authorize execution."
            )
        return self


class NewsImpactAssessment(BaseModel):
    """
    Agent-level assessment of one news item's impact on a target.

    approved_for_execution is always False — this assessment is research-only
    and does not authorize any execution or trade action.
    """

    model_config = ConfigDict(extra="forbid")

    news_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    source: str = Field(min_length=1)
    url: Optional[str] = None
    published_at: Optional[str] = None
    relevance_level: EventImpactMagnitude = "unknown"
    impact_direction: EventImpactDirection = "unknown"
    impact_magnitude: EventImpactMagnitude = "unknown"
    thesis_changing: bool = False
    is_noise: bool = False
    affected_horizons: list[str] = Field(default_factory=list)
    review_trigger: EventReviewTrigger = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_quality: EventEvidenceQuality = "unknown"
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "NewsImpactAssessment":
        for fn in ("news_id", "ticker", "headline", "source"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "NewsImpactAssessment":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-A. "
                "This layer does not authorize execution."
            )
        return self


class EarningsPlaybookAssessment(BaseModel):
    """
    Pre- and post-earnings checklist assessment.

    Captures pre-earnings expectations, key metrics, and implied move.
    possible_action is a research-only assessment; it does not authorize
    any execution or trade action. approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    earnings_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    earnings_date: Optional[str] = None
    period: Optional[str] = None
    pre_earnings_expectation: str = "unknown"
    key_metrics_to_watch: list[str] = Field(default_factory=list)
    implied_move: Optional[float] = None
    guidance_focus: str = "unknown"
    possible_action: EarningsPlaybookAction = "unknown"
    post_earnings_review_required: bool = False
    affected_horizons: list[str] = Field(default_factory=list)
    review_trigger: EventReviewTrigger = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_quality: EventEvidenceQuality = "unknown"
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "EarningsPlaybookAssessment":
        for fn in ("earnings_id", "ticker"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "EarningsPlaybookAssessment":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-A. "
                "This layer does not authorize execution."
            )
        return self


class EstimateRevisionAssessment(BaseModel):
    """
    Assessment of one consensus estimate revision event.

    approved_for_execution is always False — this assessment is research-only
    and does not authorize any execution or trade action.
    """

    model_config = ConfigDict(extra="forbid")

    revision_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    revision_metric: EventRevisionMetric = "unknown"
    revision_direction: EventRevisionDirection = "unknown"
    revision_magnitude: EventImpactMagnitude = "unknown"
    medium_term_impact: str = "unknown"
    valuation_support_or_risk: EventRevisionValuationImpact = "unknown"
    affected_horizons: list[str] = Field(default_factory=list)
    review_trigger: EventReviewTrigger = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_quality: EventEvidenceQuality = "unknown"
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "EstimateRevisionAssessment":
        for fn in ("revision_id", "ticker"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "EstimateRevisionAssessment":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-A. "
                "This layer does not authorize execution."
            )
        return self


class EventIntelligenceBundle(BaseModel):
    """
    Aggregate container for all event intelligence assessments for one target.

    Optional assessment lists default to empty. Missing categories produce
    warnings in the report rather than errors.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    catalyst_assessments: list[CatalystAssessment] = Field(default_factory=list)
    news_impact_assessments: list[NewsImpactAssessment] = Field(default_factory=list)
    earnings_playbooks: list[EarningsPlaybookAssessment] = Field(default_factory=list)
    estimate_revision_assessments: list[EstimateRevisionAssessment] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "EventIntelligenceBundle":
        for fn in ("bundle_id", "target", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class EventIntelligenceSummary(BaseModel):
    """
    Deterministic summary of one event intelligence analysis pass.

    Computed from the bundle and resolved status.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    status: EventIntelligenceStatus = "unknown"
    catalyst_count: int = 0
    news_count: int = 0
    earnings_count: int = 0
    revision_count: int = 0
    thesis_changing_event_count: int = 0
    review_required_count: int = 0
    high_impact_event_count: int = 0
    affected_horizons: list[str] = Field(default_factory=list)
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "EventIntelligenceSummary":
        v = self.target
        if not v.strip():
            raise ValueError(f"'target' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "EventIntelligenceSummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-A. "
                "This layer does not authorize execution."
            )
        return self


class EventIntelligenceReport(BaseModel):
    """
    Full event intelligence report for one analysis pass.

    Composes all four assessment types into a single auditable research artifact.

    approved_for_execution is ALWAYS False.  This report is a research
    artifact only and does not constitute investment advice or authorize
    any form of execution.
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    target: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: EventIntelligenceStatus = "unknown"
    bundle: EventIntelligenceBundle
    summary: EventIntelligenceSummary
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "EventIntelligenceReport":
        for fn in ("report_id", "target", "run_id", "created_at"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "EventIntelligenceReport":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-A. "
                "This layer does not authorize execution."
            )
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generators
# ---------------------------------------------------------------------------

def make_event_intelligence_report_id(
    run_id: str,
    target: str,
    as_of: str,
) -> str:
    """Return a deterministic stable hash ID for an EventIntelligenceReport."""
    payload = {"run_id": run_id, "target": target, "as_of": as_of}
    h = stable_hash_payload(payload, length=16)
    return f"eil_{h}"


def make_event_intelligence_bundle_id(
    target: str,
    as_of: str,
) -> str:
    """Return a deterministic stable hash ID for an EventIntelligenceBundle."""
    payload = {"target": target, "as_of": as_of, "type": "bundle"}
    h = stable_hash_payload(payload, length=16)
    return f"eib_{h}"


# ---------------------------------------------------------------------------
# Helper: status determination
# ---------------------------------------------------------------------------

def determine_event_intelligence_status(
    bundle: EventIntelligenceBundle,
) -> EventIntelligenceStatus:
    """
    Derive EventIntelligenceStatus from the bundle contents.

    Priority (highest wins):
      blocked      — any assessment has review_trigger == "risk_escalation".
      needs_review — thesis_changing news, high-impact event, or review triggers
                     that require explicit review.
      complete     — has assessments, none requiring review.
      unknown      — no assessments in bundle.

    Does not mutate bundle.
    approved_for_execution is never implied by any status value.
    """
    has_events = bool(
        bundle.catalyst_assessments
        or bundle.news_impact_assessments
        or bundle.earnings_playbooks
        or bundle.estimate_revision_assessments
    )
    if not has_events:
        return "unknown"

    # blocked (highest precedence): risk_escalation trigger on any assessment
    for ca in bundle.catalyst_assessments:
        if ca.review_trigger == "risk_escalation":
            return "blocked"
    for ni in bundle.news_impact_assessments:
        if ni.review_trigger == "risk_escalation":
            return "blocked"
    for ep in bundle.earnings_playbooks:
        if ep.review_trigger == "risk_escalation":
            return "blocked"
    for er in bundle.estimate_revision_assessments:
        if er.review_trigger == "risk_escalation":
            return "blocked"

    # needs_review: thesis_changing news, high-impact events, or review triggers
    _review_triggers = frozenset({"thesis_changing", "review_before_event", "review_after_event"})

    for ni in bundle.news_impact_assessments:
        if ni.thesis_changing:
            return "needs_review"
        if ni.impact_magnitude == "high":
            return "needs_review"
        if ni.review_trigger in _review_triggers:
            return "needs_review"

    for ca in bundle.catalyst_assessments:
        if ca.expected_impact_magnitude == "high":
            return "needs_review"
        if ca.review_trigger in _review_triggers:
            return "needs_review"

    for ep in bundle.earnings_playbooks:
        if ep.post_earnings_review_required:
            return "needs_review"
        if ep.review_trigger in _review_triggers:
            return "needs_review"

    for er in bundle.estimate_revision_assessments:
        if er.revision_magnitude == "high":
            return "needs_review"
        if er.review_trigger in _review_triggers:
            return "needs_review"

    return "complete"


# ---------------------------------------------------------------------------
# Helper: source ID collection
# ---------------------------------------------------------------------------

def collect_event_intelligence_source_ids(
    bundle: EventIntelligenceBundle,
) -> list[str]:
    """
    Collect all source/evidence IDs from the bundle deterministically.

    Collection order:
      1. Bundle-level source_ids.
      2. CatalystAssessment evidence_refs (in order).
      3. NewsImpactAssessment evidence_refs.
      4. EarningsPlaybookAssessment evidence_refs.
      5. EstimateRevisionAssessment evidence_refs.

    Deduplicates preserving first-occurrence order.
    Does not mutate bundle.
    """
    seen: set[str] = set()
    ids: list[str] = []

    def _add(eid: str) -> None:
        if eid and eid not in seen:
            seen.add(eid)
            ids.append(eid)

    for sid in bundle.source_ids:
        _add(sid)

    for ca in bundle.catalyst_assessments:
        for ref in ca.evidence_refs:
            _add(ref)

    for ni in bundle.news_impact_assessments:
        for ref in ni.evidence_refs:
            _add(ref)

    for ep in bundle.earnings_playbooks:
        for ref in ep.evidence_refs:
            _add(ref)

    for er in bundle.estimate_revision_assessments:
        for ref in er.evidence_refs:
            _add(ref)

    return ids


# ---------------------------------------------------------------------------
# Private: warning generation
# ---------------------------------------------------------------------------

def _generate_event_intelligence_warnings(
    bundle: EventIntelligenceBundle,
) -> list[str]:
    """
    Generate derived (report-level) warnings for missing or low-quality evidence.

    Returns ONLY newly generated warnings — does NOT include bundle.warnings.
    Callers are responsible for combining with bundle.warnings when assembling
    the final report.warnings list.

    Warns when:
      - A high-impact catalyst has unsupported or unknown evidence_quality.
      - A thesis-changing news item has unsupported or unknown evidence_quality.
      - All four assessment categories are absent.

    Does not crash on empty categories. Does not mutate bundle.
    """
    generated: list[str] = []

    for ca in bundle.catalyst_assessments:
        if (
            ca.expected_impact_magnitude == "high"
            and ca.evidence_quality in ("unsupported", "unknown")
        ):
            generated.append(
                f"CatalystAssessment '{ca.event_id}' is high-impact but "
                f"evidence_quality='{ca.evidence_quality}'. Manual review required."
            )

    for ni in bundle.news_impact_assessments:
        if ni.thesis_changing and ni.evidence_quality in ("unsupported", "unknown"):
            generated.append(
                f"NewsImpactAssessment '{ni.news_id}' is thesis-changing but "
                f"evidence_quality='{ni.evidence_quality}'. Manual review required."
            )

    if not (
        bundle.catalyst_assessments
        or bundle.news_impact_assessments
        or bundle.earnings_playbooks
        or bundle.estimate_revision_assessments
    ):
        generated.append(
            "EventIntelligenceBundle has no assessments in any category. "
            "Status will be 'unknown'."
        )

    return generated


# ---------------------------------------------------------------------------
# Helper: summary builder
# ---------------------------------------------------------------------------

def summarize_event_intelligence(
    bundle: EventIntelligenceBundle,
    status: EventIntelligenceStatus,
    source_ids: list[str],
    extra_warnings: Optional[list[str]] = None,
) -> EventIntelligenceSummary:
    """
    Build a deterministic EventIntelligenceSummary from the bundle and status.

    extra_warnings: optional list of generated (report-level) warnings to include
    in top_warnings alongside bundle and assessment warnings.  Pass the output of
    _generate_event_intelligence_warnings() here so generated warnings appear in
    the summary.

    top_warnings is assembled as: bundle.warnings + assessment.warnings +
    extra_warnings, deduplicated preserving first-occurrence order, capped at 5.

    Does not mutate inputs.
    approved_for_execution is always False.
    """
    # thesis_changing_event_count
    thesis_changing_event_count = sum(
        1 for ni in bundle.news_impact_assessments if ni.thesis_changing
    )

    # review_required_count
    review_required_count = 0
    for ca in bundle.catalyst_assessments:
        if ca.review_trigger in _REVIEW_REQUIRED_TRIGGERS:
            review_required_count += 1
    for ni in bundle.news_impact_assessments:
        if ni.thesis_changing or ni.review_trigger in _REVIEW_REQUIRED_TRIGGERS:
            review_required_count += 1
    for ep in bundle.earnings_playbooks:
        if ep.post_earnings_review_required or ep.review_trigger in _REVIEW_REQUIRED_TRIGGERS:
            review_required_count += 1
    for er in bundle.estimate_revision_assessments:
        if er.review_trigger in _REVIEW_REQUIRED_TRIGGERS:
            review_required_count += 1

    # high_impact_event_count
    high_impact_event_count = 0
    for ca in bundle.catalyst_assessments:
        if ca.expected_impact_magnitude == "high":
            high_impact_event_count += 1
    for ni in bundle.news_impact_assessments:
        if ni.impact_magnitude == "high":
            high_impact_event_count += 1
    for er in bundle.estimate_revision_assessments:
        if er.revision_magnitude == "high":
            high_impact_event_count += 1

    # affected_horizons — union, deduplicated, preserving first-occurrence order
    seen_h: set[str] = set()
    affected_horizons: list[str] = []
    all_assessments: list[Any] = [
        *bundle.catalyst_assessments,
        *bundle.news_impact_assessments,
        *bundle.earnings_playbooks,
        *bundle.estimate_revision_assessments,
    ]
    for a in all_assessments:
        for h in a.affected_horizons:
            if h not in seen_h:
                seen_h.add(h)
                affected_horizons.append(h)

    # top_warnings — bundle + assessment + extra (generated) warnings, deduped, first 5
    all_warnings: list[str] = list(bundle.warnings)
    for a in all_assessments:
        all_warnings.extend(a.warnings)
    if extra_warnings:
        all_warnings.extend(extra_warnings)
    seen_w: set[str] = set()
    deduped_warnings: list[str] = []
    for w in all_warnings:
        if w not in seen_w:
            seen_w.add(w)
            deduped_warnings.append(w)
    top_warnings = deduped_warnings[:5]

    return EventIntelligenceSummary(
        target=bundle.target,
        status=status,
        catalyst_count=len(bundle.catalyst_assessments),
        news_count=len(bundle.news_impact_assessments),
        earnings_count=len(bundle.earnings_playbooks),
        revision_count=len(bundle.estimate_revision_assessments),
        thesis_changing_event_count=thesis_changing_event_count,
        review_required_count=review_required_count,
        high_impact_event_count=high_impact_event_count,
        affected_horizons=affected_horizons,
        top_warnings=top_warnings,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Helper: main report builder
# ---------------------------------------------------------------------------

def build_event_intelligence_report(
    bundle: EventIntelligenceBundle,
    run_id: str,
    created_at: Optional[str] = None,
) -> EventIntelligenceReport:
    """
    Build a complete EventIntelligenceReport from the bundle.

    Steps:
      1. Generate derived warnings for evidence quality issues.
      2. Assemble full report warnings (bundle.warnings + generated), deduplicated.
      3. Collect source IDs deterministically.
      4. Determine run status.
      5. Build summary — includes generated warnings in top_warnings.
      6. Build report with stable deterministic report_id.

    Deterministic: identical inputs → identical outputs.
    created_at defaults to bundle.as_of when not supplied, making the full
    report output deterministic without an explicit timestamp argument.
    Pass created_at explicitly to override (e.g. for tests or audit records).

    No network calls. No LLM calls. No mutation of inputs.
    Does not constitute investment advice.
    approved_for_execution is always False.
    """
    # 1. Generated (derived) warnings
    generated_warnings = _generate_event_intelligence_warnings(bundle)

    # 2. Full report warnings = bundle.warnings + generated, deduplicated
    _raw_report_warnings = list(bundle.warnings) + generated_warnings
    seen_rw: set[str] = set()
    report_warnings: list[str] = []
    for w in _raw_report_warnings:
        if w not in seen_rw:
            seen_rw.add(w)
            report_warnings.append(w)

    # 3. Source IDs
    source_ids = collect_event_intelligence_source_ids(bundle)

    # 4. Status
    status = determine_event_intelligence_status(bundle)

    # 5. Summary — pass generated warnings so they appear in top_warnings
    summary = summarize_event_intelligence(
        bundle=bundle,
        status=status,
        source_ids=source_ids,
        extra_warnings=generated_warnings,
    )

    # 6. Report ID
    report_id = make_event_intelligence_report_id(
        run_id=run_id,
        target=bundle.target,
        as_of=bundle.as_of,
    )

    # Deterministic created_at: derive from bundle.as_of unless explicitly supplied.
    # This ensures identical inputs produce identical full report output.
    _created_at = created_at if created_at is not None else bundle.as_of

    return EventIntelligenceReport(
        report_id=report_id,
        target=bundle.target,
        run_id=run_id,
        status=status,
        bundle=bundle,
        summary=summary,
        source_ids=source_ids,
        warnings=report_warnings,
        created_at=_created_at,
        calculation_version=_CALCULATION_VERSION,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Helper: ToolResult adapter
# ---------------------------------------------------------------------------

def event_intelligence_tool_result_from_report(
    run_id: str,
    report: EventIntelligenceReport,
    target: Optional[str] = None,
    calculation_version: str = _CALCULATION_VERSION,
) -> ToolResult:
    """
    Wrap an EventIntelligenceReport as a ToolResult for evidence-aware pipelines.

    - tool_name is stable: "event_intelligence_report".
    - target defaults to report.target.
    - outputs includes the full report (serialized), summary, and calculation_version.
    - evidence_id is deterministic and content-sensitive.
    - Does not mutate report.
    - approved_for_execution is always False in the payload.
    - No live execution implication.
    """
    _target: str = target or report.target

    _report_dict = report.model_dump()
    _summary_dict: dict[str, Any] = {
        "report_id": report.report_id,
        "target": report.target,
        "run_id": report.run_id,
        "status": report.status,
        "catalyst_count": report.summary.catalyst_count,
        "news_count": report.summary.news_count,
        "earnings_count": report.summary.earnings_count,
        "revision_count": report.summary.revision_count,
        "thesis_changing_event_count": report.summary.thesis_changing_event_count,
        "review_required_count": report.summary.review_required_count,
        "high_impact_event_count": report.summary.high_impact_event_count,
        "warning_count": len(report.warnings),
        "source_id_count": len(report.source_ids),
        "approved_for_execution": False,  # Always False
    }

    outputs: dict[str, Any] = {
        "report": _report_dict,
        "summary": _summary_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_EVENT_INTEL_TOOL_NAME,
        target=_target,
        metric_group=_EVENT_INTEL_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_EVENT_INTEL_TOOL_NAME,
        run_id=run_id,
        ticker=report.target if report.target else None,
        inputs={"as_of": report.bundle.as_of, "target": _target},
        outputs=outputs,
        description=(
            f"EventIntelligenceReport for {report.target}: "
            f"status={report.status}, "
            f"catalysts={report.summary.catalyst_count}, "
            f"news={report.summary.news_count}, "
            f"earnings={report.summary.earnings_count}, "
            f"revisions={report.summary.revision_count}, "
            f"source_ids={len(report.source_ids)}, "
            f"warnings={len(report.warnings)}."
        ),
    )
