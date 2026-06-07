# Phase 3D — Debate by Horizon Skeleton

**Date**: 2026-05-23
**Phase**: 3D
**Status**: Implemented — Awaiting Codex Review
**Disclaimer**: All outputs from this system are for research and educational purposes only. They do not constitute investment advice. Markets involve risk.

---

## Purpose

Phase 3D creates a standalone, deterministic, mock debate layer that consumes horizon-aware synthesis and reliability artifacts, then produces structured **Bull / Bear / Risk debate outputs** for each investment horizon.

This phase establishes the structural foundation for a future live Debate Agent. Before plugging in a live LLM, the debate layer must have well-defined schemas, deterministic verdict logic, and provable evidence binding. Phase 3D delivers all three.

---

## Why Debate is Mock/Deterministic Before Live Agents

A live debate agent would call Claude to produce natural-language bull and bear positions. Before that integration is appropriate:

1. **Schema clarity first**: The DebateIssue / DebateClaim / DebatePosition / DebateRound / DebateReport schemas must be stable so the live agent has a well-typed contract to fill.
2. **Evidence binding validation**: Verdict and status logic must be provably deterministic and testable without LLM non-determinism.
3. **Safe iteration**: A mock skeleton can be reviewed, tested, and accepted before any LLM or network dependency is introduced.
4. **Compliance with project architecture**: The project principle is "Deterministic computation, agentic interpretation, auditable synthesis." Deterministic debate schemas come first.

---

## Relationship to Prior Phases

| Phase | Role in Debate |
|-------|---------------|
| Phase 3B — Horizon-aware Synthesis Skeleton | `HorizonSynthesisReport` provides per-horizon signal direction and evidence summaries used to build bull/bear positions. Debate reads `HorizonSynthesisCard.horizon` (not `card.bucket`) and `HorizonEvidenceSummary.supporting_evidence_ids` (not `evidence_ids`). Backward-compatible fallback to `bucket`/`evidence_ids` is supported but secondary. |
| Phase 3C — Macro Agent v0.1 Skeleton | `MacroAgentResult` provides macro horizon impacts and macro evidence IDs incorporated into bull positions |
| Phase 2H — Validation Aggregator | `ValidationAggregate` items are converted into `DebateIssue` counterarguments for the bear/risk positions |
| Phase 2I — Staleness Checker | `StalenessReport` findings become `stale_evidence` / `missing_evidence` `DebateIssue` objects for the risk position |
| Phase 2J — Critic Agent v0.1 | `CriticResult` issues are mapped to `DebateIssue` types (missing_risk, overconfidence, conflicting_evidence) |
| Phase 2K — Evaluation Harness | `ReliabilityScoreSummary` is carried in `DebateReport` for auditability |
| Phase 3A — Orchestration Skeleton | `OrchestrationReport` can be included in future debate input bundles |

---

## DebateInputBundle

`DebateInputBundle` is the single intake object for the debate layer. It accepts:

| Field | Type | Description |
|-------|------|-------------|
| `bundle_id` | str | Unique non-empty bundle identifier |
| `as_of` | str | Reference datetime (ISO-like) |
| `ticker` | str \| None | Optional equity ticker |
| `horizon_synthesis_report` | Any \| None | Phase 3B HorizonSynthesisReport (duck-typed) |
| `macro_agent_result` | Any \| None | Phase 3C MacroAgentResult (duck-typed) |
| `agent_result` | AgentResult \| None | Constrained agent result (Phase 1D schema) |
| `tool_results` | list[ToolResult] | Deterministic evidence artifacts |
| `validation_aggregate` | ValidationAggregate \| None | Phase 2H aggregate |
| `staleness_report` | StalenessReport \| None | Phase 2I staleness report |
| `critic_result` | CriticResult \| None | Phase 2J critic result |
| `reliability_score_summary` | ReliabilityScoreSummary \| None | Phase 2K eval score |
| `metadata` | dict | Arbitrary metadata |

The bundle does not mutate nested objects.

---

## Schema Models

### DebateIssue

One structured issue raised during a debate round or position review.

| Field | Type | Notes |
|-------|------|-------|
| `issue_id` | str (non-empty) | Deterministic stable hash |
| `issue_type` | DebateIssueType | One of 11 enumerated types |
| `severity` | "critical" \| "warning" \| "info" | Default: "warning" |
| `horizon` | DebateHorizon \| None | Optional horizon association |
| `role` | DebateRole \| None | Optional role association |
| `message` | str (non-empty) | Human-readable description |
| `related_id` | str \| None | object_id / target_id from source |
| `evidence_id` | str \| None | Associated ToolResult evidence_id |
| `field_path` | str \| None | Dot-notation field path |
| `metadata` | dict | Arbitrary metadata |

### DebateClaim

One claim made by a debate participant (bull / bear / risk / neutral).

| Field | Type | Notes |
|-------|------|-------|
| `claim_id` | str (non-empty) | Deterministic stable hash |
| `claim_type` | DebateClaimType | thesis / counterargument / risk / assumption / evidence_gap / unresolved_question / other |
| `role` | DebateRole | bull / bear / risk / neutral / unknown |
| `horizon` | DebateHorizon | short_term / medium_term / long_term |
| `text` | str (non-empty) | Claim text (no buy/sell language) |
| `evidence_ids` | list[str] | Backing evidence IDs |
| `confidence` | str | Confidence label |
| `issues` | list[DebateIssue] | Claim-level issues |
| `metadata` | dict | Arbitrary metadata |

### DebatePosition

Position taken by one debate role for one horizon.

| Field | Type | Notes |
|-------|------|-------|
| `position_id` | str (non-empty) | Deterministic stable hash |
| `role` | DebateRole | bull / bear / risk / neutral |
| `horizon` | DebateHorizon | Investment horizon |
| `summary` | str (non-empty) | Position summary |
| `claims` | list[DebateClaim] | Supporting claims |
| `evidence_ids` | list[str] | Aggregated evidence IDs |
| `issues` | list[DebateIssue] | Position-level issues |
| `confidence` | str | Confidence label |
| `metadata` | dict | Arbitrary metadata |

### DebateRound

One full debate round for a specific investment horizon. Status and verdict are auto-normalised.

| Field | Type | Notes |
|-------|------|-------|
| `round_id` | str (non-empty) | Deterministic stable hash |
| `horizon` | DebateHorizon | Investment horizon |
| `bull_position` | DebatePosition \| None | Bull case |
| `bear_position` | DebatePosition \| None | Bear case |
| `risk_position` | DebatePosition \| None | Risk review |
| `unresolved_questions` | list[str] | Outstanding questions |
| `evidence_gaps` | list[str] | Missing evidence descriptions |
| `issues` | list[DebateIssue] | Round-level debate issues |
| `verdict` | DebateVerdict | Auto-normalised |
| `status` | DebateStatus | Auto-normalised |
| `metadata` | dict | Arbitrary metadata |

### DebateReport

Full structured debate report spanning all three investment horizons.

| Field | Type | Notes |
|-------|------|-------|
| `debate_id` | str (non-empty) | Deterministic stable hash |
| `schema_version` | str | "1.0" |
| `as_of` | str (non-empty) | Reference datetime |
| `ticker` | str \| None | Optional equity ticker |
| `status` | DebateStatus | Auto-normalised from rounds |
| `recommendation` | DebateRecommendation | Auto-normalised from status |
| `rounds` | list[DebateRound] | Exactly 3 rounds |
| `issues` | list[DebateIssue] | Aggregated from rounds (deduped) |
| `horizon_synthesis_report_id` | str \| None | Traceability |
| `macro_agent_result_id` | str \| None | Traceability |
| `validation_aggregate` | ValidationAggregate \| None | Carried for auditability |
| `staleness_report` | StalenessReport \| None | Carried for auditability |
| `critic_result` | CriticResult \| None | Carried for auditability |
| `reliability_score_summary` | ReliabilityScoreSummary \| None | Eval score |
| `metadata` | dict | Arbitrary metadata |

---

## Enumerated Types

### DebateRole
`bull` | `bear` | `risk` | `neutral` | `unknown`

### DebateStatus
`pass` | `pass_with_warnings` | `fail` | `insufficient_evidence` | `unknown`

### DebateVerdict
`bull_favored` | `bear_favored` | `risk_dominant` | `mixed` | `insufficient_evidence` | `no_decision` | `unknown`

### DebateRecommendation
`proceed_to_decision_packet` | `revise` | `reject` | `needs_more_evidence` | `no_action` | `unknown`

### DebateIssueType
`unsupported_claim` | `stale_evidence` | `missing_evidence` | `validation_issue` | `critic_issue` | `conflicting_evidence` | `missing_risk` | `missing_assumption` | `overconfidence` | `horizon_mismatch` | `unresolved_question` | `other`

### DebateClaimType
`thesis` | `counterargument` | `risk` | `assumption` | `evidence_gap` | `unresolved_question` | `other`

### DebateHorizon
`short_term` | `medium_term` | `long_term`

---

## Bull / Bear / Risk Roles

### Bull Position

Built by `build_bull_position()`. Sources:
1. `HorizonSynthesisCard` for the horizon (signal_direction, evidence_ids).
2. `MacroAgentResult.horizon_impacts` for the horizon (checks if impact == "supportive").
3. If no evidence: returns an `evidence_gap` claim — not a bullish assertion.

No buy/sell language. No invented facts.

### Bear Position

Built by `build_bear_position()`. Sources:
1. Validation/staleness/critic issues converted to `DebateIssue` counterarguments.
2. `HorizonSynthesisCard` bearish/mixed signal_direction if available.
3. If no evidence or critique: returns an `evidence_gap` claim.

No invented facts. No buy/sell language.

### Risk Position

Built by `build_risk_position()`. Sources:
1. `stale_evidence` DebateIssues → stale data risk claim.
2. `overconfidence` DebateIssues → overconfidence risk claim.
3. `conflicting_evidence` DebateIssues → conflicting signal risk claim.
4. Other risk-type issues → general risk claim.
5. If no risk issues: states "no blocking issue found in available artifacts."

No trading recommendation. Not investment advice.

---

## Short / Medium / Long Rounds

`run_debate_by_horizon()` always builds exactly three rounds in this order:
1. `short_term`
2. `medium_term`
3. `long_term`

Each round independently extracts horizon-specific evidence IDs first, then general evidence. This ensures that synthesis card evidence is prioritized for the relevant horizon.

---

## Deterministic Verdict Logic

### DebateRound Status
| Condition | Status |
|-----------|--------|
| Any critical issue | `fail` |
| No position holds evidence IDs | `insufficient_evidence` |
| Warning issues or evidence_gaps present | `pass_with_warnings` |
| Otherwise | `pass` |

### DebateRound Verdict
| Condition | Verdict |
|-----------|---------|
| No position holds evidence IDs | `insufficient_evidence` |
| ≥ 50 % of issues are risk-type | `risk_dominant` |
| Bull and bear both have claims AND evidence | `mixed` |
| Otherwise | `no_decision` (conservative default) |

Risk-type issue types counted toward `risk_dominant`: `missing_risk`, `stale_evidence`, `missing_evidence`, `overconfidence`, `conflicting_evidence`, `missing_assumption`.

### DebateReport Status
| Condition | Status | Recommendation |
|-----------|--------|----------------|
| Any round fails or any critical issue | `fail` | `reject` |
| All rounds are insufficient/unknown | `insufficient_evidence` | `needs_more_evidence` |
| Any round has warnings | `pass_with_warnings` | `revise` |
| Otherwise | `pass` | `proceed_to_decision_packet` |

---

## Issue Conversion Mappings

### ValidationItemType → DebateIssueType
| ValidationItemType | DebateIssueType |
|--------------------|-----------------|
| stale_data | stale_evidence |
| missing_data | missing_evidence |
| evidence_binding | unsupported_claim |
| unsupported | unsupported_claim |
| risk_limit | missing_risk |
| safety | critic_issue |
| schema / calculation | validation_issue |
| mismatch | conflicting_evidence |
| provenance | missing_evidence |

### StalenessStatus → DebateIssueType
| StalenessStatus | DebateIssueType |
|-----------------|-----------------|
| stale / expired / near_stale | stale_evidence |
| unknown | missing_evidence |
| fresh | other |

### CriticIssueType → DebateIssueType
| CriticIssueType | DebateIssueType |
|-----------------|-----------------|
| missing_risk | missing_risk |
| missing_assumption | missing_assumption |
| conflicting_evidence | conflicting_evidence |
| stale_evidence | stale_evidence |
| unsupported_claim | unsupported_claim |
| overconfidence | overconfidence |
| weak_evidence | missing_evidence |
| validation_failure | validation_issue |
| numeric_claim_issue | unsupported_claim |
| safety_concern | critic_issue |

---

## ToolResult Wrapper Behavior

`debate_report_tool_result_from_report()` wraps a `DebateReport` into the `ToolResult` schema:
- `tool_name`: always `"debate_report"` (stable).
- `target`: `report.ticker` if set, else `"debate"`.
- `evidence_id`: content-sensitive — derived from hash of the full payload (report dict + summary + calculation_version).
- `outputs`: contains `report`, `summary`, and `calculation_version`.
- `inputs`: contains `debate_id`, `as_of`, `target`, `calculation_version` for traceability.

The `evidence_id` changes when any field in the report changes, making it safe for evidence store deduplication.

---

## Why Output is Not Investment Advice

All outputs from this module:
- Are clearly marked `[MOCK DRY-RUN]` in claim text.
- Carry the disclaimer "Not investment advice" in every claim.
- Use structural data quality signals (staleness, validation failures, critic issues), not price forecasts.
- Never use buy/sell/long/short language.
- Are explicitly for research and educational purposes only.

---

## What This Phase Does NOT Do

- **No live LLM calls**: No Claude API, no OpenAI, no remote inference.
- **No live app integration**: Does not import from `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any live workflow module.
- **No Streamlit UI**: Zero UI changes.
- **No live data fetching**: No yfinance, polygon.io, or any external data source calls.
- **No broker/order behavior**: No position sizing, allocation decisions, or order generation.
- **No final decision engine**: The `proceed_to_decision_packet` recommendation is a schema label only; no DecisionPacket is implemented in this phase.
- **No Memory Layer**: No persistent agent memory or cross-session state.
- **No Allocation Agent**: Out of scope.
- **No Option Agent**: Out of scope.
- **No live Macro/News/Catalyst/Earnings agents**: Mock/skeleton only.

---

## Future Relationship

| Future Component | How Phase 3D Connects |
|-----------------|----------------------|
| **DecisionPacket** | `DebateReport.recommendation == "proceed_to_decision_packet"` is the signal that triggers DecisionPacket construction in a future phase |
| **Investment Cockpit** | DebateReport and per-horizon verdicts will be displayed in the Cockpit UI once connected |
| **Human Feedback / Review** | Debate round verdicts are the structured artifact a human reviewer approves or overrides before any action |
| **Memory Layer** | Debate outcomes (verdicts, unresolved questions) may be stored in the Memory Layer for cross-session persistence |
| **Live Debate Agent** | A future phase will replace `run_debate_by_horizon()` with a live Claude-powered Debate Agent that fills the same schemas deterministically defined here |

---

## Key Files

| File | Description |
|------|-------------|
| `lib/reliability/debate.py` | Phase 3D: 7 enums, 6 Pydantic models, 13 helpers |
| `scripts/test_reliability_debate.py` | Phase 3D: 45 assertions |
| `docs/reliability_phase_3d_debate_by_horizon_skeleton.md` | This document |
| `lib/reliability/__init__.py` | Updated with Phase 3D exports |
