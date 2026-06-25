# constituent_rs + label lift — ThemeIntelligenceAgent enabler

**Status:** COMPLETE — merged to `main` via `--no-ff` @ `107e0f09e`
(feature commit `626107a5c`), pushed 2026-06-24. Codex APPROVED (1 pass).

**Regression:** `scripts/test_reliability_theme_baskets.py` **157/157** ·
`scripts/test_phase_8b_sector_rotation_agent.py` **34/34**.

---

## Objective

Enable the upcoming **ThemeIntelligenceAgent** to perform **intra-theme ticker
ranking** (which live-strongest tickers carry each theme, joined to their chain
role) and to share the bilingual display labels the Streamlit pages already use —
without any new network fetch and without changing any existing interface.

Three purely additive changes:

1. Lift `CLUSTER_LABELS` / `ROLE_LABELS` into `lib/theme_transmission.py` (single
   source of truth; dedup the page copies).
2. Add `constituent_rs: dict` to `ThemeMomentumResult`.
3. Populate it with per-constituent multi-window excess inside
   `_enrich_excess_stage_breadth`.

---

## Change 1 — Label lift (single source of truth)

`CLUSTER_LABELS` (8 keys) and `ROLE_LABELS` (7 keys) — each value a
`{"en": str, "zh": str}` dict — were duplicated in `pages/2_Sector.py` (both) and
`pages/7_Investment_Cockpit.py` (`CLUSTER_LABELS` only). They are now defined once
in `lib/theme_transmission.py`, inserted after `THEME_TRANSMISSION_ORDER` and
before `TICKER_ROLE_MAP`, grouped with the cluster/order seed data they describe.

Both pages delete their local copies and import lazily from
`lib.theme_transmission`, preserving each page's lazy-import discipline (no
module-top import added):

- `pages/2_Sector.py` — `_render_theme_transmission` imports both at its existing
  lazy-import site; `_render_market_themes` imports both at the top of its body so
  its **nested** card renderers (`_render_card_body`, `_render_card`) resolve them
  by **closure**.
- `pages/7_Investment_Cockpit.py` — extends the existing lazy import at the
  transmission-row `try` block to also import `CLUSTER_LABELS` (so a failed import
  fails closed: the row is simply omitted). `ROLE_LABELS` was never used here and
  is not added.

### Closure capture proof (`co_freevars`)

Because the Sector page's labels become **locals** of `_render_market_themes` (via
the import statement) and the card renderers are nested functions, Python captures
them as free variables. Verified by compiling the page and inspecting the code
objects:

```
_render_market_themes cellvars : (... 'CLUSTER_LABELS', 'ROLE_LABELS', ...)
_render_card_body     freevars : ('ROLE_LABELS', ...)
_render_card          freevars : ('CLUSTER_LABELS', ...)
_render_theme_transmission     : CLUSTER_LABELS / ROLE_LABELS are locals
```

This confirms the nested renderers resolve the labels from the enclosing scope —
**not** as the now-deleted module globals (which would `NameError` at runtime).

---

## Change 2 — `ThemeMomentumResult.constituent_rs`

A single new field, appended **last** on the dataclass, matching the existing
`excess: dict = field(default_factory=dict)` idiom:

```python
constituent_rs: dict = field(default_factory=dict)
```

- No existing field reordered.
- `_REQUIRED_RESULT_FIELDS` in the test is a **subset** assertion
  (`required - field_names`), so adding a field is non-breaking.
- The SectorRotationAgent fixtures construct `ThemeMomentumResult` with keyword
  args only, so a defaulted field requires no change there.

Shape: `{ticker: {"1m": excess, "3m": excess, "active": excess}}`, each value a
float (rounded 4 dp); only windows with a computable value are present.

---

## Change 3 — Population in `_enrich_excess_stage_breadth` ONLY

### Why this is the only correct insertion point

- **`compute_theme_breadth`** computes a per-constituent active-window excess
  (`r - bench_window_ret`) but iterates `constituent_closes.values()` — it has **no
  ticker key**, so it cannot attribute the excess to a ticker.
- **The equal-weight loop in `compute_theme_momentum`** computes per-constituent
  multi-window *raw* returns, but (a) it discards ticker identity (appends into
  `per_window[w]` lists) and (b) the benchmark window map is not yet extracted
  there, so it is **pre-benchmark** (raw, not excess).
- **`_enrich_excess_stage_breadth`** already builds `constituent_closes`
  (`{ticker: Close|None}`) for breadth **and** receives the benchmark window map
  (`bench_win`) and the active window — it is the single point where both the
  ticker key and the benchmark are in hand.

### What it does (zero new network)

Reusing the `constituent_closes` already loaded for breadth, for each constituent
with a non-`None` close it computes, for windows `"1m"`, `"3m"`, and the active
window:

```python
excess = round(_pct_return(close, THEME_WINDOW_DAYS[w]) - bench_win[w], 4)
```

`None` values are filtered (a window with no computable return or no benchmark is
omitted); a constituent whose per-ticker dict ends up empty is not stored. The
active-window excess is stored under a literal `"active"` key — kept separate by
design even when `active_window` equals `"1m"`/`"3m"` (the value may duplicate).

### Coverage by data path

- **Equal-weight themes** — enrichment runs; `constituent_rs` populated.
- **ETF themes** — enrichment runs for them too (constituent OHLCV is fetched for
  breadth on the ETF path), so `constituent_rs` populates **uniformly** across all
  live themes; only the ETF *price* drives the theme return.
- **Fixture-fallback themes** — the `used==0` / ETF-miss early return happens
  **before** enrichment, so `constituent_rs` stays at its `{}` default.

---

## Tests — `§TB-CR1..CR5` (9 checks)

- **CR1** — `constituent_rs` is populated for ≥1 theme (with `1m`/`3m`/`active`)
  when `compute_all_themes` runs under the fake loader.
- **CR2** — structure: string ticker keys; values are dicts with ≥1 of
  `1m`/`3m`/`active` as **floats**; no `None` stored.
- **CR3** — selective-inclusion probe (see below).
- **CR4** — fixture-fallback theme keeps `constituent_rs == {}` (enrichment not
  reached).
- **CR5** — label lift: `CLUSTER_LABELS` (8 keys) + `ROLE_LABELS` (7 keys),
  each value carrying `en` + `zh`.

### §TB-CR3 discrimination — honest account

CR3 drives enrichment with a loader where **NVDA** has a valid close and **INTC**
(and the rest) return `None`, then asserts: NVDA produces an entry, INTC is
excluded, and the NVDA entry carries a float window.

Discrimination was verified **empirically** by mutating the production file:

| Experiment | Mutation | Result |
|---|---|---|
| **Exp A** (review's claim) | comment out `if _close is None: continue` | **157/0 — STAYS GREEN** |
| **Exp B1** | drop `result.constituent_rs = _const_rs` (break positive path) | **154/3 — CR3 RED** |
| **Exp B2** | remove guard **and** store unconditionally (INTC leaks in as `{}`) | **156/1 — CR3 RED** |

**Honest finding:** the original review (P2) claimed removing the
`if _close is None: continue` guard would raise `TypeError` and turn CR3 red. **It
does not.** `_pct_return(None, …)` is `None`-safe (returns `None` via its own
`if close is None` check), so a `None`-close ticker produces an empty
`_ticker_excess`, which the **final `if _ticker_excess:` conditional already
filters out**. The two filters are redundant for the `None` case — removing either
*alone* leaves behavior unchanged; only removing **both** (Exp B2) makes a
`None`-close ticker leak in. The guard is therefore a defensive micro-optimization,
**not** the protection mechanism; the real protection is `if _ticker_excess:`. CR3
genuinely discriminates the two contracts that matter — **positive population**
(Exp B1) and **None-leak exclusion** (Exp B2) — which the prior empty-in/empty-out
CR3 did not (it merely duplicated CR4).

---

## Codex review

**APPROVED — 1 pass.**

- **P1** — not a code issue.
- **P2** — the §TB-CR3 discrimination concern. Fixed by replacing the vacuous
  empty-in/empty-out probe with the selective-inclusion probe above, and by the
  honest empirical account (Exp A/B1/B2) of why the `None` guard is redundant and
  what actually provides the protection.

---

## Merge-topology note (2026-06-24)

The feature branch was based on `docs/align-agent-architecture-roadmap` (2 docs
commits ahead of `main`), so the `--no-ff` merge also landed `821c39069`
(docs: align agent architecture) and `c4f5f17b0` (docs: add ROADMAP_v12) alongside
the phase work. This was surfaced before push; the user approved shipping all three
together.

---

## Next

**Phase 8B — ThemeIntelligenceAgent.** All enablers are now complete. Design lines:

- **SHORT** — intra-theme ticker ranking via `constituent_rs` ×
  `get_ticker_role(theme, ticker)`.
- **MID** — wave / cluster asymmetry via `get_diffusion_context` (recompute
  in-agent) + `get_theme_transmission_summary`.
- **LONG** — `0.0`; defer to the macro / StockResearch layer.
- **Hook** — additive, key-gated, fail-closed, immediately after the
  SectorRotationAgent hook inside the Step 4 `try`; writes only
  `theme_intelligence_agent_output`; reuses `_themes_list` (no new fetch).
