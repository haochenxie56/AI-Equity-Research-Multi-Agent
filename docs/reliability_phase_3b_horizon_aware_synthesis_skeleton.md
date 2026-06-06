# Phase 3B: Horizon-aware Synthesis Skeleton

**Date**: 2026-05-22  
**Phase**: 3B  
**Status**: Implemented — awaiting Codex review  
**Module**: `lib/reliability/horizon_synthesis.py`  

---

## Purpose

Phase 3B creates a standalone, deterministic synthesis layer that consumes existing
Phase 0–3A reliability artifacts and produces **structured, auditable, evidence-aware
synthesis outputs split by investment horizon**:

- **short_term** — days to weeks (technical/news/catalyst driven)
- **medium_term** — weeks to months (earnings/estimate/catalyst/news driven)
- **long_term** — months to years (valuation/fundamental/macro driven)

This layer is the structural bridge between the validated orchestration skeleton
(Phase 3A) and future live agents (Macro Agent v0.1, Debate by Horizon,
Catalyst Agent, etc.). It establishes the schema and synthesis logic before any
live data is introduced.

---

## Why Horizon-aware Synthesis Comes Before Live Agents

Horizon-specific synthesis must be **schema-first**. Defining:

1. What evidence is expected per horizon
2. How validation/staleness/critic issues map to horizon-level problems
3. What "sufficient evidence" means for each bucket
4. How cards are normalized and how the overall report status is derived

...before wiring live Macro, News, or Catalyst agents prevents ad-hoc accumulation
of horizon logic across multiple agent files. The skeleton is also fully testable
offline without any API keys or live data.

---

## Relationship to Prior Phases

| Prior Phase | How Phase 3B Consumes It |
|-------------|--------------------------|
| Phase 2B — Horizon Schema | `HorizonBucket` enum mirrors `InvestmentHorizon`; domain expectation tables are derived from horizon evidence requirements |
| Phase 3A — OrchestrationReport | `HorizonSynthesisInputBundle.orchestration_report` accepts an `OrchestrationReport` as fallback source for `validation_aggregate`, `staleness_report`, `critic_result` |
| Phase 2H — ValidationAggregate | `AggregatedValidationItem` objects are converted to `HorizonSynthesisIssue` via `issue_from_validation_item_for_horizon()` |
| Phase 2I — StalenessReport | `StalenessFinding` objects are converted to `HorizonSynthesisIssue` via `issue_from_staleness_finding_for_horizon()` |
| Phase 2J — CriticResult | `CriticIssue` objects are converted to `HorizonSynthesisIssue` via `issue_from_critic_issue_for_horizon()` |
| Phase 2K — Evaluation Harness | `ReliabilityScoreSummary` is accepted in the input bundle for future scoring integration |

---

## Key Schemas

### HorizonSynthesisInputBundle

The entry point for one synthesis run. Accepts:

- `bundle_id`, `as_of`, `ticker` — identification
- `agent_result` — optional AgentResult for populating supported_points/risks/assumptions
- `orchestration_report` — optional OrchestrationReport (Any type; duck-typed) for fallback artifact resolution
- `validation_aggregate`, `staleness_report`, `critic_result` — directly provided reliability artifacts
- `tool_results` — list of ToolResult for evidence ID extraction and domain coverage inference
- `reliability_score_summary` — optional for future scoring integration

**Priority**: Direct bundle fields take precedence over `orchestration_report` attributes.

### HorizonEvidenceSummary

Per-horizon evidence coverage summary:

- `evidence_count` — total unique evidence IDs collected
- `stale_evidence_count` — count of non-fresh staleness findings
- `validation_issue_count` / `critic_issue_count` — issue counts
- `supporting_evidence_ids` — list of collected evidence IDs
- `missing_domains` — expected domains not covered by tool_results
- `contested_domains` — domains with conflicting critic signals

### HorizonSynthesisCard

One horizon's synthesis output:

- `horizon` — `HorizonBucket` (short_term / medium_term / long_term)
- `status` — auto-normalized from issues and evidence count
- `signal_direction` — determined from conflicting signals and evidence
- `confidence` — determined from evidence count and issue severity
- `recommendation` — auto-normalized from status
- `thesis_summary` — mock cautious language (no investment advice)
- `supported_points`, `risks`, `assumptions` — from agent_result if provided
- `missing_evidence` — missing expected domains
- `evidence_summary` — embedded `HorizonEvidenceSummary`
- `issues` — all converted `HorizonSynthesisIssue` objects

**Model-level normalization** (applied by `model_validator`):
- critical issues → `status="fail"`, `recommendation="reject"`
- warning issues → `status="pass_with_warnings"`, `recommendation="revise"`
- no issues + evidence_count == 0 → `status="unknown"`, `recommendation="needs_more_evidence"`
- no issues + evidence > 0 → `status="pass"`, `recommendation="proceed_to_debate"`

### HorizonSynthesisReport

Full three-horizon report:

- `synthesis_id`, `as_of`, `ticker` — identification
- `status` / `recommendation` — auto-normalized from all card statuses and issues
- `cards` — exactly three cards, auto-sorted to canonical order
- Attached artifacts: `validation_aggregate`, `staleness_report`, `critic_result`
- `orchestration_report_id` — links back to Phase 3A output
- `issues` — top-level synthesis issues

**Model-level normalization**: fail if any card fails, pass_with_warnings if any card
has warnings, needs_more_evidence if all cards need evidence, pass if all pass.

---

## How Short / Medium / Long Cards Differ

Each horizon bucket has **different expected evidence domains**:

| Horizon | Expected Domains |
|---------|-----------------|
| short_term | technical, news, catalyst |
| medium_term | earnings, estimate, catalyst, news |
| long_term | valuation, fundamental, macro |

Domain coverage is **inferred heuristically** from `tool_result.tool_name` keyword
matching. If an expected domain is not covered, a `missing_evidence` warning issue is
added to the card. This is a structural heuristic only — no live data is fetched.

---

## How Validation / Staleness / Critic Issues Are Converted

### From ValidationAggregate → HorizonSynthesisIssue

`issue_from_validation_item_for_horizon()` converts `AggregatedValidationItem`:

| ValidationItemType | HorizonSynthesisIssueType |
|--------------------|--------------------------|
| stale_data | stale_evidence |
| missing_data | missing_evidence |
| evidence_binding | unsupported_claim |
| unsupported | unsupported_claim |
| risk_limit | validation_issue |
| safety | critic_issue |
| schema | validation_issue |
| mismatch | conflicting_signal |
| provenance | missing_evidence |

Severity maps directly (critical/warning/info). `item_id`, `evidence_id`, and
`field_path` are preserved as `related_id`, `evidence_id`, `field_path`.

### From StalenessReport → HorizonSynthesisIssue

`issue_from_staleness_finding_for_horizon()` converts `StalenessFinding`:

- `status == "unknown"` → `issue_type="missing_evidence"` (missing/unparseable timestamp)
- `status in ("stale", "near_stale", "expired")` → `issue_type="stale_evidence"`

`finding_id`, `evidence_id`, `field_path`, `object_id` are preserved.

### From CriticResult → HorizonSynthesisIssue

`issue_from_critic_issue_for_horizon()` converts `CriticIssue`:

| CriticIssueType | HorizonSynthesisIssueType |
|-----------------|--------------------------|
| overconfidence | overconfidence |
| missing_risk | missing_risk |
| missing_assumption | missing_assumption |
| conflicting_evidence | conflicting_signal |
| stale_evidence | stale_evidence |
| unsupported_claim | unsupported_claim |
| weak_evidence | missing_evidence |
| validation_failure | validation_issue |
| numeric_claim_issue | unsupported_claim |

`issue_id` is preserved as `related_id`.

---

## How Status / Recommendation Is Derived

### Card Level

The `HorizonSynthesisCard` model_validator runs after construction:

1. Gather all `issues`
2. If any issue has `severity="critical"` → `fail` / `reject`
3. Elif any issue has `severity="warning"` → `pass_with_warnings` / `revise`
4. Elif `evidence_count == 0` → `unknown` / `needs_more_evidence`
5. Else → `pass` / `proceed_to_debate`

### Report Level

The `HorizonSynthesisReport` model_validator runs after construction:

1. Sort cards in canonical order: short_term → medium_term → long_term
2. Gather issues from `self.issues` + all card issues
3. If any critical issue or any card fails → `fail` / `reject`
4. Elif any warning issue or any card has warnings → `pass_with_warnings` / `revise`
5. Elif all cards need more evidence → `unknown` / `needs_more_evidence`
6. Elif all cards pass → `pass` / `proceed_to_debate`
7. Else → `pass_with_warnings` / `revise` (mixed state)

---

## Why Output Is Not Investment Advice

- All thesis summaries use cautious mock language:
  - "Evidence is insufficient for this horizon."
  - "Existing artifacts support a preliminary synthesis only. Requires debate/review before decision."
- No `bullish` or `bearish` signal directions are set by the builder (only `insufficient_evidence`, `mixed`, or `unknown`)
- The schema includes `bullish`/`bearish` for future live agents that may set them based on real data
- `signal_direction` and `confidence` cannot exceed what the evidence supports
- The output explicitly requires a "Debate by Horizon" step before any decision

---

## What This Phase Does NOT Do

| Prohibited | Reason |
|-----------|--------|
| Live LLM calls | Skeleton only; all logic is deterministic |
| Live app integration | No Streamlit, no workflow wiring |
| Streamlit UI | UI changes reserved for future phases |
| Live data fetching | No yfinance, no Polygon, no API calls |
| Broker/order behavior | Not in scope |
| Allocation/Option/Macro/News live agents | Future phases |
| Investment recommendations | Output is for debate/review, not for trading |
| Modification of Phase 0–3A files | Existing tests preserved; only __init__.py extended |

---

## ToolResult Wrapping

`horizon_synthesis_tool_result_from_report()` wraps a `HorizonSynthesisReport` as:

- `tool_name = "horizon_synthesis_report"` (stable)
- `target = report.ticker or "horizon_synthesis"`
- `evidence_id` = deterministic, **content-sensitive** hash derived from the
  full serialized payload (report + summary + calculation_version).
  - Changing report content under the same `synthesis_id` / `as_of` / `target` /
    `calculation_version` **changes** the `evidence_id`.
  - Identical report payload always produces the **same** `evidence_id` (deterministic).
  - Stable serialization is guaranteed by `make_evidence_id` → `stable_hash_payload`
    (JSON `sort_keys=True` + SHA-256).
- `outputs["report"]` = full serialized `HorizonSynthesisReport`
- `outputs["summary"]` = compact `summarize_horizon_synthesis_report()` dict
- `outputs["calculation_version"]` = version tag

---

## Future Relationship

| Future Phase | How Phase 3B Enables It |
|-------------|------------------------|
| Macro Agent v0.1 | MacroSnapshot → ToolResult evidence IDs feed into `HorizonSynthesisInputBundle.tool_results`; long_term domain coverage improves |
| Catalyst Agent | CatalystSnapshot → ToolResults improve short/medium_term coverage |
| News Impact Agent | NewsSnapshot → ToolResults improve short/medium_term coverage |
| Earnings Playbook Agent | EarningsEvent → ToolResults improve medium_term coverage |
| Estimate Revision Agent | EstimateRevision → ToolResults improve medium_term coverage |
| Debate by Horizon | `HorizonSynthesisCard.recommendation == "proceed_to_debate"` gates entry |
| DecisionPacket | HorizonSynthesisReport feeds into a decision packet before investment cockpit |
| Investment Cockpit | Reads HorizonSynthesisReport cards for display |

---

## Test Coverage

`scripts/test_reliability_horizon_synthesis.py` — **67/67 tests pass**

| Group | Tests | Coverage |
|-------|-------|----------|
| Model validation | T01–T12 | accept/reject for all 5 models |
| Helper determinism | T13–T15 | issue_id and synthesis_id stability |
| Evidence extraction | T16–T18 | ToolResult, AgentResult, domain inference |
| Issue conversion | T19–T21 | validation, staleness, critic mapping |
| Card building | T22–T23 | insufficient_evidence, multi-source issues |
| Report building | T24 | canonical card ordering |
| End-to-end synthesis | T25–T27 | 3 cards, fallback, no mutation |
| ToolResult wrapping | T28–T31, T39 | valid, stable, deterministic, content-sensitive |
| Summarization | T32 | all required keys |
| Serialization | T33–T34 | roundtrip correctness |
| Isolation | T35–T37 | no live app/API/LLM imports |
| Regression | T38 | orchestration skeleton 49/49 |

T39 specifically verifies:
- `evidence_id` changes when report content changes under identical identity metadata
- Both ToolResults remain valid
- Both payloads include `report`, `summary`, `calculation_version`
- `evidence_id` remains deterministic for identical payload (T39e)

Full regression (25 scripts + eval harness): all pass.

---

## Disclaimer

All output from Phase 3B is for research and testing purposes only.
It does not constitute investment advice.
All synthesis outputs are mock/dry-run and require human review before any use.
