"""
Phase 1B: Isolated Technical ToolResult Integration — Tests

Demonstrates the end-to-end reliability pipeline for technical indicator
outputs without importing or modifying lib/technical.py.

Run from repo root:
    python3 scripts/test_reliability_technical_adapter.py
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
    create_run_context,
    validate_agent_result,
    technical_tool_result,
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
# Synthetic technical outputs — does NOT import lib/technical.py
# ---------------------------------------------------------------------------

_TICKER = "ORCL"
_RUN_ID = "ORCL_20260521_phase1b_abcd1234"

_TECHNICAL_OUTPUTS = {
    "rsi": 62.5,
    "macd": 1.25,
    "macd_signal": 0.95,
    "macd_histogram": 0.30,
    "adx": 24.8,
    "volume_ratio": 1.45,
    "atr": 4.2,
    "moving_averages": {
        "sma_20": 182.0,
        "sma_50": 176.5,
        "sma_200": 154.0,
        "ema_20": 183.1,
    },
    "bollinger": {
        "upper": 195.0,
        "middle": 182.0,
        "lower": 169.0,
    },
    "levels": {
        "support": 175.0,
        "resistance": 190.0,
    },
    "trend": {
        "direction": "bullish",
        "price_above_sma_50": True,
        "price_above_sma_200": True,
    },
}

_TECHNICAL_INPUTS = {
    "ticker": _TICKER,
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "sma_periods": [20, 50, 200],
}


def _make_store_with_technical(tmp_dir: str):
    """Helper: create an EvidenceStore with one synthetic technical ToolResult."""
    store = EvidenceStore(run_dir=Path(tmp_dir))
    tr = technical_tool_result(
        run_id=_RUN_ID,
        target=_TICKER,
        metric_group="indicators",
        outputs=_TECHNICAL_OUTPUTS,
        inputs=_TECHNICAL_INPUTS,
        metadata={"description": "Synthetic technical indicators — ORCL Phase 1B test"},
    )
    eid = store.add_tool_result(tr)
    return store, tr, eid


def _is_valid_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# A. Technical ToolResult construction
# ---------------------------------------------------------------------------

def test_a_technical_toolresult_construction():
    tr = technical_tool_result(
        run_id=_RUN_ID,
        target=_TICKER,
        metric_group="indicators",
        outputs=_TECHNICAL_OUTPUTS,
        inputs=_TECHNICAL_INPUTS,
        metadata={"description": "Synthetic technical indicators for ORCL"},
    )
    check("returns ToolResult instance", isinstance(tr, ToolResult))
    check("tool_name == 'technical_indicator_engine'",
          tr.tool_name == "technical_indicator_engine")
    check("run_id is non-empty", bool(tr.run_id))
    check("run_id matches supplied value", tr.run_id == _RUN_ID)
    check("evidence_id is non-empty", bool(tr.evidence_id))
    check("evidence_id contains run_id prefix", tr.evidence_id.startswith(_RUN_ID))
    check("ticker matches target", tr.ticker == _TICKER)
    # Top-level outputs
    check("outputs: rsi present", "rsi" in tr.outputs)
    check("outputs: rsi == 62.5", tr.outputs["rsi"] == 62.5)
    check("outputs: macd_histogram present", "macd_histogram" in tr.outputs)
    check("outputs: macd_histogram == 0.30", tr.outputs["macd_histogram"] == 0.30)
    check("outputs: adx == 24.8", tr.outputs["adx"] == 24.8)
    check("outputs: volume_ratio == 1.45", tr.outputs["volume_ratio"] == 1.45)
    # Nested moving averages
    check("outputs: moving_averages key present", "moving_averages" in tr.outputs)
    check("outputs: moving_averages.sma_50 == 176.5",
          tr.outputs["moving_averages"]["sma_50"] == 176.5)
    check("outputs: moving_averages.sma_200 == 154.0",
          tr.outputs["moving_averages"]["sma_200"] == 154.0)
    # Nested levels
    check("outputs: levels.support == 175.0",
          tr.outputs["levels"]["support"] == 175.0)
    check("outputs: levels.resistance == 190.0",
          tr.outputs["levels"]["resistance"] == 190.0)
    # Nested bollinger
    check("outputs: bollinger.upper == 195.0",
          tr.outputs["bollinger"]["upper"] == 195.0)
    # Nested trend flags
    check("outputs: trend.price_above_sma_50 is True",
          tr.outputs["trend"]["price_above_sma_50"] is True)
    # Inputs preserved
    check("inputs: rsi_period == 14", tr.inputs.get("rsi_period") == 14)
    # Description from metadata
    check("description set from metadata", "Synthetic technical" in tr.description)


# ---------------------------------------------------------------------------
# B. EvidenceStore persistence
# ---------------------------------------------------------------------------

def test_b_evidence_store_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        check("evidence_id in store.evidence_ids()", eid in store.evidence_ids())
        check("store.get() returns ToolResult", store.get(eid) is not None)
        check("retrieved outputs: rsi correct",
              store.get(eid).outputs["rsi"] == 62.5)

        store.save_manifest()
        jsonl_path = Path(tmp) / "tool_results.jsonl"
        manifest_path = Path(tmp) / "evidence_manifest.json"

        check("tool_results.jsonl exists", jsonl_path.exists())
        check("evidence_manifest.json exists", manifest_path.exists())

        lines = [ln for ln in jsonl_path.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        check("JSONL has exactly one record", len(lines) == 1)
        check("JSONL record is valid JSON", _is_valid_json(lines[0]))

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        check("manifest contains evidence_id", eid in manifest.get("evidence_ids", []))
        check("manifest tool_results_count == 1",
              manifest.get("tool_results_count") == 1)
        check("manifest has schema_version", "schema_version" in manifest)


# ---------------------------------------------------------------------------
# C. Valid metric binding (RSI top-level)
# ---------------------------------------------------------------------------

def test_c_valid_metric_binding_rsi():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="RSI is 62.5, indicating neutral-to-bullish momentum.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="technical_indicator_engine",
                    metric="rsi",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no INVALID_EVIDENCE_ID", "INVALID_EVIDENCE_ID" not in codes)
        check("no INVALID_EVIDENCE_TOOL_BINDING",
              "INVALID_EVIDENCE_TOOL_BINDING" not in codes)
        check("no INVALID_EVIDENCE_METRIC_BINDING",
              "INVALID_EVIDENCE_METRIC_BINDING" not in codes)
        check("no WEAK_NUMERIC_EVIDENCE_BINDING",
              "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("report.passed is True", report.passed)
        check("zero issues", len(report.issues) == 0)


# ---------------------------------------------------------------------------
# D. Valid field_path binding — moving average
# ---------------------------------------------------------------------------

def test_d_valid_field_path_moving_average():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="The stock trades above its 50-day moving average at 176.5.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    field_path="moving_averages.sma_50",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no WEAK_NUMERIC_EVIDENCE_BINDING",
              "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("no INVALID_EVIDENCE_FIELD_PATH_BINDING",
              "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in codes)
        check("report.passed is True", report.passed)


# ---------------------------------------------------------------------------
# E. Valid field_path binding — support/resistance
# ---------------------------------------------------------------------------

def test_e_valid_field_path_support_resistance():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="Support is near $175 and resistance is near $190.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="technical_indicator_engine",
                    field_path="levels.support",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no WEAK_NUMERIC_EVIDENCE_BINDING",
              "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("no INVALID_EVIDENCE_FIELD_PATH_BINDING",
              "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in codes)
        check("report.passed is True", report.passed)


# ---------------------------------------------------------------------------
# F. Valid metric binding — MACD histogram (top-level key)
# ---------------------------------------------------------------------------

def test_f_valid_metric_binding_macd_histogram():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="MACD histogram is positive at 0.30, confirming bullish crossover.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="technical_indicator_engine",
                    metric="macd_histogram",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no WEAK_NUMERIC_EVIDENCE_BINDING",
              "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("no INVALID_EVIDENCE_METRIC_BINDING",
              "INVALID_EVIDENCE_METRIC_BINDING" not in codes)
        check("report.passed is True", report.passed)


# ---------------------------------------------------------------------------
# G. Invalid metric binding → warning
# ---------------------------------------------------------------------------

def test_g_invalid_metric_binding_warning():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                # numeric claim — validator checks binding
                text="RSI is 62.5, indicating neutral-to-bullish momentum.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # metric only (no tool_name rescue) so binding fails cleanly
                    metric="nonexistent_indicator",
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
# H. Invalid field_path binding → warning
# ---------------------------------------------------------------------------

def test_h_invalid_field_path_binding_warning():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="The 50-day SMA is at 176.5.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # field_path only (no tool_name rescue) so binding fails cleanly
                    field_path="moving_averages.sma_999",
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
# I. Invalid tool_name binding → warning
# ---------------------------------------------------------------------------

def test_i_invalid_tool_name_binding_warning():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="RSI is 62.5.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # wrong tool_name — actual ToolResult.tool_name is
                    # "technical_indicator_engine"
                    tool_name="valuation_model",
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
# J. Missing evidence for numeric technical claim → error
# ---------------------------------------------------------------------------

def test_j_missing_evidence_numeric_claim():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="RSI is 62.5, indicating neutral-to-bullish momentum.",
                evidence=[],  # no evidence refs
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("UNSUPPORTED_NUMERIC_CLAIM error present",
              "UNSUPPORTED_NUMERIC_CLAIM" in codes)
        check("report.passed is False", not report.passed)


# ---------------------------------------------------------------------------
# K. Invalid evidence_id → error
# ---------------------------------------------------------------------------

def test_k_invalid_evidence_id_error():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            findings=[Finding(
                text="RSI is 62.5.",
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
# L. Technical risk — valid field_path binding
# ---------------------------------------------------------------------------

def test_l_technical_risk_valid_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            risks=[Risk(
                name="Support breakdown risk",
                description=(
                    "Downside risk increases if price breaks support at $175; "
                    "next major support would be the 200-day SMA at 154.0."
                ),
                severity="medium",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="technical_indicator_engine",
                    field_path="levels.support",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no WEAK_NUMERIC_EVIDENCE_BINDING (risk)",
              "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("no INVALID_EVIDENCE_FIELD_PATH_BINDING (risk)",
              "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in codes)
        check("no INVALID_EVIDENCE_TOOL_BINDING (risk)",
              "INVALID_EVIDENCE_TOOL_BINDING" not in codes)
        check("report.passed is True", report.passed)
        check("zero issues", len(report.issues) == 0)


# ---------------------------------------------------------------------------
# M. Technical risk — weak binding (evidence_id only)
# ---------------------------------------------------------------------------

def test_m_technical_risk_weak_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_store_with_technical(tmp)

        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=_RUN_ID,
            ticker=_TICKER,
            risks=[Risk(
                name="Support breakdown risk",
                description=(
                    "Downside risk increases if price breaks support at $175; "
                    "next major support would be the 200-day SMA at 154.0."
                ),
                severity="medium",
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
# N. End-to-end persisted ValidationReport
# ---------------------------------------------------------------------------

def test_n_end_to_end_persisted_report():
    with tempfile.TemporaryDirectory() as base_dir:
        # Use create_run_context with a temp base dir so CWD is irrelevant
        ctx = create_run_context(ticker=_TICKER, task="phase1b_e2e", base_dir=base_dir)

        # Build and persist technical ToolResult
        tr = technical_tool_result(
            run_id=ctx.run_id,
            target=_TICKER,
            metric_group="indicators",
            outputs=_TECHNICAL_OUTPUTS,
            inputs=_TECHNICAL_INPUTS,
            metadata={"description": "Phase 1B E2E — synthetic ORCL technical indicators"},
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

        # Well-formed AgentResult: one finding + one risk, both valid bindings
        ar = AgentResult(
            agent_name="PriceVolumeAgent",
            run_id=ctx.run_id,
            ticker=_TICKER,
            findings=[Finding(
                text=(
                    "RSI is 62.5 and MACD histogram is positive at 0.30, "
                    "with price trading above the 50-day SMA at 176.5."
                ),
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="technical_indicator_engine",
                    metric="rsi",
                )],
            )],
            risks=[Risk(
                name="Support breakdown risk",
                description=(
                    "Downside risk increases if price breaks support at $175; "
                    "next major support would be the 200-day SMA at 154.0."
                ),
                severity="medium",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="technical_indicator_engine",
                    field_path="levels.support",
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
    ("A.  Technical ToolResult construction",              test_a_technical_toolresult_construction),
    ("B.  EvidenceStore persistence",                      test_b_evidence_store_persistence),
    ("C.  Valid metric binding (RSI)",                     test_c_valid_metric_binding_rsi),
    ("D.  Valid field_path binding (moving_averages.sma_50)", test_d_valid_field_path_moving_average),
    ("E.  Valid field_path binding (levels.support)",      test_e_valid_field_path_support_resistance),
    ("F.  Valid metric binding (macd_histogram)",          test_f_valid_metric_binding_macd_histogram),
    ("G.  Invalid metric binding → warning",               test_g_invalid_metric_binding_warning),
    ("H.  Invalid field_path binding → warning",           test_h_invalid_field_path_binding_warning),
    ("I.  Invalid tool_name binding → warning",            test_i_invalid_tool_name_binding_warning),
    ("J.  Missing evidence for numeric claim → error",     test_j_missing_evidence_numeric_claim),
    ("K.  Invalid evidence_id → error",                    test_k_invalid_evidence_id_error),
    ("L.  Technical risk valid binding",                   test_l_technical_risk_valid_binding),
    ("M.  Technical risk weak binding → warning",          test_m_technical_risk_weak_binding),
    ("N.  End-to-end persisted ValidationReport",          test_n_end_to_end_persisted_report),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 1B: Isolated Technical ToolResult Integration — Tests")
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
