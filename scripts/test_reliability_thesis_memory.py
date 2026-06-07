"""
scripts/test_reliability_thesis_memory.py

Phase 4M-B: Thesis Memory by Horizon — test suite.

Run: python3 scripts/test_reliability_thesis_memory.py

All tests are offline/mock-only. No network, DB, vector store, file writes,
Claude API calls, Streamlit, or broker/order/execution dependencies.
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

from lib.reliability.thesis_memory import (
    ThesisActorType,
    ThesisAssumption,
    ThesisAssumptionImportance,
    ThesisConfidence,
    ThesisDirection,
    ThesisHorizon,
    ThesisInvalidationCondition,
    ThesisInvalidationType,
    ThesisMemoryEvent,
    ThesisMemoryEventType,
    ThesisMemoryInputBundle,
    ThesisMemoryReport,
    ThesisMemoryStatus,
    ThesisMemorySummary,
    HorizonThesisMemoryRecord,
    build_horizon_thesis_memory_record,
    build_thesis_memory_event,
    build_thesis_memory_report,
    collect_thesis_memory_artifact_refs,
    collect_thesis_memory_evidence_ids,
    collect_thesis_memory_source_ids,
    determine_thesis_memory_status,
    make_thesis_id,
    make_thesis_memory_event_id,
    make_thesis_memory_report_id,
    summarize_thesis_memory,
    thesis_memory_tool_result_from_report,
)
from lib.reliability.thesis_memory import __all__ as _thesis_all
from lib.reliability.schemas import ToolResult


# ---------------------------------------------------------------------------
# Section 1: ThesisAssumption validation
# ---------------------------------------------------------------------------

_section("Section 1: ThesisAssumption validation")

# 1.1 valid assumption
try:
    a = ThesisAssumption(
        assumption_id="a1",
        description="Revenue growth accelerates due to new product cycle.",
        horizon="short",
        importance="high",
    )
    _check("1.1 valid ThesisAssumption", a.assumption_id == "a1")
except Exception as e:
    _fail("1.1 valid ThesisAssumption", str(e))

# 1.2 default list fields
try:
    a = ThesisAssumption(assumption_id="a2", description="Test assumption.")
    _check("1.2 default list fields empty", a.source_ids == [] and a.evidence_ids == [] and a.warnings == [])
except Exception as e:
    _fail("1.2 default list fields empty", str(e))

# 1.3 whitespace assumption_id rejected
try:
    ThesisAssumption(assumption_id="   ", description="desc")
    _fail("1.3 whitespace assumption_id rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("1.3 whitespace assumption_id rejected")

# 1.4 whitespace description rejected
try:
    ThesisAssumption(assumption_id="a4", description="   ")
    _fail("1.4 whitespace description rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("1.4 whitespace description rejected")

# 1.5 all importance values accepted
for imp in ("low", "medium", "high", "unknown"):
    try:
        a = ThesisAssumption(assumption_id=f"a5_{imp}", description="d", importance=imp)
        _check(f"1.5 importance={imp!r}", a.importance == imp)
    except Exception as e:
        _fail(f"1.5 importance={imp!r}", str(e))

# 1.6 all horizon values accepted
for h in ("short", "medium", "long", "multi_horizon", "unknown"):
    try:
        a = ThesisAssumption(assumption_id=f"a6_{h}", description="d", horizon=h)
        _check(f"1.6 horizon={h!r}", a.horizon == h)
    except Exception as e:
        _fail(f"1.6 horizon={h!r}", str(e))

# 1.7 extra fields forbidden
try:
    ThesisAssumption(assumption_id="a7", description="d", extra_field="bad")
    _fail("1.7 extra fields forbidden", "no error raised")
except (ValidationError, TypeError):
    _ok("1.7 extra fields forbidden")


# ---------------------------------------------------------------------------
# Section 2: ThesisInvalidationCondition validation
# ---------------------------------------------------------------------------

_section("Section 2: ThesisInvalidationCondition validation")

# 2.1 valid condition
try:
    ic = ThesisInvalidationCondition(
        condition_id="ic1",
        description="Stock closes below 200-day MA for 3 consecutive days.",
        invalidation_type="technical",
        horizon="short",
        trigger_level=150.0,
        review_required=True,
    )
    _check("2.1 valid ThesisInvalidationCondition", ic.condition_id == "ic1")
except Exception as e:
    _fail("2.1 valid ThesisInvalidationCondition", str(e))

# 2.2 trigger_level=0.0 is valid (non-negative)
try:
    ic = ThesisInvalidationCondition(condition_id="ic2", description="d", trigger_level=0.0)
    _check("2.2 trigger_level=0.0 accepted", ic.trigger_level == 0.0)
except Exception as e:
    _fail("2.2 trigger_level=0.0 accepted", str(e))

# 2.3 negative trigger_level rejected
try:
    ThesisInvalidationCondition(condition_id="ic3", description="d", trigger_level=-5.0)
    _fail("2.3 negative trigger_level rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("2.3 negative trigger_level rejected")

# 2.4 whitespace condition_id rejected
try:
    ThesisInvalidationCondition(condition_id="  ", description="d")
    _fail("2.4 whitespace condition_id rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("2.4 whitespace condition_id rejected")

# 2.5 whitespace description rejected
try:
    ThesisInvalidationCondition(condition_id="ic5", description="   ")
    _fail("2.5 whitespace description rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("2.5 whitespace description rejected")

# 2.6 default list fields
try:
    ic = ThesisInvalidationCondition(condition_id="ic6", description="d")
    _check("2.6 default list fields empty",
           ic.source_ids == [] and ic.evidence_ids == [] and ic.warnings == [])
except Exception as e:
    _fail("2.6 default list fields empty", str(e))

# 2.7 trigger_level=None is valid (optional)
try:
    ic = ThesisInvalidationCondition(condition_id="ic7", description="d")
    _check("2.7 trigger_level None by default", ic.trigger_level is None)
except Exception as e:
    _fail("2.7 trigger_level None by default", str(e))

# 2.8 review_required defaults to False
try:
    ic = ThesisInvalidationCondition(condition_id="ic8", description="d")
    _check("2.8 review_required defaults False", ic.review_required is False)
except Exception as e:
    _fail("2.8 review_required defaults False", str(e))

# 2.9 all invalidation types accepted
for inv_type in (
    "price_level", "fundamental", "macro", "earnings", "catalyst", "news",
    "estimate_revision", "technical", "risk_limit", "time_based", "other", "unknown"
):
    try:
        ic = ThesisInvalidationCondition(
            condition_id=f"ic9_{inv_type}", description="d", invalidation_type=inv_type
        )
        _check(f"2.9 invalidation_type={inv_type!r}", ic.invalidation_type == inv_type)
    except Exception as e:
        _fail(f"2.9 invalidation_type={inv_type!r}", str(e))


# ---------------------------------------------------------------------------
# Section 3: ThesisMemoryEvent validation
# ---------------------------------------------------------------------------

_section("Section 3: ThesisMemoryEvent validation")

# 3.1 valid event
try:
    ev = ThesisMemoryEvent(
        event_id="ev1",
        event_type="thesis_created",
        created_at="2026-01-01T00:00:00Z",
        description="Thesis created for AAPL short horizon.",
        actor="system",
    )
    _check("3.1 valid ThesisMemoryEvent", ev.event_id == "ev1")
except Exception as e:
    _fail("3.1 valid ThesisMemoryEvent", str(e))

# 3.2 whitespace event_id rejected
try:
    ThesisMemoryEvent(event_id="  ", event_type="thesis_created",
                      created_at="2026-01-01T00:00:00Z", description="d")
    _fail("3.2 whitespace event_id rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("3.2 whitespace event_id rejected")

# 3.3 whitespace description rejected
try:
    ThesisMemoryEvent(event_id="ev3", event_type="thesis_created",
                      created_at="2026-01-01T00:00:00Z", description="   ")
    _fail("3.3 whitespace description rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("3.3 whitespace description rejected")

# 3.4 whitespace created_at rejected
try:
    ThesisMemoryEvent(event_id="ev4", event_type="thesis_created",
                      created_at="   ", description="d")
    _fail("3.4 whitespace created_at rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("3.4 whitespace created_at rejected")

# 3.5 default fields
try:
    ev = ThesisMemoryEvent(
        event_id="ev5",
        event_type="unknown",
        created_at="2026-01-01T00:00:00Z",
        description="d",
    )
    _check("3.5 default actor is system", ev.actor == "system")
    _check("3.5 default metadata empty dict", ev.metadata == {})
    _check("3.5 default source_ids empty", ev.source_ids == [])
    _check("3.5 default evidence_ids empty", ev.evidence_ids == [])
except Exception as e:
    _fail("3.5 default fields", str(e))

# 3.6 all event types accepted
for et in (
    "thesis_created", "thesis_updated", "thesis_review_requested",
    "thesis_invalidated", "thesis_superseded", "thesis_archived",
    "human_feedback_added", "outcome_observed", "unknown",
):
    try:
        ev = ThesisMemoryEvent(
            event_id=f"ev6_{et}", event_type=et,
            created_at="2026-01-01T00:00:00Z", description="d"
        )
        _check(f"3.6 event_type={et!r}", ev.event_type == et)
    except Exception as e:
        _fail(f"3.6 event_type={et!r}", str(e))

# 3.7 all actor types accepted
for actor in ("system", "user", "reviewer", "agent", "unknown"):
    try:
        ev = ThesisMemoryEvent(
            event_id=f"ev7_{actor}", event_type="thesis_created",
            created_at="2026-01-01T00:00:00Z", description="d", actor=actor
        )
        _check(f"3.7 actor={actor!r}", ev.actor == actor)
    except Exception as e:
        _fail(f"3.7 actor={actor!r}", str(e))


# ---------------------------------------------------------------------------
# Section 4: HorizonThesisMemoryRecord validation
# ---------------------------------------------------------------------------

_section("Section 4: HorizonThesisMemoryRecord validation")

# 4.1 valid record
try:
    rec = HorizonThesisMemoryRecord(
        thesis_id="th1",
        target="AAPL",
        horizon="short",
        direction="bullish",
        status="active",
        confidence="high",
        thesis_text="AAPL will outperform over short horizon driven by iPhone supercycle.",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    _check("4.1 valid HorizonThesisMemoryRecord", rec.thesis_id == "th1")
except Exception as e:
    _fail("4.1 valid HorizonThesisMemoryRecord", str(e))

# 4.2 approved_for_execution=True rejected
try:
    HorizonThesisMemoryRecord(
        thesis_id="th2",
        target="AAPL",
        thesis_text="text",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        approved_for_execution=True,
    )
    _fail("4.2 approved_for_execution=True rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("4.2 approved_for_execution=True rejected")

# 4.3 whitespace thesis_id rejected
try:
    HorizonThesisMemoryRecord(
        thesis_id="   ",
        target="AAPL",
        thesis_text="text",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    _fail("4.3 whitespace thesis_id rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("4.3 whitespace thesis_id rejected")

# 4.4 whitespace thesis_text rejected
try:
    HorizonThesisMemoryRecord(
        thesis_id="th4",
        target="AAPL",
        thesis_text="   ",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    _fail("4.4 whitespace thesis_text rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("4.4 whitespace thesis_text rejected")

# 4.5 optional run_id / memory_id fields
try:
    rec = HorizonThesisMemoryRecord(
        thesis_id="th5",
        target="AAPL",
        thesis_text="text",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        run_id="run001",
        memory_id="rmem_abc",
    )
    _check("4.5 run_id and memory_id accepted", rec.run_id == "run001" and rec.memory_id == "rmem_abc")
except Exception as e:
    _fail("4.5 run_id and memory_id accepted", str(e))

# 4.6 default list fields
try:
    rec = HorizonThesisMemoryRecord(
        thesis_id="th6",
        target="AAPL",
        thesis_text="text",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    _check("4.6 default list fields empty",
           rec.assumptions == [] and rec.invalidation_conditions == []
           and rec.source_ids == [] and rec.evidence_ids == []
           and rec.artifact_refs == [] and rec.event_log == [])
except Exception as e:
    _fail("4.6 default list fields empty", str(e))

# 4.7 all ThesisHorizon values accepted
for h in ("short", "medium", "long", "multi_horizon", "unknown"):
    try:
        rec = HorizonThesisMemoryRecord(
            thesis_id=f"th7_{h}",
            target="AAPL",
            thesis_text="text",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            horizon=h,
        )
        _check(f"4.7 horizon={h!r}", rec.horizon == h)
    except Exception as e:
        _fail(f"4.7 horizon={h!r}", str(e))

# 4.8 all ThesisDirection values
for d in ("bullish", "bearish", "neutral", "mixed", "unknown"):
    try:
        rec = HorizonThesisMemoryRecord(
            thesis_id=f"th8_{d}",
            target="AAPL",
            thesis_text="text",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            direction=d,
        )
        _check(f"4.8 direction={d!r}", rec.direction == d)
    except Exception as e:
        _fail(f"4.8 direction={d!r}", str(e))

# 4.9 all ThesisMemoryStatus values
for st in ("unknown", "active", "needs_review", "invalidated", "superseded", "archived", "blocked"):
    try:
        rec = HorizonThesisMemoryRecord(
            thesis_id=f"th9_{st}",
            target="AAPL",
            thesis_text="text",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            status=st,
        )
        _check(f"4.9 status={st!r}", rec.status == st)
    except Exception as e:
        _fail(f"4.9 status={st!r}", str(e))


# ---------------------------------------------------------------------------
# Section 5: ThesisMemoryInputBundle validation
# ---------------------------------------------------------------------------

_section("Section 5: ThesisMemoryInputBundle validation")

# 5.1 minimal valid bundle
try:
    b = ThesisMemoryInputBundle(target="AAPL")
    _check("5.1 minimal valid bundle", b.target == "AAPL")
except Exception as e:
    _fail("5.1 minimal valid bundle", str(e))

# 5.2 whitespace target rejected
try:
    ThesisMemoryInputBundle(target="   ")
    _fail("5.2 whitespace target rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("5.2 whitespace target rejected")

# 5.3 optional fields default to None
try:
    b = ThesisMemoryInputBundle(target="AAPL")
    _check("5.3 run_id None by default", b.run_id is None)
    _check("5.3 memory_id None by default", b.memory_id is None)
    _check("5.3 as_of None by default", b.as_of is None)
    _check("5.3 horizon_synthesis None by default", b.horizon_synthesis is None)
    _check("5.3 human_review_report None by default", b.human_review_report is None)
except Exception as e:
    _fail("5.3 optional fields default to None", str(e))

# 5.4 duck-typed artifacts accepted
try:
    mock_dp = types.SimpleNamespace(status="ok", report_id="dp001", source_ids=["s1"])
    b = ThesisMemoryInputBundle(target="AAPL", decision_packet=mock_dp)
    _check("5.4 duck-typed decision_packet accepted", b.decision_packet is mock_dp)
except Exception as e:
    _fail("5.4 duck-typed artifacts accepted", str(e))

# 5.5 default list fields
try:
    b = ThesisMemoryInputBundle(target="AAPL")
    _check("5.5 default list fields empty",
           b.source_ids == [] and b.evidence_ids == [] and b.artifact_refs == [] and b.warnings == [])
except Exception as e:
    _fail("5.5 default list fields empty", str(e))


# ---------------------------------------------------------------------------
# Section 6: ThesisMemorySummary validation
# ---------------------------------------------------------------------------

_section("Section 6: ThesisMemorySummary validation")

# 6.1 valid summary
try:
    s = ThesisMemorySummary(
        target="AAPL",
        status="active",
        thesis_count=3,
        active_count=3,
        horizons_covered=["long", "medium", "short"],
        direction_counts={"bullish": 3},
        high_confidence_count=1,
    )
    _check("6.1 valid ThesisMemorySummary", s.target == "AAPL" and s.thesis_count == 3)
except Exception as e:
    _fail("6.1 valid ThesisMemorySummary", str(e))

# 6.2 approved_for_execution=True rejected
try:
    ThesisMemorySummary(target="AAPL", approved_for_execution=True)
    _fail("6.2 approved_for_execution=True rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("6.2 approved_for_execution=True rejected")

# 6.3 default numeric fields are 0
try:
    s = ThesisMemorySummary(target="AAPL")
    _check("6.3 default counts are 0",
           s.thesis_count == 0 and s.active_count == 0
           and s.invalidated_count == 0 and s.high_confidence_count == 0)
except Exception as e:
    _fail("6.3 default counts are 0", str(e))


# ---------------------------------------------------------------------------
# Section 7: ThesisMemoryReport validation
# ---------------------------------------------------------------------------

_section("Section 7: ThesisMemoryReport validation")

_dummy_summary = ThesisMemorySummary(target="AAPL", status="active")

# 7.1 valid report
try:
    r = ThesisMemoryReport(
        report_id="trep_001",
        target="AAPL",
        status="active",
        summary=_dummy_summary,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    _check("7.1 valid ThesisMemoryReport", r.report_id == "trep_001")
except Exception as e:
    _fail("7.1 valid ThesisMemoryReport", str(e))

# 7.2 approved_for_execution=True rejected
try:
    ThesisMemoryReport(
        report_id="trep_002",
        target="AAPL",
        summary=_dummy_summary,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        approved_for_execution=True,
    )
    _fail("7.2 approved_for_execution=True rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("7.2 approved_for_execution=True rejected")

# 7.3 whitespace report_id rejected
try:
    ThesisMemoryReport(
        report_id="   ",
        target="AAPL",
        summary=_dummy_summary,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    _fail("7.3 whitespace report_id rejected", "no error raised")
except (ValidationError, ValueError):
    _ok("7.3 whitespace report_id rejected")

# 7.4 run_id is optional
try:
    r = ThesisMemoryReport(
        report_id="trep_004",
        target="AAPL",
        run_id=None,
        summary=_dummy_summary,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    _check("7.4 run_id=None accepted", r.run_id is None)
except Exception as e:
    _fail("7.4 run_id=None accepted", str(e))


# ---------------------------------------------------------------------------
# Section 8: approved_for_execution always False
# ---------------------------------------------------------------------------

_section("Section 8: approved_for_execution always False")

_models_to_check = [
    ("HorizonThesisMemoryRecord", lambda: HorizonThesisMemoryRecord(
        thesis_id="th_x", target="AAPL", thesis_text="text",
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        approved_for_execution=True,
    )),
    ("ThesisMemorySummary", lambda: ThesisMemorySummary(
        target="AAPL", approved_for_execution=True,
    )),
    ("ThesisMemoryReport", lambda: ThesisMemoryReport(
        report_id="r1", target="AAPL",
        summary=ThesisMemorySummary(target="AAPL"),
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        approved_for_execution=True,
    )),
]
for model_name, factory in _models_to_check:
    try:
        factory()
        _fail(f"8 {model_name} rejects approved_for_execution=True", "no error raised")
    except (ValidationError, ValueError):
        _ok(f"8 {model_name} rejects approved_for_execution=True")


# ---------------------------------------------------------------------------
# Section 9: build_horizon_thesis_memory_record
# ---------------------------------------------------------------------------

_section("Section 9: build_horizon_thesis_memory_record")

_ic1 = ThesisInvalidationCondition(
    condition_id="c1",
    description="Stock closes below $150 for 3 days.",
    invalidation_type="price_level",
    horizon="short",
    trigger_level=150.0,
    review_required=False,
    evidence_ids=["ev_ic1"],
)
_ic2 = ThesisInvalidationCondition(
    condition_id="c2",
    description="Q4 EPS miss by >10%.",
    invalidation_type="earnings",
    horizon="medium",
    review_required=True,
)
_a1 = ThesisAssumption(
    assumption_id="a1",
    description="iPhone 17 cycle drives ASP expansion.",
    horizon="short",
    importance="high",
    evidence_ids=["ev_a1"],
)
_a2 = ThesisAssumption(
    assumption_id="a2",
    description="Services gross margin expands to 75%+.",
    horizon="medium",
    importance="medium",
)

# 9.1 complete record with all fields
try:
    rec = build_horizon_thesis_memory_record(
        target="AAPL",
        thesis_text="AAPL is positioned for outperformance driven by iPhone supercycle.",
        horizon="short",
        direction="bullish",
        confidence="high",
        assumptions=[_a1],
        invalidation_conditions=[_ic1],
        run_id="run001",
        memory_id="rmem_abc",
        source_ids=["src1", "src2"],
        evidence_ids=["ev1", "ev2"],
        artifact_refs=["ref1", "ref2"],
        created_at="2026-01-15T10:00:00Z",
        updated_at="2026-01-15T10:00:00Z",
    )
    _check("9.1 target", rec.target == "AAPL")
    _check("9.1 horizon", rec.horizon == "short")
    _check("9.1 direction", rec.direction == "bullish")
    _check("9.1 confidence", rec.confidence == "high")
    _check("9.1 thesis_text non-empty", len(rec.thesis_text) > 0)
    _check("9.1 run_id", rec.run_id == "run001")
    _check("9.1 memory_id", rec.memory_id == "rmem_abc")
    _check("9.1 status active (clean)", rec.status == "active")
    _check("9.1 approved_for_execution False", rec.approved_for_execution is False)
    _check("9.1 event_log has creation event", len(rec.event_log) >= 1)
    _check("9.1 created_at set", rec.created_at == "2026-01-15T10:00:00Z")
    _check("9.1 updated_at set", rec.updated_at == "2026-01-15T10:00:00Z")
    _check("9.1 calculation_version set", rec.calculation_version == "thesis_memory_v1")
    _check("9.1 assumptions preserved", len(rec.assumptions) == 1)
    _check("9.1 invalidation_conditions preserved", len(rec.invalidation_conditions) == 1)
    _check("9.1 source_ids", "src1" in rec.source_ids and "src2" in rec.source_ids)
    _check("9.1 evidence_ids", "ev1" in rec.evidence_ids and "ev2" in rec.evidence_ids)
    _check("9.1 artifact_refs", "ref1" in rec.artifact_refs and "ref2" in rec.artifact_refs)
except Exception as e:
    _fail("9.1 complete record", str(e))

# 9.2 thesis_id is non-empty string
try:
    rec = build_horizon_thesis_memory_record(target="AAPL", thesis_text="text")
    _check("9.2 thesis_id non-empty", bool(rec.thesis_id))
except Exception as e:
    _fail("9.2 thesis_id non-empty", str(e))

# 9.3 event log contains thesis_created event
try:
    rec = build_horizon_thesis_memory_record(target="AAPL", thesis_text="text")
    first_event = rec.event_log[0]
    _check("9.3 first event is thesis_created", first_event.event_type == "thesis_created")
    _check("9.3 event_id non-empty", bool(first_event.event_id))
    _check("9.3 event description non-empty", bool(first_event.description))
except Exception as e:
    _fail("9.3 event log", str(e))

# 9.4 missing optional artifacts produce warnings without crashing
try:
    bundle = ThesisMemoryInputBundle(target="AAPL")
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", input_bundle=bundle
    )
    _check("9.4 no crash with empty bundle", True)
    _check("9.4 warnings produced for missing artifacts",
           any("horizon_synthesis" in w or "debate_report" in w or "decision_packet" in w
               for w in rec.warnings))
except Exception as e:
    _fail("9.4 missing artifacts produce warnings", str(e))

# 9.5 human_review_report=blocked causes thesis blocked
try:
    hrr = types.SimpleNamespace(status="blocked", report_id="hrr001")
    bundle = ThesisMemoryInputBundle(target="AAPL", human_review_report=hrr)
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", input_bundle=bundle
    )
    _check("9.5 hr blocked → thesis blocked", rec.status == "blocked")
    _check("9.5 review event added", any(e.event_type == "thesis_review_requested"
                                        for e in rec.event_log))
except Exception as e:
    _fail("9.5 human review blocked → blocked", str(e))

# 9.6 review_required invalidation condition causes needs_review
try:
    ic_review = ThesisInvalidationCondition(
        condition_id="ic_r", description="EPS miss by >10%.", review_required=True
    )
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", invalidation_conditions=[ic_review]
    )
    _check("9.6 review_required IC → needs_review", rec.status == "needs_review")
    _check("9.6 review event added", any(e.event_type == "thesis_review_requested"
                                        for e in rec.event_log))
except Exception as e:
    _fail("9.6 review_required IC → needs_review", str(e))

# 9.7 initial_status override works
try:
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", initial_status="invalidated"
    )
    _check("9.7 initial_status=invalidated respected", rec.status == "invalidated")
except Exception as e:
    _fail("9.7 initial_status override", str(e))

# 9.8 initial_status=archived
try:
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", initial_status="archived"
    )
    _check("9.8 initial_status=archived respected", rec.status == "archived")
except Exception as e:
    _fail("9.8 initial_status archived", str(e))

# 9.9 extra_warnings included in warnings
try:
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", extra_warnings=["Custom warning for test."]
    )
    _check("9.9 extra_warnings included",
           any("Custom warning for test." in w for w in rec.warnings))
except Exception as e:
    _fail("9.9 extra_warnings", str(e))


# ---------------------------------------------------------------------------
# Section 10: build_thesis_memory_report with short/medium/long theses
# ---------------------------------------------------------------------------

_section("Section 10: build_thesis_memory_report — short/medium/long theses")

_ts_short = build_horizon_thesis_memory_record(
    target="AAPL",
    thesis_text="Short-term: iPhone 17 cycle drives near-term outperformance.",
    horizon="short",
    direction="bullish",
    confidence="high",
    assumptions=[_a1],
    invalidation_conditions=[_ic1],
    source_ids=["src_short"],
    evidence_ids=["ev_short"],
    artifact_refs=["ref_short"],
    created_at="2026-01-15T00:00:00Z",
)
_ts_medium = build_horizon_thesis_memory_record(
    target="AAPL",
    thesis_text="Medium-term: Services segment margins expand to 75%+ by 2027.",
    horizon="medium",
    direction="bullish",
    confidence="medium",
    assumptions=[_a2],
    invalidation_conditions=[_ic2],
    source_ids=["src_medium"],
    evidence_ids=["ev_medium"],
    created_at="2026-01-15T00:00:00Z",
)
_ts_long = build_horizon_thesis_memory_record(
    target="AAPL",
    thesis_text="Long-term: AI integration transforms AAPL into a platform company by 2028.",
    horizon="long",
    direction="bullish",
    confidence="low",
    source_ids=["src_long"],
    created_at="2026-01-15T00:00:00Z",
)

# Note: _ic2 has review_required=True → _ts_medium.status is needs_review
# so the report status should be needs_review

_bundle_full = ThesisMemoryInputBundle(
    target="AAPL",
    run_id="run_aapl_001",
    as_of="2026-01-15T00:00:00Z",
    source_ids=["bundle_src1"],
    evidence_ids=["bundle_ev1"],
    artifact_refs=["bundle_ref1", "  ", ""],  # empty/whitespace should be filtered
)

# 10.1 build complete report
try:
    report = build_thesis_memory_report(
        input_bundle=_bundle_full,
        theses=[_ts_short, _ts_medium, _ts_long],
        created_at="2026-01-15T00:00:00Z",
    )
    _check("10.1 report_id non-empty", bool(report.report_id))
    _check("10.1 target", report.target == "AAPL")
    _check("10.1 run_id from bundle", report.run_id == "run_aapl_001")
    _check("10.1 theses count", report.summary.thesis_count == 3)
    _check("10.1 approved_for_execution False", report.approved_for_execution is False)
    _check("10.1 summary approved False", report.summary.approved_for_execution is False)
    _check("10.1 calculation_version", report.calculation_version == "thesis_memory_v1")
    _check("10.1 created_at set", report.created_at == "2026-01-15T00:00:00Z")
    _check("10.1 horizons_covered has 3", len(report.summary.horizons_covered) == 3)
    _check("10.1 high_confidence_count", report.summary.high_confidence_count == 1)
    _check("10.1 invalidation_condition_count",
           report.summary.invalidation_condition_count == 2)
except Exception as e:
    _fail("10.1 complete report", str(e))

# 10.2 needs_review thesis makes report needs_review
try:
    # _ts_medium has review_required IC so status = needs_review
    report = build_thesis_memory_report(
        input_bundle=_bundle_full,
        theses=[_ts_short, _ts_medium, _ts_long],
        created_at="2026-01-15T00:00:00Z",
    )
    _check("10.2 needs_review status from IC", report.status == "needs_review")
    _check("10.2 needs_review_count >= 1", report.summary.needs_review_count >= 1)
except Exception as e:
    _fail("10.2 needs_review from IC", str(e))

# 10.3 clean active theses produce active status
try:
    clean_short = build_horizon_thesis_memory_record(
        target="AAPL",
        thesis_text="Clean short thesis.",
        horizon="short",
        created_at="2026-01-15T00:00:00Z",
    )
    clean_long = build_horizon_thesis_memory_record(
        target="AAPL",
        thesis_text="Clean long thesis.",
        horizon="long",
        created_at="2026-01-15T00:00:00Z",
    )
    _check("10.3 clean theses are active",
           clean_short.status == "active" and clean_long.status == "active")

    clean_bundle = ThesisMemoryInputBundle(target="AAPL")
    clean_report = build_thesis_memory_report(
        input_bundle=clean_bundle,
        theses=[clean_short, clean_long],
        created_at="2026-01-15T00:00:00Z",
    )
    _check("10.3 clean report status active", clean_report.status == "active")
    _check("10.3 active_count == 2", clean_report.summary.active_count == 2)
except Exception as e:
    _fail("10.3 clean active theses", str(e))

# 10.4 direction_counts populated
try:
    report = build_thesis_memory_report(
        input_bundle=ThesisMemoryInputBundle(target="AAPL"),
        theses=[_ts_short, _ts_medium, _ts_long],
        created_at="2026-01-15T00:00:00Z",
    )
    dc = report.summary.direction_counts
    _check("10.4 direction_counts has bullish", dc.get("bullish", 0) >= 1)
except Exception as e:
    _fail("10.4 direction_counts", str(e))

# 10.5 empty theses produces unknown status
try:
    empty_report = build_thesis_memory_report(
        input_bundle=ThesisMemoryInputBundle(target="AAPL"),
        theses=[],
        created_at="2026-01-15T00:00:00Z",
    )
    _check("10.5 empty theses → unknown status", empty_report.status == "unknown")
    _check("10.5 warnings for no theses",
           any("No theses" in w for w in empty_report.warnings))
except Exception as e:
    _fail("10.5 empty theses", str(e))


# ---------------------------------------------------------------------------
# Section 11: Deterministic output without explicit timestamps
# ---------------------------------------------------------------------------

_section("Section 11: Deterministic output — no explicit timestamps")

# 11.1 identical inputs → identical thesis_ids
try:
    r1 = build_horizon_thesis_memory_record(target="NVDA", thesis_text="t1", horizon="short")
    r2 = build_horizon_thesis_memory_record(target="NVDA", thesis_text="t1", horizon="short")
    _check("11.1 thesis_id stable across identical calls", r1.thesis_id == r2.thesis_id)
except Exception as e:
    _fail("11.1 stable thesis_id", str(e))

# 11.2 identical inputs → identical report_ids
try:
    b = ThesisMemoryInputBundle(target="NVDA")
    rep1 = build_thesis_memory_report(b, theses=[])
    rep2 = build_thesis_memory_report(b, theses=[])
    _check("11.2 report_id stable across identical calls", rep1.report_id == rep2.report_id)
except Exception as e:
    _fail("11.2 stable report_id", str(e))

# 11.3 default timestamp is _DETERMINISTIC_TIMESTAMP_DEFAULT
try:
    rec = build_horizon_thesis_memory_record(target="NVDA", thesis_text="text")
    _check("11.3 created_at default is deterministic", rec.created_at == "1970-01-01T00:00:00Z")
    _check("11.3 updated_at same as created_at", rec.updated_at == rec.created_at)
except Exception as e:
    _fail("11.3 default timestamp", str(e))

# 11.4 as_of in bundle used as timestamp fallback
try:
    b = ThesisMemoryInputBundle(target="NVDA", as_of="2026-03-01T00:00:00Z")
    rec = build_horizon_thesis_memory_record(target="NVDA", thesis_text="text", input_bundle=b)
    _check("11.4 as_of used as timestamp", rec.created_at == "2026-03-01T00:00:00Z")
except Exception as e:
    _fail("11.4 as_of as timestamp", str(e))


# ---------------------------------------------------------------------------
# Section 12: Explicit created_at / updated_at override
# ---------------------------------------------------------------------------

_section("Section 12: Explicit created_at / updated_at override")

# 12.1 explicit created_at takes precedence over as_of
try:
    b = ThesisMemoryInputBundle(target="AAPL", as_of="2026-03-01T00:00:00Z")
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", input_bundle=b,
        created_at="2026-05-01T00:00:00Z",
    )
    _check("12.1 explicit created_at overrides as_of", rec.created_at == "2026-05-01T00:00:00Z")
except Exception as e:
    _fail("12.1 explicit created_at", str(e))

# 12.2 explicit updated_at is independent
try:
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-10T00:00:00Z",
    )
    _check("12.2 created_at", rec.created_at == "2026-05-01T00:00:00Z")
    _check("12.2 updated_at", rec.updated_at == "2026-05-10T00:00:00Z")
except Exception as e:
    _fail("12.2 explicit updated_at", str(e))

# 12.3 explicit created_at for report takes precedence
try:
    b = ThesisMemoryInputBundle(target="AAPL", as_of="2026-03-01T00:00:00Z")
    rep = build_thesis_memory_report(b, created_at="2026-05-01T00:00:00Z")
    _check("12.3 report explicit created_at", rep.created_at == "2026-05-01T00:00:00Z")
except Exception as e:
    _fail("12.3 report explicit created_at", str(e))

# 12.4 updated_at defaults to created_at when not specified
try:
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", created_at="2026-05-01T00:00:00Z"
    )
    _check("12.4 updated_at defaults to created_at", rec.updated_at == "2026-05-01T00:00:00Z")
except Exception as e:
    _fail("12.4 updated_at defaults to created_at", str(e))


# ---------------------------------------------------------------------------
# Section 13: Stable thesis_id / report_id
# ---------------------------------------------------------------------------

_section("Section 13: Stable thesis_id / report_id")

# 13.1 make_thesis_id deterministic
try:
    id1 = make_thesis_id("AAPL", "short", "2026-01-01T00:00:00Z", "run001")
    id2 = make_thesis_id("AAPL", "short", "2026-01-01T00:00:00Z", "run001")
    _check("13.1 make_thesis_id deterministic", id1 == id2)
    _check("13.1 starts with thesis_", id1.startswith("thesis_"))
except Exception as e:
    _fail("13.1 make_thesis_id", str(e))

# 13.2 different horizon → different thesis_id
try:
    id_short = make_thesis_id("AAPL", "short", "2026-01-01T00:00:00Z")
    id_long = make_thesis_id("AAPL", "long", "2026-01-01T00:00:00Z")
    _check("13.2 horizon changes ID", id_short != id_long)
except Exception as e:
    _fail("13.2 horizon changes ID", str(e))

# 13.3 make_thesis_memory_report_id deterministic
try:
    rid1 = make_thesis_memory_report_id("AAPL", "2026-01-01T00:00:00Z", "run001")
    rid2 = make_thesis_memory_report_id("AAPL", "2026-01-01T00:00:00Z", "run001")
    _check("13.3 make_thesis_memory_report_id deterministic", rid1 == rid2)
    _check("13.3 starts with trep_", rid1.startswith("trep_"))
except Exception as e:
    _fail("13.3 make_thesis_memory_report_id", str(e))

# 13.4 make_thesis_memory_event_id deterministic
try:
    eid1 = make_thesis_memory_event_id("th_x", "thesis_created", "2026-01-01T00:00:00Z")
    eid2 = make_thesis_memory_event_id("th_x", "thesis_created", "2026-01-01T00:00:00Z")
    _check("13.4 event ID deterministic", eid1 == eid2)
    _check("13.4 starts with tevt_", eid1.startswith("tevt_"))
except Exception as e:
    _fail("13.4 make_thesis_memory_event_id", str(e))

# 13.5 build_thesis_memory_event deterministic event_id
try:
    thesis_id_for_event = make_thesis_id("AAPL", "short", "2026-01-01T00:00:00Z")
    ev1 = build_thesis_memory_event(
        event_type="thesis_created",
        description="d",
        thesis_id=thesis_id_for_event,
        created_at="2026-01-01T00:00:00Z",
    )
    ev2 = build_thesis_memory_event(
        event_type="thesis_created",
        description="d",
        thesis_id=thesis_id_for_event,
        created_at="2026-01-01T00:00:00Z",
    )
    _check("13.5 build_thesis_memory_event deterministic", ev1.event_id == ev2.event_id)
except Exception as e:
    _fail("13.5 build_thesis_memory_event deterministic", str(e))


# ---------------------------------------------------------------------------
# Section 14: Source / evidence / artifact deduplication
# ---------------------------------------------------------------------------

_section("Section 14: Source / evidence / artifact deduplication")

# 14.1 duplicate source_ids deduplicated
try:
    b = ThesisMemoryInputBundle(target="AAPL", source_ids=["s1", "s2", "s1"])
    result = collect_thesis_memory_source_ids(b)
    _check("14.1 source_ids deduplicated", result.count("s1") == 1)
    _check("14.1 order preserved", result[0] == "s1" and result[1] == "s2")
except Exception as e:
    _fail("14.1 source_ids deduplicated", str(e))

# 14.2 evidence_ids deduplicated across bundle + thesis assumptions + conditions
try:
    ic_ev = ThesisInvalidationCondition(
        condition_id="c_ev", description="d", evidence_ids=["ev_a", "ev_b"]
    )
    a_ev = ThesisAssumption(
        assumption_id="a_ev", description="d", evidence_ids=["ev_b", "ev_c"]
    )
    thesis_ev = build_horizon_thesis_memory_record(
        target="AAPL",
        thesis_text="text",
        assumptions=[a_ev],
        invalidation_conditions=[ic_ev],
        evidence_ids=["ev_a", "ev_d"],
        created_at="2026-01-15T00:00:00Z",
    )
    b = ThesisMemoryInputBundle(target="AAPL", evidence_ids=["ev_a", "ev_x"])
    eids = collect_thesis_memory_evidence_ids(b, [thesis_ev])
    _check("14.2 ev_a appears once", eids.count("ev_a") == 1)
    _check("14.2 ev_b appears once", eids.count("ev_b") == 1)
    _check("14.2 ev_c present", "ev_c" in eids)
    _check("14.2 ev_d present", "ev_d" in eids)
    _check("14.2 ev_x present", "ev_x" in eids)
except Exception as e:
    _fail("14.2 evidence_ids deduplicated", str(e))

# 14.3 artifact_refs whitespace/empty filtered and deduplicated
try:
    b = ThesisMemoryInputBundle(
        target="AAPL",
        artifact_refs=["ref1", "", "  ", "ref1", "ref2"],
    )
    t_ref = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", artifact_refs=["ref2", "ref3"],
        created_at="2026-01-15T00:00:00Z",
    )
    refs = collect_thesis_memory_artifact_refs(b, [t_ref])
    _check("14.3 empty filtered", "" not in refs)
    _check("14.3 whitespace filtered", not any(r.strip() == "" for r in refs))
    _check("14.3 ref1 once", refs.count("ref1") == 1)
    _check("14.3 ref2 once", refs.count("ref2") == 1)
    _check("14.3 ref3 present", "ref3" in refs)
except Exception as e:
    _fail("14.3 artifact_refs filtered and deduped", str(e))

# 14.4 record-level source_ids deduplicated
try:
    rec = build_horizon_thesis_memory_record(
        target="AAPL",
        thesis_text="text",
        source_ids=["s1", "s2", "s1", "s3"],
        created_at="2026-01-15T00:00:00Z",
    )
    _check("14.4 record source_ids deduplicated", rec.source_ids.count("s1") == 1)
    _check("14.4 record source_ids order", rec.source_ids[0] == "s1")
except Exception as e:
    _fail("14.4 record source_ids deduped", str(e))


# ---------------------------------------------------------------------------
# Section 15: Event log construction
# ---------------------------------------------------------------------------

_section("Section 15: Event log construction")

# 15.1 clean thesis has 1 event (thesis_created)
try:
    rec = build_horizon_thesis_memory_record(target="AAPL", thesis_text="text",
                                             created_at="2026-01-15T00:00:00Z")
    _check("15.1 clean thesis has 1 event", len(rec.event_log) == 1)
    _check("15.1 event is thesis_created", rec.event_log[0].event_type == "thesis_created")
except Exception as e:
    _fail("15.1 clean thesis 1 event", str(e))

# 15.2 blocked thesis has 2 events (thesis_created + thesis_review_requested)
try:
    hrr = types.SimpleNamespace(status="blocked", report_id="hrr1")
    bundle = ThesisMemoryInputBundle(target="AAPL", human_review_report=hrr)
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", input_bundle=bundle,
        created_at="2026-01-15T00:00:00Z",
    )
    _check("15.2 blocked thesis has 2 events", len(rec.event_log) == 2)
    event_types = [e.event_type for e in rec.event_log]
    _check("15.2 review requested event present", "thesis_review_requested" in event_types)
except Exception as e:
    _fail("15.2 blocked thesis 2 events", str(e))

# 15.3 needs_review thesis has 2 events
try:
    ic_r = ThesisInvalidationCondition(condition_id="c_r", description="d", review_required=True)
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", invalidation_conditions=[ic_r],
        created_at="2026-01-15T00:00:00Z",
    )
    _check("15.3 needs_review thesis 2 events", len(rec.event_log) == 2)
except Exception as e:
    _fail("15.3 needs_review 2 events", str(e))

# 15.4 event actor defaults to system
try:
    rec = build_horizon_thesis_memory_record(target="AAPL", thesis_text="text",
                                             created_at="2026-01-15T00:00:00Z")
    _check("15.4 event actor is system", rec.event_log[0].actor == "system")
except Exception as e:
    _fail("15.4 event actor", str(e))

# 15.5 event created_at matches record created_at
try:
    rec = build_horizon_thesis_memory_record(target="AAPL", thesis_text="text",
                                             created_at="2026-05-01T00:00:00Z")
    _check("15.5 event created_at matches record", rec.event_log[0].created_at == "2026-05-01T00:00:00Z")
except Exception as e:
    _fail("15.5 event created_at matches record", str(e))


# ---------------------------------------------------------------------------
# Section 16: Missing optional upstream artifacts produce warnings without crashing
# ---------------------------------------------------------------------------

_section("Section 16: Missing optional upstream artifacts — no crash")

# 16.1 fully empty bundle → warnings but no crash
try:
    b = ThesisMemoryInputBundle(target="AAPL")
    rep = build_thesis_memory_report(b, theses=[], created_at="2026-01-15T00:00:00Z")
    _check("16.1 no crash with empty bundle", True)
    _check("16.1 warnings include missing horizon_synthesis",
           any("horizon_synthesis" in w for w in rep.warnings))
    _check("16.1 warnings include missing debate_report",
           any("debate_report" in w for w in rep.warnings))
    _check("16.1 warnings include missing decision_packet",
           any("decision_packet" in w for w in rep.warnings))
    _check("16.1 warnings include missing human_review_report",
           any("human_review_report" in w for w in rep.warnings))
except Exception as e:
    _fail("16.1 empty bundle no crash", str(e))

# 16.2 partial bundle (some artifacts present) — no crash
try:
    mock_hs = types.SimpleNamespace(status="ok", report_id="hs001", source_ids=[])
    b = ThesisMemoryInputBundle(target="AAPL", horizon_synthesis=mock_hs)
    rep = build_thesis_memory_report(b, theses=[], created_at="2026-01-15T00:00:00Z")
    _check("16.2 partial bundle no crash", True)
    _check("16.2 still warns about missing debate_report",
           any("debate_report" in w for w in rep.warnings))
except Exception as e:
    _fail("16.2 partial bundle", str(e))

# 16.3 all artifacts present — no crash
try:
    mock_hs = types.SimpleNamespace(status="ok", report_id="hs1", source_ids=["s1"])
    mock_dp = types.SimpleNamespace(status="ok", packet_id="dp1", source_ids=["s2"])
    mock_dr = types.SimpleNamespace(status="ok", report_id="dr1", source_ids=[])
    mock_hr = types.SimpleNamespace(status="ok", report_id="hr1", source_ids=[])
    b = ThesisMemoryInputBundle(
        target="AAPL",
        horizon_synthesis=mock_hs,
        decision_packet=mock_dp,
        debate_report=mock_dr,
        human_review_report=mock_hr,
    )
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", input_bundle=b,
        created_at="2026-01-15T00:00:00Z",
    )
    _check("16.3 all artifacts present no crash", True)
    _check("16.3 status active with all artifacts present", rec.status == "active")
except Exception as e:
    _fail("16.3 all artifacts present", str(e))


# ---------------------------------------------------------------------------
# Section 17: Human review blocked → report blocked
# ---------------------------------------------------------------------------

_section("Section 17: Human review blocked → report blocked")

# 17.1 human_review_report blocked → report blocked
try:
    hrr_blocked = types.SimpleNamespace(status="blocked", report_id="hr_blk")
    b = ThesisMemoryInputBundle(target="AAPL", human_review_report=hrr_blocked)
    clean_t = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", created_at="2026-01-15T00:00:00Z"
    )
    rep = build_thesis_memory_report(b, theses=[clean_t], created_at="2026-01-15T00:00:00Z")
    _check("17.1 report status blocked from hrr", rep.status == "blocked")
except Exception as e:
    _fail("17.1 hr blocked → report blocked", str(e))

# 17.2 thesis blocked directly → report blocked
try:
    hrr_blocked = types.SimpleNamespace(status="blocked", report_id="hr_blk2")
    bundle_for_thesis = ThesisMemoryInputBundle(target="AAPL", human_review_report=hrr_blocked)
    blocked_t = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", input_bundle=bundle_for_thesis,
        created_at="2026-01-15T00:00:00Z",
    )
    _check("17.2 thesis status blocked", blocked_t.status == "blocked")

    clean_b = ThesisMemoryInputBundle(target="AAPL")
    rep = build_thesis_memory_report(clean_b, theses=[blocked_t],
                                     created_at="2026-01-15T00:00:00Z")
    _check("17.2 report blocked from blocked thesis", rep.status == "blocked")
except Exception as e:
    _fail("17.2 thesis blocked → report blocked", str(e))

# 17.3 blocked precedence over active theses
try:
    hrr_b = types.SimpleNamespace(status="blocked", report_id="hrb3")
    b = ThesisMemoryInputBundle(target="AAPL", human_review_report=hrr_b)
    clean_t2 = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text 2", horizon="long",
        created_at="2026-01-15T00:00:00Z",
    )
    rep = build_thesis_memory_report(b, theses=[clean_t2], created_at="2026-01-15T00:00:00Z")
    _check("17.3 blocked > active precedence", rep.status == "blocked")
except Exception as e:
    _fail("17.3 blocked > active", str(e))


# ---------------------------------------------------------------------------
# Section 18: needs_review thesis → report needs_review
# ---------------------------------------------------------------------------

_section("Section 18: needs_review thesis → report needs_review")

# 18.1 thesis with review_required IC → report needs_review
try:
    ic_r2 = ThesisInvalidationCondition(
        condition_id="cr2", description="EPS miss", review_required=True
    )
    nr_thesis = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="NR thesis", invalidation_conditions=[ic_r2],
        created_at="2026-01-15T00:00:00Z",
    )
    _check("18.1 thesis status needs_review", nr_thesis.status == "needs_review")

    b = ThesisMemoryInputBundle(target="AAPL")
    rep = build_thesis_memory_report(b, theses=[nr_thesis], created_at="2026-01-15T00:00:00Z")
    _check("18.1 report status needs_review", rep.status == "needs_review")
    _check("18.1 needs_review_count >= 1", rep.summary.needs_review_count >= 1)
except Exception as e:
    _fail("18.1 needs_review from IC", str(e))

# 18.2 determine_thesis_memory_status with needs_review thesis
try:
    nr_t = HorizonThesisMemoryRecord(
        thesis_id="th_nr",
        target="AAPL",
        thesis_text="text",
        status="needs_review",
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    active_t = HorizonThesisMemoryRecord(
        thesis_id="th_ac",
        target="AAPL",
        thesis_text="text",
        status="active",
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    status, warns = determine_thesis_memory_status([active_t, nr_t])
    _check("18.2 needs_review > active in report", status == "needs_review")
except Exception as e:
    _fail("18.2 determine status needs_review", str(e))


# ---------------------------------------------------------------------------
# Section 19: invalidated thesis affects report status
# ---------------------------------------------------------------------------

_section("Section 19: invalidated thesis → report status")

# 19.1 initial_status=invalidated → thesis invalidated → report invalidated
try:
    inv_thesis = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="inv text", initial_status="invalidated",
        created_at="2026-01-15T00:00:00Z",
    )
    _check("19.1 thesis status invalidated", inv_thesis.status == "invalidated")

    b = ThesisMemoryInputBundle(target="AAPL")
    rep = build_thesis_memory_report(b, theses=[inv_thesis], created_at="2026-01-15T00:00:00Z")
    _check("19.1 report status invalidated", rep.status == "invalidated")
    _check("19.1 invalidated_count 1", rep.summary.invalidated_count == 1)
except Exception as e:
    _fail("19.1 invalidated thesis → report", str(e))

# 19.2 invalidated loses to needs_review
try:
    inv_t = HorizonThesisMemoryRecord(
        thesis_id="th_inv",
        target="AAPL",
        thesis_text="text",
        status="invalidated",
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    nr_t = HorizonThesisMemoryRecord(
        thesis_id="th_nr2",
        target="AAPL",
        thesis_text="text",
        status="needs_review",
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    status, _ = determine_thesis_memory_status([inv_t, nr_t])
    _check("19.2 needs_review > invalidated", status == "needs_review")
except Exception as e:
    _fail("19.2 needs_review > invalidated", str(e))

# 19.3 invalidated loses to blocked
try:
    inv_t2 = HorizonThesisMemoryRecord(
        thesis_id="th_inv2",
        target="AAPL",
        thesis_text="text",
        status="invalidated",
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    bl_t = HorizonThesisMemoryRecord(
        thesis_id="th_bl",
        target="AAPL",
        thesis_text="text",
        status="blocked",
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    status, _ = determine_thesis_memory_status([inv_t2, bl_t])
    _check("19.3 blocked > invalidated", status == "blocked")
except Exception as e:
    _fail("19.3 blocked > invalidated", str(e))


# ---------------------------------------------------------------------------
# Section 20: Clean active theses → active status
# ---------------------------------------------------------------------------

_section("Section 20: Clean active theses → active status")

# 20.1 all active → report active
try:
    t_s = build_horizon_thesis_memory_record(
        target="TSLA", thesis_text="short", horizon="short",
        created_at="2026-01-15T00:00:00Z",
    )
    t_m = build_horizon_thesis_memory_record(
        target="TSLA", thesis_text="medium", horizon="medium",
        created_at="2026-01-15T00:00:00Z",
    )
    t_l = build_horizon_thesis_memory_record(
        target="TSLA", thesis_text="long", horizon="long",
        created_at="2026-01-15T00:00:00Z",
    )
    _check("20.1 all theses active",
           t_s.status == "active" and t_m.status == "active" and t_l.status == "active")

    b = ThesisMemoryInputBundle(target="TSLA")
    rep = build_thesis_memory_report(b, theses=[t_s, t_m, t_l], created_at="2026-01-15T00:00:00Z")
    _check("20.1 report status active", rep.status == "active")
    _check("20.1 active_count 3", rep.summary.active_count == 3)
    _check("20.1 approved_for_execution False", rep.approved_for_execution is False)
except Exception as e:
    _fail("20.1 all active → report active", str(e))

# 20.2 archived thesis plus active → report active (active wins over archived)
try:
    act_t = HorizonThesisMemoryRecord(
        thesis_id="th_act",
        target="TSLA",
        thesis_text="active",
        status="active",
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    arch_t = HorizonThesisMemoryRecord(
        thesis_id="th_arch",
        target="TSLA",
        thesis_text="archived",
        status="archived",
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    status, _ = determine_thesis_memory_status([act_t, arch_t])
    _check("20.2 active + archived → active", status == "active")
except Exception as e:
    _fail("20.2 active + archived → active", str(e))

# 20.3 all archived → report archived
try:
    arch_t2 = HorizonThesisMemoryRecord(
        thesis_id="th_arch2",
        target="TSLA",
        thesis_text="archived2",
        status="archived",
        created_at="2026-01-15T00:00:00Z",
        updated_at="2026-01-15T00:00:00Z",
    )
    status, _ = determine_thesis_memory_status([arch_t2])
    _check("20.3 all archived → archived status", status == "archived")
except Exception as e:
    _fail("20.3 all archived", str(e))


# ---------------------------------------------------------------------------
# Section 21: Inputs not mutated
# ---------------------------------------------------------------------------

_section("Section 21: Inputs not mutated")

# 21.1 source_ids list not mutated
try:
    orig_source_ids = ["s1", "s2"]
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", source_ids=orig_source_ids,
        created_at="2026-01-15T00:00:00Z",
    )
    _check("21.1 source_ids list not mutated", orig_source_ids == ["s1", "s2"])
except Exception as e:
    _fail("21.1 source_ids not mutated", str(e))

# 21.2 assumptions list not mutated
try:
    orig_assumptions = [_a1]
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", assumptions=orig_assumptions,
        created_at="2026-01-15T00:00:00Z",
    )
    _check("21.2 assumptions list not mutated", orig_assumptions == [_a1])
except Exception as e:
    _fail("21.2 assumptions not mutated", str(e))

# 21.3 invalidation_conditions list not mutated
try:
    orig_ic = [_ic1]
    rec = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", invalidation_conditions=orig_ic,
        created_at="2026-01-15T00:00:00Z",
    )
    _check("21.3 invalidation_conditions list not mutated", orig_ic == [_ic1])
except Exception as e:
    _fail("21.3 invalidation_conditions not mutated", str(e))

# 21.4 theses list not mutated in build_thesis_memory_report
try:
    t_orig = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="text", created_at="2026-01-15T00:00:00Z"
    )
    orig_theses = [t_orig]
    b = ThesisMemoryInputBundle(target="AAPL")
    rep = build_thesis_memory_report(b, theses=orig_theses, created_at="2026-01-15T00:00:00Z")
    _check("21.4 theses list not mutated", len(orig_theses) == 1 and orig_theses[0] is t_orig)
except Exception as e:
    _fail("21.4 theses not mutated", str(e))

# 21.5 input_bundle warnings not mutated
try:
    orig_bundle_warnings = ["initial warning"]
    b = ThesisMemoryInputBundle(target="AAPL", warnings=orig_bundle_warnings)
    rep = build_thesis_memory_report(b, theses=[], created_at="2026-01-15T00:00:00Z")
    _check("21.5 bundle warnings not mutated", b.warnings == ["initial warning"])
except Exception as e:
    _fail("21.5 bundle warnings not mutated", str(e))


# ---------------------------------------------------------------------------
# Section 22: ToolResult adapter
# ---------------------------------------------------------------------------

_section("Section 22: ToolResult adapter")

_report_for_tool = build_thesis_memory_report(
    input_bundle=ThesisMemoryInputBundle(target="AAPL", run_id="run_tool"),
    theses=[
        build_horizon_thesis_memory_record(
            target="AAPL", thesis_text="short thesis", horizon="short",
            created_at="2026-01-15T00:00:00Z",
        )
    ],
    created_at="2026-01-15T00:00:00Z",
)

# 22.1 returns ToolResult instance
try:
    tr = thesis_memory_tool_result_from_report(_report_for_tool)
    _check("22.1 returns ToolResult", isinstance(tr, ToolResult))
except Exception as e:
    _fail("22.1 returns ToolResult", str(e))

# 22.2 tool_name is "thesis_memory_report"
try:
    tr = thesis_memory_tool_result_from_report(_report_for_tool)
    _check("22.2 tool_name correct", tr.tool_name == "thesis_memory_report")
except Exception as e:
    _fail("22.2 tool_name", str(e))

# 22.3 evidence_id is non-empty
try:
    tr = thesis_memory_tool_result_from_report(_report_for_tool)
    _check("22.3 evidence_id non-empty", bool(tr.evidence_id))
except Exception as e:
    _fail("22.3 evidence_id non-empty", str(e))

# 22.4 outputs includes full report, summary, calculation_version
try:
    tr = thesis_memory_tool_result_from_report(_report_for_tool)
    _check("22.4 outputs has report", "report" in tr.outputs)
    _check("22.4 outputs has summary", "summary" in tr.outputs)
    _check("22.4 outputs has calculation_version", "calculation_version" in tr.outputs)
    _check("22.4 outputs has thesis_count", "thesis_count" in tr.outputs)
    _check("22.4 approved_for_execution False in outputs",
           tr.outputs["approved_for_execution"] is False)
except Exception as e:
    _fail("22.4 outputs structure", str(e))

# 22.5 run_id override works
try:
    tr = thesis_memory_tool_result_from_report(_report_for_tool, run_id="override_run")
    _check("22.5 run_id override", tr.run_id == "override_run")
except Exception as e:
    _fail("22.5 run_id override", str(e))

# 22.6 ticker is set to target
try:
    tr = thesis_memory_tool_result_from_report(_report_for_tool)
    _check("22.6 ticker is target", tr.ticker == "AAPL")
except Exception as e:
    _fail("22.6 ticker", str(e))

# 22.7 no execution implication in tool result
try:
    tr = thesis_memory_tool_result_from_report(_report_for_tool)
    _check("22.7 no approved_for_execution=True in outputs",
           tr.outputs.get("approved_for_execution") is False)
except Exception as e:
    _fail("22.7 no execution implication", str(e))

# 22.8 description non-empty
try:
    tr = thesis_memory_tool_result_from_report(_report_for_tool)
    _check("22.8 description non-empty", bool(tr.description))
    _check("22.8 description mentions target", "AAPL" in tr.description)
except Exception as e:
    _fail("22.8 description", str(e))


# ---------------------------------------------------------------------------
# Section 23: ToolResult evidence_id changes with content
# ---------------------------------------------------------------------------

_section("Section 23: ToolResult evidence_id content-sensitive")

# 23.1 different thesis text → different evidence_id
try:
    b = ThesisMemoryInputBundle(target="AAPL", run_id="run_x", as_of="2026-01-15T00:00:00Z")
    t_v1 = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="Version 1 thesis text.",
        horizon="short", created_at="2026-01-15T00:00:00Z",
    )
    t_v2 = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="Version 2 thesis text — updated assumptions.",
        horizon="short", created_at="2026-01-15T00:00:00Z",
    )
    rep_v1 = build_thesis_memory_report(b, theses=[t_v1], created_at="2026-01-15T00:00:00Z")
    rep_v2 = build_thesis_memory_report(b, theses=[t_v2], created_at="2026-01-15T00:00:00Z")

    tr_v1 = thesis_memory_tool_result_from_report(rep_v1)
    tr_v2 = thesis_memory_tool_result_from_report(rep_v2)
    _check("23.1 different thesis text → different evidence_id", tr_v1.evidence_id != tr_v2.evidence_id)
except Exception as e:
    _fail("23.1 evidence_id changes with thesis text", str(e))

# 23.2 adding an assumption changes evidence_id
try:
    b = ThesisMemoryInputBundle(target="AAPL", run_id="run_y", as_of="2026-01-15T00:00:00Z")
    t_no_assumption = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="thesis text.",
        horizon="medium", created_at="2026-01-15T00:00:00Z",
    )
    t_with_assumption = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="thesis text.",
        horizon="medium",
        assumptions=[ThesisAssumption(assumption_id="ax", description="New assumption.")],
        created_at="2026-01-15T00:00:00Z",
    )
    rep_no = build_thesis_memory_report(b, theses=[t_no_assumption], created_at="2026-01-15T00:00:00Z")
    rep_with = build_thesis_memory_report(b, theses=[t_with_assumption], created_at="2026-01-15T00:00:00Z")

    tr_no = thesis_memory_tool_result_from_report(rep_no)
    tr_with = thesis_memory_tool_result_from_report(rep_with)
    _check("23.2 adding assumption changes evidence_id", tr_no.evidence_id != tr_with.evidence_id)
except Exception as e:
    _fail("23.2 assumption changes evidence_id", str(e))

# 23.3 adding invalidation condition changes evidence_id
try:
    b = ThesisMemoryInputBundle(target="AAPL", run_id="run_z", as_of="2026-01-15T00:00:00Z")
    t_no_ic = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="thesis.", horizon="long",
        created_at="2026-01-15T00:00:00Z",
    )
    t_with_ic = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="thesis.", horizon="long",
        invalidation_conditions=[ThesisInvalidationCondition(
            condition_id="ic_new", description="Price below $100."
        )],
        created_at="2026-01-15T00:00:00Z",
    )
    rep_no_ic = build_thesis_memory_report(b, theses=[t_no_ic], created_at="2026-01-15T00:00:00Z")
    rep_with_ic = build_thesis_memory_report(b, theses=[t_with_ic], created_at="2026-01-15T00:00:00Z")

    tr_no_ic = thesis_memory_tool_result_from_report(rep_no_ic)
    tr_with_ic = thesis_memory_tool_result_from_report(rep_with_ic)
    _check("23.3 adding IC changes evidence_id", tr_no_ic.evidence_id != tr_with_ic.evidence_id)
except Exception as e:
    _fail("23.3 IC changes evidence_id", str(e))

# 23.4 identical inputs → identical evidence_id
try:
    b1 = ThesisMemoryInputBundle(target="AAPL", run_id="run_same", as_of="2026-01-15T00:00:00Z")
    b2 = ThesisMemoryInputBundle(target="AAPL", run_id="run_same", as_of="2026-01-15T00:00:00Z")
    t_s1 = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="same thesis.", created_at="2026-01-15T00:00:00Z"
    )
    t_s2 = build_horizon_thesis_memory_record(
        target="AAPL", thesis_text="same thesis.", created_at="2026-01-15T00:00:00Z"
    )
    rep1 = build_thesis_memory_report(b1, theses=[t_s1], created_at="2026-01-15T00:00:00Z")
    rep2 = build_thesis_memory_report(b2, theses=[t_s2], created_at="2026-01-15T00:00:00Z")
    tr1 = thesis_memory_tool_result_from_report(rep1)
    tr2 = thesis_memory_tool_result_from_report(rep2)
    _check("23.4 identical inputs → identical evidence_id", tr1.evidence_id == tr2.evidence_id)
except Exception as e:
    _fail("23.4 identical inputs same evidence_id", str(e))


# ---------------------------------------------------------------------------
# Section 24: __all__ exports include Phase 4M-B public symbols
# ---------------------------------------------------------------------------

_section("Section 24: __all__ exports")

_expected_symbols = [
    # Literals
    "ThesisActorType", "ThesisAssumptionImportance", "ThesisConfidence",
    "ThesisDirection", "ThesisHorizon", "ThesisInvalidationType",
    "ThesisMemoryEventType", "ThesisMemoryStatus",
    # Models
    "ThesisAssumption", "ThesisInvalidationCondition", "ThesisMemoryEvent",
    "HorizonThesisMemoryRecord", "ThesisMemoryInputBundle",
    "ThesisMemorySummary", "ThesisMemoryReport",
    # Helpers
    "make_thesis_id", "make_thesis_memory_event_id", "make_thesis_memory_report_id",
    "build_thesis_memory_event", "determine_thesis_memory_status",
    "collect_thesis_memory_source_ids", "collect_thesis_memory_evidence_ids",
    "collect_thesis_memory_artifact_refs", "summarize_thesis_memory",
    "build_horizon_thesis_memory_record", "build_thesis_memory_report",
    "thesis_memory_tool_result_from_report",
]

for sym in _expected_symbols:
    _check(f"24 __all__ has {sym}", sym in _thesis_all)


# ---------------------------------------------------------------------------
# Section 25: No forbidden imports
# ---------------------------------------------------------------------------

_section("Section 25: No forbidden imports")

import lib.reliability.thesis_memory as _tm_module
import inspect as _inspect

_tm_source = _inspect.getsource(_tm_module)

for _forbidden in _forbidden_modules:
    _check(
        f"25 no import of {_forbidden!r}",
        f"import {_forbidden}" not in _tm_source
        and f"from {_forbidden}" not in _tm_source,
    )

# Check no actual import statement references live-app modules.
# We only inspect lines that start with 'import' or 'from' to avoid
# false positives from docstring mentions.
_import_lines = [
    line.strip() for line in _tm_source.split("\n")
    if line.strip().startswith(("import ", "from "))
]
for _live_path in [
    "app", "pages", "llm_orchestrator", "workflow_state",
    "lib.valuation", "lib.technical", "lib.rotation", "lib.data_fetcher",
]:
    _check(
        f"25 no import of {_live_path!r} in import lines",
        not any(_live_path in line for line in _import_lines),
    )


# ---------------------------------------------------------------------------
# Section 26: __init__.py exports Phase 4M-B symbols
# ---------------------------------------------------------------------------

_section("Section 26: __init__.py exports Phase 4M-B symbols")

try:
    from lib.reliability import (
        ThesisAssumption as _TA_init,
        ThesisMemoryReport as _TMR_init,
        build_thesis_memory_report as _btmr_init,
        thesis_memory_tool_result_from_report as _tmtrf_init,
        HorizonThesisMemoryRecord as _HTMR_init,
        ThesisMemoryInputBundle as _TMIB_init,
        ThesisMemorySummary as _TMS_init,
    )
    _check("26 ThesisAssumption importable from lib.reliability", True)
    _check("26 ThesisMemoryReport importable from lib.reliability", True)
    _check("26 build_thesis_memory_report importable", True)
    _check("26 thesis_memory_tool_result_from_report importable", True)
    _check("26 HorizonThesisMemoryRecord importable", True)
except ImportError as e:
    _fail("26 lib.reliability exports Phase 4M-B symbols", str(e))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"Phase 4M-B Thesis Memory: {_test_count} tests, {_fail_count} failures")
print(f"{'='*60}")

if _fail_count > 0:
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
    sys.exit(0)
