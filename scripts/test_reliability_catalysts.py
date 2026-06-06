"""
scripts/test_reliability_catalysts.py

Test suite for lib/reliability/catalysts.py — Phase 2G:
Catalyst / Earnings / Estimate Revision Schema Foundation.

Tests use synthetic/manual payloads; no real network calls are made.
No live app files are imported or modified.

Run:
    python3 scripts/test_reliability_catalysts.py

Expected: all assertions pass, 0 failures.
"""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import copy

from lib.reliability.catalysts import (
    # Literal type aliases
    CatalystType,
    CatalystTiming,
    CatalystMateriality,
    CatalystSourceType,
    EarningsStatus,
    EarningsSurpriseDirection,
    EstimateMetric,
    RevisionDirection,
    RevisionSourceType,
    # Models
    CatalystEvent,
    EarningsEvent,
    EstimateRevision,
    CatalystSnapshot,
    CatalystCoverageSummary,
    # Helpers
    infer_catalyst_timing,
    infer_earnings_surprise_direction,
    infer_revision_direction,
    calculate_revision_pct,
    catalyst_snapshot_from_components,
    catalyst_tool_result_from_snapshot,
    extract_catalyst_event_paths,
    summarize_catalyst_snapshot_coverage,
    validate_catalyst_snapshot,
)
from lib.reliability.schemas import EvidenceRef, AgentResult, Finding
from lib.reliability.evidence_store import EvidenceStore
from lib.reliability.validators import validate_agent_result
from lib.reliability.run_context import create_run_context

_PASS = 0
_FAIL = 0


def _check(label: str, condition: bool) -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {label}")


def _expect_error(label: str, fn) -> None:
    """Expect fn() to raise an exception (ValueError or similar)."""
    global _PASS, _FAIL
    try:
        fn()
        _FAIL += 1
        print(f"  FAIL (no error raised): {label}")
    except Exception:
        _PASS += 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_catalyst(
    catalyst_id: str = "cat_001",
    ticker: str = "NVDA",
    catalyst_type: str = "earnings",
    title: str = "NVDA Q1 2026 Earnings",
    event_date: str | None = "2026-05-28",
    timing: str = "upcoming",
    materiality: str = "high",
    source_type: str = "company",
) -> CatalystEvent:
    return CatalystEvent(
        catalyst_id=catalyst_id,
        ticker=ticker,
        catalyst_type=catalyst_type,   # type: ignore[arg-type]
        title=title,
        event_date=event_date,
        timing=timing,                 # type: ignore[arg-type]
        materiality=materiality,       # type: ignore[arg-type]
        source_type=source_type,       # type: ignore[arg-type]
        source_name="NVDA IR",
    )


def _make_earnings(
    earnings_id: str = "earn_001",
    ticker: str = "NVDA",
    status: str = "confirmed",
    report_date: str | None = "2026-05-28",
    consensus_eps: float | None = 5.50,
    actual_eps: float | None = None,
    consensus_revenue: float | None = 26_000_000_000.0,
    actual_revenue: float | None = None,
    implied_move_pct: float | None = 8.5,
) -> EarningsEvent:
    return EarningsEvent(
        earnings_id=earnings_id,
        ticker=ticker,
        fiscal_period="Q1 FY2027",
        fiscal_year=2027,
        report_date=report_date,
        status=status,                 # type: ignore[arg-type]
        consensus_eps=consensus_eps,
        actual_eps=actual_eps,
        consensus_revenue=consensus_revenue,
        actual_revenue=actual_revenue,
        implied_move_pct=implied_move_pct,
    )


def _make_revision(
    revision_id: str = "rev_001",
    ticker: str = "NVDA",
    metric: str = "eps",
    previous_value: float | str | None = 5.20,
    revised_value: float | str | None = 5.50,
    revision_pct: float | None = None,
    direction: str = "upward",
    revision_date: str | None = "2026-05-15",
    source_type: str = "analyst",
) -> EstimateRevision:
    return EstimateRevision(
        revision_id=revision_id,
        ticker=ticker,
        metric=metric,                 # type: ignore[arg-type]
        period="Q1 FY2027",
        previous_value=previous_value,
        revised_value=revised_value,
        revision_pct=revision_pct,
        direction=direction,           # type: ignore[arg-type]
        revision_date=revision_date,
        source_type=source_type,       # type: ignore[arg-type]
        analyst_firm="Goldman Sachs",
    )


def _make_snapshot(
    snapshot_id: str = "snap_001",
    ticker: str = "NVDA",
    as_of: str = "2026-05-22",
    catalysts: list | None = None,
    earnings_events: list | None = None,
    estimate_revisions: list | None = None,
) -> CatalystSnapshot:
    return CatalystSnapshot(
        snapshot_id=snapshot_id,
        ticker=ticker,
        as_of=as_of,
        catalysts=catalysts or [],
        earnings_events=earnings_events or [],
        estimate_revisions=estimate_revisions or [],
    )


# ---------------------------------------------------------------------------
# Tests: CatalystEvent
# ---------------------------------------------------------------------------

print("\n--- CatalystEvent ---")

# T1: accepts valid event
c = _make_catalyst()
_check("T1 CatalystEvent accepts valid event", c.catalyst_id == "cat_001" and c.ticker == "NVDA")

# T2: rejects empty catalyst_id
_expect_error("T2 CatalystEvent rejects empty catalyst_id",
    lambda: CatalystEvent(catalyst_id="", ticker="NVDA", title="X"))

# T3: rejects empty ticker
_expect_error("T3 CatalystEvent rejects empty ticker",
    lambda: CatalystEvent(catalyst_id="x", ticker="", title="X"))

# T4: rejects empty title
_expect_error("T4 CatalystEvent rejects empty title",
    lambda: CatalystEvent(catalyst_id="x", ticker="NVDA", title=""))


# ---------------------------------------------------------------------------
# Tests: EarningsEvent
# ---------------------------------------------------------------------------

print("\n--- EarningsEvent ---")

# T5: accepts valid event
e = _make_earnings()
_check("T5 EarningsEvent accepts valid event", e.earnings_id == "earn_001" and e.ticker == "NVDA")

# T6: rejects empty earnings_id
_expect_error("T6 EarningsEvent rejects empty earnings_id",
    lambda: EarningsEvent(earnings_id="", ticker="NVDA"))

# T7: rejects empty ticker
_expect_error("T7 EarningsEvent rejects empty ticker",
    lambda: EarningsEvent(earnings_id="x", ticker=""))

# T8: rejects invalid fiscal_year (<= 1900)
_expect_error("T8 EarningsEvent rejects invalid fiscal_year",
    lambda: EarningsEvent(earnings_id="x", ticker="NVDA", fiscal_year=1900))

# T9: rejects negative implied_move_pct
_expect_error("T9 EarningsEvent rejects negative implied_move_pct",
    lambda: EarningsEvent(earnings_id="x", ticker="NVDA", implied_move_pct=-1.0))

# T10: rejects negative revenue values
_expect_error("T10 EarningsEvent rejects negative consensus_revenue",
    lambda: EarningsEvent(earnings_id="x", ticker="NVDA", consensus_revenue=-1.0))
_expect_error("T10b EarningsEvent rejects negative actual_revenue",
    lambda: EarningsEvent(earnings_id="x", ticker="NVDA", actual_revenue=-1.0))


# ---------------------------------------------------------------------------
# Tests: EstimateRevision
# ---------------------------------------------------------------------------

print("\n--- EstimateRevision ---")

# T11: accepts valid EPS revision
r = _make_revision()
_check("T11 EstimateRevision accepts valid EPS revision",
    r.revision_id == "rev_001" and r.metric == "eps")

# T12: accepts string rating revision
r_str = EstimateRevision(
    revision_id="rev_str_001",
    ticker="NVDA",
    metric="rating",
    previous_value="hold",
    revised_value="buy",
    direction="upward",
    revision_date="2026-05-15",
)
_check("T12 EstimateRevision accepts string rating revision",
    r_str.previous_value == "hold" and r_str.revised_value == "buy")

# T13: rejects empty revision_id
_expect_error("T13 EstimateRevision rejects empty revision_id",
    lambda: EstimateRevision(revision_id="", ticker="NVDA", metric="eps"))

# T14: rejects empty ticker
_expect_error("T14 EstimateRevision rejects empty ticker",
    lambda: EstimateRevision(revision_id="x", ticker="", metric="eps"))


# ---------------------------------------------------------------------------
# Tests: CatalystSnapshot
# ---------------------------------------------------------------------------

print("\n--- CatalystSnapshot ---")

# T15: accepts partial/no data
snap_empty = _make_snapshot()
_check("T15 CatalystSnapshot accepts partial/no data",
    len(snap_empty.catalysts) == 0 and len(snap_empty.earnings_events) == 0)

# T16: rejects empty snapshot_id
_expect_error("T16 CatalystSnapshot rejects empty snapshot_id",
    lambda: CatalystSnapshot(snapshot_id="", ticker="NVDA", as_of="2026-05-22"))

# T17: rejects empty ticker
_expect_error("T17 CatalystSnapshot rejects empty ticker",
    lambda: CatalystSnapshot(snapshot_id="s1", ticker="", as_of="2026-05-22"))

# T18: rejects empty as_of
_expect_error("T18 CatalystSnapshot rejects empty as_of",
    lambda: CatalystSnapshot(snapshot_id="s1", ticker="NVDA", as_of=""))


# ---------------------------------------------------------------------------
# Tests: infer_catalyst_timing
# ---------------------------------------------------------------------------

print("\n--- infer_catalyst_timing ---")

# T19: timing inference
_check("T19a infer_catalyst_timing past",
    infer_catalyst_timing("2026-01-01", "2026-05-22") == "past")
_check("T19b infer_catalyst_timing upcoming",
    infer_catalyst_timing("2026-12-31", "2026-05-22") == "upcoming")
_check("T19c infer_catalyst_timing ongoing",
    infer_catalyst_timing("2026-05-22", "2026-05-22") == "ongoing")
_check("T19d infer_catalyst_timing unknown (None event_date)",
    infer_catalyst_timing(None, "2026-05-22") == "unknown")
_check("T19e infer_catalyst_timing unknown (None as_of)",
    infer_catalyst_timing("2026-05-22", None) == "unknown")
_check("T19f infer_catalyst_timing unknown (both None)",
    infer_catalyst_timing(None, None) == "unknown")
_check("T19g infer_catalyst_timing unknown (unparseable date)",
    infer_catalyst_timing("not-a-date", "2026-05-22") == "unknown")


# ---------------------------------------------------------------------------
# Tests: infer_earnings_surprise_direction
# ---------------------------------------------------------------------------

print("\n--- infer_earnings_surprise_direction ---")

# T20: surprise direction
_check("T20a beat (both positive)",
    infer_earnings_surprise_direction(5.2, 3.1) == "beat")
_check("T20b miss (both negative)",
    infer_earnings_surprise_direction(-2.0, -1.5) == "miss")
_check("T20c inline (both zero)",
    infer_earnings_surprise_direction(0.0, 0.0) == "inline")
_check("T20d unknown (mixed signs)",
    infer_earnings_surprise_direction(3.0, -1.5) == "unknown")
_check("T20e unknown (both None)",
    infer_earnings_surprise_direction(None, None) == "unknown")
_check("T20f beat (one positive, one None)",
    infer_earnings_surprise_direction(5.0, None) == "beat")
_check("T20g miss (one negative, one None)",
    infer_earnings_surprise_direction(None, -2.0) == "miss")


# ---------------------------------------------------------------------------
# Tests: infer_revision_direction
# ---------------------------------------------------------------------------

print("\n--- infer_revision_direction ---")

# T21: numeric direction
_check("T21a upward (numeric)",
    infer_revision_direction(2.50, 2.75) == "upward")
_check("T21b downward (numeric)",
    infer_revision_direction(2.75, 2.50) == "downward")
_check("T21c unchanged (numeric)",
    infer_revision_direction(2.50, 2.50) == "unchanged")

# T22: rating direction
_check("T22a upward (hold → buy)",
    infer_revision_direction("hold", "buy") == "upward")
_check("T22b downward (buy → sell)",
    infer_revision_direction("buy", "sell") == "downward")
_check("T22c unchanged (hold → hold)",
    infer_revision_direction("hold", "hold") == "unchanged")
_check("T22d unknown (unrecognised rating)",
    infer_revision_direction("xyz_rating", "buy") == "unknown")

# T23: None handling
_check("T21d unknown (None previous)",
    infer_revision_direction(None, 2.75) == "unknown")
_check("T21e unknown (None revised)",
    infer_revision_direction(2.75, None) == "unknown")


# ---------------------------------------------------------------------------
# Tests: calculate_revision_pct
# ---------------------------------------------------------------------------

print("\n--- calculate_revision_pct ---")

# T23: numeric pct
result = calculate_revision_pct(2.00, 2.50)
_check("T23a calculate_revision_pct 25.0%",
    result is not None and abs(result - 25.0) < 0.001)

result2 = calculate_revision_pct(2.50, 2.00)
_check("T23b calculate_revision_pct -20.0%",
    result2 is not None and abs(result2 - (-20.0)) < 0.001)

# T24: zero previous value → None
_check("T24 calculate_revision_pct returns None for zero previous",
    calculate_revision_pct(0.0, 2.00) is None)

_check("T24b calculate_revision_pct returns None for None",
    calculate_revision_pct(None, 2.00) is None)

_check("T24c calculate_revision_pct returns None for string (non-numeric)",
    calculate_revision_pct("hold", "buy") is None)


# ---------------------------------------------------------------------------
# Tests: catalyst_snapshot_from_components
# ---------------------------------------------------------------------------

print("\n--- catalyst_snapshot_from_components ---")

# T25: builds snapshot without mutating inputs
cat = _make_catalyst()
earn = _make_earnings()
rev = _make_revision()

original_cats = [cat]
original_earns = [earn]
original_revs = [rev]
original_meta = {"source": "test"}

snap = catalyst_snapshot_from_components(
    snapshot_id="snap_002",
    ticker="NVDA",
    as_of="2026-05-22",
    catalysts=original_cats,
    earnings_events=original_earns,
    estimate_revisions=original_revs,
    metadata=original_meta,
)

_check("T25a snapshot_from_components builds snapshot",
    snap.snapshot_id == "snap_002" and snap.ticker == "NVDA")
_check("T25b snapshot_from_components has catalysts",
    len(snap.catalysts) == 1)
_check("T25c snapshot_from_components has earnings_events",
    len(snap.earnings_events) == 1)
_check("T25d snapshot_from_components has estimate_revisions",
    len(snap.estimate_revisions) == 1)

# Verify non-mutation: modifying original lists does not affect snap
original_cats.append(_make_catalyst(catalyst_id="cat_extra"))
original_earns.append(_make_earnings(earnings_id="earn_extra"))
original_revs.append(_make_revision(revision_id="rev_extra"))
original_meta["extra"] = "injected"

_check("T25e snapshot_from_components does not mutate input catalysts list",
    len(snap.catalysts) == 1)
_check("T25f snapshot_from_components does not mutate input earnings list",
    len(snap.earnings_events) == 1)
_check("T25g snapshot_from_components does not mutate input revisions list",
    len(snap.estimate_revisions) == 1)
_check("T25h snapshot_from_components does not mutate input metadata dict",
    "extra" not in snap.metadata)


# ---------------------------------------------------------------------------
# Tests: catalyst_tool_result_from_snapshot
# ---------------------------------------------------------------------------

print("\n--- catalyst_tool_result_from_snapshot ---")

snap_tr = catalyst_snapshot_from_components(
    snapshot_id="snap_tr_001",
    ticker="NVDA",
    as_of="2026-05-22",
    catalysts=[_make_catalyst()],
    earnings_events=[_make_earnings()],
    estimate_revisions=[_make_revision()],
)

# T26: returns valid ToolResult
tr = catalyst_tool_result_from_snapshot("run_2g_001", snap_tr)
_check("T26 catalyst_tool_result_from_snapshot returns ToolResult",
    tr is not None and tr.tool_name is not None)

# T27: stable tool_name and target
_check("T27a tool_name is stable 'catalyst_snapshot'",
    tr.tool_name == "catalyst_snapshot")
_check("T27b target defaults to snapshot.ticker",
    snap_tr.ticker in tr.evidence_id)

# T28: payload includes required fields
outputs = tr.outputs
_check("T28a payload includes snapshot_id",
    "snapshot_id" in outputs and outputs["snapshot_id"] == "snap_tr_001")
_check("T28b payload includes ticker",
    "ticker" in outputs and outputs["ticker"] == "NVDA")
_check("T28c payload includes catalysts",
    "catalysts" in outputs and len(outputs["catalysts"]) == 1)
_check("T28d payload includes earnings_events",
    "earnings_events" in outputs and len(outputs["earnings_events"]) == 1)
_check("T28e payload includes estimate_revisions",
    "estimate_revisions" in outputs and len(outputs["estimate_revisions"]) == 1)

# T29: evidence_id deterministic
tr2 = catalyst_tool_result_from_snapshot("run_2g_001", snap_tr)
_check("T29 evidence_id deterministic for same run_id/snapshot",
    tr.evidence_id == tr2.evidence_id)

# Verify different run_id produces different evidence_id
tr3 = catalyst_tool_result_from_snapshot("run_2g_002", snap_tr)
_check("T29b different run_id produces different evidence_id",
    tr.evidence_id != tr3.evidence_id)


# ---------------------------------------------------------------------------
# Tests: extract_catalyst_event_paths
# ---------------------------------------------------------------------------

print("\n--- extract_catalyst_event_paths ---")

snap_paths = catalyst_snapshot_from_components(
    snapshot_id="snap_paths_001",
    ticker="NVDA",
    as_of="2026-05-22",
    catalysts=[_make_catalyst()],
    earnings_events=[_make_earnings()],
    estimate_revisions=[_make_revision()],
)

# T30: returns deterministic paths
paths = extract_catalyst_event_paths(snap_paths)
_check("T30a extract_catalyst_event_paths returns list",
    isinstance(paths, list) and len(paths) > 0)
_check("T30b catalysts.0.title in paths",
    "catalysts.0.title" in paths)
_check("T30c earnings_events.0.report_date in paths",
    "earnings_events.0.report_date" in paths)
_check("T30d estimate_revisions.0.metric in paths",
    "estimate_revisions.0.metric" in paths)
_check("T30e estimate_revisions.0.direction in paths",
    "estimate_revisions.0.direction" in paths)

# T31: validate through existing evidence binding validator
run_ctx = create_run_context(ticker="NVDA", task="phase2g_test")
store = EvidenceStore(run_dir=run_ctx.run_dir)

tr_valid = catalyst_tool_result_from_snapshot(run_ctx.run_id, snap_paths)
eid = store.add_tool_result(tr_valid)

# Build AgentResult with a field_path ref to catalysts.0.title
ref_valid = EvidenceRef(
    evidence_id=eid,
    field_path="catalysts.0.title",
    tool_name="catalyst_snapshot",
)
ar_valid = AgentResult(
    agent_name="test_catalyst_agent",
    ticker="NVDA",
    run_id=run_ctx.run_id,
    findings=[
        Finding(
            text="Upcoming earnings catalyst detected.",
            evidence=[ref_valid],
        )
    ],
)
report_valid = validate_agent_result(ar_valid, store, run_id=run_ctx.run_id, target_name="NVDA")
_check("T31 valid field path catalysts.0.title passes validation",
    report_valid.passed and not any(
        i.code == "INVALID_EVIDENCE_FIELD_PATH_BINDING" for i in report_valid.issues
    ))

# T32: invalid list-index path fails validation
ref_invalid = EvidenceRef(
    evidence_id=eid,
    field_path="catalysts.99.title",
    tool_name="catalyst_snapshot",
)
ar_invalid = AgentResult(
    agent_name="test_catalyst_agent",
    ticker="NVDA",
    run_id=run_ctx.run_id,
    findings=[
        Finding(
            text="Upcoming earnings catalyst detected.",
            evidence=[ref_invalid],
        )
    ],
)
report_invalid = validate_agent_result(ar_invalid, store, run_id=run_ctx.run_id, target_name="NVDA")
_check("T32 invalid path catalysts.99.title fails validation",
    any(i.code == "INVALID_EVIDENCE_FIELD_PATH_BINDING" for i in report_invalid.issues))


# ---------------------------------------------------------------------------
# Tests: summarize_catalyst_snapshot_coverage
# ---------------------------------------------------------------------------

print("\n--- summarize_catalyst_snapshot_coverage ---")

snap_summary = catalyst_snapshot_from_components(
    snapshot_id="snap_sum_001",
    ticker="NVDA",
    as_of="2026-05-22",
    catalysts=[
        _make_catalyst(catalyst_id="c1", timing="upcoming", materiality="high"),
        _make_catalyst(catalyst_id="c2", timing="past", materiality="medium",
                       catalyst_type="guidance"),
    ],
    earnings_events=[_make_earnings()],
    estimate_revisions=[
        _make_revision(revision_id="r1", direction="upward"),
        _make_revision(revision_id="r2", direction="downward",
                       previous_value=5.50, revised_value=5.10),
    ],
)
summary = summarize_catalyst_snapshot_coverage(snap_summary)

# T33: counts catalysts/earnings/revisions
_check("T33 catalyst_count == 2", summary.catalyst_count == 2)
_check("T33b earnings_event_count == 1", summary.earnings_event_count == 1)
_check("T33c estimate_revision_count == 2", summary.estimate_revision_count == 2)

# T34: counts upcoming catalysts
_check("T34 upcoming_catalyst_count == 1", summary.upcoming_catalyst_count == 1)

# T35: counts high materiality catalysts
_check("T35 high_materiality_count == 1", summary.high_materiality_count == 1)

# T36: counts upward/downward revisions
_check("T36a upward_revision_count == 1", summary.upward_revision_count == 1)
_check("T36b downward_revision_count == 1", summary.downward_revision_count == 1)

_check("T36c categories_present non-empty",
    len(summary.categories_present) > 0)
_check("T36d revision_metrics_present non-empty",
    len(summary.revision_metrics_present) > 0)

# Empty snapshot warns
snap_empty2 = _make_snapshot()
summary_empty = summarize_catalyst_snapshot_coverage(snap_empty2)
_check("T36e empty snapshot produces warning",
    len(summary_empty.warnings) > 0)


# ---------------------------------------------------------------------------
# Tests: validate_catalyst_snapshot
# ---------------------------------------------------------------------------

print("\n--- validate_catalyst_snapshot ---")

# T37: warns on empty snapshot
snap_empty3 = _make_snapshot()
warnings_empty = validate_catalyst_snapshot(snap_empty3)
_check("T37 warns on empty snapshot", len(warnings_empty) > 0)

# T38: warns on ticker mismatch
snap_mismatch = _make_snapshot(
    catalysts=[
        CatalystEvent(
            catalyst_id="c_bad", ticker="AAPL",  # wrong ticker
            title="Wrong ticker event",
        )
    ]
)
warnings_mismatch = validate_catalyst_snapshot(snap_mismatch)
_check("T38 warns on catalyst ticker mismatch",
    any("ticker" in w and "AAPL" not in snap_mismatch.ticker for w in warnings_mismatch))

# T39: warns on missing evidence refs
snap_no_ev = _make_snapshot(
    catalysts=[_make_catalyst()],  # no evidence_refs
)
warnings_no_ev = validate_catalyst_snapshot(snap_no_ev)
_check("T39 warns on missing evidence refs",
    any("evidence_refs" in w for w in warnings_no_ev))

# T40: warns on high materiality missing date
cat_high_no_date = CatalystEvent(
    catalyst_id="c_high_nodate",
    ticker="NVDA",
    title="High Impact Event",
    materiality="high",
    event_date=None,
)
snap_high_no_date = _make_snapshot(catalysts=[cat_high_no_date])
warnings_high = validate_catalyst_snapshot(snap_high_no_date)
_check("T40 warns on high materiality missing event_date",
    any("materiality" in w or "event_date" in w for w in warnings_high))

# T41: warns on reported earnings missing actuals
earn_reported_no_actuals = EarningsEvent(
    earnings_id="earn_r_001",
    ticker="NVDA",
    status="reported",
    actual_eps=None,
    actual_revenue=None,
)
snap_reported = _make_snapshot(earnings_events=[earn_reported_no_actuals])
warnings_reported = validate_catalyst_snapshot(snap_reported)
_check("T41 warns on reported earnings missing actuals",
    any("reported" in w or "actual" in w for w in warnings_reported))

# T42: warns on confirmed/estimated earnings missing report_date
earn_confirmed_no_date = EarningsEvent(
    earnings_id="earn_c_001",
    ticker="NVDA",
    status="confirmed",
    report_date=None,
)
snap_confirmed = _make_snapshot(earnings_events=[earn_confirmed_no_date])
warnings_confirmed = validate_catalyst_snapshot(snap_confirmed)
_check("T42 warns on confirmed earnings missing report_date",
    any("report_date" in w or "confirmed" in w for w in warnings_confirmed))

# T43: warns on revision direction conflict
rev_conflict = EstimateRevision(
    revision_id="rev_conflict",
    ticker="NVDA",
    metric="eps",
    previous_value=5.50,
    revised_value=5.10,  # decreased but direction=upward is wrong
    direction="upward",
    revision_date="2026-05-15",
)
snap_conflict = _make_snapshot(estimate_revisions=[rev_conflict])
warnings_conflict = validate_catalyst_snapshot(snap_conflict)
_check("T43 warns on revision direction conflict",
    any("conflict" in w or "direction" in w for w in warnings_conflict))

# T44: warns on missing revision_date
rev_no_date = EstimateRevision(
    revision_id="rev_no_date",
    ticker="NVDA",
    metric="revenue",
    revision_date=None,
)
snap_no_rev_date = _make_snapshot(estimate_revisions=[rev_no_date])
warnings_no_rev_date = validate_catalyst_snapshot(snap_no_rev_date)
_check("T44 warns on missing revision_date",
    any("revision_date" in w for w in warnings_no_rev_date))

# T45: warns on duplicate catalyst title/date
cat_dup1 = CatalystEvent(
    catalyst_id="c_dup1", ticker="NVDA",
    title="Q1 Earnings", event_date="2026-05-28",
)
cat_dup2 = CatalystEvent(
    catalyst_id="c_dup2", ticker="NVDA",
    title="Q1 Earnings", event_date="2026-05-28",
)
snap_dup_cat = _make_snapshot(catalysts=[cat_dup1, cat_dup2])
warnings_dup_cat = validate_catalyst_snapshot(snap_dup_cat)
_check("T45 warns on duplicate catalyst title/date",
    any("Duplicate catalyst" in w for w in warnings_dup_cat))

# T46: warns on duplicate earnings report_date/fiscal_period
earn_dup1 = EarningsEvent(
    earnings_id="earn_d1", ticker="NVDA",
    report_date="2026-05-28", fiscal_period="Q1 FY2027",
)
earn_dup2 = EarningsEvent(
    earnings_id="earn_d2", ticker="NVDA",
    report_date="2026-05-28", fiscal_period="Q1 FY2027",
)
snap_dup_earn = _make_snapshot(earnings_events=[earn_dup1, earn_dup2])
warnings_dup_earn = validate_catalyst_snapshot(snap_dup_earn)
_check("T46 warns on duplicate earnings report_date/fiscal_period",
    any("Duplicate earnings" in w for w in warnings_dup_earn))

# T47: warns on duplicate revision metric/period/date
rev_dup1 = EstimateRevision(
    revision_id="rev_d1", ticker="NVDA",
    metric="eps", period="Q1 FY2027", revision_date="2026-05-15",
)
rev_dup2 = EstimateRevision(
    revision_id="rev_d2", ticker="NVDA",
    metric="eps", period="Q1 FY2027", revision_date="2026-05-15",
)
snap_dup_rev = _make_snapshot(estimate_revisions=[rev_dup1, rev_dup2])
warnings_dup_rev = validate_catalyst_snapshot(snap_dup_rev)
_check("T47 warns on duplicate revision metric/period/date",
    any("Duplicate revision" in w for w in warnings_dup_rev))


# ---------------------------------------------------------------------------
# Tests: Serialization roundtrips
# ---------------------------------------------------------------------------

print("\n--- Serialization roundtrips ---")

# T48: CatalystCoverageSummary serialization roundtrip
cs = CatalystCoverageSummary(
    ticker="NVDA",
    catalyst_count=2,
    upcoming_catalyst_count=1,
    high_materiality_count=1,
    earnings_event_count=1,
    estimate_revision_count=2,
    upward_revision_count=1,
    downward_revision_count=1,
    categories_present=["earnings", "guidance"],
    revision_metrics_present=["eps", "revenue"],
)
cs_dict = cs.model_dump()
cs_restored = CatalystCoverageSummary(**cs_dict)
_check("T48 CatalystCoverageSummary serialization roundtrip",
    cs_restored.ticker == "NVDA"
    and cs_restored.catalyst_count == 2
    and cs_restored.upward_revision_count == 1
)

# T49: CatalystSnapshot serialization roundtrip
snap_full = catalyst_snapshot_from_components(
    snapshot_id="snap_rt_001",
    ticker="NVDA",
    as_of="2026-05-22",
    catalysts=[_make_catalyst()],
    earnings_events=[_make_earnings()],
    estimate_revisions=[_make_revision()],
    warnings=["test warning"],
    metadata={"phase": "2G"},
)
snap_dict = snap_full.model_dump()
snap_restored = CatalystSnapshot(**snap_dict)
_check("T49a CatalystSnapshot serialization roundtrip ticker",
    snap_restored.ticker == "NVDA")
_check("T49b CatalystSnapshot serialization roundtrip catalysts",
    len(snap_restored.catalysts) == 1)
_check("T49c CatalystSnapshot serialization roundtrip earnings_events",
    len(snap_restored.earnings_events) == 1)
_check("T49d CatalystSnapshot serialization roundtrip estimate_revisions",
    len(snap_restored.estimate_revisions) == 1)
_check("T49e CatalystSnapshot serialization roundtrip warnings",
    snap_restored.warnings == ["test warning"])


# ---------------------------------------------------------------------------
# Tests: No live imports or network calls
# ---------------------------------------------------------------------------

print("\n--- No live imports / no network calls ---")

# T50: no live app files imported
# Use exact-name or module-prefix matching to avoid false positives
# (e.g. "app" as substring would match "pydantic.v1.compat" etc.)
_live_modules = [
    "app",
    "pages",
    "lib.llm_orchestrator",
    "lib.data_fetcher",
    "lib.workflow_state",
    "lib.valuation",
    "lib.technical",
    "lib.rotation",
]
for mod_name in _live_modules:
    # Match exact name or any submodule (e.g. "pages.foo")
    _check(f"T50 {mod_name} not imported",
        not any(
            m == mod_name or m.startswith(mod_name + ".")
            for m in sys.modules
        )
    )

# T51: no external catalyst/earnings/estimate/API/network calls
# (verified by design: catalysts.py imports only pydantic, lib.reliability.adapters,
# lib.reliability.schemas — confirmed by inspecting the module's imports)
import lib.reliability.catalysts as _cats_mod
import inspect
_src = inspect.getsource(_cats_mod)
_check("T51a no requests/urllib import in catalysts.py",
    "import requests" not in _src and "import urllib" not in _src)
_check("T51b no yfinance import in catalysts.py",
    "yfinance" not in _src)
_check("T51c no polygon import in catalysts.py",
    "polygon" not in _src.lower())
_check("T51d no finnhub import in catalysts.py",
    "finnhub" not in _src.lower())


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

print(f"\n{'='*50}")
print(f"Results: {_PASS} passed, {_FAIL} failed")
if _FAIL > 0:
    sys.exit(1)
else:
    print("All tests passed.")
