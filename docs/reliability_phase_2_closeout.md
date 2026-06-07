# Reliability Phase 0–2 Technical Closeout

**Date**: 2026-05-22
**Status**: Phase 2 Closeout — implemented and awaiting Codex review.

---

## Overview

This document is the formal technical closeout for the reliability layer built
across Phase 0, Phase 1, and Phase 2. It records what was implemented, the
contracts introduced, verification commands, evaluation harness summary, and
what remains intentionally unintegrated.

See `docs/ai_dev_state/PHASE_2_CLOSEOUT.md` for the concise operational checkpoint.

---

## Phase 0–2 Accepted Components

### Phase 0 — Reliability Foundation

**Package**: `lib/reliability/`

| File | Purpose |
|------|---------|
| `schemas.py` | Core Pydantic models: `DataSnapshot`, `ToolResult`, `EvidenceRef`, `Finding`, `Assumption`, `Risk`, `AgentConfidence`, `AgentResult`, `ValidationIssue`, `ValidationReport` |
| `run_context.py` | `RunContext` dataclass with `run_id` (`TICKER_YYYYMMDD_HHMMSS_shortuuid`), `run_dir` under `research/runs/`, `create_run_context()` factory |
| `evidence_store.py` | `EvidenceStore`: `add_tool_result() -> evidence_id`, persists `tool_results.jsonl` and `evidence_manifest.json` |
| `validators.py` | `validate_agent_result()`: detects unsupported findings, hallucinated evidence IDs, numeric claims without evidence, missing risk evidence |
| `serialization.py` | `save_json_model()`, `save_json()` helpers |
| `__init__.py` | Package entry point |

### Phase 0.1 — Reliability Hardening

- Strengthened `validate_agent_result()` edge cases.
- Added negative-case test coverage (`scripts/test_reliability_negative_cases.py`).

### Phase 0.2 — ToolResult Adapter Planning

- `adapters.py`: `stable_hash_payload()`, `make_evidence_id()`, `tool_result_from_outputs()`, `data_snapshot_from_payload()`.
- Domain-specific adapters: `valuation_tool_result()`, `technical_tool_result()`, `scanner_tool_result()`, `sector_rotation_tool_result()`.

### Phase 1A — Isolated Valuation ToolResult Integration

- Valuation outputs wrapped as `ToolResult` via `valuation_tool_result()`.
- Test: `scripts/test_reliability_valuation_adapter.py`.

### Phase 1B — Isolated Technical ToolResult Integration

- Technical indicator outputs wrapped as `ToolResult` via `technical_tool_result()`.
- Test: `scripts/test_reliability_technical_adapter.py`.

### Phase 1C — Isolated Scanner/Rotation ToolResult Integration

- Scanner and sector rotation outputs wrapped via `scanner_tool_result()` and `sector_rotation_tool_result()`.
- Test: `scripts/test_reliability_scanner_rotation_adapter.py`.

### Phase 1D — AgentResult JSON Contract

- `agent_output.py`: `parse_agent_result_json()`, `parse_and_validate_agent_result()`, `agent_result_to_json()`.
- Test: `scripts/test_reliability_agent_output.py`.

### Phase 1E — Prompt Contract Drafting / Constrained Agent Interface

- `prompt_contracts.py`: `extract_field_paths()`, `build_evidence_packet()`, `build_schema_summary()`, `build_agent_result_prompt()`, `build_repair_prompt()`.
- Test: `scripts/test_reliability_prompt_contracts.py`.

### Phase 1F — Mock Constrained Agent Roundtrip

- End-to-end mock: deterministic tool output → `ToolResult` → evidence packet → `AgentResult` parse → validate.
- Test: `scripts/test_reliability_mock_agent_roundtrip.py`.

### Phase 1G — Reliability Orchestration Design

- `orchestration_plan.py`: `ReliabilityFeatureFlags`, `get_default_reliability_flags()`, `build_orchestration_step_plan()`, `validate_flag_combination()`, `list_supported_future_steps()`.
- Test: `scripts/test_reliability_orchestration_plan.py`.

### Phase 2A — Feature Flag Config Foundation

- `config.py`: `parse_bool()`, `load_reliability_flags_from_mapping()`, `load_reliability_flags_from_env()`, `reliability_flags_to_env_dict()`, `describe_reliability_config()`.
- Test: `scripts/test_reliability_config.py`.

### Phase 2B — Investment Horizon Schema Foundation

- `horizon.py`: `InvestmentHorizon`, `HorizonEvidenceRequirement`, `HorizonRisk`, `HorizonThesis`, `HorizonRecommendation`, `HorizonTradePlan`, `HorizonDecisionSet`.
- Helpers: `default_horizon_evidence_requirements()`, `group_horizon_decisions_by_horizon()`, `summarize_horizon_coverage()`, `validate_horizon_decision_set()`.
- Test: `scripts/test_reliability_horizon.py`.

### Phase 2C — Macro Data + ToolResult Schema Foundation

- `macro.py`: `MacroDataCategory`, `MacroIndicator`, `MacroSnapshot`, `MacroRegimeSignal`, `MacroRegimeAssessment`.
- Helpers: `default_macro_staleness_rules()`, `macro_snapshot_from_indicators()`, `macro_tool_result_from_snapshot()`, `extract_macro_indicator_paths()`, `summarize_macro_snapshot_coverage()`, `validate_macro_snapshot()`.
- Test: `scripts/test_reliability_macro.py`.

### Phase 2D — Allocation / Position Sizing Tool Schema Foundation

- `allocation.py`: `AllocationAction`, `PositionDirection`, `RiskBudgetStatus`, `PositionSnapshot`, `PortfolioSnapshot`, `AllocationTarget`, `RiskBudget`, `PositionSizingResult`, `StopLossRiskResult`, `AllocationDecisionSet`.
- Calculators: `compute_position_market_value()`, `compute_current_allocation_pct()`, `calculate_position_sizing()`, `calculate_cash_released_from_trim()`, `calculate_cash_needed_for_add()`, `calculate_stop_loss_risk()`.
- Test: `scripts/test_reliability_allocation.py`.

### Phase 2E — Option Data + Strategy Tool Schema Foundation

- `options.py`: `OptionType`, `OptionPositionSide`, `OptionStrategyType`, `OptionContractSnapshot`, `OptionChainSnapshot`, `OptionLeg`, `OptionStrategyCandidate`, `OptionPayoffResult`, `OptionLiquidityCheck`, `OptionEventRiskCheck`, `OptionStrategyDecisionSet`.
- Payoff calculators: `calculate_long_call_payoff()`, `calculate_long_put_payoff()`, `calculate_call_debit_spread_payoff()`, `calculate_put_debit_spread_payoff()`, `calculate_cash_secured_put_payoff()`, `calculate_covered_call_payoff()`.
- Test: `scripts/test_reliability_options.py`.

### Phase 2F — News ToolResult Wrapper Foundation

- `news.py`: `NewsSourceVendor`, `NewsEventCategory`, `NewsImpactHorizon`, `NewsFreshnessStatus`, `NewsEvent`, `NewsSnapshot`, `NewsCoverageSummary`.
- Helpers: `classify_news_category()`, `normalize_finnhub_news_event()`, `news_snapshot_from_events()`, `news_tool_result_from_snapshot()`, `extract_news_event_paths()`, `summarize_news_snapshot_coverage()`, `validate_news_snapshot()`.
- Test: `scripts/test_reliability_news.py`.

### Phase 2G — Catalyst / Earnings / Estimate Revision Schema Foundation

- `catalysts.py`: `CatalystType`, `CatalystTiming`, `CatalystMateriality`, `CatalystSourceType`, `EarningsStatus`, `EarningsSurpriseDirection`, `EstimateMetric`, `RevisionDirection`, `RevisionSourceType`, `CatalystEvent`, `EarningsEvent`, `EstimateRevision`, `CatalystSnapshot`, `CatalystCoverageSummary`.
- Helpers: `infer_catalyst_timing()`, `infer_earnings_surprise_direction()`, `infer_revision_direction()`, `calculate_revision_pct()`, `catalyst_snapshot_from_components()`, `catalyst_tool_result_from_snapshot()`, `extract_catalyst_event_paths()`, `summarize_catalyst_snapshot_coverage()`, `validate_catalyst_snapshot()`.
- Note: This phase merged Roadmap v4 detailed phases 2F (Catalyst Schema), 2H (Earnings Data Schema), and 2I (Estimate Revision Schema) into one foundation.
- Test: `scripts/test_reliability_catalysts.py`.

### Phase 2H — Validation Aggregator

- `validation_aggregator.py`: `ValidationDomain`, `ValidationSeverity`, `ValidationStatus`, `ValidationItemType`, `AggregatedValidationItem`, `ValidationAggregate`.
- Helpers: `make_validation_item_id()`, `warning_to_validation_item()`, `validation_report_to_items()`, `aggregate_validation_items()`, `aggregate_warning_groups()`, `merge_validation_aggregates()`, `summarize_validation_aggregate()`, `collect_phase2_validation_warnings()`, `validation_aggregate_tool_result_from_aggregate()`.
- Test: `scripts/test_reliability_validation_aggregator.py`.

### Phase 2I — Staleness Checker

- `staleness.py`: `StalenessStatus`, `StalenessDomain`, `StalenessSeverity`, `TimestampRole`, `StalenessPolicy`, `StalenessFinding`, `StalenessReport`.
- Checkers: `check_tool_result_staleness()`, `check_news_snapshot_staleness()`, `check_option_decision_set_staleness()`, `check_catalyst_snapshot_staleness()`, `check_allocation_decision_set_staleness()`, `check_macro_snapshot_staleness()`.
- Helpers: `parse_iso_like_datetime()`, `days_between()`, `make_staleness_finding_id()`, `evaluate_timestamp_staleness()`, `evaluate_expiration_status()`, `aggregate_staleness_findings()`, `default_staleness_policy_for_domain()`, `staleness_findings_to_validation_items()`, `staleness_report_tool_result_from_report()`, `summarize_staleness_report()`.
- Test: `scripts/test_reliability_staleness.py`.

### Phase 2J — Critic Agent v0.1

- `critic.py`: `CriticIssueType`, `CriticSeverity`, `CriticStatus`, `CriticTargetType`, `CriticRecommendation`, `CriticIssue`, `CriticResult`.
- 11 deterministic helpers: `make_critic_issue_id()`, `critic_issue_from_validation_item()`, `critic_issue_from_staleness_finding()`, `critique_validation_aggregate()`, `critique_staleness_report()`, `critique_agent_result_structure()`, `detect_overconfidence()`, `aggregate_critic_issues()`, `run_mock_critic()`, `critic_result_tool_result_from_result()`, `summarize_critic_result()`.
- Test: `scripts/test_reliability_critic.py`.

### Phase 2K — Evaluation Harness

See the Evaluation Harness Summary section below.

---

## Roadmap v4 Numbering Reconciliation

The project followed Roadmap v4's compressed execution sequence. The table below maps
the detailed Roadmap v4 numbering to the implemented numbering explicitly.

| Roadmap v4 Detailed | Implemented As | Status |
|---------------------|---------------|--------|
| 2F — Catalyst Schema | 2G — Catalyst / Earnings / Estimate Revision Schema | Accepted |
| 2G — News ToolResult Wrapper | 2F — News ToolResult Wrapper | Accepted |
| 2H — Earnings Data Schema | 2G — Catalyst / Earnings / Estimate Revision Schema | Accepted (merged) |
| 2I — Estimate Revision Schema | 2G — Catalyst / Earnings / Estimate Revision Schema | Accepted (merged) |
| 2J — Validation Aggregator | 2H — Validation Aggregator | Accepted |
| 2K — Staleness Checker | 2I — Staleness Checker | Accepted |
| 2L — Critic Agent v0.1 | 2J — Critic Agent v0.1 | Accepted |
| (inserted before closeout) | 2K — Evaluation Harness | Accepted |

**No detailed Roadmap v4 Phase 2 capability was intentionally skipped.**

- Catalyst, Earnings, and Estimate Revision schemas were merged into one foundation (2G)
  to reduce redundant boilerplate. All three schema types (`CatalystEvent`, `EarningsEvent`,
  `EstimateRevision`) are present in `catalysts.py`.
- The Evaluation Harness (2K) was inserted before the closeout to prove the reliability
  layer catches the required failure modes before Phase 3 begins.
- News ToolResult Wrapper and Catalyst Schema ordering was swapped in execution
  (News first), because News was a simpler warm-up before the multi-type Catalyst schema.

---

## Contracts Introduced

### Evidence Layer

| Contract | File | Description |
|----------|------|-------------|
| `ToolResult` schema | `schemas.py` | Versioned, immutable evidence artifact; `extra="forbid"` |
| `EvidenceRef` binding | `schemas.py` | Links agent claim to specific `ToolResult` field |
| `AgentResult` schema | `schemas.py` | Constrained JSON output; must reference evidence |
| `validate_agent_result()` | `validators.py` | Returns `ValidationReport`; detects hallucinated IDs, unsupported numeric claims |

### Aggregation Layer

| Contract | File | Description |
|----------|------|-------------|
| `ValidationAggregate` | `validation_aggregator.py` | Cross-domain warning aggregation |
| `StalenessReport` | `staleness.py` | Freshness risk per domain |
| `CriticResult` | `critic.py` | Deterministic critique; no live LLM |
| `ReliabilityScoreSummary` | `evaluation.py` | Aggregate pass/fail across eval cases |

### Domain Schemas

| Domain | File | Key Types |
|--------|------|-----------|
| Horizon | `horizon.py` | `InvestmentHorizon`, `HorizonDecisionSet` |
| Macro | `macro.py` | `MacroSnapshot`, `MacroRegimeAssessment` |
| Allocation | `allocation.py` | `AllocationDecisionSet`, `PositionSizingResult` |
| Options | `options.py` | `OptionStrategyDecisionSet`, `OptionPayoffResult` |
| News | `news.py` | `NewsSnapshot`, `NewsEvent` |
| Catalyst | `catalysts.py` | `CatalystSnapshot`, `EarningsEvent`, `EstimateRevision` |

---

## Test and Verification Commands

Run all reliability tests in order:

```bash
python3 scripts/test_reliability_foundation.py
python3 scripts/test_reliability_negative_cases.py
python3 scripts/test_reliability_adapters.py
python3 scripts/test_reliability_valuation_adapter.py
python3 scripts/test_reliability_technical_adapter.py
python3 scripts/test_reliability_scanner_rotation_adapter.py
python3 scripts/test_reliability_agent_output.py
python3 scripts/test_reliability_prompt_contracts.py
python3 scripts/test_reliability_mock_agent_roundtrip.py
python3 scripts/test_reliability_orchestration_plan.py
python3 scripts/test_reliability_config.py
python3 scripts/test_reliability_horizon.py
python3 scripts/test_reliability_macro.py
python3 scripts/test_reliability_allocation.py
python3 scripts/test_reliability_options.py
python3 scripts/test_reliability_news.py
python3 scripts/test_reliability_catalysts.py
python3 scripts/test_reliability_validation_aggregator.py
python3 scripts/test_reliability_staleness.py
python3 scripts/test_reliability_critic.py
python3 scripts/test_reliability_evaluation_harness.py
python3 evals/run_evals.py
python3 scripts/test_reliability_phase_2_closeout.py
```

---

## Evaluation Harness Summary (Phase 2K)

### Design

- Fixed synthetic eval cases in `evals/cases/*.json`
- Expected detection outputs in `evals/expected/*.json`
- Fail-closed runner: any missing or malformed fixture → `status="error"`, `passed_expectation=False`
- CLI runner: `evals/run_evals.py` exits nonzero on any failure
- `ReliabilityScoreSummary`: `total_cases`, `passed_cases`, `failed_cases`, `detection_rate`

### Failure Modes Covered (12 cases)

| # | Case ID | Failure Mode |
|---|---------|-------------|
| 1 | `01_unsupported_numeric_claim` | `unsupported_numeric_claim` |
| 2 | `02_hallucinated_evidence_id` | `hallucinated_evidence_id` |
| 3 | `03_stale_news_used_as_fresh` | `stale_news_used_as_fresh` |
| 4 | `04_missing_downside_risk` | `missing_downside_risk` |
| 5 | `05_missing_assumption` | `missing_assumption` |
| 6 | `06_overconfident_with_validation_warnings` | `overconfident_with_validation_warnings` |
| 7 | `07_overconfident_with_stale_data` | `overconfident_with_stale_data` |
| 8 | `08_horizon_mismatch` | `horizon_mismatch` |
| 9 | `09_unsupported_trade_plan` | `unsupported_trade_plan` |
| 10 | `10_option_strategy_without_risk_budget` | `option_strategy_without_risk_budget` |
| 11 | `11_conflicting_evidence` | `conflicting_evidence` |
| 12 | `12_clean_minimal_case` | (clean — expects no critical issues) |

### Normal Suite Result

- 12 cases, 12 passed
- Detection rate: 100%
- Fail-closed behavior verified for missing and malformed fixtures
- `scripts/test_reliability_evaluation_harness.py`: 91/91 assertions pass

---

## What Remains Intentionally Unintegrated

The reliability layer is a standalone foundation only. The following are explicitly NOT done:

- **No live app integration.** `lib/reliability/` is not imported by `app.py` or `pages/`.
- **No Streamlit UI integration.** No new UI components or reliability dashboard.
- **No live LLM orchestration changes.** `lib/llm_orchestrator.py` is unmodified.
- **No app runtime blocking.** Reliability validation does not block the live app.
- **No broker/order integration.** No trade execution behavior.
- **No live data refresh behavior.** Reliability layers do not fetch or refresh market data.
- **No automated investment recommendation output.** No buy/sell signals or advice.

These remain out of scope until Phase 3 explicitly integrates the orchestration skeleton.

---

## Phase 3 Entry Criteria

Before starting Phase 3:

1. All 23 reliability test scripts pass (including `test_reliability_phase_2_closeout.py`).
2. `evals/run_evals.py` exits 0 (12/12 pass, 100% detection).
3. Phase 2K is accepted by Codex review.
4. `docs/ai_dev_state/PROJECT_STATE.md` reflects Phase 2K as accepted and Phase 2 Closeout as complete.
5. Global guardrails remain in force (no forbidden file modifications).

---

## Phase 3 Recommendation

**Phase 3A — Validated Agent Orchestration Skeleton**

Suggested goal: a standalone script or module (no live app, no Streamlit, no LLM) that chains:

```
ToolResult inputs (synthetic/mock)
  -> mock/constrained AgentResult
  -> validate_agent_result()
  -> ValidationAggregate (aggregate_validation_items)
  -> StalenessReport (aggregate_staleness_findings)
  -> CriticResult (run_mock_critic)
  -> ReliabilityScoreSummary / eval gate reference
  -> OrchestrationReport (draft schema)
```

Constraints for Phase 3A:
- No live LLM calls
- No Streamlit or app integration
- No live data fetching
- No investment recommendation output
- Output is a deterministic, auditable JSON report

Later phases:
- **Phase 3B** — Macro Agent v0.1 or Horizon-aware Synthesis (Roadmap v4 alignment TBD)
- **Phase 3C** — Mock Debate Layer by Horizon
- **Phase 3D** — DecisionPacket schema
- **Phase 3E** — Feature-flagged dry-run orchestration planning
