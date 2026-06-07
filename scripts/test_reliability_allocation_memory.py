"""
scripts/test_reliability_allocation_memory.py

Phase 4M-D: Allocation Decision Memory — comprehensive test suite.
Also covers Phase 4M-C minor polish: source_refs deduplication in
build_event_memory_record().

Run: python3 scripts/test_reliability_allocation_memory.py

All tests are offline/mock-only. No network, DB, vector store, file writes,
Claude API calls, Streamlit, Finnhub, brokerage, broker/order/execution,
or live portfolio dependencies.
"""

import sys
import os

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import types

# ---------------------------------------------------------------------------
# Section 0: guard forbidden imports
# ---------------------------------------------------------------------------

_forbidden_modules = [
    "streamlit",
    "anthropic",
    "requests",
    "httpx",
    "sqlalchemy",
    "psycopg2",
    "pymongo",
    "redis",
    "chromadb",
    "pinecone",
    "weaviate",
    "alpaca_trade_api",
    "ib_insync",
    "robin_stocks",
    "finnhub",
]

_test_count = 0
_fail_count = 0


def _ok(label: str) -> None:
    global _test_count
    _test_count += 1
    print(f"  PASS  {label}")


def _fail(label: str, reason: str) -> None:
    global _test_count, _fail_count
    _test_count += 1
    _fail_count += 1
    print(f"  FAIL  {label}: {reason}")


def _check(label: str, condition: bool, reason: str = "") -> None:
    if condition:
        _ok(label)
    else:
        _fail(label, reason or "condition was False")


def _section(title: str) -> None:
    print(f"\n--- {title} ---")


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from pydantic import ValidationError

from lib.reliability.allocation_memory import (
    AllocationDecisionAction,
    AllocationDecisionMemoryRecord,
    AllocationDecisionOutcome,
    AllocationDecisionReviewStatus,
    AllocationDecisionSnapshot,
    AllocationMemoryActorType,
    AllocationMemoryEventType,
    AllocationMemoryInputBundle,
    AllocationMemoryLogEntry,
    AllocationMemoryReport,
    AllocationMemoryRiskLevel,
    AllocationMemorySourceRef,
    AllocationMemoryStatus,
    AllocationMemorySummary,
    allocation_memory_tool_result_from_report,
    build_allocation_decision_snapshot,
    build_allocation_memory_log_entry,
    build_allocation_memory_record,
    build_allocation_memory_report,
    collect_allocation_memory_artifact_refs,
    collect_allocation_memory_evidence_ids,
    collect_allocation_memory_source_ids,
    determine_allocation_memory_status,
    make_allocation_memory_log_entry_id,
    make_allocation_memory_record_id,
    make_allocation_memory_report_id,
    summarize_allocation_memory,
)

# Also import event_memory for Phase 4M-C polish verification
from lib.reliability.event_memory import (
    EventMemorySourceRef,
    build_event_memory_record,
)

_section("0: Forbidden import guard")

for _mod in _forbidden_modules:
    _check(
        f"0.x {_mod} not imported",
        _mod not in sys.modules,
        f"{_mod} was unexpectedly imported",
    )


# ---------------------------------------------------------------------------
# Section 1: Phase 4M-C minor polish — source_refs dedup in build_event_memory_record
# ---------------------------------------------------------------------------

_section("1: Phase 4M-C polish — build_event_memory_record source_refs deduplication")

_dup_a = EventMemorySourceRef(source_id="src_dup", source_type="news", label="First")
_dup_b = EventMemorySourceRef(source_id="src_dup", source_type="analyst_note", label="Second")
_dup_c = EventMemorySourceRef(source_id="src_unique", source_type="earnings_report")

_emr = build_event_memory_record(
    target="NVDA",
    event_name="Dedup Test",
    summary="Verifying source_refs dedup in Phase 4M-C.",
    source_refs=[_dup_a, _dup_b, _dup_c],
)
_check("1.1 duplicate source_refs deduped to 2", len(_emr.source_refs) == 2)
_check("1.2 first occurrence kept for dup id", _emr.source_refs[0].label == "First")
_check("1.3 unique ref present", _emr.source_refs[1].source_id == "src_unique")

_emr2 = build_event_memory_record(
    target="NVDA",
    event_name="Dedup Test",
    summary="Verifying source_refs dedup in Phase 4M-C.",
    source_refs=[_dup_a, _dup_b, _dup_c],
)
_check("1.4 dedup is deterministic across calls", len(_emr2.source_refs) == 2)
_check("1.5 dedup result stable", _emr.source_refs[0].source_id == _emr2.source_refs[0].source_id)

_emr_all_same = build_event_memory_record(
    target="NVDA",
    event_name="All Same IDs",
    summary="All source_refs have same source_id.",
    source_refs=[
        EventMemorySourceRef(source_id="src_x", label="A"),
        EventMemorySourceRef(source_id="src_x", label="B"),
        EventMemorySourceRef(source_id="src_x", label="C"),
    ],
)
_check("1.6 all-same source_id collapses to 1", len(_emr_all_same.source_refs) == 1)
_check("1.7 first label kept for all-same", _emr_all_same.source_refs[0].label == "A")

_emr_no_dup = build_event_memory_record(
    target="NVDA",
    event_name="No Dup",
    summary="No duplicates.",
    source_refs=[_dup_a, _dup_c],
)
_check("1.8 no-dup input preserved", len(_emr_no_dup.source_refs) == 2)


# ---------------------------------------------------------------------------
# Section 2: AllocationMemorySourceRef validation
# ---------------------------------------------------------------------------

_section("2: AllocationMemorySourceRef validation")

ref1 = AllocationMemorySourceRef(source_id="src_001", source_type="allocation_report", label="Phase3RC")
_check("2.1 AllocationMemorySourceRef creates OK", ref1.source_id == "src_001")
_check("2.2 source_type set", ref1.source_type == "allocation_report")
_check("2.3 label set", ref1.label == "Phase3RC")
_check("2.4 artifact_id defaults None", ref1.artifact_id is None)
_check("2.5 evidence_id defaults None", ref1.evidence_id is None)
_check("2.6 field_path defaults None", ref1.field_path is None)
_check("2.7 metadata defaults empty dict", ref1.metadata == {})
_check("2.8 warnings defaults empty list", ref1.warnings == [])

ref2 = AllocationMemorySourceRef(
    source_id="src_002",
    artifact_id="art_abc",
    evidence_id="eid_xyz",
    field_path="report.summary.risk_level",
    metadata={"phase": "3R-C"},
    warnings=["minor warning"],
)
_check("2.9 artifact_id set", ref2.artifact_id == "art_abc")
_check("2.10 evidence_id set", ref2.evidence_id == "eid_xyz")
_check("2.11 field_path set", ref2.field_path == "report.summary.risk_level")
_check("2.12 metadata set", ref2.metadata == {"phase": "3R-C"})
_check("2.13 warnings set", ref2.warnings == ["minor warning"])

try:
    AllocationMemorySourceRef(source_id="")
    _fail("2.14 empty source_id rejected", "should have raised")
except ValidationError:
    _ok("2.14 empty source_id rejected")

try:
    AllocationMemorySourceRef(source_id="   ")
    _fail("2.15 whitespace source_id rejected", "should have raised")
except ValidationError:
    _ok("2.15 whitespace source_id rejected")

try:
    AllocationMemorySourceRef(source_id="src_ok", extra_field="bad")
    _fail("2.16 extra fields rejected", "should have raised")
except ValidationError:
    _ok("2.16 extra fields rejected")


# ---------------------------------------------------------------------------
# Section 3: AllocationDecisionSnapshot validation
# ---------------------------------------------------------------------------

_section("3: AllocationDecisionSnapshot validation")

snap1 = AllocationDecisionSnapshot(
    snapshot_id="asnap_001",
    target="NVDA",
)
_check("3.1 snapshot creates OK with minimal fields", snap1.snapshot_id == "asnap_001")
_check("3.2 target set", snap1.target == "NVDA")
_check("3.3 all pct fields default None", snap1.target_allocation_pct is None)
_check("3.4 risk_level defaults unknown", snap1.risk_level == "unknown")
_check("3.5 source_refs defaults empty list", snap1.source_refs == [])
_check("3.6 evidence_ids defaults empty list", snap1.evidence_ids == [])
_check("3.7 artifact_refs defaults empty list", snap1.artifact_refs == [])
_check("3.8 warnings defaults empty list", snap1.warnings == [])

snap2 = AllocationDecisionSnapshot(
    snapshot_id="asnap_002",
    target="NVDA",
    target_allocation_pct=0.05,
    actual_allocation_pct=0.03,
    min_allocation_pct=0.02,
    max_allocation_pct=0.08,
    cash_pct=0.15,
    required_trade_value=10000.0,
    required_shares=50.0,
    cash_impact=-10000.0,
    projected_cash_pct=0.12,
    portfolio_loss_pct=0.02,
    risk_budget_pct=0.005,
    risk_level="medium",
)
_check("3.9 all pct fields set", snap2.target_allocation_pct == 0.05)
_check("3.10 risk_level set", snap2.risk_level == "medium")
_check("3.11 required_trade_value signed positive", snap2.required_trade_value == 10000.0)
_check("3.12 cash_impact signed negative", snap2.cash_impact == -10000.0)
_check("3.13 required_shares set", snap2.required_shares == 50.0)

# pct field out of range rejected
try:
    AllocationDecisionSnapshot(snapshot_id="s", target="X", target_allocation_pct=1.5)
    _fail("3.14 target_allocation_pct > 1 rejected", "should have raised")
except ValidationError:
    _ok("3.14 target_allocation_pct > 1 rejected")

try:
    AllocationDecisionSnapshot(snapshot_id="s", target="X", cash_pct=-0.01)
    _fail("3.15 negative cash_pct rejected", "should have raised")
except ValidationError:
    _ok("3.15 negative cash_pct rejected")

# portfolio_loss_pct negative rejected
try:
    AllocationDecisionSnapshot(snapshot_id="s", target="X", portfolio_loss_pct=-0.01)
    _fail("3.16 negative portfolio_loss_pct rejected", "should have raised")
except ValidationError:
    _ok("3.16 negative portfolio_loss_pct rejected")

# portfolio_loss_pct can be 0
snap_zero_loss = AllocationDecisionSnapshot(snapshot_id="s", target="X", portfolio_loss_pct=0.0)
_check("3.17 portfolio_loss_pct = 0 accepted", snap_zero_loss.portfolio_loss_pct == 0.0)

# risk_budget_pct negative rejected
try:
    AllocationDecisionSnapshot(snapshot_id="s", target="X", risk_budget_pct=-0.001)
    _fail("3.18 negative risk_budget_pct rejected", "should have raised")
except ValidationError:
    _ok("3.18 negative risk_budget_pct rejected")

# boundary values accepted
snap_boundary = AllocationDecisionSnapshot(
    snapshot_id="s",
    target="X",
    target_allocation_pct=0.0,
    actual_allocation_pct=1.0,
    projected_cash_pct=0.5,
)
_check("3.19 pct=0.0 accepted", snap_boundary.target_allocation_pct == 0.0)
_check("3.20 pct=1.0 accepted", snap_boundary.actual_allocation_pct == 1.0)

try:
    AllocationDecisionSnapshot(snapshot_id="s", target="X", extra_field="bad")
    _fail("3.21 extra fields rejected", "should have raised")
except ValidationError:
    _ok("3.21 extra fields rejected")


# ---------------------------------------------------------------------------
# Section 4: AllocationMemoryLogEntry validation
# ---------------------------------------------------------------------------

_section("4: AllocationMemoryLogEntry validation")

entry1 = AllocationMemoryLogEntry(
    event_id="amlog_001",
    event_type="allocation_recorded",
    created_at="2026-05-26T10:00:00Z",
    description="Test log entry.",
)
_check("4.1 log entry creates OK", entry1.event_id == "amlog_001")
_check("4.2 event_type set", entry1.event_type == "allocation_recorded")
_check("4.3 created_at set", entry1.created_at == "2026-05-26T10:00:00Z")
_check("4.4 actor defaults system", entry1.actor == "system")
_check("4.5 source_ids defaults empty", entry1.source_ids == [])
_check("4.6 evidence_ids defaults empty", entry1.evidence_ids == [])
_check("4.7 metadata defaults empty", entry1.metadata == {})
_check("4.8 warnings defaults empty", entry1.warnings == [])

try:
    AllocationMemoryLogEntry(event_id="", event_type="unknown", created_at="2026-01-01", description="x")
    _fail("4.9 empty event_id rejected", "should have raised")
except ValidationError:
    _ok("4.9 empty event_id rejected")

try:
    AllocationMemoryLogEntry(event_id="x", event_type="unknown", created_at="   ", description="x")
    _fail("4.10 whitespace created_at rejected", "should have raised")
except ValidationError:
    _ok("4.10 whitespace created_at rejected")

try:
    AllocationMemoryLogEntry(event_id="x", event_type="unknown", created_at="2026-01-01", description="   ")
    _fail("4.11 whitespace description rejected", "should have raised")
except ValidationError:
    _ok("4.11 whitespace description rejected")


# ---------------------------------------------------------------------------
# Section 5: AllocationDecisionMemoryRecord validation
# ---------------------------------------------------------------------------

_section("5: AllocationDecisionMemoryRecord validation")

_snap_for_rec = AllocationDecisionSnapshot(snapshot_id="asnap_r1", target="NVDA", risk_level="low")

rec1 = AllocationDecisionMemoryRecord(
    allocation_memory_id="amem_001",
    target="NVDA",
    action="add",
    status="active",
    review_status="not_required",
    outcome="pending",
    decision_snapshot=_snap_for_rec,
    rationale="Strong thesis, initiating position.",
    recorded_at="2026-05-26T10:00:00Z",
)
_check("5.1 record creates OK", rec1.allocation_memory_id == "amem_001")
_check("5.2 target set", rec1.target == "NVDA")
_check("5.3 action set", rec1.action == "add")
_check("5.4 status set", rec1.status == "active")
_check("5.5 review_status set", rec1.review_status == "not_required")
_check("5.6 outcome set", rec1.outcome == "pending")
_check("5.7 rationale set", rec1.rationale == "Strong thesis, initiating position.")
_check("5.8 run_id defaults None", rec1.run_id is None)
_check("5.9 memory_id defaults None", rec1.memory_id is None)
_check("5.10 thesis_id defaults None", rec1.thesis_id is None)
_check("5.11 allocation_report_id defaults None", rec1.allocation_report_id is None)
_check("5.12 trade_plan_report_id defaults None", rec1.trade_plan_report_id is None)
_check("5.13 decision_packet_id defaults None", rec1.decision_packet_id is None)
_check("5.14 forward_return_pct defaults None", rec1.forward_return_pct is None)
_check("5.15 max_drawdown_pct defaults None", rec1.max_drawdown_pct is None)
_check("5.16 lesson defaults None", rec1.lesson is None)
_check("5.17 reviewed_at defaults None", rec1.reviewed_at is None)
_check("5.18 source_refs defaults empty list", rec1.source_refs == [])
_check("5.19 evidence_ids defaults empty list", rec1.evidence_ids == [])
_check("5.20 artifact_refs defaults empty list", rec1.artifact_refs == [])
_check("5.21 event_log defaults empty list", rec1.event_log == [])
_check("5.22 warnings defaults empty list", rec1.warnings == [])
_check("5.23 approved_for_execution always False", rec1.approved_for_execution is False)

# approved_for_execution=True rejected
try:
    AllocationDecisionMemoryRecord(
        allocation_memory_id="amem_001",
        target="NVDA",
        action="add",
        status="active",
        review_status="not_required",
        outcome="pending",
        decision_snapshot=_snap_for_rec,
        rationale="x",
        recorded_at="2026-01-01",
        approved_for_execution=True,
    )
    _fail("5.24 approved_for_execution=True rejected", "should have raised")
except ValidationError:
    _ok("5.24 approved_for_execution=True rejected")

# max_drawdown_pct negative rejected
try:
    AllocationDecisionMemoryRecord(
        allocation_memory_id="amem_001",
        target="NVDA",
        action="hold",
        status="active",
        review_status="not_required",
        outcome="pending",
        decision_snapshot=_snap_for_rec,
        rationale="x",
        recorded_at="2026-01-01",
        max_drawdown_pct=-0.01,
    )
    _fail("5.25 negative max_drawdown_pct rejected", "should have raised")
except ValidationError:
    _ok("5.25 negative max_drawdown_pct rejected")

# forward_return_pct may be signed
rec_signed = AllocationDecisionMemoryRecord(
    allocation_memory_id="amem_signed",
    target="NVDA",
    action="trim",
    status="reviewed",
    review_status="reviewed",
    outcome="negative",
    decision_snapshot=_snap_for_rec,
    rationale="Trimming after loss.",
    recorded_at="2026-01-01",
    forward_return_pct=-0.15,
    max_drawdown_pct=0.20,
)
_check("5.26 negative forward_return_pct accepted", rec_signed.forward_return_pct == -0.15)
_check("5.27 max_drawdown_pct non-negative", rec_signed.max_drawdown_pct == 0.20)

# whitespace checks
try:
    AllocationDecisionMemoryRecord(
        allocation_memory_id="  ",
        target="NVDA",
        action="hold",
        status="active",
        review_status="not_required",
        outcome="pending",
        decision_snapshot=_snap_for_rec,
        rationale="x",
        recorded_at="2026-01-01",
    )
    _fail("5.28 whitespace allocation_memory_id rejected", "should have raised")
except ValidationError:
    _ok("5.28 whitespace allocation_memory_id rejected")

try:
    AllocationDecisionMemoryRecord(
        allocation_memory_id="amem_001",
        target="NVDA",
        action="hold",
        status="active",
        review_status="not_required",
        outcome="pending",
        decision_snapshot=_snap_for_rec,
        rationale="  ",
        recorded_at="2026-01-01",
    )
    _fail("5.29 whitespace rationale rejected", "should have raised")
except ValidationError:
    _ok("5.29 whitespace rationale rejected")


# ---------------------------------------------------------------------------
# Section 6: AllocationMemoryInputBundle validation
# ---------------------------------------------------------------------------

_section("6: AllocationMemoryInputBundle validation")

bundle1 = AllocationMemoryInputBundle(target="NVDA")
_check("6.1 input bundle creates OK", bundle1.target == "NVDA")
_check("6.2 run_id defaults None", bundle1.run_id is None)
_check("6.3 memory_id defaults None", bundle1.memory_id is None)
_check("6.4 thesis_id defaults None", bundle1.thesis_id is None)
_check("6.5 as_of defaults None", bundle1.as_of is None)
_check("6.6 research_run_memory_record defaults None", bundle1.research_run_memory_record is None)
_check("6.7 thesis_memory_report defaults None", bundle1.thesis_memory_report is None)
_check("6.8 allocation_report defaults None", bundle1.allocation_report is None)
_check("6.9 trade_plan_report defaults None", bundle1.trade_plan_report is None)
_check("6.10 decision_packet defaults None", bundle1.decision_packet is None)
_check("6.11 human_review_report defaults None", bundle1.human_review_report is None)
_check("6.12 source_ids defaults empty list", bundle1.source_ids == [])
_check("6.13 evidence_ids defaults empty list", bundle1.evidence_ids == [])
_check("6.14 artifact_refs defaults empty list", bundle1.artifact_refs == [])
_check("6.15 warnings defaults empty list", bundle1.warnings == [])

try:
    AllocationMemoryInputBundle(target="   ")
    _fail("6.16 whitespace target rejected", "should have raised")
except ValidationError:
    _ok("6.16 whitespace target rejected")

try:
    AllocationMemoryInputBundle(target="NVDA", extra_field="bad")
    _fail("6.17 extra fields rejected", "should have raised")
except ValidationError:
    _ok("6.17 extra fields rejected")


# ---------------------------------------------------------------------------
# Section 7: AllocationMemorySummary validation
# ---------------------------------------------------------------------------

_section("7: AllocationMemorySummary validation")

summ1 = AllocationMemorySummary(target="NVDA", status="active")
_check("7.1 summary creates OK", summ1.target == "NVDA")
_check("7.2 status set", summ1.status == "active")
_check("7.3 record_count defaults 0", summ1.record_count == 0)
_check("7.4 action_counts defaults empty dict", summ1.action_counts == {})
_check("7.5 reviewed_count defaults 0", summ1.reviewed_count == 0)
_check("7.6 needs_review_count defaults 0", summ1.needs_review_count == 0)
_check("7.7 blocked_count defaults 0", summ1.blocked_count == 0)
_check("7.8 high_risk_count defaults 0", summ1.high_risk_count == 0)
_check("7.9 pending_outcome_count defaults 0", summ1.pending_outcome_count == 0)
_check("7.10 positive_outcome_count defaults 0", summ1.positive_outcome_count == 0)
_check("7.11 negative_outcome_count defaults 0", summ1.negative_outcome_count == 0)
_check("7.12 avg_forward_return_pct defaults None", summ1.avg_forward_return_pct is None)
_check("7.13 max_drawdown_pct defaults None", summ1.max_drawdown_pct is None)
_check("7.14 top_warnings defaults empty list", summ1.top_warnings == [])
_check("7.15 approved_for_execution always False", summ1.approved_for_execution is False)

try:
    AllocationMemorySummary(target="NVDA", status="active", approved_for_execution=True)
    _fail("7.16 approved_for_execution=True rejected in summary", "should have raised")
except ValidationError:
    _ok("7.16 approved_for_execution=True rejected in summary")


# ---------------------------------------------------------------------------
# Section 8: AllocationMemoryReport validation
# ---------------------------------------------------------------------------

_section("8: AllocationMemoryReport validation")

_summ_for_report = AllocationMemorySummary(target="NVDA", status="unknown")
rpt1 = AllocationMemoryReport(
    report_id="amrep_001",
    target="NVDA",
    status="unknown",
    summary=_summ_for_report,
    created_at="2026-05-26T10:00:00Z",
    updated_at="2026-05-26T10:00:00Z",
)
_check("8.1 report creates OK", rpt1.report_id == "amrep_001")
_check("8.2 target set", rpt1.target == "NVDA")
_check("8.3 status set", rpt1.status == "unknown")
_check("8.4 run_id defaults None", rpt1.run_id is None)
_check("8.5 records defaults empty list", rpt1.records == [])
_check("8.6 source_ids defaults empty list", rpt1.source_ids == [])
_check("8.7 evidence_ids defaults empty list", rpt1.evidence_ids == [])
_check("8.8 artifact_refs defaults empty list", rpt1.artifact_refs == [])
_check("8.9 warnings defaults empty list", rpt1.warnings == [])
_check("8.10 calculation_version set", rpt1.calculation_version == "allocation_memory_v1")
_check("8.11 approved_for_execution always False", rpt1.approved_for_execution is False)

try:
    AllocationMemoryReport(
        report_id="amrep_001",
        target="NVDA",
        status="unknown",
        summary=_summ_for_report,
        created_at="2026-05-26",
        updated_at="2026-05-26",
        approved_for_execution=True,
    )
    _fail("8.12 approved_for_execution=True rejected in report", "should have raised")
except ValidationError:
    _ok("8.12 approved_for_execution=True rejected in report")

try:
    AllocationMemoryReport(
        report_id="  ",
        target="NVDA",
        status="unknown",
        summary=_summ_for_report,
        created_at="2026-05-26",
        updated_at="2026-05-26",
    )
    _fail("8.13 whitespace report_id rejected", "should have raised")
except ValidationError:
    _ok("8.13 whitespace report_id rejected")


# ---------------------------------------------------------------------------
# Section 9: ID generators — deterministic and stable
# ---------------------------------------------------------------------------

_section("9: ID generators — deterministic and stable")

id1 = make_allocation_memory_record_id("NVDA", "add", "2026-05-26")
id2 = make_allocation_memory_record_id("NVDA", "add", "2026-05-26")
_check("9.1 record id is deterministic", id1 == id2)
_check("9.2 record id has amem_ prefix", id1.startswith("amem_"))

id3 = make_allocation_memory_record_id("NVDA", "trim", "2026-05-26")
_check("9.3 different action → different id", id1 != id3)

id4 = make_allocation_memory_record_id("AAPL", "add", "2026-05-26")
_check("9.4 different target → different id", id1 != id4)

id5 = make_allocation_memory_record_id("NVDA", "add", "2026-05-26", run_id="run_001")
id6 = make_allocation_memory_record_id("NVDA", "add", "2026-05-26", run_id="run_001")
_check("9.5 with run_id deterministic", id5 == id6)
_check("9.6 with vs without run_id differ", id1 != id5)

log_id1 = make_allocation_memory_log_entry_id("amem_abc", "allocation_recorded", "2026-05-26")
log_id2 = make_allocation_memory_log_entry_id("amem_abc", "allocation_recorded", "2026-05-26")
_check("9.7 log entry id is deterministic", log_id1 == log_id2)
_check("9.8 log entry id has amlog_ prefix", log_id1.startswith("amlog_"))

log_id3 = make_allocation_memory_log_entry_id("amem_abc", "allocation_review_requested", "2026-05-26")
_check("9.9 different event_type → different log id", log_id1 != log_id3)

rep_id1 = make_allocation_memory_report_id("NVDA", "2026-05-26")
rep_id2 = make_allocation_memory_report_id("NVDA", "2026-05-26")
_check("9.10 report id is deterministic", rep_id1 == rep_id2)
_check("9.11 report id has amrep_ prefix", rep_id1.startswith("amrep_"))

rep_id3 = make_allocation_memory_report_id("AAPL", "2026-05-26")
_check("9.12 different target → different report id", rep_id1 != rep_id3)


# ---------------------------------------------------------------------------
# Section 10: build_allocation_decision_snapshot
# ---------------------------------------------------------------------------

_section("10: build_allocation_decision_snapshot")

snap_a = build_allocation_decision_snapshot(
    target="NVDA",
    target_allocation_pct=0.05,
    actual_allocation_pct=0.03,
    risk_level="medium",
    as_of="2026-05-26",
)
_check("10.1 snapshot builds OK", snap_a.target == "NVDA")
_check("10.2 target_allocation_pct set", snap_a.target_allocation_pct == 0.05)
_check("10.3 risk_level set", snap_a.risk_level == "medium")
_check("10.4 snapshot_id has asnap_ prefix", snap_a.snapshot_id.startswith("asnap_"))

# Deterministic
snap_b = build_allocation_decision_snapshot(
    target="NVDA",
    target_allocation_pct=0.05,
    actual_allocation_pct=0.03,
    risk_level="medium",
    as_of="2026-05-26",
)
_check("10.5 snapshot_id is deterministic", snap_a.snapshot_id == snap_b.snapshot_id)

# Different inputs → different snapshot_id
snap_c = build_allocation_decision_snapshot(
    target="NVDA",
    target_allocation_pct=0.08,
    actual_allocation_pct=0.03,
    risk_level="medium",
    as_of="2026-05-26",
)
_check("10.6 different target_pct → different snapshot_id", snap_a.snapshot_id != snap_c.snapshot_id)

# Source refs deduplication in snapshot
_sr1 = AllocationMemorySourceRef(source_id="src_snap", label="First")
_sr2 = AllocationMemorySourceRef(source_id="src_snap", label="Dup")
_sr3 = AllocationMemorySourceRef(source_id="src_snap2")
snap_dedup = build_allocation_decision_snapshot(
    target="NVDA",
    source_refs=[_sr1, _sr2, _sr3],
)
_check("10.7 source_refs deduped in snapshot", len(snap_dedup.source_refs) == 2)
_check("10.8 first occurrence kept in snapshot", snap_dedup.source_refs[0].label == "First")

# Evidence IDs deduped
snap_eid = build_allocation_decision_snapshot(
    target="NVDA",
    evidence_ids=["e1", "e2", "e1", "e3"],
)
_check("10.9 evidence_ids deduped in snapshot", snap_eid.evidence_ids == ["e1", "e2", "e3"])

# Empty artifact_refs filtered
snap_art = build_allocation_decision_snapshot(
    target="NVDA",
    artifact_refs=["art_001", "", "  ", "art_002"],
)
_check("10.10 empty artifact_refs filtered", snap_art.artifact_refs == ["art_001", "art_002"])

# Input not mutated
_original_refs = [_sr1, _sr2, _sr3]
build_allocation_decision_snapshot(target="NVDA", source_refs=_original_refs)
_check("10.11 input source_refs not mutated", len(_original_refs) == 3)


# ---------------------------------------------------------------------------
# Section 11: build_allocation_memory_log_entry
# ---------------------------------------------------------------------------

_section("11: build_allocation_memory_log_entry")

entry_a = build_allocation_memory_log_entry(
    event_type="allocation_recorded",
    description="Test entry.",
    allocation_memory_id="amem_test",
)
_check("11.1 log entry builds OK", entry_a.event_type == "allocation_recorded")
_check("11.2 description set", entry_a.description == "Test entry.")
_check("11.3 actor defaults system", entry_a.actor == "system")
_check("11.4 created_at defaults deterministic timestamp", entry_a.created_at == "1970-01-01T00:00:00Z")
_check("11.5 event_id has amlog_ prefix", entry_a.event_id.startswith("amlog_"))

# Deterministic
entry_b = build_allocation_memory_log_entry(
    event_type="allocation_recorded",
    description="Test entry.",
    allocation_memory_id="amem_test",
)
_check("11.6 log entry event_id is deterministic", entry_a.event_id == entry_b.event_id)

# With explicit timestamp
entry_c = build_allocation_memory_log_entry(
    event_type="allocation_recorded",
    description="Timestamped entry.",
    allocation_memory_id="amem_test",
    created_at="2026-05-26T10:00:00Z",
)
_check("11.7 explicit created_at honored", entry_c.created_at == "2026-05-26T10:00:00Z")

# Different event_type → different id
entry_d = build_allocation_memory_log_entry(
    event_type="allocation_review_requested",
    description="Review entry.",
    allocation_memory_id="amem_test",
)
_check("11.8 different event_type → different event_id", entry_a.event_id != entry_d.event_id)

# With source_ids and evidence_ids
entry_e = build_allocation_memory_log_entry(
    event_type="outcome_observed",
    description="Outcome tracked.",
    allocation_memory_id="amem_test",
    source_ids=["src_1", "src_2"],
    evidence_ids=["e1", "e2"],
    metadata={"outcome": "positive"},
    actor="user",
)
_check("11.9 source_ids set", entry_e.source_ids == ["src_1", "src_2"])
_check("11.10 evidence_ids set", entry_e.evidence_ids == ["e1", "e2"])
_check("11.11 metadata set", entry_e.metadata.get("outcome") == "positive")
_check("11.12 actor set to user", entry_e.actor == "user")


# ---------------------------------------------------------------------------
# Section 12: determine_allocation_memory_status
# ---------------------------------------------------------------------------

_section("12: determine_allocation_memory_status")

_snap_low = AllocationDecisionSnapshot(snapshot_id="s", target="NVDA", risk_level="low")
_snap_high = AllocationDecisionSnapshot(snapshot_id="s2", target="NVDA", risk_level="high")


def _make_rec(action="hold", status="active", review_status="not_required",
               risk_level="low", outcome="pending"):
    """Helper to create a minimal AllocationDecisionMemoryRecord."""
    snap = AllocationDecisionSnapshot(snapshot_id="s", target="NVDA", risk_level=risk_level)
    return AllocationDecisionMemoryRecord(
        allocation_memory_id=f"amem_{action}_{status}_{risk_level}",
        target="NVDA",
        action=action,
        status=status,
        review_status=review_status,
        outcome=outcome,
        decision_snapshot=snap,
        rationale="Test rationale.",
        recorded_at="2026-05-26",
    )


# No records → unknown
st_empty, _ = determine_allocation_memory_status([])
_check("12.1 no records → unknown", st_empty == "unknown")

# All active → active
rec_active = _make_rec(status="active")
st_active, _ = determine_allocation_memory_status([rec_active])
_check("12.2 active record → active", st_active == "active")

# All reviewed → reviewed
rec_reviewed = _make_rec(status="reviewed", review_status="reviewed")
st_reviewed, _ = determine_allocation_memory_status([rec_reviewed])
_check("12.3 reviewed record → reviewed", st_reviewed == "reviewed")

# needs_review escalates
rec_nr = _make_rec(status="needs_review", review_status="pending")
st_nr, _ = determine_allocation_memory_status([rec_nr])
_check("12.4 needs_review record → needs_review", st_nr == "needs_review")

# blocked > needs_review
rec_blocked = _make_rec(status="blocked", review_status="blocked")
st_blocked, _ = determine_allocation_memory_status([rec_blocked, rec_nr])
_check("12.5 blocked record → blocked (beats needs_review)", st_blocked == "blocked")

# HRR blocked → blocked
_hrr_blocked = types.SimpleNamespace(status="blocked")
_bundle_hrr = AllocationMemoryInputBundle(target="NVDA", human_review_report=_hrr_blocked)
st_hrr, w_hrr = determine_allocation_memory_status([], input_bundle=_bundle_hrr)
_check("12.6 HRR blocked → blocked even with no records", st_hrr == "blocked")

# High-risk unreviewed → needs_review
rec_high_active = _make_rec(status="active", risk_level="high", review_status="not_required")
rec_high_active2 = _make_rec(status="active", risk_level="high", review_status="pending")
st_high, w_high = determine_allocation_memory_status([rec_high_active2])
_check("12.7 high-risk pending review → needs_review", st_high == "needs_review")

# All archived → archived
rec_arch = _make_rec(status="archived")
st_arch, _ = determine_allocation_memory_status([rec_arch])
_check("12.8 all archived → archived", st_arch == "archived")

# Mixed archived + reviewed → reviewed (non-terminal are reviewed)
rec_mix_arch = _make_rec(status="archived")
rec_mix_rev = _make_rec(status="reviewed", review_status="reviewed")
st_mix, _ = determine_allocation_memory_status([rec_mix_arch, rec_mix_rev])
_check("12.9 archived + reviewed → reviewed", st_mix == "reviewed")

# invalidated → unknown (treated as terminal, not active)
rec_inv = _make_rec(status="invalidated")
st_inv, _ = determine_allocation_memory_status([rec_inv])
_check("12.10 only invalidated → unknown", st_inv == "unknown")

# Inputs not mutated
_recs_before = [rec_active]
_len_before = len(_recs_before)
determine_allocation_memory_status(_recs_before)
_check("12.11 input records not mutated", len(_recs_before) == _len_before)


# ---------------------------------------------------------------------------
# Section 13: build_allocation_memory_record — basic
# ---------------------------------------------------------------------------

_section("13: build_allocation_memory_record — basic")

_snap_basic = build_allocation_decision_snapshot(
    target="NVDA",
    target_allocation_pct=0.05,
    actual_allocation_pct=0.02,
    risk_level="medium",
    as_of="2026-05-26",
)

rec_basic = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="Strong earnings trend. Adding to position.",
    decision_snapshot=_snap_basic,
    review_status="not_required",
    outcome="pending",
)
_check("13.1 record builds OK", rec_basic.target == "NVDA")
_check("13.2 action set", rec_basic.action == "add")
_check("13.3 rationale set", rec_basic.rationale == "Strong earnings trend. Adding to position.")
_check("13.4 allocation_memory_id has amem_ prefix", rec_basic.allocation_memory_id.startswith("amem_"))
_check("13.5 approved_for_execution always False", rec_basic.approved_for_execution is False)
_check("13.6 event_log has creation entry", len(rec_basic.event_log) >= 1)
_check("13.7 creation entry is allocation_recorded", rec_basic.event_log[0].event_type == "allocation_recorded")
_check("13.8 recorded_at set to deterministic default", rec_basic.recorded_at == "1970-01-01T00:00:00Z")

# Status logic: not_required + medium risk → active
_check("13.9 medium risk + not_required review → active", rec_basic.status == "active")


# ---------------------------------------------------------------------------
# Section 14: build_allocation_memory_record — status logic
# ---------------------------------------------------------------------------

_section("14: build_allocation_memory_record — status logic")

# High risk + pending review → needs_review
_snap_high2 = build_allocation_decision_snapshot(target="NVDA", risk_level="high")
rec_high_pending = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="High risk add.",
    decision_snapshot=_snap_high2,
    review_status="pending",
)
_check("14.1 high risk + pending → needs_review", rec_high_pending.status == "needs_review")
_check("14.2 review_requested entry added", any(e.event_type == "allocation_review_requested" for e in rec_high_pending.event_log))

# High risk + not_required → needs_review (high risk always needs review unless reviewed)
rec_high_nr = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="High risk hold.",
    decision_snapshot=_snap_high2,
    review_status="not_required",
)
_check("14.3 high risk + not_required → needs_review", rec_high_nr.status == "needs_review")

# High risk + reviewed → reviewed
rec_high_rev = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="High risk reviewed.",
    decision_snapshot=_snap_high2,
    review_status="reviewed",
)
_check("14.4 high risk + reviewed → reviewed", rec_high_rev.status == "reviewed")

# review_status=blocked → blocked
_snap_low2 = build_allocation_decision_snapshot(target="NVDA", risk_level="low")
rec_blk = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="Blocked review.",
    decision_snapshot=_snap_low2,
    review_status="blocked",
)
_check("14.5 review_status=blocked → blocked", rec_blk.status == "blocked")

# HRR blocked → blocked
_hrr = types.SimpleNamespace(status="blocked")
_bundle_hrr2 = AllocationMemoryInputBundle(target="NVDA", human_review_report=_hrr)
rec_hrr_blk = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="HRR blocked.",
    decision_snapshot=_snap_low2,
    review_status="not_required",
    input_bundle=_bundle_hrr2,
)
_check("14.6 HRR blocked → record status blocked", rec_hrr_blk.status == "blocked")

# initial_status override
rec_init = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="Initial status override.",
    decision_snapshot=_snap_high2,
    review_status="pending",
    initial_status="archived",
)
_check("14.7 initial_status=archived overrides auto", rec_init.status == "archived")

# review_status=reviewed + low risk → reviewed
rec_rev_low = build_allocation_memory_record(
    target="NVDA",
    action="trim",
    rationale="Reviewed trim.",
    decision_snapshot=_snap_low2,
    review_status="reviewed",
)
_check("14.8 reviewed + low risk → reviewed", rec_rev_low.status == "reviewed")

# escalated review → needs_review
rec_esc = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="Escalated review.",
    decision_snapshot=_snap_low2,
    review_status="escalated",
)
_check("14.9 escalated review → needs_review", rec_esc.status == "needs_review")


# ---------------------------------------------------------------------------
# Section 15: build_allocation_memory_record — timestamps
# ---------------------------------------------------------------------------

_section("15: build_allocation_memory_record — timestamps")

# Deterministic without explicit ts
rec_ts1 = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="Ts test.",
    decision_snapshot=_snap_basic,
)
rec_ts2 = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="Ts test.",
    decision_snapshot=_snap_basic,
)
_check("15.1 identical inputs → identical record id", rec_ts1.allocation_memory_id == rec_ts2.allocation_memory_id)
_check("15.2 identical inputs → identical recorded_at", rec_ts1.recorded_at == rec_ts2.recorded_at)

# Explicit timestamp override
rec_ts3 = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="Ts test.",
    decision_snapshot=_snap_basic,
    recorded_at="2026-05-26T12:00:00Z",
)
_check("15.3 explicit recorded_at honored", rec_ts3.recorded_at == "2026-05-26T12:00:00Z")

# input_bundle.as_of used when no explicit ts
_bundle_as_of = AllocationMemoryInputBundle(target="NVDA", as_of="2026-05-20T00:00:00Z")
rec_ts4 = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="Bundle as_of test.",
    decision_snapshot=_snap_basic,
    input_bundle=_bundle_as_of,
)
_check("15.4 bundle as_of used when no explicit ts", rec_ts4.recorded_at == "2026-05-20T00:00:00Z")

# Explicit ts beats bundle as_of
rec_ts5 = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="Explicit beats bundle.",
    decision_snapshot=_snap_basic,
    input_bundle=_bundle_as_of,
    recorded_at="2026-06-01T00:00:00Z",
)
_check("15.5 explicit ts beats bundle as_of", rec_ts5.recorded_at == "2026-06-01T00:00:00Z")


# ---------------------------------------------------------------------------
# Section 16: build_allocation_memory_record — deduplication
# ---------------------------------------------------------------------------

_section("16: build_allocation_memory_record — deduplication")

_ref1 = AllocationMemorySourceRef(source_id="src_dup", label="First")
_ref2 = AllocationMemorySourceRef(source_id="src_dup", label="Dup")
_ref3 = AllocationMemorySourceRef(source_id="src_unique")

rec_dedup = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="Dedup test.",
    decision_snapshot=_snap_basic,
    source_refs=[_ref1, _ref2, _ref3],
    evidence_ids=["e1", "e2", "e1", "e3"],
    artifact_refs=["art_1", "", "  ", "art_2", "art_1"],
)
_check("16.1 source_refs deduped by source_id", len(rec_dedup.source_refs) == 2)
_check("16.2 first occurrence kept", rec_dedup.source_refs[0].label == "First")
_check("16.3 evidence_ids deduped", rec_dedup.evidence_ids == ["e1", "e2", "e3"])
_check("16.4 artifact_refs deduped and empty filtered", rec_dedup.artifact_refs == ["art_1", "art_2"])

# Input not mutated
_orig_refs = [_ref1, _ref2, _ref3]
build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="Mutation check.",
    decision_snapshot=_snap_basic,
    source_refs=_orig_refs,
)
_check("16.5 input source_refs list not mutated", len(_orig_refs) == 3)


# ---------------------------------------------------------------------------
# Section 17: build_allocation_memory_record — outcome / lesson / forward return
# ---------------------------------------------------------------------------

_section("17: build_allocation_memory_record — outcome / lesson / forward return")

rec_outcome = build_allocation_memory_record(
    target="NVDA",
    action="trim",
    rationale="Trimming after run-up.",
    decision_snapshot=_snap_basic,
    outcome="positive",
    forward_return_pct=0.25,
    max_drawdown_pct=0.08,
    lesson="Take profits at target rather than waiting for reversal.",
)
_check("17.1 outcome set", rec_outcome.outcome == "positive")
_check("17.2 forward_return_pct set", rec_outcome.forward_return_pct == 0.25)
_check("17.3 max_drawdown_pct set", rec_outcome.max_drawdown_pct == 0.08)
_check("17.4 lesson set", rec_outcome.lesson == "Take profits at target rather than waiting for reversal.")
_check("17.5 outcome_observed entry in event_log", any(e.event_type == "outcome_observed" for e in rec_outcome.event_log))
_check("17.6 lesson_added entry in event_log", any(e.event_type == "lesson_added" for e in rec_outcome.event_log))

# Negative forward return accepted
rec_neg = build_allocation_memory_record(
    target="NVDA",
    action="exit",
    rationale="Stop loss hit.",
    decision_snapshot=_snap_basic,
    outcome="negative",
    forward_return_pct=-0.15,
    max_drawdown_pct=0.20,
)
_check("17.7 negative forward_return_pct accepted", rec_neg.forward_return_pct == -0.15)
_check("17.8 max_drawdown_pct positive accepted", rec_neg.max_drawdown_pct == 0.20)


# ---------------------------------------------------------------------------
# Section 18: build_allocation_memory_record — missing optional upstream artifacts
# ---------------------------------------------------------------------------

_section("18: build_allocation_memory_record — missing optional upstream artifacts")

_bundle_no_arts = AllocationMemoryInputBundle(target="NVDA")
rec_no_arts = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="No upstream artifacts.",
    decision_snapshot=_snap_basic,
    input_bundle=_bundle_no_arts,
)
_check("18.1 missing artifacts produce warnings not crash", len(rec_no_arts.warnings) > 0)
_check("18.2 allocation_report warning present", any("allocation_report" in w for w in rec_no_arts.warnings))
_check("18.3 trade_plan_report warning present", any("trade_plan_report" in w for w in rec_no_arts.warnings))
_check("18.4 decision_packet warning present", any("decision_packet" in w for w in rec_no_arts.warnings))

# With artifacts provided — fewer warnings
_mock_alloc = types.SimpleNamespace(source_ids=["src_alloc"], report_id="arep_001")
_mock_trade = types.SimpleNamespace(source_ids=["src_trade"], report_id="trep_001")
_mock_dp = types.SimpleNamespace(source_ids=["src_dp"], packet_id="dp_001")
_bundle_w_arts = AllocationMemoryInputBundle(
    target="NVDA",
    allocation_report=_mock_alloc,
    trade_plan_report=_mock_trade,
    decision_packet=_mock_dp,
)
rec_w_arts = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="With upstream artifacts.",
    decision_snapshot=_snap_basic,
    input_bundle=_bundle_w_arts,
)
_check("18.5 fewer missing-artifact warnings when provided", len(rec_w_arts.warnings) < len(rec_no_arts.warnings))

# No snapshot provided → auto-generated with warning
rec_no_snap = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="No snapshot provided.",
)
_check("18.6 no snapshot provided → builds without crash", rec_no_snap.allocation_memory_id.startswith("amem_"))
_check("18.7 no snapshot warning issued", any("snapshot" in w.lower() for w in rec_no_snap.warnings))


# ---------------------------------------------------------------------------
# Section 19: build_allocation_memory_record — upstream artifact source_ids collected
# ---------------------------------------------------------------------------

_section("19: build_allocation_memory_record — upstream artifact source_ids")

_mock_rmr = types.SimpleNamespace(source_ids=["sid_mem"], memory_id="mem_001")
_mock_tmr = types.SimpleNamespace(source_ids=["sid_thesis"], report_id="tmr_001")
_bundle_ids = AllocationMemoryInputBundle(
    target="NVDA",
    research_run_memory_record=_mock_rmr,
    thesis_memory_report=_mock_tmr,
    source_ids=["sid_direct"],
)
rec_ids = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="Source ID collection test.",
    decision_snapshot=_snap_basic,
    source_refs=[AllocationMemorySourceRef(source_id="sid_ref")],
    input_bundle=_bundle_ids,
)
all_source_ids = collect_allocation_memory_source_ids(_bundle_ids, [rec_ids])
_check("19.1 direct source_id collected", "sid_direct" in all_source_ids)
_check("19.2 artifact source_id collected", "sid_mem" in all_source_ids)
_check("19.3 artifact report_id as source collected", "tmr_001" in all_source_ids)


# ---------------------------------------------------------------------------
# Section 20: build_allocation_memory_report — basic
# ---------------------------------------------------------------------------

_section("20: build_allocation_memory_report — basic")

_bundle_report = AllocationMemoryInputBundle(target="NVDA")
report_empty = build_allocation_memory_report(_bundle_report)
_check("20.1 empty report builds OK", report_empty.target == "NVDA")
_check("20.2 empty report status is unknown", report_empty.status == "unknown")
_check("20.3 empty report record_count = 0", report_empty.summary.record_count == 0)
_check("20.4 report_id has amrep_ prefix", report_empty.report_id.startswith("amrep_"))
_check("20.5 approved_for_execution always False", report_empty.approved_for_execution is False)
_check("20.6 summary approved_for_execution always False", report_empty.summary.approved_for_execution is False)
_check("20.7 created_at set", report_empty.created_at == "1970-01-01T00:00:00Z")
_check("20.8 calculation_version set", report_empty.calculation_version == "allocation_memory_v1")

# With records
_rec_add = build_allocation_memory_record(
    target="NVDA", action="add", rationale="Buy thesis.", decision_snapshot=_snap_basic,
)
_rec_hold = build_allocation_memory_record(
    target="NVDA", action="hold", rationale="Hold thesis.",
    decision_snapshot=build_allocation_decision_snapshot(target="NVDA", risk_level="low"),
)
report_w_recs = build_allocation_memory_report(
    _bundle_report, records=[_rec_add, _rec_hold]
)
_check("20.9 report with records builds OK", report_w_recs.summary.record_count == 2)
_check("20.10 report status is active", report_w_recs.status == "active")


# ---------------------------------------------------------------------------
# Section 21: build_allocation_memory_report — deterministic timestamps
# ---------------------------------------------------------------------------

_section("21: build_allocation_memory_report — deterministic timestamps")

_bundle_det = AllocationMemoryInputBundle(target="NVDA")
rpt_det1 = build_allocation_memory_report(_bundle_det)
rpt_det2 = build_allocation_memory_report(_bundle_det)
_check("21.1 report_id is deterministic", rpt_det1.report_id == rpt_det2.report_id)
_check("21.2 created_at is deterministic", rpt_det1.created_at == rpt_det2.created_at)

# With as_of
_bundle_as_of2 = AllocationMemoryInputBundle(target="NVDA", as_of="2026-05-26T00:00:00Z")
rpt_as_of = build_allocation_memory_report(_bundle_as_of2)
_check("21.3 bundle as_of used for created_at", rpt_as_of.created_at == "2026-05-26T00:00:00Z")

# Explicit created_at override
rpt_explicit = build_allocation_memory_report(
    _bundle_as_of2, created_at="2026-06-01T00:00:00Z", updated_at="2026-06-01T01:00:00Z"
)
_check("21.4 explicit created_at overrides bundle as_of", rpt_explicit.created_at == "2026-06-01T00:00:00Z")
_check("21.5 explicit updated_at honored", rpt_explicit.updated_at == "2026-06-01T01:00:00Z")

# updated_at defaults to created_at
rpt_upd = build_allocation_memory_report(_bundle_as_of2, created_at="2026-05-26T10:00:00Z")
_check("21.6 updated_at defaults to created_at", rpt_upd.updated_at == "2026-05-26T10:00:00Z")


# ---------------------------------------------------------------------------
# Section 22: build_allocation_memory_report — status propagation
# ---------------------------------------------------------------------------

_section("22: build_allocation_memory_report — status propagation")

_snap_low3 = build_allocation_decision_snapshot(target="NVDA", risk_level="low")
_snap_high3 = build_allocation_decision_snapshot(target="NVDA", risk_level="high")

_rec_reviewed = build_allocation_memory_record(
    target="NVDA", action="hold", rationale="r.",
    decision_snapshot=_snap_low3, review_status="reviewed",
)
_rec_active2 = build_allocation_memory_record(
    target="NVDA", action="add", rationale="r.",
    decision_snapshot=_snap_low3, review_status="not_required",
)
_rec_nr2 = build_allocation_memory_record(
    target="NVDA", action="add", rationale="r.",
    decision_snapshot=_snap_low3, review_status="pending",
)
_rec_blocked2 = build_allocation_memory_record(
    target="NVDA", action="add", rationale="r.",
    decision_snapshot=_snap_low3, review_status="blocked",
)
_rec_high_active = build_allocation_memory_record(
    target="NVDA", action="hold", rationale="r.",
    decision_snapshot=_snap_high3, review_status="not_required",
)

rpt_reviewed = build_allocation_memory_report(AllocationMemoryInputBundle(target="NVDA"), records=[_rec_reviewed])
_check("22.1 all reviewed → report reviewed", rpt_reviewed.status == "reviewed")

rpt_active2 = build_allocation_memory_report(AllocationMemoryInputBundle(target="NVDA"), records=[_rec_active2])
_check("22.2 active records → report active", rpt_active2.status == "active")

rpt_nr2 = build_allocation_memory_report(AllocationMemoryInputBundle(target="NVDA"), records=[_rec_nr2])
_check("22.3 needs_review record → report needs_review", rpt_nr2.status == "needs_review")

rpt_blocked2 = build_allocation_memory_report(
    AllocationMemoryInputBundle(target="NVDA"), records=[_rec_blocked2, _rec_nr2]
)
_check("22.4 blocked record → report blocked (beats needs_review)", rpt_blocked2.status == "blocked")

rpt_high_active = build_allocation_memory_report(
    AllocationMemoryInputBundle(target="NVDA"), records=[_rec_high_active]
)
_check("22.5 high-risk unreviewed → report needs_review", rpt_high_active.status == "needs_review")

_hrr_blocked2 = types.SimpleNamespace(status="blocked")
_bundle_hrr_blocked = AllocationMemoryInputBundle(
    target="NVDA", human_review_report=_hrr_blocked2
)
rpt_hrr_blocked = build_allocation_memory_report(
    _bundle_hrr_blocked, records=[_rec_active2]
)
_check("22.6 HRR blocked → report blocked", rpt_hrr_blocked.status == "blocked")


# ---------------------------------------------------------------------------
# Section 23: summarize_allocation_memory
# ---------------------------------------------------------------------------

_section("23: summarize_allocation_memory")

_snap_med = build_allocation_decision_snapshot(target="NVDA", risk_level="medium")
_snap_hi = build_allocation_decision_snapshot(target="NVDA", risk_level="high")

_r1 = build_allocation_memory_record(
    target="NVDA", action="add", rationale="r.",
    decision_snapshot=_snap_low3, review_status="reviewed", outcome="positive",
    forward_return_pct=0.30, max_drawdown_pct=0.10,
)
_r2 = build_allocation_memory_record(
    target="NVDA", action="trim", rationale="r.",
    decision_snapshot=_snap_med, review_status="reviewed", outcome="neutral",
    forward_return_pct=0.05, max_drawdown_pct=0.05,
)
_r3 = build_allocation_memory_record(
    target="NVDA", action="hold", rationale="r.",
    decision_snapshot=_snap_hi, review_status="pending", outcome="pending",
)

st_summ, w_summ = determine_allocation_memory_status([_r1, _r2, _r3])
summ_test = summarize_allocation_memory("NVDA", st_summ, [_r1, _r2, _r3], w_summ)
_check("23.1 record_count = 3", summ_test.record_count == 3)
_check("23.2 add count = 1", summ_test.action_counts.get("add") == 1)
_check("23.3 trim count = 1", summ_test.action_counts.get("trim") == 1)
_check("23.4 hold count = 1", summ_test.action_counts.get("hold") == 1)
_check("23.5 reviewed_count = 2", summ_test.reviewed_count == 2)
_check("23.6 needs_review_count = 1", summ_test.needs_review_count == 1)
_check("23.7 blocked_count = 0", summ_test.blocked_count == 0)
_check("23.8 high_risk_count = 1", summ_test.high_risk_count == 1)
_check("23.9 pending_outcome_count = 1", summ_test.pending_outcome_count == 1)
_check("23.10 positive_outcome_count = 1", summ_test.positive_outcome_count == 1)
_check("23.11 negative_outcome_count = 0", summ_test.negative_outcome_count == 0)
_check("23.12 avg_forward_return_pct = mean of 0.30 and 0.05", abs(summ_test.avg_forward_return_pct - 0.175) < 1e-9)
_check("23.13 max_drawdown_pct = max of 0.10 and 0.05", abs(summ_test.max_drawdown_pct - 0.10) < 1e-9)
_check("23.14 approved_for_execution always False", summ_test.approved_for_execution is False)

# No forward return records
summ_no_fwd = summarize_allocation_memory("NVDA", "unknown", [], [])
_check("23.15 avg_forward_return_pct None when no records", summ_no_fwd.avg_forward_return_pct is None)
_check("23.16 max_drawdown_pct None when no records", summ_no_fwd.max_drawdown_pct is None)


# ---------------------------------------------------------------------------
# Section 24: collect_allocation_memory_source_ids
# ---------------------------------------------------------------------------

_section("24: collect_allocation_memory_source_ids")

_mock_rmr2 = types.SimpleNamespace(source_ids=["sid_rmr"], memory_id="mem_002")
_bundle_collect = AllocationMemoryInputBundle(
    target="NVDA",
    research_run_memory_record=_mock_rmr2,
    source_ids=["sid_direct"],
)
_rec_with_ref = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="Source collection test.",
    decision_snapshot=_snap_basic,
    source_refs=[AllocationMemorySourceRef(source_id="sid_ref_rec")],
    input_bundle=AllocationMemoryInputBundle(target="NVDA"),
)
sids = collect_allocation_memory_source_ids(_bundle_collect, [_rec_with_ref])
_check("24.1 direct source_id collected", "sid_direct" in sids)
_check("24.2 artifact source_id collected", "sid_rmr" in sids)
_check("24.3 record source_ref id collected", "sid_ref_rec" in sids)
_check("24.4 no duplicates in result", len(sids) == len(set(sids)))

# Deduplication
_bundle_dup_sids = AllocationMemoryInputBundle(
    target="NVDA",
    source_ids=["sid_dup", "sid_dup", "sid_unique"],
)
sids_dedup = collect_allocation_memory_source_ids(_bundle_dup_sids)
_check("24.5 source_ids deduped", sids_dedup.count("sid_dup") == 1)


# ---------------------------------------------------------------------------
# Section 25: collect_allocation_memory_evidence_ids
# ---------------------------------------------------------------------------

_section("25: collect_allocation_memory_evidence_ids")

_bundle_eid = AllocationMemoryInputBundle(
    target="NVDA",
    evidence_ids=["e_direct"],
)
_rec_eid = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="Evidence collection.",
    decision_snapshot=_snap_basic,
    evidence_ids=["e_rec"],
    source_refs=[AllocationMemorySourceRef(source_id="src_eid", evidence_id="e_from_ref")],
    input_bundle=AllocationMemoryInputBundle(target="NVDA"),
)
eids = collect_allocation_memory_evidence_ids(_bundle_eid, [_rec_eid])
_check("25.1 direct evidence_id collected", "e_direct" in eids)
_check("25.2 record evidence_id collected", "e_rec" in eids)
_check("25.3 source_ref evidence_id collected", "e_from_ref" in eids)
_check("25.4 no duplicates", len(eids) == len(set(eids)))


# ---------------------------------------------------------------------------
# Section 26: collect_allocation_memory_artifact_refs
# ---------------------------------------------------------------------------

_section("26: collect_allocation_memory_artifact_refs")

_bundle_art = AllocationMemoryInputBundle(
    target="NVDA",
    artifact_refs=["art_direct"],
)
_rec_art = build_allocation_memory_record(
    target="NVDA",
    action="hold",
    rationale="Artifact refs test.",
    decision_snapshot=_snap_basic,
    artifact_refs=["art_rec"],
    input_bundle=AllocationMemoryInputBundle(target="NVDA"),
)
arts = collect_allocation_memory_artifact_refs(_bundle_art, [_rec_art])
_check("26.1 direct artifact_ref collected", "art_direct" in arts)
_check("26.2 record artifact_ref collected", "art_rec" in arts)
_check("26.3 no duplicates", len(arts) == len(set(arts)))

# Empty/whitespace refs filtered
_bundle_empty_art = AllocationMemoryInputBundle(
    target="NVDA",
    artifact_refs=["art_ok", "", "  "],
)
arts_filtered = collect_allocation_memory_artifact_refs(_bundle_empty_art)
_check("26.4 empty artifact refs filtered", arts_filtered == ["art_ok"])


# ---------------------------------------------------------------------------
# Section 27: ToolResult adapter
# ---------------------------------------------------------------------------

_section("27: ToolResult adapter")

_bundle_tr = AllocationMemoryInputBundle(target="NVDA", as_of="2026-05-26")
_rec_tr = build_allocation_memory_record(
    target="NVDA",
    action="add",
    rationale="ToolResult test.",
    decision_snapshot=build_allocation_decision_snapshot(
        target="NVDA",
        target_allocation_pct=0.05,
        risk_level="medium",
        as_of="2026-05-26",
    ),
    review_status="reviewed",
    outcome="positive",
    forward_return_pct=0.15,
    input_bundle=_bundle_tr,
)
report_tr = build_allocation_memory_report(_bundle_tr, records=[_rec_tr])
tr = allocation_memory_tool_result_from_report(report_tr)

_check("27.1 ToolResult builds OK", tr is not None)
_check("27.2 tool_name is allocation_memory_report", tr.tool_name == "allocation_memory_report")
_check("27.3 ticker set to target", tr.ticker == "NVDA")
_check("27.4 evidence_id is non-empty", bool(tr.evidence_id))
_check("27.5 outputs.report_id present", "report_id" in tr.outputs)
_check("27.6 outputs.summary present", "summary" in tr.outputs)
_check("27.7 outputs.calculation_version present", tr.outputs.get("calculation_version") == "allocation_memory_v1")
_check("27.8 outputs.record_count correct", tr.outputs.get("record_count") == 1)
_check("27.9 outputs.reviewed_count correct", tr.outputs.get("reviewed_count") == 1)
_check("27.10 outputs.approved_for_execution False", tr.outputs.get("approved_for_execution") is False)
_check("27.11 outputs.report is full report dict", isinstance(tr.outputs.get("report"), dict))

# evidence_id changes when content changes
_rec_tr2 = build_allocation_memory_record(
    target="NVDA",
    action="trim",
    rationale="Different decision.",
    decision_snapshot=build_allocation_decision_snapshot(
        target="NVDA",
        target_allocation_pct=0.03,
        risk_level="low",
        as_of="2026-05-26",
    ),
    input_bundle=_bundle_tr,
)
report_tr2 = build_allocation_memory_report(_bundle_tr, records=[_rec_tr2])
tr2 = allocation_memory_tool_result_from_report(report_tr2)
_check("27.12 evidence_id changes when content changes", tr.evidence_id != tr2.evidence_id)

# Deterministic evidence_id
tr3 = allocation_memory_tool_result_from_report(report_tr)
_check("27.13 evidence_id is deterministic", tr.evidence_id == tr3.evidence_id)

# With explicit run_id
tr_run = allocation_memory_tool_result_from_report(report_tr, run_id="explicit_run_001")
_check("27.14 explicit run_id used", tr_run.run_id == "explicit_run_001")


# ---------------------------------------------------------------------------
# Section 28: __all__ exports include Phase 4M-D public symbols
# ---------------------------------------------------------------------------

_section("28: __all__ exports")

from lib.reliability.allocation_memory import __all__ as _alloc_mem_all
from lib.reliability import __all__ as _pkg_all

_expected_module_symbols = [
    "AllocationDecisionAction",
    "AllocationDecisionMemoryRecord",
    "AllocationDecisionOutcome",
    "AllocationDecisionReviewStatus",
    "AllocationDecisionSnapshot",
    "AllocationMemoryActorType",
    "AllocationMemoryEventType",
    "AllocationMemoryInputBundle",
    "AllocationMemoryLogEntry",
    "AllocationMemoryReport",
    "AllocationMemoryRiskLevel",
    "AllocationMemorySourceRef",
    "AllocationMemoryStatus",
    "AllocationMemorySummary",
    "allocation_memory_tool_result_from_report",
    "build_allocation_decision_snapshot",
    "build_allocation_memory_log_entry",
    "build_allocation_memory_record",
    "build_allocation_memory_report",
    "collect_allocation_memory_artifact_refs",
    "collect_allocation_memory_evidence_ids",
    "collect_allocation_memory_source_ids",
    "determine_allocation_memory_status",
    "make_allocation_memory_log_entry_id",
    "make_allocation_memory_record_id",
    "make_allocation_memory_report_id",
    "summarize_allocation_memory",
]

for _sym in _expected_module_symbols:
    _check(f"28.module {_sym} in allocation_memory.__all__", _sym in _alloc_mem_all)

for _sym in _expected_module_symbols:
    _check(f"28.pkg {_sym} in reliability.__all__", _sym in _pkg_all)


# ---------------------------------------------------------------------------
# Section 29: no Streamlit / Claude API / external API / brokerage / DB dependency
# ---------------------------------------------------------------------------

_section("29: forbidden dependency checks")

_forbidden_live = [
    "streamlit",
    "anthropic",
    "requests",
    "httpx",
    "sqlalchemy",
    "psycopg2",
    "pymongo",
    "redis",
    "chromadb",
    "pinecone",
    "weaviate",
    "alpaca_trade_api",
    "ib_insync",
    "robin_stocks",
    "finnhub",
]
for _mod in _forbidden_live:
    _check(f"29.x {_mod} not in sys.modules", _mod not in sys.modules)

# Verify allocation_memory module does not import live modules
import lib.reliability.allocation_memory as _am_module
_am_src = open(_am_module.__file__).read()
_check("29.y no 'import streamlit' in allocation_memory", "import streamlit" not in _am_src)
_check("29.z no 'import anthropic' in allocation_memory", "import anthropic" not in _am_src)
_check("29.aa no 'import alpaca' in allocation_memory", "import alpaca" not in _am_src)
_check("29.ab no broker/order/execution in allocation_memory", "execution_id" not in _am_src)
_check("29.ac no brokerage API calls in allocation_memory", "brokerage_api" not in _am_src and "brokerage.connect" not in _am_src)


# ---------------------------------------------------------------------------
# Section 30: full end-to-end round-trip
# ---------------------------------------------------------------------------

_section("30: end-to-end round-trip")

_bundle_e2e = AllocationMemoryInputBundle(
    target="MSFT",
    run_id="run_msft_20260526",
    as_of="2026-05-26T09:30:00Z",
    source_ids=["sid_msft_research"],
    evidence_ids=["eid_msft_valuation"],
)

_snap_e2e_add = build_allocation_decision_snapshot(
    target="MSFT",
    target_allocation_pct=0.07,
    actual_allocation_pct=0.04,
    cash_pct=0.20,
    required_trade_value=15000.0,
    required_shares=40.0,
    cash_impact=-15000.0,
    projected_cash_pct=0.17,
    risk_budget_pct=0.01,
    risk_level="medium",
    as_of="2026-05-26T09:30:00Z",
)

_rec_e2e_add = build_allocation_memory_record(
    target="MSFT",
    action="add",
    rationale="MSFT cloud segment accelerating. Adding to 7% position.",
    decision_snapshot=_snap_e2e_add,
    review_status="reviewed",
    outcome="positive",
    forward_return_pct=0.18,
    max_drawdown_pct=0.07,
    lesson="Adding on fundamental conviction works well in trending markets.",
    allocation_report_id="arep_msft_001",
    trade_plan_report_id="trep_msft_001",
    decision_packet_id="dp_msft_001",
    input_bundle=_bundle_e2e,
)

_snap_e2e_hold = build_allocation_decision_snapshot(
    target="MSFT",
    target_allocation_pct=0.07,
    actual_allocation_pct=0.07,
    risk_level="low",
    as_of="2026-05-26T09:30:00Z",
)

_rec_e2e_hold = build_allocation_memory_record(
    target="MSFT",
    action="hold",
    rationale="Position at target. No action needed.",
    decision_snapshot=_snap_e2e_hold,
    review_status="not_required",
    outcome="pending",
    input_bundle=_bundle_e2e,
)

report_e2e = build_allocation_memory_report(
    _bundle_e2e,
    records=[_rec_e2e_add, _rec_e2e_hold],
)
_check("30.1 e2e report builds OK", report_e2e.target == "MSFT")
_check("30.2 e2e record_count = 2", report_e2e.summary.record_count == 2)
_check("30.3 e2e reviewed_count = 1", report_e2e.summary.reviewed_count == 1)
_check("30.4 e2e status is active (mix of reviewed + active)", report_e2e.status == "active")
_check("30.5 e2e avg_forward_return_pct = 0.18", abs(report_e2e.summary.avg_forward_return_pct - 0.18) < 1e-9)
_check("30.6 e2e max_drawdown_pct = 0.07", abs(report_e2e.summary.max_drawdown_pct - 0.07) < 1e-9)
_check("30.7 e2e positive_outcome_count = 1", report_e2e.summary.positive_outcome_count == 1)
_check("30.8 e2e pending_outcome_count = 1", report_e2e.summary.pending_outcome_count == 1)
_check("30.9 e2e add action counted", report_e2e.summary.action_counts.get("add") == 1)
_check("30.10 e2e hold action counted", report_e2e.summary.action_counts.get("hold") == 1)
_check("30.11 e2e approved_for_execution False", report_e2e.approved_for_execution is False)

tr_e2e = allocation_memory_tool_result_from_report(report_e2e)
_check("30.12 e2e ToolResult builds OK", tr_e2e.tool_name == "allocation_memory_report")
_check("30.13 e2e ToolResult evidence_id non-empty", bool(tr_e2e.evidence_id))
_check("30.14 e2e ToolResult record_count = 2", tr_e2e.outputs.get("record_count") == 2)
_check("30.15 e2e ToolResult approved_for_execution False", tr_e2e.outputs.get("approved_for_execution") is False)

# Round-trip: report dict matches model
_report_dict = report_e2e.model_dump()
_check("30.16 model_dump target matches", _report_dict["target"] == "MSFT")
_check("30.17 model_dump approved_for_execution False", _report_dict["approved_for_execution"] is False)


# ---------------------------------------------------------------------------
# Section 31: allocation_memory_id collision fix — Codex-required tests A, B, C
# ---------------------------------------------------------------------------

_section("31: allocation_memory_id collision fix (Codex-required A, B, C)")

_TARGET_31 = "GOOGL"
_ACTION_31: AllocationDecisionAction = "add"
_AS_OF_31 = "2026-05-26T00:00:00Z"
_RUN_ID_31 = "run_codex_fix_test"
_RATIONALE_31 = "Same rationale text for both records."

# --- Test A: distinct snapshots → distinct allocation_memory_id and event_id ---

_snap_31a = build_allocation_decision_snapshot(
    target=_TARGET_31,
    target_allocation_pct=0.05,
    actual_allocation_pct=0.02,
    risk_level="medium",
    as_of=_AS_OF_31,
)
_snap_31b = build_allocation_decision_snapshot(
    target=_TARGET_31,
    target_allocation_pct=0.08,  # different allocation pct
    actual_allocation_pct=0.05,  # different actual pct
    risk_level="high",            # different risk level
    as_of=_AS_OF_31,
)

# Pre-condition: the two snapshots must have different snapshot_ids
_check("31.A.pre snapshot_ids differ (pre-condition)", _snap_31a.snapshot_id != _snap_31b.snapshot_id)

_rec_31a = build_allocation_memory_record(
    target=_TARGET_31,
    action=_ACTION_31,
    rationale=_RATIONALE_31,
    decision_snapshot=_snap_31a,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_31,
    recorded_at=_AS_OF_31,
)
_rec_31b = build_allocation_memory_record(
    target=_TARGET_31,
    action=_ACTION_31,
    rationale=_RATIONALE_31,
    decision_snapshot=_snap_31b,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_31,
    recorded_at=_AS_OF_31,
)

_check(
    "31.A.1 distinct snapshots → distinct allocation_memory_id",
    _rec_31a.allocation_memory_id != _rec_31b.allocation_memory_id,
)
_check(
    "31.A.2 distinct snapshots → distinct event_log[0].event_id",
    _rec_31a.event_log[0].event_id != _rec_31b.event_log[0].event_id,
)

# --- Test B: identical inputs → stable IDs ---

_rec_31c1 = build_allocation_memory_record(
    target=_TARGET_31,
    action=_ACTION_31,
    rationale=_RATIONALE_31,
    decision_snapshot=_snap_31a,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_31,
    recorded_at=_AS_OF_31,
)
_rec_31c2 = build_allocation_memory_record(
    target=_TARGET_31,
    action=_ACTION_31,
    rationale=_RATIONALE_31,
    decision_snapshot=_snap_31a,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_31,
    recorded_at=_AS_OF_31,
)

_check(
    "31.B.1 identical inputs → stable allocation_memory_id",
    _rec_31c1.allocation_memory_id == _rec_31c2.allocation_memory_id,
)
_check(
    "31.B.2 identical inputs → stable event_id",
    _rec_31c1.event_log[0].event_id == _rec_31c2.event_log[0].event_id,
)

# --- Test C: ToolResult evidence_id behavior ---

_bundle_31c = AllocationMemoryInputBundle(
    target=_TARGET_31, run_id=_RUN_ID_31, as_of=_AS_OF_31
)

_rpt_31_stable_1 = build_allocation_memory_report(_bundle_31c, records=[_rec_31c1])
_rpt_31_stable_2 = build_allocation_memory_report(_bundle_31c, records=[_rec_31c2])
_tr_31_stable_1 = allocation_memory_tool_result_from_report(_rpt_31_stable_1)
_tr_31_stable_2 = allocation_memory_tool_result_from_report(_rpt_31_stable_2)
_check(
    "31.C.1 identical report content → same evidence_id",
    _tr_31_stable_1.evidence_id == _tr_31_stable_2.evidence_id,
)

_rpt_31_diff = build_allocation_memory_report(_bundle_31c, records=[_rec_31b])
_tr_31_diff = allocation_memory_tool_result_from_report(_rpt_31_diff)
_check(
    "31.C.2 different allocation content → different evidence_id",
    _tr_31_stable_1.evidence_id != _tr_31_diff.evidence_id,
)
_check(
    "31.C.3 distinct record IDs preserved through report into ToolResult",
    _rpt_31_stable_1.records[0].allocation_memory_id
    != _rpt_31_diff.records[0].allocation_memory_id,
)

# Also verify rationale alone is sufficient to distinguish records with
# identical snapshot content
_rec_31_rat1 = build_allocation_memory_record(
    target=_TARGET_31,
    action=_ACTION_31,
    rationale="Rationale version A.",
    decision_snapshot=_snap_31a,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_31,
    recorded_at=_AS_OF_31,
)
_rec_31_rat2 = build_allocation_memory_record(
    target=_TARGET_31,
    action=_ACTION_31,
    rationale="Rationale version B.",
    decision_snapshot=_snap_31a,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_31,
    recorded_at=_AS_OF_31,
)
_check(
    "31.C.4 different rationale → different allocation_memory_id",
    _rec_31_rat1.allocation_memory_id != _rec_31_rat2.allocation_memory_id,
)


# ---------------------------------------------------------------------------
# Section 32: Phase 4M-D minor test polish — review_status-only and
#             outcome-only ID sensitivity (Codex-suggested additions)
# ---------------------------------------------------------------------------

_section("32: review_status-only and outcome-only ID sensitivity (Phase 4M-D minor polish)")

_TARGET_32 = "AMZN"
_ACTION_32: AllocationDecisionAction = "hold"
_AS_OF_32 = "2026-05-26T12:00:00Z"
_RUN_ID_32 = "run_minor_polish_test"
_RATIONALE_32 = "Base rationale for review_status/outcome sensitivity tests."

# Build a shared snapshot so snapshot_id is identical across all records.
_snap_32 = build_allocation_decision_snapshot(
    target=_TARGET_32,
    target_allocation_pct=0.06,
    actual_allocation_pct=0.06,
    risk_level="medium",
    as_of=_AS_OF_32,
)

# ---------- Test A: review_status-only change alters allocation_memory_id ----------

_rec_32_rs_nr = build_allocation_memory_record(
    target=_TARGET_32,
    action=_ACTION_32,
    rationale=_RATIONALE_32,
    decision_snapshot=_snap_32,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_32,
    recorded_at=_AS_OF_32,
)
_rec_32_rs_reviewed = build_allocation_memory_record(
    target=_TARGET_32,
    action=_ACTION_32,
    rationale=_RATIONALE_32,
    decision_snapshot=_snap_32,
    review_status="reviewed",      # only this differs
    outcome="pending",
    run_id=_RUN_ID_32,
    recorded_at=_AS_OF_32,
)
_check(
    "32.A.1 review_status-only change → different allocation_memory_id",
    _rec_32_rs_nr.allocation_memory_id != _rec_32_rs_reviewed.allocation_memory_id,
)
_check(
    "32.A.2 review_status-only change → different event_log[0].event_id",
    _rec_32_rs_nr.event_log[0].event_id != _rec_32_rs_reviewed.event_log[0].event_id,
)

# Stable: same review_status twice → same ID
_rec_32_rs_nr2 = build_allocation_memory_record(
    target=_TARGET_32,
    action=_ACTION_32,
    rationale=_RATIONALE_32,
    decision_snapshot=_snap_32,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_32,
    recorded_at=_AS_OF_32,
)
_check(
    "32.A.3 identical review_status → stable allocation_memory_id",
    _rec_32_rs_nr.allocation_memory_id == _rec_32_rs_nr2.allocation_memory_id,
)

# ---------- Test B: outcome-only change alters allocation_memory_id ----------

_rec_32_oc_pending = build_allocation_memory_record(
    target=_TARGET_32,
    action=_ACTION_32,
    rationale=_RATIONALE_32,
    decision_snapshot=_snap_32,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_32,
    recorded_at=_AS_OF_32,
)
_rec_32_oc_positive = build_allocation_memory_record(
    target=_TARGET_32,
    action=_ACTION_32,
    rationale=_RATIONALE_32,
    decision_snapshot=_snap_32,
    review_status="not_required",
    outcome="positive",            # only this differs
    run_id=_RUN_ID_32,
    recorded_at=_AS_OF_32,
)
_check(
    "32.B.1 outcome-only change → different allocation_memory_id",
    _rec_32_oc_pending.allocation_memory_id != _rec_32_oc_positive.allocation_memory_id,
)
_check(
    "32.B.2 outcome-only change → different event_log[0].event_id",
    _rec_32_oc_pending.event_log[0].event_id != _rec_32_oc_positive.event_log[0].event_id,
)

# Stable: same outcome twice → same ID
_rec_32_oc_pending2 = build_allocation_memory_record(
    target=_TARGET_32,
    action=_ACTION_32,
    rationale=_RATIONALE_32,
    decision_snapshot=_snap_32,
    review_status="not_required",
    outcome="pending",
    run_id=_RUN_ID_32,
    recorded_at=_AS_OF_32,
)
_check(
    "32.B.3 identical outcome → stable allocation_memory_id",
    _rec_32_oc_pending.allocation_memory_id == _rec_32_oc_pending2.allocation_memory_id,
)

# ---------- Test C: simultaneous review_status + outcome change ----------

_rec_32_combined = build_allocation_memory_record(
    target=_TARGET_32,
    action=_ACTION_32,
    rationale=_RATIONALE_32,
    decision_snapshot=_snap_32,
    review_status="reviewed",      # both differ from _rec_32_oc_pending
    outcome="positive",
    run_id=_RUN_ID_32,
    recorded_at=_AS_OF_32,
)
_check(
    "32.C.1 review_status+outcome change → different allocation_memory_id vs pending/not_required",
    _rec_32_oc_pending.allocation_memory_id != _rec_32_combined.allocation_memory_id,
)
_check(
    "32.C.2 review_status+outcome change → different allocation_memory_id vs reviewed/pending",
    _rec_32_rs_reviewed.allocation_memory_id != _rec_32_combined.allocation_memory_id,
)
_check(
    "32.C.3 all four variants produce distinct IDs",
    len({
        _rec_32_rs_nr.allocation_memory_id,
        _rec_32_rs_reviewed.allocation_memory_id,
        _rec_32_oc_positive.allocation_memory_id,
        _rec_32_combined.allocation_memory_id,
    }) == 4,
)


# ---------------------------------------------------------------------------
# Section 33: Phase 4M-D minor suggestion — isolated allocation_memory_id sensitivity
#
# Six labeled checks (A.1–A.6) explicitly using both make_allocation_memory_record_id()
# directly AND build_allocation_memory_record() to satisfy the Codex-suggested test
# coverage for review_status-only and outcome-only sensitivity.
# Section 32 covers the builder path comprehensively; this section adds the
# direct-function path (A.1, A.3, A.5) which Section 32 omitted.
# ---------------------------------------------------------------------------

_section("33: Phase 4M-D minor suggestion — isolated allocation_memory_id sensitivity (A.1–A.6)")

_T33 = "NVDA"
_AC33 = "add"
_AO33 = "2026-05-26T00:00:00Z"
_RUN33 = "run_minor_isolated"
_RAT33 = "Base rationale for isolated sensitivity tests."
_SNAP33_ID = "asnap_isolated_001"  # fixed snapshot_id so make_*() behaves identically

# A.1 — identical inputs → stable make_allocation_memory_record_id (direct call)
_id33_a1 = make_allocation_memory_record_id(
    _T33, _AC33, _AO33,
    run_id=_RUN33, snapshot_id=_SNAP33_ID,
    rationale=_RAT33, review_status="not_required", outcome="pending",
)
_id33_a1b = make_allocation_memory_record_id(
    _T33, _AC33, _AO33,
    run_id=_RUN33, snapshot_id=_SNAP33_ID,
    rationale=_RAT33, review_status="not_required", outcome="pending",
)
_check("A.1 identical inputs → stable make_allocation_memory_record_id", _id33_a1 == _id33_a1b)

# A.2 — identical inputs → stable allocation_memory_id via builder
_snap33 = build_allocation_decision_snapshot(
    target=_T33, target_allocation_pct=0.05, risk_level="low", as_of=_AO33,
)
_rec33_base1 = build_allocation_memory_record(
    target=_T33, action=_AC33, rationale=_RAT33,
    decision_snapshot=_snap33, review_status="not_required", outcome="pending",
    run_id=_RUN33, recorded_at=_AO33,
)
_rec33_base2 = build_allocation_memory_record(
    target=_T33, action=_AC33, rationale=_RAT33,
    decision_snapshot=_snap33, review_status="not_required", outcome="pending",
    run_id=_RUN33, recorded_at=_AO33,
)
_check("A.2 identical inputs → stable allocation_memory_id via builder",
       _rec33_base1.allocation_memory_id == _rec33_base2.allocation_memory_id)

# A.3 — review_status-only change → different make_allocation_memory_record_id (direct call)
_id33_rs_nr = make_allocation_memory_record_id(
    _T33, _AC33, _AO33,
    run_id=_RUN33, snapshot_id=_SNAP33_ID,
    rationale=_RAT33, review_status="not_required", outcome="pending",
)
_id33_rs_rev = make_allocation_memory_record_id(
    _T33, _AC33, _AO33,
    run_id=_RUN33, snapshot_id=_SNAP33_ID,
    rationale=_RAT33, review_status="reviewed", outcome="pending",  # only review_status differs
)
_check("A.3 review_status change → different make_allocation_memory_record_id", _id33_rs_nr != _id33_rs_rev)

# A.4 — review_status-only change → different allocation_memory_id via builder
_rec33_rs_nr = build_allocation_memory_record(
    target=_T33, action=_AC33, rationale=_RAT33,
    decision_snapshot=_snap33, review_status="not_required", outcome="pending",
    run_id=_RUN33, recorded_at=_AO33,
)
_rec33_rs_reviewed = build_allocation_memory_record(
    target=_T33, action=_AC33, rationale=_RAT33,
    decision_snapshot=_snap33, review_status="reviewed", outcome="pending",  # only review_status differs
    run_id=_RUN33, recorded_at=_AO33,
)
_check("A.4 review_status change → different allocation_memory_id via builder",
       _rec33_rs_nr.allocation_memory_id != _rec33_rs_reviewed.allocation_memory_id)

# A.5 — outcome-only change → different make_allocation_memory_record_id (direct call)
_id33_oc_pending = make_allocation_memory_record_id(
    _T33, _AC33, _AO33,
    run_id=_RUN33, snapshot_id=_SNAP33_ID,
    rationale=_RAT33, review_status="not_required", outcome="pending",
)
_id33_oc_positive = make_allocation_memory_record_id(
    _T33, _AC33, _AO33,
    run_id=_RUN33, snapshot_id=_SNAP33_ID,
    rationale=_RAT33, review_status="not_required", outcome="positive",  # only outcome differs
)
_check("A.5 outcome change → different make_allocation_memory_record_id", _id33_oc_pending != _id33_oc_positive)

# A.6 — outcome-only change → different allocation_memory_id via builder
_rec33_oc_pending = build_allocation_memory_record(
    target=_T33, action=_AC33, rationale=_RAT33,
    decision_snapshot=_snap33, review_status="not_required", outcome="pending",
    run_id=_RUN33, recorded_at=_AO33,
)
_rec33_oc_positive = build_allocation_memory_record(
    target=_T33, action=_AC33, rationale=_RAT33,
    decision_snapshot=_snap33, review_status="not_required", outcome="positive",  # only outcome differs
    run_id=_RUN33, recorded_at=_AO33,
)
_check("A.6 outcome change → different allocation_memory_id via builder",
       _rec33_oc_pending.allocation_memory_id != _rec33_oc_positive.allocation_memory_id)


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"Phase 4M-D Allocation Memory Tests: {_test_count} total, {_fail_count} failed")
if _fail_count == 0:
    print("ALL TESTS PASSED")
else:
    print(f"FAILURES: {_fail_count}")
print('='*60)

sys.exit(0 if _fail_count == 0 else 1)
