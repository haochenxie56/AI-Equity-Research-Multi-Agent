"""
lib/reliability/allocation_report.py

Phase 3R-C: Allocation Agent v0.1 Non-live.

Design principles:
  - Standalone, deterministic, offline/mock-only.
  - No live LLM calls, no live data fetching, no app integration.
  - No broker / order / execution behavior.
  - Consumes typed mock portfolio/position/target inputs from caller.
  - Produces structured AllocationReport for research/review purposes only.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice or individual security recommendations.
  - Does NOT connect to brokerage, live holdings, or any external API.
  - approved_for_execution is ALWAYS False. No pathway to set it True exists.
  - Mock/dry-run only; all outputs are explicitly evidence-aware.
  - Missing optional prior artifacts produce warnings, not crashes.

Relationship to Roadmap v4 Phase 3I:
  - Phase 3R-C implements the Allocation Agent v0.1 skeleton specified
    in Roadmap v4 Phase 3I.
  - All allocation targets, calculations, and risk-budget checks are
    research-only advisory references. They are NOT executable orders.
  - approved_for_execution is permanently False (schema-enforced).
  - This phase does NOT authorize trading or execution of any kind.

Relationship to Phase 2D (allocation.py):
  - Phase 2D provides primitive portfolio/position schemas and calculators:
    PositionSnapshot, PortfolioSnapshot, AllocationTarget, RiskBudget,
    calculate_position_sizing, calculate_stop_loss_risk, etc.
  - Phase 3R-C provides a higher-level agent-output layer:
    AllocationPortfolioSnapshot, AllocationPositionSnapshot,
    AllocationTargetSpec, RiskBudgetConstraint, AllocationCalculation,
    AllocationAssessment, AllocationInputBundle, AllocationSummary,
    AllocationReport.
  - Phase 3R-C calculators operate on raw float inputs (not Phase 2D objects)
    to support the Roadmap v4 Phase 3I formula specification.

Roadmap v4 formulas implemented:
  current_position_value  = shares × current_price
  current_allocation_pct  = position_value / total_portfolio_value
  target_position_value   = target_allocation_pct × total_portfolio_value
  required_trade_value    = target_position_value - current_position_value
  required_shares         = required_trade_value / current_price
  cash_released_from_trim = shares_to_sell × current_price  (Phase 2D)
  max_loss_at_stop        = shares × (entry_price - stop_price)
  portfolio_loss_pct      = max_loss / total_portfolio_value

Phase 3R-C is part of the Roadmap v4 Phase 3 backfill sequence.

See docs/reliability_phase_3r_allocation.md for design.

Disclaimer: All outputs are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import ToolResult


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Literal type aliases (enums)
# ---------------------------------------------------------------------------

AllocationStatus = Literal[
    "unknown",
    "complete",
    "needs_review",
    "blocked",
]

AllocationActionType = Literal[
    "hold",
    "add",
    "trim",
    "exit",
    "no_action",
    "unknown",
]

AllocationRiskLevel = Literal[
    "low",
    "medium",
    "high",
    "unknown",
]

AllocationEvidenceQuality = Literal[
    "unsupported",
    "weak",
    "adequate",
    "strong",
    "unknown",
]

AllocationConstraintType = Literal[
    "max_position_pct",
    "max_portfolio_loss_pct",
    "min_cash_pct",
    "sector_exposure",
    "liquidity",
    "volatility",
    "thesis_confidence",
    "human_review_block",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_ALLOCATION_REPORT_TOOL_NAME: str = "allocation_report"
_ALLOCATION_REPORT_METRIC_GROUP: str = "allocation_report"
_CALCULATION_VERSION: str = "allocation_report_v1"

# Action inference tolerance: differences below 0.1% of portfolio are treated
# as "hold" or "no_action" (rounding noise, not a meaningful rebalance signal).
_ACTION_TOLERANCE_FRACTION: float = 0.001

_ADEQUATE_EVIDENCE: frozenset[str] = frozenset({"adequate", "strong"})
_ACTIVE_ACTION_TYPES: frozenset[str] = frozenset({"add", "trim", "exit"})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AllocationPortfolioSnapshot(BaseModel):
    """
    Simplified portfolio snapshot for Phase 3R-C allocation agent.

    This is caller-provided mock/non-live data only.
    No live portfolio data, brokerage data, or external API integration.
    Does not include a positions list — position data is provided separately
    via AllocationPositionSnapshot.

    Validation:
      - total_portfolio_value must be positive.
      - cash_value non-negative if present.
      - cash_pct between 0 and 1 if present.
    """

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str = Field(min_length=1)
    total_portfolio_value: float = Field(gt=0.0)
    cash_value: Optional[float] = None
    cash_pct: Optional[float] = None
    as_of: str = ""
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> "AllocationPortfolioSnapshot":
        if self.portfolio_id.strip() == "":
            raise ValueError("portfolio_id must not be whitespace-only.")
        if self.cash_value is not None and self.cash_value < 0:
            raise ValueError(
                f"cash_value must be >= 0 if provided; got {self.cash_value!r}."
            )
        if self.cash_pct is not None and not (0.0 <= self.cash_pct <= 1.0):
            raise ValueError(
                f"cash_pct must be between 0 and 1 if provided; got {self.cash_pct!r}."
            )
        return self


class AllocationPositionSnapshot(BaseModel):
    """
    Position snapshot for Phase 3R-C allocation agent.

    Represents one position in the portfolio for allocation calculation.
    current_position_value and current_allocation_pct may be provided
    by the caller or left None; the builder derives them from shares and price.

    Caller-provided mock/non-live data only.

    Validation:
      - shares must be >= 0.
      - current_price must be > 0.
      - cost_basis non-negative if present.
    """

    model_config = ConfigDict(extra="forbid")

    position_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    shares: float = Field(ge=0.0)
    current_price: float = Field(gt=0.0)
    cost_basis: Optional[float] = None
    current_position_value: Optional[float] = None
    current_allocation_pct: Optional[float] = None
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> "AllocationPositionSnapshot":
        if self.position_id.strip() == "":
            raise ValueError("position_id must not be whitespace-only.")
        if self.ticker.strip() == "":
            raise ValueError("ticker must not be whitespace-only.")
        if self.cost_basis is not None and self.cost_basis < 0:
            raise ValueError(
                f"cost_basis must be >= 0 if provided; got {self.cost_basis!r}."
            )
        if self.current_position_value is not None and self.current_position_value < 0:
            raise ValueError(
                f"current_position_value must be >= 0 if provided; "
                f"got {self.current_position_value!r}."
            )
        return self


class AllocationTargetSpec(BaseModel):
    """
    Allocation target specification for Phase 3R-C allocation agent.

    Research-only advisory target. NOT an executable order.

    Validation:
      - target_allocation_pct between 0 and 1.
      - min_allocation_pct <= target_allocation_pct <= max_allocation_pct
        when all bounds are present.
    """

    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    target_allocation_pct: float = Field(ge=0.0, le=1.0)
    min_allocation_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_allocation_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rationale: str = ""
    evidence_quality: AllocationEvidenceQuality = "unknown"
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> "AllocationTargetSpec":
        if self.target_id.strip() == "":
            raise ValueError("target_id must not be whitespace-only.")
        if self.ticker.strip() == "":
            raise ValueError("ticker must not be whitespace-only.")
        t = self.target_allocation_pct
        if self.min_allocation_pct is not None and self.min_allocation_pct > t:
            raise ValueError(
                f"min_allocation_pct ({self.min_allocation_pct}) must be "
                f"<= target_allocation_pct ({t})."
            )
        if self.max_allocation_pct is not None and self.max_allocation_pct < t:
            raise ValueError(
                f"max_allocation_pct ({self.max_allocation_pct}) must be "
                f">= target_allocation_pct ({t})."
            )
        return self


class RiskBudgetConstraint(BaseModel):
    """
    Risk budget constraint for Phase 3R-C allocation agent.

    Research-only advisory constraint. NOT an executable limit or stop order.

    Validation:
      - pct values between 0 and 1 if present.
      - stop_price non-negative if present.
    """

    model_config = ConfigDict(extra="forbid")

    constraint_id: str = Field(min_length=1)
    constraint_type: AllocationConstraintType = "unknown"
    max_position_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_portfolio_loss_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    min_cash_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    stop_price: Optional[float] = None
    risk_level: AllocationRiskLevel = "unknown"
    rationale: str = ""
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> "RiskBudgetConstraint":
        if self.constraint_id.strip() == "":
            raise ValueError("constraint_id must not be whitespace-only.")
        if self.stop_price is not None and self.stop_price < 0:
            raise ValueError(
                f"stop_price must be >= 0 if provided; got {self.stop_price!r}."
            )
        return self


class AllocationCalculation(BaseModel):
    """
    Deterministic calculated allocation metrics for one position.

    All values are computed from caller-provided mock inputs using
    Roadmap v4 formulas. No live data, no network calls, no LLM calls.

    Fields:
      current_position_value  — shares × current_price (or provided value)
      current_allocation_pct  — position_value / total_portfolio_value
      target_position_value   — target_pct × total_portfolio_value
      required_trade_value    — target - current (positive=add, negative=trim)
      required_shares         — required_trade_value / current_price
      action_type             — inferred from required_trade_value
      cash_impact             — = -required_trade_value
      projected_cash_value    — cash_value + cash_impact (if cash_value provided)
      projected_cash_pct      — projected_cash_value / total_portfolio_value
      max_loss_at_stop        — shares × max(entry_price - stop_price, 0)
      portfolio_loss_pct      — max_loss_at_stop / total_portfolio_value
      constraint_violations   — list of violated constraint descriptions
    """

    model_config = ConfigDict(extra="forbid")

    current_position_value: float = Field(ge=0.0)
    current_allocation_pct: float = Field(ge=0.0)
    target_position_value: float = Field(ge=0.0)
    required_trade_value: float  # May be negative (trim/exit)
    required_shares: float       # May be negative (trim/exit)
    action_type: AllocationActionType = "unknown"
    cash_impact: float           # = -required_trade_value
    projected_cash_value: Optional[float] = None
    projected_cash_pct: Optional[float] = None
    max_loss_at_stop: Optional[float] = Field(default=None, ge=0.0)
    portfolio_loss_pct: Optional[float] = Field(default=None, ge=0.0)
    constraint_violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class AllocationAssessment(BaseModel):
    """
    Allocation assessment for one ticker position.

    Combines deterministic calculation with risk assessment.
    Research-only output; does NOT authorize execution.
    approved_for_execution is ALWAYS False.
    """

    model_config = ConfigDict(extra="forbid")

    assessment_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    calculation: AllocationCalculation
    recommendation_action: AllocationActionType = "unknown"
    risk_level: AllocationRiskLevel = "unknown"
    constraint_violations: list[str] = Field(default_factory=list)
    review_required: bool = False
    rationale: str = ""
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "AllocationAssessment":
        for fn in ("assessment_id", "ticker"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "AllocationAssessment":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-C. "
                "This layer does not authorize execution."
            )
        return self


class AllocationInputBundle(BaseModel):
    """
    Input context bundle for one allocation calculation pass.

    Holds portfolio/position/target data and optional prior-phase research
    artifacts for evidence tracing. All data is caller-provided mock/non-live
    only. No live portfolio data, brokerage data, or external API.

    This bundle is research context only. No execution authorization.
    Missing optional prior artifacts produce warnings, not crashes.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    as_of: str = ""
    portfolio_snapshot: AllocationPortfolioSnapshot
    position_snapshot: AllocationPositionSnapshot
    allocation_target: AllocationTargetSpec
    risk_constraints: list[RiskBudgetConstraint] = Field(default_factory=list)
    trade_plan_report: Optional[Any] = None
    decision_packet: Optional[Any] = None
    human_review_report: Optional[Any] = None
    validation_aggregate: Optional[Any] = None
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "AllocationInputBundle":
        v = self.target
        if not v.strip():
            raise ValueError(f"'target' must not be whitespace-only; got {v!r}.")
        return self


class AllocationSummary(BaseModel):
    """
    Concise deterministic summary of one allocation report.

    Computed from AllocationAssessment and resolved status.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    status: AllocationStatus = "unknown"
    action_type: AllocationActionType = "unknown"
    current_allocation_pct: float = 0.0
    target_allocation_pct: float = 0.0
    required_trade_value: float = 0.0
    required_shares: float = 0.0
    cash_impact: float = 0.0
    projected_cash_pct: Optional[float] = None
    portfolio_loss_pct: Optional[float] = None
    constraint_violation_count: int = 0
    review_required: bool = False
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "AllocationSummary":
        v = self.target
        if not v.strip():
            raise ValueError(f"'target' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "AllocationSummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-C. "
                "This layer does not authorize execution."
            )
        return self


class AllocationReport(BaseModel):
    """
    Full allocation assessment report for one analysis pass.

    Composes all allocation results into a single auditable research artifact.

    approved_for_execution is ALWAYS False. This report is a research
    artifact only and does not constitute investment advice or authorize
    any form of execution. No pathway to approve execution exists in
    Phase 3R-C.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    report_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    target: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: AllocationStatus = "unknown"
    input_bundle: AllocationInputBundle
    assessment: AllocationAssessment
    summary: AllocationSummary
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "AllocationReport":
        for fn in ("report_id", "target", "run_id", "created_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "AllocationReport":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-C. "
                "This layer does not authorize execution."
            )
        return self


# ---------------------------------------------------------------------------
# Calculator functions (Roadmap v4 formulas)
# ---------------------------------------------------------------------------

def calculate_position_value(shares: float, current_price: float) -> float:
    """
    Compute position value = shares × current_price.

    Args:
        shares:        Number of shares (>= 0).
        current_price: Price per share (> 0).

    Returns:
        Position value as a float.

    Raises:
        ValueError: If shares < 0 or current_price <= 0.
    """
    if shares < 0:
        raise ValueError(f"shares must be >= 0; got {shares!r}.")
    if current_price <= 0:
        raise ValueError(f"current_price must be > 0; got {current_price!r}.")
    return shares * current_price


def calculate_allocation_pct(
    position_value: float,
    total_portfolio_value: float,
) -> float:
    """
    Compute allocation percentage = position_value / total_portfolio_value.

    Args:
        position_value:        Market value of the position (>= 0).
        total_portfolio_value: Total portfolio value (> 0).

    Returns:
        Allocation fraction (0.0–1.0+).

    Raises:
        ValueError: If total_portfolio_value <= 0 or position_value < 0.
    """
    if total_portfolio_value <= 0:
        raise ValueError(
            f"total_portfolio_value must be > 0; got {total_portfolio_value!r}."
        )
    if position_value < 0:
        raise ValueError(f"position_value must be >= 0; got {position_value!r}.")
    return position_value / total_portfolio_value


def calculate_target_position_value(
    target_allocation_pct: float,
    total_portfolio_value: float,
) -> float:
    """
    Compute target position value = target_allocation_pct × total_portfolio_value.

    Args:
        target_allocation_pct: Target fraction of portfolio (0.0–1.0).
        total_portfolio_value: Total portfolio value (> 0).

    Returns:
        Target position value as a float.

    Raises:
        ValueError: If target_allocation_pct < 0 or > 1, or
                    total_portfolio_value <= 0.
    """
    if total_portfolio_value <= 0:
        raise ValueError(
            f"total_portfolio_value must be > 0; got {total_portfolio_value!r}."
        )
    if not (0.0 <= target_allocation_pct <= 1.0):
        raise ValueError(
            f"target_allocation_pct must be between 0 and 1; "
            f"got {target_allocation_pct!r}."
        )
    return target_allocation_pct * total_portfolio_value


def calculate_required_trade_value(
    target_position_value: float,
    current_position_value: float,
) -> float:
    """
    Compute required trade value = target - current.

    Positive result means buy (add/enter).
    Negative result means sell (trim/exit).
    Near-zero result means hold/no_action.

    Args:
        target_position_value:  Target position market value.
        current_position_value: Current position market value.

    Returns:
        Required trade value (may be negative).
    """
    return target_position_value - current_position_value


def calculate_required_shares(
    required_trade_value: float,
    current_price: float,
) -> float:
    """
    Compute required shares = required_trade_value / current_price.

    Positive = shares to buy. Negative = shares to sell.

    Args:
        required_trade_value: From calculate_required_trade_value (may be negative).
        current_price:        Current market price per share (> 0).

    Returns:
        Required shares (may be negative).

    Raises:
        ValueError: If current_price <= 0.
    """
    if current_price <= 0:
        raise ValueError(f"current_price must be > 0; got {current_price!r}.")
    return required_trade_value / current_price


def calculate_max_loss_at_stop(
    shares: float,
    entry_price: float,
    stop_price: float,
) -> float:
    """
    Compute maximum loss at stop = max(entry_price - stop_price, 0) × shares.

    When stop_price >= entry_price, the max loss is 0 (no downside).

    Args:
        shares:       Shares held (>= 0).
        entry_price:  Price at which the loss is measured (>= 0).
        stop_price:   Stop-loss trigger price (>= 0).

    Returns:
        Maximum loss amount (>= 0).

    Raises:
        ValueError: If shares < 0, entry_price < 0, or stop_price < 0.
    """
    if shares < 0:
        raise ValueError(f"shares must be >= 0; got {shares!r}.")
    if entry_price < 0:
        raise ValueError(f"entry_price must be >= 0; got {entry_price!r}.")
    if stop_price < 0:
        raise ValueError(f"stop_price must be >= 0; got {stop_price!r}.")
    return max(entry_price - stop_price, 0.0) * shares


def calculate_portfolio_loss_pct(
    max_loss: float,
    total_portfolio_value: float,
) -> float:
    """
    Compute portfolio loss percentage = max_loss / total_portfolio_value.

    Args:
        max_loss:              Maximum loss amount (>= 0).
        total_portfolio_value: Total portfolio value (> 0).

    Returns:
        Portfolio loss as a fraction (>= 0).

    Raises:
        ValueError: If total_portfolio_value <= 0 or max_loss < 0.
    """
    if total_portfolio_value <= 0:
        raise ValueError(
            f"total_portfolio_value must be > 0; got {total_portfolio_value!r}."
        )
    if max_loss < 0:
        raise ValueError(f"max_loss must be >= 0; got {max_loss!r}.")
    return max_loss / total_portfolio_value


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _infer_action_type(
    required_trade_value: float,
    current_position_value: float,
    target_position_value: float,
    tolerance: float,
) -> AllocationActionType:
    """
    Infer AllocationActionType from trade value metrics.

    Priority order:
      exit      — target ≈ 0 AND current position > 0
      hold      — abs(required) < tolerance AND current position > 0
      no_action — abs(required) < tolerance AND current position ≈ 0
      add       — required > tolerance
      trim      — required < -tolerance
    """
    if target_position_value < tolerance and current_position_value > tolerance:
        return "exit"
    if abs(required_trade_value) < tolerance:
        if current_position_value < tolerance:
            return "no_action"
        return "hold"
    if required_trade_value > 0:
        return "add"
    return "trim"


def _check_constraint_violations(
    constraint: RiskBudgetConstraint,
    target_allocation_pct: float,
    portfolio_loss_pct: Optional[float],
    projected_cash_pct: Optional[float],
) -> list[str]:
    """
    Check one constraint and return a list of violation description strings.

    Checks are numeric where a threshold is present.
    human_review_block always generates a violation.
    Other constraint types (sector_exposure, liquidity, volatility,
    thesis_confidence) are advisory only — flagged as warnings elsewhere.
    """
    violations: list[str] = []
    ct = constraint.constraint_type

    if ct == "human_review_block":
        violations.append(
            f"RiskBudgetConstraint '{constraint.constraint_id}': "
            "constraint_type='human_review_block' — allocation blocked "
            "pending human review."
        )
    elif ct == "max_position_pct" and constraint.max_position_pct is not None:
        if target_allocation_pct > constraint.max_position_pct:
            violations.append(
                f"RiskBudgetConstraint '{constraint.constraint_id}': "
                f"target_allocation_pct ({target_allocation_pct:.4f}) exceeds "
                f"max_position_pct ({constraint.max_position_pct:.4f})."
            )
    elif ct == "max_portfolio_loss_pct" and constraint.max_portfolio_loss_pct is not None:
        if (
            portfolio_loss_pct is not None
            and portfolio_loss_pct > constraint.max_portfolio_loss_pct
        ):
            violations.append(
                f"RiskBudgetConstraint '{constraint.constraint_id}': "
                f"portfolio_loss_pct ({portfolio_loss_pct:.4f}) exceeds "
                f"max_portfolio_loss_pct ({constraint.max_portfolio_loss_pct:.4f})."
            )
    elif ct == "min_cash_pct" and constraint.min_cash_pct is not None:
        if (
            projected_cash_pct is not None
            and projected_cash_pct < constraint.min_cash_pct
        ):
            violations.append(
                f"RiskBudgetConstraint '{constraint.constraint_id}': "
                f"projected_cash_pct ({projected_cash_pct:.4f}) is below "
                f"min_cash_pct ({constraint.min_cash_pct:.4f})."
            )

    return violations


def _infer_risk_level(constraint_violations: list[str]) -> AllocationRiskLevel:
    """Infer AllocationRiskLevel from constraint violations."""
    if not constraint_violations:
        return "low"
    if any(
        "human_review_block" in v or "max_portfolio_loss_pct" in v
        for v in constraint_violations
    ):
        return "high"
    return "medium"


def _generate_allocation_warnings(
    input_bundle: AllocationInputBundle,
) -> list[str]:
    """
    Generate derived warnings for missing optional prior artifacts.

    Returns ONLY newly generated warnings — does NOT include bundle.warnings.
    Callers are responsible for combining with bundle.warnings when assembling
    the final report.warnings list.

    Does not crash on missing optional artifacts. Does not mutate inputs.
    """
    generated: list[str] = []
    if input_bundle.trade_plan_report is None:
        generated.append(
            "AllocationInputBundle: trade_plan_report is missing. "
            "Allocation context may lack trade plan rationale."
        )
    if input_bundle.decision_packet is None:
        generated.append(
            "AllocationInputBundle: decision_packet is missing. "
            "Allocation context may lack decision rationale."
        )
    if not input_bundle.risk_constraints:
        generated.append(
            "AllocationInputBundle: no risk_constraints provided. "
            "Constraint violation checks are skipped."
        )
    return generated


# ---------------------------------------------------------------------------
# Helper: deterministic ID generator
# ---------------------------------------------------------------------------

def make_allocation_report_id(
    run_id: str,
    target: str,
    as_of: str,
) -> str:
    """Return a deterministic stable hash ID for an AllocationReport."""
    payload = {"run_id": run_id, "target": target, "as_of": as_of}
    h = stable_hash_payload(payload, length=16)
    return f"alr_{h}"


# ---------------------------------------------------------------------------
# Helper: status determination
# ---------------------------------------------------------------------------

def determine_allocation_status(
    assessment: AllocationAssessment,
    human_review_report: Any = None,
) -> AllocationStatus:
    """
    Derive AllocationStatus from assessment and optional human review report.

    Priority (highest wins):
      blocked      — human_review_report.status == "blocked"
                   — OR any constraint violation contains "human_review_block"
      needs_review — any constraint violations exist
                   — OR risk_level == "high"
      complete     — no violations, valid (non-unknown) action
      unknown      — action_type == "unknown" (insufficient data)

    Does not mutate any input. No network calls. No LLM calls.
    approved_for_execution is never implied by any status value.
    """
    # blocked: human review says blocked
    if human_review_report is not None:
        hr_status = getattr(human_review_report, "status", None)
        if hr_status == "blocked":
            return "blocked"

    # blocked: human_review_block constraint violation
    if any("human_review_block" in v for v in assessment.constraint_violations):
        return "blocked"

    # needs_review: constraint violations exist
    if assessment.constraint_violations:
        return "needs_review"

    # needs_review: high risk level
    if assessment.risk_level == "high":
        return "needs_review"

    # unknown: action type is unknown (insufficient data)
    if assessment.recommendation_action == "unknown":
        return "unknown"

    # complete: passed all checks above
    return "complete"


# ---------------------------------------------------------------------------
# Helper: source ID collection
# ---------------------------------------------------------------------------

def collect_allocation_source_ids(
    input_bundle: AllocationInputBundle,
    assessment: AllocationAssessment,
) -> list[str]:
    """
    Collect all source/evidence IDs from the input bundle and assessment.

    Collection order:
      1. Bundle-level source_ids.
      2. Portfolio snapshot source_ids.
      3. Position snapshot source_ids.
      4. Allocation target source_ids.
      5. Risk constraints source_ids (in order).
      6. Assessment source_ids.
      7. Calculation source_ids.

    Deduplicates preserving first-occurrence order.
    Does not mutate any input.
    """
    seen: set[str] = set()
    ids: list[str] = []

    def _add(eid: str) -> None:
        if eid and eid not in seen:
            seen.add(eid)
            ids.append(eid)

    for sid in input_bundle.source_ids:
        _add(sid)
    for sid in input_bundle.portfolio_snapshot.source_ids:
        _add(sid)
    for sid in input_bundle.position_snapshot.source_ids:
        _add(sid)
    for sid in input_bundle.allocation_target.source_ids:
        _add(sid)
    for rc in input_bundle.risk_constraints:
        for sid in rc.source_ids:
            _add(sid)
    for sid in assessment.source_ids:
        _add(sid)
    for sid in assessment.calculation.source_ids:
        _add(sid)

    return ids


# ---------------------------------------------------------------------------
# Helper: allocation calculation builder
# ---------------------------------------------------------------------------

def build_allocation_calculation(
    portfolio_snapshot: AllocationPortfolioSnapshot,
    position_snapshot: AllocationPositionSnapshot,
    allocation_target: AllocationTargetSpec,
    risk_constraints: list[RiskBudgetConstraint],
) -> AllocationCalculation:
    """
    Build a deterministic AllocationCalculation from input snapshots.

    Applies Roadmap v4 formulas:
      current_position_value  = shares × current_price
      current_allocation_pct  = position_value / total_portfolio_value
      target_position_value   = target_allocation_pct × total_portfolio_value
      required_trade_value    = target_position_value - current_position_value
      required_shares         = required_trade_value / current_price
      cash_impact             = -required_trade_value

    Also computes:
      projected_cash_value/pct — if portfolio.cash_value is provided
      max_loss_at_stop/portfolio_loss_pct — from first constraint with stop_price
      constraint_violations — for all applicable constraints

    Deterministic: identical inputs → identical outputs.
    No network calls. No LLM calls. No mutation of inputs.
    """
    total_pv = portfolio_snapshot.total_portfolio_value
    tolerance = _ACTION_TOLERANCE_FRACTION * total_pv

    # Current position value (prefer provided, fallback to formula)
    if position_snapshot.current_position_value is not None:
        current_pv = position_snapshot.current_position_value
    else:
        current_pv = calculate_position_value(
            position_snapshot.shares, position_snapshot.current_price
        )

    # Current allocation pct
    current_alloc = calculate_allocation_pct(current_pv, total_pv)

    # Target position value
    target_pv = calculate_target_position_value(
        allocation_target.target_allocation_pct, total_pv
    )

    # Required trade and shares
    req_trade = calculate_required_trade_value(target_pv, current_pv)
    req_shares = calculate_required_shares(req_trade, position_snapshot.current_price)
    cash_impact = -req_trade

    # Infer action type
    action_type = _infer_action_type(req_trade, current_pv, target_pv, tolerance)

    # Projected cash values (only when portfolio has cash_value)
    projected_cash_value: Optional[float] = None
    projected_cash_pct: Optional[float] = None
    if portfolio_snapshot.cash_value is not None:
        projected_cash_value = portfolio_snapshot.cash_value + cash_impact
        projected_cash_pct = projected_cash_value / total_pv

    # Max loss at stop (from first constraint that provides stop_price)
    max_loss_at_stop: Optional[float] = None
    portfolio_loss_pct: Optional[float] = None
    for rc in risk_constraints:
        if rc.stop_price is not None:
            entry_price = (
                position_snapshot.cost_basis
                if position_snapshot.cost_basis is not None
                else position_snapshot.current_price
            )
            max_loss_at_stop = calculate_max_loss_at_stop(
                position_snapshot.shares, entry_price, rc.stop_price
            )
            portfolio_loss_pct = calculate_portfolio_loss_pct(
                max_loss_at_stop, total_pv
            )
            break

    # Constraint violations
    all_violations: list[str] = []
    for rc in risk_constraints:
        violations = _check_constraint_violations(
            rc,
            allocation_target.target_allocation_pct,
            portfolio_loss_pct,
            projected_cash_pct,
        )
        all_violations.extend(violations)

    # Collect source IDs from all input objects
    seen_sids: set[str] = set()
    calc_source_ids: list[str] = []

    def _add_sid(sid: str) -> None:
        if sid and sid not in seen_sids:
            seen_sids.add(sid)
            calc_source_ids.append(sid)

    for sid in portfolio_snapshot.source_ids:
        _add_sid(sid)
    for sid in position_snapshot.source_ids:
        _add_sid(sid)
    for sid in allocation_target.source_ids:
        _add_sid(sid)
    for rc in risk_constraints:
        for sid in rc.source_ids:
            _add_sid(sid)

    # Calculation-level warnings
    calc_warnings: list[str] = []
    if position_snapshot.shares == 0 and action_type in _ACTIVE_ACTION_TYPES:
        calc_warnings.append(
            f"AllocationPositionSnapshot '{position_snapshot.position_id}': "
            "shares=0 but action_type implies trading. Verify position data."
        )

    return AllocationCalculation(
        current_position_value=current_pv,
        current_allocation_pct=current_alloc,
        target_position_value=target_pv,
        required_trade_value=req_trade,
        required_shares=req_shares,
        action_type=action_type,
        cash_impact=cash_impact,
        projected_cash_value=projected_cash_value,
        projected_cash_pct=projected_cash_pct,
        max_loss_at_stop=max_loss_at_stop,
        portfolio_loss_pct=portfolio_loss_pct,
        constraint_violations=all_violations,
        warnings=calc_warnings,
        source_ids=calc_source_ids,
    )


# ---------------------------------------------------------------------------
# Helper: main report builder
# ---------------------------------------------------------------------------

def build_allocation_report(
    input_bundle: AllocationInputBundle,
    run_id: str,
    created_at: Optional[str] = None,
) -> AllocationReport:
    """
    Build a complete AllocationReport from the input bundle.

    Steps:
      1. Build AllocationCalculation from portfolio/position/target/constraints.
      2. Infer risk level and review_required from constraint violations.
      3. Build AllocationAssessment.
      4. Extract human_review_report for status determination.
      5. Generate derived warnings for missing optional artifacts.
      6. Assemble full report warnings (bundle + generated + calc), deduplicated.
      7. Collect source IDs deterministically.
      8. Determine status.
      9. Build AllocationSummary.
     10. Build AllocationReport with stable deterministic report_id.

    Deterministic: identical inputs → identical outputs.
    created_at defaults to input_bundle.as_of (or run_id if empty), making
    the full report output deterministic without an explicit timestamp argument.
    Pass created_at explicitly to override (e.g. for tests or audit records).

    No network calls. No LLM calls. No mutation of inputs.
    approved_for_execution is always False.
    """
    # 1. Build calculation
    calculation = build_allocation_calculation(
        portfolio_snapshot=input_bundle.portfolio_snapshot,
        position_snapshot=input_bundle.position_snapshot,
        allocation_target=input_bundle.allocation_target,
        risk_constraints=input_bundle.risk_constraints,
    )

    # 2. Risk level and review_required
    risk_level = _infer_risk_level(calculation.constraint_violations)
    review_required = (
        risk_level in ("high", "medium") or bool(calculation.constraint_violations)
    )

    # 3. Build assessment
    _assessment_payload = {
        "run_id": run_id,
        "target": input_bundle.target,
        "as_of": input_bundle.as_of,
        "action_type": calculation.action_type,
    }
    assessment_id = "ast_" + stable_hash_payload(_assessment_payload, length=16)

    assessment = AllocationAssessment(
        assessment_id=assessment_id,
        ticker=input_bundle.allocation_target.ticker,
        calculation=calculation,
        recommendation_action=calculation.action_type,
        risk_level=risk_level,
        constraint_violations=list(calculation.constraint_violations),
        review_required=review_required,
        rationale=input_bundle.allocation_target.rationale,
        source_ids=list(calculation.source_ids),
        warnings=list(calculation.warnings),
        approved_for_execution=False,
    )

    # 4. Human review report for status
    human_review_report = input_bundle.human_review_report

    # 5. Generated warnings for missing optional artifacts
    generated_warnings = _generate_allocation_warnings(input_bundle)

    # 6. Full report warnings (bundle + generated + calc), deduplicated
    _raw_report_warnings = (
        list(input_bundle.warnings) + generated_warnings + list(calculation.warnings)
    )
    seen_rw: set[str] = set()
    report_warnings: list[str] = []
    for w in _raw_report_warnings:
        if w not in seen_rw:
            seen_rw.add(w)
            report_warnings.append(w)

    # 7. Source IDs
    source_ids = collect_allocation_source_ids(input_bundle, assessment)

    # 8. Status
    status = determine_allocation_status(assessment, human_review_report)

    # 9. Summary — top_warnings from assessment + bundle + generated, deduped, first 5
    _summary_warnings = (
        list(assessment.warnings)
        + list(input_bundle.warnings)
        + generated_warnings
    )
    seen_sw: set[str] = set()
    deduped_sw: list[str] = []
    for w in _summary_warnings:
        if w not in seen_sw:
            seen_sw.add(w)
            deduped_sw.append(w)

    summary = AllocationSummary(
        target=input_bundle.target,
        status=status,
        action_type=calculation.action_type,
        current_allocation_pct=calculation.current_allocation_pct,
        target_allocation_pct=input_bundle.allocation_target.target_allocation_pct,
        required_trade_value=calculation.required_trade_value,
        required_shares=calculation.required_shares,
        cash_impact=calculation.cash_impact,
        projected_cash_pct=calculation.projected_cash_pct,
        portfolio_loss_pct=calculation.portfolio_loss_pct,
        constraint_violation_count=len(calculation.constraint_violations),
        review_required=review_required,
        top_warnings=deduped_sw[:5],
        approved_for_execution=False,
    )

    # 10. Report ID (deterministic)
    _as_of = input_bundle.as_of or run_id
    report_id = make_allocation_report_id(run_id, input_bundle.target, _as_of)
    _created_at = created_at if created_at is not None else _as_of

    return AllocationReport(
        report_id=report_id,
        target=input_bundle.target,
        run_id=run_id,
        status=status,
        input_bundle=input_bundle,
        assessment=assessment,
        summary=summary,
        source_ids=source_ids,
        warnings=report_warnings,
        created_at=_created_at,
        calculation_version=_CALCULATION_VERSION,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Helper: report summary
# ---------------------------------------------------------------------------

def summarize_allocation_report(report: AllocationReport) -> dict[str, Any]:
    """
    Return a concise summary dict of one AllocationReport.

    Returns:
        A dict with report_id, target, status, action_type, key metrics,
        constraint_violation_count, review_required, warning_count,
        source_id_count, calculation_version, and approved_for_execution.

    Does not mutate report. Deterministic.
    """
    return {
        "report_id": report.report_id,
        "target": report.target,
        "status": report.status,
        "action_type": report.summary.action_type,
        "current_allocation_pct": report.summary.current_allocation_pct,
        "target_allocation_pct": report.summary.target_allocation_pct,
        "required_trade_value": report.summary.required_trade_value,
        "required_shares": report.summary.required_shares,
        "cash_impact": report.summary.cash_impact,
        "projected_cash_pct": report.summary.projected_cash_pct,
        "portfolio_loss_pct": report.summary.portfolio_loss_pct,
        "constraint_violation_count": report.summary.constraint_violation_count,
        "review_required": report.summary.review_required,
        "warning_count": len(report.warnings),
        "source_id_count": len(report.source_ids),
        "calculation_version": report.calculation_version,
        "approved_for_execution": False,
    }


# ---------------------------------------------------------------------------
# ToolResult adapter
# ---------------------------------------------------------------------------

def allocation_report_tool_result_from_report(
    run_id: str,
    report: AllocationReport,
    target: Optional[str] = None,
    calculation_version: str = _CALCULATION_VERSION,
) -> ToolResult:
    """
    Wrap an AllocationReport as a ToolResult for evidence-aware pipelines.

    - tool_name is stable: "allocation_report".
    - target defaults to report.target.
    - outputs includes full report (serialized), summary, calculation_version.
    - evidence_id is deterministic and content-sensitive.
    - Does not mutate report.
    - approved_for_execution is always False in the payload.
    - No live execution implication.
    - Does not look like an order ticket; contains no order_id, broker_order,
      account_id, execution_status, or live order instruction.
    """
    _target: str = target or report.target

    _report_dict = report.model_dump()
    _summary_dict: dict[str, Any] = {
        "report_id": report.report_id,
        "target": report.target,
        "run_id": report.run_id,
        "status": report.status,
        "action_type": report.summary.action_type,
        "current_allocation_pct": report.summary.current_allocation_pct,
        "target_allocation_pct": report.summary.target_allocation_pct,
        "required_trade_value": report.summary.required_trade_value,
        "required_shares": report.summary.required_shares,
        "cash_impact": report.summary.cash_impact,
        "constraint_violation_count": report.summary.constraint_violation_count,
        "review_required": report.summary.review_required,
        "warning_count": len(report.warnings),
        "source_id_count": len(report.source_ids),
        "approved_for_execution": False,
    }

    outputs: dict[str, Any] = {
        "report": _report_dict,
        "summary": _summary_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_ALLOCATION_REPORT_TOOL_NAME,
        target=_target,
        metric_group=_ALLOCATION_REPORT_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_ALLOCATION_REPORT_TOOL_NAME,
        run_id=run_id,
        ticker=report.target if report.target else None,
        inputs={"as_of": report.input_bundle.as_of, "target": _target},
        outputs=outputs,
        description=(
            f"AllocationReport for {report.target}: "
            f"status={report.status}, "
            f"action={report.summary.action_type}, "
            f"required_trade={report.summary.required_trade_value:.2f}, "
            f"violations={report.summary.constraint_violation_count}, "
            f"review_required={report.summary.review_required}, "
            f"source_ids={len(report.source_ids)}, "
            f"warnings={len(report.warnings)}."
        ),
    )
