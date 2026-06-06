"""
lib/reliability/phase5_horizon_views.py

Phase 5C: Horizon Decision Cards + ThesisTracker ViewModel Contract.

Purpose
-------
Defines deterministic, cockpit-ready Pydantic view-model contracts that
project Phase 4M thesis memory (per horizon) and the Phase 5A
fixture-backed memory query result into:

  1. Horizon-specific decision cards
       - short-term trade
       - medium-term position
       - long-term investment
  2. ThesisTracker rows
       - thesis status, assumptions, invalidation triggers, review
         status, evidence/memory coverage, next review/action labels

This module is a **view-model contract layer only**. It does not connect
to the live Streamlit app, does not introduce a UI, does not perform any
data fetch, does not invoke any LLM, and does not produce trade
instructions or investment advice. It surfaces only what existing
Phase 4M memory records and Phase 5A query results carry, by reference.

Design principles
-----------------
- Standalone, deterministic, offline / mock-only.
- No live LLM calls.
- No live data fetching, no Streamlit, no Anthropic SDK calls.
- No database writes, no file persistence, no vector store.
- No reading of the live workflow state JSON file.
- No import of ``app.py``, ``pages/*``, ``lib/llm_orchestrator.py``, or
  ``lib/workflow_state.py``.
- No broker / order / execution behavior.
- No ``approved_for_execution`` field on any Phase 5C view; the upstream
  Phase 4M records and Phase 5A query result already reject truthy
  ``approved_for_execution`` at their model layers, so this view layer
  inherits the invariant by construction.

Horizon ordering
----------------
The canonical Phase 5C horizon iteration order is::

    short -> medium -> long

`HORIZON_ORDER` enumerates it. ThesisTracker rows are deterministically
ordered by ``(target, horizon_index)``.

Relationship to Phase 4M and Phase 5A
-------------------------------------
- Phase 4M-B (``HorizonThesisMemoryRecord``) supplies per-horizon thesis
  text, assumptions, and invalidation conditions.
- Phase 4M-C (``EventMemoryRecord``) supplies catalyst / news / earnings
  signals that may flip a thesis into a review-needed state.
- Phase 4M-F (``HumanFeedbackMemoryRecord``) supplies human review
  status and override flags.
- Phase 4M-G (``AgentEvaluationRecord``) supplies agent calibration and
  outcome grades.
- Phase 5A's ``MemoryStoreProtocol`` / ``MemoryQueryResult`` provide the
  query boundary.
- Phase 5B's identity contract is intentionally not imported (Phase 5C is
  panel-independent); callers may pair the Phase 5C view with a Phase 5B
  ``CompanyResearchHubView`` outside this module.

Disclaimer: outputs are for research / educational purposes only and do
not constitute investment advice.

See ``docs/reliability_phase_5c_horizon_decision_cards_thesis_tracker.md``.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.thesis_memory import (
    HorizonThesisMemoryRecord,
    ThesisAssumption,
    ThesisInvalidationCondition,
)
from lib.reliability.event_memory import EventMemoryRecord
from lib.reliability.human_feedback_memory import HumanFeedbackMemoryRecord
from lib.reliability.agent_evaluation import AgentEvaluationRecord
from lib.reliability.phase5_memory_query import (
    MemoryQueryByTicker,
    MemoryQueryResult,
    MemoryStoreProtocol,
)


# ---------------------------------------------------------------------------
# Literal aliases
# ---------------------------------------------------------------------------

HorizonKey = Literal["short", "medium", "long"]

HORIZON_ORDER: tuple[HorizonKey, ...] = ("short", "medium", "long")


# Subset of memory record types whose presence we track per-horizon for
# the missing-evidence badge. Thesis is the canonical anchor; the rest
# are optional context.
HorizonEvidenceKind = Literal[
    "thesis",
    "event",
    "human_feedback",
    "agent_evaluation",
]

HORIZON_EVIDENCE_KINDS: tuple[HorizonEvidenceKind, ...] = (
    "thesis",
    "event",
    "human_feedback",
    "agent_evaluation",
)


CardStatus = Literal[
    "active",
    "needs_review",
    "invalidated",
    "blocked",
    "archived",
    "superseded",
    "missing",
    "unknown",
]


_CALCULATION_VERSION: str = "phase5_horizon_views_v1"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _horizon_index(h: str) -> int:
    """Return deterministic horizon index for sorting. Unknown -> 99."""
    try:
        return HORIZON_ORDER.index(h)  # type: ignore[arg-type]
    except ValueError:
        return 99


def _is_truthy_review_required(record: Any) -> bool:
    rr = getattr(record, "review_required", None)
    if rr is not None:
        return bool(rr)
    summary = getattr(record, "summary", None)
    if summary is not None and not isinstance(summary, str):
        srr = getattr(summary, "review_required", None)
        if srr is not None:
            return bool(srr)
    return False


def _event_signals_review(record: EventMemoryRecord) -> bool:
    """An event signals a review if its review_status is pending/escalated,
    its impact is high, OR it is thesis_changing."""
    rs = str(getattr(record, "review_status", "") or "")
    if rs in ("pending", "escalated"):
        return True
    if str(getattr(record, "status", "") or "") in ("blocked", "needs_review"):
        return True
    if bool(getattr(record, "thesis_changing", False)):
        return True
    if str(getattr(record, "impact_magnitude", "") or "") == "high":
        return True
    return False


def _filter_events_for_horizon(
    events: list[EventMemoryRecord], horizon: HorizonKey
) -> list[EventMemoryRecord]:
    out: list[EventMemoryRecord] = []
    for e in events:
        ah = getattr(e, "affected_horizons", []) or []
        if horizon in ah:
            out.append(e)
    return out


def _filter_evaluations_for_horizon(
    evaluations: list[AgentEvaluationRecord], horizon: HorizonKey
) -> list[AgentEvaluationRecord]:
    out: list[AgentEvaluationRecord] = []
    for e in evaluations:
        # Try evaluation.target_ref.horizon first, then signals[*].horizon.
        target_ref = getattr(e, "target_ref", None)
        ref_h = getattr(target_ref, "horizon", None) if target_ref else None
        if ref_h == horizon:
            out.append(e)
            continue
        for s in getattr(e, "signals", []) or []:
            if getattr(s, "horizon", None) == horizon:
                out.append(e)
                break
    return out


def _query_result_for_target(
    memory_store: Optional[MemoryStoreProtocol],
    target: Optional[str],
) -> MemoryQueryResult:
    """Run a target-scoped memory query. Empty result if no store / target."""
    if memory_store is None or target is None or not str(target).strip():
        return MemoryQueryResult()
    return memory_store.query(MemoryQueryByTicker(target=target))


def _thesis_for_horizon(
    result: MemoryQueryResult, target: str, horizon: HorizonKey
) -> Optional[HorizonThesisMemoryRecord]:
    """Return the first thesis record matching (target, horizon) by insertion
    order, or None if missing. Phase 5C never fabricates a thesis."""
    for t in result.thesis_records:
        if getattr(t, "target", None) == target and getattr(t, "horizon", None) == horizon:
            return t
    return None


# ---------------------------------------------------------------------------
# View models — primitive sub-views
# ---------------------------------------------------------------------------


class HorizonAssumptionView(BaseModel):
    """Read-only projection of a single Phase 4M-B thesis assumption."""

    model_config = ConfigDict(extra="forbid")

    assumption_id: str = Field(min_length=1)
    description: str = ""
    horizon: str = "unknown"
    importance: str = "unknown"


class InvalidationTriggerView(BaseModel):
    """Read-only projection of a single Phase 4M-B invalidation condition."""

    model_config = ConfigDict(extra="forbid")

    condition_id: str = Field(min_length=1)
    invalidation_type: str = "unknown"
    description: str = ""
    horizon: str = "unknown"
    trigger_level: Optional[float] = None
    trigger_date: Optional[str] = None
    review_required: bool = False


class ThesisStatusView(BaseModel):
    """
    Read-only projection of one Phase 4M-B thesis record's status surface.

    Reflects what the underlying record carries. The view never fabricates a
    status: when no thesis exists, callers receive a ``"missing"`` /
    ``"unknown"`` card instead of this view.
    """

    model_config = ConfigDict(extra="forbid")

    thesis_id: str = Field(min_length=1)
    horizon: HorizonKey = "short"
    status: str = "unknown"
    direction: str = "unknown"
    confidence: str = "unknown"
    thesis_text: str = ""
    last_updated_at: Optional[str] = None


class ReviewNeededBadgeView(BaseModel):
    """
    Surfaces whether the card needs human or downstream review.

    ``review_needed`` is True when ANY of the following hold:
      - thesis status is ``blocked`` / ``needs_review`` / ``invalidated``
      - a catalyst / news / earnings event signals review
      - human feedback record carries ``review_required=True`` or has
        status ``needs_review`` / ``blocked``
      - agent evaluation record carries ``review_required=True`` or has
        status ``needs_review`` / ``blocked``
    """

    model_config = ConfigDict(extra="forbid")

    review_needed: bool = False
    reasons: list[str] = Field(default_factory=list)


class MissingEvidenceBadgeView(BaseModel):
    """
    Surfaces which memory record types are absent for the horizon.

    ``missing_kinds`` is the subset of ``HORIZON_EVIDENCE_KINDS`` that have
    no record contributing to this card. ``has_missing_evidence`` is the
    boolean shorthand. Thesis absence is the dominant case; the card itself
    is marked ``"missing"`` when the thesis is absent.
    """

    model_config = ConfigDict(extra="forbid")

    missing_kinds: list[HorizonEvidenceKind] = Field(default_factory=list)
    present_kinds: list[HorizonEvidenceKind] = Field(default_factory=list)
    has_missing_evidence: bool = False
    warnings: list[str] = Field(default_factory=list)


class HorizonEvidenceSummaryView(BaseModel):
    """
    Aggregate per-horizon evidence coverage projection.

    Counts of records contributing to this card from each Phase 4M memory
    type, plus de-duplicated evidence_ids and artifact_refs sourced from the
    thesis record (Phase 5C never invents new evidence IDs).
    """

    model_config = ConfigDict(extra="forbid")

    horizon: HorizonKey = "short"
    record_counts_by_kind: dict[str, int] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    has_thesis: bool = False
    has_any_evidence: bool = False


class HorizonRiskSummaryView(BaseModel):
    """
    Aggregate per-horizon risk projection.

    Counts and short descriptions of the invalidation triggers attached to
    the thesis record. Does not fabricate new risks; merely re-projects
    what Phase 4M-B carries.
    """

    model_config = ConfigDict(extra="forbid")

    horizon: HorizonKey = "short"
    invalidation_trigger_count: int = 0
    review_required_trigger_count: int = 0
    triggers: list[InvalidationTriggerView] = Field(default_factory=list)


class HorizonNextActionView(BaseModel):
    """
    Read-only "next action" label surface for the cockpit.

    Never contains executable instructions. ``label`` is one of:
      - ``"review_thesis"``          — block / needs_review
      - ``"refresh_invalidation"``   — invalidated
      - ``"none_supported"``         — no thesis / unknown
      - ``"watch"``                  — active default

    ``warnings`` enumerates the reasons. The cockpit can choose to display
    these labels, but the labels themselves are descriptive, not executive.
    """

    model_config = ConfigDict(extra="forbid")

    label: Literal[
        "review_thesis",
        "refresh_invalidation",
        "none_supported",
        "watch",
    ] = "none_supported"
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# View models — horizon decision card
# ---------------------------------------------------------------------------


class HorizonDecisionCardView(BaseModel):
    """
    One horizon-specific decision card.

    Designed to be cockpit-renderable. When the underlying thesis record is
    absent, ``is_populated=False``, ``status="missing"``, ``thesis=None``,
    and a warning is recorded. The view never fabricates a thesis,
    recommendation, target, or risk text.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    horizon: HorizonKey = "short"
    is_populated: bool = False
    status: CardStatus = "missing"
    thesis: Optional[ThesisStatusView] = None
    assumptions: list[HorizonAssumptionView] = Field(default_factory=list)
    invalidation_triggers: list[InvalidationTriggerView] = Field(default_factory=list)
    review_needed_badge: ReviewNeededBadgeView = Field(
        default_factory=ReviewNeededBadgeView
    )
    missing_evidence_badge: MissingEvidenceBadgeView = Field(
        default_factory=MissingEvidenceBadgeView
    )
    evidence_summary: HorizonEvidenceSummaryView
    risk_summary: HorizonRiskSummaryView
    next_action: HorizonNextActionView = Field(default_factory=HorizonNextActionView)
    related_event_ids: list[str] = Field(default_factory=list)
    related_human_feedback_ids: list[str] = Field(default_factory=list)
    related_agent_evaluation_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    calculation_version: str = _CALCULATION_VERSION


class HorizonDecisionCardsView(BaseModel):
    """
    Aggregate of horizon decision cards in canonical order: short → medium → long.

    The view always carries exactly three cards in canonical order. A horizon
    without a thesis still appears as a safe ``"missing"`` card so the
    cockpit can render the slot. ``warnings`` collects card-level warnings.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    cards: list[HorizonDecisionCardView] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    calculation_version: str = _CALCULATION_VERSION

    @model_validator(mode="after")
    def _validate(self) -> "HorizonDecisionCardsView":
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        if len(self.cards) != len(HORIZON_ORDER):
            raise ValueError(
                f"'cards' must contain exactly {len(HORIZON_ORDER)} entries "
                f"(short, medium, long); got {len(self.cards)}."
            )
        for expected, card in zip(HORIZON_ORDER, self.cards):
            if card.horizon != expected:
                raise ValueError(
                    "cards must be in canonical horizon order "
                    f"{HORIZON_ORDER}; got {[c.horizon for c in self.cards]}."
                )
        return self


# ---------------------------------------------------------------------------
# View models — thesis tracker
# ---------------------------------------------------------------------------


class ThesisTrackerRowView(BaseModel):
    """
    One ThesisTracker row, scoped to one (ticker, horizon) thesis.

    Rows are deterministic. When the thesis is missing, a safe degraded row
    with ``is_populated=False`` and ``status="missing"`` is produced — never
    a hallucinated row.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    horizon: HorizonKey = "short"
    is_populated: bool = False
    status: CardStatus = "missing"
    direction: str = "unknown"
    confidence: str = "unknown"
    thesis_id: Optional[str] = None
    last_updated_at: Optional[str] = None
    last_reviewed_at: Optional[str] = None
    invalidation_trigger_count: int = 0
    review_needed: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    missing_evidence_kinds: list[HorizonEvidenceKind] = Field(default_factory=list)
    evidence_id_count: int = 0
    next_action_label: str = "none_supported"
    warnings: list[str] = Field(default_factory=list)


class ThesisTrackerView(BaseModel):
    """
    Aggregate ThesisTracker projection.

    Rows are ordered deterministically by ``(target, horizon_index)``, then
    by insertion order within ties. A target with no thesis records yields
    three safe ``"missing"`` rows (one per horizon).

    No fabricated rows; no recommendation; no execution authority. Phase 5C
    does not surface ``approved_for_execution``.
    """

    model_config = ConfigDict(extra="forbid")

    rows: list[ThesisTrackerRowView] = Field(default_factory=list)
    target_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    calculation_version: str = _CALCULATION_VERSION


# ---------------------------------------------------------------------------
# Builder helpers — sub-views
# ---------------------------------------------------------------------------


def _project_assumptions(thesis: HorizonThesisMemoryRecord) -> list[HorizonAssumptionView]:
    out: list[HorizonAssumptionView] = []
    for a in thesis.assumptions:
        out.append(
            HorizonAssumptionView(
                assumption_id=a.assumption_id,
                description=a.description,
                horizon=str(a.horizon),
                importance=str(a.importance),
            )
        )
    return out


def _project_invalidations(
    thesis: HorizonThesisMemoryRecord,
) -> list[InvalidationTriggerView]:
    out: list[InvalidationTriggerView] = []
    for c in thesis.invalidation_conditions:
        out.append(
            InvalidationTriggerView(
                condition_id=c.condition_id,
                invalidation_type=str(c.invalidation_type),
                description=c.description,
                horizon=str(c.horizon),
                trigger_level=c.trigger_level,
                trigger_date=c.trigger_date,
                review_required=bool(c.review_required),
            )
        )
    return out


def build_horizon_evidence_summary(
    horizon: HorizonKey,
    thesis: Optional[HorizonThesisMemoryRecord],
    events: Optional[list[EventMemoryRecord]] = None,
    human_feedback_records: Optional[list[HumanFeedbackMemoryRecord]] = None,
    agent_evaluation_records: Optional[list[AgentEvaluationRecord]] = None,
) -> HorizonEvidenceSummaryView:
    """Build a deterministic ``HorizonEvidenceSummaryView`` for one horizon."""
    events = list(events or [])
    human_feedback_records = list(human_feedback_records or [])
    agent_evaluation_records = list(agent_evaluation_records or [])

    counts: dict[str, int] = {k: 0 for k in HORIZON_EVIDENCE_KINDS}
    evidence_ids: list[str] = []
    artifact_refs: list[str] = []
    source_ids: list[str] = []

    has_thesis = thesis is not None
    if has_thesis:
        counts["thesis"] = 1
        for eid in (thesis.evidence_ids or []):  # type: ignore[union-attr]
            if eid and eid not in evidence_ids:
                evidence_ids.append(eid)
        for ar in (thesis.artifact_refs or []):  # type: ignore[union-attr]
            if ar and ar not in artifact_refs:
                artifact_refs.append(ar)
        for sid in (thesis.source_ids or []):  # type: ignore[union-attr]
            if sid and sid not in source_ids:
                source_ids.append(sid)

    counts["event"] = len(events)
    counts["human_feedback"] = len(human_feedback_records)
    counts["agent_evaluation"] = len(agent_evaluation_records)

    has_any = (
        has_thesis
        or bool(events)
        or bool(human_feedback_records)
        or bool(agent_evaluation_records)
    )

    return HorizonEvidenceSummaryView(
        horizon=horizon,
        record_counts_by_kind=counts,
        evidence_ids=evidence_ids,
        artifact_refs=artifact_refs,
        source_ids=source_ids,
        has_thesis=has_thesis,
        has_any_evidence=has_any,
    )


def build_missing_evidence_badge(
    summary: HorizonEvidenceSummaryView,
) -> MissingEvidenceBadgeView:
    """Build a ``MissingEvidenceBadgeView`` from a horizon evidence summary."""
    missing: list[HorizonEvidenceKind] = []
    present: list[HorizonEvidenceKind] = []
    warnings: list[str] = []
    for kind in HORIZON_EVIDENCE_KINDS:
        c = int(summary.record_counts_by_kind.get(kind, 0))
        if c == 0:
            missing.append(kind)
        else:
            present.append(kind)
    if missing:
        warnings.append(
            "Horizon evidence coverage incomplete: missing kind(s) "
            f"{missing} for horizon={summary.horizon!r}."
        )
    return MissingEvidenceBadgeView(
        missing_kinds=missing,
        present_kinds=present,
        has_missing_evidence=bool(missing),
        warnings=warnings,
    )


def build_review_needed_badge(
    thesis: Optional[HorizonThesisMemoryRecord],
    events: Optional[list[EventMemoryRecord]] = None,
    human_feedback_records: Optional[list[HumanFeedbackMemoryRecord]] = None,
    agent_evaluation_records: Optional[list[AgentEvaluationRecord]] = None,
) -> ReviewNeededBadgeView:
    """Build a ``ReviewNeededBadgeView`` from per-horizon memory records."""
    events = list(events or [])
    human_feedback_records = list(human_feedback_records or [])
    agent_evaluation_records = list(agent_evaluation_records or [])

    reasons: list[str] = []

    if thesis is not None:
        ts = str(getattr(thesis, "status", "") or "")
        if ts == "blocked":
            reasons.append("Thesis status is 'blocked'.")
        elif ts == "needs_review":
            reasons.append("Thesis status is 'needs_review'.")
        elif ts == "invalidated":
            reasons.append("Thesis status is 'invalidated'.")
        # Invalidation conditions flagged review_required.
        rr_conds = [
            c for c in (thesis.invalidation_conditions or []) if getattr(c, "review_required", False)
        ]
        if rr_conds:
            reasons.append(
                f"{len(rr_conds)} invalidation trigger(s) flagged review_required."
            )

    for e in events:
        if _event_signals_review(e):
            name = str(getattr(e, "event_name", "")) or "event"
            rs = str(getattr(e, "review_status", "") or "")
            reasons.append(
                f"Event '{name}' signals review (review_status={rs!r})."
            )

    for f in human_feedback_records:
        if _is_truthy_review_required(f):
            reasons.append(
                f"Human feedback record requires review "
                f"(feedback_memory_id={getattr(f, 'feedback_memory_id', '')!r})."
            )
            continue
        fs = str(getattr(f, "status", "") or "")
        if fs in ("blocked", "needs_review"):
            reasons.append(
                f"Human feedback record status is {fs!r}."
            )

    for ev in agent_evaluation_records:
        if _is_truthy_review_required(ev):
            reasons.append(
                f"Agent evaluation record requires review "
                f"(evaluation_id={getattr(ev, 'evaluation_id', '')!r})."
            )
            continue
        es = str(getattr(ev, "status", "") or "")
        if es in ("blocked", "needs_review"):
            reasons.append(
                f"Agent evaluation record status is {es!r}."
            )

    return ReviewNeededBadgeView(
        review_needed=bool(reasons),
        reasons=reasons,
    )


def _derive_card_status(
    thesis: Optional[HorizonThesisMemoryRecord],
    review_badge: ReviewNeededBadgeView,
) -> CardStatus:
    if thesis is None:
        return "missing"
    ts = str(getattr(thesis, "status", "") or "")
    if ts == "blocked":
        return "blocked"
    if ts == "needs_review":
        return "needs_review"
    if ts == "invalidated":
        return "invalidated"
    if ts == "archived":
        return "archived"
    if ts == "superseded":
        return "superseded"
    if review_badge.review_needed:
        # Thesis itself active/unknown but downstream signal forces review.
        return "needs_review"
    if ts == "active":
        return "active"
    return "unknown"


def _derive_next_action(
    status: CardStatus,
    review_badge: ReviewNeededBadgeView,
) -> HorizonNextActionView:
    if status in ("blocked", "needs_review"):
        return HorizonNextActionView(
            label="review_thesis",
            warnings=list(review_badge.reasons or []) or [
                f"Thesis status is {status!r}; review recommended."
            ],
        )
    if status == "invalidated":
        return HorizonNextActionView(
            label="refresh_invalidation",
            warnings=["Thesis is invalidated; refresh invalidation conditions."],
        )
    if status in ("missing", "unknown", "archived", "superseded"):
        return HorizonNextActionView(
            label="none_supported",
            warnings=[
                f"Card status is {status!r}; no next action can be supported "
                "from current memory records."
            ],
        )
    return HorizonNextActionView(label="watch", warnings=[])


def build_horizon_decision_card(
    target: str,
    horizon: HorizonKey,
    thesis: Optional[HorizonThesisMemoryRecord] = None,
    events: Optional[list[EventMemoryRecord]] = None,
    human_feedback_records: Optional[list[HumanFeedbackMemoryRecord]] = None,
    agent_evaluation_records: Optional[list[AgentEvaluationRecord]] = None,
) -> HorizonDecisionCardView:
    """Build a deterministic ``HorizonDecisionCardView`` for one horizon."""
    if not target or not str(target).strip():
        raise ValueError("'target' must not be empty or whitespace-only.")
    if horizon not in HORIZON_ORDER:
        raise ValueError(
            f"Unknown horizon {horizon!r}; expected one of {HORIZON_ORDER}."
        )

    events = list(events or [])
    human_feedback_records = list(human_feedback_records or [])
    agent_evaluation_records = list(agent_evaluation_records or [])

    evidence_summary = build_horizon_evidence_summary(
        horizon=horizon,
        thesis=thesis,
        events=events,
        human_feedback_records=human_feedback_records,
        agent_evaluation_records=agent_evaluation_records,
    )
    missing_badge = build_missing_evidence_badge(summary=evidence_summary)
    review_badge = build_review_needed_badge(
        thesis=thesis,
        events=events,
        human_feedback_records=human_feedback_records,
        agent_evaluation_records=agent_evaluation_records,
    )
    status = _derive_card_status(thesis=thesis, review_badge=review_badge)

    warnings: list[str] = []
    if thesis is None:
        warnings.append(
            f"No thesis memory record found for horizon={horizon!r}; "
            "card returned in safe degraded ('missing') state."
        )

    thesis_view: Optional[ThesisStatusView] = None
    assumption_views: list[HorizonAssumptionView] = []
    invalidation_views: list[InvalidationTriggerView] = []
    if thesis is not None:
        thesis_view = ThesisStatusView(
            thesis_id=thesis.thesis_id,
            horizon=horizon,
            status=str(thesis.status),
            direction=str(thesis.direction),
            confidence=str(thesis.confidence),
            thesis_text=thesis.thesis_text,
            last_updated_at=thesis.updated_at,
        )
        assumption_views = _project_assumptions(thesis)
        invalidation_views = _project_invalidations(thesis)

    risk_summary = HorizonRiskSummaryView(
        horizon=horizon,
        invalidation_trigger_count=len(invalidation_views),
        review_required_trigger_count=sum(
            1 for c in invalidation_views if c.review_required
        ),
        triggers=invalidation_views,
    )

    next_action = _derive_next_action(status=status, review_badge=review_badge)

    related_event_ids = [
        getattr(e, "event_memory_id", "") for e in events
        if getattr(e, "event_memory_id", "")
    ]
    related_hf_ids = [
        getattr(f, "feedback_memory_id", "") for f in human_feedback_records
        if getattr(f, "feedback_memory_id", "")
    ]
    related_eval_ids = [
        getattr(ev, "evaluation_id", "") for ev in agent_evaluation_records
        if getattr(ev, "evaluation_id", "")
    ]

    is_populated = thesis is not None

    return HorizonDecisionCardView(
        target=target,
        horizon=horizon,
        is_populated=is_populated,
        status=status,
        thesis=thesis_view,
        assumptions=assumption_views,
        invalidation_triggers=invalidation_views,
        review_needed_badge=review_badge,
        missing_evidence_badge=missing_badge,
        evidence_summary=evidence_summary,
        risk_summary=risk_summary,
        next_action=next_action,
        related_event_ids=related_event_ids,
        related_human_feedback_ids=related_hf_ids,
        related_agent_evaluation_ids=related_eval_ids,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Builder helpers — aggregate views
# ---------------------------------------------------------------------------


def build_horizon_decision_cards_view(
    target: str,
    memory_store: Optional[MemoryStoreProtocol] = None,
    memory_query_result: Optional[MemoryQueryResult] = None,
) -> HorizonDecisionCardsView:
    """
    Build a deterministic ``HorizonDecisionCardsView`` for one target.

    Parameters
    ----------
    target : str
        Ticker / research target identifier. Required.
    memory_store : MemoryStoreProtocol, optional
        Phase 5A memory store. When supplied and ``memory_query_result``
        is not, a target-scoped query is run internally.
    memory_query_result : MemoryQueryResult, optional
        Pre-computed memory query result; takes precedence over
        ``memory_store`` for the records this view consumes.

    Returns
    -------
    HorizonDecisionCardsView
        Always exactly three cards in canonical short → medium → long
        order. Horizons without a thesis still appear as safe "missing"
        cards; the cockpit can render the slot regardless.
    """
    if not target or not str(target).strip():
        raise ValueError("'target' must not be empty or whitespace-only.")

    result = memory_query_result
    if result is None:
        result = _query_result_for_target(memory_store, target)

    events_all = [
        e for e in result.event_records if getattr(e, "target", None) == target
    ]
    feedback_all = [
        f for f in result.human_feedback_records if getattr(f, "target", None) == target
    ]
    eval_all = [
        ev for ev in result.agent_evaluation_records if getattr(ev, "target", None) == target
    ]

    cards: list[HorizonDecisionCardView] = []
    view_warnings: list[str] = []
    if memory_store is None and memory_query_result is None:
        view_warnings.append(
            "No memory store or query result supplied; horizon decision "
            "cards built without memory-backed evidence."
        )

    for horizon in HORIZON_ORDER:
        thesis = _thesis_for_horizon(result, target=target, horizon=horizon)
        h_events = _filter_events_for_horizon(events_all, horizon)
        # Human feedback memory records are not horizon-scoped in Phase 4M-F;
        # surface all target-scoped records on every card so cockpit reviewers
        # do not lose them. Cards do not duplicate counts in the aggregate
        # tracker view.
        h_evals = _filter_evaluations_for_horizon(eval_all, horizon)
        card = build_horizon_decision_card(
            target=target,
            horizon=horizon,
            thesis=thesis,
            events=h_events,
            human_feedback_records=feedback_all,
            agent_evaluation_records=h_evals,
        )
        cards.append(card)
        if not card.is_populated:
            view_warnings.append(
                f"No thesis memory record found for horizon={horizon!r}; "
                "card returned in safe degraded ('missing') state."
            )

    return HorizonDecisionCardsView(
        target=target,
        cards=cards,
        warnings=view_warnings,
    )


def build_thesis_tracker_row(
    target: str,
    horizon: HorizonKey,
    thesis: Optional[HorizonThesisMemoryRecord] = None,
    events: Optional[list[EventMemoryRecord]] = None,
    human_feedback_records: Optional[list[HumanFeedbackMemoryRecord]] = None,
    agent_evaluation_records: Optional[list[AgentEvaluationRecord]] = None,
) -> ThesisTrackerRowView:
    """Build one deterministic ``ThesisTrackerRowView``."""
    if not target or not str(target).strip():
        raise ValueError("'target' must not be empty or whitespace-only.")
    if horizon not in HORIZON_ORDER:
        raise ValueError(
            f"Unknown horizon {horizon!r}; expected one of {HORIZON_ORDER}."
        )

    events = list(events or [])
    human_feedback_records = list(human_feedback_records or [])
    agent_evaluation_records = list(agent_evaluation_records or [])

    evidence_summary = build_horizon_evidence_summary(
        horizon=horizon,
        thesis=thesis,
        events=events,
        human_feedback_records=human_feedback_records,
        agent_evaluation_records=agent_evaluation_records,
    )
    missing_badge = build_missing_evidence_badge(summary=evidence_summary)
    review_badge = build_review_needed_badge(
        thesis=thesis,
        events=events,
        human_feedback_records=human_feedback_records,
        agent_evaluation_records=agent_evaluation_records,
    )
    status = _derive_card_status(thesis=thesis, review_badge=review_badge)
    next_action = _derive_next_action(status=status, review_badge=review_badge)

    last_reviewed_at: Optional[str] = None
    if thesis is not None:
        # event_log entries are sorted by insertion order; pull the most recent
        # review_requested / outcome_observed timestamp if present.
        for ev in reversed(thesis.event_log):
            et = str(getattr(ev, "event_type", "") or "")
            if et in ("thesis_review_requested", "outcome_observed", "thesis_updated"):
                last_reviewed_at = str(getattr(ev, "created_at", "") or "") or None
                if last_reviewed_at:
                    break

    warnings: list[str] = []
    if thesis is None:
        warnings.append(
            f"No thesis memory record found for horizon={horizon!r}; "
            "row returned in safe degraded ('missing') state."
        )

    return ThesisTrackerRowView(
        target=target,
        horizon=horizon,
        is_populated=thesis is not None,
        status=status,
        direction=str(getattr(thesis, "direction", "unknown")) if thesis else "unknown",
        confidence=str(getattr(thesis, "confidence", "unknown")) if thesis else "unknown",
        thesis_id=getattr(thesis, "thesis_id", None) if thesis else None,
        last_updated_at=getattr(thesis, "updated_at", None) if thesis else None,
        last_reviewed_at=last_reviewed_at,
        invalidation_trigger_count=(
            len(thesis.invalidation_conditions) if thesis else 0
        ),
        review_needed=review_badge.review_needed,
        review_reasons=list(review_badge.reasons),
        missing_evidence_kinds=list(missing_badge.missing_kinds),
        evidence_id_count=len(evidence_summary.evidence_ids),
        next_action_label=next_action.label,
        warnings=warnings,
    )


def build_thesis_tracker_view(
    targets: list[str],
    memory_store: Optional[MemoryStoreProtocol] = None,
    memory_query_result: Optional[MemoryQueryResult] = None,
) -> ThesisTrackerView:
    """
    Build a deterministic ``ThesisTrackerView`` covering one or more targets.

    For each target in ``targets`` (deduplicated, preserving first-occurrence
    order), three rows are produced in canonical short → medium → long
    horizon order. Missing thesis records still yield safe ``"missing"`` rows.

    When ``memory_query_result`` is supplied, it is used directly for all
    targets — callers wanting per-target scoping should run target-scoped
    queries up front and call this builder once per scope (or simply pass
    ``memory_store`` and let the builder query per target).
    """
    if not isinstance(targets, list):
        raise TypeError("'targets' must be a list of strings.")
    deduped: list[str] = []
    for t in targets:
        if not isinstance(t, str) or not t.strip():
            raise ValueError("'targets' entries must be non-empty strings.")
        if t not in deduped:
            deduped.append(t)

    rows: list[ThesisTrackerRowView] = []
    view_warnings: list[str] = []
    if memory_store is None and memory_query_result is None:
        view_warnings.append(
            "No memory store or query result supplied; thesis tracker rows "
            "built without memory-backed evidence."
        )

    for target in deduped:
        if memory_query_result is not None:
            scoped = memory_query_result
        else:
            scoped = _query_result_for_target(memory_store, target)

        events_all = [
            e for e in scoped.event_records if getattr(e, "target", None) == target
        ]
        feedback_all = [
            f for f in scoped.human_feedback_records if getattr(f, "target", None) == target
        ]
        eval_all = [
            ev for ev in scoped.agent_evaluation_records if getattr(ev, "target", None) == target
        ]

        for horizon in HORIZON_ORDER:
            thesis = _thesis_for_horizon(scoped, target=target, horizon=horizon)
            h_events = _filter_events_for_horizon(events_all, horizon)
            h_evals = _filter_evaluations_for_horizon(eval_all, horizon)
            row = build_thesis_tracker_row(
                target=target,
                horizon=horizon,
                thesis=thesis,
                events=h_events,
                human_feedback_records=feedback_all,
                agent_evaluation_records=h_evals,
            )
            rows.append(row)

    # Rows are already in canonical (target, horizon) order because we iterate
    # targets in deduped order and horizons in HORIZON_ORDER. Sort defensively
    # to guarantee determinism even if the iteration order ever changes.
    rows.sort(key=lambda r: (deduped.index(r.target), _horizon_index(r.horizon)))

    return ThesisTrackerView(
        rows=rows,
        target_count=len(deduped),
        warnings=view_warnings,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal aliases / constants
    "HorizonKey",
    "HORIZON_ORDER",
    "HorizonEvidenceKind",
    "HORIZON_EVIDENCE_KINDS",
    "CardStatus",
    # Sub-view models
    "HorizonAssumptionView",
    "InvalidationTriggerView",
    "ThesisStatusView",
    "ReviewNeededBadgeView",
    "MissingEvidenceBadgeView",
    "HorizonEvidenceSummaryView",
    "HorizonRiskSummaryView",
    "HorizonNextActionView",
    # Card / tracker models
    "HorizonDecisionCardView",
    "HorizonDecisionCardsView",
    "ThesisTrackerRowView",
    "ThesisTrackerView",
    # Builders
    "build_horizon_evidence_summary",
    "build_missing_evidence_badge",
    "build_review_needed_badge",
    "build_horizon_decision_card",
    "build_horizon_decision_cards_view",
    "build_thesis_tracker_row",
    "build_thesis_tracker_view",
]
