# Phase 2C: Macro Data + ToolResult Schema Foundation

**Date**: 2026-05-21
**Status**: Implemented
**Author**: Reliability Refactor — Phase 2C
**Depends on**: Phase 2B (`docs/reliability_phase_2b_investment_horizon_schema.md`)

---

## A. Purpose

Phase 2C creates **standalone, Pydantic-compatible schema models** for macro
research data and their corresponding ToolResult wrappers.  Macro data —
interest rates, yield curve, inflation, liquidity, credit spreads, volatility,
market breadth, and regime signals — is the upstream context that eventually
shapes sector analysis, stock screening, and investment horizon decisions.

Its goal is to answer the following design questions:

1. How does the system represent sourced macro data in a structured,
   auditable, evidence-first way?
2. How are macro datapoints wrapped into `ToolResult` evidence for LLM agents
   to cite?
3. How are macro regime signals structured for agent interpretation?
4. How does the system detect missing or stale macro coverage?

### What Phase 2C does

- Creates `lib/reliability/macro.py` with:
  - `MacroDataCategory` — Literal type alias (nine categories).
  - `MacroIndicator` — one sourced macro datapoint.
  - `MacroSnapshot` — container for indicators for one research run.
  - `MacroRegimeSignal` — a deterministic regime signal with evidence refs.
  - `MacroRegimeAssessment` — container for regime signals.
  - `default_macro_staleness_rules()` — advisory stale-after-days by category.
  - `macro_snapshot_from_indicators()` — builder for `MacroSnapshot`.
  - `macro_tool_result_from_snapshot()` — wraps snapshot into `ToolResult`.
  - `extract_macro_indicator_paths()` — field paths for `EvidenceRef`.
  - `summarize_macro_snapshot_coverage()` — coverage summary.
  - `validate_macro_snapshot()` — advisory soft-validator.
- Updates `lib/reliability/__init__.py` to export all new symbols.
- Creates `scripts/test_reliability_macro.py` — 167 assertions.
- Creates this design document.

### What Phase 2C does NOT do

- Does **not** fetch real macro data from any source.
- Does **not** implement a Macro Agent.
- Does **not** implement a macro UI dashboard or cockpit panel.
- Does **not** modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any
  workflow module.
- Does **not** call the Claude API.
- Does **not** modify any live prompt.
- Does **not** wire macro schemas into any Streamlit page.

---

## B. Why Macro Research Is Upstream of Sector Analysis

Macro context determines the regime in which sector and stock analysis takes
place.  The same sector analysis can lead to opposite conclusions depending on
the macro environment:

| Macro condition | Sector impact example |
|---|---|
| Rates rising fast (tightening) | Growth/tech multiple compression; financials may benefit |
| Yield curve deeply inverted | Recessionary signal; defensives outperform cyclicals |
| Inflation above trend | Energy/commodities inflate; consumer discretionary pressured |
| Liquidity contracting | Risk-off; credit spreads widen; quality over momentum |
| VIX spiking (high volatility) | Option strategies change risk profile; scanner signals may be false |
| Breadth deteriorating | Market rally may be narrow/unsustainable |

Without a macro layer, sector and stock agents effectively assume a neutral
macro regime — a silent assumption that can produce dangerously wrong
recommendations during macro dislocations.

The target architecture (Phase 3+) is:

```
MacroAgent (interprets MacroSnapshot ToolResults)
       │
       ▼
SectorAgent (macro-aware)
       │
       ▼
Scanner (regime-aware filters)
       │
       ▼
Horizon decisions (risk budget adjusted for vol/regime)
```

Phase 2C only defines the data contract for the first layer.

---

## C. Why Macro Facts Must Come From ToolResults

The same principle that governs financial analysis applies to macro data:

> **Deterministic computation, agentic interpretation, auditable synthesis.**

The Macro Agent must **not** invent rates, inflation figures, credit spreads,
or liquidity conditions.  It must cite `EvidenceRef` objects pointing to
`MacroSnapshot` ToolResults.  The same validation rules that catch
hallucinated DCF numbers apply to hallucinated Fed funds rate claims.

---

## D. Supported Macro Categories

| Category | Description | Staleness |
|---|---|---|
| `rates` | Central bank and money-market rates | 2 days |
| `yield_curve` | Term structure shape and spreads | 2 days |
| `inflation` | CPI, PCE, PPI, breakeven | 45 days |
| `growth` | GDP, industrial production | 45 days |
| `liquidity` | Fed balance sheet, bank reserves, TGA | 7 days |
| `credit_spread` | IG/HY spreads, CDS | 3 days |
| `volatility` | VIX, realized vol, options market implied vol | 2 days |
| `market_breadth` | A/D line, percent above moving averages | 2 days |
| `macro_regime` | Holistic regime assessment | 7 days |

The staleness defaults from `default_macro_staleness_rules()` are **advisory
only**.  Operators may override them per deployment context.

---

## E. Schemas Overview

### `MacroIndicator`

One sourced macro datapoint.  `value` may be numeric or a string label
(e.g. `"expanding"`, `"inverted"`).

| Field | Required | Notes |
|---|---|---|
| `name` | Yes | Non-empty; e.g. `"fed_funds_rate"` |
| `category` | Yes | One of the nine `MacroDataCategory` values |
| `value` | Yes | `bool \| int \| float \| str` |
| `unit` | No | e.g. `"%"`, `"bps"` |
| `as_of` | Yes | Non-empty; data vintage date |
| `source` | Yes | Non-empty; e.g. `"FRED"`, `"Bloomberg"` |
| `frequency` | No | e.g. `"daily"`, `"monthly"` |
| `stale_after_days` | No | Advisory; validator warns if `<= 0` |
| `metadata` | No | Arbitrary key/value dict |

### `MacroSnapshot`

Container for macro indicators for one research run.

| Field | Required | Notes |
|---|---|---|
| `snapshot_id` | Yes | Non-empty; unique per run |
| `as_of` | Yes | Non-empty |
| `indicators` | No | May be partial |
| `notes` | No | Free-text notes |
| `warnings` | No | Coverage/quality warnings |

### `MacroRegimeSignal`

A regime signal with evidence refs and optional confidence.

Allowed `category` values:
`risk_on_risk_off`, `rates`, `liquidity`, `growth`, `inflation`,
`credit`, `volatility`, `breadth`

Allowed `signal` values:
`risk_on`, `risk_off`, `neutral`, `tightening`, `easing`, `expansion`,
`contraction`, `high`, `low`, `mixed`, `unknown`

### `MacroRegimeAssessment`

Container for regime signals.  `target` defaults to `"macro"`.

---

## F. Example `MacroSnapshot` JSON

```json
{
  "snapshot_id": "MACRO_20260521_120000_abc123",
  "schema_version": "1.0",
  "as_of": "2026-05-21",
  "indicators": [
    {
      "name": "fed_funds_rate",
      "category": "rates",
      "value": 5.25,
      "unit": "%",
      "as_of": "2026-05-01",
      "source": "FRED",
      "description": "Federal funds effective rate",
      "frequency": "daily",
      "stale_after_days": 2,
      "metadata": {"series_id": "DFF"}
    },
    {
      "name": "2y10y_spread",
      "category": "yield_curve",
      "value": -45,
      "unit": "bps",
      "as_of": "2026-05-21",
      "source": "Bloomberg",
      "stale_after_days": 2,
      "metadata": {}
    },
    {
      "name": "cpi_yoy",
      "category": "inflation",
      "value": 3.2,
      "unit": "%",
      "as_of": "2026-04-01",
      "source": "BLS",
      "frequency": "monthly",
      "stale_after_days": 45,
      "metadata": {}
    },
    {
      "name": "vix",
      "category": "volatility",
      "value": 18.5,
      "unit": "index",
      "as_of": "2026-05-21",
      "source": "CBOE",
      "stale_after_days": 2,
      "metadata": {}
    }
  ],
  "notes": [],
  "warnings": []
}
```

---

## G. Example Macro ToolResult Payload Shape

```python
from lib.reliability.macro import (
    MacroIndicator, MacroSnapshot,
    macro_snapshot_from_indicators,
    macro_tool_result_from_snapshot,
)

indicators = [
    MacroIndicator(name="fed_funds_rate", category="rates",
                   value=5.25, as_of="2026-05-21", source="FRED"),
]
snap = macro_snapshot_from_indicators("MACRO_20260521_001", "2026-05-21", indicators)
tr = macro_tool_result_from_snapshot("MACRO_20260521_120000_abc123", snap)

# tr.tool_name == "macro_snapshot"
# tr.evidence_id == "MACRO_20260521_120000_abc123:macro_snapshot:macro:macro_snapshot:<hash>"
# tr.outputs includes: snapshot_id, as_of, indicators, calculation_version
# tr.inputs includes: snapshot_id, as_of, calculation_version
# tr.ticker == None  (macro data is not ticker-specific)
```

The ToolResult is then submitted to `EvidenceStore.add_tool_result(tr)`.
A Macro Agent citing this evidence would include an `EvidenceRef` like:

```json
{
  "evidence_id": "MACRO_20260521_120000_abc123:macro_snapshot:macro:macro_snapshot:<hash>",
  "tool_name": "macro_snapshot",
  "field_path": "indicators.0.value",
  "excerpt": "Fed funds rate 5.25%"
}
```

---

## H. Helper Functions

### `default_macro_staleness_rules() -> dict[str, int]`

Returns advisory stale-after-days by `MacroDataCategory`.  Deterministic and
pure — safe to call at startup for validation context or logging.

### `macro_snapshot_from_indicators(snapshot_id, as_of, indicators, notes, warnings)`

Builds a `MacroSnapshot` from provided indicators.  Does not fetch data.
Does not mutate the input list.

### `macro_tool_result_from_snapshot(run_id, snapshot, target="macro", calculation_version="macro_schema_v1")`

Wraps a `MacroSnapshot` into a `ToolResult`.  The evidence_id is
deterministic: same `run_id` + same snapshot data → same id.
`ticker` is set to `None` since macro data is not ticker-specific.

### `extract_macro_indicator_paths(snapshot) -> list[str]`

Returns dot-notation field paths (e.g. `"indicators.0.value"`) for use as
`EvidenceRef.field_path` suggestions.  Five paths per indicator.

### `summarize_macro_snapshot_coverage(snapshot) -> dict`

Returns `categories_present`, `categories_missing`, `indicator_count`,
`stale_rule_categories_available`, `warnings_count`.

### `validate_macro_snapshot(snapshot) -> list[str]`

Advisory soft-validator.  Returns warning strings, never raises.  Checks:
- No indicators.
- Duplicate indicator names within same category.
- Missing major categories (rates, yield_curve, inflation, volatility,
  market_breadth).
- `stale_after_days <= 0`.
- Blank string values.

---

## I. Guardrails

| Rule | Reason |
|---|---|
| Macro schemas do not create facts | Facts come from sourced `MacroIndicator` values |
| Macro Agent must not invent rates/inflation/liquidity data | `AgentResult` findings must cite `EvidenceRef` pointing to `MacroSnapshot` ToolResults |
| Staleness checking will be strengthened later | `stale_after_days` is advisory in this phase |
| Live data connectors belong to later phases | This phase uses synthetic payloads only |
| UI dashboard belongs to Investment Cockpit phase | No Streamlit changes in this phase |

---

## J. Relationship to Future Phases

| Phase | Description | Macro schema role |
|---|---|---|
| **Phase 2C (this)** | Schema + adapter foundation | Define data contracts |
| **Phase 2D** | Macro Agent prompt contract | Use `MacroSnapshot` ToolResult as evidence |
| **Phase 2E** | Macro-aware sector analysis | Pass `MacroRegimeAssessment` to sector agent |
| **Phase 2F** | Macro-aware scanner | Filter scanner output by regime signal |
| **Phase 3A** | Horizon integration | Adjust horizon evidence requirements by regime |
| **Phase 3B** | Risk budget / allocation | Cap position size based on volatility regime |
| **Phase 3C** | Option strategy caution | Suppress option strategies under event/vol regimes |
| **Phase 4** | Cockpit UI | Render `MacroRegimeAssessment` as dashboard cards |
| **Phase 5** | Memory | Persist macro regime history across research sessions |

---

## Appendix: Exported Symbols

```python
from lib.reliability.macro import (
    MacroDataCategory,
    MacroIndicator,
    MacroSnapshot,
    MacroRegimeSignal,
    MacroRegimeAssessment,
    default_macro_staleness_rules,
    macro_snapshot_from_indicators,
    macro_tool_result_from_snapshot,
    extract_macro_indicator_paths,
    summarize_macro_snapshot_coverage,
    validate_macro_snapshot,
)
```

## Appendix: Test Script

```bash
python3 scripts/test_reliability_macro.py
```

167 assertions across groups A–L:
- A: `MacroDataCategory` — all 9 categories (9)
- B: `MacroIndicator` — float/int/str values, optional fields, validation (12)
- C: `MacroSnapshot` — partial data, validation (10)
- D: `default_macro_staleness_rules` — coverage, values, determinism (16)
- E: `macro_snapshot_from_indicators` — construction, no mutation (10)
- F: `macro_tool_result_from_snapshot` — shape, determinism, custom target (18)
- G: `extract_macro_indicator_paths` — paths, determinism, empty (10)
- H: `summarize_macro_snapshot_coverage` — present/missing, counts (14)
- I: `validate_macro_snapshot` — all warning conditions (10)
- J: `MacroRegimeSignal` and `MacroRegimeAssessment` — literals, validation (35)
- K: Serialization roundtrip — all four model types (13)
- L: No live app files or network calls imported (13)
