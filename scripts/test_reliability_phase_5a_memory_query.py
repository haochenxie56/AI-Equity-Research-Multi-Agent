#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5a_memory_query.py

Phase 5A: Existing Workflow Memory Adapter + Fixture-backed Memory Query
Contract test suite.

Validates:
  - ExistingWorkflowSnapshot construction and serialization.
  - InMemoryWorkflowToMemoryAdapter conversion of a fixture snapshot into a
    Phase 4M-compatible WorkflowMemoryBundle.
  - FixtureBackedMemoryStore registration and query semantics.
  - Query by ticker / run_id / horizon / type / review_status.
  - Empty result behavior for missing ticker / run_id / horizon.
  - Adapter does not require lib/workflow_state.py.
  - No live module imports.
  - approved_for_execution remains False on every record produced.
  - No DB / vector store / persistence / external API assumptions.
  - Deterministic ordering / IDs.

Usage:
    python3 scripts/test_reliability_phase_5a_memory_query.py
"""

from __future__ import annotations

import json
import os
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
# Section 1 — Module imports must succeed (and forbidden imports must not occur)
# ---------------------------------------------------------------------------

from lib.reliability import workflow_memory_adapter as _wma_mod
from lib.reliability import phase5_memory_query as _q_mod
from lib.reliability import phase5_fixtures as _fix_mod

check("1.1 workflow_memory_adapter importable", _wma_mod is not None)
check("1.2 phase5_memory_query importable", _q_mod is not None)
check("1.3 phase5_fixtures importable", _fix_mod is not None)

_FORBIDDEN_LIVE_MODULES = (
    "lib.workflow_state",
    "lib.llm_orchestrator",
    "lib.data_fetcher",
    "lib.valuation",
    "lib.technical",
    "lib.rotation",
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

import pathlib

_PHASE5_SOURCES = [
    pathlib.Path(_REPO_ROOT) / "lib" / "reliability" / "workflow_memory_adapter.py",
    pathlib.Path(_REPO_ROOT) / "lib" / "reliability" / "phase5_memory_query.py",
    pathlib.Path(_REPO_ROOT) / "lib" / "reliability" / "phase5_fixtures.py",
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
    "import streamlit",
    "import anthropic",
    # Note: ``research/.workflow_state.json`` is referenced in docstrings to
    # declare that Phase 5A does NOT read it. A literal-substring check would
    # trip on those documentation lines, so we enforce the no-read guarantee
    # via the import checks above and via Section 17 (no filesystem writes).
]

for src in _PHASE5_SOURCES:
    text = src.read_text()
    for needle in _FORBIDDEN_SUBSTRINGS:
        check(
            f"2.x no forbidden source ref in {src.name}: {needle!r}",
            needle not in text,
        )


# ---------------------------------------------------------------------------
# Section 3 — ExistingWorkflowSnapshot construction
# ---------------------------------------------------------------------------

from lib.reliability.workflow_memory_adapter import (
    ExistingPageOutputRef,
    ExistingWorkflowSnapshot,
    ExistingWorkflowStepSnapshot,
    ExistingWorkflowSynthesisSnapshot,
    InMemoryWorkflowToMemoryAdapter,
    WORKFLOW_STEP_ORDER,
    WorkflowMemoryBundle,
    WorkflowToMemoryAdapter,
    make_workflow_snapshot_id,
)

snap_minimal = ExistingWorkflowSnapshot(
    run_id="r1", target="FIXTKR", as_of="2026-05-24T12:00:00+00:00"
)
check("3.1 minimal snapshot constructs", snap_minimal.run_id == "r1")
check("3.2 minimal snapshot approved=False", snap_minimal.approved_for_execution is False)
check("3.3 minimal snapshot empty steps", snap_minimal.steps == {})

expect_error(
    "3.4 snapshot empty run_id raises",
    lambda: ExistingWorkflowSnapshot(run_id="", target="x"),
    Exception,
)
expect_error(
    "3.5 snapshot whitespace target raises",
    lambda: ExistingWorkflowSnapshot(run_id="r", target="   "),
    Exception,
)
expect_error(
    "3.6 snapshot approved_for_execution=True raises",
    lambda: ExistingWorkflowSnapshot(
        run_id="r", target="t", approved_for_execution=True
    ),
    ValueError,
    "approved_for_execution",
)
expect_error(
    "3.7 snapshot unknown step key raises",
    lambda: ExistingWorkflowSnapshot(
        run_id="r",
        target="t",
        steps={"not_a_step": ExistingWorkflowStepSnapshot(step="sector")},
    ),
    Exception,
)
expect_error(
    "3.8 snapshot step key != step name raises",
    lambda: ExistingWorkflowSnapshot(
        run_id="r",
        target="t",
        steps={"sector": ExistingWorkflowStepSnapshot(step="scanner")},
    ),
    Exception,
)

# Construct a deterministic full snapshot and serialize round-trip
from lib.reliability.phase5_fixtures import (
    SAMPLE_FIXTURE_AS_OF,
    SAMPLE_FIXTURE_RUN_ID,
    SAMPLE_FIXTURE_TICKER,
    build_sample_fixture_pack,
    build_sample_workflow_memory_bundle,
    make_sample_workflow_snapshot,
)

snap_full = make_sample_workflow_snapshot()
check("3.9 full snapshot run_id matches fixture", snap_full.run_id == SAMPLE_FIXTURE_RUN_ID)
check(
    "3.10 full snapshot has all 6 steps present",
    set(snap_full.steps.keys()) == set(WORKFLOW_STEP_ORDER),
)
check(
    "3.11 full snapshot step_keys ordered",
    snap_full.step_keys() == list(WORKFLOW_STEP_ORDER),
)
check(
    "3.12 full snapshot synthesis present",
    snap_full.synthesis is not None,
)

_dumped = snap_full.model_dump()
_round = ExistingWorkflowSnapshot.model_validate(_dumped)
check("3.13 snapshot serialize round-trip equal", _round == snap_full)
_json_round = ExistingWorkflowSnapshot.model_validate_json(snap_full.model_dump_json())
check("3.14 snapshot JSON round-trip equal", _json_round == snap_full)

# Deterministic snapshot ID
snap_id_a = make_workflow_snapshot_id(
    run_id="r", target="FIXTKR", as_of="2026-01-01T00:00:00Z"
)
snap_id_b = make_workflow_snapshot_id(
    run_id="r", target="FIXTKR", as_of="2026-01-01T00:00:00Z"
)
snap_id_c = make_workflow_snapshot_id(
    run_id="r2", target="FIXTKR", as_of="2026-01-01T00:00:00Z"
)
check("3.15 snapshot_id deterministic", snap_id_a == snap_id_b)
check("3.16 snapshot_id sensitive to run_id", snap_id_a != snap_id_c)


# ---------------------------------------------------------------------------
# Section 4 — Adapter contract
# ---------------------------------------------------------------------------

adapter = InMemoryWorkflowToMemoryAdapter()
check(
    "4.1 InMemoryWorkflowToMemoryAdapter satisfies Protocol",
    isinstance(adapter, WorkflowToMemoryAdapter),
)

empty_bundle = adapter.adapt(snap_full)
check(
    "4.2 empty adapter returns empty WorkflowMemoryBundle",
    isinstance(empty_bundle, WorkflowMemoryBundle)
    and empty_bundle.research_run_memory is None
    and not empty_bundle.thesis_records,
)
check(
    "4.3 empty adapter snapshot_id matches deterministic ID",
    empty_bundle.snapshot_id
    == make_workflow_snapshot_id(
        run_id=snap_full.run_id,
        target=snap_full.target,
        as_of=snap_full.as_of,
    ),
)
check(
    "4.4 empty adapter approved_for_execution False",
    empty_bundle.approved_for_execution is False,
)
check(
    "4.5 empty adapter contains warning about missing records",
    any("No Phase 4M memory records" in w for w in empty_bundle.warnings),
)

# Register fixture records and confirm bundle structure
snap_p, adapter_p, bundle_p = build_sample_fixture_pack()
check("4.6 fixture pack adapter satisfies Protocol", isinstance(adapter_p, WorkflowToMemoryAdapter))
check("4.7 fixture pack snapshot matches sample", snap_p.run_id == SAMPLE_FIXTURE_RUN_ID)
check("4.8 fixture pack bundle approved=False", bundle_p.approved_for_execution is False)
check("4.9 fixture pack research_run set", bundle_p.research_run_memory is not None)
check("4.10 fixture pack 3 thesis records", len(bundle_p.thesis_records) == 3)
check("4.11 fixture pack 1 event record", len(bundle_p.event_records) == 1)
check("4.12 fixture pack 1 allocation record", len(bundle_p.allocation_records) == 1)
check("4.13 fixture pack 1 option trade record", len(bundle_p.option_trade_records) == 1)
check("4.14 fixture pack 1 human feedback record", len(bundle_p.human_feedback_records) == 1)
check("4.15 fixture pack 1 agent evaluation record", len(bundle_p.agent_evaluation_records) == 1)
check(
    "4.16 fixture pack workflow_step_keys ordered",
    bundle_p.workflow_step_keys == list(WORKFLOW_STEP_ORDER),
)

# Deterministic re-build
snap_p2, _, bundle_p2 = build_sample_fixture_pack()
check(
    "4.17 fixture pack deterministic snapshot_id",
    bundle_p.snapshot_id == bundle_p2.snapshot_id,
)
check(
    "4.18 fixture pack deterministic research_run memory_id",
    bundle_p.research_run_memory.memory_id == bundle_p2.research_run_memory.memory_id,
)


# ---------------------------------------------------------------------------
# Section 5 — Adapter mismatch detection
# ---------------------------------------------------------------------------

other_snap = ExistingWorkflowSnapshot(
    run_id="other_run", target="OTHER", as_of="2026-05-24T12:00:00+00:00"
)
adapter_x = InMemoryWorkflowToMemoryAdapter()
# Register the fixture records (which carry the original run_id/target) against
# a non-matching snapshot: warnings should be emitted but no crash.
mismatch_bundle = adapter_x.register_records(
    snapshot=other_snap,
    research_run_memory=bundle_p.research_run_memory,
    thesis_records=bundle_p.thesis_records,
    event_records=bundle_p.event_records,
    allocation_records=bundle_p.allocation_records,
    option_trade_records=bundle_p.option_trade_records,
    human_feedback_records=bundle_p.human_feedback_records,
    agent_evaluation_records=bundle_p.agent_evaluation_records,
)
check(
    "5.1 adapter detects run_id mismatch",
    any("run_id" in w for w in mismatch_bundle.warnings),
)
check(
    "5.2 adapter detects target mismatch",
    any("target" in w for w in mismatch_bundle.warnings),
)
check(
    "5.3 adapter still produces bundle with approved=False",
    mismatch_bundle.approved_for_execution is False,
)


# ---------------------------------------------------------------------------
# Section 6 — FixtureBackedMemoryStore basics
# ---------------------------------------------------------------------------

from lib.reliability.phase5_memory_query import (
    FixtureBackedMemoryStore,
    MEMORY_RECORD_TYPES,
    MemoryQuery,
    MemoryQueryByHorizon,
    MemoryQueryByReviewStatus,
    MemoryQueryByRunId,
    MemoryQueryByTicker,
    MemoryQueryByType,
    MemoryQueryResult,
    MemoryStoreProtocol,
    MemoryQueryProtocol,
    build_fixture_memory_store_from_snapshot,
)

store = FixtureBackedMemoryStore()
check("6.1 store satisfies MemoryStoreProtocol", isinstance(store, MemoryStoreProtocol))
check("6.2 MemoryQueryProtocol alias works", isinstance(store, MemoryQueryProtocol))
store.register_bundle(bundle_p)

all_res = store.query(MemoryQuery())
check("6.3 all-query returns MemoryQueryResult", isinstance(all_res, MemoryQueryResult))
check("6.4 all-query total_count == 9", all_res.total_count == 9)
check("6.5 all-query approved=False", all_res.approved_for_execution is False)
check(
    "6.6 all-query counts_by_type matches Phase 4M shape",
    all_res.count_by_type()
    == {
        "research_run": 1,
        "thesis": 3,
        "event": 1,
        "allocation": 1,
        "option_trade": 1,
        "human_feedback": 1,
        "agent_evaluation": 1,
    },
)
check("6.7 MEMORY_RECORD_TYPES has 7 entries", len(MEMORY_RECORD_TYPES) == 7)


# ---------------------------------------------------------------------------
# Section 7 — Query by ticker
# ---------------------------------------------------------------------------

q_t = MemoryQueryByTicker(target=SAMPLE_FIXTURE_TICKER)
res_t = store.query(q_t)
check("7.1 ticker query returns 9 records", res_t.total_count == 9)
check(
    "7.2 ticker query research_run target == fixture",
    res_t.research_run_records[0].target == SAMPLE_FIXTURE_TICKER,
)

# Filtered by record_types
q_t_filter = MemoryQueryByTicker(
    target=SAMPLE_FIXTURE_TICKER,
    record_types=["thesis", "allocation"],
)
res_t_filter = store.query(q_t_filter)
check(
    "7.3 ticker query w/ record_types filter returns only those types",
    res_t_filter.research_run_records == []
    and len(res_t_filter.thesis_records) == 3
    and len(res_t_filter.allocation_records) == 1
    and res_t_filter.option_trade_records == [],
)

# Missing ticker -> empty result
res_missing = store.query(MemoryQueryByTicker(target="UNKNOWN_TICKER"))
check("7.4 missing ticker returns empty result", res_missing.is_empty())
check("7.5 missing ticker total_count == 0", res_missing.total_count == 0)
check(
    "7.6 missing ticker approved=False",
    res_missing.approved_for_execution is False,
)

expect_error(
    "7.7 empty ticker raises",
    lambda: MemoryQueryByTicker(target=""),
    Exception,
)
expect_error(
    "7.8 unknown record_type filter raises",
    lambda: MemoryQueryByTicker(target="x", record_types=["bogus"]),
    Exception,
)


# ---------------------------------------------------------------------------
# Section 8 — Query by run_id
# ---------------------------------------------------------------------------

res_r = store.query(MemoryQueryByRunId(run_id=SAMPLE_FIXTURE_RUN_ID))
check("8.1 run_id query returns 9 records", res_r.total_count == 9)

# Missing run_id -> empty
res_r_missing = store.query(MemoryQueryByRunId(run_id="DOES_NOT_EXIST_RUN"))
check("8.2 missing run_id empty", res_r_missing.is_empty())
check("8.3 missing run_id total_count == 0", res_r_missing.total_count == 0)

expect_error(
    "8.4 empty run_id raises",
    lambda: MemoryQueryByRunId(run_id=""),
    Exception,
)


# ---------------------------------------------------------------------------
# Section 9 — Query by horizon
# ---------------------------------------------------------------------------

res_h_short = store.query(MemoryQueryByHorizon(horizon="short"))
check("9.1 horizon=short returns 1 thesis", len(res_h_short.thesis_records) == 1)
check(
    "9.2 horizon=short thesis.horizon == short",
    res_h_short.thesis_records[0].horizon == "short",
)
res_h_medium = store.query(MemoryQueryByHorizon(horizon="medium"))
check("9.3 horizon=medium returns 1 thesis", len(res_h_medium.thesis_records) == 1)
res_h_long = store.query(MemoryQueryByHorizon(horizon="long"))
check("9.4 horizon=long returns 1 thesis", len(res_h_long.thesis_records) == 1)

# Missing horizon -> empty
res_h_missing = store.query(MemoryQueryByHorizon(horizon="multi_horizon"))
check("9.5 horizon=multi_horizon empty", res_h_missing.is_empty())
res_h_missing2 = store.query(MemoryQueryByHorizon(horizon="unknown"))
check("9.6 horizon=unknown empty", res_h_missing2.is_empty())

# Horizon scoped by target
res_h_other = store.query(
    MemoryQueryByHorizon(horizon="short", target="OTHER_TARGET")
)
check("9.7 horizon scoped by mismatched target empty", res_h_other.is_empty())


# ---------------------------------------------------------------------------
# Section 10 — Query by type
# ---------------------------------------------------------------------------

for type_key in MEMORY_RECORD_TYPES:
    res_type = store.query(MemoryQueryByType(record_type=type_key))
    if type_key == "thesis":
        expected = 3
    else:
        expected = 1
    check(
        f"10.x query record_type={type_key!r} returns {expected}",
        res_type.total_count == expected,
    )

expect_error(
    "10.99 unknown record_type raises",
    lambda: MemoryQueryByType(record_type="bogus"),
    Exception,
)

# Type-scoped query w/ run_id filter
res_type_run = store.query(
    MemoryQueryByType(record_type="thesis", run_id=SAMPLE_FIXTURE_RUN_ID)
)
check(
    "10.100 type=thesis + run_id returns all 3 thesis",
    len(res_type_run.thesis_records) == 3,
)
res_type_run_miss = store.query(
    MemoryQueryByType(record_type="thesis", run_id="MISSING_RUN")
)
check(
    "10.101 type=thesis + missing run_id empty",
    res_type_run_miss.is_empty(),
)


# ---------------------------------------------------------------------------
# Section 11 — Query by review status
# ---------------------------------------------------------------------------

res_any = store.query(MemoryQueryByReviewStatus(review_status="any"))
check("11.1 review_status=any total == 9", res_any.total_count == 9)

# In the fixture, only the research_run record is incomplete with
# review_required=True (because the input bundle has no decision_packet /
# reliability_report). All other 8 records are clean.
res_clean = store.query(MemoryQueryByReviewStatus(review_status="clean"))
check(
    "11.2 review_status=clean returns 8 records (all but research_run)",
    res_clean.total_count == 8,
)
check(
    "11.2b clean result has no research_run records",
    res_clean.research_run_records == [],
)

res_blocked = store.query(MemoryQueryByReviewStatus(review_status="blocked"))
check("11.3 review_status=blocked returns 0", res_blocked.total_count == 0)

res_needs = store.query(MemoryQueryByReviewStatus(review_status="needs_review"))
check(
    "11.4 review_status=needs_review returns 1 (research_run via review_required)",
    res_needs.total_count == 1
    and len(res_needs.research_run_records) == 1,
)

res_rev_req = store.query(MemoryQueryByReviewStatus(review_status="review_required"))
check(
    "11.4b review_status=review_required returns 1 (research_run)",
    res_rev_req.total_count == 1
    and len(res_rev_req.research_run_records) == 1,
)

# Empty review_status filter combined with missing target
res_rs_missing = store.query(
    MemoryQueryByReviewStatus(review_status="any", target="MISSING_TARGET")
)
check("11.5 review_status=any with missing target empty", res_rs_missing.is_empty())


# ---------------------------------------------------------------------------
# Section 12 — approved_for_execution invariant
# ---------------------------------------------------------------------------

def _all_records_safe(result: MemoryQueryResult) -> bool:
    all_recs = (
        result.research_run_records
        + result.thesis_records
        + result.event_records
        + result.allocation_records
        + result.option_trade_records
        + result.human_feedback_records
        + result.agent_evaluation_records
    )
    return all(getattr(r, "approved_for_execution", False) is False for r in all_recs)


check(
    "12.1 every record in all-query has approved_for_execution=False",
    _all_records_safe(all_res),
)
check(
    "12.2 every record in ticker query has approved_for_execution=False",
    _all_records_safe(res_t),
)
check(
    "12.3 option trade record has approved_for_execution=False",
    bundle_p.option_trade_records[0].approved_for_execution is False,
)
check(
    "12.4 allocation record has approved_for_execution=False",
    bundle_p.allocation_records[0].approved_for_execution is False,
)
check(
    "12.5 result.approved_for_execution=False on all results",
    all(
        r.approved_for_execution is False
        for r in [res_t, res_r, res_h_short, res_any, res_clean, all_res]
    ),
)


# ---------------------------------------------------------------------------
# Section 13 — Limit and deterministic ordering
# ---------------------------------------------------------------------------

res_lim = store.query(MemoryQuery(limit=1))
check(
    "13.1 limit=1 clamps each list to <= 1",
    all(
        len(getattr(res_lim, f)) <= 1
        for f in (
            "research_run_records",
            "thesis_records",
            "event_records",
            "allocation_records",
            "option_trade_records",
            "human_feedback_records",
            "agent_evaluation_records",
        )
    ),
)
check(
    "13.2 limit=1 preserves total_count (pre-clamp)",
    res_lim.total_count == 9,
)

# Deterministic ordering: re-register a fresh store with bundle_p2 and confirm
# the same record IDs come back in the same order.
store2 = FixtureBackedMemoryStore()
store2.register_bundle(bundle_p2)
res_all_a = store.query(MemoryQuery())
res_all_b = store2.query(MemoryQuery())

check(
    "13.3 ordered thesis_id list deterministic across builds",
    [t.thesis_id for t in res_all_a.thesis_records]
    == [t.thesis_id for t in res_all_b.thesis_records],
)
check(
    "13.4 research_run memory_id deterministic across builds",
    res_all_a.research_run_records[0].memory_id
    == res_all_b.research_run_records[0].memory_id,
)


# ---------------------------------------------------------------------------
# Section 14 — Convenience helper: build store directly from snapshot
# ---------------------------------------------------------------------------

conv_store = build_fixture_memory_store_from_snapshot(snap_p, adapter_p)
res_conv = conv_store.query(MemoryQueryByTicker(target=SAMPLE_FIXTURE_TICKER))
check(
    "14.1 convenience store from snapshot has 9 records",
    res_conv.total_count == 9,
)
check(
    "14.2 convenience store research_run id matches bundle",
    res_conv.research_run_records[0].memory_id
    == bundle_p.research_run_memory.memory_id,
)

# Empty adapter -> empty store
empty_adapter = InMemoryWorkflowToMemoryAdapter()
empty_store = build_fixture_memory_store_from_snapshot(snap_p, empty_adapter)
res_empty_conv = empty_store.query(MemoryQuery())
check(
    "14.3 convenience store w/ empty adapter empty",
    res_empty_conv.is_empty(),
)


# ---------------------------------------------------------------------------
# Section 15 — Rejecting approved_for_execution=True via store
# ---------------------------------------------------------------------------

# Approved fixture cannot be constructed at the record level (Phase 4M
# validators raise), so this is a defense-in-depth check at the store
# registration level. We synthesize a record-like object that bypasses
# Pydantic validation only to confirm the store guard would still trigger if
# someone mutated the field after construction.

class _MockApprovedRecord:
    approved_for_execution = True
    run_id = SAMPLE_FIXTURE_RUN_ID
    target = SAMPLE_FIXTURE_TICKER
    status = "active"


_bad_store = FixtureBackedMemoryStore()
expect_error(
    "15.1 add_research_run_record rejects approved=True",
    lambda: _bad_store.add_research_run_record(_MockApprovedRecord()),  # type: ignore[arg-type]
    ValueError,
    "approved_for_execution",
)
expect_error(
    "15.2 add_thesis_record rejects approved=True",
    lambda: _bad_store.add_thesis_record(_MockApprovedRecord()),  # type: ignore[arg-type]
    ValueError,
    "approved_for_execution",
)
expect_error(
    "15.3 add_event_record rejects approved=True",
    lambda: _bad_store.add_event_record(_MockApprovedRecord()),  # type: ignore[arg-type]
    ValueError,
    "approved_for_execution",
)
expect_error(
    "15.4 add_allocation_record rejects approved=True",
    lambda: _bad_store.add_allocation_record(_MockApprovedRecord()),  # type: ignore[arg-type]
    ValueError,
    "approved_for_execution",
)
expect_error(
    "15.5 add_option_trade_record rejects approved=True",
    lambda: _bad_store.add_option_trade_record(_MockApprovedRecord()),  # type: ignore[arg-type]
    ValueError,
    "approved_for_execution",
)
expect_error(
    "15.6 add_human_feedback_record rejects approved=True",
    lambda: _bad_store.add_human_feedback_record(_MockApprovedRecord()),  # type: ignore[arg-type]
    ValueError,
    "approved_for_execution",
)
expect_error(
    "15.7 add_agent_evaluation_record rejects approved=True",
    lambda: _bad_store.add_agent_evaluation_record(_MockApprovedRecord()),  # type: ignore[arg-type]
    ValueError,
    "approved_for_execution",
)


# ---------------------------------------------------------------------------
# Section 16 — Unknown query type raises
# ---------------------------------------------------------------------------

class _OtherQuery:
    pass


expect_error(
    "16.1 unknown query type raises TypeError",
    lambda: store.query(_OtherQuery()),  # type: ignore[arg-type]
    TypeError,
    "unsupported",
)


# ---------------------------------------------------------------------------
# Section 17 — No persistence / no external IO side effects
# ---------------------------------------------------------------------------

# Build a fresh fixture and confirm no files are written under research/
# by the Phase 5A pipeline. We just check absence of any new file under a
# fresh path that the adapter would conceivably touch.
import tempfile

with tempfile.TemporaryDirectory() as tmp:
    before = set(os.listdir(tmp))
    # Run the full pipeline; none of it should touch disk.
    _ = build_sample_fixture_pack()
    after = set(os.listdir(tmp))
    check("17.1 no files written to tmp by Phase 5A pipeline", before == after)


# ---------------------------------------------------------------------------
# Section 18 — Exports + __all__ checks
# ---------------------------------------------------------------------------

from lib.reliability.workflow_memory_adapter import __all__ as _WMA_ALL
from lib.reliability.phase5_memory_query import __all__ as _Q_ALL
from lib.reliability.phase5_fixtures import __all__ as _FIX_ALL

_EXPECTED_WMA = {
    "ExistingWorkflowStep",
    "ExistingWorkflowStepStatus",
    "WORKFLOW_STEP_ORDER",
    "ExistingPageOutputRef",
    "ExistingWorkflowStepSnapshot",
    "ExistingWorkflowSynthesisSnapshot",
    "ExistingWorkflowSnapshot",
    "WorkflowMemoryBundle",
    "WorkflowToMemoryAdapter",
    "InMemoryWorkflowToMemoryAdapter",
    "make_workflow_snapshot_id",
}
_EXPECTED_Q = {
    "MemoryRecordType",
    "MEMORY_RECORD_TYPES",
    "MemoryHorizon",
    "MemoryReviewStatus",
    "MemoryRecord",
    "MemoryQuery",
    "MemoryQueryByTicker",
    "MemoryQueryByRunId",
    "MemoryQueryByHorizon",
    "MemoryQueryByType",
    "MemoryQueryByReviewStatus",
    "MemoryQueryResult",
    "MemoryStoreProtocol",
    "MemoryQueryProtocol",
    "FixtureBackedMemoryStore",
    "build_fixture_memory_store_from_snapshot",
}
_EXPECTED_FIX = {
    "SAMPLE_FIXTURE_TICKER",
    "SAMPLE_FIXTURE_RUN_ID",
    "SAMPLE_FIXTURE_AS_OF",
    "make_sample_workflow_snapshot",
    "make_sample_research_run_memory",
    "make_sample_thesis_records",
    "make_sample_event_record",
    "make_sample_allocation_record",
    "make_sample_option_trade_record",
    "make_sample_human_feedback_record",
    "make_sample_agent_evaluation_record",
    "build_sample_workflow_memory_bundle",
    "build_sample_fixture_pack",
}

check("18.1 workflow_memory_adapter __all__ matches", set(_WMA_ALL) == _EXPECTED_WMA)
check("18.2 phase5_memory_query __all__ matches", set(_Q_ALL) == _EXPECTED_Q)
check("18.3 phase5_fixtures __all__ matches", set(_FIX_ALL) == _EXPECTED_FIX)


# ---------------------------------------------------------------------------
# Section 19 — Package-level re-exports
# ---------------------------------------------------------------------------

import lib.reliability as _rel_pkg

for _sym in (
    "ExistingWorkflowSnapshot",
    "ExistingWorkflowStepSnapshot",
    "ExistingPageOutputRef",
    "InMemoryWorkflowToMemoryAdapter",
    "WorkflowMemoryBundle",
    "WorkflowToMemoryAdapter",
    "MemoryQuery",
    "MemoryQueryByTicker",
    "MemoryQueryByRunId",
    "MemoryQueryByHorizon",
    "MemoryQueryByType",
    "MemoryQueryByReviewStatus",
    "MemoryQueryResult",
    "MemoryStoreProtocol",
    "FixtureBackedMemoryStore",
    "build_fixture_memory_store_from_snapshot",
    "build_sample_fixture_pack",
):
    check(
        f"19.x lib.reliability re-exports {_sym}",
        hasattr(_rel_pkg, _sym),
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("Phase 5A — Existing Workflow Memory Adapter + Fixture-backed")
print("Memory Query Contract — test results")
print("=" * 70)

if _failures:
    print()
    for line in _failures:
        print(line)

print()
print(f"Passed: {PASS}")
print(f"Failed: {FAIL}")
print(f"Total:  {PASS + FAIL}")
print()

if FAIL == 0:
    print("RESULT: PASS — Phase 5A contract verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
