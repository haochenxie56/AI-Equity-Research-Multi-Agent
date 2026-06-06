# Reliability Phase 5P — Phase 5 Roadmap Decision / Planning

**Date**: 2026-05-27
**Status**: Implemented — awaiting Codex review (planning-only; no runtime changes).
**Type**: Repo-level roadmap decision / planning document.
**Module(s) touched**: None (documentation and state files only).
**Tests added**: None new; Section 31 of `scripts/test_reliability_agent_evaluation.py` updated to reflect the new accepted state.

> **Phase 5P makes no runtime changes.** It does not add a new package,
> a new module, a new helper, a new schema, a new test harness, a new
> Streamlit page, a new live integration, a database, a vector store, a
> file-based persistence layer, a broker connector, an order ticket, an
> external API call, or any pathway that sets `approved_for_execution = True`.
> Phase 5P only writes planning prose and reconciles state files so future
> sessions can pick up Phase 5A safely.

---

## 1. Current Accepted Baseline

The following are accepted as of 2026-05-27:

| Phase Block | Status |
|-------------|--------|
| Phase 0 — Reliability Foundation | Accepted |
| Phase 0.1 — Reliability Hardening | Accepted |
| Phase 0.2 — ToolResult Adapter Planning | Accepted |
| Phase 1A–1G — Adapter / contract / mock roundtrip | Accepted |
| Phase 2A–2K — Schemas, validation aggregator, staleness, critic, eval harness | Accepted |
| Phase 2 Closeout | Accepted |
| Phase 3A–3G — Orchestration, horizon synthesis, macro, debate, DecisionPacket, human review, review loop | Accepted |
| Phase 3 Closeout | Accepted |
| Phase 4A — Reliability Integration Boundary Contract | Accepted (early infrastructure only; **not** the start of Roadmap Phase 4 Memory; **not** wired into the live app) |
| Phase 3R-0..3R-E — Roadmap v4 Phase 3 backfill (Event Intelligence, Trade Plan, Allocation, Option Expression, Closeout) | Accepted |
| Phase 3R Closeout (Phase 3R-E) | Accepted |
| Phase 4M-A — Research Run Memory | Accepted |
| Phase 4M-B — Thesis Memory by Horizon | Accepted |
| Phase 4M-C — Catalyst / News / Earnings Memory | Accepted |
| Phase 4M-D — Allocation Decision Memory | Accepted |
| Phase 4M-E — Option Trade Plan Memory | Accepted |
| Phase 4M-F — Human Feedback Layer | Accepted |
| Phase 4M-G — Agent Evaluation | Accepted |
| Phase 4M-H — Phase 4 Memory Closeout | **Accepted** |

The Streamlit *stale `workflow_state`* issue surfaced during Phase 4M work was
diagnosed and resolved by clearing stale persisted workflow state (see
`research/.workflow_state.json` lifecycle). It was **not** caused by any
Phase 0–4M reliability/memory work, and it is **not** part of Phase 5
deliverables. It is recorded here only as an operational note.

**Phase 5 implementation has not started.** Phase 5P is the formal *start of
planning* for Phase 5. No Phase 5 subphase implementation is performed in this
document.

---

## 2. Relationship Between the Original README App and Roadmap v4

The original README documents a working Streamlit application:

- **Streamlit pages**: Overview, Sector, Scanner, Equity, Financial, PriceVolume.
- **Existing five-step AI workflow**: Sector Analysis → Stock Scanner → Equity
  Research → Financial Analysis → PriceVolume Analysis → Synthesis.
- **Existing live Claude workflow** via `lib/llm_orchestrator.py` calling
  the Anthropic Claude API.
- **Existing workflow state** via `lib/workflow_state.py` persisted to
  `research/.workflow_state.json`.
- **Existing data layer**: `lib/data_fetcher.py` (yfinance primary,
  polygon.io fallback), `lib/valuation.py`, `lib/technical.py`,
  `lib/rotation.py`, `lib/cache_manager.py`.
- **Existing report/cache infrastructure** under `research/` and `data/us/`.

Roadmap v4 extends this **without replacing it**. The current accepted
state shows this clearly: every reliability and memory module added in
Phase 0–4M lives under `lib/reliability/` and is *not* imported by `app.py`,
`pages/*`, `lib/llm_orchestrator.py`, or any other live runtime file.

Therefore Phase 5 must be planned as an **overlay architecture on top of the
existing app**, not as a replacement app. Existing user workflows must
continue to function exactly as documented in the README throughout Phase 5
planning and through Phase 5 implementation phases. Live wiring is **not**
part of Phase 5; it is deferred to a later, explicitly approved, controlled
integration phase.

---

## 3. Phase 5 Positioning: Overlay Architecture, Not App Replacement

Phase 5 is positioned as a **planning / contract / view-model boundary layer**
sitting *between* the existing live app and the accepted reliability + memory
layers. Conceptually:

```
                        ┌─────────────────────────────────────────────┐
                        │   Existing Streamlit App (README, intact)   │
                        │   Overview / Sector / Scanner / Equity /    │
                        │   Financial / PriceVolume                    │
                        │   lib/llm_orchestrator.py                    │
                        │   lib/workflow_state.py                      │
                        │   lib/valuation.py / technical.py /          │
                        │   rotation.py / data_fetcher.py              │
                        └───────────────┬─────────────────────────────┘
                                        │  (existing 5-step workflow runs as
                                        │   it does today; no Phase 5 wiring)
                                        ▼
                        ┌─────────────────────────────────────────────┐
                        │  Phase 5 — Overlay (planning only)          │
                        │                                              │
                        │  • Memory Adapter contract (5A)              │
                        │  • Cockpit / Hub / Decision / Portfolio      │
                        │    ViewModel contracts (5B / 5C / 5D)        │
                        │  • Cockpit UI Planning Boundary (5E)         │
                        │  • Shadow Mode Integration Boundary (5F)     │
                        │  • Fixture Demo Pack (5G)                    │
                        │  • Phase 5 Closeout (5H)                     │
                        └───────────────┬─────────────────────────────┘
                                        │  (read-only handoff via fixtures
                                        │   in Phase 5A–5G; no live calls,
                                        │   no live persistence)
                                        ▼
                        ┌─────────────────────────────────────────────┐
                        │  Accepted Phase 4M Memory Layer              │
                        │  (in-memory Pydantic; no DB, no vector       │
                        │   store, no file persistence)                │
                        │                                              │
                        │  Composed on Phase 3 reliability backbone    │
                        │  + Phase 3R agent skeletons + Phase 4A       │
                        │  Integration Boundary contract (frozen).     │
                        └─────────────────────────────────────────────┘
```

Phase 5 deliverables are **planning / contract / view-model boundary work**
until an explicitly approved later phase opens controlled integration. No
Phase 5 phase touches the live app or live data.

---

## 4. Existing App Capabilities to Preserve

Phase 5 planning must preserve all of these existing behaviors without
modification or regression:

- Five-step automated AI workflow on the **Overview** page.
- The **Sector** page's six-dimensional sector analysis and ETF / rotation
  visualization.
- The **Scanner** page's four-strategy parallel screening and AI cross-strategy
  evaluation.
- The **Equity** page's moat radar, peer comparison, and AI deep-research view.
- The **Financial** page's three-statement table, multi-scenario DCF, and
  relative-valuation peer comparison.
- The **PriceVolume** page's K-line, RSI / MACD / ADX / Bollinger overlay,
  support / resistance, and stop-loss reference.
- Bilingual EN / ZH UX, dark / light theme switching.
- Local Parquet cache via `lib/cache_manager.py`.
- Workflow state persistence at `research/.workflow_state.json` via
  `lib/workflow_state.py`.
- Live Claude API calls via `lib/llm_orchestrator.py` (Anthropic SDK).

None of these are changed by Phase 5 planning. None of these will be wired
into Phase 5 contracts in Phase 5A–5G. Wiring is reserved for a later phase
explicitly approved for controlled integration.

---

## 5. Phase 5 Goals

Phase 5 has three planning-only goals:

1. **Define a stable, offline boundary** between the existing app and the
   accepted Phase 4M memory layer, expressed as adapter / view-model /
   shadow-mode contracts. The boundary must be **non-invasive** — usable by
   the live app *or* not, with no behavior change either way.
2. **Define cockpit / hub / decision-card / portfolio view-model contracts**
   that describe how research and memory artifacts could be rendered to a
   human reviewer, *without* introducing any new live UI page or any
   Streamlit-level integration.
3. **Define a fixture demo pack** that demonstrates the boundary end-to-end
   using deterministic synthetic data — not live data — and that proves the
   overlay can be exercised without touching the live workflow.

Phase 5 *does not* aim to:

- Ship a new UI or new pages.
- Persist memory to disk / DB / vector store.
- Call the Claude API.
- Call any external data API.
- Mutate workflow_state, agent definitions, or prompts.
- Place orders / route trades / approve execution.

---

## 6. Route Comparison

Five distinct overlay strategies were considered for Phase 5A. Each is
evaluated against current accepted state, guardrail safety, and the
overlay-not-replacement positioning above.

### Route A — Persistence / Memory Store Interface Contract

**What it would be**: Define a `MemoryStore` protocol (add/get/list semantics)
and provide an in-memory implementation only; later phases would back the
protocol with SQL / NoSQL / vector / file.

**Pros**:

- Natural follow-up to Phase 4M, which produced in-memory-only records.
- Mirrors Phase 4A's "interface-first, no live backend" pattern.

**Cons**:

- Frames Phase 5A as a *persistence* contract, which is one step closer to
  real persistence than the project is ready for. Even an "interface only"
  framing risks downstream phases interpreting it as authorization to wire
  SQL/files/vectors.
- Does **not** address the live-app overlay problem. It only addresses
  *future* persistence, leaving the existing 5-step Streamlit workflow
  un-served by any Phase 5 contract.
- Naming risk: "Persistence Boundary" was the Phase 4M-H closeout's
  recommendation, but the project has since narrowed Phase 5 to a
  Cockpit / overlay planning boundary — see Phase 4M-H Section 9 for the
  prior recommendation and Phase 5P (this document) for the updated scope.

**Verdict**: Useful eventually, but not the correct shape for the *first*
Phase 5 subphase. Persistence belongs after the overlay shape stabilizes.

### Route B — Investment Cockpit / Review UI Planning Boundary

**What it would be**: Define a planning-only contract for a future cockpit
page (research hub + decision cards + thesis tracker + portfolio panel) that
sits *next to*, not *inside*, the existing six Streamlit pages.

**Pros**:

- Forces clarity about what a human reviewer needs to see across runs:
  research summary, horizon decision cards, thesis evolution, allocation,
  option overlay, human feedback log, agent evaluation calibration.
- Naturally complements Phase 4M memory artifacts.
- Compatible with overlay positioning: a cockpit can be planned without
  being built.

**Cons**:

- Skips the adapter problem: if Phase 5A is just "cockpit UI planning",
  there is no contract yet describing *how the existing five-step workflow
  feeds memory artifacts* to that cockpit.
- Risks producing planning documents disconnected from the runtime entry
  point (`app.py` + the five-step workflow on the Overview page).

**Verdict**: Necessary for Phase 5B / 5C / 5D / 5E, but not the right
*first* Phase 5 subphase. Cockpit contracts depend on a memory-adapter
contract being defined first.

### Route C — Integration Boundary Shadow Mode Planning

**What it would be**: Plan how Phase 4A's `DISABLED / SHADOW / ENFORCED`
boundary contract would be extended into a *shadow mode* runtime adapter,
where the existing workflow runs untouched and the reliability/memory layer
observes side-by-side without affecting outputs.

**Pros**:

- Reuses Phase 4A's mode framework directly.
- Honors the overlay-not-replacement principle by definition: shadow mode
  is *observation only*.

**Cons**:

- Belongs *later* in the Phase 5 sequence, after view-model and adapter
  contracts exist. Without a stable adapter and stable view-models, "shadow
  mode planning" has nothing to compare against.
- Risks early-binding the project to a runtime hook before the contracts
  it shadows are stable.

**Verdict**: Correct as Phase 5F, not as Phase 5A.

### Route D — Cockpit ViewModel Contract Layer

**What it would be**: Define purely-structural Pydantic view-model
contracts describing the cockpit's data needs (CompanyResearchHubViewModel,
HorizonDecisionCardViewModel, ThesisTrackerViewModel,
PortfolioCockpitViewModel, OptionOverlayViewModel) without any UI code.

**Pros**:

- Sharply scoped, easily Codex-reviewable.
- Provides a stable seam for any future cockpit UI without committing to
  one.

**Cons**:

- Has the same gap as Route B alone: no adapter contract describing how
  the existing live workflow + accepted Phase 4M memory artifacts populate
  the view-models.

**Verdict**: Correct as Phase 5B / 5C / 5D, not as Phase 5A.

### Route E — Fixture Demo Pack

**What it would be**: Build a deterministic fixture set demonstrating the
overlay end-to-end (synthetic workflow run → memory adapter → view-models →
shadow-mode comparison output → cockpit render plan).

**Pros**:

- Concrete and demoable.
- Ideal acceptance signal at the end of Phase 5.

**Cons**:

- Premature as Phase 5A: cannot fixture an interface that has not been
  defined yet.

**Verdict**: Correct as Phase 5G, the *final* implementation subphase
before Phase 5 Closeout.

### Comparison summary

| Route | As Phase 5A? | Final Phase 5 role |
|-------|--------------|--------------------|
| A — Persistence boundary | ✗ (too persistence-coded; framing risk) | Deferred until after overlay shape stabilizes |
| B — Cockpit UI Planning Boundary | ✗ (no adapter contract yet) | Phase 5E |
| C — Shadow Mode Planning | ✗ (no contracts to shadow yet) | Phase 5F |
| D — Cockpit ViewModel Contract | ✗ (still no adapter) | Phase 5B / 5C / 5D |
| E — Fixture Demo Pack | ✗ (premature) | Phase 5G |

Therefore Phase 5A must be a **new intermediate route**: an **Existing
Workflow Memory Adapter + Fixture-backed Memory Query Contract**. This
defines (i) a small read-only adapter contract that maps the existing
five-step workflow's outputs onto the accepted Phase 4M memory record
types, and (ii) a fixture-only query interface (no live workflow_state
read, no DB, no vector store) used by all subsequent Phase 5 view-model
contracts.

---

## 7. Recommendation: Phase 5A

> **Phase 5A — Existing Workflow Memory Adapter + Fixture-backed
> Memory Query Contract.**
>
> Phase 5A is **not real persistence implementation.** It is a protocol /
> interface plus a **fixture / mock query boundary only**.

### What Phase 5A is

- A typed adapter contract describing how the existing five-step workflow's
  *already-produced* outputs (sector analysis, scanner candidates, equity
  research, financial analysis, price/volume analysis, synthesis) would
  map onto the accepted Phase 4M memory record types
  (`ResearchRunMemoryRecord`, `HorizonThesisMemoryRecord`,
  `*EventMemoryRecord`, `AllocationDecisionMemoryRecord`,
  `OptionTradePlanMemoryRecord`, `HumanFeedbackMemoryRecord`,
  `AgentEvaluationRecord`).
- A *fixture-backed* query interface (e.g. `MemoryQueryAdapter` Protocol)
  that returns deterministic mock memory records from synthetic fixtures
  only. **No live workflow_state read.** **No DB query.** **No vector
  search.** **No file IO for persistence.**
- A small set of fixture JSON / Python literal definitions used by future
  Phase 5B / 5C / 5D / 5G phases.

### What Phase 5A is **not**

- **Not** a real persistence backend (no SQL, no NoSQL, no file store,
  no vector store).
- **Not** a real workflow_state read (no `lib/workflow_state.py` import in
  any new Phase 5A runtime path; no `research/.workflow_state.json` read).
- **Not** wired into `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or
  any existing live module.
- **Not** a Streamlit integration.
- **Not** an external API call.
- **Not** execution capability — `approved_for_execution` continues to
  remain `False` everywhere it appears.

### Why Phase 5A is the right first overlay step

- It is the *thinnest* overlay that gives every subsequent Phase 5 subphase
  a stable seam to write against.
- It is fixture-backed, so it cannot drift into accidental live integration.
- It composes naturally on the accepted Phase 4M record types without
  inventing new persistence semantics.
- It preserves the README app entirely unchanged.

---

## 8. Phase 5 Subphase Sequence

Phase 5 is sequenced as follows:

1. **Phase 5P — Phase 5 Roadmap Decision / Planning** *(this document)*.
2. **Phase 5A — Existing Workflow Memory Adapter + Fixture-backed Memory Query Contract.**
   Protocol/interface + fixture-only query boundary. No live workflow_state
   read, no DB, no vector store, no persistence, no app wiring, no UI, no
   external API, no execution capability.
3. **Phase 5B — Company Research Hub ViewModel Contract.**
   Defines a `CompanyResearchHubViewModel` Pydantic contract sourced via
   the Phase 5A fixture adapter. No UI. No Streamlit page.
4. **Phase 5C — Horizon Decision Cards + ThesisTracker ViewModel Contract.**
   Defines horizon-keyed `HorizonDecisionCardViewModel` and
   `ThesisTrackerViewModel` contracts that reference Phase 4M thesis /
   debate / decision artifacts via the Phase 5A adapter. No UI.
5. **Phase 5D — Portfolio / TradePlan / Option Overlay ViewModel Contract.**
   Defines `PortfolioCockpitViewModel`, `TradePlanCockpitViewModel`, and
   `OptionOverlayCockpitViewModel`. No UI. No broker. No order ticket.
6. **Phase 5E — Cockpit UI Planning Boundary for Existing Streamlit App.**
   *Planning document only.* Describes how a future cockpit UI could
   render Phase 5B / 5C / 5D view-models *next to* (not inside) the
   existing six pages. No new pages added. No `pages/*` modification.
7. **Phase 5F — Shadow Mode Integration Boundary Planning.**
   *Planning document only.* Plans how the existing five-step workflow
   could be observed in shadow mode by the Phase 4A integration boundary
   (reusing its `DISABLED / SHADOW / ENFORCED` mode framework). No wiring
   is performed. Phase 4A remains frozen.
8. **Phase 5G — Fixture Demo Pack Based on Original App Flow.**
   Deterministic synthetic-fixture pack demonstrating an end-to-end
   overlay traversal (workflow outputs → adapter → memory records →
   view-models → shadow-mode comparison output → cockpit render plan).
   Runs offline. No live workflow.
9. **Phase 5H — Phase 5 Cockpit Boundary Closeout.**
   Closeout / acceptance document covering Phase 5A–5G coverage,
   architectural boundaries, safety notes, test matrix, and next-phase
   recommendation.

A later, explicitly approved, controlled integration phase (referred to here
as *post-Phase 5* until scoped) would be required before any live wiring
is performed.

---

## 9. Non-Goals and Guardrails

### Non-goals for Phase 5

Phase 5 does **not** include any of the following, in any subphase:

- New live Streamlit pages.
- Modification of any existing Streamlit page.
- Modification of the existing five-step workflow on the Overview page.
- Modification of `lib/llm_orchestrator.py` or any Claude API call site.
- Modification of `lib/workflow_state.py` or `research/.workflow_state.json`.
- Modification of `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`,
  `lib/data_fetcher.py`, or `lib/cache_manager.py`.
- Modification of any file under `.claude/agents/*`.
- Modification of any existing live prompt file.
- A real database backend (SQL or NoSQL).
- A real file-based persistence layer for memory records.
- A vector store, embedding pipeline, or similarity index.
- Any live Anthropic SDK call.
- Any external HTTP / API call.
- Any broker / order / execution path.
- Any pathway that sets `approved_for_execution = True`.

### Phase 4A guardrail

Phase 4A (`lib/reliability/integration_boundary.py`) remains accepted as
*early infrastructure* and is **frozen** in its current standalone state.
Phase 5 planning may *reference* Phase 4A's `DISABLED / SHADOW / ENFORCED`
mode framework — particularly in Phase 5F shadow-mode planning — but
Phase 5 must not wire Phase 4A into the live app and must not extend or
modify `integration_boundary.py`.

### Schema guardrail

All Phase 5 view-model contracts must be deterministic Pydantic models. No
free-form LLM-derived content. No fabricated numeric claims. View-models
must reference accepted Phase 4M record IDs or accepted ToolResult IDs by
their existing fields — they must not invent new evidence semantics.

### Approved-for-execution guardrail

Any Phase 5 view-model or contract that mentions an execution intent must
preserve `approved_for_execution = False`. No Phase 5 phase may introduce
a code path that sets `approved_for_execution = True`.

---

## 10. Forbidden Files (Phase 5P and onward through Phase 5G)

Do **not** modify any of these files during Phase 5P or any Phase 5A–5G
subphase. Each Phase 5 subphase document must repeat this list.

- `app.py`
- `pages/*`
- `lib/llm_orchestrator.py`
- `lib/valuation.py`
- `lib/technical.py`
- `lib/rotation.py`
- `lib/data_fetcher.py`
- `lib/workflow_state.py`
- `lib/cache_manager.py` *(read-only conceptually; not modified)*
- `lib/reliability/integration_boundary.py` *(frozen Phase 4A; not modified)*
- `.claude/agents/*`
- Existing live prompt files
- Existing Streamlit UI
- Existing news / Finnhub / data-fetch behavior
- Existing live workflow behavior
- `research/.workflow_state.json` *(not modified by Phase 5 planning)*

---

## 11. Acceptance Criteria for Phase 5P

Phase 5P is a planning-only phase. Acceptance criteria are:

1. **This document exists** at
   `docs/reliability_phase_5p_roadmap_decision.md` and covers:
   current accepted baseline, README-app ↔ Roadmap v4 relationship, overlay
   positioning, existing capabilities to preserve, Phase 5 goals, the route
   comparison (A–E), the Phase 5A recommendation, the full subphase
   sequence, non-goals / guardrails, forbidden files, and acceptance
   criteria.
2. **`docs/ai_dev_state/PROJECT_STATE.md`** has been updated so that:
   - Phase 4M-H Phase 4 Memory Closeout is recorded as **Accepted**.
   - Phase 5P is recorded as the current planning phase (or completed
     planning phase, depending on review status).
   - The full Phase 5 subphase sequence (5A–5H) is recorded under Pending.
   - Prior accepted phase history is preserved.
   - Phase 5A is **not** claimed to have started.
3. **`docs/ai_dev_state/CURRENT_TASK.md`** has been updated so that:
   - The current task is **Phase 5P**.
   - The recommended next phase is **Phase 5A — Existing Workflow Memory
     Adapter + Fixture-backed Memory Query Contract**.
   - No outstanding minor suggestions from Phase 4M-H acceptance are
     carried forward (none exist).
   - The Streamlit stale `workflow_state` issue is noted *only* as a
     resolved operational note, not as a Phase 5 deliverable.
4. **No runtime / app file was modified.** The forbidden-files list above
   was honored.
5. **No DB, no vector store, no file persistence, no external API, no
   broker / order / execution path** was introduced.
6. **State-file phrasing tests pass.** Section 31 of
   `scripts/test_reliability_agent_evaluation.py` was updated to reflect
   the new state (Phase 4M-H accepted; Phase 5P implemented and awaiting
   Codex review; Phase 5A not started). No module / helper behavior was
   modified.

---

## 12. Explicit "No Runtime Changes" Statement

> **Phase 5P makes no runtime changes.**
>
> Phase 5P does not add a new `lib/` module, does not modify any existing
> `lib/` module, does not add or modify any Streamlit page, does not modify
> `lib/llm_orchestrator.py` or `lib/workflow_state.py`, does not change any
> `.claude/agents/*` file, does not add a database / file / vector store
> persistence backend, does not call the Claude API, does not call any
> external API, does not introduce broker / order / execution logic, does
> not enable `approved_for_execution = True` anywhere, and does not start
> Phase 5A implementation.
>
> The only file changes performed under Phase 5P are:
>
> - This new planning document (`docs/reliability_phase_5p_roadmap_decision.md`).
> - State-file reconciliation in `docs/ai_dev_state/PROJECT_STATE.md` and
>   `docs/ai_dev_state/CURRENT_TASK.md`.
> - A documentation-only Section 31 update in
>   `scripts/test_reliability_agent_evaluation.py` so its state-file
>   assertions match the newly accepted Phase 4M-H state and the newly
>   active Phase 5P planning phase. No module behavior is changed by this
>   update; the assertions only describe the state files above.
