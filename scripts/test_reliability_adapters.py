"""
Tests for the Phase 0.2 reliability adapter helpers.

Run from repo root:
    python3 scripts/test_reliability_adapters.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.reliability import (
    AgentResult,
    DataSnapshot,
    EvidenceRef,
    EvidenceStore,
    Finding,
    ToolResult,
    data_snapshot_from_payload,
    make_evidence_id,
    scanner_tool_result,
    stable_hash_payload,
    technical_tool_result,
    tool_result_from_outputs,
    validate_agent_result,
    valuation_tool_result,
)

# ---------------------------------------------------------------------------
# Minimal test harness (shared with other test scripts)
# ---------------------------------------------------------------------------

_failures: list[str] = []
_current_test: str = ""

_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


def check(label: str, condition: bool, detail: str = "") -> None:
    tag = f"{_current_test} / {label}"
    if condition:
        print(f"  {_GREEN}PASS{_RESET}  {label}")
    else:
        _failures.append(tag)
        suffix = f": {detail}" if detail else ""
        print(f"  {_RED}FAIL{_RESET}  {label}{suffix}")


def run(name: str, fn) -> None:
    global _current_test
    _current_test = name
    print(f"\n{name}")
    fn()


# ---------------------------------------------------------------------------
# ── 1. stable_hash_payload ─────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def test_stable_hash_key_order_independence():
    h1 = stable_hash_payload({"b": 2, "a": 1})
    h2 = stable_hash_payload({"a": 1, "b": 2})
    check("same hash for different key order", h1 == h2)


def test_stable_hash_changes_with_payload():
    h1 = stable_hash_payload({"fair_value": 200})
    h2 = stable_hash_payload({"fair_value": 201})
    check("different hash when payload changes", h1 != h2)


def test_stable_hash_length():
    h = stable_hash_payload({"x": 1})
    check("default length is 12", len(h) == 12)

    h8 = stable_hash_payload({"x": 1}, length=8)
    check("custom length=8 works", len(h8) == 8)


def test_stable_hash_nested_dict():
    h1 = stable_hash_payload({"a": {"c": 3, "b": 2}})
    h2 = stable_hash_payload({"a": {"b": 2, "c": 3}})
    check("nested dicts with different key order hash identically", h1 == h2)


# ---------------------------------------------------------------------------
# ── 2. make_evidence_id ────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

_SAMPLE_PAYLOAD = {"intrinsic_value_per_share": 142.5, "upside_pct": 12.3}


def test_make_evidence_id_deterministic():
    id1 = make_evidence_id("run-001", "valuation_model", "ORCL", "dcf", _SAMPLE_PAYLOAD)
    id2 = make_evidence_id("run-001", "valuation_model", "ORCL", "dcf", _SAMPLE_PAYLOAD)
    check("evidence_id is deterministic for same inputs", id1 == id2)


def test_make_evidence_id_changes_with_payload():
    id1 = make_evidence_id("run-001", "valuation_model", "ORCL", "dcf", {"fair_value": 200})
    id2 = make_evidence_id("run-001", "valuation_model", "ORCL", "dcf", {"fair_value": 201})
    check("evidence_id changes when payload changes", id1 != id2)


def test_make_evidence_id_changes_with_run_id():
    id1 = make_evidence_id("run-001", "valuation_model", "ORCL", "dcf", _SAMPLE_PAYLOAD)
    id2 = make_evidence_id("run-002", "valuation_model", "ORCL", "dcf", _SAMPLE_PAYLOAD)
    check("evidence_id changes when run_id changes", id1 != id2)


def test_make_evidence_id_format():
    eid = make_evidence_id("run-001", "valuation_model", "ORCL", "dcf", _SAMPLE_PAYLOAD)
    parts = eid.split(":")
    check("evidence_id has 5 colon-separated segments", len(parts) == 5)
    check("first segment matches sanitized run_id", parts[0] == "run-001")
    check("second segment matches tool_name", parts[1] == "valuation_model")
    check("third segment matches target", parts[2] == "ORCL")
    check("fourth segment matches metric_group", parts[3] == "dcf")
    check("fifth segment is a 12-char hex hash", len(parts[4]) == 12)


def test_make_evidence_id_sanitizes_spaces():
    eid = make_evidence_id(
        "run 001",            # space in run_id
        "valuation model",    # space in tool_name
        "XL K",               # space in target
        "sector score",       # space in metric_group
        {},
    )
    check("no spaces in evidence_id", " " not in eid)
    check("spaces replaced with underscores", "run_001" in eid)


def test_make_evidence_id_sanitizes_special_chars():
    eid = make_evidence_id("run/001", "tool@name", "tick!er", "group#1", {})
    check("slashes sanitized", "/" not in eid)
    check("@ sanitized", "@" not in eid)
    check("! sanitized", "!" not in eid)
    check("# sanitized", "#" not in eid)


def test_make_evidence_id_rejects_empty_run_id():
    for bad in ["", "   "]:
        raised = False
        try:
            make_evidence_id(bad, "valuation_model", "ORCL", "dcf", {})
        except ValueError:
            raised = True
        check(f"empty/blank run_id {bad!r} raises ValueError", raised)


def test_make_evidence_id_rejects_empty_tool_name():
    for bad in ["", "   "]:
        raised = False
        try:
            make_evidence_id("run-001", bad, "ORCL", "dcf", {})
        except ValueError:
            raised = True
        check(f"empty/blank tool_name {bad!r} raises ValueError", raised)


def test_make_evidence_id_rejects_empty_target():
    for bad in ["", "   "]:
        raised = False
        try:
            make_evidence_id("run-001", "valuation_model", bad, "dcf", {})
        except ValueError:
            raised = True
        check(f"empty/blank target {bad!r} raises ValueError", raised)


def test_make_evidence_id_rejects_empty_metric_group():
    for bad in ["", "   "]:
        raised = False
        try:
            make_evidence_id("run-001", "valuation_model", "ORCL", bad, {})
        except ValueError:
            raised = True
        check(f"empty/blank metric_group {bad!r} raises ValueError", raised)


def test_make_evidence_id_sanitized_empty_behavior():
    # "///" sanitizes to "___" (non-empty) — should be accepted
    eid = make_evidence_id("run-001", "valuation_model", "///", "dcf", {})
    check("target '///' sanitizes to non-empty '___' and is accepted", "___" in eid)
    # Purely whitespace strips to "" — should be rejected
    raised = False
    try:
        make_evidence_id("run-001", "valuation_model", "   ", "dcf", {})
    except ValueError:
        raised = True
    check("blank target (spaces only) raises ValueError", raised)


# ---------------------------------------------------------------------------
# ── 3. tool_result_from_outputs ────────────────────────────────────────────
# ---------------------------------------------------------------------------

_RUN_ID = "ORCL_20260521_test_abcd1234"
_OUTPUTS = {"intrinsic_value_per_share": 142.5, "upside_pct": 12.3}


def test_tool_result_from_outputs_returns_valid():
    tr = tool_result_from_outputs(
        run_id=_RUN_ID,
        tool_name="valuation_model",
        target="ORCL",
        metric_group="dcf",
        outputs=_OUTPUTS,
        inputs={"wacc": 0.09},
        metadata={"description": "DCF for ORCL"},
    )
    check("returns ToolResult instance", isinstance(tr, ToolResult))
    check("tool_name matches", tr.tool_name == "valuation_model")
    check("run_id matches", tr.run_id == _RUN_ID)
    check("ticker matches target", tr.ticker == "ORCL")
    check("outputs preserved", tr.outputs == _OUTPUTS)
    check("inputs preserved", tr.inputs == {"wacc": 0.09})
    check("description from metadata", tr.description == "DCF for ORCL")
    check("evidence_id is non-empty", len(tr.evidence_id) > 0)
    check("evidence_id contains run_id prefix", tr.evidence_id.startswith("ORCL_20260521_test_abcd1234"))


def test_tool_result_from_outputs_deterministic_evidence_id():
    tr1 = tool_result_from_outputs(_RUN_ID, "valuation_model", "ORCL", "dcf", _OUTPUTS)
    tr2 = tool_result_from_outputs(_RUN_ID, "valuation_model", "ORCL", "dcf", _OUTPUTS)
    check("evidence_id is deterministic", tr1.evidence_id == tr2.evidence_id)


def test_tool_result_from_outputs_rejects_empty_run_id():
    raised = False
    try:
        tool_result_from_outputs("", "valuation_model", "ORCL", "dcf", {})
    except ValueError:
        raised = True
    check("empty run_id raises ValueError", raised)

    raised = False
    try:
        tool_result_from_outputs("   ", "valuation_model", "ORCL", "dcf", {})
    except ValueError:
        raised = True
    check("blank run_id raises ValueError", raised)


def test_tool_result_from_outputs_rejects_empty_tool_name():
    raised = False
    try:
        tool_result_from_outputs(_RUN_ID, "", "ORCL", "dcf", {})
    except ValueError:
        raised = True
    check("empty tool_name raises ValueError", raised)


def test_tool_result_from_outputs_rejects_empty_target():
    raised = False
    try:
        tool_result_from_outputs(_RUN_ID, "valuation_model", "", "dcf", {})
    except ValueError:
        raised = True
    check("empty target raises ValueError", raised)


def test_tool_result_from_outputs_rejects_empty_metric_group():
    raised = False
    try:
        tool_result_from_outputs(_RUN_ID, "valuation_model", "ORCL", "", {})
    except ValueError:
        raised = True
    check("empty metric_group raises ValueError", raised)


# ---------------------------------------------------------------------------
# ── 4. ToolResult → EvidenceStore integration ──────────────────────────────
# ---------------------------------------------------------------------------

def test_tool_result_can_be_added_to_evidence_store():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))
        tr = tool_result_from_outputs(_RUN_ID, "valuation_model", "ORCL", "dcf", _OUTPUTS)
        eid = store.add_tool_result(tr)
        check("add_tool_result returns evidence_id string", isinstance(eid, str))
        check("evidence_id matches ToolResult.evidence_id", eid == tr.evidence_id)
        check("store contains evidence_id", eid in store.evidence_ids())
        retrieved = store.get(eid)
        check("retrieved ToolResult matches original", retrieved is not None and retrieved.outputs == _OUTPUTS)


# ---------------------------------------------------------------------------
# ── 5. End-to-end: adapter → store → validator ─────────────────────────────
# ---------------------------------------------------------------------------

def test_adapter_evidence_ref_metric_binding_passes():
    """
    ToolResult created via adapter + EvidenceRef with metric → no WEAK_NUMERIC_EVIDENCE_BINDING.
    """
    outputs = {"intrinsic_value_per_share": 142.5, "upside_pct": 12.3}
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))
        tr = tool_result_from_outputs(_RUN_ID, "valuation_model", "ORCL", "dcf", outputs)
        eid = store.add_tool_result(tr)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker="ORCL",
            findings=[Finding(
                text="DCF intrinsic value is $142.50 with 12.3% upside.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="valuation_model",
                    metric="intrinsic_value_per_share",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("no WEAK_NUMERIC_EVIDENCE_BINDING (valid metric via adapter)", "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("validation passes", report.passed)
        check("no issues at all", len(report.issues) == 0)


def test_adapter_evidence_ref_field_path_binding_passes():
    """
    ToolResult with nested outputs + EvidenceRef with field_path → no WEAK_NUMERIC_EVIDENCE_BINDING.
    """
    outputs = {
        "valuation": {"dcf": {"fair_value": 142.5, "wacc": 0.09}},
        "upside_pct": 12.3,
    }
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))
        tr = tool_result_from_outputs(_RUN_ID, "valuation_model", "ORCL", "dcf_nested", outputs)
        eid = store.add_tool_result(tr)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker="ORCL",
            findings=[Finding(
                text="DCF fair value is $142.50 with 12.3% upside.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    field_path="valuation.dcf.fair_value",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("no WEAK_NUMERIC_EVIDENCE_BINDING (valid field_path via adapter)", "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("validation passes", report.passed)


# ---------------------------------------------------------------------------
# ── 6. data_snapshot_from_payload ──────────────────────────────────────────
# ---------------------------------------------------------------------------

def test_data_snapshot_from_payload_returns_valid():
    snap = data_snapshot_from_payload(
        snapshot_id="snap-orcl-20260521",
        source="yfinance",
        payload={"close": 127.40, "volume": 8_200_000},
        metadata={"description": "ORCL closing price on 2026-05-21"},
    )
    check("returns DataSnapshot instance", isinstance(snap, DataSnapshot))
    check("snapshot_id matches", snap.snapshot_id == "snap-orcl-20260521")
    check("source matches", snap.source == "yfinance")
    check("payload preserved", snap.data["close"] == 127.40)
    check("description from metadata", snap.description == "ORCL closing price on 2026-05-21")


def test_data_snapshot_no_metadata():
    snap = data_snapshot_from_payload("snap-001", "polygon.io", {"open": 100.0})
    check("description is empty string when no metadata", snap.description == "")
    check("data preserved", snap.data["open"] == 100.0)


def test_data_snapshot_non_string_metadata():
    snap = data_snapshot_from_payload(
        "snap-002", "manual",
        {"value": 99},
        metadata={"source_ts": "2026-05-21T00:00:00Z", "rows": 100},
    )
    check("non-string metadata serialized to description", len(snap.description) > 0)


# ---------------------------------------------------------------------------
# ── 7. Convenience wrappers ────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def test_valuation_tool_result_uses_correct_tool_name():
    tr = valuation_tool_result(_RUN_ID, "ORCL", "dcf", {"fair_value": 142.5})
    check("valuation_tool_result.tool_name == 'valuation_model'", tr.tool_name == "valuation_model")
    check("ticker set correctly", tr.ticker == "ORCL")


def test_technical_tool_result_uses_correct_tool_name():
    tr = technical_tool_result(_RUN_ID, "ORCL", "rsi", {"rsi_14": 55.0})
    check("technical_tool_result.tool_name == 'technical_indicator_engine'",
          tr.tool_name == "technical_indicator_engine")
    check("outputs preserved", tr.outputs["rsi_14"] == 55.0)


def test_scanner_tool_result_uses_correct_tool_name():
    tr = scanner_tool_result(_RUN_ID, "ORCL", "composite", {"composite_score": 78.5})
    check("scanner_tool_result.tool_name == 'stock_scanner'", tr.tool_name == "stock_scanner")
    check("outputs preserved", tr.outputs["composite_score"] == 78.5)


def test_convenience_wrappers_produce_different_evidence_ids():
    outputs = {"score": 80.0}
    tr_val = valuation_tool_result(_RUN_ID, "ORCL", "dcf", outputs)
    tr_tech = technical_tool_result(_RUN_ID, "ORCL", "dcf", outputs)
    tr_scan = scanner_tool_result(_RUN_ID, "ORCL", "dcf", outputs)
    check("valuation vs technical evidence_ids differ (different tool_name)",
          tr_val.evidence_id != tr_tech.evidence_id)
    check("valuation vs scanner evidence_ids differ",
          tr_val.evidence_id != tr_scan.evidence_id)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_TESTS = [
    # stable_hash_payload
    ("1-1. stable_hash: key order independence",          test_stable_hash_key_order_independence),
    ("1-2. stable_hash: changes with payload",            test_stable_hash_changes_with_payload),
    ("1-3. stable_hash: length control",                  test_stable_hash_length),
    ("1-4. stable_hash: nested dict normalisation",       test_stable_hash_nested_dict),
    # make_evidence_id
    ("2-1. evidence_id: deterministic",                   test_make_evidence_id_deterministic),
    ("2-2. evidence_id: changes with payload",            test_make_evidence_id_changes_with_payload),
    ("2-3. evidence_id: changes with run_id",             test_make_evidence_id_changes_with_run_id),
    ("2-4. evidence_id: format / segments",               test_make_evidence_id_format),
    ("2-5. evidence_id: sanitizes spaces",                test_make_evidence_id_sanitizes_spaces),
    ("2-6. evidence_id: sanitizes special chars",         test_make_evidence_id_sanitizes_special_chars),
    ("2-7. evidence_id: rejects empty/blank run_id",      test_make_evidence_id_rejects_empty_run_id),
    ("2-8. evidence_id: rejects empty/blank tool_name",   test_make_evidence_id_rejects_empty_tool_name),
    ("2-9. evidence_id: rejects empty/blank target",      test_make_evidence_id_rejects_empty_target),
    ("2-10. evidence_id: rejects empty/blank metric_group", test_make_evidence_id_rejects_empty_metric_group),
    ("2-11. evidence_id: sanitized-empty / slash behavior", test_make_evidence_id_sanitized_empty_behavior),
    # tool_result_from_outputs
    ("3-1. tool_result: returns valid ToolResult",        test_tool_result_from_outputs_returns_valid),
    ("3-2. tool_result: deterministic evidence_id",       test_tool_result_from_outputs_deterministic_evidence_id),
    ("3-3. tool_result: rejects empty run_id",            test_tool_result_from_outputs_rejects_empty_run_id),
    ("3-4. tool_result: rejects empty tool_name",         test_tool_result_from_outputs_rejects_empty_tool_name),
    ("3-5. tool_result: rejects empty target",            test_tool_result_from_outputs_rejects_empty_target),
    ("3-6. tool_result: rejects empty metric_group",      test_tool_result_from_outputs_rejects_empty_metric_group),
    # EvidenceStore integration
    ("4-1. store: adapter result accepted by EvidenceStore", test_tool_result_can_be_added_to_evidence_store),
    # End-to-end adapter → store → validator
    ("5-1. e2e: metric binding passes (no WEAK)",         test_adapter_evidence_ref_metric_binding_passes),
    ("5-2. e2e: field_path binding passes (no WEAK)",     test_adapter_evidence_ref_field_path_binding_passes),
    # data_snapshot_from_payload
    ("6-1. snapshot: returns valid DataSnapshot",         test_data_snapshot_from_payload_returns_valid),
    ("6-2. snapshot: no metadata → empty description",    test_data_snapshot_no_metadata),
    ("6-3. snapshot: non-string metadata serialised",     test_data_snapshot_non_string_metadata),
    # Convenience wrappers
    ("7-1. valuation_tool_result tool_name",              test_valuation_tool_result_uses_correct_tool_name),
    ("7-2. technical_tool_result tool_name",              test_technical_tool_result_uses_correct_tool_name),
    ("7-3. scanner_tool_result tool_name",                test_scanner_tool_result_uses_correct_tool_name),
    ("7-4. wrappers produce distinct evidence_ids",       test_convenience_wrappers_produce_different_evidence_ids),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 0.2 Reliability Adapters — Tests")
    print("=" * 70)
    for name, fn in _TESTS:
        run(name, fn)
    print("\n" + "=" * 70)
    if _failures:
        print(f"{_RED}FAILED{_RESET}: {len(_failures)} assertion(s):")
        for f in _failures:
            print(f"  • {f}")
        sys.exit(1)
    else:
        print(f"{_GREEN}All {len(_TESTS)} tests passed.{_RESET}")
