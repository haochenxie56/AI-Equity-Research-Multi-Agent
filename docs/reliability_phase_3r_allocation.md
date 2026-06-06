# Phase 3R-C: Allocation Agent v0.1 Non-live

**Date**: 2026-05-24
**Status**: Implemented — awaiting Codex review
**Phase**: 3R-C (Roadmap v4 Phase 3 Backfill)
**File**: `lib/reliability/allocation_report.py`

---

## Purpose

Phase 3R-C delivers a standalone, deterministic, offline/mock-only Allocation Agent
skeleton for the investment research reliability layer. It implements the
**Roadmap v4 Phase 3I** Allocation Agent specification.

This phase provides:

- Deterministic portfolio/position/allocation calculators using the exact
  Roadmap v4 formulas.
- Pydantic schema models for allocation inputs, calculations, assessments,
  and reports.
- Status logic with precedence rules consistent with the Phase 3 backbone.
- A ToolResult adapter for evidence-aware pipelines.
- Comprehensive source ID collection and deduplication.

**This phase does NOT authorize trading or execution.** All outputs are
research-only advisory artifacts. `approved_for_execution` is permanently
`False` in all schemas. No pathway to set it `True` exists.

---

## Relationship to Roadmap v4

Roadmap v4 specifies a Phase 3 backfill sequence before Phase 4 Memory work
begins. Phase 3R-C is the third backfill sub-phase:

| Sub-phase | Description |
|-----------|-------------|
| Phase 3R-A | Event Intelligence Agents Skeleton |
| Phase 3R-B | Trade Plan Drafting Agent Skeleton |
| **Phase 3R-C** | **Allocation Agent v0.1 Non-live** |
| Phase 3R-D | Option Expression Agent v0.1 Non-live |
| Phase 3R-E | Roadmap Alignment Closeout |

Roadmap v4 requires that Allocation Agent be preceded by deterministic
portfolio/position/cash impact/risk budget calculators. Phase 3R-C
delivers both the calculators and the agent-output layer.

---

## Relationship to Phase 2D (allocation.py)

Phase 2D (`lib/reliability/allocation.py`) provides the Phase 2 primitive
schemas and calculators:

| Phase 2D | Phase 3R-C |
|----------|-----------|
| `PositionSnapshot` (brokerage-ish) | `AllocationPositionSnapshot` (agent-level) |
| `PortfolioSnapshot` (brokerage-ish) | `AllocationPortfolioSnapshot` (agent-level) |
| `AllocationTarget` | `AllocationTargetSpec` |
| `RiskBudget` | `RiskBudgetConstraint` |
| `calculate_position_sizing` | `build_allocation_calculation` |
| `calculate_stop_loss_risk` | Embedded in `build_allocation_calculation` |

Phase 3R-C calculators operate on raw float inputs (not Phase 2D object types)
to satisfy the Roadmap v4 Phase 3I formula specification exactly. The two
layers coexist without conflict.

---

## Deterministic Calculators

All calculators are pure functions with no side effects, no network calls, and
no LLM calls. Same inputs always produce the same outputs.

### Roadmap v4 Formulas Implemented

```
calculate_position_value(shares, current_price)
  → shares × current_price

calculate_allocation_pct(position_value, total_portfolio_value)
  → position_value / total_portfolio_value

calculate_target_position_value(target_allocation_pct, total_portfolio_value)
  → target_allocation_pct × total_portfolio_value

calculate_required_trade_value(target_position_value, current_position_value)
  → target_position_value - current_position_value

calculate_required_shares(required_trade_value, current_price)
  → required_trade_value / current_price

calculate_max_loss_at_stop(shares, entry_price, stop_price)
  → max(entry_price - stop_price, 0) × shares

calculate_portfolio_loss_pct(max_loss, total_portfolio_value)
  → max_loss / total_portfolio_value
```

`cash_released_from_trim` is handled implicitly via `cash_impact = -required_trade_value`.
When `required_trade_value < 0` (trim/exit), `cash_impact > 0` (cash received).

### Error Handling

Each calculator raises `ValueError` with a descriptive message for invalid
inputs (negative shares, zero price, negative portfolio value, etc.). No
silent NaN or infinity propagation.

---

## Schemas

### Literal Type Aliases (5)

| Alias | Values |
|-------|--------|
| `AllocationStatus` | `unknown`, `complete`, `needs_review`, `blocked` |
| `AllocationActionType` | `hold`, `add`, `trim`, `exit`, `no_action`, `unknown` |
| `AllocationRiskLevel` | `low`, `medium`, `high`, `unknown` |
| `AllocationEvidenceQuality` | `unsupported`, `weak`, `adequate`, `strong`, `unknown` |
| `AllocationConstraintType` | `max_position_pct`, `max_portfolio_loss_pct`, `min_cash_pct`, `sector_exposure`, `liquidity`, `volatility`, `thesis_confidence`, `human_review_block`, `unknown` |

### Pydantic Models (9)

#### AllocationPortfolioSnapshot

Simplified portfolio context. Caller-provided mock/non-live data only.

| Field | Type | Constraint |
|-------|------|-----------|
| `portfolio_id` | `str` | non-empty, non-whitespace |
| `total_portfolio_value` | `float` | > 0 |
| `cash_value` | `Optional[float]` | >= 0 if present |
| `cash_pct` | `Optional[float]` | 0–1 if present |
| `as_of` | `str` | optional timestamp |
| `source_ids` | `list[str]` | default `[]` |
| `warnings` | `list[str]` | default `[]` |

#### AllocationPositionSnapshot

One position for allocation calculation. Caller-provided mock/non-live.

| Field | Type | Constraint |
|-------|------|-----------|
| `position_id` | `str` | non-empty |
| `ticker` | `str` | non-empty |
| `shares` | `float` | >= 0 |
| `current_price` | `float` | > 0 |
| `cost_basis` | `Optional[float]` | >= 0 if present |
| `current_position_value` | `Optional[float]` | caller override; >= 0 if present |
| `current_allocation_pct` | `Optional[float]` | caller override |

#### AllocationTargetSpec

Research-only advisory allocation target. NOT an executable order.

| Field | Type | Constraint |
|-------|------|-----------|
| `target_id` | `str` | non-empty |
| `ticker` | `str` | non-empty |
| `target_allocation_pct` | `float` | 0–1 |
| `min_allocation_pct` | `Optional[float]` | 0–1; <= target if present |
| `max_allocation_pct` | `Optional[float]` | 0–1; >= target if present |
| `rationale` | `str` | optional |
| `evidence_quality` | `AllocationEvidenceQuality` | default `unknown` |

#### RiskBudgetConstraint

Research-only advisory risk budget constraint. NOT an executable limit order.

| Field | Type | Constraint |
|-------|------|-----------|
| `constraint_id` | `str` | non-empty |
| `constraint_type` | `AllocationConstraintType` | |
| `max_position_pct` | `Optional[float]` | 0–1 |
| `max_portfolio_loss_pct` | `Optional[float]` | 0–1 |
| `min_cash_pct` | `Optional[float]` | 0–1 |
| `stop_price` | `Optional[float]` | >= 0 |
| `risk_level` | `AllocationRiskLevel` | default `unknown` |

#### AllocationCalculation

Deterministic computed allocation metrics for one position.

| Field | Derivation |
|-------|-----------|
| `current_position_value` | shares × price (or caller-provided override) |
| `current_allocation_pct` | position_value / portfolio_value |
| `target_position_value` | target_pct × portfolio_value |
| `required_trade_value` | target − current |
| `required_shares` | required_trade_value / price |
| `action_type` | inferred (see Action Classification below) |
| `cash_impact` | = −required_trade_value |
| `projected_cash_value` | cash_value + cash_impact (when cash_value provided) |
| `projected_cash_pct` | projected_cash_value / portfolio_value |
| `max_loss_at_stop` | from first constraint with stop_price |
| `portfolio_loss_pct` | max_loss_at_stop / portfolio_value |
| `constraint_violations` | list of violated constraint descriptions |

#### AllocationAssessment

Allocation assessment combining calculation and risk level. `approved_for_execution`
is schema-enforced `False` with a Pydantic `model_validator`.

#### AllocationInputBundle

Input context bundle for one allocation pass. Holds portfolio/position/target/constraints
plus optional prior-phase research artifacts for evidence tracing. All data is
caller-provided mock/non-live. Missing optional priors produce warnings, not crashes.

#### AllocationSummary

Concise deterministic summary. `approved_for_execution` is schema-enforced `False`.

#### AllocationReport

Full allocation report. `approved_for_execution` is schema-enforced `False` in
the report, assessment, and summary.

---

## Action Classification

`build_allocation_calculation` infers `AllocationActionType` from calculated values
using a tolerance threshold (`0.1% × total_portfolio_value`):

```
exit      — target_position_value ≈ 0 AND current_position_value > 0
hold      — |required_trade_value| < tolerance AND current_position_value > 0
no_action — |required_trade_value| < tolerance AND current_position_value ≈ 0
add       — required_trade_value > tolerance
trim      — required_trade_value < −tolerance
```

---

## Status Logic

`determine_allocation_status` applies a priority precedence chain:

```
blocked      — human_review_report.status == "blocked"
           — OR any constraint violation contains "human_review_block"
needs_review — any constraint violations exist
           — OR risk_level == "high"
unknown      — action_type == "unknown" (insufficient data)
complete     — all checks passed, valid action inferred
```

Precedence: `blocked > needs_review > unknown > complete`.

---

## Constraint Violation Checks

`build_allocation_calculation` checks each `RiskBudgetConstraint` and appends
descriptions to `constraint_violations`:

| Constraint Type | Check |
|----------------|-------|
| `human_review_block` | Always generates a violation |
| `max_position_pct` | target_allocation_pct > max_position_pct |
| `max_portfolio_loss_pct` | portfolio_loss_pct > max_portfolio_loss_pct |
| `min_cash_pct` | projected_cash_pct < min_cash_pct |
| Other types | Advisory only — flagged via `_generate_allocation_warnings` |

---

## Relationship to Accepted Phase 3 Backbone

Phase 3R-C integrates with the accepted Phase 3 pipeline:

```
Phase 3G ReliabilityRunReport
  ↑ references
Phase 3F HumanReviewReport       ← consumed as optional input by AllocationInputBundle
  ↑ references
Phase 3E DecisionPacket          ← consumed as optional input by AllocationInputBundle
  ↑ references
Phase 3R-B TradePlanReport       ← consumed as optional input by AllocationInputBundle
  ↑ references
Phase 3R-A EventIntelligenceReport
  ↑
Phase 3R-C AllocationReport      ← NEW (this phase)
```

`AllocationInputBundle` accepts duck-typed optional prior artifacts. Only `status`
attributes are read. Missing artifacts produce warnings, not crashes.

---

## ToolResult Adapter

`allocation_report_tool_result_from_report(run_id, report, target=None)` wraps
an `AllocationReport` as a `ToolResult` for evidence-aware pipelines.

| Property | Value |
|----------|-------|
| `tool_name` | `"allocation_report"` (stable) |
| `evidence_id` | Deterministic (content-hash of outputs) |
| `outputs["report"]` | Full serialized report |
| `outputs["summary"]` | Concise summary dict |
| `outputs["calculation_version"]` | `"allocation_report_v1"` |

The ToolResult is **not** an order ticket. It contains no `order_id`,
`broker_order`, `account_id`, `execution_status`, or live order instruction.
`approved_for_execution` is always `False` in the payload.

---

## Source / Evidence Handling

`collect_allocation_source_ids` collects IDs in a deterministic order:

1. Bundle-level `source_ids`
2. `portfolio_snapshot.source_ids`
3. `position_snapshot.source_ids`
4. `allocation_target.source_ids`
5. `risk_constraints[*].source_ids` (in order)
6. `assessment.source_ids`
7. `assessment.calculation.source_ids`

Deduplication preserves first-occurrence order. No mutations to inputs.

---

## Deterministic Timestamps

`build_allocation_report` follows the Phase 3R-A / Phase 3R-B convention:

- `created_at` defaults to `input_bundle.as_of` (falling back to `run_id` if `as_of` is empty).
- Passing `created_at` explicitly always overrides.
- `report_id` is a stable hash of `{run_id, target, as_of}`.

Same inputs always produce the same `report_id`, `assessment_id`, `evidence_id`.

---

## Execution Safety Guardrails

This phase enforces multiple layers of execution safety:

1. **Schema-level `model_validator`**: `AllocationAssessment`, `AllocationSummary`,
   and `AllocationReport` all reject `approved_for_execution=True` with `ValueError`.
2. **Constructor default**: `approved_for_execution=False` everywhere.
3. **ToolResult payload**: `approved_for_execution=False` is explicitly set.
4. **No pathway**: No function, helper, or method in this module can produce a
   result where `approved_for_execution` is `True`.
5. **Docstrings**: All public models and functions carry explicit disclaimers
   that outputs are research-only and do not authorize execution.

---

## Offline / Mock-only Nature

This module:

- Does **not** import `app.py`, `pages/*`, or `lib/llm_orchestrator.py`.
- Does **not** call the Claude API or any external API.
- Does **not** import `streamlit`, `anthropic`, or any brokerage SDK.
- Does **not** read live portfolio or brokerage data.
- Does **not** import live position or price data.
- Makes **no network calls** of any kind.
- All inputs are caller-provided mock values only.

---

## Future Integration with Phase 4 Memory

Phase 3R-C is designed for seamless integration with Roadmap v4 Phase 4:

- **Allocation Decision Memory**: `AllocationReport` is JSON-serializable via
  `model_dump()`. Evidence chain via `source_ids` supports storage in
  `EvidenceStore`.
- **Human Feedback Layer**: `AllocationInputBundle.human_review_report` is
  already wired for Phase 3F `HumanReviewReport`. When feedback is accepted,
  the status propagation chain is already in place.
- **Agent Evaluation**: `AllocationReport` has a stable `report_id` and
  `calculation_version` for eval harness integration.
- **Review Loop Integration**: `AllocationReport` can feed `ReliabilityRunReport`
  as an additional source artifact.

**Phase 4 Memory mainline is NOT started in this phase.** It remains paused
until Phase 3R-E is accepted.

---

## Test Results

| Script | Tests | Result |
|--------|-------|--------|
| `scripts/test_reliability_allocation_report.py` | 392 | PASS |
| `scripts/test_reliability_trade_plan.py` (regression) | 652 | PASS |
| `scripts/test_reliability_event_intelligence.py` (regression) | 152 | PASS |
| `scripts/test_reliability_review_loop.py` (regression) | 151 | PASS |
| `scripts/test_reliability_human_review.py` (regression) | 113 | PASS |
| `scripts/test_reliability_decision_packet.py` (regression) | 58 | PASS |
| `scripts/test_reliability_allocation.py` (Phase 2D regression) | 288 | PASS |

---

## Disclaimer

All outputs from this module are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
This module does not authorize trading, execution, or any live portfolio action.
