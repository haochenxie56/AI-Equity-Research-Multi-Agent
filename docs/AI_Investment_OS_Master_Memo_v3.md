# AI Investment OS — Master Architecture, Roadmap, and Project Memory Memo

**Version:** Master Memo v3 (2026-06-21)
**Supersedes:** Master Memo v2 (2026-06-17, baseline `79433d5`).
**Purpose:** Cross-session migration, architecture preservation, roadmap alignment, and phase-planning baseline.
**Scope:** Consolidates completed work through **Phase 8B — MacroRegimeAgent Production Implementation** and its post-merge fixes (`main @ a19b862`). Records the Phase 8 architectural realignment (World 1 ↔ World 2 activation, the agent map, the PM layer, the confidence framework, and the new alternative-data sources).
**Status convention:** `README.md` and the live phase docs (`docs/ai\_dev\_state/PROJECT\_STATE.md`, `CURRENT\_TASK.md`) are the current authoritative sources. This memo is **P1 context** — it explains and records, but yields to the live docs on any conflict.

> \*\*Disclaimer:\*\* This project is a research and decision-support system. It does not provide investment advice, does not place orders, and must remain review-only unless a future phase explicitly changes the scope under separate safety review.

\---

## 0\. How to Use This Memo

This memo solves the project's recurring context-drift problem. Use it as:

1. **A new-session startup context** for Claude / Claude Code / Codex (see §11 startup block).
2. **An architecture map** of the live product path, the reliability/evidence stack, and the new agent framework that connects them.
3. **A roadmap-memory source** for why each phase existed and what it must not be confused with.
4. **A design-principle guardrail** to prevent future phases from weakening review-only safety, the numeric firewall, evidence discipline, or auditability.

### 0.1 Source Authority

|Priority|Source|Use|
|-|-|-|
|P0|Latest `README.md`|Product definition, feature inventory, architecture, safety principles, tech stack.|
|P0|`docs/ai\_dev\_state/PROJECT\_STATE.md` + `CURRENT\_TASK.md`|Authoritative completed-state snapshot, current next phase, per-phase detail with commit hashes.|
|P1|This memo (v3)|Cross-session context, design rationale, agent-framework architecture, anti-drift guardrails. Yields to P0 on conflict.|
|P2|Codex review records under `docs/`|Independent reality check + mutation-probe history per phase.|
|P3|Master Memo v1/v2, historical phase PDFs|Historical evolution only. Do not override current docs.|

### 0.2 Supersession Notes

* Anything in v1/v2 that contradicts v3 is stale. v2's baseline was `79433d5` (Phase 7C). The current baseline is `a19b862`.
* v2 framed the system as an "Investment OS / decision-support stack." v3 keeps that, but adds the **Phase 8 realignment**: the long-term shape is an **AI Fund workflow** — foundation agents → a horizon-aware PM layer → a MasterPM — with the Streamlit app as the **AI-PM reporting surface**, not the decision tool.
* Phases 6A–7C, Valuation Refactor v1, Anchor Intelligence v2–v2.5, Thesis Ingestion MVP, Legacy Red Suite Archival: all closed and merged (see v2 + PROJECT\_STATE.md).

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

**Decision (Phase 8):** do **not** rebuild. Activate World 2 by adding **connective tissue** — a thin agent framework (`lib/agent\_framework/`) that wraps World-1 deterministic outputs as evidence, runs an evidence-constrained LLM call, validates the result against the evidence, and emits a unified `AgentOutput`. The first real agent (MacroRegimeAgent) proves the pattern end-to-end.

### 1.3 The corrected LLM boundary

> \*\*Code computes facts and numbers. The LLM synthesizes actionable implications from those facts — and never emits a numeric value.\*\*

A foundation agent's deterministic side produces every number (regime votes, confidences, GEX/DEX, scores). The LLM is handed those numbers as **evidence** and asked only: *what does this mean for positioning, across horizons?* Its prose judgment must cite evidence IDs and must contain no digits, `%`, `$`, or metric tokens.

\---

## 2\. Architecture Principles (the non-negotiables)

These are enforced by code, tests, and review. New phases must not weaken them.

1. **Numeric firewall.** Code computes every number. The LLM never invents valuations, indicators, scores, probabilities, or market data. Numeric/metric claims in findings must cite an `EvidenceRef`.
2. **`evidence\_refs` must never be empty.** `agent\_result\_to\_agent\_output` flattens evidence from `findings\[].evidence + risks\[].evidence` and **raises** if the result is empty. An agent with no evidence is not an agent.
3. **`approved\_for\_execution` is always `False`.** No broker, no order, no payload, no account ID, no quantity-to-execute. Review-only by design.
4. **All `lib.reliability` imports are lazy.** Inside `lib/agent\_framework/` and `lib/agents/`, every `lib.reliability` / `lib.llm\_orchestrator` import is **inside the function that needs it**; module level uses only `TYPE\_CHECKING`. Importing the agent framework must never trigger the \~52-module eager `lib.reliability.\_\_init\_\_` (subprocess import-guard test enforces this).
5. **`\_repair\_llm\_response()` pattern for every agent.** LLMs (especially `claude-sonnet-4-6`) flatten the `AgentResult` shape. Because the schemas are `extra="forbid"`, a flat response is rejected. A **structural repair layer** sits between extraction and validation: it wraps top-level `text`/`evidence` into `findings`, injects missing `agent\_name`/`run\_id`, and coerces a float `confidence` into an `AgentConfidence` object. **Reuse this for all future agents.**
6. **`valid\_until = end\_of\_today\_iso()` for all agents.** Foundation agents are part of the daily Cockpit refresh; their outputs expire end-of-day (UTC 23:59:59). Longer-lived validity is a PM-layer concern, not a foundation-agent one.
7. **Numeric-free judgment.** `findings\[0].text` (the PM-facing one-sentence judgment) must contain no digits / `%` / `$` / metric tokens; it is extracted as the **first complete sentence** (≤ 400 chars), not hard-truncated mid-sentence.
8. **Append-only audit trails.** Daily snapshots, anchor archive, agent-output JSONL, ingest logs: append, never rewrite. Corrections append a new record with provenance.
9. **Tighten-only market internals.** Fragility can annotate / tighten short-term entry / warn; it can never flip macro regime, loosen a gate, or authorize buying.
10. **Exclude, do not down-weight.** An untrustworthy anchor/peer set is excluded and labeled, never hidden behind a continuous weighting knob.
11. **Never fabricate a number** (historical or live). Backfill only recomputes computable anchors under filing-lag rules; analyst anchors are never invented for past dates.
12. **Access-path-matrix first.** Before unifying a producer or wiring an agent into a page, map the caller-contract matrix (who needs network, who is network-free, who can write cache, who touches snapshots).

\---

## 3\. Agent Map (current confirmed state)

The agent map is the Phase-8 target shape. **Only MacroRegimeAgent is implemented; MoneyFlowAgent is next.** The remaining foundation agents are the **planned wrapping targets** — each wraps an existing deterministic World-1 producer. Their exact names/scoping are confirmed at each agent's STEP 0 (the names below are provisional and map 1:1 to the live module).

### 3.1 Data layer

|Tier|Contents|
|-|-|
|**Raw sources**|yfinance (price/VIX/ETF), FRED (rates/credit/dollar/releases/liquidity), Finnhub (news/earnings-calendar/social), **Quiver Quantitative** (dark pool / congress / insider / institutional), **Massive Options = Polygon** (options chain w/ Greeks/IV/OI).|
|**Processed signals (deterministic)**|`macro\_regime.classify\_regime` → `MacroRegimeResult` (now with vote fields); `market\_internals` fragility; `theme\_baskets`/`rotation`/`theme\_transmission`; `relative\_strength`; `candidate\_generator`/`signal\_engine`; `opportunity\_ranker`; `equity\_valuation`/`valuation\_router`/`valuation\_diagnosis`; `anchor\_archive`/`anchor\_migration`; **`gex\_dex.compute\_gex\_dex`** + **`quiver\_fetcher.compute\_dark\_pool\_signal`**.|

### 3.2 Foundation agents (roster mapped to deterministic producers)

|#|Agent (provisional)|Deterministic input (code computes)|LLM synthesizes|Status|
|-|-|-|-|-|
|1|**MacroRegimeAgent**|`classify\_regime` (regime, votes, data\_coverage) + snapshot regime history; 3 confidences|regime implications for positioning across 3 horizons|✅ **built** (`eabf0c2d` + fixes)|
|2|**MoneyFlowAgent**|`gex\_dex` (GEX/DEX/walls/squeeze) from Massive + `compute\_dark\_pool\_signal` from Quiver|dealer-positioning \& flow implications; squeeze/pin context|⏳ **next** (STEP 0)|
|3|MarketInternalsAgent|`market\_internals` fragility components + level|deterioration/health read, tighten-only context|📋 planned|
|4|RotationAgent|`rotation` + `theme\_baskets` + `theme\_transmission` (stage, breadth, wave)|which themes/waves capital is rotating through|📋 planned|
|5|RelativeStrengthAgent|`relative\_strength` multi-window excess vs SPY/QQQ|leadership/laggard read per horizon|📋 planned|
|6|CandidateAgent|`candidate\_generator` + `signal\_engine` dual-track|candidate-universe framing|📋 planned|
|7|OpportunityAgent|`opportunity\_ranker` (3-horizon scores/status)|opportunity-queue narrative|📋 planned|
|8|ValuationAgent|`equity\_valuation`/`valuation\_router`/`valuation\_diagnosis`|valuation-role implications (no numbers)|📋 planned|
|9|TechnicalAgent|`technical` indicators + S/R|entry-timing/risk context|📋 planned|
|10|ThesisAgent|`thesis\_monitor` + thesis card library|thesis intact vs broken; what changed|📋 planned|
|11|AnchorHistoryAgent|`anchor\_migration` (direction/velocity/consistency)|anchor-migration watch note|📋 planned|

> Caveat: the roster is the \*\*confirmed architecture\*\* ("\~11 foundation agents, one per signal domain"), but only rows 1–2 are committed work. Rows 3–11 are wrapping targets; their names and exact scoping are decided at each agent's STEP 0, not here.

### 3.3 PM layer

|Tier|Horizon|Consumes|
|-|-|-|
|**ShortTermPM**|1–4 weeks|each foundation agent's SHORT finding + short\_confidence|
|**MidTermPM**|1–3 months|each foundation agent's MID finding + mid\_confidence|
|**LongTermPM**|6–18 months|each foundation agent's LONG finding + long\_confidence|
|**MasterPM**|cross-horizon|the three PM syntheses; arbitrates conflicts; portfolio-level view; emits no execution instruction|

Foundation agents already emit **three findings (SHORT / MID / LONG)** with three confidences precisely so the PM tier can consume by horizon. The PM layer and MasterPM are **future phases** — not yet built.

### 3.4 UI layer

The Investment Cockpit is the AI-PM reporting surface. MacroRegimeAgent is wired in **additively**: after the existing `classify\_regime` step, a key-gated, fail-closed hook runs the agent and stores the result under `st.session\_state\["macro\_regime\_agent\_output"]` — the existing `macro\_regime\_result` state and every downstream consumer are untouched. PM-layer reporting UI is a future phase.

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
| 7 | `7_Investment_Cockpit.py` | Investment Cockpit | ⭐ Main entry. One-click refresh aggregates macro regime, market-internals fragility, theme rotation, and the opportunity queue (20 candidates × 3 horizons); writes the daily snapshot. | **MacroRegimeAgent** (additive, key-gated hook → `macro_regime_agent_output`) + `macro_regime` / `market_internals` / `opportunity_ranker` / `theme_baskets` processed signals. |
| 8 | `8_Macro_Dashboard.py` | Macro Dashboard | Live macro-regime classification + Market Internals workbench (fragility trend / components) + liquidity / rates / inflation / credit / volatility / breadth tabs. | `macro_data` / `macro_regime` / `market_internals`; processed signals only. |
| 9 | `9_Trading_Desk.py` | Trading Desk | Holdings thesis monitor, code-computed entry/exit levels (entry v4) with an LLM narrative, opportunity watch. Review-only. | `holdings` / `thesis_monitor` / `order_advisor` / `equity_valuation`; processed signals + LLM narrative. No World-2 agent. |
| 10 | `10_Thesis_Library.py` | Thesis Library | Curated external research → one-LLM-call-per-argument structured thesis cards → browse / manage. Isolated from scoring / ranking / snapshot / anchor. | `thesis_ingestion` (extraction LLM; isolated). Not a foundation agent. |
| 11 | `11_Audit_Review.py` | Audit Review | Read-only review of the daily snapshot audit trail: coverage, fragility-level history, per-ticker status timeline, "Actionable Now" follow-through. | `audit_query` (read-only snapshot reads); processed signals only. No agent. |

> Only the Investment Cockpit (page 7) currently consumes a World-2 agent output (MacroRegimeAgent). Every other page consumes deterministic processed signals and/or page-local LLM calls. As the foundation-agent roster (§3.2) fills in, more pages move from "processed signals only" to "agent outputs."

\---

## 5\. Confidence Calculation Framework

MacroRegimeAgent computes **three deterministic confidences** (no LLM) and persists them as evidence before the LLM runs. This is the template; other agents will have **agent-specific** confidence formulas, but the short/mid/long triad and the "compute-before-LLM, persist-as-evidence" discipline are the pattern.

|Confidence|Formula|Meaning|Source data|
|-|-|-|-|
|**short\_confidence**|`abs(votes\_risk\_on − votes\_risk\_off) / votes\_total`|how decisively the live indicators agree right now|`MacroRegimeResult.votes\_\*` (added this phase; degraded path → 0.0)|
|**mid\_confidence**|consecutive same-regime days mapped through a saturating curve `\_MID\_CONFIDENCE\_BREAKPOINTS` `\[(0,0.1)(1,0.2)(3,0.4)(5,0.6)(7,0.75)(10,0.9)(14,1.0)]`|regime stability over recent history|`audit\_query.load\_all\_meta()` snapshot history; **Guard A** current-regime degrade→0.0; **Guard B** unknown/degraded history day is a hard streak break|
|**long\_confidence**|`data\_coverage × short\_confidence`|data-foundation solidity discounted by directional clarity|`MacroRegimeResult.data\_coverage` × short|

The two ToolResults persisted per run are `classify\_regime` (the regime signals) and `macro\_regime\_confidence` (the three confidences + vote counts + `consecutive\_same\_regime\_days`) — so every number the LLM might reference is evidence-bound.

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

### 6.3 MoneyFlowAgent data strategy (next phase)

GEX / DEX / OI-walls / gamma-squeeze monitor from **Massive** (`gex\_dex.compute\_gex\_dex`, with `prior\_result` DEX-trend for condition C) + dark-pool buy/sell pressure from **Quiver** (`compute\_dark\_pool\_signal`). Both are pure deterministic aggregators; the agent wraps them as evidence and asks the LLM for the flow/positioning implication.

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

\---

## 8\. Current Baseline \& Next Steps

```
Baseline:   main @ a19b862  (fix: structural repair layer for flat LLM AgentResult)
Test state: 69 test\_reliability\_\* parity suites (GREEN)
            + agent framework suite 15/15 (§8A.1–§8A.15)
            + Phase 8B MacroRegimeAgent 24/24 (§8B-M1–M11)
            + Phase 8B-0 24 (Quiver 6 / Massive 5 / GEX-DEX 13)
Built agents: MacroRegimeAgent (production)
```

**Next: Phase 8B — MoneyFlowAgent (STEP 0 first).** Consumes the Phase 8B-0 GEX/DEX (Massive) + dark-pool (Quiver) processed signals, following the MacroRegimeAgent pattern exactly: deterministic signals → two+ ToolResults → constrained prompt (with REQUIRED OUTPUT FORMAT) → `\_repair\_llm\_response` → validated `AgentOutput`; three horizon findings; agent-specific confidence formulas; additive Cockpit hook. STEP 0 must map the data/access matrix and decide the confidence definitions before coding.

After the foundation-agent roster fills in: the **PM layer** (ShortTermPM / MidTermPM / LongTermPM) and **MasterPM**, then the **Evidence Infrastructure / debate** phases (reverse DCF, valuation/macro debate) and the human-in-the-loop **Judgment Console**.

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

Every closeout syncs `PROJECT\_STATE.md`, `CURRENT\_TASK.md`, the phase doc, and `README.md`. README is a first-class deliverable; truthfulness rule applies (real hashes/counts, planned scope labeled as planned).

\---

## 10\. Known Issues \& Lessons Learned

### 10.1 This session's lessons (Phase 8 realignment)

1. **LLM schema compliance is not free — always add `\_repair\_llm\_response()`.** `claude-sonnet-4-6` consistently flattened `AgentResult` (top-level `text`/`evidence`, float `confidence`). With `extra="forbid"`, the flat shape is rejected → rule-based fallback. The prompt-side fix (REQUIRED OUTPUT FORMAT example) reduces it; the **structural repair layer** is the durable fix. Every future agent reuses it.
2. **Prompt JSON examples must use 4-space indentation, not backtick fences.** Fences interfere with `\_extract\_json\_obj`. The REQUIRED OUTPUT FORMAT block is built from plain (non-f) string literals so its braces are literal.
3. **Judgment extraction: first complete sentence, not hard truncation.** Mid-sentence 200-char truncation produced broken PM-facing text. Now: first sentence up to 400 chars; `validate\_judgment` limit raised 200→400.
4. **Streamlit secrets instability — prefer `set -a \&\& source .env`.** `.streamlit/secrets.toml` / `st.secrets` resolution has been unreliable; environment-variable injection is the dependable startup path.
5. **Lazy imports do not hot-reload reliably — full restart after editing an agent.** Because all `lib.reliability` imports are lazy (inside functions), Streamlit's module reload can serve a stale closure; restart the server rather than trusting hot-reload.
6. **Additive, key-gated, fail-closed is the safe way to wire an agent into a live page.** The Cockpit hook reuses the already-computed regime (no second fetch), gates on `\_has\_llm\_api\_key()`, owns its `try/except`, and writes only a new session key — so a keyless or failing agent is a clean no-op, never an aborted refresh.
7. **Activate, don't rebuild.** World 2 was fully built and dormant; the win was the thin connective tissue, not a rewrite.

### 10.2 Carried-over guardrails (still true)

8. The project is an investment **workflow/Fund system**, not a stock picker; the central path is **opportunity-first**, not ticker-first.
9. **Horizon awareness is mandatory** — the same ticker differs across short/mid/long; this is why agents emit three findings + three confidences.
10. **Review-only is non-negotiable.** `approved\_for\_execution` is always `False`.
11. **Append-only audit trails** (snapshots, anchor archive, agent-output JSONL, ingest log) — future evaluation uses audit snapshots, never rolling recomputation.
12. **Tighten-only market internals** — never flips regime or loosens gates.
13. **`thesis\_ingestion` / `theme\_transmission` isolation** — never imported by ranking/scoring/snapshot/anchor modules; `current\_evidence\_status` stays `"unknown"` until the Judgment Console phase.
14. **STEP 0 reuse-over-rebuild** — scan Phase 0–5 legacy code for reusable structures before writing new ones (e.g. MoneyFlowAgent reuses the Phase 2E option schema and the MacroRegimeAgent pattern wholesale).

### 10.3 Open design debt

* **Split-brain still partial.** Only MacroRegimeAgent is wired; the live pages still consume deterministic producers directly. Activation proceeds agent-by-agent.
* **`llm\_orchestrator.py` lenient JSON scanner** (`\_first\_obj`) shares the silent-inner-object risk that bit the thesis extractor; guarded only by callers' per-key checks. Latent, not yet fixed.
* **Calibration debt** — fragility thresholds after more snapshots; vol\_shrink/weak-bounce definitions; valuation\_role + peer-match edge cases.
* **No PM layer yet** — foundation agents emit per-horizon findings, but ShortTermPM/MidTermPM/LongTermPM/MasterPM are unbuilt.

> The authoritative, full collaboration-lessons ledger lives in the live phase docs / ROADMAP; this section reproduces what is current as of `a19b862`. On any conflict, the live docs win.

\---

## 11\. Cross-Session Startup Block

```
We are continuing the AI Investment OS project (an AI Fund workflow system, not a dashboard).

Authoritative sources: latest README.md + docs/ai\_dev\_state/PROJECT\_STATE.md + CURRENT\_TASK.md.
This memo (Master Memo v3, 2026-06-21) is supplementary P1 context; it yields to the live docs on conflict.

Current baseline:
- main @ a19b862 (Phase 8B MacroRegimeAgent production + repair-layer/judgment fixes)
- 69 parity suites + agent framework 15/15 + Phase 8B 24/24 + Phase 8B-0 24

Architecture (Phase 8 realignment):
- Two worlds: World 1 (live Streamlit deterministic producers) + World 2 (reliability/evidence stack).
  Phase 8 activates World 2 via lib/agent\_framework/ connective tissue — wrap deterministic
  outputs as evidence → constrained LLM call → validate → AgentOutput. Activate, don't rebuild.
- Pipeline: data layer → \~11 foundation agents (one per signal domain) → PM layer
  (ShortTermPM/MidTermPM/LongTermPM) → MasterPM → UI (AI-PM reporting + human confirmation).
- LLM boundary: code computes ALL numbers; LLM synthesizes implications and emits NO numeric value.

Built so far:
- MacroRegimeAgent (production): 3 deterministic confidences (short=vote agreement,
  mid=consecutive same-regime days, long=data\_coverage\*short), two ToolResults, three
  horizon findings, additive key-gated Cockpit hook.
- Data sources: + Quiver Quantitative (Hobbyist) + Massive Options (Starter); Unusual Whales excluded.

Non-negotiables:
- approved\_for\_execution always False; evidence\_refs never empty; numeric firewall.
- All lib.reliability imports lazy (never from package root).
- \_repair\_llm\_response() pattern + REQUIRED OUTPUT FORMAT prompt block for every agent.
- valid\_until = end\_of\_today\_iso(); judgment = first complete sentence, no numerics.
- Append-only audit; tighten-only internals; exclude-not-down-weight; never fabricate a number.

Next task:
- Phase 8B — MoneyFlowAgent (STEP 0 first): consume Phase 8B-0 GEX/DEX (Massive) + dark pool
  (Quiver); same pattern as MacroRegimeAgent; agent-specific confidences.

Collaboration:
- Chinese for architecture; English single-code-block prompts (4-space inner JSON, no fences).
- Streamlit: set -a \&\& source .env \&\& set +a \&\& streamlit run app.py
- Git: --no-ff merges, heredoc commits, push only after explicit APPROVE, report unexpected state.
```

\---

## 12\. The Most Important Things Not to Forget

1. It is an **AI Fund workflow system**, not a stock picker or a dashboard. The UI reports the AI PM team's work; it is not the decision tool.
2. **Activate, don't rebuild** — World 2 was dormant, not missing. Connective tissue beats rewrites.
3. **Code computes every number; the LLM emits none.** Findings cite evidence; judgments are numeric-free.
4. **`approved\_for\_execution` is always `False`.** Review-only, no broker, ever.
5. **`evidence\_refs` must never be empty**; an agent without evidence is not created.
6. **`\_repair\_llm\_response()` + REQUIRED OUTPUT FORMAT** are mandatory for every agent — LLMs flatten the schema.
7. **All `lib.reliability` imports lazy** — importing the agent framework must not trigger the eager reliability `\_\_init\_\_`.
8. **Three findings + three confidences per foundation agent** — so the PM layer can consume by horizon.
9. **`valid\_until = end\_of\_today\_iso()`** for foundation agents (daily refresh expiry).
10. **Append-only audit trails**; future evaluation uses snapshots, never rolling recompute.
11. **Tighten-only internals; exclude-not-down-weight; never fabricate a number** (live or historical).
12. **STEP 0 reuse-over-rebuild** and **access-path-matrix-first** before any wiring.
13. **README + PROJECT\_STATE/CURRENT\_TASK are authoritative**; this memo yields to them.
14. **Streamlit via `set -a \&\& source .env`**, full restart after agent edits, and additive/key-gated/fail-closed when wiring an agent into a live page.

