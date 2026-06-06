# Phase 3E: DecisionPacket Schema / Decision Synthesis Skeleton

**Status**: Implemented — Awaiting Codex Review  
**Date**: 2026-05-23  
**File**: `lib/reliability/decision_packet.py`  
**Tests**: `scripts/test_reliability_decision_packet.py` (58 assertions)

---

## Purpose

Phase 3E creates a standalone, deterministic DecisionPacket synthesis layer.

It consumes research artifacts produced by Phases 3A–3D (and the Phase 0–2K
reliability foundation) and produces a structured `DecisionPacket` draft
suitable for human review.

**This phase does NOT produce investment advice.**
All DecisionPacket outputs are research and review artifacts only.
No trading, order placement, or buy/sell execution is authorized or implied.

---

## Why DecisionPacket Is a Research/Review Artifact

A `DecisionPacket` is:

- A structured, auditable summary of all available research signals for one ticker.
- A container for rationales, guardrails, review requirements, and action drafts.
- A snapshot of deterministic synthesis — not a live recommendation.
- A document that must undergo human review before any execution-related use.

A `DecisionPacket` is NOT:

- An investment recommendation.
- A buy, sell, or hold signal.
- An order or trading instruction.
- The output of a live LLM agent.
- A guarantee of data accuracy or completeness.

The `execution_forbidden` guardrail is always present and always triggered.
Human review is always required.

---

## Relationships to Prior Phases

| Phase | Artifact | How DecisionPacket Uses It |
|-------|----------|---------------------------|
| Phase 3D | `DebateReport` | Bull/bear/risk rationales; round verdicts; debate issues → packet issues |
| Phase 3B | `HorizonSynthesisReport` | Per-horizon signal/confidence rationales; evidence IDs from `HorizonSynthesisCard.evidence_summary.supporting_evidence_ids` |
| Phase 3C | `MacroAgentResult` | Macro regime / sector bias context; evidence from regime, horizon impact, and sector bias artifacts |
| Phase 3A | `OrchestrationReport` | Source ID tracking |
| Phase 2H | `ValidationAggregate` | Validation issues → packet issues; triggers `validation_failure` guardrail |
| Phase 2I | `StalenessReport` | Staleness findings → packet issues; triggers `stale_data` guardrail |
| Phase 2J | `CriticResult` | Critic issues → packet issues; triggers `critic_blocker` guardrail |
| Phase 2K | `ReliabilityScoreSummary` | Available as bundle input for future integration |
| Phase 0 | `AgentResult`, `ToolResult` | Evidence ID collection; agent rationale; ToolResult wrapper |

---

## DecisionPacketInputBundle

`DecisionPacketInputBundle` aggregates all inputs to the synthesis:

```python
class DecisionPacketInputBundle(BaseModel):
    bundle_id: str                           # Non-empty; uniquely identifies this synthesis run
    as_of: str                               # Snapshot date
    ticker: str | None                       # Optional ticker symbol
    debate_report: Any | None                # Phase 3D DebateReport (duck-typed)
    horizon_synthesis_report: Any | None     # Phase 3B HorizonSynthesisReport (duck-typed)
    macro_agent_result: Any | None           # Phase 3C MacroAgentResult (duck-typed)
    orchestration_report: Any | None         # Phase 3A OrchestrationReport (duck-typed)
    validation_aggregate: ValidationAggregate | None
    staleness_report: StalenessReport | None
    critic_result: CriticResult | None
    reliability_score_summary: ReliabilityScoreSummary | None
    agent_result: AgentResult | None
    tool_results: list[ToolResult]
    metadata: dict[str, Any]
```

All fields are optional except `bundle_id` and `as_of`.
Duck typing is used for Phase 3A–3D artifacts to avoid circular imports.

---

## Evidence Handoff

DecisionPacket synthesis preserves evidence IDs from accepted Phase 3B and Phase 3C
artifact fields:

- Phase 3B horizon evidence is read from
  `HorizonSynthesisCard.evidence_summary.supporting_evidence_ids`.
- Phase 3C macro evidence is read from
  `MacroRegimeAssessment.supporting_evidence_ids`,
  `MacroHorizonImpact.evidence_ids`, and `MacroSectorBias.evidence_ids`.
- Legacy duck-typed fields such as card-level `supporting_evidence_ids`,
  card-level `evidence_ids`, `evidence_summary.evidence_ids`, or
  impact/bias `supporting_evidence_ids` are fallback-only.

When present, these IDs are preserved into decision rationales and the packet's
ToolResult payload. No evidence IDs are fabricated.

---

## DecisionRationale

`DecisionRationale` captures one structured research point:

- `source_type`: where the rationale came from (debate, horizon_synthesis, macro_agent, etc.)
- `horizon`: which investment horizon this rationale addresses
- `summary`: cautious, research-only summary (no investment advice)
- `supporting_points`: evidence-backed supporting observations
- `opposing_points`: counterarguments or risk signals
- `evidence_ids`: IDs of supporting `ToolResult` evidence
- `confidence`: derived from artifact signals (high/medium/low/insufficient_evidence/unknown)

Rationales are built from DebateReport rounds, HorizonSynthesisCards,
MacroAgentResult horizon impacts, and AgentResult findings.
If no artifacts are available, a fallback rationale with `confidence=insufficient_evidence`
is created.

---

## DecisionGuardrail

`DecisionGuardrail` is a named condition that must be evaluated before the packet
can be used downstream:

- `guardrail_type`: one of 11 types (execution_forbidden, stale_data, validation_failure, etc.)
- `triggered`: boolean — whether the condition was triggered
- `severity`: critical / warning / info
- `message`: human-readable description
- `related_issue_ids`: links to `DecisionPacketIssue` IDs

**Always-triggered guardrails**:
- `execution_forbidden`: always present, always triggered, severity=critical
- `human_review_required`: always present, always triggered, severity=critical

**Conditionally triggered guardrails**: validation_failure, stale_data, critic_blocker,
debate_unresolved, missing_risk, missing_assumption, conflicting_evidence,
overconfidence, insufficient_evidence.

---

## DecisionActionDraft

`DecisionActionDraft` is a research/monitoring action suggestion:

- `action_type`: one of `no_action | monitor | needs_more_research | prepare_watchlist | prepare_scenario_plan | human_review_required | reject | unknown`
- `allowed_next_steps`: research, review, and monitoring actions only
- `prohibited_actions`: explicitly includes live trading, order placement, buy/sell execution
- `requires_human_review`: always True

**No live trading action types exist** in `DecisionActionType`.

---

## DecisionReviewRequirement

`DecisionReviewRequirement` documents human review obligations:

- Always includes a baseline requirement: human review before any execution-related use.
- Additional requirements for each triggered guardrail type.
- `required=True` for all requirements.
- `review_status=review_required` until a human explicitly changes it.

---

## DecisionPacket

`DecisionPacket` is the top-level output:

```python
class DecisionPacket(BaseModel):
    decision_packet_id: str          # Deterministic hash
    schema_version: str = "1.0"
    as_of: str
    ticker: str | None
    status: DecisionPacketStatus
    recommendation: DecisionRecommendation
    confidence: DecisionConfidence
    primary_action: DecisionActionDraft | None
    rationales: list[DecisionRationale]
    guardrails: list[DecisionGuardrail]
    review_requirements: list[DecisionReviewRequirement]
    issues: list[DecisionPacketIssue]
    source_ids: dict[str, str]
    metadata: dict[str, Any]
```

---

## Deterministic Status / Recommendation Derivation

Status and recommendation are derived by `_normalize_status_recommendation_confidence()`:

| Condition | Status | Recommendation |
|-----------|--------|----------------|
| Critical guardrail (validation/critic) | `blocked` | `reject` |
| Critical guardrail (other) | `fail` | `reject` |
| No evidence or insufficient_evidence guardrail | `insufficient_evidence` | `needs_more_evidence` |
| Warning guardrails only | `pass_with_warnings` | `revise` |
| No critical/warning guardrails, evidence present | `pass` | `accept_for_research` |

Note: `execution_forbidden` and `human_review_required` guardrails are **excluded**
from this derivation since they are always present. Only domain-specific guardrails
affect status.

Confidence is derived from issue counts:
- No evidence → `insufficient_evidence`
- Any critical issues → `low`
- More than 3 warnings → `low`
- Any warnings → `medium`
- Pass with evidence → `medium`

---

## execution_forbidden Guardrail

The `execution_forbidden` guardrail is:

- **Always present** in every DecisionPacket.
- **Always triggered** (triggered=True).
- **Severity: critical**.
- Message: "This decision packet does not authorize live trading, order placement,
  or any buy/sell execution. It is a research and review artifact only."

This guardrail cannot be suppressed or removed.

---

## Human Review Requirement

Every DecisionPacket includes a baseline `DecisionReviewRequirement`:

> "Human review is always required before any execution-related use of this decision
> packet. It is a research artifact only."

Additional review requirements are added for each triggered guardrail type.
All have `required=True` and `review_status=review_required`.

---

## ToolResult Wrapper Behavior

`decision_packet_tool_result_from_packet()` wraps a `DecisionPacket` into a
`ToolResult` for evidence-chain storage:

- `tool_name = "decision_packet"` (stable, never changes)
- `target` = `packet.ticker` if available, else `"decision_packet"`
- `payload.packet` = full `DecisionPacket.model_dump()`
- `payload.summary` = `summarize_decision_packet(packet)` output
- `payload.calculation_version` = `"decision_packet_skeleton_v1"`
- `evidence_id` = content-sensitive deterministic hash (same packet → same ID)

---

## What This Phase Does NOT Do

- **No live LLM calls**: All synthesis is deterministic and rule-based.
- **No live app integration**: Does not modify `app.py`, `pages/*`, or any live workflow.
- **No Streamlit UI**: No frontend components are added.
- **No live data fetching**: No yfinance, polygon.io, or API calls.
- **No broker/order behavior**: No order management, broker API, or execution logic.
- **No portfolio execution**: No position sizing, allocation, or portfolio management.
- **No investment advice**: All outputs are research artifacts only.
- **No automated recommendations**: Human review is always required.

---

## Future Relationships

Once accepted, this phase provides the foundation for:

| Future Component | Relationship |
|-----------------|--------------|
| **Investment Cockpit** | DecisionPacket will be displayed in a cockpit view for human review. |
| **Human Feedback / Review Layer** | Humans will update `review_status` fields and provide structured feedback. |
| **Memory Layer** | Reviewed packets may be persisted for longitudinal tracking. |
| **Allocation Agent** | Only a reviewed/approved packet may feed into allocation sizing. |
| **Option Expression Agent** | Only a reviewed/approved packet may feed into option strategy selection. |
| **Feature-flagged dry-run integration** | DecisionPacket synthesis may be triggered as a dry-run step in the live app workflow, behind a feature flag, with no execution path. |

None of these integrations are implemented in Phase 3E.

---

## Implemented Enums

| Enum | Values |
|------|--------|
| `DecisionPacketStatus` | pass / pass_with_warnings / fail / insufficient_evidence / blocked / unknown |
| `DecisionActionType` | no_action / monitor / needs_more_research / prepare_watchlist / prepare_scenario_plan / human_review_required / reject / unknown |
| `DecisionConfidence` | high / medium / low / insufficient_evidence / unknown |
| `DecisionGuardrailType` | insufficient_evidence / stale_data / validation_failure / critic_blocker / debate_unresolved / missing_risk / missing_assumption / conflicting_evidence / overconfidence / execution_forbidden / human_review_required / other |
| `DecisionReviewStatus` | not_reviewed / review_required / reviewed / rejected / approved_for_research_only / unknown |
| `DecisionSourceType` | debate / horizon_synthesis / macro_agent / orchestration / validation / staleness / critic / evaluation / agent_result / tool_result / manual / unknown |
| `DecisionHorizon` | short_term / medium_term / long_term / multi_horizon / unknown |
| `DecisionRecommendation` | accept_for_research / revise / reject / needs_more_evidence / monitor_only / unknown |

---

## Disclaimer

All outputs from Phase 3E are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk; invest with caution.
