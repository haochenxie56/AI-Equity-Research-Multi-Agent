"""
scripts/test_reliability_prompt_contracts.py

Phase 1E: Prompt Contract Drafting — isolated end-to-end test suite.

Tests extract_field_paths(), build_evidence_packet(), build_agent_result_prompt(),
build_schema_summary(), and build_repair_prompt() using synthetic ToolResults.

No live Claude API calls. No yfinance. No Anthropic SDK. No Streamlit.

Run:
    python scripts/test_reliability_prompt_contracts.py
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
    create_run_context,
    valuation_tool_result,
    technical_tool_result,
    scanner_tool_result,
    validate_agent_result,
    parse_agent_result_json,
)
from lib.reliability.prompt_contracts import (
    extract_field_paths,
    build_evidence_packet,
    build_schema_summary,
    build_agent_result_prompt,
    build_repair_prompt,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_RUN_ID = "ORCL_20260521_phase1e_abcd1234"
_TICKER = "ORCL"

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
        "bull_case": {"fair_value": 240.0},
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
}

_TECHNICAL_INPUTS = {
    "ticker": _TICKER,
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
}

_SCANNER_OUTPUTS = {
    "selected_tickers": ["ORCL", "AMD", "MSFT"],
    "universe_size": 500,
    "as_of": "2026-05-21",
    "candidates": {
        "ORCL": {
            "composite_score": 91.2,
            "candidate_rank": 1,
            "sector": "Technology",
            "strategy_breakdown": {
                "momentum_score": 88.0,
                "quality_growth_score": 92.5,
            },
        },
    },
}


def _make_val_tr():
    return valuation_tool_result(
        run_id=_RUN_ID,
        target=_TICKER,
        metric_group="dcf",
        outputs=_VALUATION_OUTPUTS,
        inputs=_VALUATION_INPUTS,
        metadata={"description": "DCF valuation model output for ORCL"},
    )


def _make_tech_tr():
    return technical_tool_result(
        run_id=_RUN_ID,
        target=_TICKER,
        metric_group="rsi_macd",
        outputs=_TECHNICAL_OUTPUTS,
        inputs=_TECHNICAL_INPUTS,
        metadata={"description": "Technical indicator engine output for ORCL"},
    )


def _make_scanner_tr():
    return scanner_tool_result(
        run_id=_RUN_ID,
        target="market",
        metric_group="stock_scanner",
        outputs=_SCANNER_OUTPUTS,
    )


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
# Test Group A — extract_field_paths: basic nested dict
# ===========================================================================

def test_a():
    print("\n[A] extract_field_paths — basic nested dict")

    payload = {
        "dcf": {"base_case": {"fair_value": 200}, "bear_case": {"fair_value": 150}},
        "assumptions": {"wacc": 0.095, "terminal_growth": 0.025},
        "fair_value": 200.0,
        "current_price": 180.0,
    }

    def _a1():
        paths = extract_field_paths(payload)
        assert "dcf.base_case.fair_value" in paths, \
            f"Expected 'dcf.base_case.fair_value' in {paths}"
        _pass("A1: dcf.base_case.fair_value found")

    def _a2():
        paths = extract_field_paths(payload)
        assert "assumptions.wacc" in paths, \
            f"Expected 'assumptions.wacc' in {paths}"
        _pass("A2: assumptions.wacc found")

    def _a3():
        paths = extract_field_paths(payload)
        assert "assumptions.terminal_growth" in paths, \
            f"Expected 'assumptions.terminal_growth' in {paths}"
        _pass("A3: assumptions.terminal_growth found")

    def _a4():
        paths = extract_field_paths(payload)
        assert "fair_value" in paths, f"Expected 'fair_value' in {paths}"
        assert "current_price" in paths, f"Expected 'current_price' in {paths}"
        _pass("A4: top-level scalar paths present")

    def _a5():
        # Lists: field name recorded, items not traversed
        p = {"items": [1, 2, 3], "nested": {"inner_list": ["a", "b"]}}
        paths = extract_field_paths(p)
        assert "items" in paths, f"Expected 'items' in {paths}"
        assert "nested.inner_list" in paths, f"Expected 'nested.inner_list' in {paths}"
        _pass("A5: list fields recorded without traversal into items")

    def _a6():
        # Empty dict → []
        paths = extract_field_paths({})
        assert paths == [], f"Expected [], got {paths}"
        _pass("A6: empty dict returns empty list")

    def _a7():
        # Non-dict → []
        paths = extract_field_paths("not a dict")  # type: ignore
        assert paths == [], f"Expected [], got {paths}"
        _pass("A7: non-dict returns empty list")

    _run("A1", _a1)
    _run("A2", _a2)
    _run("A3", _a3)
    _run("A4", _a4)
    _run("A5", _a5)
    _run("A6", _a6)
    _run("A7", _a7)


# ===========================================================================
# Test Group B — extract_field_paths: determinism with reordered dict
# ===========================================================================

def test_b():
    print("\n[B] extract_field_paths — deterministic output")

    def _b1():
        # Two dicts with same content but different key insertion order
        payload_a = {"wacc": 0.095, "fair_value": 200.0, "terminal_growth": 0.025}
        payload_b = {"terminal_growth": 0.025, "fair_value": 200.0, "wacc": 0.095}
        paths_a = extract_field_paths(payload_a)
        paths_b = extract_field_paths(payload_b)
        assert paths_a == paths_b, \
            f"Paths differ:\n  A: {paths_a}\n  B: {paths_b}"
        _pass("B1: same content, different key order → identical paths")

    def _b2():
        # Nested dicts with reordered keys
        payload_a = {
            "dcf": {"bear_case": {"fair_value": 150}, "base_case": {"fair_value": 200}},
            "rsi": 62.5,
        }
        payload_b = {
            "rsi": 62.5,
            "dcf": {"base_case": {"fair_value": 200}, "bear_case": {"fair_value": 150}},
        }
        paths_a = extract_field_paths(payload_a)
        paths_b = extract_field_paths(payload_b)
        assert paths_a == paths_b, \
            f"Paths differ:\n  A: {paths_a}\n  B: {paths_b}"
        _pass("B2: nested dicts with reordered keys → identical paths")

    def _b3():
        # Calling twice on same payload → identical output
        payload = _VALUATION_OUTPUTS
        assert extract_field_paths(payload) == extract_field_paths(payload), \
            "Same call twice should produce identical result"
        _pass("B3: idempotent — same payload same result")

    _run("B1", _b1)
    _run("B2", _b2)
    _run("B3", _b3)


# ===========================================================================
# Test Group C — extract_field_paths: max_paths limit
# ===========================================================================

def test_c():
    print("\n[C] extract_field_paths — max_paths limit")

    def _c1():
        # Many leaf paths — truncated to max_paths
        payload = {str(i): {str(j): j for j in range(10)} for i in range(10)}
        paths = extract_field_paths(payload, max_paths=5)
        assert len(paths) == 5, f"Expected 5 paths, got {len(paths)}"
        _pass("C1: max_paths=5 limits output to 5 paths")

    def _c2():
        # max_paths=0 → empty
        payload = {"a": 1, "b": 2}
        paths = extract_field_paths(payload, max_paths=0)
        assert paths == [], f"Expected [], got {paths}"
        _pass("C2: max_paths=0 returns empty list")

    def _c3():
        # max_paths larger than total paths → returns all
        payload = {"a": 1, "b": 2, "c": 3}
        paths = extract_field_paths(payload, max_paths=100)
        assert len(paths) == 3, f"Expected 3 paths, got {len(paths)}"
        _pass("C3: max_paths larger than total → returns all paths")

    def _c4():
        # Paths from full valuation outputs respect max_paths
        paths = extract_field_paths(_VALUATION_OUTPUTS, max_paths=3)
        assert len(paths) <= 3, f"Expected ≤3 paths, got {len(paths)}"
        _pass("C4: real valuation outputs respect max_paths=3")

    _run("C1", _c1)
    _run("C2", _c2)
    _run("C3", _c3)
    _run("C4", _c4)


# ===========================================================================
# Test Group D — build_evidence_packet: basic structure
# ===========================================================================

def test_d():
    print("\n[D] build_evidence_packet — basic structure")

    tr_val = _make_val_tr()
    tr_tech = _make_tech_tr()

    def _d1():
        packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val, tr_tech])
        assert "run_id" in packet
        assert "target_name" in packet
        assert "evidence_count" in packet
        assert "available_evidence" in packet
        _pass("D1: packet has required top-level keys")

    def _d2():
        packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val, tr_tech])
        assert packet["run_id"] == _RUN_ID
        assert packet["target_name"] == _TICKER
        assert packet["evidence_count"] == 2
        _pass("D2: run_id / target_name / evidence_count correct")

    def _d3():
        packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val, tr_tech])
        ae = packet["available_evidence"]
        assert len(ae) == 2, f"Expected 2 entries, got {len(ae)}"
        _pass("D3: available_evidence has 2 entries")

    def _d4():
        packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val])
        entry = packet["available_evidence"][0]
        assert "evidence_id" in entry
        assert "tool_name" in entry
        assert "output_keys" in entry
        assert "notable_field_paths" in entry
        _pass("D4: each entry has evidence_id / tool_name / output_keys / notable_field_paths")

    def _d5():
        packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val])
        entry = packet["available_evidence"][0]
        assert entry["evidence_id"] == tr_val.evidence_id
        assert entry["tool_name"] == "valuation_model"
        _pass("D5: evidence_id and tool_name match ToolResult")

    def _d6():
        packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val])
        entry = packet["available_evidence"][0]
        # output_keys should be sorted top-level keys of outputs
        expected_keys = sorted(_VALUATION_OUTPUTS.keys())
        assert entry["output_keys"] == expected_keys, \
            f"Expected {expected_keys}, got {entry['output_keys']}"
        _pass("D6: output_keys are sorted top-level keys")

    def _d7():
        packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val])
        entry = packet["available_evidence"][0]
        paths = entry["notable_field_paths"]
        assert "assumptions.wacc" in paths, \
            f"Expected 'assumptions.wacc' in {paths}"
        assert "dcf.base_case.fair_value" in paths, \
            f"Expected 'dcf.base_case.fair_value' in {paths}"
        _pass("D7: notable_field_paths contains expected nested paths")

    def _d8():
        # Empty tool_results list
        packet = build_evidence_packet(_RUN_ID, _TICKER, [])
        assert packet["evidence_count"] == 0
        assert packet["available_evidence"] == []
        _pass("D8: empty tool_results → evidence_count=0, available_evidence=[]")

    _run("D1", _d1)
    _run("D2", _d2)
    _run("D3", _d3)
    _run("D4", _d4)
    _run("D5", _d5)
    _run("D6", _d6)
    _run("D7", _d7)
    _run("D8", _d8)


# ===========================================================================
# Test Group E — build_evidence_packet: rejects invalid inputs
# ===========================================================================

def test_e():
    print("\n[E] build_evidence_packet — input validation")

    tr_val = _make_val_tr()

    def _e1():
        try:
            build_evidence_packet("", _TICKER, [tr_val])
            _fail("E1", "Expected ValueError for empty run_id")
        except ValueError:
            _pass("E1: empty run_id raises ValueError")

    def _e2():
        try:
            build_evidence_packet("   ", _TICKER, [tr_val])
            _fail("E2", "Expected ValueError for blank run_id")
        except ValueError:
            _pass("E2: blank run_id raises ValueError")

    def _e3():
        try:
            build_evidence_packet(_RUN_ID, "", [tr_val])
            _fail("E3", "Expected ValueError for empty target_name")
        except ValueError:
            _pass("E3: empty target_name raises ValueError")

    def _e4():
        try:
            build_evidence_packet(_RUN_ID, "   ", [tr_val])
            _fail("E4", "Expected ValueError for blank target_name")
        except ValueError:
            _pass("E4: blank target_name raises ValueError")

    def _e5():
        try:
            build_evidence_packet(_RUN_ID, _TICKER, "not a list")  # type: ignore
            _fail("E5", "Expected TypeError for non-list tool_results")
        except TypeError:
            _pass("E5: non-list tool_results raises TypeError")

    _run("E1", _e1)
    _run("E2", _e2)
    _run("E3", _e3)
    _run("E4", _e4)
    _run("E5", _e5)


# ===========================================================================
# Test Group F — build_evidence_packet: does not mutate ToolResult
# ===========================================================================

def test_f():
    print("\n[F] build_evidence_packet — does not mutate ToolResult outputs")

    def _f1():
        tr_val = _make_val_tr()
        original_outputs = dict(tr_val.outputs)  # shallow copy before call
        original_fair_value = tr_val.outputs.get("fair_value")

        build_evidence_packet(_RUN_ID, _TICKER, [tr_val])

        assert tr_val.outputs.get("fair_value") == original_fair_value, \
            "fair_value was mutated"
        assert tr_val.outputs == original_outputs, \
            "ToolResult.outputs was mutated"
        _pass("F1: ToolResult.outputs not mutated by build_evidence_packet")

    def _f2():
        tr_val = _make_val_tr()
        original_evidence_id = tr_val.evidence_id
        original_tool_name = tr_val.tool_name

        build_evidence_packet(_RUN_ID, _TICKER, [tr_val])

        assert tr_val.evidence_id == original_evidence_id, \
            "evidence_id was mutated"
        assert tr_val.tool_name == original_tool_name, \
            "tool_name was mutated"
        _pass("F2: ToolResult.evidence_id and tool_name not mutated")

    _run("F1", _f1)
    _run("F2", _f2)


# ===========================================================================
# Test Group G — build_agent_result_prompt: content and constraints
# ===========================================================================

def test_g():
    print("\n[G] build_agent_result_prompt — content checks")

    tr_val = _make_val_tr()
    tr_tech = _make_tech_tr()
    packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val, tr_tech])

    prompt = build_agent_result_prompt(
        agent_name="valuation_agent",
        run_id=_RUN_ID,
        target_name=_TICKER,
        task_instruction="Analyse DCF valuation and RSI momentum for ORCL.",
        evidence_packet=packet,
    )

    def _g1():
        assert isinstance(prompt, str), f"Expected str, got {type(prompt)}"
        assert len(prompt) > 200, "Prompt suspiciously short"
        _pass("G1: returns non-trivial string")

    def _g2():
        # Must mention AgentResult (schema requirement)
        assert "AgentResult" in prompt, "Missing 'AgentResult'"
        _pass("G2: prompt mentions AgentResult schema")

    def _g3():
        # Evidence-only rule
        lower = prompt.lower()
        assert "evidence" in lower, "Missing evidence-only constraint"
        _pass("G3: prompt includes evidence constraint")

    def _g4():
        # No fabrication rule
        assert "fabricate" in prompt.lower() or "invent" in prompt.lower() or \
               "NEVER" in prompt or "NOT" in prompt, \
            "Missing anti-fabrication rule"
        _pass("G4: prompt includes anti-fabrication rule")

    def _g5():
        # Numeric claims require EvidenceRef
        assert "EvidenceRef" in prompt, "Missing EvidenceRef requirement"
        _pass("G5: prompt requires EvidenceRef for numeric claims")

    def _g6():
        # JSON only / no markdown
        assert "markdown" in prompt.lower() or "JSON" in prompt, \
            "Missing JSON-only / no-markdown instruction"
        _pass("G6: prompt includes JSON-only / no-markdown rule")

    def _g7():
        # run_id embedded
        assert _RUN_ID in prompt, f"run_id {_RUN_ID!r} not in prompt"
        _pass("G7: run_id embedded verbatim in prompt")

    def _g8():
        # target_name embedded
        assert _TICKER in prompt, f"target_name {_TICKER!r} not in prompt"
        _pass("G8: target_name embedded in prompt")

    def _g9():
        # evidence_ids from packet embedded
        for entry in packet["available_evidence"]:
            eid = entry["evidence_id"]
            assert eid in prompt, f"evidence_id {eid!r} not found in prompt"
        _pass("G9: all evidence_ids from packet appear in prompt")

    def _g10():
        # Task instruction embedded
        assert "Analyse DCF valuation" in prompt, "Task instruction not in prompt"
        _pass("G10: task instruction embedded in prompt")

    def _g11():
        # Architecture principle
        assert "Deterministic computation" in prompt or \
               "deterministic" in prompt.lower(), \
            "Missing architecture principle"
        _pass("G11: architecture principle embedded")

    def _g12():
        # Insufficiency behavior instruction
        assert "insufficient" in prompt.lower() or "uncertainty" in prompt.lower(), \
            "Missing insufficiency behavior instruction"
        _pass("G12: insufficiency behavior described")

    _run("G1", _g1)
    _run("G2", _g2)
    _run("G3", _g3)
    _run("G4", _g4)
    _run("G5", _g5)
    _run("G6", _g6)
    _run("G7", _g7)
    _run("G8", _g8)
    _run("G9", _g9)
    _run("G10", _g10)
    _run("G11", _g11)
    _run("G12", _g12)


# ===========================================================================
# Test Group G2 — build_agent_result_prompt: deterministic
# ===========================================================================

def test_g2():
    print("\n[G2] build_agent_result_prompt — deterministic output")

    tr_val = _make_val_tr()
    packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val])

    kwargs = dict(
        agent_name="valuation_agent",
        run_id=_RUN_ID,
        target_name=_TICKER,
        task_instruction="Analyse valuation for ORCL.",
        evidence_packet=packet,
    )

    def _g2a():
        prompt1 = build_agent_result_prompt(**kwargs)
        prompt2 = build_agent_result_prompt(**kwargs)
        assert prompt1 == prompt2, "Prompt is not deterministic"
        _pass("G2a: same inputs → identical prompt (deterministic)")

    def _g2b():
        # Different task instruction → different prompt
        prompt1 = build_agent_result_prompt(**kwargs)
        prompt2 = build_agent_result_prompt(
            **{**kwargs, "task_instruction": "A completely different task."}
        )
        assert prompt1 != prompt2, "Different task_instruction should produce different prompt"
        _pass("G2b: different task_instruction → different prompt")

    def _g2c():
        # Different run_id → different prompt
        prompt1 = build_agent_result_prompt(**kwargs)
        prompt2 = build_agent_result_prompt(**{**kwargs, "run_id": "ORCL_different_run"})
        assert prompt1 != prompt2, "Different run_id should produce different prompt"
        _pass("G2c: different run_id → different prompt")

    _run("G2a", _g2a)
    _run("G2b", _g2b)
    _run("G2c", _g2c)


# ===========================================================================
# Test Group H — build_agent_result_prompt: rejects empty/blank inputs
# ===========================================================================

def test_h():
    print("\n[H] build_agent_result_prompt — input validation")

    tr_val = _make_val_tr()
    packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val])

    def _try_build(**override):
        base = dict(
            agent_name="valuation_agent",
            run_id=_RUN_ID,
            target_name=_TICKER,
            task_instruction="Analyse ORCL.",
            evidence_packet=packet,
        )
        return build_agent_result_prompt(**{**base, **override})

    def _h1():
        try:
            _try_build(agent_name="")
            _fail("H1", "Expected ValueError for empty agent_name")
        except ValueError:
            _pass("H1: empty agent_name raises ValueError")

    def _h2():
        try:
            _try_build(agent_name="   ")
            _fail("H2", "Expected ValueError for blank agent_name")
        except ValueError:
            _pass("H2: blank agent_name raises ValueError")

    def _h3():
        try:
            _try_build(run_id="")
            _fail("H3", "Expected ValueError for empty run_id")
        except ValueError:
            _pass("H3: empty run_id raises ValueError")

    def _h4():
        try:
            _try_build(target_name="")
            _fail("H4", "Expected ValueError for empty target_name")
        except ValueError:
            _pass("H4: empty target_name raises ValueError")

    def _h5():
        try:
            _try_build(task_instruction="")
            _fail("H5", "Expected ValueError for empty task_instruction")
        except ValueError:
            _pass("H5: empty task_instruction raises ValueError")

    def _h6():
        try:
            _try_build(task_instruction="   ")
            _fail("H6", "Expected ValueError for blank task_instruction")
        except ValueError:
            _pass("H6: blank task_instruction raises ValueError")

    _run("H1", _h1)
    _run("H2", _h2)
    _run("H3", _h3)
    _run("H4", _h4)
    _run("H5", _h5)
    _run("H6", _h6)


# ===========================================================================
# Test Group I — build_schema_summary: key constraints present
# ===========================================================================

def test_i():
    print("\n[I] build_schema_summary — key constraints present")

    summary = build_schema_summary()

    def _i1():
        assert isinstance(summary, dict), f"Expected dict, got {type(summary)}"
        _pass("I1: returns a dict")

    def _i2():
        # Required agent_name / run_id
        required = summary.get("required_fields", {})
        assert "agent_name" in required, "Missing agent_name in required_fields"
        assert "run_id" in required, "Missing run_id in required_fields"
        _pass("I2: required_fields contains agent_name and run_id")

    def _i3():
        # Confidence score constraint
        confidence = summary.get("AgentConfidence", {})
        score_info = confidence.get("score", "")
        assert "0.0" in str(score_info) and "1.0" in str(score_info), \
            f"Expected [0.0, 1.0] constraint in score field, got: {score_info!r}"
        _pass("I3: AgentConfidence.score constraint [0.0, 1.0] present")

    def _i4():
        # EvidenceRef metadata fields
        eref = summary.get("EvidenceRef", {})
        assert "evidence_id" in eref, "Missing evidence_id in EvidenceRef"
        assert "tool_name" in eref, "Missing tool_name in EvidenceRef"
        assert "metric" in eref, "Missing metric in EvidenceRef"
        assert "field_path" in eref, "Missing field_path in EvidenceRef"
        _pass("I4: EvidenceRef binding fields described")

    def _i5():
        # Severity allowed values
        risk = summary.get("Risk", {})
        severity_info = risk.get("severity", "")
        assert "low" in str(severity_info) and "medium" in str(severity_info) \
               and "high" in str(severity_info), \
            f"Expected low/medium/high in severity, got: {severity_info!r}"
        _pass("I5: Risk.severity allowed values (low/medium/high) present")

    def _i6():
        # Assumption.source allowed values
        assumption = summary.get("Assumption", {})
        source_info = assumption.get("source", "")
        for val in ("tool", "user", "agent", "default"):
            assert val in str(source_info), \
                f"Missing source value {val!r} in: {source_info!r}"
        _pass("I6: Assumption.source allowed values present")

    def _i7():
        # Assumption.sensitivity allowed values
        assumption = summary.get("Assumption", {})
        sens_info = assumption.get("sensitivity", "")
        for val in ("low", "medium", "high"):
            assert val in str(sens_info), \
                f"Missing sensitivity value {val!r} in: {sens_info!r}"
        _pass("I7: Assumption.sensitivity allowed values present")

    def _i8():
        # Is JSON-serializable (can be embedded in prompt)
        serialized = json.dumps(summary, sort_keys=True)
        reloaded = json.loads(serialized)
        assert isinstance(reloaded, dict)
        _pass("I8: schema summary is JSON-serializable")

    _run("I1", _i1)
    _run("I2", _i2)
    _run("I3", _i3)
    _run("I4", _i4)
    _run("I5", _i5)
    _run("I6", _i6)
    _run("I7", _i7)
    _run("I8", _i8)


# ===========================================================================
# Test Group J — Prompt contract supports parser/validator roundtrip
# ===========================================================================

def test_j():
    print("\n[J] Prompt contract → parser/validator roundtrip (mock response)")

    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=tmp)
        tr_val = _make_val_tr()
        tr_tech = _make_tech_tr()
        val_eid = store.add_tool_result(tr_val)
        tech_eid = store.add_tool_result(tr_tech)

        packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val, tr_tech])
        prompt = build_agent_result_prompt(
            agent_name="valuation_agent",
            run_id=_RUN_ID,
            target_name=_TICKER,
            task_instruction="Analyse valuation and momentum for ORCL.",
            evidence_packet=packet,
        )

        # Simulate a compliant LLM response using evidence IDs from the packet
        mock_response = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
            "ticker": _TICKER,
            "findings": [
                {
                    "text": "DCF fair value is $200.0, implying 11.1% upside.",
                    "confidence": 0.85,
                    "evidence": [
                        {
                            "evidence_id": val_eid,
                            "tool_name": "valuation_model",
                            "metric": "fair_value",
                            "description": "Base DCF fair value",
                        }
                    ],
                },
                {
                    "text": "RSI of 62.5 signals building momentum.",
                    "confidence": 0.80,
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
                    "rationale": "9.5% WACC from valuation model.",
                    "value": "0.095",
                    "source": "tool",
                    "sensitivity": "high",
                }
            ],
            "risks": [
                {
                    "name": "Rate risk",
                    "description": "WACC sensitivity at 9.5%.",
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
                "level": "medium",
                "rationale": "Evidence-backed; macro uncertainty remains.",
                "score": 0.78,
            },
        }

        def _j1():
            assert isinstance(prompt, str) and len(prompt) > 100
            _pass("J1: prompt built successfully from evidence packet")

        def _j2():
            ar = parse_agent_result_json(mock_response)
            assert ar.agent_name == "valuation_agent"
            assert ar.run_id == _RUN_ID
            _pass("J2: mock response parses into AgentResult")

        def _j3():
            ar = parse_agent_result_json(mock_response)
            report = validate_agent_result(ar, store)
            assert report.passed, f"Expected passed=True, issues={report.issues}"
            _pass("J3: validation passes for compliant mock response")

        def _j4():
            ar = parse_agent_result_json(mock_response)
            report = validate_agent_result(ar, store)
            errors = [i for i in report.issues if i.severity == "error"]
            assert not errors, f"Unexpected errors: {errors}"
            _pass("J4: no error-severity issues for compliant mock response")

        def _j5():
            # JSON roundtrip: serialize mock response as string, re-parse
            raw_str = json.dumps(mock_response)
            ar = parse_agent_result_json(raw_str)
            report = validate_agent_result(ar, store)
            assert report.passed
            _pass("J5: JSON string roundtrip also passes validation")

        _run("J1", _j1)
        _run("J2", _j2)
        _run("J3", _j3)
        _run("J4", _j4)
        _run("J5", _j5)


# ===========================================================================
# Test Group K — Validator catches unsupported numeric claim
# ===========================================================================

def test_k():
    print("\n[K] Prompt contract catches unsupported numeric claim via validator")

    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=tmp)
        tr_val = _make_val_tr()
        store.add_tool_result(tr_val)

        # Mock response: numeric claim with no evidence refs
        mock_response = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
            "findings": [
                {
                    "text": "The intrinsic value is $215 based on my analysis.",
                    "evidence": [],  # empty — violates contract rule 2
                }
            ],
        }

        def _k1():
            ar = parse_agent_result_json(mock_response)
            assert ar is not None
            _pass("K1: parse succeeds even with missing evidence (schema is valid)")

        def _k2():
            ar = parse_agent_result_json(mock_response)
            report = validate_agent_result(ar, store)
            assert not report.passed, "Expected passed=False"
            _pass("K2: validation fails (passed=False)")

        def _k3():
            ar = parse_agent_result_json(mock_response)
            report = validate_agent_result(ar, store)
            codes = [i.code for i in report.issues]
            assert "UNSUPPORTED_NUMERIC_CLAIM" in codes, \
                f"Expected UNSUPPORTED_NUMERIC_CLAIM in {codes}"
            _pass("K3: UNSUPPORTED_NUMERIC_CLAIM reported")

        _run("K1", _k1)
        _run("K2", _k2)
        _run("K3", _k3)


# ===========================================================================
# Test Group L — Validator catches fabricated evidence_id
# ===========================================================================

def test_l():
    print("\n[L] Prompt contract catches fabricated evidence_id via validator")

    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceStore(run_dir=tmp)
        tr_val = _make_val_tr()
        store.add_tool_result(tr_val)

        # Mock response: uses an evidence_id not in the store
        mock_response = {
            "agent_name": "valuation_agent",
            "run_id": _RUN_ID,
            "findings": [
                {
                    "text": "DCF fair value is $200.",
                    "evidence": [
                        {
                            "evidence_id": "completely_fabricated_id_not_in_store",
                            "tool_name": "valuation_model",
                            "metric": "fair_value",
                        }
                    ],
                }
            ],
        }

        def _l1():
            ar = parse_agent_result_json(mock_response)
            assert ar is not None
            _pass("L1: parse succeeds (fabricated ID is structurally valid)")

        def _l2():
            ar = parse_agent_result_json(mock_response)
            report = validate_agent_result(ar, store)
            assert not report.passed, "Expected passed=False"
            _pass("L2: validation fails (passed=False)")

        def _l3():
            ar = parse_agent_result_json(mock_response)
            report = validate_agent_result(ar, store)
            codes = [i.code for i in report.issues]
            assert "INVALID_EVIDENCE_ID" in codes, \
                f"Expected INVALID_EVIDENCE_ID in {codes}"
            _pass("L3: INVALID_EVIDENCE_ID reported for fabricated evidence_id")

        _run("L1", _l1)
        _run("L2", _l2)
        _run("L3", _l3)


# ===========================================================================
# Test Group M — build_repair_prompt (optional)
# ===========================================================================

def test_m():
    print("\n[M] build_repair_prompt — content checks")

    tr_val = _make_val_tr()
    packet = build_evidence_packet(_RUN_ID, _TICKER, [tr_val])
    original_prompt = build_agent_result_prompt(
        agent_name="valuation_agent",
        run_id=_RUN_ID,
        target_name=_TICKER,
        task_instruction="Analyse valuation for ORCL.",
        evidence_packet=packet,
    )

    validation_errors = [
        "UNSUPPORTED_NUMERIC_CLAIM: finding[0] numeric claim with no evidence refs",
        "INVALID_EVIDENCE_ID: evidence_id 'made_up_id' not found in store",
    ]
    invalid_output = '{"agent_name": "valuation_agent", "run_id": "' + _RUN_ID + '"}'

    def _m1():
        repair = build_repair_prompt(invalid_output, validation_errors, original_prompt)
        assert isinstance(repair, str) and len(repair) > 100
        _pass("M1: returns non-trivial repair prompt string")

    def _m2():
        repair = build_repair_prompt(invalid_output, validation_errors, original_prompt)
        assert "UNSUPPORTED_NUMERIC_CLAIM" in repair, \
            "Validation error not embedded in repair prompt"
        assert "INVALID_EVIDENCE_ID" in repair, \
            "Second validation error not embedded in repair prompt"
        _pass("M2: validation errors embedded in repair prompt")

    def _m3():
        repair = build_repair_prompt(invalid_output, validation_errors, original_prompt)
        # Must prohibit inventing evidence
        lower = repair.lower()
        assert "fabricat" in lower or "invent" in lower or "NOT" in repair, \
            "Missing prohibition on inventing/fabricating evidence"
        _pass("M3: repair prompt prohibits inventing evidence")

    def _m4():
        repair = build_repair_prompt(invalid_output, validation_errors, original_prompt)
        # Must demand JSON only
        assert "JSON" in repair or "json" in repair.lower(), \
            "Missing JSON-only demand in repair prompt"
        _pass("M4: repair prompt demands JSON-only output")

    def _m5():
        # Empty validation_errors → ValueError
        try:
            build_repair_prompt(invalid_output, [], original_prompt)
            _fail("M5", "Expected ValueError for empty validation_errors")
        except ValueError:
            _pass("M5: empty validation_errors raises ValueError")

    def _m6():
        # Non-list validation_errors → ValueError
        try:
            build_repair_prompt(invalid_output, "not a list", original_prompt)  # type: ignore
            _fail("M6", "Expected ValueError for non-list validation_errors")
        except ValueError:
            _pass("M6: non-list validation_errors raises ValueError")

    _run("M1", _m1)
    _run("M2", _m2)
    _run("M3", _m3)
    _run("M4", _m4)
    _run("M5", _m5)
    _run("M6", _m6)


# ===========================================================================
# Test Group N — Integration: evidence packet from real create_run_context
# ===========================================================================

def test_n():
    print("\n[N] Integration — evidence packet with create_run_context")

    with tempfile.TemporaryDirectory() as base_dir:
        ctx = create_run_context(ticker=_TICKER, task="phase1e_test", base_dir=base_dir)
        store = EvidenceStore(run_dir=ctx.run_dir)

        tr_val = valuation_tool_result(
            run_id=ctx.run_id,
            target=_TICKER,
            metric_group="dcf",
            outputs=_VALUATION_OUTPUTS,
            metadata={"description": "Phase 1E valuation evidence"},
        )
        tr_tech = technical_tool_result(
            run_id=ctx.run_id,
            target=_TICKER,
            metric_group="rsi_macd",
            outputs=_TECHNICAL_OUTPUTS,
        )
        tr_scan = scanner_tool_result(
            run_id=ctx.run_id,
            target="market",
            metric_group="stock_scanner",
            outputs=_SCANNER_OUTPUTS,
        )

        val_eid = store.add_tool_result(tr_val)
        tech_eid = store.add_tool_result(tr_tech)
        scan_eid = store.add_tool_result(tr_scan)

        packet = build_evidence_packet(
            ctx.run_id, _TICKER, [tr_val, tr_tech, tr_scan]
        )

        def _n1():
            assert packet["run_id"] == ctx.run_id
            assert packet["evidence_count"] == 3
            _pass("N1: packet built with 3 ToolResults from RunContext")

        def _n2():
            eids_in_packet = {e["evidence_id"] for e in packet["available_evidence"]}
            assert val_eid in eids_in_packet
            assert tech_eid in eids_in_packet
            assert scan_eid in eids_in_packet
            _pass("N2: all three evidence_ids in packet")

        def _n3():
            prompt = build_agent_result_prompt(
                agent_name="integrated_agent",
                run_id=ctx.run_id,
                target_name=_TICKER,
                task_instruction="Comprehensive analysis of ORCL.",
                evidence_packet=packet,
            )
            assert ctx.run_id in prompt
            assert val_eid in prompt
            assert tech_eid in prompt
            _pass("N3: prompt embeds run_id and all evidence_ids")

        def _n4():
            # Build a mock response using the RunContext run_id
            mock = {
                "agent_name": "integrated_agent",
                "run_id": ctx.run_id,
                "ticker": _TICKER,
                "findings": [
                    {
                        "text": "DCF fair value is $200.0.",
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
            ar = parse_agent_result_json(mock)
            report = validate_agent_result(ar, store)
            assert report.passed, f"Expected passed=True, issues={report.issues}"
            _pass("N4: full pipeline (RunContext → packet → prompt → parse → validate) passes")

        _run("N1", _n1)
        _run("N2", _n2)
        _run("N3", _n3)
        _run("N4", _n4)


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    print("=" * 62)
    print("Phase 1E: Prompt Contract Drafting — test suite")
    print("=" * 62)

    test_a()
    test_b()
    test_c()
    test_d()
    test_e()
    test_f()
    test_g()
    test_g2()
    test_h()
    test_i()
    test_j()
    test_k()
    test_l()
    test_m()
    test_n()

    print("\n" + "=" * 62)
    print(f"Results: {_PASSED} passed, {_FAILED} failed")
    print("=" * 62)
    sys.exit(0 if _FAILED == 0 else 1)
