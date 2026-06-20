"""
lib/agent_framework/world_adapter.py

Phase 8A — World 1 -> World 2 adapter.

Wraps live ``lib.llm_orchestrator`` analyze_* output dicts AND deterministic
processed signals (classify_regime, market_internals, opportunity_ranker, ...)
into World 2 ``ToolResult`` objects suitable for ``EvidenceStore``. The
``processed_signals_to_tool_result`` path is the foundation of the numeric
firewall: code-computed numbers enter the evidence layer here, not via LLM
inference.

IMPORT DISCIPLINE (enforced by §8A.10): no ``lib.reliability`` import at
module-load time. The single reliability helper used here
(``tool_result_from_outputs``) is imported lazily inside each function.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # annotations only
    from lib.reliability.schemas import ToolResult


def _normalize_to_dict(value):
    """Normalize a dataclass instance to a dict; pass other values through.

    Real callers feed code-computed dataclasses (e.g. MacroRegimeResult from
    classify_regime()) straight into the adapter. Convert those to a plain
    dict so the evidence layer always stores JSON-safe outputs.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return value


def _require_nonempty_dict(value, name: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dict, got {type(value).__name__!r}.")
    if not value:
        raise ValueError(f"{name} must be a non-empty dict.")


def llm_output_to_tool_result(
    output_dict: dict,
    *,
    run_id: str,
    tool_name: str,
    target: str,
    metric_group: str,
    ticker: str | None = None,
    description: str = "",
) -> "ToolResult":
    """
    Wrap a live llm_orchestrator analyze_* output dict into a ToolResult
    using ``tool_result_from_outputs`` from ``lib.reliability.adapters``.

    output_dict: the raw dict returned by any analyze_* function
    tool_name:   e.g. "analyze_macro_regime", "analyze_sector_full"
    target:      ticker or "MACRO" or sector name
    metric_group: e.g. "regime_classification", "sector_analysis"

    Returns a ToolResult ready for EvidenceStore.add_tool_result().
    Raises ValueError if output_dict is empty or not a dict.
    """
    # Normalize dataclass inputs to dict (future callers may pass a dataclass).
    output_dict = _normalize_to_dict(output_dict)
    _require_nonempty_dict(output_dict, "output_dict")

    from lib.reliability.adapters import tool_result_from_outputs

    metadata = {"description": description} if description else None
    tr = tool_result_from_outputs(
        run_id=run_id,
        tool_name=tool_name,
        target=target,
        metric_group=metric_group,
        outputs=output_dict,
        inputs=None,
        metadata=metadata,
    )
    # tool_result_from_outputs sets ticker=target; allow an explicit override.
    if ticker is not None:
        tr.ticker = ticker
    return tr


def processed_signals_to_tool_result(
    signals: dict,
    *,
    run_id: str,
    tool_name: str,
    target: str,
    metric_group: str,
    description: str = "",
) -> "ToolResult":
    """
    Wrap deterministic processed signals (from classify_regime,
    market_internals, opportunity_ranker, etc.) into a ToolResult.

    This is the primary path for code-computed signals entering the
    evidence layer — the foundation of the numeric firewall.

    Raises ValueError if signals is empty or not a dict.
    """
    # Normalize dataclass inputs to dict (e.g. MacroRegimeResult from
    # classify_regime()) before any validation.
    signals = _normalize_to_dict(signals)
    _require_nonempty_dict(signals, "signals")

    from lib.reliability.adapters import tool_result_from_outputs

    metadata = {"description": description} if description else None
    return tool_result_from_outputs(
        run_id=run_id,
        tool_name=tool_name,
        target=target,
        metric_group=metric_group,
        outputs=signals,
        inputs=None,
        metadata=metadata,
    )
