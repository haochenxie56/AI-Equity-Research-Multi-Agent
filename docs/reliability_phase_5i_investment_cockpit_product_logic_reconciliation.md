# Reliability Phase 5I — Investment Cockpit Product Logic Reconciliation / Opportunity-first + Horizon-aware Architecture

**Date**: 2026-05-28
**Status**: Implemented — awaiting Codex review (product-logic reconciliation
and roadmap/documentation only; no code implementation of Theme Intelligence,
Opportunity Queue, Auto Research Pack, Agent Debate, or Macro Dashboard; no UI
redesign; no sidebar change; no live wiring; no LLM/API; no DB/vector/persistence;
no broker/order/execution).
**Type**: Planning / product-logic reconciliation document. Supersedes the earlier
Phase 5I "Read-only Shadow Integration" plan as the immediate next step.

> **Phase 5I reconciles the product logic of the Investment Cockpit.** After
> user feedback, the Cockpit must not become a duplicated ticker research page
> or a manual ticker page. It should become an **opportunity-first**,
> **macro/theme-aware**, **horizon-aware** decision cockpit that can eventually
> discover candidates, trigger research, run debate, and produce **review-only**
> decision plans. This phase documents that reconciliation and the revised
> Phase 5I–5S roadmap. It implements **no** Theme Intelligence, Opportunity
> Queue, Auto Research Pack, Agent Debate UI, or Macro Dashboard code. It makes
> **no** sidebar change and **no** UI redesign. It does not start Phase 5J.

---

## 0. Guardrail reminder (read first)

Phase 5I is **product-logic reconciliation and roadmap/documentation only**.

- Do not modify existing live workflow behavior.
- Do not modify existing pages 1–6 (`pages/1_Overview.py`, `pages/2_Sector.py`,
  `pages/3_Scanner.py`, `pages/4_Equity.py`, `pages/5_Financial.py`,
  `pages/6_PriceVolume.py`).
- Do not modify `app.py`, `lib/llm_orchestrator.py`, or `lib/workflow_state.py`.
- Do not modify `.claude/agents/*`.
- Do not call LLMs. Do not call external APIs.
- Do not introduce a DB / vector store / production persistence.
- Do not introduce broker / order / execution capability.
- Do not create orders, order tickets, broker payloads, execution IDs,
  account IDs, order fields, or executable trade instructions.
- `approved_for_execution` must remain `False` or absent wherever relevant and
  must never be positively authorized.
- Do not implement read-only shadow integration.
- Do not implement Theme Intelligence code yet.
- Do not implement Opportunity Queue ViewModel yet.
- Do not implement Auto Research Pack orchestration yet.
- Do not implement Agent Debate UI yet.
- Do not implement Macro Dashboard page yet.
- Do not change sidebar navigation yet, except documentation planning.
- Do not remove Financial / PriceVolume pages yet.

---

## 1. Current product baseline

### 1.1 Original app workflow

The README app today is a fixed, GenAI-assisted research pipeline:

```
Overview (AI Workflow control)
   │
   ▼
Sector Research → Scanner → Equity Research → Financial Analysis → PriceVolume Analysis → Synthesis
   (Step 1)       (Step 2)   (Step 3)          (Step 4)             (Step 5)               (综合结论)
```

Each step runs a code layer (deterministic quantitative computation) plus an
LLM layer (Claude API, JSON output), and the workflow result is persisted to
`research/.workflow_state.json`.

### 1.2 GenAI-assisted, fixed-pipeline research — not full agentic AI

The original workflow is a **GenAI-assisted, fixed-pipeline research workflow**,
not a full agentic "Investment OS." The pipeline order is fixed (sector →
scanner → equity → financial → price/volume → synthesis); the LLM interprets
and narrates deterministic outputs at each step. It does not autonomously
discover themes, dynamically choose which research to run, conduct multi-agent
debate, or branch decisions by horizon. It produces a single synthesized
research conclusion per run.

### 1.3 Financial Analysis and PriceVolume are subordinate under Equity Research

In the revised product model, **Financial Analysis** and **PriceVolume /
Technical** are no longer independent top-level destinations. They are
**sub-surfaces under Equity Research** — they deepen a specific company's
research view (valuation detail; entry/timing detail) rather than being
parallel research modules a user navigates to directly. They remain valuable
*source* analysis; they are simply repositioned beneath Equity Research in the
product hierarchy.

> This phase only **documents** this repositioning. It does **not** remove the
> Financial or PriceVolume pages and does **not** change the sidebar.

---

## 2. Problem statement

The current Cockpit / Company Hub direction has several product-logic problems:

1. **Cockpit risks duplicating Equity Research.** The Phase 5B Company Research
   Hub view, surfaced as the Cockpit's primary path, looks like a second equity
   research page. A user landing on the Cockpit would not understand why it
   exists separately from Equity Research.
2. **The existing AI Research Workflow can over-select already-extended
   winners.** Sector rotation + momentum scanning naturally surfaces names that
   have *already* run. Treating those as buy decisions risks "buying the top."
3. **Macro is currently too buried.** Macro context is embedded inside Sector
   Research, so it cannot act as a first-class gate on *whether* to prefer
   momentum, pullbacks, watchlists, or cash before opportunity selection.
4. **Traditional sector rotation does not capture theme / narrative /
   industry-chain opportunities well enough.** ETF/sector heatmaps miss
   cross-sector themes (AI, space, robotics, nuclear, quantum, data-center
   power) and their industry-chain decomposition.
5. **The user should not have to manually pick a ticker** as the main Cockpit
   path. The Cockpit's primary flow should be opportunity-first (themes →
   opportunities → decisions), not ticker-first (type a symbol → research it).

---

## 3. Revised product architecture

The product splits cleanly into **source research modules** (which produce
*candidate signals* and *evidence*) and the **Investment Cockpit decision
layer** (which interprets, debates, and produces *review-only* decision plans).

### 3.1 Source research modules

These compute facts and produce candidate signals / evidence:

- **Macro Research** *(to be promoted to first-class)*
- **Sector Research**
- **Scanner**
- **Equity Research**
- **Financial Analysis** *(sub-surface under Equity Research)*
- **PriceVolume / Technical** *(sub-surface under Equity Research)*
- **News / Catalyst / Earnings**

### 3.2 Investment Cockpit decision layer

The Cockpit is the **upper decision layer**, not a duplicate source research
page. Its surfaces are:

- **Market Themes**
- **Opportunity Queue**
- **Decision Workspace**
- **Research Snapshot** *(formerly "Company Research Hub" — summarizes source
  modules, does not duplicate them)*
- **Agent Debate**
- **Trade / Allocation Plan**
- **Option Overlay**
- **Feedback / Review**
- **Provenance / Diagnostics**

### 3.3 Separation of responsibilities

| Concern | Owner |
|---------|-------|
| Compute facts, fetch data, run deterministic tools | Source research modules |
| Produce candidate signals (momentum, rotation, screens) | Source research modules |
| Discover/decompose themes; rank opportunities by horizon | Cockpit decision layer |
| Decide *whether* and *when* to act, by horizon | Cockpit decision layer |
| Multi-agent debate / critique of a candidate | Cockpit decision layer |
| Produce **review-only** trade/allocation/option plans | Cockpit decision layer |

---

## 4. Macro-first architecture

### 4.1 Macro becomes a first-class page/input

Macro Research should be promoted from "buried inside Sector Research" to a
**first-class top-level page and a first-class Cockpit input**, evaluated
*before* opportunity selection.

### 4.2 Macro regime gates the preferred posture

The macro regime should influence whether the system prefers:

- **momentum trades**
- **pullback entries**
- **watchlist only**
- **risk-off / cash preservation**
- **long-term accumulation**

Macro does not pick tickers. It sets the posture/lens through which the
Opportunity Queue is generated and ranked.

### 4.3 Macro factors to include

- rates
- inflation
- liquidity
- credit spreads
- VIX / volatility
- market breadth
- dollar
- risk appetite
- earnings cycle
- recession/growth regime (where applicable)

> Phase 5I documents these as future inputs only. No macro computation, data
> fetch, or page is implemented in this phase.

---

## 5. Theme Intelligence / Market Heat architecture

### 5.1 Why traditional sector/ETF heatmaps are insufficient

Traditional sector/ETF heatmaps map money flow onto a fixed GICS-style sector
grid. They cannot:

- capture cross-sector **themes** (AI spans semis, software, utilities/power,
  REIT data centers, industrials);
- decompose a theme into its **industry chain** (compute → memory → optical →
  power/cooling → platform → applications);
- distinguish **narrative** strength from **fundamental confirmation**;
- measure **crowding** / lifecycle stage (early vs. late vs. exhausted);
- explain *why* a name is moving (theme tailwind vs. idiosyncratic).

Themes are the unit of opportunity discovery; sectors are too coarse.

### 5.2 Future Theme Intelligence concepts (documentation only)

| Concept | Meaning (future schema) |
|---------|------------------------|
| **Theme** | A macro narrative spanning multiple sectors (e.g. AI, space). |
| **Subtheme** | A bounded slice of a theme (e.g. AI → HBM memory). |
| **IndustryChainNode** | A node in the theme's value chain (compute, optical, power…). |
| **ThemeHeatSignal** | Aggregate momentum/attention/flow into a theme. |
| **NarrativeSignal** | Strength/recency of the narrative (news, social, sell-side). |
| **FundamentalConfirmationSignal** | Whether earnings/revenue/guidance confirm the narrative. |
| **CrowdingSignal** | Positioning / concentration / froth measure. |
| **ThemeLifecycleStage** | early / accelerating / mature / late / exhausted. |
| **ThemeCandidateTicker** | A ticker mapped to a theme + chain node with horizon-specific scores. |

### 5.3 How themes should be discovered and decomposed

Themes such as **AI, space, biotech, embodied AI, robotics, nuclear, quantum,
data-center power, memory, optical modules** should be discovered from macro +
narrative + flow signals, then decomposed into industry-chain nodes, then each
node mapped to candidate tickers carrying horizon-specific scores.

**Example — AI:**

- compute (accelerators, CPUs)
- memory / HBM
- optical / networking
- data-center power / cooling
- cloud / platform
- enterprise software
- applications
- edge / robotics

**Example — Space:**

- launch
- satellite manufacturing
- satellite communications
- earth observation
- defense space
- components / materials
- ground stations / data services

> These taxonomies are illustrative future content. Phase 5I implements no
> Theme Intelligence schema or code.

---

## 6. Avoiding "buying the top"

A high-heat theme does not imply a good entry. The product must separate the
following concepts so a candidate can be *interesting* yet *not buyable now*:

| Concept | Question it answers |
|---------|---------------------|
| **Theme Heat Score** | How hot is the theme right now? |
| **Entry Quality Score** | Is *this* entry good right now (timing/structure)? |
| **Crowding Risk** | How crowded / over-owned is the trade? |
| **Valuation Stretch** | How extended is valuation vs. fundamentals? |
| **Pullback Required** | Does a healthier entry require a pullback? |
| **Earnings Confirmation Needed** | Must earnings confirm before acting? |

**Key principle:** a candidate can have **high Theme Heat** but **low Entry Quality**.
High heat is a reason to *research*, not a reason to *buy*.

The system should distinguish these decision states for a candidate:

- `trade_now`
- `wait_for_pullback`
- `breakout_watch`
- `research_more`
- `watch_for_valuation`
- `no_trade`
- `avoid_too_crowded`

---

## 7. Horizon-aware Opportunity Queue

### 7.1 Three horizon-specific queues, not one list

The Opportunity Queue is **not** a single ranked list. It is **three
horizon-specific queues** plus cross-cutting queues:

- **Short-term Trade Queue**
- **Mid-term Position Queue**
- **Long-term Investment Queue**

Cross-cutting queues:

- **Watch / Wait**
- **Research More**
- **No Trade / Avoid**

### 7.2 Same ticker, different decisions by horizon

The **same ticker may appear in multiple queues with different horizon
decisions**. A name can be a valid `trade_now` short-term momentum trade while
being `watch_for_valuation` long-term and `wait_for_earnings_confirmation`
mid-term. Horizon fit is a first-class dimension.

### 7.3 Per-candidate, per-horizon fields

Every candidate should carry, **per horizon**:

- `opportunity_score`
- `horizon_fit_score`
- `entry_quality_score`
- `crowding_risk`
- `evidence_coverage`
- `thesis_status`
- `review_trigger`
- `next_action`
- `decision_label`

### 7.4 Decision labels by horizon

**Short-term:**

- `trade_now`
- `wait_for_pullback`
- `breakout_watch`
- `event_trade_watch`
- `too_extended`
- `no_trade`

**Mid-term:**

- `position_candidate`
- `accumulate_on_pullback`
- `research_more`
- `wait_for_earnings_confirmation`
- `thesis_improving`
- `thesis_unconfirmed`
- `no_trade`

**Long-term:**

- `investment_candidate`
- `watch_for_valuation`
- `compounder_watch`
- `quality_but_expensive`
- `thesis_durable`
- `thesis_insufficient`
- `no_trade`

### 7.5 Overextended candidates are not auto-rejected

Overextended candidates are **not** automatically rejected. Depending on
evidence, they may become `wait_for_pullback`, `watch`, long-term-only,
`research_more`, or `no_trade`. Agent discretion is allowed for horizon fit,
but **every decision must be evidence-first and validated**.

---

## 8. Original AI Research Workflow as candidate source

The original five-step AI Research Workflow is **not discarded**. It is
repositioned as a **candidate source**, not a final decision engine:

- Its sector-rotation / momentum candidates may be valid **short-term trades**.
- They must still pass **Entry Quality / Crowding / Macro / Evidence**
  validation before any decision.
- They **feed the Opportunity Queue**; they do **not** directly produce buy
  decisions.

In other words: the workflow's `recommendation` output becomes an input
*signal* to the Cockpit decision layer, subject to macro gating, entry-quality
scoring, crowding checks, and evidence validation, with horizon-specific
labeling — never an automatic buy.

---

## 9. Revised Phase 5 roadmap

The earlier Phase 5I "shadow-integration-first" path is **replaced**. The
revised Phase 5 sequence is:

| Phase | Title |
|-------|-------|
| **Phase 5I** | Investment Cockpit Product Logic Reconciliation / Opportunity-first + Horizon-aware Architecture *(this document)* |
| Phase 5J | Theme Intelligence / Market Heat Schema |
| Phase 5K | Horizon-aware Opportunity Queue ViewModel |
| Phase 5L | Auto Research Pack Orchestration Boundary |
| Phase 5M | Agent Debate / Decision Workspace Contract |
| Phase 5N | Cockpit UI v0.2 Opportunity-first Redesign |
| Phase 5O | Macro Dashboard v0.1 |
| Phase 5P | Source Page Navigation Cleanup |
| Phase 5Q | Human Feedback UI v0.1 |
| Phase 5R | Product UX Polish / Demo Readiness |
| Phase 5S | Phase 5 Productization Closeout |

> **Numbering note:** "Phase 5P" here denotes the **Source Page Navigation
> Cleanup** phase in the revised forward roadmap. It is distinct from the
> already-accepted historical "Phase 5P — Phase 5 Roadmap Decision / Planning"
> recorded in `PROJECT_STATE.md`. The reused letter refers to two different
> milestones; the historical accepted phase is unchanged.

The previously-listed "Phase 5I — Read-only Shadow Integration" is no longer the
immediate next step. Shadow integration may still happen later, but only after
the opportunity-first / horizon-aware product logic is established.

---

## 10. Impact on current Cockpit UI

- The current **Phase 5H.1 page remains a fixture-backed preview**. It should be
  treated as a **temporary / demo product shell**, not the final cockpit.
- The future UI should shift from the current Phase 5H.1 tab order:

  ```
  Overview/Safety → Company Hub → Horizon Cards → ThesisTracker
      → Portfolio/TradePlan → Option Overlay
  ```

  to the opportunity-first order:

  ```
  Overview/Safety → Market Themes → Opportunity Queue → Decision Workspace
      → Research Snapshot → Agent Debate → Trade/Allocation Plan
      → Option Overlay → Feedback/Review → Provenance/Diagnostics
  ```

- **Company Research Hub** should be renamed/repositioned as **Research Snapshot
  / Company Research Snapshot**. It should **summarize** source modules, not
  duplicate them.

> Phase 5I documents this future shift only. It does not redesign the UI, does
> not reorder tabs, and does not rename any surface in code.

---

## 11. Sidebar / source module planning

- **Financial Analysis** and **PriceVolume** should eventually be **removed from
  the top-level sidebar**, because they are now sub-surfaces under Equity
  Research.
- **Macro Research** should become a **first-class top-level page**.
- This phase **documents** these navigation intentions but does **not**
  implement any sidebar change and does **not** remove the Financial or
  PriceVolume pages.

The actual navigation cleanup is deferred to the future "Phase 5P — Source Page
Navigation Cleanup" (revised-roadmap milestone in §9), and the Macro Dashboard
page itself is deferred to "Phase 5O — Macro Dashboard v0.1."

---

## 12. Non-goals

Phase 5I does **not**:

- Implement any Theme Intelligence code.
- Implement any Opportunity Queue (ViewModel or otherwise).
- Redesign the UI.
- Change the sidebar.
- Integrate with the live workflow.
- Implement read-only shadow integration.
- Call any LLM or external API.
- Introduce any DB / vector store / persistence.
- Introduce any broker / order / execution capability.
- Remove the Financial or PriceVolume pages.
- Modify existing pages 1–6, `app.py`, `lib/llm_orchestrator.py`, or
  `lib/workflow_state.py`.

---

## 13. Guardrails

- `approved_for_execution` remains `False` / absent everywhere and is never
  positively authorized.
- Evidence-first: every decision must reference evidence and pass validation.
- Review-only: the Cockpit produces decision plans for human review, never
  executable instructions.
- Human-in-the-loop at every decision boundary.
- No investment advice.
- No automatic execution.

### 13.1 Forbidden files (must not be modified by Phase 5I)

- `app.py`
- `pages/1_Overview.py`
- `pages/2_Sector.py`
- `pages/3_Scanner.py`
- `pages/4_Equity.py`
- `pages/5_Financial.py`
- `pages/6_PriceVolume.py`
- `lib/llm_orchestrator.py`
- `lib/workflow_state.py`
- `lib/valuation.py`
- `lib/technical.py`
- `lib/rotation.py`
- `lib/data_fetcher.py`
- `lib/cache_manager.py`
- `lib/reliability/integration_boundary.py` *(frozen Phase 4A)*
- `.claude/agents/*`
- existing live prompt files
- `research/.workflow_state.json`

---

## 14. Acceptance criteria

Phase 5I is accepted when:

1. Product logic is reconciled: source research modules vs. Cockpit decision
   layer responsibilities are clearly separated.
2. The future Phase 5 roadmap is updated (revised Phase 5I–5S sequence present).
3. Horizon-aware, opportunity-first principles are explicit (three horizon
   queues + cross-cutting queues + per-horizon decision labels).
4. Original app responsibilities vs. Cockpit responsibilities are clearly
   separated; the original AI Research Workflow is described as a **candidate
   source**, not a final decision engine.
5. Macro / theme intelligence is established as a **future first-class input**
   (macro-first gating + Theme Intelligence concepts), with no code implemented.
6. Non-goals and guardrails are explicit; `approved_for_execution` is never
   positively authorized.
7. State files mark Phase 5H.1 **accepted** and Phase 5I **awaiting review**,
   and point next to **Phase 5J — Theme Intelligence / Market Heat Schema**.
8. Phase 5J is **not** started.

---

## 15. Validation

```bash
git status --short
python3 scripts/test_reliability_phase_5i_product_logic_reconciliation.py
# (Phase 5H.1 preview test only if the page or its docs changed:)
python3 scripts/test_reliability_phase_5h_cockpit_ui_preview.py
```

Phase 5I is documentation / product-logic only. No runtime module, no Streamlit
page, no live wiring, no LLM/API, no DB/vector/persistence, and no
broker/order/execution path is introduced.

---

## 16. Next step

**Codex review of Phase 5I.** After Phase 5I is accepted, the next recommended
phase is **Phase 5J — Theme Intelligence / Market Heat Schema** (schema /
contract only; offline / mock-only; no live wiring; no DB/vector; no
LLM/API; no broker/order/execution). **Phase 5J has not started.**
