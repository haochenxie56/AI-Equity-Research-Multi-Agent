# Phase 8B — MoneyFlowAgent

**Status:** COMPLETE — Codex APPROVED (2 passes: initial + fix round).
**Merge:** `--no-ff` merge `760f356a3` into `main` (feature commit `1c32d40a7`), pushed 2026-06-22.
**Phase doc owner:** reliability / foundation-agent layer.

---

## 1. Objective and role in the foundation layer

MoneyFlowAgent is the **second production foundation agent** on the Phase 8A
framework (after MacroRegimeAgent). Foundation agents convert deterministic
producers into horizon-aware, evidence-backed `AgentOutput` objects for the PM
layer. MoneyFlowAgent's domain is **money flow / dealer positioning**: where the
options-dealer hedging flow and the dark-pool net flow point over the next hours
to weeks.

It follows the MacroRegimeAgent pattern **exactly**:

```
options chain  -> compute_gex_dex (deterministic dealer positioning)
dark pool      -> compute_dark_pool_signal (deterministic net flow)
               -> deterministic confidence metrics (short / mid / long)
               -> THREE ToolResults into the EvidenceStore (numeric firewall)
               -> constrained Claude prompt -> validated AgentResult
               -> AgentOutput (JSONL)
```

The architectural invariant from CLAUDE.md holds: **code computes facts, tools
produce versioned deterministic outputs, the LLM only interprets**. Every number
the LLM may cite is computed in code and persisted as evidence **before** the LLM
runs; the LLM never invents a GEX sign, a wall, a confidence, or a flow direction.

---

## 2. Two data sources and how they complement each other

| Source | Producer | Schema (consumed) | Horizon character |
|---|---|---|---|
| **GEX/DEX** (Massive Options = Polygon) | `lib/gex_dex.py::compute_gex_dex` over `fetch_options_chain(ticker, expiry_filter)` | `gex_sign`, `dex_sign`, `call_wall`, `put_wall`, `squeeze_probability`, `squeeze_direction`, `squeeze_trigger_conditions`, `degraded`, `regime_summary` (via `gex_dex_to_signals`) | Intraday → ~2 weeks. Dealer gamma/delta positioning: where price is pinned (positive GEX) or amplified (negative GEX), and the OI walls that bound it. |
| **Dark pool** (Quiver Quantitative) | `lib/quiver_fetcher.py::compute_dark_pool_signal` over `fetch_dark_pool` | `net_direction` (bullish/bearish/neutral/insufficient_data), `signal_strength` (strong/moderate/weak/none), `total_amount`, `record_count`, `degraded` | Multi-day → ~1–4 weeks. Aggregated off-exchange buy/sell pressure (price-vs-prev-close proxy). |

**Complementarity.** GEX/DEX is a *structural* read — it describes the
volatility/pinning regime and the levels that matter **right now**. Dark pool is
a *directional, multi-day* read — accumulation or distribution that plays out over
weeks. Together they answer two different questions: GEX/DEX → "what structure am
I trading inside, and where are the walls?"; dark pool → "which way is the slow
money leaning?". The agent's job is to surface **agreement** (both point the same
way → conviction) or **divergence** (structure vs. flow disagree → caution /
mean-reversion setups), and to translate that into a named options-structure
strategy referencing the walls.

Both producers are **fail-closed**: a missing API key or any network/parse error
yields a neutral/degraded result, never an exception. The agent inherits that
discipline and adds its own outer guard.

---

## 3. Three confidence formulas (computed before the LLM)

All three are deterministic, rounded to 6 dp, and persisted as the
`money_flow_confidence` ToolResult **before** the LLM call.

### short_confidence — breadth of the live read
```
signal_1 = gex_sign  ∈ {positive, negative}  AND not gex_result.degraded
signal_2 = dex_sign  ∈ {positive, negative}  AND not gex_result.degraded
signal_3 = dark_pool net_direction ∈ {bullish, bearish} AND not dark_pool.degraded
short_confidence = (signal_1 + signal_2 + signal_3) / 3
```
**Rationale.** The short horizon trusts *breadth*: how many of the three
independent money-flow signals carry a usable direction rather than collapsing to
neutral/degraded. A degraded GEX/DEX read zeros **both** signal_1 and signal_2
(they share the same chain). Fully neutral/degraded → 0.0.

### mid_confidence — dark-pool strength × direction clarity
```
strength_map = {strong: 1.0, moderate: 0.6, weak: 0.3, none: 0.0}
direction_valid = dark_pool net_direction ∈ {bullish, bearish}
mid_confidence = strength_map[signal_strength]  if (direction_valid and not degraded) else 0.0
```
**Rationale.** The dark-pool aggregator is a *multi-day net-flow* read, so it
anchors the 1–4 week horizon. Confidence scales with the strength of the flow, but
only when the net direction is decisive — `degraded=True` OR
`net_direction ∈ {neutral, insufficient_data}` collapses it to 0.0 (a strong
*magnitude* with no clear *direction* must not borrow confidence).

### long_confidence — structurally zero
```
long_confidence = 0.0   (always)
```
**Rationale.** GEX/DEX and dark pool are **intraday-to-3-week** signals; they
carry no long-horizon information. Rather than fabricate a weak long score, the
agent returns 0.0 and records the rationale string
(`"GEX/DEX and dark pool are intraday-to-3-week signals; not meaningful beyond 1
month"`) in both the confidence ToolResult description and the `long_rationale`
field of the TR3 payload. The long-horizon finding explicitly defers to
MacroRegimeAgent.

---

## 4. prior_result design (squeeze condition C)

`compute_gex_dex(chain, expiry_filter, prior_result=...)` evaluates **gamma
squeeze condition C** — *DEX trend rising* — as `dex_total > prior_result.dex_total`.
Without a prior snapshot, condition C is unreachable (you cannot rise above an
unknown baseline). To make condition C live across runs, MoneyFlowAgent persists
its `GexDexResult` fields in `supporting_data` each run and reloads them on the
next run.

### `_load_prior_gex_dex_result(agent_output_dir, ticker)`
- Reads the **newest** `MoneyFlowAgent` JSONL under
  `<agent_output_dir>/MoneyFlowAgent/<YYYY-MM-DD>.jsonl` (newest file first; within
  a file, the last line is newest), filtered to the matching `ticker`.
- **Validates `_REQUIRED_PRIOR_FIELDS`** — an 11-key frozenset:
  `{ticker, gex_total, dex_total, gex_sign, dex_sign, call_wall, put_wall,
  squeeze_probability, squeeze_direction, contracts_used, degraded}`. If the most
  recent matching record is missing **any** one of these, it returns `None` rather
  than silently defaulting a fabricated prior state into `compute_gex_dex`.
- **Reconstructs** a `GexDexResult` via `_reconstruct_gex_dex` (only `dex_total`
  is functionally consumed downstream; the remaining required dataclass fields not
  stored on output are filled with neutral defaults).

### Fail-closed discipline
- No prior dir / no matching record → `None`.
- Most-recent matching record missing a required field → `None`.
- **Unreadable file OR any invalid-JSON line → `None` immediately.** The function
  does **not** `continue` to an older file: a corrupted most-recent file must not
  cause the agent to silently fall back to stale prior state. This was Codex
  Finding 2 (see §7).
- The whole body is wrapped so it **never raises** — a prior-state read can never
  abort a refresh.

`supporting_data` carries every `GexDexResult` field the next run needs
(`gex_total`, `dex_total`, `gex_sign`, `dex_sign`, `call_wall`, `put_wall`,
`squeeze_probability`, `squeeze_direction`, `contracts_used`, `degraded`, plus
`dark_pool_direction` / `dark_pool_strength` and the three confidences).

---

## 5. Prompt design

The `task_instruction` is built dynamically and interpolates **only qualitative
context** (signs, probability bands, directions) — never a number the model could
echo. It demands three findings:

- **SHORT (intraday–2 weeks):** GEX environment and its volatility implication,
  DEX direction and buy/sell support, agreement/divergence with dark pool, gamma
  squeeze status/direction if mid/high. **Must name a strategy type** (directional
  long/short, sell put spread, sell call spread, iron condor) and reference a key
  level (call wall / put wall) from evidence. **A neutral GEX environment MUST
  still produce an options-structure strategy** (e.g. an iron condor / credit
  spread between the walls) — never "wait and see".
- **MID (1–4 weeks):** dark-pool multi-day flow direction + strength, whether the
  GEX structure supports or contradicts it, and the positioning implication.
- **LONG (6–18 months):** always state that money-flow signals are not meaningful
  beyond one month, and defer long-horizon context to MacroRegimeAgent.

**Invariants enforced in the prompt and by the framework:**
- `REQUIRED OUTPUT FORMAT` block uses **4-space indentation, NOT triple-backtick
  fences** (fences confuse the JSON extractor in `agent_runner`).
- `findings[]` is a list of `{text, evidence:[{evidence_id, excerpt}]}`;
  `confidence` is an **object** `{level, rationale, score}`, never a float;
  `run_id` and `agent_name` ("MoneyFlowAgent") copied verbatim.
- **No numbers / `$` / `%` / metric tokens in finding text.** Numeric specifics
  live in `supporting_data` + evidence, not in the prose judgment.
- Every finding must cite ≥1 `evidence_id` from the packet.
- `_repair_llm_response` (in `agent_runner`) coerces a flattened response into the
  `AgentResult` shape before the schema bind; `_SYSTEM_INVARIANTS` reinforce the
  rules. `approved_for_execution` is always `False`.

---

## 6. Cockpit hook — four invariants

Inserted in `pages/7_Investment_Cockpit.py::_run_refresh` Step 1, **immediately
after the MacroRegimeAgent hook**:

```python
try:
    from lib.agents.money_flow_agent import run_money_flow_agent
    from lib.llm_orchestrator import _has_llm_api_key
    if _has_llm_api_key():
        _mf_output = run_money_flow_agent(ticker="SPY")
        st.session_state["money_flow_agent_output"] = _mf_output
except Exception as _e:  # noqa: BLE001 — additive; never abort the refresh
    import logging
    logging.warning("MoneyFlowAgent failed: %s", _e)
```

1. **Additive** — writes only the new `money_flow_agent_output` key; touches no
   existing state.
2. **Key-gated** — `_has_llm_api_key()` so a keyless run is a clean no-op, not a
   guaranteed fallback write.
3. **Reuses upstream / no second fetch** — defaults `ticker="SPY"` (the index
   proxy); fetches its own GEX/DEX + dark-pool signals (its domain is independent
   of the macro regime), but adds no second macro fetch.
4. **Fail-closed** — its own `try/except` guarantees an agent failure never aborts
   the refresh.

---

## 7. Codex review history

**Pass 1 (initial review).** Two findings:
- **Finding 1 — missing required-field validation.** `_load_prior_gex_dex_result`
  originally checked only `gex_total` / `dex_total` before reconstructing a
  `GexDexResult`; other required fields could be silently defaulted, feeding a
  fabricated prior to `compute_gex_dex`. **Fix:** validate the full 11-key
  `_REQUIRED_PRIOR_FIELDS` frozenset; missing any one → `None`.
- **Finding 2 — unreadable JSONL falls through to older records.** A corrupted
  most-recent file used `continue` to skip to the next (older) file — fail-open,
  silently using stale prior state. **Fix:** on any unreadable/unparseable file,
  return `None` immediately (no fall-through).

**Pass 2 (fix round).** Both fixes verified; **APPROVED, 0 findings remaining.**
Two new assertions added to lock the fixes (`§8B-MF8b` missing-field → `None`;
`§8B-MF8c` invalid-JSON → `None`, no fall-through).

---

## 8. Tests and regression

**Suite:** `scripts/test_phase_8b_money_flow_agent.py` — **34 checks, all passing.**
Project hand-rolled harness (not pytest). All LLM calls mocked at the
`lib.agent_framework.agent_runner.run_llm_agent` source; all network mocked at the
`fetch_options_chain` / `compute_gex_dex` / `compute_dark_pool_signal` sources
(lazy imports pick up the patched attrs). Fixtures are the **real** `GexDexResult`
dataclass and the **exact** dark-pool dict schema.

Coverage: `§8B-MF1` (short=1.0 + flip-probe), `§8B-MF2` (gex degraded → 0.0 + only
dark pool counts), `§8B-MF3` (strength_map + neutral-direction probe), `§8B-MF4`
(long always 0.0), `§8B-MF5` (three ToolResults / correct names), `§8B-MF6`
(run_llm_agent args: horizon=cross, valid_until, three TRs, max_tokens=1024),
`§8B-MF7` (LLM failure → fallback, no exception), `§8B-MF8` (cold start → None),
`§8B-MF8b` (missing field → None), `§8B-MF8c` (invalid JSON → None), `§8B-MF9`
(reconstruct + wrong-ticker/missing-field probes), `§8B-MF10` (supporting_data
carries all reconstruction fields), `§8B-MF11` (agree_count==2 → neither 0.0 nor
1.0).

**Two mutation probes confirmed discriminating:**
- `§8B-MF1` — flipping one signal to neutral drops short_confidence below 1.0.
- `§8B-MF11` — a `signals_agree_count == 2` fixture yields a value that is neither
  1.0 nor 0.0 (the formula is discriminating, not a pass-through).

**Regression (no new failures):** MoneyFlow 34/34 · MacroRegime 24/24 ·
AgentFramework 15/15 · gex_dex 13/13 · quiver 6/6 · reliability-foundation green.

---

## 9. Commit

- Feature commit: `1c32d40a7`
- `--no-ff` merge into `main`: **`760f356a3`** (pushed)
- Files: `lib/agents/money_flow_agent.py` (new),
  `scripts/test_phase_8b_money_flow_agent.py` (new),
  `pages/7_Investment_Cockpit.py` (additive hook).
