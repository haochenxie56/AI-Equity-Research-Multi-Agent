"""
Phase 1A: Isolated Valuation ToolResult Integration — Tests

Demonstrates the end-to-end reliability pipeline for valuation outputs
without importing or modifying lib/valuation.py.

Run from repo root:
    python3 scripts/test_reliability_valuation_adapter.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.reliability import (
    AgentResult,
    EvidenceRef,
    EvidenceStore,
    Finding,
    Risk,
    ToolResult,
    ValidationReport,
    create_run_context,
    validate_agent_result,
    valuation_tool_result,
)
from lib.reliability.serialization import save_json_model


# ---------------------------------------------------------------------------
# Minimal test harness (shared style with other reliability test scripts)
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
# Synthetic valuation outputs — does NOT import lib/valuation.py
# ---------------------------------------------------------------------------

_TICKER = "ORCL"
_RUN_ID = "ORCL_20260521_phase1a_abcd1234"

_VALUATION_OUTPUTS = {
    "fair_value": 200.0,
    "current_price": 180.0,
    "upside_pct": 0.1111,
    "assumptions": {
        "wacc": 0.095,
        "terminal_growth": 0.025,
        "forecast_years": 5,
    },
    "dcf": {
        "base_case": {
            "fair_value": 200.0,
            "implied_upside_pct": 0.1111,
        },
        "bull_case": {
            "fair_value": 240.0,
        },
        "bear_case": {
            "fair_value": 150.0,
        },
    },
    "relative_multiples": {
        "pe": 28.5,
        "ev_ebitda": 18.2,
    },
}

_VALUATION_INPUTS = {
    "wacc": 0.095,
    "terminal_growth": 0.025,
    "forecast_years": 5,
}


def _make_store_with_valuation(tmp_dir: str):
    """Helper: create an EvidenceStore with one synthetic valuation ToolResult."""
    store = EvidenceStore(run_dir=Path(tmp_dir))
    tr = valuation_tool_result(
        run_id=_RUN_ID,
        target=_TICKER,
        metric_group="dcf",
        outputs=_VALUATION_OUTPUTS,
        inputs=_VALUATION_INPUTS,
        metadata={"description": "Synthetic DCF valuation — ORCL Phase 1A test"},
    )
    eid = store.add_tool_result(tr)
    return store, tr, eid


# ---------------------------------------------------------------------------
# A. Valuation ToolResult construction
# ---------------------------------------------------------------------------

def test_a_valuation_toolresult_construction():
    tr = valuation_tool_result(
        run_id=_RUN_ID,
        target=_TICKER,
        metric_group="dcf",
        outputs=_VALUATION_OUTPUTS,
        inputs=_VALUATION_INPUTS,
        metadata={"description": "Synthetic DCF valuation for ORCL"},
    )
    check("returns ToolResult instance", isinstance(tr, ToolResult))
    check("tool_name == 'valuation_model'", tr.tool_name == "valuation_model")
    check("run_id is non-empty", bool(tr.run_id))
    check("run_id matches supplied value", tr.run_id == _RUN_ID)
    check("evidence_id is non-empty", bool(tr.evidence_id))
    check("evidence_id contains run_id prefix", tr.evidence_id.startswith(_RUN_ID))
    check("ticker matches target", tr.ticker == _TICKER)
    # Top-level outputs
    check("outputs: fair_value present", "fair_value" in tr.outputs)
    check("outputs: fair_value == 200.0", tr.outputs["fair_value"] == 200.0)
    check("outputs: upside_pct present", "upside_pct" in tr.outputs)
    # Nested dcf
    check("outputs: dcf key present", "dcf" in tr.outputs)
    check("outputs: dcf.base_case present", "base_case" in tr.outputs["dcf"])
    check("outputs: dcf.base_case.fair_value == 200.0",
          tr.outputs["dcf"]["base_case"]["fair_value"] == 200.0)
    check("outputs: dcf.bull_case.fair_value == 240.0",
          tr.outputs["dcf"]["bull_case"]["fair_value"] == 240.0)
    check("outputs: dcf.bear_case.fair_value == 150.0",
          tr.outputs["dcf"]["bear_case"]["fair_value"] == 150.0)
    # Nested assumptions
    check("outputs: assumptions.wacc == 0.095",
          tr.outputs.get("assumptions", {}).get("wacc") == 0.095)
    # Inputs preserved
    check("inputs: wacc preserved", tr.inputs.get("wacc") == 0.095)
    check("inputs: terminal_growth preserved", tr.inputs.get("terminal_growth") == 0.025)
    # Description from metadata
    check("description set from metadata", "Synthetic DCF" in tr.description)


# ---------------------------------------------------------------------------
# B. EvidenceStore persistence
# ---------------------------------------------------------------------------

def test_b_evidence_store_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        check("evidence_id in store.evidence_ids()", eid in store.evidence_ids())
        check("store.get() returns ToolResult", store.get(eid) is not None)
        check("retrieved outputs: fair_value correct",
              store.get(eid).outputs["fair_value"] == 200.0)

        store.save_manifest()
        jsonl_path = Path(tmp) / "tool_results.jsonl"
        manifest_path = Path(tmp) / "evidence_manifest.json"

        check("tool_results.jsonl exists", jsonl_path.exists())
        check("evidence_manifest.json exists", manifest_path.exists())

        lines = [ln for ln in jsonl_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("JSONL has exactly one record", len(lines) == 1)
        check("JSONL record is valid JSON", _is_valid_json(lines[0]))

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        check("manifest contains evidence_id", eid in manifest.get("evidence_ids", []))
        check("manifest tool_results_count == 1", manifest.get("tool_results_count") == 1)
        check("manifest has schema_version", "schema_version" in manifest)


def _is_valid_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# C. Valid metric binding
# ---------------------------------------------------------------------------

def test_c_valid_metric_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="DCF fair value is $200 with 11.1% upside.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="valuation_model",
                    metric="fair_value",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no INVALID_EVIDENCE_ID", "INVALID_EVIDENCE_ID" not in codes)
        check("no INVALID_EVIDENCE_TOOL_BINDING", "INVALID_EVIDENCE_TOOL_BINDING" not in codes)
        check("no INVALID_EVIDENCE_METRIC_BINDING", "INVALID_EVIDENCE_METRIC_BINDING" not in codes)
        check("no WEAK_NUMERIC_EVIDENCE_BINDING", "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("report.passed is True", report.passed)
        check("zero issues", len(report.issues) == 0)


# ---------------------------------------------------------------------------
# D. Valid field_path binding (DCF nested)
# ---------------------------------------------------------------------------

def test_d_valid_field_path_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="Base case DCF fair value is $200.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    field_path="dcf.base_case.fair_value",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no WEAK_NUMERIC_EVIDENCE_BINDING", "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("no INVALID_EVIDENCE_FIELD_PATH_BINDING", "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in codes)
        check("report.passed is True", report.passed)


# ---------------------------------------------------------------------------
# E. Valid assumption field_path binding
# ---------------------------------------------------------------------------

def test_e_valid_assumption_field_path_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="The DCF uses a 9.5% WACC assumption.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    field_path="assumptions.wacc",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no WEAK_NUMERIC_EVIDENCE_BINDING", "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("no INVALID_EVIDENCE_FIELD_PATH_BINDING", "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in codes)
        check("report.passed is True", report.passed)


# ---------------------------------------------------------------------------
# F. Invalid metric binding warning
# ---------------------------------------------------------------------------

def test_f_invalid_metric_binding_warning():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                # numeric claim — validator checks binding
                text="DCF fair value is $200.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # metric only (no tool_name rescue) so binding fails cleanly
                    metric="nonexistent_metric",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("INVALID_EVIDENCE_METRIC_BINDING warning present",
              "INVALID_EVIDENCE_METRIC_BINDING" in codes)
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed remains True (warnings only)", report.passed)
        check("no error-severity issues",
              not any(i.severity == "error" for i in report.issues))


# ---------------------------------------------------------------------------
# G. Invalid field_path binding warning
# ---------------------------------------------------------------------------

def test_g_invalid_field_path_binding_warning():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="DCF base case fair value is $200.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # field_path only (no tool_name rescue) so binding fails cleanly
                    field_path="dcf.base_case.nonexistent_field",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("INVALID_EVIDENCE_FIELD_PATH_BINDING warning present",
              "INVALID_EVIDENCE_FIELD_PATH_BINDING" in codes)
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed remains True (warnings only)", report.passed)
        check("no error-severity issues",
              not any(i.severity == "error" for i in report.issues))


# ---------------------------------------------------------------------------
# H. Invalid tool_name binding warning
# ---------------------------------------------------------------------------

def test_h_invalid_tool_name_binding_warning():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="DCF fair value is $200.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # wrong tool_name — actual ToolResult.tool_name is "valuation_model"
                    tool_name="technical_indicator_engine",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("INVALID_EVIDENCE_TOOL_BINDING warning present",
              "INVALID_EVIDENCE_TOOL_BINDING" in codes)
        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed remains True (warnings only)", report.passed)
        check("no error-severity issues",
              not any(i.severity == "error" for i in report.issues))


# ---------------------------------------------------------------------------
# I. Missing evidence for numeric valuation claim (error)
# ---------------------------------------------------------------------------

def test_i_missing_evidence_numeric_claim():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="DCF fair value is $200 with 11.1% upside.",
                evidence=[],  # no evidence refs
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("UNSUPPORTED_NUMERIC_CLAIM error present",
              "UNSUPPORTED_NUMERIC_CLAIM" in codes)
        check("report.passed is False", not report.passed)


# ---------------------------------------------------------------------------
# J. Invalid evidence_id (error)
# ---------------------------------------------------------------------------

def test_j_invalid_evidence_id_error():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="DCF fair value is $200.",
                evidence=[EvidenceRef(
                    evidence_id="nonexistent_evidence_id_xyz",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("INVALID_EVIDENCE_ID error present", "INVALID_EVIDENCE_ID" in codes)
        check("report.passed is False", not report.passed)


# ---------------------------------------------------------------------------
# K. Valuation risk — valid binding
# ---------------------------------------------------------------------------

def test_k_valuation_risk_valid_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            risks=[Risk(
                name="WACC compression risk",
                description="Downside risk is 35% if WACC rises 200bp from current 9.5%.",
                severity="high",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="valuation_model",
                    field_path="assumptions.wacc",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no WEAK_NUMERIC_EVIDENCE_BINDING (risk)", "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("no INVALID_EVIDENCE_FIELD_PATH_BINDING (risk)", "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in codes)
        check("no INVALID_EVIDENCE_TOOL_BINDING (risk)", "INVALID_EVIDENCE_TOOL_BINDING" not in codes)
        check("report.passed is True", report.passed)
        check("zero issues", len(report.issues) == 0)


# ---------------------------------------------------------------------------
# L. Valuation risk — weak binding (evidence_id only, no binding metadata)
# ---------------------------------------------------------------------------

def test_l_valuation_risk_weak_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_valuation(tmp)

        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            risks=[Risk(
                name="WACC compression risk",
                description="Downside risk is 35% if WACC rises 200bp from current 9.5%.",
                severity="high",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # no tool_name, metric, or field_path — only evidence_id
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("WEAK_NUMERIC_EVIDENCE_BINDING warning present (risk)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" in codes)
        check("report.passed remains True (warnings only)", report.passed)
        check("no error-severity issues",
              not any(i.severity == "error" for i in report.issues))


# ---------------------------------------------------------------------------
# M. End-to-end persisted ValidationReport
# ---------------------------------------------------------------------------

def test_m_end_to_end_persisted_report():
    with tempfile.TemporaryDirectory() as base_dir:
        # Use create_run_context with a temp base dir so CWD is irrelevant
        ctx = create_run_context(ticker=_TICKER, task="phase1a_e2e", base_dir=base_dir)

        # Build and persist valuation ToolResult
        tr = valuation_tool_result(
            run_id=ctx.run_id,
            target=_TICKER,
            metric_group="dcf",
            outputs=_VALUATION_OUTPUTS,
            inputs=_VALUATION_INPUTS,
            metadata={"description": "Phase 1A E2E — synthetic ORCL DCF"},
        )
        store = EvidenceStore(run_dir=ctx.run_dir)
        eid = store.add_tool_result(tr)
        store.save_manifest()

        check("run_id is non-empty", bool(ctx.run_id))
        check("run_dir exists", ctx.run_dir.exists())
        check("tool_results.jsonl created",
              (ctx.run_dir / "tool_results.jsonl").exists())
        check("evidence_manifest.json created",
              (ctx.run_dir / "evidence_manifest.json").exists())

        # Well-formed AgentResult: finding + risk, both with valid bindings
        ar = AgentResult(
            agent_name="FinancialAgent",
            run_id=ctx.run_id,
            ticker=_TICKER,
            findings=[Finding(
                text="DCF fair value is $200 based on 9.5% WACC, implying 11.1% upside.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="valuation_model",
                    metric="fair_value",
                )],
            )],
            risks=[Risk(
                name="Valuation downside",
                description="Bear case DCF implies 17% downside if FCF growth disappoints.",
                severity="medium",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="valuation_model",
                    field_path="dcf.bear_case.fair_value",
                )],
            )],
        )

        report = validate_agent_result(ar, store)

        check("report.passed is True", report.passed)
        check("report.run_id == ctx.run_id", report.run_id == ctx.run_id)
        check("report.target_name == 'ORCL'", report.target_name == _TICKER)
        check("zero validation issues", len(report.issues) == 0)

        # Persist ValidationReport using existing serialization helper
        report_path = ctx.run_dir / "validation_report.json"
        save_json_model(report, report_path)

        check("validation_report.json created", report_path.exists())

        # Read back and verify JSON structure
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        check("JSON has 'run_id'", "run_id" in raw)
        check("JSON has 'target_name'", "target_name" in raw)
        check("JSON has 'passed'", "passed" in raw)
        check("JSON has 'issues'", "issues" in raw)
        check("JSON passed == true", raw["passed"] is True)
        check("JSON run_id matches", raw["run_id"] == ctx.run_id)

        print(f"\n    Run ID  : {ctx.run_id}")
        print(f"    Run dir : {ctx.run_dir}")
        print(f"    Evidence: {eid}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_TESTS = [
    ("A.  Valuation ToolResult construction",              test_a_valuation_toolresult_construction),
    ("B.  EvidenceStore persistence",                      test_b_evidence_store_persistence),
    ("C.  Valid metric binding",                           test_c_valid_metric_binding),
    ("D.  Valid field_path binding (dcf.base_case)",       test_d_valid_field_path_binding),
    ("E.  Valid assumption field_path binding (wacc)",     test_e_valid_assumption_field_path_binding),
    ("F.  Invalid metric binding → warning",               test_f_invalid_metric_binding_warning),
    ("G.  Invalid field_path binding → warning",           test_g_invalid_field_path_binding_warning),
    ("H.  Invalid tool_name binding → warning",            test_h_invalid_tool_name_binding_warning),
    ("I.  Missing evidence for numeric claim → error",     test_i_missing_evidence_numeric_claim),
    ("J.  Invalid evidence_id → error",                    test_j_invalid_evidence_id_error),
    ("K.  Valuation risk valid binding",                   test_k_valuation_risk_valid_binding),
    ("L.  Valuation risk weak binding → warning",          test_l_valuation_risk_weak_binding),
    ("M.  End-to-end persisted ValidationReport",          test_m_end_to_end_persisted_report),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 1A: Isolated Valuation ToolResult Integration — Tests")
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
