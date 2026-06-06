# Phase 2H: Validation Aggregator

**Date**: 2026-05-22
**Phase**: 2H
**Layer**: `lib/reliability/`
**Status**: Standalone schema/helper foundation only — no live agents or UI

---

## Purpose

Phase 2H adds a standalone validation aggregation layer that collects, normalizes,
and summarizes validation outputs from all Phase 2 data/tool foundations into a
single, auditable `ValidationAggregate` object.

The key problem Phase 2H solves: each Phase 2 module (`horizon`, `macro`,
`allocation`, `options`, `news`, `catalysts`) produces its own list of warning
strings via a `validate_*` function. Without aggregation, there is no unified view
of the overall data quality status across domains before a Critic Agent or the
Investment Cockpit processes the results.

Phase 2H creates the glue layer that:
1. Converts domain-specific warning strings → structured `AggregatedValidationItem` objects
2. Converts existing `ValidationReport` issues from `validate_agent_result()` → items
3. Aggregates items across domains into a single `ValidationAggregate`
4. Wraps the aggregate as a `ToolResult` for evidence-chain tracking

---

## Relationship to Existing `validate_agent_result()`

Phase 2H does **not** replace, modify, or alter `validate_agent_result()` in any way.

The existing function in `lib/reliability/validators.py` validates `AgentResult`
objects against an `EvidenceStore` and returns a `ValidationReport`.

Phase 2H adds `validation_report_to_items()` which converts an already-produced
`ValidationReport` into `AggregatedValidationItem` objects — this is a one-way
transformation for aggregation purposes only.

```
validate_agent_result()          ← unchanged Phase 0/1 behavior
        │
        ▼ (existing output)
ValidationReport + ValidationIssue
        │
        ▼ (new Phase 2H: read-only conversion)
list[AggregatedValidationItem]
        │
        ▼
ValidationAggregate
```

---

## Why Phase 2 Warning Strings Need Aggregation

Phase 2 module validators each return `list[str]` — simple warning strings:

```python
validate_news_snapshot(snap)        # → ["NewsSnapshot has no events."]
validate_macro_snapshot(snap)       # → ["No indicators in snapshot."]
validate_catalyst_snapshot(snap)    # → ["High materiality catalyst missing event_date."]
```

These strings are:
- **Un-structured**: no severity, no domain tag, no evidence reference
- **Un-aggregated**: spread across 6+ modules, with no combined status
- **Un-auditable**: not wrapped in a ToolResult or evidence chain

The `ValidationAggregate` provides a single, structured summary with:
- Per-item severity classification (`critical`, `warning`, `info`)
- Domain tagging (`news`, `catalyst`, `macro`, `allocation`, `option`, `horizon`, `agent_result`, ...)
- Blocking status (items that should halt downstream processing)
- Counts and overall `status` (`pass`, `pass_with_warnings`, `fail`)
- Optional conversion to `ToolResult` for evidence-chain tracking

---

## Scope of This Phase

**Schema/helper/adapter foundation only:**

- No live app integration (no `app.py`, `pages/`, `lib/llm_orchestrator.py` changes)
- No LLM calls
- No data fetching
- No workflow behavior changes
- No Critic Agent, Debate Layer, or Investment Cockpit implementation
- No modification to `validate_agent_result()` or `ValidationReport`

---

## Supported Validation Domains

| Domain | Source |
|--------|--------|
| `agent_result` | Converted from `ValidationReport` issues |
| `horizon` | `validate_horizon_decision_set()` |
| `macro` | `validate_macro_snapshot()` |
| `allocation` | `validate_allocation_decision_set()` |
| `option` | `validate_option_strategy_decision_set()` |
| `news` | `validate_news_snapshot()` |
| `catalyst` | `validate_catalyst_snapshot()` |
| `earnings` | Part of `validate_catalyst_snapshot()` for earnings sub-items |
| `estimate_revision` | Part of `validate_catalyst_snapshot()` for revision sub-items |
| `tool_result` | Future: ToolResult provenance checks |
| `evidence` | Future: Evidence binding checks |
| `system` | System-level errors (unavailable validators, import failures) |
| `unknown` | Unclassified items |

---

## Severity and Status Logic

### Severity

| Input | ValidationSeverity |
|-------|--------------------|
| Phase 2 warning strings | `"warning"` (default) |
| Phase 2 critical strings | caller can set `"critical"` |
| ValidationIssue.severity `"error"` | `"critical"` |
| ValidationIssue.severity `"warning"` | `"warning"` |
| ValidationIssue.severity `"info"` | `"info"` |

### Status

| Condition | ValidationStatus |
|-----------|-----------------|
| Any critical item OR any blocking item | `"fail"` |
| Any warning item (no critical/blocking) | `"pass_with_warnings"` |
| Only info items or no items | `"pass"` |

---

## Core Schema Models

### `AggregatedValidationItem`

One structured validation issue with domain, severity, type, and optional context.

| Field | Type | Description |
|-------|------|-------------|
| `item_id` | `str` | Deterministic unique ID |
| `domain` | `ValidationDomain` | Source domain |
| `severity` | `ValidationSeverity` | `critical / warning / info` |
| `item_type` | `ValidationItemType` | Classification |
| `message` | `str` | Human-readable description |
| `source_name` | `str \| None` | Module, snapshot_id, or tool name |
| `object_id` | `str \| None` | ID of source object |
| `evidence_id` | `str \| None` | Related evidence_id |
| `field_path` | `str \| None` | Related field path |
| `blocking` | `bool` | True for critical severity |
| `metadata` | `dict` | Arbitrary metadata |

### `ValidationAggregate`

Aggregated summary across multiple domains.

| Field | Type | Description |
|-------|------|-------------|
| `aggregate_id` | `str` | Non-empty unique identifier |
| `schema_version` | `str` | Default `"1.0"` |
| `as_of` | `str` | Snapshot date |
| `status` | `ValidationStatus` | Auto-normalised from items: `pass / pass_with_warnings / fail` |
| `items` | `list[AggregatedValidationItem]` | De-duplicated items |
| `source_domains` | `list[ValidationDomain]` | Auto-normalised: sorted unique domains from items |
| `critical_count` | `int` | Auto-normalised: critical severity item count |
| `warning_count` | `int` | Auto-normalised: warning severity item count |
| `info_count` | `int` | Auto-normalised: info severity item count |
| `blocking_count` | `int` | Auto-normalised: blocking item count |
| `metadata` | `dict` | Arbitrary metadata |

> **Auto-normalisation**: After construction, `status`, counts, and `source_domains`
> are always recomputed from `items`. Caller-supplied values for these fields are
> accepted by the schema but then replaced by the normalised values. Empty `items`
> always normalises to `status="pass"`, all counts 0, `source_domains=[]`.

---

## ValidationItemType Classification

| Item Type | Meaning |
|-----------|---------|
| `schema` | Pydantic validation failure |
| `evidence_binding` | Evidence ID or field path binding issue |
| `missing_data` | Required data is absent |
| `stale_data` | Data is older than acceptable threshold |
| `duplicate_data` | Duplicate records detected |
| `mismatch` | Ticker or domain mismatch |
| `risk_limit` | Risk budget or position limit violation |
| `unsupported` | Unsupported numeric claim without evidence |
| `calculation` | Calculation integrity issue |
| `provenance` | Data provenance concern |
| `safety` | Safety or guardrail violation |
| `other` | Unclassified |

---

## Core Helper Functions

### `make_validation_item_id(domain, message, source_name, object_id, field_path) -> str`

Deterministic stable ID from SHA-256 hash of key fields. Same inputs → same ID.

### `warning_to_validation_item(warning, domain, ...) -> AggregatedValidationItem`

Converts a warning string to a structured item. Sets `blocking=True` when
`severity == "critical"`. Does not mutate metadata dict.

### `validation_report_to_items(report) -> list[AggregatedValidationItem]`

Converts an existing `ValidationReport` from `validate_agent_result()` into
aggregate items. Does not modify `ValidationReport` schema or validator behavior.

### `aggregate_validation_items(aggregate_id, as_of, items, metadata) -> ValidationAggregate`

De-duplicates by `item_id`, computes counts, determines status, sorts domains.

### `aggregate_warning_groups(aggregate_id, as_of, warning_groups, ...) -> ValidationAggregate`

Converts `dict[ValidationDomain, list[str]]` → `ValidationAggregate`.
Empty groups produce `"pass"` status.

### `merge_validation_aggregates(aggregate_id, as_of, aggregates, ...) -> ValidationAggregate`

Merges items from multiple aggregates, de-duplicates by `item_id`, recomputes all counts.

### `summarize_validation_aggregate(aggregate) -> dict`

Returns a concise summary dict with `status`, counts, `top_messages` (capped at 10),
and `source_domains`.

### `collect_phase2_validation_warnings(...) -> dict[ValidationDomain, list[str]]`

Convenience helper that calls existing Phase 2 validators only when corresponding
objects are provided. Does not fetch data, does not import live app modules.
Returns domain → warning strings dict. If a Phase 2 validation helper is
unavailable (e.g., `ImportError`), a fallback warning is recorded under the
corresponding originating domain (e.g., `"news"`, `"catalyst"`, `"horizon"`)
rather than crashing. Fallback warnings are **not** placed under
`ValidationDomain.system` unless the implementation explicitly does so.

### `validation_aggregate_tool_result_from_aggregate(run_id, aggregate, target, ...) -> ToolResult`

Wraps a `ValidationAggregate` into a `ToolResult` for evidence-chain tracking.
`tool_name` is always `"validation_aggregate"`. `evidence_id` is deterministic and
includes the `target` value (default `"validation"`). `inputs` stores
`{aggregate_id, as_of, target, calculation_version}` so the target is explicitly
verifiable from the ToolResult.

---

## Example: Warning String Flow

```python
from lib.reliability.news import validate_news_snapshot, NewsSnapshot
from lib.reliability.validation_aggregator import (
    aggregate_warning_groups,
    summarize_validation_aggregate,
)

snap = NewsSnapshot(
    snapshot_id="snap_001", ticker="AAPL", as_of="2026-05-22", events=[]
)
warnings = validate_news_snapshot(snap)
# → ["NewsSnapshot has no events."]

agg = aggregate_warning_groups(
    "agg_001", "2026-05-22", {"news": warnings}
)
summary = summarize_validation_aggregate(agg)
# → {"status": "pass_with_warnings", "warning_count": 1, ...}
```

---

## Example: ValidationReport Conversion Flow

```python
from lib.reliability.validators import validate_agent_result
from lib.reliability.validation_aggregator import (
    validation_report_to_items,
    aggregate_validation_items,
)

report = validate_agent_result(agent_result, store)
items = validation_report_to_items(report)
agg = aggregate_validation_items("agg_ar_001", "2026-05-22", items)
```

---

## Example ValidationAggregate JSON

```json
{
  "aggregate_id": "agg_nvda_20260522",
  "schema_version": "1.0",
  "as_of": "2026-05-22",
  "status": "pass_with_warnings",
  "items": [
    {
      "item_id": "news:3a9f8c1d2e4b",
      "domain": "news",
      "severity": "warning",
      "item_type": "missing_data",
      "message": "NewsSnapshot has no events.",
      "source_name": "news_module",
      "object_id": null,
      "evidence_id": null,
      "field_path": null,
      "blocking": false,
      "metadata": {}
    }
  ],
  "source_domains": ["news"],
  "critical_count": 0,
  "warning_count": 1,
  "info_count": 0,
  "blocking_count": 0,
  "metadata": {}
}
```

---

## Example validation_aggregate ToolResult Payload

```json
{
  "aggregate_id": "agg_nvda_20260522",
  "schema_version": "1.0",
  "as_of": "2026-05-22",
  "status": "pass_with_warnings",
  "items": [...],
  "source_domains": ["news"],
  "critical_count": 0,
  "warning_count": 1,
  "info_count": 0,
  "blocking_count": 0,
  "metadata": {},
  "calculation_version": "validation_aggregator_v1"
}
```

---

## Future Relationship to Other Components

| Future Component | Relationship to Phase 2H |
|------------------|--------------------------|
| **Staleness Checker** | Will produce `stale_data` items that feed into `ValidationAggregate` |
| **Critic Agent v0.1** | Reads `ValidationAggregate.status` and `items` as structured input rather than raw warning strings |
| **Debate Layer** | Uses aggregate `critical_count` and blocking items to decide whether to proceed |
| **Investment Cockpit** | Displays `ValidationAggregate` summary as a data quality dashboard panel |
| **Human Feedback / Review** | Reviewers see structured items; can filter by domain and severity |

---

## Guardrails

- **No live app integration.** `validation_aggregator.py` does not import `app.py`,
  `pages/`, `lib/llm_orchestrator.py`, `lib/data_fetcher.py`, or any Streamlit module.
- **No LLM calls.** All classification is deterministic keyword/code-based logic.
- **No data fetching.** The aggregator consumes already-computed objects only.
- **No workflow behavior changes.** Existing research runs are unaffected.
- **No replacement of existing validators.** `validate_agent_result()` is unchanged.
- **The aggregator summarizes warnings; it does not generate investment conclusions.**
  Status `"fail"` means data quality issues were found — it does not mean "do not invest."

---

## Running Tests

```bash
python3 scripts/test_reliability_validation_aggregator.py
```

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
python3 scripts/test_reliability_validation_aggregator.py
```
