"""
lib/agents/macro_regime_agent.py

Phase 8A — MacroRegimeAgent smoke test.

This is the first concrete agent on the Phase 8A framework. It is NOT a
production agent: it exists to prove the run_llm_agent pipeline functions
end to end (deterministic signals -> ToolResult/EvidenceStore -> constrained
prompt -> Claude -> validated AgentResult -> AgentOutput -> JSONL).

IMPORT DISCIPLINE: no ``lib.reliability`` import at module-load time. The
single reliability helper used (``create_run_context``) is imported lazily.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from lib.agent_framework.agent_runner import run_llm_agent
from lib.agent_framework.world_adapter import processed_signals_to_tool_result

if TYPE_CHECKING:  # annotations only
    from lib.agent_framework.agent_output import AgentOutput


_MACRO_TASK_INSTRUCTION = (
    "You are MacroRegimeAgent. Based on the macro regime signals in the "
    "evidence packet, provide an actionable synthesis for the PM layer. "
    "What do these signals mean for portfolio positioning across horizons? "
    "Be specific about sector implications and time windows. First finding "
    "must be a one-sentence judgment."
)


def end_of_today_iso() -> str:
    """Return today's date at 23:59:59 UTC as an ISO datetime string."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()


def run_macro_regime_agent(
    regime_signals: dict,
    *,
    horizon: str = "cross",
    ticker: str | None = None,
) -> "AgentOutput":
    """
    Minimal MacroRegimeAgent smoke test.

    regime_signals: output of macro_regime.classify_regime() (MacroRegimeResult
                    dataclass) or a plain dict with at least:
                    {"regime": str, "confidence": str, "horizon_bias": dict,
                     "key_signals": list, "opportunity_posture": str,
                     "data_coverage": float, "signals": list}
                    Dataclass inputs are automatically normalized to dict.

    Steps:
      1. Wrap regime_signals as a ToolResult via processed_signals_to_tool_result.
      2. Build a minimal macro task_instruction.
      3. Call run_llm_agent (valid_until = end of today, cross/short horizon).
      4. Return the AgentOutput.
    """
    # Normalize a dataclass input (e.g. MacroRegimeResult) to a dict once, so
    # both the supporting_data copy below and the JSON-safe serialization in
    # run_llm_agent receive a plain dict. (processed_signals_to_tool_result
    # also normalizes defensively, but supporting_data needs a dict here too.)
    import dataclasses

    if dataclasses.is_dataclass(regime_signals) and not isinstance(regime_signals, type):
        regime_signals = dataclasses.asdict(regime_signals)

    # A ToolResult must be run-linked, so mint the run_id up front and reuse
    # it for the runner (so the EvidenceStore and the packet agree on run_id).
    from lib.reliability.run_context import create_run_context

    ctx = create_run_context(ticker=ticker or "MACRO", task="macro regime synthesis")
    run_id = ctx.run_id

    tool_result = processed_signals_to_tool_result(
        regime_signals,
        run_id=run_id,
        tool_name="classify_regime",
        target="MACRO",
        metric_group="regime_classification",
        description="Deterministic macro regime classification signals.",
    )

    return run_llm_agent(
        agent_id="MacroRegimeAgent",
        horizon=horizon,
        task_instruction=_MACRO_TASK_INSTRUCTION,
        tool_results=[tool_result],
        supporting_data=dict(regime_signals),
        requires_human_confirmation=True,
        judgment_source="llm_proposed",
        valid_until=end_of_today_iso(),
        ticker=ticker,
        max_tokens=1024,
        run_id=run_id,
    )
