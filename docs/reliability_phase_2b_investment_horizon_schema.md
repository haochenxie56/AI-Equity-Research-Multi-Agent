# Phase 2B: Investment Horizon Schema Foundation

**Date**: 2026-05-21
**Status**: Implemented
**Author**: Reliability Refactor — Phase 2B
**Depends on**: Phase 2A (`docs/reliability_phase_2a_feature_flag_config.md`)

---

## A. Purpose

Phase 2B creates **standalone, Pydantic-compatible schema models** for
horizon-aware investment reasoning.  The schemas express *what to say* about
an investment at three distinct time horizons — short-term, medium-term, and
long-term — using the same evidence-first discipline established in Phases 0–2A.

Its goal is to answer the following design questions:

1. How does the system represent horizon-specific theses, risks, and
   recommendations in a structured, auditable way?
2. How are evidence requirements differentiated by horizon?
3. How does the system detect missing or unsupported horizon reasoning?
4. How do these schemas integrate with the existing `EvidenceRef` and
   `AgentConfidence` contracts?

### What Phase 2B does

- Creates `lib/reliability/horizon.py` with:
  - `InvestmentHorizon` — Literal type alias (`"short_term"`, `"medium_term"`,
    `"long_term"`).
  - `HorizonEvidenceRequirement` — required / preferred evidence categories
    per horizon.
  - `HorizonRisk` — horizon-specific risk with severity and evidence refs.
  - `HorizonThesis` — horizon-specific investment thesis with evidence refs.
  - `HorizonRecommendation` — horizon-specific action with evidence refs.
  - `HorizonTradePlan` — descriptive trade plan (no position sizing, no
    option payoff calculations).
  - `HorizonDecisionSet` — container for all horizon outputs for one target.
  - `default_horizon_evidence_requirements()` — factory for all three
    default requirements.
  - `group_horizon_decisions_by_horizon()` — groups entries by horizon.
  - `summarize_horizon_coverage()` — identifies present/missing horizons.
  - `validate_horizon_decision_set()` — advisory soft-validation helper.
- Updates `lib/reliability/__init__.py` to export all new symbols.
- Creates `scripts/test_reliability_horizon.py` — 128 assertions.
- Creates this design document.

### What Phase 2B does NOT do

- Does **not** modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any
  workflow module.
- Does **not** call the Claude API.
- Does **not** modify any live prompt.
- Does **not** wire horizon schemas into any Streamlit page.
- Does **not** compute position sizes.
- Does **not** compute option payoffs or option chain data.
- Does **not** implement macro, debate, memory, or cockpit logic.

---

## B. Why Separate Horizons?

A single "buy" or "sell" recommendation conflates three fundamentally different
investment contexts:

| Horizon | Timeframe | Evidence focus | Decision driver |
|---|---|---|---|
| **Short-term** | Days to weeks | Price action, volume, event risk | Momentum, breakout/breakdown, catalyst timing |
| **Medium-term** | Weeks to months | Earnings outlook, sector rotation, relative valuation | Estimate revision, catalyst setup, positioning |
| **Long-term** | Months to years | Business quality, moat, management, capital allocation | Compounding durability, valuation vs intrinsic value |

A stock can be simultaneously:
- **Short-term**: overextended — wait for pullback
- **Medium-term**: positive catalyst setup — add on weakness
- **Long-term**: strong business but valuation risk — accumulate at better prices

Without explicit horizon separation, these views collapse into an ambiguous
single recommendation that cannot be audited, invalidated, or acted upon
precisely.

---

## C. Schemas Overview

### `InvestmentHorizon`

```python
InvestmentHorizon = Literal["short_term", "medium_term", "long_term"]
```

Used as the `horizon` field on all horizon-aware models.

---

### `HorizonEvidenceRequirement`

Specifies the evidence categories a well-formed horizon decision should cite.

| Field | Type | Description |
|---|---|---|
| `horizon` | `InvestmentHorizon` | Which horizon these requirements apply to |
| `required_evidence_categories` | `list[str]` | Categories that must be present |
| `preferred_evidence_categories` | `list[str]` | Categories that are useful but not required |
| `description` | `str \| None` | Human-readable annotation |

---

### `HorizonRisk`

A horizon-specific risk with optional evidence references and an optional
invalidation trigger.

| Field | Type | Notes |
|---|---|---|
| `horizon` | `InvestmentHorizon` | |
| `risk_type` | `str` | Non-empty label (e.g. `"earnings_miss"`) |
| `description` | `str` | Non-empty |
| `severity` | `Literal["low","medium","high","critical"]` | |
| `evidence_refs` | `list[EvidenceRef]` | Optional; links risk to ToolResult evidence |
| `invalidation_trigger` | `str \| None` | Condition that negates the risk |

---

### `HorizonThesis`

The core investment thesis for a given horizon.

| Field | Type | Notes |
|---|---|---|
| `horizon` | `InvestmentHorizon` | |
| `thesis` | `str` | Non-empty |
| `supporting_points` | `list[str]` | Each must be non-empty |
| `evidence_refs` | `list[EvidenceRef]` | Should cite ToolResult evidence |
| `confidence` | `AgentConfidence \| None` | Optional confidence assessment |
| `invalidation_conditions` | `list[str]` | Conditions that kill the thesis |

---

### `HorizonRecommendation`

A horizon-specific action recommendation.

Allowed `action` values:

| Action | Meaning |
|---|---|
| `buy` | Initiate or increase position |
| `hold` | Maintain current position |
| `trim` | Reduce position partially |
| `exit` | Close position entirely |
| `avoid` | Do not initiate |
| `wait` | Monitor; no action yet |
| `add_on_pullback` | Add to position on price weakness |
| `add_on_breakout` | Add to position on price breakout |
| `no_action` | Explicitly decided not to act |

Active actions (`buy`, `add_on_pullback`, `add_on_breakout`) should always
carry either an `invalidation_trigger` or a `review_trigger`.  The advisory
validator will warn if neither is set.

---

### `HorizonTradePlan`

Descriptive trade plan — captures *what* and *when*, not *how much*.

| Field | Notes |
|---|---|
| `preferred_instrument` | One of: `stock`, `option`, `cash`, `watchlist`, `no_trade`, `undetermined` |
| `entry_zone` | Descriptive price or condition |
| `add_zone`, `trim_zone`, `target_zone` | Descriptive ranges |
| `stop_loss` | Qualitative stop description |
| `max_risk_note` | Brief qualitative risk note |
| `time_stop` | Re-evaluation deadline |
| `review_trigger` | Event/level triggering review |
| `evidence_refs` | Supporting ToolResult evidence |

**Position sizing does not belong here** — that is the Allocation phase.
**Option payoff does not belong here** — that is the Option Tool phase.

---

### `HorizonDecisionSet`

Container for all horizon outputs for one research target.

- `target` must be non-empty.
- Partial coverage is allowed — not all three horizons need data.
- All list fields default to empty.
- `schema_version` defaults to `"1.0"`.

---

## D. Default Evidence Categories

```
short_term:
  required:  technical, price_volume, event
  preferred: options_flow, news_sentiment

medium_term:
  required:  catalyst, earnings, estimate_revision, valuation, sector_rotation
  preferred: macro, relative_strength

long_term:
  required:  business_quality, financials, valuation, moat, management,
             capital_allocation
  preferred: esg, regulatory, macro
```

These are advisory starting points.  Future phases may override them per
research context (e.g. a merger-arb play may require `event` across all
horizons).

---

## E. Example `HorizonDecisionSet` JSON

```json
{
  "target": "AAPL",
  "schema_version": "1.0",
  "theses": [
    {
      "horizon": "short_term",
      "thesis": "Price coiling below $185 resistance; volume dry-up suggests buyers in control.",
      "supporting_points": ["RSI reset to 45", "Volume -40% vs 20-day average"],
      "evidence_refs": [
        {
          "evidence_id": "AAPL_20260521_120000_abc123:technical_indicator_engine:AAPL:indicators:xyz",
          "tool_name": "technical_indicator_engine",
          "field_path": "rsi",
          "excerpt": "RSI 45.2"
        }
      ],
      "confidence": {"level": "medium", "rationale": "Setup looks good but macro is uncertain.", "score": 0.6},
      "invalidation_conditions": ["Daily close below $178"]
    },
    {
      "horizon": "long_term",
      "thesis": "Dominant ecosystem with durable pricing power and expanding services margin.",
      "supporting_points": [],
      "evidence_refs": [],
      "confidence": null,
      "invalidation_conditions": []
    }
  ],
  "risks": [
    {
      "horizon": "medium_term",
      "risk_type": "guide_down",
      "description": "Management may guide Q4 revenue below consensus on FX headwinds.",
      "severity": "medium",
      "evidence_refs": [],
      "invalidation_trigger": "Q3 earnings call confirms no FX guide-down"
    }
  ],
  "recommendations": [
    {
      "horizon": "short_term",
      "action": "wait",
      "rationale": "Wait for $185 breakout confirmation before adding.",
      "confidence": null,
      "evidence_refs": [],
      "entry_condition": "Daily close above $185 on > 1.5x average volume",
      "exit_condition": null,
      "review_trigger": "Price closes below $178",
      "invalidation_trigger": null
    },
    {
      "horizon": "long_term",
      "action": "buy",
      "rationale": "Accumulate on weakness; strong compounder at fair value.",
      "evidence_refs": [
        {
          "evidence_id": "AAPL_20260521_120000_abc123:valuation_model:AAPL:dcf:xyz",
          "tool_name": "valuation_model",
          "metric": "fair_value",
          "excerpt": "DCF fair value $195"
        }
      ],
      "invalidation_trigger": "Gross margin sustains decline > 200bps for 2 consecutive quarters"
    }
  ],
  "trade_plans": [
    {
      "horizon": "short_term",
      "preferred_instrument": "stock",
      "entry_zone": "$185 breakout",
      "trim_zone": "$195",
      "stop_loss": "Close below $178",
      "target_zone": "$200–$210",
      "review_trigger": "Q4 earnings",
      "evidence_refs": []
    }
  ],
  "evidence_requirements": []
}
```

---

## F. Helper Functions

### `default_horizon_evidence_requirements() -> list[HorizonEvidenceRequirement]`

Returns the three default requirements (one per horizon).  Deterministic and
pure — safe to call at startup for logging or validation context.

### `group_horizon_decisions_by_horizon(ds) -> dict`

Groups all entries in a `HorizonDecisionSet` by horizon.  Returns a dict
keyed by `"short_term"`, `"medium_term"`, `"long_term"`; each value is a
dict with `theses`, `risks`, `recommendations`, `trade_plans`,
`evidence_requirements`.

### `summarize_horizon_coverage(ds) -> dict`

Returns `target`, `present_horizons`, `missing_horizons`, `counts`,
`total_theses`, `total_risks`, `total_recommendations`, `total_trade_plans`.
Useful for logging the completeness of a research run.

### `validate_horizon_decision_set(ds) -> list[str]`

Advisory soft-validator.  Returns warning strings (never raises).  Detects:
- No recommendations / no theses.
- Recommendations or theses with no evidence refs.
- Active actions (`buy` / `add_on_*`) with no invalidation or review trigger.
- Option trade plans with no evidence refs.
- Duplicate recommendations for the same horizon.

Does **not** integrate with `ValidationReport` in this phase.

---

## G. Guardrails

| Rule | Reason |
|---|---|
| Horizon schemas do not create facts | Facts come from deterministic ToolResults |
| Horizon recommendations must eventually be evidence-linked | Unsupported claims are flagged by the advisory validator |
| Position sizing belongs to the Allocation phase | This phase is schema-only |
| Option payoff belongs to the Option Tool phase | This phase is schema-only |
| UI cards belong to the Cockpit phase | No Streamlit changes in this phase |
| `validate_horizon_decision_set` is advisory only | It returns warnings, not exceptions, to allow iterative development |

---

## H. Relationship to Future Phases

| Phase | Description | Horizon schema role |
|---|---|---|
| **Phase 2B (this)** | Schema foundation | Define contracts |
| **Phase 2C** | Horizon-aware prompt contracts | Use `HorizonDecisionSet` in constrained prompts |
| **Phase 2D** | Horizon validation integration | Link `validate_horizon_decision_set` to `ValidationReport` |
| **Phase 2E** | Debate / critic layer | Compare horizon theses across agents |
| **Phase 2F** | Macro & regime overlay | Attach macro context to horizon evidence requirements |
| **Phase 3A** | Allocation | Consume `HorizonRecommendation` for position sizing |
| **Phase 3B** | Option Tool | Consume `HorizonTradePlan` (instrument=option) for payoff analysis |
| **Phase 4** | Cockpit UI | Render `HorizonDecisionSet` as Streamlit cards |
| **Phase 5** | Memory | Persist `HorizonDecisionSet` across research sessions |

---

## Appendix: Exported Symbols

```python
from lib.reliability.horizon import (
    InvestmentHorizon,
    HorizonEvidenceRequirement,
    HorizonRisk,
    HorizonThesis,
    HorizonRecommendation,
    HorizonTradePlan,
    HorizonDecisionSet,
    default_horizon_evidence_requirements,
    group_horizon_decisions_by_horizon,
    summarize_horizon_coverage,
    validate_horizon_decision_set,
)

# Also available via the package shorthand:
from lib.reliability import HorizonDecisionSet, validate_horizon_decision_set
```

## Appendix: Test Script

```bash
python3 scripts/test_reliability_horizon.py
```

128 assertions across groups A–K:
- A: Default evidence requirements (14 assertions)
- B: `HorizonThesis` — EvidenceRef, AgentConfidence, validation (12)
- C: `HorizonRisk` — severity literals, validation (11)
- D: `HorizonRecommendation` — all 9 action literals, validation (15)
- E: `HorizonTradePlan` — all 6 instrument literals, validation (11)
- F: `HorizonDecisionSet` — partial data, empty target, extra fields (11)
- G: `group_horizon_decisions_by_horizon` — correctness (9)
- H: `summarize_horizon_coverage` — present/missing horizons, counts (13)
- I: `validate_horizon_decision_set` — all warning conditions (10)
- J: Serialization roundtrip `model_dump` / `model_validate` / JSON (13)
- K: No live app files imported (9)
