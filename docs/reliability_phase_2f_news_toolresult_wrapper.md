# Phase 2F: News ToolResult Wrapper Foundation

**Date**: 2026-05-22
**Status**: Implemented
**Author**: Reliability Refactor — Phase 2F
**Depends on**: Phase 2E (`docs/reliability_phase_2e_option_strategy_schema.md`)

---

## A. Purpose

Phase 2F creates **standalone, Pydantic-compatible schema models**, deterministic
helper functions, and `ToolResult` wrappers for stock and company news data.

The product already has individual stock news capability via the Finnhub API
(surfaced in the existing Streamlit pages).  Phase 2F does **not** modify that
live code path in any way.  Instead it builds a parallel, isolated layer that:

1. Defines stable, vendor-agnostic schemas for news events and snapshots.
2. Normalises raw Finnhub-like payloads into those schemas deterministically.
3. Wraps normalised snapshots into `ToolResult` evidence objects that future
   agents can cite.
4. Provides deterministic helpers for classification, coverage summarisation,
   and lightweight advisory validation.

### What Phase 2F does

- Creates `lib/reliability/news.py` with:
  - `NewsSourceVendor` — Literal alias (6 vendor values).
  - `NewsEventCategory` — Literal alias (18 category values).
  - `NewsImpactHorizon` — Literal alias (4 values).
  - `NewsFreshnessStatus` — Literal alias (3 values).
  - `NewsEvent` — One sourced news item with full provenance fields.
  - `NewsSnapshot` — Container for a batch of events for one ticker.
  - `NewsCoverageSummary` — Aggregate coverage metrics for a snapshot.
  - `classify_news_category()` — Deterministic keyword classifier.
  - `normalize_finnhub_news_event()` — Finnhub-like payload normaliser.
  - `news_snapshot_from_events()` — Snapshot builder from event list.
  - `news_tool_result_from_snapshot()` — `ToolResult` adapter.
  - `extract_news_event_paths()` — `EvidenceRef`-friendly field paths.
  - `summarize_news_snapshot_coverage()` — Coverage summary builder.
  - `validate_news_snapshot()` — Advisory soft-validator.
- Updates `lib/reliability/__init__.py` to re-export all new symbols.
- Creates `scripts/test_reliability_news.py` — 173 assertions.
- Creates this design document.

### What Phase 2F does NOT do

- Does **not** fetch real news data from Finnhub, Polygon, or any source.
- Does **not** modify the existing Finnhub news fetch logic.
- Does **not** modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any
  workflow module.
- Does **not** implement a News Agent, Catalyst Agent, or Earnings Agent.
- Does **not** call the Claude API.
- Does **not** modify any live prompt.
- Does **not** wire news schemas into any Streamlit page.
- Does **not** implement margin, assignment probability, or position sizing for
  news-driven trades.

---

## B. Why News Must Become Evidence-Linked ToolResults

The core reliability principle applies to news just as it does to financial
data and option payoffs:

> **Deterministic computation, agentic interpretation, auditable synthesis.**

A News Impact Agent must **not** invent headlines, invent events, or
summarise news from memory.  It must cite `EvidenceRef` objects that point
to `NewsEvent` fields inside a `ToolResult` payload.

Without a stable, versioned `NewsSnapshot` ToolResult, two agents may
produce irreconcilable event lists from the same underlying data — a dangerous
inconsistency for thesis tracking and risk monitoring.

Phase 2F solves this by converting raw vendor payloads into an immutable,
hash-identified evidence object **before** any agent interpretation occurs.

---

## C. Supported Vendors

| `NewsSourceVendor` | Description |
|---|---|
| `"finnhub"` | Finnhub Company News API |
| `"polygon"` | Polygon.io News API |
| `"alpha_vantage"` | Alpha Vantage News Sentiment API |
| `"manual"` | Manually entered / curated news |
| `"synthetic"` | Synthetic/test payloads (default) |
| `"other"` | Any other source |

Only `"finnhub"` normalisation is implemented in Phase 2F via
`normalize_finnhub_news_event()`.  Other vendors follow the same schema contract
and can be normalised in later phases.

---

## D. Supported News Event Categories

| `NewsEventCategory` | Typical headlines |
|---|---|
| `"earnings"` | Quarterly results, EPS beat/miss, revenue reports |
| `"guidance"` | Forward guidance, raised/lowered outlook |
| `"analyst_rating"` | Upgrades, downgrades, initiations, price target changes |
| `"price_target"` | Price target revisions |
| `"product"` | Product launches, software releases, hardware unveils |
| `"partnership"` | Strategic alliances, joint ventures, collaborations |
| `"m_and_a"` | Acquisitions, mergers, takeovers, divestitures |
| `"regulatory"` | FDA approvals, SEC investigations, compliance orders |
| `"macro"` | Fed policy, interest rates, GDP, macro events |
| `"litigation"` | Lawsuits, class actions, settlements, verdicts |
| `"management"` | CEO/CFO changes, executive appointments/resignations |
| `"financing"` | IPOs, debt offerings, equity raises, credit facilities |
| `"dividend"` | Dividend announcements, increases, cuts |
| `"buyback"` | Share repurchase programme announcements |
| `"sector"` | Sector trends, industry-wide reports |
| `"sentiment"` | Market sentiment, investor mood shifts |
| `"other"` | Known but unclassified |
| `"unknown"` | Could not be classified |

---

## E. Schemas Overview

### `NewsEvent`

One sourced news item.

| Field | Required | Notes |
|---|---|---|
| `event_id` | Yes | Non-empty; deterministic from vendor ID or payload hash |
| `ticker` | Yes | Non-empty; always from caller argument in normalisers |
| `headline` | Yes | Non-empty; raises `ValueError` in normalisers if blank |
| `summary` | No | Optional extended body; `None` if absent |
| `source` | Yes | Non-empty publisher name |
| `vendor` | No | `NewsSourceVendor`; defaults to `"synthetic"` |
| `url` | No | Optional article URL; `None` if absent |
| `published_at` | Yes | Non-empty publication timestamp string |
| `category` | No | `NewsEventCategory`; defaults to `"unknown"` |
| `related_symbols` | No | List of related tickers; may be empty |
| `sentiment_score` | No | `float` in `[-1.0, 1.0]`; `None` if absent |
| `impact_horizon` | No | `NewsImpactHorizon`; defaults to `"unknown"` |
| `raw_payload` | No | Preserved vendor dict; not mutated |
| `metadata` | No | Arbitrary key/value metadata |

### `NewsSnapshot`

Container for a batch of events for one ticker.

| Field | Required | Notes |
|---|---|---|
| `snapshot_id` | Yes | Non-empty unique identifier |
| `ticker` | Yes | Non-empty ticker symbol |
| `schema_version` | No | Defaults to `"1.0"` |
| `as_of` | Yes | Non-empty snapshot date/datetime string |
| `vendor` | No | Primary vendor; defaults to `"synthetic"` |
| `events` | No | List of `NewsEvent`; may be empty |
| `lookback_days` | No | `> 0` if provided; `None` if not applicable |
| `warnings` | No | Advisory warnings list |
| `metadata` | No | Arbitrary key/value metadata |

### `NewsCoverageSummary`

Aggregate coverage metrics returned by
`summarize_news_snapshot_coverage()`.

| Field | Required | Notes |
|---|---|---|
| `ticker` | Yes | Non-empty ticker |
| `event_count` | Yes | `>= 0` |
| `categories_present` | No | Sorted list of unique categories seen |
| `vendors_present` | No | Sorted list of unique vendors seen |
| `missing_url_count` | No | Events with no URL |
| `duplicate_headline_count` | No | Events sharing a headline |
| `duplicate_url_count` | No | Events sharing a URL |
| `stale_event_count` | No | Events older than `stale_after_days` |
| `warnings` | No | Advisory warnings from the summariser |

---

## F. Finnhub-like Normalisation

`normalize_finnhub_news_event(raw, ticker, event_id_prefix="finnhub")`
converts a Finnhub company-news API response item into a `NewsEvent`.

### Expected Finnhub-like keys

| Key | Type | Behaviour |
|---|---|---|
| `id` | int/str | If present, `event_id = "{prefix}_{id}"` |
| `datetime` | int (Unix) / str | Converted to ISO-8601 UTC string |
| `headline` | str | **Required**; `ValueError` if missing/blank |
| `summary` | str | Preserved as `summary` |
| `source` | str | Preserved as `source`; `"unknown"` if absent |
| `url` | str | Preserved as `url`; `None` if absent |
| `category` | str | Mapped via `_FINNHUB_CATEGORY_MAP` then keyword fallback |
| `related` | str/list | Comma-split string or list → `related_symbols` |
| `image` | str | Preserved in `raw_payload` only |

### Determinism guarantees

- `raw` is never mutated — a shallow copy is taken at entry.
- `event_id` is deterministic: same vendor ID → same prefix-ID string; no
  vendor ID → stable SHA-256 hash of `(ticker, headline, url, datetime)`.
- `category` classification is purely rule-based (no LLM, no API calls).
- Unix timestamps are converted to `"%Y-%m-%dT%H:%M:%SZ"` UTC strings.

---

## G. Keyword Category Classifier

`classify_news_category(headline, summary=None, raw_category=None)`
is a deterministic, LLM-free heuristic:

1. If `raw_category` is provided and maps to an entry in
   `_FINNHUB_CATEGORY_MAP`, return that mapped value immediately.
2. Concatenate `headline.lower()` and (if given) `summary.lower()` and
   search for the first matching keyword from `_CATEGORY_KEYWORDS` (in
   priority order).
3. Return `"unknown"` if no keyword matches.

Keywords are designed to minimise false matches.  In particular:
- `" eps"` (with leading space) avoids matching `"steps"` or `"express"`.
- `"board of directors"` is used rather than the generic `"board"`.

---

## H. Example `NewsEvent` JSON

```json
{
  "event_id": "finnhub_12345",
  "ticker": "AAPL",
  "headline": "AAPL reports record revenue in Q2",
  "summary": "Apple Inc. posted quarterly revenue of $97B, beating estimates.",
  "source": "Reuters",
  "vendor": "finnhub",
  "url": "https://example.com/aapl-q2",
  "published_at": "2026-05-21T12:00:00Z",
  "category": "earnings",
  "related_symbols": ["AAPL", "MSFT"],
  "sentiment_score": null,
  "impact_horizon": "unknown",
  "raw_payload": {
    "id": 12345,
    "datetime": 1748476800,
    "headline": "AAPL reports record revenue in Q2",
    "summary": "Apple Inc. posted quarterly revenue of $97B, beating estimates.",
    "source": "Reuters",
    "url": "https://example.com/aapl-q2",
    "category": "earnings",
    "related": "AAPL,MSFT",
    "image": "https://example.com/img.jpg"
  },
  "metadata": {}
}
```

---

## I. Example `NewsSnapshot` JSON

```json
{
  "snapshot_id": "AAPL_NEWS_20260521_001",
  "ticker": "AAPL",
  "schema_version": "1.0",
  "as_of": "2026-05-21",
  "vendor": "finnhub",
  "events": [
    {
      "event_id": "finnhub_12345",
      "ticker": "AAPL",
      "headline": "AAPL reports record revenue in Q2",
      "summary": "Apple Inc. posted quarterly revenue of $97B.",
      "source": "Reuters",
      "vendor": "finnhub",
      "url": "https://example.com/aapl-q2",
      "published_at": "2026-05-21T12:00:00Z",
      "category": "earnings",
      "related_symbols": ["AAPL", "MSFT"],
      "sentiment_score": null,
      "impact_horizon": "unknown",
      "raw_payload": {},
      "metadata": {}
    }
  ],
  "lookback_days": 30,
  "warnings": [],
  "metadata": {}
}
```

---

## J. Example News ToolResult Payload Shape

```python
from lib.reliability.news import (
    NewsEvent, NewsSnapshot,
    news_snapshot_from_events,
    news_tool_result_from_snapshot,
    normalize_finnhub_news_event,
)

# 1. Normalise raw vendor payload into NewsEvent
raw_item = {
    "id": 12345,
    "datetime": 1748476800,
    "headline": "AAPL beats Q2 EPS",
    "source": "Reuters",
    "category": "earnings",
    "related": "AAPL",
}
event = normalize_finnhub_news_event(raw_item, ticker="AAPL")

# 2. Bundle into a NewsSnapshot
snapshot = news_snapshot_from_events(
    snapshot_id="AAPL_NEWS_20260521_001",
    ticker="AAPL",
    as_of="2026-05-21",
    events=[event],
    vendor="finnhub",
    lookback_days=30,
)

# 3. Wrap as a ToolResult for EvidenceStore
tr = news_tool_result_from_snapshot("RUN_20260521_001", snapshot)

# tr.tool_name == "news_snapshot"
# tr.ticker == "AAPL"
# tr.evidence_id == "<run_id>:news_snapshot:AAPL:news_snapshot:<hash>"
# tr.inputs == {snapshot_id, ticker, as_of, calculation_version}
# tr.outputs == full snapshot dict + calculation_version
```

A future News Impact Agent citing this evidence includes an `EvidenceRef`:

```json
{
  "evidence_id": "<run_id>:news_snapshot:AAPL:news_snapshot:...",
  "tool_name": "news_snapshot",
  "field_path": "events.0.headline",
  "excerpt": "AAPL beats Q2 EPS"
}
```

---

## K. Helper Functions

### `classify_news_category(headline, summary=None, raw_category=None) → NewsEventCategory`

Deterministic keyword classifier.  No LLM, no API calls.  See Section G.

### `normalize_finnhub_news_event(raw, ticker, event_id_prefix="finnhub") → NewsEvent`

Normalises a Finnhub-like raw dict.  See Section F.

### `news_snapshot_from_events(snapshot_id, ticker, as_of, events, ...) → NewsSnapshot`

Builds a `NewsSnapshot` from a list of `NewsEvent` objects.
Does not mutate inputs.

### `news_tool_result_from_snapshot(run_id, snapshot, target=None, calculation_version="news_schema_v1") → ToolResult`

Wraps a `NewsSnapshot` into a `ToolResult`.  Evidence ID is deterministic:
same `run_id` + same snapshot → same ID.  Full snapshot dict is serialised
into the payload.

### `extract_news_event_paths(snapshot) → list[str]`

Returns EvidenceRef-friendly field paths for all events:
`events.{i}.headline`, `.summary`, `.source`, `.url`, `.published_at`,
`.category`, `.related_symbols`.

### `summarize_news_snapshot_coverage(snapshot, stale_after_days=14) → NewsCoverageSummary`

Counts events, categories, vendors, missing URLs, duplicate headlines,
duplicate URLs, and stale events.  If timestamp parsing fails, staleness is
not counted and a warning is added.

### `validate_news_snapshot(snapshot) → list[str]`

Returns advisory warning strings.  Never raises.  Checks:
1. No events.
2. Event ticker mismatch with snapshot ticker.
3. Missing URL.
4. Duplicate headline (case-insensitive).
5. Duplicate URL (non-`None`).
6. Missing summary.
7. Unknown category (`"unknown"`).
8. Missing `related_symbols` (empty list).
9. Stale event (date parseable and `> 14` days before `as_of`).
10. Inconsistent vendor between snapshot and events.

---

## L. Relationship to Existing Finnhub News Capability

The product's existing Finnhub integration lives in `lib/data_fetcher.py`
and is surfaced via the Streamlit pages.  Phase 2F creates a **completely
independent** layer:

```
Existing path (unchanged):
  lib/data_fetcher.py → Finnhub API → Streamlit page display

Phase 2F path (new, standalone):
  Raw Finnhub dict → normalize_finnhub_news_event() → NewsEvent
                   → news_snapshot_from_events()    → NewsSnapshot
                   → news_tool_result_from_snapshot()→ ToolResult (EvidenceStore)
                   → (future) News Impact Agent cites EvidenceRef
```

Phase 2F neither calls the Finnhub API itself nor modifies the existing fetch
path.  It operates on pre-fetched or synthetic dicts only.

---

## M. Future Phases

| Agent / Feature | Role of Phase 2F schemas |
|---|---|
| **News Impact Agent** | Cites `NewsEvent` fields via `EvidenceRef` to justify impact assessments |
| **Catalyst Agent** | Classifies near-term catalysts from `NewsSnapshot` events |
| **Earnings Agent** | Filters `category="earnings"` events; cites EPS data from `summary` |
| **Estimate Revision Agent** | Watches `category="analyst_rating"` and `"price_target"` events |
| **ThesisTracker** | Checks whether incoming events confirm or challenge an active thesis |
| **Watchlist** | Highlights high-impact events for monitored tickers |
| **Human Feedback / Review** | Presents `NewsSnapshot` summary for analyst annotation |

All future agents must cite evidence IDs from `ToolResult` objects produced by
`news_tool_result_from_snapshot()`.  They must **not** invent headlines or
synthesise events from memory.

---

## N. Guardrails

| Rule | Reason |
|---|---|
| `classify_news_category` uses keyword matching only | No LLM; deterministic and auditable |
| `normalize_finnhub_news_event` does not call Finnhub API | Accepts pre-fetched dicts only |
| `news_tool_result_from_snapshot` does not write to disk | Caller passes result to `EvidenceStore.add_tool_result()` |
| News schemas do not determine thesis impact | Impact analysis belongs to the News Impact Agent phase |
| News Agent must not invent headlines or events | Must cite `EvidenceRef` pointing to `NewsEvent` fields |
| Live news connectors remain existing app/data layer | `lib/data_fetcher.py` and Streamlit pages are untouched |
| This phase does not change live app behaviour | No Streamlit files were modified |
| UI news dashboards belong to Investment Cockpit phase | No UI changes in this phase |
| `raw_payload` is a read-only provenance store | Agents must not use `raw_payload` as canonical field source |

---

## Appendix: Exported Symbols

```python
from lib.reliability.news import (
    # Literal aliases
    NewsSourceVendor,
    NewsEventCategory,
    NewsImpactHorizon,
    NewsFreshnessStatus,
    # Models
    NewsEvent,
    NewsSnapshot,
    NewsCoverageSummary,
    # Helpers
    classify_news_category,
    normalize_finnhub_news_event,
    news_snapshot_from_events,
    news_tool_result_from_snapshot,
    extract_news_event_paths,
    summarize_news_snapshot_coverage,
    validate_news_snapshot,
)
```

All symbols are also re-exported from `lib.reliability` (the package root).

## Appendix: Test Script

```bash
python3 scripts/test_reliability_news.py
```

173 assertions across groups A–M:

- A: Literal type aliases — all 4 types (8)
- B: `NewsEvent` — all fields, optional fields, validation (23)
- C: `NewsSnapshot` — `lookback_days` validation, empty events (12)
- D: `classify_news_category` — all major categories, raw_category hint (21)
- E: `normalize_finnhub_news_event` — mapping, mutation safety, edge cases (21)
- F: `news_snapshot_from_events` — construction, mutation safety (7)
- G: `news_tool_result_from_snapshot` — shape, determinism, custom target (19)
- H: `extract_news_event_paths` — all path fields, two-event coverage (11)
- I: `summarize_news_snapshot_coverage` — counts, stale detection (14)
- J: `validate_news_snapshot` — all 10 warning conditions, clean snapshot (11)
- K: Serialization roundtrips — all key model types (10)
- L: ToolResult payload field paths (7)
- M: Safety — no live imports, all symbols from `lib.reliability` (9)
