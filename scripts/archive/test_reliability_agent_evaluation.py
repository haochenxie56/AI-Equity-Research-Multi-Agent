"""
test_reliability_agent_evaluation.py
Phase 4M-G: Agent Evaluation reliability tests.

Standalone, deterministic, offline/mock-only test suite. No DB, no vector
store, no broker, no live LLM, no external API, no Streamlit, no model
training, no agent definition mutation.
"""
import sys
import pathlib

sys.path.insert(0, "/home/hchxie/projects/investment-agents")

PASS = 0
FAIL = 0


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
        fn()
        FAIL += 1
        print(f"FAIL [{label}]: expected {exc_type.__name__} but no error raised")
    except exc_type as e:
        if keyword and keyword.lower() not in str(e).lower():
            FAIL += 1
            print(
                f"FAIL [{label}]: raised {exc_type.__name__} but missing keyword "
                f"{keyword!r} in: {e}"
            )
        else:
            PASS += 1
    except Exception as e:
        FAIL += 1
        print(
            f"FAIL [{label}]: expected {exc_type.__name__} but got "
            f"{type(e).__name__}: {e}"
        )


# ── Section 1: __all__ exports ───────────────────────────────────────────────
from lib.reliability.agent_evaluation import __all__ as AE_ALL

EXPECTED_EXPORTS = {
    # Literal type aliases (8)
    "AgentEvaluationStatus",
    "EvaluatedAgentType",
    "AgentEvaluationOutcome",
    "AgentEvaluationSignalType",
    "AgentEvaluationHorizon",
    "AgentEvaluationGrade",
    "AgentEvaluationEventType",
    "AgentEvaluationActor",
    # Pydantic models (9)
    "AgentEvaluationSourceRef",
    "AgentEvaluationTargetRef",
    "AgentEvaluationSignal",
    "AgentEvaluationCalibration",
    "AgentEvaluationLogEntry",
    "AgentEvaluationRecord",
    "AgentEvaluationInputBundle",
    "AgentEvaluationSummary",
    "AgentEvaluationReport",
    # Helpers (15)
    "make_agent_evaluation_record_id",
    "make_agent_evaluation_log_entry_id",
    "make_agent_evaluation_report_id",
    "build_agent_evaluation_target_ref",
    "build_agent_evaluation_signal",
    "build_agent_evaluation_calibration",
    "build_agent_evaluation_log_entry",
    "build_agent_evaluation_record",
    "build_agent_evaluation_report",
    "determine_agent_evaluation_status",
    "collect_agent_evaluation_source_ids",
    "collect_agent_evaluation_evidence_ids",
    "collect_agent_evaluation_artifact_refs",
    "summarize_agent_evaluation",
    "agent_evaluation_tool_result_from_report",
}
check("1.1 __all__ count == 32", len(AE_ALL) == 32, len(AE_ALL))
check("1.2 __all__ no missing", EXPECTED_EXPORTS == set(AE_ALL), EXPECTED_EXPORTS - set(AE_ALL))
check("1.3 __all__ no extras", set(AE_ALL) - EXPECTED_EXPORTS == set())

# Also confirm exports are re-exported from package __init__
from lib.reliability import __all__ as PKG_ALL
for _sym in EXPECTED_EXPORTS:
    check(f"1.4.{_sym} re-exported from package", _sym in PKG_ALL)

# ── Section 2: forbidden dependencies ────────────────────────────────────────
_src = pathlib.Path(
    "/home/hchxie/projects/investment-agents/lib/reliability/agent_evaluation.py"
).read_text()
_low = _src.lower()
_forbidden = [
    "streamlit", "anthropic", "alpaca_trade_api", "finnhub", "polygon",
    "requests", "httpx", "aiohttp", "boto", "flask", "django", "sqlalchemy",
    "psycopg", "pymongo", "redis", "celery", "kafka", "pika",
    "broker", "brokerage", "order_management", "option_chain_live",
    "yfinance", "openai",
]
for _dep in _forbidden:
    check(f"2.x no-import:{_dep}", f"import {_dep}" not in _low and f"from {_dep}" not in _low)

# Also confirm no live runtime references
for _live in ["app.py", "pages/", "llm_orchestrator", "workflow_state"]:
    check(f"2.live:{_live}", _live not in _src)

# ── Section 3: AgentEvaluationSourceRef ──────────────────────────────────────
from lib.reliability.agent_evaluation import AgentEvaluationSourceRef

s3a = AgentEvaluationSourceRef(source_id="src1", source_type="thesis_memory")
check("3.1 SourceRef basic", s3a.source_id == "src1")
check("3.2 SourceRef type stored", s3a.source_type == "thesis_memory")
check("3.3 SourceRef metadata default", s3a.metadata == {})
check("3.4 SourceRef warnings default", s3a.warnings == [])
expect_error("3.5 SourceRef empty source_id",
             lambda: AgentEvaluationSourceRef(source_id=""), ValueError)
expect_error("3.6 SourceRef whitespace source_id",
             lambda: AgentEvaluationSourceRef(source_id="   "), ValueError)
expect_error("3.7 SourceRef extra field rejected",
             lambda: AgentEvaluationSourceRef(source_id="x", unknown="y"), Exception)

# ── Section 4: AgentEvaluationTargetRef ──────────────────────────────────────
from lib.reliability.agent_evaluation import AgentEvaluationTargetRef

t4 = AgentEvaluationTargetRef(
    target_ref_id="tref1", artifact_id="art1", agent_type="macro_agent"
)
check("4.1 TargetRef construction", t4.artifact_id == "art1")
check("4.2 TargetRef agent_type stored", t4.agent_type == "macro_agent")
check("4.3 TargetRef defaults empty refs", t4.source_refs == [] and t4.evidence_ids == [])
check("4.4 TargetRef horizon Optional None", t4.horizon is None)
expect_error("4.5 TargetRef empty target_ref_id",
             lambda: AgentEvaluationTargetRef(target_ref_id="", artifact_id="a1"),
             Exception)
expect_error("4.6 TargetRef whitespace artifact_id",
             lambda: AgentEvaluationTargetRef(target_ref_id="t1", artifact_id="   "),
             Exception)
expect_error("4.7 TargetRef extra field rejected",
             lambda: AgentEvaluationTargetRef(
                 target_ref_id="t1", artifact_id="a1", account_id="x"
             ), Exception)
expect_error("4.8 TargetRef invalid agent_type",
             lambda: AgentEvaluationTargetRef(
                 target_ref_id="t1", artifact_id="a1", agent_type="nope"
             ), Exception)
# No broker/order/account/execution fields:
for _bad in ("account_id", "order_id", "execution_id", "brokerage_id"):
    check(f"4.9.no-field:{_bad}",
          _bad not in AgentEvaluationTargetRef.model_fields)

# ── Section 5: AgentEvaluationSignal ─────────────────────────────────────────
from lib.reliability.agent_evaluation import AgentEvaluationSignal

s5a = AgentEvaluationSignal(
    signal_id="sg1", rationale="reason text",
    signal_type="thesis_direction", agent_type="thesis_memory",
    horizon="medium", original_confidence=0.7, evaluated_outcome="correct",
    evaluation_grade="good",
)
check("5.1 Signal construct", s5a.signal_id == "sg1")
check("5.2 Signal outcome", s5a.evaluated_outcome == "correct")
check("5.3 Signal approved_for_execution default False",
      s5a.approved_for_execution is False)
expect_error("5.4 Signal empty signal_id",
             lambda: AgentEvaluationSignal(signal_id="", rationale="r"), Exception)
expect_error("5.5 Signal whitespace rationale",
             lambda: AgentEvaluationSignal(signal_id="x", rationale="   "), Exception)
expect_error("5.6 Signal confidence > 1",
             lambda: AgentEvaluationSignal(
                 signal_id="x", rationale="r", original_confidence=1.5
             ), Exception)
expect_error("5.7 Signal confidence < 0",
             lambda: AgentEvaluationSignal(
                 signal_id="x", rationale="r", original_confidence=-0.01
             ), Exception)
expect_error("5.8 Signal approved_for_execution=True rejected",
             lambda: AgentEvaluationSignal(
                 signal_id="x", rationale="r", approved_for_execution=True
             ), ValueError, keyword="approved_for_execution")
expect_error("5.9 Signal extra field",
             lambda: AgentEvaluationSignal(
                 signal_id="x", rationale="r", broker_account="acc1"
             ), Exception)

# ── Section 6: AgentEvaluationCalibration ────────────────────────────────────
from lib.reliability.agent_evaluation import AgentEvaluationCalibration

cal6 = AgentEvaluationCalibration(
    calibration_id="cal1", agent_type="macro_agent",
    sample_count=10, correct_count=7, incorrect_count=2, partial_count=1,
    accuracy_rate=0.7, average_confidence=0.6, calibration_gap=0.1,
)
check("6.1 Calibration construct", cal6.sample_count == 10)
check("6.2 Calibration calibration_gap signed", cal6.calibration_gap == 0.1)
expect_error("6.3 Calibration neg sample_count",
             lambda: AgentEvaluationCalibration(calibration_id="c", sample_count=-1),
             Exception)
expect_error("6.4 Calibration neg correct_count",
             lambda: AgentEvaluationCalibration(calibration_id="c", correct_count=-1),
             Exception)
expect_error("6.5 Calibration accuracy_rate > 1",
             lambda: AgentEvaluationCalibration(calibration_id="c", accuracy_rate=1.5),
             Exception)
expect_error("6.6 Calibration override_rate < 0",
             lambda: AgentEvaluationCalibration(calibration_id="c", override_rate=-0.1),
             Exception)
expect_error("6.7 Calibration calibration_gap out of range",
             lambda: AgentEvaluationCalibration(calibration_id="c", calibration_gap=1.5),
             Exception)
expect_error("6.8 Calibration empty id",
             lambda: AgentEvaluationCalibration(calibration_id=""), Exception)
# Negative calibration_gap allowed (signed)
cal6_neg = AgentEvaluationCalibration(
    calibration_id="cnegtest", accuracy_rate=0.3, average_confidence=0.8,
    calibration_gap=-0.5,
)
check("6.9 Calibration negative calibration_gap allowed",
      cal6_neg.calibration_gap == -0.5)

# ── Section 7: AgentEvaluationLogEntry ───────────────────────────────────────
from lib.reliability.agent_evaluation import AgentEvaluationLogEntry

le7 = AgentEvaluationLogEntry(
    event_id="ev1", event_type="evaluation_recorded",
    created_at="2025-01-01T00:00:00Z", description="d",
)
check("7.1 LogEntry construct", le7.event_id == "ev1")
check("7.2 LogEntry actor default system", le7.actor == "system")
expect_error("7.3 LogEntry empty event_id",
             lambda: AgentEvaluationLogEntry(
                 event_id="", created_at="t", description="d"
             ), Exception)
expect_error("7.4 LogEntry whitespace description",
             lambda: AgentEvaluationLogEntry(
                 event_id="e", created_at="t", description="  "
             ), Exception)

# ── Section 8: AgentEvaluationRecord ─────────────────────────────────────────
from lib.reliability.agent_evaluation import (
    AgentEvaluationRecord, build_agent_evaluation_signal,
    build_agent_evaluation_target_ref,
)

_tref8 = build_agent_evaluation_target_ref(artifact_id="art1", agent_type="macro_agent")
_sig8 = build_agent_evaluation_signal(
    signal_id="sg1", rationale="ok", evaluated_outcome="correct"
)
rec8 = AgentEvaluationRecord(
    evaluation_id="ev1", target="AAPL", agent_type="macro_agent",
    target_ref=_tref8, signals=[_sig8], recorded_at="2025-01-01T00:00:00Z",
)
check("8.1 Record construct", rec8.evaluation_id == "ev1")
check("8.2 Record approved_for_execution default False",
      rec8.approved_for_execution is False)
expect_error("8.3 Record empty evaluation_id",
             lambda: AgentEvaluationRecord(
                 evaluation_id="", target="T", target_ref=_tref8, signals=[_sig8],
                 recorded_at="t",
             ), Exception)
expect_error("8.4 Record empty signals",
             lambda: AgentEvaluationRecord(
                 evaluation_id="e", target="T", target_ref=_tref8, signals=[],
                 recorded_at="t",
             ), Exception)
expect_error("8.5 Record approved_for_execution=True rejected",
             lambda: AgentEvaluationRecord(
                 evaluation_id="e", target="T", target_ref=_tref8, signals=[_sig8],
                 recorded_at="t", approved_for_execution=True,
             ), ValueError, keyword="approved_for_execution")
for _bad in ("account_id", "order_id", "execution_id", "brokerage_id"):
    check(f"8.6.no-field:{_bad}",
          _bad not in AgentEvaluationRecord.model_fields)

# ── Section 9: AgentEvaluationInputBundle ────────────────────────────────────
from lib.reliability.agent_evaluation import AgentEvaluationInputBundle

ib9 = AgentEvaluationInputBundle(target="AAPL")
check("9.1 InputBundle construct", ib9.target == "AAPL")
check("9.2 InputBundle defaults None", ib9.research_run_memory_record is None)
expect_error("9.3 InputBundle whitespace target",
             lambda: AgentEvaluationInputBundle(target="   "), Exception)
expect_error("9.4 InputBundle extra field",
             lambda: AgentEvaluationInputBundle(target="x", broker_id="y"), Exception)

# ── Section 10: AgentEvaluationSummary ───────────────────────────────────────
from lib.reliability.agent_evaluation import AgentEvaluationSummary

sm10 = AgentEvaluationSummary(target="AAPL", status="evaluated")
check("10.1 Summary construct", sm10.status == "evaluated")
check("10.2 Summary approved_for_execution False",
      sm10.approved_for_execution is False)
expect_error("10.3 Summary approved_for_execution=True rejected",
             lambda: AgentEvaluationSummary(
                 target="T", approved_for_execution=True
             ), ValueError, keyword="approved_for_execution")

# ── Section 11: AgentEvaluationReport ────────────────────────────────────────
from lib.reliability.agent_evaluation import AgentEvaluationReport

rpt11 = AgentEvaluationReport(
    report_id="r1", target="AAPL",
    summary=AgentEvaluationSummary(target="AAPL"),
    created_at="t", updated_at="t",
)
check("11.1 Report construct", rpt11.report_id == "r1")
check("11.2 Report approved_for_execution False",
      rpt11.approved_for_execution is False)
expect_error("11.3 Report approved_for_execution=True rejected",
             lambda: AgentEvaluationReport(
                 report_id="r", target="T",
                 summary=AgentEvaluationSummary(target="T"),
                 created_at="t", updated_at="t",
                 approved_for_execution=True,
             ), ValueError, keyword="approved_for_execution")

# ── Section 12: build_agent_evaluation_target_ref ────────────────────────────
from lib.reliability.agent_evaluation import build_agent_evaluation_target_ref

tref12a = build_agent_evaluation_target_ref(
    artifact_id="art1", agent_type="trade_plan", run_id="run1",
)
tref12b = build_agent_evaluation_target_ref(
    artifact_id="art1", agent_type="trade_plan", run_id="run1",
)
check("12.1 target_ref deterministic ID equality",
      tref12a.target_ref_id == tref12b.target_ref_id)
tref12c = build_agent_evaluation_target_ref(
    artifact_id="art2", agent_type="trade_plan", run_id="run1",
)
check("12.2 target_ref artifact_id changes ID",
      tref12c.target_ref_id != tref12a.target_ref_id)
tref12d = build_agent_evaluation_target_ref(
    artifact_id="art1", agent_type="allocation_agent", run_id="run1",
)
check("12.3 target_ref agent_type changes ID",
      tref12d.target_ref_id != tref12a.target_ref_id)
# dedup
sr_a = AgentEvaluationSourceRef(source_id="dup", label="first")
sr_b = AgentEvaluationSourceRef(source_id="dup", label="second")
tref12e = build_agent_evaluation_target_ref(
    artifact_id="art1", source_refs=[sr_a, sr_b],
    evidence_ids=["e1", "e2", "e1"], artifact_refs=["a1", "a2", "a1"],
)
check("12.4 target_ref source_refs deduped", len(tref12e.source_refs) == 1)
check("12.5 target_ref first occurrence wins",
      tref12e.source_refs[0].label == "first")
check("12.6 target_ref evidence_ids deduped",
      tref12e.evidence_ids == ["e1", "e2"])
check("12.7 target_ref artifact_refs deduped",
      tref12e.artifact_refs == ["a1", "a2"])

# ── Section 13: build_agent_evaluation_signal ────────────────────────────────
sig13a = build_agent_evaluation_signal(
    signal_id="sg13", rationale="r", evaluated_outcome="correct",
    evaluation_grade="good", original_confidence=0.7,
)
check("13.1 signal builder construct", sig13a.signal_id == "sg13")
check("13.2 signal approved_for_execution False",
      sig13a.approved_for_execution is False)
sig13b = build_agent_evaluation_signal(
    signal_id="sg13b", rationale="r",
    source_refs=[sr_a, sr_b], evidence_ids=["e", "e"], artifact_refs=["a", "a"],
)
check("13.3 signal source_refs deduped", len(sig13b.source_refs) == 1)
check("13.4 signal evidence_ids deduped", sig13b.evidence_ids == ["e"])
check("13.5 signal artifact_refs deduped", sig13b.artifact_refs == ["a"])

# ── Section 14: build_agent_evaluation_calibration ───────────────────────────
from lib.reliability.agent_evaluation import build_agent_evaluation_calibration

cal14 = build_agent_evaluation_calibration(
    calibration_id="cal14", agent_type="macro_agent",
    sample_count=10, correct_count=7, incorrect_count=2,
    false_positive_count=1, false_negative_count=0, override_count=3,
    average_confidence=0.6,
)
check("14.1 calibration accuracy_rate", abs(cal14.accuracy_rate - 0.7) < 1e-9)
check("14.2 calibration fp_rate", abs(cal14.false_positive_rate - 0.1) < 1e-9)
check("14.3 calibration fn_rate", cal14.false_negative_rate == 0.0)
check("14.4 calibration override_rate", abs(cal14.override_rate - 0.3) < 1e-9)
check("14.5 calibration_gap signed = 0.7-0.6 = 0.1",
      abs(cal14.calibration_gap - 0.1) < 1e-9)
# rates None when sample_count = 0
cal14b = build_agent_evaluation_calibration(
    calibration_id="cal14b", sample_count=0,
)
check("14.6 calibration sample=0 accuracy_rate None",
      cal14b.accuracy_rate is None)
check("14.7 calibration sample=0 fp_rate None",
      cal14b.false_positive_rate is None)
check("14.8 calibration sample=0 calibration_gap None",
      cal14b.calibration_gap is None)
# negative calibration_gap
cal14c = build_agent_evaluation_calibration(
    calibration_id="cal14c", sample_count=10, correct_count=3,
    average_confidence=0.9,
)
check("14.9 calibration negative gap", cal14c.calibration_gap < 0)

# ── Section 15: build_agent_evaluation_log_entry ─────────────────────────────
from lib.reliability.agent_evaluation import (
    build_agent_evaluation_log_entry, make_agent_evaluation_log_entry_id,
)

le15 = build_agent_evaluation_log_entry(
    event_type="evaluation_recorded", description="d",
    evaluation_id="ev1", created_at="2025-01-01T00:00:00Z",
)
check("15.1 log entry construct", le15.event_id.startswith("aevev_"))
le15b = build_agent_evaluation_log_entry(
    event_type="evaluation_recorded", description="d2",
    evaluation_id="ev1", created_at="2025-01-01T00:00:00Z",
)
check("15.2 log entry id stable (same evaluation_id+type+ts)",
      le15.event_id == le15b.event_id)
le15c = build_agent_evaluation_log_entry(
    event_type="outcome_updated", description="d",
    evaluation_id="ev1", created_at="2025-01-01T00:00:00Z",
)
check("15.3 log entry id differs by event_type",
      le15c.event_id != le15.event_id)
le15d = build_agent_evaluation_log_entry(
    event_type="evaluation_recorded", description="d",
    evaluation_id="ev2", created_at="2025-01-01T00:00:00Z",
)
check("15.4 log entry id differs by evaluation_id",
      le15d.event_id != le15.event_id)

# ── Section 16: build_agent_evaluation_record (basic + IDs) ──────────────────
from lib.reliability.agent_evaluation import build_agent_evaluation_record

def _make_record(
    target="AAPL", artifact_id="art1", agent_type="macro_agent",
    signal_outcome="correct", signal_grade="good",
    lesson=None, human_feedback_memory_id=None, run_id=None, as_of=None,
    review_required=False, initial_status=None, hfm_blocked=False,
    missing_important_upstream=False, signals_extra=None,
):
    tref = build_agent_evaluation_target_ref(
        artifact_id=artifact_id, agent_type=agent_type,
        run_id=run_id, as_of=as_of,
    )
    sig = build_agent_evaluation_signal(
        signal_id="sg1", rationale="ok",
        agent_type=agent_type, evaluated_outcome=signal_outcome,
        evaluation_grade=signal_grade,
    )
    signals = [sig] + list(signals_extra or [])
    return build_agent_evaluation_record(
        target=target, target_ref=tref, signals=signals,
        agent_type=agent_type, lesson=lesson,
        human_feedback_memory_id=human_feedback_memory_id, run_id=run_id,
        review_required=review_required, initial_status=initial_status,
        hfm_blocked=hfm_blocked,
        missing_important_upstream=missing_important_upstream, as_of=as_of,
    )

rec16a = _make_record()
rec16b = _make_record()
check("16.1 record deterministic id equality",
      rec16a.evaluation_id == rec16b.evaluation_id)
check("16.2 record evaluation_id prefix", rec16a.evaluation_id.startswith("aev_"))
check("16.3 record status evaluated when clean", rec16a.status == "evaluated")
check("16.4 record approved_for_execution False",
      rec16a.approved_for_execution is False)
rec16c = _make_record(signal_outcome="incorrect")
check("16.5 record id changes with outcome",
      rec16c.evaluation_id != rec16a.evaluation_id)
rec16d = _make_record(signal_grade="poor")
check("16.6 record id changes with grade",
      rec16d.evaluation_id != rec16a.evaluation_id)
rec16e = _make_record(lesson="be careful")
check("16.7 record id changes with lesson",
      rec16e.evaluation_id != rec16a.evaluation_id)
rec16f = _make_record(human_feedback_memory_id="hfm123")
check("16.8 record id changes with human_feedback_memory_id",
      rec16f.evaluation_id != rec16a.evaluation_id)
rec16g = _make_record(run_id="run9")
check("16.9 record id changes with run_id",
      rec16g.evaluation_id != rec16a.evaluation_id)
rec16h = _make_record(as_of="2025-12-31T00:00:00Z")
check("16.10 record id changes with as_of",
      rec16h.evaluation_id != rec16a.evaluation_id)

# ── Section 17: event log IDs ────────────────────────────────────────────────
# stable across identical records
ids_a = [ev.event_id for ev in rec16a.event_log]
ids_b = [ev.event_id for ev in rec16b.event_log]
check("17.1 event_log identical for identical records", ids_a == ids_b)
# event log differs for materially distinct records
ids_c = [ev.event_id for ev in rec16c.event_log]
check("17.2 event_log differs by outcome", ids_a != ids_c)
# evaluation_recorded entry present
event_types_a = [ev.event_type for ev in rec16a.event_log]
check("17.3 evaluation_recorded event present",
      "evaluation_recorded" in event_types_a)
# outcome_updated present when outcome != unknown
check("17.4 outcome_updated event present", "outcome_updated" in event_types_a)
# lesson_added present when lesson present
event_types_e = [ev.event_type for ev in rec16e.event_log]
check("17.5 lesson_added event present", "lesson_added" in event_types_e)
# human_feedback_linked present when feedback_memory_id present
event_types_f = [ev.event_type for ev in rec16f.event_log]
check("17.6 human_feedback_linked event present",
      "human_feedback_linked" in event_types_f)

# ── Section 18: status precedence ────────────────────────────────────────────
# Precedence is: blocked > needs_review > incomplete > evaluated > archived > unknown
# initial_status is NOT a free override; stronger conditions outrank it.
rec18_blocked = _make_record(hfm_blocked=True)
check("18.1 record status blocked under hfm_blocked",
      rec18_blocked.status == "blocked")
rec18_review = _make_record(review_required=True)
check("18.2 record status needs_review when flag set",
      rec18_review.status == "needs_review")
rec18_incomp = _make_record(missing_important_upstream=True)
check("18.3 record status incomplete when upstream missing",
      rec18_incomp.status == "incomplete")
rec18_unknown = _make_record(signal_outcome="unknown", signal_grade="unknown")
check("18.4 record status incomplete when all outcomes unknown",
      rec18_unknown.status == "incomplete")
# Safe initial_status wins only when no stronger condition fires
rec18_init = _make_record(initial_status="archived")
check("18.5 record initial_status='archived' applies when safe",
      rec18_init.status == "archived")
# initial_status='evaluated' + hfm_blocked=True -> blocked
rec18_evb = _make_record(initial_status="evaluated", hfm_blocked=True)
check("18.6 initial_status='evaluated' + hfm_blocked -> blocked",
      rec18_evb.status == "blocked")
# initial_status='archived' + hfm_blocked=True -> blocked
rec18_arb = _make_record(initial_status="archived", hfm_blocked=True)
check("18.7 initial_status='archived' + hfm_blocked -> blocked",
      rec18_arb.status == "blocked")
# initial_status='evaluated' + review_required=True -> needs_review
rec18_evr = _make_record(initial_status="evaluated", review_required=True)
check("18.8 initial_status='evaluated' + review_required -> needs_review",
      rec18_evr.status == "needs_review")
# initial_status='evaluated' + missing_important_upstream=True -> incomplete
rec18_evi = _make_record(
    initial_status="evaluated", missing_important_upstream=True
)
check("18.9 initial_status='evaluated' + missing_important_upstream -> incomplete",
      rec18_evi.status == "incomplete")
# initial_status='archived' + review_required=True -> needs_review
rec18_arr = _make_record(initial_status="archived", review_required=True)
check("18.10 initial_status='archived' + review_required -> needs_review",
      rec18_arr.status == "needs_review")
# initial_status='archived' + missing_important_upstream=True -> incomplete
rec18_ari = _make_record(
    initial_status="archived", missing_important_upstream=True
)
check("18.11 initial_status='archived' + missing_important_upstream -> incomplete",
      rec18_ari.status == "incomplete")
# Safe initial_status values still propagate when no stronger condition fires
rec18_unk = _make_record(initial_status="unknown")
check("18.12 initial_status='unknown' applies when safe",
      rec18_unk.status == "unknown")
rec18_ev = _make_record(initial_status="evaluated")
check("18.13 initial_status='evaluated' applies when safe",
      rec18_ev.status == "evaluated")
# initial_status='blocked' alone (without hfm flag) still yields blocked
rec18_initblk = _make_record(initial_status="blocked")
check("18.14 initial_status='blocked' yields blocked",
      rec18_initblk.status == "blocked")
# initial_status='needs_review' alone yields needs_review
rec18_initnr = _make_record(initial_status="needs_review")
check("18.15 initial_status='needs_review' yields needs_review",
      rec18_initnr.status == "needs_review")
# initial_status='incomplete' alone yields incomplete
rec18_initinc = _make_record(initial_status="incomplete")
check("18.16 initial_status='incomplete' yields incomplete",
      rec18_initinc.status == "incomplete")
# blocked beats needs_review beats incomplete in combined cases
rec18_combo = _make_record(
    hfm_blocked=True, review_required=True, missing_important_upstream=True,
)
check("18.17 blocked beats needs_review + incomplete",
      rec18_combo.status == "blocked")
rec18_combo2 = _make_record(
    review_required=True, missing_important_upstream=True,
)
check("18.18 needs_review beats incomplete",
      rec18_combo2.status == "needs_review")
# Report-level still follows the same precedence (sanity)
from lib.reliability.agent_evaluation import determine_agent_evaluation_status as _det
_st_rep_blk, _ = _det(
    records=[_make_record(hfm_blocked=True), _make_record(review_required=True)],
    input_bundle=AgentEvaluationInputBundle(target="T"),
)
check("18.19 report blocked beats needs_review",
      _st_rep_blk == "blocked")
_st_rep_nr, _ = _det(
    records=[_make_record(review_required=True),
             _make_record(missing_important_upstream=True)],
    input_bundle=AgentEvaluationInputBundle(target="T"),
)
check("18.20 report needs_review beats incomplete",
      _st_rep_nr == "needs_review")
_st_rep_inc, _ = _det(
    records=[_make_record(missing_important_upstream=True),
             _make_record(initial_status="archived")],
    input_bundle=AgentEvaluationInputBundle(target="T"),
)
check("18.21 report incomplete beats archived",
      _st_rep_inc == "incomplete")

# ── Section 19: determine_agent_evaluation_status ────────────────────────────
from lib.reliability.agent_evaluation import determine_agent_evaluation_status

class _Stub:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

# blocked upstream HFM
ib19_blocked = AgentEvaluationInputBundle(
    target="T", as_of="2025-01-01T00:00:00Z",
)
ib19_blocked.human_feedback_memory_report = _Stub(status="blocked")
status19, w19 = determine_agent_evaluation_status(
    records=[_make_record()], input_bundle=ib19_blocked
)
check("19.1 HFM blocked -> report blocked", status19 == "blocked")
check("19.2 HFM blocked warning emitted", any("blocked" in w.lower() for w in w19))
# blocked upstream review loop
ib19_rlblk = AgentEvaluationInputBundle(target="T")
ib19_rlblk.review_loop_report = _Stub(status="blocked")
status19b, _ = determine_agent_evaluation_status(
    records=[_make_record()], input_bundle=ib19_rlblk
)
check("19.3 review_loop blocked -> report blocked", status19b == "blocked")
# no records
ib19_empty = AgentEvaluationInputBundle(target="T")
status19c, w19c = determine_agent_evaluation_status(
    records=[], input_bundle=ib19_empty
)
check("19.4 no records -> unknown", status19c == "unknown")
# record needs_review propagates
status19d, _ = determine_agent_evaluation_status(
    records=[_make_record(review_required=True)],
    input_bundle=AgentEvaluationInputBundle(target="T"),
)
check("19.5 needs_review propagates", status19d == "needs_review")
# record incomplete propagates (when not blocked / needs_review)
status19e, _ = determine_agent_evaluation_status(
    records=[_make_record(missing_important_upstream=True)],
    input_bundle=AgentEvaluationInputBundle(target="T"),
)
check("19.6 incomplete propagates", status19e == "incomplete")
# all archived -> archived
status19f, _ = determine_agent_evaluation_status(
    records=[_make_record(initial_status="archived")],
    input_bundle=AgentEvaluationInputBundle(target="T"),
)
check("19.7 all archived -> archived", status19f == "archived")
# clean -> evaluated
status19g, _ = determine_agent_evaluation_status(
    records=[_make_record()],
    input_bundle=AgentEvaluationInputBundle(target="T"),
)
check("19.8 clean -> evaluated", status19g == "evaluated")

# ── Section 20: build_agent_evaluation_report ────────────────────────────────
from lib.reliability.agent_evaluation import build_agent_evaluation_report

ib20 = AgentEvaluationInputBundle(target="AAPL", as_of="2025-01-01T00:00:00Z")
rpt20 = build_agent_evaluation_report(input_bundle=ib20, records=[_make_record()])
check("20.1 report id prefix", rpt20.report_id.startswith("aevrpt_"))
check("20.2 report status evaluated under clean record", rpt20.status == "evaluated")
check("20.3 report approved_for_execution False",
      rpt20.approved_for_execution is False)
check("20.4 report record_count == 1", rpt20.summary.record_count == 1)
check("20.5 report deterministic created_at",
      rpt20.created_at == "2025-01-01T00:00:00Z")
check("20.6 report updated_at default == created_at",
      rpt20.updated_at == rpt20.created_at)
# explicit timestamp override works
rpt20b = build_agent_evaluation_report(
    input_bundle=ib20, records=[_make_record()],
    created_at="2030-01-01T00:00:00Z", updated_at="2030-12-31T23:59:59Z",
)
check("20.7 report created_at override", rpt20b.created_at == "2030-01-01T00:00:00Z")
check("20.8 report updated_at override",
      rpt20b.updated_at == "2030-12-31T23:59:59Z")
# missing upstream artifacts produce warnings rather than crashing
warning_text = " ".join(rpt20.warnings)
for w in (
    "research_run_memory_record",
    "human_feedback_memory_report",
    "review_loop_report",
    "decision_packet",
):
    check(f"20.9.warn:{w}", w in warning_text)
# deterministic across identical input
rpt20c = build_agent_evaluation_report(input_bundle=ib20, records=[_make_record()])
check("20.10 report id deterministic across identical input",
      rpt20.report_id == rpt20c.report_id)

# ── Section 21: deterministic timestamps default ──────────────────────────────
# When no explicit timestamps, recorded_at uses _DETERMINISTIC_TIMESTAMP_DEFAULT
rec21 = _make_record()
check("21.1 record default recorded_at",
      rec21.recorded_at == "1970-01-01T00:00:00Z")
ib21 = AgentEvaluationInputBundle(target="T")
rpt21 = build_agent_evaluation_report(input_bundle=ib21, records=[rec21])
check("21.2 report default created_at",
      rpt21.created_at == "1970-01-01T00:00:00Z")

# ── Section 22: summarize_agent_evaluation ───────────────────────────────────
from lib.reliability.agent_evaluation import summarize_agent_evaluation

# Multi-signal record covering different outcomes/horizons/grades
def _mk_signal(sid, outcome="correct", grade="good", horizon="medium",
               signal_type="thesis_direction"):
    return build_agent_evaluation_signal(
        signal_id=sid, rationale="r", evaluated_outcome=outcome,
        evaluation_grade=grade, horizon=horizon, signal_type=signal_type,
    )

tref22 = build_agent_evaluation_target_ref(
    artifact_id="art22", agent_type="trade_plan",
)
sigs22 = [
    _mk_signal("s1", outcome="correct", grade="good", horizon="short"),
    _mk_signal("s2", outcome="incorrect", grade="poor", horizon="medium"),
    _mk_signal("s3", outcome="false_positive", grade="mixed", horizon="long"),
    _mk_signal("s4", outcome="false_negative", grade="mixed", horizon="medium"),
    _mk_signal("s5", outcome="partially_correct", grade="good", horizon="multi_horizon"),
    _mk_signal("s6", outcome="inconclusive", grade="unknown", horizon="unknown"),
    _mk_signal("s7", outcome="unknown", grade="unknown", horizon="unknown",
               signal_type="human_override"),
]
rec22 = build_agent_evaluation_record(
    target="X", target_ref=tref22, signals=sigs22, agent_type="trade_plan",
)
sm22 = summarize_agent_evaluation(
    target="X", status="evaluated", records=[rec22], warnings=[],
)
check("22.1 signal_count", sm22.signal_count == 7)
check("22.2 correct_count == 1", sm22.correct_count == 1)
check("22.3 incorrect_count counts incorrect+FP+FN",
      sm22.incorrect_count >= 3)
check("22.4 partial_count == 1", sm22.partial_count == 1)
check("22.5 false_positive_count == 1", sm22.false_positive_count == 1)
check("22.6 false_negative_count == 1", sm22.false_negative_count == 1)
check("22.7 override_count counted via signal_type", sm22.override_count >= 1)
check("22.8 horizon_counts populated", sm22.horizon_counts.get("medium", 0) == 2)
check("22.9 agent_counts populated",
      sm22.agent_counts.get("trade_plan", 0) == 1)
check("22.10 outcome_counts populated",
      sm22.outcome_counts.get("correct", 0) == 1)
check("22.11 grade_counts populated",
      sm22.grade_counts.get("good", 0) == 2)

# review_required_count
rec22r = _make_record(review_required=True)
sm22r = summarize_agent_evaluation(
    target="X", status="needs_review", records=[rec22r], warnings=[],
)
check("22.12 review_required_count == 1", sm22r.review_required_count == 1)
# override_count includes calibration.override_count if present
cal22 = build_agent_evaluation_calibration(
    calibration_id="cal22", sample_count=10, override_count=4,
)
tref22b = build_agent_evaluation_target_ref(artifact_id="art22b")
sig22b = build_agent_evaluation_signal(signal_id="s", rationale="r")
rec22cal = build_agent_evaluation_record(
    target="X", target_ref=tref22b, signals=[sig22b],
    calibration=cal22,
)
sm22cal = summarize_agent_evaluation(
    target="X", status="evaluated", records=[rec22cal], warnings=[],
)
check("22.13 override_count includes calibration.override_count",
      sm22cal.override_count >= 4)

# ── Section 23: collect_* dedup ──────────────────────────────────────────────
from lib.reliability.agent_evaluation import (
    collect_agent_evaluation_source_ids,
    collect_agent_evaluation_evidence_ids,
    collect_agent_evaluation_artifact_refs,
)

# bundle + record source_ids both contribute "src_x"
sr_shared = AgentEvaluationSourceRef(source_id="src_shared")
tref23 = build_agent_evaluation_target_ref(
    artifact_id="art23", source_refs=[sr_shared],
)
sig23 = build_agent_evaluation_signal(
    signal_id="s23", rationale="r",
    source_refs=[AgentEvaluationSourceRef(source_id="src_signal")],
    evidence_ids=["e_signal", "e_signal"],
    artifact_refs=["a_signal", "a_signal"],
)
rec23 = build_agent_evaluation_record(
    target="T", target_ref=tref23, signals=[sig23],
    source_refs=[AgentEvaluationSourceRef(source_id="src_shared")],
    evidence_ids=["e_record"],
    artifact_refs=["a_record"],
)
ib23 = AgentEvaluationInputBundle(
    target="T", source_ids=["src_shared", "src_bundle"],
    evidence_ids=["e_signal", "e_bundle"],
    artifact_refs=["a_record", "a_bundle"],
)
sids23 = collect_agent_evaluation_source_ids(ib23, [rec23])
check("23.1 source_ids deduped", sids23.count("src_shared") == 1)
check("23.2 source_ids include record source", "src_signal" in sids23)
check("23.3 source_ids include bundle source", "src_bundle" in sids23)
eids23 = collect_agent_evaluation_evidence_ids(ib23, [rec23])
check("23.4 evidence_ids deduped", eids23.count("e_signal") == 1)
check("23.5 evidence_ids include record evidence", "e_record" in eids23)
arefs23 = collect_agent_evaluation_artifact_refs(ib23, [rec23])
check("23.6 artifact_refs deduped", arefs23.count("a_record") == 1)
check("23.7 artifact_refs include signal", "a_signal" in arefs23)

# upstream artifact source_ids contribute
ib23b = AgentEvaluationInputBundle(target="T")
ib23b.thesis_memory_report = _Stub(
    source_ids=["src_thesis"], evidence_ids=["e_thesis"],
    report_id="thesis_rpt_1",
)
sids23b = collect_agent_evaluation_source_ids(ib23b, [])
check("23.8 upstream artifact source_ids collected",
      "src_thesis" in sids23b)
check("23.9 upstream artifact id collected",
      "thesis_rpt_1" in sids23b)
eids23b = collect_agent_evaluation_evidence_ids(ib23b, [])
check("23.10 upstream artifact evidence_ids collected",
      "e_thesis" in eids23b)

# ── Section 24: ToolResult adapter ───────────────────────────────────────────
from lib.reliability.agent_evaluation import (
    agent_evaluation_tool_result_from_report,
)

ib24 = AgentEvaluationInputBundle(target="AAPL", as_of="2025-01-01T00:00:00Z")
rpt24 = build_agent_evaluation_report(
    input_bundle=ib24, records=[_make_record()],
)
tr24 = agent_evaluation_tool_result_from_report(rpt24)
check("24.1 tool name", tr24.tool_name == "agent_evaluation_report")
check("24.2 ToolResult approved_for_execution False",
      tr24.outputs.get("approved_for_execution") is False)
check("24.3 ToolResult outputs include report",
      isinstance(tr24.outputs.get("report"), dict))
check("24.4 ToolResult outputs include summary",
      isinstance(tr24.outputs.get("summary"), dict))
check("24.5 ToolResult outputs include calculation_version",
      tr24.outputs.get("calculation_version") == "agent_evaluation_v1")
check("24.6 ToolResult evidence_id present", bool(tr24.evidence_id))
# evidence_id stable
tr24b = agent_evaluation_tool_result_from_report(rpt24)
check("24.7 evidence_id stable for identical report",
      tr24.evidence_id == tr24b.evidence_id)
# evidence_id changes when content changes
rpt24c = build_agent_evaluation_report(
    input_bundle=ib24, records=[_make_record(signal_outcome="incorrect")],
)
tr24c = agent_evaluation_tool_result_from_report(rpt24c)
check("24.8 evidence_id changes when evaluation content changes",
      tr24.evidence_id != tr24c.evidence_id)
# adapter does NOT imply execution
check("24.9 adapter description does not mention 'approved'",
      "approved" not in tr24.description.lower() or "approved_for_execution"
      not in tr24.outputs.get("description", "").lower())

# ── Section 25: inputs are not mutated ───────────────────────────────────────
ib25 = AgentEvaluationInputBundle(
    target="T", source_ids=["s1"], evidence_ids=["e1"], artifact_refs=["a1"],
)
_orig_source_ids = list(ib25.source_ids)
_orig_evidence_ids = list(ib25.evidence_ids)
_orig_artifact_refs = list(ib25.artifact_refs)
_orig_warnings = list(ib25.warnings)
rec25 = _make_record()
build_agent_evaluation_report(input_bundle=ib25, records=[rec25])
check("25.1 input source_ids not mutated", ib25.source_ids == _orig_source_ids)
check("25.2 input evidence_ids not mutated",
      ib25.evidence_ids == _orig_evidence_ids)
check("25.3 input artifact_refs not mutated",
      ib25.artifact_refs == _orig_artifact_refs)
check("25.4 input warnings not mutated", ib25.warnings == _orig_warnings)
# record signals are not mutated
_orig_sig_count = len(rec25.signals)
build_agent_evaluation_report(input_bundle=ib25, records=[rec25])
check("25.5 record signals not mutated", len(rec25.signals) == _orig_sig_count)

# ── Section 26: overall_outcome / overall_grade derivation ───────────────────
# correct + incorrect -> partially_correct
tref26 = build_agent_evaluation_target_ref(artifact_id="art26")
sigs26 = [
    _mk_signal("s1", outcome="correct", grade="good"),
    _mk_signal("s2", outcome="incorrect", grade="poor"),
]
rec26 = build_agent_evaluation_record(
    target="T", target_ref=tref26, signals=sigs26,
)
check("26.1 mixed outcomes -> partially_correct",
      rec26.overall_outcome == "partially_correct")
check("26.2 mixed grades -> mixed", rec26.overall_grade == "mixed")
# pure correct -> correct/excellent
sigs26b = [_mk_signal("a", outcome="correct", grade="excellent"),
           _mk_signal("b", outcome="correct", grade="excellent")]
rec26b = build_agent_evaluation_record(
    target="T", target_ref=tref26, signals=sigs26b,
)
check("26.3 all correct -> correct", rec26b.overall_outcome == "correct")
check("26.4 all excellent -> excellent", rec26b.overall_grade == "excellent")
# override_outcome/grade explicit
rec26c = build_agent_evaluation_record(
    target="T", target_ref=tref26, signals=sigs26b,
    overall_outcome="inconclusive", overall_grade="mixed",
)
check("26.5 explicit overall_outcome wins", rec26c.overall_outcome == "inconclusive")
check("26.6 explicit overall_grade wins", rec26c.overall_grade == "mixed")

# ── Section 27: ToolResult ticker/run_id mapping ─────────────────────────────
ib27 = AgentEvaluationInputBundle(
    target="MSFT", run_id="run_msft_001", as_of="2025-01-01T00:00:00Z",
)
rpt27 = build_agent_evaluation_report(input_bundle=ib27, records=[_make_record()])
tr27 = agent_evaluation_tool_result_from_report(rpt27)
check("27.1 ToolResult run_id from report", tr27.run_id == "run_msft_001")
check("27.2 ToolResult ticker from report.target", tr27.ticker == "MSFT")
tr27b = agent_evaluation_tool_result_from_report(rpt27, run_id="override_run")
check("27.3 ToolResult run_id override works", tr27b.run_id == "override_run")

# ── Section 28: make_agent_evaluation_record_id direct sensitivity ───────────
from lib.reliability.agent_evaluation import make_agent_evaluation_record_id

id28a = make_agent_evaluation_record_id(
    target_id="art1", agent_type="macro_agent",
    signal_ids=["s1"], outcomes=["correct"], grades=["good"],
)
id28b = make_agent_evaluation_record_id(
    target_id="art1", agent_type="macro_agent",
    signal_ids=["s1"], outcomes=["correct"], grades=["good"],
)
check("28.1 record_id deterministic", id28a == id28b)
check("28.2 record_id prefix", id28a.startswith("aev_"))
check("28.3 record_id changes by target_id",
      make_agent_evaluation_record_id(
          target_id="art2", agent_type="macro_agent",
          signal_ids=["s1"], outcomes=["correct"], grades=["good"],
      ) != id28a)
check("28.4 record_id changes by agent_type",
      make_agent_evaluation_record_id(
          target_id="art1", agent_type="trade_plan",
          signal_ids=["s1"], outcomes=["correct"], grades=["good"],
      ) != id28a)
check("28.5 record_id changes by outcomes",
      make_agent_evaluation_record_id(
          target_id="art1", agent_type="macro_agent",
          signal_ids=["s1"], outcomes=["incorrect"], grades=["good"],
      ) != id28a)
check("28.6 record_id changes by grades",
      make_agent_evaluation_record_id(
          target_id="art1", agent_type="macro_agent",
          signal_ids=["s1"], outcomes=["correct"], grades=["poor"],
      ) != id28a)
check("28.7 record_id changes by lesson",
      make_agent_evaluation_record_id(
          target_id="art1", agent_type="macro_agent",
          signal_ids=["s1"], outcomes=["correct"], grades=["good"],
          lesson="careful",
      ) != id28a)
check("28.8 record_id changes by human_feedback_memory_id",
      make_agent_evaluation_record_id(
          target_id="art1", agent_type="macro_agent",
          signal_ids=["s1"], outcomes=["correct"], grades=["good"],
          human_feedback_memory_id="hfm1",
      ) != id28a)
check("28.9 record_id changes by run_id",
      make_agent_evaluation_record_id(
          target_id="art1", agent_type="macro_agent",
          signal_ids=["s1"], outcomes=["correct"], grades=["good"],
          run_id="r9",
      ) != id28a)
check("28.10 record_id changes by as_of",
      make_agent_evaluation_record_id(
          target_id="art1", agent_type="macro_agent",
          signal_ids=["s1"], outcomes=["correct"], grades=["good"],
          as_of="2030-01-01T00:00:00Z",
      ) != id28a)

# ── Section 29: design doc existence ─────────────────────────────────────────
_doc = pathlib.Path(
    "/home/hchxie/projects/investment-agents/docs/reliability_phase_4m_agent_evaluation.md"
)
check("29.1 design doc exists", _doc.exists())

# ── Section 30: review_loop status "block" handled too ───────────────────────
ib30 = AgentEvaluationInputBundle(target="T")
ib30.review_loop_report = _Stub(status="block")
st30, _ = determine_agent_evaluation_status(records=[_make_record()], input_bundle=ib30)
check("30.1 review_loop status='block' -> blocked", st30 == "blocked")

# ── Section 31a: rejection analysis (Phase 4M-G fix) ─────────────────────────
# Calibration accepts rejection_count and derives rejection_rate
cal31a = build_agent_evaluation_calibration(
    calibration_id="cal31a", sample_count=10, correct_count=5,
    rejection_count=3,
)
check("31a.1 calibration rejection_count stored",
      cal31a.rejection_count == 3)
check("31a.2 calibration rejection_rate derived",
      abs(cal31a.rejection_rate - 0.3) < 1e-9)
# rejection_rate None when sample_count == 0
cal31a_z = build_agent_evaluation_calibration(
    calibration_id="cal31az", sample_count=0, rejection_count=0,
)
check("31a.3 calibration rejection_rate None when sample=0",
      cal31a_z.rejection_rate is None)
# Negative rejection_count rejected
expect_error("31a.4 calibration negative rejection_count rejected",
             lambda: AgentEvaluationCalibration(
                 calibration_id="c", rejection_count=-1,
             ), Exception)
# rejection_rate out-of-range rejected
expect_error("31a.5 calibration rejection_rate > 1 rejected",
             lambda: AgentEvaluationCalibration(
                 calibration_id="c", rejection_rate=1.5,
             ), Exception)
expect_error("31a.6 calibration rejection_rate < 0 rejected",
             lambda: AgentEvaluationCalibration(
                 calibration_id="c", rejection_rate=-0.1,
             ), Exception)
# Summary aggregates rejection_count from records
cal31a_rec = build_agent_evaluation_calibration(
    calibration_id="cal31arec", sample_count=10, override_count=2,
    rejection_count=4,
)
tref31a = build_agent_evaluation_target_ref(artifact_id="art31a")
sig31a = build_agent_evaluation_signal(signal_id="s31a", rationale="r")
rec31a = build_agent_evaluation_record(
    target="X", target_ref=tref31a, signals=[sig31a],
    calibration=cal31a_rec,
)
sm31a = summarize_agent_evaluation(
    target="X", status="evaluated", records=[rec31a], warnings=[],
)
check("31a.7 summary rejection_count aggregated from calibration",
      sm31a.rejection_count == 4)
# Existing override_count still aggregates
check("31a.8 summary override_count still aggregated",
      sm31a.override_count >= 2)
# Existing acceptance_rate still settable on calibration
cal31a_acc = build_agent_evaluation_calibration(
    calibration_id="cal31aacc", sample_count=10, correct_count=7,
    acceptance_rate=0.8,
)
check("31a.9 acceptance_rate still flows through",
      cal31a_acc.acceptance_rate == 0.8)
# Summary rejection_rate derived from signal_count
sm31a_rate = sm31a.rejection_rate
check("31a.10 summary rejection_rate present when signals > 0",
      sm31a_rate is not None and 0.0 <= sm31a_rate <= 1.0)
# Summary rejection_rate None when no signals (records=[])
sm31a_empty = summarize_agent_evaluation(
    target="X", status="unknown", records=[], warnings=[],
)
check("31a.11 summary rejection_rate None when no signals",
      sm31a_empty.rejection_rate is None)
# ToolResult adapter surfaces rejection_count + rejection_rate
ib31a = AgentEvaluationInputBundle(target="X", as_of="2025-01-01T00:00:00Z")
rpt31a = build_agent_evaluation_report(
    input_bundle=ib31a, records=[rec31a],
)
tr31a = agent_evaluation_tool_result_from_report(rpt31a)
check("31a.12 ToolResult outputs include rejection_count",
      tr31a.outputs.get("rejection_count") == 4)
check("31a.13 ToolResult outputs include rejection_rate",
      "rejection_rate" in tr31a.outputs)
check("31a.14 ToolResult description includes rejection token",
      "rejection=" in tr31a.description)

# ── Section 31b: AgentEvaluationSummary non-negative count validators ───────
# All count fields reject negative values
for _fn in (
    "record_count", "signal_count", "correct_count", "incorrect_count",
    "partial_count", "inconclusive_count", "false_positive_count",
    "false_negative_count", "override_count", "rejection_count",
    "review_required_count",
):
    expect_error(
        f"31b.neg:{_fn}",
        (lambda fn=_fn: AgentEvaluationSummary(target="T", **{fn: -1})),
        Exception,
    )
# Summary rejection_rate out-of-range rejected
expect_error("31b.rate>1",
             lambda: AgentEvaluationSummary(target="T", rejection_rate=1.5),
             Exception)
expect_error("31b.rate<0",
             lambda: AgentEvaluationSummary(target="T", rejection_rate=-0.01),
             Exception)
# Zero counts still accepted (sanity)
sm31b_zero = AgentEvaluationSummary(
    target="T",
    record_count=0, signal_count=0, correct_count=0, incorrect_count=0,
    partial_count=0, inconclusive_count=0, false_positive_count=0,
    false_negative_count=0, override_count=0, rejection_count=0,
    review_required_count=0,
)
check("31b.zero allowed", sm31b_zero.record_count == 0)

# ── Section 31: state-file phrasing reflects current accepted phase ──────────
# The state files should accurately reflect the current accepted phase and
# the current planning task:
#   - Phase 4M-F is accepted.
#   - Phase 4M-G Agent Evaluation is accepted.
#   - Phase 4M-H Phase 4 Memory Closeout is accepted (no longer awaiting
#     review).
#   - Phase 5P Phase 5 Roadmap Decision / Planning is now ACCEPTED (no
#     longer awaiting review; the Phase 5P review-fix pass on 2026-05-27
#     reconciled stale Phase 4M-H wording and the agent-evaluation test
#     count, after which Codex accepted Phase 5P).
#   - No phase is currently in "Implemented — Awaiting Codex Review".
#   - Phase 5A implementation has not started.
state_phase = pathlib.Path(
    "/home/hchxie/projects/investment-agents/docs/ai_dev_state/PROJECT_STATE.md"
).read_text()
check("31.1 PROJECT_STATE 4M-F entry present",
      "Phase 4M-F" in state_phase and "Human Feedback Layer" in state_phase)
check("31.2 PROJECT_STATE 4M-G entry present",
      "Phase 4M-G" in state_phase and "Agent Evaluation" in state_phase)
_accepted_section = ""
_awaiting_section = ""
if "### Accepted" in state_phase:
    _accepted_section = state_phase.split("### Accepted", 1)[1]
    if "### Implemented" in _accepted_section:
        _accepted_section, _post_accepted = _accepted_section.split("### Implemented", 1)
        _awaiting_section = _post_accepted.split("### In Progress", 1)[0] \
            if "### In Progress" in _post_accepted else _post_accepted
# Phase 4M-G should have an accepted-table row in the Accepted section.
check("31.3 PROJECT_STATE Phase 4M-G accepted-row appears under Accepted",
      "| Phase 4M-G |" in _accepted_section)
check("31.3b PROJECT_STATE Phase 4M-G has no row under 'Implemented — Awaiting Codex Review'",
      "| Phase 4M-G |" not in _awaiting_section)
# Phase 4M-H is now accepted; it must have a row under Accepted and must NOT
# have its own row under the Awaiting section.
check("31.4 PROJECT_STATE Phase 4M-H accepted-row appears under Accepted",
      "| Phase 4M-H |" in _accepted_section)
check("31.4b PROJECT_STATE Phase 4M-H has no row under 'Implemented — Awaiting Codex Review'",
      "| Phase 4M-H |" not in _awaiting_section)
# Phase 5P is now accepted. It must have a row under Accepted and must NOT
# have its own row under the Awaiting section.
check("31.5 PROJECT_STATE Phase 5P accepted-row appears under Accepted",
      "Phase 5P" in state_phase
      and "| Phase 5P |" in _accepted_section
      and "| Phase 5P |" not in _awaiting_section)
# Phase 5A must NOT have started. It may appear under Pending or in
# descriptive prose, but it must be explicitly described as not started /
# not yet implemented.
check("31.5b PROJECT_STATE Phase 5A not started",
      "Phase 5A" in state_phase
      and ("not started" in state_phase.lower()
           or "Do not start" in state_phase
           or "has not started" in state_phase.lower()))

current_task = pathlib.Path(
    "/home/hchxie/projects/investment-agents/docs/ai_dev_state/CURRENT_TASK.md"
).read_text()
check("31.6 CURRENT_TASK 4M-F Accepted",
      "Phase 4M-F Human Feedback Layer" in current_task
      and "**Accepted**" in current_task)
check("31.7 CURRENT_TASK 4M-G Accepted",
      "Phase 4M-G Agent Evaluation" in current_task
      and "Phase 4M-G Agent Evaluation | **Accepted**" in current_task)
check("31.8 CURRENT_TASK 4M-H Accepted (no longer awaiting review)",
      "Phase 4M-H" in current_task
      and "Phase 4M-H Phase 4 Memory Closeout | **Accepted**" in current_task)
check("31.9 CURRENT_TASK Phase 5P Accepted",
      "Phase 5P" in current_task
      and "Phase 5P Phase 5 Roadmap Decision / Planning | **Accepted**" in current_task)
check("31.10 CURRENT_TASK Phase 5A not started",
      "Phase 5A" in current_task and "Not started" in current_task)

# ── Final summary ────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"RESULTS: {PASS} passed, {FAIL} failed")
if FAIL > 0:
    print("SOME TESTS FAILED")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
    sys.exit(0)
