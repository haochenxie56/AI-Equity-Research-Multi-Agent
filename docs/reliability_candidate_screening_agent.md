# Phase 8B — CandidateScreeningAgent

**Status:** COMPLETE — Codex arc APPROVE WITH FIXES (6 discriminating test adds) → APPROVED.
**Merged:** `main` via `--no-ff` @ `PENDING-MERGE` (feature commit `PENDING-FEATURE`), 2026-07-01.
**Module:** `lib/agents/candidate_screening_agent.py`
**Enabler (prior, already merged):** `lib/candidate_eligibility.py` (merge `f78ef606f`).
**Tests:** `scripts/test_phase_8b_candidate_screening_agent.py` (**104 assertions**, §CSA-1..CSA-18), fully offline.

---

## 1. Strategy identity — v1 is ONE fixed strategy: MOMENTUM / RS-GAP

CandidateScreeningAgent is the **sixth production foundation agent** on the Phase 8A
framework (after MacroRegime / MoneyFlow / MarketStructure / SectorRotation /
ThemeIntelligence). **v1 implements exactly one strategy: momentum / relative-strength
gap.** The primary ranking key is the per-horizon RS composite gap **within a theme**.

Future strategies (leader play, high-beta elasticity) will be **separate agents**
(e.g. `LeaderScreeningAgent`), never parameters of this one. There is deliberately
**no pluggable strategy interface** in v1 — the momentum strategy is hard-wired, and
the roster will list the future strategy agents alongside this one.

---

## 2. What it IS / IS NOT

**IS** a PER-THEME **relative** screener. For ONE active theme it: takes the theme's
candidates → runs each through the deterministic eligibility gate → builds a
deterministic comparison table over the **eligible** set → computes a deterministic
frontrunner per horizon → decides `no_clear_winner` **in code** → asks the LLM ONLY to
explain which differences are decisive and translate trade-offs into horizon fit +
invalidation conditions. It answers *"which one or two tickers are worth **advancing**
to the next trade-construction step."*

**IS NOT** a cross-theme ranker (PM's job), an entry-timing engine (TechnicalEntry), a
ticker-level money-flow validator (a future Stage-2 MoneyFlow run on primary/secondary
only), or a deep-conviction fundamental agent (StockResearch). It does **not** pick the
market's best name; it picks a **theme's** best name. The judgment tone is *"LITE is the
strongest candidate to advance to short-term trade construction; final entry depends on
money-flow, technical entry, and portfolio-risk checks"* — never *"buy LITE now."*
Advisory only: `requires_human_confirmation` is always `True`; no execution field.

---

## 3. Two-phase structure — the eligibility gate is the enabler

CandidateScreeningAgent shipped in **two phases**:

1. **Enabler (already merged, `f78ef606f`):** `lib/candidate_eligibility.py` — the
   deterministic, LLM-free four-state gate (`eligible` / `conditional` / `ineligible`
   / `unknown`) per `(ticker, horizon)` over `OpportunityCard` + `CandidateSignal`.
   Six gates, two tiers (HARD `thesis`/`eps`/`valuation`/`event` + SOFT
   `liquidity`/`distribution`), horizon-asymmetric, with a numeric-firewall valuation
   provenance guard. See `docs/reliability_candidate_eligibility_gate.md`.
2. **Agent body (this phase):** the LLM agent that CONSUMES the gate — comparison
   table + frontrunner + `no_clear_winner` + slate skeleton + 3 ToolResults +
   constrained LLM synthesis + the per-theme Cockpit hook.

---

## 4. The deterministic comparison table — A/B dimension typing + tradability guard

For ONE theme's **eligible** candidates (`compute_eligibility(...).status == "eligible"`;
`conditional` → watch-only, `ineligible`/`unknown` → rejected), the code builds a frozen
`CandidateProfile` per ticker. Pure deterministic code — no LLM, no fabricated numbers.

**A-dimensions** (keep the cleaned gap so the LLM can judge magnitude from evidence;
every A-dim also carries the `quality_capped` flag):
1. `relative_strength` — the momentum strategy's PRIMARY key. Per-horizon RS composite
   (`card.rs["rs_short"]` / `["rs_mid"]`, fallback `rs_composite`); raw per-window excess
   (`ret_*_vs_spy/qqq`) is carried into evidence only, never LLM prose.
2. `valuation_elasticity` — `CandidateSignal.valuation_percentile`, **provenance-gated**
   via the gate's own `_valuation_missing` (a defaulted 0.5 is `unknown`, never imputed).
3. `short_crowding` — **UNAVAILABLE** (see §6): no backing field, excluded from the key.

**B-dimensions** (code assigns a category; the LLM sees only the label):
4. `theme_role` — `theme_transmission.get_ticker_role(theme, ticker)`
   (leader / second_derivative_beneficiary / supplier / platform / laggard / unknown).
5. `volume_confirmation` — confirmed / unconfirmed / divergent, from rs `vol_ratio` +
   `above_sma20/50` against `_VOL_CONFIRM_RATIO`.
6. `options_structure` — **UNAVAILABLE** (see §6): Stage-2 MoneyFlow's lane.
7. `catalyst_proximity` — imminent / near / far / unknown, bucketed from
   `days_to_earnings` reusing the gate's `_EARNINGS_IMMINENT_DAYS` / `_EARNINGS_WINDOW_DAYS`.
8. `tradability` — sufficient / marginal (below).

**Tradability (cross-cutting credibility correction — the penny-stock guard).** Per
ticker: `market_cap_tier` (`ample` ≥ `_MCAP_AMPLE`, else `marginal`, else `unknown` —
market_cap is usually unreachable, see §6/§P2), `liquidity_tier` (FUNNEL/BOTH → `ample`,
ALT_SIGNAL → `marginal`, missing → `unknown` — the reachable penny guard), and
`quality_capped = (market_cap_tier == marginal) OR (liquidity_tier == marginal)`.
`quality_capped` is attached to EVERY A-dimension entry: a high raw gap on a capped
ticker must **not** read as genuine leadership. This is **exclude-not-down-weight** —
tiers are discrete labels, tradability annotates (it never excludes; the gate already
handled exclusion), there is no continuous multiplier.

---

## 5. Code decides the frontrunner + `no_clear_winner`; the LLM cannot override

Per horizon in {short, mid} (long is `not_applicable` — defers to StockResearch /
ValuationDebate):

- **Ranking key** (`_sort_key`, documented order): `-RS composite` → `volume_confirmation`
  (confirmed > unconfirmed > divergent) → `valuation_elasticity` (lower percentile better;
  unknown sorts last) → tradability (`quality_capped` False before True) → `ticker`
  (byte-stable final tie-break). Only AVAILABLE dimensions participate.
- **`deterministic_frontrunner[horizon]`** = top of that ranking (or None if empty).
- **`no_clear_winner[horizon]`** is set by CODE (the LLM MUST NOT flip it) when either:
  (a) the eligible set is empty; (b) the frontrunner's lead over the runner-up on the
  primary key is below `_RS_GAP_DECISIVE_PCT`; or (c) the frontrunner is `quality_capped`
  AND its lead is not decisive (a lone capped eligible name has no contest → refused —
  the penny-stock-with-biggest-move guard). A capped frontrunner **with** a decisive lead
  over a runner-up is allowed-but-flagged (path (c) only fires when the lead is not
  decisive).
- Short and mid frontrunners MAY be different tickers (a fast RS leader short vs a better
  chain-position / valuation name mid) — this is expected and representable.

---

## 6. Down-scoped UNAVAILABLE dimensions — honest, not fabricated

The PREFLIGHT read of the real dataclasses found **no backing field** for four intended
signals, so each is marked `unavailable` / `unknown` and **excluded from the frontrunner
key** — a data source is never invented:

| Dimension | Why unavailable |
|-----------|-----------------|
| `short_crowding` | No short-interest / days-to-cover / % float field on `OpportunityCard` or `CandidateSignal`. |
| `options_structure` | GEX / call-put wall is not per-ticker at screening time — Stage-2 MoneyFlow's lane. |
| `beta` | No field; was only for a future high-beta strategy (a separate agent). |
| dollar-ADV | No field; `liquidity_tier` uses the documented `candidate_type` proxy instead. |
| `market_cap` | Only on the v1 `FundamentalSignals` shim, generally `None` in production → `market_cap_tier` is usually `unknown`; read opportunistically when a `market_cap` attribute IS present (test / forward-compat). |

---

## 7. The signals= deviation and its fail-closed join

The prompt's sketched signature was cards-only. But the eligibility gate reads
`eps` / `valuation` / `entry_quality` off the **CandidateSignal**, and the
`OpportunityCard` does not carry those fields — so with `signal=None` every card
degrades to a hard-unknown verdict → rejected → the agent produces nothing. The public
API therefore adds an **optional `signals=` kwarg** (list | dict), matched to cards
**exactly by ticker**:

```
run_candidate_screening_agent(cards, *, theme_key, signals=None,
                              theme_context=None, as_of=None,
                              snapshot_dir="data/snapshots") -> AgentOutput
```

The Cockpit passes the live `_candidates` (the CandidateSignal list). The join **fails
closed**: an unmatched or missing signal resolves to hard-unknown → rejected, **never**
silently eligible, and it is an EXACT-by-ticker join (a wrong-ticker signal never
cross-contaminates another card's gate evaluation). ONE `AgentOutput` per theme
(`ticker == theme_key`), never a global output.

---

## 8. The slate skeleton persists in supporting_data (no second file)

Per horizon the code assembles a frozen `CandidateSlate` skeleton:
`primary` = the frontrunner (or None when `no_clear_winner`), `secondary` = the next 0–2
eligible names by the same key (never the primary), `watch` = eligible-but-not-chosen +
all `conditional` tickers, `rejected` = `ineligible` + `unknown` tickers each with the
gate's reason codes, plus `no_clear_winner` / `no_trade_reason` / `signal_basis`.

The machine-readable primary/secondary/watch/rejected is the **CODE-decided** skeleton.
It is placed on the `AgentOutput.supporting_data` **before** the LLM call, so
`append_agent_output` serializes it verbatim — **no second file**, and **not** routed
through the `AgentResult` (which is `extra="forbid"`). The LLM's contribution is the
narrative judgment + per-ticker decisive-factor rationale in findings; it does not choose
the primary (code did) and it does not override `no_clear_winner`.

---

## 9. Three ToolResults + confidence + signal_basis (numeric firewall)

Built via `processed_signals_to_tool_result` **before** the LLM call; every number the
LLM may cite lives here as evidence:

- **TR1 `candidate_screening_comparison`** (`metric_group="screening"`): the per-ticker
  comparison table (ranks, tiers, labels, `quality_capped` flags, availability markers;
  raw RS excess as evidence).
- **TR2 `candidate_screening_slate`** (`metric_group="slate"`): the deterministic slate
  skeleton (primary/secondary/watch/rejected + `no_clear_winner` + `no_trade_reason` +
  `signal_basis`).
- **TR3 `candidate_screening_confidence`** (`metric_group="confidence"`): short/mid/long
  confidence + decomposition + long rationale.

**Confidence (deterministic, before the LLM).** `coverage` = fraction of the theme's
candidates that are eligible-or-conditional with live (non-degraded) RS = usable / total.
`short_confidence = coverage × short_clarity` where `short_clarity` reflects how decisive
the top RS gap is (`min(lead / _RS_GAP_DECISIVE_PCT, 1.0)`; 0 when `no_clear_winner[short]`;
1.0 for a lone decisive eligible name). `mid_confidence` mirrors it. `long_confidence = 0.0`
(defers, `_LONG_RATIONALE`). All `round(…, 6)`.

**`signal_basis` (three-way, per horizon).** `signal_present` (an eligible frontrunner
with a decisive gap); `no_clear_winner` (eligible candidates exist but no decisive
separation — a NEUTRAL / WAIT state the prompt forbids reading as bearish or "sell");
`degraded_insufficient` (no eligible frontrunner, or coverage below `_COVERAGE_MIN`).

---

## 10. Prompt — LLM emits NO number

`REQUIRED OUTPUT FORMAT` block uses **4-space indentation, no backtick fences**. The
interpolated context is **qualitative only** — ticker symbols, role/tier labels,
direction words, `signal_basis` — never a numeric value. The LLM's stated job: explain
WHICH differences are decisive between the code's frontrunner and the runner-up (citing
evidence_ids); translate trade-offs into HORIZON FIT; give INVALIDATION conditions;
respect `quality_capped` (never present a capped ticker's magnitude as leadership);
respect `no_clear_winner` (if code set it, say "theme attractive but no constituent is
decisively actionable" and do NOT manufacture a pick); tone = "worth advancing to trade
construction," never "buy X." Three findings (short / mid / long-defer), each citing at
least one evidence_id, no numeric tokens. `run_llm_agent` call: `horizon="cross"`,
`ticker=theme_key`, `requires_human_confirmation=True`, `judgment_source="llm_proposed"`,
`max_tokens=1024`, `valid_until=end_of_today_iso()`. Outer try/except →
`_fallback_agent_output`. All `lib.reliability` / `lib.llm_orchestrator` /
`lib.agent_framework` / `lib.candidate_eligibility` / `lib.theme_transmission` imports are
function-level lazy (verified by a subprocess import guard, §CSA-11).

---

## 11. Cockpit hook — additive, per-theme loop, fail-closed

In `pages/7_Investment_Cockpit.py::_run_refresh`, **immediately after the
ThemeIntelligenceAgent block, inside the Step 4 `try`**. It reuses the already-computed
`_cards` (ranked opportunities), `_candidates` (their CandidateSignals — the gate needs
them), and `_themes_list` (Step 2) — **no new fetch, no re-rank**. It selects up to 3
ACTIVE themes (`stage in {leading, rotating_in}` AND `stage_confirmed`), and for each
filters `_cards` to that theme and calls `run_candidate_screening_agent`. Each theme runs
in its **own try/except** so one theme's failure isolates. Results are stored under
`st.session_state["candidate_screening_agent_output"]` as a dict keyed by `theme_key`.
Gated on `_has_llm_api_key()` AND non-empty `_cards`. This is **Stage 1 only** — no
Stage-2 ticker-level MoneyFlow wiring. It is a **session-state-only hook with no new
visible widget this phase**; the reporting/degradation-visibility UI is the next phase.

---

## 12. Calibration thresholds (calibration debt)

All named + commented as calibration debt:

- `_RS_GAP_DECISIVE_PCT = 0.08` — min frontrunner lead on the RS composite key.
- `_MCAP_AMPLE = 10_000_000_000.0` — $10B ample market-cap tier (leader-vs-barely above
  the $2B funnel floor).
- `_VOL_CONFIRM_RATIO = 1.2` — volume-surge cutoff (matches `lib.relative_strength`).
- `_COVERAGE_MIN = 0.34` — thin-coverage floor for `degraded_insufficient`.

Reuses the gate's `_EARNINGS_IMMINENT_DAYS` / `_EARNINGS_WINDOW_DAYS`.

---

## 13. KNOWN LIMITATION (P2) — penny-guard coverage is mostly the ALT_SIGNAL proxy

`market_cap` is usually absent in production (only on the v1 `FundamentalSignals` shim)
and dollar-ADV has no field, so `market_cap_tier` is usually `unknown` and the reachable
penny-stock guard collapses to the `candidate_type` ALT_SIGNAL proxy (a name that
bypassed the funnel's $2B / $10M-ADV floor). This is honest — the flag is only raised on
positive marginal evidence, never fabricated — but coverage is thin. This is a driver for
the upcoming **Degradation-Visibility Layer** (surface every agent's degradation
vocabulary from `supporting_data`) and for a future live market-cap / ADV channel.

---

## 14. Tests and Codex arc

**Suite — 104 assertions (`§CSA-1..CSA-18`), fully offline.** Real `OpportunityCard` /
`CandidateSignal` / `FundamentalSignals` instances (no mocks); the deterministic layer is
called directly, and the LLM boundary is stubbed only where a full run is exercised
(`§CSA-8` drives the REAL `run_llm_agent` with `agent_runner._call_llm` patched — success
+ fail-closed fallback). Discriminating cases: frontrunner-by-RS-gap, thin-gap
`no_clear_winner`, penny-guard `quality_capped` path (c) + capped-but-decisive allowed
(§CSA-3 / §CSA-14), short≠mid frontrunner, eligibility routing into the slate,
unavailable-dims-excluded + `_sort_key` cannot read them, degraded coverage,
numeric-firewall real-path + fallback, per-theme identity, determinism, the tie-break
chain (§CSA-12), empty-set path (a) (§CSA-13), the `signals=` fail-closed join (§CSA-15),
no cross-contamination (§CSA-16), and valuation-provenance not re-leaked at the agent
layer (§CSA-18). Plus the lazy-import subprocess guard (§CSA-11).

**Codex arc:** the recon-first PREFLIGHT (surfacing the missing fields + the `signals=`
deviation before implementing) prevented a REJECT; review returned **APPROVE WITH FIXES**
— six discriminating **test additions** (tie-break order, empty-set path, capped-decisive,
missing-signal fail-closed, wrong-ticker no-contamination, unavailable-dim sort guard;
zero production-code bugs) — then **APPROVED**. No production-code change in the fix round.

- **Feature commit:** `PENDING-FEATURE`.
- **Merge commit:** `PENDING-MERGE` (`--no-ff`, two-parent topology preserved), pushed to
  `origin/main`.
