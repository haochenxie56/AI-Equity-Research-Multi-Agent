"""
scripts/test_reliability_mock_agent_roundtrip.py

Phase 1F: Mock Constrained Agent Roundtrip — end-to-end test suite.

Demonstrates the complete non-live loop:
    synthetic ToolResults
    → EvidenceStore
    → build_evidence_packet()
    → build_agent_result_prompt()
    → mock AgentResult JSON response
    → parse_agent_result_json()
    → validate_agent_result()
    → ValidationReport
    → build_repair_prompt() for invalid output

No live Claude API calls. No yfinance. No Anthropic SDK. No Streamlit.

Run:
    python scripts/test_reliability_mock_agent_roundtrip.py
"""

import json
import sys
import tempfile
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.reliability import (
    EvidenceStore,
    ValidationReport,
    create_run_context,
    validate_agent_result,
    valuation_tool_result,
    technical_tool_result,
    scanner_tool_result,
    parse_agent_result_json,
    parse_and_validate_agent_result,
    agent_result_to_json,
    build_evidence_packet,
    build_agent_result_prompt,
    build_repair_prompt,
)

# ---------------------------------------------------------------------------
# Synthetic output fixtures (per Phase 1F spec)
# ---------------------------------------------------------------------------

_TICKER = "ORCL"

_VAL_OUTPUTS = {
    "fair_value": 200.0,
    "current_price": 180.0,
    "upside_pct": 0.1111,
    "assumptions": {
        "wacc": 0.095,
        "terminal_growth": 0.025,
    },
    "dcf": {
        "base_case": {
            "fair_value": 200.0,
        },
    },
}

_TECH_OUTPUTS = {
    "rsi": 62.5,
    "macd_histogram": 0.30,
    "moving_averages": {
        "sma_50": 176.5,
    },
    "levels": {
        "support": 175.0,
        "resistance": 190.0,
    },
}

_SCAN_OUTPUTS = {
    "selected_tickers": ["ORCL"],
    "candidates": {
        "ORCL": {
            "composite_score": 91.2,
            "candidate_rank": 1,
            "strategy_breakdown": {
                "quality_growth_score": 92.5,
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Shared helper: build a standard store with 3 ToolResults
# ---------------------------------------------------------------------------

def _build_standard_store(tmp_dir: str):
    """
    Create RunContext + EvidenceStore with valuation, technical, and scanner
    ToolResults.

    Returns:
        (store, run_id, val_eid, tech_eid, scan_eid, run_dir, packet)
    """
    ctx = create_run_context(ticker=_TICKER, task="phase1f", base_dir=tmp_dir)
    store = EvidenceStore(run_dir=ctx.run_dir)

    tr_val = valuation_tool_result(
        run_id=ctx.run_id,
        target=_TICKER,
        metric_group="dcf",
        outputs=_VAL_OUTPUTS,
        metadata={"description": "Phase 1F synthetic valuation evidence"},
    )
    tr_tech = technical_tool_result(
        run_id=ctx.run_id,
        target=_TICKER,
        metric_group="rsi_macd",
        outputs=_TECH_OUTPUTS,
        metadata={"description": "Phase 1F synthetic technical evidence"},
    )
    tr_scan = scanner_tool_result(
        run_id=ctx.run_id,
        target="market",
        metric_group="stock_scanner",
        outputs=_SCAN_OUTPUTS,
        metadata={"description": "Phase 1F synthetic scanner evidence"},
    )

    val_eid = store.add_tool_result(tr_val)
    tech_eid = store.add_tool_result(tr_tech)
    scan_eid = store.add_tool_result(tr_scan)

    packet = build_evidence_packet(
        ctx.run_id, _TICKER, [tr_val, tr_tech, tr_scan]
    )

    return store, ctx.run_id, val_eid, tech_eid, scan_eid, ctx.run_dir, packet


def _valid_mock_response(run_id: str, val_eid: str, tech_eid: str, scan_eid: str) -> dict:
    """
    Build a compliant mock AgentResult dict that satisfies the Phase 1F prompt
    contract for all three ToolResults.

    Every numeric claim cites a valid evidence_id with matching tool_name and
    a resolvable metric or field_path.
    """
    return {
        "agent_name": "integrated_agent",
        "run_id": run_id,
        "ticker": _TICKER,
        "findings": [
            {
                "text": "DCF fair value is $200.",
                "confidence": 0.85,
                "evidence": [
                    {
                        "evidence_id": val_eid,
                        "tool_name": "valuation_model",
                        "metric": "fair_value",
                        "description": "Base case DCF fair value from valuation model",
                    }
                ],
            },
            {
                "text": "RSI is 62.5, indicating building momentum.",
                "confidence": 0.80,
                "evidence": [
                    {
                        "evidence_id": tech_eid,
                        "tool_name": "technical_indicator_engine",
                        "field_path": "rsi",
                        "description": "RSI from technical indicator engine",
                    }
                ],
            },
            {
                "text": "ORCL composite scanner score is 91.2.",
                "confidence": 0.75,
                "evidence": [
                    {
                        "evidence_id": scan_eid,
                        "tool_name": "stock_scanner",
                        "field_path": "candidates.ORCL.composite_score",
                        "description": "Composite score from stock scanner",
                    }
                ],
            },
        ],
        "assumptions": [
            {
                "name": "WACC",
                "rationale": "9.5% WACC from valuation model.",
                "value": "0.095",
                "source": "tool",
                "sensitivity": "high",
            }
        ],
        "risks": [
            {
                "name": "Support break risk",
                "description": (
                    "Downside risk increases if price breaks support at $175."
                ),
                "severity": "medium",
                "evidence": [
                    {
                        "evidence_id": tech_eid,
                        "tool_name": "technical_indicator_engine",
                        "field_path": "levels.support",
                        "description": "Support level from technical engine",
                    }
                ],
            }
        ],
        "confidence": {
            "level": "medium",
            "rationale": "Evidence-backed valuation, momentum, and scanner signals.",
            "score": 0.78,
        },
    }


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

_PASSED = 0
_FAILED = 0


def _pass(label: str) -> None:
    global _PASSED
    _PASSED += 1
    print(f"  PASS  {label}")


def _fail(label: str, reason: str) -> None:
    global _FAILED
    _FAILED += 1
    print(f"  FAIL  {label}")
    print(f"        {reason}")


def _run(label: str, fn):
    try:
        fn()
    except AssertionError as exc:
        _fail(label, str(exc) or "AssertionError")
    except Exception:
        _fail(label, traceback.format_exc().strip().splitlines()[-1])


# ===========================================================================
# Test Group A — Full valid roundtrip
# ===========================================================================

def test_a():
    print("\n[A] Full valid roundtrip — all findings fully evidenced")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, tech_eid, scan_eid, _rd, packet = \
            _build_standard_store(tmp)

        mock = _valid_mock_response(run_id, val_eid, tech_eid, scan_eid)

        def _a1():
            ar, report = parse_and_validate_agent_result(mock, store)
            assert ar.agent_name == "integrated_agent"
            assert ar.run_id == run_id
            _pass("A1: parse_and_validate returns (AgentResult, ValidationReport)")

        def _a2():
            _ar, report = parse_and_validate_agent_result(mock, store)
            assert report.passed, f"Expected passed=True, issues={report.issues}"
            _pass("A2: report.passed is True")

        def _a3():
            _ar, report = parse_and_validate_agent_result(mock, store)
            errors = [i for i in report.issues if i.severity == "error"]
            assert not errors, f"Unexpected errors: {errors}"
            _pass("A3: zero error-severity issues")

        def _a4():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "UNSUPPORTED_NUMERIC_CLAIM" not in codes, \
                f"Unexpected UNSUPPORTED_NUMERIC_CLAIM: {codes}"
            _pass("A4: no UNSUPPORTED_NUMERIC_CLAIM")

        def _a5():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_ID" not in codes, \
                f"Unexpected INVALID_EVIDENCE_ID: {codes}"
            _pass("A5: no INVALID_EVIDENCE_ID")

        def _a6():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes, \
                f"Unexpected WEAK_NUMERIC_EVIDENCE_BINDING: {codes}"
            _pass("A6: no WEAK_NUMERIC_EVIDENCE_BINDING")

        def _a7():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            binding_warnings = [
                c for c in codes if c.startswith("INVALID_EVIDENCE_") and "BINDING" in c
            ]
            assert not binding_warnings, \
                f"Unexpected binding warnings: {binding_warnings}"
            _pass("A7: no INVALID_EVIDENCE_*_BINDING warnings")

        def _a8():
            # Full zero-issue validation
            _ar, report = parse_and_validate_agent_result(mock, store)
            assert len(report.issues) == 0, \
                f"Expected 0 issues, got {len(report.issues)}: {report.issues}"
            _pass("A8: zero total issues (perfect roundtrip)")

        def _a9():
            # Valuation finding: "$200" bound via metric="fair_value"
            ar, report = parse_and_validate_agent_result(mock, store)
            val_finding = ar.findings[0]
            assert "200" in val_finding.text
            assert val_finding.evidence[0].evidence_id == val_eid
            assert val_finding.evidence[0].metric == "fair_value"
            _pass("A9: valuation finding has correct evidence binding")

        def _a10():
            # Technical finding: "62.5" bound via field_path="rsi"
            ar, report = parse_and_validate_agent_result(mock, store)
            tech_finding = ar.findings[1]
            assert "62.5" in tech_finding.text
            assert tech_finding.evidence[0].evidence_id == tech_eid
            assert tech_finding.evidence[0].field_path == "rsi"
            _pass("A10: technical finding has correct field_path binding")

        def _a11():
            # Scanner finding: "91.2" bound via field_path="candidates.ORCL.composite_score"
            ar, report = parse_and_validate_agent_result(mock, store)
            scan_finding = ar.findings[2]
            assert "91.2" in scan_finding.text
            ref = scan_finding.evidence[0]
            assert ref.evidence_id == scan_eid
            assert ref.field_path == "candidates.ORCL.composite_score"
            _pass("A11: scanner finding has correct deep field_path binding")

        def _a12():
            # Risk: "$175" bound via field_path="levels.support"
            ar, report = parse_and_validate_agent_result(mock, store)
            risk = ar.risks[0]
            assert "175" in risk.description
            ref = risk.evidence[0]
            assert ref.evidence_id == tech_eid
            assert ref.field_path == "levels.support"
            _pass("A12: risk has correct evidence binding for support level")

        _run("A1", _a1)
        _run("A2", _a2)
        _run("A3", _a3)
        _run("A4", _a4)
        _run("A5", _a5)
        _run("A6", _a6)
        _run("A7", _a7)
        _run("A8", _a8)
        _run("A9", _a9)
        _run("A10", _a10)
        _run("A11", _a11)
        _run("A12", _a12)


# ===========================================================================
# Test Group B — Prompt contains evidence contract
# ===========================================================================

def test_b():
    print("\n[B] Prompt contract content verification")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, tech_eid, scan_eid, _rd, packet = \
            _build_standard_store(tmp)

        prompt = build_agent_result_prompt(
            agent_name="integrated_agent",
            run_id=run_id,
            target_name=_TICKER,
            task_instruction=(
                "Analyse ORCL valuation, RSI momentum, and scanner ranking. "
                "Cite all numeric values from the evidence packet."
            ),
            evidence_packet=packet,
        )

        def _b1():
            assert isinstance(prompt, str) and len(prompt) > 500
            _pass("B1: prompt is a non-trivial string")

        def _b2():
            assert "JSON" in prompt or "json" in prompt.lower()
            _pass("B2: JSON-only requirement present")

        def _b3():
            assert "fabricate" in prompt.lower() or "NEVER" in prompt or "NOT" in prompt
            _pass("B3: anti-fabrication rule present")

        def _b4():
            assert "EvidenceRef" in prompt
            _pass("B4: EvidenceRef requirement present")

        def _b5():
            assert run_id in prompt
            _pass("B5: run_id embedded in prompt")

        def _b6():
            assert _TICKER in prompt
            _pass("B6: target_name (ORCL) embedded in prompt")

        def _b7():
            assert val_eid in prompt, f"val_eid {val_eid!r} not in prompt"
            assert tech_eid in prompt, f"tech_eid {tech_eid!r} not in prompt"
            assert scan_eid in prompt, f"scan_eid {scan_eid!r} not in prompt"
            _pass("B7: all three evidence_ids embedded in prompt")

        def _b8():
            assert "AgentResult" in prompt
            _pass("B8: AgentResult schema summary embedded")

        def _b9():
            assert "invent" in prompt.lower() or "fabricat" in prompt.lower()
            _pass("B9: no-fabrication language present")

        def _b10():
            assert "insufficient" in prompt.lower() or "uncertainty" in prompt.lower()
            _pass("B10: insufficiency-behaviour instruction present")

        def _b11():
            assert "markdown" in prompt.lower() or "prose" in prompt.lower()
            _pass("B11: no-markdown / no-prose rule present")

        def _b12():
            # Evidence packet JSON is embedded in prompt (check a known path)
            assert "candidates.ORCL.composite_score" in prompt or \
                   "notable_field_paths" in prompt
            _pass("B12: notable field paths from scanner embedded in prompt")

        _run("B1", _b1)
        _run("B2", _b2)
        _run("B3", _b3)
        _run("B4", _b4)
        _run("B5", _b5)
        _run("B6", _b6)
        _run("B7", _b7)
        _run("B8", _b8)
        _run("B9", _b9)
        _run("B10", _b10)
        _run("B11", _b11)
        _run("B12", _b12)


# ===========================================================================
# Test Group C — Unsupported numeric claim roundtrip
# ===========================================================================

def test_c():
    print("\n[C] Unsupported numeric claim — no evidence refs")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, _tech, _scan, _rd, _pkt = \
            _build_standard_store(tmp)

        mock = {
            "agent_name": "integrated_agent",
            "run_id": run_id,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [],  # empty — violates contract rule 2
                }
            ],
        }

        def _c1():
            ar = parse_agent_result_json(mock)
            assert ar is not None
            _pass("C1: parse succeeds (schema is structurally valid)")

        def _c2():
            _ar, report = parse_and_validate_agent_result(mock, store)
            assert not report.passed, "Expected passed=False"
            _pass("C2: report.passed is False")

        def _c3():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "UNSUPPORTED_NUMERIC_CLAIM" in codes, \
                f"Expected UNSUPPORTED_NUMERIC_CLAIM in {codes}"
            _pass("C3: UNSUPPORTED_NUMERIC_CLAIM reported")

        def _c4():
            _ar, report = parse_and_validate_agent_result(mock, store)
            errors = [i for i in report.issues if i.severity == "error"]
            assert len(errors) >= 1
            _pass("C4: at least one error-severity issue present")

        _run("C1", _c1)
        _run("C2", _c2)
        _run("C3", _c3)
        _run("C4", _c4)


# ===========================================================================
# Test Group D — Fabricated evidence_id roundtrip
# ===========================================================================

def test_d():
    print("\n[D] Fabricated evidence_id — not in EvidenceStore")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, _tech, _scan, _rd, _pkt = \
            _build_standard_store(tmp)

        mock = {
            "agent_name": "integrated_agent",
            "run_id": run_id,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [
                        {
                            # Fabricated ID — not in store
                            "evidence_id": "hallucinated_eid_not_in_store_xyz",
                            "tool_name": "valuation_model",
                            "metric": "fair_value",
                        }
                    ],
                }
            ],
        }

        def _d1():
            ar = parse_agent_result_json(mock)
            assert ar is not None
            _pass("D1: parse succeeds (fabricated ID is structurally valid)")

        def _d2():
            _ar, report = parse_and_validate_agent_result(mock, store)
            assert not report.passed, "Expected passed=False"
            _pass("D2: report.passed is False")

        def _d3():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_ID" in codes, \
                f"Expected INVALID_EVIDENCE_ID in {codes}"
            _pass("D3: INVALID_EVIDENCE_ID reported")

        _run("D1", _d1)
        _run("D2", _d2)
        _run("D3", _d3)


# ===========================================================================
# Test Group E — Weak binding (evidence_id only, no metadata)
# ===========================================================================

def test_e():
    print("\n[E] Weak binding — evidence_id only, no tool_name/metric/field_path")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, _tech, _scan, _rd, _pkt = \
            _build_standard_store(tmp)

        mock = {
            "agent_name": "integrated_agent",
            "run_id": run_id,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            # No tool_name, metric, or field_path
                        }
                    ],
                }
            ],
        }

        def _e1():
            _ar, report = parse_and_validate_agent_result(mock, store)
            assert report.passed, \
                f"Expected passed=True (warnings only), issues={report.issues}"
            _pass("E1: report.passed is True (warnings do not fail)")

        def _e2():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "WEAK_NUMERIC_EVIDENCE_BINDING" in codes, \
                f"Expected WEAK_NUMERIC_EVIDENCE_BINDING in {codes}"
            _pass("E2: WEAK_NUMERIC_EVIDENCE_BINDING warning reported")

        def _e3():
            _ar, report = parse_and_validate_agent_result(mock, store)
            errors = [i for i in report.issues if i.severity == "error"]
            assert not errors, f"Unexpected errors: {errors}"
            _pass("E3: no error-severity issues (evidence_id is valid)")

        _run("E1", _e1)
        _run("E2", _e2)
        _run("E3", _e3)


# ===========================================================================
# Test Group F — Mismatched tool_name roundtrip
# ===========================================================================

def test_f():
    print("\n[F] Mismatched tool_name — wrong tool cited for valuation evidence")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, _tech, _scan, _rd, _pkt = \
            _build_standard_store(tmp)

        mock = {
            "agent_name": "integrated_agent",
            "run_id": run_id,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            # Wrong tool — val_eid belongs to "valuation_model"
                            "tool_name": "technical_indicator_engine",
                        }
                    ],
                }
            ],
        }

        def _f1():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_TOOL_BINDING" in codes, \
                f"Expected INVALID_EVIDENCE_TOOL_BINDING in {codes}"
            _pass("F1: INVALID_EVIDENCE_TOOL_BINDING warning reported")

        def _f2():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "WEAK_NUMERIC_EVIDENCE_BINDING" in codes, \
                f"Expected WEAK_NUMERIC_EVIDENCE_BINDING in {codes}"
            _pass("F2: WEAK_NUMERIC_EVIDENCE_BINDING also reported (no valid binding)")

        def _f3():
            _ar, report = parse_and_validate_agent_result(mock, store)
            assert report.passed, \
                f"Expected passed=True (warnings only), issues={report.issues}"
            _pass("F3: report.passed is True (no error-severity issues)")

        _run("F1", _f1)
        _run("F2", _f2)
        _run("F3", _f3)


# ===========================================================================
# Test Group G — Invalid metric roundtrip
# ===========================================================================

def test_g():
    print("\n[G] Invalid metric — key not in ToolResult.outputs")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, _tech, _scan, _rd, _pkt = \
            _build_standard_store(tmp)

        mock = {
            "agent_name": "integrated_agent",
            "run_id": run_id,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            "metric": "nonexistent_metric_xyz",
                        }
                    ],
                }
            ],
        }

        def _g1():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_METRIC_BINDING" in codes, \
                f"Expected INVALID_EVIDENCE_METRIC_BINDING in {codes}"
            _pass("G1: INVALID_EVIDENCE_METRIC_BINDING warning reported")

        def _g2():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "WEAK_NUMERIC_EVIDENCE_BINDING" in codes, \
                f"Expected WEAK_NUMERIC_EVIDENCE_BINDING in {codes}"
            _pass("G2: WEAK_NUMERIC_EVIDENCE_BINDING also reported")

        def _g3():
            _ar, report = parse_and_validate_agent_result(mock, store)
            assert report.passed, \
                f"Expected passed=True (warnings only), issues={report.issues}"
            _pass("G3: report.passed is True (no error-severity issues)")

        _run("G1", _g1)
        _run("G2", _g2)
        _run("G3", _g3)


# ===========================================================================
# Test Group H — Invalid field_path roundtrip
# ===========================================================================

def test_h():
    print("\n[H] Invalid field_path — path does not resolve in outputs")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, _tech, _scan, _rd, _pkt = \
            _build_standard_store(tmp)

        mock = {
            "agent_name": "integrated_agent",
            "run_id": run_id,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            "field_path": "dcf.base_case.nonexistent_key",
                        }
                    ],
                }
            ],
        }

        def _h1():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_FIELD_PATH_BINDING" in codes, \
                f"Expected INVALID_EVIDENCE_FIELD_PATH_BINDING in {codes}"
            _pass("H1: INVALID_EVIDENCE_FIELD_PATH_BINDING warning reported")

        def _h2():
            _ar, report = parse_and_validate_agent_result(mock, store)
            codes = [i.code for i in report.issues]
            assert "WEAK_NUMERIC_EVIDENCE_BINDING" in codes, \
                f"Expected WEAK_NUMERIC_EVIDENCE_BINDING in {codes}"
            _pass("H2: WEAK_NUMERIC_EVIDENCE_BINDING also reported")

        def _h3():
            _ar, report = parse_and_validate_agent_result(mock, store)
            assert report.passed, \
                f"Expected passed=True (warnings only), issues={report.issues}"
            _pass("H3: report.passed is True (no error-severity issues)")

        _run("H1", _h1)
        _run("H2", _h2)
        _run("H3", _h3)


# ===========================================================================
# Test Group I — Malformed JSON roundtrip
# ===========================================================================

def test_i():
    print("\n[I] Malformed JSON string — parse_agent_result_json raises ValueError")

    def _i1():
        try:
            parse_agent_result_json("{not valid json at all}")
            _fail("I1", "Expected ValueError, got none")
        except ValueError as exc:
            assert "decode" in str(exc).lower() or "malformed" in str(exc).lower(), \
                f"Unexpected message: {exc}"
            _pass("I1: malformed JSON raises ValueError")

    def _i2():
        try:
            parse_agent_result_json('{"agent_name": "x"')  # unterminated
            _fail("I2", "Expected ValueError, got none")
        except ValueError:
            _pass("I2: unterminated JSON raises ValueError")

    def _i3():
        try:
            parse_agent_result_json(json.dumps([1, 2, 3]))  # JSON array
            _fail("I3", "Expected ValueError for JSON array")
        except ValueError as exc:
            assert "dict" in str(exc).lower() or "object" in str(exc).lower(), \
                f"Unexpected message: {exc}"
            _pass("I3: JSON array raises ValueError (must be object)")

    def _i4():
        try:
            parse_agent_result_json(None)  # type: ignore
            _fail("I4", "Expected TypeError for None")
        except TypeError:
            _pass("I4: None input raises TypeError")

    _run("I1", _i1)
    _run("I2", _i2)
    _run("I3", _i3)
    _run("I4", _i4)


# ===========================================================================
# Test Group J — Schema-invalid JSON roundtrip
# ===========================================================================

def test_j():
    print("\n[J] Schema-invalid JSON — missing required fields")

    def _j1():
        # Missing agent_name (required, min_length=1)
        d = {"run_id": "ORCL_run_001", "findings": []}
        try:
            parse_agent_result_json(d)
            _fail("J1", "Expected ValueError for missing agent_name")
        except ValueError:
            _pass("J1: missing agent_name raises ValueError")

    def _j2():
        # Missing run_id (required, min_length=1)
        d = {"agent_name": "valuation_agent", "findings": []}
        try:
            parse_agent_result_json(d)
            _fail("J2", "Expected ValueError for missing run_id")
        except ValueError:
            _pass("J2: missing run_id raises ValueError")

    def _j3():
        # Extra field (extra="forbid")
        d = {
            "agent_name": "valuation_agent",
            "run_id": "ORCL_run_001",
            "not_a_valid_field": "boom",
        }
        try:
            parse_agent_result_json(d)
            _fail("J3", "Expected ValueError for extra field")
        except ValueError:
            _pass("J3: extra field raises ValueError (extra='forbid')")

    def _j4():
        # Invalid confidence level (must be high/medium/low)
        d = {
            "agent_name": "valuation_agent",
            "run_id": "ORCL_run_001",
            "confidence": {
                "level": "very_high",  # not allowed
                "rationale": "test",
                "score": 0.9,
            },
        }
        try:
            parse_agent_result_json(d)
            _fail("J4", "Expected ValueError for invalid confidence level")
        except ValueError:
            _pass("J4: invalid confidence level raises ValueError")

    def _j5():
        # Empty agent_name (min_length=1)
        d = {"agent_name": "", "run_id": "ORCL_run_001"}
        try:
            parse_agent_result_json(d)
            _fail("J5", "Expected ValueError for empty agent_name")
        except ValueError:
            _pass("J5: empty agent_name raises ValueError")

    _run("J1", _j1)
    _run("J2", _j2)
    _run("J3", _j3)
    _run("J4", _j4)
    _run("J5", _j5)


# ===========================================================================
# Test Group K — Repair prompt generation
# ===========================================================================

def test_k():
    print("\n[K] Repair prompt generation from failed validation")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, tech_eid, scan_eid, _rd, packet = \
            _build_standard_store(tmp)

        # Build original prompt
        original_prompt = build_agent_result_prompt(
            agent_name="integrated_agent",
            run_id=run_id,
            target_name=_TICKER,
            task_instruction="Analyse ORCL valuation, momentum, and scanner.",
            evidence_packet=packet,
        )

        # Build a mock response that fails validation (fabricated evidence ID)
        invalid_mock = json.dumps({
            "agent_name": "integrated_agent",
            "run_id": run_id,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [
                        {"evidence_id": "fabricated_eid_xyz", "metric": "fair_value"}
                    ],
                }
            ],
        })

        # Collect validation errors
        _ar = parse_agent_result_json(invalid_mock)
        report = validate_agent_result(_ar, store)
        error_messages = [i.message for i in report.issues if i.severity == "error"]

        def _k1():
            assert not report.passed, "Expected passed=False for invalid mock"
            assert len(error_messages) >= 1, "Expected at least one error message"
            _pass("K1: invalid mock response produces validation errors")

        def _k2():
            repair = build_repair_prompt(
                invalid_output=invalid_mock,
                validation_errors=error_messages,
                original_prompt=original_prompt,
            )
            assert isinstance(repair, str) and len(repair) > 100
            _pass("K2: build_repair_prompt returns non-trivial string")

        def _k3():
            repair = build_repair_prompt(
                invalid_output=invalid_mock,
                validation_errors=error_messages,
                original_prompt=original_prompt,
            )
            # Each error message embedded in repair prompt
            for err in error_messages:
                assert err in repair, f"Error message not in repair prompt: {err!r}"
            _pass("K3: validation error messages embedded in repair prompt")

        def _k4():
            repair = build_repair_prompt(
                invalid_output=invalid_mock,
                validation_errors=error_messages,
                original_prompt=original_prompt,
            )
            lower = repair.lower()
            assert "invent" in lower or "fabricat" in lower or "NOT" in repair
            _pass("K4: repair prompt prohibits fabricating evidence")

        def _k5():
            repair = build_repair_prompt(
                invalid_output=invalid_mock,
                validation_errors=error_messages,
                original_prompt=original_prompt,
            )
            assert "JSON" in repair or "json" in repair.lower()
            _pass("K5: repair prompt demands JSON-only output")

        def _k6():
            # build_repair_prompt does NOT call any API or LLM —
            # it is a pure string-builder, so calling it never blocks or
            # raises a network error.
            import time
            t0 = time.monotonic()
            build_repair_prompt(
                invalid_output=invalid_mock,
                validation_errors=error_messages,
                original_prompt=original_prompt,
            )
            elapsed = time.monotonic() - t0
            assert elapsed < 1.0, f"build_repair_prompt took {elapsed:.3f}s — LLM call?!"
            _pass("K6: build_repair_prompt is fast (<1s), no API call")

        _run("K1", _k1)
        _run("K2", _k2)
        _run("K3", _k3)
        _run("K4", _k4)
        _run("K5", _k5)
        _run("K6", _k6)


# ===========================================================================
# Test Group L — ValidationReport JSON serialisation
# ===========================================================================

def test_l():
    print("\n[L] ValidationReport JSON serialisation")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, tech_eid, scan_eid, _rd, _pkt = \
            _build_standard_store(tmp)

        mock = _valid_mock_response(run_id, val_eid, tech_eid, scan_eid)
        _ar, report = parse_and_validate_agent_result(mock, store)

        def _l1():
            json_str = report.model_dump_json()
            assert isinstance(json_str, str)
            _pass("L1: model_dump_json() returns a string")

        def _l2():
            json_str = report.model_dump_json()
            reloaded = json.loads(json_str)
            assert isinstance(reloaded, dict)
            _pass("L2: serialised JSON is parseable")

        def _l3():
            json_str = report.model_dump_json()
            reloaded = json.loads(json_str)
            assert "run_id" in reloaded, "Missing run_id"
            assert "target_name" in reloaded, "Missing target_name"
            assert "passed" in reloaded, "Missing passed"
            assert "issues" in reloaded, "Missing issues"
            _pass("L3: serialised JSON has run_id / target_name / passed / issues")

        def _l4():
            json_str = report.model_dump_json()
            reloaded = json.loads(json_str)
            assert reloaded["passed"] is True
            assert reloaded["issues"] == []
            _pass("L4: passed=True and issues=[] in serialised JSON")

        def _l5():
            # Failing report also serialises correctly
            fail_mock = {
                "agent_name": "integrated_agent",
                "run_id": run_id,
                "findings": [
                    {"text": "DCF fair value is $200.", "evidence": []}
                ],
            }
            _ar2, report2 = parse_and_validate_agent_result(fail_mock, store)
            json_str = report2.model_dump_json()
            reloaded = json.loads(json_str)
            assert reloaded["passed"] is False
            assert len(reloaded["issues"]) >= 1
            _pass("L5: failing report serialises with passed=False and issues list")

        _run("L1", _l1)
        _run("L2", _l2)
        _run("L3", _l3)
        _run("L4", _l4)
        _run("L5", _l5)


# ===========================================================================
# Test Group M — End-to-end artifact persistence
# ===========================================================================

def test_m():
    print("\n[M] End-to-end artifact persistence")

    with tempfile.TemporaryDirectory() as tmp:
        store, run_id, val_eid, tech_eid, scan_eid, run_dir, packet = \
            _build_standard_store(tmp)

        mock = _valid_mock_response(run_id, val_eid, tech_eid, scan_eid)
        _ar, report = parse_and_validate_agent_result(mock, store)

        # Persist manifest explicitly (save_manifest() is the caller's responsibility)
        store.save_manifest()

        def _m1():
            jsonl_path = Path(run_dir) / "tool_results.jsonl"
            assert jsonl_path.exists(), f"tool_results.jsonl not found: {jsonl_path}"
            _pass("M1: tool_results.jsonl created on disk")

        def _m2():
            manifest_path = Path(run_dir) / "evidence_manifest.json"
            assert manifest_path.exists(), \
                f"evidence_manifest.json not found: {manifest_path}"
            _pass("M2: evidence_manifest.json created on disk")

        def _m3():
            jsonl_path = Path(run_dir) / "tool_results.jsonl"
            lines = jsonl_path.read_text().strip().splitlines()
            assert len(lines) == 3, f"Expected 3 JSONL records, got {len(lines)}"
            _pass("M3: tool_results.jsonl has exactly 3 records (val + tech + scan)")

        def _m4():
            jsonl_path = Path(run_dir) / "tool_results.jsonl"
            for line in jsonl_path.read_text().strip().splitlines():
                record = json.loads(line)  # must be valid JSON
                assert "evidence_id" in record
            _pass("M4: every JSONL record is valid JSON with evidence_id")

        def _m5():
            manifest_path = Path(run_dir) / "evidence_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            assert manifest.get("tool_results_count") == 3, \
                f"Expected tool_results_count=3, got {manifest}"
            _pass("M5: manifest tool_results_count == 3")

        def _m6():
            manifest_path = Path(run_dir) / "evidence_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            eids = manifest.get("evidence_ids", [])
            assert val_eid in eids, f"val_eid {val_eid!r} not in manifest"
            assert tech_eid in eids, f"tech_eid {tech_eid!r} not in manifest"
            assert scan_eid in eids, f"scan_eid {scan_eid!r} not in manifest"
            _pass("M6: all three evidence_ids in manifest")

        def _m7():
            run_dir_path = Path(run_dir)
            assert run_dir_path.exists()
            assert run_id in str(run_dir_path)
            _pass("M7: run directory exists and matches run_id")

        _run("M1", _m1)
        _run("M2", _m2)
        _run("M3", _m3)
        _run("M4", _m4)
        _run("M5", _m5)
        _run("M6", _m6)
        _run("M7", _m7)


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    print("=" * 62)
    print("Phase 1F: Mock Constrained Agent Roundtrip — test suite")
    print("=" * 62)

    test_a()
    test_b()
    test_c()
    test_d()
    test_e()
    test_f()
    test_g()
    test_h()
    test_i()
    test_j()
    test_k()
    test_l()
    test_m()

    print("\n" + "=" * 62)
    print(f"Results: {_PASSED} passed, {_FAILED} failed")
    print("=" * 62)
    sys.exit(0 if _FAILED == 0 else 1)
