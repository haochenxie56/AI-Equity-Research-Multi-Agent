"""
lib/agent_framework/agent_runner.py

Phase 8A — the LLM agent runner.

``run_llm_agent`` is the full evidence-first agent pipeline: persist
deterministic ToolResults to an EvidenceStore, build a constrained prompt
from an evidence packet, call Claude, parse + validate the response against
the stored evidence, and map the validated AgentResult into an AgentOutput.

Design rules:
  - Deterministic computation stays in code; the LLM only interprets evidence.
  - Fail-closed: any LLM/parse failure yields a rule-based fallback
    AgentOutput flagged for human confirmation, never an exception leak.
  - Validation ERRORS (unsupported numeric claims, missing/invalid evidence)
    raise AgentRunError — the agent must not silently emit invalid output.

IMPORT DISCIPLINE (enforced by §8A.10): no ``lib.reliability`` and no
``lib.llm_orchestrator`` import at module-load time. Every such import is
lazy, inside the function that needs it. Only the (lightweight) sibling
``lib.agent_framework.agent_output`` is imported at module level.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from lib.agent_framework.agent_output import (
    AgentOutput,
    agent_result_to_agent_output,
    append_agent_output,
)

if TYPE_CHECKING:  # annotations only
    from lib.reliability.schemas import ToolResult


_log = logging.getLogger("agent_framework.agent_runner")

_AGENT_MODEL = "claude-sonnet-4-6"   # keep in sync with llm_orchestrator._MODEL
_JUDGMENT_MAX_LEN = 200

_SYSTEM_INVARIANTS = (
    "SYSTEM INVARIANTS (never violate):\n"
    "1. Respond ONLY with valid JSON matching the AgentResult schema. "
    "No markdown, no code fences, no prose before or after the JSON.\n"
    "2. Every claim in findings[] must cite at least one evidence_id from "
    "the evidence packet. Do not invent evidence IDs.\n"
    "3. Never fabricate numeric values. If a number is not in the evidence "
    "packet, do not include it in any finding text.\n"
    "4. The first finding MUST be a one-sentence actionable judgment of "
    "<= 200 characters containing NO numeric values, %, $, or metric names. "
    "This finding is the agent's primary conclusion for the PM layer.\n"
    "5. approved_for_execution is always False.\n"
    "6. Emit run_id and agent_name exactly as given in the prompt."
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AgentRunError(Exception):
    """Raised when validate_agent_result returns severity==error issues."""

    def __init__(self, agent_id: str, issues: list):
        self.agent_id = agent_id
        self.issues = issues
        super().__init__(
            f"AgentRunError [{agent_id}]: "
            + "; ".join(i.message for i in issues)
        )


# ---------------------------------------------------------------------------
# LLM call (reuse the World 1 client factory; do NOT duplicate it)
# ---------------------------------------------------------------------------

def _get_llm_client():
    from lib.llm_orchestrator import _get_client
    return _get_client()


def _call_llm(system: str, user: str, max_tokens: int) -> str:
    """Return the raw text response. Raises on API error."""
    client = _get_llm_client()
    resp = client.messages.create(
        model=_AGENT_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _repair_llm_response(data: dict, run_id: str, agent_id: str) -> dict:
    """
    Attempt to coerce a flat LLM response into AgentResult shape.
    Called only when the raw parsed dict lacks a "findings" key,
    indicating the LLM flattened the structure.

    Handles two observed failure patterns:
      Pattern A: top-level "text" and "evidence" (single finding)
      Pattern B: top-level "text" and "evidence" are absent but
                 "findings" is missing entirely

    Never raises. Returns the (possibly repaired) dict.
    The caller still runs parse_agent_result_json after this,
    so any remaining schema errors will be caught there.
    """
    if "findings" in data:
        # already has findings array — only fix confidence if needed
        repaired = dict(data)
    else:
        # Pattern A/B: findings are at top level, wrap them
        finding = {}
        if "text" in data:
            finding["text"] = data["text"]
        if "evidence" in data:
            finding["evidence"] = data["evidence"]
        repaired = {k: v for k, v in data.items()
                    if k not in ("text", "evidence")}
        if finding:
            repaired["findings"] = [finding]
        else:
            repaired["findings"] = []

    # Always inject agent_name and run_id if missing
    if "agent_name" not in repaired or not repaired["agent_name"]:
        repaired["agent_name"] = agent_id
    if "run_id" not in repaired or not repaired["run_id"]:
        repaired["run_id"] = run_id

    # Coerce float confidence to AgentConfidence object
    if isinstance(repaired.get("confidence"), (int, float)):
        score = float(repaired["confidence"])
        level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
        repaired["confidence"] = {
            "level": level,
            "rationale": "Confidence coerced from float by repair layer.",
            "score": score,
        }

    return repaired


def _extract_json_obj(text: str) -> dict:
    """
    Extract the first decodable JSON object from an LLM response, tolerating
    markdown fences and preamble/trailing prose. Raises ValueError if no
    JSON object can be decoded.
    """
    from lib.llm_orchestrator import _strip_fences

    cleaned = _strip_fences(text or "")
    decoder = json.JSONDecoder()
    for i, ch in enumerate(cleaned):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(cleaned, i)
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
    raise ValueError(
        f"no decodable JSON object in LLM response (head: {cleaned[:120]!r})"
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback_agent_output(
    agent_id: str,
    horizon: str,
    supporting_data: dict,
    error: Exception,
    *,
    valid_until: str,
    run_id: str | None = None,
    target: str = "MARKET",
    ticker: str | None = None,
) -> AgentOutput:
    """
    Build (and persist) a rule-based fallback AgentOutput after a runner
    failure. Carries one synthetic EvidenceRef pointing to a "runner_error"
    ToolResult, is flagged requires_human_confirmation=True, and uses
    judgment_source="rule_based".
    """
    from lib.reliability.schemas import EvidenceRef
    from lib.reliability.adapters import tool_result_from_outputs

    err_text = f"{type(error).__name__}: {error}"
    rid = run_id or "fallback"
    err_tr = tool_result_from_outputs(
        run_id=rid,
        tool_name="runner_error",
        target=target or "MARKET",
        metric_group="error",
        outputs={"error": err_text},
        metadata={"description": "agent runner failure"},
    )
    ref = EvidenceRef(
        evidence_id=err_tr.evidence_id,
        tool_name="runner_error",
        description="Synthetic evidence for an agent runner failure.",
        excerpt=err_text[:200],
    )
    ao = AgentOutput(
        agent_id=agent_id,
        timestamp=_now_iso(),
        horizon=horizon,
        judgment="Agent run failed; manual review required before any action.",
        confidence=0.0,
        evidence_refs=[ref],
        supporting_data={**(supporting_data or {}), "runner_error": err_text},
        requires_human_confirmation=True,
        judgment_source="rule_based",
        valid_until=valid_until,
        agent_result=None,
        debate_report=None,
    )
    append_agent_output(ao)
    return ao


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_llm_agent(
    *,
    agent_id: str,
    horizon: str,
    task_instruction: str,
    tool_results: "list[ToolResult]",
    supporting_data: dict,
    requires_human_confirmation: bool,
    judgment_source: str = "llm_proposed",
    valid_until: str,
    ticker: str | None = None,
    max_tokens: int = 1024,
    run_id: str | None = None,
) -> AgentOutput:
    """
    Full agent run pipeline (see module docstring). Returns a validated
    AgentOutput, or a rule-based fallback AgentOutput on LLM/parse failure.

    Raises:
        ValueError:     if tool_results or task_instruction is empty.
        AgentRunError:  if evidence validation returns severity==error issues.
    """
    # 1. Validate inputs.
    if not task_instruction or not task_instruction.strip():
        raise ValueError("run_llm_agent: task_instruction must be non-empty.")
    if not tool_results:
        raise ValueError("run_llm_agent: tool_results must be non-empty.")

    # 2. Mint a run_id if not provided.
    if not run_id:
        from lib.reliability.run_context import create_run_context
        ctx = create_run_context(ticker=ticker, task=task_instruction[:120])
        run_id = ctx.run_id

    target_name = ticker or agent_id

    # 3. Persist tool_results to an EvidenceStore under data/agent_evidence/.
    from lib.reliability.evidence_store import EvidenceStore

    run_dir = Path("data/agent_evidence") / agent_id / run_id
    store = EvidenceStore(run_dir)
    for tr in tool_results:
        try:
            store.add_tool_result(tr)
        except ValueError:
            # Duplicate evidence_id already present in the store — content is
            # identical (evidence_id is content-addressed), so this is safe.
            _log.debug("run_llm_agent[%s]: duplicate evidence_id skipped.", agent_id)
    store.save_manifest()

    # 4-5. Build the evidence packet and the constrained prompt.
    from lib.reliability.prompt_contracts import (
        build_agent_result_prompt,
        build_evidence_packet,
    )

    packet = build_evidence_packet(
        run_id=run_id,
        target_name=target_name,
        tool_results=tool_results,
    )
    user_prompt = build_agent_result_prompt(
        agent_name=agent_id,
        run_id=run_id,
        target_name=target_name,
        task_instruction=task_instruction,
        evidence_packet=packet,
    )

    # 6. Call Claude (fail-closed).
    try:
        raw = _call_llm(_SYSTEM_INVARIANTS, user_prompt, max_tokens)
    except Exception as exc:  # noqa: BLE001 — fail-closed
        _log.warning("run_llm_agent[%s]: LLM call failed: %s", agent_id, exc)
        return _fallback_agent_output(
            agent_id, horizon, supporting_data, exc,
            valid_until=valid_until, run_id=run_id,
            target=target_name, ticker=ticker,
        )

    # 7. Parse + validate against the evidence store (parse failure is
    #    fail-closed; validation ERRORS raise AgentRunError).
    from lib.reliability.agent_output import parse_and_validate_agent_result

    try:
        obj = _extract_json_obj(raw)
        # Structural repair: coerce a flattened LLM response (top-level
        # text/evidence, float confidence, missing agent_name/run_id) into the
        # AgentResult shape before the extra="forbid" schema bind rejects it.
        obj = _repair_llm_response(obj, run_id=run_id, agent_id=agent_id)
        agent_result, report = parse_and_validate_agent_result(obj, store)
    except Exception as exc:  # noqa: BLE001 — malformed LLM output, fail-closed
        _log.warning(
            "run_llm_agent[%s]: could not parse/validate LLM output: %s",
            agent_id, exc,
        )
        return _fallback_agent_output(
            agent_id, horizon, supporting_data, exc,
            valid_until=valid_until, run_id=run_id,
            target=target_name, ticker=ticker,
        )

    for issue in report.issues:
        _log.warning(
            "run_llm_agent[%s]: validation %s [%s]: %s @ %s",
            agent_id, issue.severity, issue.code, issue.message, issue.location,
        )
    error_issues = [i for i in report.issues if i.severity == "error"]
    if error_issues:
        raise AgentRunError(agent_id, error_issues)

    # 8. Extract the one-sentence judgment (the prompt puts it first).
    judgment = ""
    if agent_result.findings:
        judgment = (agent_result.findings[0].text or "").strip()
    if not judgment:
        judgment = "No actionable judgment was produced; manual review required."
    judgment = judgment[:_JUDGMENT_MAX_LEN]

    # 9. Map to AgentOutput.
    ao = agent_result_to_agent_output(
        agent_result,
        horizon=horizon,
        judgment=judgment,
        requires_human_confirmation=requires_human_confirmation,
        judgment_source=judgment_source,
        valid_until=valid_until,
        supporting_data=supporting_data,
    )

    # 10. Persist.
    append_agent_output(ao)

    # 11. Return.
    return ao
