# Phase 8B — ThemeIntelligenceAgent

**Status:** COMPLETE — Codex APPROVED (1 pass).
**Merged:** `main` via `--no-ff` @ `5ecfb7875` (feature commit `7b86dcaba`), 2026-06-26.
**Module:** `lib/agents/theme_intelligence_agent.py`
**Tests:** `scripts/test_phase_8b_theme_intelligence_agent.py` (39 checks, §8B-TI1..TI14).

---

## 1. Objective and differentiation from SectorRotationAgent

ThemeIntelligenceAgent (TIA) is the **fifth production foundation agent** on the
Phase 8A framework (after MacroRegimeAgent, MoneyFlowAgent, MarketStructureAgent,
SectorRotationAgent). It consumes the **same** deterministic theme readout that
SectorRotationAgent (SRA) consumes — the `list[ThemeMomentumResult]` from
`compute_all_themes()` — but answers **two different questions**:

| Agent | Question | Primary signal |
|-------|----------|----------------|
| **SRA** | Which wave / sector character leads *right now*? | within-wave rotation + GICS offense/defense |
| **TIA** | (a) Which *ticker* leads *within* a theme? (b) Which themes are *structurally early* / un-crowded? | per-ticker role × live RS ranking; cross-wave asymmetry |

TIA's two lanes:

1. **ROLE.** Within each top-momentum theme, cross the live `constituent_rs`
   active-window excess ranking against the seed transmission **role** map
   (`leader` / `second_derivative_beneficiary` / `supplier` / `platform` /
   `speculative` / `laggard` / `unknown`). A live ranking that **diverges** from a
   ticker's seed role — e.g. a seed-`leader` showing laggard relative strength — is
   a deterioration signal. No existing agent or page performs this role × live-RS
   join.
2. **ASYMMETRY.** Detect themes that are structurally early in the transmission
   chain (`wave_order` in {1, 2} **AND** an early `stage`) and therefore represent
   un-crowded, asymmetric upside. This is a **cross-wave** angle, explicitly **NOT**
   SRA's "lagging WITHIN the active wave" — the two are different concepts and the
   prompt forbids conflating them.

Like its siblings TIA is interpretation, not computation, and is **advisory**:
`approved_for_execution` is never `True`, `requires_human_confirmation` is always
`True`.

---

## 2. `constituent_rs` is the enabler (prior phase)

TIA is only possible because of the prior **constituent_rs + label lift** phase
(merge `107e0f09e`), which added `ThemeMomentumResult.constituent_rs` — populated in
`_enrich_excess_stage_breadth` by reusing the already-loaded `constituent_closes`
(**zero new network calls**) — storing `{ticker: {"1m", "3m", "active"}}` per
constituent (the per-window EXCESS vs benchmark, `None` values filtered). That same
phase also lifted `CLUSTER_LABELS` / `ROLE_LABELS` into `lib/theme_transmission.py`
as the single source of truth. TIA consumes both: the `constituent_rs["active"]`
excess is the live ranking key, and the seed `TICKER_ROLE_MAP` (via
`get_ticker_role`) supplies the role to cross it against.

**Fixture themes carry `constituent_rs = {}`** (they hit the ETF-miss / `used==0`
early return before enrichment), so TIA's ranking degrades to `[]` for them — by
design, never a fabricated role.

The agent performs **no network I/O and no recompute**: every `theme_transmission`
lookup and `get_diffusion_context` is pure arithmetic over data already on `themes`.

---

## 3. `_rank_theme_constituents` — the role × live-RS join

`_rank_theme_constituents(result, n_top=5)`:

1. Reads `result.constituent_rs`; returns `[]` immediately if empty/missing.
2. For each ticker, reads `constituent_rs[ticker]["active"]`; **filters out** any
   ticker whose active excess is `None` (or whose `"active"` key is absent).
3. Crosses each surviving ticker with `get_ticker_role(theme_key, ticker)`.
4. Sorts **descending** by `active_excess`, takes the top `n_top`, and stamps a
   1-based `rank`.
5. Returns a list of `{ticker, role, active_excess, rank}`.

All imports are **lazy**; the helper **never raises** (a bare `except` returns `[]`)
— a ranking helper must never be able to abort the refresh.

---

## 4. The three confidence formulas (deterministic, before the LLM)

Let `live = [t for t in themes if t.data_source != "fixture"]` and
`theme_coverage = len(live) / len(themes)`.

### short_confidence = `theme_coverage × role_resolution`
- `role_resolution = named_roles / total_constituents`, where:
  - **numerator** `named_roles` = constituents with a valid
    `constituent_rs[...]["active"]` excess **AND** a seed role `!= "unknown"`.
  - **denominator** `total_constituents` = **ALL** constituents across every live
    theme — **honest coverage**, NOT just the RS-populated ones. Pinning the
    denominator to the full live field means partial role coverage reads as partial
    confidence, never as full confidence on a thin slice.
- **Rationale:** the short-term role read is trustworthy in proportion to how many
  of the live constituents we can actually pin to a NAMED role.
- **→ 0.0 when:** no themes / all fixture (coverage 0), no live constituent has an
  active excess (e.g. all `constituent_rs={}`), or every named-role candidate
  resolves to `"unknown"` (resolution 0).

### mid_confidence = `theme_coverage × asymmetry_strength`
- `asymmetry_strength = early_asymmetric / len(ordered_live)`, where `ordered_live`
  are the live themes that have a transmission order, and `early_asymmetric` counts
  those with `wave_order in {1,2}` **AND** `stage in _EARLY_STAGES`.
- **Rationale:** the 2–6 week asymmetry read is trustworthy in proportion to how
  much of the ordered live field is structurally early and un-crowded.
- **→ 0.0 when:** all fixture, no live theme has a transmission order, or no ordered
  live theme is early-wave + early-stage.

### long_confidence = `0.0` (always)
- **Rationale:** theme transmission roles / asymmetry are tactical short-to-mid
  signals and carry no long-horizon information. The long finding always defers to
  **StockResearchAgent** for deep role conviction (`_LONG_RATIONALE`, emitted in
  TR3). Mirrors SRA / MoneyFlowAgent / MarketStructureAgent.

All three are rounded to 6 dp and persisted in TR3 **before** the LLM runs.

---

## 5. `_EARLY_STAGES` design decision — why `""` is excluded

`_EARLY_STAGES = frozenset({"rotating_in"})`. Only `"rotating_in"` counts as
early-stage for asymmetry detection:

- `"rotating_in"` — early relay-in (5D strong / 1M flat-or-weak): structurally
  early, the asymmetric-upside case.
- `"leading"` — both windows strong: already **crowded**, not asymmetric.
- `"rotating_out"` / `"out_of_favor"` — fading / weak: past-peak.
- `""` (empty string) — **data missing**, NOT early. A theme with no computable
  divergence stage must never be counted as an early opportunity; folding `""` into
  the early set would let a data gap masquerade as an asymmetric signal.

`_EARLY_WAVE_ORDERS = frozenset({1, 2})` — orders 1–2 are the structurally early
nodes in the transmission chain (`ai_chips` is order 1; `semiconductor_mfg` /
`hbm_memory` / `cloud_hyperscaler` order 2). The §8B-TI5 mutation probe (flip
`stage` from `"rotating_in"` to `"leading"`) drives `mid` from `1.0 → 0.0`, proving
the `_EARLY_STAGES` membership is load-bearing.

---

## 6. `signal_basis` — why `no_role_signal` is NOT bearish

A low/zero read is ambiguous. The three-way classifier
(`_compute_signal_basis(themes, diffusion, short_conf, mid_conf)`) resolves it:

| Value | Condition | Meaning |
|-------|-----------|---------|
| `signal_present` | `short_conf > 0` OR `mid_conf > 0` | a named live role and/or an asymmetric theme was found |
| `degraded_insufficient` | no live themes, OR `len(live) < len(themes) // 2` | too little live data to assess — must NOT be read as "no signal" |
| `no_role_signal` | live (≥ half) but both confidences are 0.0 | seed-map coverage sparse, OR all themes already late-stage |

`no_role_signal` is deliberately **not** directional. It means the manually-curated
seed `TICKER_ROLE_MAP` did not resolve a named role for the live-ranked
constituents (sparse coverage), **not** that the themes are weak. The prompt forbids
the model from presenting `no_role_signal` as bullish or bearish.
`degraded_insufficient` likewise forces an honest "coverage is insufficient" rather
than a false all-clear.

---

## 7. Cross-wave asymmetry vs within-wave laggard — the distinction

This is the single most important conceptual guard in the prompt. Two superficially
similar ideas must not be conflated:

- **TIA's cross-wave asymmetry** = a theme that is **early in the chain** (low
  `wave_order`) **and** early in its own cycle (`stage="rotating_in"`). The bet is
  that capital has not yet propagated to it — structurally un-crowded upside.
- **SRA's within-wave laggard** (`diffusion["lagging_themes"]`) = a theme **inside
  the currently-hot wave** whose momentum trails its wave's average. The bet is a
  catch-up within an already-active wave.

These are different time-axes (cross-wave propagation vs intra-wave dispersion) and
different theses. The prompt explicitly prohibits presenting one as the other, and
the agent's TR2 `asymmetric_themes` set is built from `wave_order` + `stage`, never
from `lagging_themes`.

---

## 8. Three ToolResults (numeric firewall) — and why each differs from SRA's

All three are built via `processed_signals_to_tool_result` **before** the LLM call;
every number the LLM may cite lives here as evidence, never echoed in finding text.

- **TR1 `theme_intelligence_roles`** (`metric_group="theme_roles"`): `top_themes` —
  the top `_TOP_N_THEMES` (5) **live** themes by momentum_score, each carrying
  `wave_order`, `cluster`, `stage`, `stage_confirmed`, `momentum_score`, and the
  **`ranked_constituents`** list (the role × live-RS join from §3). Plus
  `upstream_downstream` — per top theme, the `upstream_themes` / `downstream_themes`
  / `same_wave_themes` from `get_theme_transmission_summary`, showing propagation
  direction. *Differs from SRA's TR1:* SRA carries theme-level rotation + O/D
  fields; TIA carries **per-ticker** role rankings.
- **TR2 `theme_intelligence_asymmetry`** (`metric_group="asymmetry"`):
  `asymmetric_themes` — live themes with `wave_order in {1,2}` AND
  `stage="rotating_in"`, each with its `upstream_themes`, **sorted by `wave_order`
  ascending then `momentum_score` descending**; `late_stage_themes` — live themes in
  `{leading, rotating_out, out_of_favor}`, the **contrast set** showing what is
  already crowded; `active_wave_context` (`active_order` / `next_order` /
  `next_order_themes`); and `signal_basis`. *No SRA analogue* — this is TIA's
  unique cross-wave lane.
- **TR3 `theme_intelligence_confidence`** (`metric_group="confidence"`):
  `short_confidence`, `mid_confidence`, `long_confidence`, plus the decomposition
  `theme_coverage` / `role_resolution` / `asymmetry_strength`, the counts `n_live` /
  `n_fixture` / `n_asymmetric` / `n_late_stage`, and `long_rationale`.

The `late_stage_themes` contrast set exists so the model can frame asymmetry
*against* what is already crowded, rather than in a vacuum.

---

## 9. Prompt

`REQUIRED OUTPUT FORMAT` block uses **4-space indentation, no backtick fences**
(fences confuse the JSON extractor in `agent_runner`). The interpolated context is
**qualitative only** — theme labels, role words, stage labels, ticker symbols, and
`signal_basis` — never a numeric value (no `wave_order` ints, no excess figures), so
the model is never handed a number to echo. Three findings are required (SHORT role
/ MID asymmetry / LONG defer), each citing at least one evidence_id, with no numeric
tokens in finding text; `confidence` must be an object `{level, rationale, score}`,
never a bare float; `agent_name` must be exactly `"ThemeIntelligenceAgent"` and
`run_id` copied verbatim. The prohibitions block enforces: no `no_role_signal`-as-
bearish, no invented role labels, no cross-wave/within-wave conflation, evidence_ids
only.

---

## 10. Cockpit hook

In `pages/7_Investment_Cockpit.py::_run_refresh`, **immediately after the
SectorRotationAgent hook, inside the Step 4 `try` block** (so `_themes_list` is in
scope). Four invariants:

1. **Additive** — writes only `theme_intelligence_agent_output`; touches no existing
   state.
2. **Dual-gated** — runs only when `_has_llm_api_key()` AND `_themes_list` is
   non-empty (a keyless or theme-less run is a clean no-op).
3. **Reuses upstream** — `themes=_themes_list` (Step 2) **only**. Unlike SRA, TIA
   takes **no `offense_defense`** — its lane is role + asymmetry, not O/D. No new
   fetch.
4. **Fail-closed** — its own `try/except` logs and swallows any agent failure, so
   it never aborts the refresh.

---

## 11. Tests and regression

**New suite — 39 checks (`§8B-TI1..TI14`):** LLM/network mocked at the source
modules; `create_run_context` patched to a no-disk stub; fixtures are real
`ThemeMomentumResult` dataclasses with `constituent_rs` populated. Coverage includes
all confidence edge cases (fixture-only, empty `constituent_rs`, no early-wave
rotating_in), the `signal_basis` three-way classifier, TR1 `ranked_constituents`,
TR2 `asymmetric_themes` membership + `late_stage_themes` contrast, the three
ToolResult names/order, the `run_llm_agent` call contract, LLM-failure fallback, and
the `_rank_theme_constituents` filter/sort behaviour.

**Mutation probes (confirmed discriminating):**
- `§8B-TI3c` — force all roles to `"unknown"`: short `1.0 → 0.0`.
- `§8B-TI5c` — flip `stage` `"rotating_in" → "leading"`: mid `1.0 → 0.0`.
- `§8B-TI13d` — reverse the sort: the highest-excess ticker (AVGO) is no longer
  first (AMD is), proving the descending-sort assertion genuinely discriminates.

**Regression (all green):** ThemeIntelligence **39** · SectorRotation **34** ·
MarketStructure **44** · MoneyFlow **34** · MacroRegime **24** · AgentFramework
**15** · theme_baskets **157** · 7B rotation **229**.

---

## 12. Review and commit

- **Codex review:** 1 pass — APPROVED.
  - **P2a** — the module-level `TYPE_CHECKING` import block (for the `AgentOutput`
    annotation) approved **AS-IS**: it is runtime-safe (never imported at runtime
    via `from __future__ import annotations`), a standard pattern, and matches every
    other foundation agent. The lazy-import rule targets *runtime* imports of
    `lib.reliability` / `lib.agent_framework` / `lib.theme_transmission`, all of
    which are inside function bodies (verified: zero leaked at module load).
  - **P2b** — the test script's module-level imports approved **AS-IS**: the
    lazy-import discipline applies to **agent modules** (which the Cockpit imports on
    every page load), not to standalone test scripts.
- **Feature commit:** `7b86dcaba`.
- **Merge commit:** `5ecfb7875` (`--no-ff`, two-parent topology preserved), pushed
  to `origin/main`.
