# Phase 2D: Allocation / Position Sizing Tool Schema Foundation

**Date**: 2026-05-21
**Status**: Implemented
**Author**: Reliability Refactor — Phase 2D
**Depends on**: Phase 2C (`docs/reliability_phase_2c_macro_toolresult_schema.md`)

---

## A. Purpose

Phase 2D creates **standalone, Pydantic-compatible schema models, deterministic
calculators, and ToolResult wrappers** for allocation and position sizing.

Its goal is to answer the following design questions:

1. How does the system represent current portfolio positions in a structured,
   auditable, evidence-first way?
2. How are target allocations expressed and constrained?
3. How are position sizing calculations performed deterministically — without
   LLM inference — and wrapped into `ToolResult` evidence?
4. How is stop-loss risk assessed against a portfolio risk budget?
5. How does the system detect missing or inconsistent allocation coverage?

### What Phase 2D does

- Creates `lib/reliability/allocation.py` with:
  - `AllocationAction` — Literal type alias (eight values).
  - `PositionDirection` — Literal type alias (`"long"`, `"short"`, `"flat"`).
  - `RiskBudgetStatus` — Literal type alias (four values).
  - `PositionSnapshot` — one current position in a portfolio.
  - `PortfolioSnapshot` — container for positions, cash, and total value.
  - `AllocationTarget` — target allocation for one ticker with ordering constraint.
  - `RiskBudget` — portfolio-level risk budget parameters.
  - `PositionSizingResult` — output of a deterministic sizing calculation.
  - `StopLossRiskResult` — output of a deterministic stop-loss risk calculation.
  - `AllocationDecisionSet` — container for all allocation outputs.
  - `compute_position_market_value()` — market value from snapshot.
  - `compute_current_allocation_pct()` — allocation fraction from snapshot.
  - `calculate_position_sizing()` — required trade to reach target allocation.
  - `calculate_cash_released_from_trim()` — cash received from partial sell.
  - `calculate_cash_needed_for_add()` — cash required for partial buy.
  - `calculate_stop_loss_risk()` — classify stop-loss risk against budget.
  - `allocation_tool_result_from_decision_set()` — wraps into `ToolResult`.
  - `summarize_allocation_decision_set()` — coverage summary.
  - `validate_portfolio_snapshot()` — advisory soft-validator.
  - `validate_allocation_decision_set()` — advisory soft-validator.
- Updates `lib/reliability/__init__.py` to export all new symbols.
- Creates `scripts/test_reliability_allocation.py` — 272 assertions.
- Creates this design document.

### What Phase 2D does NOT do

- Does **not** fetch live prices from any broker, exchange, or data vendor.
- Does **not** integrate with any broker or custodian API.
- Does **not** execute trades.
- Does **not** compute volatility-scaled position sizes (Kelly, CVaR, ATR-stop).
- Does **not** implement option payoff calculations.
- Does **not** implement a Portfolio Agent.
- Does **not** modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any
  workflow module.
- Does **not** call the Claude API.
- Does **not** modify any live prompt.
- Does **not** wire allocation schemas into any Streamlit page.

---

## B. Why Allocation Must Be Deterministic and Evidence-First

The same principle that governs financial and macro analysis applies to
position sizing:

> **Deterministic computation, agentic interpretation, auditable synthesis.**

A Portfolio Agent must **not** invent position sizes, allocation percentages,
or risk assessments.  All sizing figures must derive from deterministic
calculators operating on concrete `PortfolioSnapshot` inputs.  Results are
wrapped into `ToolResult` evidence that agents cite via `EvidenceRef`.

This eliminates:
- LLM hallucination of portfolio weights (e.g., inventing "5% allocation" without a source)
- Inconsistent sizing logic across agent runs
- Untraceable risk decisions that cannot be audited or replicated

---

## C. Schemas Overview

### `PositionSnapshot`

One current position in a portfolio.

| Field | Required | Notes |
|---|---|---|
| `ticker` | Yes | Non-empty ticker symbol (whitespace-only rejected) |
| `shares` | Yes | >= 0 |
| `current_price` | **Yes** | > 0; **required** — market-value-only positions are invalid |
| `as_of` | **Yes** | Non-empty date/datetime string (whitespace-only rejected) |
| `source` | No | Non-empty source label; defaults to `"synthetic"` |
| `market_value` | No | >= 0 if provided; preferred over computed value |
| `direction` | No | `"long"`, `"short"`, or `"flat"`; defaults to `"long"` |
| `cost_basis` | No | >= 0 if provided |
| `metadata` | No | Arbitrary key/value |

**Note:** `current_price` is required in Phase 2D.  Market-value-only positions
are not supported — every `PositionSnapshot` must carry a sourced price.

### `PortfolioSnapshot`

Container for portfolio state.

| Field | Required | Notes |
|---|---|---|
| `portfolio_id` | Yes | Non-empty unique identifier (whitespace-only rejected) |
| `as_of` | Yes | Non-empty date/datetime string (whitespace-only rejected) |
| `total_value` | Yes | > 0 |
| `cash` | Yes | >= 0 |
| `positions` | No | May be empty |
| `source` | No | Non-empty source label; defaults to `"synthetic"` |
| `metadata` | No | Arbitrary key/value |

### `AllocationTarget`

Target allocation for one ticker.  All fractions are 0.0–1.0.

| Field | Required | Notes |
|---|---|---|
| `ticker` | Yes | Non-empty |
| `target_allocation_pct` | Yes | 0.0–1.0 (0 = exit) |
| `min_allocation_pct` | No | Must be <= target if provided |
| `max_allocation_pct` | No | Must be >= target if provided |
| `action` | No | Advisory `AllocationAction`; defaults to `"hold"` |
| `evidence_refs` | No | Supporting ToolResult evidence |
| `rationale` | No | Human-readable rationale |

**Ordering constraint:** `min_allocation_pct <= target_allocation_pct <= max_allocation_pct`
(enforced by `@model_validator`).

### `RiskBudget`

Portfolio-level risk budget.  All fractions are 0.0–1.0.

| Field | Required | Notes |
|---|---|---|
| `max_single_position_risk_pct` | Yes | > 0; max portfolio-loss fraction from one stop-loss hit |
| `max_sector_allocation_pct` | Yes | > 0; max fraction in one sector |
| `max_cash_pct` | Yes | > 0; max cash fraction |
| `max_position_allocation_pct` | No | 0.0–1.0; optional cap on any single position's target weight |
| `notes` | No | Free-text notes |

When `max_position_allocation_pct` is set, `validate_allocation_decision_set`
will warn if any `AllocationTarget.target_allocation_pct` exceeds it.

### `PositionSizingResult`

Output of `calculate_position_sizing()`.

| Field | Notes |
|---|---|
| `ticker` | Non-empty ticker symbol |
| `current_price` | **Required** (> 0); price used for the calculation |
| `current_shares` | Shares held at calculation time (>= 0) |
| `current_market_value` | Computed as `shares * current_price` (>= 0) |
| `current_allocation_pct` | Fraction of portfolio (>= 0) |
| `target_allocation_pct` | Target fraction (0.0–1.0) |
| `target_market_value` | `target_allocation_pct * portfolio.total_value` (>= 0) |
| `required_trade_value` | Positive = buy, negative = sell |
| `required_shares` | None when price not available |
| `cash_impact` | `= -required_trade_value` |
| `action` | Inferred from required trade vs tolerance (or from `target.action`) |
| `evidence_refs` | Optional supporting evidence |

### `StopLossRiskResult`

Output of `calculate_stop_loss_risk()`.

| Field | Notes |
|---|---|
| `ticker` | Non-empty ticker symbol |
| `shares` | Shares held (>= 0) |
| `current_price` | Current price per share (> 0) |
| `stop_price` | Stop-loss trigger price (>= 0) |
| `position_market_value` | **Required** `shares * current_price` (>= 0) |
| `max_loss_amount` | `max(current_price - stop_price, 0) * shares` (>= 0) |
| `portfolio_loss_pct` | `max_loss_amount / portfolio.total_value` (>= 0) |
| `risk_budget_status` | `"within_budget"`, `"near_limit"`, or `"over_budget"` |
| `evidence_refs` | Optional supporting evidence |

### `AllocationDecisionSet`

Container for all allocation outputs for one portfolio research run.
Partial data is explicitly allowed.

---

## D. Deterministic Calculators

### `compute_position_market_value(position) -> float`

Returns `position.market_value` when set; otherwise `position.shares * position.current_price`.
Since `current_price` is required on `PositionSnapshot`, this function always
succeeds — it never raises `ValueError` for missing price.

### `compute_current_allocation_pct(position, portfolio) -> float`

Returns `market_value / portfolio.total_value`.

### `calculate_position_sizing(portfolio, target, current_price=None) -> PositionSizingResult`

Computes the required trade to move `target.ticker` to `target.target_allocation_pct`.

When the ticker is not in `portfolio.positions`, `current_price` must be supplied
explicitly — otherwise `ValueError` is raised.

When a matching position exists, `current_price` (if supplied) overrides
`position.current_price` for **both** `current_market_value` and `required_shares`
computation.

```
current_market_value  = current_shares * resolved_price
target_market_value   = target_allocation_pct * portfolio.total_value
required_trade_value  = target_market_value - current_market_value
required_shares       = required_trade_value / resolved_price
cash_impact           = -required_trade_value
```

Action resolution (tolerance = 0.1% of portfolio total_value):

| Condition | Action |
|---|---|
| `target.action != "no_action"` | use `target.action` directly |
| `|required_trade_value| < tolerance` | `"hold"` |
| `target_mv < tolerance` and `current_shares > 0` | `"exit"` |
| `required_trade_value > tolerance` | `"add"` |
| `required_trade_value < -tolerance` | `"trim"` |

### `calculate_stop_loss_risk(position, portfolio, stop_price, risk_budget) -> StopLossRiskResult`

```
max_loss_amount    = max(current_price - stop_price, 0) * shares
portfolio_loss_pct = max_loss_amount / portfolio.total_value
```

Risk budget status:

| Status | Condition |
|---|---|
| `"within_budget"` | `portfolio_loss_pct < 80%` of `max_single_position_risk_pct` |
| `"near_limit"` | `80% ≤ portfolio_loss_pct ≤ max_single_position_risk_pct` |
| `"over_budget"` | `portfolio_loss_pct > max_single_position_risk_pct` |

---

## E. Example `PortfolioSnapshot` JSON

```json
{
  "portfolio_id": "PORTFOLIO_20260521_001",
  "as_of": "2026-05-21",
  "positions": [
    {
      "ticker": "AAPL",
      "shares": 100.0,
      "current_price": 185.0,
      "market_value": 18500.0,
      "direction": "long",
      "cost_basis": 150.0
    },
    {
      "ticker": "NVDA",
      "shares": 20.0,
      "current_price": 900.0,
      "market_value": 18000.0,
      "direction": "long"
    }
  ],
  "cash": 13500.0,
  "total_value": 50000.0,
  "notes": []
}
```

---

## F. Example `AllocationDecisionSet` JSON

```json
{
  "portfolio_id": "PORTFOLIO_20260521_001",
  "as_of": "2026-05-21",
  "schema_version": "1.0",
  "targets": [
    {
      "ticker": "AAPL",
      "target_allocation_pct": 0.40,
      "min_allocation_pct": 0.30,
      "max_allocation_pct": 0.50,
      "action": "add",
      "evidence_refs": [
        {
          "evidence_id": "RUN_001:valuation_model:AAPL:dcf:abc123",
          "tool_name": "valuation_model",
          "field_path": "intrinsic_value_per_share",
          "excerpt": "DCF fair value $195"
        }
      ],
      "rationale": "Underweight vs target; strong earnings setup"
    }
  ],
  "sizing_results": [
    {
      "ticker": "AAPL",
      "current_shares": 100.0,
      "current_market_value": 18500.0,
      "current_allocation_pct": 0.37,
      "target_allocation_pct": 0.40,
      "target_market_value": 20000.0,
      "required_trade_value": 1500.0,
      "required_shares": 8.11,
      "cash_impact": -1500.0,
      "action": "add",
      "calculation_version": "allocation_schema_v1"
    }
  ],
  "stop_loss_results": [
    {
      "ticker": "AAPL",
      "shares": 100.0,
      "current_price": 185.0,
      "stop_price": 170.0,
      "max_loss_amount": 1500.0,
      "portfolio_loss_pct": 0.03,
      "risk_budget_status": "over_budget",
      "calculation_version": "allocation_schema_v1"
    }
  ],
  "notes": [],
  "warnings": []
}
```

---

## G. Example ToolResult Payload Shape

```python
from lib.reliability.allocation import (
    AllocationTarget, AllocationDecisionSet,
    allocation_tool_result_from_decision_set,
)

target = AllocationTarget(ticker="AAPL", target_allocation_pct=0.40)
ds = AllocationDecisionSet(
    portfolio_id="PORTFOLIO_20260521_001",
    as_of="2026-05-21",
    targets=[target],
)
tr = allocation_tool_result_from_decision_set("RUN_20260521_001", ds)

# tr.tool_name == "allocation_model"
# tr.ticker == None  (not ticker-specific)
# tr.evidence_id == "RUN_20260521_001:allocation_model:portfolio:allocation_decision_set:<hash>"
# tr.outputs includes: portfolio_id, as_of, targets, sizing_results, calculation_version
```

---

## H. Helper Functions

### `summarize_allocation_decision_set(decision_set) -> dict`

Returns `portfolio_id`, `as_of`, `target_count`, `sizing_result_count`,
`stop_loss_result_count`, `tickers_targeted`, `tickers_sized`,
`tickers_stop_loss`, `total_target_allocation_pct`, `warnings_count`.

### `validate_portfolio_snapshot(portfolio) -> list[str]`

Advisory soft-validator.  Returns warning strings, never raises.  Checks:
- No positions.
- Cash > total_value.
- Sum of market values + cash differs materially from total_value (tolerance 5%;
  only when all positions can be valued).
- Duplicate tickers.
- Provided `market_value` differs materially from `shares * current_price`
  (tolerance 1%).

### `validate_allocation_decision_set(decision_set) -> list[str]`

Advisory soft-validator.  Returns warning strings, never raises.  Checks:
1. No `sizing_results` in the decision set.
2. Duplicate tickers in `targets`.
3. `AllocationTarget` with no `evidence_refs`.
4. `PositionSizingResult` with no `evidence_refs`.
5. `StopLossRiskResult` with `risk_budget_status == "over_budget"`.
6. `AllocationTarget.target_allocation_pct` exceeds
   `risk_budget.max_position_allocation_pct` (when both are set).

---

## I. Guardrails

| Rule | Reason |
|---|---|
| Calculators do not fetch live prices | Prices must come from a sourced `PositionSnapshot` |
| Allocation Agent must not invent weights | `AgentResult` findings must cite `EvidenceRef` pointing to `AllocationDecisionSet` ToolResults |
| No broker integration in this phase | Live price and execution belong to later phases |
| No volatility-scaled sizing | Kelly, CVaR, ATR-stop sizing belong to later phases |
| No option payoff | Option tool phase covers option-specific sizing |
| UI portfolio view belongs to Cockpit phase | No Streamlit changes in this phase |

---

## J. Relationship to Future Phases

| Phase | Description | Allocation schema role |
|---|---|---|
| **Phase 2D (this)** | Schema + calculator foundation | Define data contracts |
| **Phase 2E** | Macro-aware sector analysis | Pass macro regime to sector agent |
| **Phase 2F** | Macro-aware scanner | Filter by regime signal |
| **Phase 3A** | Horizon integration | Consume `HorizonRecommendation` → `AllocationTarget` |
| **Phase 3B** | Portfolio Agent prompt contract | Use `AllocationDecisionSet` ToolResult as evidence |
| **Phase 3C** | Volatility-scaled sizing | ATR-stop, Kelly fraction sizing |
| **Phase 3D** | Option strategy sizing | Option-specific position sizing |
| **Phase 4** | Cockpit UI | Render `AllocationDecisionSet` as portfolio cards |
| **Phase 5** | Memory | Persist allocation history across sessions |

---

## Appendix: Exported Symbols

```python
from lib.reliability.allocation import (
    # Literal aliases
    AllocationAction,
    PositionDirection,
    RiskBudgetStatus,
    # Models
    PositionSnapshot,
    PortfolioSnapshot,
    AllocationTarget,
    RiskBudget,
    PositionSizingResult,
    StopLossRiskResult,
    AllocationDecisionSet,
    # Calculators
    compute_position_market_value,
    compute_current_allocation_pct,
    calculate_position_sizing,
    calculate_cash_released_from_trim,
    calculate_cash_needed_for_add,
    calculate_stop_loss_risk,
    # Adapter
    allocation_tool_result_from_decision_set,
    # Helpers
    summarize_allocation_decision_set,
    validate_portfolio_snapshot,
    validate_allocation_decision_set,
)
```

## Appendix: Test Script

```bash
python3 scripts/test_reliability_allocation.py
```

288 assertions across groups A–R (Phase 2D second targeted fix):
- A: `AllocationAction` (8), `PositionDirection` (3), `RiskBudgetStatus` (4) (18)
- B: `PositionSnapshot` — required `current_price`/`as_of`/`source`, optional fields, whitespace validators (22)
- C: `PortfolioSnapshot` — required fields, source, whitespace rejection (13)
- D: `AllocationTarget` — creation, min/target/max constraint, all 8 actions (23)
- E: `RiskBudget` — creation, `max_position_allocation_pct`, field constraints (10)
- F: `PositionSizingResult` (with `current_price`) + `StopLossRiskResult` (with `position_market_value`) (18)
- G: `AllocationDecisionSet` — `risk_budget`, partial data, defaults (15)
- H: `compute_position_market_value` — market_value priority, price fallback, edge cases (8)
- I: `compute_current_allocation_pct` — correctness, determinism (6)
- J: `calculate_position_sizing` — add/hold/trim/exit/new position/price-override/explicit-action (27)
- K: `calculate_cash_released_from_trim` + `calculate_cash_needed_for_add` (13)
- L: `calculate_stop_loss_risk` — within/near/over budget, `position_market_value` (18)
- M: `allocation_tool_result_from_decision_set` — shape, determinism (20)
- N: `summarize_allocation_decision_set` — all keys (14)
- O: `validate_portfolio_snapshot` — all warning conditions (8)
- P: `validate_allocation_decision_set` — new warning conditions (10)
- Q: Serialization roundtrip — all model types with new required fields (17)
- R: No forbidden live or network modules; `__init__.py` exports (13+)
