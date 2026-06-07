"""
scripts/test_reliability_validation_aggregator.py

Test suite for lib/reliability/validation_aggregator.py — Phase 2H:
Validation Aggregator.

Tests use synthetic payloads; no real network calls are made.
No live app files are imported or modified.

Run:
    python3 scripts/test_reliability_validation_aggregator.py

Expected: all assertions pass, 0 failures.
"""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.reliability.validation_aggregator import (
    # Literal type aliases
    ValidationDomain,
    ValidationSeverity,
    ValidationStatus,
    ValidationItemType,
    # Models
    AggregatedValidationItem,
    ValidationAggregate,
    # Helpers
    make_validation_item_id,
    warning_to_validation_item,
    validation_report_to_items,
    aggregate_validation_items,
    aggregate_warning_groups,
    merge_validation_aggregates,
    summarize_validation_aggregate,
    collect_phase2_validation_warnings,
    validation_aggregate_tool_result_from_aggregate,
)
from lib.reliability.schemas import (
    ValidationReport, ValidationIssue, AgentResult, Finding, EvidenceRef,
)
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

def _make_item(
    item_id: str = "item_001",
    domain: str = "news",
    severity: str = "warning",
    item_type: str = "missing_data",
    message: str = "No events in snapshot.",
    source_name: str | None = "news_module",
    blocking: bool = False,
) -> AggregatedValidationItem:
    return AggregatedValidationItem(
        item_id=item_id,
        domain=domain,           # type: ignore[arg-type]
        severity=severity,       # type: ignore[arg-type]
        item_type=item_type,     # type: ignore[arg-type]
        message=message,
        source_name=source_name,
        blocking=blocking,
    )


def _make_aggregate(
    aggregate_id: str = "agg_001",
    as_of: str = "2026-05-22",
    items: list | None = None,
    status: str = "pass",
    critical_count: int = 0,
    warning_count: int = 0,
) -> ValidationAggregate:
    return ValidationAggregate(
        aggregate_id=aggregate_id,
        as_of=as_of,
        status=status,           # type: ignore[arg-type]
        items=items or [],
        critical_count=critical_count,
        warning_count=warning_count,
    )


def _make_validation_report(
    run_id: str = "run_test_001",
    target_name: str = "NVDA",
    passed: bool = True,
    issues: list | None = None,
) -> ValidationReport:
    return ValidationReport(
        passed=passed,
        run_id=run_id,
        target_name=target_name,
        issues=issues or [],
    )


# ---------------------------------------------------------------------------
# Tests: AggregatedValidationItem
# ---------------------------------------------------------------------------

print("\n--- AggregatedValidationItem ---")

# T1: accepts valid item
item = _make_item()
_check("T1 AggregatedValidationItem accepts valid item",
    item.item_id == "item_001" and item.message == "No events in snapshot.")

# T2: rejects empty item_id
_expect_error("T2 AggregatedValidationItem rejects empty item_id",
    lambda: AggregatedValidationItem(
        item_id="", domain="news", message="Some warning."))

# T3: rejects empty message
_expect_error("T3 AggregatedValidationItem rejects empty message",
    lambda: AggregatedValidationItem(
        item_id="x", domain="news", message=""))


# ---------------------------------------------------------------------------
# Tests: ValidationAggregate
# ---------------------------------------------------------------------------

print("\n--- ValidationAggregate ---")

# T4: accepts empty item list
agg_empty = _make_aggregate()
_check("T4 ValidationAggregate accepts empty item list",
    agg_empty.items == [] and agg_empty.critical_count == 0)

# T5: rejects empty aggregate_id
_expect_error("T5 ValidationAggregate rejects empty aggregate_id",
    lambda: ValidationAggregate(aggregate_id="", as_of="2026-05-22"))

# T6: rejects empty as_of
_expect_error("T6 ValidationAggregate rejects empty as_of",
    lambda: ValidationAggregate(aggregate_id="x", as_of=""))

# T7: rejects negative counts
_expect_error("T7 ValidationAggregate rejects negative critical_count",
    lambda: ValidationAggregate(
        aggregate_id="x", as_of="2026-05-22", critical_count=-1))
_expect_error("T7b ValidationAggregate rejects negative warning_count",
    lambda: ValidationAggregate(
        aggregate_id="x", as_of="2026-05-22", warning_count=-1))


# ---------------------------------------------------------------------------
# Tests: make_validation_item_id
# ---------------------------------------------------------------------------

print("\n--- make_validation_item_id ---")

# T8: deterministic
id1 = make_validation_item_id("news", "No events.", source_name="snap_001")
id2 = make_validation_item_id("news", "No events.", source_name="snap_001")
_check("T8 make_validation_item_id is deterministic", id1 == id2)

# T9: changes with message/source
id3 = make_validation_item_id("news", "Different message.", source_name="snap_001")
id4 = make_validation_item_id("news", "No events.", source_name="snap_002")
id5 = make_validation_item_id("catalyst", "No events.", source_name="snap_001")
_check("T9a make_validation_item_id changes with different message", id1 != id3)
_check("T9b make_validation_item_id changes with different source_name", id1 != id4)
_check("T9c make_validation_item_id changes with different domain", id1 != id5)


# ---------------------------------------------------------------------------
# Tests: warning_to_validation_item
# ---------------------------------------------------------------------------

print("\n--- warning_to_validation_item ---")

# T10: creates warning item
w_item = warning_to_validation_item(
    "No events in snapshot.", "news", source_name="news_module"
)
_check("T10a warning_to_validation_item creates item", w_item is not None)
_check("T10b warning_to_validation_item has correct message",
    w_item.message == "No events in snapshot.")
_check("T10c warning_to_validation_item severity=warning", w_item.severity == "warning")
_check("T10d warning_to_validation_item not blocking", not w_item.blocking)

# T11: sets blocking true for critical severity
crit_item = warning_to_validation_item(
    "Critical error occurred.", "agent_result", severity="critical"
)
_check("T11a critical severity sets blocking=True", crit_item.blocking is True)
_check("T11b critical severity item is critical", crit_item.severity == "critical")

# T12: does not mutate metadata
orig_meta = {"key": "value"}
import copy
meta_copy = copy.copy(orig_meta)
item_with_meta = warning_to_validation_item(
    "Test warning.", "system", metadata=orig_meta
)
orig_meta["injected"] = "mutation"
_check("T12 warning_to_validation_item does not mutate metadata",
    "injected" not in item_with_meta.metadata)


# ---------------------------------------------------------------------------
# Tests: validation_report_to_items
# ---------------------------------------------------------------------------

print("\n--- validation_report_to_items ---")

# T13: converts warning issue
warn_report = _make_validation_report(
    passed=True,
    issues=[
        ValidationIssue(
            severity="warning",
            code="MISSING_EVIDENCE",
            message="Finding has no evidence references.",
            location="findings[0]",
        )
    ]
)
items_from_report = validation_report_to_items(warn_report)
_check("T13a validation_report_to_items produces items",
    len(items_from_report) == 1)
_check("T13b warning issue → warning severity",
    items_from_report[0].severity == "warning")
_check("T13c MISSING_EVIDENCE → missing_data item_type",
    items_from_report[0].item_type == "missing_data")
_check("T13d domain is agent_result",
    items_from_report[0].domain == "agent_result")

# T14: converts error/critical issue to critical item
err_report = _make_validation_report(
    passed=False,
    issues=[
        ValidationIssue(
            severity="error",
            code="INVALID_EVIDENCE_ID",
            message="Evidence ID 'xyz' not found in store.",
            location="findings[0].evidence[0]",
        )
    ]
)
items_from_err = validation_report_to_items(err_report)
_check("T14a error issue → critical severity",
    items_from_err[0].severity == "critical")
_check("T14b error issue → blocking=True",
    items_from_err[0].blocking is True)
_check("T14c INVALID_EVIDENCE_ID → evidence_binding item_type",
    items_from_err[0].item_type == "evidence_binding")

# Clean report → empty items
clean_report = _make_validation_report(passed=True, issues=[])
_check("T14d clean report → empty item list",
    validation_report_to_items(clean_report) == [])


# ---------------------------------------------------------------------------
# Tests: aggregate_validation_items
# ---------------------------------------------------------------------------

print("\n--- aggregate_validation_items ---")

item_w1 = _make_item(item_id="w1", domain="news", severity="warning", message="Warning 1")
item_w2 = _make_item(item_id="w2", domain="catalyst", severity="warning", message="Warning 2")
item_c1 = _make_item(item_id="c1", domain="agent_result", severity="critical",
                     message="Critical error", blocking=True)
item_i1 = _make_item(item_id="i1", domain="macro", severity="info", message="Info note")

# T15: deduplicates by item_id
dup_item = _make_item(item_id="w1", domain="news", severity="warning", message="Warning 1")
agg_dedup = aggregate_validation_items("agg_dedup", "2026-05-22", [item_w1, dup_item])
_check("T15 aggregate deduplicates by item_id", len(agg_dedup.items) == 1)

# T16: counts correctly
agg_counts = aggregate_validation_items(
    "agg_counts", "2026-05-22", [item_w1, item_w2, item_c1, item_i1]
)
_check("T16a critical_count == 1", agg_counts.critical_count == 1)
_check("T16b warning_count == 2", agg_counts.warning_count == 2)
_check("T16c info_count == 1", agg_counts.info_count == 1)
_check("T16d blocking_count == 1", agg_counts.blocking_count == 1)

# T17: status pass when no warnings/errors
agg_pass = aggregate_validation_items("agg_pass", "2026-05-22", [])
_check("T17 status pass for empty items", agg_pass.status == "pass")

agg_info_only = aggregate_validation_items("agg_info", "2026-05-22", [item_i1])
_check("T17b status pass for info-only items", agg_info_only.status == "pass")

# T18: status pass_with_warnings when warning exists
agg_warn = aggregate_validation_items("agg_warn", "2026-05-22", [item_w1])
_check("T18 status pass_with_warnings for warning items",
    agg_warn.status == "pass_with_warnings")

# T19: status fail when critical exists
agg_crit = aggregate_validation_items("agg_crit", "2026-05-22", [item_c1])
_check("T19 status fail for critical items", agg_crit.status == "fail")

# T20: status fail when blocking item exists
item_blocking = _make_item(
    item_id="b1", domain="news", severity="warning",
    message="Blocking warning", blocking=True,
)
agg_blocking = aggregate_validation_items("agg_block", "2026-05-22", [item_blocking])
_check("T20 status fail when blocking item exists", agg_blocking.status == "fail")

# T21: source_domains deterministic
_check("T21 source_domains sorted and unique",
    agg_counts.source_domains == sorted(set(["news", "catalyst", "agent_result", "macro"])))

# T22: does not mutate input item list
original_list = [item_w1, item_w2]
original_len = len(original_list)
_ = aggregate_validation_items("agg_nomut", "2026-05-22", original_list)
_check("T22 aggregate does not mutate input item list",
    len(original_list) == original_len)


# ---------------------------------------------------------------------------
# Tests: aggregate_warning_groups
# ---------------------------------------------------------------------------

print("\n--- aggregate_warning_groups ---")

# T23: converts domain warning groups
groups = {
    "news": ["NewsSnapshot has no events.", "Duplicate headlines detected."],
    "catalyst": ["CatalystSnapshot is empty."],
}
agg_from_groups = aggregate_warning_groups("agg_grp_001", "2026-05-22", groups)
_check("T23a aggregate_warning_groups produces items",
    len(agg_from_groups.items) == 3)
_check("T23b status pass_with_warnings",
    agg_from_groups.status == "pass_with_warnings")
_check("T23c source_domains contains news and catalyst",
    "news" in agg_from_groups.source_domains
    and "catalyst" in agg_from_groups.source_domains)

# T24: empty warnings returns pass
agg_empty_grps = aggregate_warning_groups("agg_empty_grp", "2026-05-22", {})
_check("T24 empty warning groups returns pass", agg_empty_grps.status == "pass")

agg_all_empty = aggregate_warning_groups(
    "agg_all_empty", "2026-05-22", {"news": [], "catalyst": []}
)
_check("T24b all-empty warning lists returns pass", agg_all_empty.status == "pass")


# ---------------------------------------------------------------------------
# Tests: merge_validation_aggregates
# ---------------------------------------------------------------------------

print("\n--- merge_validation_aggregates ---")

agg_a = aggregate_validation_items(
    "agg_a", "2026-05-22",
    [_make_item(item_id="ma1", message="Warning A1", domain="news"),
     _make_item(item_id="ma2", message="Warning A2", domain="macro")]
)
agg_b = aggregate_validation_items(
    "agg_b", "2026-05-22",
    [_make_item(item_id="mb1", message="Warning B1", domain="catalyst"),
     _make_item(item_id="mb2", message="Warning B2", domain="allocation")]
)

# T25: merges items
merged = merge_validation_aggregates("merged_001", "2026-05-22", [agg_a, agg_b])
_check("T25 merge_validation_aggregates merges items",
    len(merged.items) == 4)

# T26: deduplicates duplicate item IDs
agg_dup_a = aggregate_validation_items(
    "agg_dup_a", "2026-05-22",
    [_make_item(item_id="shared_id", message="Shared warning", domain="news")]
)
agg_dup_b = aggregate_validation_items(
    "agg_dup_b", "2026-05-22",
    [_make_item(item_id="shared_id", message="Shared warning", domain="news"),
     _make_item(item_id="unique_id", message="Unique warning", domain="catalyst")]
)
merged_dup = merge_validation_aggregates(
    "merged_dup", "2026-05-22", [agg_dup_a, agg_dup_b]
)
_check("T26 merge deduplicates duplicate item IDs", len(merged_dup.items) == 2)

# T27: recomputes counts/status
agg_c = aggregate_validation_items(
    "agg_c", "2026-05-22",
    [_make_item(item_id="mc1", severity="critical", message="Critical!", domain="agent_result",
                blocking=True)]
)
merged_crit = merge_validation_aggregates("merged_crit", "2026-05-22", [agg_a, agg_c])
_check("T27a recomputes critical_count",
    merged_crit.critical_count == 1 and merged_crit.warning_count == 2)
_check("T27b recomputes status to fail",
    merged_crit.status == "fail")


# ---------------------------------------------------------------------------
# Tests: summarize_validation_aggregate
# ---------------------------------------------------------------------------

print("\n--- summarize_validation_aggregate ---")

agg_for_summary = aggregate_validation_items(
    "agg_sum", "2026-05-22",
    [_make_item(item_id="s1", message="First warning", domain="news"),
     _make_item(item_id="s2", message="Second warning", domain="catalyst"),
     _make_item(item_id="s3", severity="info", message="Info note", domain="macro")],
    metadata={"phase": "2H"},
)

# T28: returns expected summary
summary = summarize_validation_aggregate(agg_for_summary)
_check("T28a summary has aggregate_id", summary["aggregate_id"] == "agg_sum")
_check("T28b summary has status", "status" in summary)
_check("T28c summary has total_items", summary["total_items"] == 3)
_check("T28d summary has critical_count == 0", summary["critical_count"] == 0)
_check("T28e summary has warning_count == 2", summary["warning_count"] == 2)
_check("T28f summary has info_count == 1", summary["info_count"] == 1)
_check("T28g summary has source_domains", "source_domains" in summary)
_check("T28h summary has top_messages", "top_messages" in summary
    and len(summary["top_messages"]) == 3)
_check("T28i metadata_keys present for non-empty metadata",
    "metadata_keys" in summary and "phase" in summary["metadata_keys"])


# ---------------------------------------------------------------------------
# Tests: collect_phase2_validation_warnings
# ---------------------------------------------------------------------------

print("\n--- collect_phase2_validation_warnings ---")

# T29: works with a NewsSnapshot
from lib.reliability.news import NewsSnapshot

snap_news = NewsSnapshot(
    snapshot_id="snap_news_001",
    ticker="AAPL",
    as_of="2026-05-22",
    events=[],  # empty → will produce warnings
)
groups_news = collect_phase2_validation_warnings(news_snapshot=snap_news)
_check("T29a news domain present in result", "news" in groups_news)
_check("T29b news warnings is a list", isinstance(groups_news["news"], list))
_check("T29c news warnings non-empty (empty snapshot triggers warning)",
    len(groups_news["news"]) > 0)
_check("T29d no other domains present when only news supplied",
    all(k == "news" for k in groups_news.keys()))

# T30: works with a CatalystSnapshot
from lib.reliability.catalysts import CatalystSnapshot

snap_cat = CatalystSnapshot(
    snapshot_id="snap_cat_001",
    ticker="NVDA",
    as_of="2026-05-22",
    catalysts=[],
    earnings_events=[],
    estimate_revisions=[],
)
groups_cat = collect_phase2_validation_warnings(catalyst_snapshot=snap_cat)
_check("T30a catalyst domain present in result", "catalyst" in groups_cat)
_check("T30b catalyst warnings is a list", isinstance(groups_cat["catalyst"], list))
_check("T30c catalyst warnings non-empty (empty snapshot triggers warning)",
    len(groups_cat["catalyst"]) > 0)

# T31: works with an AllocationDecisionSet
from lib.reliability.allocation import AllocationDecisionSet

alloc_ds = AllocationDecisionSet(
    portfolio_id="port_001",
    as_of="2026-05-22",
)
groups_alloc = collect_phase2_validation_warnings(allocation_decision_set=alloc_ds)
_check("T31a allocation domain present in result", "allocation" in groups_alloc)
_check("T31b allocation warnings is a list", isinstance(groups_alloc["allocation"], list))
# Empty decision set triggers "no sizing results" warning
_check("T31c allocation warnings non-empty (empty set triggers warning)",
    len(groups_alloc["allocation"]) > 0)

# Multiple domains together
groups_multi = collect_phase2_validation_warnings(
    news_snapshot=snap_news,
    catalyst_snapshot=snap_cat,
)
_check("T31d multi-domain collection works",
    "news" in groups_multi and "catalyst" in groups_multi)

# None inputs produce no entries
groups_none = collect_phase2_validation_warnings()
_check("T31e no inputs → empty dict", groups_none == {})


# ---------------------------------------------------------------------------
# Tests: validation_aggregate_tool_result_from_aggregate
# ---------------------------------------------------------------------------

print("\n--- validation_aggregate_tool_result_from_aggregate ---")

agg_for_tr = aggregate_warning_groups(
    "agg_tr_001", "2026-05-22",
    {"news": ["No events in snapshot."], "catalyst": ["CatalystSnapshot is empty."]},
)

# T32: returns valid ToolResult
tr = validation_aggregate_tool_result_from_aggregate("run_2h_001", agg_for_tr)
_check("T32 validation_aggregate_tool_result_from_aggregate returns ToolResult",
    tr is not None and tr.tool_name is not None)

# T33: stable tool_name and target
_check("T33a tool_name is stable 'validation_aggregate'",
    tr.tool_name == "validation_aggregate")

# T33b: default target is "validation" — verified via inputs["target"] and evidence_id
_check("T33b inputs['target'] is 'validation' by default",
    tr.inputs.get("target") == "validation")
_check("T33c 'validation' appears in evidence_id (target participates in ID generation)",
    "validation" in tr.evidence_id)

# T33d: custom target is reflected correctly
tr_custom = validation_aggregate_tool_result_from_aggregate(
    "run_2h_001", agg_for_tr, target="custom_target"
)
_check("T33d custom target stored in inputs['target']",
    tr_custom.inputs.get("target") == "custom_target")
_check("T33e custom target appears in evidence_id",
    "custom_target" in tr_custom.evidence_id)
_check("T33f different targets produce different evidence_ids",
    tr.evidence_id != tr_custom.evidence_id)

# T34: payload includes status/counts/items
outputs = tr.outputs
_check("T34a payload includes status",
    "status" in outputs)
_check("T34b payload includes critical_count",
    "critical_count" in outputs)
_check("T34c payload includes warning_count",
    "warning_count" in outputs and outputs["warning_count"] == 2)
_check("T34d payload includes items",
    "items" in outputs and len(outputs["items"]) == 2)
_check("T34e payload includes blocking_count",
    "blocking_count" in outputs)
_check("T34f payload includes source_domains",
    "source_domains" in outputs)

# T35: evidence_id deterministic
tr2 = validation_aggregate_tool_result_from_aggregate("run_2h_001", agg_for_tr)
_check("T35 evidence_id deterministic for same run_id/aggregate",
    tr.evidence_id == tr2.evidence_id)

tr3 = validation_aggregate_tool_result_from_aggregate("run_2h_002", agg_for_tr)
_check("T35b different run_id produces different evidence_id",
    tr.evidence_id != tr3.evidence_id)


# ---------------------------------------------------------------------------
# Tests: Serialization roundtrips
# ---------------------------------------------------------------------------

print("\n--- Serialization roundtrips ---")

# T36: ValidationAggregate serialization roundtrip
agg_rt = aggregate_warning_groups(
    "agg_rt_001", "2026-05-22",
    {"news": ["Warning 1", "Warning 2"], "macro": ["Macro warning"]},
    metadata={"phase": "2H"},
)
agg_rt_dict = agg_rt.model_dump()
agg_rt_restored = ValidationAggregate(**agg_rt_dict)
_check("T36a ValidationAggregate roundtrip aggregate_id",
    agg_rt_restored.aggregate_id == "agg_rt_001")
_check("T36b ValidationAggregate roundtrip item count",
    len(agg_rt_restored.items) == 3)
_check("T36c ValidationAggregate roundtrip warning_count",
    agg_rt_restored.warning_count == 3)
_check("T36d ValidationAggregate roundtrip status",
    agg_rt_restored.status == "pass_with_warnings")

# T37: AggregatedValidationItem serialization roundtrip
item_rt = _make_item(
    item_id="rt_item_001",
    domain="catalyst",
    severity="critical",
    message="Critical catalyst issue.",
    blocking=True,
)
item_rt_dict = item_rt.model_dump()
item_rt_restored = AggregatedValidationItem(**item_rt_dict)
_check("T37a AggregatedValidationItem roundtrip item_id",
    item_rt_restored.item_id == "rt_item_001")
_check("T37b AggregatedValidationItem roundtrip severity",
    item_rt_restored.severity == "critical")
_check("T37c AggregatedValidationItem roundtrip blocking",
    item_rt_restored.blocking is True)


# ---------------------------------------------------------------------------
# Tests: ValidationAggregate auto-normalization
# ---------------------------------------------------------------------------

print("\n--- ValidationAggregate auto-normalization ---")

# D1: Manual construction with intentionally wrong counts/status/source_domains
#     is corrected automatically.
item_d1_crit = AggregatedValidationItem(
    item_id="d1_crit",
    domain="agent_result",
    severity="critical",
    message="Critical issue.",
    blocking=True,
)
item_d1_warn = AggregatedValidationItem(
    item_id="d1_warn",
    domain="news",
    severity="warning",
    message="Warning issue.",
)
item_d1_info = AggregatedValidationItem(
    item_id="d1_info",
    domain="macro",
    severity="info",
    message="Info note.",
)

agg_manual = ValidationAggregate(
    aggregate_id="agg_manual_001",
    as_of="2026-05-22",
    items=[item_d1_crit, item_d1_warn, item_d1_info],
    # Intentionally wrong values — should be overridden by normalization
    status="pass",           # wrong: should be "fail"
    critical_count=99,       # wrong: should be 1
    warning_count=0,         # wrong: should be 1
    info_count=0,            # wrong: should be 1
    blocking_count=0,        # wrong: should be 1
    source_domains=[],       # wrong: should be ["agent_result", "macro", "news"]
)
_check("D1a normalized critical_count == 1", agg_manual.critical_count == 1)
_check("D1b normalized warning_count == 1", agg_manual.warning_count == 1)
_check("D1c normalized info_count == 1", agg_manual.info_count == 1)
_check("D1d normalized blocking_count == 1", agg_manual.blocking_count == 1)
_check("D1e normalized status == 'fail'", agg_manual.status == "fail")
_check("D1f normalized source_domains sorted and correct",
    agg_manual.source_domains == ["agent_result", "macro", "news"])

# D2: Empty items always normalizes to pass/zero/empty regardless of
#     what the caller supplied.
agg_empty_norm = ValidationAggregate(
    aggregate_id="agg_empty_norm",
    as_of="2026-05-22",
    items=[],
    status="unknown",        # supplying "unknown" is accepted then overridden
    critical_count=0,
    warning_count=0,
)
_check("D2a empty items → status 'pass'", agg_empty_norm.status == "pass")
_check("D2b empty items → critical_count 0", agg_empty_norm.critical_count == 0)
_check("D2c empty items → warning_count 0", agg_empty_norm.warning_count == 0)
_check("D2d empty items → info_count 0", agg_empty_norm.info_count == 0)
_check("D2e empty items → blocking_count 0", agg_empty_norm.blocking_count == 0)
_check("D2f empty items → source_domains []", agg_empty_norm.source_domains == [])

# D3: Normalization is idempotent — a roundtrip through model_dump / reconstruct
#     produces the same normalised values.
agg_manual_dict = agg_manual.model_dump()
agg_manual_restored = ValidationAggregate(**agg_manual_dict)
_check("D3a roundtrip critical_count preserved", agg_manual_restored.critical_count == 1)
_check("D3b roundtrip status preserved", agg_manual_restored.status == "fail")
_check("D3c roundtrip source_domains preserved",
    agg_manual_restored.source_domains == ["agent_result", "macro", "news"])

# ---------------------------------------------------------------------------
# Tests: No live imports / no network calls
# ---------------------------------------------------------------------------

print("\n--- No live imports / no network calls ---")

# T38: no live app files imported
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
    _check(f"T38 {mod_name} not imported",
        not any(
            m == mod_name or m.startswith(mod_name + ".")
            for m in sys.modules
        )
    )

# T39: no external API/network calls
import lib.reliability.validation_aggregator as _agg_mod
import inspect
_src = inspect.getsource(_agg_mod)
_check("T39a no requests/urllib import in validation_aggregator.py",
    "import requests" not in _src and "import urllib" not in _src)
_check("T39b no yfinance import",
    "yfinance" not in _src)
_check("T39c no network-related imports",
    "socket" not in _src and "http" not in _src.lower().split("import")[0])


# ---------------------------------------------------------------------------
# Tests: Existing validate_agent_result behavior unchanged
# ---------------------------------------------------------------------------

print("\n--- Existing validate_agent_result stability ---")

# T40: Run a small AgentResult validation scenario and verify expected result
run_ctx = create_run_context(ticker="AAPL", task="phase2h_stability_test")
store = EvidenceStore(run_dir=run_ctx.run_dir)

# AgentResult with no evidence (should produce MISSING_EVIDENCE warning)
ar_no_ev = AgentResult(
    agent_name="stability_test_agent",
    ticker="AAPL",
    run_id=run_ctx.run_id,
    findings=[
        Finding(text="Revenue grew 15% year-over-year.", evidence=[])
    ],
)
report = validate_agent_result(ar_no_ev, store, run_id=run_ctx.run_id, target_name="AAPL")
_check("T40a validate_agent_result still works (not broken by Phase 2H)",
    report is not None)
_check("T40b validate_agent_result returns ValidationReport",
    hasattr(report, "passed") and hasattr(report, "issues"))
_check("T40c numeric finding with no evidence → UNSUPPORTED_NUMERIC_CLAIM error",
    any(i.code == "UNSUPPORTED_NUMERIC_CLAIM" for i in report.issues))
_check("T40d report.passed is False (error present)",
    report.passed is False)

# Convert that report to aggregated items and verify the chain works end-to-end
items_e2e = validation_report_to_items(report)
agg_e2e = aggregate_validation_items("agg_e2e", "2026-05-22", items_e2e)
_check("T40e end-to-end: ValidationReport → items → aggregate works",
    agg_e2e.critical_count >= 1 and agg_e2e.status == "fail")

tr_e2e = validation_aggregate_tool_result_from_aggregate(run_ctx.run_id, agg_e2e)
_check("T40f end-to-end: aggregate → ToolResult works",
    tr_e2e.tool_name == "validation_aggregate")


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

print(f"\n{'='*50}")
print(f"Results: {_PASS} passed, {_FAIL} failed")
if _FAIL > 0:
    sys.exit(1)
else:
    print("All tests passed.")
