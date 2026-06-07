"""
lib/reliability/option_expression.py

Phase 3R-D: Option Expression Agent v0.1 Non-live.

Design principles:
  - Standalone, deterministic, offline/mock-only.
  - No live LLM calls, no live data fetching, no app integration.
  - No broker / order / brokerage / execution behavior.
  - Consumes typed mock inputs (market snapshot, candidate strategies, optional
    prior-phase artifacts) from caller.
  - Produces structured OptionExpressionReport for research/review purposes only.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice or individual security recommendations.
  - Does NOT connect to option-chain APIs, brokerage, or any external API.
  - approved_for_execution is ALWAYS False. No pathway to set it True exists.
  - Mock/dry-run only; all outputs are explicitly evidence-aware and auditable.
  - Missing optional prior artifacts produce warnings, not crashes.
  - No mutation of input artifacts.

Relationship to Roadmap v4 Phase 3J:
  - Phase 3R-D implements the Option Expression Agent v0.1 skeleton specified
    in Roadmap v4 Phase 3J.
  - Option Agent expresses an already validated thesis — it does NOT decide
    the thesis.
  - Option Agent does NOT decide total portfolio allocation.
  - Option Agent does NOT override Allocation Agent.
  - Option Agent does NOT generate broker-ready orders.
  - no_trade is a valid and often preferred output.
  - All option payoff/breakeven/risk-reward outputs are research references only.
    They are NOT executable orders.
  - approved_for_execution is permanently False (schema-enforced).
  - This phase does NOT authorize trading or execution of any kind.

Relationship to Phase 2E (options.py):
  - Phase 2E provides primitive option chain/strategy schemas and payoff calculators:
    OptionContractSnapshot, OptionChainSnapshot, OptionStrategyType, OptionLeg,
    OptionStrategyCandidate, OptionPayoffResult, etc.
  - Phase 3R-D provides a higher-level agent-output layer:
    OptionExpressionLeg, OptionMarketSnapshot, OptionStrategyCalculation,
    OptionExpressionCandidate, OptionExpressionInputBundle, OptionExpressionAssessment,
    OptionExpressionSummary, OptionExpressionReport.
  - Phase 3R-D calculators operate on raw float inputs (not Phase 2E objects)
    to support the Roadmap v4 Phase 3J formula specification.
  - Phase 3R-D defines its own local Literal type aliases so the module
    is self-contained and does not re-export Phase 2E names.

Roadmap v4 formulas implemented:
  long_call_breakeven          = strike + premium
  long_put_breakeven           = strike - premium
  long_option_max_loss         = premium × contracts × 100
  call_debit_spread_max_loss   = net_debit × contracts × 100
  call_debit_spread_max_gain   = (spread_width − net_debit) × contracts × 100
  put_debit_spread_breakeven   = long_put_strike − net_debit
  put_debit_spread_max_loss    = net_debit × contracts × 100
  cash_secured_put_cash_req    = strike × contracts × 100
  cash_secured_put_breakeven   = strike − premium
  covered_call_effective_sale  = strike + premium
  covered_call_upside_cap      = strike − stock_cost_basis + premium
  risk_reward_ratio            = max_gain / max_loss  (handles undefined max_loss)

Phase 3R-D is part of the Roadmap v4 Phase 3 backfill sequence.

See docs/reliability_phase_3r_option_expression.md for design.

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
# Literal type aliases
# ---------------------------------------------------------------------------

OptionExpressionStatus = Literal[
    "unknown",
    "complete",
    "needs_review",
    "blocked",
]

OptionExpressionDecision = Literal[
    "stock",
    "option",
    "no_trade",
    "wait",
    "unknown",
]

OptionExpressionStrategyType = Literal[
    "long_call",
    "long_put",
    "call_debit_spread",
    "put_debit_spread",
    "cash_secured_put",
    "covered_call",
    "stock",
    "no_trade",
    "unknown",
]

# Inherent risk level of an option strategy (includes "undefined" for cases
# where max_loss cannot be computed from available inputs).
OptionRiskLevel = Literal[
    "low",
    "medium",
    "high",
    "undefined",
    "unknown",
]

# Liquidity classification for option expression purposes.
# Uses "poor/acceptable/good" to distinguish from Phase 2E's "liquid/acceptable/illiquid".
OptionLiquidityLevel = Literal[
    "poor",
    "acceptable",
    "good",
    "unknown",
]

# Event risk classification local to Phase 3R-D.
OptionExpressionEventRiskLevel = Literal[
    "low",
    "medium",
    "high",
    "unknown",
]

OptionEvidenceQuality = Literal[
    "unsupported",
    "weak",
    "adequate",
    "strong",
    "unknown",
]

OptionNoTradeReason = Literal[
    "thesis_not_validated",
    "allocation_not_approved",
    "event_risk_too_high",
    "liquidity_too_poor",
    "spread_too_wide",
    "risk_reward_unfavorable",
    "max_loss_too_high",
    "expiration_mismatch",
    "missing_required_inputs",
    "unknown",
]

# Used within OptionExpressionLeg — named separately to avoid clash with
# Phase 2E's OptionType = Literal["call", "put"].
OptionLegType = Literal[
    "call",
    "put",
    "stock",
    "unknown",
]

OptionLegSide = Literal[
    "long",
    "short",
    "none",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_OPTION_EXPRESSION_TOOL_NAME: str = "option_expression_report"
_OPTION_EXPRESSION_METRIC_GROUP: str = "option_expression_report"
_CALCULATION_VERSION: str = "option_expression_v1"

_ADEQUATE_EVIDENCE: frozenset[str] = frozenset({"adequate", "strong"})
_REAL_STRATEGY_TYPES: frozenset[str] = frozenset({
    "long_call", "long_put", "call_debit_spread", "put_debit_spread",
    "cash_secured_put", "covered_call",
})
_STOCK_STRATEGY_TYPES: frozenset[str] = frozenset({"stock"})

# Default option contract multiplier.
_CONTRACT_MULTIPLIER: int = 100


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class OptionExpressionLeg(BaseModel):
    """
    One leg of an option strategy for Phase 3R-D expression assessment.

    This is a strategy leg model only, NOT an order leg.
    Contains no order_id, account_id, execution_status, or broker fields.
    All values are caller-provided mock/non-live data.

    Validation:
      - strike non-negative if present.
      - premium non-negative if present.
      - contracts non-negative integer if present.
      - underlying_shares non-negative if present.
    """

    model_config = ConfigDict(extra="forbid")

    leg_id: str = Field(min_length=1)
    option_type: OptionLegType = "unknown"
    position_side: OptionLegSide = "unknown"
    strike: Optional[float] = None
    premium: Optional[float] = None
    expiration: Optional[str] = None
    contracts: Optional[int] = None
    underlying_shares: Optional[float] = None
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionExpressionLeg":
        if not self.leg_id.strip():
            raise ValueError("leg_id must not be whitespace-only.")
        if self.strike is not None and self.strike < 0:
            raise ValueError(
                f"strike must be >= 0 if provided; got {self.strike!r}."
            )
        if self.premium is not None and self.premium < 0:
            raise ValueError(
                f"premium must be >= 0 if provided; got {self.premium!r}."
            )
        if self.contracts is not None and self.contracts < 0:
            raise ValueError(
                f"contracts must be >= 0 if provided; got {self.contracts!r}."
            )
        if self.underlying_shares is not None and self.underlying_shares < 0:
            raise ValueError(
                f"underlying_shares must be >= 0 if provided; got {self.underlying_shares!r}."
            )
        return self


class OptionMarketSnapshot(BaseModel):
    """
    Mock option market snapshot for Phase 3R-D expression assessment.

    All data must be caller-provided mock/non-live data.
    No live option-chain data, brokerage data, or external API integration.

    Validation:
      - underlying_price must be positive.
      - iv_rank and bid_ask_spread_pct between 0 and 1 if present.
      - open_interest and volume non-negative if present.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    underlying_price: float = Field(gt=0.0)
    as_of: str = ""
    implied_volatility: Optional[float] = None
    iv_rank: Optional[float] = None
    bid_ask_spread_pct: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    liquidity_level: OptionLiquidityLevel = "unknown"
    event_risk_level: OptionExpressionEventRiskLevel = "unknown"
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionMarketSnapshot":
        if not self.snapshot_id.strip():
            raise ValueError("snapshot_id must not be whitespace-only.")
        if not self.ticker.strip():
            raise ValueError("ticker must not be whitespace-only.")
        if self.iv_rank is not None and not (0.0 <= self.iv_rank <= 1.0):
            raise ValueError(
                f"iv_rank must be between 0 and 1 if provided; got {self.iv_rank!r}."
            )
        if self.bid_ask_spread_pct is not None and not (
            0.0 <= self.bid_ask_spread_pct <= 1.0
        ):
            raise ValueError(
                f"bid_ask_spread_pct must be between 0 and 1 if provided; "
                f"got {self.bid_ask_spread_pct!r}."
            )
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError(
                f"open_interest must be >= 0 if provided; got {self.open_interest!r}."
            )
        if self.volume is not None and self.volume < 0:
            raise ValueError(
                f"volume must be >= 0 if provided; got {self.volume!r}."
            )
        return self


class OptionStrategyCalculation(BaseModel):
    """
    Deterministic calculated option strategy metrics.

    All values are computed from caller-provided mock inputs using Roadmap v4
    formulas. No live data, no network calls, no LLM calls.

    Must NOT contain order_id, account_id, broker_order, or execution fields.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    calculation_id: str = Field(min_length=1)
    strategy_type: OptionExpressionStrategyType = "unknown"
    breakeven: Optional[float] = None
    max_loss: Optional[float] = Field(default=None, ge=0.0)
    max_gain: Optional[float] = Field(default=None, ge=0.0)
    net_debit: Optional[float] = Field(default=None, ge=0.0)
    net_credit: Optional[float] = Field(default=None, ge=0.0)
    cash_required: Optional[float] = Field(default=None, ge=0.0)
    effective_sale_price: Optional[float] = None
    upside_cap: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    warnings: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionStrategyCalculation":
        if not self.calculation_id.strip():
            raise ValueError("calculation_id must not be whitespace-only.")
        return self


class OptionExpressionCandidate(BaseModel):
    """
    One candidate option strategy for Phase 3R-D expression assessment.

    Research-only advisory candidate. NOT an executable order or trade ticket.
    Contains no order_id, account_id, execution_status, or broker fields.
    approved_for_execution is ALWAYS False.

    Validation:
      - If strategy_type == "no_trade", no_trade_reason must be non-empty.
      - If strategy_type != "no_trade" and != "unknown", legs must be non-empty.
      - Setting approved_for_execution to True is rejected at the schema level.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    strategy_type: OptionExpressionStrategyType = "unknown"
    legs: list[OptionExpressionLeg] = Field(default_factory=list)
    calculation: Optional[OptionStrategyCalculation] = None
    thesis_alignment: str = ""
    horizon_alignment: str = ""
    liquidity_level: OptionLiquidityLevel = "unknown"
    event_risk_level: OptionExpressionEventRiskLevel = "unknown"
    risk_level: OptionRiskLevel = "unknown"
    evidence_quality: OptionEvidenceQuality = "unknown"
    rationale: str = ""
    exit_rule: str = ""
    no_trade_reason: Optional[OptionNoTradeReason] = None
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionExpressionCandidate":
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be whitespace-only.")
        if not self.ticker.strip():
            raise ValueError("ticker must not be whitespace-only.")
        if self.strategy_type == "no_trade" and not self.no_trade_reason:
            raise ValueError(
                "no_trade_reason must be set when strategy_type == 'no_trade'."
            )
        if (
            self.strategy_type in _REAL_STRATEGY_TYPES
            and not self.legs
        ):
            raise ValueError(
                f"legs must be non-empty when strategy_type == {self.strategy_type!r}."
            )
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "OptionExpressionCandidate":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-D. "
                "This layer does not authorize execution."
            )
        return self


class OptionExpressionInputBundle(BaseModel):
    """
    Input context bundle for one option expression assessment pass.

    Holds market snapshot, candidate strategies, and optional prior-phase
    research artifacts for evidence tracing. All data is caller-provided
    mock/non-live only. No live market data, brokerage data, or external API.

    Important: if validated thesis / trade plan / allocation context is missing,
    option expression should generally be no_trade or needs_review, not an
    option recommendation.

    Missing optional prior artifacts produce warnings, not crashes.
    No mutation of inputs.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    as_of: str = ""
    market_snapshot: Optional[OptionMarketSnapshot] = None
    validated_thesis_reference: Optional[Any] = None
    trade_plan_report: Optional[Any] = None
    allocation_report: Optional[Any] = None
    event_intelligence_report: Optional[Any] = None
    decision_packet: Optional[Any] = None
    human_review_report: Optional[Any] = None
    validation_aggregate: Optional[Any] = None
    candidate_strategies: list[OptionExpressionCandidate] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_target(self) -> "OptionExpressionInputBundle":
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        return self


class OptionExpressionAssessment(BaseModel):
    """
    Option expression assessment for one analysis pass.

    Combines deterministic candidate selection with risk assessment.
    Research-only output; does NOT authorize execution.
    approved_for_execution is ALWAYS False.
    """

    model_config = ConfigDict(extra="forbid")

    assessment_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    decision: OptionExpressionDecision = "unknown"
    selected_strategy: Optional[OptionExpressionCandidate] = None
    candidate_count: int = Field(ge=0)
    no_trade_reason: Optional[OptionNoTradeReason] = None
    review_required: bool = False
    risk_level: OptionRiskLevel = "unknown"
    liquidity_level: OptionLiquidityLevel = "unknown"
    event_risk_level: OptionExpressionEventRiskLevel = "unknown"
    rationale: str = ""
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionExpressionAssessment":
        for fn in ("assessment_id", "ticker"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        if self.decision == "no_trade" and not self.no_trade_reason:
            raise ValueError(
                "no_trade_reason must be set when decision == 'no_trade'."
            )
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "OptionExpressionAssessment":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-D. "
                "This layer does not authorize execution."
            )
        return self


class OptionExpressionSummary(BaseModel):
    """
    Concise deterministic summary of one option expression report.

    Computed from OptionExpressionAssessment and resolved status.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    status: OptionExpressionStatus = "unknown"
    decision: OptionExpressionDecision = "unknown"
    selected_strategy_type: Optional[OptionExpressionStrategyType] = None
    candidate_count: int = Field(ge=0)
    no_trade_reason: Optional[OptionNoTradeReason] = None
    max_loss: Optional[float] = None
    breakeven: Optional[float] = None
    cash_required: Optional[float] = None
    risk_level: OptionRiskLevel = "unknown"
    liquidity_level: OptionLiquidityLevel = "unknown"
    event_risk_level: OptionExpressionEventRiskLevel = "unknown"
    review_required: bool = False
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_target(self) -> "OptionExpressionSummary":
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        if self.decision == "no_trade" and not self.no_trade_reason:
            raise ValueError(
                "no_trade_reason must be set when decision == 'no_trade'."
            )
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "OptionExpressionSummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-D. "
                "This layer does not authorize execution."
            )
        return self


class OptionExpressionReport(BaseModel):
    """
    Full option expression assessment report for one analysis pass.

    Composes all option expression results into a single auditable research
    artifact.

    approved_for_execution is ALWAYS False. This report is a research artifact
    only and does not constitute investment advice or authorize any form of
    execution. No pathway to approve execution exists in Phase 3R-D.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    report_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    target: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: OptionExpressionStatus = "unknown"
    input_bundle: OptionExpressionInputBundle
    assessment: OptionExpressionAssessment
    summary: OptionExpressionSummary
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionExpressionReport":
        for fn in ("report_id", "target", "run_id", "created_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "OptionExpressionReport":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-D. "
                "This layer does not authorize execution."
            )
        return self


# ---------------------------------------------------------------------------
# Deterministic option calculator functions (Roadmap v4 formulas)
# ---------------------------------------------------------------------------

def calculate_long_call_breakeven(strike: float, premium: float) -> float:
    """
    Compute long call breakeven = strike + premium.

    Args:
        strike:  Strike price (>= 0).
        premium: Premium paid per share (>= 0).

    Returns:
        Breakeven price as a float.

    Raises:
        ValueError: If strike < 0 or premium < 0.
    """
    if strike < 0:
        raise ValueError(f"strike must be >= 0; got {strike!r}.")
    if premium < 0:
        raise ValueError(f"premium must be >= 0; got {premium!r}.")
    return strike + premium


def calculate_long_put_breakeven(strike: float, premium: float) -> float:
    """
    Compute long put breakeven = strike - premium.

    Args:
        strike:  Strike price (>= 0).
        premium: Premium paid per share (>= 0).

    Returns:
        Breakeven price as a float.

    Raises:
        ValueError: If strike < 0 or premium < 0.
    """
    if strike < 0:
        raise ValueError(f"strike must be >= 0; got {strike!r}.")
    if premium < 0:
        raise ValueError(f"premium must be >= 0; got {premium!r}.")
    return strike - premium


def calculate_long_option_max_loss(premium: float, contracts: int) -> float:
    """
    Compute long option max loss = premium × contracts × 100.

    Maximum loss on a long option is the total premium paid.

    Args:
        premium:   Premium paid per share (>= 0).
        contracts: Number of contracts (>= 0).

    Returns:
        Maximum loss as a float (>= 0).

    Raises:
        ValueError: If premium < 0 or contracts < 0.
    """
    if premium < 0:
        raise ValueError(f"premium must be >= 0; got {premium!r}.")
    if contracts < 0:
        raise ValueError(f"contracts must be >= 0; got {contracts!r}.")
    return premium * contracts * _CONTRACT_MULTIPLIER


def calculate_call_debit_spread_max_loss(
    net_debit: float,
    contracts: int,
) -> float:
    """
    Compute call debit spread max loss = net_debit × contracts × 100.

    Max loss equals the net debit paid to enter the spread.

    Args:
        net_debit:  Net premium paid (>= 0).
        contracts:  Number of contracts (>= 0).

    Returns:
        Maximum loss as a float (>= 0).

    Raises:
        ValueError: If net_debit < 0 or contracts < 0.
    """
    if net_debit < 0:
        raise ValueError(f"net_debit must be >= 0; got {net_debit!r}.")
    if contracts < 0:
        raise ValueError(f"contracts must be >= 0; got {contracts!r}.")
    return net_debit * contracts * _CONTRACT_MULTIPLIER


def calculate_call_debit_spread_max_gain(
    long_strike: float,
    short_strike: float,
    net_debit: float,
    contracts: int,
) -> float:
    """
    Compute call debit spread max gain.

    Formula: (spread_width - net_debit) × contracts × 100

    Args:
        long_strike:  Strike of the long call (>= 0).
        short_strike: Strike of the short call (>= long_strike).
        net_debit:    Net premium paid (>= 0).
        contracts:    Number of contracts (>= 0).

    Returns:
        Maximum gain as a float (>= 0).

    Raises:
        ValueError: If strikes < 0, short_strike < long_strike,
                    net_debit < 0, or contracts < 0.
    """
    if long_strike < 0:
        raise ValueError(f"long_strike must be >= 0; got {long_strike!r}.")
    if short_strike < long_strike:
        raise ValueError(
            f"short_strike ({short_strike!r}) must be >= long_strike ({long_strike!r})."
        )
    if net_debit < 0:
        raise ValueError(f"net_debit must be >= 0; got {net_debit!r}.")
    if contracts < 0:
        raise ValueError(f"contracts must be >= 0; got {contracts!r}.")
    spread_width = short_strike - long_strike
    max_gain_per_share = max(spread_width - net_debit, 0.0)
    return max_gain_per_share * contracts * _CONTRACT_MULTIPLIER


def calculate_put_debit_spread_breakeven(
    long_put_strike: float,
    net_debit: float,
) -> float:
    """
    Compute put debit spread breakeven = long_put_strike - net_debit.

    Args:
        long_put_strike: Strike of the long put (>= 0).
        net_debit:       Net premium paid (>= 0).

    Returns:
        Breakeven price as a float.

    Raises:
        ValueError: If long_put_strike < 0 or net_debit < 0.
    """
    if long_put_strike < 0:
        raise ValueError(f"long_put_strike must be >= 0; got {long_put_strike!r}.")
    if net_debit < 0:
        raise ValueError(f"net_debit must be >= 0; got {net_debit!r}.")
    return long_put_strike - net_debit


def calculate_put_debit_spread_max_loss(
    net_debit: float,
    contracts: int,
) -> float:
    """
    Compute put debit spread max loss = net_debit × contracts × 100.

    Args:
        net_debit:  Net premium paid (>= 0).
        contracts:  Number of contracts (>= 0).

    Returns:
        Maximum loss as a float (>= 0).

    Raises:
        ValueError: If net_debit < 0 or contracts < 0.
    """
    if net_debit < 0:
        raise ValueError(f"net_debit must be >= 0; got {net_debit!r}.")
    if contracts < 0:
        raise ValueError(f"contracts must be >= 0; got {contracts!r}.")
    return net_debit * contracts * _CONTRACT_MULTIPLIER


def calculate_cash_secured_put_cash_required(
    strike: float,
    contracts: int,
) -> float:
    """
    Compute cash secured put cash required = strike × contracts × 100.

    Args:
        strike:    Put strike price (>= 0).
        contracts: Number of contracts (>= 0).

    Returns:
        Cash required as a float (>= 0).

    Raises:
        ValueError: If strike < 0 or contracts < 0.
    """
    if strike < 0:
        raise ValueError(f"strike must be >= 0; got {strike!r}.")
    if contracts < 0:
        raise ValueError(f"contracts must be >= 0; got {contracts!r}.")
    return strike * contracts * _CONTRACT_MULTIPLIER


def calculate_cash_secured_put_breakeven(
    strike: float,
    premium: float,
) -> float:
    """
    Compute cash secured put breakeven = strike - premium.

    Args:
        strike:  Put strike price (>= 0).
        premium: Premium received per share (>= 0).

    Returns:
        Breakeven price as a float.

    Raises:
        ValueError: If strike < 0 or premium < 0.
    """
    if strike < 0:
        raise ValueError(f"strike must be >= 0; got {strike!r}.")
    if premium < 0:
        raise ValueError(f"premium must be >= 0; got {premium!r}.")
    return strike - premium


def calculate_covered_call_effective_sale_price(
    strike: float,
    premium: float,
) -> float:
    """
    Compute covered call effective sale price = strike + premium.

    Args:
        strike:  Call strike price (>= 0).
        premium: Premium received per share (>= 0).

    Returns:
        Effective sale price as a float.

    Raises:
        ValueError: If strike < 0 or premium < 0.
    """
    if strike < 0:
        raise ValueError(f"strike must be >= 0; got {strike!r}.")
    if premium < 0:
        raise ValueError(f"premium must be >= 0; got {premium!r}.")
    return strike + premium


def calculate_covered_call_upside_cap(
    strike: float,
    stock_cost_basis: float,
    premium: float,
) -> float:
    """
    Compute covered call upside cap per share = strike - stock_cost_basis + premium.

    Args:
        strike:           Call strike price (>= 0).
        stock_cost_basis: Cost basis per share (>= 0).
        premium:          Premium received per share (>= 0).

    Returns:
        Upside cap per share (may be negative if cost basis > strike + premium).

    Raises:
        ValueError: If strike < 0, stock_cost_basis < 0, or premium < 0.
    """
    if strike < 0:
        raise ValueError(f"strike must be >= 0; got {strike!r}.")
    if stock_cost_basis < 0:
        raise ValueError(f"stock_cost_basis must be >= 0; got {stock_cost_basis!r}.")
    if premium < 0:
        raise ValueError(f"premium must be >= 0; got {premium!r}.")
    return strike - stock_cost_basis + premium


def calculate_risk_reward_ratio(
    max_gain: Optional[float],
    max_loss: Optional[float],
) -> Optional[float]:
    """
    Compute risk/reward ratio = max_gain / max_loss.

    Returns None when max_gain or max_loss is None, or when max_loss == 0.
    A zero max_loss represents unlimited reward (e.g., naked calls) or
    a free trade (which is never realistic in practice). Both cases cannot
    produce a finite ratio.

    Args:
        max_gain: Maximum potential gain (>= 0), or None.
        max_loss: Maximum potential loss (>= 0), or None.

    Returns:
        Risk/reward ratio as a float, or None.

    Raises:
        ValueError: If max_gain < 0 or max_loss < 0.
    """
    if max_gain is not None and max_gain < 0:
        raise ValueError(f"max_gain must be >= 0 if provided; got {max_gain!r}.")
    if max_loss is not None and max_loss < 0:
        raise ValueError(f"max_loss must be >= 0 if provided; got {max_loss!r}.")
    if max_gain is None or max_loss is None or max_loss == 0.0:
        return None
    return max_gain / max_loss


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_long_leg(
    legs: list[OptionExpressionLeg],
    option_type: OptionLegType,
) -> Optional[OptionExpressionLeg]:
    """Return first leg matching option_type with position_side='long'."""
    for leg in legs:
        if leg.option_type == option_type and leg.position_side == "long":
            return leg
    return None


def _extract_short_leg(
    legs: list[OptionExpressionLeg],
    option_type: OptionLegType,
) -> Optional[OptionExpressionLeg]:
    """Return first leg matching option_type with position_side='short'."""
    for leg in legs:
        if leg.option_type == option_type and leg.position_side == "short":
            return leg
    return None


def _infer_option_risk_level(
    selected_candidate: Optional[OptionExpressionCandidate],
    event_risk_level: OptionExpressionEventRiskLevel,
    liquidity_level: OptionLiquidityLevel,
) -> OptionRiskLevel:
    """
    Infer OptionRiskLevel from candidate, event risk, and liquidity.

    Priority:
      high     — event_risk_level == "high"
      medium   — event_risk_level == "medium"
               — OR liquidity_level == "poor"
               — OR selected_candidate.evidence_quality in ("unsupported", "weak")
      low      — event_risk_level == "low" AND liquidity_level in ("acceptable", "good")
                 AND evidence_quality in ("adequate", "strong")
      unknown  — no candidate data available
    """
    if event_risk_level == "high":
        return "high"
    if event_risk_level == "medium" or liquidity_level == "poor":
        return "medium"
    if selected_candidate is None:
        return "unknown"
    if selected_candidate.evidence_quality in ("unsupported", "weak"):
        return "medium"
    if (
        event_risk_level == "low"
        and liquidity_level in ("acceptable", "good")
        and selected_candidate.evidence_quality in _ADEQUATE_EVIDENCE
    ):
        return "low"
    return "medium"


def _determine_review_required(
    decision: OptionExpressionDecision,
    risk_level: OptionRiskLevel,
    liquidity_level: OptionLiquidityLevel,
    event_risk_level: OptionExpressionEventRiskLevel,
    evidence_quality: OptionEvidenceQuality,
    has_thesis: bool,
) -> bool:
    """
    Determine whether human review is required for this expression.

    Returns True when:
      - risk_level == "high"
      - liquidity_level == "poor"
      - event_risk_level in ("high", "medium")
      - evidence_quality in ("unsupported", "weak")
      - decision is "option" but thesis is not validated
    """
    if risk_level == "high":
        return True
    if liquidity_level == "poor":
        return True
    if event_risk_level in ("high", "medium"):
        return True
    if evidence_quality in ("unsupported", "weak"):
        return True
    if decision == "option" and not has_thesis:
        return True
    return False


def _strategy_type_to_decision(
    strategy_type: OptionExpressionStrategyType,
) -> OptionExpressionDecision:
    """Map an OptionExpressionStrategyType to an OptionExpressionDecision."""
    if strategy_type == "no_trade":
        return "no_trade"
    if strategy_type == "stock":
        return "stock"
    if strategy_type == "unknown":
        return "unknown"
    return "option"


def _select_candidate_strategy(
    candidates: list[OptionExpressionCandidate],
    has_thesis: bool,
) -> tuple[
    Optional[OptionExpressionCandidate],
    OptionExpressionDecision,
    Optional[OptionNoTradeReason],
]:
    """
    Select the best candidate strategy from the list.

    Priority logic:
      1. No candidates → (None, "unknown", "missing_required_inputs")
      2. Thesis not validated + real option or stock candidates exist →
           prefer first no_trade candidate (or implicit "thesis_not_validated")
      3. Thesis validated + adequate real option/stock candidates → first adequate
      4. Thesis validated + weak real option/stock candidates → first real/stock
      5. Only no_trade candidates → first no_trade candidate
      6. Otherwise → (None, "unknown", "missing_required_inputs")

    Stock candidates (strategy_type == "stock") are treated as a first-class
    expression path alongside option candidates. They do not require option legs.
    A selected stock candidate produces decision == "stock".

    Returns:
        (selected_candidate, decision, no_trade_reason)
    """
    if not candidates:
        return None, "unknown", "missing_required_inputs"

    no_trade_candidates = [c for c in candidates if c.strategy_type == "no_trade"]
    real_candidates = [
        c for c in candidates if c.strategy_type in _REAL_STRATEGY_TYPES
    ]
    stock_candidates = [
        c for c in candidates if c.strategy_type in _STOCK_STRATEGY_TYPES
    ]
    # All expression candidates (option or stock)
    expression_candidates = real_candidates + stock_candidates

    # Thesis not validated — prefer no_trade
    if not has_thesis and expression_candidates:
        if no_trade_candidates:
            c = no_trade_candidates[0]
            return c, "no_trade", c.no_trade_reason or "thesis_not_validated"
        return None, "no_trade", "thesis_not_validated"

    # Thesis present or no expression candidates — try to find the best expression candidate
    adequate_expr = [c for c in expression_candidates if c.evidence_quality in _ADEQUATE_EVIDENCE]
    if adequate_expr:
        c = adequate_expr[0]
        return c, _strategy_type_to_decision(c.strategy_type), None

    if expression_candidates:
        c = expression_candidates[0]
        return c, _strategy_type_to_decision(c.strategy_type), None

    # Only no_trade or unknown candidates
    if no_trade_candidates:
        c = no_trade_candidates[0]
        return c, "no_trade", c.no_trade_reason or "unknown"

    return None, "unknown", "missing_required_inputs"


def _generate_option_expression_warnings(
    input_bundle: OptionExpressionInputBundle,
) -> list[str]:
    """
    Generate derived warnings for missing optional prior artifacts.

    Returns ONLY newly generated warnings — does NOT include bundle.warnings.
    Callers are responsible for combining with bundle.warnings.

    Does not crash on missing optional artifacts. Does not mutate inputs.
    """
    generated: list[str] = []
    if input_bundle.market_snapshot is None:
        generated.append(
            "OptionExpressionInputBundle: market_snapshot is missing. "
            "Liquidity and event risk context unavailable."
        )
    if input_bundle.validated_thesis_reference is None:
        generated.append(
            "OptionExpressionInputBundle: validated_thesis_reference is missing. "
            "Option expression should prefer no_trade without a validated thesis."
        )
    if input_bundle.trade_plan_report is None:
        generated.append(
            "OptionExpressionInputBundle: trade_plan_report is missing. "
            "Option expression lacks trade plan context."
        )
    if input_bundle.allocation_report is None:
        generated.append(
            "OptionExpressionInputBundle: allocation_report is missing. "
            "Option expression lacks allocation sizing context."
        )
    if not input_bundle.candidate_strategies:
        generated.append(
            "OptionExpressionInputBundle: candidate_strategies is empty. "
            "No candidate strategies to evaluate; decision will be unknown."
        )
    return generated


# ---------------------------------------------------------------------------
# Helper: deterministic ID generator
# ---------------------------------------------------------------------------

def make_option_expression_report_id(
    run_id: str,
    target: str,
    as_of: str,
) -> str:
    """Return a deterministic stable hash ID for an OptionExpressionReport."""
    payload = {"run_id": run_id, "target": target, "as_of": as_of}
    h = stable_hash_payload(payload, length=16)
    return f"oer_{h}"


# ---------------------------------------------------------------------------
# Helper: status determination
# ---------------------------------------------------------------------------

def determine_option_expression_status(
    assessment: OptionExpressionAssessment,
    human_review_report: Any = None,
) -> OptionExpressionStatus:
    """
    Derive OptionExpressionStatus from assessment and optional human review report.

    Priority (highest wins):
      blocked      — human_review_report.status == "blocked"
      needs_review — risk_level == "high"
                   — OR review_required == True
      unknown      — decision == "unknown" (after needs_review checks)
      complete     — valid decision (non-unknown), review not required

    Note: needs_review is evaluated before unknown. A decision of "unknown"
    combined with high risk or review_required flags returns "needs_review",
    not "unknown".

    Does not mutate any input. No network calls. No LLM calls.
    approved_for_execution is never implied by any status value.
    """
    # blocked: human review says blocked
    if human_review_report is not None:
        hr_status = getattr(human_review_report, "status", None)
        if hr_status == "blocked":
            return "blocked"

    # needs_review: high risk level (beats unknown)
    if assessment.risk_level == "high":
        return "needs_review"

    # needs_review: review_required flag (beats unknown)
    if assessment.review_required:
        return "needs_review"

    # unknown: no valid decision (checked after needs_review conditions)
    if assessment.decision == "unknown":
        return "unknown"

    # complete: passed all checks above
    return "complete"


# ---------------------------------------------------------------------------
# Helper: source ID collection
# ---------------------------------------------------------------------------

def collect_option_expression_source_ids(
    input_bundle: OptionExpressionInputBundle,
    assessment: OptionExpressionAssessment,
) -> list[str]:
    """
    Collect all source/evidence IDs from the input bundle and assessment.

    Collection order:
      1. Bundle-level source_ids.
      2. Market snapshot source_ids (if present).
      3. All candidate strategy source_ids (in order).
      4. Selected strategy leg source_ids (if present).
      5. Selected strategy calculation source_ids (if present).
      6. Assessment source_ids.

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
    if input_bundle.market_snapshot is not None:
        for sid in input_bundle.market_snapshot.source_ids:
            _add(sid)
    for candidate in input_bundle.candidate_strategies:
        for sid in candidate.source_ids:
            _add(sid)
        for leg in candidate.legs:
            for sid in leg.source_ids:
                _add(sid)
        if candidate.calculation is not None:
            for sid in candidate.calculation.source_ids:
                _add(sid)
    for sid in assessment.source_ids:
        _add(sid)
    if assessment.selected_strategy is not None:
        for sid in assessment.selected_strategy.source_ids:
            _add(sid)

    return ids


# ---------------------------------------------------------------------------
# Helper: option strategy calculation builder
# ---------------------------------------------------------------------------

def build_option_strategy_calculation(
    strategy_type: OptionExpressionStrategyType,
    legs: list[OptionExpressionLeg],
    source_ids: Optional[list[str]] = None,
    run_id: str = "",
    target: str = "",
) -> OptionStrategyCalculation:
    """
    Build a deterministic OptionStrategyCalculation from a strategy type and legs.

    Applies Roadmap v4 formulas for each supported strategy type. Extracts
    strike, premium, and contracts from legs. Warnings are generated when
    required leg data is missing for a given strategy type.

    Supported formulas:
      long_call:          breakeven = strike + premium; max_loss = premium × n × 100
      long_put:           breakeven = strike - premium; max_loss = premium × n × 100
      call_debit_spread:  max_loss = net_debit × n × 100;
                          max_gain = (spread_width - net_debit) × n × 100
      put_debit_spread:   breakeven = long_put_strike - net_debit;
                          max_loss = net_debit × n × 100
      cash_secured_put:   cash_required = strike × n × 100;
                          breakeven = strike - premium
      covered_call:       effective_sale_price = strike + premium;
                          upside_cap = strike - cost_basis + premium
      no_trade / unknown: no calculation; empty result with warning.

    Deterministic: identical inputs → identical outputs.
    No network calls. No LLM calls. No mutation of inputs.
    """
    _source_ids: list[str] = list(source_ids) if source_ids else []
    for leg in legs:
        for sid in leg.source_ids:
            if sid and sid not in _source_ids:
                _source_ids.append(sid)

    warnings: list[str] = []

    calc_payload = {
        "strategy_type": strategy_type,
        "run_id": run_id,
        "target": target,
        "legs": [leg.leg_id for leg in legs],
    }
    calculation_id = "osc_" + stable_hash_payload(calc_payload, length=16)

    # Default values
    breakeven: Optional[float] = None
    max_loss: Optional[float] = None
    max_gain: Optional[float] = None
    net_debit: Optional[float] = None
    net_credit: Optional[float] = None
    cash_required: Optional[float] = None
    effective_sale_price: Optional[float] = None
    upside_cap: Optional[float] = None
    risk_reward_ratio: Optional[float] = None

    if strategy_type in ("no_trade", "stock", "unknown"):
        warnings.append(
            f"build_option_strategy_calculation: no option formulas apply for "
            f"strategy_type={strategy_type!r}."
        )

    elif strategy_type == "long_call":
        long_call = _extract_long_leg(legs, "call")
        if long_call is None:
            warnings.append(
                "build_option_strategy_calculation: long_call requires a long call "
                "leg; none found."
            )
        elif long_call.strike is None or long_call.premium is None:
            warnings.append(
                f"build_option_strategy_calculation: leg '{long_call.leg_id}' "
                "missing strike or premium for long_call calculation."
            )
        else:
            n = long_call.contracts if long_call.contracts is not None else 1
            breakeven = calculate_long_call_breakeven(long_call.strike, long_call.premium)
            max_loss = calculate_long_option_max_loss(long_call.premium, n)
            net_debit = max_loss
            risk_reward_ratio = None  # unlimited upside

    elif strategy_type == "long_put":
        long_put = _extract_long_leg(legs, "put")
        if long_put is None:
            warnings.append(
                "build_option_strategy_calculation: long_put requires a long put "
                "leg; none found."
            )
        elif long_put.strike is None or long_put.premium is None:
            warnings.append(
                f"build_option_strategy_calculation: leg '{long_put.leg_id}' "
                "missing strike or premium for long_put calculation."
            )
        else:
            n = long_put.contracts if long_put.contracts is not None else 1
            breakeven = calculate_long_put_breakeven(long_put.strike, long_put.premium)
            max_loss = calculate_long_option_max_loss(long_put.premium, n)
            max_gain_per_share = max(long_put.strike - long_put.premium, 0.0)
            max_gain = max_gain_per_share * n * _CONTRACT_MULTIPLIER
            net_debit = max_loss
            risk_reward_ratio = calculate_risk_reward_ratio(max_gain, max_loss)

    elif strategy_type == "call_debit_spread":
        long_call = _extract_long_leg(legs, "call")
        short_call = _extract_short_leg(legs, "call")
        if long_call is None or short_call is None:
            warnings.append(
                "build_option_strategy_calculation: call_debit_spread requires a "
                "long call leg and a short call leg; one or both missing."
            )
        elif (
            long_call.strike is None
            or long_call.premium is None
            or short_call.strike is None
            or short_call.premium is None
        ):
            warnings.append(
                "build_option_strategy_calculation: call_debit_spread legs missing "
                "strike or premium."
            )
        else:
            n = long_call.contracts if long_call.contracts is not None else 1
            _net_debit_per_share = long_call.premium - short_call.premium
            if _net_debit_per_share < 0:
                warnings.append(
                    "build_option_strategy_calculation: call_debit_spread net_debit "
                    "is negative (credit); check leg direction."
                )
                _net_debit_per_share = 0.0
            max_loss = calculate_call_debit_spread_max_loss(_net_debit_per_share, n)
            max_gain = calculate_call_debit_spread_max_gain(
                long_call.strike, short_call.strike, _net_debit_per_share, n
            )
            breakeven = long_call.strike + _net_debit_per_share
            net_debit = max_loss
            risk_reward_ratio = calculate_risk_reward_ratio(max_gain, max_loss)

    elif strategy_type == "put_debit_spread":
        long_put = _extract_long_leg(legs, "put")
        short_put = _extract_short_leg(legs, "put")
        if long_put is None or short_put is None:
            warnings.append(
                "build_option_strategy_calculation: put_debit_spread requires a "
                "long put leg and a short put leg; one or both missing."
            )
        elif (
            long_put.strike is None
            or long_put.premium is None
            or short_put.strike is None
            or short_put.premium is None
        ):
            warnings.append(
                "build_option_strategy_calculation: put_debit_spread legs missing "
                "strike or premium."
            )
        else:
            n = long_put.contracts if long_put.contracts is not None else 1
            _net_debit_per_share = long_put.premium - short_put.premium
            if _net_debit_per_share < 0:
                warnings.append(
                    "build_option_strategy_calculation: put_debit_spread net_debit "
                    "is negative (credit); check leg direction."
                )
                _net_debit_per_share = 0.0
            max_loss = calculate_put_debit_spread_max_loss(_net_debit_per_share, n)
            _spread_width = long_put.strike - short_put.strike
            _max_gain_per_share = max(_spread_width - _net_debit_per_share, 0.0)
            max_gain = _max_gain_per_share * n * _CONTRACT_MULTIPLIER
            breakeven = calculate_put_debit_spread_breakeven(
                long_put.strike, _net_debit_per_share
            )
            net_debit = max_loss
            risk_reward_ratio = calculate_risk_reward_ratio(max_gain, max_loss)

    elif strategy_type == "cash_secured_put":
        short_put = _extract_short_leg(legs, "put")
        if short_put is None:
            warnings.append(
                "build_option_strategy_calculation: cash_secured_put requires a "
                "short put leg; none found."
            )
        elif short_put.strike is None or short_put.premium is None:
            warnings.append(
                f"build_option_strategy_calculation: leg '{short_put.leg_id}' "
                "missing strike or premium for cash_secured_put calculation."
            )
        else:
            n = short_put.contracts if short_put.contracts is not None else 1
            cash_required = calculate_cash_secured_put_cash_required(short_put.strike, n)
            breakeven = calculate_cash_secured_put_breakeven(short_put.strike, short_put.premium)
            max_gain = short_put.premium * n * _CONTRACT_MULTIPLIER
            max_loss = max(breakeven, 0.0) * n * _CONTRACT_MULTIPLIER
            net_credit = max_gain
            risk_reward_ratio = calculate_risk_reward_ratio(max_gain, max_loss)

    elif strategy_type == "covered_call":
        short_call = _extract_short_leg(legs, "call")
        stock_leg = _extract_long_leg(legs, "stock")
        if short_call is None:
            warnings.append(
                "build_option_strategy_calculation: covered_call requires a "
                "short call leg; none found."
            )
        elif short_call.strike is None or short_call.premium is None:
            warnings.append(
                f"build_option_strategy_calculation: leg '{short_call.leg_id}' "
                "missing strike or premium for covered_call calculation."
            )
        else:
            effective_sale_price = calculate_covered_call_effective_sale_price(
                short_call.strike, short_call.premium
            )
            net_credit = (
                short_call.premium
                * (short_call.contracts if short_call.contracts is not None else 1)
                * _CONTRACT_MULTIPLIER
            )
            if stock_leg is not None and stock_leg.strike is not None:
                # strike on stock leg = cost basis
                upside_cap = calculate_covered_call_upside_cap(
                    short_call.strike, stock_leg.strike, short_call.premium
                )

    return OptionStrategyCalculation(
        calculation_id=calculation_id,
        strategy_type=strategy_type,
        breakeven=breakeven,
        max_loss=max_loss,
        max_gain=max_gain,
        net_debit=net_debit,
        net_credit=net_credit,
        cash_required=cash_required,
        effective_sale_price=effective_sale_price,
        upside_cap=upside_cap,
        risk_reward_ratio=risk_reward_ratio,
        warnings=warnings,
        source_ids=_source_ids,
    )


# ---------------------------------------------------------------------------
# Helper: main report builder
# ---------------------------------------------------------------------------

def build_option_expression_report(
    input_bundle: OptionExpressionInputBundle,
    run_id: str,
    created_at: Optional[str] = None,
) -> OptionExpressionReport:
    """
    Build a complete OptionExpressionReport from the input bundle.

    Steps:
      1. Generate warnings for missing optional prior artifacts.
      2. Determine has_thesis from input bundle.
      3. Select the best candidate strategy deterministically.
      4. Resolve liquidity and event risk levels from market_snapshot.
      5. Resolve evidence quality from selected candidate.
      6. Infer risk level.
      7. Determine review_required.
      8. Build OptionExpressionAssessment.
      9. Determine status (using human_review_report).
     10. Assemble full report warnings (bundle + generated + candidate), deduped.
     11. Collect source IDs deterministically.
     12. Build OptionExpressionSummary.
     13. Build OptionExpressionReport with stable deterministic report_id.

    Deterministic: identical inputs → identical outputs.
    created_at defaults to input_bundle.as_of (or run_id if empty), making
    the full report output deterministic without an explicit timestamp argument.
    Pass created_at explicitly to override (e.g. for tests or audit records).

    No network calls. No LLM calls. No mutation of inputs.
    approved_for_execution is always False.
    """
    # 1. Generated warnings for missing optional artifacts
    generated_warnings = _generate_option_expression_warnings(input_bundle)

    # 2. Determine whether a validated thesis is present
    has_thesis = input_bundle.validated_thesis_reference is not None

    # 3. Select best candidate strategy
    selected_candidate, decision, no_trade_reason = _select_candidate_strategy(
        input_bundle.candidate_strategies, has_thesis
    )

    # 4. Liquidity and event risk levels from market snapshot
    if input_bundle.market_snapshot is not None:
        liquidity_level: OptionLiquidityLevel = input_bundle.market_snapshot.liquidity_level
        event_risk_level: OptionExpressionEventRiskLevel = (
            input_bundle.market_snapshot.event_risk_level
        )
    elif selected_candidate is not None:
        liquidity_level = selected_candidate.liquidity_level
        event_risk_level = selected_candidate.event_risk_level
    else:
        liquidity_level = "unknown"
        event_risk_level = "unknown"

    # 5. Evidence quality from selected candidate
    evidence_quality: OptionEvidenceQuality = (
        selected_candidate.evidence_quality
        if selected_candidate is not None
        else "unknown"
    )

    # 6. Infer risk level
    risk_level = _infer_option_risk_level(selected_candidate, event_risk_level, liquidity_level)

    # 7. Determine review_required
    review_required = _determine_review_required(
        decision=decision,
        risk_level=risk_level,
        liquidity_level=liquidity_level,
        event_risk_level=event_risk_level,
        evidence_quality=evidence_quality,
        has_thesis=has_thesis,
    )

    # 8. Build assessment
    _assessment_payload = {
        "run_id": run_id,
        "target": input_bundle.target,
        "as_of": input_bundle.as_of,
        "decision": decision,
        "strategy_type": (
            selected_candidate.strategy_type if selected_candidate else "unknown"
        ),
    }
    assessment_id = "oea_" + stable_hash_payload(_assessment_payload, length=16)

    # Aggregate source IDs for assessment from selected candidate
    _assessment_source_ids: list[str] = []
    _seen_asids: set[str] = set()

    def _add_asid(sid: str) -> None:
        if sid and sid not in _seen_asids:
            _seen_asids.add(sid)
            _assessment_source_ids.append(sid)

    if selected_candidate is not None:
        for sid in selected_candidate.source_ids:
            _add_asid(sid)
        for leg in selected_candidate.legs:
            for sid in leg.source_ids:
                _add_asid(sid)
        if selected_candidate.calculation is not None:
            for sid in selected_candidate.calculation.source_ids:
                _add_asid(sid)

    # Build assessment rationale
    _rationale = (
        selected_candidate.rationale
        if selected_candidate is not None and selected_candidate.rationale
        else f"Decision: {decision}. No selected candidate rationale available."
    )

    # Collect assessment-level warnings
    _assessment_warnings: list[str] = list(
        selected_candidate.warnings if selected_candidate is not None else []
    )
    if decision == "no_trade" and selected_candidate is None:
        _assessment_warnings.append(
            "OptionExpressionAssessment: no_trade decision derived from missing "
            "thesis/candidates context; no explicit no_trade candidate was selected."
        )

    assessment = OptionExpressionAssessment(
        assessment_id=assessment_id,
        ticker=input_bundle.target,
        decision=decision,
        selected_strategy=selected_candidate,
        candidate_count=len(input_bundle.candidate_strategies),
        no_trade_reason=no_trade_reason,
        review_required=review_required,
        risk_level=risk_level,
        liquidity_level=liquidity_level,
        event_risk_level=event_risk_level,
        rationale=_rationale,
        source_ids=_assessment_source_ids,
        warnings=_assessment_warnings,
        approved_for_execution=False,
    )

    # 9. Status determination
    status = determine_option_expression_status(assessment, input_bundle.human_review_report)

    # 10. Full report warnings (bundle + generated + assessment), deduped
    _raw_warnings = (
        list(input_bundle.warnings)
        + generated_warnings
        + list(assessment.warnings)
    )
    _seen_rw: set[str] = set()
    report_warnings: list[str] = []
    for w in _raw_warnings:
        if w not in _seen_rw:
            _seen_rw.add(w)
            report_warnings.append(w)

    # 11. Source IDs
    source_ids = collect_option_expression_source_ids(input_bundle, assessment)

    # 12. Summary
    _selected_calc = (
        selected_candidate.calculation
        if selected_candidate is not None
        else None
    )
    _summary_warnings = (
        list(assessment.warnings)
        + generated_warnings
        + list(input_bundle.warnings)
    )
    _seen_sw: set[str] = set()
    _deduped_sw: list[str] = []
    for w in _summary_warnings:
        if w not in _seen_sw:
            _seen_sw.add(w)
            _deduped_sw.append(w)

    summary = OptionExpressionSummary(
        target=input_bundle.target,
        status=status,
        decision=decision,
        selected_strategy_type=(
            selected_candidate.strategy_type if selected_candidate is not None else None
        ),
        candidate_count=len(input_bundle.candidate_strategies),
        no_trade_reason=no_trade_reason,
        max_loss=_selected_calc.max_loss if _selected_calc is not None else None,
        breakeven=_selected_calc.breakeven if _selected_calc is not None else None,
        cash_required=_selected_calc.cash_required if _selected_calc is not None else None,
        risk_level=risk_level,
        liquidity_level=liquidity_level,
        event_risk_level=event_risk_level,
        review_required=review_required,
        top_warnings=_deduped_sw[:5],
        approved_for_execution=False,
    )

    # 13. Report ID and created_at
    _as_of = input_bundle.as_of or run_id
    report_id = make_option_expression_report_id(run_id, input_bundle.target, _as_of)
    _created_at = created_at if created_at is not None else _as_of

    return OptionExpressionReport(
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

def summarize_option_expression_report(report: OptionExpressionReport) -> dict[str, Any]:
    """
    Return a concise summary dict of one OptionExpressionReport.

    Returns:
        A dict with report_id, target, status, decision, selected_strategy_type,
        candidate_count, key metrics, review_required, warning_count,
        source_id_count, calculation_version, and approved_for_execution.

    Does not mutate report. Deterministic.
    """
    return {
        "report_id": report.report_id,
        "target": report.target,
        "status": report.status,
        "decision": report.summary.decision,
        "selected_strategy_type": report.summary.selected_strategy_type,
        "candidate_count": report.summary.candidate_count,
        "no_trade_reason": report.summary.no_trade_reason,
        "max_loss": report.summary.max_loss,
        "breakeven": report.summary.breakeven,
        "cash_required": report.summary.cash_required,
        "risk_level": report.summary.risk_level,
        "liquidity_level": report.summary.liquidity_level,
        "event_risk_level": report.summary.event_risk_level,
        "review_required": report.summary.review_required,
        "warning_count": len(report.warnings),
        "source_id_count": len(report.source_ids),
        "calculation_version": report.calculation_version,
        "approved_for_execution": False,
    }


# ---------------------------------------------------------------------------
# ToolResult adapter
# ---------------------------------------------------------------------------

def option_expression_tool_result_from_report(
    run_id: str,
    report: OptionExpressionReport,
    target: Optional[str] = None,
    calculation_version: str = _CALCULATION_VERSION,
) -> ToolResult:
    """
    Wrap an OptionExpressionReport as a ToolResult for evidence-aware pipelines.

    - tool_name is stable: "option_expression_report".
    - target defaults to report.target.
    - outputs includes full report (serialized), summary, calculation_version.
    - evidence_id is deterministic and content-sensitive.
    - Does not mutate report.
    - approved_for_execution is always False in the payload.
    - No live execution implication.
    - Does not look like an option order ticket; contains no order_id,
      broker_order, account_id, execution_status, or live order instruction.
    - Payload does not authorize trading or execution of any kind.
    """
    _target: str = target or report.target

    _report_dict = report.model_dump()
    _summary_dict: dict[str, Any] = {
        "report_id": report.report_id,
        "target": report.target,
        "run_id": report.run_id,
        "status": report.status,
        "decision": report.summary.decision,
        "selected_strategy_type": report.summary.selected_strategy_type,
        "candidate_count": report.summary.candidate_count,
        "no_trade_reason": report.summary.no_trade_reason,
        "max_loss": report.summary.max_loss,
        "breakeven": report.summary.breakeven,
        "cash_required": report.summary.cash_required,
        "risk_level": report.summary.risk_level,
        "liquidity_level": report.summary.liquidity_level,
        "event_risk_level": report.summary.event_risk_level,
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
        tool_name=_OPTION_EXPRESSION_TOOL_NAME,
        target=_target,
        metric_group=_OPTION_EXPRESSION_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_OPTION_EXPRESSION_TOOL_NAME,
        run_id=run_id,
        ticker=report.target if report.target else None,
        inputs={"as_of": report.input_bundle.as_of, "target": _target},
        outputs=outputs,
        description=(
            f"OptionExpressionReport for {report.target}: "
            f"status={report.status}, "
            f"decision={report.summary.decision}, "
            f"strategy={report.summary.selected_strategy_type}, "
            f"risk={report.summary.risk_level}, "
            f"review_required={report.summary.review_required}, "
            f"source_ids={len(report.source_ids)}, "
            f"warnings={len(report.warnings)}."
        ),
    )
