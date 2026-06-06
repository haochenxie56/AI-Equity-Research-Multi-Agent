# Phase 3R-D: Option Expression Agent v0.1 Non-live

**Date**: 2026-05-24
**Status**: Implemented — Codex fixes applied — awaiting Codex re-review
**Module**: `lib/reliability/option_expression.py`
**Test script**: `scripts/test_reliability_option_expression.py` — 277/277 tests pass

---

## 1. Purpose

Phase 3R-D implements the **Option Expression Agent v0.1** skeleton as specified in
Roadmap v4 Phase 3J. It is a standalone, deterministic, offline/mock-only module
that:

- Accepts caller-provided mock market snapshots and option strategy candidates.
- Applies Roadmap v4 option payoff/breakeven/risk-reward/liquidity/event-risk formulas.
- Produces a structured `OptionExpressionReport` for research and review purposes.
- Treats `no_trade` as a legal (and often preferred) output.
- Never produces broker-ready orders, order tickets, or executable trades.
- Never sets `approved_for_execution = True`.

This phase is part of the **Roadmap v4 Phase 3 backfill sequence** (Phase 3R).

---

## 2. Relationship to Roadmap v4 Phase 3J

| Roadmap v4 Phase 3J Requirement | Phase 3R-D Implementation |
|----------------------------------|--------------------------|
| Option Agent expresses an already validated thesis | `OptionExpressionInputBundle.validated_thesis_reference` — missing thesis → `no_trade` preferred |
| `no_trade` is a legal output | `OptionExpressionStrategyType` includes `"no_trade"`; `OptionExpressionDecision` includes `"no_trade"` |
| Option Agent must not decide the thesis | Option Agent does not create or modify `validated_thesis_reference` |
| Option Agent must not decide total portfolio allocation | No `AllocationReport` generation; `allocation_report` is an input artifact only |
| Option Agent must not override Allocation Agent | `allocation_report` is a read-only input; the expression agent cannot change it |
| Option Agent must not generate broker-ready orders | No `order_id`, `account_id`, `broker_order`, or execution fields exist in any model |
| Deterministic option chain / payoff / breakeven / risk-reward / liquidity / event-risk ToolResults required | 12 calculator functions + `OptionMarketSnapshot` + `OptionStrategyCalculation` |

---

## 3. Relationship to Accepted Phase 3 Backbone

Phase 3R-D follows the same architectural conventions as all accepted Phase 3R phases:

| Convention | How Phase 3R-D Applies It |
|-----------|--------------------------|
| Literal type aliases | 10 aliases (e.g., `OptionExpressionStatus`, `OptionExpressionDecision`) |
| Pydantic models with `extra="forbid"` | 8 models with strict field validation |
| `model_validator` guards on `approved_for_execution` | Present in `OptionExpressionCandidate`, `OptionExpressionAssessment`, `OptionExpressionSummary`, `OptionExpressionReport` |
| Deterministic stable hash IDs | `make_option_expression_report_id`, `stable_hash_payload` |
| `ToolResult` wrapper | `option_expression_tool_result_from_report` |
| Source ID collection and deduplication | `collect_option_expression_source_ids` |
| Missing optional prior artifacts → warnings, not crashes | `_generate_option_expression_warnings` |
| Status precedence: `blocked > needs_review > complete > unknown` | `determine_option_expression_status` |
| No live data, LLM calls, or external APIs | Enforced throughout |

---

## 4. Relationship to Prior Phase 3R Phases

| Prior Phase | Relationship to Phase 3R-D |
|-------------|---------------------------|
| Phase 3R-A Event Intelligence | `event_intelligence_report` is an optional input in `OptionExpressionInputBundle`; event risk context informs `event_risk_level` and `review_required` |
| Phase 3R-B Trade Plan | `trade_plan_report` is an optional input; trade plan context informs option strategy horizon and rationale |
| Phase 3R-C Allocation Agent | `allocation_report` is an optional input; allocation context (sizing, position limits) is referenced but not overridden |

Phase 3R-D does **not** replace or override any prior phase output. It is a
downstream consumer of prior-phase research artifacts.

---

## 5. Relationship to Phase 2E (options.py)

Phase 2E (`lib/reliability/options.py`) provides primitive option chain and strategy
schemas: `OptionContractSnapshot`, `OptionChainSnapshot`, `OptionStrategyType`,
`OptionLeg`, `OptionStrategyCandidate`, `OptionPayoffResult`, etc.

Phase 3R-D provides a **higher-level agent-output layer** with distinct types that
do not conflict with Phase 2E names:

| Phase 2E type | Phase 3R-D counterpart | Key difference |
|--------------|----------------------|----------------|
| `OptionLeg` | `OptionExpressionLeg` | Expression-layer model; includes `OptionLegType` ("stock" allowed); research-only |
| `OptionStrategyCandidate` | `OptionExpressionCandidate` | Agent-output with `approved_for_execution` guard; includes `evidence_quality`, `no_trade_reason` |
| `OptionStrategyType` | `OptionExpressionStrategyType` | Simplified subset for expression agent (no collar/straddle/strangle); adds `"unknown"` |
| `OptionEventRiskLevel` | `OptionExpressionEventRiskLevel` | Identical values; defined locally to keep module self-contained |
| `OptionLiquidityStatus` | `OptionLiquidityLevel` | Different value set: `poor/acceptable/good/unknown` vs `liquid/acceptable/illiquid/unknown` |

Phase 2E symbols remain unmodified and are still exported from `lib.reliability.__all__`.

---

## 6. Schemas

### Literal Type Aliases (10)

| Name | Values |
|------|--------|
| `OptionExpressionStatus` | `unknown`, `complete`, `needs_review`, `blocked` |
| `OptionExpressionDecision` | `stock`, `option`, `no_trade`, `wait`, `unknown` |
| `OptionExpressionStrategyType` | `long_call`, `long_put`, `call_debit_spread`, `put_debit_spread`, `cash_secured_put`, `covered_call`, `stock`, `no_trade`, `unknown` |
| `OptionRiskLevel` | `low`, `medium`, `high`, `undefined`, `unknown` |
| `OptionLiquidityLevel` | `poor`, `acceptable`, `good`, `unknown` |
| `OptionExpressionEventRiskLevel` | `low`, `medium`, `high`, `unknown` |
| `OptionEvidenceQuality` | `unsupported`, `weak`, `adequate`, `strong`, `unknown` |
| `OptionNoTradeReason` | `thesis_not_validated`, `allocation_not_approved`, `event_risk_too_high`, `liquidity_too_poor`, `spread_too_wide`, `risk_reward_unfavorable`, `max_loss_too_high`, `expiration_mismatch`, `missing_required_inputs`, `unknown` |
| `OptionLegType` | `call`, `put`, `stock`, `unknown` |
| `OptionLegSide` | `long`, `short`, `none`, `unknown` |

### Pydantic Models (8)

| Model | Purpose |
|-------|---------|
| `OptionExpressionLeg` | One strategy leg (research-only; no order fields) |
| `OptionMarketSnapshot` | Mock market conditions snapshot (underlying price, IV, liquidity, event risk) |
| `OptionStrategyCalculation` | Deterministic computed metrics (breakeven, max_loss, max_gain, cash_required, etc.) |
| `OptionExpressionCandidate` | One candidate strategy with legs, calculation, and evidence metadata |
| `OptionExpressionInputBundle` | Full input context: market snapshot + candidates + optional prior artifacts |
| `OptionExpressionAssessment` | Selected strategy, decision, risk level, review flag |
| `OptionExpressionSummary` | Concise summary of the assessment and key metrics |
| `OptionExpressionReport` | Full auditable research artifact |

**All models use `extra="forbid"`.** `OptionExpressionCandidate`, `OptionExpressionAssessment`,
`OptionExpressionSummary`, and `OptionExpressionReport` have `model_validator` guards
that unconditionally reject `approved_for_execution=True`.

---

## 7. Deterministic Calculator Functions (12)

| Function | Formula |
|----------|---------|
| `calculate_long_call_breakeven(strike, premium)` | `strike + premium` |
| `calculate_long_put_breakeven(strike, premium)` | `strike - premium` |
| `calculate_long_option_max_loss(premium, contracts)` | `premium × contracts × 100` |
| `calculate_call_debit_spread_max_loss(net_debit, contracts)` | `net_debit × contracts × 100` |
| `calculate_call_debit_spread_max_gain(long_strike, short_strike, net_debit, contracts)` | `(spread_width - net_debit) × contracts × 100` |
| `calculate_put_debit_spread_breakeven(long_put_strike, net_debit)` | `long_put_strike - net_debit` |
| `calculate_put_debit_spread_max_loss(net_debit, contracts)` | `net_debit × contracts × 100` |
| `calculate_cash_secured_put_cash_required(strike, contracts)` | `strike × contracts × 100` |
| `calculate_cash_secured_put_breakeven(strike, premium)` | `strike - premium` |
| `calculate_covered_call_effective_sale_price(strike, premium)` | `strike + premium` |
| `calculate_covered_call_upside_cap(strike, stock_cost_basis, premium)` | `strike - stock_cost_basis + premium` |
| `calculate_risk_reward_ratio(max_gain, max_loss)` | `max_gain / max_loss`; returns `None` when `max_loss=0` or either arg is `None` |

All calculators raise `ValueError` on invalid inputs (negative strike/premium, etc.)
and return `None` for undefined/undefined cases rather than raising.

---

## 8. Status Logic

```
blocked      — human_review_report.status == "blocked"
needs_review — risk_level == "high"
             — OR review_required == True
             (needs_review is evaluated BEFORE unknown)
unknown      — decision == "unknown" (after needs_review checks)
complete     — valid decision (non-unknown), review not required
```

**Priority**: `blocked > needs_review > complete > unknown`

**Important**: `needs_review` outranks `unknown`. A decision of `"unknown"` combined
with `risk_level == "high"` or `review_required == True` returns `"needs_review"`,
not `"unknown"`. Only a plain `"unknown"` with no risk/review flags returns `"unknown"`.

**review_required = True when:**
- `risk_level == "high"` (driven by event_risk_level == "high")
- `liquidity_level == "poor"`
- `event_risk_level in ("high", "medium")`
- `evidence_quality in ("unsupported", "weak")`
- `decision == "option"` but `validated_thesis_reference is None`

---

## 9. Candidate Selection Logic

The `build_option_expression_report` function selects the best candidate from
`input_bundle.candidate_strategies` using deterministic priority rules.

Three first-class expression paths exist: **stock**, **option**, and **no_trade**.

1. **No candidates** → `(None, "unknown", "missing_required_inputs")`
2. **No validated thesis + expression candidates (option or stock) exist** → prefer first `no_trade`
   candidate, or implicit `"thesis_not_validated"` if no `no_trade` candidate is present
3. **Validated thesis + adequate-evidence expression candidates (option or stock)** → first adequate
4. **Validated thesis + weak-evidence expression candidates** → first candidate (triggers `needs_review`)
5. **Only `no_trade` candidates** → select first `no_trade` candidate
6. **Otherwise** → `(None, "unknown", "missing_required_inputs")`

Stock and option candidates are treated equivalently as "expression candidates" in this
priority order. The selected candidate's `strategy_type` determines the final decision:
`"stock"` → `decision == "stock"`, option strategy types → `decision == "option"`,
`"no_trade"` → `decision == "no_trade"`.

---

## 10. Source ID and Evidence Handling

Source IDs are collected from all input layers in order:
1. `input_bundle.source_ids`
2. `market_snapshot.source_ids` (if present)
3. All candidate `source_ids` + leg `source_ids` + calculation `source_ids`
4. `assessment.source_ids`
5. `selected_strategy.source_ids` (if present)

All collections are deduplicated preserving first-occurrence order using `set`
tracking. No source IDs are fabricated. Missing optional inputs produce warnings,
not fake evidence IDs.

---

## 11. ToolResult Adapter

`option_expression_tool_result_from_report(run_id, report, target=None)` wraps
an `OptionExpressionReport` as a `ToolResult` for evidence-aware pipelines.

- **tool_name**: stable `"option_expression_report"`
- **evidence_id**: deterministic content-sensitive hash via `make_evidence_id`
- **outputs**: `{report: ..., summary: ..., calculation_version: "option_expression_v1"}`
- **No order ticket fields** in any output key
- **`approved_for_execution: False`** in summary dict

---

## 12. Three First-Class Outputs: stock, option, no_trade

Phase 3R-D produces one of three first-class decisions:

### `decision == "stock"`
- Selected when a `strategy_type == "stock"` candidate is the best expression candidate.
- Means: **express the already validated thesis via equity (stock) rather than options**.
- Does NOT mean: buy stock now, generate a stock order, or approve any execution.
- Stock candidates do **not** require option legs.
- `approved_for_execution` remains `False`.
- No `order_id`, `account_id`, `broker_order`, or `execution_status` fields exist anywhere.
- The output is a research artifact, not a trade ticket.

### `decision == "option"`
- Selected when a real option strategy candidate (long_call, long_put, spread, etc.) is best.
- Means: express the thesis via the selected option structure.
- Same research-only, non-executable constraints as `"stock"`.

### `decision == "no_trade"`
- Selected when no thesis is validated, risk is too high, or no viable expression exists.
- `no_trade_reason` is **always required** when `decision == "no_trade"` — enforced by schema.
- A `no_trade` outcome is not a failure — it is a valid, auditable research conclusion.
- `OptionNoTradeReason` provides 10 specific reasons.

### `no_trade_reason` Consistency

`no_trade_reason` must be non-empty whenever `decision == "no_trade"`:
- `OptionExpressionCandidate`: enforced when `strategy_type == "no_trade"`.
- `OptionExpressionAssessment`: enforced when `decision == "no_trade"`.
- `OptionExpressionSummary`: enforced when `decision == "no_trade"`.
- `build_option_expression_report` always supplies a reason from `_select_candidate_strategy`
  when it produces a `no_trade` decision.

---

## 13. Distinction Between Option Expression and Executable Option Order

| Option Expression Report (Phase 3R-D) | Executable Option Order (not in this codebase) |
|--------------------------------------|-----------------------------------------------|
| Research artifact | Execution artifact |
| `approved_for_execution = False` (schema-enforced) | Would require `approved_for_execution = True` |
| No `order_id`, `account_id`, `broker_order` | Would include these fields |
| Offline / mock-only inputs | Would require live market data |
| No brokerage import | Would import broker SDK |
| No routing or fill simulation | Would include routing, fills, and confirmations |
| For research and review only | For execution |

**Phase 3R-D does not authorize trading or execution of any kind.**

---

## 14. Option Agent Constraints (Roadmap v4)

The Option Agent in Phase 3R-D:

- **Does NOT decide the thesis** — it expresses an already-validated thesis
- **Does NOT decide total portfolio allocation** — allocation context is read-only input
- **Does NOT override Allocation Agent** — `allocation_report` is consumed, not modified
- **Does NOT generate broker-ready orders** — no order fields, no brokerage integration
- **Does NOT call live option-chain APIs** — all data is caller-provided mock/non-live
- **Does NOT call Claude API or any LLM** — fully deterministic

---

## 15. Execution-Safety Guardrails

1. All models use `extra="forbid"` — unknown fields cause immediate validation error.
2. `approved_for_execution` is schema-guarded in 4 models with `model_validator`.
3. `OptionExpressionCandidate` with `approved_for_execution=True` raises `ValueError`.
4. No import of `streamlit`, `anthropic`, or any broker/brokerage module.
5. `build_option_expression_report` never calls external APIs or writes to external state.
6. Input artifacts are never mutated.
7. All IDs are deterministic hashes — no UUIDs that could masquerade as order IDs.

---

## 16. Offline / Mock-Only Nature

This phase is **offline and mock-only**:

- `OptionMarketSnapshot` is caller-provided mock data, not live option chain data.
- `OptionExpressionCandidate` strategies are caller-specified, not auto-generated from live feeds.
- No network calls are made anywhere in `option_expression.py`.
- No `yfinance`, `polygon.io`, or other market data client is imported.
- The module can run in a completely air-gapped environment.

---

## 17. Future Integration with Phase 4 Memory

When Roadmap Phase 4 Memory + Human Feedback work begins (after Phase 3R-E
is accepted), Phase 3R-D outputs can be extended with:

| Future Component | Integration Point |
|-----------------|-------------------|
| Option Trade Plan Memory | Store `OptionExpressionReport` in a persistent memory bank keyed by ticker + run_id |
| Human Feedback Layer | Add `HumanReviewReport` via the existing `input_bundle.human_review_report` field |
| Agent Evaluation | `OptionExpressionReport` already produces `ToolResult` suitable for evaluation harness |
| Live Phase Integration | `OptionExpressionInputBundle` can be wired to live `OptionMarketSnapshot` via Phase 4A's boundary contract |

**Phase 3R-D does not implement any of the above.** It provides the schema and
helper layer that future phases will wrap or extend.

---

## 18. Explicit Statement on Non-Authorization

> **This phase does not authorize trading or execution of any kind.**
>
> All outputs of `lib/reliability/option_expression.py` are for investment research
> and educational purposes only. They do not constitute investment advice, option
> recommendations, or trading instructions. Markets involve risk; invest with caution.
>
> `approved_for_execution` is permanently `False` in all Phase 3R-D models and
> reports. There is no code path in this module that can set it to `True`.

---

## 19. Files Created / Modified

| File | Status | Purpose |
|------|--------|---------|
| `lib/reliability/option_expression.py` | Created + Codex fixes | Main implementation (10+1 Literal aliases, 8 Pydantic models, 12 calculators, 7 helpers) |
| `scripts/test_reliability_option_expression.py` | Created + Codex fixes | Comprehensive test suite (277/277 tests pass) |
| `docs/reliability_phase_3r_option_expression.md` | Created + Codex fixes | This design documentation |
| `lib/reliability/__init__.py` | Modified | Added Phase 3R-D imports + `__all__` entries (39 new symbols) |
| `docs/ai_dev_state/PROJECT_STATE.md` | Modified | Phase 3R-C moved to Accepted; Phase 3R-D added to Awaiting Review |
| `docs/ai_dev_state/CURRENT_TASK.md` | Modified | Current task updated to Phase 3R-D |

### Codex Required Fixes Applied (this session)

| Fix | Change |
|-----|--------|
| Fix 1: Stock expression path | Added `"stock"` to `OptionExpressionStrategyType`; added `_STOCK_STRATEGY_TYPES` constant; `_strategy_type_to_decision("stock")` → `"stock"`; `_select_candidate_strategy` handles stock candidates as first-class alongside option candidates; `build_option_strategy_calculation` handles `"stock"` without crashing |
| Fix 2: Status precedence | Moved `needs_review` checks (high risk, review_required) before `unknown` check in `determine_option_expression_status`; `unknown + high risk` now returns `needs_review`, not `unknown` |
| Fix 3: no_trade_reason consistency | Added `model_validator` to `OptionExpressionAssessment` and `OptionExpressionSummary` enforcing non-empty `no_trade_reason` when `decision == "no_trade"` |
| Fix 4: Direct test command | Added `sys.path` fix at top of `scripts/test_reliability_option_expression.py`; runs without `PYTHONPATH=.` |
