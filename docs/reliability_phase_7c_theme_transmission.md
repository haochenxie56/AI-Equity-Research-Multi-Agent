# Phase 7C — Theme Transmission Mapping

**Status**: Implemented + UI-verified (lib + tests green). Review-only; not
investment advice. **Awaiting review — not merged to `main`, not pushed.**
**Suite**: `scripts/test_reliability_theme_transmission.py` — **11 sections
(S1–S9 + extras), ALL 11 TESTS PASSED**, mock-only / offline.
**Branch / feature commit**: `phase-7c-theme-transmission` @ `bbdf5b0`.

---

## Overview

Phase 7C adds a deterministic **transmission-chain** layer on top of the
existing theme-basket system. It represents the *order* in which capital
propagates across the AI industry chain and each ticker's *role* within a
theme, so the UI can show where capital is currently concentrated and which
nodes are next.

The layer is **display / context only**. It contributes **no number to any
scoring path** — `lib/opportunity_ranker.py` is touched solely to append
human-readable rationale tags. Reliability principle preserved: *code computes
facts; this layer interprets and labels, it does not rank.*

---

## What shipped

### New module — `lib/theme_transmission.py`

- **`THEME_TRANSMISSION_ORDER`** — the 12 AI themes mapped to a capital
  propagation **order** (1–4, a *sequence* not a strength ranking) and a
  **transmission cluster** (`compute_core`, `supply_chain`,
  `demand_application`, `infrastructure`, `defense_security`,
  `physical_buildout`, `endpoint_diffusion`, `adjacent_cycle`).
- **`TICKER_ROLE_MAP`** — per-ticker role seed across all 12 themes using the
  Phase-5 `ThemeCandidateRole` literal (`leader`,
  `second_derivative_beneficiary`, `supplier`, `platform`, `speculative`,
  `laggard`). Tickers absent from the seed resolve to `unknown` — the module
  never raises on an unknown ticker and never skips a constituent.
- **Builds onto** `lib/reliability/phase5_theme_intelligence.py` (Phase 5J)
  rather than introducing a parallel schema: `IndustryChainNode`,
  `ThemeCandidateRole`, `ThemeCandidateTicker`, `ThemeRecord`,
  `SubthemeRecord`, `ThemeIntelligenceSnapshot`. **Zero schema duplication.**
  `build_theme_transmission_snapshot()` maps the baskets + seeds onto that
  schema and runs `validate_theme_intelligence_snapshot()` as a build-time
  integrity check (a dangling chain-node ref raises `ValueError`).
- **Public API**: `get_transmission_order`, `get_transmission_cluster`,
  `get_ticker_role`, `get_theme_transmission_summary`, `get_diffusion_context`.
- **Zero network calls, zero LLM calls**; all seed data deterministic.

### New test — `scripts/test_reliability_theme_transmission.py`

11 sections: the real build path (zero dangling refs), schema mapping + role
validity, query functions + unknown fallbacks, role-map ⊆ constituents,
summary structure, diffusion context, snapshot caching, plus the reliability
guards **S1** (import isolation, AST-based), **S7** (opportunity_ranker
fail-closed import inside a `try`, AST-based), **S8** (no
`approved_for_execution` literal), and **S9** (the existing
`test_reliability_theme_baskets.py` suite still exits 0 — parity regression).
**ALL 11 TESTS PASSED.**

### Consumer wiring (display only)

- **`lib/opportunity_ranker.py`** — fail-closed `try/except ImportError` import
  of `theme_transmission`; transmission role tags appended to the rationale
  `ReasonCode` list. **Zero changes to scoring, weights, or numeric outputs**
  (the three-period scoring logic is untouched); `unknown` roles are omitted.
- **`pages/7_Investment_Cockpit.py`** — theme card gains a transmission row
  (`第N波 · <cluster>`, localized via a `CLUSTER_LABELS` map) plus a leaders +
  downstream-themes caption; fail-closed (the row is simply omitted on any
  error).
- **`pages/2_Sector.py`** — Market Themes tab redesigned into a wave-based card
  layout (4 waves, horizontal `st.columns` per wave) with button-triggered
  expand/collapse cards; the thumbnail adopts the Cockpit theme-card visual
  style; cluster + role labels localized.

---

## Files

**Created**
- `lib/theme_transmission.py`
- `scripts/test_reliability_theme_transmission.py`
- `docs/reliability_phase_7c_theme_transmission.md` (this file)

**Modified**
- `lib/opportunity_ranker.py` (display-only rationale tags)
- `pages/7_Investment_Cockpit.py`
- `pages/2_Sector.py`

**Untouched (deliberately)**
- `lib/reliability/phase5_theme_intelligence.py` — reused, not modified.
- `lib/theme_baskets.py` — read-only consumer; not modified.

---

## Invariants

- **Isolation**: `theme_transmission` imports only `theme_baskets` and
  `phase5_theme_intelligence`; it never imports `opportunity_ranker`,
  `thesis_ingestion`, `anchor_cache`, or any `pages/` module (enforced by test
  S1).
- **Scoring firewall**: transmission data is display / rationale only and never
  enters the ranking math (the ranker import is fail-closed; S7 pins the
  `try/except ImportError`).
- **Determinism**: no network, no LLM; all seed data is a static, manually
  curated June-2026 snapshot (`seed_source = "manual"`).
- **No execution surface**: no `approved_for_execution` field anywhere (S8).
- **Parity**: the active `scripts/test_reliability_*.py` sweep is **68** suites
  (67 prior + this new suite); `test_reliability_theme_baskets.py` still exits
  0 (S9).
