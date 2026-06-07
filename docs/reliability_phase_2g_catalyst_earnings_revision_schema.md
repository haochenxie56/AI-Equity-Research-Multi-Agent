# Phase 2G: Catalyst / Earnings / Estimate Revision Schema Foundation

**Date**: 2026-05-22
**Phase**: 2G
**Layer**: `lib/reliability/`
**Status**: Standalone schema/helper/adapter foundation only — no live agents or UI

---

## Purpose

Phase 2G adds a standalone, evidence-first schema foundation for three closely related
domains:

- **Catalysts** — upcoming or past events that could materially move a stock price
  (earnings, guidance, FDA decisions, management changes, M&A, etc.)
- **Earnings Events** — scheduled or historical earnings report snapshots including
  consensus estimates, actual results, and guidance summaries
- **Estimate Revisions** — analyst or consensus changes to key financial metrics
  (EPS, revenue, price targets, ratings, etc.)

These domains share a common concern: future agents must reason about them **only
from evidence-wrapped, deterministic data**. LLMs must never invent catalyst dates,
earnings estimates, or analyst revision numbers.

---

## Why Deterministic ToolResults Before Agent Interpretation

Catalyst, earnings, and estimate revision data are high-stakes inputs:

- An earnings beat or miss can move a stock 10–20% overnight.
- A series of upward EPS revisions is a strong momentum signal used by many
  institutional screening strategies.
- A high-materiality catalyst (FDA decision, analyst day) shapes the option
  strategy and risk budget for weeks before the event.

If LLMs invent or hallucinate any of this data — even plausibly — the downstream
thesis, position sizing, and option hedges become unreliable. Phase 2G enforces the
same architectural rule as all prior phases:

> **Code computes facts. Tools produce versioned, deterministic outputs.
> LLM agents interpret, critique, and synthesize.**

Every catalyst, earnings event, and estimate revision must be wrapped in a `ToolResult`
before any agent interpretation. Agents reference evidence IDs; validators confirm those
IDs resolve to real tool outputs.

---

## Scope of This Phase

This phase is **schema/helper/adapter foundation only**:

- No live earnings calendar, estimate, analyst, or catalyst API integration.
- No Catalyst Agent, Earnings Agent, or Estimate Revision Agent implementation.
- No Streamlit UI, cockpit, or dashboard elements.
- No modifications to any existing live file (`app.py`, `pages/`, `lib/llm_orchestrator.py`,
  `lib/data_fetcher.py`, `lib/workflow_state.py`, `lib/valuation.py`, `lib/technical.py`,
  `lib/rotation.py`, `.claude/agents/`, existing prompt files).
- Tests use synthetic/manual payloads only.

---

## Core Schema Models

### `CatalystEvent`

Represents one sourced catalyst event for a stock or company.

| Field | Type | Notes |
|-------|------|-------|
| `catalyst_id` | `str` (non-empty) | Unique identifier |
| `ticker` | `str` (non-empty) | Underlying ticker |
| `catalyst_type` | `CatalystType` | See enum below |
| `title` | `str` (non-empty) | Short catalyst title |
| `description` | `str \| None` | Optional detail |
| `event_date` | `str \| None` | ISO date; may be absent for ongoing/unknown |
| `timing` | `CatalystTiming` | `past / upcoming / ongoing / unknown` |
| `materiality` | `CatalystMateriality` | `low / medium / high / unknown` |
| `source_type` | `CatalystSourceType` | Source category |
| `source_name` | `str \| None` | Source/publisher name |
| `url` | `str \| None` | Reference URL |
| `related_symbols` | `list[str]` | Related tickers |
| `evidence_refs` | `list[EvidenceRef]` | May be empty at schema level; validation warns |
| `raw_payload` | `dict` | Original source payload |
| `metadata` | `dict` | Arbitrary metadata |

**Example JSON:**

```json
{
  "catalyst_id": "cat_nvda_001",
  "ticker": "NVDA",
  "catalyst_type": "earnings",
  "title": "NVDA Q1 FY2027 Earnings",
  "description": "NVIDIA reports fiscal Q1 2027 results after market close.",
  "event_date": "2026-05-28",
  "timing": "upcoming",
  "materiality": "high",
  "source_type": "company",
  "source_name": "NVIDIA IR",
  "url": null,
  "related_symbols": ["AMD", "INTC"],
  "evidence_refs": [],
  "raw_payload": {},
  "metadata": {}
}
```

---

### `EarningsEvent`

Snapshot of one earnings event including consensus, actuals, and surprise metrics.

| Field | Type | Notes |
|-------|------|-------|
| `earnings_id` | `str` (non-empty) | Unique identifier |
| `ticker` | `str` (non-empty) | Underlying ticker |
| `fiscal_period` | `str \| None` | E.g. `"Q1 FY2027"` |
| `fiscal_year` | `int \| None` | Must be > 1900 if provided |
| `report_date` | `str \| None` | Scheduled or actual report date |
| `status` | `EarningsStatus` | `confirmed / estimated / reported / unknown` |
| `consensus_eps` | `float \| None` | Consensus EPS estimate |
| `actual_eps` | `float \| None` | Actual reported EPS |
| `eps_surprise_pct` | `float \| None` | Surprise % (can be negative) |
| `consensus_revenue` | `float \| None` | Consensus revenue estimate (>= 0) |
| `actual_revenue` | `float \| None` | Actual revenue (>= 0) |
| `revenue_surprise_pct` | `float \| None` | Revenue surprise % (can be negative) |
| `guidance_summary` | `str \| None` | Management guidance summary |
| `implied_move_pct` | `float \| None` | Options-implied move magnitude (>= 0) |
| `price_reaction_1d_pct` | `float \| None` | 1-day post-earnings return (can be negative) |
| `source_type` | `CatalystSourceType` | Source category |
| `source_name` | `str \| None` | Source name |
| `evidence_refs` | `list[EvidenceRef]` | Validation warns if empty |
| `raw_payload` | `dict` | Original payload |
| `metadata` | `dict` | Arbitrary metadata |

**Example JSON:**

```json
{
  "earnings_id": "earn_nvda_q1fy2027",
  "ticker": "NVDA",
  "fiscal_period": "Q1 FY2027",
  "fiscal_year": 2027,
  "report_date": "2026-05-28",
  "status": "confirmed",
  "consensus_eps": 5.50,
  "actual_eps": null,
  "eps_surprise_pct": null,
  "consensus_revenue": 26000000000.0,
  "actual_revenue": null,
  "revenue_surprise_pct": null,
  "guidance_summary": null,
  "implied_move_pct": 8.5,
  "price_reaction_1d_pct": null,
  "source_type": "synthetic",
  "source_name": null,
  "evidence_refs": [],
  "raw_payload": {},
  "metadata": {}
}
```

---

### `EstimateRevision`

One analyst or consensus estimate revision for a financial metric.

| Field | Type | Notes |
|-------|------|-------|
| `revision_id` | `str` (non-empty) | Unique identifier |
| `ticker` | `str` (non-empty) | Underlying ticker |
| `metric` | `EstimateMetric` | The metric being revised |
| `period` | `str \| None` | E.g. `"FY2026"` |
| `previous_value` | `float \| str \| None` | Previous estimate (numeric or rating label) |
| `revised_value` | `float \| str \| None` | Revised estimate |
| `revision_pct` | `float \| None` | Computed % change (can be negative) |
| `direction` | `RevisionDirection` | `upward / downward / mixed / unchanged / unknown` |
| `revision_date` | `str \| None` | Date of revision |
| `source_type` | `RevisionSourceType` | Source category |
| `source_name` | `str \| None` | Source name |
| `analyst_firm` | `str \| None` | Analyst firm |
| `analyst_name` | `str \| None` | Individual analyst |
| `evidence_refs` | `list[EvidenceRef]` | Validation warns if empty |
| `raw_payload` | `dict` | Original payload |
| `metadata` | `dict` | Arbitrary metadata |

**Example JSON:**

```json
{
  "revision_id": "rev_nvda_eps_q1fy2027",
  "ticker": "NVDA",
  "metric": "eps",
  "period": "Q1 FY2027",
  "previous_value": 5.20,
  "revised_value": 5.50,
  "revision_pct": 5.77,
  "direction": "upward",
  "revision_date": "2026-05-15",
  "source_type": "analyst",
  "source_name": "Goldman Sachs Research",
  "analyst_firm": "Goldman Sachs",
  "analyst_name": null,
  "evidence_refs": [],
  "raw_payload": {},
  "metadata": {}
}
```

---

### `CatalystSnapshot`

Container for catalyst events, earnings events, and estimate revisions for one ticker.

| Field | Type | Notes |
|-------|------|-------|
| `snapshot_id` | `str` (non-empty) | Unique identifier |
| `ticker` | `str` (non-empty) | Underlying ticker |
| `schema_version` | `str` | Default `"1.0"` |
| `as_of` | `str` (non-empty) | Snapshot date |
| `catalysts` | `list[CatalystEvent]` | May be empty (partial data allowed) |
| `earnings_events` | `list[EarningsEvent]` | May be empty |
| `estimate_revisions` | `list[EstimateRevision]` | May be empty |
| `warnings` | `list[str]` | Advisory warnings |
| `metadata` | `dict` | Arbitrary metadata |

**Example JSON:**

```json
{
  "snapshot_id": "snap_nvda_20260522",
  "ticker": "NVDA",
  "schema_version": "1.0",
  "as_of": "2026-05-22",
  "catalysts": [...],
  "earnings_events": [...],
  "estimate_revisions": [...],
  "warnings": [],
  "metadata": {"source": "synthetic"}
}
```

---

### `CatalystCoverageSummary`

Concise summary of coverage for a `CatalystSnapshot`.

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | `str` | Underlying ticker |
| `catalyst_count` | `int` | Total catalysts |
| `upcoming_catalyst_count` | `int` | Catalysts with `timing == "upcoming"` |
| `high_materiality_count` | `int` | Catalysts with `materiality == "high"` |
| `earnings_event_count` | `int` | Total earnings events |
| `estimate_revision_count` | `int` | Total estimate revisions |
| `upward_revision_count` | `int` | Revisions with `direction == "upward"` |
| `downward_revision_count` | `int` | Revisions with `direction == "downward"` |
| `categories_present` | `list[CatalystType]` | Unique catalyst types |
| `revision_metrics_present` | `list[EstimateMetric]` | Unique revision metrics |
| `warnings` | `list[str]` | Advisory warnings |

---

## Enums and Literals

### `CatalystType`
`earnings`, `guidance`, `analyst_day`, `investor_day`, `product_launch`,
`fda_regulatory`, `macro_event`, `management_change`, `m_and_a`, `litigation`,
`dividend`, `buyback`, `financing`, `index_inclusion`, `sector_event`, `other`, `unknown`

### `CatalystTiming`
`past`, `upcoming`, `ongoing`, `unknown`

### `CatalystMateriality`
`low`, `medium`, `high`, `unknown`

### `CatalystSourceType`
`company`, `sec_filing`, `news`, `analyst`, `exchange`, `macro_calendar`,
`manual`, `synthetic`, `other`

### `EarningsStatus`
`confirmed`, `estimated`, `reported`, `unknown`

### `EarningsSurpriseDirection`
`beat`, `miss`, `inline`, `unknown`

### `EstimateMetric`
`eps`, `revenue`, `ebitda`, `operating_margin`, `gross_margin`, `free_cash_flow`,
`price_target`, `rating`, `other`

### `RevisionDirection`
`upward`, `downward`, `mixed`, `unchanged`, `unknown`

### `RevisionSourceType`
`analyst`, `consensus`, `company_guidance`, `model`, `manual`, `synthetic`, `other`

---

## Core Helper Functions

### `infer_catalyst_timing(event_date, as_of) -> CatalystTiming`

Infers timing from ISO date string comparison. No external data.

- `event_date < as_of` → `"past"`
- `event_date == as_of` → `"ongoing"`
- `event_date > as_of` → `"upcoming"`
- Missing or unparseable → `"unknown"`

### `infer_earnings_surprise_direction(eps_surprise_pct, revenue_surprise_pct) -> EarningsSurpriseDirection`

Determines if earnings beat, missed, or came in line from surprise percentages. No LLM.

- Both positive → `"beat"`
- Both negative → `"miss"`
- Both zero → `"inline"`
- Mixed signs → `"unknown"`
- Both None → `"unknown"`

### `infer_revision_direction(previous_value, revised_value) -> RevisionDirection`

Infers direction from numeric or rating-string comparison.

- Numeric: compares float values.
- Strings: uses a rank table (`sell < underperform < hold/neutral < buy < outperform/overweight < strong buy`).
- Unknown/incompatible types → `"unknown"`.

### `calculate_revision_pct(previous_value, revised_value) -> float | None`

Computes `(revised - previous) / abs(previous) * 100`. Returns `None` for zero,
non-numeric, or missing values.

### `catalyst_snapshot_from_components(...) -> CatalystSnapshot`

Builds a `CatalystSnapshot` from provided lists. Does not fetch data. Does not
mutate input lists or dicts.

### `catalyst_tool_result_from_snapshot(run_id, snapshot, target, calculation_version) -> ToolResult`

Wraps a `CatalystSnapshot` into a `ToolResult` for submission to `EvidenceStore`.

- `tool_name` is always `"catalyst_snapshot"` (stable).
- `evidence_id` is deterministic for the same `run_id` and snapshot content.
- `outputs` includes the full serialized snapshot plus `calculation_version`.

### `extract_catalyst_event_paths(snapshot) -> list[str]`

Returns dot-notation field paths for `EvidenceRef.field_path` bindings.

Examples:
- `catalysts.0.title`
- `earnings_events.0.consensus_eps`
- `estimate_revisions.0.direction`

Paths resolve through the existing `_resolve_field_path` validator in
`lib/reliability/validators.py` (list-index support added in Phase 2F).

### `summarize_catalyst_snapshot_coverage(snapshot) -> CatalystCoverageSummary`

Counts catalysts, earnings events, and revisions; classifies by timing, materiality,
and revision direction; warns if all sections are empty.

### `validate_catalyst_snapshot(snapshot) -> list[str]`

Returns advisory warning strings. Does not raise. Does not produce a `ValidationReport`.

Checks:
1. Empty snapshot
2. Catalyst ticker mismatch
3. Earnings ticker mismatch
4. Revision ticker mismatch
5. Catalyst with no `evidence_refs`
6. Earnings event with no `evidence_refs`
7. Estimate revision with no `evidence_refs`
8. High materiality catalyst missing `event_date`
9. Upcoming catalyst missing `event_date`
10. Reported earnings missing actual EPS or revenue
11. Confirmed/estimated earnings missing `report_date`
12. Revision direction conflicts with numeric previous/revised values
13. Revision missing `revision_date`
14. Duplicate catalyst title/date pairs
15. Duplicate earnings report_date/fiscal_period pairs
16. Duplicate revision metric/period/date pairs

---

## Future Relationship to Other Agents and Components

Phase 2G is the schema/helper foundation only. Future phases will build on it:

| Future Component | Relationship to Phase 2G |
|------------------|--------------------------|
| **Catalyst Agent** | Uses `CatalystSnapshot` ToolResults as evidence; must not invent catalyst data |
| **Earnings Agent** | Uses `EarningsEvent` snapshots; consensus vs. actual comparison is deterministic code, not LLM |
| **Estimate Revision Agent** | Uses `EstimateRevision` snapshots; direction/pct computed by Phase 2G helpers |
| **ThesisTracker** | May consume `CatalystCoverageSummary` to flag upcoming catalyst risk |
| **Watchlist** | May display catalyst timeline from `CatalystSnapshot` |
| **Option Strategy Agent** | Uses `implied_move_pct` and `event_date` from `EarningsEvent` for event-driven option setups |
| **Allocation / Risk Budget** | May use `high_materiality_count` and catalyst timing to adjust risk allocation near events |
| **Human Feedback / Review** | Validators warn on missing evidence_refs, directing reviewers to fill gaps |
| **News Impact Agent** | `CatalystType` aligns with `NewsEventCategory` for cross-referencing catalyst and news signals |

---

## Guardrails

- **LLMs must not invent catalyst dates, earnings estimates, or analyst revisions.**
  All numeric claims must be backed by a `ToolResult` evidence ID.
- **No live data fetching in this phase.** `catalysts.py` imports only `pydantic`,
  `lib.reliability.adapters`, and `lib.reliability.schemas`.
- **Schemas do not determine thesis impact.** That is the role of future agent
  interpretation.
- **Live integrations belong to later phases.** Real earnings calendar APIs
  (e.g., yfinance `calendar`, polygon earnings endpoint) will be wired in a
  dedicated data-fetch phase.
- **UI belongs to the Investment Cockpit phase.** No Streamlit changes are made here.

---

## Running Tests

```bash
python3 scripts/test_reliability_catalysts.py
```

Expected output: all tests pass, 0 failures.

### Full Regression Suite

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
```
