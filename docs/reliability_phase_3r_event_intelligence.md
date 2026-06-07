# Phase 3R-A: Event Intelligence Agents Skeleton

**Date**: 2026-05-24 (polish: 2026-05-24)
**Status**: Implemented — awaiting Codex review (polish applied)
**Phase**: 3R-A (Roadmap v4 Phase 3 Backfill)
**File**: `lib/reliability/event_intelligence.py`

---

## 1. Purpose

Phase 3R-A delivers offline / mock-only skeleton implementations for four
event intelligence agents that were specified in Roadmap v4 Phase 3 but were
not delivered before the Phase 3 Closeout:

| Agent | Assessment Schema |
|-------|------------------|
| Catalyst Agent | `CatalystAssessment` |
| News Impact Agent | `NewsImpactAssessment` |
| Earnings Playbook Agent | `EarningsPlaybookAssessment` |
| Estimate Revision Agent | `EstimateRevisionAssessment` |

These agents assess discrete events (catalysts, news items, earnings releases,
estimate revisions) and classify their impact on a target ticker. All assessment
outputs are research-only. No trading, broker, or execution logic is present.

---

## 2. Relationship to Roadmap v4

### Phase 3R-A is part of the Phase 3R Backfill sequence

```
[Accepted]
  Phase 3A–3G   Orchestration, Synthesis, Macro, Debate, Decision, HR, Review Loop
  Phase 3 Closeout
  Phase 4A      Integration Boundary Contract (early infrastructure)

[Inserted — Phase 3R Backfill]
  Phase 3R-0    Roadmap Alignment Reconciliation (accepted)
  Phase 3R-A    Event Intelligence Agents Skeleton  ← THIS PHASE
  Phase 3R-B    Trade Plan Drafting Agent Skeleton
  Phase 3R-C    Allocation Agent v0.1 Non-live
  Phase 3R-D    Option Expression Agent v0.1 Non-live
  Phase 3R-E    Roadmap Alignment Closeout

[Paused — resume after Phase 3R-E]
  Phase 4       Memory + Human Feedback + Review
```

### Roadmap v4 Phase 3 gap this phase fills

Roadmap v4 Phase 3 specified Catalyst, News Impact, Earnings Playbook, and
Estimate Revision agents as validated-agent-skeleton deliverables. Phase 3A–3G
delivered the orchestration backbone but did not implement these four domain
agents. Phase 3R-A closes that gap.

### Relationship to Phase 2G (catalysts.py)

Phase 2G (`lib/reliability/catalysts.py`) provides **data-layer schemas** for
raw catalyst, earnings, and estimate revision data: `CatalystEvent`,
`EarningsEvent`, `EstimateRevision`, `CatalystSnapshot`.

Phase 3R-A adds **agent-layer assessment schemas** that interpret and assess
those data-layer artifacts from an agent's perspective:
`CatalystAssessment`, `NewsImpactAssessment`, `EarningsPlaybookAssessment`,
`EstimateRevisionAssessment`.

The two layers are intentionally separated: Phase 2G normalizes raw data;
Phase 3R-A interprets it into agent-level structured assessments.

### Relationship to accepted Phase 3 reliability composition backbone

Phase 3R-A outputs (`EventIntelligenceReport`) can be consumed by future
Phase 3R-B–3D agents, the Phase 3A orchestration layer, and ultimately
by Phase 3G's Review Loop via the ToolResult adapter, consistent with the
established Phase 3 composition pattern.

---

## 3. Schemas

### 3.1 Literal Type Aliases (enums)

| Alias | Values |
|-------|--------|
| `EventIntelligenceStatus` | `unknown`, `complete`, `needs_review`, `blocked` |
| `EventCategory` | `catalyst`, `news`, `earnings`, `estimate_revision`, `macro`, `regulatory`, `product`, `management`, `legal`, `other`, `unknown` |
| `EventImpactDirection` | `positive`, `negative`, `mixed`, `neutral`, `unknown` |
| `EventImpactMagnitude` | `low`, `medium`, `high`, `unknown` |
| `EventReviewTrigger` | `no_review_needed`, `monitor`, `review_before_event`, `review_after_event`, `thesis_changing`, `risk_escalation`, `unknown` |
| `EventEvidenceQuality` | `unsupported`, `weak`, `adequate`, `strong`, `unknown` |
| `EarningsPlaybookAction` | `hold`, `reduce`, `wait`, `review_after`, `unknown` |
| `EventRevisionMetric` | `eps`, `revenue`, `margin`, `rating`, `price_target`, `guidance`, `other`, `unknown` |
| `EventRevisionDirection` | `up`, `down`, `mixed`, `unchanged`, `unknown` |
| `EventRevisionValuationImpact` | `supports_valuation`, `risks_valuation`, `neutral`, `unknown` |

`EventRevisionMetric` and `EventRevisionDirection` are new aliases distinct
from Phase 2G's `EstimateMetric` and `RevisionDirection` to reflect agent-level
semantics (e.g., `margin` instead of `operating_margin`; `up`/`down` instead
of `upward`/`downward`).

### 3.2 Pydantic Models

#### CatalystAssessment

Agent-level assessment of one catalyst event.

Key fields: `event_id`, `ticker`, `event_name`, `category`, `event_date`,
`affected_horizons`, `expected_impact_direction`, `expected_impact_magnitude`,
`thesis_link`, `review_trigger`, `evidence_refs`, `evidence_quality`,
`warnings`, `approved_for_execution` (always False).

#### NewsImpactAssessment

Agent-level assessment of one news item.

Key fields: `news_id`, `ticker`, `headline`, `source`, `url`, `published_at`,
`relevance_level`, `impact_direction`, `impact_magnitude`, `thesis_changing`,
`is_noise`, `affected_horizons`, `review_trigger`, `evidence_refs`,
`evidence_quality`, `warnings`, `approved_for_execution` (always False).

#### EarningsPlaybookAssessment

Pre- and post-earnings checklist assessment.

Key fields: `earnings_id`, `ticker`, `earnings_date`, `period`,
`pre_earnings_expectation`, `key_metrics_to_watch`, `implied_move`,
`guidance_focus`, `possible_action`, `post_earnings_review_required`,
`affected_horizons`, `review_trigger`, `evidence_refs`, `evidence_quality`,
`warnings`, `approved_for_execution` (always False).

`possible_action` is a research-level assessment of the most prudent course;
it does NOT authorize execution.

#### EstimateRevisionAssessment

Assessment of one consensus estimate revision.

Key fields: `revision_id`, `ticker`, `revision_metric`, `revision_direction`,
`revision_magnitude`, `medium_term_impact`, `valuation_support_or_risk`,
`affected_horizons`, `review_trigger`, `evidence_refs`, `evidence_quality`,
`warnings`, `approved_for_execution` (always False).

#### EventIntelligenceBundle

Aggregate container for all four assessment types for one target.

Fields: `bundle_id`, `target`, `as_of`, `catalyst_assessments`,
`news_impact_assessments`, `earnings_playbooks`, `estimate_revision_assessments`,
`source_ids`, `warnings`, `metadata`.

All four assessment lists default to empty. Missing categories produce warnings,
not errors.

#### EventIntelligenceSummary

Deterministic computed summary of the bundle.

Fields: `target`, `status`, `catalyst_count`, `news_count`, `earnings_count`,
`revision_count`, `thesis_changing_event_count`, `review_required_count`,
`high_impact_event_count`, `affected_horizons`, `top_warnings`,
`approved_for_execution` (always False).

#### EventIntelligenceReport

Full auditable report for one event intelligence analysis pass.

Fields: `report_id`, `schema_version`, `target`, `run_id`, `status`,
`bundle`, `summary`, `source_ids`, `warnings`, `created_at`,
`calculation_version`, `approved_for_execution` (always False).

---

## 4. Status Logic

```
determine_event_intelligence_status(bundle) → EventIntelligenceStatus
```

Priority (highest wins):

| Priority | Status | Condition |
|----------|--------|-----------|
| 1 (highest) | `blocked` | Any assessment has `review_trigger == "risk_escalation"` |
| 2 | `needs_review` | Any news is `thesis_changing=True`, or any event has `impact_magnitude == "high"` (or `revision_magnitude == "high"`), or any event has `review_trigger` in `{thesis_changing, review_before_event, review_after_event}`, or any earnings has `post_earnings_review_required=True` |
| 3 | `complete` | Bundle has at least one assessment, none of the above conditions |
| 4 (lowest) | `unknown` | Bundle has no assessments in any category |

`approved_for_execution` is never implied by any status value.

---

## 5. Helper Functions

| Function | Description |
|----------|-------------|
| `make_event_intelligence_report_id(run_id, target, as_of)` | Deterministic `eil_{hash}` ID for a report |
| `make_event_intelligence_bundle_id(target, as_of)` | Deterministic `eib_{hash}` ID for a bundle |
| `determine_event_intelligence_status(bundle)` | Status from bundle contents; no mutation |
| `collect_event_intelligence_source_ids(bundle)` | Deduplicated source/evidence IDs, first-occurrence order |
| `summarize_event_intelligence(bundle, status, source_ids, extra_warnings=None)` | Build `EventIntelligenceSummary`; includes generated warnings in `top_warnings`; no mutation |
| `build_event_intelligence_report(bundle, run_id, created_at=None)` | Full pipeline: warnings → source IDs → status → summary → report; `created_at` defaults to `bundle.as_of` (deterministic) |
| `event_intelligence_tool_result_from_report(run_id, report, target=None)` | Wrap report as `ToolResult` for evidence-aware pipelines |

---

## 6. ToolResult Adapter

```python
event_intelligence_tool_result_from_report(run_id, report) → ToolResult
```

Behavior:
- `tool_name`: stable `"event_intelligence_report"` (never changes)
- `target`: defaults to `report.target`
- `outputs`: `{"report": ..., "summary": ..., "calculation_version": ...}`
- `evidence_id`: deterministic, content-sensitive hash via `make_evidence_id()`
- Does not mutate the report
- `approved_for_execution` is always `False` in the payload
- No live execution implication

The ToolResult can be registered in an `EvidenceStore` and referenced by
downstream agents via `EvidenceRef` in the standard Phase 0–3G pattern.

---

## 7. Source / Evidence Handling

Source IDs are collected in deterministic order:
1. Bundle-level `source_ids`
2. `CatalystAssessment.evidence_refs` (in list order)
3. `NewsImpactAssessment.evidence_refs`
4. `EarningsPlaybookAssessment.evidence_refs`
5. `EstimateRevisionAssessment.evidence_refs`

Duplicates are removed preserving first-occurrence order. No ID is fabricated;
all source IDs must be provided by callers from actual ToolResult evidence chains.

---

## 8. Execution-Safety Guardrails

Every model that could theoretically be used for execution has a
`model_validator(mode="after")` that raises `ValueError` if
`approved_for_execution=True` is set. This applies to:

- `CatalystAssessment`
- `NewsImpactAssessment`
- `EarningsPlaybookAssessment`
- `EstimateRevisionAssessment`
- `EventIntelligenceSummary`
- `EventIntelligenceReport`

No pathway exists in Phase 3R-A to set `approved_for_execution=True`.
The `possible_action` field in `EarningsPlaybookAssessment` is a research-only
assessment label; it does not authorize any form of execution.

---

## 9. Offline / Mock-Only Nature

Phase 3R-A:
- Makes no network calls
- Makes no live LLM calls
- Reads no live data feeds
- Writes no files
- Has no Streamlit dependency
- Has no broker / order / exchange dependency
- Does not modify any existing `lib/reliability/` module except `__init__.py`
- Does not modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any
  live workflow module

All outputs are deterministic for identical inputs.
`created_at` in `build_event_intelligence_report()` defaults to `bundle.as_of`
(not the current wall-clock time), so identical inputs always produce identical
full report output. Pass `created_at` explicitly to override.

---

## 10. Warning Propagation

Generated (report-level) warnings are included in `EventIntelligenceSummary.top_warnings`.

The private helper `_generate_event_intelligence_warnings(bundle)` returns only
newly derived warnings (not `bundle.warnings`). `build_event_intelligence_report()`
assembles the full `report.warnings` list as `bundle.warnings + generated_warnings`
(deduplicated, first-occurrence order) and passes `generated_warnings` to
`summarize_event_intelligence()` via the `extra_warnings` parameter.

`top_warnings` in the summary is drawn from:
  `bundle.warnings` + each assessment's `warnings` + `extra_warnings`
deduplicated, first-occurrence order, capped at 5.

### Future evidence enhancement (not implemented)

A future phase could promote `evidence_refs: list[str]` to
`evidence_refs: list[EvidenceRef]` to support field-path-level evidence binding
(matching the Phase 0–3G `EvidenceRef` pattern). This would allow validators to
check that each claim in an assessment is backed by a specific field in a specific
`ToolResult`. Phase 3R-A uses string IDs to remain schema-backward-compatible with
the simpler evidence_refs lists already present in Phase 2G models.

---

## 12. Future Integration with Phase 4 Memory

When Roadmap Phase 4 Memory is started (after Phase 3R-E is accepted),
the following integration points are anticipated:

| Memory Type | Integration |
|-------------|-------------|
| Catalyst Memory | Store `CatalystAssessment` outcomes keyed by `(ticker, event_id)` |
| News Memory | Store `NewsImpactAssessment` outcomes keyed by `(ticker, news_id)` |
| Earnings Memory | Store `EarningsPlaybookAssessment` outcomes keyed by `(ticker, period)` |
| Thesis Memory by Horizon | `thesis_changing=True` news triggers thesis update across horizons |
| Agent Evaluation | `EventIntelligenceReport.status` feeds into agent evaluation metrics |

None of these integrations are implemented in Phase 3R-A.
Phase 4 Memory work is paused until Phase 3R-E is accepted.

---

## 13. Explicit Non-Authorization Statement

> **This phase does not authorize trading or execution of any kind.**
>
> All outputs from `lib/reliability/event_intelligence.py` are for
> investment research and educational purposes only. They do not
> constitute investment advice. Markets involve risk.
>
> `approved_for_execution` is enforced as `False` in all output schemas.
> No pathway exists to set it `True`. The `possible_action` field in
> `EarningsPlaybookAssessment` is a research-only assessment label only.

---

## 14. Test Coverage

**Test script**: `scripts/test_reliability_event_intelligence.py`

**152/152 tests pass** (as of 2026-05-24, including polish fixes).

Test sections:
- CatalystAssessment construction and validation (7 tests)
- NewsImpactAssessment construction and validation (6 tests)
- EarningsPlaybookAssessment construction and validation (6 tests)
- EstimateRevisionAssessment construction and validation (5 tests)
- EventIntelligenceBundle aggregation (8 tests)
- Status determination logic (11 tests)
- Source ID collection and deduplication (8 tests)
- Summary builder (11 tests)
- Full report builder pipeline (12 tests)
- ToolResult adapter (6 tests)
- ID helper determinism (5 tests)
- `__all__` export coverage (24 tests)
- No forbidden dependencies (7 tests)
- EventIntelligenceSummary validator (3 tests)
- Determinism + warning propagation (polish fixes) (13 tests)

---

## 15. Public API

Exported via `lib/reliability/__init__.py`:

**Literal aliases**: `EventIntelligenceStatus`, `EventCategory`,
`EventImpactDirection`, `EventImpactMagnitude`, `EventReviewTrigger`,
`EventEvidenceQuality`, `EarningsPlaybookAction`, `EventRevisionMetric`,
`EventRevisionDirection`, `EventRevisionValuationImpact`

**Models**: `CatalystAssessment`, `NewsImpactAssessment`,
`EarningsPlaybookAssessment`, `EstimateRevisionAssessment`,
`EventIntelligenceBundle`, `EventIntelligenceSummary`, `EventIntelligenceReport`

**Helpers**: `make_event_intelligence_report_id`, `make_event_intelligence_bundle_id`,
`determine_event_intelligence_status`, `collect_event_intelligence_source_ids`,
`summarize_event_intelligence`, `build_event_intelligence_report`,
`event_intelligence_tool_result_from_report`
