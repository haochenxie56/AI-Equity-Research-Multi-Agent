"""
scripts/test_reliability_agent_output.py

Phase 1D: AgentResult JSON Contract / LLM Output Adapter — end-to-end test.

Tests parse_agent_result_json(), parse_and_validate_agent_result(), and
agent_result_to_json() using synthetic fixtures only.

No live Claude API calls. No yfinance. No Anthropic SDK.

Run:
    python scripts/test_reliability_agent_output.py
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
    EvidenceRef,
    Finding,
    AgentResult,
    AgentConfidence,
    Assumption,
    Risk,
    create_run_context,
    valuation_tool_result,
    technical_tool_result,
    parse_agent_result_json,
    parse_and_validate_agent_result,
    agent_result_to_json,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_RUN_ID = "ORCL_20260521_phase1d_abcd1234"
_TICKER = "ORCL"

# Placeholder evidence_id used in schema-only tests (not backed by a real store)
_PLACEHOLDER_EID = "schema_test_placeholder_eid_001"

_VALUATION_OUTPUTS = {
    "fair_value": 200.0,
    "current_price": 180.0,
    "upside_pct": 0.1111,
    "assumptions": {
        "wacc": 0.095,
        "terminal_growth": 0.025,
    },
    "dcf": {
        "base_case": {"fair_value": 200.0},
        "bear_case": {"fair_value": 150.0},
    },
}

_VALUATION_INPUTS = {
    "ticker": _TICKER,
    "wacc": 0.095,
    "terminal_growth_rate": 0.025,
    "forecast_years": 10,
}

_TECHNICAL_OUTPUTS = {
    "rsi": 62.5,
    "macd": 1.25,
    "moving_averages": {
        "sma_50": 176.5,
        "sma_200": 154.0,
    },
}

_TECHNICAL_INPUTS = {
    "ticker": _TICKER,
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
}

# Valid AgentResult dict for schema-only parsing tests (uses placeholder evidence_id)
_VALID_AGENT_DICT = {
    "agent_name": "valuation_agent",
    "run_id": _RUN_ID,
    "ticker": _TICKER,
    "findings": [
        {
            "text": "DCF fair value is $200, implying 11.1% upside.",
            "confidence": 0.82,
            "evidence": [
                {
                    "evidence_id": _PLACEHOLDER_EID,
                    "tool_name": "valuation_model",
                    "metric": "fair_value",
                    "description": "Base DCF fair value output",
                }
            ],
        }
    ],
    "assumptions": [
        {
            "name": "WACC assumption",
            "rationale": "Uses 9.5% WACC based on CAPM.",
            "source": "tool",
            "sensitivity": "high",
        }
    ],
    "risks": [
        {
            "name": "Valuation sensitivity",
            "description": "Downside if WACC rises above 10%.",
            "severity": "medium",
            "evidence": [
                {
                    "evidence_id": _PLACEHOLDER_EID,
                    "tool_name": "valuation_model",
                    "field_path": "assumptions.wacc",
                }
            ],
        }
    ],
    "confidence": {
        "level": "medium",
        "rationale": "High evidence quality from valuation model.",
        "score": 0.78,
    },
}


# ---------------------------------------------------------------------------
# Helper: build an EvidenceStore with valuation + technical ToolResults
# ---------------------------------------------------------------------------

def _make_store(tmp_dir: str) -> tuple[EvidenceStore, str, str]:
    """
    Creates an EvidenceStore with two ToolResults.

    Returns (store, val_eid, tech_eid).
    """
    store = EvidenceStore(run_dir=tmp_dir)

    tr_val = valuation_tool_result(
        run_id=_RUN_ID,
        target=_TICKER,
        metric_group="dcf",
        outputs=_VALUATION_OUTPUTS,
        inputs=_VALUATION_INPUTS,
    )
    val_eid = store.add_tool_result(tr_val)

    tr_tech = technical_tool_result(
        run_id=_RUN_ID,
        target=_TICKER,
        metric_group="rsi_macd",
        outputs=_TECHNICAL_OUTPUTS,
        inputs=_TECHNICAL_INPUTS,
    )
    tech_eid = store.add_tool_result(tr_tech)

    return store, val_eid, tech_eid


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
# Test Group A — parse valid dict
# ===========================================================================

def test_a():
    print("\n[A] parse_agent_result_json — valid dict")

    def _a1():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        assert isinstance(ar, AgentResult), f"Expected AgentResult, got {type(ar)}"
        _pass("A1: returns AgentResult instance")

    def _a2():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        assert ar.agent_name == "valuation_agent"
        assert ar.run_id == _RUN_ID
        assert ar.ticker == _TICKER
        _pass("A2: agent_name / run_id / ticker preserved")

    def _a3():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        assert len(ar.findings) == 1
        assert ar.findings[0].text == "DCF fair value is $200, implying 11.1% upside."
        _pass("A3: findings parsed correctly")

    def _a4():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        assert len(ar.assumptions) == 1
        assert ar.assumptions[0].name == "WACC assumption"
        assert ar.assumptions[0].source == "tool"
        assert ar.assumptions[0].sensitivity == "high"
        _pass("A4: assumptions parsed correctly")

    def _a5():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        assert len(ar.risks) == 1
        assert ar.risks[0].severity == "medium"
        _pass("A5: risks parsed correctly")

    def _a6():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        assert ar.confidence is not None
        assert ar.confidence.level == "medium"
        assert abs(ar.confidence.score - 0.78) < 1e-9
        _pass("A6: confidence parsed correctly")

    _run("A1", _a1)
    _run("A2", _a2)
    _run("A3", _a3)
    _run("A4", _a4)
    _run("A5", _a5)
    _run("A6", _a6)


# ===========================================================================
# Test Group B — parse valid JSON string
# ===========================================================================

def test_b():
    print("\n[B] parse_agent_result_json — valid JSON string")

    def _b1():
        raw_str = json.dumps(_VALID_AGENT_DICT)
        ar = parse_agent_result_json(raw_str)
        assert isinstance(ar, AgentResult)
        _pass("B1: parses valid JSON string")

    def _b2():
        raw_str = json.dumps(_VALID_AGENT_DICT)
        ar = parse_agent_result_json(raw_str)
        assert ar.agent_name == _VALID_AGENT_DICT["agent_name"]
        assert ar.run_id == _VALID_AGENT_DICT["run_id"]
        _pass("B2: string parse yields same fields as dict parse")

    _run("B1", _b1)
    _run("B2", _b2)


# ===========================================================================
# Test Group C — malformed JSON → ValueError
# ===========================================================================

def test_c():
    print("\n[C] parse_agent_result_json — malformed JSON string")

    def _c1():
        try:
            parse_agent_result_json("{not valid json}")
            _fail("C1", "Expected ValueError, got none")
        except ValueError as exc:
            assert "could not decode" in str(exc).lower() or "malformed" in str(exc).lower(), \
                f"Unexpected message: {exc}"
            _pass("C1: malformed JSON raises ValueError")

    def _c2():
        try:
            parse_agent_result_json('{"agent_name": "x"')  # unterminated
            _fail("C2", "Expected ValueError, got none")
        except ValueError:
            _pass("C2: unterminated JSON raises ValueError")

    _run("C1", _c1)
    _run("C2", _c2)


# ===========================================================================
# Test Group D — unsupported type → TypeError / ValueError
# ===========================================================================

def test_d():
    print("\n[D] parse_agent_result_json — unsupported input types")

    def _d1():
        try:
            parse_agent_result_json([{"agent_name": "x"}])  # list
            _fail("D1", "Expected TypeError, got none")
        except TypeError as exc:
            assert "list" in str(exc).lower() or "Expected" in str(exc), \
                f"Unexpected message: {exc}"
            _pass("D1: list input raises TypeError")

    def _d2():
        try:
            parse_agent_result_json(42)  # int
            _fail("D2", "Expected TypeError, got none")
        except TypeError:
            _pass("D2: int input raises TypeError")

    def _d3():
        try:
            parse_agent_result_json(None)  # None
            _fail("D3", "Expected TypeError, got none")
        except TypeError:
            _pass("D3: None input raises TypeError")

    def _d4():
        # JSON string that decodes to a list is also invalid
        try:
            parse_agent_result_json(json.dumps([1, 2, 3]))
            _fail("D4", "Expected ValueError, got none")
        except ValueError as exc:
            assert "dict" in str(exc).lower() or "object" in str(exc).lower(), \
                f"Unexpected message: {exc}"
            _pass("D4: JSON list string raises ValueError (must be object)")

    _run("D1", _d1)
    _run("D2", _d2)
    _run("D3", _d3)
    _run("D4", _d4)


# ===========================================================================
# Test Group E — missing required fields → ValueError
# ===========================================================================

def test_e():
    print("\n[E] parse_agent_result_json — missing required fields")

    def _e1():
        # Missing agent_name
        d = {k: v for k, v in _VALID_AGENT_DICT.items() if k != "agent_name"}
        try:
            parse_agent_result_json(d)
            _fail("E1", "Expected ValueError for missing agent_name")
        except ValueError:
            _pass("E1: missing agent_name raises ValueError")

    def _e2():
        # Missing run_id
        d = {k: v for k, v in _VALID_AGENT_DICT.items() if k != "run_id"}
        try:
            parse_agent_result_json(d)
            _fail("E2", "Expected ValueError for missing run_id")
        except ValueError:
            _pass("E2: missing run_id raises ValueError")

    def _e3():
        # Empty agent_name (min_length=1)
        d = {**_VALID_AGENT_DICT, "agent_name": ""}
        try:
            parse_agent_result_json(d)
            _fail("E3", "Expected ValueError for empty agent_name")
        except ValueError:
            _pass("E3: empty agent_name raises ValueError")

    _run("E1", _e1)
    _run("E2", _e2)
    _run("E3", _e3)


# ===========================================================================
# Test Group F — extra fields → ValueError (extra="forbid")
# ===========================================================================

def test_f():
    print("\n[F] parse_agent_result_json — extra fields rejected")

    def _f1():
        d = {**_VALID_AGENT_DICT, "unknown_extra_field": "boom"}
        try:
            parse_agent_result_json(d)
            _fail("F1", "Expected ValueError for extra field, got none")
        except ValueError as exc:
            assert "extra" in str(exc).lower() or "unexpected" in str(exc).lower() \
                or "forbidden" in str(exc).lower() or "schema" in str(exc).lower(), \
                f"Unexpected message: {exc}"
            _pass("F1: extra top-level field raises ValueError")

    def _f2():
        # Extra field inside a Finding
        d = dict(_VALID_AGENT_DICT)
        d["findings"] = [
            {
                "text": "RSI is 62.5.",
                "confidence": 0.9,
                "evidence": [],
                "extra_finding_field": "not allowed",
            }
        ]
        try:
            parse_agent_result_json(d)
            _fail("F2", "Expected ValueError for extra Finding field, got none")
        except ValueError:
            _pass("F2: extra field inside Finding raises ValueError")

    _run("F1", _f1)
    _run("F2", _f2)


# ===========================================================================
# Test Group G — EvidenceRef binding metadata preserved
# ===========================================================================

def test_g():
    print("\n[G] parse_agent_result_json — EvidenceRef metadata preserved")

    d = {
        "agent_name": "technical_agent",
        "run_id": _RUN_ID,
        "findings": [
            {
                "text": "RSI is 62.5, indicating momentum.",
                "evidence": [
                    {
                        "evidence_id": _PLACEHOLDER_EID,
                        "tool_name": "technical_indicator_engine",
                        "metric": "rsi",
                        "field_path": "rsi",
                        "excerpt": "rsi=62.5",
                        "description": "RSI from technical engine",
                    }
                ],
            }
        ],
    }

    def _g1():
        ar = parse_agent_result_json(d)
        ref = ar.findings[0].evidence[0]
        assert ref.evidence_id == _PLACEHOLDER_EID
        _pass("G1: evidence_id preserved")

    def _g2():
        ar = parse_agent_result_json(d)
        ref = ar.findings[0].evidence[0]
        assert ref.tool_name == "technical_indicator_engine"
        assert ref.metric == "rsi"
        assert ref.field_path == "rsi"
        _pass("G2: tool_name / metric / field_path preserved")

    def _g3():
        ar = parse_agent_result_json(d)
        ref = ar.findings[0].evidence[0]
        assert ref.excerpt == "rsi=62.5"
        assert ref.description == "RSI from technical engine"
        _pass("G3: excerpt / description preserved")

    _run("G1", _g1)
    _run("G2", _g2)
    _run("G3", _g3)


# ===========================================================================
# Test Group H — parse succeeds with placeholder eid; validation fails
# ===========================================================================

def test_h():
    print("\n[H] parse succeeds / validation fails for unknown evidence_id")

    d = {
        "agent_name": "valuation_agent",
        "run_id": _RUN_ID,
        "findings": [
            {
                "text": "DCF fair value is $200.",
                "evidence": [
                    {
                        "evidence_id": "definitely_not_in_any_store_abc123",
                        "tool_name": "valuation_model",
                        "metric": "fair_value",
                    }
                ],
            }
        ],
    }

    def _h1():
        ar = parse_agent_result_json(d)
        assert isinstance(ar, AgentResult)
        _pass("H1: parse succeeds even with unknown evidence_id")

    def _h2():
        ar = parse_agent_result_json(d)
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(run_dir=tmp)
            from lib.reliability import validate_agent_result
            report = validate_agent_result(ar, store)
        assert not report.passed, "Expected validation to fail for unknown evidence_id"
        _pass("H2: validation fails (passed=False) for unknown evidence_id")

    def _h3():
        ar = parse_agent_result_json(d)
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(run_dir=tmp)
            from lib.reliability import validate_agent_result
            report = validate_agent_result(ar, store)
        codes = [i.code for i in report.issues]
        assert "INVALID_EVIDENCE_ID" in codes, f"Expected INVALID_EVIDENCE_ID in {codes}"
        _pass("H3: INVALID_EVIDENCE_ID reported for missing evidence_id")

    _run("H1", _h1)
    _run("H2", _h2)
    _run("H3", _h3)


# ===========================================================================
# Test Group I — parse_and_validate: valid valuation finding → passes
# ===========================================================================

def test_i():
    print("\n[I] parse_and_validate — valid valuation finding")

    with tempfile.TemporaryDirectory() as tmp:
        store, val_eid, _tech_eid = _make_store(tmp)

        d = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
            "ticker": _TICKER,
            "findings": [
                {
                    "text": "DCF fair value is $200, implying 11.1% upside.",
                    "confidence": 0.85,
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            "tool_name": "valuation_model",
                            "metric": "fair_value",
                        }
                    ],
                }
            ],
        }

        def _i1():
            ar, report = parse_and_validate_agent_result(d, store)
            assert isinstance(ar, AgentResult)
            _pass("I1: returns (AgentResult, ValidationReport) tuple")

        def _i2():
            ar, report = parse_and_validate_agent_result(d, store)
            errors = [i for i in report.issues if i.severity == "error"]
            assert not errors, f"Unexpected errors: {errors}"
            _pass("I2: no error-severity issues")

        def _i3():
            ar, report = parse_and_validate_agent_result(d, store)
            assert report.passed, f"Expected passed=True, issues={report.issues}"
            _pass("I3: report.passed is True")

        _run("I1", _i1)
        _run("I2", _i2)
        _run("I3", _i3)


# ===========================================================================
# Test Group J — parse_and_validate: valid technical finding → passes
# ===========================================================================

def test_j():
    print("\n[J] parse_and_validate — valid technical finding")

    with tempfile.TemporaryDirectory() as tmp:
        store, _val_eid, tech_eid = _make_store(tmp)

        d = {
            "agent_name": "technical_agent",
            "run_id": _RUN_ID,
            "ticker": _TICKER,
            "findings": [
                {
                    "text": "RSI reads 62.5 — momentum is building.",
                    "evidence": [
                        {
                            "evidence_id": tech_eid,
                            "tool_name": "technical_indicator_engine",
                            "field_path": "rsi",
                        }
                    ],
                }
            ],
        }

        def _j1():
            _ar, report = parse_and_validate_agent_result(d, store)
            assert report.passed, f"Expected passed=True, issues={report.issues}"
            _pass("J1: technical finding with field_path binding passes")

        def _j2():
            _ar, report = parse_and_validate_agent_result(d, store)
            errors = [i for i in report.issues if i.severity == "error"]
            assert not errors, f"Unexpected errors: {errors}"
            _pass("J2: no error-severity issues for technical finding")

        _run("J1", _j1)
        _run("J2", _j2)


# ===========================================================================
# Test Group K — numeric claim missing evidence → UNSUPPORTED_NUMERIC_CLAIM error
# ===========================================================================

def test_k():
    print("\n[K] parse_and_validate — numeric claim missing evidence")

    with tempfile.TemporaryDirectory() as tmp:
        store, _val_eid, _tech_eid = _make_store(tmp)

        d = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
            "findings": [
                {
                    "text": "The DCF fair value is $200.",
                    "evidence": [],  # empty — triggers UNSUPPORTED_NUMERIC_CLAIM
                }
            ],
        }

        def _k1():
            _ar, report = parse_and_validate_agent_result(d, store)
            assert not report.passed, "Expected passed=False"
            _pass("K1: report.passed is False")

        def _k2():
            _ar, report = parse_and_validate_agent_result(d, store)
            codes = [i.code for i in report.issues]
            assert "UNSUPPORTED_NUMERIC_CLAIM" in codes, \
                f"Expected UNSUPPORTED_NUMERIC_CLAIM in {codes}"
            _pass("K2: UNSUPPORTED_NUMERIC_CLAIM reported")

        _run("K1", _k1)
        _run("K2", _k2)


# ===========================================================================
# Test Group L — invalid evidence_id → INVALID_EVIDENCE_ID error
# ===========================================================================

def test_l():
    print("\n[L] parse_and_validate — invalid evidence_id")

    with tempfile.TemporaryDirectory() as tmp:
        store, _val_eid, _tech_eid = _make_store(tmp)

        d = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
            "findings": [
                {
                    "text": "Fair value is $200.",
                    "evidence": [
                        {
                            "evidence_id": "nonexistent_eid_xyz_000",
                            "tool_name": "valuation_model",
                            "metric": "fair_value",
                        }
                    ],
                }
            ],
        }

        def _l1():
            _ar, report = parse_and_validate_agent_result(d, store)
            assert not report.passed, "Expected passed=False"
            _pass("L1: report.passed is False")

        def _l2():
            _ar, report = parse_and_validate_agent_result(d, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_ID" in codes, \
                f"Expected INVALID_EVIDENCE_ID in {codes}"
            _pass("L2: INVALID_EVIDENCE_ID reported")

        _run("L1", _l1)
        _run("L2", _l2)


# ===========================================================================
# Test Group M — evidence_id only (no binding metadata) → WEAK_NUMERIC_EVIDENCE_BINDING
# ===========================================================================

def test_m():
    print("\n[M] parse_and_validate — evidence_id only, no binding → WEAK warning")

    with tempfile.TemporaryDirectory() as tmp:
        store, val_eid, _tech_eid = _make_store(tmp)

        d = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
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

        def _m1():
            _ar, report = parse_and_validate_agent_result(d, store)
            assert report.passed, f"Expected passed=True (warnings only), issues={report.issues}"
            _pass("M1: report passes (warnings are not failures)")

        def _m2():
            _ar, report = parse_and_validate_agent_result(d, store)
            codes = [i.code for i in report.issues]
            assert "WEAK_NUMERIC_EVIDENCE_BINDING" in codes, \
                f"Expected WEAK_NUMERIC_EVIDENCE_BINDING in {codes}"
            _pass("M2: WEAK_NUMERIC_EVIDENCE_BINDING issued for unbound evidence")

        def _m3():
            _ar, report = parse_and_validate_agent_result(d, store)
            errors = [i for i in report.issues if i.severity == "error"]
            assert not errors, f"Unexpected errors: {errors}"
            _pass("M3: no error-severity issues (evidence_id exists in store)")

        _run("M1", _m1)
        _run("M2", _m2)
        _run("M3", _m3)


# ===========================================================================
# Test Group N — mismatched tool_name → INVALID_EVIDENCE_TOOL_BINDING + WEAK warning
# ===========================================================================

def test_n():
    print("\n[N] parse_and_validate — mismatched tool_name")

    with tempfile.TemporaryDirectory() as tmp:
        store, val_eid, _tech_eid = _make_store(tmp)

        d = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            # Wrong tool_name — ToolResult.tool_name is "valuation_model"
                            "tool_name": "technical_indicator_engine",
                        }
                    ],
                }
            ],
        }

        def _n1():
            _ar, report = parse_and_validate_agent_result(d, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_TOOL_BINDING" in codes, \
                f"Expected INVALID_EVIDENCE_TOOL_BINDING in {codes}"
            _pass("N1: INVALID_EVIDENCE_TOOL_BINDING reported for wrong tool_name")

        def _n2():
            _ar, report = parse_and_validate_agent_result(d, store)
            codes = [i.code for i in report.issues]
            assert "WEAK_NUMERIC_EVIDENCE_BINDING" in codes, \
                f"Expected WEAK_NUMERIC_EVIDENCE_BINDING in {codes}"
            _pass("N2: WEAK_NUMERIC_EVIDENCE_BINDING also reported (no valid binding)")

        def _n3():
            _ar, report = parse_and_validate_agent_result(d, store)
            errors = [i for i in report.issues if i.severity == "error"]
            assert not errors, f"Unexpected errors: {errors}"
            _pass("N3: no error-severity issues (evidence_id valid, only tool mismatch)")

        _run("N1", _n1)
        _run("N2", _n2)
        _run("N3", _n3)


# ===========================================================================
# Test Group O — invalid metric → INVALID_EVIDENCE_METRIC_BINDING + WEAK warning
# ===========================================================================

def test_o():
    print("\n[O] parse_and_validate — invalid metric binding")

    with tempfile.TemporaryDirectory() as tmp:
        store, val_eid, _tech_eid = _make_store(tmp)

        d = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            # Metric not present in _VALUATION_OUTPUTS
                            "metric": "nonexistent_metric_xyz",
                        }
                    ],
                }
            ],
        }

        def _o1():
            _ar, report = parse_and_validate_agent_result(d, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_METRIC_BINDING" in codes, \
                f"Expected INVALID_EVIDENCE_METRIC_BINDING in {codes}"
            _pass("O1: INVALID_EVIDENCE_METRIC_BINDING reported for bad metric")

        def _o2():
            _ar, report = parse_and_validate_agent_result(d, store)
            codes = [i.code for i in report.issues]
            assert "WEAK_NUMERIC_EVIDENCE_BINDING" in codes, \
                f"Expected WEAK_NUMERIC_EVIDENCE_BINDING in {codes}"
            _pass("O2: WEAK_NUMERIC_EVIDENCE_BINDING also reported")

        _run("O1", _o1)
        _run("O2", _o2)


# ===========================================================================
# Test Group P — risk with valid field_path binding → passes cleanly
# ===========================================================================

def test_p():
    print("\n[P] parse_and_validate — risk with valid nested field_path binding")

    with tempfile.TemporaryDirectory() as tmp:
        store, val_eid, tech_eid = _make_store(tmp)

        d = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
            "ticker": _TICKER,
            "findings": [
                {
                    "text": "The stock is attractively valued.",
                    # Non-numeric finding — no evidence required
                    "evidence": [],
                }
            ],
            "risks": [
                {
                    "name": "WACC sensitivity",
                    "description": "WACC is 9.5% — upside narrows if rates rise.",
                    "severity": "high",
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            "tool_name": "valuation_model",
                            "field_path": "assumptions.wacc",
                        }
                    ],
                }
            ],
        }

        def _p1():
            _ar, report = parse_and_validate_agent_result(d, store)
            assert report.passed, f"Expected passed=True, issues={report.issues}"
            _pass("P1: risk with valid field_path binding passes")

        def _p2():
            _ar, report = parse_and_validate_agent_result(d, store)
            codes = [i.code for i in report.issues]
            assert "WEAK_NUMERIC_EVIDENCE_BINDING" not in codes, \
                f"Unexpected WEAK_NUMERIC_EVIDENCE_BINDING: {codes}"
            _pass("P2: no WEAK_NUMERIC_EVIDENCE_BINDING when field_path resolves")

        def _p3():
            _ar, report = parse_and_validate_agent_result(d, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in codes, \
                f"Unexpected INVALID_EVIDENCE_FIELD_PATH_BINDING: {codes}"
            _pass("P3: no INVALID_EVIDENCE_FIELD_PATH_BINDING for valid nested path")

        _run("P1", _p1)
        _run("P2", _p2)
        _run("P3", _p3)


# ===========================================================================
# Test Group Q — agent_result_to_json round-trip
# ===========================================================================

def test_q():
    print("\n[Q] agent_result_to_json — JSON serialisation round-trip")

    def _q1():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        json_str = agent_result_to_json(ar)
        assert isinstance(json_str, str), f"Expected str, got {type(json_str)}"
        _pass("Q1: agent_result_to_json returns a string")

    def _q2():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        json_str = agent_result_to_json(ar)
        # Must be parseable JSON
        reloaded = json.loads(json_str)
        assert isinstance(reloaded, dict)
        _pass("Q2: output is valid JSON")

    def _q3():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        json_str = agent_result_to_json(ar)
        # Round-trip through parse
        ar2 = parse_agent_result_json(json_str)
        assert ar2.agent_name == ar.agent_name
        assert ar2.run_id == ar.run_id
        assert ar2.ticker == ar.ticker
        _pass("Q3: round-trip preserves agent_name / run_id / ticker")

    def _q4():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        json_str = agent_result_to_json(ar)
        ar2 = parse_agent_result_json(json_str)
        assert len(ar2.findings) == len(ar.findings)
        assert ar2.findings[0].text == ar.findings[0].text
        assert ar2.findings[0].confidence == ar.findings[0].confidence
        _pass("Q4: round-trip preserves findings")

    def _q5():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        json_str = agent_result_to_json(ar)
        ar2 = parse_agent_result_json(json_str)
        assert ar2.confidence is not None
        assert ar2.confidence.level == "medium"
        assert abs(ar2.confidence.score - 0.78) < 1e-9
        _pass("Q5: round-trip preserves confidence")

    def _q6():
        ar = parse_agent_result_json(_VALID_AGENT_DICT)
        json_str = agent_result_to_json(ar)
        ar2 = parse_agent_result_json(json_str)
        assert len(ar2.assumptions) == 1
        assert ar2.assumptions[0].name == "WACC assumption"
        assert ar2.assumptions[0].source == "tool"
        _pass("Q6: round-trip preserves assumptions")

    _run("Q1", _q1)
    _run("Q2", _q2)
    _run("Q3", _q3)
    _run("Q4", _q4)
    _run("Q5", _q5)
    _run("Q6", _q6)


# ===========================================================================
# Bonus test: E2E with create_run_context and two findings from different tools
# ===========================================================================

def test_e2e():
    print("\n[E2E] Full pipeline — two findings, two ToolResults, create_run_context")

    with tempfile.TemporaryDirectory() as base_dir:
        ctx = create_run_context(ticker=_TICKER, task="phase1d_e2e", base_dir=base_dir)
        store = EvidenceStore(run_dir=ctx.run_dir)

        tr_val = valuation_tool_result(
            run_id=ctx.run_id,
            target=_TICKER,
            metric_group="dcf",
            outputs=_VALUATION_OUTPUTS,
        )
        tr_tech = technical_tool_result(
            run_id=ctx.run_id,
            target=_TICKER,
            metric_group="rsi_macd",
            outputs=_TECHNICAL_OUTPUTS,
        )
        val_eid = store.add_tool_result(tr_val)
        tech_eid = store.add_tool_result(tr_tech)

        d = {
            "agent_name": "integrated_agent",
            "run_id": ctx.run_id,
            "ticker": _TICKER,
            "findings": [
                {
                    "text": "DCF fair value is $200, implying 11.1% upside.",
                    "confidence": 0.85,
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            "tool_name": "valuation_model",
                            "metric": "fair_value",
                        }
                    ],
                },
                {
                    "text": "RSI at 62.5 signals building momentum.",
                    "confidence": 0.75,
                    "evidence": [
                        {
                            "evidence_id": tech_eid,
                            "tool_name": "technical_indicator_engine",
                            "field_path": "rsi",
                        }
                    ],
                },
            ],
            "assumptions": [
                {
                    "name": "WACC",
                    "rationale": "Uses 9.5% WACC.",
                    "value": "0.095",
                    "source": "tool",
                    "sensitivity": "high",
                }
            ],
            "risks": [
                {
                    "name": "Rate risk",
                    "description": "WACC sensitivity — upside narrows if rates rise.",
                    "severity": "high",
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            "tool_name": "valuation_model",
                            "field_path": "assumptions.wacc",
                        }
                    ],
                }
            ],
            "confidence": {
                "level": "high",
                "rationale": "Both valuation and technical evidence available.",
                "score": 0.88,
            },
        }

        def _e1():
            ar, report = parse_and_validate_agent_result(d, store)
            assert isinstance(ar, AgentResult)
            assert len(ar.findings) == 2
            _pass("E2E-1: AgentResult with 2 findings parsed")

        def _e2():
            ar, report = parse_and_validate_agent_result(d, store)
            assert report.passed, f"Expected passed=True, issues={report.issues}"
            _pass("E2E-2: validation passes for both findings")

        def _e3():
            ar, report = parse_and_validate_agent_result(d, store)
            errors = [i for i in report.issues if i.severity == "error"]
            assert not errors, f"Unexpected errors: {errors}"
            _pass("E2E-3: no error-severity issues")

        def _e4():
            ar, report = parse_and_validate_agent_result(d, store)
            # Serialise and re-parse
            json_str = agent_result_to_json(ar)
            ar2 = parse_agent_result_json(json_str)
            assert len(ar2.findings) == 2
            assert ar2.confidence.level == "high"
            _pass("E2E-4: JSON round-trip preserves full result")

        def _e5():
            # Verify that the run_dir was created on disk
            assert Path(ctx.run_dir).exists(), f"run_dir not created: {ctx.run_dir}"
            _pass("E2E-5: run directory created on disk")

        _run("E2E-1", _e1)
        _run("E2E-2", _e2)
        _run("E2E-3", _e3)
        _run("E2E-4", _e4)
        _run("E2E-5", _e5)


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 1D: AgentResult JSON Contract — test suite")
    print("=" * 60)

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
    test_n()
    test_o()
    test_p()
    test_q()
    test_e2e()

    print("\n" + "=" * 60)
    print(f"Results: {_PASSED} passed, {_FAILED} failed")
    print("=" * 60)
    sys.exit(0 if _FAILED == 0 else 1)
