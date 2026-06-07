"""
lib/reliability/agent_output.py

Pure helper functions for parsing structured LLM-like JSON into AgentResult
and optionally validating it against an EvidenceStore.

Design principles:
  - No Streamlit imports.
  - No Claude API calls.
  - No imports from lib/llm_orchestrator.py.
  - parse_agent_result_json() and validate_agent_result() are intentionally
    kept separate: schema parsing proves the JSON is well-formed; evidence
    validation proves the claims are backed by deterministic ToolResult data.
  - The parser never fabricates evidence IDs, never creates fake findings, and
    never silently drops fields that would otherwise cause validation errors.

See docs/reliability_phase_1d_agent_result_contract.md for the design rationale.
"""

import json
from typing import Any

from pydantic import ValidationError

from lib.reliability.evidence_store import EvidenceStore
from lib.reliability.schemas import AgentResult, ValidationReport
from lib.reliability.validators import validate_agent_result as _validate


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_agent_result_json(raw: "str | dict") -> AgentResult:
    """
    Parse a raw JSON string or dict into an AgentResult.

    Parsing is intentionally separated from evidence validation — this
    function only proves the JSON conforms to the AgentResult schema.
    Call ``validate_agent_result()`` (or ``parse_and_validate_agent_result()``)
    separately to check evidence binding.

    Args:
        raw: A JSON-encoded string or a plain Python dict.

    Returns:
        A validated ``AgentResult`` instance.

    Raises:
        TypeError:  If ``raw`` is neither a ``str`` nor a ``dict`` (e.g., list,
                    int, None).
        ValueError: If ``raw`` is a string that is not valid JSON.
        ValueError: If the decoded dict does not conform to the AgentResult
                    schema (missing required fields, extra fields, wrong types).

    Examples::

        # From a dict
        ar = parse_agent_result_json({
            "agent_name": "valuation_agent",
            "run_id": "ORCL_20260521_abcd",
            "findings": [{
                "text": "DCF fair value is $200.",
                "evidence": [{"evidence_id": "...", "metric": "fair_value"}],
            }],
        })

        # From a JSON string
        ar = parse_agent_result_json(json.dumps({...}))
    """
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Malformed JSON string — could not decode: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ValueError(
                f"JSON string must decode to an object (dict), "
                f"got {type(data).__name__!r}."
            )
    elif isinstance(raw, dict):
        data = raw
    else:
        raise TypeError(
            f"Expected a JSON string or dict, got {type(raw).__name__!r}. "
            "Pass a JSON-encoded string or a plain Python dict."
        )

    try:
        return AgentResult.model_validate(data)
    except ValidationError as exc:
        raise ValueError(
            f"AgentResult schema validation failed:\n{exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Parse-then-validate convenience
# ---------------------------------------------------------------------------

def parse_and_validate_agent_result(
    raw: "str | dict",
    evidence_store: EvidenceStore,
) -> "tuple[AgentResult, ValidationReport]":
    """
    Parse raw JSON into AgentResult, then validate against an EvidenceStore.

    This is a two-step convenience wrapper:
      1. ``parse_agent_result_json(raw)`` — schema validation only.
      2. ``validate_agent_result(agent_result, evidence_store)`` — evidence
         existence and numeric binding validation.

    Returns:
        ``(AgentResult, ValidationReport)`` — both objects regardless of
        whether validation passes or not.

    Does not persist any files. Does not call LLMs.

    Raises:
        TypeError / ValueError: on parse failure (propagated from
        ``parse_agent_result_json``).
    """
    agent_result = parse_agent_result_json(raw)
    report = _validate(agent_result, evidence_store)
    return agent_result, report


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

def agent_result_to_json(agent_result: AgentResult) -> str:
    """
    Serialize an AgentResult to a JSON string.

    Uses Pydantic's ``model_dump_json()`` for consistent, schema-aware
    serialization.  The result can be passed back to
    ``parse_agent_result_json()`` for a lossless round-trip.

    No side effects — does not write files or call external services.
    """
    return agent_result.model_dump_json()
