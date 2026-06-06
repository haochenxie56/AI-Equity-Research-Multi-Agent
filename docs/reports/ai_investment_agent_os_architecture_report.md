# AI Investment Agent OS Architecture / Functionality Audit

**Date**: 2026-06-05  
**Scope**: Repository comprehension and product/architecture audit only. No functional code changes were made.  
**Audience**: Project owner and future ChatGPT/Codex sessions planning the next roadmap.

## 1. Executive Summary

The repository has evolved from a five-step Claude-assisted equity research app into an early-stage **AI Investment OS**. The current codebase includes a Streamlit UI, live/free-source macro and signal modules, deterministic valuation/technical/risk logic, a holdings/trading-desk workflow, and a large offline reliability/evidence architecture.

The strongest implementation areas are:

- **Deterministic market-data and calculation modules**: macro regime classification, technical indicators, valuation anchors, app fair value, signal scoring, order-entry zones, thesis monitor, and portfolio/risk overlays.
- **Product workflow scaffolding**: Investment Cockpit, Macro Dashboard, Scanner, Equity Research, and Trading Desk now share session-state handoffs.
- **Reliability primitives**: typed `ToolResult`, `EvidenceRef`, `AgentResult`, validators, critic, orchestration, decision packet, memory schemas, and many mock-only tests.

The weakest areas are:

- The system is **not yet a full-market stock-selection engine**. It screens a capped universe built from a hardcoded S&P 500 top-100 list, selected theme baskets, manual tickers, and session handoffs, not all NYSE/NASDAQ names.
- Many reliability artifacts remain **offline/schema/test-only** and are not enforced around the live Streamlit LLM calls.
- Theme/narrative logic is useful but still lightweight: no deep supply-chain graph, no robust beneficiary-tier taxonomy, no ETF-flow/options-flow/social/KOL layer, and no persistent post-entry research memory loop wired into the live app.
- README claims are directionally aligned with current Phase 6C work but sometimes overstate maturity, especially around “autonomous discovery,” “real-time” macro, agent debate, and complete Track A/Track B data coverage.

Fit against the requested four-layer trading framework:

| Layer | Current Support | Summary |
|---|---:|---|
| Layer 1 Fundamental / Narrative Validity | Partial | Has business/financial pages, LLM narrative matching, theme tags, EPS/valuation/margin/quality scoring, but beneficiary classification and narrative-to-financial proof are shallow. |
| Layer 2 Marginal Capital / Catalyst Logic | Partial | Has LLM catalyst extraction from news, unusual-news keywords, analyst revision signal, insider signal, macro/rotation context; lacks explicit marginal-buyer hypothesis, ETF/options/dealer/social/institutional flow. |
| Layer 3 Price-Volume / Technical Confirmation | Strong/Partial | Technical indicators, relative sector rotation, entry quality, support/resistance, EMA/SMA/ATR/RSI/ADX/volume are implemented; relative strength versus QQQ/SPY/peers and group-confirmation are incomplete. |
| Layer 4 Position Sizing / Risk Management | Partial/Strong | Trading Desk implements holdings, thesis status, horizon-aware entry zones, stops, risk overlay, max position settings, add logic; long-horizon thesis/valuation overlay exists but monitoring is not yet a full persistent loop. |

Overall maturity: **credible prototype / early productized OS**, not yet a production-grade investment decision system.

## 2. Current Repository / Project State

Required state files inspected first:

- `docs/ai_dev_state/PROJECT_STATE.md`
- `docs/ai_dev_state/CURRENT_TASK.md`
- `docs/ai_dev_state/PHASE_2_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_3_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_3R_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_4M_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_5_CLOSEOUT.md`

Current state from the files:

- Phase 0-3: accepted reliability foundation and offline orchestration skeletons.
- Phase 3R: accepted roadmap backfill for event intelligence, trade plan, allocation, option expression skeletons.
- Phase 4M: accepted memory/human-feedback/agent-evaluation schema/helper layer, still offline and non-persistent.
- Phase 5A-5R: accepted productization/demo UI and fixture-backed cockpit/macro layers.
- Phase 5S closeout file says implemented awaiting review, but `PROJECT_STATE.md` later states Phase 5S and Phase 5R were accepted during subsequent Phase 6 progress. This is a documentation lag.
- Phase 6A: live macro data integration implemented.
- Phase 6B: live signal layer / dual-track stock selection implemented.
- Phase 6C-A v1/v2/v3: Trading Desk and Entry Strategy v4 implemented, awaiting review in state wording.
- Phase 6C-B: current task, implemented awaiting Codex review. It rebuilds Investment Cockpit into a live aggregation hub and wires app-computed fair value into Trading Desk.
- Phase 6D Monitoring & Review has not started.

State consistency:

- The high-level state is mostly consistent: Phase 6C-B is current and not accepted.
- Older closeout files are historical and sometimes say later phases have not started. That is expected for checkpoint files.
- The biggest inconsistency is `PHASE_5_CLOSEOUT.md` saying Phase 5S is awaiting review while `PROJECT_STATE.md` later treats Phase 5S as accepted in the Phase 6 timeline.
- README is ahead of the most conservative state docs and describes the app as a more integrated OS. Actual code partially supports this, but not all claims are fully mature.

Git state:

- The working tree was already heavily dirty before this report. Many Phase 5/6 files are untracked or modified.
- Latest commit shown by `git log --oneline -n 10`: `046dfa4 docs: update README to reflect current architecture`.

## 3. Architecture Overview

### App / UI Layer

Purpose: Streamlit multi-page app with bilingual UI, dark/light mode, shared navigation, and workflow handoffs.

Important files:

- `app.py`: home page and legacy module cards.
- `ui_utils.py`: theme, translations, sidebar, formatting, cached data loaders.
- `pages/1_Overview.py`: legacy one-click AI research workflow.
- `pages/2_Sector.py`: GICS sector analysis plus AI theme baskets.
- `pages/3_Scanner.py`: scanner and Phase 6B signal candidate UI.
- `pages/4_Equity.py`: stock deep-dive plus Phase 6C-B AI valuation summary.
- `pages/5_Financial.py`, `pages/6_PriceVolume.py`: sub-surfaces under Equity Research.
- `pages/7_Investment_Cockpit.py`: current primary cockpit / live aggregation hub.
- `pages/8_Macro_Dashboard.py`: live/fixture macro dashboard.
- `pages/9_Trading_Desk.py`: holdings, thesis monitor, order recommendations, opportunity watch.

Integration: Uses `st.session_state` as the main cross-page bus: `macro_regime_result`, `theme_momentum_results`, `cockpit_all_signals`, `cockpit_triple_signals`, `equity_research_results`, `td_pending_signals`, `td_prefill`, `holdings.json` data.

### Workflow Orchestration

There are two orchestration models:

- Legacy live workflow in `pages/1_Overview.py` and `lib/workflow_state.py`.
- Cockpit-driven workflow in `pages/7_Investment_Cockpit.py`.

The Cockpit refresh runs:

1. `fetch_all_macro()` + `classify_regime()` and stores regime through `macro_state`.
2. `compute_all_themes()`.
3. `generate_candidates()`, which publishes scanner signals.
4. Equity valuation is now on demand via “Run Equity Research,” not part of Refresh All.

This is implemented and integrated through session state, but it is not a durable workflow engine or job graph.

### Data Fetching

Important files:

- `lib/data_fetcher.py`: yfinance primary, polygon.io fallback for OHLCV, Finnhub news, earnings calendar, recommendations, pre/post market.
- `lib/macro_data.py`: yfinance, FRED, Finnhub free endpoints; per-group fixture fallbacks.
- `lib/theme_baskets.py`: yfinance returns for ETFs/constituents, fixture fallback.
- `lib/signal_engine.py`: yfinance/Finnhub signal reads, cached and fail-closed.

Data is cached through `lib/cache_manager.py`, Streamlit caches, and Parquet files in `data/us/`.

### Valuation

Important files:

- `lib/valuation.py`: classic DCF/WACC/comps helpers.
- `lib/financial_tab.py`: financial statement UI and scenario DCF.
- `lib/valuation_anchor.py`: analyst/relative anchor, dispersion, analyst count, confidence tier.
- `lib/equity_valuation.py`: app-computed fair value blending DCF, relative sector P/E, and analyst target into low/mid/high.

Deterministic. LLM only narrates/debates in `lib/llm_orchestrator.analyze_equity_fair_value_debate`.

### Technical Analysis

Important files:

- `lib/technical.py`: EMA/SMA, RSI, MACD, Bollinger, ATR, ADX, OBV, volume ratio, nearest swing support/resistance, candlestick pattern.
- `lib/pv_tab.py`: UI for chart/technical page.
- `lib/order_advisor.py`: consumes technical snapshots for entry zones.

Deterministic and integrated into Scanner, Trading Desk, and Price/Volume page.

### Rotation / Sector / Theme

Important files:

- `lib/rotation.py`: GICS sector ETF scoring, subsector scores, rotation phase, sector stock ranking, volume flow, sector valuation.
- `lib/theme_baskets.py`: 12 cross-GICS AI theme baskets and theme momentum.
- `pages/2_Sector.py`: sector/theme UI and handoff to Scanner.

Implementation is practical and useful, but the theme taxonomy is manually curated and shallow relative to the desired AI value-chain rotation system.

### Stock Selection / Signal Engine

Important files:

- `lib/candidate_generator.py`
- `lib/signal_engine.py`
- `pages/3_Scanner.py`
- `pages/7_Investment_Cockpit.py`

Current design:

- Universe = S&P 500 top-100 + selected theme baskets + manual tickers + Sector handoff + legacy workflow state, capped by config.
- Track A = hard filter, LLM narrative/catalyst match, deterministic fundamentals, deterministic entry quality.
- Track B = insider signal, unusual news keywords, analyst revision signal.
- Scores are composed into short/mid/long horizon scores and `single`/`double`/`triple` signal strength.

### Portfolio / Risk / Trading Desk

Important files:

- `lib/holdings.py`: `HoldingRecord`, `PortfolioSettings`, cash, holdings CRUD, JSON persistence.
- `lib/thesis_monitor.py`: thesis status from news, EPS, technical, macro, short time stop.
- `lib/order_advisor.py`: horizon/scenario-aware entry zones, stops, risk/reward, sizing, add overlay.
- `pages/9_Trading_Desk.py`: UI.

This is one of the more product-complete areas. Guardrails keep `approved_for_execution=False` and no broker/order execution exists.

### Reliability / Evidence Layer

Important files:

- Core: `lib/reliability/schemas.py`, `evidence_store.py`, `validators.py`, `adapters.py`, `agent_output.py`.
- Review: `critic.py`, `validation_aggregator.py`, `staleness.py`, `evaluation.py`.
- Pipeline: `orchestration.py`, `horizon_synthesis.py`, `macro_agent.py`, `debate.py`, `decision_packet.py`, `human_review.py`, `review_loop.py`.
- Memory: `research_memory.py`, `thesis_memory.py`, `event_memory.py`, `allocation_memory.py`, `option_trade_memory.py`, `human_feedback_memory.py`, `agent_evaluation.py`.
- Phase 5 product contracts: `phase5_*`.

Mostly deterministic, offline, and mock-only. Powerful as a future audit framework; not fully enforced in live LLM routes.

## 4. End-to-End Workflow

### Implemented and Integrated

1. User opens Investment Cockpit.
2. Clicks Refresh All.
3. Cockpit fetches macro data, classifies regime, computes theme momentum, and generates candidates.
4. Candidate signals are displayed and can be staged for Trading Desk or selected for equity valuation.
5. User runs equity research for selected tickers.
6. App computes fair value and optionally runs LLM debate constrained to app-computed numbers.
7. Fair value is stored in session state.
8. Trading Desk consumes holdings, thesis checks, app fair values, and technicals to compute order recommendations.
9. User manually records/edits/monitors positions in `data/holdings.json`.

### Implemented but Isolated / Partially Integrated

- Reliability `AgentResult` validation and evidence store are not wrapped around all live LLM calls.
- Phase 3/4/5 reliability decision/debate/memory artifacts are mostly schema/view-model/test artifacts, not live runtime controllers.
- Macro Dashboard publishes live regime to session state, but fixture Phase 5 macro view-models still coexist.

### Planned / Documented but Not Fully Implemented

- Persistent research memory beyond holdings JSON.
- Full market regime and theme universe construction from institutional-grade sources.
- Explicit marginal-buyer engine.
- Real ETF flows, options flow/dealer positioning, short interest, social/KOL signals.
- Broker/order execution, intentionally absent.

## 5. Current Feature Inventory

| Area | Feature | Implemented? | Integrated? | Relevant Files | Notes |
|---|---|---:|---:|---|---|
| Market regime | Live macro fetch + regime classifier | Yes | Yes | `macro_data.py`, `macro_regime.py`, `pages/8`, `pages/7` | Free sources; coverage guard can degrade to fixture. |
| Sector/theme rotation | GICS sector rotation | Yes | Yes | `rotation.py`, `pages/2` | ETF momentum and valuation. |
| Sector/theme rotation | 12 AI theme baskets | Yes | Yes | `theme_baskets.py`, `pages/2`, `pages/7` | Static curated taxonomy. |
| Stock research | Single-ticker equity research | Yes | Yes | `pages/4`, `llm_orchestrator.py`, `data_fetcher.py` | LLM plus yfinance data. |
| Valuation | DCF/WACC/comps | Yes | Yes | `valuation.py`, `financial_tab.py` | Financial page and report. |
| Valuation | App fair value low/mid/high | Yes | Yes | `equity_valuation.py`, `pages/4`, `pages/7`, `order_advisor.py` | Session-state handoff to Trading Desk. |
| Technical | Indicators and snapshot | Yes | Yes | `technical.py`, `pv_tab.py`, `order_advisor.py` | Good deterministic coverage. |
| Catalyst | LLM catalyst from recent news | Yes | Partial | `signal_engine.py` | Only for top-N LLM narrative calls; no structured event calendar engine. |
| News | Company news | Yes | Partial | `data_fetcher.py`, `signal_engine.py`, `thesis_monitor.py` | Finnhub free; keyword sentiment and LLM interpretation. |
| Analyst consensus | Targets and recommendation revisions | Yes | Partial | `valuation_anchor.py`, `equity_valuation.py`, `signal_engine.py` | Uses yfinance info and Finnhub recommendation history. |
| Options/dealer flow | Option expression schema | Schema only | No | `reliability/option_expression.py` | No live option chain or dealer flow. |
| Short squeeze | Squeeze logic | Missing | No | N/A | No short interest / borrow / options squeeze scoring. |
| Portfolio allocation | Holdings + settings | Yes | Yes | `holdings.py`, `pages/9` | JSON persistence. |
| Risk overlay | Horizon/scenario entry and add overlay | Yes | Yes | `order_advisor.py` | Stronger than most modules. |
| Horizon decisions | Short/mid/long scoring | Yes | Yes | `signal_engine.py`, `order_advisor.py`, `pages/3`, `pages/9` | Implemented for signals and entry zones. |
| Monitoring loop | Thesis invalidation monitor | Yes | Partial | `thesis_monitor.py`, `pages/9` | Runs on Trading Desk load; not a scheduled/persistent monitor. |
| Evidence validation | Evidence refs and numeric validation | Yes | Isolated | `reliability/*` | Not generally wired into live LLM routes. |
| Hallucination prevention | Parser/validator/critic/evals | Yes | Partial | `reliability/*`, `scripts/test_reliability_*` | Strong offline, weaker live. |
| Agent confidence | Confidence schema | Yes | Isolated | `schemas.py`, many reliability modules | Live LLM outputs use bespoke fields. |
| Decision synthesis | DecisionPacket skeleton | Yes | Isolated | `decision_packet.py` | Research-only skeleton. |
| UI/reporting | Streamlit pages + Markdown report writers | Yes | Yes | `pages/*`, `report_writer.py` | UI is functional; app home still has legacy links. |
| Persistence | Parquet cache + holdings JSON | Yes | Yes | `cache_manager.py`, `holdings.py`, `data/us` | No DB/vector store. |

## 6. Reliability / Evidence Architecture

The reliability system is extensive but mostly separate from the live product flow.

Evidence objects:

- `DataSnapshot`: raw-source payload with `snapshot_id`, source, data, fetched timestamp.
- `ToolResult`: primary deterministic evidence unit with `evidence_id`, tool name, run ID, inputs, outputs, snapshots.
- `EvidenceRef`: LLM claim reference back to a `ToolResult`; supports `tool_name`, `metric`, `field_path`, and `snapshot_id`.
- `AgentResult`: constrained LLM output with findings, assumptions, risks, and confidence.
- `ValidationReport`: result of validating an `AgentResult`.

Evidence IDs:

- `adapters.make_evidence_id()` builds deterministic IDs from run ID, tool name, target, metric group, and payload hash.
- `EvidenceStore` is an in-memory map backed by append-only `tool_results.jsonl`.

Numeric claim binding:

- `validate_agent_result()` detects numeric/metric-looking claims using regex.
- Numeric findings without evidence produce `UNSUPPORTED_NUMERIC_CLAIM` errors.
- Numeric findings with evidence but without valid metric/tool/field binding produce `WEAK_NUMERIC_EVIDENCE_BINDING` warnings.
- Field paths resolve only through safe dot-separated dict keys/list indexes.

Important limitation:

- Validation proves a referenced field exists; it does **not** prove the prose accurately restates the field value or that the evidence is semantically relevant. A finding can cite an existing evidence ID/field and still be misleading.
- Non-numeric qualitative claims can pass with weak or irrelevant evidence more easily.

Agent output parsing:

- `parse_agent_result_json()` parses JSON or dict into the constrained schema.
- It rejects extra fields and malformed payloads but does not fabricate missing evidence.

Critic/review:

- `critic.py` provides deterministic critic issues for unsupported claims, stale data, validation failures, missing risk/assumptions, overconfidence, conflicts, and safety concerns.
- `orchestration.py`, `decision_packet.py`, and review-loop modules chain validation/staleness/critic outputs.

Tests:

- 70 `scripts/test_reliability*.py` files exist.
- Tests heavily cover schema contracts, negative cases, validation, critic behavior, phase closeouts, and mock-only product contracts.
- Tests are strong for contract regressions but do not prove investment quality, alpha, or live-data decision validity.

Overall anti-hallucination strength:

- **Strong offline foundation** for auditable research artifacts.
- **Partial live protection**: live LLM calls often use constrained JSON and fail-closed parsers, but not the full `ToolResult`/`AgentResult`/`EvidenceStore` validation pipeline.

## 7. Fit Against the Four-Layer Trading Framework

### Layer 1 — Fundamental / Narrative Validity: Partial

Supported:

- Equity page uses yfinance info, business summary, financials, news, valuation, and LLM research.
- Scanner Track A uses narrative stage, macro alignment, narrative strength, theme tags, EPS revision, valuation percentile, margin trend, and quality composite.
- Theme baskets define AI value-chain-like groups such as AI chips, HBM, optical networking, AI servers, data-center power, cloud, data infra, AI software, cybersecurity, edge AI, robotics.

Missing/weak:

- No robust “core / second-order / peripheral beneficiary” classifier.
- No structured mapping from revenue/backlog/capex/customer demand/policy support to theme exposure.
- No explicit “stock already pricing in bull case” framework beyond valuation percentile and fair-value upside.

Rating: **Partial**.

### Layer 2 — Marginal Capital / Catalyst Logic: Partial

Supported:

- LLM catalyst extraction from recent company news.
- Catalyst horizon/recency/already-priced-in fields.
- Track B insider buying, unusual news keywords, and analyst revision signal.
- Macro regime, theme momentum, and sector rotation context.
- Earnings calendar and news helpers exist.

Missing/weak:

- No explicit marginal-buyer hypothesis object.
- No ETF/index inclusion engine, ETF flow data, institutional accumulation proxy, options/dealer hedging, short interest, borrow data, or social/KOL attention.
- Analyst upgrades are approximated through Finnhub recommendation history rather than a rich estimate/target revision feed.

Rating: **Partial**.

### Layer 3 — Price-Volume / Technical Confirmation: Strong / Partial

Supported:

- EMA10/20, SMA20/50/200, RSI, MACD, ADX, ATR, Bollinger, OBV, volume ratio.
- Support/resistance from swing levels.
- Candlestick pattern detection.
- Entry quality and horizon-specific gates.
- Sector rotation and ETF relative momentum versus SPY in `rotation.py` and macro ETF returns.

Missing/weak:

- No systematic relative strength ranking versus QQQ/SPY/sector peers at ticker level inside the four-layer candidate score.
- No explicit multi-stock theme confirmation logic beyond theme momentum and scanner candidate grouping.
- Accumulation/distribution is limited; OBV exists but is not central to scoring.

Rating: **Strong/Partial**.

### Layer 4 — Position Sizing / Risk Management: Partial / Strong

Supported:

- Holdings persistence and active-position monitor.
- Thesis status: intact/watch/weakening/broken.
- Horizon-aware entries: short EMA/volume, mid SMA50/volume, long valuation/SMA200.
- Long-horizon risk avoids a simple fixed percentage stop and uses thesis/valuation framing.
- Portfolio settings include max position percentage, short/mid max loss, long stop label.
- Add overlay checks max position, risk-to-stop budget, projected weight, and blended cost.

Missing/weak:

- No complete portfolio optimizer or risk aggregation across correlated themes.
- No durable monitoring scheduler/alerting beyond page-load refresh/cache.
- Add/trim/exit plan is computed per position but not managed as a persistent lifecycle plan with outcome review.

Rating: **Partial/Strong**.

## 8. Stock Selection / Screening Capability Assessment

Can it screen a universe? **Yes, but not the full market.**

- Universe is capped and composed from hardcoded S&P top-100, selected theme baskets, manual tickers, Sector handoffs, and legacy workflow state.
- It does not enumerate all NYSE/NASDAQ names.

Can it rank stocks inside a theme? **Partially.**

- Theme basket constituents can be included in Scanner.
- `rotation.rank_sector_stocks()` ranks sector constituents.
- There is no full theme-specific leader/laggard ranking with beneficiary tiers and value-chain layers.

Can it identify sector/theme leaders and second-order beneficiaries? **Weak/Partial.**

- It has hardcoded theme constituents and GICS sector leaders/challengers/sleepers.
- It does not classify direct versus second-order versus speculative exposure in a structured way.

Can it compare stocks across AI value chain? **Partial.**

- The 12 theme baskets approximate the AI value chain.
- There is no graph/taxonomy model that assigns exposure type, revenue sensitivity, capex linkage, or customer dependency.

Can it detect next rotation candidates? **Partial.**

- It rewards early narrative stage, inflecting EPS, valuation gap, and oversold entry quality.
- It lacks explicit “next layer rotation” logic across value-chain layers.

Scoring support:

| Scoring Dimension | Current Support |
|---|---|
| Narrative fit | Yes, LLM narrative tags/stage/strength. |
| Catalyst strength | Partial, LLM catalyst plus recency/priced-in. |
| Relative strength | Partial, technical entry quality and sector/theme momentum; not robust ticker-relative-to-peer/QQQ. |
| Valuation gap | Yes, valuation percentile and app fair value. |
| Liquidity | Partial, market cap and dollar ADV gates. |
| Institutional/analyst support | Partial, analyst count/target/recommendation revision; no institutional holdings/flow. |
| Risk/reward | Yes in Trading Desk; less central in Scanner ranking. |
| Position suitability | Yes in Trading Desk; partial in Scanner horizon scores. |

Trade type separation:

- Long-term compounders: partial through long horizon valuation/quality/margin.
- Mid-term theme rotation trades: partial through EPS/narrative/macro.
- Short-term event trades: partial through catalyst/entry quality.
- Speculative squeeze/momentum trades: weak; no short interest/options flow.

Practical missing pieces:

- Full universe builder.
- Theme exposure taxonomy.
- Cross-theme and within-theme ranking.
- Marginal-buyer model.
- Options/short/flow data.
- Persistent watchlist score history.
- Backtesting/evaluation of signal quality.

## 9. Data Source Assessment

| Source | Provides | Used In | Limitations |
|---|---|---|---|
| yfinance | OHLCV, info, financials, analyst targets, EPS fields, recommendations, ETF returns | Most modules | Unofficial, inconsistent fields, rate limits, stale/missing data. |
| Finnhub | Company news, market news, insider transactions, recommendation trends, social sentiment attempt | `data_fetcher.py`, `signal_engine.py`, `macro_data.py`, `thesis_monitor.py` | Free tier limits; some endpoints premium; incomplete analyst/insider coverage. |
| FRED | Rates, breakevens, credit, dollar, economic releases | `macro_data.py` | Requires key; can rate-limit; macro data lag. |
| polygon.io | OHLCV fallback | `data_fetcher.py` | Requires key; fallback path only. |
| Local Parquet cache | Cached OHLCV/financial data | `data/us`, `cache_manager.py` | Cache hygiene/staleness controls are basic. |
| `data/holdings.json` | Holdings, cash, portfolio settings | `holdings.py`, Trading Desk | Manual and local only. |
| Static theme baskets | AI value-chain-like universe | `theme_baskets.py`, Scanner/Sector/Cockpit | Manually curated, not exhaustive, no exposure weights. |

Missing data for target framework:

- Full NYSE/NASDAQ listings and liquidity metadata.
- SEC filings and earnings call transcripts.
- Analyst estimate revisions and target-change history.
- ETF holdings and flow data.
- Options chain, IV rank, skew, unusual options flow, dealer gamma.
- Short interest, borrow fee, days-to-cover.
- Institutional ownership/13F changes.
- Social/KOL attention.
- Corporate event calendars, policy/contract databases.

## 10. Test Coverage / Quality Assessment

Observed:

- 70 reliability test scripts exist.
- Phase-specific tests cover adapters, schemas, validation, critic, horizon, macro, option/allocation/trade-plan memory, Phase 5 UI contracts, Phase 6 live data, signal layer, scanner universe, Trading Desk, entry strategy, and Cockpit rebuild.
- Targeted compile check passed for key Phase 6 files: `pages/7_Investment_Cockpit.py`, `pages/8_Macro_Dashboard.py`, `pages/9_Trading_Desk.py`, `lib/order_advisor.py`, `lib/candidate_generator.py`, `lib/signal_engine.py`.

Strengths:

- Strong schema/contract and negative-case coverage.
- Good guardrail tests around review-only outputs and `approved_for_execution`.
- Mock-only tests reduce network brittleness.

Gaps:

- Tests mostly validate contracts and deterministic rules, not investment workflow quality.
- Little evidence of end-to-end UI integration tests against live Streamlit pages in current Phase 6 paths.
- No backtest or historical eval harness for stock-selection performance.
- No data-quality evals for yfinance/Finnhub field missingness.
- Reliability tests do not mean live LLM outputs are evidence-validated in production flow.

## 11. Major Gaps and Design Risks

1. **Full stock selection remains constrained.** The universe is capped and manually/static-driven, not full NYSE/NASDAQ.
2. **Reliability/live gap.** The strongest anti-hallucination layer is not yet the mandatory wrapper around live LLM research outputs.
3. **Theme taxonomy is static.** It lacks exposure weights, beneficiary tiers, supply-chain graph edges, and freshness.
4. **Marginal buyer logic is missing as a first-class module.**
5. **Catalyst engine is lightweight.** News LLM extraction and keywords help, but structured event/earnings/estimate/policy/contract logic is incomplete.
6. **Alternative signals are thin.** No options flow, short squeeze, ETF flows, dealer positioning, institutional accumulation, or social attention.
7. **Portfolio risk is per-position.** There is no cross-position correlation/theme exposure control.
8. **Monitoring is not durable.** Thesis monitor runs in UI/session context, not as scheduled persistent monitoring.
9. **State/README drift.** README describes an ambitious OS; actual code partially supports it, with some features still prototype-level.
10. **Data reliability.** Heavy dependence on yfinance/Finnhub free fields creates missing/stale/inconsistent-data risk.

## 12. README Consistency Audit

Classification key:

1. Fully implemented and integrated.
2. Implemented but isolated.
3. Partially implemented.
4. UI/documentation only.
5. Missing.

| README Claim | Classification | Evidence / Notes |
|---|---:|---|
| Investment Cockpit | 3 | `pages/7` is live aggregation hub for macro/themes/signals and on-demand valuation; not a durable OS orchestrator. |
| Trading Desk | 1/3 | `pages/9`, `holdings.py`, `thesis_monitor.py`, `order_advisor.py` integrated; no execution, scheduler, or broker by design. |
| Macro Dashboard | 1/3 | Live/free macro fetch and deterministic classifier integrated; “real-time” is cached/free-source and can degrade to fixture. |
| Sector Research | 1/3 | GICS and theme UI exist; deeper AI value-chain taxonomy remains partial. |
| Stock Scanner | 3 | Dual-track scanner exists; not full market and not all alt data. |
| Equity Research | 1/3 | Single-ticker research and fair-value summary exist; debate is LLM narrative over numbers, not multi-agent validated workflow. |
| Financial Analysis | 1 | Financial page and valuation helpers exist. |
| Price & Volume | 1 | Technical page and indicator engine exist. |
| Track A four-layer funnel | 3 | Implemented as hard filter, LLM narrative, fundamentals, entry quality; differs from owner’s four-layer trading framework and is not full-market. |
| Track B alternative signals | 3 | Insider/unusual news/analyst revision exist; no options/short/social/ETF/institutional flow. |
| Short/Mid/Long horizon scoring | 1/3 | Implemented in signal engine and order advisor; scoring quality not backtested. |
| Entry Strategy v4 | 1/3 | Implemented in `order_advisor.py`; no execution, review-only. |
| Thesis Invalidation Monitor | 1/3 | Implemented and integrated in Trading Desk; runs on page load/cache, not scheduled. |
| Deterministic numeric calculations | 1 | Core numbers are code-computed. |
| LLM-only interpretation | 3 | Mostly true for Phase 6 modules, but legacy LLM workflow still has bespoke JSON outputs not fully routed through reliability evidence validation. |

## 13. Recommendations for Future Roadmap

### Near-Term Architecture Fixes

1. Define one canonical live workflow graph: Macro → Theme → Universe → Scanner → Research Pack → Debate → Decision/Trade Plan → Monitor.
2. Replace ad hoc session-state handoffs with typed view-model/session contracts.
3. Wire live LLM outputs through `AgentResult`/`EvidenceStore` validation at least in shadow mode.
4. Add source-quality and freshness banners to every live-derived decision panel.
5. Reconcile README/state docs after Phase 6C-B review so claimed capabilities match accepted code.

### Feature Additions for Stock Selection

1. Full US universe builder with exchange, market cap, ADV, price, sector, and listing filters.
2. Theme Universe Builder with exposure tiers: core, second-order, peripheral, speculative.
3. AI Value Chain Taxonomy with layers, dependencies, exposure weights, and freshness.
4. Relative Strength Ranker versus SPY, QQQ, sector ETF, and theme peers.
5. Catalyst Engine covering earnings, estimate revisions, guidance, policy, contracts, product events, customer read-throughs.
6. Marginal Buyer Hypothesis Generator: who buys next, why now, and what evidence would confirm it.
7. Watchlist Scoring Engine combining narrative, catalyst, valuation, technical, liquidity, analyst support, and risk/reward.
8. Horizon Classifier separating investment, swing trade, event trade, and speculative momentum/squeeze setups.

### Reliability Improvements

1. Treat every deterministic calculation as a `ToolResult`.
2. Require every numeric LLM claim to cite `EvidenceRef.field_path`.
3. Add semantic evidence checks: quoted value equals evidence value within tolerance.
4. Add live shadow-mode validation around Sector/Scanner/Equity/Trading Desk LLM calls.
5. Persist research runs and validated decision packets, not just holdings.

### Data Improvements

1. Add official listings/universe source.
2. Add SEC filings and earnings-call transcript ingestion.
3. Add analyst estimate/target revision history.
4. Add options chain, IV rank, OI/volume, skew, and possibly gamma/dealer proxies.
5. Add short interest/borrow data.
6. Add ETF holdings/flow data.
7. Add institutional ownership/13F deltas.
8. Add social/KOL attention data only with strict source quality controls.

### UI / Product Workflow Improvements

1. Make Cockpit the true funnel: regime → hottest themes → theme layers → ranked tickers → research pack → entry plan → monitor.
2. Add a Theme Detail page with layer map and candidate rankings.
3. Add candidate compare view across horizons.
4. Add a persistent Watchlist/Opportunity Queue with score history.
5. Add a Monitoring page for thesis changes, catalysts, price alerts, and position actions.
6. Surface “why not now?” blockers as first-class UI: missing catalyst, poor entry, valuation stretched, weak evidence, macro headwind.

## 14. Questions / Handoff Items for Strategy Review

1. How should the stock selection scoring model weight narrative fit, catalyst strength, valuation gap, technical confirmation, liquidity, and risk/reward by horizon?
2. Which parts of stock selection must be deterministic versus LLM-generated?
3. What is the highest-ROI next module: full universe builder, relative strength ranker, catalyst engine, or evidence validation integration?
4. How should the AI value-chain taxonomy represent layers, exposure weights, and beneficiary tiers?
5. How should the system distinguish long-term investment, mid-term rotation trade, short-term event trade, and speculative squeeze/momentum trade?
6. What data must be added before real stock ranking is credible enough for owner use?
7. How should horizon-aware risk management integrate with portfolio-level theme/correlation exposure?
8. What should become persistent memory versus session-only state?
9. Should the reliability layer first run in live shadow mode or enforced mode for specific pages?
10. What acceptance criteria should define “real stock-selection engine v1”?

## Files Inspected

State/docs:

- `docs/ai_dev_state/PROJECT_STATE.md`
- `docs/ai_dev_state/CURRENT_TASK.md`
- `docs/ai_dev_state/PHASE_2_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_3_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_3R_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_4M_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_5_CLOSEOUT.md`
- `README.md`

Core app/UI:

- `app.py`
- `ui_utils.py`
- `pages/2_Sector.py`
- `pages/3_Scanner.py`
- `pages/4_Equity.py`
- `pages/7_Investment_Cockpit.py`
- `pages/8_Macro_Dashboard.py`
- `pages/9_Trading_Desk.py`

Core runtime modules:

- `lib/data_fetcher.py`
- `lib/cache_manager.py`
- `lib/valuation.py`
- `lib/equity_valuation.py`
- `lib/valuation_anchor.py`
- `lib/technical.py`
- `lib/rotation.py`
- `lib/theme_baskets.py`
- `lib/candidate_generator.py`
- `lib/signal_engine.py`
- `lib/macro_data.py`
- `lib/macro_regime.py`
- `lib/macro_state.py`
- `lib/holdings.py`
- `lib/thesis_monitor.py`
- `lib/order_advisor.py`
- `lib/llm_orchestrator.py`
- `lib/financial_tab.py`
- `lib/pv_tab.py`

Reliability modules:

- `lib/reliability/schemas.py`
- `lib/reliability/evidence_store.py`
- `lib/reliability/validators.py`
- `lib/reliability/adapters.py`
- `lib/reliability/agent_output.py`
- `lib/reliability/critic.py`
- `lib/reliability/orchestration.py`
- `lib/reliability/decision_packet.py`
- `lib/reliability/integration_boundary.py`
- broader `lib/reliability/` file inventory

Tests:

- `scripts/test_reliability*.py` inventory
- Compile-only check of key Phase 6 files listed above.
