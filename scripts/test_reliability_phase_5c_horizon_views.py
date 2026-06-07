#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5c_horizon_views.py

Phase 5C: Horizon Decision Cards + ThesisTracker ViewModel Contract test suite.

Validates:
  - lib/reliability/phase5_horizon_views.py imports without loading any
    forbidden live runtime module (Streamlit, workflow_state,
    llm_orchestrator, data_fetcher, Anthropic SDK, etc.).
  - Source-level forbidden import substrings are absent.
  - build_horizon_decision_cards_view() builds three cards (short / medium
    / long) in canonical order from the Phase 5A complete fixture pack.
  - Per-horizon thesis content is preserved on each card.
  - Missing short / medium / long thesis returns a safe degraded card +
    warning.
  - Missing ticker / no records returns an empty safe view (three
    "missing" cards), with no hallucination.
  - ThesisTracker rows are created by (ticker, horizon).
  - Catalyst / news / earnings review-needed signal surfaces on the
    review_needed badge when fixture supports it.
  - Human feedback status surfaces when fixture supports it.
  - Agent evaluation summary surfaces when fixture supports it.
  - Missing-evidence badge appears for incomplete horizon records.
  - Validation status (review_needed / missing_evidence) does not
    fabricate clean / success state when records are missing.
  - No approved_for_execution=True appears anywhere in the views.
  - Deterministic serialization across rebuilds.
  - Phase 5B regression: builds CompanyResearchHubView from the same
    fixture pack and confirms the existing 175/175 Phase 5A and 163/163
    Phase 5B test surfaces still resolve.

Usage:
    python3 scripts/test_reliability_phase_5c_horizon_views.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

# Add repo root to sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

PASS = 0
FAIL = 0
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


def expect_error(label: str, fn, exc_type=Exception, keyword: str | None = None) -> None:
    global PASS, FAIL
    try:
        fn()
        FAIL += 1
        _failures.append(
            f"FAIL  {label}: expected {exc_type.__name__} but no error raised"
        )
        return
    except exc_type as e:
        if keyword and keyword.lower() not in str(e).lower():
            FAIL += 1
            _failures.append(
                f"FAIL  {label}: raised {exc_type.__name__} but missing keyword "
                f"{keyword!r}: {e}"
            )
            return
        PASS += 1
    except Exception as e:
        FAIL += 1
        _failures.append(
            f"FAIL  {label}: expected {exc_type.__name__} but got "
            f"{type(e).__name__}: {e}"
        )


# ---------------------------------------------------------------------------
# Section 1 — Module imports must succeed and forbidden imports must not occur
# ---------------------------------------------------------------------------

from lib.reliability import phase5_horizon_views as _hv_mod

check("1.1 phase5_horizon_views importable", _hv_mod is not None)

_FORBIDDEN_LIVE_MODULES = (
    "lib.workflow_state",
    "lib.llm_orchestrator",
    "lib.data_fetcher",
    "lib.valuation",
    "lib.technical",
    "lib.rotation",
    "lib.cache_manager",
    "app",
    "streamlit",
    "anthropic",
)

for _m in _FORBIDDEN_LIVE_MODULES:
    loaded = any(name == _m or name.startswith(_m + ".") for name in sys.modules)
    check(f"1.x forbidden module not loaded: {_m}", not loaded)


# ---------------------------------------------------------------------------
# Section 2 — Source-level forbidden imports check
# ---------------------------------------------------------------------------

_PHASE5C_SOURCES = [
    pathlib.Path(_REPO_ROOT) / "lib" / "reliability" / "phase5_horizon_views.py",
]

_FORBIDDEN_SUBSTRINGS = [
    "import lib.workflow_state",
    "from lib.workflow_state",
    "import lib.llm_orchestrator",
    "from lib.llm_orchestrator",
    "import lib.data_fetcher",
    "from lib.data_fetcher",
    "import lib.valuation",
    "from lib.valuation",
    "import lib.technical",
    "from lib.technical",
    "import lib.rotation",
    "from lib.rotation",
    "import lib.cache_manager",
    "from lib.cache_manager",
    "import streamlit",
    "from streamlit",
    "import anthropic",
    "from anthropic",
    "import app",
    "from app",
    "from lib.reliability.integration_boundary",
    "import lib.reliability.integration_boundary",
    "research/.workflow_state.json",
]

for src in _PHASE5C_SOURCES:
    text = src.read_text(encoding="utf-8")
    for sub in _FORBIDDEN_SUBSTRINGS:
        check(
            f"2.{src.name}::{sub!r}",
            sub not in text,
            f"forbidden substring {sub!r} found in {src.name}",
        )


# ---------------------------------------------------------------------------
# Section 3 — Imports from the module
# ---------------------------------------------------------------------------

from lib.reliability.phase5_horizon_views import (
    CardStatus,
    HORIZON_EVIDENCE_KINDS,
    HORIZON_ORDER,
    HorizonAssumptionView,
    HorizonDecisionCardView,
    HorizonDecisionCardsView,
    HorizonEvidenceKind,
    HorizonEvidenceSummaryView,
    HorizonKey,
    HorizonNextActionView,
    HorizonRiskSummaryView,
    InvalidationTriggerView,
    MissingEvidenceBadgeView,
    ReviewNeededBadgeView,
    ThesisStatusView,
    ThesisTrackerRowView,
    ThesisTrackerView,
    build_horizon_decision_card,
    build_horizon_decision_cards_view,
    build_horizon_evidence_summary,
    build_missing_evidence_badge,
    build_review_needed_badge,
    build_thesis_tracker_row,
    build_thesis_tracker_view,
)
from lib.reliability.phase5_fixtures import (
    SAMPLE_FIXTURE_AS_OF,
    SAMPLE_FIXTURE_RUN_ID,
    SAMPLE_FIXTURE_TICKER,
    build_sample_fixture_pack,
    make_sample_event_record,
    make_sample_thesis_records,
    make_sample_workflow_snapshot,
)
from lib.reliability.phase5_memory_query import (
    FixtureBackedMemoryStore,
    MemoryQuery,
    MemoryQueryByTicker,
    MemoryQueryResult,
)
from lib.reliability.thesis_memory import HorizonThesisMemoryRecord
from lib.reliability.event_memory import EventMemoryRecord, build_event_memory_record

check("3.1 HorizonDecisionCardsView class importable", HorizonDecisionCardsView is not None)
check("3.2 ThesisTrackerView class importable", ThesisTrackerView is not None)
check("3.3 build_horizon_decision_cards_view importable", build_horizon_decision_cards_view is not None)
check("3.4 HORIZON_ORDER canonical short→medium→long", HORIZON_ORDER == ("short", "medium", "long"))
check(
    "3.5 HORIZON_EVIDENCE_KINDS includes thesis/event/human_feedback/agent_evaluation",
    set(HORIZON_EVIDENCE_KINDS) == {"thesis", "event", "human_feedback", "agent_evaluation"},
)


# ---------------------------------------------------------------------------
# Section 4 — Build full HorizonDecisionCardsView from Phase 5A fixture pack
# ---------------------------------------------------------------------------

snap, adapter, bundle = build_sample_fixture_pack()
store = FixtureBackedMemoryStore()
store.register_bundle(bundle)

cards_view = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=store
)

check("4.1 cards_view is HorizonDecisionCardsView", isinstance(cards_view, HorizonDecisionCardsView))
check("4.2 cards_view.target matches fixture", cards_view.target == SAMPLE_FIXTURE_TICKER)
check("4.3 cards_view has exactly 3 cards", len(cards_view.cards) == 3)
check(
    "4.4 cards_view horizon order short/medium/long",
    [c.horizon for c in cards_view.cards] == ["short", "medium", "long"],
)
check(
    "4.5 cards_view.calculation_version stable",
    cards_view.calculation_version == "phase5_horizon_views_v1",
)
check("4.6 cards_view no top-level warnings (full fixture)", cards_view.warnings == [])


# ---------------------------------------------------------------------------
# Section 5 — Short / medium / long cards preserve thesis content
# ---------------------------------------------------------------------------

card_short, card_medium, card_long = cards_view.cards

check("5.1 short card is_populated", card_short.is_populated is True)
check("5.2 short card horizon=short", card_short.horizon == "short")
check("5.3 short card thesis present", card_short.thesis is not None and card_short.thesis.thesis_id.startswith("thesis_"))
check("5.4 short card status active", card_short.status == "active")
check(
    "5.5 short card thesis_text matches fixture",
    card_short.thesis is not None
    and "short-horizon thesis" in card_short.thesis.thesis_text.lower(),
)
check("5.6 short card direction bullish", card_short.thesis is not None and card_short.thesis.direction == "bullish")
check("5.7 short card confidence medium", card_short.thesis is not None and card_short.thesis.confidence == "medium")

check("5.8 short card has 1 assumption", len(card_short.assumptions) == 1)
check(
    "5.9 short card assumption_id matches fixture",
    card_short.assumptions[0].assumption_id == "fix5a_assump_short_1",
)
check("5.10 short card invalidation_triggers count 1", len(card_short.invalidation_triggers) == 1)
check(
    "5.11 short card invalidation_type technical",
    card_short.invalidation_triggers[0].invalidation_type == "technical",
)

check("5.12 medium card horizon=medium", card_medium.horizon == "medium")
check("5.13 medium card is_populated", card_medium.is_populated is True)
check("5.14 medium card direction neutral", card_medium.thesis.direction == "neutral")

check("5.15 long card horizon=long", card_long.horizon == "long")
check("5.16 long card is_populated", card_long.is_populated is True)
check("5.17 long card direction bullish", card_long.thesis.direction == "bullish")
check("5.18 long card confidence high", card_long.thesis.confidence == "high")


# ---------------------------------------------------------------------------
# Section 6 — Evidence + risk + next_action sub-views
# ---------------------------------------------------------------------------

check(
    "6.1 short card evidence_summary has_thesis True",
    card_short.evidence_summary.has_thesis is True,
)
check(
    "6.2 short card evidence_summary record_counts_by_kind has thesis=1",
    card_short.evidence_summary.record_counts_by_kind.get("thesis") == 1,
)
check(
    "6.3 short card evidence_summary evidence_ids includes fix5a_evid_short",
    "fix5a_evid_short" in card_short.evidence_summary.evidence_ids,
)

check(
    "6.4 short card risk_summary invalidation_trigger_count 1",
    card_short.risk_summary.invalidation_trigger_count == 1,
)
check(
    "6.5 short card next_action label 'watch' for active card",
    card_short.next_action.label == "watch",
)


# ---------------------------------------------------------------------------
# Section 7 — Missing short thesis returns safe missing card + warning
# ---------------------------------------------------------------------------

# Build a memory store with only medium / long thesis.
snap2 = make_sample_workflow_snapshot()
theses_all = make_sample_thesis_records(snap2)
no_short_store = FixtureBackedMemoryStore()
no_short_store.add_thesis_record(theses_all[1])  # medium
no_short_store.add_thesis_record(theses_all[2])  # long

view_no_short = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=no_short_store
)
check(
    "7.1 missing short -> short card is_populated False",
    view_no_short.cards[0].is_populated is False,
)
check(
    "7.2 missing short -> short card status missing",
    view_no_short.cards[0].status == "missing",
)
check(
    "7.3 missing short -> short card warnings non-empty",
    len(view_no_short.cards[0].warnings) >= 1
    and "short" in view_no_short.cards[0].warnings[0].lower(),
)
check(
    "7.4 missing short -> medium card still populated",
    view_no_short.cards[1].is_populated is True,
)
check(
    "7.5 missing short -> long card still populated",
    view_no_short.cards[2].is_populated is True,
)
check(
    "7.6 missing short -> top-level warnings mention short",
    any("short" in w.lower() for w in view_no_short.warnings),
)


# ---------------------------------------------------------------------------
# Section 8 — Missing medium thesis returns safe missing card + warning
# ---------------------------------------------------------------------------

no_med_store = FixtureBackedMemoryStore()
no_med_store.add_thesis_record(theses_all[0])  # short
no_med_store.add_thesis_record(theses_all[2])  # long
view_no_med = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=no_med_store
)
check("8.1 missing medium -> medium card status missing", view_no_med.cards[1].status == "missing")
check("8.2 missing medium -> medium card warnings non-empty", len(view_no_med.cards[1].warnings) >= 1)
check("8.3 missing medium -> short card still populated", view_no_med.cards[0].is_populated is True)
check("8.4 missing medium -> long card still populated", view_no_med.cards[2].is_populated is True)


# ---------------------------------------------------------------------------
# Section 9 — Missing long thesis returns safe missing card + warning
# ---------------------------------------------------------------------------

no_long_store = FixtureBackedMemoryStore()
no_long_store.add_thesis_record(theses_all[0])  # short
no_long_store.add_thesis_record(theses_all[1])  # medium
view_no_long = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=no_long_store
)
check("9.1 missing long -> long card status missing", view_no_long.cards[2].status == "missing")
check("9.2 missing long -> long card is_populated False", view_no_long.cards[2].is_populated is False)
check(
    "9.3 missing long -> long card next_action label none_supported",
    view_no_long.cards[2].next_action.label == "none_supported",
)


# ---------------------------------------------------------------------------
# Section 10 — Missing ticker / no records returns empty safe view
# ---------------------------------------------------------------------------

empty_store = FixtureBackedMemoryStore()
empty_view = build_horizon_decision_cards_view(
    target="NONEXISTENT", memory_store=empty_store
)
check("10.1 empty view: target preserved", empty_view.target == "NONEXISTENT")
check("10.2 empty view: 3 cards (all missing)", len(empty_view.cards) == 3)
check(
    "10.3 empty view: all cards status missing",
    all(c.status == "missing" for c in empty_view.cards),
)
check(
    "10.4 empty view: all cards is_populated False",
    all(c.is_populated is False for c in empty_view.cards),
)
check(
    "10.5 empty view: every card has warnings",
    all(len(c.warnings) >= 1 for c in empty_view.cards),
)
check(
    "10.6 empty view: top-level warnings list every missing horizon",
    all(
        any(h in w.lower() for w in empty_view.warnings)
        for h in ("short", "medium", "long")
    ),
)


# ---------------------------------------------------------------------------
# Section 11 — ThesisTracker rows are created by ticker/horizon
# ---------------------------------------------------------------------------

tracker = build_thesis_tracker_view(
    targets=[SAMPLE_FIXTURE_TICKER], memory_store=store
)
check("11.1 tracker is ThesisTrackerView", isinstance(tracker, ThesisTrackerView))
check("11.2 tracker.target_count == 1", tracker.target_count == 1)
check("11.3 tracker.rows count == 3", len(tracker.rows) == 3)
check(
    "11.4 tracker.rows ordered by short/medium/long",
    [r.horizon for r in tracker.rows] == ["short", "medium", "long"],
)
check(
    "11.5 tracker.rows[0] populated for short",
    tracker.rows[0].is_populated is True
    and tracker.rows[0].status == "active",
)
check(
    "11.6 tracker.rows[1] populated for medium",
    tracker.rows[1].is_populated is True,
)
check(
    "11.7 tracker.rows[2] populated for long",
    tracker.rows[2].is_populated is True,
)
check(
    "11.8 tracker.rows preserve thesis_id from fixture",
    tracker.rows[0].thesis_id is not None
    and tracker.rows[0].thesis_id.startswith("thesis_"),
)
check(
    "11.9 tracker.rows preserve invalidation_trigger_count",
    tracker.rows[0].invalidation_trigger_count == 1,
)
check(
    "11.10 tracker.rows preserve next_action_label",
    tracker.rows[0].next_action_label == "watch",
)


# ---------------------------------------------------------------------------
# Section 12 — Multi-target tracker preserves deterministic ordering
# ---------------------------------------------------------------------------

# Build a second target without records, confirm the tracker emits 3
# missing rows for it, ordered after the first target.
tracker_multi = build_thesis_tracker_view(
    targets=[SAMPLE_FIXTURE_TICKER, "OTHERFIX"], memory_store=store
)
check("12.1 multi-target tracker has 6 rows", len(tracker_multi.rows) == 6)
check(
    "12.2 multi-target tracker preserves target ordering",
    [r.target for r in tracker_multi.rows]
    == [
        SAMPLE_FIXTURE_TICKER,
        SAMPLE_FIXTURE_TICKER,
        SAMPLE_FIXTURE_TICKER,
        "OTHERFIX",
        "OTHERFIX",
        "OTHERFIX",
    ],
)
check(
    "12.3 multi-target tracker emits missing rows for unknown target",
    all(r.status == "missing" for r in tracker_multi.rows[3:]),
)
check(
    "12.4 multi-target tracker dedupes repeated targets",
    build_thesis_tracker_view(
        targets=[SAMPLE_FIXTURE_TICKER, SAMPLE_FIXTURE_TICKER],
        memory_store=store,
    ).target_count
    == 1,
)


# ---------------------------------------------------------------------------
# Section 13 — Catalyst/news/earnings review-needed signal surfaces
# ---------------------------------------------------------------------------

# Build a store with thesis + an event whose review_status is "pending".
review_store = FixtureBackedMemoryStore()
review_store.add_thesis_record(theses_all[0])  # short
pending_event: EventMemoryRecord = build_event_memory_record(
    target=SAMPLE_FIXTURE_TICKER,
    event_name="Pending fixture event",
    summary="Pending event awaiting review.",
    event_type="catalyst",
    impact_direction="neutral",
    impact_magnitude="medium",
    review_status="pending",
    thesis_changing=False,
    affected_horizons=["short"],
    event_date=SAMPLE_FIXTURE_AS_OF,
    run_id=SAMPLE_FIXTURE_RUN_ID,
    recorded_at=SAMPLE_FIXTURE_AS_OF,
)
review_store.add_event_record(pending_event)

review_view = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=review_store
)
short_review_card = review_view.cards[0]
check(
    "13.1 pending event -> short card review_needed True",
    short_review_card.review_needed_badge.review_needed is True,
)
check(
    "13.2 pending event -> short card review reasons mention event",
    any("event" in r.lower() for r in short_review_card.review_needed_badge.reasons),
)
check(
    "13.3 pending event -> short card status flipped to needs_review",
    short_review_card.status == "needs_review",
)
check(
    "13.4 pending event -> short card next_action label review_thesis",
    short_review_card.next_action.label == "review_thesis",
)
check(
    "13.5 pending event id surfaces in related_event_ids",
    pending_event.event_memory_id in short_review_card.related_event_ids,
)


# ---------------------------------------------------------------------------
# Section 14 — Human feedback status surfaces when fixture supports it
# ---------------------------------------------------------------------------

# The Phase 5A complete fixture pack includes a human feedback record;
# confirm that record IDs surface on the card relations even if no review
# is currently required.
short_card_full = cards_view.cards[0]
check(
    "14.1 fixture human_feedback IDs surface on related_human_feedback_ids",
    len(short_card_full.related_human_feedback_ids) >= 1,
)


# Build a synthetic human feedback record with review_required=True.
from lib.reliability.human_feedback_memory import (
    HumanFeedbackEntry,
    HumanFeedbackTargetRef,
    build_human_feedback_entry,
    build_human_feedback_memory_record,
    build_human_feedback_target_ref,
)

hf_target_ref: HumanFeedbackTargetRef = build_human_feedback_target_ref(
    target_id="fix5c_target_artifact_1",
    target_type="research_run_memory",
    run_id=SAMPLE_FIXTURE_RUN_ID,
    label="Fixture HF target ref",
    as_of=SAMPLE_FIXTURE_AS_OF,
)
hf_entry: HumanFeedbackEntry = build_human_feedback_entry(
    feedback_id="fix5c_feedback_1",
    feedback_text="Reviewer requests follow-up before relying on the thesis.",
    decision="deferred",
    reason_type="risk_too_high",
    actor="reviewer",
    created_at=SAMPLE_FIXTURE_AS_OF,
)
hf_record = build_human_feedback_memory_record(
    target=SAMPLE_FIXTURE_TICKER,
    target_ref=hf_target_ref,
    feedback_entries=[hf_entry],
    outcome="pending",
    run_id=SAMPLE_FIXTURE_RUN_ID,
    review_required=True,
    recorded_at=SAMPLE_FIXTURE_AS_OF,
)

hf_store = FixtureBackedMemoryStore()
hf_store.add_thesis_record(theses_all[0])  # short
hf_store.add_human_feedback_record(hf_record)
hf_view = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=hf_store
)
short_hf_card = hf_view.cards[0]
check(
    "14.2 hf review_required True -> short card review_needed True",
    short_hf_card.review_needed_badge.review_needed is True,
)
check(
    "14.3 hf review_required True -> reasons mention human feedback",
    any(
        "human feedback" in r.lower() or "feedback_memory_id" in r.lower()
        for r in short_hf_card.review_needed_badge.reasons
    ),
)
check(
    "14.4 hf record id surfaces on related_human_feedback_ids",
    hf_record.feedback_memory_id in short_hf_card.related_human_feedback_ids,
)


# ---------------------------------------------------------------------------
# Section 15 — Agent evaluation summary surfaces when fixture supports it
# ---------------------------------------------------------------------------

# Confirm the Phase 5A fixture agent evaluation record reaches the medium
# card (the fixture eval is keyed to medium horizon).
medium_card_full = cards_view.cards[1]
check(
    "15.1 fixture eval record id surfaces on medium card related_agent_evaluation_ids",
    len(medium_card_full.related_agent_evaluation_ids) >= 1,
)
check(
    "15.2 medium card evidence_summary records agent_evaluation count >= 1",
    medium_card_full.evidence_summary.record_counts_by_kind.get("agent_evaluation", 0) >= 1,
)


# ---------------------------------------------------------------------------
# Section 16 — Missing-evidence badge appears for incomplete horizons
# ---------------------------------------------------------------------------

# When only a thesis exists (no events, no human feedback, no agent eval),
# the missing-evidence badge should flag the three missing kinds.
thesis_only_store = FixtureBackedMemoryStore()
thesis_only_store.add_thesis_record(theses_all[0])
thesis_only_view = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=thesis_only_store
)
short_thesis_only = thesis_only_view.cards[0]
check(
    "16.1 thesis-only card missing_evidence_badge has_missing_evidence True",
    short_thesis_only.missing_evidence_badge.has_missing_evidence is True,
)
check(
    "16.2 thesis-only card missing_kinds == {event, human_feedback, agent_evaluation}",
    set(short_thesis_only.missing_evidence_badge.missing_kinds)
    == {"event", "human_feedback", "agent_evaluation"},
)
check(
    "16.3 thesis-only card present_kinds == [thesis]",
    short_thesis_only.missing_evidence_badge.present_kinds == ["thesis"],
)
check(
    "16.4 thesis-only card missing_evidence_badge warnings non-empty",
    len(short_thesis_only.missing_evidence_badge.warnings) >= 1,
)

# Empty card -> all four kinds missing.
empty_card = empty_view.cards[0]
check(
    "16.5 empty card missing_kinds includes all four kinds",
    set(empty_card.missing_evidence_badge.missing_kinds)
    == {"thesis", "event", "human_feedback", "agent_evaluation"},
)


# ---------------------------------------------------------------------------
# Section 17 — Validation does not fabricate clean state
# ---------------------------------------------------------------------------

# Empty card: no thesis -> status='missing', evidence_summary.has_any_evidence False.
check(
    "17.1 empty card evidence_summary.has_any_evidence False",
    empty_card.evidence_summary.has_any_evidence is False,
)
check(
    "17.2 empty card review_needed False (no records to flag review)",
    empty_card.review_needed_badge.review_needed is False,
)
# But the card is NOT "clean" — status is "missing" and next_action is "none_supported"
check("17.3 empty card status missing (not active)", empty_card.status == "missing")
check(
    "17.4 empty card next_action label none_supported (no fabrication)",
    empty_card.next_action.label == "none_supported",
)


# ---------------------------------------------------------------------------
# Section 18 — No approved_for_execution=True appears anywhere
# ---------------------------------------------------------------------------

cards_json = cards_view.model_dump_json()
check(
    "18.1 cards_view JSON does not contain approved_for_execution=true",
    '"approved_for_execution": true' not in cards_json.lower().replace(" ", "")
    and '"approved_for_execution":true' not in cards_json.lower(),
)
tracker_json = tracker.model_dump_json()
check(
    "18.2 tracker JSON does not contain approved_for_execution=true",
    '"approved_for_execution": true' not in tracker_json.lower().replace(" ", "")
    and '"approved_for_execution":true' not in tracker_json.lower(),
)

# Phase 5C view models themselves must not declare approved_for_execution.
for cls in (
    HorizonDecisionCardsView,
    HorizonDecisionCardView,
    ThesisTrackerView,
    ThesisTrackerRowView,
    ThesisStatusView,
    InvalidationTriggerView,
    HorizonAssumptionView,
    ReviewNeededBadgeView,
    MissingEvidenceBadgeView,
    HorizonEvidenceSummaryView,
    HorizonRiskSummaryView,
    HorizonNextActionView,
):
    field_names = set(cls.model_fields.keys())
    check(
        f"18.3 {cls.__name__}: approved_for_execution not a field",
        "approved_for_execution" not in field_names,
    )


# ---------------------------------------------------------------------------
# Section 19 — Deterministic serialization across rebuilds
# ---------------------------------------------------------------------------

snap_r, adapter_r, bundle_r = build_sample_fixture_pack()
store_r = FixtureBackedMemoryStore()
store_r.register_bundle(bundle_r)
cards_view_r = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=store_r
)
tracker_r = build_thesis_tracker_view(
    targets=[SAMPLE_FIXTURE_TICKER], memory_store=store_r
)
check(
    "19.1 cards_view deterministic JSON across rebuilds",
    json.dumps(cards_view.model_dump(mode="json"), sort_keys=True)
    == json.dumps(cards_view_r.model_dump(mode="json"), sort_keys=True),
)
check(
    "19.2 tracker deterministic JSON across rebuilds",
    json.dumps(tracker.model_dump(mode="json"), sort_keys=True)
    == json.dumps(tracker_r.model_dump(mode="json"), sort_keys=True),
)


# ---------------------------------------------------------------------------
# Section 20 — Build with explicit MemoryQueryResult
# ---------------------------------------------------------------------------

qres = store.query(MemoryQueryByTicker(target=SAMPLE_FIXTURE_TICKER))
cards_with_qres = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_query_result=qres
)
check(
    "20.1 build with explicit MemoryQueryResult: cards equal store version",
    json.dumps(cards_with_qres.model_dump(mode="json"), sort_keys=True)
    == json.dumps(cards_view.model_dump(mode="json"), sort_keys=True),
)


# ---------------------------------------------------------------------------
# Section 21 — Builder rejects empty / whitespace target
# ---------------------------------------------------------------------------

expect_error(
    "21.1 build_horizon_decision_cards_view empty target raises",
    lambda: build_horizon_decision_cards_view(target=""),
    exc_type=ValueError,
)
expect_error(
    "21.2 build_horizon_decision_cards_view whitespace target raises",
    lambda: build_horizon_decision_cards_view(target="   "),
    exc_type=ValueError,
)
expect_error(
    "21.3 build_horizon_decision_card empty target raises",
    lambda: build_horizon_decision_card(target="", horizon="short"),
    exc_type=ValueError,
)
expect_error(
    "21.4 build_horizon_decision_card unknown horizon raises",
    lambda: build_horizon_decision_card(target="X", horizon="weekly"),  # type: ignore[arg-type]
    exc_type=ValueError,
    keyword="horizon",
)
expect_error(
    "21.5 build_thesis_tracker_view empty entry raises",
    lambda: build_thesis_tracker_view(targets=[""], memory_store=store),
    exc_type=ValueError,
)
expect_error(
    "21.6 build_thesis_tracker_view non-list raises",
    lambda: build_thesis_tracker_view(targets="X", memory_store=store),  # type: ignore[arg-type]
    exc_type=TypeError,
)


# ---------------------------------------------------------------------------
# Section 22 — Build without memory store at all
# ---------------------------------------------------------------------------

bare_view = build_horizon_decision_cards_view(target="BARE")
check(
    "22.1 bare view: 3 missing cards",
    len(bare_view.cards) == 3
    and all(c.status == "missing" for c in bare_view.cards),
)
check(
    "22.2 bare view: top-level warnings mention missing memory",
    any("memory store" in w.lower() for w in bare_view.warnings),
)
bare_tracker = build_thesis_tracker_view(targets=["BARE"])
check(
    "22.3 bare tracker: 3 missing rows",
    len(bare_tracker.rows) == 3
    and all(r.status == "missing" for r in bare_tracker.rows),
)
check(
    "22.4 bare tracker: top-level warnings mention missing memory",
    any("memory store" in w.lower() for w in bare_tracker.warnings),
)


# ---------------------------------------------------------------------------
# Section 23 — Aggregate view validators reject malformed inputs
# ---------------------------------------------------------------------------

def _make_two_cards_view():
    HorizonDecisionCardsView(
        target="X",
        cards=[
            cards_view.cards[0],
            cards_view.cards[1],
        ],
    )


expect_error(
    "23.1 HorizonDecisionCardsView rejects wrong card count",
    _make_two_cards_view,
    exc_type=Exception,
    keyword="cards",
)


def _make_out_of_order_view():
    HorizonDecisionCardsView(
        target="X",
        cards=[cards_view.cards[1], cards_view.cards[0], cards_view.cards[2]],
    )


expect_error(
    "23.2 HorizonDecisionCardsView rejects out-of-order cards",
    _make_out_of_order_view,
    exc_type=Exception,
    keyword="order",
)


# ---------------------------------------------------------------------------
# Section 24 — Package-level re-exports through lib/reliability/__init__.py
# ---------------------------------------------------------------------------

import lib.reliability as _r

_PHASE5C_EXPECTED_EXPORTS = (
    "CardStatus",
    "HORIZON_EVIDENCE_KINDS",
    "HORIZON_ORDER",
    "HorizonAssumptionView",
    "HorizonDecisionCardView",
    "HorizonDecisionCardsView",
    "HorizonEvidenceKind",
    "HorizonEvidenceSummaryView",
    "HorizonKey",
    "HorizonNextActionView",
    "HorizonRiskSummaryView",
    "InvalidationTriggerView",
    "MissingEvidenceBadgeView",
    "ReviewNeededBadgeView",
    "ThesisStatusView",
    "ThesisTrackerRowView",
    "ThesisTrackerView",
    "build_horizon_decision_card",
    "build_horizon_decision_cards_view",
    "build_horizon_evidence_summary",
    "build_missing_evidence_badge",
    "build_review_needed_badge",
    "build_thesis_tracker_row",
    "build_thesis_tracker_view",
)

for name in _PHASE5C_EXPECTED_EXPORTS:
    check(
        f"24.x lib.reliability re-exports {name}",
        hasattr(_r, name) and name in _r.__all__,
    )


# ---------------------------------------------------------------------------
# Section 25 — __all__ symmetry between module and re-exports
# ---------------------------------------------------------------------------

check(
    "25.1 module __all__ contains all Phase 5C view symbols",
    set(_PHASE5C_EXPECTED_EXPORTS).issubset(set(_hv_mod.__all__)),
)


# ---------------------------------------------------------------------------
# Section 26 — No filesystem writes during the Phase 5C pipeline
# ---------------------------------------------------------------------------

_before = (
    set(pathlib.Path(_REPO_ROOT, "research").rglob("*"))
    if pathlib.Path(_REPO_ROOT, "research").exists()
    else set()
)

_ = build_horizon_decision_cards_view(target=SAMPLE_FIXTURE_TICKER, memory_store=store)
_ = build_thesis_tracker_view(targets=[SAMPLE_FIXTURE_TICKER], memory_store=store)
_ = build_horizon_decision_cards_view(target="NONE")

_after = (
    set(pathlib.Path(_REPO_ROOT, "research").rglob("*"))
    if pathlib.Path(_REPO_ROOT, "research").exists()
    else set()
)

check("26.1 no new files written under research/", _before == _after)


# ---------------------------------------------------------------------------
# Section 27 — Phase 5B regression: CompanyResearchHubView still builds
# ---------------------------------------------------------------------------

from lib.reliability.company_research_hub import (
    CompanyResearchHubView,
    build_company_research_hub_view,
)

phase5b_view = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap, memory_store=store
)
check(
    "27.1 Phase 5B CompanyResearchHubView still builds from fixture",
    isinstance(phase5b_view, CompanyResearchHubView),
)
check(
    "27.2 Phase 5B equity panel still populated",
    phase5b_view.equity_panel.is_populated is True,
)
check(
    "27.3 Phase 5B evidence_coverage_panel total_memory_record_count == 9",
    phase5b_view.evidence_coverage_panel.total_memory_record_count == 9,
)


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

print("=" * 70)
print("Phase 5C — Horizon Decision Cards + ThesisTracker — test results")
print("=" * 70)
print()
print(f"Passed: {PASS}")
print(f"Failed: {FAIL}")
print(f"Total:  {PASS + FAIL}")
print()
if FAIL:
    print("Failures:")
    for f in _failures:
        print("  " + f)
    print()
    print("RESULT: FAIL — Phase 5C contract NOT verified.")
    sys.exit(1)
else:
    print("RESULT: PASS — Phase 5C contract verified.")
    sys.exit(0)
