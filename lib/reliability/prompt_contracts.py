"""
lib/reliability/prompt_contracts.py

Pure helper functions for building constrained prompt contracts and evidence
packets for future LLM agents that must output AgentResult-compatible JSON.

Design principles:
  - Pure functions only.  No Streamlit imports.  No Claude API calls.
  - No imports from lib/llm_orchestrator.py or .claude agents.
  - All functions are deterministic for the same inputs.
  - No file I/O.  No side effects.
  - These helpers define the contract for a FUTURE constrained agent interface.
    They do not modify any live prompt or workflow.

See docs/reliability_phase_1e_prompt_contract.md for the full design rationale.
"""

import json
from typing import Any

from lib.reliability.schemas import ToolResult


# ---------------------------------------------------------------------------
# Field path extractor
# ---------------------------------------------------------------------------

def extract_field_paths(payload: dict, max_paths: int = 20) -> list[str]:
    """
    Deterministically extract dot-separated paths from a nested dict.

    Traversal rules:
      - Nested dicts are traversed recursively.
      - List values: the field path is recorded; list items are not traversed.
      - Scalar values: the field path is recorded.
      - Keys are sorted alphabetically at each nesting level for determinism.
      - Output is limited to ``max_paths`` paths (DFS, early-exit).
      - Non-dict or empty payload returns ``[]``.

    Args:
        payload:   A dict (possibly nested) from which to extract paths.
        max_paths: Maximum number of paths to return (default 20).

    Returns:
        A list of dot-separated path strings in deterministic DFS order.

    Examples::

        extract_field_paths(
            {"dcf": {"base_case": {"fair_value": 200}},
             "assumptions": {"wacc": 0.095}}
        )
        # → ["assumptions.wacc", "dcf.base_case.fair_value"]

        extract_field_paths({"a": 1, "b": {"c": 2}}, max_paths=1)
        # → ["a"]

        extract_field_paths({"items": [1, 2, 3]})
        # → ["items"]  (list recorded at path; items not traversed)
    """
    if not isinstance(payload, dict):
        return []

    paths: list[str] = []

    def _collect(obj: Any, prefix: str) -> None:
        if len(paths) >= max_paths:
            return
        if isinstance(obj, dict):
            for key in sorted(obj.keys()):
                if len(paths) >= max_paths:
                    return
                full_path = f"{prefix}.{key}" if prefix else str(key)
                value = obj[key]
                if isinstance(value, dict):
                    _collect(value, full_path)
                else:
                    # Scalars and lists: record path, do not traverse further
                    paths.append(full_path)

    _collect(payload, "")
    return paths


# ---------------------------------------------------------------------------
# Evidence packet builder
# ---------------------------------------------------------------------------

def build_evidence_packet(
    run_id: str,
    target_name: str,
    tool_results: list[ToolResult],
    max_field_paths_per_result: int = 20,
) -> dict:
    """
    Build a compact, deterministic evidence packet from a list of ToolResults.

    The packet summarises available deterministic evidence without exposing
    unnecessary raw payload volume.  It is designed to be embedded in a
    constrained agent prompt so the LLM knows exactly which evidence IDs
    and field paths it is authorised to cite.

    Does NOT persist files.  Does NOT call LLMs.  Does NOT mutate ToolResults.

    Args:
        run_id:                     Run context ID (from ``create_run_context``).
        target_name:                Ticker, sector, or other target identifier.
        tool_results:               List of ToolResult objects to summarise.
        max_field_paths_per_result: Maximum ``notable_field_paths`` entries per
                                    ToolResult (default 20).

    Returns:
        A dict with keys::

            {
              "run_id": str,
              "target_name": str,
              "evidence_count": int,
              "available_evidence": [
                {
                  "evidence_id": str,
                  "tool_name": str,
                  "output_keys": list[str],         # top-level keys, sorted
                  "notable_field_paths": list[str], # dot-paths to leaves
                  "description": str,
                },
                ...
              ],
            }

    Raises:
        ValueError: If ``run_id`` or ``target_name`` is empty or blank.
        TypeError:  If ``tool_results`` is not a list.

    Examples::

        packet = build_evidence_packet("ORCL_run_001", "ORCL", [tr_val, tr_tech])
        # packet["evidence_count"] == 2
        # packet["available_evidence"][0]["tool_name"] == "valuation_model"
    """
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError(
            f"'run_id' must be a non-empty, non-blank string; got {run_id!r}."
        )
    if not isinstance(target_name, str) or not target_name.strip():
        raise ValueError(
            f"'target_name' must be a non-empty, non-blank string; got {target_name!r}."
        )
    if not isinstance(tool_results, list):
        raise TypeError(
            f"'tool_results' must be a list, got {type(tool_results).__name__!r}."
        )

    available_evidence: list[dict] = []
    for tr in tool_results:
        output_keys = sorted(tr.outputs.keys())
        notable_field_paths = extract_field_paths(
            tr.outputs, max_paths=max_field_paths_per_result
        )
        description = (
            tr.description
            if tr.description
            else f"{tr.tool_name} output for {tr.ticker or target_name}"
        )
        available_evidence.append(
            {
                "evidence_id": tr.evidence_id,
                "tool_name": tr.tool_name,
                "output_keys": output_keys,
                "notable_field_paths": notable_field_paths,
                "description": description,
            }
        )

    return {
        "run_id": run_id,
        "target_name": target_name,
        "evidence_count": len(tool_results),
        "available_evidence": available_evidence,
    }


# ---------------------------------------------------------------------------
# Schema summary
# ---------------------------------------------------------------------------

def build_schema_summary() -> dict:
    """
    Return a concise, hand-written schema summary of the AgentResult contract.

    This is a simplified, stable representation intended to be embedded in a
    constrained agent prompt.  It does not use Pydantic's JSON schema
    generation (which can be verbose and version-dependent).

    Returns:
        A dict describing the AgentResult schema contract.

    The returned value is fully deterministic and has no side effects.
    """
    return {
        "schema": "AgentResult",
        "version": "0.1",
        "note": (
            "All models use extra='forbid' — unknown fields cause a parse error."
        ),
        "required_fields": {
            "agent_name": "string (non-empty) — stable agent identifier",
            "run_id": (
                "string (non-empty) — use the run_id from the evidence packet exactly"
            ),
        },
        "optional_fields": {
            "ticker": "string | null — ticker symbol or null for market-level analysis",
            "findings": "list[Finding] — default []",
            "assumptions": "list[Assumption] — default []",
            "risks": "list[Risk] — default []",
            "confidence": "AgentConfidence | null — default null",
        },
        "Finding": {
            "text": (
                "string — claim text; numeric/metric claims REQUIRE an EvidenceRef"
            ),
            "evidence": "list[EvidenceRef] — required for numeric/metric claims; default []",
            "confidence": "float in [0.0, 1.0] — default 1.0",
        },
        "EvidenceRef": {
            "evidence_id": (
                "string (non-empty) — MUST be from the evidence packet; never fabricate"
            ),
            "tool_name": "string | null — must match the ToolResult tool_name exactly",
            "metric": (
                "string | null — a top-level key in ToolResult.outputs"
            ),
            "field_path": (
                "string | null — dot-path into ToolResult.outputs, "
                "e.g. 'dcf.base_case.fair_value'"
            ),
            "excerpt": "string — verbatim excerpt from outputs; default ''",
            "description": "string | null — human-readable binding note",
        },
        "Assumption": {
            "name": "string",
            "rationale": "string",
            "value": "string | null — assumption value as a string",
            "source": "one of: 'tool' | 'user' | 'agent' | 'default'",
            "sensitivity": "one of: 'low' | 'medium' | 'high'",
        },
        "Risk": {
            "name": "string",
            "description": (
                "string — numeric/metric content REQUIRES EvidenceRef"
            ),
            "severity": "one of: 'low' | 'medium' | 'high'",
            "evidence": "list[EvidenceRef] — cite evidence for numeric risk metrics",
        },
        "AgentConfidence": {
            "level": "one of: 'high' | 'medium' | 'low'",
            "rationale": "string — explain confidence level",
            "score": "float in [0.0, 1.0] — quantitative confidence estimate",
        },
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_agent_result_prompt(
    agent_name: str,
    run_id: str,
    target_name: str,
    task_instruction: str,
    evidence_packet: dict,
) -> str:
    """
    Build a deterministic, constrained prompt string instructing a future LLM
    to produce AgentResult-compatible JSON using only the provided evidence.

    The returned string does NOT call any external service.  It is purely a
    text template ready to be passed to a future constrained agent interface.
    It is fully deterministic: the same inputs always produce the same output.

    The prompt encodes the following constraints for the LLM:
      - Architecture principle (deterministic computation, agentic interpretation)
      - JSON-only output requirement (no markdown, no prose outside JSON)
      - Evidence-only rule (use only evidence_ids from the packet)
      - No fabricated numbers or metrics
      - EvidenceRef binding requirements for numeric/metric claims
      - Insufficiency behaviour (prefer expressing uncertainty over inventing)
      - run_id and target_name embedded verbatim
      - Full evidence packet embedded as JSON
      - AgentResult schema summary

    Args:
        agent_name:       Stable agent identifier, e.g. ``"valuation_agent"``.
        run_id:           Run context ID — embedded verbatim in the prompt.
        target_name:      Ticker or target name for this analysis.
        task_instruction: What the agent should analyse or conclude.
        evidence_packet:  Dict produced by ``build_evidence_packet()``.

    Returns:
        A deterministic prompt string (str).

    Raises:
        ValueError: If any string argument is empty or blank.

    Examples::

        prompt = build_agent_result_prompt(
            agent_name="valuation_agent",
            run_id="ORCL_20260521_abcd",
            target_name="ORCL",
            task_instruction="Analyse the DCF valuation and RSI momentum for ORCL.",
            evidence_packet=packet,
        )
        # Returns a multi-line prompt string ready for a future LLM call.
    """
    for param_name, value in [
        ("agent_name", agent_name),
        ("run_id", run_id),
        ("target_name", target_name),
        ("task_instruction", task_instruction),
    ]:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"'{param_name}' must be a non-empty, non-blank string; got {value!r}."
            )

    schema_summary = build_schema_summary()
    # sort_keys=True ensures deterministic JSON serialisation regardless of
    # dict insertion order in the caller.
    packet_json = json.dumps(evidence_packet, sort_keys=True, indent=2)
    schema_json = json.dumps(schema_summary, sort_keys=True, indent=2)

    return (
        f"You are {agent_name} — a constrained financial analysis agent "
        f"operating under strict evidence-first rules.\n"
        f"\n"
        f"ARCHITECTURE PRINCIPLE\n"
        f"Deterministic computation, agentic interpretation, auditable synthesis.\n"
        f"Code computes facts. You interpret, critique, and synthesise. "
        f"You do not compute new financial metrics.\n"
        f"\n"
        f"HARD RULES — YOU MUST FOLLOW ALL OF THEM\n"
        f"1.  Output ONLY a single valid JSON object that matches the AgentResult schema.\n"
        f"    No markdown. No code fences. No prose before or after the JSON.\n"
        f"2.  Every numeric or metric claim in findings[].text or risks[].description\n"
        f"    MUST cite at least one EvidenceRef with evidence_id from this packet.\n"
        f"3.  EvidenceRef.evidence_id MUST appear in AVAILABLE EVIDENCE below.\n"
        f"    NEVER fabricate an evidence_id. NEVER use an evidence_id not in this packet.\n"
        f"4.  EvidenceRef SHOULD include at least one binding field: tool_name, metric,\n"
        f"    or field_path.  Unbound refs will be flagged WEAK by the validator.\n"
        f"5.  Do NOT invent financial numbers, valuations, technical indicators, scanner\n"
        f"    scores, risk metrics, or any market data. Only interpret values present\n"
        f"    in the evidence packet.\n"
        f"6.  If evidence is insufficient for a numeric claim, express uncertainty\n"
        f"    in the finding text instead of making the claim.\n"
        f"    (Prefer: 'Evidence is insufficient to determine X.' over an unsupported\n"
        f"    numeric assertion.)\n"
        f"7.  Do NOT cite evidence not present in this packet.\n"
        f"8.  Assumptions MUST declare source (tool/user/agent/default) and\n"
        f"    sensitivity (low/medium/high) explicitly.\n"
        f"9.  AgentConfidence.score MUST be a float within [0.0, 1.0].\n"
        f"10. Use run_id = \"{run_id}\" exactly as provided.\n"
        f"11. Use agent_name = \"{agent_name}\" exactly as provided.\n"
        f"\n"
        f"TASK\n"
        f"{task_instruction}\n"
        f"\n"
        f"RUN CONTEXT\n"
        f"  agent_name  : {agent_name}\n"
        f"  run_id      : {run_id}\n"
        f"  target_name : {target_name}\n"
        f"\n"
        f"AVAILABLE EVIDENCE (evidence packet)\n"
        f"Use ONLY the evidence_ids listed in this packet. "
        f"Do not use any evidence_id not listed here.\n"
        f"{packet_json}\n"
        f"\n"
        f"AGENTRESULT SCHEMA SUMMARY\n"
        f"{schema_json}\n"
        f"\n"
        f"OUTPUT INSTRUCTION\n"
        f"Return a single JSON object. It must start with {{ and end with }}.\n"
        f"Do not include any text, markdown, explanation, or comments outside the JSON object.\n"
        f"The JSON must be parseable by Python json.loads().\n"
    )


# ---------------------------------------------------------------------------
# Repair prompt (future-scoped)
# ---------------------------------------------------------------------------

def build_repair_prompt(
    invalid_output: str,
    validation_errors: list[str],
    original_prompt: str,
) -> str:
    """
    Build a repair prompt instructing a future LLM to fix invalid AgentResult JSON.

    **FUTURE-SCOPED** — this helper is NOT used by the live workflow.
    It is provided for future retry/repair integration (Phase 1F+).

    Repair rules embedded in the prompt:
      - Fix only structural/schema issues listed in ``validation_errors``.
      - Do NOT invent new evidence_id values.
      - Use only evidence_ids from the original evidence packet.
      - Do NOT add numeric claims not backed by original evidence.
      - Do NOT change run_id or agent_name.
      - If a claim cannot be evidenced, remove or soften it rather than
        fabricating an evidence reference.

    Args:
        invalid_output:     The previous LLM output that failed parsing or
                            validation.
        validation_errors:  List of error/warning messages from the validator
                            or parser.  Must be non-empty.
        original_prompt:    The original constrained prompt that produced the
                            invalid output.

    Returns:
        A repair prompt string (str).

    Raises:
        ValueError: If ``validation_errors`` is empty or not a list.
    """
    if not isinstance(validation_errors, list) or not validation_errors:
        raise ValueError(
            "'validation_errors' must be a non-empty list of error strings."
        )

    errors_block = "\n".join(f"  - {e}" for e in validation_errors)

    return (
        f"The following output from a constrained financial analysis agent "
        f"failed validation.\n"
        f"Your task is to repair it so it passes the AgentResult schema and "
        f"evidence validation.\n"
        f"\n"
        f"REPAIR RULES — YOU MUST FOLLOW ALL OF THEM\n"
        f"1.  Return ONLY a single valid JSON object. "
        f"No markdown. No prose outside JSON.\n"
        f"2.  Fix ONLY the structural/schema issues listed in VALIDATION ERRORS below.\n"
        f"3.  Do NOT invent new evidence_id values. Use only the evidence_ids\n"
        f"    from the original evidence packet (see ORIGINAL PROMPT).\n"
        f"4.  Do NOT add numeric/metric claims not backed by the original evidence.\n"
        f"5.  Do NOT change the run_id or agent_name fields.\n"
        f"6.  If a claim cannot be properly evidenced, remove or soften it rather\n"
        f"    than fabricating an evidence reference.\n"
        f"7.  The repaired JSON must satisfy all HARD RULES from the original prompt.\n"
        f"\n"
        f"VALIDATION ERRORS\n"
        f"{errors_block}\n"
        f"\n"
        f"INVALID OUTPUT TO REPAIR\n"
        f"{invalid_output}\n"
        f"\n"
        f"ORIGINAL PROMPT (for context — do not add evidence not present there)\n"
        f"{original_prompt}\n"
        f"\n"
        f"OUTPUT INSTRUCTION\n"
        f"Return a single repaired JSON object. Begin with {{ and end with }}.\n"
        f"Do not include any text or explanation outside the JSON.\n"
    )
