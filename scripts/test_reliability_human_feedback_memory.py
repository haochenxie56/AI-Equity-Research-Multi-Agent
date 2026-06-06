"""
test_reliability_human_feedback_memory.py
Phase 4M-F: Human Feedback Layer reliability tests.
Sections 1-15: imports, model validation, builder smoke tests.
"""
import sys, types, importlib, traceback
sys.path.insert(0, "/home/hchxie/projects/investment-agents")

PASS = 0; FAIL = 0

def check(label, condition, info=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL [{label}]{': ' + str(info) if info else ''}")

def expect_error(label, fn, exc_type=Exception, keyword=None):
    global PASS, FAIL
    try:
        fn(); FAIL += 1; print(f"FAIL [{label}]: expected {exc_type.__name__} but no error raised")
    except exc_type as e:
        if keyword and keyword.lower() not in str(e).lower():
            FAIL += 1; print(f"FAIL [{label}]: raised {exc_type.__name__} but missing keyword {keyword!r} in: {e}")
        else:
            PASS += 1
    except Exception as e:
        FAIL += 1; print(f"FAIL [{label}]: expected {exc_type.__name__} but got {type(e).__name__}: {e}")

# ── Section 1: __all__ exports (29 symbols) ──────────────────────────────────
from lib.reliability.human_feedback_memory import __all__ as HFM_ALL
EXPECTED_EXPORTS = {
    "HumanFeedbackActor","HumanFeedbackDecision","HumanFeedbackEventType",
    "HumanFeedbackMemoryStatus","HumanFeedbackOutcome","HumanFeedbackReasonType",
    "HumanFeedbackTargetType","HumanFeedbackEntry","HumanFeedbackMemoryInputBundle",
    "HumanFeedbackMemoryLogEntry","HumanFeedbackMemoryRecord","HumanFeedbackMemoryReport",
    "HumanFeedbackMemorySummary","HumanFeedbackSourceRef","HumanFeedbackTargetRef",
    "build_human_feedback_entry","build_human_feedback_memory_log_entry",
    "build_human_feedback_memory_record","build_human_feedback_memory_report",
    "build_human_feedback_target_ref","collect_human_feedback_memory_artifact_refs",
    "collect_human_feedback_memory_evidence_ids","collect_human_feedback_memory_source_ids",
    "determine_human_feedback_memory_status","human_feedback_memory_tool_result_from_report",
    "make_human_feedback_memory_log_entry_id","make_human_feedback_memory_record_id",
    "make_human_feedback_memory_report_id","summarize_human_feedback_memory",
}
check("1.1 __all__ count == 29", len(HFM_ALL) == 29, len(HFM_ALL))
check("1.2 __all__ no missing symbols", EXPECTED_EXPORTS == set(HFM_ALL), set(HFM_ALL) - EXPECTED_EXPORTS)
check("1.3 __all__ no extra symbols", set(HFM_ALL) - EXPECTED_EXPORTS == set())

# ── Section 2: No forbidden dependencies ────────────────────────────────────
import ast, pathlib
_src = pathlib.Path("/home/hchxie/projects/investment-agents/lib/reliability/human_feedback_memory.py").read_text()
_forbidden = ["streamlit","anthropic","alpaca_trade_api","finnhub","polygon","requests","httpx","aiohttp","boto","flask","django","sqlalchemy","psycopg","pymongo","redis","celery","kafka","pika","broker","brokerage","order_management"]
for _dep in _forbidden:
    check(f"2.x no-import:{_dep}", _dep not in _src.lower() or f"import {_dep}" not in _src.lower())

# ── Section 3: HumanFeedbackSourceRef ────────────────────────────────────────
from lib.reliability.human_feedback_memory import HumanFeedbackSourceRef
ref3a = HumanFeedbackSourceRef(source_id="src1", source_type="thesis_memory")
check("3.1 SourceRef basic construction", ref3a.source_id == "src1")
check("3.2 SourceRef source_type stored", ref3a.source_type == "thesis_memory")
check("3.3 SourceRef target_type optional None", ref3a.target_type is None)
check("3.4 SourceRef warnings default empty", ref3a.warnings == [])
ref3b = HumanFeedbackSourceRef(source_id="s2", target_type="allocation_memory", evidence_id="ev1")
check("3.5 SourceRef target_type set", ref3b.target_type == "allocation_memory")
check("3.6 SourceRef evidence_id stored", ref3b.evidence_id == "ev1")
expect_error("3.7 SourceRef empty source_id", lambda: HumanFeedbackSourceRef(source_id=""), ValueError)
expect_error("3.8 SourceRef whitespace source_id", lambda: HumanFeedbackSourceRef(source_id="   "), ValueError)
expect_error("3.9 SourceRef extra field rejected", lambda: HumanFeedbackSourceRef(source_id="x", unknown_field="y"), Exception)

# ── Section 4: HumanFeedbackTargetRef ────────────────────────────────────────
from lib.reliability.human_feedback_memory import HumanFeedbackTargetRef
ref4 = HumanFeedbackTargetRef(target_ref_id="tref1", target_id="run_abc", target_type="research_run_memory")
check("4.1 TargetRef construction", ref4.target_id == "run_abc")
check("4.2 TargetRef target_type set", ref4.target_type == "research_run_memory")
check("4.3 TargetRef default source_refs empty", ref4.source_refs == [])
check("4.4 TargetRef default evidence_ids empty", ref4.evidence_ids == [])
expect_error("4.5 TargetRef empty target_ref_id", lambda: HumanFeedbackTargetRef(target_ref_id="", target_id="t1"), ValueError)
expect_error("4.6 TargetRef whitespace target_id", lambda: HumanFeedbackTargetRef(target_ref_id="r1", target_id="  "), ValueError)
expect_error("4.7 TargetRef extra field rejected", lambda: HumanFeedbackTargetRef(target_ref_id="r", target_id="t", _bad="x"), Exception)

# ── Section 5: HumanFeedbackEntry ────────────────────────────────────────────
from lib.reliability.human_feedback_memory import HumanFeedbackEntry
entry5a = HumanFeedbackEntry(feedback_id="fb1", feedback_text="Looks good", decision="accepted")
check("5.1 Entry basic construction", entry5a.feedback_id == "fb1")
check("5.2 Entry decision stored", entry5a.decision == "accepted")
check("5.3 Entry approved_for_execution always False", entry5a.approved_for_execution is False)
check("5.4 Entry warnings default empty", entry5a.warnings == [])

expect_error("5.5 Entry approved_for_execution=True raises", lambda: HumanFeedbackEntry(feedback_id="x", feedback_text="t", approved_for_execution=True), ValueError, "approved_for_execution")
expect_error("5.6 Entry empty feedback_id raises", lambda: HumanFeedbackEntry(feedback_id="", feedback_text="t"), ValueError)
expect_error("5.7 Entry whitespace feedback_text raises", lambda: HumanFeedbackEntry(feedback_id="x", feedback_text="   "), ValueError)

# Confidence bounds
entry5b = HumanFeedbackEntry(feedback_id="f2", feedback_text="ok", confidence_adjustment=0.5)
check("5.8 Entry confidence 0.5 ok", entry5b.confidence_adjustment == 0.5)
entry5c = HumanFeedbackEntry(feedback_id="f3", feedback_text="ok", original_confidence=0.0)
check("5.9 Entry confidence 0.0 ok", entry5c.original_confidence == 0.0)
entry5d = HumanFeedbackEntry(feedback_id="f4", feedback_text="ok", adjusted_confidence=1.0)
check("5.10 Entry confidence 1.0 ok", entry5d.adjusted_confidence == 1.0)
expect_error("5.11 Entry confidence_adjustment >1 raises", lambda: HumanFeedbackEntry(feedback_id="x", feedback_text="t", confidence_adjustment=1.1), ValueError)
expect_error("5.12 Entry confidence_adjustment <0 raises", lambda: HumanFeedbackEntry(feedback_id="x", feedback_text="t", confidence_adjustment=-0.1), ValueError)
expect_error("5.13 Entry original_confidence >1 raises", lambda: HumanFeedbackEntry(feedback_id="x", feedback_text="t", original_confidence=2.0), ValueError)

# overrode without override_reason → hard validation failure (Phase 4M-F Codex fix)
expect_error(
    "5.14 overrode no override_reason raises ValueError",
    lambda: HumanFeedbackEntry(feedback_id="f5", feedback_text="override note", decision="overrode"),
    ValueError, "override_reason"
)
expect_error(
    "5.15 overrode with empty-string override_reason raises ValueError",
    lambda: HumanFeedbackEntry(feedback_id="f5b", feedback_text="override note", decision="overrode", override_reason=""),
    ValueError, "override_reason"
)
expect_error(
    "5.15a overrode with whitespace-only override_reason raises ValueError",
    lambda: HumanFeedbackEntry(feedback_id="f5c", feedback_text="override note", decision="overrode", override_reason="   "),
    ValueError, "override_reason"
)

# overrode WITH override_reason → constructs cleanly
entry5f = HumanFeedbackEntry(feedback_id="f6", feedback_text="override note", decision="overrode", override_reason="Market conditions changed")
check("5.16 overrode with override_reason constructs", entry5f.decision == "overrode")
check("5.16a overrode with override_reason no warnings", len(entry5f.warnings) == 0)
check("5.16b overrode with override_reason stored", entry5f.override_reason == "Market conditions changed")

# rejected with unknown reason_type → soft warning (not overrode → no override_reason required)
entry5g = HumanFeedbackEntry(feedback_id="f7", feedback_text="rejected this", decision="rejected", reason_type="unknown")
check("5.17 rejected with unknown reason_type gets warning", len(entry5g.warnings) > 0)
check("5.17a rejected does not require override_reason", entry5g.override_reason is None)

# rejected with specific reason_type → no warning
entry5h = HumanFeedbackEntry(feedback_id="f8", feedback_text="rejected", decision="rejected", reason_type="risk_too_high")
check("5.18 rejected with specific reason_type no warning", len(entry5h.warnings) == 0)

# needs_revision with unknown reason_type → soft warning (not overrode → no override_reason required)
entry5i = HumanFeedbackEntry(feedback_id="f9", feedback_text="revise this", decision="needs_revision")
check("5.19 needs_revision with unknown reason_type gets warning", len(entry5i.warnings) > 0)
check("5.19a needs_revision does not require override_reason", entry5i.override_reason is None)

# accepted, skipped, deferred, executed_manually, unknown should not require override_reason
for _dec in ("accepted","skipped","deferred","executed_manually","unknown"):
    _e = HumanFeedbackEntry(feedback_id=f"f_{_dec}", feedback_text="t", decision=_dec)
    check(f"5.19b decision={_dec!r} does not require override_reason", _e.decision == _dec and _e.override_reason is None)

# executed_manually is allowed (memory label)
entry5j = HumanFeedbackEntry(feedback_id="f10", feedback_text="executed manually by user", decision="executed_manually")
check("5.20 executed_manually accepted", entry5j.decision == "executed_manually")
check("5.21 executed_manually approved_for_execution still False", entry5j.approved_for_execution is False)
# Re-confirm approved_for_execution=True rejection still holds (safety regression guard)
expect_error("5.21a Entry approved_for_execution=True still rejected", lambda: HumanFeedbackEntry(feedback_id="x", feedback_text="t", approved_for_execution=True), ValueError, "approved_for_execution")

# No broker/order/account fields
for _field in ["order_id","account_id","brokerage","broker","execution_id","trade_id"]:
    check(f"5.22 no-field:{_field}", not hasattr(entry5a, _field))

print(f"\n--- Sections 1-5 complete ---")
# ── Section 6: HumanFeedbackMemoryLogEntry ───────────────────────────────────
from lib.reliability.human_feedback_memory import HumanFeedbackMemoryLogEntry
log6 = HumanFeedbackMemoryLogEntry(event_id="ev1", event_type="feedback_recorded", created_at="2025-01-01T00:00:00Z", description="Test event")
check("6.1 LogEntry construction", log6.event_id == "ev1")
check("6.2 LogEntry event_type stored", log6.event_type == "feedback_recorded")
check("6.3 LogEntry default actor=system", log6.actor == "system")
check("6.4 LogEntry source_ids empty default", log6.source_ids == [])
expect_error("6.5 LogEntry empty event_id raises", lambda: HumanFeedbackMemoryLogEntry(event_id="", event_type="unknown", created_at="t", description="d"), ValueError)
expect_error("6.6 LogEntry whitespace created_at raises", lambda: HumanFeedbackMemoryLogEntry(event_id="e1", event_type="unknown", created_at="  ", description="d"), ValueError)
expect_error("6.7 LogEntry whitespace description raises", lambda: HumanFeedbackMemoryLogEntry(event_id="e1", event_type="unknown", created_at="t", description="   "), ValueError)
expect_error("6.8 LogEntry extra field rejected", lambda: HumanFeedbackMemoryLogEntry(event_id="e", event_type="unknown", created_at="t", description="d", _x="y"), Exception)

# ── Section 7: HumanFeedbackMemoryRecord ─────────────────────────────────────
from lib.reliability.human_feedback_memory import HumanFeedbackMemoryRecord, HumanFeedbackTargetRef, HumanFeedbackEntry

_tref7 = HumanFeedbackTargetRef(target_ref_id="tr1", target_id="run1", target_type="thesis_memory")
_entry7 = HumanFeedbackEntry(feedback_id="fe1", feedback_text="ok", decision="accepted")

rec7 = HumanFeedbackMemoryRecord(
    feedback_memory_id="hfm_test1", target="AAPL", target_ref=_tref7,
    feedback_entries=[_entry7], recorded_at="2025-01-01T00:00:00Z"
)
check("7.1 Record construction", rec7.feedback_memory_id == "hfm_test1")
check("7.2 Record target stored", rec7.target == "AAPL")
check("7.3 Record approved_for_execution always False", rec7.approved_for_execution is False)
check("7.4 Record event_log auto-populated", isinstance(rec7.event_log, list))

expect_error("7.5 Record approved_for_execution=True raises", lambda: HumanFeedbackMemoryRecord(
    feedback_memory_id="x", target="T", target_ref=_tref7,
    feedback_entries=[_entry7], recorded_at="t", approved_for_execution=True
), ValueError, "approved_for_execution")

expect_error("7.6 Record empty feedback_entries raises", lambda: HumanFeedbackMemoryRecord(
    feedback_memory_id="x", target="T", target_ref=_tref7,
    feedback_entries=[], recorded_at="t"
), ValueError, "feedback_entries")

expect_error("7.7 Record whitespace feedback_memory_id raises", lambda: HumanFeedbackMemoryRecord(
    feedback_memory_id="   ", target="T", target_ref=_tref7,
    feedback_entries=[_entry7], recorded_at="t"
), ValueError)

expect_error("7.8 Record whitespace recorded_at raises", lambda: HumanFeedbackMemoryRecord(
    feedback_memory_id="x", target="T", target_ref=_tref7,
    feedback_entries=[_entry7], recorded_at="   "
), ValueError)

# ── Section 8: HumanFeedbackMemorySummary ────────────────────────────────────
from lib.reliability.human_feedback_memory import HumanFeedbackMemorySummary
sum8 = HumanFeedbackMemorySummary(target="AAPL", status="recorded")
check("8.1 Summary construction", sum8.target == "AAPL")
check("8.2 Summary approved_for_execution always False", sum8.approved_for_execution is False)
check("8.3 Summary record_count default 0", sum8.record_count == 0)
check("8.4 Summary manual_execution_count present", hasattr(sum8, "manual_execution_count"))
expect_error("8.5 Summary approved_for_execution=True raises", lambda: HumanFeedbackMemorySummary(target="T", approved_for_execution=True), ValueError, "approved_for_execution")
expect_error("8.6 Summary extra field rejected", lambda: HumanFeedbackMemorySummary(target="T", _bad="x"), Exception)

# ── Section 9: HumanFeedbackMemoryReport ─────────────────────────────────────
from lib.reliability.human_feedback_memory import HumanFeedbackMemoryReport, HumanFeedbackMemorySummary
_sum9 = HumanFeedbackMemorySummary(target="AAPL", status="recorded")
rpt9 = HumanFeedbackMemoryReport(
    report_id="hfmrpt_test", target="AAPL", status="recorded",
    summary=_sum9, created_at="2025-01-01T00:00:00Z", updated_at="2025-01-01T00:00:00Z"
)
check("9.1 Report construction", rpt9.report_id == "hfmrpt_test")
check("9.2 Report approved_for_execution always False", rpt9.approved_for_execution is False)
check("9.3 Report calculation_version set", "human_feedback_memory_v1" in rpt9.calculation_version)
expect_error("9.4 Report approved_for_execution=True raises", lambda: HumanFeedbackMemoryReport(
    report_id="x", target="T", summary=_sum9, created_at="t", updated_at="t", approved_for_execution=True
), ValueError, "approved_for_execution")
expect_error("9.5 Report extra field rejected", lambda: HumanFeedbackMemoryReport(
    report_id="x", target="T", summary=_sum9, created_at="t", updated_at="t", _bad="y"
), Exception)

# ── Section 10: HumanFeedbackMemoryInputBundle ───────────────────────────────
from lib.reliability.human_feedback_memory import HumanFeedbackMemoryInputBundle
bundle10 = HumanFeedbackMemoryInputBundle(target="TSLA")
check("10.1 Bundle minimal construction", bundle10.target == "TSLA")
check("10.2 Bundle all upstream slots None by default", all(
    getattr(bundle10, a) is None for a in [
        "research_run_memory_record","thesis_memory_report","event_memory_report",
        "allocation_memory_report","option_trade_memory_report","decision_packet",
        "human_review_report","review_loop_report"
    ]
))
check("10.3 Bundle source_ids empty default", bundle10.source_ids == [])
expect_error("10.4 Bundle whitespace target raises", lambda: HumanFeedbackMemoryInputBundle(target="   "), ValueError)
expect_error("10.5 Bundle extra field rejected", lambda: HumanFeedbackMemoryInputBundle(target="X", _bad="y"), Exception)

# Can accept arbitrary objects (duck typing)
class _MockReport:
    source_ids = ["sid1"]; evidence_ids = ["ev1"]; evidence_id = "ev2"; report_id = "r1"; status = "unknown"
bundle10b = HumanFeedbackMemoryInputBundle(target="TSLA", thesis_memory_report=_MockReport())
check("10.6 Bundle accepts arbitrary upstream artifacts", bundle10b.thesis_memory_report is not None)

print(f"\n--- Sections 6-10 complete ---")
# ── Section 11: build_human_feedback_target_ref ───────────────────────────────
from lib.reliability.human_feedback_memory import build_human_feedback_target_ref, HumanFeedbackSourceRef
tref11 = build_human_feedback_target_ref(target_id="run_abc", target_type="research_run_memory", run_id="run1")
check("11.1 build_target_ref returns HumanFeedbackTargetRef", hasattr(tref11, "target_ref_id"))
check("11.2 build_target_ref target_id stored", tref11.target_id == "run_abc")
check("11.3 build_target_ref target_type stored", tref11.target_type == "research_run_memory")
check("11.4 build_target_ref target_ref_id prefixed hftref_", tref11.target_ref_id.startswith("hftref_"))
check("11.5 build_target_ref run_id stored", tref11.run_id == "run1")

# source_refs dedup
_sr1 = HumanFeedbackSourceRef(source_id="s1"); _sr2 = HumanFeedbackSourceRef(source_id="s2")
_sr1b = HumanFeedbackSourceRef(source_id="s1", label="dup")
tref11b = build_human_feedback_target_ref(target_id="t", source_refs=[_sr1, _sr2, _sr1b])
check("11.6 build_target_ref source_refs deduped", len(tref11b.source_refs) == 2)
check("11.7 build_target_ref first occurrence wins", tref11b.source_refs[0].label is None)

# evidence_ids dedup
tref11c = build_human_feedback_target_ref(target_id="t", evidence_ids=["ev1","ev2","ev1"])
check("11.8 build_target_ref evidence_ids deduped", tref11c.evidence_ids == ["ev1","ev2"])

# stability: same inputs → same ID
tref11d = build_human_feedback_target_ref(target_id="run_abc", target_type="research_run_memory", run_id="run1")
check("11.9 build_target_ref ID stable", tref11.target_ref_id == tref11d.target_ref_id)

# sensitivity: different target_id → different ID
tref11e = build_human_feedback_target_ref(target_id="run_xyz", target_type="research_run_memory", run_id="run1")
check("11.10 build_target_ref ID sensitive to target_id", tref11.target_ref_id != tref11e.target_ref_id)

# ── Section 12: build_human_feedback_entry ────────────────────────────────────
from lib.reliability.human_feedback_memory import build_human_feedback_entry
fe12 = build_human_feedback_entry(feedback_id="fe1", feedback_text="All good", decision="accepted", reason_type="preference")
check("12.1 build_entry returns HumanFeedbackEntry", hasattr(fe12, "feedback_id"))
check("12.2 build_entry decision stored", fe12.decision == "accepted")
check("12.3 build_entry approved_for_execution False", fe12.approved_for_execution is False)
check("12.4 build_entry created_at defaults to epoch", fe12.created_at == "1970-01-01T00:00:00Z")

fe12b = build_human_feedback_entry(feedback_id="fe2", feedback_text="note", decision="overrode", override_reason="New data arrived")
check("12.5 build_entry overrode with override_reason no warnings", len(fe12b.warnings) == 0)

# source_refs dedup in entry builder
_sr12a = HumanFeedbackSourceRef(source_id="sa"); _sr12b = HumanFeedbackSourceRef(source_id="sa", label="dup")
fe12c = build_human_feedback_entry(feedback_id="fe3", feedback_text="t", source_refs=[_sr12a, _sr12b])
check("12.6 build_entry source_refs deduped", len(fe12c.source_refs) == 1)

# ── Section 13: build_human_feedback_memory_log_entry ─────────────────────────
from lib.reliability.human_feedback_memory import build_human_feedback_memory_log_entry, make_human_feedback_memory_log_entry_id
le13 = build_human_feedback_memory_log_entry(
    event_type="feedback_recorded", description="Test log entry",
    feedback_memory_id="hfm_abc", created_at="2025-01-01T00:00:00Z"
)
check("13.1 build_log_entry returns LogEntry", hasattr(le13, "event_id"))
check("13.2 build_log_entry event_type stored", le13.event_type == "feedback_recorded")
check("13.3 build_log_entry event_id prefixed hfmev_", le13.event_id.startswith("hfmev_"))
check("13.4 build_log_entry description stored", le13.description == "Test log entry")
check("13.5 build_log_entry default actor=system", le13.actor == "system")

# stability
le13b = build_human_feedback_memory_log_entry(
    event_type="feedback_recorded", description="Test log entry",
    feedback_memory_id="hfm_abc", created_at="2025-01-01T00:00:00Z"
)
check("13.6 build_log_entry ID stable", le13.event_id == le13b.event_id)

# ── Section 14: build_human_feedback_memory_record ───────────────────────────
from lib.reliability.human_feedback_memory import build_human_feedback_memory_record, build_human_feedback_target_ref, build_human_feedback_entry
_tref14 = build_human_feedback_target_ref(target_id="run1", target_type="research_run_memory")
_entry14 = build_human_feedback_entry(feedback_id="fe1", feedback_text="ok", decision="accepted")
rec14 = build_human_feedback_memory_record(
    target="AAPL", target_ref=_tref14, feedback_entries=[_entry14],
    outcome="positive", run_id="r1", as_of="2025-01-01T00:00:00Z"
)
check("14.1 build_record returns Record", hasattr(rec14, "feedback_memory_id"))
check("14.2 build_record feedback_memory_id prefixed hfm_", rec14.feedback_memory_id.startswith("hfm_"))
check("14.3 build_record target stored", rec14.target == "AAPL")
check("14.4 build_record outcome stored", rec14.outcome == "positive")
check("14.5 build_record approved_for_execution False", rec14.approved_for_execution is False)
check("14.6 build_record event_log has feedback_recorded entry", any(e.event_type == "feedback_recorded" for e in rec14.event_log))
check("14.7 build_record event_log has outcome_updated for positive", any(e.event_type == "outcome_updated" for e in rec14.event_log))

# with agent_evaluation_flag
rec14b = build_human_feedback_memory_record(
    target="AAPL", target_ref=_tref14, feedback_entries=[_entry14],
    agent_evaluation_flag=True, as_of="2025-01-01T00:00:00Z"
)
check("14.8 build_record event_log has agent_evaluation_flagged", any(e.event_type == "agent_evaluation_flagged" for e in rec14b.event_log))

# with lesson
rec14c = build_human_feedback_memory_record(
    target="AAPL", target_ref=_tref14, feedback_entries=[_entry14],
    lesson="Always check macro first.", as_of="2025-01-01T00:00:00Z"
)
check("14.9 build_record event_log has lesson_added", any(e.event_type == "lesson_added" for e in rec14c.event_log))

# stability: same inputs → same ID
rec14d = build_human_feedback_memory_record(
    target="AAPL", target_ref=_tref14, feedback_entries=[_entry14],
    outcome="positive", run_id="r1", as_of="2025-01-01T00:00:00Z"
)
check("14.10 build_record ID stable", rec14.feedback_memory_id == rec14d.feedback_memory_id)

# source_refs dedup at record level
_sr14a = HumanFeedbackSourceRef(source_id="sa"); _sr14b = HumanFeedbackSourceRef(source_id="sa")
rec14e = build_human_feedback_memory_record(
    target="AAPL", target_ref=_tref14, feedback_entries=[_entry14],
    source_refs=[_sr14a, _sr14b], as_of="2025-01-01T00:00:00Z"
)
check("14.11 build_record source_refs deduped", len(rec14e.source_refs) == 1)

print(f"\n--- Sections 11-14 complete ---")
# ── Section 15: build_human_feedback_memory_report ───────────────────────────
from lib.reliability.human_feedback_memory import (
    build_human_feedback_memory_report, HumanFeedbackMemoryInputBundle,
    build_human_feedback_memory_record, build_human_feedback_target_ref,
    build_human_feedback_entry
)
_tref15 = build_human_feedback_target_ref(target_id="run1", target_type="thesis_memory")
_entry15 = build_human_feedback_entry(feedback_id="fe1", feedback_text="ok", decision="accepted")
_rec15 = build_human_feedback_memory_record(
    target="NVDA", target_ref=_tref15, feedback_entries=[_entry15],
    as_of="2025-01-01T00:00:00Z"
)
_bundle15 = HumanFeedbackMemoryInputBundle(target="NVDA", as_of="2025-01-01T00:00:00Z")
rpt15 = build_human_feedback_memory_report(input_bundle=_bundle15, records=[_rec15])
check("15.1 build_report returns Report", hasattr(rpt15, "report_id"))
check("15.2 build_report report_id prefixed hfmrpt_", rpt15.report_id.startswith("hfmrpt_"))
check("15.3 build_report target stored", rpt15.target == "NVDA")
check("15.4 build_report approved_for_execution False", rpt15.approved_for_execution is False)
check("15.5 build_report summary.record_count == 1", rpt15.summary.record_count == 1)
check("15.6 build_report summary.feedback_count == 1", rpt15.summary.feedback_count == 1)
check("15.7 build_report summary.accepted_count == 1", rpt15.summary.accepted_count == 1)
check("15.8 build_report calculation_version set", rpt15.calculation_version == "human_feedback_memory_v1")
check("15.9 build_report warnings includes missing optional artifact hints",
    any("Missing optional" in w or "missing" in w.lower() for w in rpt15.warnings))

# empty records → status=unknown
rpt15b = build_human_feedback_memory_report(input_bundle=_bundle15, records=[])
check("15.10 build_report no records status=unknown", rpt15b.status == "unknown")

# stability
rpt15c = build_human_feedback_memory_report(input_bundle=_bundle15, records=[_rec15])
check("15.11 build_report report_id stable", rpt15.report_id == rpt15c.report_id)

print(f"\n--- Section 15 complete ---")

# ── Section 16: make_human_feedback_memory_record_id ─────────────────────────
from lib.reliability.human_feedback_memory import make_human_feedback_memory_record_id
_id16a = make_human_feedback_memory_record_id("run1","thesis_memory",["accepted"],["preference"],["ok"],[None],"positive",run_id="r1",as_of="2025-01-01T00:00:00Z")
_id16b = make_human_feedback_memory_record_id("run1","thesis_memory",["accepted"],["preference"],["ok"],[None],"positive",run_id="r1",as_of="2025-01-01T00:00:00Z")
check("16.1 record_id prefixed hfm_", _id16a.startswith("hfm_"))
check("16.2 record_id stable", _id16a == _id16b)

# sensitivity checks
_id16c = make_human_feedback_memory_record_id("run2","thesis_memory",["accepted"],["preference"],["ok"],[None],"positive",run_id="r1",as_of="2025-01-01T00:00:00Z")
check("16.3 record_id sensitive to target_id", _id16a != _id16c)
_id16d = make_human_feedback_memory_record_id("run1","thesis_memory",["rejected"],["preference"],["ok"],[None],"positive",run_id="r1",as_of="2025-01-01T00:00:00Z")
check("16.4 record_id sensitive to decisions", _id16a != _id16d)
_id16e = make_human_feedback_memory_record_id("run1","thesis_memory",["accepted"],["risk_too_high"],["ok"],[None],"positive",run_id="r1",as_of="2025-01-01T00:00:00Z")
check("16.5 record_id sensitive to reason_types", _id16a != _id16e)
_id16f = make_human_feedback_memory_record_id("run1","thesis_memory",["accepted"],["preference"],["different text"],[None],"positive",run_id="r1",as_of="2025-01-01T00:00:00Z")
check("16.6 record_id sensitive to feedback_texts", _id16a != _id16f)
_id16g = make_human_feedback_memory_record_id("run1","thesis_memory",["accepted"],["preference"],["ok"],[None],"negative",run_id="r1",as_of="2025-01-01T00:00:00Z")
check("16.7 record_id sensitive to outcome", _id16a != _id16g)
_id16h = make_human_feedback_memory_record_id("run1","thesis_memory",["accepted"],["preference"],["ok"],["override note"],"positive",run_id="r1",as_of="2025-01-01T00:00:00Z")
check("16.8 record_id sensitive to override_reasons", _id16a != _id16h)
_id16i = make_human_feedback_memory_record_id("run1","thesis_memory",["accepted"],["preference"],["ok"],[None],"positive",run_id="r2",as_of="2025-01-01T00:00:00Z")
check("16.9 record_id sensitive to run_id", _id16a != _id16i)
_id16j = make_human_feedback_memory_record_id("run1","thesis_memory",["accepted"],["preference"],["ok"],[None],"positive",run_id="r1",as_of="2025-06-01T00:00:00Z")
check("16.10 record_id sensitive to as_of", _id16a != _id16j)

# ── Section 17: make_human_feedback_memory_log_entry_id ──────────────────────
from lib.reliability.human_feedback_memory import make_human_feedback_memory_log_entry_id
_lid17a = make_human_feedback_memory_log_entry_id("hfm_abc","feedback_recorded","2025-01-01T00:00:00Z")
_lid17b = make_human_feedback_memory_log_entry_id("hfm_abc","feedback_recorded","2025-01-01T00:00:00Z")
check("17.1 log_entry_id prefixed hfmev_", _lid17a.startswith("hfmev_"))
check("17.2 log_entry_id stable", _lid17a == _lid17b)
_lid17c = make_human_feedback_memory_log_entry_id("hfm_xyz","feedback_recorded","2025-01-01T00:00:00Z")
check("17.3 log_entry_id sensitive to feedback_memory_id", _lid17a != _lid17c)
_lid17d = make_human_feedback_memory_log_entry_id("hfm_abc","outcome_updated","2025-01-01T00:00:00Z")
check("17.4 log_entry_id sensitive to event_type", _lid17a != _lid17d)
_lid17e = make_human_feedback_memory_log_entry_id("hfm_abc","feedback_recorded","2026-01-01T00:00:00Z")
check("17.5 log_entry_id sensitive to created_at", _lid17a != _lid17e)

# ── Section 18: make_human_feedback_memory_report_id ─────────────────────────
from lib.reliability.human_feedback_memory import make_human_feedback_memory_report_id
_rid18a = make_human_feedback_memory_report_id("AAPL","2025-01-01T00:00:00Z",run_id="r1")
_rid18b = make_human_feedback_memory_report_id("AAPL","2025-01-01T00:00:00Z",run_id="r1")
check("18.1 report_id prefixed hfmrpt_", _rid18a.startswith("hfmrpt_"))
check("18.2 report_id stable", _rid18a == _rid18b)
_rid18c = make_human_feedback_memory_report_id("MSFT","2025-01-01T00:00:00Z",run_id="r1")
check("18.3 report_id sensitive to target", _rid18a != _rid18c)
_rid18d = make_human_feedback_memory_report_id("AAPL","2026-01-01T00:00:00Z",run_id="r1")
check("18.4 report_id sensitive to as_of", _rid18a != _rid18d)
_rid18e = make_human_feedback_memory_report_id("AAPL","2025-01-01T00:00:00Z",run_id="r2")
check("18.5 report_id sensitive to run_id", _rid18a != _rid18e)

print(f"\n--- Sections 16-18 complete ---")
# ── Section 19: _derive_record_status (via build_record) ─────────────────────
from lib.reliability.human_feedback_memory import build_human_feedback_memory_record, build_human_feedback_target_ref, build_human_feedback_entry

_tref19 = build_human_feedback_target_ref(target_id="run1", target_type="thesis_memory")

def _make_rec19(decision, review_required=False, initial_status=None, hrr_blocked=False):
    _override_reason = "audit reason" if decision == "overrode" else None
    entry = build_human_feedback_entry(
        feedback_id="fe1", feedback_text="ok", decision=decision,
        override_reason=_override_reason,
    )
    return build_human_feedback_memory_record(
        target="T", target_ref=_tref19, feedback_entries=[entry],
        review_required=review_required, initial_status=initial_status,
        hrr_blocked=hrr_blocked, as_of="2025-01-01T00:00:00Z"
    )

check("19.1 status=recorded for accepted decision", _make_rec19("accepted").status == "recorded")
check("19.2 status=recorded for skipped decision", _make_rec19("skipped").status == "recorded")
check("19.3 status=recorded for deferred decision", _make_rec19("deferred").status == "recorded")
check("19.4 status=recorded for executed_manually decision", _make_rec19("executed_manually").status == "recorded")
check("19.5 status=needs_review for rejected decision", _make_rec19("rejected").status == "needs_review")
check("19.6 status=needs_review for overrode decision", _make_rec19("overrode").status == "needs_review")
check("19.7 status=needs_review for needs_revision decision", _make_rec19("needs_revision").status == "needs_review")
check("19.8 status=needs_review when review_required=True", _make_rec19("accepted", review_required=True).status == "needs_review")
check("19.9 status=blocked when hrr_blocked=True", _make_rec19("accepted", hrr_blocked=True).status == "blocked")
check("19.10 initial_status overrides derived status", _make_rec19("rejected", initial_status="resolved").status == "resolved")

# ── Section 20: determine_human_feedback_memory_status ───────────────────────
from lib.reliability.human_feedback_memory import determine_human_feedback_memory_status, HumanFeedbackMemoryInputBundle

def _make_recs20(statuses):
    results = []
    for i, s in enumerate(statuses):
        entry = build_human_feedback_entry(feedback_id=f"fe{i}", feedback_text="ok", decision="accepted")
        tref = build_human_feedback_target_ref(target_id=f"run{i}", target_type="thesis_memory")
        rec = build_human_feedback_memory_record(
            target="T", target_ref=tref, feedback_entries=[entry],
            initial_status=s, as_of="2025-01-01T00:00:00Z"
        )
        results.append(rec)
    return results

# no records → unknown
_st20, _w20 = determine_human_feedback_memory_status([], None)
check("20.1 no records → unknown", _st20 == "unknown")
check("20.2 no records → warning issued", len(_w20) > 0)

# blocked wins
_st20b, _ = determine_human_feedback_memory_status(_make_recs20(["blocked","recorded"]), None)
check("20.3 any blocked → blocked", _st20b == "blocked")

# needs_review
_st20c, _ = determine_human_feedback_memory_status(_make_recs20(["needs_review","recorded"]), None)
check("20.4 any needs_review → needs_review", _st20c == "needs_review")

# all resolved
_st20d, _ = determine_human_feedback_memory_status(_make_recs20(["resolved","resolved"]), None)
check("20.5 all resolved → resolved", _st20d == "resolved")

# all recorded
_st20e, _ = determine_human_feedback_memory_status(_make_recs20(["recorded","recorded"]), None)
check("20.6 all recorded → recorded", _st20e == "recorded")

# all archived
_st20f, _ = determine_human_feedback_memory_status(_make_recs20(["archived","archived"]), None)
check("20.7 all archived → archived", _st20f == "archived")

# mixed recorded+resolved → recorded (any recorded)
_st20g, _ = determine_human_feedback_memory_status(_make_recs20(["resolved","recorded"]), None)
check("20.8 mixed resolved+recorded → recorded", _st20g == "recorded")

# hrr blocked via input_bundle
class _BlockedHRR:
    status = "blocked"
_bundle20 = HumanFeedbackMemoryInputBundle(target="T", human_review_report=_BlockedHRR())
_bundle20_plain = HumanFeedbackMemoryInputBundle(target="T", human_review_report=_BlockedHRR())
# Manually assign human_review_report to the bundle (already done above via constructor)
_st20h, _w20h = determine_human_feedback_memory_status(_make_recs20(["recorded"]), _bundle20_plain)
check("20.9 hrr blocked → status blocked", _st20h == "blocked")
check("20.10 hrr blocked → warning issued", any("blocked" in w.lower() for w in _w20h))

print(f"\n--- Sections 19-20 complete ---")
# ── Section 21: summarize_human_feedback_memory ───────────────────────────────
from lib.reliability.human_feedback_memory import summarize_human_feedback_memory, build_human_feedback_memory_record, build_human_feedback_target_ref, build_human_feedback_entry

def _make_full_rec21(decision, outcome="unknown", review_required=False, agent_evaluation_flag=False):
    tref = build_human_feedback_target_ref(target_id="run1", target_type="thesis_memory")
    _override_reason = "audit reason" if decision == "overrode" else None
    entry = build_human_feedback_entry(
        feedback_id=f"fe_{decision}", feedback_text="ok", decision=decision,
        override_reason=_override_reason,
    )
    return build_human_feedback_memory_record(
        target="T", target_ref=tref, feedback_entries=[entry],
        outcome=outcome, review_required=review_required,
        agent_evaluation_flag=agent_evaluation_flag, as_of="2025-01-01T00:00:00Z"
    )

_recs21 = [
    _make_full_rec21("accepted"),
    _make_full_rec21("rejected"),
    _make_full_rec21("overrode"),
    _make_full_rec21("skipped"),
    _make_full_rec21("deferred"),
    _make_full_rec21("needs_revision"),
    _make_full_rec21("executed_manually"),
]
_summ21 = summarize_human_feedback_memory("T", "recorded", _recs21, [])
check("21.1 summary record_count == 7", _summ21.record_count == 7)
check("21.2 summary feedback_count == 7", _summ21.feedback_count == 7)
check("21.3 summary accepted_count == 1", _summ21.accepted_count == 1)
check("21.4 summary rejected_count == 1", _summ21.rejected_count == 1)
check("21.5 summary overrode_count == 1", _summ21.overrode_count == 1)
check("21.6 summary skipped_count == 1", _summ21.skipped_count == 1)
check("21.7 summary deferred_count == 1", _summ21.deferred_count == 1)
check("21.8 summary needs_revision_count == 1", _summ21.needs_revision_count == 1)
check("21.9 summary manual_execution_count == 1", _summ21.manual_execution_count == 1)
check("21.10 summary approved_for_execution False", _summ21.approved_for_execution is False)

# outcome counts
_recs21b = [
    _make_full_rec21("accepted", outcome="positive"),
    _make_full_rec21("accepted", outcome="avoided_loss"),
    _make_full_rec21("accepted", outcome="prevented_bad_action"),
    _make_full_rec21("rejected", outcome="negative"),
    _make_full_rec21("rejected", outcome="missed_gain"),
    _make_full_rec21("rejected", outcome="caused_bad_action"),
    _make_full_rec21("skipped", outcome="neutral"),
    _make_full_rec21("skipped", outcome="unknown"),
]
_summ21b = summarize_human_feedback_memory("T", "recorded", _recs21b, [])
check("21.11 positive_outcome_count == 3", _summ21b.positive_outcome_count == 3)
check("21.12 negative_outcome_count == 3", _summ21b.negative_outcome_count == 3)

# review_required and agent_evaluation_flag counts
_recs21c = [
    _make_full_rec21("accepted", review_required=True, agent_evaluation_flag=True),
    _make_full_rec21("accepted", review_required=True, agent_evaluation_flag=False),
    _make_full_rec21("accepted", review_required=False, agent_evaluation_flag=True),
]
_summ21c = summarize_human_feedback_memory("T", "recorded", _recs21c, [])
check("21.13 review_required_count == 2", _summ21c.review_required_count == 2)
check("21.14 agent_evaluation_flag_count == 2", _summ21c.agent_evaluation_flag_count == 2)

# unresolved_count: not in (resolved, archived, superseded, unknown)
_recs21d = [
    _make_full_rec21("accepted"),  # status=recorded → unresolved
    _make_full_rec21("accepted", review_required=True),  # status=needs_review → unresolved
]
# patch statuses to resolved/archived for two more
from lib.reliability.human_feedback_memory import HumanFeedbackMemoryRecord, HumanFeedbackTargetRef, HumanFeedbackEntry
_tref_u = build_human_feedback_target_ref(target_id="u1", target_type="thesis_memory")
_entry_u = build_human_feedback_entry(feedback_id="fu", feedback_text="ok", decision="accepted")
_rec_resolved = build_human_feedback_memory_record(target="T", target_ref=_tref_u, feedback_entries=[_entry_u], initial_status="resolved", as_of="2025-01-01T00:00:00Z")
_rec_archived = build_human_feedback_memory_record(target="T", target_ref=_tref_u, feedback_entries=[_entry_u], initial_status="archived", as_of="2025-01-01T00:00:00Z")
_summ21d = summarize_human_feedback_memory("T", "recorded", _recs21d + [_rec_resolved, _rec_archived], [])
check("21.15 unresolved_count == 2", _summ21d.unresolved_count == 2)

# top_warnings capped at 5
_warnings21 = [f"w{i}" for i in range(10)]
_summ21e = summarize_human_feedback_memory("T", "recorded", [], _warnings21)
check("21.16 top_warnings capped at 5", len(_summ21e.top_warnings) == 5)

print(f"\n--- Section 21 complete ---")
# ── Section 22: collect_human_feedback_memory_source_ids ─────────────────────
from lib.reliability.human_feedback_memory import collect_human_feedback_memory_source_ids, HumanFeedbackMemoryInputBundle

class _MockArtifact22:
    def __init__(self, source_ids=None, report_id=None):
        self.source_ids = source_ids or []
        self.report_id = report_id

_bundle22 = HumanFeedbackMemoryInputBundle(target="T", source_ids=["s_bundle"])
_sids22 = collect_human_feedback_memory_source_ids(_bundle22, [])
check("22.1 collect source_ids from bundle.source_ids", "s_bundle" in _sids22)

# Collect from upstream artifact source_ids + report_id
_bundle22b = HumanFeedbackMemoryInputBundle(
    target="T",
    thesis_memory_report=_MockArtifact22(source_ids=["s_thesis"], report_id="rpt1")
)
_sids22b = collect_human_feedback_memory_source_ids(_bundle22b, [])
check("22.2 collect from upstream artifact source_ids", "s_thesis" in _sids22b)
check("22.3 collect artifact report_id as source_id", "rpt1" in _sids22b)

# Dedup
_bundle22c = HumanFeedbackMemoryInputBundle(target="T", source_ids=["s1","s1","s2"])
_sids22c = collect_human_feedback_memory_source_ids(_bundle22c, [])
check("22.4 collect source_ids deduped", _sids22c.count("s1") == 1)
check("22.5 collect source_ids order preserved", _sids22c.index("s1") < _sids22c.index("s2"))

# Collect from records
_tref22 = build_human_feedback_target_ref(target_id="run1", target_type="thesis_memory")
_sr22 = HumanFeedbackSourceRef(source_id="s_rec")
_entry22 = build_human_feedback_entry(feedback_id="fe1", feedback_text="ok", decision="accepted")
_rec22 = build_human_feedback_memory_record(
    target="T", target_ref=_tref22, feedback_entries=[_entry22],
    source_refs=[_sr22], as_of="2025-01-01T00:00:00Z"
)
_bundle22d = HumanFeedbackMemoryInputBundle(target="T")
_sids22d = collect_human_feedback_memory_source_ids(_bundle22d, [_rec22])
check("22.6 collect source_ids from record source_refs", "s_rec" in _sids22d)

# ── Section 23: collect_human_feedback_memory_evidence_ids ───────────────────
from lib.reliability.human_feedback_memory import collect_human_feedback_memory_evidence_ids

class _MockArtifact23:
    def __init__(self, evidence_ids=None, evidence_id=None):
        self.evidence_ids = evidence_ids or []
        self.evidence_id = evidence_id

_bundle23 = HumanFeedbackMemoryInputBundle(target="T", evidence_ids=["ev_bundle"])
_eids23 = collect_human_feedback_memory_evidence_ids(_bundle23, [])
check("23.1 collect evidence_ids from bundle.evidence_ids", "ev_bundle" in _eids23)

# From upstream artifact evidence_ids list
_bundle23b = HumanFeedbackMemoryInputBundle(
    target="T",
    allocation_memory_report=_MockArtifact23(evidence_ids=["ev1","ev2"], evidence_id="ev3")
)
_eids23b = collect_human_feedback_memory_evidence_ids(_bundle23b, [])
check("23.2 collect from upstream artifact evidence_ids", "ev1" in _eids23b)
check("23.3 collect from upstream artifact evidence_ids list", "ev2" in _eids23b)
check("23.4 collect from upstream artifact evidence_id attribute", "ev3" in _eids23b)

# Dedup
_bundle23c = HumanFeedbackMemoryInputBundle(target="T", evidence_ids=["ev1","ev1","ev2"])
_eids23c = collect_human_feedback_memory_evidence_ids(_bundle23c, [])
check("23.5 collect evidence_ids deduped", _eids23c.count("ev1") == 1)

# Missing attribute safe
class _NoEvidenceArtifact:
    pass  # no evidence_ids or evidence_id
_bundle23d = HumanFeedbackMemoryInputBundle(target="T", thesis_memory_report=_NoEvidenceArtifact())
try:
    _eids23d = collect_human_feedback_memory_evidence_ids(_bundle23d, [])
    check("23.6 collect evidence_ids safe with no-attribute artifact", True)
except Exception as e:
    check("23.6 collect evidence_ids safe with no-attribute artifact", False, e)

# ── Section 24: collect_human_feedback_memory_artifact_refs ──────────────────
from lib.reliability.human_feedback_memory import collect_human_feedback_memory_artifact_refs

_bundle24 = HumanFeedbackMemoryInputBundle(target="T", artifact_refs=["ref_bundle"])
_arefs24 = collect_human_feedback_memory_artifact_refs(_bundle24, [])
check("24.1 collect artifact_refs from bundle", "ref_bundle" in _arefs24)

# From records
_tref24 = build_human_feedback_target_ref(target_id="run1", target_type="thesis_memory")
_entry24 = build_human_feedback_entry(feedback_id="fe1", feedback_text="ok", decision="accepted", artifact_refs=["ref_entry"])
_rec24 = build_human_feedback_memory_record(
    target="T", target_ref=_tref24, feedback_entries=[_entry24],
    artifact_refs=["ref_rec"], as_of="2025-01-01T00:00:00Z"
)
_bundle24b = HumanFeedbackMemoryInputBundle(target="T")
_arefs24b = collect_human_feedback_memory_artifact_refs(_bundle24b, [_rec24])
check("24.2 collect artifact_refs from record", "ref_rec" in _arefs24b)
check("24.3 collect artifact_refs from entry", "ref_entry" in _arefs24b)

# Dedup
_bundle24c = HumanFeedbackMemoryInputBundle(target="T", artifact_refs=["r1","r1","r2"])
_arefs24c = collect_human_feedback_memory_artifact_refs(_bundle24c, [])
check("24.4 collect artifact_refs deduped", _arefs24c.count("r1") == 1)

# Whitespace-only refs excluded
_bundle24d = HumanFeedbackMemoryInputBundle(target="T", artifact_refs=["  ","r1"])
_arefs24d = collect_human_feedback_memory_artifact_refs(_bundle24d, [])
check("24.5 whitespace artifact_refs excluded", "  " not in _arefs24d and "r1" in _arefs24d)

print(f"\n--- Sections 22-24 complete ---")
# ── Section 25: human_feedback_memory_tool_result_from_report (adapter) ──────
from lib.reliability.human_feedback_memory import (
    human_feedback_memory_tool_result_from_report, build_human_feedback_memory_report,
    HumanFeedbackMemoryInputBundle, build_human_feedback_memory_record,
    build_human_feedback_target_ref, build_human_feedback_entry
)
_tref25 = build_human_feedback_target_ref(target_id="run1", target_type="thesis_memory")
_entry25 = build_human_feedback_entry(feedback_id="fe1", feedback_text="ok", decision="accepted")
_rec25 = build_human_feedback_memory_record(
    target="AAPL", target_ref=_tref25, feedback_entries=[_entry25],
    as_of="2025-01-01T00:00:00Z"
)
_bundle25 = HumanFeedbackMemoryInputBundle(target="AAPL", as_of="2025-01-01T00:00:00Z")
_rpt25 = build_human_feedback_memory_report(input_bundle=_bundle25, records=[_rec25])
_tr25 = human_feedback_memory_tool_result_from_report(_rpt25, run_id="r1")

check("25.1 adapter returns ToolResult", hasattr(_tr25, "evidence_id"))
check("25.2 adapter tool_name set", _tr25.tool_name == "human_feedback_memory_report")
check("25.3 adapter evidence_id not empty", bool(_tr25.evidence_id))
check("25.4 adapter outputs.approved_for_execution False", _tr25.outputs.get("approved_for_execution") is False)
check("25.5 adapter outputs.report_id present", "report_id" in _tr25.outputs)
check("25.6 adapter outputs.record_count present", "record_count" in _tr25.outputs)
check("25.7 adapter outputs.feedback_count present", "feedback_count" in _tr25.outputs)
check("25.8 adapter outputs.review_required_count present", "review_required_count" in _tr25.outputs)
check("25.9 adapter outputs.agent_evaluation_flag_count present", "agent_evaluation_flag_count" in _tr25.outputs)
check("25.10 adapter outputs.calculation_version present", "calculation_version" in _tr25.outputs)

# evidence_id stability
_tr25b = human_feedback_memory_tool_result_from_report(_rpt25, run_id="r1")
check("25.11 adapter evidence_id stable", _tr25.evidence_id == _tr25b.evidence_id)

# evidence_id sensitivity: different report → different evidence_id
_bundle25b = HumanFeedbackMemoryInputBundle(target="MSFT", as_of="2025-01-01T00:00:00Z")
_tref25b = build_human_feedback_target_ref(target_id="run2", target_type="thesis_memory")
_rec25b = build_human_feedback_memory_record(
    target="MSFT", target_ref=_tref25b, feedback_entries=[_entry25],
    as_of="2025-01-01T00:00:00Z"
)
_rpt25b = build_human_feedback_memory_report(input_bundle=_bundle25b, records=[_rec25b])
_tr25c = human_feedback_memory_tool_result_from_report(_rpt25b, run_id="r1")
check("25.12 adapter evidence_id sensitive to report", _tr25.evidence_id != _tr25c.evidence_id)

# ── Section 26: executed_manually memory-only semantics ──────────────────────
_tref26 = build_human_feedback_target_ref(target_id="run1", target_type="option_trade_memory")
_entry26 = build_human_feedback_entry(
    feedback_id="fe_em", feedback_text="User executed trade manually",
    decision="executed_manually"
)
_rec26 = build_human_feedback_memory_record(
    target="AAPL", target_ref=_tref26, feedback_entries=[_entry26],
    as_of="2025-01-01T00:00:00Z"
)
check("26.1 executed_manually decision stored", _rec26.feedback_entries[0].decision == "executed_manually")
check("26.2 executed_manually approved_for_execution False in entry", _rec26.feedback_entries[0].approved_for_execution is False)
check("26.3 executed_manually approved_for_execution False in record", _rec26.approved_for_execution is False)
# status derived as "recorded" (not needs_review)
check("26.4 executed_manually status=recorded (not needs_review)", _rec26.status == "recorded")

_bundle26 = HumanFeedbackMemoryInputBundle(target="AAPL", as_of="2025-01-01T00:00:00Z")
_rpt26 = build_human_feedback_memory_report(input_bundle=_bundle26, records=[_rec26])
_tr26 = human_feedback_memory_tool_result_from_report(_rpt26)
check("26.5 executed_manually report approved_for_execution False", _rpt26.approved_for_execution is False)
check("26.6 executed_manually adapter approved_for_execution False", _tr26.outputs.get("approved_for_execution") is False)

# summary.manual_execution_count incremented
_summ26 = _rpt26.summary
check("26.7 executed_manually counted in manual_execution_count", _summ26.manual_execution_count == 1)
check("26.8 executed_manually accepted_count == 0", _summ26.accepted_count == 0)

print(f"\n--- Sections 25-26 complete ---")
# ── Section 27: deduplication behaviors ──────────────────────────────────────
from lib.reliability.human_feedback_memory import (
    HumanFeedbackSourceRef, build_human_feedback_target_ref,
    build_human_feedback_entry, build_human_feedback_memory_record,
    collect_human_feedback_memory_source_ids,
    collect_human_feedback_memory_evidence_ids,
    collect_human_feedback_memory_artifact_refs,
    HumanFeedbackMemoryInputBundle
)

# Source refs: first occurrence wins by source_id
_sr27a = HumanFeedbackSourceRef(source_id="dup", label="first")
_sr27b = HumanFeedbackSourceRef(source_id="dup", label="second")
_tref27 = build_human_feedback_target_ref(target_id="r1", source_refs=[_sr27a, _sr27b])
check("27.1 target_ref source_refs deduped", len(_tref27.source_refs) == 1)
check("27.2 target_ref first occurrence wins", _tref27.source_refs[0].label == "first")

# Evidence IDs dedup in target_ref builder
_tref27b = build_human_feedback_target_ref(target_id="r1", evidence_ids=["e1","e2","e1"])
check("27.3 target_ref evidence_ids deduped", _tref27b.evidence_ids == ["e1","e2"])

# Artifact refs dedup in record builder
_tref27c = build_human_feedback_target_ref(target_id="r2")
_entry27 = build_human_feedback_entry(feedback_id="fe1", feedback_text="ok")
_rec27 = build_human_feedback_memory_record(
    target="T", target_ref=_tref27c, feedback_entries=[_entry27],
    artifact_refs=["ar1","ar2","ar1"], as_of="2025-01-01T00:00:00Z"
)
check("27.4 record artifact_refs deduped", _rec27.artifact_refs == ["ar1","ar2"])

# collect functions dedup across bundle + records
_bundle27 = HumanFeedbackMemoryInputBundle(target="T", source_ids=["src_both"])
_sr27_rec = HumanFeedbackSourceRef(source_id="src_both")
_tref27d = build_human_feedback_target_ref(target_id="r3")
_rec27b = build_human_feedback_memory_record(
    target="T", target_ref=_tref27d, feedback_entries=[_entry27],
    source_refs=[_sr27_rec], as_of="2025-01-01T00:00:00Z"
)
_sids27 = collect_human_feedback_memory_source_ids(_bundle27, [_rec27b])
check("27.5 collect source_ids deduped across bundle+records", _sids27.count("src_both") == 1)

_bundle27b = HumanFeedbackMemoryInputBundle(target="T", evidence_ids=["ev_both"])
_rec27c = build_human_feedback_memory_record(
    target="T", target_ref=_tref27d, feedback_entries=[_entry27],
    evidence_ids=["ev_both"], as_of="2025-01-01T00:00:00Z"
)
_eids27 = collect_human_feedback_memory_evidence_ids(_bundle27b, [_rec27c])
check("27.6 collect evidence_ids deduped across bundle+records", _eids27.count("ev_both") == 1)

# ── Section 28: agent_evaluation_flag reporting ───────────────────────────────
from lib.reliability.human_feedback_memory import (
    build_human_feedback_memory_report, HumanFeedbackMemoryInputBundle,
    build_human_feedback_memory_record, build_human_feedback_target_ref,
    build_human_feedback_entry
)

def _make_rec28(agent_evaluation_flag=False):
    tref = build_human_feedback_target_ref(target_id="run1", target_type="thesis_memory")
    entry = build_human_feedback_entry(feedback_id="fe1", feedback_text="ok", decision="accepted")
    return build_human_feedback_memory_record(
        target="T", target_ref=tref, feedback_entries=[entry],
        agent_evaluation_flag=agent_evaluation_flag, as_of="2025-01-01T00:00:00Z"
    )

_recs28 = [_make_rec28(True), _make_rec28(True), _make_rec28(False)]
_bundle28 = HumanFeedbackMemoryInputBundle(target="T", as_of="2025-01-01T00:00:00Z")
_rpt28 = build_human_feedback_memory_report(input_bundle=_bundle28, records=_recs28)
check("28.1 agent_evaluation_flag_count == 2", _rpt28.summary.agent_evaluation_flag_count == 2)
check("28.2 agent_evaluation_flag_count in adapter outputs", _rpt28.summary.agent_evaluation_flag_count == human_feedback_memory_tool_result_from_report(_rpt28).outputs.get("agent_evaluation_flag_count"))

# ── Section 29: design doc existence ─────────────────────────────────────────
import pathlib
_doc29 = pathlib.Path("/home/hchxie/projects/investment-agents/docs/reliability_phase_4m_human_feedback_memory.md")
check("29.1 design doc exists", _doc29.exists())

# ── Final summary ─────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"RESULTS: {PASS} passed, {FAIL} failed")
if FAIL > 0:
    print("SOME TESTS FAILED")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
    sys.exit(0)