# Phase 8B — SectorRotationAgent

**Status:** COMPLETE — Codex APPROVED (1 pass, 0 findings).
**Merged:** `main` via `--no-ff` @ `fbf0cc41d` (feature commit `b3ffd88b9`), 2026-06-22.
**Module:** `lib/agents/sector_rotation_agent.py`
**Tests:** `scripts/test_phase_8b_sector_rotation_agent.py` (34 checks, §8B-SR1..SR14).

---

## 1. Objective and agent role

SectorRotationAgent is the **fourth production foundation agent** on the Phase 8A
framework (after MacroRegimeAgent, MoneyFlowAgent, MarketStructureAgent). It turns
the deterministic **theme-momentum rotation** read and the **GICS offense/defense**
read into a horizon-aware, evidence-backed `AgentOutput` for the PM layer.

Its job is interpretation, not computation: it tells the Short / Mid / Long PM
agents *where capital is rotating across the AI industry chain* and *whether the
broad market favors offense or defense* — citing only code-computed evidence, never
inventing a number, a stage, or a direction. Like its siblings it is **tighten-safe
and advisory**: `approved_for_execution` is never `True` and
`requires_human_confirmation` is always `True`.

---

## 2. Two data sources — both injected, no new fetches

| Source | Origin | How it reaches the agent |
|--------|--------|--------------------------|
| Theme momentum | `lib.theme_baskets.compute_all_themes()` — Cockpit **Step 2** | `themes: list[ThemeMomentumResult]` passed in |
| Offense/defense | `lib.rotation.offense_defense_reading()` computed inside `compute_market_fragility` — Cockpit **Step 4** | `offense_defense: dict` read from `FragilityReading.offense_defense` (the full reading, enabled by the prior **O/D extension**) |

The agent performs **no network I/O and no recompute**. The only derived data it
builds is the **diffusion context** (see §3), which is pure arithmetic over the
momentum scores already present on `themes`.

This mirrors MarketStructureAgent's "inject, don't recompute" discipline: the
Cockpit computes each producer once, and the agent consumes the already-computed
object — so the banner and the agent can never diverge on vintage.

---

## 3. `get_diffusion_context` — pure arithmetic, no network

`lib.theme_transmission.get_diffusion_context({theme_key: momentum_score})` groups
the themes by transmission **wave** (order 1–4), averages momentum per wave, and
returns the leading wave (`active_order`), its clusters (`active_clusters`), the
next wave (`next_order` / `next_order_themes`), and the themes lagging within the
active wave (`lagging_themes`). It is deterministic, offline, and side-effect free
— it never touches yfinance, an LLM, or Streamlit. The agent imports it **lazily**
inside `run_sector_rotation_agent`.

---

## 4. The three confidence formulas (deterministic, before the LLM)

Let `live = [t for t in themes if t.data_source != "fixture"]` and
`theme_coverage = len(live) / len(themes)`.

### short_confidence = `theme_coverage × short_clarity`
- `short_clarity = (# live themes with stage_confirmed=True) / len(live)`.
- **Rationale:** the short-term rotation read is trustworthy in proportion to how
  much *live, breadth-confirmed* rotation the themes actually show. Unconfirmed
  stages are single-stock noise and do not count.
- **→ 0.0 when:** no themes / all fixture (coverage 0), or no live theme has a
  confirmed stage (clarity 0).

### mid_confidence = `theme_coverage × dispersion × wave_clear`
- `dispersion = max(momentum_score) − mean(momentum_score)` over live themes (0–1).
- `wave_clear = 1.0` iff `diffusion["active_order"] is not None`, else `0.0`.
- **Rationale:** the 2–6 week read is trustworthy when there is a clearly-led wave
  AND the leader is separated from the field — a flat percentile field carries no
  rotation conviction.
- **→ 0.0 when:** all fixture, no `active_order` (wave_clear 0), or a flat
  momentum field (dispersion 0).

### long_confidence = `0.0` (always)
- **Rationale:** theme rotation / sector momentum are tactical short-to-mid signals
  and carry no long-horizon information, so the long confidence is structurally
  zero. The long finding always defers to MacroRegimeAgent for sector-cycle context
  (`_LONG_RATIONALE`, emitted in TR3). Mirrors MoneyFlowAgent / MarketStructureAgent.

All three are rounded to 6 dp and persisted in TR3 **before** the LLM runs.

---

## 5. `signal_basis` — why `no_clear_leadership` is neutral, not bearish

A low/zero short read is ambiguous: it can mean "data present, no rotation" or "we
could not assess rotation". The three-way classifier resolves it:

| Value | Condition | Meaning |
|-------|-----------|---------|
| `signal_present` | `n_confirmed > 0` AND `active_order` set | a confirmed stage fired and a leading wave exists |
| `degraded_insufficient` | no live themes, OR `len(live) < len(themes) // 2` | too little live data to assess — must NOT be read as "no rotation" |
| `no_clear_leadership` | data present, but neither a confirmed stage nor a clear wave | **a genuine neutral / wait state** |

`no_clear_leadership` is deliberately **not** directional. Absence of a clear
rotation leader is not a sell signal and not a buy signal — it is a "wait for
confirmation" state. The prompt enforces this explicitly: the model is forbidden
from presenting `no_clear_leadership` as bullish or bearish, and must state plainly
that no clear leadership is present. `degraded_insufficient` likewise forces an
honest "coverage is insufficient" rather than a false all-clear.

---

## 6. Three ToolResults (numeric firewall) — why TR1 carries the full O/D fields

All three are built via `processed_signals_to_tool_result` **before** the LLM call;
every number the LLM may cite lives here as evidence, never echoed in finding text.

- **TR1 `sector_rotation_signals`** (`metric_group="rotation"`): `top_themes` (top 5
  by momentum_score), the diffusion wave fields (`active_order`, `active_clusters`,
  `next_order`, `next_order_themes`, `lagging_themes`), `offense_defense_direction`
  / `offense_defense_magnitude`, **and the full offense/defense fields `od_avg_diff`
  / `od_confirming_windows` / `od_n_windows`**.
- **TR2 `sector_rotation_health`** (`metric_group="data_health"`): `n_themes`,
  `n_live`, `n_fixture`, `fixture_theme_keys`, `theme_coverage`,
  `active_window="1m"`, `signal_basis`, `od_available`.
- **TR3 `sector_rotation_confidence`** (`metric_group="confidence"`):
  `short_confidence`, `mid_confidence`, `long_confidence`, `theme_coverage`,
  `short_clarity`, `mid_clarity`, `dispersion`, `wave_clear`, `long_rationale`.

**Why the full O/D fields matter:** `od_avg_diff` / `od_confirming_windows` /
`od_n_windows` come straight from `FragilityReading.offense_defense`, which only
became available after the prior **O/D extension** surfaced the whole reading (the
producer previously discarded everything but `direction` / `magnitude`). Their
presence in TR1 is the concrete payoff of that extension — and `§8B-SR14` asserts
the injected values (`avg_diff=-3.1`, `confirming_windows=["1m","3m"]`,
`n_windows=4`) appear verbatim in the TR1 payload, proving the agent consumes the
extension rather than recomputing.

`active_window` is pinned to `"1m"` because the Cockpit computes themes with
`regime="unknown"` (Step 2), so the theme breadth lens is always the 1M window —
recorded honestly in TR2 rather than implied.

---

## 7. Prompt

`REQUIRED OUTPUT FORMAT` block uses **4-space indentation, no backtick fences**
(fences confuse the JSON extractor in `agent_runner`). The interpolated context is
**qualitative only** — theme/cluster names, stage words, the offense/defense
direction/magnitude words, and `signal_basis` — never a numeric value, so the model
is never handed a number to echo. Three findings are required (SHORT / MID / LONG),
each citing at least one evidence_id, with no numeric tokens in finding text;
`confidence` must be an object `{level, rationale, score}`, never a bare float;
`agent_name` must be exactly `"SectorRotationAgent"` and `run_id` copied verbatim.

---

## 8. Cockpit hook

In `pages/7_Investment_Cockpit.py::_run_refresh`, **immediately after the
MarketStructureAgent hook, inside the Step 4 `try` block** (so `_themes_list` and
`_fragility` are in scope). Four invariants:

1. **Additive** — writes only `sector_rotation_agent_output`; touches no existing
   state.
2. **Dual-gated** — runs only when `_has_llm_api_key()` AND `_themes_list` is
   non-empty (a keyless or theme-less run is a clean no-op).
3. **Reuses upstream** — `themes=_themes_list` (Step 2) and
   `offense_defense=getattr(_fragility, "offense_defense", {})` (Step 4). No new
   fetch.
4. **Fail-closed** — its own `try/except` logs and swallows any agent failure, so
   it never aborts the refresh.

---

## 9. Tests and regression

**New suite — 34 checks (`§8B-SR1..SR14`):** LLM/network mocked at the source
modules; `create_run_context` patched to a no-disk stub; fixtures are real
`ThemeMomentumResult` dataclasses. Coverage includes all confidence edge cases
(fixture-only, no confirmed stage, no active_order, flat field), the `signal_basis`
classifier, the three ToolResult names/order, TR2 (`signal_basis` / `od_available`),
TR1 full-O/D fields, LLM-failure fallback, and the `run_llm_agent` call contract.

**Mutation probes (confirmed discriminating):**
- `§8B-SR3c` — flip one theme to fixture: short `1.0 → 0.667`.
- `§8B-SR6c` — set `active_order=None`: mid `0.4 → 0.0`.

**Regression (all green):** SectorRotation **34** · MarketStructure **44** ·
MoneyFlow **34** · MacroRegime **24** · AgentFramework **15** · 7B rotation **229** ·
8B-0 gex_dex **13** / massive **5** / quiver **6**.

---

## 10. Review and commit

- **Codex review:** 1 pass, 0 findings — APPROVED.
- **Feature commit:** `b3ffd88b9`.
- **Merge commit:** `fbf0cc41d` (`--no-ff`, two-parent topology preserved), pushed
  to `origin/main`.
