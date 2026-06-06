"""
lib/reliability/integration_boundary.py

Phase 4A: Reliability Integration Boundary Contract.

This module defines the contract through which the reliability layer could
later integrate with the live AI workflow. In Phase 4A, it is an isolated
boundary contract only — it does not wire into any live app, Streamlit page,
Claude API call, workflow orchestrator, or live workflow state.

Design principles:
  - Strongly typed, deterministic, side-effect-free.
  - No file writes inside boundary functions.
  - No imports from streamlit, anthropic, app.py, pages/*,
    lib/llm_orchestrator, or lib/workflow_state.
  - No live workflow state mutation.
  - No network calls.
  - DISABLED mode is always pass-through with no evaluation.
  - SHADOW mode is non-blocking; evaluation is noted as not yet wired
    in Phase 4A.
  - ENFORCED mode is defined but not wired to live workflow in Phase 4A;
    it returns a deterministic non-live result with diagnostics.

See docs/reliability_phase_4a_integration_boundary.md for design rationale.

Disclaimer: All outputs are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReliabilityExecutionMode(str, Enum):
    """Controls whether the reliability layer is active and how it behaves."""
    DISABLED = "disabled"
    SHADOW = "shadow"
    ENFORCED = "enforced"


class ReliabilitySourceWorkflow(str, Enum):
    """Identifies which workflow or page initiated the boundary evaluation."""
    OVERVIEW_WORKFLOW = "overview_workflow"
    SECTOR_PAGE = "sector_page"
    SCANNER_PAGE = "scanner_page"
    EQUITY_PAGE = "equity_page"
    FINANCIAL_PAGE = "financial_page"
    PRICE_VOLUME_PAGE = "price_volume_page"
    CLI = "cli"
    UNKNOWN = "unknown"


class ReliabilityBoundaryStatus(str, Enum):
    """Outcome status of a boundary evaluation."""
    PASS_THROUGH = "pass_through"
    SHADOW_EVALUATED = "shadow_evaluated"
    BLOCKED = "blocked"
    ERROR_CAPTURED = "error_captured"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ReliabilityBoundaryRequest(BaseModel):
    """Input contract for a reliability boundary evaluation."""
    model_config = ConfigDict(frozen=True)

    source_workflow: ReliabilitySourceWorkflow
    execution_mode: ReliabilityExecutionMode
    run_id: Optional[str] = Field(default=None)
    step_name: Optional[str] = Field(default=None)
    ticker: Optional[str] = Field(default=None)
    payload: Optional[Dict[str, Any]] = Field(default=None)
    metadata: Optional[Dict[str, Any]] = Field(default=None)


class ReliabilityBoundaryResult(BaseModel):
    """Output contract from a reliability boundary evaluation."""
    model_config = ConfigDict(frozen=True)

    status: ReliabilityBoundaryStatus
    execution_mode: ReliabilityExecutionMode
    source_workflow: ReliabilitySourceWorkflow
    should_block: bool
    diagnostics: List[str] = Field(default_factory=list)
    payload: Optional[Dict[str, Any]] = Field(default=None)
    reliability_summary: Optional[Dict[str, Any]] = Field(default=None)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_execution_mode(value: Any) -> ReliabilityExecutionMode:
    """Normalize a string or enum value to ReliabilityExecutionMode.

    Accepts:
      - ReliabilityExecutionMode instances (returned as-is)
      - Strings: case-insensitive match to enum values
    Raises:
      - ValueError for unrecognized string values or non-string/non-enum types
    """
    if isinstance(value, ReliabilityExecutionMode):
        return value
    if isinstance(value, str):
        try:
            return ReliabilityExecutionMode(value.lower())
        except ValueError:
            raise ValueError(
                f"Unrecognized execution mode: {value!r}. "
                f"Valid values: {[m.value for m in ReliabilityExecutionMode]}"
            )
    raise ValueError(
        f"Cannot normalize execution mode from {type(value).__name__}: {value!r}"
    )


def normalize_source_workflow(value: Any) -> ReliabilitySourceWorkflow:
    """Normalize a string or enum value to ReliabilitySourceWorkflow.

    Accepts:
      - ReliabilitySourceWorkflow instances (returned as-is)
      - Strings: case-insensitive match to enum values
    Raises:
      - ValueError for unrecognized string values or non-string/non-enum types
    """
    if isinstance(value, ReliabilitySourceWorkflow):
        return value
    if isinstance(value, str):
        try:
            return ReliabilitySourceWorkflow(value.lower())
        except ValueError:
            raise ValueError(
                f"Unrecognized source workflow: {value!r}. "
                f"Valid values: {[w.value for w in ReliabilitySourceWorkflow]}"
            )
    raise ValueError(
        f"Cannot normalize source workflow from {type(value).__name__}: {value!r}"
    )


# ---------------------------------------------------------------------------
# Boundary evaluation
# ---------------------------------------------------------------------------

def evaluate_reliability_boundary(
    request: ReliabilityBoundaryRequest,
) -> ReliabilityBoundaryResult:
    """Evaluate a reliability boundary request and return a typed result.

    Behavior by mode:
      DISABLED  — pass-through; no validation; should_block=False; payload
                  preserved; reliability_summary=None.
      SHADOW    — non-blocking; notes that shadow evaluation is not yet wired
                  to live workflow in Phase 4A; should_block=False; payload
                  preserved; reliability_summary contains phase metadata.
      ENFORCED  — not wired to live workflow in Phase 4A; returns a
                  deterministic non-live result with diagnostics explaining
                  enforced mode is deferred; should_block=False in Phase 4A;
                  payload preserved.

    This function is deterministic and side-effect-free. It does not write
    files, call external APIs, mutate input objects, or interact with live
    workflow state.
    """
    mode = request.execution_mode
    workflow = request.source_workflow

    if mode == ReliabilityExecutionMode.DISABLED:
        return ReliabilityBoundaryResult(
            status=ReliabilityBoundaryStatus.PASS_THROUGH,
            execution_mode=mode,
            source_workflow=workflow,
            should_block=False,
            diagnostics=[
                "Reliability layer is DISABLED. Pass-through with no evaluation."
            ],
            payload=request.payload,
            reliability_summary=None,
        )

    if mode == ReliabilityExecutionMode.SHADOW:
        return ReliabilityBoundaryResult(
            status=ReliabilityBoundaryStatus.SHADOW_EVALUATED,
            execution_mode=mode,
            source_workflow=workflow,
            should_block=False,
            diagnostics=[
                "SHADOW mode: reliability boundary evaluated. "
                "Shadow evaluation is not wired to live workflow in Phase 4A. "
                "No live validation or critic execution performed. "
                "Payload preserved as pass-through."
            ],
            payload=request.payload,
            reliability_summary={
                "shadow_wired": False,
                "phase": "4A",
                "note": (
                    "Shadow evaluation contract defined; "
                    "wiring deferred to Phase 4B+."
                ),
            },
        )

    # ENFORCED mode: contract is defined but not wired in Phase 4A.
    return ReliabilityBoundaryResult(
        status=ReliabilityBoundaryStatus.PASS_THROUGH,
        execution_mode=mode,
        source_workflow=workflow,
        should_block=False,
        diagnostics=[
            "ENFORCED mode: reliability boundary contract is defined. "
            "ENFORCED mode is NOT wired to live workflow in Phase 4A. "
            "No blocking, no live validation, no live critic execution. "
            "Wiring of ENFORCED mode to live workflow is deferred to a future phase. "
            "Payload preserved as pass-through."
        ],
        payload=request.payload,
        reliability_summary={
            "enforced_wired": False,
            "phase": "4A",
            "note": (
                "ENFORCED mode contract defined; "
                "live wiring deferred to Phase 4B+."
            ),
        },
    )
