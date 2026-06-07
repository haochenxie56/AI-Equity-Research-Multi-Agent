# Phase 5L — Auto Research Pack Orchestration Boundary

**Status:** Implemented — awaiting Codex review.

**Module:** `lib/reliability/phase5_research_pack.py`
**Test:** `scripts/test_reliability_phase_5l_research_pack_orchestration.py`
**Exports:** additive in `lib/reliability/__init__.py`

> Disclaimer: outputs are for research / educational purposes only and do not
> constitute investment advice.

---

## Purpose

Phase 5L defines the **deterministic contracts** for how a future Investment
Cockpit agent will convert Phase 5K opportunity-queue candidates into structured
research-pack requests and research-pack bundles:

```
Phase 5K Opportunity Queue candidate (HorizonCandidateView)
  -> ResearchPackRequest        (what to research, and why)
  -> ResearchPackPlan           (which conceptual modules, in what order)
  -> ResearchPackBundle/Status  (placeholder module result refs + status)
  -> (future) Agent Debate / Decision Packet input  (Phase 5M+)
```

This phase defines the **boundary only**. It does **not** actually run company
research, financial analysis, price-volume analysis, news fetches,
catalyst/earnings lookups, macro/theme/sector/scanner analysis, LLM calls, or
external APIs. Module requests are **descriptive placeholders**
(`is_runtime_call=False`); module result references are **placeholders**
(`is_placeholder=True`, `result_ref=None`) — never generated analysis.

---

## Relationship to Phase 5I (Product Logic Reconciliation)

Phase 5I established the cockpit as **opportunity-first**, **macro-theme-aware**,
and **horizon-aware**, and separated the *source research modules* (the original
five-step AI Research Workflow: Overview / Sector / Scanner / Equity / Financial
/ PriceVolume) from the *cockpit decision layer*. Phase 5L is the first concrete
expression of Phase 5I's "research pack is assembled, not manually wired"
principle: it takes opportunity candidates and decides **which conceptual
research modules a deeper investigation would need**, using the original app
modules as *conceptual source modules* — without calling them.

## Relationship to Phase 5J (Theme Intelligence / Market Heat Schema)

Phase 5J is the upstream **input layer** (themes, subthemes, industry-chain
nodes, candidate tickers, heat / narrative / fundamental / crowding signals,
evidence coverage). Phase 5L consumes Phase 5J only indirectly, through the
Phase 5K opportunity queue. Phase 5J theme / subtheme / chain-node identifiers
are preserved end-to-end onto each `ResearchPackRequest`. Optional Phase 5J theme
metadata may be referenced, but no Phase 5J record is recomputed and no live data
is fetched.

## Relationship to Phase 5K (Horizon-aware Opportunity Queue)

Phase 5K is the **direct input**. Each `HorizonCandidateView` (one ticker
evaluated for one horizon, carrying a decision label, theme heat / entry quality
/ crowding / evidence badges, a next action, and warnings) becomes one
`ResearchPackRequest` + one `ResearchPackBundle`. Because Phase 5K evaluates the
**same ticker across all three horizons** with potentially different decisions,
Phase 5L emits **a distinct research pack per (ticker, horizon)** — the same
name can carry a short-term technical pack and a long-term durability pack at the
same time. Phase 5K's invariant that **heat is not a buy signal** is preserved:
a research pack is a *request to investigate*, never a buy.

---

## Why this is an orchestration boundary only

The cockpit's value is auditability: every step from "interesting opportunity"
to "decision" must be explicit and reviewable. Phase 5L deliberately stops at the
*request/plan/bundle* boundary so that:

- the **module selection logic** is deterministic, inspectable, and testable;
- nothing is executed implicitly — running the modules is a later, separately
  governed step;
- the handoff into Agent Debate / Decision Packet (Phase 5M+) is a clean,
  schema-typed object, not free-form reasoning.

No Phase 5L output is an order, an order ticket, a broker payload, or an
execution instruction. `approved_for_execution` never appears on any Phase 5L
model and is never positively authorized.

---

## Source module taxonomy

A research pack draws on eleven **conceptual source modules**. Each maps to an
original-app capability but is **not called** in Phase 5L:

| Module | Conceptual origin (not executed) |
|--------|----------------------------------|
| `macro_context` | Macro regime / liquidity backdrop (macro agent layer) |
| `theme_context` | Theme intelligence / market heat (Phase 5J) |
| `sector_context` | Sector cycle / rotation (Sector page / sector-research) |
| `scanner_context` | Screening / candidate context (Scanner page / stock-scanner) |
| `company_research` | Business model / moat / management (Equity page / equity-research) |
| `financial_analysis` | 3-statement / DCF / relative valuation (Financial page / financial-analyst) |
| `price_volume_analysis` | Chart / momentum / volume timing (PriceVolume page / price-volume-analyst) |
| `news_sentiment` | News / sentiment context (news ToolResult layer) |
| `catalyst_earnings` | Catalyst / earnings / estimate-revision context (catalyst schema) |
| `risk_review` | Risk / crowding / critic review (Critic layer) |
| `evidence_validation` | Evidence coverage / validator gate (validators / evidence store) |

`RESEARCH_PACK_SOURCE_MODULES` is the canonical ordering used for deterministic
module-list emission.

---

## Horizon-specific research pack rules

| Horizon | Required modules | Optional modules |
|---------|------------------|------------------|
| `short_term` | `price_volume_analysis`, `news_sentiment`, `catalyst_earnings`, `risk_review`, `evidence_validation` | `company_research`, `financial_analysis` |
| `mid_term` | `company_research`, `financial_analysis`, `price_volume_analysis`, `catalyst_earnings`, `risk_review`, `evidence_validation` | `news_sentiment`, `macro_context` |
| `long_term` | `macro_context`, `theme_context`, `company_research`, `financial_analysis`, `risk_review`, `evidence_validation` | `price_volume_analysis`, `catalyst_earnings` |

`evidence_validation` is always required (the evidence gate). Short-term packs
center on **timing** (technical / news / catalyst); mid-term packs add
**fundamental confirmation** (company / financial); long-term packs lead with
**macro + theme durability** plus full fundamentals.

---

## Evidence gap handling

`build_research_pack_evidence_gaps()` derives deterministic gaps from a Phase 5K
candidate view — from its evidence coverage badge (incomplete coverage, missing
fundamental confirmation) and from its mapped warnings. Heat / "not a buy signal"
warnings are **not** gaps. Each gap lists the conceptual modules that *would*
address it (`addressed_by_modules`); nothing is fabricated. Gap → module mapping:

| Gap type | Addressed by |
|----------|--------------|
| `incomplete_evidence` | `evidence_validation`, `company_research` |
| `missing_fundamental_confirmation` | `financial_analysis`, `catalyst_earnings` |
| `narrative_only` | `news_sentiment`, `evidence_validation` |
| `crowding_risk` | `price_volume_analysis`, `risk_review` |
| `valuation_stretch` | `financial_analysis`, `risk_review` |
| `late_cycle` | `macro_context`, `risk_review` |
| `unconfirmed_fundamentals` | `financial_analysis`, `catalyst_earnings` |
| `needs_macro_validation` | `macro_context`, `risk_review` |
| `entry_quality` | `price_volume_analysis`, `risk_review` |

### Research_more behavior

For `research_more` / `insufficient_evidence` / `thesis_unconfirmed` /
`thesis_insufficient` / `watch_wait` decisions, the gap-closing modules are
**promoted into the required set** (beyond the horizon base set), tagged with the
`evidence_gap` trigger reason and elevated to `high` priority. Example: a
no-evidence speculative short-term candidate (`research_more`) promotes
`company_research` and `financial_analysis` into required even though they are
only *optional* in the base short-term rule, because the candidate's gaps demand
them.

### Wait_for_pullback / too_extended behavior

For `wait_for_pullback` / `too_extended`, the pack **forces
`price_volume_analysis` and `risk_review` into the required set** (the entry /
crowding gate) and tags the pack with `entry_quality_check` and
`crowding_risk_check` trigger reasons. A technical and risk read must precede any
trade plan; no trade-plan-enabling commitment is implied.

### No_trade / avoid behavior

For `no_trade` and `avoid_too_crowded`, the pack is **review-only and minimal**:
its required set is exactly `risk_review` + `evidence_validation`, it has no
optional (trade-enabling) modules, it is flagged `is_review_only=True`, and it
carries a `no_trade_review_only` trigger and warning. A no-trade / avoid
candidate therefore **does not become an executable research-to-trade path** — it
yields a documented review-only pack, not a trade pipeline. (A future phase could
elect to emit no pack at all; this phase emits a clearly-labelled review-only
pack so the decision remains auditable.)

---

## Research pack statuses

`ResearchPackStatus` / `ResearchModuleStatus`: `planned`, `waiting_for_data`,
`partial`, `complete`, `blocked`, `skipped`, `failed`, `unknown`.

Because Phase 5L executes nothing, it mostly produces:

- **`planned`** — default fixture: every module result is a planned placeholder
  with `result_ref=None`.
- **`blocked`** — degraded fixture: upstream data unavailable; result refs are
  safe placeholders.
- **`skipped`** — empty queue: no modules.

`determine_research_pack_status()` derives a pack status deterministically from
its module result refs.

---

## Fixture examples

Deterministic fixture builders:

- `build_default_research_pack_bundle()` — the full orchestration boundary built
  from the Phase 5K **default** opportunity queue. Demonstrates:
  - short-term momentum candidate → technical / news / catalyst / risk / evidence
    pack;
  - mid-term position candidate → company / financial / technical / catalyst /
    risk / evidence pack;
  - long-term investment candidate → macro / theme / company / financial / risk /
    evidence pack;
  - `research_more` candidate → gap-driven required modules;
  - `wait_for_pullback` / `too_extended` candidate → price_volume + risk required.
- `build_degraded_research_pack_bundle()` — boundary built from the degraded
  opportunity queue; all module result refs are unavailable `blocked`
  placeholders and each bundle carries warnings (missing refs handled safely).
- `build_empty_research_pack_bundle()` — boundary built from the empty
  opportunity queue: safe empty (no requests / bundles), `skipped`, with warnings.

"Bundle" in the default/degraded builder names refers to the full set of
per-candidate research-pack bundles held by the `AutoResearchPackOrchestrationBoundary`.

---

## Safe / degraded states

- **Empty opportunity queue** → safe empty boundary
  (`validation_summary.is_safe_empty == True`), status `skipped`, no fabricated
  candidates.
- **Degraded upstream** → module result refs are `blocked` placeholders with
  `result_ref=None` and no evidence refs; warnings describe the degradation; no
  analysis is fabricated.
- **Missing candidate fields** (e.g. `company_name=None`) → a descriptive warning
  is added and the field is left empty; nothing is fabricated.
- Module requests are **descriptive** (`is_runtime_call=False`); module result
  refs are **placeholders** (`is_placeholder=True`).
- No final buy/sell recommendation, no executable order field, no
  `approved_for_execution`.

---

## Non-goals

- No final buy/sell recommendation.
- No executable trading instruction / order ticket / broker payload / execution id.
- No actual Auto Research runtime; no calling of original page functions; no
  triggering of the original AI Research Workflow.
- No Agent Debate (Phase 5M), Decision Packet, Macro Dashboard, UI redesign,
  sidebar cleanup, or read-only shadow integration.
- No live data, LLM, or external API calls.
- No DB / vector store / production persistence.

---

## Guardrails

- Offline / mock-only, deterministic; schema / helper / orchestration-boundary /
  fixture only.
- Every model sets `extra="forbid"`; no `approved_for_execution` or order-ticket
  field can be smuggled in via construction. `approved_for_execution` is **absent**
  (not declared) on every Phase 5L model and is never positively authorized.
- Module requests carry `is_runtime_call=False`; module result refs carry
  `is_placeholder=True` and never fabricate analysis.
- Does not import or modify `app.py`, `pages/*`, `ui_utils.py`, Streamlit,
  `lib/workflow_state.py`, `lib/llm_orchestrator.py`, `lib/data_fetcher.py`,
  `.claude/agents/*`, or any live data-fetch / broker / order module.
- Does not read `research/.workflow_state.json`.
- Phase 4A is not wired in.

---

## Acceptance criteria

1. The default research pack bundle (orchestration boundary) builds
   deterministically from the Phase 5K default opportunity queue, with a
   populated validation summary and `status="planned"`.
2. Short-term candidate selection yields price_volume / news / catalyst / risk /
   evidence required modules.
3. Mid-term candidate selection yields company / financial / price_volume /
   catalyst / risk / evidence required modules.
4. Long-term candidate selection yields macro / theme / company / financial /
   risk / evidence required modules.
5. `research_more` / `insufficient_evidence` candidates promote gap-closing
   modules into the required set.
6. `wait_for_pullback` / `too_extended` candidates require `price_volume_analysis`
   and `risk_review`.
7. `no_trade` / `avoid_too_crowded` candidates produce a review-only minimal pack
   that does not become an executable research-to-trade path.
8. The empty opportunity queue returns a safe empty boundary.
9. The degraded fixture returns warnings and safe placeholder module refs.
10. Module requests are descriptive (`is_runtime_call=False`) and do not call live
    modules; no forbidden imports exist.
11. No `approved_for_execution=True` is positively authorized; no buy/sell/order
    fields are introduced; serialization is deterministic.
12. The test suite
    `scripts/test_reliability_phase_5l_research_pack_orchestration.py` passes; the
    Phase 5K and Phase 5J tests still pass.

---

## Future Phase 5M dependency

The next phase, **Phase 5M — Agent Debate / Decision Workspace Contract** (a
future, not-yet-started phase), will consume the Phase 5L research-pack bundles as
the structured input to an evidence-bound debate and decision-packet workspace.
Phase 5L deliberately stops at the orchestration boundary so that *which* research
runs — and *whether* it leads to a decision — remains explicit and auditable.
**Phase 5M has not started.**
