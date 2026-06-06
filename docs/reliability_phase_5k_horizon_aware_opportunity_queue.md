# Phase 5K — Horizon-aware Opportunity Queue ViewModel

**Status:** Implemented — awaiting Codex review.

**Module:** `lib/reliability/phase5_opportunity_queue.py`
**Test:** `scripts/test_reliability_phase_5k_opportunity_queue.py`
**Exports:** additive in `lib/reliability/__init__.py`

> Disclaimer: outputs are for research / educational purposes only and do not
> constitute investment advice.

---

## Purpose

Phase 5K converts the Phase 5J **Theme Intelligence / Market Heat** records
(`ThemeIntelligenceSnapshot` → `ThemeRecord` → `ThemeCandidateTicker`) into a
deterministic, **horizon-aware Opportunity Queue** view model that an
opportunity-first cockpit can render. It sorts theme candidate tickers into:

- short-term **trade** candidates,
- mid-term **position** candidates,
- long-term **investment** candidates,
- **watch / wait**,
- **research more**,
- **no trade / avoid**.

Phase 5K is a **view-model contract layer only**. It does **not** decide final
trades, does **not** produce order instructions, and does **not** bypass the
future research / debate / decision-packet phases. It is offline / mock-only,
deterministic, and schema / helper / view-model / fixture only.

---

## Relationship to Phase 5I (Product Logic Reconciliation)

Phase 5I established the cockpit as **opportunity-first**, **macro-theme-aware**,
and **horizon-aware**, and separated the *source research modules* (the original
five-step AI Research Workflow: Overview / Sector / Scanner / Equity / Financial
/ PriceVolume) from the *cockpit decision layer*. Phase 5K is the first concrete
view-model that expresses Phase 5I's opportunity-first / horizon-aware principle
as data:

- It is **opportunity-first** (candidates are organized by opportunity and
  horizon, not by a single ticker drill-down).
- It is **horizon-aware** (three horizon queues, not one ranked list).
- It preserves the principle that the original AI Research Workflow momentum
  candidates are *inputs* that still require macro / entry / crowding / evidence
  validation — they are never auto-promoted to a buy.

## Relationship to Phase 5J (Theme Intelligence / Market Heat Schema)

Phase 5J is the **upstream input layer**. It defines themes, subthemes,
industry-chain nodes, candidate tickers, heat / narrative / fundamental /
crowding signals, the `ThemeHeatScore` container, lifecycle stages, evidence
coverage, and warnings — but it explicitly **does not** compute entry quality,
does **not** produce a queue, and does **not** decide buy/sell. Phase 5K consumes
those records and produces the queue. The Phase 5J invariant that **heat is not a
buy signal** is carried through unchanged.

---

## Why the Opportunity Queue is horizon-aware

A single ranked "top ideas" list collapses three genuinely different questions
into one:

- *Is this a good trade right now?* (timing, momentum, entry, crowding)
- *Is this a good position to build over the next quarters?* (fundamental
  confirmation, lifecycle, evidence quality)
- *Is this a durable long-term investment?* (complete evidence, durable
  fundamentals, valuation discipline)

A name can be a great short-term trade and a poor long-term hold, or a wonderful
long-term compounder that is a terrible entry today. Forcing one rank hides this.
Phase 5K therefore evaluates **every candidate independently for all three
horizons** and lets the **same ticker appear in multiple horizons with different
decisions**.

### Short-term / mid-term / long-term queue semantics

| Horizon | Queue | What qualifies | Primary gates |
|---------|-------|----------------|---------------|
| `short_term` | `ShortTermTradeQueue` | momentum / heat with acceptable entry | entry quality, crowding |
| `mid_term` | `MidTermPositionQueue` | fundamental confirmation + lifecycle + evidence | evidence completeness, confirmation |
| `long_term` | `LongTermInvestmentQueue` | complete evidence + durable fundamentals | evidence completeness, valuation/crowding |

Momentum is sufficient *consideration* for the short-term queue but **not** for
the mid-/long-term queues, which require stronger evidence beyond momentum.

### Cross-cutting queues: Watch/Wait, Research More, No Trade/Avoid

Independently of horizon, a per-horizon evaluation can resolve to a cross-cutting
outcome that routes the candidate out of its horizon queue:

- **Watch / Wait** (`WatchWaitQueue`) — interesting but no actionable trigger
  yet (`watch_wait`).
- **Research More** (`ResearchMoreQueue`) — insufficient or partial evidence
  (`research_more`, `insufficient_evidence`, `thesis_unconfirmed`,
  `thesis_insufficient`).
- **No Trade / Avoid** (`NoTradeAvoidQueue`) — actively avoid
  (`avoid_too_crowded`, `no_trade`).

### Same ticker across multiple horizons

`build_horizon_candidate_views(candidate, theme)` returns three
`HorizonCandidateView`s (one per horizon). `build_cross_horizon_candidate_comparison`
groups them per `(theme_id, ticker)` into a `CrossHorizonCandidateComparison`
with `decisions_by_horizon` (ordered `short → mid → long`) and a
`has_divergent_decisions` flag. Example from the default fixture:

- **NVDA** → short `wait_for_pullback`, mid `accumulate_on_pullback`, long
  `quality_but_expensive` (hot + crowded leader: divergent across horizons).
- **MU / VRT** → short `wait_for_pullback`, mid/long `research_more`
  (momentum names with only partial evidence).
- **FIXSPEC** → short `research_more`, mid/long `insufficient_evidence`
  (speculative, no evidence).

---

## Decision labels by horizon

**Short-term:** `trade_now`, `wait_for_pullback`, `breakout_watch`,
`event_trade_watch`, `too_extended`, `no_trade`.

**Mid-term:** `position_candidate`, `accumulate_on_pullback`, `research_more`,
`wait_for_earnings_confirmation`, `thesis_improving`, `thesis_unconfirmed`,
`no_trade`.

**Long-term:** `investment_candidate`, `watch_for_valuation`, `compounder_watch`,
`quality_but_expensive`, `thesis_durable`, `thesis_insufficient`, `no_trade`.

**Cross-cutting:** `watch_wait`, `research_more`, `avoid_too_crowded`,
`insufficient_evidence`, `no_trade`.

`OpportunityDecisionLabel` is the union of all distinct labels. Each label maps
to a descriptive `OpportunityNextAction` (e.g. `wait_for_pullback`,
`monitor_valuation`, `research_more`, `add_to_watchlist`, `reduce_or_avoid`) —
**none of which are order instructions.**

---

## Scores and badges

### HorizonFitScore

A deterministic heuristic placeholder (0..1, with a `poor/fair/good/strong/unknown`
band) of how well a candidate fits a given horizon:

- **short-term fit** favors heat / momentum + leadership role,
- **mid-term fit** favors fundamental confirmation + evidence + constructive
  lifecycle,
- **long-term fit** favors complete evidence + durable confirmation, penalized by
  crowding / late-cycle.

### EntryQualityScore

A deterministic heuristic placeholder of **entry timing / structure**, kept
**separate from theme heat**. It is crowding-dominant (chasing risk), slightly
worsened by a hotter heat band (more extended) and by thin evidence.
`EntryQualityScore.is_heat_score` is hard-coded `False` to make the separation
assertable. This is the Phase 5K realization of the Phase 5J
`EntryQualityScorePlaceholder`.

### ThemeHeatScore usage / ThemeHeatBadge

`ThemeHeatBadge` is a compact projection of the Phase 5J `ThemeHeatScore` (band
`cool/warm/hot/red_hot/unknown` + value + status). Heat **contributes to**
`opportunity_score` but never determines a decision alone.
`ThemeHeatBadge.is_buy_signal` is hard-coded `False`.

### CrowdingRiskBadge

Projects the Phase 5J crowding context (`low … extreme / unknown`). Crowding can
**downgrade** a decision: `elevated` crowding turns a would-be `trade_now` into
`wait_for_pullback`; `high` + red-hot heat becomes `too_extended`; `extreme`
becomes `avoid_too_crowded`.

### EvidenceCoverageBadge

Projects evidence completeness (`complete/partial/none/unknown`) and whether the
theme carries fundamental confirmation. Missing evidence reduces coverage and
pushes decisions toward `research_more` / `insufficient_evidence`.

### Why heat score is not a buy signal

A theme can be very hot and a very poor place to enter (crowded,
valuation-stretched, late-lifecycle). High heat + poor entry quality therefore
becomes `wait_for_pullback` / `too_extended` / `watch_wait` / `research_more` —
**never** an automatic `trade_now`. The only path to `trade_now` requires
momentum **and** a good/strong entry-quality band **and** non-elevated crowding
**and** evidence; the validation summary re-checks this invariant
(`no_unsafe_trade_now`).

### Why this is not a final trade recommendation

Phase 5K is a view-model contract. Final trade / allocation / option planning
happens **later**, after the Auto Research Pack (Phase 5L) + Agent Debate
(Phase 5M) + Decision Packet. No Phase 5K output is an order, an order ticket, a
broker payload, or an execution instruction. `approved_for_execution` never
appears and is never positively authorized.

---

## Fixture examples

Deterministic fixture builders (Phase 5J fixtures as input):

- `build_default_opportunity_queue_view()` /
  `build_opportunity_queue_from_default_theme_snapshot()` — from the Phase 5J
  default snapshot (AI + Space + degraded embodied-AI). Demonstrates:
  - same ticker across horizons with different decisions (NVDA),
  - high-heat but crowded leader becoming `wait_for_pullback` (not `trade_now`),
  - momentum candidates entering the short-term queue,
  - partial-evidence momentum names becoming `research_more` mid/long,
  - long-term quality-but-expensive (NVDA long `quality_but_expensive`).
- `build_degraded_opportunity_queue_view()` — only the degraded / emerging
  embodied-AI theme: partial / no evidence → `research_more` /
  `insufficient_evidence` with warnings; no fabricated actionable candidates.
- `build_empty_opportunity_queue_view()` — empty theme universe → safe empty
  queues.

Synthetic edge cases (exercised by the test via the per-horizon builders):
`high` crowding + red-hot heat → `too_extended`; `extreme` crowding →
`avoid_too_crowded`; disconfirming fundamentals → `no_trade`; unknown heat +
weak momentum + partial evidence → `watch_wait`.

---

## Safe / degraded states

- Empty `ThemeIntelligenceSnapshot` → safe empty queues
  (`validation_summary.is_safe_empty == True`), no fabricated candidates.
- Missing theme candidate data → warnings, not fabricated candidates.
- Partial / unknown scores remain partial / unknown; decisions degrade toward
  `research_more` / `watch_wait` / `insufficient_evidence`.
- No candidate carries `approved_for_execution=True`.
- No buy/sell field, no order field, no broker/execution semantics.

---

## Non-goals

- No final buy/sell recommendation.
- No executable trading instruction / order ticket / broker payload.
- No Auto Research Pack orchestration (Phase 5L), Agent Debate (Phase 5M),
  Decision Packet, Macro Dashboard, UI redesign, sidebar cleanup, or read-only
  shadow integration.
- No live data, LLM, or external API calls.
- No DB / vector store / production persistence.

---

## Guardrails

- Offline / mock-only, deterministic; schema / helper / view-model / fixture
  only.
- Every model sets `extra="forbid"`; no `approved_for_execution` or order-ticket
  field can be smuggled in via construction.
- `ThemeHeatBadge.is_buy_signal` and `EntryQualityScore.is_heat_score` are
  hard-coded `False`.
- Does not import or modify `app.py`, `pages/*`, `ui_utils.py`, Streamlit,
  `lib/workflow_state.py`, `lib/llm_orchestrator.py`, `.claude/agents/*`, or any
  live data-fetch / broker / order module.
- Does not read `research/.workflow_state.json`.
- Phase 4A is not wired in.

---

## Acceptance criteria

1. Default opportunity queue builds deterministically from the Phase 5J default
   theme snapshot, with a populated validation summary.
2. Short / mid / long horizon queues plus the three cross-cutting queues exist
   and are deterministic.
3. The same ticker can appear in multiple horizons with different decision
   labels (cross-horizon comparison demonstrates divergence).
4. High theme heat does not automatically produce `trade_now`; any `trade_now`
   passes the entry-quality + crowding gate (`no_unsafe_trade_now`).
5. High crowding downgrades to `wait_for_pullback` / `too_extended` /
   `avoid_too_crowded`.
6. Momentum candidates may enter the short-term queue.
7. Mid / long-term labels require stronger evidence beyond momentum.
8. Partial / missing evidence produces `research_more` / `insufficient_evidence`
   / `watch_wait`.
9. Empty theme snapshot returns safe empty queues; degraded fixture produces
   warnings.
10. Candidate source refs / theme IDs / subtheme IDs / chain node IDs are
    preserved.
11. No `approved_for_execution=True` is positively authorized; no buy/sell/order
    fields are introduced; serialization is deterministic.
12. The test suite `scripts/test_reliability_phase_5k_opportunity_queue.py`
    passes; the Phase 5J test still passes.

---

## Future Phase 5L dependency

The next phase, **Phase 5L — Auto Research Pack Orchestration Boundary** (a
future, not-yet-started phase), will consume the Phase 5K opportunity queue to
decide *which candidates warrant a deeper, orchestrated research pack* before any
Agent Debate / Decision Packet stage. Phase 5K deliberately stops at the
view-model boundary so that gating remains explicit and auditable. **Phase 5L has
not started.**
