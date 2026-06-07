# Phase 2E: Option Data + Strategy Tool Schema Foundation

**Date**: 2026-05-21
**Status**: Implemented (contract-aware API)
**Author**: Reliability Refactor — Phase 2E
**Depends on**: Phase 2D (`docs/reliability_phase_2d_allocation_position_sizing_schema.md`)

---

## A. Purpose

Phase 2E creates **standalone, Pydantic-compatible schema models** for option
contract data, basic option strategy analysis, and their corresponding
ToolResult wrappers.  Option strategies — long calls, long puts, debit
spreads, cash-secured puts, covered calls — are the primary vehicle through
which the equity research system expresses leveraged or risk-defined
investment theses.

Its goal is to answer the following design questions:

1. How does the system represent sourced option market data in a structured,
   auditable, evidence-first way?
2. How are option payoff calculations structured as deterministic outputs
   that LLM agents can cite?
3. How does the system assess option liquidity and event risk in a
   repeatable, auditable manner?
4. How are option strategy decisions wrapped into `ToolResult` evidence
   for citation by LLM agents?

### What Phase 2E does

- Creates `lib/reliability/options.py` with:
  - `OptionType` — Literal alias: `"call"` or `"put"`.
  - `OptionPositionSide` — Literal alias: `"long"` or `"short"`.
  - `OptionStrategyType` — Literal alias (11 strategy types).
  - `OptionLiquidityStatus` — Literal alias (4 levels).
  - `OptionEventRiskLevel` — Literal alias (4 levels).
  - `OptionTradeExpression` — Literal alias (6 values).
  - `OptionContractSnapshot` — Market data for a single option contract.
  - `OptionChainSnapshot` — Container for a set of contracts; requires `underlying_price`.
  - `OptionLeg` — One leg of a multi-leg strategy.
  - `OptionStrategyCandidate` — A candidate strategy with evidence refs.
  - `OptionPayoffResult` — Output of a deterministic payoff calculation.
  - `OptionLiquidityCheck` — Output of an aggregate liquidity assessment.
  - `OptionEventRiskCheck` — Output of an event risk assessment.
  - `OptionStrategyDecisionSet` — Container for all option outputs for one run.
  - `option_mid_price(contract)` — Deterministic mid-price from contract data.
  - `option_leg_premium(leg)` — Per-share premium from leg data.
  - `calculate_long_call_payoff(contract, ...)` — Long call payoff profile.
  - `calculate_long_put_payoff(contract, ...)` — Long put payoff profile.
  - `calculate_call_debit_spread_payoff(long_call, short_call, ...)` — Bull call spread payoff profile.
  - `calculate_put_debit_spread_payoff(long_put, short_put, ...)` — Bear put spread payoff profile.
  - `calculate_cash_secured_put_payoff(contract, ...)` — CSP payoff profile.
  - `calculate_covered_call_payoff(call_contract, ...)` — Covered call payoff profile.
  - `calculate_option_liquidity(contracts, ...)` — Aggregate liquidity from a list of contracts.
  - `assess_option_event_risk(underlying, expiration, ...)` — Event risk by event type and date.
  - `option_strategy_tool_result_from_decision_set()` — ToolResult adapter.
  - `summarize_option_strategy_decision_set()` — Coverage summary.
  - `validate_option_strategy_decision_set()` — Advisory soft-validator.
- Updates `lib/reliability/__init__.py` to export all new symbols.
- Creates `scripts/test_reliability_options.py` — 223 assertions.
- Creates this design document.

### What Phase 2E does NOT do

- Does **not** fetch real option market data from any source.
- Does **not** implement an Option Agent.
- Does **not** compute option Greeks (gamma, theta, vega, delta are optional
  passthrough fields sourced externally; not computed here).
- Does **not** implement a volatility surface, IV smile, or term structure.
- Does **not** implement American exercise early-assignment logic.
- Does **not** implement margin or assignment probability models.
- Does **not** modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any
  workflow module.
- Does **not** call the Claude API.
- Does **not** modify any live prompt.
- Does **not** wire option schemas into any Streamlit page.

---

## B. Why Option Math Must Be Deterministic

The same principle that governs all reliability-layer computations applies to
option payoff analysis:

> **Deterministic computation, agentic interpretation, auditable synthesis.**

An Option Agent must **not** invent breakevens, max-loss figures, or
risk/reward ratios from free-form reasoning.  It must cite `EvidenceRef`
objects pointing to `OptionPayoffResult` ToolResults.

Without deterministic payoff calculation, two agents analyzing the same trade
may produce different (and irreconcilable) risk figures — a dangerous
inconsistency in a production research system.

---

## C. Net Premium Convention

| Sign of `net_premium` | Meaning                  | Strategy examples |
|---|---|---|
| **Positive** (debit)  | Cash paid for the position | Long call, long put, debit spreads |
| **Negative** (credit) | Cash received for the position | Cash-secured put, covered call |

This convention propagates consistently through all payoff calculators and
the `OptionStrategyCandidate` and `OptionPayoffResult` models.

---

## D. Contract Multiplier

Each option contract controls **100 shares**.  All dollar payoff calculations
multiply per-share premiums and widths by `contracts * 100`.

---

## E. Supported Strategy Types

| `OptionStrategyType` | Description |
|---|---|
| `"long_call"` | Buy a call; bullish directional play |
| `"long_put"` | Buy a put; bearish directional or hedge play |
| `"call_debit_spread"` | Bull call spread: buy lower call, sell higher call |
| `"put_debit_spread"` | Bear put spread: buy higher put, sell lower put |
| `"cash_secured_put"` | Sell a put with cash collateral; premium income |
| `"covered_call"` | Sell a call against existing stock; income overlay |
| `"protective_put"` | Buy a put against existing stock; downside hedge |
| `"collar"` | Covered call + protective put |
| `"straddle"` | Buy call and put at same strike; volatility play |
| `"strangle"` | Buy OTM call and put; lower-cost volatility play |
| `"no_trade"` | Explicit decision not to trade options |

Payoff calculators are implemented for the first six strategies.  The
remaining four (`protective_put`, `collar`, `straddle`, `strangle`) are
placeholder entries in the Literal alias for future implementation.

---

## F. Schemas Overview

### `OptionContractSnapshot`

One sourced option contract's market data.

| Field | Required | Notes |
|---|---|---|
| `underlying` | Yes | Non-empty underlying ticker symbol |
| `option_type` | Yes | `"call"` or `"put"` |
| `expiration` | Yes | Non-empty ISO date string (e.g. `"2026-06-20"`) |
| `strike` | Yes | `> 0` (per share) |
| `bid` | Yes | `>= 0` (per share) |
| `ask` | Yes | `>= bid >= 0` (per share) |
| `last` | No | `>= 0`; last traded price per share |
| `mid` | No | `>= 0`; pre-computed mid if provided by source |
| `volume` | No | `>= 0`; daily volume in contracts |
| `open_interest` | No | `>= 0`; open interest in contracts |
| `implied_volatility` | No | `>= 0`; decimal fraction (e.g. `0.30` = 30%) |
| `delta` | No | `-1.0` to `1.0`; sourced externally |
| `gamma` | No | Sourced externally; no bounds enforced |
| `theta` | No | Sourced externally; no bounds enforced |
| `vega` | No | Sourced externally; no bounds enforced |
| `as_of` | Yes | Non-empty snapshot date/time string |
| `source` | No | Defaults to `"synthetic"` |
| `metadata` | No | Arbitrary key/value dict |

Validation: `ask >= bid` enforced; whitespace-only `underlying`, `expiration`,
`as_of`, and `source` are rejected.

### `OptionChainSnapshot`

Container for a collection of contracts for one underlying.

| Field | Required | Notes |
|---|---|---|
| `underlying` | Yes | Non-empty ticker |
| `underlying_price` | Yes | `> 0`; current stock price at time of snapshot |
| `snapshot_id` | No | Optional unique identifier string |
| `expirations` | No | List of expiration date strings present in this snapshot |
| `contracts` | No | List of `OptionContractSnapshot`; may be empty |
| `as_of` | Yes | Non-empty snapshot date/time |
| `source` | No | Defaults to `"synthetic"` |
| `warnings` | No | Advisory warnings list |
| `metadata` | No | Arbitrary key/value dict |

`underlying_price > 0` is required to support downstream moneyness calculations
and serve as an auditable anchor for the snapshot.

### `OptionLeg`

One leg of a multi-leg option strategy.

| Field | Required | Notes |
|---|---|---|
| `contract` | Yes | `OptionContractSnapshot` |
| `side` | Yes | `"long"` or `"short"` |
| `quantity` | No | `>= 1`; defaults to `1` |
| `premium` | No | `>= 0`; explicit per-share premium override; if absent, `option_mid_price(contract)` is used |

Pre-computed `mid_price` and `leg_premium` fields are **not** stored on the
leg; they are computed on demand by `option_leg_premium(leg)`.

### `OptionStrategyCandidate`

A candidate strategy with evidence references.

| Field | Required | Notes |
|---|---|---|
| `underlying` | Yes | Non-empty ticker |
| `strategy_type` | Yes | One of `OptionStrategyType` values |
| `legs` | No | List of `OptionLeg`; may be empty (allowed for `"no_trade"`) |
| `net_premium` | No | Signed; defaults to `0.0` |
| `trade_expression` | No | Defaults to `"option"` |
| `evidence_refs` | No | List of `EvidenceRef` |
| `rationale` | No | Human-readable rationale |
| `metadata` | No | Arbitrary key/value dict |

### `OptionPayoffResult`

Output of a deterministic payoff calculator.

| Field | Required | Notes |
|---|---|---|
| `strategy_type` | Yes | One of `OptionStrategyType` values |
| `underlying` | Yes | Non-empty ticker |
| `net_premium` | Yes | Signed (positive=debit, negative=credit) |
| `max_loss` | No | `>= 0`; `None` for strategies where max loss is not computable |
| `max_gain` | No | `>= 0`; `None` = unlimited (e.g. long call) |
| `breakeven` | No | `float` or `list[float]`; `None` if not computable (e.g. covered call without cost basis) |
| `risk_reward_ratio` | No | `>= 0`; `None` when max_gain is unlimited or max_loss is zero |
| `cash_required` | No | `>= 0`; cash needed to enter (e.g. CSP strike × 100) |
| `collateral_required` | No | `>= 0`; collateral required (e.g. same as cash for CSP) |
| `notes` | No | List of advisory notes (e.g. "Upside is theoretically unlimited.") |
| `warnings` | No | List of advisory warnings |
| `evidence_refs` | No | List of `EvidenceRef` for citing upstream evidence |
| `calculation_version` | No | Defaults to `"option_schema_v1"` |

### `OptionLiquidityCheck`

Result of a deterministic **aggregate** liquidity assessment across a list of contracts.

| Field | Required | Notes |
|---|---|---|
| `contract_count` | Yes | `>= 0`; number of contracts assessed |
| `max_bid_ask_spread_pct` | No | `>= 0`; worst spread_pct across all contracts |
| `avg_bid_ask_spread_pct` | No | `>= 0`; average spread_pct |
| `min_volume` | No | `>= 0`; minimum volume across contracts with data |
| `min_open_interest` | No | `>= 0`; minimum OI across contracts with data |
| `status` | Yes | One of `OptionLiquidityStatus` values |
| `warnings` | No | Advisory warnings (e.g. missing volume or OI data) |
| `calculation_version` | No | Defaults to `"option_schema_v1"` |

Per-contract fields such as `ticker`, `contract_key`, `bid_ask_spread`, and
`spread_pct` are **not** present; this model summarizes across all contracts
in the input list.

### `OptionEventRiskCheck`

Result of a deterministic event risk assessment.

| Field | Required | Notes |
|---|---|---|
| `underlying` | Yes | Non-empty ticker |
| `expiration` | Yes | Non-empty ISO date string |
| `event_type` | No | E.g. `"earnings"`, `"major_event"`, `"dividend"` |
| `event_date` | No | ISO date string; `None` if no event known |
| `event_before_expiration` | No | `True/False/None` |
| `risk_level` | Yes | One of `OptionEventRiskLevel` values |
| `warnings` | No | Advisory warnings list |
| `notes` | No | Advisory notes list |
| `calculation_version` | No | Defaults to `"option_schema_v1"` |

### `OptionStrategyDecisionSet`

Container for all option strategy outputs for one research run.

| Field | Required | Notes |
|---|---|---|
| `underlying` | Yes | Non-empty underlying ticker |
| `as_of` | Yes | Non-empty date/datetime string |
| `schema_version` | No | Defaults to `"1.0"` |
| `chain_snapshot` | No | Full `OptionChainSnapshot` object (not an ID string); `None` if unavailable |
| `candidates` | No | List of `OptionStrategyCandidate` |
| `payoff_results` | No | List of `OptionPayoffResult` |
| `liquidity_checks` | No | List of `OptionLiquidityCheck` |
| `event_risk_checks` | No | List of `OptionEventRiskCheck` |
| `warnings` | No | Advisory warnings list |

`chain_snapshot` embeds the full object (not just an ID) so the ToolResult
payload is self-contained and fully auditable without external lookups.

---

## G. Payoff Calculator Formulas

All calculators accept `OptionContractSnapshot` objects.  They validate
`option_type`, and spread calculators validate that both legs share the same
`underlying` and `expiration`.

### Long Call

```
premium_used  = explicit premium OR option_mid_price(contract)
net_premium   = premium_used × contracts × 100   (positive = debit)
max_loss      = net_premium
max_gain      = None  (unlimited)
breakeven     = strike + premium_used
risk_reward_ratio = None
```

Requires `contract.option_type == "call"`.

### Long Put

```
premium_used  = explicit premium OR option_mid_price(contract)
net_premium   = premium_used × contracts × 100
max_loss      = net_premium
max_gain      = max(strike − premium_used, 0) × contracts × 100
breakeven     = strike − premium_used
risk_reward_ratio = max_gain / max_loss  (if max_loss > 0)
```

Requires `contract.option_type == "put"`.

### Call Debit Spread (Bull Call Spread)

```
long_p, short_p = respective premiums or mids
net_debit     = long_p − short_p
spread_width  = short_call.strike − long_call.strike  (short_strike > long_strike)
net_premium   = net_debit × contracts × 100
max_loss      = max(net_premium, 0)
max_gain      = max(spread_width − net_debit, 0) × contracts × 100
breakeven     = long_call.strike + net_debit
```

Requires both legs `option_type == "call"`, same `underlying`, same `expiration`,
and `short_call.strike > long_call.strike`.

### Put Debit Spread (Bear Put Spread)

```
long_p, short_p = respective premiums or mids
net_debit     = long_p − short_p
spread_width  = long_put.strike − short_put.strike  (long_strike > short_strike)
net_premium   = net_debit × contracts × 100
max_loss      = max(net_premium, 0)
max_gain      = max(spread_width − net_debit, 0) × contracts × 100
breakeven     = long_put.strike − net_debit
```

Requires both legs `option_type == "put"`, same `underlying`, same `expiration`,
and `long_put.strike > short_put.strike`.

### Cash-Secured Put

```
premium_used  = explicit premium OR option_mid_price(contract)
net_premium   = −premium_used × contracts × 100   (negative = credit received)
max_gain      = premium_used × contracts × 100
max_loss      = max(strike − premium_used, 0) × contracts × 100
breakeven     = strike − premium_used
cash_required = strike × contracts × 100
collateral_required = cash_required
```

Requires `contract.option_type == "put"`.

### Covered Call

```
premium_used  = explicit premium OR option_mid_price(contract)
credit        = premium_used × contracts × 100
net_premium   = −credit   (credit received)

# If stock_cost_basis is provided:
max_gain      = max(strike − cost_basis, 0) × contracts × 100 + credit
max_loss      = max(cost_basis − premium_used, 0) × contracts × 100
breakeven     = cost_basis − premium_used

# If stock_cost_basis is None:
max_gain = max_loss = breakeven = None
(noted in result.notes)
```

Requires `call_contract.option_type == "call"` and
`shares_owned >= contracts × 100`.

---

## H. Liquidity Classification Rules

`calculate_option_liquidity(contracts, max_acceptable_spread_pct=0.15)` accepts
a **list** of `OptionContractSnapshot` objects and returns an aggregate
`OptionLiquidityCheck`.

For each contract:
```
mid = contract.mid  if set,  else  (bid + ask) / 2
spread_pct = (ask − bid) / mid   (0.0 when mid == 0)
```

Then classification uses the **worst (maximum) spread_pct** across all contracts:

| Status | Condition |
|---|---|
| `"unknown"` | Input list is empty |
| `"liquid"` | `max_spread_pct <= 0.10` AND (`min_oi is None` OR `min_oi >= 100`) |
| `"acceptable"` | `max_spread_pct <= max_acceptable_spread_pct` (default 0.15) |
| `"illiquid"` | `max_spread_pct > max_acceptable_spread_pct` |

Warnings are appended when volume or open_interest data is missing for any
contract.  Thresholds are **advisory only**.

---

## I. Event Risk Classification Rules

`assess_option_event_risk(underlying, expiration, event_type=None, event_date=None)`
classifies risk by event type and date relationship to the option expiration.

| `risk_level` | Condition |
|---|---|
| `"unknown"` | `event_type is None` OR `event_date is None` |
| `"high"` | `event_date <= expiration` AND `event_type in {"earnings", "major_event"}` |
| `"medium"` | `event_date <= expiration` AND `event_type` is any other value |
| `"low"` | `event_date > expiration` (event falls after option expires) |

`event_before_expiration` is set to `True/False` when both date strings are
provided; `None` when data is missing.  Lexicographic ISO date comparison is
used.

---

## J. Example `OptionStrategyDecisionSet` JSON

```json
{
  "underlying": "AAPL",
  "as_of": "2026-05-21",
  "schema_version": "1.0",
  "chain_snapshot": {
    "underlying": "AAPL",
    "underlying_price": 155.0,
    "snapshot_id": "AAPL_CHAIN_20260521_001",
    "expirations": ["2026-06-20", "2026-07-18"],
    "contracts": [],
    "as_of": "2026-05-21",
    "source": "synthetic",
    "warnings": [],
    "metadata": {}
  },
  "candidates": [
    {
      "underlying": "AAPL",
      "strategy_type": "long_call",
      "legs": [],
      "net_premium": 300.0,
      "trade_expression": "option",
      "evidence_refs": [],
      "rationale": "Bullish momentum, defined risk play.",
      "metadata": {}
    }
  ],
  "payoff_results": [
    {
      "strategy_type": "long_call",
      "underlying": "AAPL",
      "net_premium": 300.0,
      "max_loss": 300.0,
      "max_gain": null,
      "breakeven": 153.0,
      "risk_reward_ratio": null,
      "cash_required": null,
      "collateral_required": null,
      "notes": ["Upside is theoretically unlimited."],
      "warnings": [],
      "evidence_refs": [],
      "calculation_version": "option_schema_v1"
    }
  ],
  "liquidity_checks": [
    {
      "contract_count": 1,
      "max_bid_ask_spread_pct": 0.086,
      "avg_bid_ask_spread_pct": 0.086,
      "min_volume": null,
      "min_open_interest": 1200,
      "status": "liquid",
      "warnings": ["Volume data missing for 1 contract(s)."],
      "calculation_version": "option_schema_v1"
    }
  ],
  "event_risk_checks": [
    {
      "underlying": "AAPL",
      "expiration": "2026-06-20",
      "event_type": null,
      "event_date": null,
      "event_before_expiration": null,
      "risk_level": "unknown",
      "warnings": ["Insufficient event data to assess risk."],
      "notes": [],
      "calculation_version": "option_schema_v1"
    }
  ],
  "warnings": []
}
```

---

## K. Example ToolResult Payload Shape

```python
from lib.reliability.options import (
    OptionContractSnapshot,
    OptionChainSnapshot,
    OptionStrategyDecisionSet,
    option_strategy_tool_result_from_decision_set,
    calculate_long_call_payoff,
)

# 1. Build a contract snapshot
contract = OptionContractSnapshot(
    underlying="AAPL", option_type="call", expiration="2026-06-20",
    strike=150.0, bid=2.80, ask=3.20, as_of="2026-05-21",
)

# 2. Build chain snapshot (underlying_price required)
chain = OptionChainSnapshot(
    underlying="AAPL", underlying_price=155.0,
    contracts=[contract], as_of="2026-05-21",
)

# 3. Compute payoff deterministically
payoff = calculate_long_call_payoff(contract, premium=3.0, contracts=1)

# 4. Bundle into decision set
ds = OptionStrategyDecisionSet(
    underlying="AAPL", as_of="2026-05-21",
    chain_snapshot=chain, payoff_results=[payoff],
)

# 5. Wrap as ToolResult
tr = option_strategy_tool_result_from_decision_set("RUN_20260521_001", ds)

# tr.tool_name == "option_strategy_decision_set"
# tr.ticker == "AAPL"
# tr.evidence_id == "<run_id>:option_strategy_decision_set:AAPL:option_strategy_decision_set:<hash>"
# tr.inputs includes: underlying, as_of, calculation_version
# tr.outputs includes: chain_snapshot (full object), candidates, payoff_results,
#                       liquidity_checks, event_risk_checks, warnings
```

The ToolResult is submitted to `EvidenceStore.add_tool_result(tr)`.
An Option Agent citing this evidence includes an `EvidenceRef` like:

```json
{
  "evidence_id": "<run_id>:option_strategy_decision_set:AAPL:...",
  "tool_name": "option_strategy_decision_set",
  "field_path": "payoff_results.0.breakeven",
  "excerpt": "Long call breakeven at $153.00"
}
```

---

## L. Helper Functions

### `option_mid_price(contract: OptionContractSnapshot) -> float`

Returns `contract.mid` if set, else `(contract.bid + contract.ask) / 2.0`.
Deterministic and pure; uses the pre-computed mid when available.

### `option_leg_premium(leg: OptionLeg) -> float`

Returns `leg.premium` if set, else `option_mid_price(leg.contract)`.
Returns the per-share premium for use in payoff calculations.

### `calculate_long_call_payoff(contract, premium=None, contracts=1) -> OptionPayoffResult`

Computes the payoff profile for a long call.  `max_gain = None` (unlimited).
Raises `ValueError` if `contract.option_type != "call"` or `contracts <= 0`.

### `calculate_long_put_payoff(contract, premium=None, contracts=1) -> OptionPayoffResult`

Computes the payoff profile for a long put.  `max_gain` is bounded by the
stock going to zero.
Raises `ValueError` if `contract.option_type != "put"` or `contracts <= 0`.

### `calculate_call_debit_spread_payoff(long_call, short_call, long_premium=None, short_premium=None, contracts=1) -> OptionPayoffResult`

Bull call spread.  Validates both legs are calls, same `underlying`, same
`expiration`, and `short_call.strike > long_call.strike`.

### `calculate_put_debit_spread_payoff(long_put, short_put, long_premium=None, short_premium=None, contracts=1) -> OptionPayoffResult`

Bear put spread.  Validates both legs are puts, same `underlying`, same
`expiration`, and `long_put.strike > short_put.strike`.

### `calculate_cash_secured_put_payoff(contract, premium=None, contracts=1) -> OptionPayoffResult`

Returns `net_premium < 0` (credit received).  Sets `cash_required` and
`collateral_required` to `strike × contracts × 100`.

### `calculate_covered_call_payoff(call_contract, shares_owned=100, stock_cost_basis=None, premium=None, contracts=1) -> OptionPayoffResult`

Returns `net_premium < 0` (credit received).  `max_gain`, `max_loss`, and
`breakeven` require `stock_cost_basis`; set to `None` without it.
Raises `ValueError` if `shares_owned < contracts × 100`.

### `calculate_option_liquidity(contracts: list[OptionContractSnapshot], max_acceptable_spread_pct=0.15) -> OptionLiquidityCheck`

Classifies the aggregate liquidity of a list of contracts.  Returns
`status="unknown"` for an empty list.

### `assess_option_event_risk(underlying, expiration, event_type=None, event_date=None) -> OptionEventRiskCheck`

Classifies event risk as `"high"`, `"medium"`, `"low"`, or `"unknown"`.
High risk requires `event_type in {"earnings", "major_event"}` before expiry.

### `option_strategy_tool_result_from_decision_set(run_id, decision_set, target=None, calculation_version="option_schema_v1") -> ToolResult`

Wraps an `OptionStrategyDecisionSet` into a `ToolResult`.  Evidence ID is
deterministic: same `run_id` + same decision_set → same ID.  The full
`chain_snapshot` object is serialized into the payload.

### `summarize_option_strategy_decision_set(decision_set) -> dict`

Returns summary keys: `underlying`, `as_of`, `candidate_count`,
`payoff_result_count`, `liquidity_check_count`, `event_risk_check_count`,
`strategy_types_present`, `warnings_count`, `has_high_event_risk`,
`chain_snapshot_present`.

### `validate_option_strategy_decision_set(decision_set) -> list[str]`

Advisory soft-validator.  Returns warning strings, never raises.  Checks:
1. No candidates.
2. Non-`"no_trade"` candidate with no legs.
3. Candidate with no `evidence_refs`.
4. `OptionPayoffResult` with `max_loss=None` (non-no_trade strategy).
5. Liquidity check with `status="illiquid"`.
6. Event risk check with `risk_level="high"`.
7. `chain_snapshot is None`.
8. `chain_snapshot.underlying` does not match `decision_set.underlying`.
9. Any `candidate.underlying` does not match `decision_set.underlying`.
10. Any `payoff_result.underlying` does not match `decision_set.underlying`.

---

## M. Guardrails

| Rule | Reason |
|---|---|
| Option calculators do not call LLMs | All math is deterministic Python |
| Calculators validate `option_type` | Prevents accidentally computing a call payoff with a put contract |
| Spread calculators validate `underlying` + `expiration` match | Prevents mixing legs from different tickers or expiries |
| Option Agent must not invent breakevens or max-loss values | Must cite `EvidenceRef` pointing to `OptionPayoffResult` ToolResults |
| `chain_snapshot` is embedded as full object | ToolResult payload is self-contained and audit-ready |
| Liquidity thresholds are advisory in this phase | Production thresholds may differ by broker or market condition |
| Event risk uses lexicographic ISO date comparison | No external calendar API; relies on sourced event data from upstream agents |
| Greeks are passthrough-only; not computed | Delta/gamma/theta/vega belong to a future options-greeks phase |
| Live option data connectors belong to later phases | This phase uses synthetic payloads only |
| UI dashboard belongs to Investment Cockpit phase | No Streamlit changes in this phase |

---

## N. Relationship to Future Phases

| Phase | Description | Option schema role |
|---|---|---|
| **Phase 2E (this)** | Schema + calculator foundation | Define data contracts and payoff math |
| **Phase 2F** | Option Agent prompt contract | Use `OptionPayoffResult` ToolResult as evidence |
| **Phase 3A** | Horizon integration | Select option strategy based on horizon evidence |
| **Phase 3B** | Macro-aware option selection | Suppress option strategies under high-vol regimes |
| **Phase 3C** | Multi-leg Greek hedging | Extend with delta/gamma/vega analysis |
| **Phase 4** | Cockpit UI | Render option strategy payoff diagrams |
| **Phase 5** | Memory | Persist option strategy history across research sessions |

---

## Appendix: Exported Symbols

```python
from lib.reliability.options import (
    # Literal aliases
    OptionType,
    OptionPositionSide,
    OptionStrategyType,
    OptionLiquidityStatus,
    OptionEventRiskLevel,
    OptionTradeExpression,
    # Models
    OptionContractSnapshot,
    OptionChainSnapshot,
    OptionLeg,
    OptionStrategyCandidate,
    OptionPayoffResult,
    OptionLiquidityCheck,
    OptionEventRiskCheck,
    OptionStrategyDecisionSet,
    # Calculators / helpers
    option_mid_price,
    option_leg_premium,
    calculate_long_call_payoff,
    calculate_long_put_payoff,
    calculate_call_debit_spread_payoff,
    calculate_put_debit_spread_payoff,
    calculate_cash_secured_put_payoff,
    calculate_covered_call_payoff,
    calculate_option_liquidity,
    assess_option_event_risk,
    # Adapter / summary / validator
    option_strategy_tool_result_from_decision_set,
    summarize_option_strategy_decision_set,
    validate_option_strategy_decision_set,
)
```

All symbols are also re-exported from `lib.reliability` (the package root).

## Appendix: Test Script

```bash
python3 scripts/test_reliability_options.py
```

223 assertions across groups A–S:

- A: Literal type aliases — all 6 types, coverage and counts (8)
- B: `OptionContractSnapshot` — `underlying`/`expiration` fields, optional Greeks, validation (29)
- C: `OptionChainSnapshot` — `underlying_price` required, `expirations`, `snapshot_id` optional (8)
- D: `OptionLeg` — `quantity`, optional `premium`, fallback to contract mid (6)
- E: `option_mid_price` — uses `contract.mid` if set, else `(bid+ask)/2` (4)
- F: `calculate_long_call_payoff` — contract-aware, rejects put, rejects 0 contracts (11)
- G: `calculate_long_put_payoff` — contract-aware, rejects call (9)
- H: `calculate_call_debit_spread_payoff` — rejects mismatched type/underlying/expiration (13)
- I: `calculate_put_debit_spread_payoff` — rejects mismatched type/underlying/expiration (11)
- J: `calculate_cash_secured_put_payoff` — credit convention, `cash_required` (10)
- K: `calculate_covered_call_payoff` — with/without `stock_cost_basis`, `shares_owned` check (12)
- L: `calculate_option_liquidity` — liquid/acceptable/illiquid/unknown, multi-contract (14)
- M: `assess_option_event_risk` — high/medium/low/unknown by `event_type` (17)
- N: `validate_option_strategy_decision_set` — all 10 warning conditions (13)
- O: `option_strategy_tool_result_from_decision_set` — shape, `chain_snapshot` in payload (19)
- P: `summarize_option_strategy_decision_set` — `strategy_types_present`, `chain_snapshot_present` (13)
- Q: `EvidenceRef` integration — candidate and payoff evidence refs (3)
- R: Serialization roundtrip — all key model types (16)
- S: Safety — no live app imports, all symbols importable from `lib.reliability` (7)
