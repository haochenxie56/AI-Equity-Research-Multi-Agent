# AI Investment Agent OS Architecture and Functionality Report

**Date**: 2026-06-12
**Audience**: Project owner and future strategy/roadmap review sessions
**Scope**: Repository audit only. No functional code changes were made.
**Disclaimer**: This report is for research and educational purposes only and does not constitute investment advice.

## 1. Executive Summary

The repository is now substantially more than the original five-step Claude-assisted
equity research workflow. It contains a live Streamlit decision-support application
with:

- deterministic macro-regime classification and market-internals monitoring;
- manually curated cross-GICS theme baskets and sector/theme rotation analytics;
- a capped multi-stock candidate universe and dual-track signal pipeline;
- independent short-, mid-, and long-horizon opportunity ranking;
- stock-level valuation, technical analysis, entry-zone logic, holdings tracking,
  thesis monitoring, and portfolio risk overlays;
- local snapshots, holdings persistence, valuation-anchor cache/history, and market-data
  cache; and
- a large standalone reliability package with typed evidence, constrained agent-output
  contracts, validators, staleness checks, critics, decision packets, review artifacts,
  memory schemas, and evaluation fixtures.

The main architectural fact is that the repository contains **two systems with selective
integration**:

1. The live product path in `app.py`, `pages/`, and the non-reliability `lib/` modules.
   This path uses deterministic Python, yfinance/FRED/Finnhub data, and selected direct
   Claude calls.
2. The `lib/reliability/` contract and audit stack. Much of this is deterministic and
   extensively tested, but most Phase 0-5 orchestration, debate, decision-packet, memory,
   and evidence-validation machinery is not the mandatory execution path for the live
   Streamlit research workflow.

Maturity is therefore mixed:

- **Strongest**: deterministic calculation modules, horizon-aware ranking, technical and
  entry logic, valuation-anchor discipline, fail-closed degradation, review-only safety,
  and contract-level test depth.
- **Weakest**: causal fundamental/narrative verification, robust catalyst and marginal
  buyer intelligence, full-market and dynamic theme-universe construction, institutional/
  ETF/options-flow data, portfolio valuation accuracy, post-entry monitoring automation,
  and live integration of the evidence-first reliability stack.

Support for the target four-layer framework is:

| Layer | Rating | Verdict |
|---|---|---|
| 1. Fundamental / Narrative Validity | **Partial** | Valuation and financial inputs are meaningful; narrative exposure and repricing logic remain lightweight and partly LLM-proxy based. |
| 2. Marginal Capital / Catalyst Logic | **Weak** | Some earnings, news, analyst revision, insider, macro, and rotation signals exist, but there is no complete marginal-buyer model. |
| 3. Price-Volume / Technical Confirmation | **Strong** | Multi-window relative strength, technical indicators, entry zones, market breadth, theme breadth, and fragility are integrated. |
| 4. Position Sizing / Risk Management | **Partial-to-Strong** | Horizon-aware entry/add logic, portfolio caps, loss budgets, and thesis-driven long logic exist; portfolio accounting and monitoring remain incomplete. |

The OS can now rank a practical but limited universe of stocks. It cannot yet credibly
claim comprehensive US-equity selection or consistently identify the next rotation based
on complete fundamental, flow, and catalyst evidence.

## 2. Current Repository / Project State

### Current state from repository artifacts

- `PROJECT_STATE.md` is updated through June 12, 2026 and records:
  - Phase 6A live macro data;
  - Phase 6B stock-selection signal layers;
  - Phase 6C Trading Desk and Cockpit rebuild;
  - Phase 7A opportunity ranking;
  - Phase 7B multi-window relative strength, two-ring rotation, and market internals;
  - Valuation Stop-the-Bleed;
  - Valuation Refactor v1;
  - Anchor Intelligence v2 through v2.5;
  - the latest earnings-calendar fetch-order and FRED liquidity changes.
- `CURRENT_TASK.md` describes the June 12 batch segment as closed.
- Git `main` is aligned with `origin/main` and was clean at the start of the audit.
- Latest commit inspected: `372dd25 feat(data-layer): earnings-calendar fetch hoist + FRED liquidity fetchers`.

### Accepted / implemented status

The best current interpretation is:

- Phases 0-4M: accepted contract/reliability foundations.
- Phase 5A-5R: accepted product/view-model work; Phase 5S has stale “awaiting review”
  language in its closeout document.
- Phase 6A: explicitly recorded as accepted.
- Phase 6B, 6C, 7A, and 7B: executable implementations exist and are used by the current
  app, even though older sections of `PROJECT_STATE.md` still contain historical
  “awaiting review” or “current task” labels.
- Valuation Refactor and Anchor Intelligence v2.1-v2.5: explicitly closed/approved.
- June 10/12 UI and data-layer batches: closed and committed.

### State-file consistency

The state files are useful but not internally clean:

- `PHASE_5_CLOSEOUT.md` still says Phase 5S awaits review and Phase 6 has not started,
  which is contradicted by later code, docs, commits, and the top of `PROJECT_STATE.md`.
- `PROJECT_STATE.md` preserves many historical status blocks verbatim. Its top section is
  current, but its older roadmap tables and “In Progress” section contain stale statuses.
- `CURRENT_TASK.md` is more current than the Phase 5 closeout and correctly records the
  latest batch as closed.
- There is no concise Phase 6 or Phase 7 closeout state file equivalent to the Phase 2,
  Phase 3, Phase 3R, Phase 4M, and Phase 5 closeouts.

The mismatch is primarily documentation drift, not absence of executable code.

## 3. Architecture Overview

| Component | Purpose and important files | Inputs / outputs | Integration status |
|---|---|---|---|
| Streamlit app/UI | `app.py`, `pages/1_Overview.py` through `pages/9_Trading_Desk.py`, `ui_utils.py` | User actions, session state, rendered cards/tables/charts | Live and integrated |
| Original workflow orchestration | `pages/1_Overview.py`, `lib/llm_orchestrator.py`, `lib/workflow_state.py` | Sector/scan/equity/financial/technical data; Claude JSON | Live, direct, separate from mandatory reliability validation |
| Market data | `lib/data_fetcher.py`, `lib/cache_manager.py` | yfinance; Polygon fallback; local Parquet | Live and integrated |
| Macro layer | `lib/macro_data.py`, `lib/macro_regime.py`, `pages/8_Macro_Dashboard.py` | yfinance, FRED, Finnhub, fixtures | Live, deterministic classification |
| Sector / rotation | `lib/rotation.py`, `lib/sectors.py`, `pages/2_Sector.py` | ETF/stock OHLCV, macro proxies | Live and integrated |
| Theme intelligence | `lib/theme_baskets.py` | Static baskets plus yfinance returns | Live computation over manually curated taxonomy |
| Candidate generation | `lib/candidate_generator.py`, `lib/signal_engine.py` | S&P top-100 anchor, selected themes/manual/session tickers, fundamentals/news/LLM | Live and integrated in Scanner/Cockpit |
| Opportunity ranking | `lib/opportunity_ranker.py` | Candidate signals, themes, RS, macro, events, cached anchors | Live and integrated; deterministic |
| Technical analysis | `lib/technical.py`, `lib/relative_strength.py`, `lib/pv_tab.py` | OHLCV | Live and integrated |
| Valuation | `lib/valuation.py`, `lib/equity_valuation.py`, `lib/valuation_router.py`, `lib/valuation_diagnosis.py` | Financial statements, price, analyst targets, peers | Live; deterministic numeric producer |
| Entry/risk engine | `lib/order_advisor.py` | Technical snapshot, horizon, thesis, valuation, holdings/settings | Live and integrated; optional LLM narrative after numbers |
| Holdings/thesis | `lib/holdings.py`, `lib/thesis_monitor.py`, `pages/9_Trading_Desk.py` | Local holdings, news/EPS/technical/macro signals | Live, local persistence, review-only |
| Market internals | `lib/market_internals.py` | Benchmark/universe frames, earnings calendar, sector/theme signals | Live and integrated; tighten-only |
| Persistence/audit | `data/holdings.json`, `data/snapshots/`, `data/anchor_cache.json`, `data/anchor_archive/`, `research/.workflow_state.json` | JSON/JSONL/Parquet | Multiple local stores; no unified database |
| Reliability foundation | `lib/reliability/schemas.py`, `evidence_store.py`, `validators.py`, `staleness.py`, `critic.py` | ToolResult, AgentResult, EvidenceRef | Executable library, mostly not live-path mandatory |
| Reliability synthesis | `orchestration.py`, `horizon_synthesis.py`, `debate.py`, `decision_packet.py`, `human_review.py`, `review_loop.py` | Typed reliability artifacts | Offline/deterministic skeletons |
| Reliability memory/product contracts | Phase 4M and Phase 5 modules under `lib/reliability/` | Caller/fixture supplied records | Mostly in-memory, fixture, or view-model contracts |

### Deterministic versus LLM-facing

Deterministic modules compute macro classifications, theme/sector returns, technicals,
valuation bands, candidate scores, horizon grades, statuses, entry zones, stops, sizing,
fragility, and validation outcomes.

LLM-facing modules include:

- `lib/llm_orchestrator.py` for the original research workflow and valuation debate;
- `signal_engine.llm_narrative_match()` for top candidate narrative/catalyst labeling;
- `order_advisor.generate_order_narrative()` for prose over computed levels;
- `thesis_monitor` for a bounded news/thesis interpretation.

The live LLM outputs are generally fail-closed, but they do not all pass through
`AgentResult` plus `EvidenceStore` validation.

## 4. End-to-End Workflow

### Primary Cockpit workflow

1. The user refreshes `pages/7_Investment_Cockpit.py`.
2. `fetch_all_macro()` obtains grouped macro data and `classify_regime()` produces
   deterministic regime, confidence, horizon bias, and posture.
3. Theme baskets are computed using yfinance price histories and QQQ-relative excess
   returns.
4. `generate_candidates()` builds a universe from:
   - hardcoded S&P 500 top-100 names;
   - selected theme constituents;
   - Sector-to-Scanner session handoff;
   - manual tickers; and
   - prior workflow subsector constituents.
5. Candidate generation runs:
   - Layer 1 hard filters;
   - Layer 2 top-N LLM narrative/catalyst matching;
   - Layer 3 deterministic fundamental scoring;
   - independent Track B insider/news/analyst signals;
   - short/mid/long signal scoring.
6. Cached relative-strength data is computed against SPY/QQQ using horizon-specific
   windows.
7. `compute_market_fragility()` calculates distribution, breadth, earnings reaction,
   weak-bounce, theme-volume, and offense/defense components with hysteresis.
8. `rank_opportunities()` scores every candidate for three horizons and enriches the
   top N with entry-engine statuses, earnings timing, risk blockers, cached valuation
   anchors, and next triggers.
9. `write_daily_snapshot()` writes opportunity and selected macro/fragility/anchor
   metadata to JSONL.
10. The UI displays market context, themes, ranked opportunities, research actions, and
    Trading Desk handoffs.

### Original five-step workflow

`pages/1_Overview.py` still runs sector -> scanner -> equity -> financial -> price/volume
sequentially. Each step combines deterministic data with direct Claude JSON. Results are
saved to Streamlit state and `research/.workflow_state.json`, then synthesized.

### Trading Desk workflow

1. User manually records positions or imports a candidate handoff.
2. Holdings and portfolio settings are stored in `data/holdings.json`.
3. `thesis_monitor.py` evaluates news, EPS revisions, technical breakdown, macro context,
   fragility annotation, and anchor migration.
4. `order_advisor.py` computes horizon/scenario-specific entry, add, trim, stop,
   valuation, and risk-overlay fields.
5. Optional Claude prose explains already-computed numbers.
6. All actions remain manual and `approved_for_execution` remains false.

### Integration truth

- The quantitative Cockpit/Trading Desk path is genuinely integrated.
- The original Claude workflow is genuinely integrated.
- The general-purpose reliability orchestration and decision-packet stack is mostly
  implemented but isolated from those live flows.
- Several Phase 5 “agent debate,” research-pack, and memory surfaces are contract or
  fixture-driven rather than real multi-agent runtime execution.

## 5. Current Feature Inventory

| Area | Feature | Implemented? | Integrated? | Relevant files | Notes |
|---|---|---:|---:|---|---|
| Market regime | Deterministic risk-on/off/transition/degraded | Yes | Yes | `macro_data.py`, `macro_regime.py` | Coverage guard; free-data fixtures |
| Sector rotation | Multi-window GICS rotation and offense/defense | Yes | Yes | `rotation.py`, page 2 | ETF/proxy based |
| Theme rotation | Cross-GICS baskets, excess return, stage, breadth | Yes | Yes | `theme_baskets.py` | Static curated taxonomy |
| Universe screening | Up to 150 names | Yes | Yes | `candidate_generator.py` | Not full NYSE/NASDAQ |
| Stock ranking | Three-horizon opportunity ranking | Yes | Yes | `signal_engine.py`, `opportunity_ranker.py` | Deterministic weights |
| Fundamental research | Financials, margins, EPS revisions, quality | Yes | Partial | `data_fetcher.py`, `signal_engine.py`, pages 4/5 | Limited causal thesis verification |
| Valuation | DCF, relative, analyst anchors, method routing | Yes | Yes | `equity_valuation.py`, `valuation_router.py` | One of the strongest areas |
| Analyst consensus | Median/mean/high/low/count/dispersion | Yes | Yes | `equity_valuation.py` | Pool dispersion gates confidence |
| Technical analysis | SMA/EMA/RSI/MACD/ADX/Bollinger/ATR/OBV | Yes | Yes | `technical.py` | Strong stock-level coverage |
| Relative strength | SPY/QQQ multi-window excess | Yes | Yes | `relative_strength.py` | Date-aligned; vintage guards |
| Price-volume confirmation | Breakout/pullback/volume/support/resistance | Yes | Yes | `technical.py`, `order_advisor.py` | Accumulation is proxied, not institutional-flow measured |
| Catalysts | Earnings/news/LLM catalyst fields | Yes | Partial | `signal_engine.py`, `data_fetcher.py` | No normalized catalyst calendar/impact engine |
| Marginal buyer logic | “Who buys next and why now” | Weak | No coherent engine | Multiple | Scattered proxies only |
| Options/dealer flow | Schemas/calculators | Partial | No live chain/flow | `lib/reliability/options.py`, `option_expression.py` | No real options flow or dealer gamma |
| Short squeeze | Direct squeeze model | No | No | - | Insider/news Track B is not a squeeze engine |
| ETF flows | Holdings/flow analytics | No | No | - | ETF price proxies only |
| Social/KOL | Finnhub market sentiment fallback | Partial | Macro only | `macro_data.py` | Premium endpoint may be unavailable; no stock-ranking KOL model |
| Portfolio allocation | Caps, risk budgets, holdings, cash | Yes | Partial | `holdings.py`, `order_advisor.py` | Other positions valued at cost basis proxy |
| Horizon-aware decisions | Short/mid/long scoring and entry logic | Yes | Yes | signal/ranker/order modules | Strong |
| Monitoring loop | Thesis checks and snapshots | Partial | Partial | `thesis_monitor.py`, snapshots | No scheduler/alerts or persistent event loop |
| Evidence validation | Typed ToolResult/EvidenceRef validation | Yes | Mostly isolated | `lib/reliability/` | Not mandatory for live Claude output |
| Hallucination prevention | Numeric binding, staleness, critic, evals | Yes | Partial | reliability package | Strong contracts; semantic relevance gap |
| Final decision synthesis | DecisionPacket/review schemas | Yes | Mostly offline | `decision_packet.py`, `review_loop.py` | Live UI uses separate ranker/status logic |
| UI/reporting | Nine Streamlit pages, Markdown/report helpers | Yes | Yes | `pages/`, `report_writer.py` | Product has several overlapping entry points |
| Persistence | Workflow JSON, holdings JSON, snapshots, anchors, Parquet | Yes | Yes | multiple | Fragmented local persistence |

## 6. Reliability / Evidence Architecture

### Core objects

- `DataSnapshot`: source data and fetch metadata.
- `ToolResult`: deterministic evidence unit with `evidence_id`, `run_id`, inputs,
  outputs, and snapshots.
- `EvidenceRef`: links a claim to an evidence ID and optionally a tool, metric,
  field path, or snapshot.
- `AgentResult`: constrained findings, assumptions, risks, and confidence.
- `ValidationReport`: pass/fail plus structured issues.
- Higher-order artifacts include validation aggregates, staleness reports, critic
  results, horizon synthesis, debate reports, decision packets, human reviews, and
  reliability-run reports.

### Evidence IDs and persistence

Adapters create deterministic/content-sensitive evidence IDs. `EvidenceStore` maintains
an in-memory map and append-only `tool_results.jsonl`, rejects duplicate IDs, and writes
an evidence manifest.

### Numeric claim binding

`validate_agent_result()` detects numeric/financial terms using regex. Numeric findings:

- fail with an error when evidence is absent;
- fail when the evidence ID is unknown;
- warn when no valid tool/metric/field-path binding exists; and
- warn on invalid binding metadata.

Important limitation: `ValidationReport.passed` becomes false only for **errors**.
`WEAK_NUMERIC_EVIDENCE_BINDING` is a warning. A numeric claim can therefore pass the
base validator while citing a valid but semantically irrelevant field path.

### Relevance and value verification limits

The validator checks that:

- an evidence ID exists;
- a tool name matches; or
- a metric/field path resolves.

It does **not** generally prove that:

- the claim’s number equals the cited evidence value;
- the excerpt is verbatim;
- the cited field is relevant to the claim’s subject;
- the evidence supports the direction or causal language of the finding; or
- one ticker’s evidence was not used to support another ticker’s claim, beyond whatever
  the caller encodes and checks elsewhere.

Thus irrelevant evidence can still pass structural validation.

### Parsing and confidence

`parse_agent_result_json()` uses strict Pydantic schemas with `extra="forbid"`.
`AgentConfidence` contains categorical level, rationale, and score. The deterministic
critic flags high confidence when validation or staleness is poor.

### Critic and evaluation coverage

The mock critic catches structural issues such as unsupported claims, weak evidence,
staleness, missing assumptions/risks, conflicting evidence, overconfidence, validation
failures, and safety concerns. The 12-case evaluation harness covers these failure modes.

Audit execution on June 12, 2026:

- 12 cases passed;
- 0 failed/errors;
- 100% expected detection;
- 0 expected false positives.

### Reliability strength

The anti-hallucination architecture is **strong as a contract and test framework**, but
only **partial as a product control** because:

- direct live Claude functions return ad hoc dictionaries rather than mandatory
  `AgentResult`;
- live recommendations are not universally registered in an EvidenceStore;
- semantic entailment and exact numeric-value binding are not enforced; and
- many advanced Phase 3-5 artifacts remain offline/fixture contracts.

## 7. Fit Against the Four-Layer Trading Framework

### Layer 1 - Fundamental / Narrative Validity: Partial

Supported:

- statements, cash flow, balances, earnings estimates, margins, quality, valuation;
- EPS revision direction and margin trend;
- company-type-specific valuation methods;
- analyst pool and peer-quality checks;
- LLM narrative stage, theme tags, catalyst summary, equity research, moat/competition.

Missing or weak:

- no structured revenue-exposure mapping by product/customer/theme;
- no core/second-order/peripheral beneficiary classifier in the live stock engine;
- limited backlog, guidance, capex, customer-demand, policy, and filing-derived evidence;
- no systematic “bull case already priced” decomposition beyond valuation percentile,
  catalyst recency, and an LLM `already_priced_in` flag;
- no SEC filing or transcript ingestion in the main data layer.

### Layer 2 - Marginal Capital / Catalyst Logic: Weak

Supported:

- earnings dates and reactions;
- news headlines/sentiment;
- analyst recommendation revision;
- insider transactions;
- macro regime and sector/theme rotation;
- recent catalyst label from the top-N narrative LLM call.

Missing or weak:

- no explicit marginal-buyer hypothesis object;
- no buyer-type probabilities or evidence chain;
- no institutional holdings-change or 13F model;
- no ETF creation/redemption or constituent-flow model;
- no real options-flow/dealer-gamma model;
- no robust short-interest/borrow/squeeze model;
- no stock-level social/KOL acceleration model;
- no peer-earnings read-through graph;
- no normalized catalyst surprise/impact scoring and decay model.

### Layer 3 - Price-Volume / Technical Confirmation: Strong

Supported:

- multi-window relative strength versus SPY/QQQ;
- sector/theme excess returns and theme breadth;
- breakout/pullback/entry-zone state;
- volume ratio/trend, moving averages, ATR, RSI, MACD, ADX, Bollinger, OBV;
- support/resistance and candlestick patterns;
- market breadth, distribution days, weak bounces, and good-news-sold behavior;
- multi-stock theme confirmation and leading/rotating stages.

Limitations:

- VWAP is not a prominent first-class signal;
- institutional accumulation/distribution is inferred from price/volume, not measured;
- peer-relative ranking is stronger at theme level than within a fully normalized
  industry peer universe.

### Layer 4 - Position Sizing / Risk Management: Partial-to-Strong

Supported:

- explicit short/mid/long horizons;
- initiate/add/manage scenarios;
- technical stops for short/mid and thesis-driven long logic;
- persisted settings:
  - `max_position_pct = 0.15`;
  - `short_max_loss_pct = 0.02`;
  - `mid_max_loss_pct = 0.05`;
  - `long_stop = "thesis_break"`;
- position cap and risk-to-stop sizing for adds;
- long add requires intact thesis;
- valuation >= 70th percentile blocks entry;
- add/trim/exit action vocabulary;
- thesis monitor, anchor migration, snapshots, and review triggers.

Gaps:

- the long overlay does not exactly implement a single explicit rule object matching all
  three proposed conditions; logic is distributed across gates;
- non-current holdings are valued at cost basis in portfolio totals, not current market
  value;
- no covariance, factor, sector, theme, liquidity, gap-risk, or correlation budget;
- no tax-lot, wash-sale, margin, or options exposure;
- no scheduler, alerts, or automated post-entry data refresh;
- position recommendations remain approximate and manual.

## 8. Stock Selection / Screening Capability Assessment

### What it can do

- Screen a multi-stock universe, not merely one ticker.
- Build a universe from a reproducible large-cap anchor plus themes/manual/session inputs.
- Rank candidates separately for short, mid, and long horizons.
- Rank stocks in manually curated AI and adjacent theme baskets.
- Detect theme rotation stages and breadth confirmation.
- Surface potential early-cycle names through EPS inflection, valuation, and alternative
  signals rather than momentum alone.
- Score narrative/catalyst, technical, valuation, quality, theme, relative strength,
  liquidity, and entry status in different parts of the pipeline.
- Separate several setup forms such as momentum breakout, pullback, research-required,
  and alternative-signal candidates.

### What it cannot yet do credibly

- It does not screen all NYSE/NASDAQ listings; the base is roughly the top 100 S&P names
  plus curated additions, capped at 150.
- It does not maintain a complete security master or survivorship-aware universe.
- AI value-chain classification is a static basket taxonomy, not a company revenue/
  product exposure graph.
- “Next rotation” is based mainly on price excess, short/medium divergence, and breadth;
  it lacks capex/order/backlog/estimate-flow propagation across supply-chain layers.
- It does not fully score institutional support, ETF flows, options positioning, short
  squeeze, social attention, or event-specific risk/reward.
- It does not cleanly classify every candidate as compounder, theme rotation trade,
  event trade, or speculative squeeze using a first-class taxonomy.
- The LLM narrative call is cost-bounded to top candidates and safe-defaults the rest,
  which can bias narrative coverage toward names already favored by deterministic
  pre-ranking.

### Missing practical selection-engine modules

1. Dynamic US security master and liquidity/eligibility engine.
2. Versioned theme/value-chain exposure graph.
3. Deterministic catalyst event store with impact/decay scoring.
4. Marginal-buyer hypothesis contract.
5. Cross-sectional peer/theme ranking with standardized features.
6. Event/swing/investment horizon classifier.
7. Institutional, ETF, short-interest, and options-positioning data adapters.
8. Portfolio-aware opportunity selection and concentration optimizer.
9. Historical evaluation/backtest of ranking quality and calibration.

## 9. Data Source Assessment

| Source | Current use | Reliability / limitations |
|---|---|---|
| yfinance | OHLCV, company info, financials, analyst targets, recommendations, news, ETF proxies | Broad and free, but unofficial, field availability varies, revisions and metadata can be stale |
| Finnhub | Earnings, recommendations, company news, insider data, market news/social attempt | Free-tier rate limits; social endpoint may require premium; current code has explicit 429/degrade handling |
| FRED | Rates, inflation, credit, dollar, releases, SOFR/RRP/TGA/reserves | Strong macro source; requires key; release-vintage/revision handling is limited |
| Polygon | OHLCV fallback in `data_fetcher.py` | Configured but not the dominant application path |
| Claude API | Sector/equity/workflow narrative, candidate narrative/catalyst, order prose, thesis news interpretation | Useful for synthesis; direct outputs are not universally evidence-contract validated |
| Local files | Parquet cache, workflow JSON, holdings JSON, snapshots JSONL, anchor cache/history | Auditable locally, but fragmented and not transactionally unified |
| SEC filings | Not materially integrated | Major gap for revenue exposure, filings, guidance, backlog, risk factors |
| Earnings transcripts | Not integrated | Major gap for narrative/catalyst verification |
| Options chains/flow | Schemas/calculators only | No live chain, open-interest change, IV surface, dealer positioning, or unusual flow |
| Short interest/borrow | Not integrated | Prevents credible squeeze scoring |
| ETF holdings/flows | Not integrated | ETF prices are used, not capital flows |
| Institutional holdings | Not integrated | No 13F/13D/13G or ownership-change signal |
| Social/KOL | Limited market-level Finnhub attempt | No robust stock-level attention acceleration |
| User watchlists/holdings | Session state and local holdings | Useful but manual; no brokerage reconciliation |

The largest data gap is not another price feed. It is structured fundamental/event/flow
data needed to verify theme exposure and identify the next marginal buyer.

## 10. Test Coverage / Quality Assessment

Repository counts observed:

- 79 `scripts/test_reliability_*.py` suites;
- 53 Python modules in `lib/reliability/`;
- 9 Streamlit pages;
- existing snapshot and anchor-archive artifacts.

Test styles include:

- unit tests for formulas, schemas, validators, and deterministic builders;
- mutation/discrimination tests proving a changed invariant turns a test red;
- integration-style tests across ranking, entry, cache, and snapshot paths;
- Streamlit AppTest render/smoke tests;
- structural source guards for forbidden imports/network calls;
- fixture and negative-case evaluation tests;
- parity tests between UI and persisted snapshot fields.

Strengths:

- unusually deep contract coverage;
- strong regression protection for reliability and decision-layer invariants;
- explicit fail-closed and no-execution checks;
- access-path/cache-order tests;
- evaluation harness passed 12/12 during this audit.

Weaknesses:

- many tests validate contracts, fixtures, strings, and structural invariants rather
  than investment outcome quality;
- no credible historical walk-forward evaluation of stock ranking alpha, hit rate,
  drawdown, turnover, or calibration;
- static thresholds and weights are heavily tested for stability but not empirically
  justified;
- some state docs report a full-suite baseline with 13 pre-existing red suites;
- network/provider behavior is mostly mocked;
- semantic evidence relevance is not tested end to end for live Claude outputs.

## 11. Major Gaps and Design Risks

1. **Split-brain architecture**: live Claude outputs and the reliability stack are not one
   mandatory pipeline.
2. **Universe limitation**: a capped, manually anchored universe cannot support a claim
   of full NYSE/NASDAQ discovery.
3. **Static theme taxonomy**: baskets are useful but manually curated and exposure-blind.
4. **Weak marginal-buyer model**: catalysts and flows are scattered proxies.
5. **Fundamental causality gap**: limited SEC/transcript/backlog/customer/capex evidence.
6. **Data fallback ambiguity**: fixtures keep pages alive but may look decision-ready
   unless users inspect provenance.
7. **Portfolio valuation approximation**: other holdings use cost basis as a price proxy.
8. **No automated monitoring loop**: no scheduler, alerts, or persistent event-driven
   thesis review.
9. **No outcome evaluation**: ranking and risk rules lack walk-forward evidence.
10. **Evidence semantics gap**: valid IDs/paths do not guarantee claim entailment.
11. **Persistence fragmentation**: multiple JSON/JSONL/Parquet stores lack one run-level
    lineage transaction.
12. **State-file drift**: historical statuses remain mixed with current status, making
    roadmap interpretation difficult.
13. **UI overlap**: Overview, Scanner, Equity, Cockpit, and Trading Desk expose partially
    overlapping workflows and state handoffs.
14. **Provider/rate-limit fragility**: yfinance variability and Finnhub free-tier limits
    can materially degrade candidate/event coverage.
15. **Risk model incompleteness**: no factor/correlation/theme/sector exposure controls.

## 12. Recommendations for Future Roadmap

### Near-Term Architecture Fixes

1. Define one canonical `ResearchRun` envelope with run ID, as-of/vintage, inputs,
   ToolResults, agent outputs, validations, rankings, and UI references.
2. Adapt live deterministic modules into ToolResults and require live LLM calls to emit
   `AgentResult` or a successor contract.
3. Make validation/staleness/critic status visible and binding before a live conclusion
   becomes “actionable.”
4. Consolidate current phase status into one concise authoritative state file and archive
   historical status blocks.
5. Define provenance rules for live versus fixture values and visually prevent fixture
   data from appearing equivalent to live decision data.
6. Create a persistence interface over existing local stores before adding more formats.

### Feature Additions for Stock Selection

1. **Market Regime Agent v2**: add growth/inflation/liquidity/earnings-cycle dimensions,
   with deterministic regime facts and evidence-bound interpretation.
2. **Theme Universe Builder**: dynamic theme discovery plus reviewed taxonomy versions.
3. **AI Value Chain Taxonomy**: nodes for compute, memory, networking, power, cooling,
   cloud, data, software, edge, robotics, with company exposure weights and evidence.
4. **Sector Rotation Detector v2**: combine price rotation with earnings revisions,
   breadth, fund flows, and capex/order propagation.
5. **Relative Strength Ranker**: cross-sectional percentile ranks within market, sector,
   theme, and peer cohorts.
6. **Catalyst Engine**: normalized events, expected date, surprise direction, confidence,
   impacted horizons, decay, and peer read-through.
7. **Marginal Buyer Hypothesis Generator**: structured buyer type, trigger, timing,
   evidence, disconfirmers, and confidence.
8. **Watchlist Scoring Engine**: unified deterministic feature vector and transparent
   horizon-specific scoring.
9. **Horizon Classifier**: compounder, thematic swing, event trade, and speculative
   momentum/squeeze as explicit, non-overlapping primary intents.
10. **Portfolio Risk Overlay v2**: live marks, sector/theme/factor concentration,
    correlation, liquidity, event gap risk, and total risk budget.
11. **Monitoring Loop**: scheduled refresh, alert rules, thesis-state transitions, and
    “what changed since entry” records.

### Reliability Improvements

1. Validate exact numeric values against bound field paths, including units and
   tolerances.
2. Add ticker/subject/run/vintage consistency checks to EvidenceRef validation.
3. Validate excerpts and semantic relevance, using deterministic claim templates where
   possible and an evidence-entailment critic only as a secondary check.
4. Escalate weak numeric binding from warning to blocking for decision-relevant claims.
5. Require every recommendation, catalyst, and marginal-buyer claim to carry supporting
   and disconfirming evidence.
6. Add calibration records comparing confidence with subsequent outcomes.
7. Expand evals with irrelevant-but-valid evidence, wrong-value citations, cross-ticker
   citations, stale-but-same-ID evidence, and causal overclaim cases.

### Data Improvements

Priority order:

1. SEC company facts and filing text.
2. Earnings calendars, estimates, and transcript provider with reliable historical data.
3. Point-in-time universe/security master.
4. Institutional ownership and short-interest data.
5. ETF holdings and flow data.
6. Options chain/OI/IV and, if affordable, flow/dealer-positioning data.
7. Structured policy/government-contract sources.
8. Better analyst-estimate history and revision breadth.

Do not add expensive flow data before the point-in-time universe, fundamental exposure
model, and outcome-evaluation harness are in place.

### UI / Product Workflow Improvements

Organize the product as one guided funnel:

1. **Market**: regime, liquidity, fragility, and confidence.
2. **Themes**: ranked themes, stage, breadth, catalysts, and data quality.
3. **Value chain**: layers receiving or losing marginal capital.
4. **Candidates**: cross-sectional ranking with complete score decomposition.
5. **Research packet**: narrative validity, catalysts, technical confirmation,
   valuation, risks, and evidence.
6. **Trade plan**: horizon, entry, invalidation, size, add/trim/exit.
7. **Portfolio check**: concentration and risk budget.
8. **Monitoring**: thesis status, changed evidence, alerts, and review history.

The user should see one canonical recommendation state per ticker/horizon, with links to
supporting modules rather than multiple independent summaries.

## 13. Questions / Handoff Items for Strategy Review

1. What exact point-in-time universe should the first credible ranking engine cover?
2. How should the stock-selection score combine narrative fit, catalysts, RS, valuation,
   liquidity, analyst/institutional support, and risk/reward without double counting?
3. Which features must remain deterministic, and which judgments genuinely benefit from
   an LLM?
4. How should the AI value-chain taxonomy represent company exposure, confidence,
   evidence, and changing business mix?
5. What constitutes a core, second-order, and peripheral beneficiary?
6. How should marginal-buyer hypotheses be represented and falsified?
7. What data is mandatory before ETF-flow, options-flow, squeeze, or institutional
   scoring is credible?
8. How should the system distinguish investment, swing/theme rotation, event trade, and
   speculative momentum/squeeze?
9. Should one ticker support simultaneous but independent theses by horizon?
10. How should horizon-aware risk rules interact with portfolio-level sector/theme/factor
    concentration?
11. What historical evaluation design will avoid look-ahead and survivorship bias?
12. Which current thresholds/weights should be treated as policy versus calibration
    parameters?
13. Should weak evidence binding block “Actionable Now” even if deterministic price
    signals are strong?
14. What is the highest-ROI next module: point-in-time universe, exposure taxonomy,
    catalyst engine, or live reliability integration?
15. How should current local persistence evolve without creating unnecessary database
    complexity?

## Files Inspected

### State and roadmap

- `docs/ai_dev_state/PROJECT_STATE.md`
- `docs/ai_dev_state/CURRENT_TASK.md`
- `docs/ai_dev_state/PHASE_2_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_3_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_3R_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_4M_CLOSEOUT.md`
- `docs/ai_dev_state/PHASE_5_CLOSEOUT.md`
- `docs/ai_dev_state/ROADMAP_V4_ALIGNMENT.md`
- `README.md`

### Live application and decision modules

- `app.py`
- `pages/1_Overview.py`
- structural/function/import inspection across `pages/2_Sector.py`,
  `pages/3_Scanner.py`, `pages/4_Equity.py`, `pages/7_Investment_Cockpit.py`,
  `pages/8_Macro_Dashboard.py`, and `pages/9_Trading_Desk.py`
- `lib/data_fetcher.py`
- `lib/cache_manager.py`
- `lib/llm_orchestrator.py`
- `lib/workflow_state.py`
- `lib/valuation.py`
- `lib/technical.py`
- `lib/rotation.py`
- `lib/theme_baskets.py`
- `lib/macro_data.py`
- `lib/macro_regime.py`
- `lib/market_internals.py`
- `lib/relative_strength.py`
- `lib/signal_engine.py`
- `lib/candidate_generator.py`
- `lib/opportunity_ranker.py`
- `lib/equity_valuation.py`
- `lib/valuation_router.py`
- `lib/valuation_diagnosis.py`
- `lib/holdings.py`
- `lib/order_advisor.py`
- `lib/thesis_monitor.py`

### Reliability and evaluation

- `lib/reliability/schemas.py`
- `lib/reliability/evidence_store.py`
- `lib/reliability/validators.py`
- `lib/reliability/agent_output.py`
- `lib/reliability/prompt_contracts.py`
- `lib/reliability/critic.py`
- `lib/reliability/orchestration.py`
- `lib/reliability/decision_packet.py`
- function/class inventory across all `lib/reliability/*.py`
- `evals/cases/*.json`
- `evals/expected/*.json`
- `evals/run_evals.py`
- test-suite inventory under `scripts/`
- `requirements.txt`
- `.env.example`

## Audit Verification

- `git status --short --branch`: clean `main`, aligned with `origin/main` before report creation.
- `git log --oneline -n 10`: inspected.
- `python3 -B evals/run_evals.py`: 12/12 cases passed, 100% expected detection.
- No application, library, test, state, or configuration file was modified.
- The only audit-created file is this report.
