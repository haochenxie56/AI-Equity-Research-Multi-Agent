"""
scripts/test_reliability_research_memory.py

Phase 4M-A: Research Run Memory Schema — test suite.

Tests:
  Section 1  — Literal type alias values
  Section 2  — MemorySourceRef validation
  Section 3  — MemoryEvent validation
  Section 4  — ResearchRunMemoryInputBundle validation
  Section 5  — ResearchRunMemorySummary validation (incl. approved_for_execution)
  Section 6  — ResearchRunMemoryRecord validation (incl. approved_for_execution)
  Section 7  — ResearchRunMemoryIndexEntry validation
  Section 8  — make_research_run_memory_id (determinism, stability)
  Section 9  — make_memory_event_id (determinism)
  Section 10 — collect_memory_source_refs (deduplication, auto-detect)
  Section 11 — collect_memory_evidence_ids (deduplication)
  Section 12 — collect_memory_tool_result_ids (deduplication)
  Section 13 — determine_research_run_memory_status (all branches)
  Section 14 — build_memory_event
  Section 15 — summarize_research_run_memory
  Section 16 — build_research_run_memory_record (full integration)
  Section 17 — build_memory_index_entry
  Section 18 — research_run_memory_tool_result_from_record (ToolResult adapter)
  Section 19 — __all__ export smoke test
  Section 20 — Forbidden dependency check
  Section 21 — Deterministic timestamp regression tests (Fix 1)
  Section 22 — ToolResult full record payload and evidence fidelity (Fix 2)
  Section 23 — artifact_refs empty string filtering (Fix 4)

Run:
  python3 scripts/test_reliability_research_memory.py
"""

import sys
import os

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import types
import unittest
from typing import Any

from lib.reliability.research_memory import (
    # Literals
    MemoryActorType,
    MemoryEventType,
    MemoryRecordStatus,
    ResearchRunMemorySourceType,
    ResearchRunMemoryStatus,
    # Models
    MemoryEvent,
    MemorySourceRef,
    ResearchRunMemoryIndexEntry,
    ResearchRunMemoryInputBundle,
    ResearchRunMemoryRecord,
    ResearchRunMemorySummary,
    # Helpers
    build_memory_event,
    build_memory_index_entry,
    build_research_run_memory_record,
    collect_memory_evidence_ids,
    collect_memory_source_refs,
    collect_memory_tool_result_ids,
    determine_research_run_memory_status,
    make_memory_event_id,
    make_research_run_memory_id,
    research_run_memory_tool_result_from_record,
    summarize_research_run_memory,
    _CALCULATION_VERSION,
    _DETERMINISTIC_TIMESTAMP_DEFAULT,
)
from lib.reliability.schemas import ToolResult


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_RUN_ID = "AAPL_20260524_120000_abcd"
_TARGET = "AAPL"
_AS_OF = "2026-05-24T12:00:00+00:00"
_TS = "2026-05-24T12:00:00+00:00"


def _make_minimal_bundle(**kwargs: Any) -> ResearchRunMemoryInputBundle:
    defaults = {
        "run_id": _RUN_ID,
        "target": _TARGET,
        "as_of": _AS_OF,
    }
    defaults.update(kwargs)
    return ResearchRunMemoryInputBundle(**defaults)


def _make_source_ref(
    source_id: str = "src_001",
    source_type: str = "orchestration",
) -> MemorySourceRef:
    return MemorySourceRef(source_id=source_id, source_type=source_type)  # type: ignore[arg-type]


def _make_mock_human_review(status: str = "approved_for_research_only") -> Any:
    """Minimal duck-typed mock human review report."""
    obj = types.SimpleNamespace()
    obj.status = status
    obj.report_id = "hr_abc123"
    obj.feedback_items = []
    obj.revision_requests = []
    obj.outcome = None
    return obj


def _make_mock_decision_packet(status: str = "approved") -> Any:
    obj = types.SimpleNamespace()
    obj.status = status
    obj.packet_id = "dp_xyz789"
    return obj


def _make_mock_reliability_report(status: str = "complete") -> Any:
    obj = types.SimpleNamespace()
    obj.status = status
    obj.report_id = "rlr_zzz000"
    return obj


# ---------------------------------------------------------------------------
# Section 1 — Literal type alias values
# ---------------------------------------------------------------------------

class TestLiteralTypeAliases(unittest.TestCase):

    def test_memory_record_status_values(self) -> None:
        expected = {"unknown", "active", "archived", "superseded", "invalidated", "needs_review"}
        args = MemoryRecordStatus.__args__  # type: ignore[attr-defined]
        self.assertEqual(set(args), expected)

    def test_research_run_memory_status_values(self) -> None:
        expected = {"unknown", "recorded", "incomplete", "needs_review", "blocked"}
        args = ResearchRunMemoryStatus.__args__  # type: ignore[attr-defined]
        self.assertEqual(set(args), expected)

    def test_research_run_memory_source_type_includes_all(self) -> None:
        expected_subset = {
            "orchestration", "horizon_synthesis", "macro", "debate",
            "decision_packet", "human_review", "review_loop",
            "event_intelligence", "trade_plan", "allocation",
            "option_expression", "integration_boundary", "validation",
            "staleness", "critic", "tool_result", "user_feedback", "unknown",
        }
        args = set(ResearchRunMemorySourceType.__args__)  # type: ignore[attr-defined]
        self.assertEqual(args, expected_subset)

    def test_memory_event_type_values(self) -> None:
        expected = {
            "research_run_created", "thesis_created", "decision_created",
            "review_requested", "human_feedback_added", "outcome_updated",
            "superseded", "invalidated", "unknown",
        }
        args = set(MemoryEventType.__args__)  # type: ignore[attr-defined]
        self.assertEqual(args, expected)

    def test_memory_actor_type_values(self) -> None:
        expected = {"system", "user", "reviewer", "agent", "unknown"}
        args = set(MemoryActorType.__args__)  # type: ignore[attr-defined]
        self.assertEqual(args, expected)


# ---------------------------------------------------------------------------
# Section 2 — MemorySourceRef validation
# ---------------------------------------------------------------------------

class TestMemorySourceRef(unittest.TestCase):

    def test_minimal_valid(self) -> None:
        ref = MemorySourceRef(source_id="src_001", source_type="orchestration")
        self.assertEqual(ref.source_id, "src_001")
        self.assertEqual(ref.source_type, "orchestration")
        self.assertIsNone(ref.artifact_id)
        self.assertEqual(ref.metadata, {})
        self.assertEqual(ref.warnings, [])

    def test_full_fields(self) -> None:
        ref = MemorySourceRef(
            source_id="src_002",
            source_type="decision_packet",
            artifact_id="dp_abc",
            run_id=_RUN_ID,
            target=_TARGET,
            field_path="status",
            evidence_id="eid_001",
            label="Decision Packet",
            metadata={"k": "v"},
            warnings=["warn1"],
        )
        self.assertEqual(ref.artifact_id, "dp_abc")
        self.assertEqual(ref.evidence_id, "eid_001")
        self.assertEqual(ref.label, "Decision Packet")
        self.assertEqual(ref.metadata, {"k": "v"})

    def test_empty_source_id_raises(self) -> None:
        with self.assertRaises(Exception):
            MemorySourceRef(source_id="", source_type="orchestration")

    def test_whitespace_source_id_raises(self) -> None:
        with self.assertRaises(Exception):
            MemorySourceRef(source_id="   ", source_type="orchestration")

    def test_extra_fields_forbidden(self) -> None:
        with self.assertRaises(Exception):
            MemorySourceRef(source_id="s", source_type="unknown", extra_field="oops")

    def test_unknown_source_type_accepted(self) -> None:
        ref = MemorySourceRef(source_id="s", source_type="unknown")
        self.assertEqual(ref.source_type, "unknown")

    def test_all_source_types_accepted(self) -> None:
        types_ = ResearchRunMemorySourceType.__args__  # type: ignore[attr-defined]
        for st in types_:
            ref = MemorySourceRef(source_id=f"src_{st}", source_type=st)  # type: ignore[arg-type]
            self.assertEqual(ref.source_type, st)


# ---------------------------------------------------------------------------
# Section 3 — MemoryEvent validation
# ---------------------------------------------------------------------------

class TestMemoryEvent(unittest.TestCase):

    def test_minimal_valid(self) -> None:
        evt = MemoryEvent(
            event_id="evt_001",
            event_type="research_run_created",
            created_at=_TS,
        )
        self.assertEqual(evt.event_id, "evt_001")
        self.assertEqual(evt.actor, "system")
        self.assertEqual(evt.description, "")
        self.assertEqual(evt.source_refs, [])
        self.assertEqual(evt.metadata, {})
        self.assertEqual(evt.warnings, [])

    def test_full_fields(self) -> None:
        ref = _make_source_ref()
        evt = MemoryEvent(
            event_id="evt_002",
            event_type="review_requested",
            created_at=_TS,
            actor="reviewer",
            description="Review was requested.",
            source_refs=[ref],
            metadata={"note": "x"},
            warnings=["w1"],
        )
        self.assertEqual(evt.actor, "reviewer")
        self.assertEqual(len(evt.source_refs), 1)

    def test_empty_event_id_raises(self) -> None:
        with self.assertRaises(Exception):
            MemoryEvent(event_id="", event_type="unknown", created_at=_TS)

    def test_whitespace_created_at_raises(self) -> None:
        with self.assertRaises(Exception):
            MemoryEvent(event_id="e", event_type="unknown", created_at="  ")

    def test_all_event_types_accepted(self) -> None:
        types_ = MemoryEventType.__args__  # type: ignore[attr-defined]
        for et in types_:
            evt = MemoryEvent(event_id=f"e_{et}", event_type=et, created_at=_TS)  # type: ignore[arg-type]
            self.assertEqual(evt.event_type, et)

    def test_all_actor_types_accepted(self) -> None:
        actors = MemoryActorType.__args__  # type: ignore[attr-defined]
        for actor in actors:
            evt = MemoryEvent(
                event_id=f"e_{actor}", event_type="unknown",
                created_at=_TS, actor=actor,  # type: ignore[arg-type]
            )
            self.assertEqual(evt.actor, actor)

    def test_extra_fields_forbidden(self) -> None:
        with self.assertRaises(Exception):
            MemoryEvent(event_id="e", event_type="unknown", created_at=_TS, bad=1)


# ---------------------------------------------------------------------------
# Section 4 — ResearchRunMemoryInputBundle validation
# ---------------------------------------------------------------------------

class TestResearchRunMemoryInputBundle(unittest.TestCase):

    def test_minimal_valid(self) -> None:
        bundle = _make_minimal_bundle()
        self.assertEqual(bundle.run_id, _RUN_ID)
        self.assertEqual(bundle.target, _TARGET)
        self.assertIsNone(bundle.workflow_name)
        self.assertEqual(bundle.source_refs, [])
        self.assertEqual(bundle.tool_result_ids, [])
        self.assertEqual(bundle.evidence_ids, [])
        self.assertEqual(bundle.artifact_refs, [])
        self.assertIsNone(bundle.decision_packet)
        self.assertIsNone(bundle.human_review_report)

    def test_full_bundle(self) -> None:
        ref = _make_source_ref()
        bundle = _make_minimal_bundle(
            workflow_name="test_workflow",
            source_refs=[ref],
            tool_result_ids=["tr_001"],
            evidence_ids=["eid_001"],
            artifact_refs=["art_001"],
            validation_summary={"ok": True},
            decision_packet=_make_mock_decision_packet(),
            human_review_report=_make_mock_human_review(),
            warnings=["w1"],
        )
        self.assertEqual(bundle.workflow_name, "test_workflow")
        self.assertEqual(len(bundle.source_refs), 1)
        self.assertIsNotNone(bundle.decision_packet)

    def test_empty_run_id_raises(self) -> None:
        with self.assertRaises(Exception):
            ResearchRunMemoryInputBundle(run_id="", target=_TARGET)

    def test_whitespace_target_raises(self) -> None:
        with self.assertRaises(Exception):
            ResearchRunMemoryInputBundle(run_id=_RUN_ID, target="  ")

    def test_extra_fields_forbidden(self) -> None:
        with self.assertRaises(Exception):
            ResearchRunMemoryInputBundle(run_id=_RUN_ID, target=_TARGET, bad_field=1)

    def test_optional_artifacts_default_none(self) -> None:
        bundle = _make_minimal_bundle()
        for attr in (
            "event_intelligence_report", "trade_plan_report",
            "allocation_report", "option_expression_report",
            "integration_boundary_report",
        ):
            self.assertIsNone(getattr(bundle, attr))


# ---------------------------------------------------------------------------
# Section 5 — ResearchRunMemorySummary validation
# ---------------------------------------------------------------------------

class TestResearchRunMemorySummary(unittest.TestCase):

    def _make(self, **kwargs: Any) -> ResearchRunMemorySummary:
        defaults = {
            "run_id": _RUN_ID,
            "target": _TARGET,
            "status": "recorded",
        }
        defaults.update(kwargs)
        return ResearchRunMemorySummary(**defaults)

    def test_minimal_valid(self) -> None:
        s = self._make()
        self.assertEqual(s.status, "recorded")
        self.assertFalse(s.approved_for_execution)
        self.assertFalse(s.blocked)
        self.assertFalse(s.review_required)
        self.assertFalse(s.has_decision_packet)
        self.assertFalse(s.has_human_review)

    def test_approved_for_execution_true_raises(self) -> None:
        with self.assertRaises(Exception):
            self._make(approved_for_execution=True)

    def test_all_status_values_accepted(self) -> None:
        statuses = ResearchRunMemoryStatus.__args__  # type: ignore[attr-defined]
        for st in statuses:
            s = self._make(status=st)  # type: ignore[arg-type]
            self.assertEqual(s.status, st)

    def test_counts_default_zero(self) -> None:
        s = self._make()
        self.assertEqual(s.source_count, 0)
        self.assertEqual(s.evidence_count, 0)
        self.assertEqual(s.tool_result_count, 0)
        self.assertEqual(s.artifact_count, 0)

    def test_top_warnings_populated(self) -> None:
        s = self._make(top_warnings=["a", "b"])
        self.assertEqual(s.top_warnings, ["a", "b"])

    def test_extra_fields_forbidden(self) -> None:
        with self.assertRaises(Exception):
            self._make(bad_field="x")


# ---------------------------------------------------------------------------
# Section 6 — ResearchRunMemoryRecord validation
# ---------------------------------------------------------------------------

class TestResearchRunMemoryRecord(unittest.TestCase):

    def _make_summary(self) -> ResearchRunMemorySummary:
        return ResearchRunMemorySummary(
            run_id=_RUN_ID, target=_TARGET, status="recorded"
        )

    def _make(self, **kwargs: Any) -> ResearchRunMemoryRecord:
        summary = self._make_summary()
        defaults = {
            "memory_id": "rmem_abc123",
            "run_id": _RUN_ID,
            "target": _TARGET,
            "status": "recorded",
            "summary": summary,
            "created_at": _TS,
            "updated_at": _TS,
        }
        defaults.update(kwargs)
        return ResearchRunMemoryRecord(**defaults)

    def test_minimal_valid(self) -> None:
        r = self._make()
        self.assertEqual(r.memory_id, "rmem_abc123")
        self.assertEqual(r.status, "recorded")
        self.assertFalse(r.approved_for_execution)
        self.assertEqual(r.calculation_version, _CALCULATION_VERSION)
        self.assertEqual(r.event_log, [])
        self.assertEqual(r.source_refs, [])
        self.assertEqual(r.evidence_ids, [])
        self.assertEqual(r.tool_result_ids, [])
        self.assertEqual(r.artifact_refs, [])

    def test_approved_for_execution_true_raises(self) -> None:
        with self.assertRaises(Exception):
            self._make(approved_for_execution=True)

    def test_empty_memory_id_raises(self) -> None:
        with self.assertRaises(Exception):
            self._make(memory_id="")

    def test_whitespace_target_raises(self) -> None:
        with self.assertRaises(Exception):
            self._make(target="  ")

    def test_whitespace_created_at_raises(self) -> None:
        with self.assertRaises(Exception):
            self._make(created_at="  ")

    def test_all_status_values(self) -> None:
        statuses = ResearchRunMemoryStatus.__args__  # type: ignore[attr-defined]
        for st in statuses:
            r = self._make(status=st, summary=ResearchRunMemorySummary(  # type: ignore[arg-type]
                run_id=_RUN_ID, target=_TARGET, status=st  # type: ignore[arg-type]
            ))
            self.assertEqual(r.status, st)

    def test_extra_fields_forbidden(self) -> None:
        with self.assertRaises(Exception):
            self._make(bad_field=True)

    def test_with_source_refs_and_events(self) -> None:
        ref = _make_source_ref()
        evt = MemoryEvent(event_id="e1", event_type="research_run_created", created_at=_TS)
        r = self._make(source_refs=[ref], event_log=[evt])
        self.assertEqual(len(r.source_refs), 1)
        self.assertEqual(len(r.event_log), 1)


# ---------------------------------------------------------------------------
# Section 7 — ResearchRunMemoryIndexEntry validation
# ---------------------------------------------------------------------------

class TestResearchRunMemoryIndexEntry(unittest.TestCase):

    def _make(self, **kwargs: Any) -> ResearchRunMemoryIndexEntry:
        defaults = {
            "memory_id": "rmem_abc",
            "run_id": _RUN_ID,
            "target": _TARGET,
            "status": "recorded",
            "created_at": _TS,
            "updated_at": _TS,
        }
        defaults.update(kwargs)
        return ResearchRunMemoryIndexEntry(**defaults)

    def test_minimal_valid(self) -> None:
        e = self._make()
        self.assertEqual(e.memory_id, "rmem_abc")
        self.assertFalse(e.review_required)
        self.assertFalse(e.blocked)
        self.assertEqual(e.tags, [])

    def test_with_tags(self) -> None:
        e = self._make(tags=["aapl", "q1-2026"])
        self.assertEqual(e.tags, ["aapl", "q1-2026"])

    def test_empty_memory_id_raises(self) -> None:
        with self.assertRaises(Exception):
            self._make(memory_id="")

    def test_whitespace_run_id_raises(self) -> None:
        with self.assertRaises(Exception):
            self._make(run_id="  ")

    def test_extra_fields_forbidden(self) -> None:
        with self.assertRaises(Exception):
            self._make(extra=True)


# ---------------------------------------------------------------------------
# Section 8 — make_research_run_memory_id
# ---------------------------------------------------------------------------

class TestMakeResearchRunMemoryId(unittest.TestCase):

    def test_returns_string(self) -> None:
        mid = make_research_run_memory_id(_RUN_ID, _TARGET, _AS_OF)
        self.assertIsInstance(mid, str)

    def test_starts_with_prefix(self) -> None:
        mid = make_research_run_memory_id(_RUN_ID, _TARGET, _AS_OF)
        self.assertTrue(mid.startswith("rmem_"))

    def test_deterministic(self) -> None:
        id1 = make_research_run_memory_id(_RUN_ID, _TARGET, _AS_OF)
        id2 = make_research_run_memory_id(_RUN_ID, _TARGET, _AS_OF)
        self.assertEqual(id1, id2)

    def test_different_inputs_different_ids(self) -> None:
        id1 = make_research_run_memory_id(_RUN_ID, _TARGET, _AS_OF)
        id2 = make_research_run_memory_id("OTHER_run", _TARGET, _AS_OF)
        self.assertNotEqual(id1, id2)

    def test_target_affects_id(self) -> None:
        id1 = make_research_run_memory_id(_RUN_ID, "AAPL", _AS_OF)
        id2 = make_research_run_memory_id(_RUN_ID, "MSFT", _AS_OF)
        self.assertNotEqual(id1, id2)

    def test_as_of_affects_id(self) -> None:
        id1 = make_research_run_memory_id(_RUN_ID, _TARGET, "2026-05-24T12:00:00Z")
        id2 = make_research_run_memory_id(_RUN_ID, _TARGET, "2026-05-25T12:00:00Z")
        self.assertNotEqual(id1, id2)


# ---------------------------------------------------------------------------
# Section 9 — make_memory_event_id
# ---------------------------------------------------------------------------

class TestMakeMemoryEventId(unittest.TestCase):

    def test_returns_string(self) -> None:
        eid = make_memory_event_id("rmem_abc", "research_run_created", _TS)
        self.assertIsInstance(eid, str)

    def test_starts_with_prefix(self) -> None:
        eid = make_memory_event_id("rmem_abc", "research_run_created", _TS)
        self.assertTrue(eid.startswith("mevt_"))

    def test_deterministic(self) -> None:
        id1 = make_memory_event_id("rmem_abc", "research_run_created", _TS)
        id2 = make_memory_event_id("rmem_abc", "research_run_created", _TS)
        self.assertEqual(id1, id2)

    def test_different_event_type_different_id(self) -> None:
        id1 = make_memory_event_id("rmem_abc", "research_run_created", _TS)
        id2 = make_memory_event_id("rmem_abc", "review_requested", _TS)
        self.assertNotEqual(id1, id2)


# ---------------------------------------------------------------------------
# Section 10 — collect_memory_source_refs
# ---------------------------------------------------------------------------

class TestCollectMemorySourceRefs(unittest.TestCase):

    def test_empty_bundle_returns_empty(self) -> None:
        bundle = _make_minimal_bundle()
        refs = collect_memory_source_refs(bundle)
        self.assertEqual(refs, [])

    def test_caller_supplied_refs_included(self) -> None:
        ref = _make_source_ref("s1", "orchestration")
        bundle = _make_minimal_bundle(source_refs=[ref])
        refs = collect_memory_source_refs(bundle)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].source_id, "s1")

    def test_deduplication_by_source_id(self) -> None:
        ref1 = _make_source_ref("s1", "orchestration")
        ref2 = _make_source_ref("s1", "debate")  # same ID, different type
        bundle = _make_minimal_bundle(source_refs=[ref1, ref2])
        refs = collect_memory_source_refs(bundle)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].source_type, "orchestration")  # first wins

    def test_auto_detect_from_reliability_report(self) -> None:
        rr = _make_mock_reliability_report()
        bundle = _make_minimal_bundle(reliability_report=rr)
        refs = collect_memory_source_refs(bundle)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].source_type, "review_loop")

    def test_auto_detect_from_decision_packet(self) -> None:
        dp = _make_mock_decision_packet()
        bundle = _make_minimal_bundle(decision_packet=dp)
        refs = collect_memory_source_refs(bundle)
        self.assertTrue(any(r.source_type == "decision_packet" for r in refs))

    def test_auto_detect_from_human_review(self) -> None:
        hr = _make_mock_human_review()
        bundle = _make_minimal_bundle(human_review_report=hr)
        refs = collect_memory_source_refs(bundle)
        self.assertTrue(any(r.source_type == "human_review" for r in refs))

    def test_auto_detect_multiple_artifacts(self) -> None:
        bundle = _make_minimal_bundle(
            decision_packet=_make_mock_decision_packet(),
            human_review_report=_make_mock_human_review(),
            reliability_report=_make_mock_reliability_report(),
        )
        refs = collect_memory_source_refs(bundle)
        types_ = {r.source_type for r in refs}
        self.assertIn("decision_packet", types_)
        self.assertIn("human_review", types_)
        self.assertIn("review_loop", types_)

    def test_caller_refs_before_auto_detected(self) -> None:
        ref = _make_source_ref("explicit_001", "orchestration")
        dp = _make_mock_decision_packet()
        bundle = _make_minimal_bundle(source_refs=[ref], decision_packet=dp)
        refs = collect_memory_source_refs(bundle)
        # explicit ref should come first
        self.assertEqual(refs[0].source_id, "explicit_001")

    def test_input_bundle_not_mutated(self) -> None:
        ref = _make_source_ref("s1")
        bundle = _make_minimal_bundle(source_refs=[ref])
        original_count = len(bundle.source_refs)
        collect_memory_source_refs(bundle)
        self.assertEqual(len(bundle.source_refs), original_count)


# ---------------------------------------------------------------------------
# Section 11 — collect_memory_evidence_ids
# ---------------------------------------------------------------------------

class TestCollectMemoryEvidenceIds(unittest.TestCase):

    def test_empty_returns_empty(self) -> None:
        bundle = _make_minimal_bundle()
        result = collect_memory_evidence_ids(bundle, [])
        self.assertEqual(result, [])

    def test_caller_supplied_ids_included(self) -> None:
        bundle = _make_minimal_bundle(evidence_ids=["eid_001", "eid_002"])
        result = collect_memory_evidence_ids(bundle, [])
        self.assertEqual(result, ["eid_001", "eid_002"])

    def test_deduplication(self) -> None:
        bundle = _make_minimal_bundle(evidence_ids=["eid_001", "eid_001", "eid_002"])
        result = collect_memory_evidence_ids(bundle, [])
        self.assertEqual(result.count("eid_001"), 1)
        self.assertIn("eid_002", result)

    def test_source_ref_evidence_ids_included(self) -> None:
        ref = MemorySourceRef(source_id="s1", source_type="orchestration", evidence_id="eid_from_ref")
        bundle = _make_minimal_bundle()
        result = collect_memory_evidence_ids(bundle, [ref])
        self.assertIn("eid_from_ref", result)

    def test_cross_deduplication(self) -> None:
        ref = MemorySourceRef(source_id="s1", source_type="orchestration", evidence_id="eid_shared")
        bundle = _make_minimal_bundle(evidence_ids=["eid_shared", "eid_other"])
        result = collect_memory_evidence_ids(bundle, [ref])
        self.assertEqual(result.count("eid_shared"), 1)
        self.assertIn("eid_other", result)

    def test_order_preserved(self) -> None:
        bundle = _make_minimal_bundle(evidence_ids=["eid_a", "eid_b", "eid_c"])
        result = collect_memory_evidence_ids(bundle, [])
        self.assertEqual(result, ["eid_a", "eid_b", "eid_c"])


# ---------------------------------------------------------------------------
# Section 12 — collect_memory_tool_result_ids
# ---------------------------------------------------------------------------

class TestCollectMemoryToolResultIds(unittest.TestCase):

    def test_empty_returns_empty(self) -> None:
        bundle = _make_minimal_bundle()
        result = collect_memory_tool_result_ids(bundle, [])
        self.assertEqual(result, [])

    def test_caller_supplied_ids_included(self) -> None:
        bundle = _make_minimal_bundle(tool_result_ids=["tr_001", "tr_002"])
        result = collect_memory_tool_result_ids(bundle, [])
        self.assertEqual(result, ["tr_001", "tr_002"])

    def test_deduplication(self) -> None:
        bundle = _make_minimal_bundle(tool_result_ids=["tr_001", "tr_001", "tr_002"])
        result = collect_memory_tool_result_ids(bundle, [])
        self.assertEqual(result.count("tr_001"), 1)

    def test_empty_strings_excluded(self) -> None:
        bundle = _make_minimal_bundle(tool_result_ids=["", "tr_001", ""])
        result = collect_memory_tool_result_ids(bundle, [])
        self.assertNotIn("", result)
        self.assertIn("tr_001", result)


# ---------------------------------------------------------------------------
# Section 13 — determine_research_run_memory_status
# ---------------------------------------------------------------------------

class TestDetermineResearchRunMemoryStatus(unittest.TestCase):

    def test_empty_bundle_incomplete_or_unknown(self) -> None:
        # Empty bundle: no dp, no rr → incomplete (missing both core artifacts)
        bundle = _make_minimal_bundle()
        refs = collect_memory_source_refs(bundle)
        status, review_req, blocked, warns = determine_research_run_memory_status(bundle, refs)
        self.assertIn(status, ("incomplete", "unknown"))
        self.assertTrue(review_req)  # missing important artifacts
        self.assertFalse(blocked)

    def test_human_review_blocked_causes_blocked(self) -> None:
        hr = _make_mock_human_review(status="blocked")
        bundle = _make_minimal_bundle(human_review_report=hr)
        refs = collect_memory_source_refs(bundle)
        status, _, blocked, warns = determine_research_run_memory_status(bundle, refs)
        self.assertEqual(status, "blocked")
        self.assertTrue(blocked)
        self.assertTrue(any("blocked" in w.lower() for w in warns))

    def test_decision_packet_blocked_causes_blocked(self) -> None:
        dp = _make_mock_decision_packet(status="blocked")
        bundle = _make_minimal_bundle(decision_packet=dp)
        refs = collect_memory_source_refs(bundle)
        status, _, blocked, _ = determine_research_run_memory_status(bundle, refs)
        self.assertEqual(status, "blocked")
        self.assertTrue(blocked)

    def test_missing_decision_packet_causes_review_required(self) -> None:
        bundle = _make_minimal_bundle()
        refs = collect_memory_source_refs(bundle)
        _, review_req, _, _ = determine_research_run_memory_status(bundle, refs)
        self.assertTrue(review_req)

    def test_missing_both_core_artifacts_causes_incomplete(self) -> None:
        bundle = _make_minimal_bundle()
        refs = collect_memory_source_refs(bundle)
        status, _, _, _ = determine_research_run_memory_status(bundle, refs)
        # No dp AND no rr → incomplete or unknown (missing important)
        self.assertIn(status, ("incomplete", "unknown"))

    def test_with_dp_and_rr_review_not_required(self) -> None:
        dp = _make_mock_decision_packet(status="approved")
        rr = _make_mock_reliability_report(status="complete")
        bundle = _make_minimal_bundle(
            decision_packet=dp,
            reliability_report=rr,
            source_refs=[_make_source_ref("s1")],
        )
        refs = collect_memory_source_refs(bundle)
        status, review_req, blocked, _ = determine_research_run_memory_status(bundle, refs)
        self.assertEqual(status, "recorded")
        self.assertFalse(blocked)

    def test_dp_fail_causes_needs_review(self) -> None:
        dp = _make_mock_decision_packet(status="fail")
        bundle = _make_minimal_bundle(decision_packet=dp, source_refs=[_make_source_ref("s1")])
        refs = collect_memory_source_refs(bundle)
        status, review_req, _, _ = determine_research_run_memory_status(bundle, refs)
        self.assertTrue(review_req)

    def test_rr_needs_revision_causes_needs_review(self) -> None:
        rr = _make_mock_reliability_report(status="needs_revision")
        bundle = _make_minimal_bundle(reliability_report=rr, source_refs=[_make_source_ref("s1")])
        refs = collect_memory_source_refs(bundle)
        _, review_req, _, _ = determine_research_run_memory_status(bundle, refs)
        self.assertTrue(review_req)

    def test_clean_run_recorded(self) -> None:
        dp = _make_mock_decision_packet(status="approved")
        rr = _make_mock_reliability_report(status="complete")
        bundle = _make_minimal_bundle(
            decision_packet=dp,
            reliability_report=rr,
            source_refs=[_make_source_ref("s1", "orchestration")],
        )
        refs = collect_memory_source_refs(bundle)
        status, review_req, blocked, _ = determine_research_run_memory_status(bundle, refs)
        self.assertEqual(status, "recorded")
        self.assertFalse(review_req)
        self.assertFalse(blocked)

    def test_status_precedence_blocked_beats_needs_review(self) -> None:
        hr = _make_mock_human_review(status="blocked")
        dp = _make_mock_decision_packet(status="fail")  # would be needs_review alone
        bundle = _make_minimal_bundle(
            human_review_report=hr, decision_packet=dp,
            source_refs=[_make_source_ref("s1")],
        )
        refs = collect_memory_source_refs(bundle)
        status, _, blocked, _ = determine_research_run_memory_status(bundle, refs)
        self.assertEqual(status, "blocked")
        self.assertTrue(blocked)

    def test_source_refs_makes_recorded_possible(self) -> None:
        dp = _make_mock_decision_packet(status="approved")
        rr = _make_mock_reliability_report(status="complete")
        bundle = _make_minimal_bundle(
            decision_packet=dp,
            reliability_report=rr,
            source_refs=[_make_source_ref("explicit_src")],
        )
        refs = collect_memory_source_refs(bundle)
        status, _, _, _ = determine_research_run_memory_status(bundle, refs)
        self.assertEqual(status, "recorded")


# ---------------------------------------------------------------------------
# Section 14 — build_memory_event
# ---------------------------------------------------------------------------

class TestBuildMemoryEvent(unittest.TestCase):

    def test_returns_memory_event(self) -> None:
        evt = build_memory_event(
            event_type="research_run_created",
            description="Created.",
            memory_id="rmem_abc",
            created_at=_TS,
        )
        self.assertIsInstance(evt, MemoryEvent)
        self.assertTrue(evt.event_id.startswith("mevt_"))
        self.assertEqual(evt.event_type, "research_run_created")
        self.assertEqual(evt.actor, "system")

    def test_explicit_created_at_used(self) -> None:
        evt = build_memory_event("unknown", "test", "rmem_abc", created_at=_TS)
        self.assertEqual(evt.created_at, _TS)

    def test_deterministic_with_explicit_created_at(self) -> None:
        e1 = build_memory_event("unknown", "test", "rmem_abc", created_at=_TS)
        e2 = build_memory_event("unknown", "test", "rmem_abc", created_at=_TS)
        self.assertEqual(e1.event_id, e2.event_id)

    def test_source_refs_passed_through(self) -> None:
        ref = _make_source_ref()
        evt = build_memory_event(
            "review_requested", "desc", "rmem_abc", created_at=_TS, source_refs=[ref]
        )
        self.assertEqual(len(evt.source_refs), 1)

    def test_actor_override(self) -> None:
        evt = build_memory_event("unknown", "d", "rmem_abc", created_at=_TS, actor="reviewer")
        self.assertEqual(evt.actor, "reviewer")

    def test_metadata_and_warnings(self) -> None:
        evt = build_memory_event(
            "unknown", "d", "rmem_abc", created_at=_TS,
            metadata={"k": 1}, warnings=["w"],
        )
        self.assertEqual(evt.metadata, {"k": 1})
        self.assertEqual(evt.warnings, ["w"])


# ---------------------------------------------------------------------------
# Section 15 — summarize_research_run_memory
# ---------------------------------------------------------------------------

class TestSummarizeResearchRunMemory(unittest.TestCase):

    def _call(self, **kwargs: Any) -> ResearchRunMemorySummary:
        bundle = _make_minimal_bundle(**kwargs)
        refs = collect_memory_source_refs(bundle)
        eids = collect_memory_evidence_ids(bundle, refs)
        tids = collect_memory_tool_result_ids(bundle, refs)
        status, review_req, blocked, warns = determine_research_run_memory_status(bundle, refs)
        return summarize_research_run_memory(
            input_bundle=bundle,
            status=status,
            source_refs=refs,
            evidence_ids=eids,
            tool_result_ids=tids,
            review_required=review_req,
            blocked=blocked,
            warnings=warns,
        )

    def test_approved_for_execution_always_false(self) -> None:
        s = self._call()
        self.assertFalse(s.approved_for_execution)

    def test_source_count_matches(self) -> None:
        ref = _make_source_ref()
        s = self._call(source_refs=[ref])
        self.assertGreaterEqual(s.source_count, 1)

    def test_has_decision_packet_true(self) -> None:
        dp = _make_mock_decision_packet()
        s = self._call(decision_packet=dp)
        self.assertTrue(s.has_decision_packet)

    def test_has_human_review_true(self) -> None:
        hr = _make_mock_human_review()
        s = self._call(human_review_report=hr)
        self.assertTrue(s.has_human_review)

    def test_has_flags_for_optional_artifacts(self) -> None:
        bundle = _make_minimal_bundle(
            event_intelligence_report=types.SimpleNamespace(report_id="ei_1"),
            trade_plan_report=types.SimpleNamespace(report_id="tp_1"),
            allocation_report=types.SimpleNamespace(report_id="alloc_1"),
            option_expression_report=types.SimpleNamespace(report_id="opt_1"),
            integration_boundary_report=types.SimpleNamespace(report_id="ib_1"),
        )
        refs = collect_memory_source_refs(bundle)
        eids = collect_memory_evidence_ids(bundle, refs)
        tids = collect_memory_tool_result_ids(bundle, refs)
        status, review_req, blocked, warns = determine_research_run_memory_status(bundle, refs)
        s = summarize_research_run_memory(
            input_bundle=bundle, status=status, source_refs=refs,
            evidence_ids=eids, tool_result_ids=tids,
            review_required=review_req, blocked=blocked, warnings=warns,
        )
        self.assertTrue(s.has_event_intelligence)
        self.assertTrue(s.has_trade_plan)
        self.assertTrue(s.has_allocation)
        self.assertTrue(s.has_option_expression)
        self.assertTrue(s.has_integration_boundary)

    def test_top_warnings_capped_at_five(self) -> None:
        warns = [f"warn_{i}" for i in range(10)]
        bundle = _make_minimal_bundle()
        refs = collect_memory_source_refs(bundle)
        eids = collect_memory_evidence_ids(bundle, refs)
        tids = collect_memory_tool_result_ids(bundle, refs)
        s = summarize_research_run_memory(
            input_bundle=bundle, status="unknown", source_refs=refs,
            evidence_ids=eids, tool_result_ids=tids,
            review_required=False, blocked=False, warnings=warns,
        )
        self.assertLessEqual(len(s.top_warnings), 5)


# ---------------------------------------------------------------------------
# Section 16 — build_research_run_memory_record (full integration)
# ---------------------------------------------------------------------------

class TestBuildResearchRunMemoryRecord(unittest.TestCase):

    def test_minimal_valid_record(self) -> None:
        bundle = _make_minimal_bundle()
        record = build_research_run_memory_record(bundle, created_at=_TS, updated_at=_TS)
        self.assertIsInstance(record, ResearchRunMemoryRecord)
        self.assertTrue(record.memory_id.startswith("rmem_"))
        self.assertEqual(record.run_id, _RUN_ID)
        self.assertEqual(record.target, _TARGET)
        self.assertFalse(record.approved_for_execution)
        self.assertEqual(record.calculation_version, _CALCULATION_VERSION)

    def test_deterministic_with_explicit_timestamps(self) -> None:
        bundle = _make_minimal_bundle()
        r1 = build_research_run_memory_record(bundle, created_at=_TS, updated_at=_TS)
        r2 = build_research_run_memory_record(bundle, created_at=_TS, updated_at=_TS)
        self.assertEqual(r1.memory_id, r2.memory_id)
        self.assertEqual(r1.status, r2.status)

    def test_stable_memory_id_across_calls(self) -> None:
        bundle = _make_minimal_bundle()
        r1 = build_research_run_memory_record(bundle, created_at=_TS)
        r2 = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(r1.memory_id, r2.memory_id)

    def test_explicit_created_at_used(self) -> None:
        bundle = _make_minimal_bundle()
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(record.created_at, _TS)

    def test_explicit_updated_at_used(self) -> None:
        updated = "2026-05-25T00:00:00+00:00"
        bundle = _make_minimal_bundle()
        record = build_research_run_memory_record(bundle, created_at=_TS, updated_at=updated)
        self.assertEqual(record.updated_at, updated)

    def test_event_log_has_creation_event(self) -> None:
        bundle = _make_minimal_bundle()
        record = build_research_run_memory_record(bundle, created_at=_TS)
        types_ = [e.event_type for e in record.event_log]
        self.assertIn("research_run_created", types_)

    def test_human_review_blocked_status(self) -> None:
        hr = _make_mock_human_review(status="blocked")
        bundle = _make_minimal_bundle(human_review_report=hr)
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(record.status, "blocked")
        self.assertTrue(record.summary.blocked)

    def test_clean_run_recorded_status(self) -> None:
        dp = _make_mock_decision_packet(status="approved")
        rr = _make_mock_reliability_report(status="complete")
        bundle = _make_minimal_bundle(
            decision_packet=dp,
            reliability_report=rr,
            source_refs=[_make_source_ref("s1")],
        )
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(record.status, "recorded")

    def test_source_refs_deduped(self) -> None:
        ref1 = _make_source_ref("dup_001")
        ref2 = _make_source_ref("dup_001")  # same ID
        bundle = _make_minimal_bundle(source_refs=[ref1, ref2])
        record = build_research_run_memory_record(bundle, created_at=_TS)
        ids = [r.source_id for r in record.source_refs]
        self.assertEqual(ids.count("dup_001"), 1)

    def test_evidence_ids_deduped(self) -> None:
        bundle = _make_minimal_bundle(evidence_ids=["eid_x", "eid_x", "eid_y"])
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(record.evidence_ids.count("eid_x"), 1)
        self.assertIn("eid_y", record.evidence_ids)

    def test_tool_result_ids_deduped(self) -> None:
        bundle = _make_minimal_bundle(tool_result_ids=["tr_a", "tr_a", "tr_b"])
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(record.tool_result_ids.count("tr_a"), 1)

    def test_missing_optional_artifacts_no_crash(self) -> None:
        bundle = _make_minimal_bundle()
        # Should not raise even though all optional artifacts are None
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertIsInstance(record, ResearchRunMemoryRecord)

    def test_missing_optional_artifacts_produce_warnings(self) -> None:
        bundle = _make_minimal_bundle()
        record = build_research_run_memory_record(bundle, created_at=_TS)
        # Missing decision_packet and reliability_report → warnings expected
        self.assertGreater(len(record.warnings), 0)

    def test_input_bundle_not_mutated(self) -> None:
        bundle = _make_minimal_bundle(source_refs=[_make_source_ref("s1")])
        original_refs = list(bundle.source_refs)
        build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(len(bundle.source_refs), len(original_refs))

    def test_approved_for_execution_always_false(self) -> None:
        bundle = _make_minimal_bundle()
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertFalse(record.approved_for_execution)
        self.assertFalse(record.summary.approved_for_execution)

    def test_review_required_event_present_when_blocked(self) -> None:
        hr = _make_mock_human_review(status="blocked")
        bundle = _make_minimal_bundle(human_review_report=hr)
        record = build_research_run_memory_record(bundle, created_at=_TS)
        evt_types = [e.event_type for e in record.event_log]
        self.assertIn("review_requested", evt_types)

    def test_full_artifact_bundle_record(self) -> None:
        dp = _make_mock_decision_packet(status="approved")
        hr = _make_mock_human_review(status="approved_for_research_only")
        rr = _make_mock_reliability_report(status="complete")
        ei = types.SimpleNamespace(report_id="ei_001")
        tp = types.SimpleNamespace(report_id="tp_001")
        alloc = types.SimpleNamespace(report_id="alloc_001")
        opt = types.SimpleNamespace(report_id="opt_001")
        ib = types.SimpleNamespace(report_id="ib_001")

        bundle = _make_minimal_bundle(
            decision_packet=dp,
            human_review_report=hr,
            reliability_report=rr,
            event_intelligence_report=ei,
            trade_plan_report=tp,
            allocation_report=alloc,
            option_expression_report=opt,
            integration_boundary_report=ib,
            tool_result_ids=["tr_001"],
            evidence_ids=["eid_001"],
            artifact_refs=["art_001"],
        )
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(record.status, "recorded")
        self.assertTrue(record.summary.has_decision_packet)
        self.assertTrue(record.summary.has_human_review)
        self.assertTrue(record.summary.has_event_intelligence)
        self.assertTrue(record.summary.has_trade_plan)
        self.assertTrue(record.summary.has_allocation)
        self.assertTrue(record.summary.has_option_expression)
        self.assertTrue(record.summary.has_integration_boundary)

    def test_without_explicit_timestamps_does_not_crash(self) -> None:
        bundle = _make_minimal_bundle()
        record = build_research_run_memory_record(bundle)
        self.assertIsInstance(record, ResearchRunMemoryRecord)
        self.assertTrue(len(record.created_at) > 0)


# ---------------------------------------------------------------------------
# Section 17 — build_memory_index_entry
# ---------------------------------------------------------------------------

class TestBuildMemoryIndexEntry(unittest.TestCase):

    def _make_record(self, status: str = "recorded") -> ResearchRunMemoryRecord:
        dp = _make_mock_decision_packet(status="approved")
        rr = _make_mock_reliability_report(status="complete")
        bundle = _make_minimal_bundle(
            decision_packet=dp, reliability_report=rr,
            source_refs=[_make_source_ref("s1")],
        )
        return build_research_run_memory_record(bundle, created_at=_TS)

    def test_returns_index_entry(self) -> None:
        record = self._make_record()
        entry = build_memory_index_entry(record)
        self.assertIsInstance(entry, ResearchRunMemoryIndexEntry)

    def test_memory_id_matches(self) -> None:
        record = self._make_record()
        entry = build_memory_index_entry(record)
        self.assertEqual(entry.memory_id, record.memory_id)

    def test_run_id_and_target_match(self) -> None:
        record = self._make_record()
        entry = build_memory_index_entry(record)
        self.assertEqual(entry.run_id, record.run_id)
        self.assertEqual(entry.target, record.target)

    def test_tags_default_empty(self) -> None:
        record = self._make_record()
        entry = build_memory_index_entry(record)
        self.assertEqual(entry.tags, [])

    def test_tags_passed_through(self) -> None:
        record = self._make_record()
        entry = build_memory_index_entry(record, tags=["aapl", "q1"])
        self.assertEqual(entry.tags, ["aapl", "q1"])

    def test_status_matches_record(self) -> None:
        record = self._make_record()
        entry = build_memory_index_entry(record)
        self.assertEqual(entry.status, record.status)

    def test_source_count_matches_summary(self) -> None:
        record = self._make_record()
        entry = build_memory_index_entry(record)
        self.assertEqual(entry.source_count, record.summary.source_count)

    def test_review_required_matches_summary(self) -> None:
        record = self._make_record()
        entry = build_memory_index_entry(record)
        self.assertEqual(entry.review_required, record.summary.review_required)

    def test_blocked_matches_summary(self) -> None:
        record = self._make_record()
        entry = build_memory_index_entry(record)
        self.assertEqual(entry.blocked, record.summary.blocked)


# ---------------------------------------------------------------------------
# Section 18 — research_run_memory_tool_result_from_record
# ---------------------------------------------------------------------------

class TestResearchRunMemoryToolResult(unittest.TestCase):

    def _make_record(self) -> ResearchRunMemoryRecord:
        dp = _make_mock_decision_packet(status="approved")
        rr = _make_mock_reliability_report(status="complete")
        bundle = _make_minimal_bundle(
            decision_packet=dp, reliability_report=rr,
            source_refs=[_make_source_ref("s1")],
        )
        return build_research_run_memory_record(bundle, created_at=_TS)

    def test_returns_tool_result(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertIsInstance(tr, ToolResult)

    def test_stable_tool_name(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertEqual(tr.tool_name, "research_run_memory_record")

    def test_ticker_matches_record_target(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertEqual(tr.ticker, record.target)

    def test_run_id_matches_record(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertEqual(tr.run_id, record.run_id)

    def test_evidence_id_is_deterministic(self) -> None:
        record = self._make_record()
        tr1 = research_run_memory_tool_result_from_record(record)
        tr2 = research_run_memory_tool_result_from_record(record)
        self.assertEqual(tr1.evidence_id, tr2.evidence_id)

    def test_evidence_id_non_empty(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertTrue(len(tr.evidence_id) > 0)

    def test_outputs_contains_key_fields(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        for key in (
            "memory_id", "run_id", "target", "status",
            "calculation_version", "approved_for_execution",
        ):
            self.assertIn(key, tr.outputs)

    def test_approved_for_execution_false_in_outputs(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertFalse(tr.outputs["approved_for_execution"])

    def test_no_order_ticket_fields_in_outputs(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        # No brokerage / order / execution fields
        for bad_key in (
            "order_id", "account_id", "broker", "execution_price",
            "fill_qty", "order_type", "limit_price",
        ):
            self.assertNotIn(bad_key, tr.outputs)

    def test_different_records_different_evidence_ids(self) -> None:
        bundle1 = _make_minimal_bundle()
        bundle2 = _make_minimal_bundle(run_id="MSFT_20260524_120000_zzzz", target="MSFT")
        r1 = build_research_run_memory_record(bundle1, created_at=_TS)
        r2 = build_research_run_memory_record(bundle2, created_at=_TS)
        tr1 = research_run_memory_tool_result_from_record(r1)
        tr2 = research_run_memory_tool_result_from_record(r2)
        self.assertNotEqual(tr1.evidence_id, tr2.evidence_id)


# ---------------------------------------------------------------------------
# Section 19 — __all__ export smoke test
# ---------------------------------------------------------------------------

class TestAllExports(unittest.TestCase):

    EXPECTED_SYMBOLS = [
        # Literals
        "MemoryActorType",
        "MemoryEventType",
        "MemoryRecordStatus",
        "ResearchRunMemorySourceType",
        "ResearchRunMemoryStatus",
        # Models
        "MemoryEvent",
        "MemorySourceRef",
        "ResearchRunMemoryIndexEntry",
        "ResearchRunMemoryInputBundle",
        "ResearchRunMemoryRecord",
        "ResearchRunMemorySummary",
        # Helpers
        "build_memory_event",
        "build_memory_index_entry",
        "build_research_run_memory_record",
        "collect_memory_evidence_ids",
        "collect_memory_source_refs",
        "collect_memory_tool_result_ids",
        "determine_research_run_memory_status",
        "make_memory_event_id",
        "make_research_run_memory_id",
        "research_run_memory_tool_result_from_record",
        "summarize_research_run_memory",
    ]

    def test_module_all_contains_phase_4m_symbols(self) -> None:
        import lib.reliability.research_memory as mod
        for sym in self.EXPECTED_SYMBOLS:
            self.assertIn(sym, mod.__all__, f"Missing from __all__: {sym}")

    def test_init_all_contains_phase_4m_symbols(self) -> None:
        import lib.reliability as pkg
        for sym in self.EXPECTED_SYMBOLS:
            self.assertIn(sym, pkg.__all__, f"Missing from lib.reliability.__all__: {sym}")

    def test_symbols_importable_from_package(self) -> None:
        import lib.reliability as pkg
        for sym in self.EXPECTED_SYMBOLS:
            self.assertTrue(
                hasattr(pkg, sym),
                f"Symbol not importable from lib.reliability: {sym}",
            )


# ---------------------------------------------------------------------------
# Section 20 — Forbidden dependency check
# ---------------------------------------------------------------------------

class TestForbiddenDependencies(unittest.TestCase):
    """
    Verify that research_memory.py does not import forbidden modules.

    Checks that importing research_memory does NOT pull in:
      - streamlit
      - anthropic (Claude API)
      - openai
      - sqlalchemy, pymongo, redis (databases)
      - chromadb, pinecone, weaviate (vector stores)
      - alpaca, ibapi, td_api (brokers/order systems)
      - app, pages (live workflow)
      - llm_orchestrator (live LLM dispatch)
    """

    # Check for actual import statements — substring search on the full source would
    # produce false positives for words like "app" appearing in docstrings.
    FORBIDDEN_IMPORT_PATTERNS = [
        "import streamlit",
        "import anthropic",
        "import openai",
        "import sqlalchemy",
        "import pymongo",
        "import redis",
        "import chromadb",
        "import pinecone",
        "import weaviate",
        "import alpaca",
        "import ibapi",
        "from lib.llm_orchestrator",
        "import lib.llm_orchestrator",
        "from app ",
        "import app\n",
    ]

    def test_no_forbidden_imports(self) -> None:
        import lib.reliability.research_memory as mod
        source_file = getattr(mod, "__file__", None)
        self.assertIsNotNone(source_file)
        with open(source_file, "r", encoding="utf-8") as f:
            source = f.read()
        for pattern in self.FORBIDDEN_IMPORT_PATTERNS:
            self.assertNotIn(
                pattern,
                source,
                f"Forbidden import pattern {pattern!r} found in research_memory.py",
            )

    def test_no_network_calls_imported(self) -> None:
        # urllib3, httpx, requests should not be imported
        import lib.reliability.research_memory as mod
        source_file = getattr(mod, "__file__", None)
        assert source_file is not None
        with open(source_file, "r", encoding="utf-8") as f:
            source = f.read()
        for net_lib in ("requests", "urllib3", "httpx", "aiohttp"):
            self.assertNotIn(
                f"import {net_lib}",
                source,
                f"Network library '{net_lib}' imported in research_memory.py",
            )


# ---------------------------------------------------------------------------
# Section 21 — Deterministic timestamp regression tests (Fix 1)
# ---------------------------------------------------------------------------

class TestDeterministicTimestamps(unittest.TestCase):
    """Regression tests verifying timestamp resolution is fully deterministic."""

    def test_no_explicit_timestamps_fully_deterministic(self) -> None:
        """Build record twice without explicit timestamps → identical model_dump."""
        bundle = _make_minimal_bundle()  # has as_of=_AS_OF
        r1 = build_research_run_memory_record(bundle)
        r2 = build_research_run_memory_record(bundle)
        self.assertEqual(r1.model_dump(), r2.model_dump())

    def test_default_created_at_from_as_of(self) -> None:
        """Without explicit timestamps, created_at defaults to input_bundle.as_of."""
        bundle = ResearchRunMemoryInputBundle(run_id=_RUN_ID, target=_TARGET, as_of=_AS_OF)
        record = build_research_run_memory_record(bundle)
        self.assertEqual(record.created_at, _AS_OF)
        self.assertEqual(record.updated_at, _AS_OF)

    def test_bundle_created_at_takes_priority_over_as_of(self) -> None:
        """input_bundle.created_at takes priority over input_bundle.as_of."""
        bundle_ts = "2026-06-01T08:00:00+00:00"
        bundle = ResearchRunMemoryInputBundle(
            run_id=_RUN_ID, target=_TARGET,
            as_of="2026-05-01T00:00:00+00:00",
            created_at=bundle_ts,
        )
        record = build_research_run_memory_record(bundle)
        self.assertEqual(record.created_at, bundle_ts)

    def test_deterministic_fallback_constant_when_no_timestamps(self) -> None:
        """Without as_of or bundle.created_at, the fallback constant is used."""
        bundle = ResearchRunMemoryInputBundle(run_id=_RUN_ID, target=_TARGET)
        r1 = build_research_run_memory_record(bundle)
        r2 = build_research_run_memory_record(bundle)
        self.assertEqual(r1.created_at, r2.created_at)
        self.assertEqual(r1.updated_at, r2.updated_at)
        self.assertEqual(r1.created_at, _DETERMINISTIC_TIMESTAMP_DEFAULT)

    def test_deterministic_fallback_full_model_dump_identical(self) -> None:
        """Full model_dump identical when no timestamps available."""
        bundle = ResearchRunMemoryInputBundle(run_id=_RUN_ID, target=_TARGET)
        r1 = build_research_run_memory_record(bundle)
        r2 = build_research_run_memory_record(bundle)
        self.assertEqual(r1.model_dump(), r2.model_dump())

    def test_explicit_created_at_overrides_bundle_as_of(self) -> None:
        """Explicit created_at arg overrides bundle.as_of."""
        bundle = ResearchRunMemoryInputBundle(
            run_id=_RUN_ID, target=_TARGET,
            as_of="2026-05-01T00:00:00+00:00",
        )
        explicit_ts = "2026-06-01T00:00:00+00:00"
        record = build_research_run_memory_record(bundle, created_at=explicit_ts)
        self.assertEqual(record.created_at, explicit_ts)

    def test_explicit_created_at_overrides_bundle_created_at(self) -> None:
        """Explicit created_at arg overrides input_bundle.created_at."""
        bundle = ResearchRunMemoryInputBundle(
            run_id=_RUN_ID, target=_TARGET,
            created_at="2026-05-10T00:00:00+00:00",
        )
        explicit_ts = "2026-06-01T00:00:00+00:00"
        record = build_research_run_memory_record(bundle, created_at=explicit_ts)
        self.assertEqual(record.created_at, explicit_ts)

    def test_updated_at_defaults_to_created_at_when_omitted(self) -> None:
        """If only created_at is resolved, updated_at defaults to created_at."""
        bundle = ResearchRunMemoryInputBundle(run_id=_RUN_ID, target=_TARGET)
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(record.updated_at, _TS)

    def test_explicit_updated_at_overrides_created_at_default(self) -> None:
        """Explicit updated_at is used even when it differs from created_at."""
        updated = "2026-05-25T00:00:00+00:00"
        bundle = ResearchRunMemoryInputBundle(run_id=_RUN_ID, target=_TARGET)
        record = build_research_run_memory_record(bundle, created_at=_TS, updated_at=updated)
        self.assertEqual(record.updated_at, updated)

    def test_event_log_timestamps_match_resolved_created_at(self) -> None:
        """Events in the initial log use the same resolved created_at."""
        bundle = ResearchRunMemoryInputBundle(run_id=_RUN_ID, target=_TARGET, as_of=_AS_OF)
        record = build_research_run_memory_record(bundle)
        for evt in record.event_log:
            self.assertEqual(evt.created_at, _AS_OF)


# ---------------------------------------------------------------------------
# Section 22 — ToolResult full record payload and evidence fidelity (Fix 2)
# ---------------------------------------------------------------------------

class TestToolResultFullRecordPayload(unittest.TestCase):
    """Regression tests verifying ToolResult includes the full record and has
    content-sensitive evidence_id."""

    def _make_record(self, **kwargs: Any) -> ResearchRunMemoryRecord:
        bundle = _make_minimal_bundle(**kwargs)
        return build_research_run_memory_record(bundle, created_at=_TS)

    def test_outputs_include_full_record(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertIn("record", tr.outputs)
        self.assertEqual(tr.outputs["record"], record.model_dump())

    def test_outputs_include_summary(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertIn("summary", tr.outputs)
        self.assertEqual(tr.outputs["summary"], record.summary.model_dump())

    def test_outputs_include_calculation_version(self) -> None:
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertIn("calculation_version", tr.outputs)
        self.assertEqual(tr.outputs["calculation_version"], _CALCULATION_VERSION)

    def test_evidence_id_changes_with_different_source_refs(self) -> None:
        """Different source_refs → different evidence_id even when counts are equal."""
        ref_a = MemorySourceRef(source_id="src_aaa_unique", source_type="orchestration")
        ref_b = MemorySourceRef(source_id="src_bbb_unique", source_type="orchestration")
        r1 = build_research_run_memory_record(
            _make_minimal_bundle(source_refs=[ref_a]), created_at=_TS
        )
        r2 = build_research_run_memory_record(
            _make_minimal_bundle(source_refs=[ref_b]), created_at=_TS
        )
        # Both have source_count == 1, but different source_ref content
        self.assertEqual(r1.summary.source_count, r2.summary.source_count)
        tr1 = research_run_memory_tool_result_from_record(r1)
        tr2 = research_run_memory_tool_result_from_record(r2)
        self.assertNotEqual(tr1.evidence_id, tr2.evidence_id)

    def test_evidence_id_changes_with_different_warnings(self) -> None:
        """Different warnings → different evidence_id even if counts are same."""
        r1 = build_research_run_memory_record(
            _make_minimal_bundle(warnings=["warn_alpha"]), created_at=_TS
        )
        r2 = build_research_run_memory_record(
            _make_minimal_bundle(warnings=["warn_beta"]), created_at=_TS
        )
        tr1 = research_run_memory_tool_result_from_record(r1)
        tr2 = research_run_memory_tool_result_from_record(r2)
        self.assertNotEqual(tr1.evidence_id, tr2.evidence_id)

    def test_evidence_id_changes_with_different_artifact_refs(self) -> None:
        """Different artifact_refs → different evidence_id."""
        r1 = build_research_run_memory_record(
            _make_minimal_bundle(artifact_refs=["art_aaa_unique"]), created_at=_TS
        )
        r2 = build_research_run_memory_record(
            _make_minimal_bundle(artifact_refs=["art_bbb_unique"]), created_at=_TS
        )
        tr1 = research_run_memory_tool_result_from_record(r1)
        tr2 = research_run_memory_tool_result_from_record(r2)
        self.assertNotEqual(tr1.evidence_id, tr2.evidence_id)

    def test_evidence_id_changes_with_different_event_log(self) -> None:
        """Different event log content → different evidence_id."""
        bundle1 = _make_minimal_bundle()
        bundle2 = _make_minimal_bundle(warnings=["extra_warning_for_event_log"])
        r1 = build_research_run_memory_record(bundle1, created_at=_TS)
        r2 = build_research_run_memory_record(bundle2, created_at=_TS)
        tr1 = research_run_memory_tool_result_from_record(r1)
        tr2 = research_run_memory_tool_result_from_record(r2)
        self.assertNotEqual(tr1.evidence_id, tr2.evidence_id)

    def test_evidence_id_stable_for_identical_records(self) -> None:
        """Same record produces same evidence_id on repeated calls."""
        record = self._make_record()
        tr1 = research_run_memory_tool_result_from_record(record)
        tr2 = research_run_memory_tool_result_from_record(record)
        self.assertEqual(tr1.evidence_id, tr2.evidence_id)

    def test_approved_for_execution_false_in_record_payload(self) -> None:
        """approved_for_execution is False in both top-level and nested record."""
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        self.assertFalse(tr.outputs["approved_for_execution"])
        self.assertFalse(tr.outputs["record"]["approved_for_execution"])

    def test_no_execution_implication_in_outputs(self) -> None:
        """ToolResult outputs contain no order/broker/execution fields."""
        record = self._make_record()
        tr = research_run_memory_tool_result_from_record(record)
        for bad_key in (
            "order_id", "account_id", "broker", "execution_price",
            "fill_qty", "order_type", "limit_price",
        ):
            self.assertNotIn(bad_key, tr.outputs)

    def test_full_record_includes_source_refs(self) -> None:
        """Full record dump in outputs includes source_refs list."""
        ref = _make_source_ref("fidelity_test_src", "orchestration")
        record = self._make_record(source_refs=[ref])
        tr = research_run_memory_tool_result_from_record(record)
        full = tr.outputs["record"]
        self.assertIn("source_refs", full)
        self.assertEqual(len(full["source_refs"]), 1)
        self.assertEqual(full["source_refs"][0]["source_id"], "fidelity_test_src")

    def test_full_record_includes_artifact_refs(self) -> None:
        """Full record dump includes artifact_refs."""
        record = self._make_record(artifact_refs=["art_fidelity_001"])
        tr = research_run_memory_tool_result_from_record(record)
        self.assertIn("artifact_refs", tr.outputs["record"])
        self.assertIn("art_fidelity_001", tr.outputs["record"]["artifact_refs"])

    def test_full_record_includes_warnings(self) -> None:
        """Full record dump includes warnings list."""
        record = self._make_record(warnings=["test_warning_fidelity"])
        tr = research_run_memory_tool_result_from_record(record)
        self.assertIn("warnings", tr.outputs["record"])


# ---------------------------------------------------------------------------
# Section 23 — artifact_refs empty string filtering (Fix 4)
# ---------------------------------------------------------------------------

class TestArtifactRefsFiltering(unittest.TestCase):
    """Optional Fix 4: empty/whitespace artifact_refs are filtered out."""

    def test_empty_string_artifact_refs_excluded(self) -> None:
        bundle = _make_minimal_bundle(artifact_refs=["", "art_valid", ""])
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertNotIn("", record.artifact_refs)
        self.assertIn("art_valid", record.artifact_refs)

    def test_whitespace_artifact_refs_excluded(self) -> None:
        bundle = _make_minimal_bundle(artifact_refs=["   ", "art_valid2", "\t"])
        record = build_research_run_memory_record(bundle, created_at=_TS)
        for r in record.artifact_refs:
            self.assertTrue(r.strip(), f"Whitespace-only ref not filtered: {r!r}")
        self.assertIn("art_valid2", record.artifact_refs)

    def test_valid_artifact_refs_preserved(self) -> None:
        bundle = _make_minimal_bundle(artifact_refs=["art_a", "art_b", "art_c"])
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(record.artifact_refs, ["art_a", "art_b", "art_c"])

    def test_artifact_count_excludes_empty_strings(self) -> None:
        bundle = _make_minimal_bundle(artifact_refs=["", "art_x", ""])
        record = build_research_run_memory_record(bundle, created_at=_TS)
        self.assertEqual(record.summary.artifact_count, 1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestLiteralTypeAliases,
        TestMemorySourceRef,
        TestMemoryEvent,
        TestResearchRunMemoryInputBundle,
        TestResearchRunMemorySummary,
        TestResearchRunMemoryRecord,
        TestResearchRunMemoryIndexEntry,
        TestMakeResearchRunMemoryId,
        TestMakeMemoryEventId,
        TestCollectMemorySourceRefs,
        TestCollectMemoryEvidenceIds,
        TestCollectMemoryToolResultIds,
        TestDetermineResearchRunMemoryStatus,
        TestBuildMemoryEvent,
        TestSummarizeResearchRunMemory,
        TestBuildResearchRunMemoryRecord,
        TestBuildMemoryIndexEntry,
        TestResearchRunMemoryToolResult,
        TestAllExports,
        TestForbiddenDependencies,
        TestDeterministicTimestamps,
        TestToolResultFullRecordPayload,
        TestArtifactRefsFiltering,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total - failures - errors

    print(f"\n{'='*60}")
    print(f"Phase 4M-A Research Run Memory Schema — Test Results")
    print(f"{'='*60}")
    print(f"Total:   {total}")
    print(f"Passed:  {passed}")
    print(f"Failed:  {failures}")
    print(f"Errors:  {errors}")

    if failures == 0 and errors == 0:
        print(f"\nALL {total} TESTS PASSED.")
        sys.exit(0)
    else:
        print(f"\nSOME TESTS FAILED.")
        sys.exit(1)
