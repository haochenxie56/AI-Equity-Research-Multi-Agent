"""
Negative-case and hardening tests for the Phase 0.1 reliability foundation.
Covers all required scenarios without requiring pytest.

Run from repo root:
    python scripts/test_reliability_negative_cases.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from lib.reliability import (
    AgentResult,
    EvidenceRef,
    EvidenceStore,
    Finding,
    Risk,
    ToolResult,
    validate_agent_result,
)
from lib.reliability.schemas import (
    AgentConfidence,
    ValidationReport,
)

# ---------------------------------------------------------------------------
# Minimal test harness
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
# Shared helpers
# ---------------------------------------------------------------------------

_RUN_ID = "test-run-000"   # stable run_id used for ToolResults in helpers


def _base_tool_result(evidence_id: str = "ev_001", **kwargs) -> ToolResult:
    """Minimal valid ToolResult with required run_id."""
    return ToolResult(
        evidence_id=evidence_id,
        tool_name=kwargs.pop("tool_name", "DCFValuation"),
        run_id=kwargs.pop("run_id", _RUN_ID),
        **kwargs,
    )


def _make_store(
    tmp: Path,
    evidence_id: str = "ev_001",
    outputs: dict | None = None,
    tool_name: str = "DCFValuation",
) -> tuple[EvidenceStore, ToolResult]:
    store = EvidenceStore(run_dir=tmp)
    tr = _base_tool_result(
        evidence_id=evidence_id,
        tool_name=tool_name,
        ticker="AAPL",
        outputs=outputs or {"intrinsic_value": 200.0},
    )
    store.add_tool_result(tr)
    return store, tr


def _base_agent(run_id: str = "agent-run-001", ticker: str = "AAPL", **kwargs) -> AgentResult:
    """Minimal valid AgentResult with required run_id."""
    return AgentResult(agent_name="FinancialAgent", run_id=run_id, ticker=ticker, **kwargs)


# ---------------------------------------------------------------------------
# ── GROUP 0: Existing Phase 0.1 tests (must continue to pass) ──────────────
# ---------------------------------------------------------------------------

def test_happy_path():
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp))
        ar = _base_agent(
            run_id="test-run-001",
            findings=[Finding(
                text="DCF values the stock at $200.",
                evidence=[EvidenceRef(
                    evidence_id="ev_001",
                    tool_name="DCFValuation",
                    metric="intrinsic_value",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        check("validation passes", report.passed)
        check("no issues", len(report.issues) == 0)


def test_missing_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))
        # Text has no numeric/metric content — only MISSING_EVIDENCE warning
        ar = _base_agent(findings=[Finding(text="This company has a strong competitive moat.")])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("MISSING_EVIDENCE warning present", "MISSING_EVIDENCE" in codes)
        check("no errors — report.passed is True", report.passed)


def test_unsupported_numeric_claim():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))
        ar = _base_agent(findings=[Finding(
            text="EBITDA grew 25% in FY2025, revenue hit $5B with a 40% margin.",
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("UNSUPPORTED_NUMERIC_CLAIM error present", "UNSUPPORTED_NUMERIC_CLAIM" in codes)
        check("report.passed is False", not report.passed)


def test_invalid_finding_evidence_id():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))
        ar = _base_agent(findings=[Finding(
            text="Some qualitative analysis.",
            evidence=[EvidenceRef(evidence_id="nonexistent_001")],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("INVALID_EVIDENCE_ID error present", "INVALID_EVIDENCE_ID" in codes)
        check("report.passed is False", not report.passed)


def test_invalid_risk_evidence_id():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))
        ar = _base_agent(risks=[Risk(
            name="Valuation risk",
            description="The stock may be overvalued.",
            evidence=[EvidenceRef(evidence_id="ghost_id")],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("INVALID_RISK_EVIDENCE_ID error present", "INVALID_RISK_EVIDENCE_ID" in codes)
        check("report.passed is False", not report.passed)


def test_duplicate_evidence_id_same_store():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))
        store.add_tool_result(_base_tool_result("dup_001"))
        raised = False
        try:
            store.add_tool_result(_base_tool_result("dup_001", tool_name="AnotherTool"))
        except ValueError:
            raised = True
        check("raises ValueError on duplicate in same store", raised)


def test_duplicate_evidence_id_across_instances():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        store1 = EvidenceStore(run_dir=p)
        store1.add_tool_result(_base_tool_result("shared_001"))
        store2 = EvidenceStore(run_dir=p)
        check("second store loads existing ID from disk", "shared_001" in store2.evidence_ids())
        raised = False
        try:
            store2.add_tool_result(_base_tool_result("shared_001", tool_name="AnotherTool"))
        except ValueError:
            raised = True
        check("raises ValueError on duplicate across instances", raised)


def test_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        store = EvidenceStore(run_dir=p)
        store.add_tool_result(_base_tool_result("persist_001", outputs={"value": 100.0}))
        store.save_manifest()
        jsonl_path = p / "tool_results.jsonl"
        manifest_path = p / "evidence_manifest.json"
        check("tool_results.jsonl exists", jsonl_path.exists())
        check("evidence_manifest.json exists", manifest_path.exists())
        lines = [ln.strip() for ln in jsonl_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("every JSONL line is valid JSON", all(_is_valid_json(ln) for ln in lines))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        check("manifest has schema_version", "schema_version" in manifest)
        check("manifest tool_results_count == 1", manifest.get("tool_results_count") == 1)
        check("manifest has evidence_ids list", isinstance(manifest.get("evidence_ids"), list))


def test_weak_numeric_evidence_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))
        store.add_tool_result(_base_tool_result("ev_weak"))
        ar = _base_agent(findings=[Finding(
            text="DCF valuation suggests a $150 intrinsic value with 15% upside.",
            evidence=[EvidenceRef(evidence_id="ev_weak")],  # no tool_name/metric/field_path
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        severities = {i.severity for i in report.issues}
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present", "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed is True (warnings only)", report.passed)
        check("no error-severity issues", "error" not in severities)


# ---------------------------------------------------------------------------
# ── GROUP A: Required audit IDs ────────────────────────────────────────────
# ---------------------------------------------------------------------------

def test_required_run_id_tool_result():
    raised = False
    try:
        ToolResult(evidence_id="ev_001", tool_name="DCFValuation")   # missing run_id
    except ValidationError:
        raised = True
    check("ToolResult without run_id raises ValidationError", raised)

    raised = False
    try:
        ToolResult(evidence_id="ev_001", tool_name="DCFValuation", run_id="")  # empty
    except ValidationError:
        raised = True
    check("ToolResult with empty run_id raises ValidationError", raised)


def test_required_run_id_agent_result():
    raised = False
    try:
        AgentResult(agent_name="FinancialAgent")   # missing run_id
    except ValidationError:
        raised = True
    check("AgentResult without run_id raises ValidationError", raised)

    raised = False
    try:
        AgentResult(agent_name="FinancialAgent", run_id="")  # empty
    except ValidationError:
        raised = True
    check("AgentResult with empty run_id raises ValidationError", raised)


def test_required_run_id_validation_report():
    raised = False
    try:
        ValidationReport(passed=True, target_name="AAPL")   # missing run_id
    except ValidationError:
        raised = True
    check("ValidationReport without run_id raises ValidationError", raised)

    raised = False
    try:
        ValidationReport(passed=True, run_id="", target_name="AAPL")  # empty
    except ValidationError:
        raised = True
    check("ValidationReport with empty run_id raises ValidationError", raised)


def test_required_target_name_validation_report():
    raised = False
    try:
        ValidationReport(passed=True, run_id="run-001")   # missing target_name
    except ValidationError:
        raised = True
    check("ValidationReport without target_name raises ValidationError", raised)

    raised = False
    try:
        ValidationReport(passed=True, run_id="run-001", target_name="")  # empty
    except ValidationError:
        raised = True
    check("ValidationReport with empty target_name raises ValidationError", raised)


# ---------------------------------------------------------------------------
# ── GROUP B: Confidence constraints ────────────────────────────────────────
# ---------------------------------------------------------------------------

def test_confidence_constraints():
    # Finding.confidence
    raised = False
    try:
        Finding(text="x", confidence=-0.1)
    except ValidationError:
        raised = True
    check("Finding.confidence < 0 raises ValidationError", raised)

    raised = False
    try:
        Finding(text="x", confidence=1.1)
    except ValidationError:
        raised = True
    check("Finding.confidence > 1 raises ValidationError", raised)

    # AgentConfidence.score
    raised = False
    try:
        AgentConfidence(level="medium", rationale="r", score=1.5)
    except ValidationError:
        raised = True
    check("AgentConfidence.score > 1 raises ValidationError", raised)

    raised = False
    try:
        AgentConfidence(level="medium", rationale="r", score=-0.1)
    except ValidationError:
        raised = True
    check("AgentConfidence.score < 0 raises ValidationError", raised)


# ---------------------------------------------------------------------------
# ── GROUP C: extra="forbid" ────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def test_extra_forbid():
    raised = False
    try:
        ToolResult(evidence_id="ev", tool_name="t", run_id="r", unexpected_field="x")
    except ValidationError:
        raised = True
    check("ToolResult with extra field raises ValidationError", raised)

    raised = False
    try:
        AgentResult(agent_name="a", run_id="r", unexpected_field="x")
    except ValidationError:
        raised = True
    check("AgentResult with extra field raises ValidationError", raised)

    raised = False
    try:
        Finding(text="t", unexpected_field="x")
    except ValidationError:
        raised = True
    check("Finding with extra field raises ValidationError", raised)


# ---------------------------------------------------------------------------
# ── GROUP D: Numeric binding validation ────────────────────────────────────
# ---------------------------------------------------------------------------

_RICH_OUTPUTS = {
    "fair_value": 200,
    "valuation": {"dcf": {"fair_value": 200}},
    "rsi": 55,
}


def test_valid_metric_binding():
    """metric exists as a top-level key → no WEAK_NUMERIC_EVIDENCE_BINDING."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), outputs=_RICH_OUTPUTS, tool_name="valuation_model")
        ar = _base_agent(findings=[Finding(
            text="DCF fair value is $200.",
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                metric="fair_value",
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("no WEAK_NUMERIC_EVIDENCE_BINDING (valid metric)", "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("report.passed is True", report.passed)


def test_valid_field_path_binding():
    """Nested field_path resolves → no WEAK_NUMERIC_EVIDENCE_BINDING."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), outputs=_RICH_OUTPUTS, tool_name="valuation_model")
        ar = _base_agent(findings=[Finding(
            text="DCF fair value is $200.",
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                field_path="valuation.dcf.fair_value",
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("no WEAK_NUMERIC_EVIDENCE_BINDING (valid field_path)", "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("report.passed is True", report.passed)


def test_mismatched_tool_name_binding():
    """tool_name doesn't match ToolResult → INVALID_EVIDENCE_TOOL_BINDING + WEAK."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), tool_name="valuation_model")
        ar = _base_agent(findings=[Finding(
            text="RSI is 55, indicating neutral momentum.",
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                tool_name="technical_indicator",   # wrong — ToolResult says "valuation_model"
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("INVALID_EVIDENCE_TOOL_BINDING warning present",
              "INVALID_EVIDENCE_TOOL_BINDING" in codes)
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present (no valid binding)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed is True (warnings only)", report.passed)


def test_invalid_metric_binding():
    """metric not present in outputs → INVALID_EVIDENCE_METRIC_BINDING + WEAK."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), outputs=_RICH_OUTPUTS)
        ar = _base_agent(findings=[Finding(
            text="Revenue grew to $500M with a 30% margin.",
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                metric="nonexistent_metric",   # not in _RICH_OUTPUTS
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("INVALID_EVIDENCE_METRIC_BINDING warning present",
              "INVALID_EVIDENCE_METRIC_BINDING" in codes)
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present (no valid binding)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed is True (warnings only)", report.passed)


def test_invalid_field_path_binding():
    """field_path doesn't resolve in outputs → INVALID_EVIDENCE_FIELD_PATH_BINDING + WEAK."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), outputs=_RICH_OUTPUTS)
        ar = _base_agent(findings=[Finding(
            text="DCF fair value is $200.",
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                field_path="valuation.dcf.nonexistent",   # last segment missing
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("INVALID_EVIDENCE_FIELD_PATH_BINDING warning present",
              "INVALID_EVIDENCE_FIELD_PATH_BINDING" in codes)
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present (no valid binding)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed is True (warnings only)", report.passed)


# ---------------------------------------------------------------------------
# ── GROUP E: Corrupted JSONL ───────────────────────────────────────────────
# ---------------------------------------------------------------------------

def test_corrupted_jsonl_duplicate_on_load():
    """
    Manually write two JSONL lines with the same evidence_id.
    EvidenceStore.__init__ should raise ValueError when loading.
    """
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        jsonl_path = p / "tool_results.jsonl"
        tr = _base_tool_result("dup_jsonl_001")
        line = tr.model_dump_json()
        # Write the same record twice
        jsonl_path.write_text(line + "\n" + line + "\n", encoding="utf-8")

        raised = False
        try:
            EvidenceStore(run_dir=p)
        except ValueError:
            raised = True
        check("EvidenceStore raises ValueError on duplicate in persisted JSONL", raised)


# ---------------------------------------------------------------------------
# ── GROUP F: Risk-side numeric evidence binding ────────────────────────────
# ---------------------------------------------------------------------------

_RISK_OUTPUTS = {
    "wacc": 0.095,
    "valuation": {"dcf": {"downside_pct": -0.35}},
}

# Risk text that contains numeric/metric content (WACC keyword + percentage)
_NUMERIC_RISK = Risk(
    name="WACC sensitivity",
    description="Downside is 35% if WACC rises by 100bps.",
)


def test_risk_valid_metric_binding():
    """Numeric risk with metric that exists in outputs → no WEAK_NUMERIC_EVIDENCE_BINDING."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), outputs=_RISK_OUTPUTS, tool_name="valuation_model")
        ar = _base_agent(risks=[Risk(
            name=_NUMERIC_RISK.name,
            description=_NUMERIC_RISK.description,
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                metric="wacc",          # top-level key in _RISK_OUTPUTS ✓
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("no WEAK_NUMERIC_EVIDENCE_BINDING (valid risk metric)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("report.passed is True", report.passed)


def test_risk_valid_field_path_binding():
    """Numeric risk with nested field_path that resolves → no WEAK_NUMERIC_EVIDENCE_BINDING."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), outputs=_RISK_OUTPUTS, tool_name="valuation_model")
        ar = _base_agent(risks=[Risk(
            name=_NUMERIC_RISK.name,
            description=_NUMERIC_RISK.description,
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                field_path="valuation.dcf.downside_pct",   # resolves ✓
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("no WEAK_NUMERIC_EVIDENCE_BINDING (valid risk field_path)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("report.passed is True", report.passed)


def test_risk_mismatched_tool_name():
    """Numeric risk with wrong tool_name → INVALID_EVIDENCE_TOOL_BINDING + WEAK."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), tool_name="valuation_model")
        ar = _base_agent(risks=[Risk(
            name=_NUMERIC_RISK.name,
            description=_NUMERIC_RISK.description,
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                tool_name="technical_indicator",   # mismatch — ToolResult is "valuation_model"
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("INVALID_EVIDENCE_TOOL_BINDING warning present (risk)",
              "INVALID_EVIDENCE_TOOL_BINDING" in codes)
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present (risk, no valid binding)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed is True (warnings only)", report.passed)


def test_risk_invalid_metric():
    """Numeric risk with metric not in outputs → INVALID_EVIDENCE_METRIC_BINDING + WEAK."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), outputs=_RISK_OUTPUTS)
        ar = _base_agent(risks=[Risk(
            name=_NUMERIC_RISK.name,
            description=_NUMERIC_RISK.description,
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                metric="nonexistent_metric",   # not in _RISK_OUTPUTS
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("INVALID_EVIDENCE_METRIC_BINDING warning present (risk)",
              "INVALID_EVIDENCE_METRIC_BINDING" in codes)
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present (risk, no valid binding)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed is True (warnings only)", report.passed)


def test_risk_invalid_field_path():
    """Numeric risk with unresolvable field_path → INVALID_EVIDENCE_FIELD_PATH_BINDING + WEAK."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), outputs=_RISK_OUTPUTS)
        ar = _base_agent(risks=[Risk(
            name=_NUMERIC_RISK.name,
            description=_NUMERIC_RISK.description,
            evidence=[EvidenceRef(
                evidence_id="ev_001",
                field_path="valuation.dcf.nonexistent",   # last segment missing
            )],
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        check("INVALID_EVIDENCE_FIELD_PATH_BINDING warning present (risk)",
              "INVALID_EVIDENCE_FIELD_PATH_BINDING" in codes)
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present (risk, no valid binding)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed is True (warnings only)", report.passed)


def test_risk_no_binding_metadata():
    """Numeric risk with valid evidence_id but no binding metadata → WEAK_NUMERIC_EVIDENCE_BINDING."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(Path(tmp), outputs=_RISK_OUTPUTS)
        ar = _base_agent(risks=[Risk(
            name=_NUMERIC_RISK.name,
            description=_NUMERIC_RISK.description,
            evidence=[EvidenceRef(evidence_id="ev_001")],   # no tool_name/metric/field_path
        )])
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}
        severities = {i.severity for i in report.issues}
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present (risk, no metadata)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed is True (warnings only)", report.passed)
        check("no error-severity issues", "error" not in severities)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_TESTS = [
    # Group 0 — original Phase 0.1 regression tests
    ("0-1. Happy path",                                  test_happy_path),
    ("0-2. Missing evidence",                            test_missing_evidence),
    ("0-3. Unsupported numeric claim",                   test_unsupported_numeric_claim),
    ("0-4. Invalid finding evidence_id",                 test_invalid_finding_evidence_id),
    ("0-5. Invalid risk evidence_id",                    test_invalid_risk_evidence_id),
    ("0-6. Duplicate evidence ID (same store)",          test_duplicate_evidence_id_same_store),
    ("0-7. Duplicate evidence ID (across instances)",    test_duplicate_evidence_id_across_instances),
    ("0-8. Persistence",                                 test_persistence),
    ("0-9. Weak numeric evidence binding",               test_weak_numeric_evidence_binding),
    # Group A — required audit IDs
    ("A-1. Required run_id on ToolResult",               test_required_run_id_tool_result),
    ("A-2. Required run_id on AgentResult",              test_required_run_id_agent_result),
    ("A-3. Required run_id on ValidationReport",         test_required_run_id_validation_report),
    ("A-4. Required target_name on ValidationReport",    test_required_target_name_validation_report),
    # Group B — confidence constraints
    ("B-1. Confidence field constraints",                test_confidence_constraints),
    # Group C — extra="forbid"
    ("C-1. Extra fields rejected",                       test_extra_forbid),
    # Group D — numeric binding validation
    ("D-1. Valid metric binding",                        test_valid_metric_binding),
    ("D-2. Valid field_path binding",                    test_valid_field_path_binding),
    ("D-3. Mismatched tool_name",                        test_mismatched_tool_name_binding),
    ("D-4. Invalid metric",                              test_invalid_metric_binding),
    ("D-5. Invalid field_path",                          test_invalid_field_path_binding),
    # Group E — corrupted JSONL
    ("E-1. Corrupted JSONL duplicate on load",           test_corrupted_jsonl_duplicate_on_load),
    # Group F — risk-side numeric evidence binding
    ("F-1. Risk valid metric binding",                   test_risk_valid_metric_binding),
    ("F-2. Risk valid field_path binding",               test_risk_valid_field_path_binding),
    ("F-3. Risk mismatched tool_name",                   test_risk_mismatched_tool_name),
    ("F-4. Risk invalid metric",                         test_risk_invalid_metric),
    ("F-5. Risk invalid field_path",                     test_risk_invalid_field_path),
    ("F-6. Risk no binding metadata",                    test_risk_no_binding_metadata),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 0.1 Reliability Foundation — Hardening Tests")
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
