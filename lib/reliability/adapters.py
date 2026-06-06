"""
lib/reliability/adapters.py

Generic adapter helpers for wrapping already-computed deterministic outputs
into ToolResult / DataSnapshot objects.

Design principles:
  - Pure functions only.  No Streamlit, no valuation.py, no technical.py imports.
  - Accepts already-computed Python dicts; does not perform computation.
  - Does not persist anything.  EvidenceStore.add_tool_result() is the caller's job.
  - Evidence IDs are deterministic: same inputs → same ID.

See docs/reliability_phase_0_2_adapter_plan.md for the full design rationale.
"""

import hashlib
import json
import re
from typing import Any

from lib.reliability.schemas import DataSnapshot, ToolResult


# ---------------------------------------------------------------------------
# Internal sanitizer
# ---------------------------------------------------------------------------

def _sanitize(part: str) -> str:
    """Replace whitespace and path-unsafe characters with underscores."""
    return re.sub(r"[^\w\-\.]", "_", part.strip())


# ---------------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------------

def stable_hash_payload(payload: Any, length: int = 12) -> str:
    """
    Deterministic SHA-256 hash of a JSON-serializable payload.

    Dict key order is irrelevant — keys are sorted before hashing.
    Falls back to str(payload) if JSON serialization fails.

    Returns the first `length` hex characters (default: 12).

    Examples::

        stable_hash_payload({"b": 2, "a": 1}) == stable_hash_payload({"a": 1, "b": 2})
        # True — key order is normalised

        stable_hash_payload({"a": 1}) != stable_hash_payload({"a": 2})
        # True — different payload, different hash
    """
    try:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        raw = str(payload)
    return hashlib.sha256(raw.encode()).hexdigest()[:length]


# ---------------------------------------------------------------------------
# Evidence ID
# ---------------------------------------------------------------------------

def make_evidence_id(
    run_id: str,
    tool_name: str,
    target: str,
    metric_group: str,
    payload: Any,
) -> str:
    """
    Build a deterministic, human-readable evidence_id.

    Format::

        {run_id}:{tool_name}:{target}:{metric_group}:{payload_hash}

    All five segments are sanitized (spaces and path-unsafe characters →
    underscores).  The colon character ``:`` is used only as a separator
    and never appears inside a segment.

    The hash is derived from the payload, so the ID changes if outputs change
    while remaining stable across identical executions.

    Examples::

        make_evidence_id(
            "ORCL_20260521_xxxx",
            "valuation_model",
            "ORCL",
            "dcf",
            {"intrinsic_value_per_share": 142.5},
        )
        # → "ORCL_20260521_xxxx:valuation_model:ORCL:dcf:a3f8c9d0e1b2"

    Raises:
        ValueError: If any of run_id, tool_name, target, or metric_group is
                    not a string, is empty, or is blank (whitespace-only).
    """
    for param_name, value in [
        ("run_id", run_id),
        ("tool_name", tool_name),
        ("target", target),
        ("metric_group", metric_group),
    ]:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"'{param_name}' must be a non-empty, non-blank string; got {value!r}."
            )
    hash_suffix = stable_hash_payload(payload, length=12)
    segments = [run_id, tool_name, target, metric_group, hash_suffix]
    return ":".join(_sanitize(s) for s in segments)


# ---------------------------------------------------------------------------
# ToolResult factory
# ---------------------------------------------------------------------------

def tool_result_from_outputs(
    run_id: str,
    tool_name: str,
    target: str,
    metric_group: str,
    outputs: dict,
    inputs: dict | None = None,
    metadata: dict | None = None,
) -> ToolResult:
    """
    Wrap already-computed outputs into a ToolResult.

    Does NOT persist anything.  The caller is responsible for calling
    ``EvidenceStore.add_tool_result()`` with the returned object.

    Args:
        run_id:        Run context ID (from ``create_run_context``).
        tool_name:     Stable identifier for the deterministic tool,
                       e.g. ``"valuation_model"``, ``"technical_indicator_engine"``.
        target:        Ticker, sector, or other target identifier, e.g. ``"ORCL"``.
        metric_group:  Logical grouping of metrics, e.g. ``"dcf"``, ``"rsi_macd"``.
        outputs:       Dict of computed values to store as evidence.
        inputs:        Optional dict of inputs used to produce the outputs.
        metadata:      Optional dict.  If it contains a ``"description"`` key
                       (str), that becomes ``ToolResult.description``.
                       Otherwise the whole dict is JSON-serialised as description.

    Raises:
        ValueError: If any of run_id, tool_name, target, or metric_group is
                    empty or blank.
    """
    for param_name, value in [
        ("run_id", run_id),
        ("tool_name", tool_name),
        ("target", target),
        ("metric_group", metric_group),
    ]:
        if not value or not value.strip():
            raise ValueError(f"'{param_name}' must be a non-empty string.")

    evidence_id = make_evidence_id(run_id, tool_name, target, metric_group, outputs)

    description = ""
    if metadata:
        if isinstance(metadata.get("description"), str):
            description = metadata["description"]
        else:
            try:
                description = json.dumps(metadata, default=str)
            except Exception:
                description = str(metadata)

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=tool_name,
        run_id=run_id,
        ticker=target,
        inputs=inputs or {},
        outputs=outputs,
        description=description,
    )


# ---------------------------------------------------------------------------
# DataSnapshot factory
# ---------------------------------------------------------------------------

def data_snapshot_from_payload(
    snapshot_id: str,
    source: str,
    payload: dict,
    metadata: dict | None = None,
) -> DataSnapshot:
    """
    Wrap a raw data payload into a DataSnapshot.

    Does NOT persist anything.  DataSnapshots are typically embedded in
    ``ToolResult.data_snapshots`` to link raw source data to a computed output,
    creating a two-level provenance chain:

        EvidenceRef → ToolResult → DataSnapshot → raw source

    Args:
        snapshot_id:  Unique identifier for this snapshot.
        source:       Source name, e.g. ``"yfinance"``, ``"polygon.io"``.
        payload:      Raw data dict.
        metadata:     Optional dict.  If it contains a ``"description"`` key
                      (str), that becomes ``DataSnapshot.description``.
    """
    description = ""
    if metadata:
        if isinstance(metadata.get("description"), str):
            description = metadata["description"]
        else:
            try:
                description = json.dumps(metadata, default=str)
            except Exception:
                description = str(metadata)

    return DataSnapshot(
        snapshot_id=snapshot_id,
        source=source,
        data=payload,
        description=description,
    )


# ---------------------------------------------------------------------------
# Convenience wrappers (tool_name constants baked in)
# ---------------------------------------------------------------------------

def valuation_tool_result(
    run_id: str,
    target: str,
    metric_group: str,
    outputs: dict,
    inputs: dict | None = None,
    metadata: dict | None = None,
) -> ToolResult:
    """
    Shorthand adapter for valuation module outputs.

    Equivalent to ``tool_result_from_outputs(..., tool_name="valuation_model", ...)``.
    Intended for DCF, WACC, FCF, relative-valuation, and valuation-range outputs.
    """
    return tool_result_from_outputs(
        run_id=run_id,
        tool_name="valuation_model",
        target=target,
        metric_group=metric_group,
        outputs=outputs,
        inputs=inputs,
        metadata=metadata,
    )


def technical_tool_result(
    run_id: str,
    target: str,
    metric_group: str,
    outputs: dict,
    inputs: dict | None = None,
    metadata: dict | None = None,
) -> ToolResult:
    """
    Shorthand adapter for technical indicator outputs.

    Equivalent to ``tool_result_from_outputs(..., tool_name="technical_indicator_engine", ...)``.
    Intended for RSI, MACD, SMA/EMA, ADX, Bollinger, and volume outputs.
    """
    return tool_result_from_outputs(
        run_id=run_id,
        tool_name="technical_indicator_engine",
        target=target,
        metric_group=metric_group,
        outputs=outputs,
        inputs=inputs,
        metadata=metadata,
    )


def scanner_tool_result(
    run_id: str,
    target: str,
    metric_group: str,
    outputs: dict,
    inputs: dict | None = None,
    metadata: dict | None = None,
) -> ToolResult:
    """
    Shorthand adapter for scanner / rotation model outputs.

    Equivalent to ``tool_result_from_outputs(..., tool_name="stock_scanner", ...)``.
    Intended for composite scores, sector ranks, and strategy outputs.
    """
    return tool_result_from_outputs(
        run_id=run_id,
        tool_name="stock_scanner",
        target=target,
        metric_group=metric_group,
        outputs=outputs,
        inputs=inputs,
        metadata=metadata,
    )


def sector_rotation_tool_result(
    run_id: str,
    target: str,
    metric_group: str,
    outputs: dict,
    inputs: dict | None = None,
    metadata: dict | None = None,
) -> ToolResult:
    """
    Shorthand adapter for sector rotation model outputs.

    Equivalent to ``tool_result_from_outputs(..., tool_name="sector_rotation_model", ...)``.
    Intended for sector scores, ETF momentum, relative strength, sector rankings,
    and rotation signal outputs produced by ``lib/rotation.py``.

    The ``target`` parameter may be a sector name (``"Technology"``), an ETF
    ticker (``"XLK"``), or a placeholder such as ``"market"`` when the output
    covers multiple sectors simultaneously.
    """
    return tool_result_from_outputs(
        run_id=run_id,
        tool_name="sector_rotation_model",
        target=target,
        metric_group=metric_group,
        outputs=outputs,
        inputs=inputs,
        metadata=metadata,
    )
