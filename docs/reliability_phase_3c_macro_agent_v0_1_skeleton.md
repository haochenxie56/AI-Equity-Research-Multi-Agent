# Phase 3C — Macro Agent v0.1 Skeleton

**Status**: Implemented — Awaiting Codex review
**Date**: 2026-05-23
**File**: `lib/reliability/macro_agent.py`
**Test**: `scripts/test_reliability_macro_agent.py` — 101/101 assertions pass

---

## 1. Purpose

Phase 3C introduces the Macro Agent v0.1 Skeleton: a **deterministic, rule-based, offline** macro regime interpretation layer that bridges existing Phase 2C macro evidence artifacts (`MacroSnapshot`, macro `ToolResult`) with the constrained reliability output contracts (`AgentResult`, `ToolResult`) established in Phases 0–3B.

This agent does **not**:
- Call Claude API or any external LLM.
- Fetch live macro data.
- Integrate with the live Streamlit app or live workflow.
- Produce investment advice or buy/sell recommendations.

All outputs are labeled as mock/dry-run research artifacts for audit and testing purposes only.

---

## 2. Why Dry-Run / Mock-Only First

The Macro Agent skeleton follows the same design discipline as Phase 3A (Orchestration Skeleton) and Phase 3B (Horizon-aware Synthesis Skeleton):

> **Deterministic computation, agentic interpretation, auditable synthesis.**

Building the schema, rule-based inference, and evidence-binding layers first enables:
- Complete unit test coverage before live LLM calls are introduced.
- Auditable outputs that can be evaluated against the Phase 2K evaluation harness.
- Iterative refinement of signal domain mapping and regime inference rules without incurring LLM API costs.
- A stable integration surface for Phase 3D+ agents (Debate by Horizon, Sector Selection).

---

## 3. Relationship to Prior Phases

| Prior Phase | Relationship |
|-------------|-------------|
| Phase 2C — Macro ToolResult Schema | `MacroSnapshot`, `MacroIndicator`, `MacroRegimeSignal`, `macro_tool_result_from_snapshot()` are the primary input data types consumed by the Macro Agent input bundle. |
| Phase 2H — ValidationAggregate | `ValidationAggregate` and `AggregatedValidationItem` are converted into `MacroAgentIssue` objects via `issue_from_validation_item_for_macro()`. |
| Phase 2I — StalenessReport | `StalenessReport` and `StalenessFinding` are converted into `MacroAgentIssue` objects via `issue_from_staleness_finding_for_macro()`. |
| Phase 2J — CriticResult | `CriticResult` and `CriticIssue` are converted into `MacroAgentIssue` objects via `issue_from_critic_issue_for_macro()`. |
| Phase 3A — Orchestration Skeleton | `OrchestrationReport` is accepted as an optional duck-typed field in `MacroAgentInputBundle`. |
| Phase 3B — Horizon-aware Synthesis | `HorizonSynthesisReport` is accepted as an optional duck-typed field in `MacroAgentInputBundle`. |
| Phase 2K — Evaluation Harness | `MacroAgentResult` and `MacroAgentInputBundle` are compatible with the eval harness via the `AgentResult` bridge. |

---

## 4. Schema Models

### 4.1 MacroAgentInputBundle

Collects all available reliability artifacts needed for macro regime assessment:

| Field | Type | Purpose |
|-------|------|---------|
| `bundle_id` | str | Non-empty unique identifier |
| `as_of` | str | Research date |
| `ticker` | str \| None | Optional ticker (macro data is often non-ticker-specific) |
| `macro_snapshot` | Any \| None | Phase 2C `MacroSnapshot` (duck-typed) |
| `tool_results` | list[ToolResult] | All available `ToolResult` artifacts |
| `validation_aggregate` | ValidationAggregate \| None | Phase 2H output |
| `staleness_report` | StalenessReport \| None | Phase 2I output |
| `critic_result` | CriticResult \| None | Phase 2J output |
| `horizon_synthesis_report` | Any \| None | Phase 3B output (duck-typed) |
| `orchestration_report` | Any \| None | Phase 3A output (duck-typed) |

### 4.2 MacroSignalSummary

Aggregates evidence for one signal domain (rates, inflation, growth, etc.):

| Field | Description |
|-------|-------------|
| `domain` | `MacroSignalDomain` literal |
| `direction` | `MacroHorizonImpactDirection` inferred from evidence |
| `strength` | high / medium / low / unknown |
| `evidence_ids` | Collected from matching ToolResults |
| `stale` | True if staleness findings relate to this domain |
| `contested` | True if critic/validation issues relate to this domain |

### 4.3 MacroRegimeAssessment

Inferred macro regime from available signal summaries:

| Field | Description |
|-------|-------------|
| `regime` | `MacroRegimeType` (risk_on, risk_off, neutral, inflationary, etc.) |
| `confidence` | high / medium / low / insufficient_evidence / unknown |
| `risk_appetite` | `MacroRiskAppetite` (high, moderate, low, defensive, etc.) |
| `signal_summaries` | All summaries used for regime inference |
| `supporting_evidence_ids` | Deduped list of evidence IDs |
| `issues` | Regime-level `MacroAgentIssue` objects |

### 4.4 MacroSectorBias

Broad macro-level sector bias (not individual security recommendation):

| Field | Description |
|-------|-------------|
| `sector` | Broad sector label (e.g. "growth_equities", "defensives") |
| `bias` | `MacroSectorBiasDirection` (overweight, underweight, neutral, etc.) |
| `rationale` | Text explanation; no buy/sell language |
| `supporting_domains` | Which macro signal domains support this bias |

### 4.5 MacroHorizonImpact

Macro impact per investment horizon:

| Field | Description |
|-------|-------------|
| `horizon` | short_term / medium_term / long_term |
| `impact` | `MacroHorizonImpactDirection` (supportive, headwind, neutral, mixed, etc.) |
| `confidence` | low / medium / high / insufficient_evidence / unknown |
| `rationale` | Non-investment-advice explanation |

### 4.6 MacroAgentResult

Full result from the Macro Agent v0.1 run:

| Field | Description |
|-------|-------------|
| `macro_agent_id` | Deterministic stable identifier |
| `status` | `MacroAgentStatus` (pass, pass_with_warnings, fail, insufficient_evidence) |
| `recommendation` | `MacroAgentRecommendation` (proceed_to_horizon_synthesis, revise, reject, needs_more_evidence) |
| `regime_assessment` | `MacroRegimeAssessment` \| None |
| `sector_biases` | list[MacroSectorBias] |
| `horizon_impacts` | list[MacroHorizonImpact] — always 3 entries if regime determined |
| `issues` | Aggregated `MacroAgentIssue` list (deduped) |
| `validation_aggregate` | Passed through from input bundle |
| `staleness_report` | Passed through from input bundle |
| `critic_result` | Passed through from input bundle |

**Auto-normalisation rules:**
- `fail` + `reject` if any critical issue.
- `pass_with_warnings` + `revise` if any warning issue (no criticals).
- `insufficient_evidence` + `needs_more_evidence` if no regime assessment and missing evidence.
- `pass` + `proceed_to_horizon_synthesis` otherwise.

---

## 5. Deterministic Rule-Based Regime Inference

`infer_macro_regime()` applies conservative keyword-based rules to signal domain sets:

| Condition | Regime | Risk Appetite |
|-----------|--------|---------------|
| No signal summaries | `insufficient_evidence` | `insufficient_evidence` |
| ≥ 50% signals stale/contested | `mixed` | `unknown` |
| liquidity + breadth + volatility domains present | `neutral` | `moderate` |
| credit + growth domains present | `risk_off` | `defensive` |
| inflation + rates domains present | `inflationary` | `low` |
| growth only | `neutral` | `moderate` |
| ≥ 3 domains, no specific pattern | `mixed` | `unknown` |
| < 3 domains, no pattern | `insufficient_evidence` | `insufficient_evidence` |

All confidence values are `"low"` in v0.1 skeleton — live LLM interpretation will refine these in future phases.

---

## 6. Sector Bias Mapping (Mock)

`derive_macro_sector_biases()` applies broad mock sector bias based on regime:

| Regime | Sector | Mock Bias |
|--------|--------|-----------|
| risk_on / liquidity_easing / early_cycle | growth_equities | neutral |
| risk_on / liquidity_easing / early_cycle | cyclicals | neutral |
| risk_on / liquidity_easing / early_cycle | defensives | underweight |
| risk_off / recessionary / liquidity_tightening / late_cycle | defensives | neutral |
| risk_off / recessionary / liquidity_tightening / late_cycle | cyclicals | underweight |
| risk_off / recessionary / liquidity_tightening / late_cycle | growth_equities | underweight |
| inflationary / disinflationary | energy_materials | neutral |
| inflationary / disinflationary | long_duration_growth | underweight |
| neutral / mixed / other | all_sectors | neutral |

All rationales explicitly state: **"Not an investment recommendation."**

---

## 7. Horizon Impact Mapping

`derive_macro_horizon_impacts()` always produces short_term, medium_term, long_term entries:

| Horizon | Sensitive Domains | Headwind Regimes | Supportive Regimes |
|---------|------------------|------------------|--------------------|
| short_term | volatility, breadth, liquidity, credit | risk_off, recessionary, liquidity_tightening | risk_on, liquidity_easing, early_cycle |
| medium_term | growth, inflation, rates, credit | recessionary, risk_off | risk_on, early_cycle, liquidity_easing |
| long_term | policy, growth, liquidity, rates | recessionary | liquidity_easing, early_cycle |

---

## 8. Validation / Staleness / Critic Issue Incorporation

Three converters map existing reliability artifacts to `MacroAgentIssue`:

| Function | Input | Output |
|----------|-------|--------|
| `issue_from_validation_item_for_macro()` | `AggregatedValidationItem` | `MacroAgentIssue` |
| `issue_from_staleness_finding_for_macro()` | `StalenessFinding` | `MacroAgentIssue` |
| `issue_from_critic_issue_for_macro()` | `CriticIssue` | `MacroAgentIssue` |

All converters:
- Preserve `evidence_id`, `field_path`, and `related_id` / `object_id`.
- Infer `MacroSignalDomain` from `field_path` or `message` via `infer_macro_signal_domain_from_path()`.
- Map source issue types to `MacroAgentIssueType`.
- Do not mutate inputs.

`build_macro_agent_result()` collects issues from regime_assessment, sector_biases, horizon_impacts, and all three converters. It deduplicates by `issue_id` (first occurrence wins).

---

## 9. AgentResult Bridge

`macro_agent_result_to_agent_result()` converts a `MacroAgentResult` into the existing constrained `AgentResult` contract for downstream compatibility:

- `agent_name = "macro_agent_v0_skeleton"`.
- Findings cite available evidence IDs via `EvidenceRef`.
- All finding text is prefixed `[MOCK DRY-RUN]`.
- No buy/sell/purchase language.
- Confidence score is low (0.2–0.5) for mock output.
- Includes `dry_run` and `regime_inference_method` assumptions.
- Risks populated from critical and warning issues.

---

## 10. ToolResult Wrapper

`macro_agent_tool_result_from_result()` wraps a `MacroAgentResult` into a `ToolResult` for submission to `EvidenceStore`:

- `tool_name = "macro_agent_result"` (stable).
- `target` defaults to `result.ticker` or `"macro_agent"`.
- `payload` = `{"result": ..., "summary": ..., "calculation_version": ...}`.
- `evidence_id` is content-sensitive: the full payload is built before hashing, so changing result content changes the `evidence_id`.
- `summarize_macro_agent_result()` provides a compact summary dict for the payload.

---

## 11. What This Phase Does NOT Do

| Not Implemented | Reason |
|----------------|--------|
| Live LLM calls | Dry-run / mock-only per Phase 3C scope |
| Live macro data fetching | No live data integration in Phase 3C |
| Live app integration | Streamlit UI / live workflow unchanged |
| Streamlit UI | Forbidden by global guardrails |
| Broker / order behavior | Out of scope |
| Allocation / option decisioning | Separate dedicated agents |
| Debate Agent | Phase 3D or later |
| Memory Layer | Future phase |
| Sector Selection Agent | Future phase |
| Stock Selection Agent | Future phase |

---

## 12. Future Relationship

| Future Phase | Relationship |
|-------------|-------------|
| Phase 3D — Debate by Horizon | Debate layer will consume `MacroAgentResult` + `HorizonSynthesisReport` |
| Phase 3D — Catalyst Agent | Catalyst agent produces `CatalystSnapshot` consumed alongside macro evidence |
| Sector Selection Agent | Will consume `MacroSectorBias` outputs |
| Horizon-aware Synthesis | `MacroHorizonImpact` outputs flow into horizon cards |
| Allocation Agent | Macro risk appetite informs risk budget inputs |
| Option Expression Agent | Macro regime context influences options strategy selection |
| Investment Cockpit | Will surface macro regime, risk appetite, sector bias in dashboard |

---

## 13. Disclaimer

All outputs from this system are for investment research and educational purposes only. They do not constitute investment advice. Markets involve risk; invest with caution.
