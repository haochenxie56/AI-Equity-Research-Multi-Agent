# Reliability Phase 4M-G — Agent Evaluation

**Status**: **Accepted** (status reconciled 2026-05-27).
**Module**: `lib/reliability/agent_evaluation.py`
**Tests**: `scripts/test_reliability_agent_evaluation.py`
**Roadmap position**: Roadmap v4 Phase 4 (Memory + Human Feedback mainline).
**Scope**: standalone, deterministic, offline/mock-only schema/helper layer.
**Not in scope**: UI, persistence, database, vector store, live workflow
integration, external API calls, brokerage calls, model retraining, prompt or
agent-definition mutation, broker/order/execution behavior.

> **Note on historical phrasing below**: this document was drafted when
> Phase 4M-G was still awaiting Codex review and Phase 4M Closeout was a
> future deliverable. Phase 4M-G is now accepted. Phase 4M-H Phase 4 Memory
> Closeout has been implemented and is awaiting Codex review
> (see `docs/ai_dev_state/PHASE_4M_CLOSEOUT.md`). The "Future closeout"
> section below is retained as historical roadmap context.

---

## 1. Purpose

Phase 4M-G defines a deterministic evaluation layer that consumes accepted
memory artifacts (Phase 4M-A through 4M-F) and emits an `AgentEvaluationReport`
which classifies, per agent and per signal, whether the agent's output was:

- correct / incorrect / partially_correct / inconclusive
- a false positive / false negative
- an avoided_loss / missed_gain / prevented_bad_action / caused_bad_action
- accepted, rejected, overridden, skipped, or manually executed (from feedback)

It also records:

- per-agent counts
- per-signal-type counts
- per-horizon counts (short / medium / long / multi_horizon / unknown)
- confidence calibration metrics (accuracy, FP rate, FN rate,
  override_rate, calibration_gap)
- lesson extraction (free-text lesson per record)
- linkage to upstream `HumanFeedbackMemoryRecord` IDs

The output is intentionally a **schema/helper layer**: it does not mutate
agents, prompts, model weights, or live workflow behavior. It does not write
to disk and does not connect to any external service. Future closeout phases
(Phase 4M Closeout, Phase 4 Memory Closeout) may consume this report, but
Phase 4M-G itself produces only an in-memory `AgentEvaluationReport` plus a
wrapping `ToolResult` for evidence binding.

---

## 2. Roadmap relationships

### 2.1 Roadmap v4 Phase 4 Agent Evaluation
Roadmap v4 Phase 4 enumerated several Agent Evaluation responsibilities:

- which agent / module was right or wrong → `AgentEvaluationRecord.agent_type` + per-record `signals[*].evaluated_outcome`
- which signal produced false positives / false negatives → `signals[*].evaluated_outcome == "false_positive"|"false_negative"`, `summary.false_positive_count`, `summary.false_negative_count`
- which thesis horizon performed better → `signals[*].horizon` + `summary.horizon_counts`
- which outputs were accepted, rejected, overridden, skipped, or manually executed → consumed from `HumanFeedbackMemoryReport`; surfaced via `signal_type == "human_override"` and `summary.override_count`
- confidence calibration → `AgentEvaluationCalibration` (accuracy_rate, FP/FN rate, calibration_gap)
- lesson extraction for future reliability improvement → `AgentEvaluationRecord.lesson` and `AgentEvaluationLogEntry(event_type="lesson_added")`

### 2.2 Phase 4M-A Research Run Memory
The Research Run Memory record is a duck-typed optional input
(`AgentEvaluationInputBundle.research_run_memory_record`). Its `source_ids`,
`evidence_ids`, and `memory_id`/`report_id` flow into the
`AgentEvaluationReport` via the collection helpers.

### 2.3 Phase 4M-B Thesis Memory
`thesis_memory_report` provides upstream context about thesis direction by
horizon. Its `report_id`, `source_ids`, and `evidence_ids` are dedup-collected.
Per-horizon counts in `summary.horizon_counts` align with the thesis-memory
horizon convention (short / medium / long / multi_horizon / unknown).

### 2.4 Phase 4M-C Catalyst / News / Earnings Memory
`event_memory_report` supplies historic event impact context. Used as a
duck-typed input source for source_ids and evidence_ids; `signal_type`
values `catalyst_call`, `news_impact`, `earnings_view`, `estimate_revision`
align with the event-memory taxonomy.

### 2.5 Phase 4M-D Allocation Decision Memory
`allocation_memory_report` supplies the historical allocation decision
context. `signal_type == "allocation_decision"` evaluates Phase 3R-C
allocation agent outputs against accepted memory and human feedback.

### 2.6 Phase 4M-E Option Trade Plan Memory
`option_trade_memory_report` supplies the historical option trade plan
context. `signal_type == "option_expression"` evaluates Phase 3R-D option
expression agent outputs.

### 2.7 Phase 4M-F Human Feedback Layer
`human_feedback_memory_report` is the **primary** upstream input. Its
`HumanFeedbackMemoryRecord.feedback_memory_id` is referenced from
`AgentEvaluationRecord.human_feedback_memory_id`. Override / acceptance /
rejection / executed_manually decisions from Phase 4M-F flow into the
agent evaluation summary via signal-level outcomes and `signal_type ==
"human_override"`. A **blocked** HumanFeedbackMemoryReport forces the
agent evaluation report status to `blocked`.

### 2.8 Phase 3F Human Review and Phase 3G Review Loop
`review_loop_report` (Phase 3G) is a duck-typed optional upstream input. If
its `status` is `block` or `blocked`, the agent evaluation report status is
forced to `blocked`. Phase 3F human review reports are consumed indirectly
via Phase 4M-F human-feedback memory or via the Phase 3G review loop.

### 2.9 Phase 3 / 3R accepted reliability agents
The `EvaluatedAgentType` literal enumerates all accepted reliability agents
whose outputs may be evaluated:

- `macro_agent` (Phase 3C)
- `horizon_synthesis` (Phase 3B)
- `debate_agent` (Phase 3D)
- `decision_packet` (Phase 3E)
- `human_review` (Phase 3F)
- `review_loop` (Phase 3G)
- `event_intelligence` (Phase 3R-A)
- `trade_plan` (Phase 3R-B)
- `allocation_agent` (Phase 3R-C)
- `option_expression` (Phase 3R-D)
- plus the Phase 4M memory layers:
  - `research_memory` (Phase 4M-A)
  - `thesis_memory` (Phase 4M-B)
  - `event_memory` (Phase 4M-C)
  - `allocation_memory` (Phase 4M-D)
  - `option_trade_memory` (Phase 4M-E)
  - `human_feedback` (Phase 4M-F)
- plus `integration_boundary` (Phase 4A early infrastructure)
- and a fallback `unknown`

### 2.10 Phase 4A Reliability Integration Boundary
Phase 4M-G is **not** wired into the Phase 4A integration boundary. Phase 4A
remains a frozen, accepted, standalone piece of early infrastructure. The
agent evaluation layer is consumed only when a caller explicitly assembles
an `AgentEvaluationInputBundle` and invokes `build_agent_evaluation_report`.

---

## 3. Evaluation schema

### 3.1 Literal type aliases (8)

| Alias | Domain |
|-------|--------|
| `AgentEvaluationStatus` | unknown, evaluated, needs_review, incomplete, archived, blocked |
| `EvaluatedAgentType` | per §2.9 enumeration above |
| `AgentEvaluationOutcome` | unknown, correct, incorrect, partially_correct, inconclusive, false_positive, false_negative, avoided_loss, missed_gain, prevented_bad_action, caused_bad_action |
| `AgentEvaluationSignalType` | thesis_direction, confidence, risk_warning, catalyst_call, news_impact, earnings_view, estimate_revision, trade_plan, allocation_decision, option_expression, no_trade_call, review_trigger, human_override, unknown |
| `AgentEvaluationHorizon` | short, medium, long, multi_horizon, unknown |
| `AgentEvaluationGrade` | excellent, good, mixed, poor, unknown |
| `AgentEvaluationEventType` | evaluation_recorded, outcome_updated, lesson_added, calibration_updated, human_feedback_linked, archived, unknown |
| `AgentEvaluationActor` | system, user, reviewer, agent, unknown |

### 3.2 Pydantic models (9)

All models use `ConfigDict(extra="forbid")` so unknown fields cause
construction failure. None of the models accepts `account_id`, `order_id`,
`execution_id`, `brokerage_id`, or any other broker/order/account/execution
field.

- `AgentEvaluationSourceRef` — pointer to upstream evidence/memory/artifact.
- `AgentEvaluationTargetRef` — pointer to the agent output being evaluated
  (`artifact_id` required, `agent_type` constrained to `EvaluatedAgentType`).
- `AgentEvaluationSignal` — one evaluated signal/claim. Enforces
  `0.0 <= original_confidence <= 1.0` when present; rejects
  `approved_for_execution=True`.
- `AgentEvaluationCalibration` — calibration metrics. Enforces non-negative
  counts (including `rejection_count`) and `0 <= rate <= 1` for the six
  rate fields (`acceptance_rate`, `override_rate`, `rejection_rate`,
  `accuracy_rate`, `false_positive_rate`, `false_negative_rate`).
  `calibration_gap` is signed and constrained to `[-1, 1]` (see §5.3).
- `AgentEvaluationLogEntry` — append-only event log entry.
- `AgentEvaluationRecord` — full evaluation record; rejects empty `signals`;
  rejects `approved_for_execution=True`.
- `AgentEvaluationInputBundle` — duck-typed input wrapper for upstream memory
  artifacts plus pre-populated source/evidence/artifact reference lists.
- `AgentEvaluationSummary` — aggregated counts; rejects negative count
  fields (`record_count`, `signal_count`, `correct_count`, `incorrect_count`,
  `partial_count`, `inconclusive_count`, `false_positive_count`,
  `false_negative_count`, `override_count`, `rejection_count`,
  `review_required_count`); bounds `rejection_rate` to `[0, 1]` when
  present; rejects `approved_for_execution=True`.
- `AgentEvaluationReport` — final report; rejects `approved_for_execution=True`.

---

## 4. Signal evaluation model

One `AgentEvaluationSignal` represents a single agent claim:

- `signal_type` identifies the kind of claim (thesis direction, confidence,
  catalyst call, etc.).
- `original_claim` / `original_direction` / `original_confidence` capture
  what the agent originally said (free-text or numeric).
- `evaluated_outcome` is the resolved evaluation (correct, false_positive,
  caused_bad_action, etc.).
- `evaluation_grade` is the qualitative score (excellent, good, mixed,
  poor, unknown).
- `rationale` is a required short explanation of why the outcome was
  assigned.

The `_derive_overall_outcome()` and `_derive_overall_grade()` helpers
collapse a list of signals into the record-level outcome/grade with
documented precedence:

- If a record has both "correct-leaning" and "incorrect-leaning" signals,
  `overall_outcome = "partially_correct"`.
- If any grade is `poor` and any is `excellent`/`good`,
  `overall_grade = "mixed"`.
- Otherwise, the highest-priority signal outcome/grade wins.

Explicit `overall_outcome` / `overall_grade` arguments to
`build_agent_evaluation_record` override the derivation.

---

## 5. Calibration model

### 5.1 Counts
- `sample_count`, `correct_count`, `incorrect_count`, `partial_count`,
  `inconclusive_count`, `false_positive_count`, `false_negative_count`,
  `override_count`, `rejection_count`. All non-negative
  (validator-enforced).

### 5.2 Rates
- `accuracy_rate = correct_count / sample_count`
- `false_positive_rate = false_positive_count / sample_count`
- `false_negative_rate = false_negative_count / sample_count`
- `override_rate = override_count / sample_count`
- `rejection_rate = rejection_count / sample_count`
- `acceptance_rate` is supplied by the caller (Phase 4M-F memory aggregates
  the acceptance count; this layer does not recompute it).
- All rates are `None` when `sample_count == 0`. All rates that are present
  are validator-bounded to `[0, 1]`.

### 5.3 calibration_gap convention
`calibration_gap = accuracy_rate - average_confidence`.

- **Signed**: range `[-1, 1]`.
- Positive gap means the agent was more accurate than confident
  (under-confident).
- Negative gap means the agent was less accurate than confident
  (over-confident).
- `None` when either `accuracy_rate` or `average_confidence` is `None`.

This sign convention is the chosen behavior of Phase 4M-G; the validator
enforces `-1 <= calibration_gap <= 1`.

---

## 6. False positive / false negative tracking

False positives and false negatives are surfaced both:

- At the **signal level**, via `AgentEvaluationSignal.evaluated_outcome`
  taking the value `false_positive` or `false_negative`.
- At the **calibration level**, via
  `AgentEvaluationCalibration.false_positive_count`,
  `.false_negative_count`, `.false_positive_rate`, `.false_negative_rate`.
- At the **report level**, via `AgentEvaluationSummary.false_positive_count`
  and `.false_negative_count`, computed by `summarize_agent_evaluation`.

This gives consumers three views: per signal, per agent calibration, and
per report.

---

## 7. Override / acceptance / rejection analysis

Phase 4M-G surfaces acceptance, override, and rejection as three distinct,
deterministically-counted views into agent outcomes.

### 7.1 Override

Override information enters Phase 4M-G in three ways:

1. From Phase 4M-F human-feedback signals: callers pass
   `human_feedback_memory_id` on the record and may construct signals with
   `signal_type == "human_override"` to count manual overrides.
2. From per-record calibration: `calibration.override_count` is summed into
   `summary.override_count`.
3. From the input bundle: a blocked `human_feedback_memory_report`
   forces the entire report status to `blocked`.

### 7.2 Acceptance

`acceptance_rate` is **caller-supplied** on `AgentEvaluationCalibration`
because the acceptance count is already computed by Phase 4M-F memory;
this avoids re-deriving the same metric in two places. The validator
constrains it to `[0, 1]` when present.

### 7.3 Rejection (Phase 4M-G fix)

Rejection is tracked deterministically as a **first-class** field, so
Roadmap v4's acceptance/rejection/override expectation is fully covered:

- `AgentEvaluationCalibration.rejection_count` (caller-supplied,
  non-negative; mirrors how `override_count` and `acceptance_rate` enter the
  layer). The corresponding `rejection_rate = rejection_count /
  sample_count` is auto-derived (validator-bounded to `[0, 1]`, `None` when
  `sample_count == 0`).
- `AgentEvaluationSummary.rejection_count` aggregates
  `record.calibration.rejection_count` across all records, alongside
  `override_count`. `AgentEvaluationSummary.rejection_rate` divides by the
  summary `signal_count` (clamped to `[0, 1]`, `None` when no signals).
- `ToolResult.outputs` surfaces both `rejection_count` and `rejection_rate`,
  and the description string includes a `rejection=...` token.

Rejection counts are never fabricated by this layer. They are passed in by
the caller (typically derived from Phase 4M-F human-feedback memory
records). If no caller supplies them, the rejection fields remain at their
deterministic defaults (`0` and `None`).

`AgentEvaluationSummary.review_required_count` separately tracks records
where the evaluator (or upstream review loop) flagged `review_required`.

---

## 8. Horizon-level evaluation

`AgentEvaluationSummary.horizon_counts` is keyed by the
`AgentEvaluationHorizon` literal (`short`, `medium`, `long`,
`multi_horizon`, `unknown`). The aggregation increments per signal, so a
record with multiple signals at different horizons contributes to multiple
keys. This supports the Roadmap v4 question "which thesis horizon performed
better" without prescribing a comparison metric.

---

## 9. Agent-level evaluation

`AgentEvaluationSummary.agent_counts` is keyed by the
`EvaluatedAgentType` literal. The aggregation increments per record (each
record evaluates one agent's output). This supports the Roadmap v4 question
"which agent / module was right or wrong".

---

## 10. Event log design

Each `AgentEvaluationRecord` carries an immutable `event_log:
list[AgentEvaluationLogEntry]`. Event IDs are derived from
`(evaluation_id, event_type, created_at)`, so two records with materially
distinct evaluation IDs always have distinct event-log IDs, and identical
records produce identical event-log IDs. The builder emits:

- `evaluation_recorded` always (one entry per record).
- `calibration_updated` when `calibration` is provided.
- `human_feedback_linked` when `human_feedback_memory_id` is provided.
- `lesson_added` when `lesson` is provided.
- `outcome_updated` when the derived overall outcome is not `unknown`.

---

## 11. Status logic

Both `_derive_record_status` (record-level) and
`determine_agent_evaluation_status` (report-level) follow a single, fixed
precedence:

```
blocked > needs_review > incomplete > evaluated > archived > unknown
```

This precedence is non-negotiable. Stronger labels always outrank weaker
labels regardless of any caller-supplied hint.

### 11.1 Record-level derivation

Evaluated in this exact order:

1. **Blocked.** `hfm_blocked=True` forces `blocked`. An explicit
   `initial_status == "blocked"` also forces `blocked`.
2. **Needs review.** `review_required=True` forces `needs_review`. An
   explicit `initial_status == "needs_review"` also forces `needs_review`
   (unless rule 1 already fired).
3. **Incomplete.** `missing_important_upstream=True` forces `incomplete`.
   An explicit `initial_status == "incomplete"` also forces `incomplete`
   (unless a stronger rule already fired). When all signal outcomes are
   `unknown`, the record is also `incomplete`.
4. **Safe `initial_status` fallback.** Only if none of the above triggered:
   if the caller supplied `initial_status in {"evaluated", "archived",
   "unknown"}`, that label is applied.
5. **Default.** Otherwise the record is `evaluated`.

Crucially, `initial_status` is **not** a free override. A caller passing
`initial_status="evaluated"` together with `hfm_blocked=True` still
yields `blocked`. A caller passing `initial_status="archived"` together
with `review_required=True` still yields `needs_review`. The
`missing_important_upstream` signal can produce either `incomplete` or a
stronger label depending on which conditions fire above it.

### 11.2 Report-level derivation

- A blocked `human_feedback_memory_report` or `review_loop_report` (status
  `blocked` or `block`) forces the report to `blocked`.
- Empty records → `unknown`.
- Any record `blocked` → `blocked`.
- Any record `needs_review` → `needs_review`.
- Any record `incomplete` → `incomplete`.
- All non-terminal records `evaluated` → `evaluated`.
- All records `archived` → `archived`.

---

## 12. ToolResult adapter

`agent_evaluation_tool_result_from_report(report, run_id=None)` returns a
`ToolResult` with:

- `tool_name = "agent_evaluation_report"`
- `run_id = run_id or report.run_id or report.target`
- `ticker = report.target` (Phase 4M-G uses `target` as the canonical
  evaluation subject; tickers are one such subject)
- `evidence_id` is a deterministic hash of the outputs (so it is stable for
  identical reports and changes whenever the report content changes)
- `outputs` includes the full `report` dump, `summary` dump,
  `calculation_version`, and the key signal/outcome counts
- `approved_for_execution = False`

The adapter does not imply persistence, write success, model retraining,
prompt mutation, or any live agent update.

---

## 13. Safety guardrails

- **No persistence / no DB / no vector store** in this phase. The schema
  and helpers are pure functions on Pydantic models plus the deterministic
  `stable_hash_payload` and `make_evidence_id` utilities from
  `lib.reliability.adapters`.
- **No live workflow integration.** The module is not imported by
  `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any live runtime
  file. The Phase 4A integration boundary is left untouched.
- **No model retraining / no prompt mutation / no agent definition
  mutation.** The module reads upstream artifacts duck-typed and emits new
  schema objects.
- **Offline / mock-only.** No network calls. No imports of yfinance,
  Finnhub, Polygon, brokerage SDKs, live option chains, news APIs, or
  Anthropic/OpenAI client libraries. The test suite asserts the absence of
  these imports.
- **No execution authorization.** All four execution-relevant models
  (`AgentEvaluationSignal`, `AgentEvaluationRecord`,
  `AgentEvaluationSummary`, `AgentEvaluationReport`) enforce
  `approved_for_execution = False` via a `model_validator`; constructing
  any of them with `approved_for_execution=True` raises `ValueError` with
  the keyword `approved_for_execution` in the message.
- **No broker / order / account / execution fields.** The Pydantic
  `extra="forbid"` config plus the absence of these field names ensures
  callers cannot smuggle order data through this layer.

---

## 14. Determinism

All builders use `_DETERMINISTIC_TIMESTAMP_DEFAULT = "1970-01-01T00:00:00Z"`
when no explicit timestamp is provided. Callers may supply explicit
timestamps via `recorded_at`, `created_at`, `updated_at`, `as_of`, or
`reviewed_at`, and the explicit values take precedence. `as_of` from the
`AgentEvaluationInputBundle` is preferred over the constant default when
no other timestamp is supplied. All IDs are content-sensitive hashes
computed with `stable_hash_payload` (12 hex chars), so identical inputs
produce identical IDs and materially distinct inputs produce distinct IDs.

Inputs (the `AgentEvaluationInputBundle` and the input record lists) are
not mutated by any helper. Source-ref/evidence-id/artifact-ref dedup is
first-occurrence-wins.

---

## 15. Closeout (historical context)

> Status reconciled 2026-05-27: Phase 4M-H Phase 4 Memory Closeout has been
> implemented and is awaiting Codex review. See
> `docs/ai_dev_state/PHASE_4M_CLOSEOUT.md` for the closeout document, full
> Phase 4M regression sweep, and conservative next-phase recommendation. The
> closeout introduces no persistence, DB, vector store, broker, or external
> API behavior; it is a documentation + regression-sweep phase.

- **Phase 4M-H Phase 4 Memory Closeout**: Implemented — awaiting Codex review.
  Reconciles roadmap, confirms acceptance status of 4M-A through 4M-G,
  captures the list of accepted artifacts and tests.

Neither this acceptance nor any future closeout introduces persistence, DB,
vector store, broker, or external API behavior; both remain documentation +
regression-sweep phases.
