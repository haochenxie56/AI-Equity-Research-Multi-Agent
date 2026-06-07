# Reliability Phase 4M-E: Option Trade Plan Memory

**Date**: 2026-05-26 (status reconciled 2026-05-27)
**Phase**: 4M-E
**Status**: **Accepted** (Codex FAIL fixes accepted)
**Module**: `lib/reliability/option_trade_memory.py`
**Test suite**: `scripts/test_reliability_option_trade_memory.py`

> **Note on historical phrasing below**: this document was drafted when later
> Phase 4M subphases (4M-F and 4M-G) were still pending. All Phase 4M
> subphases through 4M-G are now accepted, and Phase 4M-H Phase 4 Memory
> Closeout has been implemented and is awaiting Codex review. The
> "Future Subphases" section below is retained as historical roadmap context.

---

## 1. Purpose

Phase 4M-E implements the Roadmap v4 Phase 4 **Option Trade Plan Memory**. It defines an offline, deterministic, mock-only memory schema and helper layer for recording option expression and option trade plan decisions across the research lifecycle.

The module records:
- the strategy chosen (option type, stock, no_trade, wait)
- entry and exit conditions (IV, underlying price, expiration, max loss/gain, breakeven, cash required, risk/reward)
- planned exit rules and actual exit reasons
- PnL placeholders, lessons learned, and review lifecycle events

All artifacts are schema/helper artifacts only — no live option-chain API, no brokerage integration, no execution authorization, and no file/database persistence.

---

## 2. Roadmap Relationship

### Roadmap v4 Phase 4 Memory mainline

Phase 4M-E is the fifth sub-phase in the Roadmap v4 Phase 4 Memory + Human Feedback mainline:

| Sub-phase | Module | Description |
|-----------|--------|-------------|
| Phase 4M-A | `research_memory.py` | Research Run Memory Schema |
| Phase 4M-B | `thesis_memory.py` | Thesis Memory by Horizon |
| Phase 4M-C | `event_memory.py` | Catalyst / News / Earnings Memory |
| Phase 4M-D | `allocation_memory.py` | Allocation Decision Memory |
| **Phase 4M-E** | `option_trade_memory.py` | **Option Trade Plan Memory (this phase)** |

### Relationship to accepted phases

| Phase | Module | Relationship |
|-------|--------|--------------|
| Phase 4M-A | `research_memory.py` | `memory_id` optionally links to `ResearchRunMemoryRecord` |
| Phase 4M-B | `thesis_memory.py` | `thesis_id` optionally links to `HorizonThesisMemoryRecord` |
| Phase 4M-C | `event_memory.py` | Parallel memory stream: event intelligence findings |
| Phase 4M-D | `allocation_memory.py` | `allocation_memory_id` optionally links to `AllocationDecisionMemoryRecord` |
| Phase 3R-D | `option_expression.py` | `option_expression_report_id` links to `OptionExpressionReport` |
| Phase 3R-B | `trade_plan.py` | `trade_plan_report_id` links to `TradePlanReport` |
| Phase 3E | `decision_packet.py` | `decision_packet_id` links to `DecisionPacket` |
| Phase 4A | `integration_boundary.py` | Accepted early infrastructure; not part of memory mainline |

---

## 3. Memory Lifecycle

Each `OptionTradePlanMemoryRecord` progresses through a lifecycle. The following statuses are defined:

| Status | Meaning |
|--------|---------|
| `planned` | Option trade plan recorded but not yet entered |
| `active` | Trade is active (position entered, or pending entry) |
| `needs_review` | Requires human review (high-risk, pending review, or escalated) |
| `reviewed` | Reviewed by a human reviewer |
| `closed` | Trade concluded with a terminal outcome but not yet reviewed |
| `invalidated` | Plan was invalidated (thesis collapsed, market conditions changed) |
| `archived` | Record archived after lifecycle completion |
| `blocked` | Human review is blocked; no further processing until unblocked |
| `unknown` | Default fallback; no records present or indeterminate state |

### Single-record status precedence

```
initial_status override
  → blocked (HRR blocked, or review_status=blocked)
    → needs_review (high-risk unreviewed, or pending/escalated review)
      → closed (terminal outcome reached, not yet reviewed)
        → reviewed (review_status=reviewed)
          → active (default)
```

### Report-level status precedence

```
blocked > needs_review > closed > reviewed > active > planned > archived > unknown
```

---

## 4. Schema Summary

### Literal Type Aliases (8)

| Alias | Values |
|-------|--------|
| `OptionTradeMemoryStatus` | unknown, planned, active, reviewed, needs_review, closed, invalidated, archived, blocked |
| `OptionTradeStrategyType` | long_call, long_put, call_debit_spread, put_debit_spread, cash_secured_put, covered_call, stock, no_trade, unknown |
| `OptionTradeDecision` | option, stock, no_trade, wait, unknown |
| `OptionTradeReviewStatus` | not_required, pending, reviewed, escalated, blocked, unknown |
| `OptionTradeOutcome` | unknown, pending, profit, loss, breakeven, expired_worthless, assigned, exercised, invalidated, no_trade |
| `OptionTradeMemoryEventType` | option_plan_recorded, review_requested, review_completed, exit_rule_updated, outcome_observed, pnl_updated, lesson_added, human_feedback_added, archived, unknown |
| `OptionTradeRiskLevel` | low, medium, high, undefined, unknown |
| `OptionTradeMemoryActorType` | system, user, reviewer, agent, unknown |

### Pydantic Models (7)

#### OptionTradeMemorySourceRef

A stable pointer to an upstream artifact or evidence source. Fields: `source_id` (required, non-empty, non-whitespace), `source_type`, `artifact_id`, `evidence_id`, `field_path`, `label`, `metadata`, `warnings`. Extra fields forbidden.

#### OptionTradePlanSnapshot

A non-live snapshot of the option expression / option plan at decision time. Contains:

- **Core decision fields**: `snapshot_id`, `target`, `decision`, `strategy_type`, `risk_level`
- **IV fields** (non-negative float): `entry_iv`, `exit_iv`
- **Price fields** (non-negative float): `entry_underlying_price`, `exit_underlying_price`, `breakeven`
- **Sizing fields** (non-negative): `max_loss`, `max_gain`, `cash_required`, `risk_reward_ratio`, `contracts` (int)
- **Exit semantics**: `planned_exit_rule` (string), `actual_exit_reason` (string)
- **Expiration**: `expiration` (date string)
- **References**: `source_refs`, `evidence_ids`, `artifact_refs`, `warnings`

No broker/order/account/execution fields. No live data. `no_trade` strategy does not require option metrics — all option-specific fields are optional.

#### OptionTradeMemoryLogEntry

A timestamped lifecycle event in the record's event log. Fields: `event_id`, `event_type`, `created_at`, `actor`, `description`, `source_ids`, `evidence_ids`, `metadata`, `warnings`. Whitespace-only `event_id`, `created_at`, or `description` are rejected.

#### OptionTradePlanMemoryRecord

The main memory record. Fields:

- `option_trade_memory_id`, `target` (required, non-empty)
- `run_id`, `memory_id`, `thesis_id`, `allocation_memory_id` (optional upstream links)
- `option_expression_report_id`, `trade_plan_report_id`, `decision_packet_id` (optional phase links)
- `status`, `decision`, `review_status`, `outcome`
- `plan_snapshot` (`OptionTradePlanSnapshot`)
- `rationale` (required, non-empty)
- `review_trigger`, `actual_exit_date`, `lesson`
- `pnl_amount`, `pnl_pct` (signed; negative for losses)
- `recorded_at`, `reviewed_at`
- `source_refs`, `evidence_ids`, `artifact_refs`, `event_log`, `warnings`
- `approved_for_execution` (always False; `ValidationError` if set True)

#### OptionTradeMemoryInputBundle

Input bundle for building option trade memory reports. Optional upstream artifacts (duck-typed `Any`): `research_run_memory_record`, `thesis_memory_report`, `allocation_memory_report`, `option_expression_report`, `trade_plan_report`, `decision_packet`, `human_review_report`. Missing artifacts produce warnings, not crashes.

#### OptionTradeMemorySummary

Aggregate counts across all records: `record_count`, `decision_counts`, `strategy_counts`, `reviewed_count`, `needs_review_count`, `blocked_count`, `closed_count`, `no_trade_count`, `high_risk_count`, `pending_outcome_count`, `profit_count`, `loss_count`, `total_pnl_amount`, `avg_pnl_pct`, `max_loss_planned`, `top_warnings`. Always `approved_for_execution=False`.

#### OptionTradeMemoryReport

Full report: `report_id`, `target`, `run_id`, `status`, `records`, `summary`, `source_ids`, `evidence_ids`, `artifact_refs`, `warnings`, `created_at`, `updated_at`, `calculation_version`. Always `approved_for_execution=False`.

---

## 5. What Gets Recorded

Each `OptionTradePlanMemoryRecord` captures the following at decision time:

| Category | Fields |
|----------|--------|
| Strategy | `strategy_type` (long_call, long_put, call_debit_spread, put_debit_spread, cash_secured_put, covered_call, stock, no_trade) |
| Decision | `decision` (option, stock, no_trade, wait) |
| Entry IV | `plan_snapshot.entry_iv` |
| Exit IV | `plan_snapshot.exit_iv` |
| Expiration | `plan_snapshot.expiration` |
| Underlying prices | `plan_snapshot.entry_underlying_price`, `plan_snapshot.exit_underlying_price` |
| Max loss | `plan_snapshot.max_loss` (non-negative) |
| Max gain | `plan_snapshot.max_gain` (non-negative) |
| Breakeven | `plan_snapshot.breakeven` (non-negative) |
| Cash required | `plan_snapshot.cash_required` (non-negative) |
| Risk/reward | `plan_snapshot.risk_reward_ratio` (non-negative) |
| Contracts | `plan_snapshot.contracts` (non-negative integer) |
| Planned exit rule | `plan_snapshot.planned_exit_rule` (free-text string) |
| Actual exit reason | `plan_snapshot.actual_exit_reason` (free-text string) |
| PnL | `pnl_amount` (signed), `pnl_pct` (signed) |
| Lesson | `lesson` (free-text string) |
| Review status | `review_status` |
| Source references | `source_refs` (list of `OptionTradeMemorySourceRef`) |
| Evidence references | `evidence_ids` |
| Artifact references | `artifact_refs` |
| Event log | `event_log` (list of `OptionTradeMemoryLogEntry`) |

---

## 6. ID Strategy

### snapshot_id

`build_option_trade_plan_snapshot()` computes a deterministic SHA-256 hash from all material option-plan fields:

| Field | Notes |
|-------|-------|
| `target` | Always included |
| `decision` | Always included |
| `strategy_type` | Always included |
| `expiration` | Always included (may be None) |
| `entry_iv` | Always included (may be None) |
| `exit_iv` | Always included (may be None) |
| `entry_underlying_price` | Always included (may be None) |
| `exit_underlying_price` | Always included (may be None) |
| `max_loss` | Always included (may be None) |
| `max_gain` | Always included (may be None) |
| `breakeven` | Always included (may be None) |
| `cash_required` | Always included (may be None) |
| `risk_reward_ratio` | Always included (may be None) |
| `contracts` | Always included (may be None) |
| `planned_exit_rule` | Always included (may be None) |
| `actual_exit_reason` | Always included (may be None) |
| `risk_level` | Always included |
| `as_of` | Always included; defaults to `_DETERMINISTIC_TIMESTAMP_DEFAULT` |

Two snapshots that differ only in `planned_exit_rule` produce distinct `snapshot_id` values. The same applies to `actual_exit_reason` and all other material fields.

Format: `otsnap_<12-char-hex>`

### option_trade_memory_id

`make_option_trade_memory_record_id()` computes a deterministic SHA-256 hash from:

| Field | Included When |
|-------|--------------|
| `target` | Always |
| `decision` | Always |
| `strategy_type` | Always |
| `snapshot_id` | Always (derived from content-sensitive snapshot hash) |
| `rationale` | Always |
| `review_status` | Always |
| `outcome` | Always |
| `run_id` | When not None |
| `as_of` | When not None |

Because `snapshot_id` is itself content-sensitive (includes `planned_exit_rule`, `actual_exit_reason`, and all material option-plan fields), `option_trade_memory_id` automatically differs when any material snapshot field differs.

`build_option_trade_memory_record()` always finalizes the snapshot before calling `make_option_trade_memory_record_id()`.

Format: `otmem_<16-char-hex>`

### Event IDs

Event IDs are derived from `(option_trade_memory_id, event_type, created_at)`. Because `option_trade_memory_id` is content-sensitive, event IDs for distinct records automatically differ.

Format: `otlog_<12-char-hex>`

### report_id

Derived from `(target, as_of, run_id)`. Format: `otmrep_<16-char-hex>`

---

## 7. ToolResult Adapter

`option_trade_memory_tool_result_from_report(report, run_id=None)` wraps an `OptionTradeMemoryReport` as a `ToolResult`:

- **Stable tool name**: `"option_trade_memory_report"`
- **ticker**: `report.target`
- **evidence_id**: deterministic SHA-256 hash of full payload including report dict, summary dict, record_count, reviewed_count, needs_review_count, blocked_count, closed_count, no_trade_count, and calculation_version
- **outputs include**: full report dict, summary dict, record_count, reviewed_count, needs_review_count, blocked_count, closed_count, no_trade_count, calculation_version, `approved_for_execution=False`
- **No fake evidence** — evidence_id changes when content changes
- **No execution implication** — not an order ticket or persistence receipt

---

## 8. Safety Guardrails

The following are prohibited in this module:

| Guardrail | Status |
|-----------|--------|
| Live option-chain API calls | ❌ Prohibited |
| Brokerage import / brokerage API calls | ❌ Prohibited |
| External API calls (network, HTTP) | ❌ Prohibited |
| Database writes | ❌ Prohibited |
| File persistence | ❌ Prohibited |
| Vector store writes | ❌ Prohibited |
| Streamlit UI | ❌ Prohibited |
| Live workflow integration | ❌ Prohibited |
| Broker / order / execution fields | ❌ Prohibited |
| Execution authorization pathway | ❌ Prohibited — `approved_for_execution` always False |
| LLM calls | ❌ Prohibited |

`approved_for_execution` is always `False` in `OptionTradePlanMemoryRecord`, `OptionTradeMemorySummary`, and `OptionTradeMemoryReport`. Setting it to `True` raises a `ValidationError`. No pathway exists to authorize execution.

---

## 9. no_trade

`no_trade` is a valid, first-class memory outcome. It means:

- The agent or researcher decided not to enter a trade this cycle.
- The snapshot `strategy_type` is `"no_trade"` and `decision` is `"no_trade"`.
- No option metrics are required (all option-specific fields are optional).
- `no_trade` is a terminal outcome — the record status becomes `"closed"` (or `"reviewed"` if review_status is `"reviewed"`).
- `no_trade` does **not** imply execution, a skipped order, or any brokerage semantics beyond recording a research memory decision.
- `no_trade_count` in the summary counts records where `decision == "no_trade"` or `outcome == "no_trade"`.

---

## 10. No Persistence / No DB / No Vector Store

This phase introduces:
- ✅ Schema definitions (Pydantic models)
- ✅ Deterministic helper functions
- ✅ ToolResult adapter (wrapping only, no side effects)
- ❌ No file writes
- ❌ No database writes
- ❌ No vector store writes
- ❌ No network calls
- ❌ No LLM calls
- ❌ No Streamlit UI

---

## 11. Subsequent Phase 4M Subphases (historical roadmap context)

> Status reconciled 2026-05-27: all Phase 4M subphases through 4M-G are now
> accepted. Phase 4M-H Phase 4 Memory Closeout has been implemented and is
> awaiting Codex review. This table is retained as historical roadmap context.

| Subphase | Description | Status |
|----------|-------------|--------|
| Phase 4M-F | Human Feedback Layer — record human corrections and feedback for agent improvement | Accepted |
| Phase 4M-G | Agent Evaluation — offline evaluation of agent output quality over time | Accepted |
| Phase 4M-H | Phase 4 Memory Closeout — Roadmap v4 Phase 4 coverage map, regression sweep, conservative next-phase recommendation | Implemented — awaiting Codex review |

---

## Disclaimer

All outputs from this module are for research and educational purposes only. They do not constitute investment advice. Markets involve risk; invest with caution.
