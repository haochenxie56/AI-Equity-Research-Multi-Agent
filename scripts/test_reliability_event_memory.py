"""
scripts/test_reliability_event_memory.py

Phase 4M-C: Catalyst / News / Earnings Memory — test suite.

Run: python3 scripts/test_reliability_event_memory.py

All tests are offline/mock-only. No network, DB, vector store, file writes,
Claude API calls, Streamlit, Finnhub, earnings API, or broker/order/execution
dependencies.
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

from lib.reliability.event_memory import (
    EventMemoryActorType,
    EventMemoryEventType,
    EventMemoryImpactDirection,
    EventMemoryImpactMagnitude,
    EventMemoryInputBundle,
    EventMemoryLogEntry,
    EventMemoryRecord,
    EventMemoryReport,
    EventMemoryReviewStatus,
    EventMemorySourceRef,
    EventMemorySourceType,
    EventMemoryStatus,
    EventMemorySummary,
    EventMemoryType,
    build_event_memory_log_entry,
    build_event_memory_record,
    build_event_memory_report,
    collect_event_memory_artifact_refs,
    collect_event_memory_evidence_ids,
    collect_event_memory_source_ids,
    determine_event_memory_status,
    event_memory_tool_result_from_report,
    make_event_memory_log_entry_id,
    make_event_memory_record_id,
    make_event_memory_report_id,
    summarize_event_memory,
)
from lib.reliability.schemas import ToolResult


# ---------------------------------------------------------------------------
# Section 0: forbidden imports guard
# ---------------------------------------------------------------------------

_section("0: forbidden imports guard")

for _mod in _forbidden_modules:
    _check(
        f"forbidden module '{_mod}' not imported",
        _mod not in sys.modules,
        f"'{_mod}' found in sys.modules",
    )


# ---------------------------------------------------------------------------
# Section 1: EventMemorySourceRef validation
# ---------------------------------------------------------------------------

_section("1: EventMemorySourceRef validation")

ref1 = EventMemorySourceRef(source_id="src_001", source_type="news", label="Reuters")
_check("1.1 EventMemorySourceRef creates with required fields", ref1.source_id == "src_001")
_check("1.2 source_type default", ref1.source_type == "news")
_check("1.3 label round-trips", ref1.label == "Reuters")
_check("1.4 metadata defaults to dict", isinstance(ref1.metadata, dict))
_check("1.5 warnings defaults to list", isinstance(ref1.warnings, list))
_check("1.6 optional fields default to None", ref1.artifact_id is None)
_check("1.7 url defaults to None", ref1.url is None)
_check("1.8 published_at defaults to None", ref1.published_at is None)
_check("1.9 evidence_id defaults to None", ref1.evidence_id is None)
_check("1.10 field_path defaults to None", ref1.field_path is None)

ref2 = EventMemorySourceRef(
    source_id="src_002",
    source_type="earnings_report",
    artifact_id="art_001",
    evidence_id="ev_001",
    url="https://example.com/report",
    published_at="2026-01-15",
    field_path="reports[0].eps",
    label="Q4 Earnings",
    metadata={"quarter": "Q4"},
    warnings=["preliminary"],
)
_check("1.11 full EventMemorySourceRef round-trips", ref2.published_at == "2026-01-15")
_check("1.12 full EventMemorySourceRef artifact_id", ref2.artifact_id == "art_001")

try:
    EventMemorySourceRef(source_id="   ")
    _fail("1.13 whitespace-only source_id rejected", "should have raised")
except ValidationError:
    _ok("1.13 whitespace-only source_id rejected")

try:
    EventMemorySourceRef(source_id="")
    _fail("1.14 empty source_id rejected", "should have raised")
except ValidationError:
    _ok("1.14 empty source_id rejected")


# ---------------------------------------------------------------------------
# Section 2: EventMemoryLogEntry validation
# ---------------------------------------------------------------------------

_section("2: EventMemoryLogEntry validation")

entry1 = EventMemoryLogEntry(
    event_id="entry_001",
    event_type="event_recorded",
    created_at="2026-01-15T10:00:00Z",
    actor="system",
    description="Event recorded for NVDA.",
)
_check("2.1 EventMemoryLogEntry creates OK", entry1.event_id == "entry_001")
_check("2.2 event_type round-trips", entry1.event_type == "event_recorded")
_check("2.3 actor round-trips", entry1.actor == "system")
_check("2.4 source_ids defaults to list", isinstance(entry1.source_ids, list))
_check("2.5 evidence_ids defaults to list", isinstance(entry1.evidence_ids, list))
_check("2.6 metadata defaults to dict", isinstance(entry1.metadata, dict))
_check("2.7 warnings defaults to list", isinstance(entry1.warnings, list))

try:
    EventMemoryLogEntry(
        event_id="   ", event_type="event_recorded",
        created_at="2026-01-15T10:00:00Z", actor="system",
        description="test",
    )
    _fail("2.8 whitespace event_id rejected", "should have raised")
except ValidationError:
    _ok("2.8 whitespace event_id rejected")

try:
    EventMemoryLogEntry(
        event_id="e1", event_type="event_recorded",
        created_at="   ", actor="system",
        description="test",
    )
    _fail("2.9 whitespace created_at rejected", "should have raised")
except ValidationError:
    _ok("2.9 whitespace created_at rejected")

try:
    EventMemoryLogEntry(
        event_id="e1", event_type="event_recorded",
        created_at="2026-01-15", actor="system",
        description="   ",
    )
    _fail("2.10 whitespace description rejected", "should have raised")
except ValidationError:
    _ok("2.10 whitespace description rejected")


# ---------------------------------------------------------------------------
# Section 3: EventMemoryRecord validation
# ---------------------------------------------------------------------------

_section("3: EventMemoryRecord validation")

rec1 = EventMemoryRecord(
    event_memory_id="emem_001",
    target="NVDA",
    event_name="Q4 Earnings Beat",
    recorded_at="2026-01-15T10:00:00Z",
    summary="NVDA reported Q4 EPS beat of 15%.",
)
_check("3.1 EventMemoryRecord creates OK", rec1.event_memory_id == "emem_001")
_check("3.2 event_type defaults unknown", rec1.event_type == "unknown")
_check("3.3 status defaults unknown", rec1.status == "unknown")
_check("3.4 review_status defaults unknown", rec1.review_status == "unknown")
_check("3.5 approved_for_execution defaults False", rec1.approved_for_execution is False)
_check("3.6 thesis_changing defaults False", rec1.thesis_changing is False)
_check("3.7 source_refs defaults to list", isinstance(rec1.source_refs, list))
_check("3.8 evidence_ids defaults to list", isinstance(rec1.evidence_ids, list))
_check("3.9 artifact_refs defaults to list", isinstance(rec1.artifact_refs, list))
_check("3.10 event_log defaults to list", isinstance(rec1.event_log, list))
_check("3.11 affected_horizons defaults to list", isinstance(rec1.affected_horizons, list))

try:
    EventMemoryRecord(
        event_memory_id="emem_001",
        target="NVDA",
        event_name="Q4 Earnings Beat",
        recorded_at="2026-01-15T10:00:00Z",
        summary="EPS beat.",
        approved_for_execution=True,
    )
    _fail("3.12 approved_for_execution=True rejected", "should have raised")
except ValidationError:
    _ok("3.12 approved_for_execution=True rejected")

try:
    EventMemoryRecord(
        event_memory_id="   ",
        target="NVDA",
        event_name="Q4",
        recorded_at="2026-01-15",
        summary="test",
    )
    _fail("3.13 whitespace event_memory_id rejected", "should have raised")
except ValidationError:
    _ok("3.13 whitespace event_memory_id rejected")

try:
    EventMemoryRecord(
        event_memory_id="emem_001",
        target="   ",
        event_name="Q4",
        recorded_at="2026-01-15",
        summary="test",
    )
    _fail("3.14 whitespace target rejected", "should have raised")
except ValidationError:
    _ok("3.14 whitespace target rejected")

try:
    EventMemoryRecord(
        event_memory_id="emem_001",
        target="NVDA",
        event_name="   ",
        recorded_at="2026-01-15",
        summary="test",
    )
    _fail("3.15 whitespace event_name rejected", "should have raised")
except ValidationError:
    _ok("3.15 whitespace event_name rejected")


# ---------------------------------------------------------------------------
# Section 4: EventMemoryInputBundle validation
# ---------------------------------------------------------------------------

_section("4: EventMemoryInputBundle validation")

bundle1 = EventMemoryInputBundle(target="NVDA")
_check("4.1 EventMemoryInputBundle creates OK", bundle1.target == "NVDA")
_check("4.2 run_id defaults None", bundle1.run_id is None)
_check("4.3 as_of defaults None", bundle1.as_of is None)
_check("4.4 source_ids defaults list", isinstance(bundle1.source_ids, list))
_check("4.5 evidence_ids defaults list", isinstance(bundle1.evidence_ids, list))
_check("4.6 artifact_refs defaults list", isinstance(bundle1.artifact_refs, list))
_check("4.7 warnings defaults list", isinstance(bundle1.warnings, list))
_check("4.8 research_run_memory_record defaults None", bundle1.research_run_memory_record is None)
_check("4.9 thesis_memory_report defaults None", bundle1.thesis_memory_report is None)
_check("4.10 event_intelligence_report defaults None", bundle1.event_intelligence_report is None)
_check("4.11 decision_packet defaults None", bundle1.decision_packet is None)
_check("4.12 human_review_report defaults None", bundle1.human_review_report is None)
_check("4.13 memory_id defaults None", bundle1.memory_id is None)
_check("4.14 thesis_id defaults None", bundle1.thesis_id is None)

try:
    EventMemoryInputBundle(target="   ")
    _fail("4.15 whitespace target rejected", "should have raised")
except ValidationError:
    _ok("4.15 whitespace target rejected")

bundle2 = EventMemoryInputBundle(
    target="AAPL",
    run_id="run_001",
    memory_id="rmem_001",
    thesis_id="thesis_001",
    as_of="2026-01-15T00:00:00Z",
    source_ids=["s1", "s2"],
    evidence_ids=["e1"],
    artifact_refs=["a1"],
    warnings=["w1"],
)
_check("4.16 full EventMemoryInputBundle round-trips", bundle2.run_id == "run_001")
_check("4.17 thesis_id round-trips", bundle2.thesis_id == "thesis_001")


# ---------------------------------------------------------------------------
# Section 5: EventMemorySummary validation
# ---------------------------------------------------------------------------

_section("5: EventMemorySummary validation")

summ1 = EventMemorySummary(target="NVDA", status="active")
_check("5.1 EventMemorySummary creates OK", summ1.target == "NVDA")
_check("5.2 record_count defaults 0", summ1.record_count == 0)
_check("5.3 approved_for_execution defaults False", summ1.approved_for_execution is False)
_check("5.4 affected_horizons defaults list", isinstance(summ1.affected_horizons, list))
_check("5.5 top_warnings defaults list", isinstance(summ1.top_warnings, list))

try:
    EventMemorySummary(target="NVDA", status="active", approved_for_execution=True)
    _fail("5.6 approved_for_execution=True rejected", "should have raised")
except ValidationError:
    _ok("5.6 approved_for_execution=True rejected")


# ---------------------------------------------------------------------------
# Section 6: EventMemoryReport validation
# ---------------------------------------------------------------------------

_section("6: EventMemoryReport validation")

summ_for_rep = EventMemorySummary(target="NVDA", status="unknown")
rep1 = EventMemoryReport(
    report_id="emrep_001",
    target="NVDA",
    summary=summ_for_rep,
    created_at="2026-01-15T00:00:00Z",
    updated_at="2026-01-15T00:00:00Z",
)
_check("6.1 EventMemoryReport creates OK", rep1.report_id == "emrep_001")
_check("6.2 status defaults unknown", rep1.status == "unknown")
_check("6.3 records defaults list", isinstance(rep1.records, list))
_check("6.4 approved_for_execution defaults False", rep1.approved_for_execution is False)

try:
    EventMemoryReport(
        report_id="emrep_001",
        target="NVDA",
        summary=summ_for_rep,
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
        approved_for_execution=True,
    )
    _fail("6.5 approved_for_execution=True rejected", "should have raised")
except ValidationError:
    _ok("6.5 approved_for_execution=True rejected")

try:
    EventMemoryReport(
        report_id="   ",
        target="NVDA",
        summary=summ_for_rep,
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    _fail("6.6 whitespace report_id rejected", "should have raised")
except ValidationError:
    _ok("6.6 whitespace report_id rejected")


# ---------------------------------------------------------------------------
# Section 7: ID generators — determinism and uniqueness
# ---------------------------------------------------------------------------

_section("7: ID generators — determinism and uniqueness")

rid1 = make_event_memory_record_id("NVDA", "Q4 Earnings", "earnings", "2026-01-15", "run1")
rid2 = make_event_memory_record_id("NVDA", "Q4 Earnings", "earnings", "2026-01-15", "run1")
rid3 = make_event_memory_record_id("NVDA", "Q4 Earnings", "earnings", "2026-01-15", "run2")
rid4 = make_event_memory_record_id("AAPL", "Q4 Earnings", "earnings", "2026-01-15", "run1")
rid5 = make_event_memory_record_id("NVDA", "Product Launch", "catalyst", "2026-01-15", "run1")
_check("7.1 record ID is deterministic", rid1 == rid2)
_check("7.2 different run_id → different ID", rid1 != rid3)
_check("7.3 different target → different ID", rid1 != rid4)
_check("7.4 different event_name → different ID", rid1 != rid5)
_check("7.5 record ID starts with emem_", rid1.startswith("emem_"))

evtid1 = make_event_memory_log_entry_id("emem_001", "event_recorded", "2026-01-15T10:00:00Z")
evtid2 = make_event_memory_log_entry_id("emem_001", "event_recorded", "2026-01-15T10:00:00Z")
evtid3 = make_event_memory_log_entry_id("emem_001", "review_requested", "2026-01-15T10:00:00Z")
_check("7.6 log entry ID is deterministic", evtid1 == evtid2)
_check("7.7 different event_type → different ID", evtid1 != evtid3)
_check("7.8 log entry ID starts with emevt_", evtid1.startswith("emevt_"))

repid1 = make_event_memory_report_id("NVDA", "2026-01-15", "run1")
repid2 = make_event_memory_report_id("NVDA", "2026-01-15", "run1")
repid3 = make_event_memory_report_id("NVDA", "2026-01-15", "run2")
repid4 = make_event_memory_report_id("AAPL", "2026-01-15", "run1")
_check("7.9 report ID is deterministic", repid1 == repid2)
_check("7.10 different run_id → different report ID", repid1 != repid3)
_check("7.11 different target → different report ID", repid1 != repid4)
_check("7.12 report ID starts with emrep_", repid1.startswith("emrep_"))


# ---------------------------------------------------------------------------
# Section 8: build_event_memory_log_entry
# ---------------------------------------------------------------------------

_section("8: build_event_memory_log_entry")

le1 = build_event_memory_log_entry(
    event_type="event_recorded",
    description="NVDA Q4 earnings beat recorded.",
    event_memory_id="emem_001",
    created_at="2026-01-15T10:00:00Z",
    actor="system",
    source_ids=["s1", "s2"],
    evidence_ids=["e1"],
    metadata={"key": "val"},
    warnings=["w1"],
)
_check("8.1 log entry builds OK", le1.event_type == "event_recorded")
_check("8.2 actor round-trips", le1.actor == "system")
_check("8.3 source_ids preserved", le1.source_ids == ["s1", "s2"])
_check("8.4 evidence_ids preserved", le1.evidence_ids == ["e1"])
_check("8.5 metadata preserved", le1.metadata == {"key": "val"})
_check("8.6 event_id is deterministic", le1.event_id == make_event_memory_log_entry_id("emem_001", "event_recorded", "2026-01-15T10:00:00Z"))

le_no_ts = build_event_memory_log_entry(
    event_type="review_requested",
    description="Review requested.",
    event_memory_id="emem_001",
)
_check("8.7 no timestamp → fallback used", le_no_ts.created_at == "1970-01-01T00:00:00Z")
_check("8.8 deterministic without timestamp", le_no_ts.event_id.startswith("emevt_"))


# ---------------------------------------------------------------------------
# Section 9: build_event_memory_record — catalyst
# ---------------------------------------------------------------------------

_section("9: build_event_memory_record — catalyst")

catalyst_rec = build_event_memory_record(
    target="NVDA",
    event_name="AI Data Center Partnership Announced",
    summary="NVDA announced a major AI data center partnership.",
    event_type="catalyst",
    impact_direction="positive",
    impact_magnitude="high",
    thesis_changing=True,
    affected_horizons=["medium", "long"],
    recorded_at="2026-01-15T10:00:00Z",
)
_check("9.1 catalyst record builds OK", catalyst_rec.event_type == "catalyst")
_check("9.2 impact_direction round-trips", catalyst_rec.impact_direction == "positive")
_check("9.3 impact_magnitude round-trips", catalyst_rec.impact_magnitude == "high")
_check("9.4 thesis_changing round-trips", catalyst_rec.thesis_changing is True)
_check("9.5 affected_horizons preserved", catalyst_rec.affected_horizons == ["medium", "long"])
_check("9.6 status is thesis_changing (thesis_changing=True, no review)", catalyst_rec.status == "thesis_changing")
_check("9.7 event_log not empty", len(catalyst_rec.event_log) > 0)
_check("9.8 event_log includes event_recorded", any(e.event_type == "event_recorded" for e in catalyst_rec.event_log))
_check("9.9 event_log includes review_requested (thesis_changing)", any(e.event_type == "review_requested" for e in catalyst_rec.event_log))
_check("9.10 event_log includes thesis_changed", any(e.event_type == "thesis_changed" for e in catalyst_rec.event_log))
_check("9.11 approved_for_execution is False", catalyst_rec.approved_for_execution is False)
_check("9.12 recorded_at uses explicit timestamp", catalyst_rec.recorded_at == "2026-01-15T10:00:00Z")


# ---------------------------------------------------------------------------
# Section 10: build_event_memory_record — news
# ---------------------------------------------------------------------------

_section("10: build_event_memory_record — news")

news_rec = build_event_memory_record(
    target="MSFT",
    event_name="Regulatory Probe Announced",
    summary="EU regulatory probe into MSFT cloud bundling practices.",
    event_type="news",
    impact_direction="negative",
    impact_magnitude="medium",
    review_status="pending",
    affected_horizons=["short"],
)
_check("10.1 news record builds OK", news_rec.event_type == "news")
_check("10.2 status is needs_review (review_status=pending)", news_rec.status == "needs_review")
_check("10.3 review_status preserved", news_rec.review_status == "pending")
_check("10.4 no timestamp → fallback", news_rec.recorded_at == "1970-01-01T00:00:00Z")


# ---------------------------------------------------------------------------
# Section 11: build_event_memory_record — earnings
# ---------------------------------------------------------------------------

_section("11: build_event_memory_record — earnings")

earnings_rec = build_event_memory_record(
    target="AAPL",
    event_name="Q1 FY2026 Earnings",
    summary="AAPL reported Q1 FY2026 earnings with 8% revenue growth.",
    event_type="earnings",
    impact_direction="positive",
    impact_magnitude="medium",
    review_status="reviewed",
    market_reaction="Stock up 3% AH.",
    guidance_update="Q2 guidance in-line with estimates.",
    recorded_at="2026-01-30T21:00:00Z",
)
_check("11.1 earnings record builds OK", earnings_rec.event_type == "earnings")
_check("11.2 status is reviewed (review_status=reviewed)", earnings_rec.status == "reviewed")
_check("11.3 market_reaction preserved", earnings_rec.market_reaction == "Stock up 3% AH.")
_check("11.4 guidance_update preserved", earnings_rec.guidance_update == "Q2 guidance in-line with estimates.")


# ---------------------------------------------------------------------------
# Section 12: build_event_memory_record — guidance
# ---------------------------------------------------------------------------

_section("12: build_event_memory_record — guidance")

guidance_rec = build_event_memory_record(
    target="TSLA",
    event_name="FY2026 Delivery Guidance Cut",
    summary="TSLA cut FY2026 delivery guidance by 10%.",
    event_type="guidance",
    impact_direction="negative",
    impact_magnitude="high",
    review_status="unknown",
    guidance_update="FY2026 deliveries now guided to 1.8M vs prior 2.0M.",
)
_check("12.1 guidance record builds OK", guidance_rec.event_type == "guidance")
_check("12.2 high-impact with unknown review → needs_review", guidance_rec.status == "needs_review")
_check("12.3 guidance_update preserved", "1.8M" in (guidance_rec.guidance_update or ""))


# ---------------------------------------------------------------------------
# Section 13: build_event_memory_record — estimate revision
# ---------------------------------------------------------------------------

_section("13: build_event_memory_record — estimate revision")

est_rec = build_event_memory_record(
    target="GOOG",
    event_name="FY2026 EPS Estimate Revision",
    summary="Consensus EPS estimate for GOOG FY2026 raised by 5%.",
    event_type="estimate_revision",
    impact_direction="positive",
    impact_magnitude="low",
    review_status="not_required",
    estimate_revision_summary="EPS estimate raised from $7.20 to $7.56.",
)
_check("13.1 estimate_revision record builds OK", est_rec.event_type == "estimate_revision")
_check("13.2 status is active (low impact, not_required)", est_rec.status == "active")
_check("13.3 estimate_revision_summary preserved", "7.56" in (est_rec.estimate_revision_summary or ""))


# ---------------------------------------------------------------------------
# Section 14: build_event_memory_record — initial_status override
# ---------------------------------------------------------------------------

_section("14: build_event_memory_record — initial_status override")

archived_rec = build_event_memory_record(
    target="NVDA",
    event_name="Old Product Launch",
    summary="Legacy product launch, now archived.",
    event_type="product",
    initial_status="archived",
)
_check("14.1 initial_status=archived overrides auto-determination", archived_rec.status == "archived")

blocked_rec = build_event_memory_record(
    target="NVDA",
    event_name="Sensitive Legal Event",
    summary="Legal matter under review.",
    event_type="legal",
    initial_status="blocked",
)
_check("14.2 initial_status=blocked overrides auto-determination", blocked_rec.status == "blocked")


# ---------------------------------------------------------------------------
# Section 15: build_event_memory_record — source_refs and evidence_ids
# ---------------------------------------------------------------------------

_section("15: build_event_memory_record — source_refs and evidence_ids")

source_refs = [
    EventMemorySourceRef(source_id="src_001", source_type="news", label="Reuters"),
    EventMemorySourceRef(source_id="src_002", source_type="analyst_note"),
]
rec_with_refs = build_event_memory_record(
    target="NVDA",
    event_name="Analyst Upgrade",
    summary="NVDA upgraded to Buy by Goldman.",
    event_type="news",
    source_refs=source_refs,
    evidence_ids=["ev_001", "ev_002"],
    artifact_refs=["art_001"],
    recorded_at="2026-01-20T09:00:00Z",
)
_check("15.1 source_refs preserved", len(rec_with_refs.source_refs) == 2)
_check("15.2 source_refs[0].source_id", rec_with_refs.source_refs[0].source_id == "src_001")
_check("15.3 evidence_ids deduplicated and preserved", "ev_001" in rec_with_refs.evidence_ids)
_check("15.4 artifact_refs preserved", "art_001" in rec_with_refs.artifact_refs)

# Deduplication
rec_dedup = build_event_memory_record(
    target="NVDA",
    event_name="Dedup Test",
    summary="Testing deduplication.",
    event_type="catalyst",
    evidence_ids=["ev_001", "ev_001", "ev_002", "ev_001"],
    artifact_refs=["art_1", "art_1", "art_2"],
)
_check("15.5 evidence_ids deduplicated", rec_dedup.evidence_ids == ["ev_001", "ev_002"])
_check("15.6 artifact_refs deduplicated", rec_dedup.artifact_refs == ["art_1", "art_2"])


# ---------------------------------------------------------------------------
# Section 16: build_event_memory_record — input_bundle integration
# ---------------------------------------------------------------------------

_section("16: build_event_memory_record — input_bundle integration")

bundle_w_as_of = EventMemoryInputBundle(
    target="NVDA",
    run_id="run_001",
    memory_id="rmem_001",
    thesis_id="thesis_001",
    as_of="2026-03-01T00:00:00Z",
)
rec_with_bundle = build_event_memory_record(
    target="NVDA",
    event_name="Q1 Preview",
    summary="Pre-earnings catalyst.",
    event_type="catalyst",
    input_bundle=bundle_w_as_of,
)
_check("16.1 run_id from input_bundle", rec_with_bundle.run_id == "run_001")
_check("16.2 memory_id from input_bundle", rec_with_bundle.memory_id == "rmem_001")
_check("16.3 thesis_id from input_bundle", rec_with_bundle.thesis_id == "thesis_001")
_check("16.4 recorded_at from bundle as_of", rec_with_bundle.recorded_at == "2026-03-01T00:00:00Z")

# Explicit recorded_at overrides bundle as_of
rec_explicit_ts = build_event_memory_record(
    target="NVDA",
    event_name="Q1 Preview",
    summary="Pre-earnings catalyst.",
    event_type="catalyst",
    input_bundle=bundle_w_as_of,
    recorded_at="2026-04-01T00:00:00Z",
)
_check("16.5 explicit recorded_at overrides bundle as_of", rec_explicit_ts.recorded_at == "2026-04-01T00:00:00Z")


# ---------------------------------------------------------------------------
# Section 17: build_event_memory_record — missing optional upstream artifacts
# ---------------------------------------------------------------------------

_section("17: build_event_memory_record — missing optional upstream artifacts")

bundle_no_artifacts = EventMemoryInputBundle(target="NVDA")
rec_no_artifacts = build_event_memory_record(
    target="NVDA",
    event_name="Routine News",
    summary="No upstream artifacts available.",
    event_type="news",
    input_bundle=bundle_no_artifacts,
)
_check("17.1 builds without crash (no artifacts)", rec_no_artifacts.event_type == "news")
_check("17.2 warnings include missing event_intelligence_report", any("event_intelligence_report" in w for w in rec_no_artifacts.warnings))
_check("17.3 warnings include missing decision_packet", any("decision_packet" in w for w in rec_no_artifacts.warnings))


# ---------------------------------------------------------------------------
# Section 18: build_event_memory_record — human review blocked causes blocked
# ---------------------------------------------------------------------------

_section("18: build_event_memory_record — human review blocked causes blocked")


class _MockHRR:
    status = "blocked"


bundle_hrr_blocked = EventMemoryInputBundle(
    target="NVDA",
    human_review_report=_MockHRR(),
)
rec_hrr_blocked = build_event_memory_record(
    target="NVDA",
    event_name="HRR Blocked Event",
    summary="Human review is blocked.",
    event_type="regulatory",
    input_bundle=bundle_hrr_blocked,
)
_check("18.1 HRR blocked → record status blocked", rec_hrr_blocked.status == "blocked")
_check("18.2 warning mentions blocked", any("blocked" in w for w in rec_hrr_blocked.warnings))


# ---------------------------------------------------------------------------
# Section 19: determine_event_memory_status — report-level
# ---------------------------------------------------------------------------

_section("19: determine_event_memory_status — report-level")

empty_bundle = EventMemoryInputBundle(target="NVDA")

status_empty, _ = determine_event_memory_status([], empty_bundle)
_check("19.1 empty records → unknown", status_empty == "unknown")

rec_active = build_event_memory_record(
    target="NVDA",
    event_name="Active Event",
    summary="Active event.",
    event_type="news",
    review_status="not_required",
)
status_active, _ = determine_event_memory_status([rec_active], empty_bundle)
_check("19.2 all active → active", status_active == "active")

rec_reviewed = build_event_memory_record(
    target="NVDA",
    event_name="Reviewed Event",
    summary="Reviewed event.",
    event_type="news",
    review_status="reviewed",
)
status_reviewed, _ = determine_event_memory_status([rec_reviewed], empty_bundle)
_check("19.3 all reviewed → reviewed", status_reviewed == "reviewed")

rec_needs_review = build_event_memory_record(
    target="NVDA",
    event_name="Needs Review Event",
    summary="Needs review.",
    event_type="news",
    review_status="pending",
)
status_nr, _ = determine_event_memory_status([rec_reviewed, rec_needs_review], empty_bundle)
_check("19.4 any needs_review → needs_review", status_nr == "needs_review")

rec_tc = build_event_memory_record(
    target="NVDA",
    event_name="Thesis Changer",
    summary="Thesis-changing event.",
    event_type="catalyst",
    thesis_changing=True,
)
status_tc, _ = determine_event_memory_status([rec_reviewed, rec_tc], empty_bundle)
_check("19.5 any thesis_changing → thesis_changing", status_tc == "thesis_changing")

rec_blocked_inner = build_event_memory_record(
    target="NVDA",
    event_name="Blocked Event",
    summary="Blocked.",
    event_type="legal",
    initial_status="blocked",
)
status_blocked, _ = determine_event_memory_status([rec_reviewed, rec_tc, rec_blocked_inner], empty_bundle)
_check("19.6 any blocked → blocked", status_blocked == "blocked")

# HRR blocked at bundle level
bundle_hrr = EventMemoryInputBundle(target="NVDA", human_review_report=_MockHRR())
status_hrr, _ = determine_event_memory_status([rec_reviewed], bundle_hrr)
_check("19.7 HRR blocked → report blocked", status_hrr == "blocked")

# Precedence: blocked > thesis_changing > needs_review > reviewed > active
recs_mixed = [rec_active, rec_reviewed, rec_needs_review, rec_tc]
status_prec, _ = determine_event_memory_status(recs_mixed, empty_bundle)
_check("19.8 blocked > thesis_changing > needs_review precedence: thesis_changing wins", status_prec == "thesis_changing")

recs_all_archived = [
    build_event_memory_record(target="NVDA", event_name="Old1", summary="old", initial_status="archived"),
    build_event_memory_record(target="NVDA", event_name="Old2", summary="old", initial_status="archived"),
]
status_arch, _ = determine_event_memory_status(recs_all_archived, empty_bundle)
_check("19.9 all archived → archived", status_arch == "archived")

# High-impact unreviewed escalates to needs_review
rec_high_active = build_event_memory_record(
    target="NVDA",
    event_name="High Impact Active",
    summary="High impact, not reviewed.",
    event_type="catalyst",
    impact_magnitude="high",
    review_status="not_required",  # not_required means no review needed → status=active
)
# But determine_event_memory_status should see high impact + status=active → needs_review
status_hi, _ = determine_event_memory_status([rec_high_active], empty_bundle)
_check("19.10 high-impact active record → needs_review at report level", status_hi == "needs_review")


# ---------------------------------------------------------------------------
# Section 20: build_event_memory_report — complete report
# ---------------------------------------------------------------------------

_section("20: build_event_memory_report — complete report")

bundle_full = EventMemoryInputBundle(
    target="NVDA",
    run_id="run_001",
    as_of="2026-03-01T00:00:00Z",
    source_ids=["bundle_src_1"],
    evidence_ids=["bundle_ev_1"],
    artifact_refs=["bundle_art_1"],
)

records_full = [
    build_event_memory_record(
        target="NVDA",
        event_name="Q4 Earnings Beat",
        summary="EPS beat by 15%.",
        event_type="earnings",
        review_status="reviewed",
        recorded_at="2026-01-15T10:00:00Z",
    ),
    build_event_memory_record(
        target="NVDA",
        event_name="AI Partnership",
        summary="Major AI data center partnership.",
        event_type="catalyst",
        thesis_changing=True,
        impact_magnitude="high",
        recorded_at="2026-01-20T10:00:00Z",
    ),
    build_event_memory_record(
        target="NVDA",
        event_name="Analyst Upgrade",
        summary="Goldman upgrades NVDA.",
        event_type="news",
        review_status="not_required",
        impact_magnitude="low",
        recorded_at="2026-02-01T10:00:00Z",
    ),
]

report_full = build_event_memory_report(
    input_bundle=bundle_full,
    records=records_full,
)
_check("20.1 report builds OK", report_full.target == "NVDA")
_check("20.2 report_id deterministic", report_full.report_id.startswith("emrep_"))
_check("20.3 run_id from bundle", report_full.run_id == "run_001")
_check("20.4 records preserved", len(report_full.records) == 3)
_check("20.5 status is thesis_changing (any thesis_changing record)", report_full.status == "thesis_changing")
_check("20.6 created_at from bundle as_of", report_full.created_at == "2026-03-01T00:00:00Z")
_check("20.7 updated_at defaults to created_at", report_full.updated_at == "2026-03-01T00:00:00Z")
_check("20.8 approved_for_execution is False", report_full.approved_for_execution is False)
_check("20.9 summary.record_count = 3", report_full.summary.record_count == 3)
_check("20.10 summary.earnings_count = 1", report_full.summary.earnings_count == 1)
_check("20.11 summary.catalyst_count = 1", report_full.summary.catalyst_count == 1)
_check("20.12 summary.news_count = 1", report_full.summary.news_count == 1)
_check("20.13 summary.thesis_changing_count = 1", report_full.summary.thesis_changing_count == 1)
_check("20.14 summary.reviewed_count = 1", report_full.summary.reviewed_count == 1)


# ---------------------------------------------------------------------------
# Section 21: build_event_memory_report — deterministic timestamps
# ---------------------------------------------------------------------------

_section("21: build_event_memory_report — deterministic timestamps")

bundle_no_ts = EventMemoryInputBundle(target="NVDA")
report_no_ts1 = build_event_memory_report(input_bundle=bundle_no_ts)
report_no_ts2 = build_event_memory_report(input_bundle=bundle_no_ts)
_check("21.1 no timestamp → fallback used", report_no_ts1.created_at == "1970-01-01T00:00:00Z")
_check("21.2 deterministic without timestamp", report_no_ts1.report_id == report_no_ts2.report_id)

report_explicit_ts = build_event_memory_report(
    input_bundle=bundle_no_ts,
    created_at="2026-05-01T00:00:00Z",
    updated_at="2026-05-02T00:00:00Z",
)
_check("21.3 explicit created_at overrides fallback", report_explicit_ts.created_at == "2026-05-01T00:00:00Z")
_check("21.4 explicit updated_at overrides fallback", report_explicit_ts.updated_at == "2026-05-02T00:00:00Z")

bundle_with_ts = EventMemoryInputBundle(target="NVDA", as_of="2026-03-15T00:00:00Z")
report_bundle_ts = build_event_memory_report(input_bundle=bundle_with_ts)
_check("21.5 bundle as_of used as timestamp", report_bundle_ts.created_at == "2026-03-15T00:00:00Z")


# ---------------------------------------------------------------------------
# Section 22: build_event_memory_report — stable IDs
# ---------------------------------------------------------------------------

_section("22: build_event_memory_report — stable IDs")

bundle_stable = EventMemoryInputBundle(target="NVDA", run_id="run_001", as_of="2026-01-01")
recs_stable = [
    build_event_memory_record(target="NVDA", event_name="E1", summary="Summary.", recorded_at="2026-01-01"),
]
r1 = build_event_memory_report(input_bundle=bundle_stable, records=recs_stable)
r2 = build_event_memory_report(input_bundle=bundle_stable, records=recs_stable)
_check("22.1 stable report_id for identical inputs", r1.report_id == r2.report_id)
_check("22.2 stable created_at for identical inputs", r1.created_at == r2.created_at)

rec_id_a = make_event_memory_record_id("NVDA", "Q4 Earnings", "earnings", "2026-01-15")
rec_id_b = make_event_memory_record_id("NVDA", "Q4 Earnings", "earnings", "2026-01-15")
_check("22.3 stable record ID without run_id", rec_id_a == rec_id_b)


# ---------------------------------------------------------------------------
# Section 23: source / evidence / artifact deduplication
# ---------------------------------------------------------------------------

_section("23: source / evidence / artifact deduplication")

bundle_dedup = EventMemoryInputBundle(
    target="NVDA",
    source_ids=["s1", "s2", "s1", "s3"],
    evidence_ids=["e1", "e2", "e1"],
    artifact_refs=["a1", "a2", "a1", ""],
)
rec_dedup2 = build_event_memory_record(
    target="NVDA",
    event_name="Dedup Report Test",
    summary="Dedup.",
    event_type="news",
    source_refs=[
        EventMemorySourceRef(source_id="s2", source_type="news"),
        EventMemorySourceRef(source_id="s4", source_type="analyst_note"),
    ],
    evidence_ids=["e2", "e3"],
    artifact_refs=["a2", "a3"],
)

src_ids = collect_event_memory_source_ids(bundle_dedup, [rec_dedup2])
_check("23.1 source_ids deduplicated: s1, s2, s3, s4", src_ids == ["s1", "s2", "s3", "s4"])

ev_ids = collect_event_memory_evidence_ids(bundle_dedup, [rec_dedup2])
_check("23.2 evidence_ids deduplicated: e1, e2, e3", ev_ids == ["e1", "e2", "e3"])

art_refs = collect_event_memory_artifact_refs(bundle_dedup, [rec_dedup2])
_check("23.3 artifact_refs deduplicated (empty filtered): a1, a2, a3", art_refs == ["a1", "a2", "a3"])


# ---------------------------------------------------------------------------
# Section 24: inputs are not mutated
# ---------------------------------------------------------------------------

_section("24: inputs are not mutated")

bundle_orig = EventMemoryInputBundle(
    target="NVDA",
    source_ids=["s1"],
    evidence_ids=["e1"],
    artifact_refs=["a1"],
)
orig_source_ids = list(bundle_orig.source_ids)
orig_evidence_ids = list(bundle_orig.evidence_ids)
orig_artifact_refs = list(bundle_orig.artifact_refs)

build_event_memory_report(input_bundle=bundle_orig, records=[])
_check("24.1 input_bundle.source_ids not mutated", bundle_orig.source_ids == orig_source_ids)
_check("24.2 input_bundle.evidence_ids not mutated", bundle_orig.evidence_ids == orig_evidence_ids)
_check("24.3 input_bundle.artifact_refs not mutated", bundle_orig.artifact_refs == orig_artifact_refs)

rec_to_check = build_event_memory_record(
    target="NVDA",
    event_name="Immutability Test",
    summary="Test.",
    event_type="news",
    evidence_ids=["e1", "e2"],
    artifact_refs=["a1"],
)
orig_rec_ev = list(rec_to_check.evidence_ids)
collect_event_memory_evidence_ids(bundle_orig, [rec_to_check])
_check("24.4 record.evidence_ids not mutated after collection", rec_to_check.evidence_ids == orig_rec_ev)


# ---------------------------------------------------------------------------
# Section 25: pending review causes needs_review
# ---------------------------------------------------------------------------

_section("25: pending review causes needs_review")

rec_pending = build_event_memory_record(
    target="NVDA",
    event_name="Pending Review Event",
    summary="Pending review.",
    event_type="news",
    review_status="pending",
    impact_magnitude="low",
)
_check("25.1 pending review → needs_review status", rec_pending.status == "needs_review")

bundle_empty = EventMemoryInputBundle(target="NVDA")
status_pending, _ = determine_event_memory_status([rec_pending], bundle_empty)
_check("25.2 report status needs_review from pending record", status_pending == "needs_review")


# ---------------------------------------------------------------------------
# Section 26: reviewed records produce reviewed status
# ---------------------------------------------------------------------------

_section("26: reviewed records produce reviewed status")

rec_r1 = build_event_memory_record(
    target="NVDA", event_name="R1", summary="S1.", review_status="reviewed",
)
rec_r2 = build_event_memory_record(
    target="NVDA", event_name="R2", summary="S2.", review_status="reviewed",
)
status_reviewed_all, _ = determine_event_memory_status([rec_r1, rec_r2], bundle_empty)
_check("26.1 all reviewed records → reviewed report status", status_reviewed_all == "reviewed")


# ---------------------------------------------------------------------------
# Section 27: ToolResult adapter
# ---------------------------------------------------------------------------

_section("27: ToolResult adapter")

bundle_tool = EventMemoryInputBundle(target="NVDA", run_id="run_001")
recs_tool = [
    build_event_memory_record(
        target="NVDA", event_name="E1", summary="S1.", event_type="catalyst",
        thesis_changing=True, recorded_at="2026-01-01T00:00:00Z",
    ),
]
report_tool = build_event_memory_report(input_bundle=bundle_tool, records=recs_tool)
tr = event_memory_tool_result_from_report(report_tool)

_check("27.1 ToolResult type", isinstance(tr, ToolResult))
_check("27.2 tool_name is event_memory_report", tr.tool_name == "event_memory_report")
_check("27.3 run_id from report", tr.run_id == "run_001")
_check("27.4 ticker set to target", tr.ticker == "NVDA")
_check("27.5 evidence_id is deterministic", tr.evidence_id is not None)
_check("27.6 approved_for_execution=False in outputs", tr.outputs.get("approved_for_execution") is False)
_check("27.7 full report in outputs", "report" in tr.outputs)
_check("27.8 summary in outputs", "summary" in tr.outputs)
_check("27.9 calculation_version in outputs", "calculation_version" in tr.outputs)
_check("27.10 record_count in outputs", tr.outputs.get("record_count") == 1)
_check("27.11 thesis_changing_count in outputs", tr.outputs.get("thesis_changing_count") == 1)
_check("27.12 inputs contains target", tr.inputs.get("target") == "NVDA")
_check("27.13 inputs contains report_id", "report_id" in tr.inputs)

# Evidence ID changes when content changes
recs_tool_2 = [
    build_event_memory_record(
        target="NVDA", event_name="E1", summary="S1.", event_type="news",
        recorded_at="2026-01-01T00:00:00Z",
    ),
]
report_tool_2 = build_event_memory_report(input_bundle=bundle_tool, records=recs_tool_2)
tr2 = event_memory_tool_result_from_report(report_tool_2)
_check("27.14 evidence_id changes when records change", tr.evidence_id != tr2.evidence_id)

# run_id override
tr_override = event_memory_tool_result_from_report(report_tool, run_id="override_run")
_check("27.15 run_id override works", tr_override.run_id == "override_run")


# ---------------------------------------------------------------------------
# Section 28: __all__ exports include Phase 4M-C public symbols
# ---------------------------------------------------------------------------

_section("28: __all__ exports include Phase 4M-C public symbols")

import lib.reliability.event_memory as _em_module

_expected_exports = [
    "EventMemoryActorType",
    "EventMemoryEventType",
    "EventMemoryImpactDirection",
    "EventMemoryImpactMagnitude",
    "EventMemoryInputBundle",
    "EventMemoryLogEntry",
    "EventMemoryRecord",
    "EventMemoryReport",
    "EventMemoryReviewStatus",
    "EventMemorySourceRef",
    "EventMemorySourceType",
    "EventMemoryStatus",
    "EventMemorySummary",
    "EventMemoryType",
    "build_event_memory_log_entry",
    "build_event_memory_record",
    "build_event_memory_report",
    "collect_event_memory_artifact_refs",
    "collect_event_memory_evidence_ids",
    "collect_event_memory_source_ids",
    "determine_event_memory_status",
    "event_memory_tool_result_from_report",
    "make_event_memory_log_entry_id",
    "make_event_memory_record_id",
    "make_event_memory_report_id",
    "summarize_event_memory",
]
for sym in _expected_exports:
    _check(f"28.{_expected_exports.index(sym)+1} {sym!r} in __all__", sym in _em_module.__all__)


# ---------------------------------------------------------------------------
# Section 29: lib.reliability __all__ includes Phase 4M-C symbols
# ---------------------------------------------------------------------------

_section("29: lib.reliability __all__ includes Phase 4M-C symbols")

import lib.reliability as _lr

_4mc_exports = [
    "EventMemoryActorType",
    "EventMemoryEventType",
    "EventMemoryImpactDirection",
    "EventMemoryImpactMagnitude",
    "EventMemoryInputBundle",
    "EventMemoryLogEntry",
    "EventMemoryRecord",
    "EventMemoryReport",
    "EventMemoryReviewStatus",
    "EventMemorySourceRef",
    "EventMemorySourceType",
    "EventMemoryStatus",
    "EventMemorySummary",
    "EventMemoryType",
    "build_event_memory_log_entry",
    "build_event_memory_record",
    "build_event_memory_report",
    "collect_event_memory_artifact_refs",
    "collect_event_memory_evidence_ids",
    "collect_event_memory_source_ids",
    "determine_event_memory_status",
    "event_memory_tool_result_from_report",
    "make_event_memory_log_entry_id",
    "make_event_memory_record_id",
    "make_event_memory_report_id",
    "summarize_event_memory",
]
for sym in _4mc_exports:
    _check(
        f"29.{_4mc_exports.index(sym)+1} {sym!r} in lib.reliability.__all__",
        sym in _lr.__all__,
    )


# ---------------------------------------------------------------------------
# Section 30: no forbidden dependency in event_memory module
# ---------------------------------------------------------------------------

_section("30: no forbidden dependency in event_memory module")

import inspect
import lib.reliability.event_memory as _em_check

for _forbidden in _forbidden_modules:
    _check(
        f"30.{_forbidden_modules.index(_forbidden)+1} '{_forbidden}' not imported in event_memory module",
        _forbidden not in sys.modules or not any(
            _forbidden in getattr(m, "__name__", "")
            for m in getattr(_em_check, "__dict__", {}).values()
            if hasattr(m, "__module__")
        ),
    )

_em_src = inspect.getsource(_em_check)
_check("30.14 no 'streamlit' in source", "streamlit" not in _em_src)
_check("30.15 no 'finnhub' in source", "finnhub" not in _em_src)
_check("30.16 no 'anthropic' in source", "anthropic" not in _em_src)
_check("30.17 no 'sqlalchemy' in source", "sqlalchemy" not in _em_src)
_check("30.18 no broker import/execution call in source",
       "import broker" not in _em_src and "broker_api" not in _em_src
       and "order_execution" not in _em_src and "execute_order" not in _em_src)


# ---------------------------------------------------------------------------
# Section 31: collect_event_memory helpers — upstream artifact auto-detection
# ---------------------------------------------------------------------------

_section("31: collect helpers — upstream artifact auto-detection")


class _MockResearchMemory:
    report_id = "rmem_report_001"
    source_ids = ["rmem_src_1", "rmem_src_2"]


class _MockThesisMemory:
    report_id = "thesis_report_001"
    source_ids = ["thesis_src_1"]


bundle_with_artifacts = EventMemoryInputBundle(
    target="NVDA",
    source_ids=["bundle_src_1"],
    research_run_memory_record=_MockResearchMemory(),
    thesis_memory_report=_MockThesisMemory(),
)
src_ids_auto = collect_event_memory_source_ids(bundle_with_artifacts)
_check("31.1 bundle source_ids included", "bundle_src_1" in src_ids_auto)
_check("31.2 research_run_memory source_ids included", "rmem_src_1" in src_ids_auto)
_check("31.3 thesis_memory source_ids included", "thesis_src_1" in src_ids_auto)
_check("31.4 artifact report_ids included as source_ids", "rmem_report_001" in src_ids_auto)
_check("31.5 no duplicates", len(src_ids_auto) == len(set(src_ids_auto)))


# ---------------------------------------------------------------------------
# Section 32: missing optional upstream artifacts — warnings not crashes
# ---------------------------------------------------------------------------

_section("32: missing optional upstream artifacts — warnings not crashes")

bundle_missing = EventMemoryInputBundle(target="NVDA")
report_missing = build_event_memory_report(input_bundle=bundle_missing, records=[])
_check("32.1 builds without crash", report_missing.status == "unknown")
_check("32.2 warns about missing event_intelligence_report",
       any("event_intelligence_report" in w for w in report_missing.warnings))
_check("32.3 warns about missing decision_packet",
       any("decision_packet" in w for w in report_missing.warnings))
_check("32.4 warns about missing human_review_report",
       any("human_review_report" in w for w in report_missing.warnings))


# ---------------------------------------------------------------------------
# Section 33: affected_horizons aggregation in summary
# ---------------------------------------------------------------------------

_section("33: affected_horizons aggregation in summary")

rec_horizon1 = build_event_memory_record(
    target="NVDA", event_name="H1", summary="S1.",
    affected_horizons=["short", "medium"], review_status="not_required",
)
rec_horizon2 = build_event_memory_record(
    target="NVDA", event_name="H2", summary="S2.",
    affected_horizons=["medium", "long"], review_status="not_required",
)
bundle_h = EventMemoryInputBundle(target="NVDA")
report_h = build_event_memory_report(input_bundle=bundle_h, records=[rec_horizon1, rec_horizon2])
_check("33.1 summary aggregates affected_horizons", set(report_h.summary.affected_horizons) == {"short", "medium", "long"})
_check("33.2 affected_horizons is sorted", report_h.summary.affected_horizons == sorted(report_h.summary.affected_horizons))


# ---------------------------------------------------------------------------
# Section 34: summary counts
# ---------------------------------------------------------------------------

_section("34: summary counts")

recs_count = [
    build_event_memory_record(target="NVDA", event_name="C1", summary="S.", event_type="catalyst", impact_magnitude="high", review_status="not_required"),
    build_event_memory_record(target="NVDA", event_name="N1", summary="S.", event_type="news", review_status="reviewed"),
    build_event_memory_record(target="NVDA", event_name="E1", summary="S.", event_type="earnings", review_status="reviewed"),
    build_event_memory_record(target="NVDA", event_name="G1", summary="S.", event_type="guidance", review_status="pending"),
    build_event_memory_record(target="NVDA", event_name="ER1", summary="S.", event_type="estimate_revision", review_status="not_required"),
    build_event_memory_record(target="NVDA", event_name="TC1", summary="S.", event_type="catalyst", thesis_changing=True),
]
bundle_cnt = EventMemoryInputBundle(target="NVDA")
report_cnt = build_event_memory_report(input_bundle=bundle_cnt, records=recs_count)
summ = report_cnt.summary
_check("34.1 record_count = 6", summ.record_count == 6)
_check("34.2 catalyst_count = 2", summ.catalyst_count == 2)
_check("34.3 news_count = 1", summ.news_count == 1)
_check("34.4 earnings_count = 1", summ.earnings_count == 1)
_check("34.5 guidance_count = 1", summ.guidance_count == 1)
_check("34.6 estimate_revision_count = 1", summ.estimate_revision_count == 1)
_check("34.7 thesis_changing_count = 1", summ.thesis_changing_count == 1)
_check("34.8 reviewed_count = 2", summ.reviewed_count == 2)
_check("34.9 high_impact_count = 1", summ.high_impact_count == 1)


# ---------------------------------------------------------------------------
# Section 35: calculation_version in report
# ---------------------------------------------------------------------------

_section("35: calculation_version in report")

bundle_ver = EventMemoryInputBundle(target="NVDA")
report_ver = build_event_memory_report(input_bundle=bundle_ver)
_check("35.1 calculation_version present", report_ver.calculation_version == "event_memory_v1")
tr_ver = event_memory_tool_result_from_report(report_ver)
_check("35.2 calculation_version in ToolResult outputs", tr_ver.outputs.get("calculation_version") == "event_memory_v1")


# ---------------------------------------------------------------------------
# Section 36: build_event_memory_record — source_refs deduplication
# ---------------------------------------------------------------------------

_section("36: build_event_memory_record — source_refs deduplication (Phase 4M-C polish)")

_dup_ref_a = EventMemorySourceRef(source_id="src_dup", source_type="news", label="First")
_dup_ref_b = EventMemorySourceRef(source_id="src_dup", source_type="analyst_note", label="Duplicate")
_dup_ref_c = EventMemorySourceRef(source_id="src_unique", source_type="earnings_report")

_rec_dedup = build_event_memory_record(
    target="AAPL",
    event_name="Dedup Test Event",
    summary="Testing source_refs deduplication.",
    source_refs=[_dup_ref_a, _dup_ref_b, _dup_ref_c],
)
_check("36.1 duplicate source_refs deduped to 2", len(_rec_dedup.source_refs) == 2)
_check("36.2 first occurrence (src_dup) preserved", _rec_dedup.source_refs[0].source_id == "src_dup")
_check("36.3 first occurrence label preserved", _rec_dedup.source_refs[0].label == "First")
_check("36.4 unique ref (src_unique) present", _rec_dedup.source_refs[1].source_id == "src_unique")

# Deterministic: same duplicated input → same deduped output
_rec_dedup2 = build_event_memory_record(
    target="AAPL",
    event_name="Dedup Test Event",
    summary="Testing source_refs deduplication.",
    source_refs=[_dup_ref_a, _dup_ref_b, _dup_ref_c],
)
_check("36.5 dedup is deterministic", len(_rec_dedup2.source_refs) == 2)
_check("36.6 dedup result stable across calls", _rec_dedup.source_refs[0].source_id == _rec_dedup2.source_refs[0].source_id)

# No duplication in input → no change
_rec_no_dup = build_event_memory_record(
    target="AAPL",
    event_name="No Dup Event",
    summary="No duplicates in source_refs.",
    source_refs=[_dup_ref_a, _dup_ref_c],
)
_check("36.7 no-dup input preserved as-is", len(_rec_no_dup.source_refs) == 2)

# All same source_id → only one kept
_rec_all_dup = build_event_memory_record(
    target="AAPL",
    event_name="All Same Event",
    summary="All source_refs share same source_id.",
    source_refs=[
        EventMemorySourceRef(source_id="src_same", label="A"),
        EventMemorySourceRef(source_id="src_same", label="B"),
        EventMemorySourceRef(source_id="src_same", label="C"),
    ],
)
_check("36.8 all-same source_id collapses to 1", len(_rec_all_dup.source_refs) == 1)
_check("36.9 first label kept for all-same", _rec_all_dup.source_refs[0].label == "A")


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"Phase 4M-C Event Memory Tests: {_test_count} total, {_fail_count} failed")
if _fail_count == 0:
    print("ALL TESTS PASSED")
else:
    print(f"FAILURES: {_fail_count}")
print('='*60)

sys.exit(0 if _fail_count == 0 else 1)
