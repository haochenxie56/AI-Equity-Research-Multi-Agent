# Phase 3R-B: Trade Plan Drafting Agent Skeleton

**Date**: 2026-05-24
**Status**: Implemented — awaiting Codex review
**File**: `lib/reliability/trade_plan.py`
**Test script**: `scripts/test_reliability_trade_plan.py`

---

## Purpose

Phase 3R-B implements the **Trade Plan Drafting Agent Skeleton** specified in
Roadmap v4 Phase 3H as part of the Phase 3R backfill sequence.

This module provides a standalone, deterministic, offline/mock-only reliability
layer for modeling research trade-plan drafts from validated thesis and review
artifacts. It does **not** create broker-ready orders, execution authorizations,
or any pathway to live trading.

---

## Relationship to Prior Phases

### Roadmap v4 Phase 3H

Roadmap v4 Phase 3H specifies a Trade Plan Drafting Agent that can produce:
- entry, add, trim, stop, target, review trigger, horizon

Phase 3R-B delivers this as a research-only skeleton consistent with the Phase 3
architectural boundary. No execution logic is present.

### Phase 3 Backbone (3A–3G)

The Phase 3 backbone established the full offline reliability pipeline:

```
orchestration plan          (Phase 3A — OrchestrationReport)
  → horizon-aware synthesis (Phase 3B — SynthesisCard per horizon)
  → macro context           (Phase 3C — MacroAgentResult)
  → debate by horizon       (Phase 3D — DebateReport)
  → decision packet         (Phase 3E — DecisionPacket)
  → human review            (Phase 3F — HumanReviewReport)
  → reliability run report  (Phase 3G — ReliabilityRunReport)
```

Phase 3R-B adds a parallel branch that consumes artifacts from the backbone
(primarily Phase 3E DecisionPacket and Phase 3B HorizonSynthesisReport) and
produces a TradePlanReport for the Phase 3H capability.

### Phase 3R-A Event Intelligence

Phase 3R-A delivered Catalyst, News, Earnings Playbook, and Estimate Revision
agent skeletons. Phase 3R-B can consume the EventIntelligenceReport from Phase
3R-A via `TradePlanInputBundle.event_intelligence_report` (duck-typed, optional).

---

## Schemas

### Literal Type Aliases (6)

| Alias | Values |
|-------|--------|
| `TradePlanStatus` | unknown, draft, complete, needs_review, blocked |
| `TradePlanActionType` | watch, enter, add, trim, hold, exit, no_trade, unknown |
| `TradePlanHorizon` | short, medium, long, multi_horizon, unknown |
| `TradePlanTriggerType` | price_level, valuation_gap, technical_confirmation, earnings, catalyst, news, estimate_revision, macro_regime, thesis_invalidation, risk_limit, review_date, unknown |
| `TradePlanRiskLevel` | low, medium, high, unknown |
| `TradePlanEvidenceQuality` | unsupported, weak, adequate, strong, unknown |

### Pydantic Models (7)

#### TradePlanPriceZone

Research-only advisory price zone or reference level. NOT an executable order.

Key fields: `zone_id`, `label`, `trigger_type`, `lower_bound`, `upper_bound`,
`reference_price`, `rationale`, `source_ids`, `warnings`.

Validation:
- `lower_bound <= upper_bound` when both present.
- All numeric values must be non-negative.
- `zone_id` and `label` must not be whitespace-only.

#### TradePlanRiskControl

Research-only risk control reference. NOT a broker stop order.

Key fields: `risk_control_id`, `stop_reference`, `invalidation_condition`,
`max_loss_reference`, `risk_level`, `review_required`, `rationale`,
`source_ids`, `warnings`.

Validation:
- `stop_reference` and `max_loss_reference` must be non-negative.
- `risk_control_id` must not be whitespace-only.

#### TradePlanReviewTrigger

A condition that, if met, requires re-evaluation of the trade plan. NOT a trade signal.

Key fields: `trigger_id`, `trigger_type`, `description`, `affected_horizon`,
`review_required`, `source_ids`, `warnings`.

#### TradePlanDraft

Research-only trade plan draft for one target and horizon.

Key fields: `plan_id`, `ticker`, `horizon`, `action_type`, `thesis_summary`,
`entry_zones`, `add_zones`, `trim_zones`, `target_zones`, `risk_controls`,
`review_triggers`, `no_trade_reason`, `evidence_quality`, `source_ids`,
`warnings`, `approved_for_execution` (always False).

Validation:
- `action_type == "no_trade"` requires non-empty `no_trade_reason`.
- `approved_for_execution` must always be `False` (schema-enforced).
- All price zones, risk controls, and review triggers are advisory references only.

#### TradePlanInputBundle

Input context bundle holding optional prior-phase artifacts for evidence tracing.
All prior artifact fields are duck-typed (`Optional[Any]`).

Key fields: `target`, `run_id`, `as_of`, `decision_packet`, `horizon_synthesis`,
`debate_report`, `event_intelligence_report`, `human_review_report`,
`validation_aggregate`, `staleness_report`, `critic_result`, `source_ids`, `warnings`.

Missing optional artifacts generate warnings, not crashes.

#### TradePlanSummary

Deterministic summary of one trade plan drafting pass.

Key fields: `target`, `status`, `plan_count`, `action_counts`, `horizons_covered`,
`no_trade_count`, `review_trigger_count`, `high_risk_count`, `missing_evidence_count`,
`top_warnings`, `approved_for_execution` (always False).

#### TradePlanReport

Full trade plan drafting report. Composes all `TradePlanDraft` objects into a
single auditable research artifact.

Key fields: `report_id`, `schema_version`, `target`, `run_id`, `status`,
`input_bundle`, `plans`, `summary`, `source_ids`, `warnings`, `created_at`,
`calculation_version`, `approved_for_execution` (always False).

---

## Status Logic

Status precedence (highest wins):

```
blocked > needs_review > complete > draft > unknown
```

| Status | Condition |
|--------|-----------|
| `unknown` | No plans in the report |
| `draft` | Plans exist but all have `action_type == "unknown"` |
| `complete` | All plans pass clean-check (no_trade with reason, watch/hold, or active with adequate evidence) |
| `needs_review` | Any active plan (enter/add/trim/exit) without adequate evidence, or any high-risk control without adequate evidence |
| `blocked` | `human_review_report.status == "blocked"` |

### Status Examples

| Scenario | Status |
|----------|--------|
| No plans | `unknown` |
| All action_type="unknown" | `draft` |
| no_trade with rationale | `complete` |
| watch/hold | `complete` |
| enter + adequate evidence | `complete` |
| enter + unsupported evidence | `needs_review` |
| high-risk control + weak evidence | `needs_review` |
| HR report blocked | `blocked` |
| HR blocked + missing evidence | `blocked` (blocked wins) |

---

## Helper Functions

| Function | Description |
|----------|-------------|
| `make_trade_plan_report_id(run_id, target, as_of)` | Deterministic `tpr_` prefixed ID |
| `determine_trade_plan_status(plans, human_review_report)` | Derives status from plans + HR report |
| `collect_trade_plan_source_ids(input_bundle, plans)` | Collects and deduplicates all source IDs |
| `summarize_trade_plans(target, status, plans, source_ids, extra_warnings)` | Builds TradePlanSummary |
| `build_trade_plan_report(input_bundle, plans, run_id, created_at)` | Full report pipeline |
| `trade_plan_tool_result_from_report(run_id, report, target, calculation_version)` | ToolResult adapter |

---

## ToolResult Adapter

`trade_plan_tool_result_from_report()` wraps a `TradePlanReport` as a `ToolResult`
for integration with evidence-aware pipelines.

- **stable tool_name**: `"trade_plan_report"`
- **deterministic evidence_id**: content-sensitive SHA-256 hash
- **payload**: full report, summary dict, calculation_version
- **does not mutate** the input report
- **no order ticket fields**: `order_id`, `broker_order`, `account_id`,
  `execution_status` are absent from the payload
- **approved_for_execution is False** throughout the payload

---

## Source / Evidence Handling

Source IDs are collected deterministically in this order:

1. `input_bundle.source_ids`
2. Per-plan `source_ids` (in list order)
3. Per-plan zone `source_ids` (entry, add, trim, target)
4. Per-plan `risk_controls` source_ids
5. Per-plan `review_triggers` source_ids

Deduplication preserves first-occurrence order. No IDs are fabricated.

---

## no_trade as a Valid Output

`action_type = "no_trade"` is a first-class output. It means the research
process concluded that no position action is appropriate at this time.

Requirements:
- `no_trade_reason` must be non-empty (schema-enforced).
- A no_trade plan can produce a `complete` status if the rationale is clear.
- No-trade plans appear in `summary.no_trade_count`.

---

## Distinction: Research Trade Plan vs Executable Order

| Aspect | TradePlanDraft (Phase 3R-B) | Executable Order (forbidden) |
|--------|---------------------------|------------------------------|
| Purpose | Research advisory reference | Live trade instruction |
| Price zones | Advisory research bounds | Order prices |
| Stop reference | Research invalidation level | Broker stop order |
| Execution flag | `approved_for_execution=False` (schema-enforced) | Would be True |
| Broker IDs | None | order_id, account_id, etc. |
| Legal standing | None — disclaimer applies | Contract |

---

## Execution-Safety Guardrails

1. **`approved_for_execution` is permanently False** on all models:
   `TradePlanDraft`, `TradePlanSummary`, `TradePlanReport`.
   A `model_validator` raises `ValidationError` if this is set to True.

2. **No pathway to set `approved_for_execution=True`** exists anywhere in
   `lib/reliability/trade_plan.py`.

3. **No broker/order fields** exist in any model or output dict:
   `order_id`, `broker_order`, `account_id`, `execution_status` are absent.

4. **No live API calls**: no network, no LLM calls, no external data fetching.

5. **All prior artifact fields are optional and duck-typed**: missing artifacts
   produce warnings, not errors.

---

## Offline / Mock-Only Nature

Phase 3R-B is strictly offline:

- No imports from `app.py`, `pages/*`, `lib/llm_orchestrator.py`, `lib/valuation.py`,
  `lib/technical.py`, `lib/rotation.py`, `lib/data_fetcher.py`, `lib/workflow_state.py`.
- No `anthropic` SDK usage.
- No `streamlit` usage.
- No `requests`, `httpx`, or any HTTP library.
- All helper functions are pure: same inputs → same outputs, no side effects,
  no mutation of input objects.
- `created_at` defaults to `input_bundle.as_of` (or `run_id` if empty) for
  deterministic full report output.

---

## Future Integration with Phase 4 Memory

Phase 3R-B is designed to integrate cleanly with the planned Roadmap Phase 4
Memory + Human Feedback layer. Expected integration points:

| Phase 4 Capability | How Phase 3R-B Supports It |
|--------------------|---------------------------|
| Thesis Memory by Horizon | `TradePlanDraft.horizon` and `thesis_summary` |
| Allocation Decision Memory | `TradePlanDraft.action_type` and evidence_quality |
| Option Trade Plan Memory | Future: TradePlanDraft with option-specific zones |
| Human Feedback Layer | `TradePlanInputBundle.human_review_report` integration |
| Agent Evaluation | `TradePlanReport` is a typed, evidence-bound artifact suitable for eval harness |

**Phase 4 Memory work is paused until Phase 3R-E is accepted.**

---

## Test Results

**624/624 tests pass** (`scripts/test_reliability_trade_plan.py`).

Regression:
- Phase 3R-A: 152/152 ✓
- Phase 3G Review Loop: 151/151 ✓
- Phase 3F Human Review: 113/113 ✓
- Phase 3E Decision Packet: 58/58 ✓

---

## Disclaimer

**This phase does not authorize trading or execution.**

All outputs from `lib/reliability/trade_plan.py` are for research and educational
purposes only. They do not constitute investment advice. `approved_for_execution`
is permanently `False` throughout this module. Markets involve risk; invest with
caution.
