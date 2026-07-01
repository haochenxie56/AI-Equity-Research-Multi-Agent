# AI Investment OS — Master Architecture, Roadmap, and Project Memory Memo

**Version:** Master Memo v4 (2026-07-01)
**Supersedes:** Master Memo v3 (2026-06-21; revised 2026-06-24, baseline `6cc972e9a`). Master Memo v2 (2026-06-17, baseline `79433d5`) before it.
**Purpose:** Cross-session migration, architecture preservation, roadmap alignment, and phase-planning baseline.
**Scope:** Consolidates completed work through **Phase 8B — CandidateScreeningAgent** (`main @ f17f4e572`) — the **sixth** production foundation agent — together with its deterministic **candidate-eligibility-gate enabler** (`lib/candidate_eligibility.py`). Records the Phase 8 architectural realignment (World 1 ↔ World 2 activation, the agent map, the PM layer, the confidence framework, and the alternative-data sources). The 2026-07-01 revision advances the foundation-agent roster (five → **six**), the baseline, and the "next" pointer (now the **Degradation-Visibility Layer**) to match `README.md` and `PROJECT_STATE.md` after the candidate-eligibility gate enabler and CandidateScreeningAgent shipped.
**Status convention:** `README.md` and the live phase docs (`docs/ai\_dev\_state/PROJECT\_STATE.md`, `CURRENT\_TASK.md`) are the current authoritative sources. This memo is **P1 context** — it explains and records, but yields to the live docs on any conflict.

> \*\*Disclaimer:\*\* This project is a research and decision-support system. It does not provide investment advice, does not place orders, and must remain review-only unless a future phase explicitly changes the scope under separate safety review.

\---

## 0\. How to Use This Memo

This memo solves the project's recurring context-drift problem. Use it as:

1. **A new-session startup context** for Claude / Claude Code / Codex (see §11 startup block).
2. **An architecture map** of the live product path, the reliability/evidence stack, and the agent framework that connects them.
3. **A roadmap-memory source** for why each phase existed and what it must not be confused with.
4. **A design-principle guardrail** to prevent future phases from weakening review-only safety, the numeric firewall, evidence discipline, or auditability.

### 0.1 Source Authority

|Priority|Source|Use|
|-|-|-|
|P0|Latest `README.md`|Product definition, feature inventory, architecture, safety principles, tech stack.|
|P0|`docs/ai\_dev\_state/PROJECT\_STATE.md` + `CURRENT\_TASK.md`|Authoritative completed-state snapshot, current next phase, per-phase detail with commit hashes.|
|P1|This memo (v4)|Cross-session context, design rationale, agent-framework architecture, anti-drift guardrails. Yields to P0 on conflict.|
|P2|Codex review records under `docs/`|Independent reality check + mutation-probe history per phase.|
|P3|Master Memo v1/v2/v3, historical phase PDFs|Historical evolution only. Do not override current docs.|

### 0.2 Supersession Notes

* Anything in v1/v2/v3 that contradicts v4 is stale. v2's baseline was `79433d5` (Phase 7C); v3's baseline was `6cc972e9a` (Phase 8B ThemeIntelligenceAgent docs closeout). The current baseline is **`f17f4e572`** (Phase 8B CandidateScreeningAgent docs-hash follow-up; phase merge `e6c5be89a`, feature commit `b6daea492`; candidate-eligibility-gate enabler merge `f78ef606f`, feature `b1310ec1e`). *(Historical: the original v3 was cut at `a19b862`, the MacroRegimeAgent-production baseline.)*
* v2 framed the system as an "Investment OS / decision-support stack." v3/v4 keep that, but add the **Phase 8 realignment**: the long-term shape is an **AI Fund workflow** — foundation agents → a horizon-aware PM layer → a MasterPM — with the Streamlit app as the **AI-PM reporting surface**, not the decision tool.
* Phases 6A–7C, Valuation Refactor v1, Anchor Intelligence v2–v2.5, Thesis Ingestion MVP, Legacy Red Suite Archival, Phase 8A, Phase 8B-0, MacroRegime / MoneyFlow / MarketStructure / SectorRotation / ThemeIntelligence agents, the candidate-eligibility-gate enabler, and **CandidateScreeningAgent**: all closed and merged (see v2/v3 + PROJECT\_STATE.md).

\---

## 1\. Project Overview \& Goal

**One sentence:** A personal US-equity **AI Fund workflow system** that turns deterministic market/valuation/technical/flow computation into horizon-aware, evidence-bound, human-confirmed investment judgments — surfaced through an Investment Cockpit and never placing an order.

### 1.1 It is a workflow system, not a dashboard

The Streamlit app is the **reporting and confirmation surface for an AI PM team**, not the place where decisions are made. The decision pipeline is:

```
Data layer (raw sources + deterministic processed signals)
   ↓
Foundation agents (one per signal domain; code computes facts, LLM synthesizes implications)
   ↓
PM layer (ShortTermPM · MidTermPM · LongTermPM — consume foundation findings by horizon)
   ↓
MasterPM (cross-horizon / cross-agent conflict arbitration, portfolio-level synthesis)
   ↓
UI: AI-PM reporting dashboard + human confirmation (review-only)
```

### 1.2 The "two-world" problem this realignment solves

The project had drifted into **two disconnected halves**:

* **World 1 — the live Streamlit app:** deterministic producers (`macro\_regime`, `market\_internals`, `opportunity\_ranker`, `equity\_valuation`, …) feeding pages directly. Real, shipping, used daily.
* **World 2 — the dormant reliability/evidence stack:** `ToolResult` / `AgentResult` / `EvidenceRef` schemas, validators, evidence store, prompt contracts (`lib/reliability/`). Built across Phases 0–4M, fully tested, but **never wired into the live path** — `reliability\_enabled=False`, integration boundary a pass-through.

**Decision (Phase 8):** do **not** rebuild. Activate World 2 by adding **connective tissue** — a thin agent framework (`lib/agent\_framework/`) that wraps World-1 deterministic outputs as evidence, runs an evidence-constrained LLM call, validates the result against the evidence, and emits a unified `AgentOutput`. The first real agent (MacroRegimeAgent) proves the pattern end-to-end; five more follow it.

### 1.3 The corrected LLM boundary

> \*\*Code computes facts and numbers. The LLM synthesizes actionable implications from those facts — and never emits a numeric value.\*\*

A foundation agent's deterministic side produces every number (regime votes, confidences, GEX/DEX, scores, RS gaps, comparison-table tiers). The LLM is handed those numbers as **evidence** and asked only: *what does this mean for positioning, across horizons?* Its prose judgment must cite evidence IDs and must contain no digits, `%`, `$`, or metric tokens.

> **Sharpened by CandidateScreeningAgent (Phase 8B):** the boundary is not only "no numbers." Where a deterministic *decision* exists — the frontrunner, the `no_clear_winner` verdict — **code decides it and the LLM cannot override it.** The LLM's job narrows to *explaining which coded differences are decisive*, translating trade-offs into horizon fit, and stating invalidation conditions. It never picks the primary and never flips a code-set `no_clear_winner`.

\---

## 2\. Architecture Principles (the non-negotiables)

These are enforced by code, tests, and review. New phases must not weaken them.

1. **Numeric firewall.** Code computes every number. The LLM never invents valuations, indicators, scores, probabilities, or market data. Numeric/metric claims in findings must cite an `EvidenceRef`.
2. **`evidence\_refs` must never be empty.** `agent\_result\_to\_agent\_output` flattens evidence from `findings\[].evidence + risks\[].evidence` and **raises** if the result is empty. An agent with no evidence is not an agent.
3. **`approved\_for\_execution` is always `False`.** No broker, no order, no payload, no account ID, no quantity-to-execute. Review-only by design.
4. **All `lib.reliability` imports are lazy.** Inside `lib/agent\_framework/` and `lib/agents/`, every `lib.reliability` / `lib.llm\_orchestrator` import is **inside the function that needs it**; module level uses only `TYPE\_CHECKING`. Importing the agent framework must never trigger the \~52-module eager `lib.reliability.\_\_init\_\_` (subprocess import-guard test enforces this — now proven for CandidateScreeningAgent's extra `lib.candidate\_eligibility` / `lib.theme\_transmission` imports too).
5. **`\_repair\_llm\_response()` pattern for every agent.** LLMs (especially `claude-sonnet-4-6`) flatten the `AgentResult` shape. Because the schemas are `extra="forbid"`, a flat response is rejected. A **structural repair layer** sits between extraction and validation: it wraps top-level `text`/`evidence` into `findings`, injects missing `agent\_name`/`run\_id`, and coerces a float `confidence` into an `AgentConfidence` object. **Reuse this for all future agents.**
6. **`valid\_until = end\_of\_today\_iso()` for all agents.** Foundation agents are part of the daily Cockpit refresh; their outputs expire end-of-day (UTC 23:59:59). Longer-lived validity is a PM-layer concern, not a foundation-agent one.
7. **Numeric-free judgment.** `findings\[0].text` (the PM-facing one-sentence judgment) must contain no digits / `%` / `$` / metric tokens; it is extracted as the **first complete sentence** (≤ 400 chars), not hard-truncated mid-sentence.
8. **Append-only audit trails.** Daily snapshots, anchor archive, agent-output JSONL, ingest logs: append, never rewrite. Corrections append a new record with provenance.
9. **Tighten-only market internals.** Fragility can annotate / tighten short-term entry / warn; it can never flip macro regime, loosen a gate, or authorize buying.
10. **Exclude, do not down-weight.** An untrustworthy anchor/peer set is excluded and labeled, never hidden behind a continuous weighting knob. *(CandidateScreeningAgent extends this: the tradability penny-guard uses discrete `quality_capped` labels that annotate — the eligibility gate already did the excluding — never a continuous multiplier.)*
11. **Never fabricate a number** (historical or live). Backfill only recomputes computable anchors under filing-lag rules; analyst anchors are never invented for past dates. *(CandidateScreeningAgent extends this to fields: `short_crowding` / `options_structure` / `beta` / dollar-ADV have no backing field, so they are marked `unavailable` and excluded from the ranking key — a data source is never invented; `market_cap`, usually absent, yields `unknown` and never a fabricated tier.)*
12. **Access-path-matrix first.** Before unifying a producer or wiring an agent into a page, map the caller-contract matrix (who needs network, who is network-free, who can write cache, who touches snapshots).
13. **Code decides deterministic verdicts; the LLM explains, never overrides.** Where a decision can be computed deterministically (the CandidateScreeningAgent frontrunner, `no_clear_winner`, the slate skeleton), **code owns it** and persists it as evidence / `supporting_data` before the LLM runs. The LLM cannot pick the primary or flip `no_clear_winner`; it explains which coded differences are decisive and gives horizon-fit + invalidation. This is the operational form of the corrected LLM boundary (§1.3).
14. **Fail-closed by-ticker joins.** When an agent must join two producers' rows (e.g. CandidateScreeningAgent joining `CandidateSignal` fields onto `OpportunityCard` via the `signals=` kwarg), the join is **exact by ticker and fails closed** — an unmatched / missing / wrong-ticker row resolves to a hard-unknown → rejected verdict, **never** silently eligible, and never cross-contaminates another ticker's evaluation.
15. **Degradation is defensive-vs-runtime-avoidable, and both must be visible.** Two kinds of degradation exist and must be distinguished: **(1) defensive fail-closed degradation** when data is genuinely absent (missing field, no key, no per-ticker signal) — this is the numeric firewall doing its job and **MUST be preserved**; and **(2) runtime-avoidable degradation** where a key / tier / field / cache / network was simply not wired — which, from a trading standpoint, is a **BUG**. Today both hide in `supporting_data` (`signal_basis` / `no_trade_reason` / `*_unavailable` / degraded coverage / `greeks_unavailable` / `vintage_mismatch` / `insufficient_data`). The **Degradation-Visibility Layer** (next phase) surfaces both; a later **runtime zero-degradation acceptance protocol** (defined once the 8B roster is complete) will codify (2)=bug with a documented exemption list for (1).

\---

## 3\. Agent Map (current confirmed state)

The agent map is the Phase-8 target shape. **Six foundation agents are implemented (MacroRegimeAgent, MoneyFlowAgent, MarketStructureAgent, SectorRotationAgent, ThemeIntelligenceAgent, CandidateScreeningAgent); the remaining four (StockResearch / ValuationDebate / TechnicalEntry / SectorResearch / RiskOverlay) are planned wrapping targets** — each wraps an existing deterministic World-1 producer. The roster below is the **canonical target roster** (aligned with `README.md`); a few provisional names from earlier drafts (MarketInternalsAgent / RotationAgent / RelativeStrengthAgent / CandidateAgent / OpportunityAgent / ValuationAgent / TechnicalAgent / ThesisAgent / AnchorHistoryAgent) have been reconciled into it — some of those (relative_strength, opportunity_ranker, thesis_monitor, anchor_migration) are **deterministic inputs** to a canonical agent, not standalone agents.

### 3.1 Data layer

|Tier|Contents|
|-|-|
|**Raw sources**|yfinance (price/VIX/ETF), FRED (rates/credit/dollar/releases/liquidity), Finnhub (news/earnings-calendar/social), **Quiver Quantitative** (dark pool / congress / insider / institutional), **Massive Options = Polygon** (options chain w/ Greeks/IV/OI).|
|**Processed signals (deterministic)**|`macro\_regime.classify\_regime` → `MacroRegimeResult` (with vote fields); `market\_internals` fragility; `theme\_baskets`/`rotation`/`theme\_transmission`; `relative\_strength`; `candidate\_generator`/`signal\_engine`; `opportunity\_ranker`; **`candidate\_eligibility`** (four-state gate — the CandidateScreeningAgent enabler); `equity\_valuation`/`valuation\_router`/`valuation\_diagnosis`; `anchor\_archive`/`anchor\_migration`; **`gex\_dex.compute\_gex\_dex`** + **`quiver\_fetcher.compute\_dark\_pool\_signal`**.|

### 3.2 Foundation agents (roster mapped to deterministic producers)

|#|Group|Agent (canonical)|Deterministic input (code computes)|LLM synthesizes|Status|
|-|-|-|-|-|-|
|1|Market env|**MacroRegimeAgent**|`classify\_regime` (regime, votes, data\_coverage) + snapshot regime history; 3 confidences|regime implications for positioning across 3 horizons|✅ **built** (`eabf0c2d` + fixes)|
|2|Market env|**MarketStructureAgent**|`market\_internals` fragility reading (injected from Cockpit Step 4; no second compute)|deterioration/health read, tighten-only context|✅ **built** (`8792343f9`)|
|3|Market env|**MoneyFlowAgent**|`gex\_dex` (GEX/DEX/walls/squeeze) from Massive + `compute\_dark\_pool\_signal` from Quiver|dealer-positioning \& flow implications; squeeze/pin context|✅ **built** (`760f356a3`)|
|4|Opportunity|**SectorRotationAgent**|`theme\_baskets` + `theme\_transmission` + full offense/defense (O/D) reading|which themes/waves capital is rotating through|✅ **built** (`fbf0cc41d`)|
|5|Opportunity|**ThemeIntelligenceAgent**|`theme\_transmission` (transmission order, cluster, per-ticker chain role) + `constituent\_rs`|theme-wave / capital-transmission narrative|✅ **built** (`5ecfb7875`)|
|6|Opportunity|**CandidateScreeningAgent** (v1: momentum / RS-gap)|`opportunity\_ranker` (3-horizon scores/status) + `candidate\_generator` / `signal\_engine` dual-track + **`candidate\_eligibility`** four-state gate|per-theme relative candidate slate: which differences are decisive, horizon fit, invalidation (no numbers, cannot pick primary)|✅ **built** (`e6c5be89a`; enabler `f78ef606f`)|
|7|Stock research|**StockResearchAgent**|`thesis\_monitor` + thesis card library + equity-research artifacts|business/thesis read; intact vs broken; what changed|📋 planned|
|8|Stock research|**ValuationDebateAgent**|`equity\_valuation`/`valuation\_router`/`valuation\_diagnosis` + `anchor\_migration` + reverse DCF (Phase 8D)|valuation-role implications, adversarial valuation (no numbers)|📋 planned (Phase 8D)|
|9|Stock research|**TechnicalEntryAgent**|`technical` indicators + S/R + `order\_advisor` entry strategy|entry-timing / risk context|📋 planned|
|10|Stock research|**SectorResearchAgent**|sector research (macro/policy/supply-chain/cycle context)|sector positioning / cycle read|📋 planned|
|11|Risk control|**RiskOverlayAgent**|portfolio / position-sizing / fragility risk overlay|portfolio-level risk caution|📋 planned|

> Caveat: this is the **canonical target roster** (11 foundation agents across market-environment / opportunity-discovery / stock-research / risk-control). Rows 1–6 are committed, shipped work; rows 7–11 are wrapping targets whose exact confidence formulas and scoping are decided at each agent's STEP 0, not here. Deterministic producers such as `relative\_strength`, `opportunity\_ranker`, `thesis\_monitor`, and `anchor\_migration` are **evidence inputs** to the agents above, not standalone agents.

#### 3.2.1 The candidate-eligibility-gate enabler (deterministic, not an agent)

CandidateScreeningAgent shipped in **two phases**, mirroring the prior deterministic enablers (`constituent\_rs`, `FragilityReading.offense\_defense`) that preceded their agents:

* **Enabler first (merge `f78ef606f`, feature `b1310ec1e`):** `lib/candidate\_eligibility.py` — a deterministic, **LLM-free** four-state gate (`eligible` / `conditional` / `ineligible` / `unknown`) per `(ticker, horizon)` over an `OpportunityCard` + its matching `CandidateSignal`. It is **not an agent** (no LLM, no `AgentOutput`, no slate, no Cockpit hook). Six gates in two tiers — **HARD** `thesis` / `eps` / `valuation` / `event` (may reach `ineligible`) + **SOFT** `liquidity` / `distribution` (never `ineligible`) — horizon-asymmetric (`eps` / `valuation` / `event` differ across short/mid/long; a near-earnings print gates SHORT only, never LONG). Aggregation precedence: hard-fail → hard-unknown → any-conditional → soft-unknown(→conditional) → eligible. It carries the **numeric-firewall provenance guard** `_forward_pe_is_usable` (rejects `None` / non-numeric / `bool` / `<= 0`), which plugs the leak where `fetch_fundamental` stamps `data_source["valuation"]="live"` on an invalid `forwardPE` and `_valuation_percentile` then defaults the percentile to 0.5 — a defaulted 0.5 is read as `VALUATION_UNKNOWN`, never a real pass. 18 tests / 87 assertions, fully offline, real dataclass instances. Codex REJECT (provenance leak) → APPROVE. Phase doc `docs/reliability_candidate_eligibility_gate.md`.

* **Agent body (merge `e6c5be89a`, feature `b6daea492`):** the LLM agent that CONSUMES the gate — see §7.11.

> **Strategy identity — v1 = ONE fixed strategy: MOMENTUM / RS-GAP.** The primary ranking key is the per-horizon RS composite gap **within a theme**. Future strategies (leader play, high-beta elasticity) will be **separate agents** (e.g. `LeaderScreeningAgent`) listed **alongside** this one in the roster — never parameters of it. v1 deliberately has **no pluggable strategy interface**.

### 3.3 PM layer

|Tier|Horizon|Consumes|
|-|-|-|
|**ShortTermPM**|1–4 weeks|each foundation agent's SHORT finding + short\_confidence|
|**MidTermPM**|1–3 months|each foundation agent's MID finding + mid\_confidence|
|**LongTermPM**|6–18 months|each foundation agent's LONG finding + long\_confidence|
|**MasterPM**|cross-horizon|the three PM syntheses; arbitrates conflicts; portfolio-level view; emits no execution instruction|

Foundation agents already emit **three findings (SHORT / MID / LONG)** with three confidences precisely so the PM tier can consume by horizon. The PM layer and MasterPM are **future phases** — not yet built.

### 3.4 UI layer

The Investment Cockpit is the AI-PM reporting surface. **All six shipped foundation agents are wired in additively** via `_run_refresh`: each is a key-gated (`_has\_llm\_api\_key()`), fail-closed hook that reuses already-computed deterministic signals (no second fetch/compute) and stores its result under a dedicated session key — `macro\_regime\_agent\_output` (Step 1), `money\_flow\_agent\_output` (Step 1, after the macro hook), `market\_structure\_agent\_output` (after Step 4, reusing the fragility reading), `sector\_rotation\_agent\_output` (after the MarketStructure hook, reusing the themes list + O/D reading), `theme\_intelligence\_agent\_output` (Step 4, after the SectorRotation hook, reusing `_themes\_list` only — no offense/defense), and `candidate\_screening\_agent\_output` (Step 4, immediately after the ThemeIntelligence block, reusing `_cards` + `_candidates` + `_themes\_list`; a **per-theme loop** over 2–3 ACTIVE themes, each theme in its own try/except so one theme's failure isolates; the value is a dict keyed by `theme\_key`). The existing `macro\_regime\_result` state and every downstream consumer are untouched; no agent aborts the refresh. **CandidateScreeningAgent is a session-state-only hook with no new visible widget this phase** — the reporting / degradation-visibility UI is the next phase. PM-layer reporting UI is a future phase.

\---

## 4\. Current UI Pages

The app currently has 11 pages. Each page is accessible from the sidebar. The UI role is AI PM reporting — pages display agent outputs and processed signals, not raw data.

| Page # | File | Title (EN) | Purpose | Agent/Data consumed |
|---|---|---|---|---|
| 1 | `1_Overview.py` | AI Workflow Control Center | Five-step automated research workflow (sector → stock → equity → financial → price/volume → synthesis); the system's origin, now a research-layer component. | `workflow_state` + `llm_orchestrator` workflow; processed signals via `ui_utils` loaders. No World-2 agent. |
| 2 | `2_Sector.py` | Sector Analysis & Rotation | Rotation workbench: macro environment, rotation signal, sector heat map, ETF trend vs SPY, stock ranking tiers, sub-sectors. | `rotation` + `theme_baskets` (+ `theme_transmission`); processed signals only. |
| 3 | `3_Scanner.py` | Stock Scanner | Four-strategy scan + an AI candidate-signal layer over the scan universe. | `candidate_generator` / `signal_engine` / `macro_regime` / `theme_baskets`; processed signals + LLM eval. No World-2 agent. |
| 4 | `4_Equity.py` | Equity Research (个股研究) | Company deep-dive in four tabs: moat/peers/valuation-diagnosis, financials (DCF/relative), price & volume, news & sentiment. | `equity_valuation` / `valuation_router` / `valuation_diagnosis` / `financial_tab` / `pv_tab`; processed signals + LLM research. No World-2 agent. |
| 5 | `5_Financial.py` | Financials → Equity | Redirect stub — Financial analysis was merged into Page 4 as a tab; the file is kept to preserve sidebar structure. | Static / no agent. |
| 6 | `6_PriceVolume.py` | Price & Volume → Equity | Redirect stub — Price & Volume was merged into Page 4 as a tab; the file is kept to preserve sidebar structure. | Static / no agent. |
| 7 | `7_Investment_Cockpit.py` | Investment Cockpit | ⭐ Main entry. One-click refresh aggregates macro regime, market-internals fragility, theme rotation, and the opportunity queue (20 candidates × 3 horizons); writes the daily snapshot. | **MacroRegimeAgent · MoneyFlowAgent · MarketStructureAgent · SectorRotationAgent · ThemeIntelligenceAgent · CandidateScreeningAgent** (six additive, key-gated hooks → `*_agent_output`; CandidateScreening is a per-theme dict) + `macro_regime` / `market_internals` / `opportunity_ranker` / `theme_baskets` / `candidate_eligibility` processed signals. |
| 8 | `8_Macro_Dashboard.py` | Macro Dashboard | Live macro-regime classification + Market Internals workbench (fragility trend / components) + liquidity / rates / inflation / credit / volatility / breadth tabs. | `macro_data` / `macro_regime` / `market_internals`; processed signals only. |
| 9 | `9_Trading_Desk.py` | Trading Desk | Holdings thesis monitor, code-computed entry/exit levels (entry v4) with an LLM narrative, opportunity watch. Review-only. | `holdings` / `thesis_monitor` / `order_advisor` / `equity_valuation`; processed signals + LLM narrative. No World-2 agent. |
| 10 | `10_Thesis_Library.py` | Thesis Library | Curated external research → one-LLM-call-per-argument structured thesis cards → browse / manage. Isolated from scoring / ranking / snapshot / anchor. | `thesis_ingestion` (extraction LLM; isolated). Not a foundation agent. |
| 11 | `11_Audit_Review.py` | Audit Review | Read-only review of the daily snapshot audit trail: coverage, fragility-level history, per-ticker status timeline, "Actionable Now" follow-through. | `audit_query` (read-only snapshot reads); processed signals only. No agent. |

> Only the Investment Cockpit (page 7) currently consumes World-2 agent outputs — now **six** of them (MacroRegimeAgent, MoneyFlowAgent, MarketStructureAgent, SectorRotationAgent, ThemeIntelligenceAgent, CandidateScreeningAgent). Every other page consumes deterministic processed signals and/or page-local LLM calls. As the foundation-agent roster (§3.2) fills in, more pages move from "processed signals only" to "agent outputs."

\---

## 5\. Confidence Calculation Framework

MacroRegimeAgent computes **three deterministic confidences** (no LLM) and persists them as evidence before the LLM runs. This is the template; other agents have **agent-specific** confidence formulas, but the short/mid/long triad and the "compute-before-LLM, persist-as-evidence" discipline are the pattern.

|Confidence|Formula|Meaning|Source data|
|-|-|-|-|
|**short\_confidence**|`abs(votes\_risk\_on − votes\_risk\_off) / votes\_total`|how decisively the live indicators agree right now|`MacroRegimeResult.votes\_\*` (added this phase; degraded path → 0.0)|
|**mid\_confidence**|consecutive same-regime days mapped through a saturating curve `\_MID\_CONFIDENCE\_BREAKPOINTS` `\[(0,0.1)(1,0.2)(3,0.4)(5,0.6)(7,0.75)(10,0.9)(14,1.0)]`|regime stability over recent history|`audit\_query.load\_all\_meta()` snapshot history; **Guard A** current-regime degrade→0.0; **Guard B** unknown/degraded history day is a hard streak break|
|**long\_confidence**|`data\_coverage × short\_confidence`|data-foundation solidity discounted by directional clarity|`MacroRegimeResult.data\_coverage` × short|

The two ToolResults persisted per run are `classify\_regime` (the regime signals) and `macro\_regime\_confidence` (the three confidences + vote counts + `consecutive\_same\_regime\_days`) — so every number the LLM might reference is evidence-bound.

### 5.1 The six shipped instantiations (short / mid / long)

The template above generalizes into six agent-specific triads. Every one computes all three confidences in code and persists them as a ToolResult **before** the LLM runs.

|Agent|short|mid|long|
|-|-|-|-|
|**MacroRegimeAgent**|vote-agreement ratio|consecutive same-regime days (saturating curve)|`data\_coverage × short`|
|**MoneyFlowAgent**|`signals\_agree\_count / 3` (degraded→0)|`strength\_map × direction\_valid` (strong 1.0 / moderate 0.6 / weak 0.3)|`0.0` (intraday-to-3-week signal)|
|**MarketStructureAgent**|`coverage × clarity` (coverage = 1 − degraded\_core/5; clarity = min(points,4)/4)|trailing elevated+ run via saturating curve; `vintage\_mismatch`/snapshot fallback → `min(interpolated, 0.1)` **cap not floor**|`0.0`|
|**SectorRotationAgent**|`theme\_coverage × stage\_confirmed rate`|`theme\_coverage × momentum\_dispersion × wave\_clarity`|`0.0`|
|**ThemeIntelligenceAgent**|`theme\_coverage × role\_resolution` (all-constituent denominator — honest coverage)|`theme\_coverage × asymmetry\_strength`|`0.0` (defers to StockResearch)|
|**CandidateScreeningAgent**|`coverage × short\_clarity` where `coverage` = usable/total (eligible-or-conditional with live RS) and `short\_clarity = min(lead / \_RS\_GAP\_DECISIVE\_PCT, 1.0)` (0 when `no\_clear\_winner[short]`; 1.0 for a lone decisive eligible name)|`coverage × mid\_clarity` (mirrors short)|`0.0` (defers to StockResearch / ValuationDebate)|

CandidateScreeningAgent is the **sixth agent's instantiation** of the shipped coverage×clarity template — the same "compute-before-LLM, persist-as-evidence" discipline, with `long = 0.0` because a per-theme momentum screen has nothing to say over 6–18 months (that is StockResearch / ValuationDebate's lane). All values `round(…, 6)`.

\---

## 6\. Data Sources

### 6.1 Already integrated (free / existing)

|Source|Role|Key|
|-|-|-|
|**yfinance**|price / VIX / ETF proxies|none|
|**FRED**|rates, credit (HY OAS), broad dollar, NFP/CPI/PPI, money-market liquidity|`FRED\_API\_KEY` (free)|
|**Finnhub**|earnings calendar (good-news-sold), general news, social sentiment|`FINNHUB\_API\_KEY` (free)|

### 6.2 New (paid alternative data — Phase 8B-0)

|Source|Plan|Provides|Key|
|-|-|-|-|
|**Quiver Quantitative**|Hobbyist (\~$25/mo)|dark pool, congressional trades, insider trades, hedge-fund/institutional positions|`QUIVER\_API\_KEY`|
|**Massive Options** (= Polygon under the hood; v3 snapshot shape)|Starter (\~$29/mo)|options chain with Greeks / IV / OI → GEX/DEX|`MASSIVE\_API\_KEY` (`.env.example` renamed POLYGON→MASSIVE, +QUIVER)|

* **Excluded: Unusual Whales API (\~$125/mo)** — unnecessary for the GEX strategy; `gex\_dex.py` computes dealer exposure from the Massive chain directly.
* **Free-tier caveat:** Massive free tier has **no Greeks/OI** → live GEX/DEX needs Starter; the layer degrades gracefully (Greeks `None`, `greeks\_unavailable: free tier`) until then. Quiver `prev\_close` field names still need live-API confirmation (parsers read defensively, fail-closed 50/50 when absent).

### 6.3 MoneyFlowAgent data strategy (shipped — `760f356a3`)

GEX / DEX / OI-walls / gamma-squeeze monitor from **Massive** (`gex\_dex.compute\_gex\_dex`, with `prior\_result` DEX-trend for condition C) + dark-pool buy/sell pressure from **Quiver** (`compute\_dark\_pool\_signal`). Both are pure deterministic aggregators; the agent wraps them as evidence and asks the LLM for the flow/positioning implication. MoneyFlowAgent is the third production foundation agent (three confidences: short = signals-agree count / 3, mid = strength × direction-valid, long = 0.0).

### 6.4 The market-cap / dollar-ADV gap (CandidateScreeningAgent driver)

CandidateScreeningAgent's tradability penny-guard wants a real `market_cap` tier and a dollar-ADV read, but **`market_cap` is usually absent in production** (it exists only on the v1 `FundamentalSignals` shim) and **dollar-ADV has no field at all**. So the reachable penny-guard collapses to the `candidate_type == ALT_SIGNAL` proxy (a name that bypassed the funnel's $2B market-cap / $10M-ADV floor). This is honest — the flag is only raised on positive marginal evidence, never fabricated — but its real-world coverage is thin. It is a **driver for a future live market-cap / ADV channel** and part of why the Degradation-Visibility Layer comes next.

\---

## 7\. Completed Phases (commit hashes + key files)

Earlier phases (Original five-step workflow → Phase 0–4M reliability/validation/debate/memory → Phase 5 cockpit productization → 6A–6C → 7A–7C → Valuation Refactor v1 → Anchor Intelligence v2–v2.5 → Thesis Ingestion MVP → Legacy Red Suite Archival) are recorded in **Master Memo v2** and `PROJECT\_STATE.md`. The Phase-7D-onward record:

### 7.1 Phase 7D Block A — Snapshot Audit Query Interface (merged `5a57850`)

Read-only audit layer over `data/snapshots/opportunities\_\*.jsonl`. **`lib/audit\_query.py`** (`load\_all\_meta`, `load\_all\_opportunities`, `query\_status\_transitions`, `compute\_actionable\_follow\_through`, `compute\_fragility\_series`; `MetaRecord`/`OpportunityRecord` tolerant of schema drift; no signal engine, no network, fail-closed) + **`pages/11\_Audit\_Review.py`** (bilingual A–E sections). 10 tests; AST + runtime import-guard that audit never pulls `signal\_engine`. *Audit track and live track stay separate by construction.*

### 7.2 Phase 8A — Agent Framework Foundation (merged `f6a0f74`)

The connective tissue activating World 2. 7 new files; no existing file modified:

* **`lib/agent\_framework/agent\_output.py`** — `AgentOutput` dataclass (embeds `Optional\[AgentResult]`, NOT a Pydantic subclass), `validate\_judgment`, `agent\_result\_to\_agent\_output` (raises on empty evidence), JSONL persistence at `data/agent\_outputs/<agent\_id>/<YYYY-MM-DD>.jsonl`.
* **`lib/agent\_framework/agent\_runner.py`** — `run\_llm\_agent` 11-step pipeline (ToolResults → `EvidenceStore` at `data/agent\_evidence/<agent\_id>/<run\_id>/` → evidence packet → constrained prompt → Claude → parse+validate → `AgentOutput` → JSONL). `AgentRunError` on validation severity-`error`; fail-closed rule-based fallback on LLM/parse failure.
* **`lib/agent\_framework/world\_adapter.py`** — `llm\_output\_to\_tool\_result` + `processed\_signals\_to\_tool\_result` (dataclass→dict via `asdict`).
* **`lib/agents/macro\_regime\_agent.py`** — initial smoke test.
* 11 tests (§8A.1–§8A.11); §8A.10 subprocess import-guard.

### 7.3 Phase 8B-0 — New Data Source Ingestion Layer (merged `69d7c9f`)

3 new lib modules + 3 test files; only existing edits were a 1-line `signal\_engine` comment + `.env.example` key rename:

* **`lib/quiver\_fetcher.py`** — `fetch\_dark\_pool` / `fetch\_congress\_trades` / `fetch\_insider\_trades` / `fetch\_hedge\_fund\_positions` (fail-closed, `@st.cache\_data`) + `compute\_dark\_pool\_signal` (pure aggregator).
* **`lib/massive\_options\_fetcher.py`** — `fetch\_options\_chain(ticker, expiry\_filter)` → existing Phase 2E `OptionChainSnapshot`/`OptionContractSnapshot` (`source="massive"`); paginated ≤5; per-contract `try/except`; free-tier graceful.
* **`lib/gex\_dex.py`** — pure deterministic `compute\_gex\_dex(chain, expiry\_filter, prior\_result=None)` (GEX/DEX sums, OI walls, 3-condition gamma-squeeze monitor); zero `lib.reliability` imports; `regime\_summary` numeric-free.
* 24 tests (Quiver 6 + Massive 5 + GEX/DEX 13).

### 7.4 Phase 8B — MacroRegimeAgent Production Implementation (merged `eabf0c2d`, + fixes `8b84f17a`, `a19b862`)

First foundation agent upgraded smoke→production:

* **`lib/macro\_regime.py`** — additive `votes\_risk\_on` / `votes\_risk\_off` / `votes\_total` on `MacroRegimeResult`; `classify\_regime` populates them (degraded path stays 0). `macro\_state.serialize\_regime` unaffected (field whitelist).
* **`lib/agents/macro\_regime\_agent.py`** (full rewrite) — `\_compute\_short\_confidence` / `\_compute\_mid\_confidence` (Guard A/B + `\_MID\_CONFIDENCE\_BREAKPOINTS`) / `\_compute\_long\_confidence`; `run\_macro\_regime\_agent(regime\_signals=None, \*, horizon, ticker, snapshot\_dir, macro\_data)` accepts `MacroRegimeResult`/dict/`None`; builds two ToolResults; dynamic task instruction with a **REQUIRED OUTPUT FORMAT** JSON example; outer fail-closed guard; lazy `lib.reliability`.
* **`pages/7\_Investment\_Cockpit.py`** — additive, key-gated, fail-closed hook → `macro\_regime\_agent\_output`.
* **Post-merge fixes:**

  * `8b84f17a` — REQUIRED OUTPUT FORMAT block in the prompt + judgment now extracted as **first complete sentence** (≤400 chars, `\_JUDGMENT\_MAX\_LEN` 200→400) instead of mid-sentence truncation.
  * `a19b862` — **`\_repair\_llm\_response()`** structural repair layer in `agent\_runner.py` (wraps flat `text`/`evidence` into `findings`, injects `agent\_name`/`run\_id`, coerces float `confidence`), wired between `\_extract\_json\_obj` and `parse\_and\_validate\_agent\_result`.
* Tests: §8B-M1–M11 **24/24** (MacroRegimeAgent suite) + agent framework suite **15/15** (§8A.1–§8A.15, incl. §8A.12–14 repair-unit + §8A.15 end-to-end). Phase 6A regression 337/337.

### 7.5 Step 3 Narrative Disk Cache + `\_meta` extension + Cockpit cold-start hydration (merged `a2e43cd3` / `ffe9e1e2` / `3eb4a8912`)

Three small infrastructure ships between the MacroRegimeAgent production merge and the next agents:

* **Narrative disk cache** (`a2e43cd3`) — `llm\_narrative\_match` results persist at `data/narrative\_cache/<TICKER>/<regime>\_<fp>.json` (prompt-aligned fingerprint, TTL 24h, atomic write, only `data\_source="live"` persisted); the `@st.cache\_data` layer stays the hot path. 27 tests.
* **`\_meta` extension** (`ffe9e1e2`) — three deterministic `classify\_regime` fields (`key\_signals` / `opportunity\_posture` / `confidence`) persisted into the daily snapshot `\_meta` block, with a pre-`try` collision guard; `MetaRecord` gains the three `.get()`-defaulted fields. 7 parity checks. The prerequisite for full Section-A cold-start hydration.
* **Cockpit cold-start hydration** (`3eb4a8912`) — `lib/cockpit\_hydration.py::hydrate\_cockpit\_from\_snapshot` re-reads the latest daily snapshot into Section A + Section C on restart with empty `session\_state` (runs at most once, atomic, fail-closed, no `st.rerun()`); `macro\_regime\_agent\_output` (valid\_until=EOD) and Sections B/D/E are deliberately not hydrated. 10 tests.

### 7.6 Phase 8B — MoneyFlowAgent (merged `760f356a3`)

Second production foundation agent. Consumes GEX/DEX (Massive) + dark pool (Quiver) processed signals. Three deterministic confidences before the LLM (short = signals-agree count / 3, mid = strength-map × direction-valid, long = 0.0). `\_load\_prior\_gex\_dex\_result` validates an 11-key `\_REQUIRED\_PRIOR\_FIELDS` frozenset and is fail-closed for squeeze condition C. A neutral GEX environment must still name an options-structure strategy. Additive Cockpit hook (`money\_flow\_agent\_output`, `ticker="SPY"`). 34 tests; Codex 2 passes.

### 7.7 Phase 8B — MarketStructureAgent (merged `8792343f9`)

Third production foundation agent. Wraps `market\_internals` — the `FragilityReading` is **injected from Cockpit Step 4** (no second compute, no vintage divergence). Three confidences (short = coverage × clarity over the 5 core components, with `leading\_theme\_breadth\_narrowing` excluded as permanently scaffolded; mid = trailing elevated+ run via a saturating curve, `vintage\_mismatch`/snapshot fallback → `min(interpolated, 0.1)` **cap not floor**; long = 0.0). `signal\_basis` three-way classifier; tighten-only prohibitions written into the prompt. 44 tests; Codex 2 passes.

### 7.8 FragilityReading O/D extension + Phase 8B — SectorRotationAgent (merged `bb77ee28e` / `fbf0cc41d`)

* **FragilityReading O/D extension** (`bb77ee28e`) — surfaces the full offense/defense reading (`avg\_diff` / `by\_window` / `n\_windows` / `confirming\_windows`) onto `FragilityReading.offense\_defense` (two-line dataclass change; `fragility\_snapshot()` untouched). Enables SectorRotationAgent to consume the O/D data without recomputing. 7B suite 229/229.
* **SectorRotationAgent** (`fbf0cc41d`) — fourth production foundation agent. Wraps `theme\_baskets` + `theme\_transmission` + the injected full O/D reading. Three confidences (short = theme\_coverage × short\_clarity, mid = theme\_coverage × dispersion × wave\_clear, long = 0.0). `signal\_basis` three-way includes `no\_clear\_leadership` (a neutral / wait state, never presented as directional). TR1 carries the full O/D dict, proving the extension is the source. Additive Cockpit hook (`sector\_rotation\_agent\_output`). 34 tests; Codex APPROVED (1 pass, 0 findings).

### 7.9 Enablers + Phase 8B — ThemeIntelligenceAgent (merged `5ecfb7875`; docs `6cc972e9a`; enabler merge `107e0f09e`)

Two enabler phases shipped between SectorRotationAgent and ThemeIntelligenceAgent:

* **constituent\_rs + CLUSTER/ROLE label lift** (`107e0f09e`) — `ThemeMomentumResult` gains `constituent\_rs: dict = field(default\_factory=dict)` populated in `\_enrich\_excess\_stage\_breadth` (zero new network; reuses already-fetched constituent OHLCV; stores `{ticker: {"1m","3m","active": excess\_float}}`). `CLUSTER\_LABELS` and `ROLE\_LABELS` lifted from both page files into `lib/theme\_transmission.py` (single source of truth; lazy import preserved; closure capture verified). theme\_baskets 157/157.

* **ThemeIntelligenceAgent** (`5ecfb7875`) — fifth production foundation agent. Distinct from SectorRotationAgent: per-ticker role (constituent\_rs × seed role) + cross-wave asymmetric opportunity (wave\_order {1,2} + stage="rotating\_in"; `\_EARLY\_STAGES = frozenset({"rotating\_in"})` — "" excluded by design). short\_confidence = theme\_coverage × role\_resolution (all-constituent denominator, honest coverage); mid\_confidence = theme\_coverage × asymmetry\_strength; long\_confidence = 0.0 (defers to StockResearchAgent). `no\_role\_signal` is neutral/wait — never bearish (prompt prohibits directional framing). TR1 ranked\_constituents per top theme; TR2 asymmetric\_themes + late\_stage contrast. Cockpit hook: Step 4, after SectorRotation, `\_themes\_list` only (no offense/defense). 39 tests; 3 discriminating mutation probes (TI3/TI5/TI13). Codex APPROVED (1 pass, P2a/P2b AS-IS).

### 7.10 Phase 8B — Candidate Eligibility Gate (enabler, merged `f78ef606f`)

The deterministic, LLM-free enabler that PRECEDES CandidateScreeningAgent — the numeric-firewall side of the agent. It is **not** an agent (no LLM, no `AgentOutput`, no slate, no Cockpit hook). Merged on its own ahead of the agent body, mirroring the prior enablers (`constituent\_rs`, `FragilityReading.offense\_defense`). Feature branch `phase-8b-candidate-eligibility` off `main @ 0bcf01f09`, feature commit `b1310ec1e`.

* **`lib/candidate\_eligibility.py` (new; stdlib-only at import):** a frozen `EligibilityVerdict` (`status ∈ {eligible, conditional, ineligible, unknown}`, sorted `blockers`/`conditions`/`unknowns` reason tuples from a frozen vocabulary, `data\_quality ∈ {live, partial, degraded}`, `strategy\_type` passthrough of `card.setup`, `as\_of`). `compute\_eligibility(card, signal=None, \*, horizon, as\_of=None)` + `eligibility\_by\_horizon(...)`. Reads `OpportunityCard` + `CandidateSignal` fields **read-only**, tolerating a dataclass OR a dict via a private `\_field` reader.
* **Six gates in two tiers.** **HARD** (may reach `ineligible`): `thesis` (`status\_by\_horizon[h]=="Avoid Chasing"` fail, `None`→unknown; plus a defensive `risk\_overlay\_failed` blocker branch the ranker does not currently emit — kept forward-compatible), `eps` (`deteriorating` → SHORT conditional / MID+LONG fail; `unknown`/no-signal → unknown), `valuation` (elevated ≥ `\_VALUATION\_ELEVATED\_PCT` 0.70 → MID/LONG conditional; prohibited ≥ `\_VALUATION\_PROHIBITED\_PCT` 0.85 → SHORT conditional / MID+LONG fail), `event` (earnings proximity — LONG always passes; SHORT: ≤2d imminent / ≤7d window conditional, `None`→unknown; MID: ≤2d pending conditional, else pass; **FOMC/CPI deliberately excluded** — market-wide, no per-candidate differentiation, MarketStructure's lane). **SOFT** (never `ineligible`): `liquidity` (`candidate\_type` FUNNEL/BOTH pass, ALT\_SIGNAL conditional, missing unknown — a generation-time proxy, not a fresh re-read) + `distribution` (`entry\_quality\_label` avoid/extended conditional, missing unknown — a proxy; no per-ticker distribution-day field exists, that signal is market-wide in MarketStructure).
* **Aggregation precedence (core invariant):** hard-fail → `ineligible`; elif hard-unknown → `unknown`; elif any-conditional → `conditional`; elif soft-unknown → `conditional`; else `eligible`. `blockers`/`conditions`/`unknowns` are populated from ALL gates (sorted, de-duplicated). **"Never default to pass":** signal-only fields evaluate to their UNKNOWN state when `signal is None`.
* **Numeric-firewall provenance guard (the Codex REJECT → fix):** `\_forward\_pe\_is\_usable` rejects `None` / non-numeric / `bool` (a True/False forward\_pe is a data error, not 1/0) / `<= 0`. It plugs the leak where `fetch\_fundamental` stamps `data\_source["valuation"]="live"` on an invalid `forwardPE` and `\_valuation\_percentile` then defaults the percentile to 0.5 — a defaulted 0.5 with a present-but-unusable `forward\_pe` is now `VALUATION\_UNKNOWN`, never a real pass. When **no** fundamental is reachable, the bare-percentile path is preserved (a directly-constructed 0.50 → pass).
* **Thresholds (named, calibration debt):** `\_VALUATION\_ELEVATED\_PCT = 0.70` (grounds to `opportunity\_ranker.\_VALUATION\_HIGH\_PCT`); `\_VALUATION\_PROHIBITED\_PCT = 0.85` (**new band ceiling; unvalidated first guess — calibration debt**); `\_EARNINGS\_IMMINENT\_DAYS = 2`, `\_EARNINGS\_WINDOW\_DAYS = 7` (ground to the existing `earnings\_within\_window` ≤7d blocker; reused by the agent body).
* **Tests:** `scripts/test\_phase\_8b\_candidate\_eligibility.py` **18 tests / 87 assertions**, fully offline, real `OpportunityCard` / `CandidateSignal` / `Blocker` / `FundamentalResult` / `TrackAResult` instances (a field rename breaks the suite). Codex **REJECT** (provenance firewall leak) → fix round (1 code fix + 4 tests + 1 clarifying comment) → **APPROVE** (assertions 65 → 87). Phase doc `docs/reliability\_candidate\_eligibility\_gate.md`.

### 7.11 Phase 8B — CandidateScreeningAgent (sixth foundation agent, merged `e6c5be89a`)

The **sixth production foundation agent** — the LLM agent that CONSUMES the merged eligibility gate. Feature branch `phase-8b-candidate-screening-agent` off `main @ f78ef606f`, feature commit `b6daea492`; docs-hash follow-up `f17f4e572`. Phase doc `docs/reliability\_candidate\_screening\_agent.md`.

* **Strategy identity — v1 is ONE fixed strategy: MOMENTUM / RS-GAP.** Primary ranking key = the per-horizon RS composite gap WITHIN a theme. Future strategies (leader play, high-beta) will be SEPARATE agents (e.g. `LeaderScreeningAgent`), never parameters of this one — **no pluggable strategy interface** in v1.
* **A per-theme RELATIVE screener.** For one active theme: its candidates → each through the eligibility gate → a deterministic **comparison table** over the `eligible` set → a deterministic frontrunner per horizon → `no\_clear\_winner` decided **in code** → the LLM ONLY explains which differences are decisive and translates trade-offs into horizon fit + invalidation. NOT a cross-theme ranker (PM's job), NOT an entry-timing engine (TechnicalEntry), NOT ticker-level MoneyFlow (future Stage-2), NOT StockResearch. Advisory only (`requires\_human\_confirmation` always `True`; no execution field). Tone: "worth ADVANCING to trade construction," never "buy X."
* **Comparison table — A/B dimension typing + tradability guard** (frozen `CandidateProfile`): **A dims** `relative\_strength` (per-horizon RS composite, raw excess into evidence only) / `valuation\_elasticity` (provenance-gated via the gate's `\_valuation\_missing` — a defaulted 0.5 is `unknown`, never imputed) / `short\_crowding` (UNAVAILABLE). **B dims** `theme\_role` (`get\_ticker\_role`) / `volume\_confirmation` (confirmed/unconfirmed/divergent) / `options\_structure` (UNAVAILABLE) / `catalyst\_proximity` (reuses the gate's earnings-window constants) / `tradability`. **Cross-cutting tradability `quality\_capped` guard** (penny-stock guard): `market\_cap\_tier` (`ample` ≥ `\_MCAP\_AMPLE`, else `marginal`, else usually `unknown`) + `liquidity\_tier` (FUNNEL/BOTH ample, ALT\_SIGNAL marginal, missing unknown) → `quality\_capped` attached to EVERY A-dim so a high raw gap on a capped ticker does not read as genuine leadership. **exclude-not-down-weight** — discrete labels, the gate did the excluding, tradability only annotates; no continuous multiplier.
* **Code decides frontrunner + `no\_clear\_winner`; the LLM cannot override.** `\_sort\_key` order: `-RS composite` → `volume\_confirmation` → `valuation\_elasticity` (lower better; unknown last) → `quality\_capped` (False first) → `ticker` (byte-stable). Only AVAILABLE dims participate. `no\_clear\_winner[h]` set by CODE when (a) empty eligible set, (b) frontrunner lead over runner-up on the primary key < `\_RS\_GAP\_DECISIVE\_PCT`, or (c) capped frontrunner without a decisive lead (a lone capped name is refused; a capped name WITH a decisive lead is allowed-but-flagged). Short and mid frontrunners MAY differ (long = `not\_applicable`).
* **Deterministic slate skeleton persists in `supporting\_data`** (no second file, not through the `extra="forbid"` `AgentResult`): frozen `CandidateSlate` (`primary` = frontrunner or None when `no\_clear\_winner`; `secondary` = next 0–2 eligible; `watch` = eligible-unchosen + all conditional; `rejected` = ineligible+unknown with gate reason codes; + `no\_clear\_winner` / `no\_trade\_reason` / `signal\_basis`), placed on `AgentOutput.supporting\_data` BEFORE the LLM call → serialized verbatim by `append\_agent\_output`.
* **Three ToolResults** via `processed\_signals\_to\_tool\_result` (numeric firewall): TR1 `candidate\_screening\_comparison` (per-ticker table), TR2 `candidate\_screening\_slate` (the deterministic skeleton), TR3 `candidate\_screening\_confidence` (short/mid/long + decomposition). **`signal\_basis` three-way** per horizon: `signal\_present` / `no\_clear\_winner` (NEUTRAL/WAIT, never bearish or "sell") / `degraded\_insufficient` (no eligible frontrunner, or coverage below `\_COVERAGE\_MIN`).
* **`signals=` deviation + fail-closed join.** The gate reads `eps`/`valuation`/`entry\_quality` off the CandidateSignal, which the OpportunityCard does NOT carry, so the public API adds an optional `signals=` kwarg (list|dict) matched **exactly by ticker**; the Cockpit passes the live `_candidates`. An unmatched / missing / wrong-ticker signal fails closed (hard-unknown → rejected, never silently eligible, no cross-contamination). ONE `AgentOutput` per theme (`ticker == theme\_key`).
* **LLM prompt** emits NO number: qualitative tokens only (tickers, role/tier labels, direction words, `signal\_basis`); `REQUIRED OUTPUT FORMAT` 4-space indent no fences; three findings (short / mid / long-defer), each citing ≥1 evidence\_id. Respect `quality\_capped` and a code-set `no\_clear\_winner`. All `lib.reliability` / `lib.agent\_framework` / `lib.candidate\_eligibility` / `lib.theme\_transmission` imports lazy (subprocess guard §CSA-11).
* **Cockpit hook** (additive, `_run\_refresh` after the TIA block, inside Step 4 `try`): reuses `_cards` + `_candidates` + `_themes\_list` (no fetch, no re-rank); loops up to 3 ACTIVE themes (`stage ∈ {leading, rotating\_in}` AND `stage\_confirmed`); per-theme try/except isolation; writes only `candidate\_screening\_agent\_output` (dict keyed by `theme\_key`). Stage 1 only; **session-state-only, no widget this phase**.
* **Calibration debt:** `\_RS\_GAP\_DECISIVE\_PCT=0.08`, `\_MCAP\_AMPLE=10e9`, `\_VOL\_CONFIRM\_RATIO=1.2`, `\_COVERAGE\_MIN=0.34` (reuses the gate's `\_EARNINGS\_IMMINENT\_DAYS` / `\_EARNINGS\_WINDOW\_DAYS`).
* **KNOWN LIMITATION (P2):** the penny-guard mostly reduces to the `ALT\_SIGNAL` proxy because `market\_cap` is usually absent in production (only on the v1 `FundamentalSignals` shim) and dollar-ADV has no field. Honest (never fabricated) but thin — a driver for the next Degradation-Visibility Layer and a future live market-cap / ADV channel. **Down-scoped UNAVAILABLE dims** (no backing field — honest, not fabricated): `short\_crowding`, `options\_structure`, `beta`, dollar-ADV.
* **Tests:** `scripts/test\_phase\_8b\_candidate\_screening\_agent.py` **104 assertions** (§CSA-1..CSA-18), fully offline. Real `OpportunityCard` / `CandidateSignal` / `FundamentalSignals` instances; the deterministic layer called directly; **§CSA-8 drives the REAL `run\_llm\_agent` with only `agent\_runner.\_call\_llm` patched** (success + fail-closed fallback). Discriminating: RS-gap frontrunner, thin-gap `no\_clear\_winner`, penny-guard capped path (c) + capped-but-decisive-allowed, short≠mid frontrunner, eligibility routing, unavailable-dims-excluded + `\_sort\_key` guard, degraded coverage, numeric-firewall real-path, per-theme identity, determinism, tie-break chain, empty-set path (a), `signals=` fail-closed join, no cross-contamination, valuation-provenance not re-leaked, lazy-import subprocess guard.
* **Codex arc:** the recon-first PREFLIGHT (surfacing missing fields + the `signals=` deviation before implementing) prevented a REJECT → **APPROVE WITH FIXES** (6 discriminating **test additions**, zero production-code bugs) → **APPROVED**. Feature `b6daea492`; merge `e6c5be89a` (`--no-ff`, two-parent topology preserved), pushed.

\---

## 8\. Current Baseline \& Next Steps

```
Baseline:   main @ f17f4e572  (Phase 8B CandidateScreeningAgent docs-hash follow-up;
            phase merge e6c5be89a, feature b6daea492;
            eligibility-gate enabler merge f78ef606f, feature b1310ec1e)
Test state: test\_reliability\_\* parity suites (GREEN)
            + agent framework suite 15/15
            + Phase 8B MacroRegimeAgent 24/24
            + Phase 8B MoneyFlowAgent 34/34
            + Phase 8B MarketStructureAgent 44/44
            + Phase 8B SectorRotationAgent 34/34
            + Phase 8B ThemeIntelligenceAgent 39/39
            + Phase 8B candidate-eligibility gate 18 tests / 87 assertions
            + Phase 8B CandidateScreeningAgent 104 assertions (§CSA-1..CSA-18)
            + Phase 8B-0 24 (Quiver 6 / Massive 5 / GEX-DEX 13)
            + 7B rotation 229/229
            + theme\_baskets 157/157
Built agents: MacroRegimeAgent · MoneyFlowAgent · MarketStructureAgent ·
              SectorRotationAgent · ThemeIntelligenceAgent · CandidateScreeningAgent
              (all six production; CandidateScreening built on its
              candidate\_eligibility deterministic enabler)
```

**Next: the Degradation-Visibility Layer.** A Cockpit **aggregation banner** that surfaces every foundation agent's degradation vocabulary — today buried in `supporting\_data` (`signal\_basis` / `no\_trade\_reason` / `\*\_unavailable` dimensions / degraded coverage / `greeks\_unavailable` / `vintage\_mismatch` / `insufficient\_data` / …) — into a **bilingual banner** per the `bi()` discipline. Its precise purpose (locked design intent): distinguish **(1) defensive fail-closed degradation** when data is genuinely absent — which MUST be preserved (it is the numeric firewall) — from **(2) runtime-avoidable degradation** (key / tier / field / cache / network not wired) which, from a trading standpoint, is a **BUG**. The visibility layer makes both unmissable; a later **runtime zero-degradation acceptance protocol** (defined once the 8B roster is complete) will codify (2)=bug with a documented exemption list for (1). It exists precisely because CandidateScreeningAgent (and its siblings) currently write degradation only into `supporting\_data` with no visible surface.

After it, the **remaining foundation agents** — **StockResearchAgent**, **TechnicalEntryAgent**, **SectorResearchAgent**, **RiskOverlayAgent** — which will **build degradation-visibility fields into their FIRST version** (ValuationDebateAgent belongs to Phase 8D).

The canonical phase sequence after the foundation-agent roster fills in: **Phase 8C — PM layer** (ShortTermPM / MidTermPM / LongTermPM → MasterPM); **Phase 8D — ValuationDebateAgent / reverse DCF / adversarial valuation & evidence infrastructure**; **Phase 9 — Judgment Console** (human review/confirmation, judgment provenance, override, audit trail — downstream gating policy still an open architecture decision). Later: **Phase 7D Block B** (judgment performance, calibration, PM historical weighting once outputs accumulate) and **Phase 6D** (holdings-side review).

\---

## 9\. Collaboration Protocol

### 9.1 Roles

|Actor|Role|
|-|-|
|User / John|Product owner, architecture direction, final approval, **Chinese** discussion|
|Claude|Architecture partner, prompt engineer, phase planner, Codex-feedback reviewer|
|Claude Code|Implementation actor (primary worktree)|
|Codex|Independent reviewer; mutation-probe discriminability is first-class|

### 9.2 Phase rhythm

```
Chinese architecture discussion → STEP 0 recon (read-only; scan Phase 0–5 for reuse)
→ English implementation prompt (one code block) → Claude Code implements
→ Codex review (mutation probes) → fix rounds → explicit APPROVE
→ closeout (commit → --no-ff merge → push → docs sync) → UI verification for visible changes
```

> **Enabler-before-agent rhythm (validated three times).** A deterministic, LLM-free enabler is merged on its own **ahead of** the agent that consumes it — `constituent\_rs` before ThemeIntelligenceAgent, `FragilityReading.offense\_defense` before SectorRotationAgent, and the `candidate\_eligibility` gate before CandidateScreeningAgent. The enabler carries the numeric-firewall / provenance work; the agent body carries the LLM synthesis. This keeps each review small and keeps the firewall side reviewable in isolation.

### 9.3 Prompt formatting

All prompts to Claude Code / Codex go in a **single copyable code block**. Inner code/JSON examples use **4-space indentation, not nested backtick fences** (fences confuse parsers — this is exactly the bug that motivated the REQUIRED OUTPUT FORMAT block's 4-space JSON example).

### 9.4 Streamlit startup

```
set -a \&\& source .env \&\& set +a \&\& streamlit run app.py
```

Use `set -a \&\& source .env` rather than relying on `st.secrets` / `.streamlit/secrets.toml`, which has been flaky (see §10). `\_has\_llm\_api\_key()` checks `os.environ` first, then `st.secrets`.

### 9.5 Git discipline

* Implement in the primary worktree; review in the standing review worktree (`investment-agents-review`).
* Merge to `main` with **`--no-ff`** (preserve branch tips as visible parents). Never rebase / force-push published history.
* POSIX **heredoc** for commit messages (not PowerShell here-string). End commits with the `Co-Authored-By` trailer.
* **Push/merge only after explicit APPROVE** relayed by the user.
* Run `git stash list` at session start; report a non-empty stash before any git op. Stop and report on any unexpected git state.
* Known environment quirk: on the WSL↔Windows filesystem, git's background `geometric-repack` auto-maintenance prints a non-fatal `Permission denied` after commits/merges; the object writes still succeed. Use `git -c gc.auto=0` to suppress the noise.

### 9.6 Docs discipline

Every closeout syncs `PROJECT\_STATE.md`, `CURRENT\_TASK.md`, the phase doc, and `README.md`. README is a first-class deliverable; truthfulness rule applies (real hashes/counts, planned scope labeled as planned). *(This memo v4 and ROADMAP v13 are versioned successors under `docs/Memo/` and `docs/Roadmap/`; the prior v3 / v12 stay in place as superseded history — append-only doc discipline.)*

\---

## 10\. Known Issues \& Lessons Learned

### 10.1 This session's lessons (Phase 8 realignment)

1. **LLM schema compliance is not free — always add `\_repair\_llm\_response()`.** `claude-sonnet-4-6` consistently flattened `AgentResult` (top-level `text`/`evidence`, float `confidence`). With `extra="forbid"`, the flat shape is rejected → rule-based fallback. The prompt-side fix (REQUIRED OUTPUT FORMAT example) reduces it; the **structural repair layer** is the durable fix. Every future agent reuses it.
2. **Prompt JSON examples must use 4-space indentation, not backtick fences.** Fences interfere with `\_extract\_json\_obj`. The REQUIRED OUTPUT FORMAT block is built from plain (non-f) string literals so its braces are literal.
3. **Judgment extraction: first complete sentence, not hard truncation.** Mid-sentence 200-char truncation produced broken PM-facing text. Now: first sentence up to 400 chars; `validate\_judgment` limit raised 200→400.
4. **Streamlit secrets instability — prefer `set -a \&\& source .env`.** `.streamlit/secrets.toml` / `st.secrets` resolution has been unreliable; environment-variable injection is the dependable startup path.
5. **Lazy imports do not hot-reload reliably — full restart after editing an agent.** Because all `lib.reliability` imports are lazy (inside functions), Streamlit's module reload can serve a stale closure; restart the server rather than trusting hot-reload.
6. **Additive, key-gated, fail-closed is the safe way to wire an agent into a live page.** The Cockpit hook reuses the already-computed regime (no second fetch), gates on `\_has\_llm\_api\_key()`, owns its `try/except`, and writes only a new session key — so a keyless or failing agent is a clean no-op, never an aborted refresh. **CandidateScreeningAgent extends this to a per-theme LOOP** — each of the 2–3 active themes runs in its own try/except so one theme's failure isolates and the others still produce.
7. **Activate, don't rebuild.** World 2 was fully built and dormant; the win was the thin connective tissue, not a rewrite.
8. **Code decides deterministic verdicts; the LLM explains, never overrides (CandidateScreeningAgent).** The frontrunner, `no\_clear\_winner`, and the slate skeleton are computed in code and persisted as evidence / `supporting\_data` BEFORE the LLM call. The prompt forbids the LLM from picking the primary or flipping `no\_clear\_winner`; its job narrows to *explaining which coded differences are decisive* + horizon fit + invalidation. This is the sharpest form yet of the numeric-firewall boundary — it firewalls **decisions**, not just numbers.
9. **A missing field is an honest `unavailable`, never a fabricated value (CandidateScreeningAgent).** The PREFLIGHT found no backing field for `short\_crowding` / `options\_structure` / `beta` / dollar-ADV — each is marked `unavailable` and **excluded from the ranking key**, and `\_sort\_key` is tested to prove it cannot read them. `market\_cap`, usually absent, yields `unknown` (never a fabricated tier, never a silent pass-as-ample). Recon-first PREFLIGHT that surfaces missing fields before implementing is what turned a likely REJECT into an APPROVE-WITH-FIXES.
10. **Fail-closed by-ticker joins (the `signals=` deviation).** When the sketched cards-only signature could not reach the CandidateSignal fields the gate needs, the fix was an explicit `signals=` kwarg matched **exactly by ticker and failing closed** (unmatched → hard-unknown → rejected, never silently eligible, no cross-contamination) — not a silent default that would let a card ride through un-gated.

### 10.2 Carried-over guardrails (still true)

11. The project is an investment **workflow/Fund system**, not a stock picker; the central path is **opportunity-first**, not ticker-first.
12. **Horizon awareness is mandatory** — the same ticker differs across short/mid/long; this is why agents emit three findings + three confidences. *(CandidateScreeningAgent: short and mid frontrunners MAY be different tickers; long defers.)*
13. **Review-only is non-negotiable.** `approved\_for\_execution` is always `False`; `requires\_human\_confirmation` always `True`.
14. **Append-only audit trails** (snapshots, anchor archive, agent-output JSONL, ingest log) — future evaluation uses audit snapshots, never rolling recomputation.
15. **Tighten-only market internals** — never flips regime or loosens gates.
16. **`thesis\_ingestion` / `theme\_transmission` isolation** — never imported by ranking/scoring/snapshot/anchor modules; `current\_evidence\_status` stays `"unknown"` until the Judgment Console phase.
17. **STEP 0 reuse-over-rebuild** — scan Phase 0–5 legacy code for reusable structures before writing new ones (e.g. MoneyFlowAgent reuses the Phase 2E option schema; CandidateScreeningAgent reuses the eligibility gate's earnings-window constants and `\_valuation\_missing` provenance check wholesale).

### 10.3 Open design debt

* **Split-brain still partial.** Six foundation agents are wired (MacroRegime / MoneyFlow / MarketStructure / SectorRotation / ThemeIntelligence / CandidateScreening, all into the Cockpit); the live pages still consume deterministic producers directly. Activation proceeds agent-by-agent.
* **Degradation vocabulary is invisible.** Every agent writes degradation into `supporting\_data` with no aggregated surface — the immediate motivation for the next phase (Degradation-Visibility Layer), which must also separate defensive (preserve) from runtime-avoidable (bug) degradation.
* **Penny-guard coverage is thin.** CandidateScreeningAgent's tradability guard mostly reduces to the `ALT\_SIGNAL` proxy because `market\_cap` is usually absent and dollar-ADV has no field — a driver for a future live market-cap / ADV channel.
* **`llm\_orchestrator.py` lenient JSON scanner** (`\_first\_obj`) shares the silent-inner-object risk that bit the thesis extractor; guarded only by callers' per-key checks. Latent, not yet fixed.
* **Calibration debt** — fragility thresholds after more snapshots; vol\_shrink/weak-bounce definitions; valuation\_role + peer-match edge cases; **the new CandidateScreeningAgent + eligibility-gate thresholds** (`\_RS\_GAP\_DECISIVE\_PCT` 0.08, `\_MCAP\_AMPLE` 10e9, `\_VOL\_CONFIRM\_RATIO` 1.2, `\_COVERAGE\_MIN` 0.34, `\_VALUATION\_PROHIBITED\_PCT` 0.85) — all named, all unvalidated first guesses awaiting real slate outcomes.
* **No PM layer yet** — foundation agents emit per-horizon findings, but ShortTermPM/MidTermPM/LongTermPM/MasterPM are unbuilt.

> The authoritative, full collaboration-lessons ledger lives in the live phase docs / ROADMAP; this section reproduces what is current as of `f17f4e572`. On any conflict, the live docs win.

\---

## 11\. Cross-Session Startup Block

```
We are continuing the AI Investment OS project (an AI Fund workflow system, not a dashboard).

Authoritative sources: latest README.md + docs/ai\_dev\_state/PROJECT\_STATE.md + CURRENT\_TASK.md.
This memo (Master Memo v4, 2026-07-01) is supplementary P1 context; it yields to the live docs on conflict.

Current baseline:
- main @ f17f4e572 (Phase 8B CandidateScreeningAgent docs-hash follow-up; phase merge e6c5be89a,
  feature b6daea492; candidate-eligibility-gate enabler merge f78ef606f, feature b1310ec1e)
- test\_reliability\_\* parity suites + agent framework 15/15 + Phase 8B MacroRegime 24 / MoneyFlow 34 /
  MarketStructure 44 / SectorRotation 34 / ThemeIntelligence 39 / candidate-eligibility 18 (87 asserts) /
  CandidateScreening 104 asserts + Phase 8B-0 24 + 7B rotation 229 + theme\_baskets 157

Architecture (Phase 8 realignment):
- Two worlds: World 1 (live Streamlit deterministic producers) + World 2 (reliability/evidence stack).
  Phase 8 activates World 2 via lib/agent\_framework/ connective tissue — wrap deterministic
  outputs as evidence → constrained LLM call → validate → AgentOutput. Activate, don't rebuild.
- Pipeline: data layer → 11 foundation agents (market-env / opportunity / stock-research / risk) →
  PM layer (ShortTermPM/MidTermPM/LongTermPM) → MasterPM → UI (AI-PM reporting + human confirmation).
- Canonical roster: MacroRegime, MarketStructure, MoneyFlow (market env); SectorRotation,
  ThemeIntelligence, CandidateScreening (built) (opportunity); StockResearch, ValuationDebate,
  TechnicalEntry, SectorResearch (stock research); RiskOverlay (risk).
- LLM boundary: code computes ALL numbers AND all deterministic verdicts (frontrunner, no\_clear\_winner);
  LLM synthesizes implications, explains which differences are decisive, emits NO numeric value,
  and cannot pick the primary or override a code-set no\_clear\_winner.

Built so far (6 production foundation agents, all with additive key-gated Cockpit hooks):
- MacroRegimeAgent: short=vote agreement, mid=consecutive same-regime days, long=data\_coverage\*short.
- MoneyFlowAgent: GEX/DEX (Massive) + dark pool (Quiver); short=signals-agree/3, mid=strength×dir, long=0.
- MarketStructureAgent: injected fragility reading; short=coverage×clarity, mid=elevated-run cap, long=0.
- SectorRotationAgent: theme\_baskets + theme\_transmission + full O/D; short/mid coverage-weighted, long=0.
- ThemeIntelligenceAgent: per-ticker role (constituent\_rs × seed role) + cross-wave asymmetry
  (wave {1,2} + rotating\_in); short=coverage×role\_resolution; mid=coverage×asymmetry; long=0.
- CandidateScreeningAgent (v1 = momentum/RS-gap; sixth agent): consumes the deterministic
  candidate\_eligibility four-state gate via a fail-closed by-ticker signals= join; per-theme
  relative screener; CODE decides frontrunner + no\_clear\_winner, LLM explains only;
  short=coverage×decisive-gap clarity, mid=coverage×mid-clarity, long=0 (defers).
- Enabler: lib/candidate\_eligibility.py (four-state gate; \_forward\_pe\_is\_usable numeric firewall).
- Data sources: + Quiver Quantitative (Hobbyist) + Massive Options (Starter); Unusual Whales excluded.

Non-negotiables:
- approved\_for\_execution always False; requires\_human\_confirmation always True; evidence\_refs never empty; numeric firewall.
- Code decides deterministic verdicts (frontrunner / no\_clear\_winner); LLM explains, never overrides.
- Fail-closed by-ticker joins (unmatched → hard-unknown → rejected, never silently eligible).
- Degradation is defensive (preserve — it is the firewall) vs runtime-avoidable (a BUG); both must be visible.
- All lib.reliability imports lazy (never from package root).
- \_repair\_llm\_response() pattern + REQUIRED OUTPUT FORMAT prompt block for every agent.
- valid\_until = end\_of\_today\_iso(); judgment = first complete sentence, no numerics.
- Append-only audit; tighten-only internals; exclude-not-down-weight; never fabricate a number or a field.

Next task:
- Degradation-Visibility Layer: a Cockpit aggregation banner surfacing every foundation agent's
  degradation vocabulary from supporting\_data (signal\_basis / no\_trade\_reason / \*\_unavailable /
  degraded coverage / greeks\_unavailable / vintage\_mismatch / insufficient\_data), bilingual per bi().
  Purpose: distinguish (1) defensive fail-closed degradation (preserve) from (2) runtime-avoidable
  degradation (bug). Then the remaining foundation agents (StockResearch / TechnicalEntry /
  SectorResearch / RiskOverlay), which build degradation-visibility fields into their FIRST version.

Collaboration:
- Chinese for architecture; English single-code-block prompts (4-space inner JSON, no fences).
- Enabler-before-agent: merge the deterministic LLM-free enabler ahead of the agent that consumes it.
- Streamlit: set -a \&\& source .env \&\& set +a \&\& streamlit run app.py
- Git: --no-ff merges, heredoc commits, push only after explicit APPROVE, report unexpected state.
```

\---

## 12\. The Most Important Things Not to Forget

1. It is an **AI Fund workflow system**, not a stock picker or a dashboard. The UI reports the AI PM team's work; it is not the decision tool.
2. **Activate, don't rebuild** — World 2 was dormant, not missing. Connective tissue beats rewrites.
3. **Code computes every number AND every deterministic verdict; the LLM emits none and overrides none.** Findings cite evidence; judgments are numeric-free; the frontrunner and `no\_clear\_winner` are code's, not the LLM's.
4. **`approved\_for\_execution` is always `False`**; `requires\_human\_confirmation` always `True`. Review-only, no broker, ever.
5. **`evidence\_refs` must never be empty**; an agent without evidence is not created.
6. **`\_repair\_llm\_response()` + REQUIRED OUTPUT FORMAT** are mandatory for every agent — LLMs flatten the schema.
7. **All `lib.reliability` imports lazy** — importing the agent framework must not trigger the eager reliability `\_\_init\_\_`.
8. **Three findings + three confidences per foundation agent** — so the PM layer can consume by horizon.
9. **`valid\_until = end\_of\_today\_iso()`** for foundation agents (daily refresh expiry).
10. **Append-only audit trails**; future evaluation uses snapshots, never rolling recompute.
11. **Tighten-only internals; exclude-not-down-weight; never fabricate a number or a field** (live or historical); a missing field is an honest `unavailable`, excluded from ranking keys.
12. **Fail-closed by-ticker joins** and **enabler-before-agent** rhythm — the deterministic LLM-free enabler (e.g. `candidate\_eligibility`) merges ahead of the agent that consumes it.
13. **Degradation is defensive (preserve — it is the firewall) vs runtime-avoidable (a BUG); both must be made visible** — the reason the next phase is the Degradation-Visibility Layer.
14. **STEP 0 reuse-over-rebuild** and **access-path-matrix-first** before any wiring.
15. **README + PROJECT\_STATE/CURRENT\_TASK are authoritative**; this memo yields to them.
16. **Streamlit via `set -a \&\& source .env`**, full restart after agent edits, and additive/key-gated/fail-closed (per-theme-looped for CandidateScreening) when wiring an agent into a live page.
