# Phase 2I: Staleness Checker

**Date**: 2026-05-22
**Phase**: 2I
**Layer**: `lib/reliability/`
**Status**: Standalone schema/helper foundation only — no live agents or UI

---

## Purpose

Phase 2I adds a standalone staleness/freshness checking layer that evaluates
timestamps in reliability artifacts and Phase 2 snapshots without fetching
new data.

The key problem Phase 2I solves: Phase 2 reliability artifacts all carry
timestamps (`as_of`, `created_at`, `published_at`, `revision_date`, etc.) but
there is no unified mechanism to check whether those timestamps are still
current before a downstream agent or cockpit processes the results.

Phase 2I creates the staleness layer that:

1. Parses ISO-like datetime strings into timezone-aware datetimes
2. Evaluates staleness of individual timestamps against configurable policies
3. Evaluates expiration status of option contract expirations with grace period support
4. Aggregates findings across domains into a single `StalenessReport`,
   deduplicating by `finding_id`
5. Converts staleness findings into `AggregatedValidationItem` objects for
   integration with the Phase 2H Validation Aggregator
6. Wraps a `StalenessReport` as a `ToolResult` for evidence-chain tracking

---

## Relationship to Existing Components

Phase 2I does **not** replace, modify, or alter any existing Phase 0–2H components.

```
Phase 2 snapshots            ToolResult artifacts
(as_of, published_at, …)    (created_at, outputs.as_of)
        │                              │
        ▼ (new Phase 2I)               ▼
  check_*_staleness() ───────────────────
        │
        ▼
  StalenessFinding (per timestamp, with field_path / evidence_id provenance)
        │
        ▼
  StalenessReport (aggregated, deduplicated by finding_id, auto-normalised)
        │
        ├─ staleness_report_tool_result_from_report() → ToolResult
        │
        └─ staleness_findings_to_validation_items() → list[AggregatedValidationItem]
                                                            │
                                                            ▼
                                              Phase 2H ValidationAggregate
```

---

## Scope of This Phase

**Schema/helper/adapter foundation only:**

- No live app integration (no `app.py`, `pages/`, `lib/llm_orchestrator.py` changes)
- No LLM calls
- No data fetching
- No workflow behavior changes
- No Critic Agent, Debate Layer, or Investment Cockpit implementation

---

## Supported Staleness Domains

| Domain | Default max_age_days | Source Checked |
|--------|----------------------|----------------|
| `news` | 7 | `NewsSnapshot.as_of`, `NewsEvent.published_at` |
| `option` | 1 | `OptionStrategyDecisionSet.as_of`, `OptionChainSnapshot.as_of`, contract/expiration dates |
| `allocation` | 7 | `AllocationDecisionSet.as_of`, portfolio/position `as_of` |
| `macro` | 30 | `MacroSnapshot.as_of`, `MacroIndicator.as_of` |
| `catalyst` | 30 | `CatalystSnapshot.as_of`, `CatalystEvent.event_date` |
| `earnings` | 30 | `EarningsEvent.report_date` |
| `estimate_revision` | 30 | `EstimateRevision.revision_date` |
| `tool_result` | 14 | `ToolResult.created_at`, `ToolResult.outputs["as_of"]` |
| `validation` | 7 | Future: ValidationAggregate age |
| `generic` | 14 | Ad-hoc timestamp checks |
| `unknown` | 14 | Unclassified |

All domains use `near_stale_ratio=0.8`, `expiration_grace_days=0.0`,
and `allow_unknown=True` by default.

---

## Staleness Status and Priority

| Status | Condition |
|--------|-----------|
| `fresh` | Age < `max_age_days * near_stale_ratio`; or future timestamp; or `max_age_days=None` |
| `near_stale` | `max_age_days * near_stale_ratio` ≤ age < `max_age_days`; or within expiration grace window |
| `stale` | Age ≥ `max_age_days` |
| `expired` | For option contracts: past expiration date and beyond any grace window |
| `unknown` | Timestamp is None or cannot be parsed |

**Status priority in `StalenessReport`** (highest wins):
> expired > stale > near_stale > unknown > fresh

---

## Severity Mapping

| StalenessStatus | Default StalenessSeverity |
|-----------------|--------------------------|
| `fresh` | `"info"` (skipped in ValidationItems) |
| `near_stale` | `"info"` |
| `stale` | `"warning"` |
| `expired` | `"critical"` |
| `unknown` | `"warning"` if `allow_unknown=True`; `"critical"` if `allow_unknown=False` |

Configurable per domain via `StalenessPolicy` fields
`near_stale_severity`, `stale_severity`, `expired_severity`.
`unknown_severity` is a derived property from `allow_unknown`.

---

## Core Schema Models

### `StalenessPolicy`

Configuration for staleness thresholds in a specific domain.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `policy_id` | `str` | — | Non-empty unique identifier (whitespace-only rejected) |
| `domain` | `StalenessDomain` | `"generic"` | Domain this policy applies to |
| `max_age_days` | `float \| None` | `None` | Days before data is stale (gt=0 if provided; None = no age limit) |
| `near_stale_ratio` | `float` | `0.8` | Near-stale threshold fraction (0–1) |
| `expiration_grace_days` | `float` | `0.0` | Grace days after expiration before marking expired (ge=0) |
| `allow_unknown` | `bool` | `True` | Controls severity for missing/unparseable timestamps |
| `near_stale_severity` | `StalenessSeverity` | `"info"` | Severity for near_stale findings |
| `stale_severity` | `StalenessSeverity` | `"warning"` | Severity for stale findings |
| `expired_severity` | `StalenessSeverity` | `"critical"` | Severity for expired findings |
| `metadata` | `dict` | `{}` | Arbitrary metadata (default_factory=dict) |

**Property:**
- `unknown_severity` → `"warning"` if `allow_unknown=True`; `"critical"` if `allow_unknown=False`

### `StalenessFinding`

One staleness finding for a single evaluated timestamp.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `finding_id` | `str` | — | Deterministic unique ID (non-empty, whitespace-only rejected) |
| `domain` | `StalenessDomain` | — | Staleness domain |
| `status` | `StalenessStatus` | — | Freshness evaluation result |
| `severity` | `StalenessSeverity` | — | Severity level |
| `message` | `str` | — | Human-readable description (non-empty) |
| `timestamp_value` | `str \| None` | `None` | Raw timestamp string evaluated |
| `timestamp_role` | `TimestampRole` | `"unknown"` | Role of the timestamp |
| `as_of` | `str` | — | Reference date used for comparison (non-empty) |
| `age_days` | `float \| None` | `None` | Days from timestamp to reference (ge=0 if provided; None for unknown/future) |
| `max_age_days` | `float \| None` | `None` | Stale threshold (gt=0 if provided; None for expiration checks) |
| `object_id` | `str \| None` | `None` | ID of source object |
| `field_path` | `str \| None` | `None` | Dot-notation field path in the source artifact |
| `evidence_id` | `str \| None` | `None` | Associated ToolResult evidence_id |
| `source_name` | `str \| None` | `None` | Source object type/name |
| `metadata` | `dict` | `{}` | Arbitrary metadata (default_factory=dict) |

**Constraints:**
- `age_days >= 0` if provided; negative raw age (future timestamps) is normalised to `None`
- `max_age_days > 0` if provided

### `StalenessReport`

Aggregated staleness report for one or more domain checks.

| Field | Type | Description |
|-------|------|-------------|
| `report_id` | `str` | Non-empty unique identifier |
| `schema_version` | `str` | Default `"1.0"` |
| `as_of` | `str` | Reference date for evaluations |
| `target` | `str \| None` | Research target (ticker, domain, etc.) |
| `status` | `StalenessStatus` | Auto-normalised from findings |
| `findings` | `list[StalenessFinding]` | All staleness findings (deduplicated by `finding_id`) |
| `domains_present` | `list[StalenessDomain]` | Auto-normalised: sorted unique domains |
| `fresh_count` | `int` | Auto-normalised |
| `near_stale_count` | `int` | Auto-normalised |
| `stale_count` | `int` | Auto-normalised |
| `expired_count` | `int` | Auto-normalised |
| `unknown_count` | `int` | Auto-normalised |
| `critical_count` | `int` | Auto-normalised |
| `warning_count` | `int` | Auto-normalised |
| `info_count` | `int` | Auto-normalised |
| `metadata` | `dict` | Arbitrary metadata |

> **Auto-normalisation**: After construction, `status`, all counts, and
> `domains_present` are always recomputed from `findings`. Empty `findings`
> always normalises to `status="fresh"`, all counts 0, `domains_present=[]`.

---

## TimestampRole Values

| Role | Meaning |
|------|---------|
| `as_of` | Data snapshot date |
| `generated_at` | Artifact creation time (`ToolResult.created_at`) |
| `published_at` | News event publication time |
| `event_date` | Catalyst event date |
| `expiration` | Option contract expiration date |
| `revision_date` | Estimate revision date |
| `report_date` | Earnings report date |
| `unknown` | Role cannot be determined |

---

## Core Helper Functions

### `parse_iso_like_datetime(ts) -> datetime`

Parses ISO date-only `"YYYY-MM-DD"` (assumed UTC midnight), naive datetime
strings (assumed UTC), and offset-aware datetime strings. Raises `ValueError`
for unparseable strings.

### `days_between(earlier, later) -> float`

Returns float days from `earlier` to `later`. Positive = `later` is after
`earlier`. Both strings parsed via `parse_iso_like_datetime`.

### `make_staleness_finding_id(domain, timestamp_role, timestamp_value, as_of, source_name, object_id, field_path) -> str`

Deterministic finding ID via SHA-256 of key fields. `field_path` is included
in the hash payload, so findings that differ only in `field_path` are distinct.
Format: `{domain}:{timestamp_role}:{hash_16_chars}`.

### `evaluate_timestamp_staleness(timestamp, as_of, policy, field_path=None, evidence_id=None) -> (status, age_days, severity)`

Evaluates the staleness of a single timestamp against a policy.

- Returns `"unknown"` for None or unparseable timestamps.
- `unknown_severity` derived from `policy.allow_unknown` (True→warning, False→critical).
- When `policy.max_age_days` is `None`: always returns `"fresh"` (no age limit).
- `age_days` is `None` for unknown or future timestamps (negative raw age normalised to None).
- `field_path` and `evidence_id` are accepted as informational parameters.

### `evaluate_expiration_status(expiration_value, as_of, policy=None, domain="generic", object_id=None, field_path=None) -> StalenessFinding`

Evaluates whether a contract expiration date has passed. **Returns a
`StalenessFinding`** (not a tuple) with all provenance fields populated.

**Grace period behavior:**
- Missing/unparseable: `status="unknown"`, severity from `allow_unknown`.
- Expiration ≥ `as_of`: `status="fresh"`, `severity="info"`, `age_days=None`.
- `days_past ≤ grace_days`: `status="near_stale"`, `severity="warning"`.
  `metadata` includes `expiration_grace_days` and `days_past_expiration`.
- `days_past > grace_days`: `status="expired"`, `severity=policy.expired_severity`.
  `metadata` includes `expiration_grace_days` and `days_past_expiration`.

`field_path` and `object_id` are propagated into the returned `StalenessFinding`.
`timestamp_role` is always `"expiration"`.

### `aggregate_staleness_findings(report_id, as_of, findings, target=None, metadata=None) -> StalenessReport`

Aggregates a list of `StalenessFinding` into a `StalenessReport`.
**Deduplicates findings by `finding_id`** (first-occurrence wins, preserving
original order). Does not mutate the input list. Auto-normalisation recomputes
all derived fields from the de-duplicated list.

### `default_staleness_policy_for_domain(domain) -> StalenessPolicy`

Returns the default `StalenessPolicy` for a domain. Every returned policy includes:

- `policy_id = "default_{domain}_staleness_policy"`
- `max_age_days` from the table above
- `near_stale_ratio = 0.8`
- `expiration_grace_days = 0.0`
- `allow_unknown = True`

### `check_tool_result_staleness(tool_result, as_of, policy=None, report_id=None) -> StalenessReport`

Checks `ToolResult.created_at` (`field_path="created_at"`, role `generated_at`)
and `ToolResult.outputs["as_of"]` if present (`field_path="outputs.as_of"`, role `as_of`).
Both findings carry `evidence_id=tool_result.evidence_id`.

### `check_news_snapshot_staleness(snapshot, as_of, policy=None, report_id=None) -> StalenessReport`

Checks:
- `snapshot.as_of` → `field_path="as_of"`, `object_id=snapshot.snapshot_id`
- Each `event.published_at` → `field_path=f"events.{i}.published_at"`,
  `object_id=event.event_id`

Does not mutate snapshot.

### `check_option_decision_set_staleness(decision_set, as_of, policy=None, report_id=None) -> StalenessReport`

Checks:
- `decision_set.as_of` → `field_path="as_of"`
- `chain_snapshot.as_of` → `field_path="chain_snapshot.as_of"`
- **Prefers** `chain_snapshot.contracts[i].expiration` via `evaluate_expiration_status`
  (full grace period behavior): `field_path="chain_snapshot.contracts.{i}.expiration"`
- Falls back to `chain_snapshot.expirations[i]` if `contracts` is empty:
  `field_path="chain_snapshot.expirations.{i}"`

### `check_catalyst_snapshot_staleness(snapshot, as_of, policy=None, report_id=None) -> StalenessReport`

Checks (duck-typed, does not mutate):
- `snapshot.as_of` → `field_path="as_of"`, domain `catalyst`
- `catalysts[i].event_date` → `field_path="catalysts.{i}.event_date"`,
  `timestamp_role="event_date"`, `object_id=catalyst.catalyst_id`, domain `catalyst`
- `earnings_events[i].report_date` → `field_path="earnings_events.{i}.report_date"`,
  `timestamp_role="report_date"`, `object_id=earnings.earnings_id`, domain `earnings`
- `estimate_revisions[i].revision_date` → `field_path="estimate_revisions.{i}.revision_date"`,
  `timestamp_role="revision_date"`, `object_id=revision.revision_id`, domain `estimate_revision`

### `check_allocation_decision_set_staleness(decision_set, as_of, policy=None, report_id=None) -> StalenessReport`

Checks (duck-typed against Phase 2D allocation schema, does not mutate):
- `decision_set.as_of` if present → `field_path="as_of"`
- `decision_set.portfolio.as_of` or `decision_set.portfolio_snapshot.as_of` if present →
  `field_path="portfolio.as_of"` (or `"portfolio_snapshot.as_of"`),
  `object_id=portfolio.portfolio_id`
- Each `portfolio.positions[i].as_of` if present →
  `field_path="portfolio.positions.{i}.as_of"` (or `"portfolio_snapshot.positions.{i}.as_of"`),
  `object_id=position.ticker`

Domain is `allocation` for all findings.

### `check_macro_snapshot_staleness(snapshot, as_of, policy=None, report_id=None) -> StalenessReport`

Checks `MacroSnapshot.as_of` (`field_path="as_of"`) and each `MacroIndicator.as_of`
(`field_path="indicators.{i}.as_of"`). **Gracefully handles minimal or unsupported
macro shapes** — all attribute access is wrapped in try/except; a missing `as_of`
produces an unknown finding rather than raising an exception.

### `staleness_findings_to_validation_items(findings) -> list[AggregatedValidationItem]`

Converts non-fresh `StalenessFinding` objects to `AggregatedValidationItem`. Fresh findings are skipped.

**Provenance preserved:**
- `finding.field_path` → `item.field_path`
- `finding.evidence_id` → `item.evidence_id`
- `finding.object_id` → `item.object_id`
- `finding.source_name` → `item.source_name`

**Item type:**
- `"unknown"` status → `item_type="provenance"`
- `"near_stale"` / `"stale"` / `"expired"` → `item_type="stale_data"`

**Metadata:** `staleness_status`, `timestamp_value`, `timestamp_role`, `age_days`, `max_age_days`.

**Severity mapping:** 1:1 (`info`/`warning`/`critical`). `blocking=True` for critical.

**Domain mapping** (StalenessDomain → ValidationDomain):
- `tool_result`, `macro`, `allocation`, `option`, `news`, `catalyst`,
  `earnings`, `estimate_revision` → same name
- `validation`, `generic`, `unknown` → `"unknown"`

### `staleness_report_tool_result_from_report(run_id, report, target, calculation_version) -> ToolResult`

Wraps a `StalenessReport` into a `ToolResult`. `tool_name` is always
`"staleness_report"`. `evidence_id` is deterministic (same inputs → same ID).

### `summarize_staleness_report(report) -> dict`

Returns a concise summary dict with `status`, all counts, `domains_present`,
`top_messages` (capped at 10), and optional `metadata_keys`.

---

## Example: Check News Snapshot Staleness

```python
from lib.reliability.staleness import (
    check_news_snapshot_staleness,
    summarize_staleness_report,
)

snap = NewsSnapshot(
    snapshot_id="snap_001", ticker="AAPL", as_of="2026-05-10",
    events=[]
)
report = check_news_snapshot_staleness(snap, as_of="2026-05-22")
summary = summarize_staleness_report(report)
# → {"status": "stale", "stale_count": 1, ...}
```

---

## Example: Expiration Grace Period

```python
from lib.reliability.staleness import StalenessPolicy, evaluate_expiration_status

pol = StalenessPolicy(
    policy_id="option_grace_pol",
    domain="option",
    max_age_days=1.0,
    expiration_grace_days=3.0,   # 3-day grace after expiry
)

# Expired 1 day ago, within 3-day grace → near_stale warning
finding = evaluate_expiration_status("2026-05-21", "2026-05-22", policy=pol)
assert finding.status == "near_stale"
assert finding.severity == "warning"

# Expired 5 days ago, beyond grace → expired critical
finding2 = evaluate_expiration_status("2026-05-17", "2026-05-22", policy=pol)
assert finding2.status == "expired"
assert finding2.severity == "critical"
```

---

## Example: Convert to ValidationItems (preserving provenance)

```python
from lib.reliability.staleness import (
    check_news_snapshot_staleness,
    staleness_findings_to_validation_items,
)
from lib.reliability.validation_aggregator import aggregate_validation_items

report = check_news_snapshot_staleness(snap, "2026-05-22")
v_items = staleness_findings_to_validation_items(report.findings)
# field_path, evidence_id, object_id preserved on each item
agg = aggregate_validation_items("agg_001", "2026-05-22", v_items)
# → ValidationAggregate with item_type="stale_data" or "provenance" items
```

---

## Example StalenessReport JSON

```json
{
  "report_id": "staleness:news:3a9f8c1d",
  "schema_version": "1.0",
  "as_of": "2026-05-22",
  "target": "snap_001",
  "status": "stale",
  "findings": [
    {
      "finding_id": "news:as_of:3a9f8c1d",
      "domain": "news",
      "status": "stale",
      "severity": "warning",
      "timestamp_role": "as_of",
      "timestamp_value": "2026-05-10",
      "as_of": "2026-05-22",
      "age_days": 12.0,
      "max_age_days": 7.0,
      "message": "NewsSnapshot 'snap_001' as_of is stale (age=12.0d, max=7.0d).",
      "source_name": "news_snapshot",
      "object_id": "snap_001",
      "field_path": "as_of",
      "evidence_id": null,
      "metadata": {}
    }
  ],
  "domains_present": ["news"],
  "fresh_count": 0,
  "near_stale_count": 0,
  "stale_count": 1,
  "expired_count": 0,
  "unknown_count": 0,
  "critical_count": 0,
  "warning_count": 1,
  "info_count": 0,
  "metadata": {}
}
```

---

## Deduplication

`aggregate_staleness_findings()` deduplicates by `finding_id` (first-occurrence
wins). The input list is not mutated. This prevents double-counting when multiple
code paths in a domain checker might produce the same logical finding.

`make_staleness_finding_id()` includes `field_path` in its hash payload, so two
findings that differ only in `field_path` are treated as distinct.

---

## Indexed Field Paths

All `check_*` functions use zero-indexed dot-notation paths for collections:

| Checker | Field path pattern |
|---------|-------------------|
| News events | `"events.{i}.published_at"` |
| Catalyst events | `"catalysts.{i}.event_date"` |
| Earnings events | `"earnings_events.{i}.report_date"` |
| Estimate revisions | `"estimate_revisions.{i}.revision_date"` |
| Option contracts (preferred) | `"chain_snapshot.contracts.{i}.expiration"` |
| Option expirations (fallback) | `"chain_snapshot.expirations.{i}"` |
| Macro indicators | `"indicators.{i}.as_of"` |
| Portfolio positions | `"portfolio.positions.{i}.as_of"` |

---

## Default Policy IDs

| Domain | policy_id |
|--------|-----------|
| `news` | `default_news_staleness_policy` |
| `option` | `default_option_staleness_policy` |
| `allocation` | `default_allocation_staleness_policy` |
| `macro` | `default_macro_staleness_policy` |
| `catalyst` | `default_catalyst_staleness_policy` |
| `earnings` | `default_earnings_staleness_policy` |
| `estimate_revision` | `default_estimate_revision_staleness_policy` |
| `validation` | `default_validation_staleness_policy` |
| `tool_result` | `default_tool_result_staleness_policy` |
| `generic` | `default_generic_staleness_policy` |
| `unknown` | `default_unknown_staleness_policy` |

---

## Future Relationship to Other Components

| Future Component | Relationship to Phase 2I |
|------------------|--------------------------|
| **Validation Aggregator** | `staleness_findings_to_validation_items()` produces `AggregatedValidationItem` with `field_path`/`evidence_id`/`object_id` preserved and `item_type="stale_data"` or `"provenance"` |
| **Critic Agent v0.1** | Reads `StalenessReport.status` and `findings` as structured input |
| **Investment Cockpit** | Displays staleness status as a freshness indicator panel |
| **Data Refresh Pipeline** | `StalenessReport.stale_count > 0` triggers selective data refresh |

---

## Guardrails

- **No live app integration.** `staleness.py` does not import `app.py`,
  `pages/`, `lib/llm_orchestrator.py`, `lib/data_fetcher.py`, or any Streamlit module.
- **No LLM calls.** All staleness evaluation is deterministic date arithmetic.
- **No data fetching.** The checker consumes already-computed objects only.
- **No workflow behavior changes.** Existing research runs are unaffected.
- **No replacement of existing validators.** `validate_agent_result()` is unchanged.
- **No investment conclusions.** This layer produces freshness metadata only.
- **Staleness status `"stale"` or `"expired"` does not mean "do not invest."** It
  means the data may be outdated and should be refreshed before making decisions.

---

## Running Tests

```bash
python3 scripts/test_reliability_staleness.py
```

Expected output: `172 passed, 0 failed`

Test categories covered (14 total):
1. `StalenessPolicy` — policy_id, expiration_grace_days, allow_unknown, unknown_severity property
2. `StalenessFinding` — as_of, field_path, evidence_id, numeric constraints
3. `evaluate_timestamp_staleness` — allow_unknown severity, max_age_days=None, informational params
4. `evaluate_expiration_status` — grace period, allow_unknown, StalenessFinding return type
5. `aggregate_staleness_findings` — deduplication, count accuracy, input immutability
6. `check_news_snapshot_staleness` — field_path provenance, event_id as object_id
7. `check_catalyst_snapshot_staleness` — event_date, earnings, revisions, indexed field_paths
8. `check_allocation_decision_set_staleness` — portfolio.as_of, position.as_of, field_paths
9. `check_option_decision_set_staleness` — contracts preferred, grace period, field_paths
10. `check_macro_snapshot_staleness` — graceful on minimal objects, as_of checked
11. `staleness_findings_to_validation_items` — field_path/evidence_id/object_id preserved, item_type mapping
12. `default_staleness_policy_for_domain` — policy_id, expiration_grace_days, allow_unknown
13. `staleness_report_tool_result_from_report` — ToolResult validity, determinism
14. Parse/aggregation/normalisation — parse_iso_like_datetime, days_between, report auto-normalisation

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
python3 scripts/test_reliability_staleness.py
```
