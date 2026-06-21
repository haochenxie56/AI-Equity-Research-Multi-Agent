"""
scripts/test_agent_framework_foundation.py

Phase 8A — Agent Framework Foundation tests.

Run from repo root:
    pytest scripts/test_agent_framework_foundation.py -v

Tests that do not make real LLM calls mock
``lib.agent_framework.agent_runner._call_llm``. ANTHROPIC_API_KEY is set to a
dummy value so nothing accidentally depends on a real key (the client is
never instantiated because the LLM call is mocked).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# Make the repo root importable when pytest is run from anywhere.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from lib.agent_framework.agent_output import (
    AgentOutput,
    agent_output_from_dict,
    agent_output_to_dict,
    agent_result_to_agent_output,
    append_agent_output,
    load_agent_outputs,
)
from lib.agent_framework import agent_runner
from lib.agent_framework.agent_runner import run_llm_agent
from lib.agent_framework.world_adapter import (
    llm_output_to_tool_result,
    processed_signals_to_tool_result,
)
from lib.reliability.schemas import (
    AgentConfidence,
    AgentResult,
    EvidenceRef,
    Finding,
)
from lib.reliability.agent_output import agent_result_to_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_eref(evidence_id: str = "ev_test_1") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        tool_name="classify_regime",
        metric="regime",
        excerpt="risk_on",
        description="test evidence",
    )


def _make_agent_output(
    *,
    agent_id: str = "TestAgent",
    timestamp: str = "2026-06-19T12:00:00+00:00",
    evidence_id: str = "ev_test_1",
) -> AgentOutput:
    return AgentOutput(
        agent_id=agent_id,
        timestamp=timestamp,
        horizon="cross",
        judgment="Macro signals favor defensive positioning over cyclical exposure.",
        confidence=0.6,
        evidence_refs=[_make_eref(evidence_id)],
        supporting_data={"regime": "risk_on", "score": 0.8},
        requires_human_confirmation=True,
        judgment_source="llm_proposed",
        valid_until="2026-06-19T23:59:59+00:00",
        agent_result=None,
        debate_report=None,
    )


# ---------------------------------------------------------------------------
# §8A.1 — AgentOutput round-trip serialization
# ---------------------------------------------------------------------------

def test_8A_1_agent_output_roundtrip():
    ao = _make_agent_output()
    d = agent_output_to_dict(ao)
    # dict must be JSON-serializable
    json.dumps(d)

    restored = agent_output_from_dict(d)

    assert restored.agent_id == ao.agent_id
    assert restored.timestamp == ao.timestamp
    assert restored.horizon == ao.horizon
    assert restored.judgment == ao.judgment
    assert restored.confidence == ao.confidence
    assert restored.supporting_data == ao.supporting_data
    assert restored.requires_human_confirmation == ao.requires_human_confirmation
    assert restored.judgment_source == ao.judgment_source
    assert restored.valid_until == ao.valid_until
    # EvidenceRef survives the round-trip
    assert len(restored.evidence_refs) == 1
    assert restored.evidence_refs[0].evidence_id == ao.evidence_refs[0].evidence_id
    assert restored.evidence_refs[0].tool_name == ao.evidence_refs[0].tool_name
    assert restored.evidence_refs[0].metric == ao.evidence_refs[0].metric
    assert isinstance(restored.evidence_refs[0], EvidenceRef)


# ---------------------------------------------------------------------------
# §8A.2 — validate_judgment blocks numeric content
# ---------------------------------------------------------------------------

def test_8A_2_validate_judgment_blocks_numeric():
    bad = AgentOutput.validate_judgment("VIX at 21 suggests caution")
    assert bad, "expected violations for numeric/metric judgment"

    clean = AgentOutput.validate_judgment(
        "Macro signals favor defensive positioning"
    )
    assert clean == [], f"expected no violations, got {clean}"


# ---------------------------------------------------------------------------
# §8A.3 — agent_result_to_agent_output flattens evidence_refs
# ---------------------------------------------------------------------------

def test_8A_3_mapper_flattens_evidence_refs():
    ar = AgentResult(
        agent_name="TestAgent",
        run_id="RUN_8A3",
        findings=[
            Finding(text="First finding.", evidence=[_make_eref("ev_a")]),
            Finding(text="Second finding.", evidence=[_make_eref("ev_b")]),
        ],
        confidence=AgentConfidence(level="medium", rationale="ok", score=0.6),
    )
    ao = agent_result_to_agent_output(
        ar,
        horizon="cross",
        judgment="Signals favor a defensive posture.",
        requires_human_confirmation=True,
        judgment_source="llm_proposed",
        valid_until="2026-06-19T23:59:59+00:00",
    )
    assert len(ao.evidence_refs) == 2
    assert {r.evidence_id for r in ao.evidence_refs} == {"ev_a", "ev_b"}


# ---------------------------------------------------------------------------
# §8A.4 — agent_result_to_agent_output raises on empty evidence_refs
# ---------------------------------------------------------------------------

def test_8A_4_mapper_raises_on_empty_evidence():
    ar = AgentResult(
        agent_name="TestAgent",
        run_id="RUN_8A4",
        findings=[Finding(text="A claim with no evidence.", evidence=[])],
    )
    with pytest.raises(ValueError):
        agent_result_to_agent_output(
            ar,
            horizon="cross",
            judgment="A clean judgment sentence.",
            requires_human_confirmation=True,
            judgment_source="llm_proposed",
            valid_until="2026-06-19T23:59:59+00:00",
        )


# ---------------------------------------------------------------------------
# §8A.5 — append_agent_output writes to correct path
# ---------------------------------------------------------------------------

def test_8A_5_append_writes_correct_path(tmp_path):
    ao = _make_agent_output(agent_id="WriteAgent")
    path = append_agent_output(ao, base_dir=str(tmp_path))

    expected = tmp_path / "WriteAgent" / "2026-06-19.jsonl"
    assert expected.exists(), f"expected file at {expected}, runner returned {path!r}"
    assert Path(path) == expected

    lines = expected.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])  # valid JSON
    assert obj["agent_id"] == "WriteAgent"


# ---------------------------------------------------------------------------
# §8A.6 — load_agent_outputs round-trips via JSONL
# ---------------------------------------------------------------------------

def test_8A_6_load_roundtrips(tmp_path):
    ao_late = _make_agent_output(
        agent_id="LoadAgent", timestamp="2026-06-19T10:00:00+00:00"
    )
    ao_early = _make_agent_output(
        agent_id="LoadAgent", timestamp="2026-06-19T09:00:00+00:00"
    )
    # Append out of order to prove load sorts ascending by timestamp.
    append_agent_output(ao_late, base_dir=str(tmp_path))
    append_agent_output(ao_early, base_dir=str(tmp_path))

    loaded = load_agent_outputs("LoadAgent", base_dir=str(tmp_path))
    assert len(loaded) == 2
    assert loaded[0].timestamp == "2026-06-19T09:00:00+00:00"
    assert loaded[1].timestamp == "2026-06-19T10:00:00+00:00"
    assert loaded[0].evidence_refs[0].evidence_id == "ev_test_1"


# ---------------------------------------------------------------------------
# §8A.7 — llm_output_to_tool_result wraps correctly
# ---------------------------------------------------------------------------

def test_8A_7_llm_output_to_tool_result():
    output_dict = {"regime": "risk_on", "score": 0.8}
    tr = llm_output_to_tool_result(
        output_dict,
        run_id="RUN_8A7",
        tool_name="analyze_macro_regime",
        target="MACRO",
        metric_group="regime_classification",
    )
    assert tr.evidence_id  # non-empty
    assert tr.tool_name == "analyze_macro_regime"
    assert tr.outputs == output_dict
    assert tr.run_id == "RUN_8A7"


# ---------------------------------------------------------------------------
# §8A.8 — run_llm_agent returns fallback on LLM failure
# ---------------------------------------------------------------------------

def test_8A_8_run_llm_agent_fallback_on_failure(monkeypatch, tmp_path):
    def _boom(system, user, max_tokens):
        raise RuntimeError("simulated LLM transport failure")

    monkeypatch.setattr(agent_runner, "_call_llm", _boom)
    # Keep persistence hermetic.
    monkeypatch.setattr(agent_runner, "append_agent_output", lambda ao: "")

    tr = processed_signals_to_tool_result(
        {"regime": "risk_off", "risk_level": "high", "signals": {"trend": "down"}},
        run_id="RUN_8A8",
        tool_name="classify_regime",
        target="MACRO",
        metric_group="regime_classification",
    )

    ao = run_llm_agent(
        agent_id="MacroRegimeAgent",
        horizon="cross",
        task_instruction="Synthesize the macro regime for the PM layer.",
        tool_results=[tr],
        supporting_data={"regime": "risk_off"},
        requires_human_confirmation=False,
        valid_until="2026-06-19T23:59:59+00:00",
        run_id="RUN_8A8",
    )

    assert ao.judgment_source == "rule_based"
    assert ao.requires_human_confirmation is True
    assert ao.evidence_refs, "fallback must carry a synthetic evidence ref"


# ---------------------------------------------------------------------------
# §8A.9 — run_llm_agent produces valid AgentOutput on mocked LLM
# ---------------------------------------------------------------------------

def test_8A_9_run_llm_agent_valid_output(monkeypatch, tmp_path):
    run_id = "RUN_8A9"
    signals = {"regime": "risk_on", "risk_level": "low", "signals": {"breadth": "wide"}}
    tr = processed_signals_to_tool_result(
        signals,
        run_id=run_id,
        tool_name="classify_regime",
        target="MACRO",
        metric_group="regime_classification",
    )
    eid = tr.evidence_id

    agent_result = AgentResult(
        agent_name="MacroRegimeAgent",
        run_id=run_id,
        ticker=None,
        findings=[
            Finding(
                text="Macro signals favor defensive positioning over cyclical exposure near term.",
                evidence=[EvidenceRef(evidence_id=eid, tool_name="classify_regime")],
            ),
            Finding(
                text="The regime classification supports a constructive but selective stance.",
                evidence=[EvidenceRef(evidence_id=eid, tool_name="classify_regime")],
            ),
        ],
        confidence=AgentConfidence(level="medium", rationale="signals align", score=0.62),
    )
    llm_json = agent_result_to_json(agent_result)

    monkeypatch.setattr(
        agent_runner, "_call_llm", lambda system, user, max_tokens: llm_json
    )
    monkeypatch.setattr(agent_runner, "append_agent_output", lambda ao: "")

    ao = run_llm_agent(
        agent_id="MacroRegimeAgent",
        horizon="cross",
        task_instruction="Synthesize the macro regime for the PM layer.",
        tool_results=[tr],
        supporting_data=dict(signals),
        requires_human_confirmation=False,
        valid_until="2026-06-19T23:59:59+00:00",
        run_id=run_id,
    )

    assert ao.evidence_refs, "expected non-empty evidence_refs"
    assert len(ao.evidence_refs) == 2
    assert ao.agent_id == "MacroRegimeAgent"
    assert ao.judgment.strip() != ""
    assert AgentOutput.validate_judgment(ao.judgment) == []


# ---------------------------------------------------------------------------
# §8A.10 — import guard: agent_framework does not load lib.reliability root
# ---------------------------------------------------------------------------

def test_8A_10_import_guard_no_reliability_root():
    script = (
        "import sys\n"
        "import lib.agent_framework.agent_output\n"
        "import lib.agent_framework.agent_runner\n"
        "import lib.agent_framework.world_adapter\n"
        "bad = [k for k in sys.modules if k == 'lib.reliability']\n"
        "assert not bad, f'lib.reliability eagerly loaded: {bad}'\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"import guard failed:\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}"
    )
    assert "OK" in proc.stdout


# ---------------------------------------------------------------------------
# §8A.11 — processed_signals_to_tool_result accepts a dataclass input
# ---------------------------------------------------------------------------

@dataclass
class FakeRegimeResult:
    regime: str = "risk_on"
    risk_level: str = "elevated"
    score: float = 0.72


def test_8A_11_processed_signals_accepts_dataclass():
    tr = processed_signals_to_tool_result(
        FakeRegimeResult(),
        run_id="r1",
        tool_name="classify_regime",
        target="MACRO",
        metric_group="regime_classification",
    )
    # Type check without importing lib.reliability at top level of this section.
    assert tr.__class__.__name__ == "ToolResult"
    assert tr.outputs["regime"] == "risk_on"
    assert tr.outputs["risk_level"] == "elevated"
    assert tr.outputs["score"] == 0.72


# ---------------------------------------------------------------------------
# §8A.12 — repair: flat text/evidence wrapped into findings
# ---------------------------------------------------------------------------

def test_8A_12_repair_wraps_flat_text_evidence():
    data = {"text": "Buy tech.", "evidence": [], "confidence": 0.8}
    result = agent_runner._repair_llm_response(
        data, run_id="r1", agent_id="TestAgent"
    )
    assert result["findings"] == [{"text": "Buy tech.", "evidence": []}]
    assert "text" not in result  # moved into findings
    assert "evidence" not in result  # moved into findings
    assert result["agent_name"] == "TestAgent"
    assert isinstance(result["confidence"], dict)
    assert result["confidence"]["score"] == 0.8


# ---------------------------------------------------------------------------
# §8A.13 — repair: existing findings array is preserved unchanged
# ---------------------------------------------------------------------------

def test_8A_13_repair_preserves_existing_findings():
    data = {
        "findings": [{"text": "Hold.", "evidence": []}],
        "agent_name": "X",
        "run_id": "r1",
        "confidence": {"level": "high", "rationale": "ok", "score": 0.9},
    }
    result = agent_runner._repair_llm_response(data, run_id="r1", agent_id="X")
    assert result["findings"] == [{"text": "Hold.", "evidence": []}]
    # confidence is already an object — must NOT be re-coerced.
    assert result["confidence"]["score"] == 0.9
    assert result["confidence"]["rationale"] == "ok"

    # DISCRIMINATING CHECK: a float confidence DOES get coerced to a dict.
    data_float = dict(data)
    data_float["confidence"] = 0.9
    result_float = agent_runner._repair_llm_response(
        data_float, run_id="r1", agent_id="X"
    )
    assert isinstance(result_float["confidence"], dict)
    assert result_float["confidence"]["score"] == 0.9


# ---------------------------------------------------------------------------
# §8A.14 — repair: agent_name and run_id injected when missing
# ---------------------------------------------------------------------------

def test_8A_14_repair_injects_agent_name_and_run_id():
    data = {
        "findings": [],
        "confidence": {"level": "low", "rationale": "x", "score": 0.3},
    }
    result = agent_runner._repair_llm_response(
        data, run_id="run-abc", agent_id="MyAgent"
    )
    assert result["agent_name"] == "MyAgent"
    assert result["run_id"] == "run-abc"

    # DISCRIMINATING CHECK: an existing agent_name is preserved, not overwritten.
    data_existing = {
        "findings": [],
        "agent_name": "Existing",
        "confidence": {"level": "low", "rationale": "x", "score": 0.3},
    }
    result_existing = agent_runner._repair_llm_response(
        data_existing, run_id="run-abc", agent_id="MyAgent"
    )
    assert result_existing["agent_name"] == "Existing"


# ---------------------------------------------------------------------------
# §8A.15 — end-to-end: flat LLM response flows through run_llm_agent
#          to a valid non-fallback AgentOutput
# ---------------------------------------------------------------------------

def test_8a_15_repair_wired_end_to_end(tmp_path):
    """
    Monkeypatch _call_llm to return a flat (unreformed) JSON response
    of the shape the LLM has been producing in production.
    Assert that run_llm_agent returns a non-fallback AgentOutput
    (judgment_source == "llm_proposed", agent_result not None).
    """
    import json
    from lib.agent_framework import agent_runner
    from lib.reliability.schemas import EvidenceRef
    from lib.agent_framework.world_adapter import processed_signals_to_tool_result

    # Build a minimal ToolResult so run_llm_agent has evidence to work with
    run_id = "TEST_20260101_000000_abcd1234"
    tr = processed_signals_to_tool_result(
        {"regime": "risk_on", "data_coverage": 0.8},
        run_id=run_id,
        tool_name="classify_regime",
        target="MACRO",
        metric_group="regime_classification",
    )

    # Use the REAL evidence_id from the ToolResult: a placeholder id is not in
    # the EvidenceStore, which is a severity=="error" binding issue that raises
    # AgentRunError (not a fallback). The real id keeps the end-to-end path on
    # the non-fallback branch this test asserts on.
    real_evidence_id = tr.evidence_id

    # The flat response shape the LLM has been producing
    flat_response = json.dumps({
        "text": "In the current risk-on regime, ShortTermPM should add "
                "exposure to cyclical sectors on pullbacks.",
        "evidence": [
            {
                "evidence_id": real_evidence_id,
                "excerpt": "regime: risk_on",
                "tool_name": "classify_regime",
                "metric": "regime",
                "field_path": "regime",
            }
        ],
        "confidence": 0.75,
    })

    # Monkeypatch _call_llm to return the flat response
    original = agent_runner._call_llm
    agent_runner._call_llm = lambda system, user, max_tokens: flat_response

    try:
        result = agent_runner.run_llm_agent(
            agent_id="MacroRegimeAgent",
            horizon="cross",
            task_instruction="Synthesize macro regime signals.",
            tool_results=[tr],
            supporting_data={"regime": "risk_on"},
            requires_human_confirmation=True,
            judgment_source="llm_proposed",
            valid_until="2026-12-31T23:59:59+00:00",
            run_id=run_id,
        )
    finally:
        agent_runner._call_llm = original

    assert result.judgment_source == "llm_proposed", (
        f"Expected llm_proposed, got {result.judgment_source}. "
        "Repair layer may not be wired correctly."
    )
    assert result.agent_result is not None, (
        "agent_result is None — repair did not produce a valid AgentResult."
    )
    assert len(result.evidence_refs) > 0, "evidence_refs must not be empty."


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
