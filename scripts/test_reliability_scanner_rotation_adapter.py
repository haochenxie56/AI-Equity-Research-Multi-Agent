"""
Phase 1C: Isolated Scanner / Rotation ToolResult Integration — Tests

Demonstrates the end-to-end reliability pipeline for scanner scores and sector
rotation outputs without importing or modifying lib/rotation.py.

Run from repo root:
    python3 scripts/test_reliability_scanner_rotation_adapter.py
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
    scanner_tool_result,
    sector_rotation_tool_result,
    validate_agent_result,
)
from lib.reliability.serialization import save_json_model


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
# Synthetic outputs — does NOT import lib/rotation.py
# ---------------------------------------------------------------------------

_RUN_ID = "MARKET_20260521_phase1c_abcd1234"
_TARGET_MARKET = "market"

_ROTATION_OUTPUTS = {
    "as_of": "2026-05-21",
    "top_sector": "Technology",
    "sectors": {
        "Technology": {
            "sector_score": 87.5,
            "sector_rank": 1,
            "sector_momentum": 0.18,
            "relative_strength": 1.22,
            "etf": "XLK",
            "etf_return_1m": 0.075,
            "etf_return_3m": 0.162,
            "volume_trend": 1.35,
        },
        "Industrials": {
            "sector_score": 72.0,
            "sector_rank": 2,
            "sector_momentum": 0.11,
            "relative_strength": 1.08,
            "etf": "XLI",
            "etf_return_1m": 0.041,
            "etf_return_3m": 0.094,
            "volume_trend": 1.12,
        },
    },
}

_ROTATION_INPUTS = {
    "lookback_1m": 21,
    "lookback_3m": 63,
    "universe": "sector_etfs",
}

_SCANNER_OUTPUTS = {
    "as_of": "2026-05-21",
    "selected_tickers": ["ORCL", "AMD", "ANET"],
    "candidates": {
        "ORCL": {
            "composite_score": 91.2,
            "candidate_rank": 1,
            "strategy_breakdown": {
                "momentum_score": 88.0,
                "value_score": 74.0,
                "quality_growth_score": 92.5,
                "oversold_rebound_score": 40.0,
            },
            "sector": "Technology",
        },
        "AMD": {
            "composite_score": 86.4,
            "candidate_rank": 2,
            "strategy_breakdown": {
                "momentum_score": 90.0,
                "value_score": 62.0,
                "quality_growth_score": 81.0,
                "oversold_rebound_score": 55.0,
            },
            "sector": "Technology",
        },
    },
}

_SCANNER_INPUTS = {
    "universe": "sp500",
    "strategy_weights": {
        "momentum": 0.35,
        "value": 0.25,
        "quality_growth": 0.30,
        "oversold_rebound": 0.10,
    },
}


def _is_valid_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


def _make_rotation_store(tmp_dir: str):
    """Create EvidenceStore with one synthetic sector rotation ToolResult."""
    store = EvidenceStore(run_dir=Path(tmp_dir))
    tr = sector_rotation_tool_result(
        run_id=_RUN_ID,
        target=_TARGET_MARKET,
        metric_group="sector_rotation",
        outputs=_ROTATION_OUTPUTS,
        inputs=_ROTATION_INPUTS,
        metadata={"description": "Synthetic sector rotation — Phase 1C test"},
    )
    eid = store.add_tool_result(tr)
    return store, tr, eid


def _make_scanner_store(tmp_dir: str):
    """Create EvidenceStore with one synthetic stock scanner ToolResult."""
    store = EvidenceStore(run_dir=Path(tmp_dir))
    tr = scanner_tool_result(
        run_id=_RUN_ID,
        target=_TARGET_MARKET,
        metric_group="stock_scanner",
        outputs=_SCANNER_OUTPUTS,
        inputs=_SCANNER_INPUTS,
        metadata={"description": "Synthetic stock scanner — Phase 1C test"},
    )
    eid = store.add_tool_result(tr)
    return store, tr, eid


# ---------------------------------------------------------------------------
# A. Sector Rotation ToolResult construction
# ---------------------------------------------------------------------------

def test_a_rotation_toolresult_construction():
    tr = sector_rotation_tool_result(
        run_id=_RUN_ID,
        target=_TARGET_MARKET,
        metric_group="sector_rotation",
        outputs=_ROTATION_OUTPUTS,
        inputs=_ROTATION_INPUTS,
        metadata={"description": "Synthetic sector rotation"},
    )
    check("returns ToolResult instance", isinstance(tr, ToolResult))
    check("tool_name == 'sector_rotation_model'",
          tr.tool_name == "sector_rotation_model")
    check("run_id is non-empty", bool(tr.run_id))
    check("run_id matches", tr.run_id == _RUN_ID)
    check("evidence_id is non-empty", bool(tr.evidence_id))
    check("evidence_id contains run_id prefix", tr.evidence_id.startswith(_RUN_ID))
    check("ticker set to target", tr.ticker == _TARGET_MARKET)
    # Top-level outputs
    check("outputs: top_sector present", "top_sector" in tr.outputs)
    check("outputs: top_sector == 'Technology'",
          tr.outputs["top_sector"] == "Technology")
    check("outputs: sectors key present", "sectors" in tr.outputs)
    # Nested sector values
    check("outputs: Technology sector_score == 87.5",
          tr.outputs["sectors"]["Technology"]["sector_score"] == 87.5)
    check("outputs: Technology sector_rank == 1",
          tr.outputs["sectors"]["Technology"]["sector_rank"] == 1)
    check("outputs: Technology etf_return_1m == 0.075",
          tr.outputs["sectors"]["Technology"]["etf_return_1m"] == 0.075)
    check("outputs: Industrials sector_score == 72.0",
          tr.outputs["sectors"]["Industrials"]["sector_score"] == 72.0)
    # Inputs preserved
    check("inputs: universe == 'sector_etfs'",
          tr.inputs.get("universe") == "sector_etfs")
    check("description set from metadata", "Synthetic sector rotation" in tr.description)


# ---------------------------------------------------------------------------
# B. Stock Scanner ToolResult construction
# ---------------------------------------------------------------------------

def test_b_scanner_toolresult_construction():
    tr = scanner_tool_result(
        run_id=_RUN_ID,
        target=_TARGET_MARKET,
        metric_group="stock_scanner",
        outputs=_SCANNER_OUTPUTS,
        inputs=_SCANNER_INPUTS,
        metadata={"description": "Synthetic stock scanner"},
    )
    check("returns ToolResult instance", isinstance(tr, ToolResult))
    check("tool_name == 'stock_scanner'", tr.tool_name == "stock_scanner")
    check("run_id is non-empty", bool(tr.run_id))
    check("run_id matches", tr.run_id == _RUN_ID)
    check("evidence_id is non-empty", bool(tr.evidence_id))
    check("evidence_id contains run_id prefix", tr.evidence_id.startswith(_RUN_ID))
    check("ticker set to target", tr.ticker == _TARGET_MARKET)
    # Top-level outputs
    check("outputs: selected_tickers present", "selected_tickers" in tr.outputs)
    check("outputs: ORCL in selected_tickers",
          "ORCL" in tr.outputs["selected_tickers"])
    check("outputs: candidates key present", "candidates" in tr.outputs)
    # Nested candidate scores
    check("outputs: ORCL composite_score == 91.2",
          tr.outputs["candidates"]["ORCL"]["composite_score"] == 91.2)
    check("outputs: ORCL candidate_rank == 1",
          tr.outputs["candidates"]["ORCL"]["candidate_rank"] == 1)
    check("outputs: ORCL quality_growth_score == 92.5",
          tr.outputs["candidates"]["ORCL"]["strategy_breakdown"]["quality_growth_score"] == 92.5)
    check("outputs: AMD composite_score == 86.4",
          tr.outputs["candidates"]["AMD"]["composite_score"] == 86.4)
    # Inputs preserved
    check("inputs: universe == 'sp500'", tr.inputs.get("universe") == "sp500")
    check("description set from metadata", "Synthetic stock scanner" in tr.description)


# ---------------------------------------------------------------------------
# C. EvidenceStore persistence — both ToolResults in same store
# ---------------------------------------------------------------------------

def test_c_evidencestore_persistence_both():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=Path(tmp))

        tr_rot = sector_rotation_tool_result(
            run_id=_RUN_ID, target=_TARGET_MARKET,
            metric_group="sector_rotation", outputs=_ROTATION_OUTPUTS,
        )
        tr_scan = scanner_tool_result(
            run_id=_RUN_ID, target=_TARGET_MARKET,
            metric_group="stock_scanner", outputs=_SCANNER_OUTPUTS,
        )

        eid_rot = store.add_tool_result(tr_rot)
        eid_scan = store.add_tool_result(tr_scan)

        check("rotation evidence_id in store", eid_rot in store.evidence_ids())
        check("scanner evidence_id in store", eid_scan in store.evidence_ids())
        check("evidence IDs are distinct", eid_rot != eid_scan)
        check("store contains 2 results", len(store.all()) == 2)

        store.save_manifest()
        jsonl_path = Path(tmp) / "tool_results.jsonl"
        manifest_path = Path(tmp) / "evidence_manifest.json"

        check("tool_results.jsonl exists", jsonl_path.exists())
        check("evidence_manifest.json exists", manifest_path.exists())

        lines = [ln for ln in jsonl_path.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        check("JSONL has exactly 2 records", len(lines) == 2)
        check("both JSONL lines are valid JSON",
              all(_is_valid_json(ln) for ln in lines))

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        check("manifest tool_results_count == 2",
              manifest.get("tool_results_count") == 2)
        check("manifest contains rotation evidence_id",
              eid_rot in manifest.get("evidence_ids", []))
        check("manifest contains scanner evidence_id",
              eid_scan in manifest.get("evidence_ids", []))


# ---------------------------------------------------------------------------
# D. Valid rotation field_path binding — sector score
# ---------------------------------------------------------------------------

def test_d_valid_rotation_field_path_sector_score():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_rotation_store(tmp)

        ar = AgentResult(
            agent_name="SectorAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            findings=[Finding(
                text="Technology has a sector score of 87.5, ranking 1st.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="sector_rotation_model",
                    field_path="sectors.Technology.sector_score",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no INVALID_EVIDENCE_ID", "INVALID_EVIDENCE_ID" not in codes)
        check("no INVALID_EVIDENCE_TOOL_BINDING",
              "INVALID_EVIDENCE_TOOL_BINDING" not in codes)
        check("no INVALID_EVIDENCE_FIELD_PATH_BINDING",
              "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in codes)
        check("no WEAK_NUMERIC_EVIDENCE_BINDING",
              "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("report.passed is True", report.passed)
        check("zero issues", len(report.issues) == 0)


# ---------------------------------------------------------------------------
# E. Valid rotation field_path binding — ETF return
# ---------------------------------------------------------------------------

def test_e_valid_rotation_etf_return_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_rotation_store(tmp)

        ar = AgentResult(
            agent_name="SectorAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            findings=[Finding(
                text="XLK returned 7.5% over the last month.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="sector_rotation_model",
                    field_path="sectors.Technology.etf_return_1m",
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
# F. Valid scanner field_path binding — composite score
# ---------------------------------------------------------------------------

def test_f_valid_scanner_composite_score_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_scanner_store(tmp)

        ar = AgentResult(
            agent_name="ScannerAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            findings=[Finding(
                text="ORCL has a composite scanner score of 91.2, ranking 1st.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="stock_scanner",
                    field_path="candidates.ORCL.composite_score",
                )],
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("no INVALID_EVIDENCE_ID", "INVALID_EVIDENCE_ID" not in codes)
        check("no INVALID_EVIDENCE_TOOL_BINDING",
              "INVALID_EVIDENCE_TOOL_BINDING" not in codes)
        check("no INVALID_EVIDENCE_FIELD_PATH_BINDING",
              "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in codes)
        check("no WEAK_NUMERIC_EVIDENCE_BINDING",
              "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes)
        check("report.passed is True", report.passed)
        check("zero issues", len(report.issues) == 0)


# ---------------------------------------------------------------------------
# G. Valid scanner deep field_path binding — strategy breakdown
# ---------------------------------------------------------------------------

def test_g_valid_scanner_strategy_breakdown_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_scanner_store(tmp)

        ar = AgentResult(
            agent_name="ScannerAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            findings=[Finding(
                text="ORCL quality growth score is 92.5, highest in the universe.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="stock_scanner",
                    field_path="candidates.ORCL.strategy_breakdown.quality_growth_score",
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
# H. Invalid metric binding → warning
# ---------------------------------------------------------------------------

def test_h_invalid_metric_binding_warning():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_scanner_store(tmp)

        ar = AgentResult(
            agent_name="ScannerAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            findings=[Finding(
                text="ORCL has a composite scanner score of 91.2.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # metric only (no tool_name rescue) so binding fails cleanly
                    metric="nonexistent_score",
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
# I. Invalid field_path binding → warning
# ---------------------------------------------------------------------------

def test_i_invalid_field_path_binding_warning():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_scanner_store(tmp)

        ar = AgentResult(
            agent_name="ScannerAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            findings=[Finding(
                text="ORCL has a composite scanner score of 91.2.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # field_path only (no tool_name rescue) so binding fails cleanly
                    field_path="candidates.ORCL.strategy_breakdown.nonexistent_score",
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
# J. Invalid tool_name binding → warning
# ---------------------------------------------------------------------------

def test_j_invalid_tool_name_binding_warning():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_scanner_store(tmp)

        ar = AgentResult(
            agent_name="ScannerAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            findings=[Finding(
                text="ORCL has a composite scanner score of 91.2.",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    # wrong tool_name — actual ToolResult.tool_name is "stock_scanner"
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
# K. Missing evidence for numeric scanner claim → error
# ---------------------------------------------------------------------------

def test_k_missing_evidence_numeric_claim():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_scanner_store(tmp)

        ar = AgentResult(
            agent_name="ScannerAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            findings=[Finding(
                text="ORCL has a composite scanner score of 91.2.",
                evidence=[],  # no evidence refs
            )],
        )
        report = validate_agent_result(ar, store)
        codes = {i.code for i in report.issues}

        check("UNSUPPORTED_NUMERIC_CLAIM error present",
              "UNSUPPORTED_NUMERIC_CLAIM" in codes)
        check("report.passed is False", not report.passed)


# ---------------------------------------------------------------------------
# L. Invalid evidence_id → error
# ---------------------------------------------------------------------------

def test_l_invalid_evidence_id_error():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_scanner_store(tmp)

        ar = AgentResult(
            agent_name="ScannerAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            findings=[Finding(
                text="ORCL has a composite scanner score of 91.2.",
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
# M. Scanner / rotation risk — valid binding
# ---------------------------------------------------------------------------

def test_m_rotation_risk_valid_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_rotation_store(tmp)

        ar = AgentResult(
            agent_name="SectorAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            risks=[Risk(
                name="Sector rotation reversal",
                description=(
                    "Rotation risk rises if Technology sector score falls below 70; "
                    "current score is 87.5."
                ),
                severity="medium",
                evidence=[EvidenceRef(
                    evidence_id=eid,
                    tool_name="sector_rotation_model",
                    field_path="sectors.Technology.sector_score",
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
# N. Scanner / rotation risk — weak binding (evidence_id only)
# ---------------------------------------------------------------------------

def test_n_rotation_risk_weak_binding():
    with tempfile.TemporaryDirectory() as tmp:
        store, tr, eid = _make_rotation_store(tmp)

        ar = AgentResult(
            agent_name="SectorAgent",
            run_id=_RUN_ID,
            ticker=_TARGET_MARKET,
            risks=[Risk(
                name="Sector rotation reversal",
                description=(
                    "Rotation risk rises if Technology sector score falls below 70; "
                    "current score is 87.5."
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
# O. End-to-end persisted ValidationReport — both ToolResults in same store
# ---------------------------------------------------------------------------

def test_o_end_to_end_persisted_report():
    with tempfile.TemporaryDirectory() as base_dir:
        # Use create_run_context with a temp base dir
        ctx = create_run_context(
            ticker="MARKET", task="phase1c_e2e", base_dir=base_dir
        )
        store = EvidenceStore(run_dir=ctx.run_dir)

        # Add both ToolResults to shared store
        tr_rot = sector_rotation_tool_result(
            run_id=ctx.run_id, target="market",
            metric_group="sector_rotation", outputs=_ROTATION_OUTPUTS,
            inputs=_ROTATION_INPUTS,
            metadata={"description": "Phase 1C E2E — synthetic sector rotation"},
        )
        tr_scan = scanner_tool_result(
            run_id=ctx.run_id, target="market",
            metric_group="stock_scanner", outputs=_SCANNER_OUTPUTS,
            inputs=_SCANNER_INPUTS,
            metadata={"description": "Phase 1C E2E — synthetic stock scanner"},
        )
        eid_rot = store.add_tool_result(tr_rot)
        eid_scan = store.add_tool_result(tr_scan)
        store.save_manifest()

        check("run_id is non-empty", bool(ctx.run_id))
        check("tool_results.jsonl created",
              (ctx.run_dir / "tool_results.jsonl").exists())
        check("evidence_manifest.json created",
              (ctx.run_dir / "evidence_manifest.json").exists())

        # AgentResult with findings from both ToolResults + one risk
        ar = AgentResult(
            agent_name="OrchestratorAgent",
            run_id=ctx.run_id,
            ticker="MARKET",
            findings=[
                Finding(
                    text=(
                        "Technology sector ranks 1st with a sector score of 87.5 "
                        "and a 1-month ETF return of 7.5%."
                    ),
                    evidence=[EvidenceRef(
                        evidence_id=eid_rot,
                        tool_name="sector_rotation_model",
                        field_path="sectors.Technology.sector_score",
                    )],
                ),
                Finding(
                    text=(
                        "ORCL ranks 1st with composite score 91.2 and quality "
                        "growth score 92.5."
                    ),
                    evidence=[EvidenceRef(
                        evidence_id=eid_scan,
                        tool_name="stock_scanner",
                        field_path="candidates.ORCL.composite_score",
                    )],
                ),
            ],
            risks=[Risk(
                name="Sector rotation reversal",
                description=(
                    "Rotation risk rises if Technology sector score falls below 70; "
                    "current score is 87.5."
                ),
                severity="medium",
                evidence=[EvidenceRef(
                    evidence_id=eid_rot,
                    tool_name="sector_rotation_model",
                    field_path="sectors.Technology.sector_score",
                )],
            )],
        )

        report = validate_agent_result(ar, store)

        check("report.passed is True", report.passed)
        check("report.run_id == ctx.run_id", report.run_id == ctx.run_id)
        check("report.target_name == 'MARKET'", report.target_name == "MARKET")
        check("zero validation issues", len(report.issues) == 0)

        # Persist ValidationReport
        report_path = ctx.run_dir / "validation_report.json"
        save_json_model(report, report_path)

        check("validation_report.json created", report_path.exists())

        raw = json.loads(report_path.read_text(encoding="utf-8"))
        check("JSON has 'run_id'", "run_id" in raw)
        check("JSON has 'target_name'", "target_name" in raw)
        check("JSON has 'passed'", "passed" in raw)
        check("JSON has 'issues'", "issues" in raw)
        check("JSON passed == true", raw["passed"] is True)
        check("JSON run_id matches", raw["run_id"] == ctx.run_id)

        print(f"\n    Run ID       : {ctx.run_id}")
        print(f"    Run dir      : {ctx.run_dir}")
        print(f"    Rotation EID : {eid_rot}")
        print(f"    Scanner EID  : {eid_scan}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_TESTS = [
    ("A.  Sector rotation ToolResult construction",        test_a_rotation_toolresult_construction),
    ("B.  Stock scanner ToolResult construction",          test_b_scanner_toolresult_construction),
    ("C.  EvidenceStore persistence (both ToolResults)",   test_c_evidencestore_persistence_both),
    ("D.  Valid rotation field_path (sector_score)",       test_d_valid_rotation_field_path_sector_score),
    ("E.  Valid rotation field_path (etf_return_1m)",      test_e_valid_rotation_etf_return_binding),
    ("F.  Valid scanner field_path (composite_score)",     test_f_valid_scanner_composite_score_binding),
    ("G.  Valid scanner deep field_path (strategy breakdown)", test_g_valid_scanner_strategy_breakdown_binding),
    ("H.  Invalid metric binding → warning",               test_h_invalid_metric_binding_warning),
    ("I.  Invalid field_path binding → warning",           test_i_invalid_field_path_binding_warning),
    ("J.  Invalid tool_name binding → warning",            test_j_invalid_tool_name_binding_warning),
    ("K.  Missing evidence for numeric claim → error",     test_k_missing_evidence_numeric_claim),
    ("L.  Invalid evidence_id → error",                    test_l_invalid_evidence_id_error),
    ("M.  Rotation risk valid binding",                    test_m_rotation_risk_valid_binding),
    ("N.  Rotation risk weak binding → warning",           test_n_rotation_risk_weak_binding),
    ("O.  End-to-end persisted ValidationReport",          test_o_end_to_end_persisted_report),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 1C: Isolated Scanner / Rotation ToolResult Integration — Tests")
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
