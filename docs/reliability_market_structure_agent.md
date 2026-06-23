# Phase 8B — MarketStructureAgent

**Status:** COMPLETE — Codex-APPROVED (2 passes: initial + fix round).
**Merge:** `--no-ff` into `main` @ `8792343f9` (feature commit `2dfbd563a`), 2026-06-22.
**Files:** `lib/agents/market_structure_agent.py` (new), `pages/7_Investment_Cockpit.py`
(additive hook), `scripts/test_phase_8b_market_structure_agent.py` (new, 44 tests).

---

## Objective

MarketStructureAgent is the **third production foundation agent** on the Phase 8A
framework (after MacroRegimeAgent and MoneyFlowAgent). It wraps the existing
`lib.market_internals` deterministic producer
(`compute_market_fragility` → `FragilityReading`) and turns the market-internals
fragility reading into a horizon-aware, evidence-backed `AgentOutput` that provides
**structural CAUTION context** to the PM agents.

Market internals are a *leading-caution* layer: they warn that the market's
internal structure is deteriorating (distribution days, narrowing breadth, good
news sold, weak bounces, a defensive offense/defense tilt) **before** price
confirms. The agent interprets that deterministic reading; it never computes a new
number and never relaxes a gate.

---

## Hook placement rationale — Step 4, after fragility is computed

The Cockpit `_run_refresh` already computes the fragility reading **once** in Step 4
(`compute_market_fragility`) to drive the banner and the daily snapshot. The
MacroRegimeAgent and MoneyFlowAgent hooks live in Step 1, but MarketStructureAgent
is deliberately placed **after Step 4**, once `cockpit_fragility` /
`cockpit_fragility_series` have been written.

Reason: the **single-vintage invariant**. Step 4 pins one data vintage (the
in-memory fresh `ui_utils.load_ohlcv` loader + the hoisted earnings calendar) so
the benchmark, breadth, rolling series and clock check all share ONE last trading
date. If the agent ran in Step 1 it would have to call `compute_market_fragility`
itself — a **second compute** that (a) duplicates work and (b) risks reading a
different vintage than the banner (the candidate frames are not yet warmed in Step
1). Placing the hook after Step 4 lets the agent **reuse the in-scope `_fragility`
reading** that the banner already rendered, so the agent and the banner can never
disagree.

The hook is:

- **Additive** — writes only `st.session_state["market_structure_agent_output"]`;
  touches no existing state.
- **Key-gated** — runs only when `_has_llm_api_key()` (a keyless run is a clean
  no-op, not a guaranteed fallback write) **and** `_fragility is not None`.
- **Reuses upstream** — injects `reading=_fragility`,
  `fragility_series=list(_fragility.rolling_raw_series)`, and the
  `clock_suspect=(_clk_suspect, _clk_reason)` tuple. No second compute.
- **Fail-closed** — its own `try/except` so an agent failure never aborts the
  refresh.

---

## Three confidence formulas (deterministic, before the LLM)

All three are computed in code and persisted as evidence (the numeric firewall)
**before** the constrained LLM call. The LLM never invents them.

### `short_confidence = coverage × clarity`

How decisively the live internals fired, discounted by how much of the underlying
data was present.

- `coverage = 1.0 − n_degraded_core / _N_CORE_DATA_COMPONENTS`, where
  `_N_CORE_DATA_COMPONENTS = 5` and the five CORE codes are
  `{distribution_days, breadth, earnings_reaction, offense_defense,
  leading_theme_volume}`.
- `clarity = min(points, _HIGH_POINTS_THRESHOLD) / _HIGH_POINTS_THRESHOLD`, with
  `_HIGH_POINTS_THRESHOLD = 4` (mirrors `INTERNALS_CONFIG["high_points"]`);
  clarity saturates at the high threshold (points ≥ 4 → 1.0).
- Edge cases (both → 0.0): `points == 0` (no signal → clarity 0, regardless of
  coverage); all five core components degraded (coverage 0).
- Range 0.0–1.0, rounded to 6 dp.

### `mid_confidence` — trend persistence, cap not floor

The mid horizon trusts a **persistent** deterioration, not a single-day spike.

- Count the trailing run of sessions at/above ELEVATED (`_LEVEL_RANK` ≥ 1) from the
  most-recent end of `rolling_raw_series`.
- Interpolate the run through `_MID_CONFIDENCE_BREAKPOINTS =
  [(0,0.0),(2,0.4),(4,0.7),(6,1.0)]` (saturating linear interpolation, clamped at
  the ends).
- Empty series → 0.0 (no signal trail at all).
- **Degraded path is a CAP, not a floor** (see the fix-round section): when
  `vintage_mismatch` is True OR `hysteresis_source != "rolling"` (the producer fell
  back to the snapshot audit trail), the trailing run is **still interpolated
  normally**, then clamped: `round(min(interpolated, 0.1), 6)`. A flat `normal`
  trail (run 0) therefore still yields 0.0; a deteriorating trail is trusted at
  most 0.1.
- Range 0.0–1.0, rounded to 6 dp.

### `long_confidence = 0.0` (always)

Market internals are intraday-to-~1-month caution signals; they carry no
long-horizon information, so the long confidence is structurally zero (mirrors
`MoneyFlowAgent._compute_long_confidence`). The rationale string `_LONG_RATIONALE`
("Market internals are short-to-mid caution signals; not meaningful beyond ~1
month — long horizon defers to MacroRegimeAgent.") is recorded in the confidence
ToolResult and TR3 payload.

---

## `signal_basis` — three-way classifier (prevents false reassurance)

A `normal` level with zero points is **ambiguous**: it can mean the data is present
and the structure is genuinely constructive, OR that the internals could not be
assessed because the data was missing. Conflating the two would let the agent emit
"market is healthy" when in fact it is blind — a tighten-only violation.

`_compute_signal_basis(reading)` resolves the ambiguity into three values, carried
in TR2 so the prompt can speak honestly:

- `signal_present` — `points > 0` AND something triggered.
- `degraded_insufficient` — no signal AND ≥ 3 core components degraded (coverage
  too thin to assess — the prompt MUST say "insufficient" and MUST NOT imply the
  market is healthy).
- `full_data_no_signal` — no signal but the data IS present (genuinely
  constructive structure — the prompt MUST state "no warning signal detected,
  market structure appears constructive" rather than stay silent).

Precedence: `signal_present` first (points fired), then `degraded_insufficient`
(thin coverage), else `full_data_no_signal`.

---

## Three ToolResults

Built via `processed_signals_to_tool_result`, all before the LLM:

1. **`market_fragility_signals`** (`metric_group="fragility"`) — level / raw_level /
   points / triggered / consecutive_raw + the component values (distribution days
   SPY/QQQ, breadth_above_sma20, breadth_slope, good_news_sold, weak_bounce,
   offense_defense direction & magnitude, leading_theme_volume_shrinking).
2. **`market_fragility_health`** (`metric_group="data_health"`) — degraded list,
   earnings_degrade_reason, hysteresis_source, vintage_mismatch, adjacency_degraded,
   data_vintage, clock_suspect (bool) + clock_suspect_reason (str), and
   **`signal_basis`**.
3. **`market_structure_confidence`** (`metric_group="confidence"`) —
   short/mid/long confidence + n_triggered, coverage, clarity, trailing_run,
   long_rationale.

---

## Tighten-only invariant — what the prompt prohibits and why

`lib.market_internals` is STRICT tighten-only: the regime classifier is frozen, and
fragility can only ADD caution (at `high` it gates the SHORT horizon in-zone
Actionable → wait; `elevated` only annotates). The agent INTERPRETS this reading; it
must never widen that effect. The prompt therefore explicitly prohibits:

- Any **bullish / add-exposure / loosen-risk** recommendation — internals can only
  counsel caution, patience, or tightening, never green-light risk.
- **Overriding or contradicting the macro regime** — regime calls defer to
  MacroRegimeAgent.
- Implying a **normal + degraded** state means the market is healthy — say the
  signal is insufficient instead.
- Implying internals tighten anything **beyond the SHORT horizon**.
- **Inventing numbers** — cite evidence_ids only.

The `REQUIRED OUTPUT FORMAT` block uses 4-space indentation (NOT triple-backtick
fences, which confuse the JSON extractor in `agent_runner`); confidence is an object
`{level, rationale, score}`, `agent_name` is exactly `"MarketStructureAgent"`,
`run_id` is copied verbatim, and no numeric values appear in finding text.
`valid_until = end_of_today_iso()`; the runner's invariant keeps
`approved_for_execution` always `False`.

---

## `leading_theme_breadth_narrowing` exclusion rationale

`compute_market_fragility` always appends `"leading_theme_breadth_narrowing"` to
`degraded` because the component is **permanently scaffolded** — it needs per-theme
historical internal breadth that the snapshot does not yet persist, so it stays
`False` and always-degraded. If it were counted in the coverage denominator, every
refresh would falsely floor coverage (and hence `short_confidence`). It is therefore
**excluded** from `_CORE_DEGRADE_CODES` (denominator = 5, not 6). The five CORE
codes are exactly the components that can actually be present or absent on a given
refresh.

---

## Codex review history

- **Pass 1 (initial review):** 2 findings.
  - **Finding 1 — `mid_confidence` 0.1 was a floor instead of a cap.** The degraded
    path returned 0.1 unconditionally, so a flat `normal` trail (trailing_run = 0)
    wrongly returned 0.1 instead of 0.0. **Fixed:** interpolate the trailing run
    first, then clamp — `return round(min(interpolated, 0.1), 6)` on the degraded
    path; empty series still → 0.0. New boundary tests `§8B-MS6a..6e` cover
    run 0 → 0.0, run 2 (mismatch) → 0.1, run 2 (clean) → 0.4, and the snapshot
    fallback variants.
  - **Finding 2 — TR1 prefixed field names** (`fragility_*` prefixes on the TR1
    payload keys). **APPROVED AS-IS** — the prefixes match the flat
    `fragility_snapshot` schema the rest of the system reads, so they are
    intentional, not drift.
- **Pass 2 (fix round):** Finding 1 verified fixed; re-APPROVED.

---

## Tests & regression

**`scripts/test_phase_8b_market_structure_agent.py` — 44 tests** (`§8B-MS1..MS13`
plus the `§8B-MS6a..6e` boundary cases). All LLM calls are mocked at the
`run_llm_agent` source module and `create_run_context` is stubbed (no disk); all
fixtures are real `FragilityReading` / `FragilityComponents` dataclasses kept
physically plausible (an all-core-degraded reading carries at most the non-core
`weak_bounce` point, never a fabricated higher count).

Coverage highlights:
- `§8B-MS1` full_data_no_signal (points 0, degraded [] → short 0.0).
- `§8B-MS2` degraded_insufficient + mutation probe (removing a degrade code changes
  coverage → short_confidence).
- `§8B-MS3/MS4` short → 1.0 at points 4; clarity saturates at points ≥ 4.
- `§8B-MS5/MS6a–6e/MS7` mid: empty → 0.0; cap-vs-floor boundary; trailing-run
  interpolation (2 → 0.4, 4 → 0.7, ≥ 6 → 1.0; trailing normal breaks the run).
- `§8B-MS8` long always 0.0.
- `§8B-MS9` three ToolResults, correct names & order.
- `§8B-MS10` TR2 carries `signal_basis` with the correct value for all three cases.
- `§8B-MS11` runner call args (agent_id, horizon, valid_until, three tool_results,
  max_tokens, human-confirm, judgment_source).
- `§8B-MS12` LLM failure → fallback AgentOutput, no exception.
- `§8B-MS13` mutation probe (points 2 → neither 0.0 nor 1.0; one degrade → 0.4).

**Regression (all green):** MarketStructure 44/44 · MacroRegime 24/24 ·
MoneyFlow 34/34 · AgentFramework 15/15 · gex_dex 13/13 · massive 5/5 · quiver 6/6 ·
7B rotation & internals 226/226.
