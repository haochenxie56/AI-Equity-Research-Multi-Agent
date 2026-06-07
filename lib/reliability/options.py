"""
lib/reliability/options.py

Phase 2E: Option Data + Strategy Tool Schema Foundation.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no live data fetching.
  - All calculators are deterministic: same inputs → same outputs.
  - Contract-aware calculators validate option type, underlying, and expiration.
  - No broker integration. No live option data fetching. No order placement.
  - No Greeks computation beyond accepting delta/gamma/theta/vega as optional
    sourced inputs.
  - No real-time IV surface, smile, or margin/tax/assignment models.
  - UI dashboard belongs to the Investment Cockpit phase.

Net premium convention:
  - net_premium > 0  →  debit paid  (long strategies: long call, long put,
                                      debit spreads)
  - net_premium < 0  →  credit received  (short premium strategies: CSP,
                                          covered call)

Contract multiplier: each option contract controls 100 shares.

See docs/reliability_phase_2e_option_strategy_schema.md for full design
rationale and rollout context.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id
from lib.reliability.schemas import EvidenceRef, ToolResult


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

OptionType = Literal["call", "put"]

OptionPositionSide = Literal["long", "short"]

OptionStrategyType = Literal[
    "long_call",
    "long_put",
    "call_debit_spread",
    "put_debit_spread",
    "cash_secured_put",
    "covered_call",
    "protective_put",
    "collar",
    "straddle",
    "strangle",
    "no_trade",
]

OptionLiquidityStatus = Literal["liquid", "acceptable", "illiquid", "unknown"]

OptionEventRiskLevel = Literal["low", "medium", "high", "unknown"]

OptionTradeExpression = Literal[
    "stock",
    "option",
    "cash",
    "wait",
    "no_trade",
    "undetermined",
]


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_OPTION_TOOL_NAME: str = "option_strategy_decision_set"
_OPTION_METRIC_GROUP: str = "option_strategy_decision_set"

# Each option contract controls this many shares.
_CONTRACT_MULTIPLIER: int = 100

# Liquidity thresholds (advisory):
#   liquid     → max spread <= 10% AND (OI unavailable OR min_OI >= 100)
#   acceptable → max spread <= max_acceptable_spread_pct (default 15%)
#   illiquid   → otherwise
_LIQUID_MAX_SPREAD_PCT: float = 0.10
_LIQUID_MIN_OI: int = 100


# ---------------------------------------------------------------------------
# 1. OptionContractSnapshot
# ---------------------------------------------------------------------------

class OptionContractSnapshot(BaseModel):
    """
    Market data snapshot for a single option contract.

    Fields:
        underlying:         Underlying ticker symbol (non-empty).
        option_type:        ``"call"`` or ``"put"``.
        expiration:         Expiration date string (non-empty; ISO format
                            preferred, e.g. ``"2026-06-20"``).
        strike:             Strike price (> 0).
        bid:                Bid price per share (>= 0).
        ask:                Ask price per share (>= bid >= 0).
        last:               Last traded price per share (>= 0; optional).
        mid:                Pre-computed mid price per share (>= 0; optional).
                            When provided, ``option_mid_price()`` uses this
                            value instead of computing ``(bid + ask) / 2``.
        volume:             Trading volume in contracts (>= 0; optional).
        open_interest:      Open interest in contracts (>= 0; optional).
        implied_volatility: Implied volatility as a decimal fraction
                            (e.g. 0.30 = 30%; >= 0; optional).
        delta:              Option delta (-1.0 to 1.0; optional).
        gamma:              Option gamma (optional; sign unconstrained).
        theta:              Option theta (optional; sign unconstrained).
        vega:               Option vega (optional; sign unconstrained).
        as_of:              Snapshot date/time string (non-empty).
        source:             Non-empty source label; defaults to
                            ``"synthetic"``.
        metadata:           Optional key/value metadata.

    Note:
        ``bid`` and ``ask`` are per-share prices, not per-contract totals.
        Multiply by ``_CONTRACT_MULTIPLIER`` (100) for total contract cost.
    """

    model_config = ConfigDict(extra="forbid")

    underlying: str = Field(min_length=1)
    option_type: OptionType
    expiration: str = Field(min_length=1)
    strike: float = Field(gt=0.0)
    bid: float = Field(ge=0.0)
    ask: float = Field(ge=0.0)
    last: Optional[float] = Field(default=None, ge=0.0)
    mid: Optional[float] = Field(default=None, ge=0.0)
    volume: Optional[int] = Field(default=None, ge=0)
    open_interest: Optional[int] = Field(default=None, ge=0)
    implied_volatility: Optional[float] = Field(default=None, ge=0.0)
    delta: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    as_of: str = Field(min_length=1)
    source: str = Field(default="synthetic", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionContractSnapshot":
        if self.underlying.strip() == "":
            raise ValueError("underlying must not be whitespace-only.")
        if self.expiration.strip() == "":
            raise ValueError("expiration must not be whitespace-only.")
        if self.as_of.strip() == "":
            raise ValueError("as_of must not be whitespace-only.")
        if self.source.strip() == "":
            raise ValueError("source must not be whitespace-only.")
        if self.ask < self.bid:
            raise ValueError(
                f"ask ({self.ask!r}) must be >= bid ({self.bid!r})."
            )
        return self


# ---------------------------------------------------------------------------
# 2. OptionChainSnapshot
# ---------------------------------------------------------------------------

class OptionChainSnapshot(BaseModel):
    """
    Container for a collection of option contracts for one underlying ticker.

    Fields:
        underlying:       Underlying ticker symbol (non-empty).
        underlying_price: Current price of the underlying (> 0).
        snapshot_id:      Optional unique identifier for this chain snapshot
                          (retained for backward compatibility).
        expirations:      Available expiration date strings in this chain.
        contracts:        List of option contract snapshots (may be
                          empty/partial).
        as_of:            Non-empty snapshot date/time string.
        source:           Non-empty source label; defaults to
                          ``"synthetic"``.
        warnings:         Advisory coverage/quality warnings.
        metadata:         Optional key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    underlying: str = Field(min_length=1)
    underlying_price: float = Field(gt=0.0)
    snapshot_id: Optional[str] = None
    expirations: list[str] = Field(default_factory=list)
    contracts: list[OptionContractSnapshot] = Field(default_factory=list)
    as_of: str = Field(min_length=1)
    source: str = Field(default="synthetic", min_length=1)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionChainSnapshot":
        if self.underlying.strip() == "":
            raise ValueError("underlying must not be whitespace-only.")
        if self.as_of.strip() == "":
            raise ValueError("as_of must not be whitespace-only.")
        if self.source.strip() == "":
            raise ValueError("source must not be whitespace-only.")
        return self


# ---------------------------------------------------------------------------
# 3. OptionLeg
# ---------------------------------------------------------------------------

class OptionLeg(BaseModel):
    """
    One leg of a multi-leg option strategy.

    Fields:
        contract:  The underlying option contract snapshot.
        side:      ``"long"`` (buying) or ``"short"`` (selling).
        quantity:  Number of option contracts traded (>= 1).
        premium:   Per-share premium override (>= 0 if provided).  When
                   provided, ``option_leg_premium(leg)`` uses this value
                   instead of the contract's mid price.

    Note:
        ``quantity`` counts contracts (each = 100 shares), not shares.
    """

    model_config = ConfigDict(extra="forbid")

    contract: OptionContractSnapshot
    side: OptionPositionSide
    quantity: int = Field(default=1, ge=1)
    premium: Optional[float] = Field(default=None, ge=0.0)


# ---------------------------------------------------------------------------
# 4. OptionStrategyCandidate
# ---------------------------------------------------------------------------

class OptionStrategyCandidate(BaseModel):
    """
    A candidate option strategy with evidence references.

    Fields:
        underlying:       Underlying ticker symbol (non-empty).
        strategy_type:    One of the supported ``OptionStrategyType`` values.
        legs:             Option legs forming the strategy (may be empty for
                          ``"no_trade"``).
        net_premium:      Total net premium for the strategy.  Positive =
                          debit paid; negative = credit received.
        trade_expression: Preferred trade vehicle; defaults to ``"option"``.
        evidence_refs:    Supporting ToolResult evidence.
        rationale:        Human-readable strategy rationale (optional).
        metadata:         Optional key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    underlying: str = Field(min_length=1)
    strategy_type: OptionStrategyType
    legs: list[OptionLeg] = Field(default_factory=list)
    net_premium: float = 0.0
    trade_expression: OptionTradeExpression = "option"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    rationale: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionStrategyCandidate":
        if self.underlying.strip() == "":
            raise ValueError("underlying must not be whitespace-only.")
        return self


# ---------------------------------------------------------------------------
# 5. OptionPayoffResult
# ---------------------------------------------------------------------------

class OptionPayoffResult(BaseModel):
    """
    Output of a deterministic option payoff calculation.

    Net premium convention:
        - ``net_premium > 0``: debit paid (long call, long put, debit spreads).
        - ``net_premium < 0``: credit received (CSP, covered call).

    Fields:
        strategy_type:       The strategy this result describes.
        underlying:          Underlying ticker symbol (non-empty).
        net_premium:         Total net premium (signed).
        max_loss:            Maximum possible loss in dollars (>= 0; ``None``
                             when undetermined, e.g. covered call without
                             cost basis).
        max_gain:            Maximum possible gain in dollars (>= 0; ``None``
                             when theoretically unlimited or undetermined).
        breakeven:           Breakeven price of the underlying at expiry.
                             ``float`` for single breakeven; ``list[float]``
                             for strategies with multiple breakevens (e.g.
                             straddles); ``None`` when undetermined.
        risk_reward_ratio:   ``max_gain / max_loss`` (>= 0; ``None`` when
                             max_gain is unlimited, undetermined, or
                             max_loss is zero).
        cash_required:       Cash collateral required for strategy (>= 0;
                             e.g. for CSP: strike × contracts × 100).
        collateral_required: Total collateral required (>= 0; often equals
                             cash_required).
        notes:               Human-readable calculation notes.
        warnings:            Advisory warnings about the result.
        evidence_refs:       Optional supporting ToolResult evidence.
        calculation_version: Schema/version tag for auditability.
    """

    model_config = ConfigDict(extra="forbid")

    strategy_type: OptionStrategyType
    underlying: str = Field(min_length=1)
    net_premium: float  # signed; positive = debit, negative = credit
    max_loss: Optional[float] = Field(default=None, ge=0.0)
    max_gain: Optional[float] = Field(default=None, ge=0.0)
    breakeven: Optional[Union[float, list[float]]] = None
    risk_reward_ratio: Optional[float] = Field(default=None, ge=0.0)
    cash_required: Optional[float] = Field(default=None, ge=0.0)
    collateral_required: Optional[float] = Field(default=None, ge=0.0)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    calculation_version: str = "option_schema_v1"

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionPayoffResult":
        if self.underlying.strip() == "":
            raise ValueError("underlying must not be whitespace-only.")
        return self


# ---------------------------------------------------------------------------
# 6. OptionLiquidityCheck
# ---------------------------------------------------------------------------

class OptionLiquidityCheck(BaseModel):
    """
    Aggregate liquidity assessment for a set of option contracts.

    Produced by ``calculate_option_liquidity(contracts)`` which evaluates
    all contracts together and returns one summary result.

    Fields:
        contract_count:          Number of contracts evaluated (>= 0).
        max_bid_ask_spread_pct:  Largest spread fraction across all contracts
                                 (>= 0; ``None`` when no contracts).
        avg_bid_ask_spread_pct:  Average spread fraction (>= 0; ``None``
                                 when no contracts).
        min_volume:              Minimum volume seen across contracts with
                                 available volume data (``None`` when all
                                 contracts lack volume).
        min_open_interest:       Minimum OI seen across contracts with
                                 available OI data (``None`` when all
                                 contracts lack OI).
        status:                  Liquidity classification.
        warnings:                Advisory warnings (e.g. missing data).
        calculation_version:     Schema/version tag for auditability.
    """

    model_config = ConfigDict(extra="forbid")

    contract_count: int = Field(ge=0)
    max_bid_ask_spread_pct: Optional[float] = Field(default=None, ge=0.0)
    avg_bid_ask_spread_pct: Optional[float] = Field(default=None, ge=0.0)
    min_volume: Optional[int] = Field(default=None, ge=0)
    min_open_interest: Optional[int] = Field(default=None, ge=0)
    status: OptionLiquidityStatus
    warnings: list[str] = Field(default_factory=list)
    calculation_version: str = "option_schema_v1"


# ---------------------------------------------------------------------------
# 7. OptionEventRiskCheck
# ---------------------------------------------------------------------------

class OptionEventRiskCheck(BaseModel):
    """
    Result of a deterministic option event risk assessment.

    Evaluates whether a corporate event falls before an option's expiration
    and classifies the resulting risk level.

    Fields:
        underlying:             Underlying ticker symbol (non-empty).
        expiration:             Option expiration date string (non-empty).
        event_type:             Type of corporate event (e.g. ``"earnings"``);
                                ``None`` if unknown.
        event_date:             Date of the event; ``None`` if unknown.
        event_before_expiration: ``True`` if event falls before expiration;
                                 ``False`` if after; ``None`` if
                                 undetermined.
        risk_level:             Event risk classification.
        warnings:               Advisory warnings (e.g. missing data).
        notes:                  Human-readable classification notes.
        calculation_version:    Schema/version tag for auditability.
    """

    model_config = ConfigDict(extra="forbid")

    underlying: str = Field(min_length=1)
    expiration: str = Field(min_length=1)
    event_type: Optional[str] = None
    event_date: Optional[str] = None
    event_before_expiration: Optional[bool] = None
    risk_level: OptionEventRiskLevel
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    calculation_version: str = "option_schema_v1"

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionEventRiskCheck":
        if self.underlying.strip() == "":
            raise ValueError("underlying must not be whitespace-only.")
        if self.expiration.strip() == "":
            raise ValueError("expiration must not be whitespace-only.")
        return self


# ---------------------------------------------------------------------------
# 8. OptionStrategyDecisionSet
# ---------------------------------------------------------------------------

class OptionStrategyDecisionSet(BaseModel):
    """
    Container for all option strategy outputs for one research run / ticker.

    Partial data is explicitly allowed — a set may have candidates but no
    payoff results yet, or vice versa.

    Fields:
        underlying:       Underlying ticker symbol (non-empty).
        schema_version:   Version of this schema contract.
        as_of:            Non-empty date/datetime string.
        chain_snapshot:   Full ``OptionChainSnapshot`` from which candidates
                          were derived (``None`` if not yet populated).
        candidates:       Evaluated strategy candidates.
        payoff_results:   Computed payoff results.
        liquidity_checks: Liquidity assessments for relevant contracts.
        event_risk_checks: Event risk assessments for relevant expirations.
        warnings:         Advisory warnings from validators.
    """

    model_config = ConfigDict(extra="forbid")

    underlying: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    chain_snapshot: Optional[OptionChainSnapshot] = None
    candidates: list[OptionStrategyCandidate] = Field(default_factory=list)
    payoff_results: list[OptionPayoffResult] = Field(default_factory=list)
    liquidity_checks: list[OptionLiquidityCheck] = Field(default_factory=list)
    event_risk_checks: list[OptionEventRiskCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> "OptionStrategyDecisionSet":
        if self.underlying.strip() == "":
            raise ValueError("underlying must not be whitespace-only.")
        if self.as_of.strip() == "":
            raise ValueError("as_of must not be whitespace-only.")
        return self


# ---------------------------------------------------------------------------
# Calculator 1: option_mid_price
# ---------------------------------------------------------------------------

def option_mid_price(contract: OptionContractSnapshot) -> float:
    """
    Return the mid price for *contract*.

    Uses ``contract.mid`` when it is set (allowing an authoritative
    pre-computed mid to override the bid/ask average).  Falls back to
    ``(contract.bid + contract.ask) / 2.0`` otherwise.

    The result is always >= 0 because ``bid >= 0`` and ``ask >= bid``.

    Args:
        contract: An ``OptionContractSnapshot`` instance.

    Returns:
        Per-share mid price as a ``float``.

    Examples::

        c = OptionContractSnapshot(underlying="AAPL", ..., bid=1.50, ask=1.70)
        option_mid_price(c)          # → 1.60

        c2 = OptionContractSnapshot(underlying="AAPL", ..., bid=1.50, ask=1.70, mid=1.65)
        option_mid_price(c2)         # → 1.65  (uses provided mid)
    """
    if contract.mid is not None:
        return contract.mid
    return (contract.bid + contract.ask) / 2.0


# ---------------------------------------------------------------------------
# Calculator 2: option_leg_premium
# ---------------------------------------------------------------------------

def option_leg_premium(leg: OptionLeg) -> float:
    """
    Return the per-share premium for *leg*.

    Uses ``leg.premium`` when explicitly provided.  Falls back to
    ``option_mid_price(leg.contract)`` otherwise.

    The result is always >= 0.

    Args:
        leg: An ``OptionLeg`` instance.

    Returns:
        Per-share premium as a ``float``.

    Note:
        This function returns the raw per-share premium amount (non-negative).
        The sign (credit vs debit) is determined by the payoff calculators,
        not by this function.

    Examples::

        leg = OptionLeg(contract=c, side="long", quantity=1, premium=2.5)
        option_leg_premium(leg)      # → 2.5   (uses provided premium)

        leg2 = OptionLeg(contract=c, side="short", quantity=1)
        option_leg_premium(leg2)     # → 1.60  (falls back to contract mid)
    """
    if leg.premium is not None:
        return leg.premium
    return option_mid_price(leg.contract)


# ---------------------------------------------------------------------------
# Calculator 3: calculate_long_call_payoff
# ---------------------------------------------------------------------------

def calculate_long_call_payoff(
    contract: OptionContractSnapshot,
    premium: Optional[float] = None,
    contracts: int = 1,
) -> OptionPayoffResult:
    """
    Compute the payoff profile for a long call position.

    Requirements:
        - ``contract.option_type`` must be ``"call"``; otherwise raises.
        - ``contracts > 0``; otherwise raises.

    Formulas::

        premium_used = premium if provided else option_mid_price(contract)
        net_premium  = premium_used × contracts × 100   (positive = debit)
        max_loss     = net_premium
        max_gain     = None   (unlimited upside)
        breakeven    = contract.strike + premium_used

    Args:
        contract:  An ``OptionContractSnapshot`` with ``option_type="call"``.
        premium:   Per-share premium override (must be >= 0 if provided).
                   When ``None``, uses ``option_mid_price(contract)``.
        contracts: Number of option contracts (must be > 0).

    Returns:
        An ``OptionPayoffResult`` for the long call strategy.

    Raises:
        ValueError: If ``contract.option_type != "call"``, ``contracts <= 0``,
                    or ``premium < 0``.

    Examples::

        result = calculate_long_call_payoff(call_contract, premium=3.0, contracts=1)
        result.max_loss   # → 300.0
        result.max_gain   # → None   (unlimited)
        result.breakeven  # → strike + 3.0
    """
    if contract.option_type != "call":
        raise ValueError(
            f"calculate_long_call_payoff expects a 'call' contract; "
            f"got {contract.option_type!r}."
        )
    if contracts <= 0:
        raise ValueError(f"contracts must be > 0; got {contracts!r}.")
    if premium is not None and premium < 0:
        raise ValueError(f"premium must be >= 0 if provided; got {premium!r}.")

    premium_used = premium if premium is not None else option_mid_price(contract)
    net_premium = premium_used * contracts * _CONTRACT_MULTIPLIER
    max_loss = net_premium
    breakeven = contract.strike + premium_used

    return OptionPayoffResult(
        strategy_type="long_call",
        underlying=contract.underlying,
        net_premium=net_premium,
        max_loss=max_loss,
        max_gain=None,            # unlimited upside
        breakeven=breakeven,
        risk_reward_ratio=None,   # undefined when max_gain is unlimited
        notes=["Upside is theoretically unlimited."],
    )


# ---------------------------------------------------------------------------
# Calculator 4: calculate_long_put_payoff
# ---------------------------------------------------------------------------

def calculate_long_put_payoff(
    contract: OptionContractSnapshot,
    premium: Optional[float] = None,
    contracts: int = 1,
) -> OptionPayoffResult:
    """
    Compute the payoff profile for a long put position.

    Requirements:
        - ``contract.option_type`` must be ``"put"``; otherwise raises.
        - ``contracts > 0``; otherwise raises.

    Formulas::

        premium_used      = premium if provided else option_mid_price(contract)
        net_premium       = premium_used × contracts × 100
        max_loss          = net_premium
        max_gain          = max(contract.strike - premium_used, 0) × contracts × 100
        breakeven         = contract.strike - premium_used
        risk_reward_ratio = max_gain / max_loss  (None if max_loss == 0)

    Args:
        contract:  An ``OptionContractSnapshot`` with ``option_type="put"``.
        premium:   Per-share premium override (>= 0 if provided).
        contracts: Number of option contracts (must be > 0).

    Returns:
        An ``OptionPayoffResult`` for the long put strategy.

    Raises:
        ValueError: If ``contract.option_type != "put"``, ``contracts <= 0``,
                    or ``premium < 0``.

    Examples::

        result = calculate_long_put_payoff(put_contract, premium=3.0, contracts=1)
        result.max_gain   # → (strike - 3) * 100, capped at 0 when premium > strike
        result.breakeven  # → strike - 3.0
    """
    if contract.option_type != "put":
        raise ValueError(
            f"calculate_long_put_payoff expects a 'put' contract; "
            f"got {contract.option_type!r}."
        )
    if contracts <= 0:
        raise ValueError(f"contracts must be > 0; got {contracts!r}.")
    if premium is not None and premium < 0:
        raise ValueError(f"premium must be >= 0 if provided; got {premium!r}.")

    premium_used = premium if premium is not None else option_mid_price(contract)
    net_premium = premium_used * contracts * _CONTRACT_MULTIPLIER
    max_loss = net_premium
    max_gain_per_share = max(contract.strike - premium_used, 0.0)
    max_gain = max_gain_per_share * contracts * _CONTRACT_MULTIPLIER
    breakeven = contract.strike - premium_used
    risk_reward_ratio = (max_gain / max_loss) if max_loss > 0 else None

    return OptionPayoffResult(
        strategy_type="long_put",
        underlying=contract.underlying,
        net_premium=net_premium,
        max_loss=max_loss,
        max_gain=max_gain,
        breakeven=breakeven,
        risk_reward_ratio=risk_reward_ratio,
    )


# ---------------------------------------------------------------------------
# Calculator 5: calculate_call_debit_spread_payoff
# ---------------------------------------------------------------------------

def calculate_call_debit_spread_payoff(
    long_call: OptionContractSnapshot,
    short_call: OptionContractSnapshot,
    long_premium: Optional[float] = None,
    short_premium: Optional[float] = None,
    contracts: int = 1,
) -> OptionPayoffResult:
    """
    Compute the payoff profile for a call debit spread (bull call spread).

    Structure: buy lower-strike call, sell higher-strike call.

    Requirements:
        - Both contracts must have ``option_type="call"``.
        - Both contracts must have the **same** ``underlying``.
        - Both contracts must have the **same** ``expiration``.
        - ``short_call.strike > long_call.strike``.
        - ``contracts > 0``.

    Formulas::

        long_premium_used  = long_premium or option_mid_price(long_call)
        short_premium_used = short_premium or option_mid_price(short_call)
        net_debit_per_share = long_premium_used - short_premium_used
        net_premium         = net_debit_per_share × contracts × 100
        spread_width        = short_call.strike - long_call.strike
        max_loss            = max(net_premium, 0)
        max_gain            = max(spread_width - net_debit_per_share, 0) × contracts × 100
        breakeven           = long_call.strike + net_debit_per_share
        risk_reward_ratio   = max_gain / max_loss  (None if max_loss == 0)

    Args:
        long_call:      Long (lower-strike) call contract.
        short_call:     Short (higher-strike) call contract.
        long_premium:   Per-share premium override for the long leg.
        short_premium:  Per-share premium override for the short leg.
        contracts:      Number of spreads (must be > 0).

    Returns:
        An ``OptionPayoffResult`` for the call debit spread strategy.

    Raises:
        ValueError: If option types, underlying, expiration, or strike
                    ordering constraints are violated, or ``contracts <= 0``.
    """
    if long_call.option_type != "call":
        raise ValueError(
            f"long_call must be a 'call'; got {long_call.option_type!r}."
        )
    if short_call.option_type != "call":
        raise ValueError(
            f"short_call must be a 'call'; got {short_call.option_type!r}."
        )
    if long_call.underlying != short_call.underlying:
        raise ValueError(
            f"Underlying mismatch: long_call.underlying={long_call.underlying!r}, "
            f"short_call.underlying={short_call.underlying!r}."
        )
    if long_call.expiration != short_call.expiration:
        raise ValueError(
            f"Expiration mismatch: long_call.expiration={long_call.expiration!r}, "
            f"short_call.expiration={short_call.expiration!r}."
        )
    if short_call.strike <= long_call.strike:
        raise ValueError(
            f"short_call.strike ({short_call.strike!r}) must be > "
            f"long_call.strike ({long_call.strike!r})."
        )
    if contracts <= 0:
        raise ValueError(f"contracts must be > 0; got {contracts!r}.")

    long_p = long_premium if long_premium is not None else option_mid_price(long_call)
    short_p = short_premium if short_premium is not None else option_mid_price(short_call)
    net_debit_per_share = long_p - short_p
    net_premium = net_debit_per_share * contracts * _CONTRACT_MULTIPLIER
    spread_width = short_call.strike - long_call.strike
    max_loss = max(net_premium, 0.0)
    max_gain = max(spread_width - net_debit_per_share, 0.0) * contracts * _CONTRACT_MULTIPLIER
    breakeven = long_call.strike + net_debit_per_share
    risk_reward_ratio = (max_gain / max_loss) if max_loss > 0 else None

    return OptionPayoffResult(
        strategy_type="call_debit_spread",
        underlying=long_call.underlying,
        net_premium=net_premium,
        max_loss=max_loss,
        max_gain=max_gain,
        breakeven=breakeven,
        risk_reward_ratio=risk_reward_ratio,
    )


# ---------------------------------------------------------------------------
# Calculator 6: calculate_put_debit_spread_payoff
# ---------------------------------------------------------------------------

def calculate_put_debit_spread_payoff(
    long_put: OptionContractSnapshot,
    short_put: OptionContractSnapshot,
    long_premium: Optional[float] = None,
    short_premium: Optional[float] = None,
    contracts: int = 1,
) -> OptionPayoffResult:
    """
    Compute the payoff profile for a put debit spread (bear put spread).

    Structure: buy higher-strike put, sell lower-strike put.

    Requirements:
        - Both contracts must have ``option_type="put"``.
        - Both contracts must have the **same** ``underlying``.
        - Both contracts must have the **same** ``expiration``.
        - ``long_put.strike > short_put.strike``.
        - ``contracts > 0``.

    Formulas::

        long_premium_used  = long_premium or option_mid_price(long_put)
        short_premium_used = short_premium or option_mid_price(short_put)
        net_debit_per_share = long_premium_used - short_premium_used
        net_premium         = net_debit_per_share × contracts × 100
        spread_width        = long_put.strike - short_put.strike
        max_loss            = max(net_premium, 0)
        max_gain            = max(spread_width - net_debit_per_share, 0) × contracts × 100
        breakeven           = long_put.strike - net_debit_per_share
        risk_reward_ratio   = max_gain / max_loss  (None if max_loss == 0)

    Args:
        long_put:      Long (higher-strike) put contract.
        short_put:     Short (lower-strike) put contract.
        long_premium:  Per-share premium override for the long leg.
        short_premium: Per-share premium override for the short leg.
        contracts:     Number of spreads (must be > 0).

    Returns:
        An ``OptionPayoffResult`` for the put debit spread strategy.

    Raises:
        ValueError: If option types, underlying, expiration, or strike
                    ordering constraints are violated, or ``contracts <= 0``.
    """
    if long_put.option_type != "put":
        raise ValueError(
            f"long_put must be a 'put'; got {long_put.option_type!r}."
        )
    if short_put.option_type != "put":
        raise ValueError(
            f"short_put must be a 'put'; got {short_put.option_type!r}."
        )
    if long_put.underlying != short_put.underlying:
        raise ValueError(
            f"Underlying mismatch: long_put.underlying={long_put.underlying!r}, "
            f"short_put.underlying={short_put.underlying!r}."
        )
    if long_put.expiration != short_put.expiration:
        raise ValueError(
            f"Expiration mismatch: long_put.expiration={long_put.expiration!r}, "
            f"short_put.expiration={short_put.expiration!r}."
        )
    if long_put.strike <= short_put.strike:
        raise ValueError(
            f"long_put.strike ({long_put.strike!r}) must be > "
            f"short_put.strike ({short_put.strike!r})."
        )
    if contracts <= 0:
        raise ValueError(f"contracts must be > 0; got {contracts!r}.")

    long_p = long_premium if long_premium is not None else option_mid_price(long_put)
    short_p = short_premium if short_premium is not None else option_mid_price(short_put)
    net_debit_per_share = long_p - short_p
    net_premium = net_debit_per_share * contracts * _CONTRACT_MULTIPLIER
    spread_width = long_put.strike - short_put.strike
    max_loss = max(net_premium, 0.0)
    max_gain = max(spread_width - net_debit_per_share, 0.0) * contracts * _CONTRACT_MULTIPLIER
    breakeven = long_put.strike - net_debit_per_share
    risk_reward_ratio = (max_gain / max_loss) if max_loss > 0 else None

    return OptionPayoffResult(
        strategy_type="put_debit_spread",
        underlying=long_put.underlying,
        net_premium=net_premium,
        max_loss=max_loss,
        max_gain=max_gain,
        breakeven=breakeven,
        risk_reward_ratio=risk_reward_ratio,
    )


# ---------------------------------------------------------------------------
# Calculator 7: calculate_cash_secured_put_payoff
# ---------------------------------------------------------------------------

def calculate_cash_secured_put_payoff(
    put_contract: OptionContractSnapshot,
    premium: Optional[float] = None,
    contracts: int = 1,
) -> OptionPayoffResult:
    """
    Compute the payoff profile for a cash-secured put.

    Structure: sell a put, hold cash collateral equal to the put obligation.

    Requirements:
        - ``put_contract.option_type`` must be ``"put"``; otherwise raises.
        - ``contracts > 0``; otherwise raises.

    Formulas::

        premium_used        = premium if provided else option_mid_price(put_contract)
        credit              = premium_used × contracts × 100
        net_premium         = −credit                 (negative = credit received)
        cash_required       = put_contract.strike × contracts × 100
        collateral_required = cash_required
        max_gain            = credit
        max_loss            = max(put_contract.strike − premium_used, 0) × contracts × 100
        breakeven           = put_contract.strike − premium_used
        risk_reward_ratio   = max_gain / max_loss     (None if max_loss == 0)

    Args:
        put_contract: An ``OptionContractSnapshot`` with ``option_type="put"``.
        premium:      Per-share premium override (>= 0 if provided).
        contracts:    Number of contracts (must be > 0).

    Returns:
        An ``OptionPayoffResult`` for the cash-secured put strategy.

    Raises:
        ValueError: If ``put_contract.option_type != "put"``,
                    ``contracts <= 0``, or ``premium < 0``.

    Examples::

        result = calculate_cash_secured_put_payoff(put_c, premium=3.0, contracts=1)
        result.net_premium       # → -300.0  (credit received)
        result.cash_required     # → strike × 100
        result.max_gain          # → 300.0
    """
    if put_contract.option_type != "put":
        raise ValueError(
            f"calculate_cash_secured_put_payoff expects a 'put' contract; "
            f"got {put_contract.option_type!r}."
        )
    if contracts <= 0:
        raise ValueError(f"contracts must be > 0; got {contracts!r}.")
    if premium is not None and premium < 0:
        raise ValueError(f"premium must be >= 0 if provided; got {premium!r}.")

    premium_used = premium if premium is not None else option_mid_price(put_contract)
    credit = premium_used * contracts * _CONTRACT_MULTIPLIER
    net_premium = -credit
    cash_required = put_contract.strike * contracts * _CONTRACT_MULTIPLIER
    collateral_required = cash_required
    max_gain = credit
    max_loss = max(put_contract.strike - premium_used, 0.0) * contracts * _CONTRACT_MULTIPLIER
    breakeven = put_contract.strike - premium_used
    risk_reward_ratio = (max_gain / max_loss) if max_loss > 0 else None

    return OptionPayoffResult(
        strategy_type="cash_secured_put",
        underlying=put_contract.underlying,
        net_premium=net_premium,
        max_loss=max_loss,
        max_gain=max_gain,
        breakeven=breakeven,
        risk_reward_ratio=risk_reward_ratio,
        cash_required=cash_required,
        collateral_required=collateral_required,
    )


# ---------------------------------------------------------------------------
# Calculator 8: calculate_covered_call_payoff
# ---------------------------------------------------------------------------

def calculate_covered_call_payoff(
    call_contract: OptionContractSnapshot,
    shares_owned: int = 100,
    stock_cost_basis: Optional[float] = None,
    premium: Optional[float] = None,
    contracts: int = 1,
) -> OptionPayoffResult:
    """
    Compute the payoff profile for a covered call.

    Structure: hold stock, sell an OTM call to collect premium.

    Requirements:
        - ``call_contract.option_type`` must be ``"call"``; otherwise raises.
        - ``contracts > 0``; otherwise raises.
        - ``shares_owned >= contracts × 100``; otherwise raises
          (insufficient shares to cover the call).

    Formulas::

        premium_used = premium if provided else option_mid_price(call_contract)
        credit       = premium_used × contracts × 100
        net_premium  = −credit                 (negative = credit received)

        if stock_cost_basis is provided:
            max_gain   = max(call_contract.strike − stock_cost_basis, 0)
                         × contracts × 100 + credit
            max_loss   = max(stock_cost_basis − premium_used, 0)
                         × contracts × 100
            breakeven  = stock_cost_basis − premium_used
        else:
            max_gain   = None
            max_loss   = None
            breakeven  = None

    Args:
        call_contract:    An ``OptionContractSnapshot`` with
                          ``option_type="call"``.
        shares_owned:     Shares of underlying currently held (>= contracts × 100).
        stock_cost_basis: Average cost per share of the stock held (optional;
                          required to compute max_gain / max_loss / breakeven).
        premium:          Per-share premium override (>= 0 if provided).
        contracts:        Number of contracts (must be > 0).

    Returns:
        An ``OptionPayoffResult`` for the covered call strategy.

    Raises:
        ValueError: If ``call_contract.option_type != "call"``,
                    ``contracts <= 0``, ``shares_owned < contracts × 100``,
                    or ``premium < 0``.

    Examples::

        result = calculate_covered_call_payoff(
            call_c, shares_owned=100, stock_cost_basis=145.0,
            premium=3.0, contracts=1,
        )
        result.net_premium  # → -300.0  (credit received)
        result.max_gain     # → 1300.0  (= max(155-145,0)*100 + 300)
        result.max_loss     # → 14200.0 (= max(145-3,0)*100)
    """
    if call_contract.option_type != "call":
        raise ValueError(
            f"calculate_covered_call_payoff expects a 'call' contract; "
            f"got {call_contract.option_type!r}."
        )
    if contracts <= 0:
        raise ValueError(f"contracts must be > 0; got {contracts!r}.")
    required_shares = contracts * _CONTRACT_MULTIPLIER
    if shares_owned < required_shares:
        raise ValueError(
            f"shares_owned ({shares_owned}) must be >= contracts × 100 "
            f"({required_shares}) to cover the call."
        )
    if premium is not None and premium < 0:
        raise ValueError(f"premium must be >= 0 if provided; got {premium!r}.")

    premium_used = premium if premium is not None else option_mid_price(call_contract)
    credit = premium_used * contracts * _CONTRACT_MULTIPLIER
    net_premium = -credit

    notes = ["Upside is capped at strike price plus premium received."]

    max_gain: Optional[float]
    max_loss: Optional[float]
    breakeven_val: Optional[Union[float, list[float]]]

    if stock_cost_basis is not None:
        max_gain = (
            max(call_contract.strike - stock_cost_basis, 0.0) * contracts * _CONTRACT_MULTIPLIER
            + credit
        )
        max_loss = max(stock_cost_basis - premium_used, 0.0) * contracts * _CONTRACT_MULTIPLIER
        breakeven_val = stock_cost_basis - premium_used
    else:
        max_gain = None
        max_loss = None
        breakeven_val = None
        notes.append(
            "max_gain, max_loss, and breakeven require stock_cost_basis."
        )

    risk_reward_ratio = (
        (max_gain / max_loss)
        if (max_gain is not None and max_loss is not None and max_loss > 0)
        else None
    )

    return OptionPayoffResult(
        strategy_type="covered_call",
        underlying=call_contract.underlying,
        net_premium=net_premium,
        max_loss=max_loss,
        max_gain=max_gain,
        breakeven=breakeven_val,
        risk_reward_ratio=risk_reward_ratio,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Calculator 9: calculate_option_liquidity
# ---------------------------------------------------------------------------

def calculate_option_liquidity(
    contracts: list[OptionContractSnapshot],
    max_acceptable_spread_pct: float = 0.15,
) -> OptionLiquidityCheck:
    """
    Assess the aggregate liquidity of a list of option contracts.

    Operates on the full list together; returns one ``OptionLiquidityCheck``
    summarising the worst-case spread, minimum volume/OI, and overall status.

    Classification rules (applied in order):

    +-------------------+------------------------------------------------------+
    | Status            | Condition                                            |
    +===================+======================================================+
    | ``"unknown"``     | No contracts provided.                               |
    +-------------------+------------------------------------------------------+
    | ``"liquid"``      | max spread_pct <= 10% AND (no OI data OR             |
    |                   | min_open_interest >= 100)                            |
    +-------------------+------------------------------------------------------+
    | ``"acceptable"``  | max spread_pct <= ``max_acceptable_spread_pct``      |
    |                   | (default 15%)                                        |
    +-------------------+------------------------------------------------------+
    | ``"illiquid"``    | otherwise                                            |
    +-------------------+------------------------------------------------------+

    Warning conditions:
        - Zero-mid contracts (spread_pct undefined).
        - Any contract missing ``volume``.
        - Any contract missing ``open_interest``.

    Args:
        contracts:                List of ``OptionContractSnapshot`` to assess.
        max_acceptable_spread_pct: Spread threshold for ``"acceptable"``
                                   classification (default 0.15 = 15%).

    Returns:
        An ``OptionLiquidityCheck`` with aggregate fields populated.

    Examples::

        check = calculate_option_liquidity([long_call, short_call])
        check.status   # → "liquid" / "acceptable" / "illiquid" / "unknown"
    """
    warnings_out: list[str] = []

    if not contracts:
        warnings_out.append(
            "No contracts provided; liquidity cannot be assessed."
        )
        return OptionLiquidityCheck(
            contract_count=0,
            status="unknown",
            warnings=warnings_out,
        )

    spread_pcts: list[float] = []
    volumes: list[int] = []
    open_interests: list[int] = []
    has_missing_volume = False
    has_missing_oi = False

    for c in contracts:
        mid = option_mid_price(c)
        if mid == 0.0:
            warnings_out.append(
                f"Contract {c.underlying} {c.expiration} {c.strike} "
                f"{c.option_type}: mid price is zero; spread_pct set to 0."
            )
            spread_pcts.append(0.0)
        else:
            spread_pct = (c.ask - c.bid) / mid
            spread_pcts.append(spread_pct)

        if c.volume is not None:
            volumes.append(c.volume)
        else:
            has_missing_volume = True

        if c.open_interest is not None:
            open_interests.append(c.open_interest)
        else:
            has_missing_oi = True

    if has_missing_volume:
        warnings_out.append("Some contracts are missing volume data.")
    if has_missing_oi:
        warnings_out.append("Some contracts are missing open_interest data.")

    max_spread = max(spread_pcts)
    avg_spread = sum(spread_pcts) / len(spread_pcts)
    min_vol = min(volumes) if volumes else None
    min_oi = min(open_interests) if open_interests else None

    status: OptionLiquidityStatus
    if max_spread <= _LIQUID_MAX_SPREAD_PCT and (min_oi is None or min_oi >= _LIQUID_MIN_OI):
        status = "liquid"
    elif max_spread <= max_acceptable_spread_pct:
        status = "acceptable"
    else:
        status = "illiquid"

    return OptionLiquidityCheck(
        contract_count=len(contracts),
        max_bid_ask_spread_pct=max_spread,
        avg_bid_ask_spread_pct=avg_spread,
        min_volume=min_vol,
        min_open_interest=min_oi,
        status=status,
        warnings=warnings_out,
    )


# ---------------------------------------------------------------------------
# Calculator 10: assess_option_event_risk
# ---------------------------------------------------------------------------

def assess_option_event_risk(
    underlying: str,
    expiration: str,
    event_type: Optional[str] = None,
    event_date: Optional[str] = None,
) -> OptionEventRiskCheck:
    """
    Assess whether a corporate event falls before an option's expiration.

    No external data is fetched.  The caller provides the event information;
    this function classifies the risk deterministically.

    Classification rules:

    +------------+----------------------------------------------------------+
    | risk_level | Condition                                                |
    +============+==========================================================+
    | ``"unknown"``| ``event_type`` or ``event_date`` is ``None``           |
    +------------+----------------------------------------------------------+
    | ``"high"`` | event_before_expiration AND event_type in               |
    |            | ``{"earnings", "major_event"}``                          |
    +------------+----------------------------------------------------------+
    | ``"medium"``| event_before_expiration AND event_type not in high set |
    +------------+----------------------------------------------------------+
    | ``"low"``  | event_before_expiration is ``False``                    |
    +------------+----------------------------------------------------------+

    Date comparison is lexicographic on ISO-format strings (``"YYYY-MM-DD"``).

    Args:
        underlying:  Underlying ticker symbol.
        expiration:  Option expiration date string (ISO format preferred).
        event_type:  Type of corporate event (e.g. ``"earnings"``,
                     ``"dividend"``); ``None`` → ``"unknown"`` risk.
        event_date:  ISO date string of the event; ``None`` → ``"unknown"``.

    Returns:
        An ``OptionEventRiskCheck`` with ``risk_level`` and
        ``event_before_expiration`` populated.

    Examples::

        check = assess_option_event_risk("AAPL", "2026-06-20",
                                         event_type="earnings",
                                         event_date="2026-06-01")
        check.risk_level                # → "high"
        check.event_before_expiration   # → True

        check2 = assess_option_event_risk("AAPL", "2026-06-20")
        check2.risk_level               # → "unknown"
    """
    warnings_out: list[str] = []
    notes_out: list[str] = []

    if event_type is None or event_date is None:
        risk_level: OptionEventRiskLevel = "unknown"
        event_before_expiration = None
        warnings_out.append(
            "Insufficient event data: both event_type and event_date are "
            "required to assess event risk."
        )
    else:
        try:
            event_before = event_date <= expiration
        except TypeError:
            risk_level = "unknown"
            event_before_expiration = None
            warnings_out.append(
                f"Could not compare dates: event_date={event_date!r}, "
                f"expiration={expiration!r}."
            )
        else:
            event_before_expiration = event_before
            if event_before:
                if event_type in {"earnings", "major_event"}:
                    risk_level = "high"
                    notes_out.append(
                        f"High risk: '{event_type}' event on {event_date!r} "
                        f"falls before option expiration ({expiration!r})."
                    )
                else:
                    risk_level = "medium"
                    notes_out.append(
                        f"Medium risk: '{event_type}' event on {event_date!r} "
                        f"falls before option expiration ({expiration!r})."
                    )
            else:
                risk_level = "low"
                notes_out.append(
                    f"Low risk: event on {event_date!r} is after or on "
                    f"option expiration ({expiration!r})."
                )

    return OptionEventRiskCheck(
        underlying=underlying,
        expiration=expiration,
        event_type=event_type,
        event_date=event_date,
        event_before_expiration=event_before_expiration,
        risk_level=risk_level,
        warnings=warnings_out,
        notes=notes_out,
    )


# ---------------------------------------------------------------------------
# Adapter: option_strategy_tool_result_from_decision_set
# ---------------------------------------------------------------------------

def option_strategy_tool_result_from_decision_set(
    run_id: str,
    decision_set: OptionStrategyDecisionSet,
    target: Optional[str] = None,
    calculation_version: str = "option_schema_v1",
) -> ToolResult:
    """
    Wrap an ``OptionStrategyDecisionSet`` into the existing ``ToolResult``
    model.

    The resulting ``ToolResult`` is suitable for submission to
    ``EvidenceStore.add_tool_result()``.  The caller is responsible for
    persisting it — this function does not write to disk.

    The payload includes the full serialised decision_set, including
    ``chain_snapshot`` when present.

    Args:
        run_id:              Run context ID (from ``create_run_context``).
        decision_set:        ``OptionStrategyDecisionSet`` to wrap.
        target:              Research target string; defaults to
                             ``decision_set.underlying``.
        calculation_version: Schema/version tag embedded in outputs for
                             auditability.

    Returns:
        A ``ToolResult`` with:

        - ``tool_name = "option_strategy_decision_set"``
        - ``evidence_id`` — deterministic hash of outputs.
        - ``outputs`` — serialised decision_set dict plus
          ``calculation_version``.  Includes ``chain_snapshot``,
          ``candidates``, ``payoff_results``, ``liquidity_checks``, and
          ``event_risk_checks``.
        - ``inputs`` — ``{underlying, as_of, calculation_version}``.
        - ``ticker = decision_set.underlying`` — option data is
          ticker-specific.

    Determinism guarantee:
        Same ``run_id`` + identical ``decision_set`` field values → same
        ``evidence_id``.
    """
    resolved_target = target if target is not None else decision_set.underlying
    ds_dict = decision_set.model_dump()
    outputs: dict[str, Any] = {
        **ds_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_OPTION_TOOL_NAME,
        target=resolved_target,
        metric_group=_OPTION_METRIC_GROUP,
        payload=outputs,
    )

    description = (
        f"OptionStrategyDecisionSet underlying={decision_set.underlying!r}"
        f" as_of={decision_set.as_of!r}"
        f" ({len(decision_set.candidates)} candidate(s),"
        f" {len(decision_set.payoff_results)} payoff result(s),"
        f" {len(decision_set.liquidity_checks)} liquidity check(s),"
        f" {len(decision_set.event_risk_checks)} event risk check(s))"
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_OPTION_TOOL_NAME,
        run_id=run_id,
        ticker=decision_set.underlying,
        inputs={
            "underlying": decision_set.underlying,
            "as_of": decision_set.as_of,
            "calculation_version": calculation_version,
        },
        outputs=outputs,
        description=description,
    )


# ---------------------------------------------------------------------------
# Helper 1: summarize_option_strategy_decision_set
# ---------------------------------------------------------------------------

def summarize_option_strategy_decision_set(
    decision_set: OptionStrategyDecisionSet,
) -> dict[str, Any]:
    """
    Return a concise summary of *decision_set*.

    Returns:
        A ``dict`` with:

        - ``"underlying"`` (str): Underlying ticker.
        - ``"as_of"`` (str): Snapshot date string.
        - ``"candidate_count"`` (int): Number of strategy candidates.
        - ``"payoff_result_count"`` (int): Number of payoff results.
        - ``"liquidity_check_count"`` (int): Number of liquidity checks.
        - ``"event_risk_check_count"`` (int): Number of event risk checks.
        - ``"strategy_types_present"`` (list[str]): Unique strategy types
          in candidates (insertion order preserved).
        - ``"warnings_count"`` (int): Number of decision-set-level warnings.
        - ``"has_high_event_risk"`` (bool): ``True`` if any event risk check
          has ``risk_level="high"``.
        - ``"chain_snapshot_present"`` (bool): ``True`` if ``chain_snapshot``
          is not ``None``.
    """
    strategy_types_present = list(
        dict.fromkeys(c.strategy_type for c in decision_set.candidates)
    )
    has_high_event_risk = any(
        r.risk_level == "high" for r in decision_set.event_risk_checks
    )

    return {
        "underlying": decision_set.underlying,
        "as_of": decision_set.as_of,
        "candidate_count": len(decision_set.candidates),
        "payoff_result_count": len(decision_set.payoff_results),
        "liquidity_check_count": len(decision_set.liquidity_checks),
        "event_risk_check_count": len(decision_set.event_risk_checks),
        "strategy_types_present": strategy_types_present,
        "warnings_count": len(decision_set.warnings),
        "has_high_event_risk": has_high_event_risk,
        "chain_snapshot_present": decision_set.chain_snapshot is not None,
    }


# ---------------------------------------------------------------------------
# Helper 2: validate_option_strategy_decision_set
# ---------------------------------------------------------------------------

def validate_option_strategy_decision_set(
    decision_set: OptionStrategyDecisionSet,
) -> list[str]:
    """
    Perform lightweight advisory validation on *decision_set*.

    Returns warning strings for soft issues.  Does not raise exceptions.
    Does not integrate with ``ValidationReport`` in this phase.
    Does not mutate *decision_set*.

    Checked conditions:
        1.  No candidates.
        2.  Non-``"no_trade"`` candidate with no legs.
        3.  Candidate with no evidence_refs.
        4.  Payoff result with ``max_loss=None`` for a strategy where risk
            should be defined (warns for all non-``"no_trade"`` strategies).
        5.  Liquidity check with ``status="illiquid"``.
        6.  Event risk check with ``risk_level="high"``.
        7.  ``chain_snapshot`` is ``None``.
        8.  ``chain_snapshot.underlying`` mismatches
            ``decision_set.underlying``.
        9.  Candidate ``underlying`` mismatches ``decision_set.underlying``.
        10. Payoff result ``underlying`` mismatches
            ``decision_set.underlying``.

    Args:
        decision_set: ``OptionStrategyDecisionSet`` to validate.

    Returns:
        List of warning strings (may be empty for a clean set).

    Examples::

        warnings = validate_option_strategy_decision_set(ds)
        assert all(isinstance(w, str) for w in warnings)
        # Never raises.
    """
    warnings_out: list[str] = []

    # 1. No candidates
    if not decision_set.candidates:
        warnings_out.append(
            "OptionStrategyDecisionSet has no candidates. "
            "At least one strategy candidate is expected."
        )

    # 2. Non-no_trade candidates with no legs
    for c in decision_set.candidates:
        if c.strategy_type != "no_trade" and not c.legs:
            warnings_out.append(
                f"OptionStrategyCandidate strategy_type={c.strategy_type!r} "
                f"for underlying {decision_set.underlying!r} has no legs defined."
            )

    # 3. Candidates with no evidence_refs
    for c in decision_set.candidates:
        if not c.evidence_refs:
            warnings_out.append(
                f"OptionStrategyCandidate strategy_type={c.strategy_type!r} "
                f"for underlying {decision_set.underlying!r} has no evidence_refs. "
                "Candidates should cite supporting evidence."
            )

    # 4. Payoff results with max_loss=None (except no_trade)
    for pr in decision_set.payoff_results:
        if pr.strategy_type != "no_trade" and pr.max_loss is None:
            warnings_out.append(
                f"OptionPayoffResult strategy_type={pr.strategy_type!r} "
                f"for underlying {decision_set.underlying!r} has max_loss=None. "
                "Max loss should be defined for this strategy type."
            )

    # 5. Illiquid liquidity checks
    for liq in decision_set.liquidity_checks:
        if liq.status == "illiquid":
            warnings_out.append(
                f"OptionLiquidityCheck for underlying {decision_set.underlying!r} "
                "has status='illiquid'. Wide spreads may significantly impact "
                "realized payoff."
            )

    # 6. High event risk
    for erc in decision_set.event_risk_checks:
        if erc.risk_level == "high":
            warnings_out.append(
                f"OptionEventRiskCheck for underlying {decision_set.underlying!r} "
                f"expiration={erc.expiration!r} has risk_level='high'. "
                "Consider whether option strategy is appropriate given event risk."
            )

    # 7. Chain snapshot missing
    if decision_set.chain_snapshot is None:
        warnings_out.append(
            f"OptionStrategyDecisionSet for underlying {decision_set.underlying!r} "
            "has no chain_snapshot. A chain snapshot is recommended for evidence."
        )

    # 8. Chain snapshot underlying mismatch
    if (
        decision_set.chain_snapshot is not None
        and decision_set.chain_snapshot.underlying != decision_set.underlying
    ):
        warnings_out.append(
            f"chain_snapshot.underlying ({decision_set.chain_snapshot.underlying!r}) "
            f"does not match decision_set.underlying ({decision_set.underlying!r})."
        )

    # 9. Candidate underlying mismatch
    for c in decision_set.candidates:
        if c.underlying != decision_set.underlying:
            warnings_out.append(
                f"OptionStrategyCandidate.underlying ({c.underlying!r}) does not "
                f"match decision_set.underlying ({decision_set.underlying!r})."
            )

    # 10. Payoff result underlying mismatch
    for pr in decision_set.payoff_results:
        if pr.underlying != decision_set.underlying:
            warnings_out.append(
                f"OptionPayoffResult.underlying ({pr.underlying!r}) does not match "
                f"decision_set.underlying ({decision_set.underlying!r})."
            )

    return warnings_out
