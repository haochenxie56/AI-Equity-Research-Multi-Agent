# Phase 3F: Human Review / Feedback Schema Skeleton

**Date**: 2026-05-23
**Phase**: 3F — Human Review / Feedback Schema Skeleton
**Status**: Implemented — Awaiting Codex Review
**File**: `lib/reliability/human_review.py`
**Test**: `scripts/test_reliability_human_review.py`

---

## Purpose

Phase 3F introduces a standalone, deterministic, offline human review and
feedback layer. It consumes a `DecisionPacket` and other reliability artifacts
(from Phases 3A–3E) and produces structured review records, feedback items,
revision requests, and review reports for analyst consumption.

This layer is a **dry-run/mock-only schema skeleton**. It structures review
and feedback; it does not make investment decisions, authorize execution, or
call live LLMs or APIs.

---

## Why Human Review Comes After DecisionPacket

The `DecisionPacket` (Phase 3E) is the last deterministic synthesis stage
before human judgment is applied. It aggregates evidence from all reliability
layers (debate, horizon synthesis, macro agent, validation, staleness, critic)
into a structured research artifact. Human review then:

1. Consumes the `DecisionPacket` as its primary input.
2. Converts issues and guardrails into structured `HumanFeedbackItem` records.
3. Groups feedback into `HumanRevisionRequest` objects with actionable change
   lists.
4. Produces `HumanReviewItem` records for each source artifact.
5. Determines a `HumanReviewOutcome` (block / revise / approve-for-research).
6. Assembles a final `HumanReviewReport` with normalized status and
   recommendation.

This positions human review as the last structured gate before any downstream
research use, while keeping the layer completely offline and evidence-aware.

---

## Relationship to Prior Phases

| Source Layer | Phase | Contribution |
|---|---|---|
| DecisionPacket | 3E | Primary input: issues, guardrails converted to feedback |
| Debate by Horizon | 3D | Source artifact reviewed; debate_id in source_ids |
| Horizon-aware Synthesis | 3B | Source artifact reviewed; synthesis_id in source_ids |
| Macro Agent v0.1 | 3C | Source artifact reviewed; macro_agent_id in source_ids |
| ValidationAggregate | 2H | Items converted to `HumanFeedbackItem` via validation mapper |
| StalenessReport | 2I | Findings converted to `HumanFeedbackItem` via staleness mapper |
| CriticResult | 2J | Issues converted to `HumanFeedbackItem` via critic mapper |
| Evaluation Harness | 2K | `ReliabilityScoreSummary` accepted in input bundle |

---

## Input Bundle

`HumanReviewInputBundle` accepts:

- `decision_packet` (duck-typed `Any`) — primary synthesis artifact
- `debate_report` (duck-typed `Any`) — Phase 3D output
- `horizon_synthesis_report` (duck-typed `Any`) — Phase 3B output
- `macro_agent_result` (duck-typed `Any`) — Phase 3C output
- `validation_aggregate: ValidationAggregate | None` — Phase 2H output
- `staleness_report: StalenessReport | None` — Phase 2I output
- `critic_result: CriticResult | None` — Phase 2J output
- `reliability_score_summary: ReliabilityScoreSummary | None` — Phase 2K output
- `manual_feedback: list[HumanFeedbackItem]` — manual analyst input

All nested objects are accepted by reference; the bundle does not mutate them.

---

## Schema Models

### HumanFeedbackItem

One structured feedback item for an analyst. Fields:

- `feedback_id` (non-empty deterministic hash)
- `feedback_type` (evidence_gap / stale_data / unsupported_claim /
  missing_risk / missing_assumption / conflicting_evidence /
  unclear_rationale / excessive_confidence / wording_change /
  scope_violation / safety_concern / other)
- `severity` (critical / warning / info)
- `reviewer_role` (analyst / portfolio_manager / risk_reviewer /
  compliance_reviewer / system_reviewer / unknown)
- `message` (non-empty)
- `source_type` (decision_packet / debate / horizon_synthesis / macro_agent /
  validation / staleness / critic / evaluation / manual / unknown)
- `related_id`, `evidence_id`, `field_path`, `suggested_change` (optional)
- `metadata`

### HumanRevisionRequest

Groups feedback items into actionable revision requirements. Fields:

- `revision_request_id`, `reason` (non-empty)
- `required: bool = True`
- `source_feedback_ids: list[str]` — feedback items driving this request
- `requested_changes: list[str]` — specific change descriptions
- `blocked_until_resolved: bool` — True for critical feedback

### HumanReviewItem

One review item for a specific source artifact. Fields:

- `review_item_id`, `summary` (non-empty)
- `source_type: HumanReviewSourceType`
- `source_id: str | None` — the artifact's ID (e.g., `decision_packet_id`)
- `status: HumanReviewStatus`
- `feedback_items`, `revision_requests` for this source
- `metadata`

### HumanReviewOutcome

Records the reviewer's decision. Fields:

- `outcome_id`, `rationale` (non-empty)
- `decision: HumanReviewDecision`
- `status: HumanReviewStatus`
- `recommendation: HumanReviewRecommendation`
- `reviewer_role: HumanReviewerRole`
- `approved_for_execution: bool = False` — **always False**
- `approved_for_research_only: bool`
- `revision_required: bool`
- `blocked: bool`

### HumanReviewReport

The top-level review artifact. Fields:

- `review_report_id`, `as_of` (non-empty)
- `schema_version: str = "1.0"`
- `ticker: str | None`
- `status: HumanReviewStatus` — auto-normalized
- `recommendation: HumanReviewRecommendation` — auto-normalized
- `review_items`, `feedback_items`, `revision_requests`
- `outcome: HumanReviewOutcome | None`
- `source_ids: dict[str, str]` — maps artifact names to their IDs
- `metadata`

---

## Deterministic Feedback / Revision / Outcome Logic

### Feedback Collection (`collect_human_feedback`)

Deterministic order:
1. `DecisionPacket.issues` (duck-typed) → `feedback_from_decision_packet_issue()`
2. `DecisionPacket.guardrails` (triggered, non-meta) → same converter
3. `ValidationAggregate.items` → `feedback_from_validation_item()`
4. `StalenessReport.findings` (non-fresh) → `feedback_from_staleness_finding()`
5. `CriticResult.issues` → `feedback_from_critic_issue()`
6. `manual_feedback` (pass-through)

De-duplication by `feedback_id` (first occurrence wins). No mutation of inputs.

### Type Mapping

| Source Type | Source Field | Feedback Type |
|---|---|---|
| `insufficient_evidence` guardrail | decision_packet | `evidence_gap` |
| `stale_data` guardrail | decision_packet | `stale_data` |
| `validation_failure` guardrail | decision_packet | `unsupported_claim` |
| `missing_risk` guardrail | decision_packet | `missing_risk` |
| `missing_assumption` guardrail | decision_packet | `missing_assumption` |
| `conflicting_evidence` guardrail | decision_packet | `conflicting_evidence` |
| `overconfidence` guardrail | decision_packet | `excessive_confidence` |
| `safety_concern` guardrail | decision_packet | `safety_concern` |
| `evidence_binding` item | validation | `evidence_gap` |
| `stale_data` item | validation | `stale_data` |
| `safety` item | validation | `safety_concern` |
| `stale` / `expired` finding | staleness | `stale_data` |
| `unknown` timestamp | staleness | `evidence_gap` |
| `missing_risk` issue | critic | `missing_risk` |
| `overconfidence` issue | critic | `excessive_confidence` |
| `stale_evidence` issue | critic | `stale_data` |

### Revision Requests (`build_revision_requests`)

One revision request per `feedback_type` group (critical/warning only).

- Critical feedback → `blocked_until_resolved=True`
- Evidence gaps → "Provide additional supporting evidence..."
- Stale data → "Refresh stale data sources..."
- Unsupported claims → "Bind all numeric claims to ToolResult evidence IDs..."
- Missing risk → "Add missing risks to Key Risks section..."
- Safety concern → "Escalate to compliance review..."

### Outcome Rules (`determine_human_review_outcome`)

| Conditions | Decision | Status | approved_for_research_only |
|---|---|---|---|
| Any critical feedback or blocked revision | `block` | `blocked` | False |
| Warnings only | `request_revision` | `changes_requested` | False |
| Evidence gaps only (info) | `defer` | `pending` | False |
| Clean (no critical/warning) | `approve_for_research` | `approved_for_research_only` | True |

`approved_for_execution` is **always False** under all conditions.

---

## `approved_for_research_only` vs `approved_for_execution`

| Flag | Meaning |
|---|---|
| `approved_for_research_only = True` | The artifact is suitable for research interpretation only |
| `approved_for_research_only = False` | Artifact requires revision or is blocked |
| `approved_for_execution = False` | **Always False** — Phase 3F never authorizes execution |

The `HumanReviewOutcome` Pydantic model enforces `approved_for_execution = False`
via a `model_validator`. Attempting to set it to `True` raises a `ValidationError`.

---

## ToolResult Wrapper

`human_review_tool_result_from_report(run_id, report, target=None,
calculation_version="human_review_skeleton_v1")` wraps the report as a
`ToolResult` for evidence-aware pipelines:

- `tool_name`: `"human_review_report"` (stable)
- `ticker`: from `report.ticker`
- `evidence_id`: deterministic, content-sensitive hash of `outputs`
- `outputs`: `{"report": ..., "summary": ..., "calculation_version": ...}`

`summarize_human_review_report(report)` returns a concise summary dict:
`review_report_id`, `ticker`, `status`, `recommendation`, `feedback_count`,
`revision_request_count`, `review_item_count`, `critical_count`,
`warning_count`, `info_count`, `approved_for_research_only`,
`approved_for_execution` (always False), `top_messages` (≤ 10).

---

## What Phase 3F Does NOT Do

- **No live LLM calls** — all logic is rule-based and deterministic.
- **No live app integration** — does not import `app.py`, `pages/*`, or
  `lib/llm_orchestrator.py`.
- **No Streamlit UI** — this layer has no UI components.
- **No live data fetching** — does not call yfinance, polygon.io, or any
  external API.
- **No broker/order behavior** — no buy/sell/order language.
- **No portfolio execution** — no position changes or trades.
- **No investment advice** — all outputs are research artifacts only.
- **No real approval workflow** — the "approval" is a research-only flag,
  not authorization for any action.

---

## Future Integration Points

Phase 3F is designed as a standalone foundation for future phases:

| Future Phase | Integration |
|---|---|
| Memory / Feedback Store | Persist `HumanFeedbackItem` and `HumanRevisionRequest` records for trend analysis |
| Human Feedback Store | Query historical feedback for similar tickers/regimes |
| Investment Cockpit (Streamlit) | Feature-flagged dry-run review panel consuming `HumanReviewReport` |
| Feature-flagged dry-run integration | Wire `run_human_review_skeleton()` as a post-DecisionPacket step behind a feature flag |
| Eventual review UI | Render `HumanReviewReport` in a Streamlit page with analyst actions |

All future integrations must preserve `approved_for_execution = False` until
a live execution path is explicitly designed, reviewed, and authorized.

---

## Disclaimer

All outputs from this layer are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk; invest with caution.
