# Reliability Phase 2J — Critic Agent v0.1

**Status**: Implemented  
**File**: `lib/reliability/critic.py`  
**Tests**: `scripts/test_reliability_critic.py`  
**Phase**: 2J (follows Phase 2I Staleness Checker)

---

## Purpose

Phase 2J introduces a standalone **Critic Agent v0.1 foundation** — a deterministic,
schema-only layer that can structurally inspect constrained `AgentResult` outputs and
consume `ValidationAggregate` and `StalenessReport` summaries to produce structured
`CriticResult` objects.

The critic is **not** a live LLM call, a Streamlit widget, or an investment recommendation
engine. It is a deterministic auditing layer that flags potential problems with agent
outputs for downstream review.

---

## Why Mock / Schema-Only First

Following the same "no live app integration, no LLM calls" principle as all earlier phases
(0 through 2I), Phase 2J:

- Creates the schemas and type contracts the critic will use.
- Creates deterministic helper functions that can be called programmatically.
- Creates a mock critic entry point (`run_mock_critic`) that exercises the full critique
  pipeline without any network activity or LLM inference.
- Wraps critic output as a `ToolResult` for full auditability.

This ensures the critic layer can be reviewed, tested, and validated before any live
integration is attempted.

---

## Difference Between Deterministic Critic Helpers and Future LLM Critic Agent

| Aspect | Deterministic Helpers (Phase 2J) | Future LLM Critic Agent |
|--------|----------------------------------|-------------------------|
| Source of critique | Structural inspection of schemas | LLM reasoning over full context |
| Outputs | `CriticResult` with typed issues | Same schema (`CriticResult`) |
| Evidence | Based on existing `ValidationAggregate` / `StalenessReport` | May additionally inspect raw `Finding` text |
| Reliability | Fully deterministic | Stochastic; requires output validation |
| API calls | None | Claude API (future) |
| App integration | None | Future orchestration layer |

The same `CriticIssue` and `CriticResult` schemas serve both layers. The deterministic
helpers in Phase 2J are a concrete, testable foundation; the LLM Critic Agent in a
future phase will emit the same structured output but with richer natural-language
analysis.

---

## Inputs

The critic helpers accept three categories of input:

### 1. AgentResult

`AgentResult` (from `lib/reliability/schemas.py`) is the constrained JSON output of an
LLM agent. The critic structurally inspects:

- Whether findings are present.
- Whether each finding has evidence references.
- Whether risks and assumptions are declared.
- Whether high confidence is consistent with the available evidence density.
- Whether findings contain numeric-looking claims without evidence references.
- Whether duplicate finding messages are present.

### 2. ValidationAggregate

`ValidationAggregate` (from `lib/reliability/validation_aggregator.py`) is the output
of Phase 2H's validation aggregation layer. Each `AggregatedValidationItem` is converted
into a `CriticIssue` via `critic_issue_from_validation_item()`.

### 3. StalenessReport

`StalenessReport` (from `lib/reliability/staleness.py`) is the output of Phase 2I's
staleness checker. Each `StalenessFinding` is converted into a `CriticIssue` via
`critic_issue_from_staleness_finding()`.

---

## Outputs

### CriticIssue

One structured problem raised by the critic. Key fields:

| Field | Description |
|-------|-------------|
| `issue_id` | Deterministic, stable ID (hash of issue_type + message + target/evidence/field) |
| `issue_type` | Classification: `unsupported_claim`, `weak_evidence`, `stale_evidence`, `validation_failure`, `missing_risk`, `missing_assumption`, `overconfidence`, `conflicting_evidence`, `numeric_claim_issue`, `scope_violation`, `safety_concern`, `other` |
| `severity` | `critical`, `warning`, or `info` |
| `target_type` | Type of object being critiqued: `agent_result`, `finding`, `validation_aggregate`, `staleness_report`, etc. |
| `message` | Human-readable description |
| `evidence_id` | Optional link to a `ToolResult` |
| `field_path` | Optional dot-notation path (e.g. `findings.0.evidence`) |
| `related_validation_item_id` | Link to `AggregatedValidationItem.item_id` if applicable |
| `related_staleness_finding_id` | Link to `StalenessFinding.finding_id` if applicable |
| `recommendation` | `accept`, `revise`, `reject`, `needs_more_evidence` |

### CriticResult

Aggregated result from one critic run. Key fields:

| Field | Description |
|-------|-------------|
| `critic_id` | Non-empty unique run identifier |
| `schema_version` | `"1.0"` |
| `as_of` | Reference date/datetime |
| `status` | Auto-normalised: `fail` / `pass_with_warnings` / `pass` |
| `recommendation` | Auto-normalised: `reject` / `revise` / `accept` |
| `issues` | De-duplicated list of `CriticIssue` objects |
| `critical_count` / `warning_count` / `info_count` | Auto-recomputed |

**Normalisation**: The `CriticResult` model_validator automatically de-duplicates issues
by `issue_id` (first-occurrence wins), recomputes counts, and derives `status` and
`recommendation` from the issues list. Caller-supplied values for these derived fields
are overwritten.

### ToolResult Wrapper

`critic_result_tool_result_from_result()` wraps a `CriticResult` as a `ToolResult` for
storage in the `EvidenceStore`. The `evidence_id` is deterministic for the same
`run_id` + critic payload, making critic runs fully auditable.

---

## How Validation Issues Become Critic Issues

`critique_validation_aggregate(va)` iterates `va.items` and calls
`critic_issue_from_validation_item()` on each.

Mapping:

| ValidationItemType | CriticIssueType |
|--------------------|-----------------|
| `stale_data` | `stale_evidence` |
| `evidence_binding` | `weak_evidence` |
| `missing_data` | `weak_evidence` |
| `provenance` | `weak_evidence` |
| `unsupported` | `unsupported_claim` |
| `mismatch` | `conflicting_evidence` |
| `safety` | `safety_concern` |
| `risk_limit` | `validation_failure` |
| `schema` | `validation_failure` |
| `calculation` | `validation_failure` |
| `duplicate_data` | `other` |
| `other` | `validation_failure` |

Severity is preserved from `AggregatedValidationItem.severity`. The
`related_validation_item_id`, `evidence_id`, `field_path`, and `object_id` (as
`target_id`) are all carried through.

---

## How Staleness Issues Become Critic Issues

`critique_staleness_report(sr)` iterates `sr.findings` and calls
`critic_issue_from_staleness_finding()` on each.

Mapping:

| StalenessStatus | CriticIssueType |
|-----------------|-----------------|
| `expired` | `stale_evidence` |
| `stale` | `stale_evidence` |
| `near_stale` | `stale_evidence` (severity bumped to at least `warning`) |
| `unknown` | `weak_evidence` |
| `fresh` | `other` (info — rare; staleness checks rarely emit fresh findings) |

Severity is preserved from `StalenessFinding.severity`, except that `near_stale`
findings with severity `"info"` are bumped to `"warning"` in the critic context, since
near-stale data is worth surfacing even when the staleness policy classifies it as
informational.

The `related_staleness_finding_id`, `evidence_id`, `field_path`, and `object_id` (as
`target_id`) are all carried through.

---

## How Overconfidence Detection Works

`detect_overconfidence(agent_result, validation_aggregate, staleness_report)` checks
whether the agent's declared confidence level is inconsistent with the quality of its
evidence.

Rules:

1. **No confidence declared** → returns `[]`.
2. **Non-high confidence** (e.g. `"medium"`, `"low"`) → returns `[]`.
3. **High confidence + validation aggregate `"fail"`** → `critical` overconfidence issue.
4. **High confidence + validation aggregate `"pass_with_warnings"`** → `warning`
   overconfidence issue.
5. **High confidence + staleness report status `"stale"` / `"expired"` / `"near_stale"`**:
   - If `staleness_report.critical_count > 0` → `critical` overconfidence issue.
   - Otherwise → `warning` overconfidence issue.

The critic does not invent data. It only compares the declared confidence against
summary-level quality signals already computed by Phase 2H (validation) and Phase 2I
(staleness).

---

## Mock Critic Entry Point

`run_mock_critic(critic_id, as_of, agent_result, validation_aggregate, staleness_report)`
is the main integration point for tests and future orchestration. It:

1. Calls `critique_agent_result_structure` if `agent_result` is provided.
2. Calls `critique_validation_aggregate` if `validation_aggregate` is provided.
3. Calls `critique_staleness_report` if `staleness_report` is provided.
4. Calls `detect_overconfidence` if `agent_result` is provided.
5. Aggregates all issues via `aggregate_critic_issues`.
6. Returns a `CriticResult`.

The result is fully deterministic: same inputs always produce the same issue IDs and
the same status.

---

## What This Phase Does NOT Do

- **No Claude API calls.** The critic is entirely code-driven.
- **No external LLM inference.** No prompt engineering or model invocations.
- **No live app integration.** `app.py` and all Streamlit pages are untouched.
- **No investment recommendations.** The critic flags structural and quality issues; it
  does not generate buy/sell/hold signals.
- **No Debate Agent.** The debate layer (future) will build on top of `CriticResult`;
  it is not part of Phase 2J.
- **No Memory Layer.** Critic results are not persisted to a long-term memory store.
- **No UI.** No Streamlit or other frontend rendering.
- **No data fetching.** The critic consumes already-computed summaries.
- **No blocking runtime behavior.** The critic is a pure function; it does not block
  the live workflow.

---

## Guardrails

- **The critic flags risks; it does not fabricate data.** Every `CriticIssue` references
  existing evidence summaries or structural inspection results.
- **The critic consumes evidence summaries, not raw unsupported assumptions.** The critic
  reads `ValidationAggregate`, `StalenessReport`, and structural `AgentResult` fields.
  It does not make up evidence IDs or claim to have computed financial metrics.
- **The critic does not replace validators.** `validate_agent_result()` (Phase 0) remains
  the primary validation gate. The critic is a higher-level audit layer that consumes
  validator output.
- **The critic does not refresh stale data.** If data is stale, the critic flags it. It
  does not attempt to re-fetch data to resolve the staleness.

---

## Future Relationship

| Future Phase / Component | Relationship to Phase 2J |
|--------------------------|--------------------------|
| **Phase 3 Validated Agents** | Validated agents will emit `AgentResult` objects; `run_mock_critic` or an LLM Critic Agent will audit them before synthesis. |
| **Debate Layer** | The Debate Layer will pit one `CriticResult` against another, challenging and defending agent claims. `CriticIssue` is the unit of debate. |
| **Investment Cockpit** | The cockpit will surface `CriticResult` status and top issues alongside agent output for human review. |
| **Human Feedback / Review** | Operators reviewing `CriticResult` will confirm or dismiss issues, feeding back into future critic tuning. |
| **Memory Layer** | Accepted/dismissed critic issues can be stored in memory to inform future runs for the same ticker or sector. |
| **LLM Critic Agent** | A future phase will invoke Claude to produce `CriticIssue` objects backed by richer analysis. The same `CriticResult` schema will be used. |

---

## Key Symbols

```python
from lib.reliability.critic import (
    # Literal type aliases
    CriticIssueType, CriticSeverity, CriticStatus,
    CriticTargetType, CriticRecommendation,
    # Models
    CriticIssue, CriticResult,
    # Helpers
    make_critic_issue_id,
    critic_issue_from_validation_item,
    critic_issue_from_staleness_finding,
    critique_validation_aggregate,
    critique_staleness_report,
    critique_agent_result_structure,
    detect_overconfidence,
    aggregate_critic_issues,
    run_mock_critic,
    critic_result_tool_result_from_result,
    summarize_critic_result,
)
```

All symbols are also re-exported from `lib.reliability` (`__init__.py`).

---

## Test Coverage

`scripts/test_reliability_critic.py` — 53 assertions across 15 test categories:

1. `CriticIssue` schema validation (valid, empty id, empty message)
2. `CriticResult` schema and normalisation (empty→pass/accept, reject bad ids, counts)
3. `make_critic_issue_id` determinism and prefix
4. `critic_issue_from_validation_item` (critical mapping, stale_data→stale_evidence, preservation)
5. `critic_issue_from_staleness_finding` (stale/expired mapping, field preservation)
6. `critique_validation_aggregate` (converts all items, no mutation)
7. `critique_staleness_report` (converts all findings, no mutation)
8. `critique_agent_result_structure` (no findings, no evidence, missing risks/assumptions, numeric)
9. `detect_overconfidence` (high+warnings, high+fail→critical, high+stale, no conf→empty)
10. `aggregate_critic_issues` (dedup, counts/status/recommendation)
11. `run_mock_critic` (all three sources, determinism)
12. `critic_result_tool_result_from_result` (ToolResult, stable tool_name, payload, evidence_id)
13. `summarize_critic_result` (summary keys, top_messages cap)
14. Serialisation roundtrip (CriticResult, CriticIssue, JSON)
15. Isolation (no live app, no network, no LLM, regression check on validate_agent_result)

Run with:

```bash
python3 scripts/test_reliability_critic.py
```
