# Reliability Phase 5J — Theme Intelligence / Market Heat Schema

**Date**: 2026-05-28
**Status**: Implemented — awaiting Codex review (schema / contract / helper /
fixture only; offline / mock-only; no live wiring; no DB / vector store /
persistence; no LLM / external API; no broker / order / execution).
**Type**: Reliability-layer schema / contract module + deterministic fixtures.
**Module**: `lib/reliability/phase5_theme_intelligence.py`
**Test**: `scripts/test_reliability_phase_5j_theme_intelligence.py`

> **Phase 5J defines the evidence-first schema for detecting market themes,
> measuring market heat, decomposing industry chains, and representing theme
> candidate tickers.** It is the **upstream input layer** for the future
> **Phase 5K — Horizon-aware Opportunity Queue ViewModel**. Phase 5J does
> **not** decide buy/sell, does **not** produce a final opportunity queue, does
> **not** compute entry quality, and does **not** retrieve any live data. It
> defines deterministic structures and fixture examples only.

---

## 0. Guardrail reminder (read first)

Phase 5J is **schema / contract / helper / fixture only**.

- Offline / mock-only; no live wiring.
- Do not modify existing live workflow behavior.
- Do not modify `app.py`, pages 1–7, `ui_utils.py`, `lib/llm_orchestrator.py`,
  `lib/workflow_state.py`, or `.claude/agents/*`.
- Do not call LLMs. Do not call external APIs.
- Do not introduce a DB / vector store / production persistence.
- Do not introduce broker / order / execution capability; no order tickets,
  broker payloads, execution IDs, account IDs, order fields, or executable
  trade instructions.
- `approved_for_execution` must remain `False` / absent everywhere and must
  never be positively authorized.
- Do not implement the Opportunity Queue ViewModel yet (Phase 5K).
- Do not implement Auto Research Pack orchestration, Agent Debate, or a Macro
  Dashboard.
- Do not implement read-only shadow integration.
- Do not implement any UI / sidebar change.

---

## 1. Purpose

Phase 5J provides the deterministic, evidence-first **data layer** that the
Investment Cockpit needs to become *opportunity-first* rather than
*ticker-first*. Before the system can rank opportunities by horizon (Phase 5K),
it must be able to:

1. **Detect themes** — cross-sector narratives (AI, space, robotics, nuclear,
   quantum, biotech, embodied AI, data-center power, memory, optical modules).
2. **Measure market heat** — a container of scored components describing how
   "hot" a theme/subtheme is right now (NOT a buy signal).
3. **Decompose the industry chain** — break a theme into value-chain nodes and
   their upstream/downstream relationships.
4. **Represent candidate tickers** — map tickers to a theme / subtheme / chain
   node with a role, evidence coverage, heat contribution, and crowding
   context.

Phase 5J implements all of this as **Pydantic schema + deterministic fixture
builders + a validation summary**. No decisions are made and no live data is
fetched.

---

## 2. Relationship to Phase 5I product-logic reconciliation

Phase 5I ("Investment Cockpit Product Logic Reconciliation / Opportunity-first
+ Horizon-aware Architecture") established, as documentation, that:

- The Cockpit is **opportunity-first, not ticker-first**.
- **Theme discovery must happen before candidate ranking.**
- **Macro regime and market heat are first-class inputs.**
- Traditional sector / ETF heatmaps are useful but **insufficient**.
- The system must capture **narrative / theme / industry-chain** opportunities.
- **Theme heat is not the same as entry quality.**
- **High theme heat must not automatically imply buy/trade.**
- A later phase (Phase 5K) maps theme records into short / mid / long
  opportunity queues.

Phase 5I §5 listed these future Theme Intelligence concepts as *documentation
only* (`Theme`, `Subtheme`, `IndustryChainNode`, `ThemeHeatSignal`,
`NarrativeSignal`, `FundamentalConfirmationSignal`, `CrowdingSignal`,
`ThemeLifecycleStage`, `ThemeCandidateTicker`). **Phase 5J turns those concepts
into actual schema** — and only schema. It carries forward every Phase 5I
guardrail (evidence-first, review-only, human-in-the-loop, no investment
advice, `approved_for_execution` never authorized).

---

## 3. Relationship to Roadmap v4

Roadmap v4 positions the Investment Cockpit as an **overlay** on top of the
existing six-page Streamlit research app — not a replacement. The original
five-step AI Research Workflow (Sector → Scanner → Equity → Financial →
PriceVolume → Synthesis) is a **candidate source**, not a final decision
engine. Phase 5J sits in the revised Phase 5 sequence as the schema layer that
precedes the Opportunity Queue:

| Phase | Title | Phase 5J relationship |
|-------|-------|-----------------------|
| Phase 5I | Product Logic Reconciliation | Establishes the requirement |
| **Phase 5J** | **Theme Intelligence / Market Heat Schema (this doc)** | **Defines the input schema** |
| Phase 5K | Horizon-aware Opportunity Queue ViewModel | Consumes Phase 5J records |
| Phase 5L+ | Auto Research Pack / Agent Debate / UI redesign / Macro Dashboard / … | Downstream |

---

## 4. Why sector / ETF heatmaps are insufficient

Traditional sector / ETF heatmaps map money flow onto a fixed GICS-style sector
grid. They are useful but **insufficient** because they cannot:

- capture **cross-sector themes** (AI spans semis, software, utilities/power,
  data-center REITs, industrials);
- decompose a theme into its **industry chain** (compute → memory → optical →
  power/cooling → platform → applications);
- separate **narrative** strength from **fundamental confirmation**;
- measure **crowding** and **lifecycle stage** (emerging vs. crowded vs.
  fading);
- explain *why* a name is moving (theme tailwind vs. idiosyncratic).

Themes are the unit of opportunity discovery; sectors are too coarse. Phase 5J
makes the **theme** (and its industry-chain decomposition) a first-class object.

---

## 5. Theme Intelligence concepts

Phase 5J schema (all in `lib/reliability/phase5_theme_intelligence.py`):

| Concept | Schema |
|---------|--------|
| Top-level snapshot | `ThemeIntelligenceSnapshot` |
| Theme universe | `ThemeUniverseSnapshot` |
| Theme | `ThemeRecord` |
| Subtheme | `SubthemeRecord` |
| Industry-chain node | `IndustryChainNode` |
| Candidate ticker | `ThemeCandidateTicker` |
| Heat signal | `ThemeHeatSignal` |
| Narrative signal | `NarrativeSignal` |
| Fundamental confirmation signal | `FundamentalConfirmationSignal` |
| Crowding signal | `CrowdingSignal` |
| Heat score container | `ThemeHeatScore` |
| Lifecycle stage | `ThemeLifecycleStage` (literal) |
| Evidence summary | `ThemeEvidenceSummary` |
| Risk warning | `ThemeRiskWarning` |
| Discovery source | `ThemeDiscoverySource` |
| Validation summary | `ThemeIntelligenceValidationSummary` |
| Entry-quality (future) | `EntryQualityScorePlaceholder` (not computed) |

Every model sets `model_config = ConfigDict(extra="forbid")`, so no
`approved_for_execution` or order-ticket field can be smuggled in.

### 5.1 Theme

`ThemeRecord` carries: `theme_id`, `name`, `description`, `lifecycle_stage`,
`heat_score`, `discovery_sources`, `source_signals`, `narrative_signals`,
`fundamental_confirmation_signals`, `crowding_signals`, `subthemes`,
`industry_chain_nodes`, `candidate_tickers`, `evidence`, `warnings`.

### 5.2 Subtheme

`SubthemeRecord` carries: `subtheme_id`, `parent_theme_id`, `name`,
`description`, `heat_score`, `lifecycle_stage`, `chain_node_ids`,
`candidate_tickers`, `warnings`. A subtheme is a bounded slice of a theme
(e.g. AI → HBM memory).

### 5.3 Industry-chain node

`IndustryChainNode` carries: `node_id`, `parent_theme_id`, optional
`parent_node_id`, `name`, `role_in_chain`, `upstream_node_ids`,
`downstream_node_ids`, `representative_tickers`. Nodes form a directed value
chain (e.g. memory/optical/power feed compute; compute feeds cloud → enterprise
software → applications; edge/robotics downstream of compute).

---

## 6. Market Heat concepts

### 6.1 Theme vs. subtheme vs. industry-chain node

- A **theme** is a macro narrative spanning multiple sectors.
- A **subtheme** is a bounded slice of a theme.
- An **industry-chain node** is a position in the theme's value chain.

A candidate ticker may map to **multiple subthemes and multiple chain nodes**
(`subtheme_ids` and `chain_node_ids` are lists), reflecting names with
exposure across several parts of a theme.

### 6.2 Candidate ticker roles

`ThemeCandidateTicker.role` is one of: `leader`,
`second_derivative_beneficiary`, `laggard`, `supplier`, `platform`,
`speculative`, `unknown`. A single theme can simultaneously host leaders,
second-derivative beneficiaries, laggards, suppliers, platforms, and
speculative names. Each candidate carries its own `evidence`
(`ThemeEvidenceSummary`), `heat_contribution`, `crowding_level` /
`crowding_signal`, `warnings`, and `notes`.

### 6.3 Narrative signals

`NarrativeSignal` describes the strength/recency of a narrative cluster:
`narrative_cluster`, `mention_intensity`, `source_type`, optional `timestamp`,
`explanation`, `evidence_ref`.

### 6.4 Fundamental confirmation signals

`FundamentalConfirmationSignal` describes whether earnings / revenue / guidance
/ revisions / orders / backlog / capex commentary **confirm** the narrative:
`confirmation_type`, `confirmation_direction`
(`confirming` / `mixed` / `disconfirming` / `unconfirmed` / `unknown`),
`strength`, `explanation`, `evidence_ref`. Fixture-only commentary; no live
fundamentals are fetched.

### 6.5 Crowding signals (kept separate from heat)

`CrowdingSignal` is **deliberately separate** from `ThemeHeatScore`. It carries
`crowding_level` (`low` … `extreme` / `unknown`) plus fixture-only qualitative
**placeholders**: `momentum_overextension`, `valuation_stretch`,
`volume_climax`, `rsi_placeholder`, `adx_placeholder`,
`ma_distance_placeholder`. Crowding is an argument *against* chasing a hot
theme; it is not part of the heat score.

### 6.6 Theme lifecycle stages

`ThemeLifecycleStage` is one of: `emerging`, `accelerating`, `consensus`,
`crowded`, `fading`, `unknown`. An emerging or data-sparse theme is `unknown`,
not zero.

---

## 7. Heat score semantics

`ThemeHeatScore` is a **deterministic container** of components, not a live
calculator:

- `total_score`
- `price_momentum_component`
- `volume_component`
- `breadth_component`
- `narrative_component`
- `fundamental_confirmation_component`
- `freshness_component`
- `crowding_adjustment` (a penalty/adjustment magnitude; the full crowding
  assessment lives on `CrowdingSignal`)
- `score_status`: `complete` / `partial` / `unknown`
- `is_buy_signal`: `Literal[False]` (always `False`; setting `True` raises)

`derive_heat_score_status()` classifies a score by component presence:
all material components present → `complete`; some present → `partial`; none →
`unknown`. `build_theme_heat_score()` builds the container and, only when the
status is `complete` and no `total_score` was supplied, sets `total_score` to a
deterministic sum of the supplied components minus any crowding adjustment
(simple arithmetic on supplied inputs — not a market calculation). Partial /
unknown states never fabricate a total.

### 7.1 Why heat score is not a buy signal

**A high theme heat score is a reason to *research*, not a reason to *buy*.**
Heat measures how hot a theme is; it says nothing about whether *this* entry is
good *now*. A theme can be very hot and yet a poor entry (crowded,
valuation-stretched, late-lifecycle). The schema enforces this separation:

- `CrowdingSignal` is a distinct model from `ThemeHeatScore`.
- `ThemeHeatScore.is_buy_signal` is hard-coded `False`.
- No `ThemeHeatScore` / `ThemeRecord` field is named `buy`, `sell`,
  `trade_now`, `recommendation`, `decision`, or `approved_for_execution`.
- **Entry-quality scoring** — the concept that decides whether a hot theme is
  buyable — is deferred to **Phase 5K** and appears here only as the
  non-calculated `EntryQualityScorePlaceholder` (`computed=False`,
  `deferred_to_phase="5K"`).

---

## 8. Fixture examples

All fixtures are **deterministic examples**. Sample ticker symbols are
illustrative fixture examples only — **not** live market claims,
recommendations, or current facts. No API is called. Builders:
`build_default_theme_intelligence_snapshot()`, `build_ai_theme_fixture()`,
`build_space_theme_fixture()`, `build_degraded_theme_fixture()`,
`build_empty_theme_intelligence_snapshot()`.

### 8.1 AI fixture example

`build_ai_theme_fixture()` builds an `accelerating`, `complete`-heat AI theme
with industry-chain nodes for **compute, memory / HBM, optical / networking,
data-center power / cooling, cloud / platform, enterprise software,
applications, edge / robotics** and subthemes for AI Compute, HBM Memory, and
Data-Center Power & Cooling. Candidate tickers cover every role (leader,
second-derivative beneficiary, supplier, platform, laggard, speculative), and
at least one candidate (NVDA, a fixture example) maps to **multiple subthemes
and multiple chain nodes**. The HBM Memory subtheme deliberately omits the
fundamental-confirmation component to demonstrate a `partial` heat score.

### 8.2 Space fixture example

`build_space_theme_fixture()` builds an `emerging` space theme with chain nodes
for **launch, satellite manufacturing, satellite communications, earth
observation, defense space, components / materials, ground stations / data
services** and subthemes for Launch, Satellite Communications, and Defense
Space. The Satellite Communications subtheme demonstrates a `partial` heat
score and `emerging` lifecycle.

### 8.3 Degraded / emerging theme example

`build_degraded_theme_fixture()` builds an **embodied AI / humanoid robotics**
theme with `unknown` lifecycle, an `unknown` heat score (no components),
`none`/partial evidence coverage, a single not-yet-decomposed chain node, and
high-severity `missing_evidence` / `narrative_only` warnings. It demonstrates
that **missing evidence yields partial/unknown status, never fabricated
completion**, and that an emerging theme is `unknown`, not zero.

---

## 9. Validation / safe behavior

`validate_theme_intelligence_snapshot()` returns a
`ThemeIntelligenceValidationSummary` with deterministic counts (themes,
subthemes, chain nodes, candidates, heat-score status distribution,
themes-with-warnings, unknown-lifecycle, dangling chain-node references) and
safety-invariant flags (`no_buy_signal_fields`, `no_executable_order_fields`,
`approved_for_execution_absent`). Behavior:

- **Missing evidence → partial/unknown**, never fabricated completion.
- **Empty universe is valid** (`is_safe_empty=True`) — a safe empty snapshot.
- A candidate ticker may appear in **multiple subthemes / chain nodes**.
- A theme may contain leaders, second-derivative beneficiaries, laggards,
  suppliers, platforms, and speculative names together.
- A **high heat score does not imply `trade_now` or buy** — there is no such
  field.
- A **crowded theme is represented separately** (via `CrowdingSignal` /
  `crowding_level`) from opportunity.
- **No `approved_for_execution=True`** is ever positively authorized.
- No investment advice. No final candidate queue decisions.

---

## 10. Non-goals

Phase 5J does **not**:

- Decide buy / sell.
- Generate a final opportunity queue or ranked candidate list (Phase 5K).
- Compute entry quality (Phase 5K).
- Retrieve any live data; call any LLM or external API.
- Introduce any DB / vector store / persistence.
- Introduce any broker / order / execution capability or executable order
  field.
- Modify the live workflow, `app.py`, pages 1–7, `ui_utils.py`,
  `lib/llm_orchestrator.py`, `lib/workflow_state.py`, or `.claude/agents/*`.
- Implement Opportunity Queue ViewModel, Auto Research Pack, Agent Debate,
  Macro Dashboard, UI redesign, sidebar cleanup, or shadow integration.

---

## 11. Guardrails

- `approved_for_execution` remains `False` / absent everywhere and is never
  positively authorized (`extra="forbid"` makes it structurally
  unconstructable on every Phase 5J model).
- No executable order fields (`order_type`, `time_in_force`, `broker_route`,
  `account_id`, `execution_id`, `quantity_to_execute`, etc.).
- Heat score is not a buy signal; entry quality is deferred to Phase 5K.
- Evidence-first; missing evidence is surfaced as partial/unknown.
- Deterministic and offline: no `datetime.now`, no randomness, no file I/O, no
  network.
- Review-only, human-in-the-loop, no investment advice.

### 11.1 Forbidden files (not modified by Phase 5J)

- `app.py`
- `pages/1_Overview.py` … `pages/7_Investment_Cockpit.py`
- `ui_utils.py`
- `lib/llm_orchestrator.py`
- `lib/workflow_state.py`
- `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`,
  `lib/data_fetcher.py`, `lib/cache_manager.py`
- `lib/reliability/integration_boundary.py` *(frozen Phase 4A)*
- `.claude/agents/*`
- existing live prompt files
- `research/.workflow_state.json`

---

## 12. Acceptance criteria

Phase 5J is accepted when:

1. `lib/reliability/phase5_theme_intelligence.py` defines the Theme
   Intelligence / Market Heat schema (theme, subtheme, industry-chain node,
   candidate ticker, signals, heat-score container, lifecycle, evidence,
   warnings, validation summary).
2. Deterministic fixtures build: default snapshot, AI theme, Space theme,
   degraded/emerging theme, and a safe empty snapshot.
3. AI and Space themes include the required subthemes / chain nodes.
4. Heat score supports `complete` / `partial` / `unknown`; crowding is
   separate; heat is not a buy signal.
5. A candidate ticker can map to multiple subthemes / chain nodes.
6. Empty snapshot is safe; serialization is deterministic.
7. No `approved_for_execution=True`; no order-ticket fields; no live
   data / LLM / API / DB / vector / persistence / broker / order / execution.
8. Phase 5J exports are wired into `lib/reliability/__init__.py`.
9. Documentation (this file) and the test
   (`scripts/test_reliability_phase_5j_theme_intelligence.py`) pass.
10. State files mark Phase 5I **accepted** and Phase 5J **implemented;
    awaiting Codex review**, pointing next to **Phase 5K**, without claiming
    Phase 5K has started.

---

## 13. Future Phase 5K dependency

**Phase 5K — Horizon-aware Opportunity Queue ViewModel** will consume Phase 5J
`ThemeRecord` / `ThemeCandidateTicker` records and map them into short / mid /
long opportunity queues, applying macro gating, entry-quality scoring, crowding
checks, and evidence validation. **Entry quality is computed in Phase 5K, not
here.** Phase 5K is a **future** phase and **has not started**.

---

## 14. Validation

```bash
git status --short
python3 scripts/test_reliability_phase_5j_theme_intelligence.py
```

Phase 5J is schema / contract / helper / fixture only. No runtime app file, no
Streamlit page, no live wiring, no LLM / API, no DB / vector / persistence, and
no broker / order / execution path is introduced.
