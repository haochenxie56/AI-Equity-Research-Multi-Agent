"""
lib/reliability/allocation.py

Standalone schema models, deterministic calculators, and ToolResult wrappers
for allocation and position sizing.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no live data fetching.
  - Reuses EvidenceRef from lib.reliability.schemas.
  - Reuses make_evidence_id from lib.reliability.adapters.
  - Reuses ToolResult from lib.reliability.schemas.
  - Deterministic calculators: same inputs → same outputs.
  - No broker integration. No live price fetching.
  - No volatility-scaled sizing (Kelly, CVaR) — belongs to later phases.
  - No option payoff — belongs to the Option Tool phase.
  - UI dashboard belongs to the Investment Cockpit phase.

See docs/reliability_phase_2d_allocation_position_sizing_schema.md for full
design rationale and rollout context.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id
from lib.reliability.schemas import EvidenceRef, ToolResult


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

AllocationAction = Literal[
    "add",
    "hold",
    "trim",
    "exit",
    "avoid",
    "wait",
    "rebalance",
    "no_action",
]

PositionDirection = Literal["long", "short", "flat"]

RiskBudgetStatus = Literal["within_budget", "near_limit", "over_budget", "unknown"]


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_ALLOCATION_TOOL_NAME: str = "allocation_model"
_ALLOCATION_METRIC_GROUP: str = "allocation_decision_set"

# Tolerance for "materially different" checks in advisory validators.
_PORTFOLIO_VALUE_TOLERANCE: float = 0.05  # 5% — portfolio value reconciliation
_POSITION_MV_TOLERANCE: float = 0.01      # 1% — position market_value vs price*shares

# Stop-loss near-limit threshold: 80% of max budget triggers near_limit.
_NEAR_LIMIT_FRACTION: float = 0.80

# Action inference tolerance: differences below 0.1% of portfolio are treated
# as "hold" (rounding noise, not a meaningful rebalance signal).
_ACTION_TOLERANCE_FRACTION: float = 0.001


# ---------------------------------------------------------------------------
# 1. PositionSnapshot
# ---------------------------------------------------------------------------

class PositionSnapshot(BaseModel):
    """
    One current position held in a portfolio.

    Fields:
        ticker:        Non-empty ticker symbol (whitespace-only rejected).
        shares:        Number of shares held (>= 0).
        current_price: Required current market price per share (> 0).
        direction:     ``"long"``, ``"short"``, or ``"flat"``.
        cost_basis:    Average cost per share (>= 0 if provided; optional).
        market_value:  Pre-computed market value (>= 0 if provided).
        as_of:         Non-empty date/datetime string (whitespace-only rejected).
        source:        Non-empty source label; defaults to ``"synthetic"``.
        metadata:      Optional key/value metadata.

    Note:
        ``current_price`` is required.  Market-value-only positions are not
        valid in Phase 2D; every position must carry a live or sourced price.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    shares: float = Field(ge=0.0)
    current_price: float = Field(gt=0.0)
    direction: PositionDirection = "long"
    cost_basis: Optional[float] = None
    market_value: Optional[float] = None
    as_of: str = Field(min_length=1)
    source: str = Field(default="synthetic", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_optional_numeric_fields(self) -> "PositionSnapshot":
        if self.ticker.strip() == "":
            raise ValueError("ticker must not be whitespace-only.")
        if self.as_of.strip() == "":
            raise ValueError("as_of must not be whitespace-only.")
        if self.source.strip() == "":
            raise ValueError("source must not be whitespace-only.")
        if self.market_value is not None and self.market_value < 0:
            raise ValueError(
                f"market_value must be >= 0 if provided; got {self.market_value!r}."
            )
        if self.cost_basis is not None and self.cost_basis < 0:
            raise ValueError(
                f"cost_basis must be >= 0 if provided; got {self.cost_basis!r}."
            )
        return self


# ---------------------------------------------------------------------------
# 2. PortfolioSnapshot
# ---------------------------------------------------------------------------

class PortfolioSnapshot(BaseModel):
    """
    Container for current portfolio state.

    Fields:
        portfolio_id: Non-empty unique identifier (whitespace-only rejected).
        total_value:  Total portfolio value — positions market value + cash
                      (must be > 0).
        cash:         Cash balance (>= 0).
        positions:    List of current position snapshots (may be empty).
        as_of:        Non-empty date/datetime string (whitespace-only rejected).
        source:       Non-empty source label; defaults to ``"synthetic"``.
        metadata:     Optional key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str = Field(min_length=1)
    total_value: float = Field(gt=0.0)
    cash: float = Field(ge=0.0)
    positions: list[PositionSnapshot] = Field(default_factory=list)
    as_of: str = Field(min_length=1)
    source: str = Field(default="synthetic", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "PortfolioSnapshot":
        if self.portfolio_id.strip() == "":
            raise ValueError("portfolio_id must not be whitespace-only.")
        if self.as_of.strip() == "":
            raise ValueError("as_of must not be whitespace-only.")
        if self.source.strip() == "":
            raise ValueError("source must not be whitespace-only.")
        return self


# ---------------------------------------------------------------------------
# 3. AllocationTarget
# ---------------------------------------------------------------------------

class AllocationTarget(BaseModel):
    """
    Target allocation for one ticker.

    Fractions are 0.0–1.0 (not percentage integers).  A 5% target is
    represented as ``0.05``.

    Fields:
        ticker:                Non-empty ticker symbol.
        target_allocation_pct: Target fraction of portfolio (0.0–1.0).
        min_allocation_pct:    Minimum acceptable fraction (optional;
                               must be <= target if provided).
        max_allocation_pct:    Maximum acceptable fraction (optional;
                               must be >= target if provided).
        action:                Advisory action for reaching this target.
        evidence_refs:         Supporting ToolResult evidence.
        rationale:             Human-readable rationale (optional).

    Constraint:
        ``min_allocation_pct <= target_allocation_pct <= max_allocation_pct``
        whenever both bounds are provided.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    target_allocation_pct: float = Field(ge=0.0, le=1.0)
    min_allocation_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_allocation_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    action: AllocationAction = "hold"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    rationale: Optional[str] = None

    @model_validator(mode="after")
    def _check_min_target_max_ordering(self) -> "AllocationTarget":
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


# ---------------------------------------------------------------------------
# 4. RiskBudget
# ---------------------------------------------------------------------------

class RiskBudget(BaseModel):
    """
    Portfolio-level risk budget parameters.

    All fraction fields are 0.0–1.0 (not percentage integers).

    Fields:
        max_single_position_risk_pct: Maximum acceptable portfolio-loss fraction
            from one stop-loss hit on a single position (e.g. 0.02 = 2%).
        max_sector_allocation_pct:    Maximum fraction of portfolio allowed in
            one sector (e.g. 0.30 = 30%).
        max_cash_pct:                 Maximum acceptable cash fraction before
            the portfolio is considered over-allocated to cash.
        max_position_allocation_pct:  Optional maximum fraction of portfolio
            in any single position (e.g. 0.10 = 10%).  When set, targets
            above this level will be flagged by the advisory validator.
        notes:                        Optional free-text notes.
    """

    model_config = ConfigDict(extra="forbid")

    max_single_position_risk_pct: float = Field(gt=0.0, le=1.0)
    max_sector_allocation_pct: float = Field(gt=0.0, le=1.0)
    max_cash_pct: float = Field(gt=0.0, le=1.0)
    max_position_allocation_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: str = ""


# ---------------------------------------------------------------------------
# 5. PositionSizingResult
# ---------------------------------------------------------------------------

class PositionSizingResult(BaseModel):
    """
    Output of a deterministic position sizing calculation.

    All monetary fields are in the same currency as the portfolio.
    Fraction fields are 0.0–1.0.

    Fields:
        ticker:                 Non-empty ticker symbol.
        current_price:          Current market price per share (> 0).
        current_shares:         Shares currently held (>= 0).
        current_market_value:   Current market value of the position (>= 0).
        current_allocation_pct: Current fraction of total portfolio (>= 0).
        target_allocation_pct:  Target fraction of total portfolio (0.0–1.0).
        target_market_value:    Target market value = target_pct * total_value (>= 0).
        required_trade_value:   Dollar value of required trade (positive=buy,
                                negative=sell; unconstrained sign).
        required_shares:        Shares to trade (positive=buy, negative=sell;
                                unconstrained sign; ``None`` when price unavailable).
        cash_impact:            Cash change from the trade (negative=spending,
                                positive=receiving cash; unconstrained sign).
        action:                 Inferred allocation action.
        evidence_refs:          Optional supporting ToolResult evidence.
        calculation_version:    Schema/version tag for auditability.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    current_price: float = Field(gt=0.0)
    current_shares: float = Field(ge=0.0)
    current_market_value: float = Field(ge=0.0)
    current_allocation_pct: float = Field(ge=0.0)
    target_allocation_pct: float = Field(ge=0.0, le=1.0)
    target_market_value: float = Field(ge=0.0)
    required_trade_value: float          # may be negative (trim/exit)
    required_shares: Optional[float] = None   # may be negative (trim/exit)
    cash_impact: float                   # may be negative (add)
    action: AllocationAction
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    calculation_version: str = "allocation_schema_v1"


# ---------------------------------------------------------------------------
# 6. StopLossRiskResult
# ---------------------------------------------------------------------------

class StopLossRiskResult(BaseModel):
    """
    Output of a deterministic stop-loss risk calculation.

    Fields:
        ticker:               Non-empty ticker symbol.
        shares:               Shares held at time of calculation (>= 0).
        current_price:        Current market price per share (> 0).
        stop_price:           Stop-loss trigger price (>= 0).
        position_market_value: Current position market value (>= 0).
        max_loss_amount:      ``max(current_price - stop_price, 0) * shares`` (>= 0).
        portfolio_loss_pct:   ``max_loss_amount / portfolio.total_value`` (>= 0).
        risk_budget_status:   Classification against the risk budget.
        evidence_refs:        Optional supporting ToolResult evidence.
        calculation_version:  Schema/version tag for auditability.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    shares: float = Field(ge=0.0)
    current_price: float = Field(gt=0.0)
    stop_price: float = Field(ge=0.0)
    position_market_value: float = Field(ge=0.0)
    max_loss_amount: float = Field(ge=0.0)
    portfolio_loss_pct: float = Field(ge=0.0)
    risk_budget_status: RiskBudgetStatus
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    calculation_version: str = "allocation_schema_v1"


# ---------------------------------------------------------------------------
# 7. AllocationDecisionSet
# ---------------------------------------------------------------------------

class AllocationDecisionSet(BaseModel):
    """
    Container for all allocation outputs for one portfolio research run.

    Partial data is explicitly allowed — a set may have targets but no sizing
    results yet, or vice versa.

    Fields:
        portfolio_id:      Non-empty identifier (matches source snapshot).
        as_of:             Non-empty date/datetime string.
        schema_version:    Version of this schema contract.
        risk_budget:       Optional risk budget for this decision set.
        targets:           Allocation targets (one per ticker, advisory).
        sizing_results:    Computed sizing results (one per ticker).
        stop_loss_results: Computed stop-loss risk results.
        notes:             Optional free-text notes.
        warnings:          Advisory warnings from validators.
    """

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    schema_version: str = "1.0"
    risk_budget: Optional[RiskBudget] = None
    targets: list[AllocationTarget] = Field(default_factory=list)
    sizing_results: list[PositionSizingResult] = Field(default_factory=list)
    stop_loss_results: list[StopLossRiskResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Calculator 1: compute_position_market_value
# ---------------------------------------------------------------------------

def compute_position_market_value(position: PositionSnapshot) -> float:
    """
    Return the market value of *position*.

    Prefers ``position.market_value`` when set.  Falls back to
    ``position.shares * position.current_price``.

    Since ``current_price`` is required on ``PositionSnapshot``, this
    function will always succeed unless ``market_value`` is explicitly set
    to an unexpected type.

    Args:
        position: A ``PositionSnapshot`` instance.

    Returns:
        Market value as a ``float``.

    Examples::

        pos = PositionSnapshot(ticker="AAPL", shares=100, current_price=150.0,
                               as_of="2026-05-21")
        assert compute_position_market_value(pos) == 15000.0
    """
    if position.market_value is not None:
        return position.market_value
    return position.shares * position.current_price


# ---------------------------------------------------------------------------
# Calculator 2: compute_current_allocation_pct
# ---------------------------------------------------------------------------

def compute_current_allocation_pct(
    position: PositionSnapshot,
    portfolio: PortfolioSnapshot,
) -> float:
    """
    Return the current allocation fraction for *position* within *portfolio*.

    Args:
        position:  A ``PositionSnapshot`` instance.
        portfolio: The ``PortfolioSnapshot`` containing this position.

    Returns:
        Allocation fraction (0.0–1.0+).  Values > 1.0 indicate an
        inconsistency in the snapshot (position market value exceeds total).

    Examples::

        pct = compute_current_allocation_pct(pos, portfolio)
        assert 0.0 <= pct <= 1.0
    """
    mv = compute_position_market_value(position)
    return mv / portfolio.total_value


# ---------------------------------------------------------------------------
# Calculator 3: calculate_position_sizing
# ---------------------------------------------------------------------------

def calculate_position_sizing(
    portfolio: PortfolioSnapshot,
    target: AllocationTarget,
    current_price: Optional[float] = None,
) -> PositionSizingResult:
    """
    Compute the required trade to move *target.ticker* to its target allocation.

    Does not modify the portfolio.  Does not execute any trade.

    Args:
        portfolio:     Current portfolio snapshot.
        target:        Desired allocation target for one ticker.
        current_price: Price per share override.  When provided, takes
                       precedence over the position's own ``current_price``.
                       Required when the ticker has no existing position.

    Returns:
        A ``PositionSizingResult`` with all trade fields populated.

    Raises:
        ValueError: If the ticker is not in the portfolio and *current_price*
                    is not provided.
        ValueError: If *current_price* is provided but is not > 0.

    Behavior:
        - Matching position exists: use ``position.current_price`` (or override).
        - No matching position: requires explicit *current_price* argument;
          ``current_shares = 0``, ``current_market_value = 0``.
        - ``target_market_value = target.target_allocation_pct * portfolio.total_value``
        - ``required_trade_value = target_market_value - current_market_value``
        - ``required_shares = required_trade_value / current_price``
        - ``cash_impact = -required_trade_value``

    Action inference (tolerance = 0.1% of portfolio total_value):

    +------------------+------------------------------------------------------+
    | Condition        | Action inferred                                      |
    +==================+======================================================+
    | target.action    | use target.action (unless "no_action")               |
    +------------------+------------------------------------------------------+
    | |required| < tol | ``"hold"`` — difference is noise                     |
    +------------------+------------------------------------------------------+
    | target ≈ 0 AND   | ``"exit"`` — close position entirely                |
    | current_shares>0 |                                                      |
    +------------------+------------------------------------------------------+
    | required > tol   | ``"add"`` — increase position                       |
    +------------------+------------------------------------------------------+
    | required < −tol  | ``"trim"`` — reduce position                        |
    +------------------+------------------------------------------------------+

    Examples::

        result = calculate_position_sizing(portfolio, target, current_price=150.0)
        assert result.action in ("add", "hold", "trim", "exit")
        assert result.cash_impact == -result.required_trade_value
    """
    if current_price is not None and current_price <= 0:
        raise ValueError(
            f"current_price must be > 0; got {current_price!r}."
        )

    # Locate existing position for this ticker.
    matching = [p for p in portfolio.positions if p.ticker == target.ticker]

    if matching:
        pos = matching[0]
        price: float = (
            current_price if current_price is not None else pos.current_price
        )
        current_shares = pos.shares
        current_mv = pos.shares * price
    else:
        # Ticker not yet in portfolio — treat as new position.
        if current_price is None:
            raise ValueError(
                f"Ticker '{target.ticker}' is not in the portfolio and "
                "current_price is not provided. Cannot compute position sizing."
            )
        price = current_price
        current_shares = 0.0
        current_mv = 0.0

    current_alloc_pct = current_mv / portfolio.total_value
    target_mv = target.target_allocation_pct * portfolio.total_value
    required_trade_value = target_mv - current_mv
    cash_impact = -required_trade_value
    required_shares: float = required_trade_value / price

    # Determine action: use target.action unless it is "no_action".
    tolerance = _ACTION_TOLERANCE_FRACTION * portfolio.total_value
    action: AllocationAction
    if target.action != "no_action":
        action = target.action
    elif abs(required_trade_value) < tolerance:
        action = "hold"
    elif target_mv < tolerance and current_shares > 0:
        action = "exit"
    elif required_trade_value > 0:
        action = "add"
    else:
        action = "trim"

    return PositionSizingResult(
        ticker=target.ticker,
        current_price=price,
        current_shares=current_shares,
        current_market_value=current_mv,
        current_allocation_pct=current_alloc_pct,
        target_allocation_pct=target.target_allocation_pct,
        target_market_value=target_mv,
        required_trade_value=required_trade_value,
        required_shares=required_shares,
        cash_impact=cash_impact,
        action=action,
    )


# ---------------------------------------------------------------------------
# Calculator 4: calculate_cash_released_from_trim
# ---------------------------------------------------------------------------

def calculate_cash_released_from_trim(
    shares_to_trim: float,
    current_price: float,
) -> float:
    """
    Compute cash received from trimming a position.

    Args:
        shares_to_trim: Number of shares to sell (must be >= 0).
        current_price:  Price per share (must be > 0).

    Returns:
        Cash received (non-negative float).

    Raises:
        ValueError: If *shares_to_trim* < 0 or *current_price* <= 0.

    Examples::

        cash = calculate_cash_released_from_trim(50, 100.0)
        assert cash == 5000.0
    """
    if shares_to_trim < 0:
        raise ValueError(
            f"shares_to_trim must be >= 0; got {shares_to_trim!r}."
        )
    if current_price <= 0:
        raise ValueError(
            f"current_price must be > 0; got {current_price!r}."
        )
    return shares_to_trim * current_price


# ---------------------------------------------------------------------------
# Calculator 5: calculate_cash_needed_for_add
# ---------------------------------------------------------------------------

def calculate_cash_needed_for_add(
    shares_to_add: float,
    current_price: float,
) -> float:
    """
    Compute cash required to add to a position.

    Args:
        shares_to_add:  Number of shares to buy (must be >= 0).
        current_price:  Price per share (must be > 0).

    Returns:
        Cash required (non-negative float).

    Raises:
        ValueError: If *shares_to_add* < 0 or *current_price* <= 0.

    Examples::

        cash = calculate_cash_needed_for_add(100, 50.0)
        assert cash == 5000.0
    """
    if shares_to_add < 0:
        raise ValueError(
            f"shares_to_add must be >= 0; got {shares_to_add!r}."
        )
    if current_price <= 0:
        raise ValueError(
            f"current_price must be > 0; got {current_price!r}."
        )
    return shares_to_add * current_price


# ---------------------------------------------------------------------------
# Calculator 6: calculate_stop_loss_risk
# ---------------------------------------------------------------------------

def calculate_stop_loss_risk(
    position: PositionSnapshot,
    portfolio: PortfolioSnapshot,
    stop_price: float,
    risk_budget: RiskBudget,
) -> StopLossRiskResult:
    """
    Compute stop-loss risk for *position* and classify it against *risk_budget*.

    Calculation::

        position_market_value = shares * current_price
        max_loss_amount       = max(current_price - stop_price, 0) * shares
        portfolio_loss_pct    = max_loss_amount / portfolio.total_value

    Risk budget classification:

    +-------------------+----------------------------------------------------+
    | Status            | Condition                                          |
    +===================+====================================================+
    | ``within_budget`` | portfolio_loss_pct < 80% of max_single_pos_risk   |
    +-------------------+----------------------------------------------------+
    | ``near_limit``    | 80% <= portfolio_loss_pct <= max_single_pos_risk  |
    +-------------------+----------------------------------------------------+
    | ``over_budget``   | portfolio_loss_pct > max_single_pos_risk          |
    +-------------------+----------------------------------------------------+

    Args:
        position:    Current position snapshot.
        portfolio:   Portfolio containing this position (used for total_value).
        stop_price:  Stop-loss trigger price.
        risk_budget: Portfolio risk budget parameters.

    Returns:
        A ``StopLossRiskResult`` with risk classification populated.

    Examples::

        result = calculate_stop_loss_risk(pos, portfolio, stop_price=140.0, risk_budget=rb)
        assert result.risk_budget_status in ("within_budget", "near_limit", "over_budget")
        assert result.max_loss_amount >= 0.0
    """
    current_price = position.current_price
    shares = position.shares
    position_market_value = shares * current_price
    max_loss_amount = max(current_price - stop_price, 0.0) * shares
    portfolio_loss_pct = max_loss_amount / portfolio.total_value

    max_risk = risk_budget.max_single_position_risk_pct
    near_limit_threshold = _NEAR_LIMIT_FRACTION * max_risk

    status: RiskBudgetStatus
    if portfolio_loss_pct > max_risk:
        status = "over_budget"
    elif portfolio_loss_pct >= near_limit_threshold:
        status = "near_limit"
    else:
        status = "within_budget"

    return StopLossRiskResult(
        ticker=position.ticker,
        shares=shares,
        current_price=current_price,
        stop_price=stop_price,
        position_market_value=position_market_value,
        max_loss_amount=max_loss_amount,
        portfolio_loss_pct=portfolio_loss_pct,
        risk_budget_status=status,
    )


# ---------------------------------------------------------------------------
# Adapter: allocation_tool_result_from_decision_set
# ---------------------------------------------------------------------------

def allocation_tool_result_from_decision_set(
    run_id: str,
    decision_set: AllocationDecisionSet,
    target: str = "portfolio",
    calculation_version: str = "allocation_schema_v1",
) -> ToolResult:
    """
    Wrap an ``AllocationDecisionSet`` into the existing ``ToolResult`` model.

    The resulting ``ToolResult`` is suitable for submission to
    ``EvidenceStore.add_tool_result()``.  The caller is responsible for
    persisting it — this function does not write to disk.

    Args:
        run_id:              Run context ID (from ``create_run_context``).
        decision_set:        ``AllocationDecisionSet`` to wrap.
        target:              Research target string; defaults to
                             ``"portfolio"``.
        calculation_version: Schema/version tag embedded in outputs for
                             auditability.

    Returns:
        A ``ToolResult`` with:

        - ``tool_name = "allocation_model"``
        - ``evidence_id`` — deterministic hash of outputs.
        - ``outputs`` — serialised decision_set dict plus calculation_version.
        - ``inputs`` — ``{portfolio_id, as_of, calculation_version}``.
        - ``ticker = None`` — allocation data is not ticker-specific.
        - ``description`` — includes portfolio_id, as_of, and counts.

    Determinism guarantee:
        Calling this function twice with the same ``run_id`` and identical
        ``decision_set`` field values produces the same ``evidence_id``.

    Examples::

        tr = allocation_tool_result_from_decision_set("run_001", ds)
        assert tr.tool_name == "allocation_model"
        assert tr.ticker is None
        assert "allocation_model" in tr.evidence_id
    """
    ds_dict = decision_set.model_dump()
    outputs: dict[str, Any] = {
        **ds_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_ALLOCATION_TOOL_NAME,
        target=target,
        metric_group=_ALLOCATION_METRIC_GROUP,
        payload=outputs,
    )

    description = (
        f"AllocationDecisionSet portfolio_id={decision_set.portfolio_id!r}"
        f" as_of={decision_set.as_of!r}"
        f" ({len(decision_set.targets)} target(s),"
        f" {len(decision_set.sizing_results)} sizing result(s),"
        f" {len(decision_set.stop_loss_results)} stop-loss result(s))"
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_ALLOCATION_TOOL_NAME,
        run_id=run_id,
        ticker=None,  # Allocation data is not ticker-specific
        inputs={
            "portfolio_id": decision_set.portfolio_id,
            "as_of": decision_set.as_of,
            "calculation_version": calculation_version,
        },
        outputs=outputs,
        description=description,
    )


# ---------------------------------------------------------------------------
# Helper 1: summarize_allocation_decision_set
# ---------------------------------------------------------------------------

def summarize_allocation_decision_set(
    decision_set: AllocationDecisionSet,
) -> dict[str, Any]:
    """
    Return a concise summary of *decision_set*.

    Returns:
        A ``dict`` with:

        - ``"portfolio_id"`` (str): Portfolio identifier.
        - ``"as_of"`` (str): Snapshot date string.
        - ``"target_count"`` (int): Number of allocation targets.
        - ``"sizing_result_count"`` (int): Number of sizing results.
        - ``"stop_loss_result_count"`` (int): Number of stop-loss results.
        - ``"tickers_targeted"`` (list[str]): Tickers with allocation targets.
        - ``"tickers_sized"`` (list[str]): Tickers with sizing results.
        - ``"tickers_stop_loss"`` (list[str]): Tickers with stop-loss results.
        - ``"total_target_allocation_pct"`` (float): Sum of all target
          fractions (should be <= 1.0 for a healthy portfolio).
        - ``"warnings_count"`` (int): Number of decision-set-level warnings.

    Examples::

        summary = summarize_allocation_decision_set(ds)
        summary["target_count"]               # → int
        summary["total_target_allocation_pct"]  # → float
    """
    tickers_targeted = [t.ticker for t in decision_set.targets]
    tickers_sized = [r.ticker for r in decision_set.sizing_results]
    tickers_stop_loss = [r.ticker for r in decision_set.stop_loss_results]
    total_target_pct = sum(t.target_allocation_pct for t in decision_set.targets)

    return {
        "portfolio_id": decision_set.portfolio_id,
        "as_of": decision_set.as_of,
        "target_count": len(decision_set.targets),
        "sizing_result_count": len(decision_set.sizing_results),
        "stop_loss_result_count": len(decision_set.stop_loss_results),
        "tickers_targeted": tickers_targeted,
        "tickers_sized": tickers_sized,
        "tickers_stop_loss": tickers_stop_loss,
        "total_target_allocation_pct": total_target_pct,
        "warnings_count": len(decision_set.warnings),
    }


# ---------------------------------------------------------------------------
# Helper 2: validate_portfolio_snapshot
# ---------------------------------------------------------------------------

def validate_portfolio_snapshot(portfolio: PortfolioSnapshot) -> list[str]:
    """
    Perform lightweight advisory validation on *portfolio*.

    Returns warning strings for soft issues.  Does not raise exceptions.
    Does not integrate with ``ValidationReport`` in this phase.

    Checked conditions:
        - No positions in the snapshot.
        - Cash balance exceeds total_value.
        - Sum of position market values + cash differs materially from
          total_value (tolerance 5%).
        - Duplicate ticker symbols.
        - Provided market_value differs materially from shares * current_price
          (tolerance 1%, when market_value is set).

    Args:
        portfolio: ``PortfolioSnapshot`` to validate.

    Returns:
        List of warning strings (may be empty for a clean snapshot).

    Examples::

        warnings = validate_portfolio_snapshot(portfolio)
        assert all(isinstance(w, str) for w in warnings)
    """
    warnings_out: list[str] = []

    # 1. No positions
    if not portfolio.positions:
        warnings_out.append(
            "PortfolioSnapshot has no positions. "
            "At least one position is expected for allocation calculations."
        )

    # 2. Cash > total_value
    if portfolio.cash > portfolio.total_value:
        warnings_out.append(
            f"Portfolio cash ({portfolio.cash:.2f}) exceeds total_value "
            f"({portfolio.total_value:.2f}). "
            "This may indicate a data inconsistency."
        )

    # 3. Sum of market values + cash vs total_value
    position_mv_sum = sum(compute_position_market_value(p) for p in portfolio.positions)
    gross_sum = position_mv_sum + portfolio.cash
    if (
        portfolio.positions  # only check when positions exist
        and abs(gross_sum - portfolio.total_value)
        > _PORTFOLIO_VALUE_TOLERANCE * portfolio.total_value
    ):
        warnings_out.append(
            f"Sum of position market values ({position_mv_sum:.2f}) + cash "
            f"({portfolio.cash:.2f}) = {gross_sum:.2f} differs materially "
            f"from total_value ({portfolio.total_value:.2f}). "
            f"Tolerance is {_PORTFOLIO_VALUE_TOLERANCE * 100:.0f}%."
        )

    # 4. Duplicate tickers
    seen: set[str] = set()
    for pos in portfolio.positions:
        if pos.ticker in seen:
            warnings_out.append(
                f"Duplicate position ticker '{pos.ticker}' in portfolio snapshot. "
                "Each ticker should appear at most once."
            )
        seen.add(pos.ticker)

    # 5. Provided market_value vs shares * current_price mismatch
    for pos in portfolio.positions:
        if pos.market_value is not None:
            computed_mv = pos.shares * pos.current_price
            denom = max(abs(pos.market_value), abs(computed_mv), 1.0)
            if abs(pos.market_value - computed_mv) > _POSITION_MV_TOLERANCE * denom:
                warnings_out.append(
                    f"Position '{pos.ticker}': provided market_value "
                    f"({pos.market_value:.2f}) differs materially from "
                    f"shares ({pos.shares}) * current_price ({pos.current_price}) "
                    f"= {computed_mv:.2f}. "
                    f"Tolerance is {_POSITION_MV_TOLERANCE * 100:.0f}%."
                )

    return warnings_out


# ---------------------------------------------------------------------------
# Helper 3: validate_allocation_decision_set
# ---------------------------------------------------------------------------

def validate_allocation_decision_set(
    decision_set: AllocationDecisionSet,
) -> list[str]:
    """
    Perform lightweight advisory validation on *decision_set*.

    Returns warning strings for soft issues.  Does not raise exceptions.
    Does not integrate with ``ValidationReport`` in this phase.

    Checked conditions:
        1. No sizing results.
        2. Duplicate ticker in targets.
        3. AllocationTarget with no evidence_refs.
        4. PositionSizingResult with no evidence_refs.
        5. StopLossRiskResult with risk_budget_status == ``"over_budget"``.
        6. Target allocation_pct exceeds risk_budget.max_position_allocation_pct
           (when risk_budget and max_position_allocation_pct are set).
        7. Duplicate targets for the same ticker.

    Args:
        decision_set: ``AllocationDecisionSet`` to validate.

    Returns:
        List of warning strings (may be empty for a clean set).

    Examples::

        warnings = validate_allocation_decision_set(ds)
        assert all(isinstance(w, str) for w in warnings)
    """
    warnings_out: list[str] = []

    # 1. No sizing results
    if not decision_set.sizing_results:
        warnings_out.append(
            "AllocationDecisionSet has no sizing_results. "
            "At least one PositionSizingResult is expected."
        )

    # 2 & 7. Duplicate tickers in targets
    seen_tickers: set[str] = set()
    for t in decision_set.targets:
        if t.ticker in seen_tickers:
            warnings_out.append(
                f"Duplicate AllocationTarget for ticker '{t.ticker}'. "
                "Each ticker should have at most one allocation target."
            )
        seen_tickers.add(t.ticker)

    # 3. Targets with no evidence_refs
    for t in decision_set.targets:
        if not t.evidence_refs:
            warnings_out.append(
                f"AllocationTarget for ticker '{t.ticker}' has no evidence_refs. "
                "Targets should cite supporting evidence."
            )

    # 4. Sizing results with no evidence_refs
    for r in decision_set.sizing_results:
        if not r.evidence_refs:
            warnings_out.append(
                f"PositionSizingResult for ticker '{r.ticker}' has no evidence_refs. "
                "Sizing results should cite supporting evidence."
            )

    # 5. Over-budget stop-loss results
    for slr in decision_set.stop_loss_results:
        if slr.risk_budget_status == "over_budget":
            warnings_out.append(
                f"StopLossRiskResult for ticker '{slr.ticker}' has "
                "risk_budget_status='over_budget'. "
                "Review position size or stop-loss level."
            )

    # 6. Target allocation exceeds max_position_allocation_pct
    if (
        decision_set.risk_budget is not None
        and decision_set.risk_budget.max_position_allocation_pct is not None
    ):
        max_pos_pct = decision_set.risk_budget.max_position_allocation_pct
        for t in decision_set.targets:
            if t.target_allocation_pct > max_pos_pct:
                warnings_out.append(
                    f"AllocationTarget for ticker '{t.ticker}' has "
                    f"target_allocation_pct={t.target_allocation_pct:.4f} which "
                    f"exceeds risk_budget.max_position_allocation_pct={max_pos_pct:.4f}."
                )

    return warnings_out
