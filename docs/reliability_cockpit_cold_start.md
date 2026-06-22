# Cockpit Cold-start Hydration

**Status:** COMPLETE — Codex APPROVED (1 pass, 0 findings)
**Feature commit:** `cbe2ae880`
**Merge:** `--no-ff` → `main` @ `3eb4a8912` (pushed, 2026-06-22)
**Phase doc:** this file

---

## 1. Objective and motivation

On app restart the Streamlit `session_state` is empty, so the Investment Cockpit
(`pages/7_Investment_Cockpit.py`) renders "not loaded" placeholders for every
section until the user clicks **Refresh All**. That refresh is expensive: it
fetches macro data, recomputes themes/signals, and (when a key is present) makes
LLM calls. For everyday debugging and for simply re-opening the app, the user was
forced to pay that cost just to see the *last known* view.

The `_meta` extension (merge `ffe9e1e2`) made this fixable: the three
deterministic `classify_regime` outputs (`key_signals` / `opportunity_posture` /
`confidence`) now live in the daily snapshot `_meta` header alongside the regime,
horizon bias, and the full fragility block. With those persisted, the Cockpit can
**re-read the latest snapshot from disk on cold start** and show Sections A and C
immediately — no network, no LLM, no manual refresh — behind a clearly-labelled
snapshot banner.

Two concrete wins:

* **Debug UX** — restart and instantly see the last persisted regime + opportunity
  cards instead of empty placeholders.
* **No repeated LLM calls** — hydration is a pure snapshot read; it never touches
  the live refresh path.

---

## 2. Architecture

### Extracted, Streamlit-free module

The hydration logic lives in a new module, **`lib/cockpit_hydration.py`**, not
inline in the page:

```python
def hydrate_cockpit_from_snapshot(
    session_state,
    load_meta=None,           # default: audit_query.load_all_meta
    load_opportunities=None,  # default: audit_query.load_all_opportunities
) -> Optional[str]:
```

Reasons for extraction:

* **Unit-testable without Streamlit.** `session_state` is passed in (a plain
  `dict` in tests, `st.session_state` in the page). The module imports no
  `streamlit`. Tests drive the function directly — no `AppTest`, no runtime.
* **Dependency-injected loaders.** The two snapshot readers default to
  `lib.audit_query` (itself a pure, no-network snapshot reader — see
  `docs/reliability_phase_7d_audit_query`) but are injectable so tests supply
  controlled `MetaRecord` / `OpportunityRecord` fixtures.
* **Pure reader.** It computes nothing live; it only re-reads the audit snapshot.

The banner itself stays in the page (it needs `st.info` / `bi`); the function
returns the snapshot date string on success so the caller knows to render it.

### Cold-start gate (runs at most once)

```python
if "macro_regime_result" in session_state:        return None
if "cockpit_hydrated_from_snapshot" in session_state: return None
```

Hydration runs only when **both** are absent:

* `macro_regime_result` present → a live refresh already ran this session; never
  overwrite live data with a snapshot.
* `cockpit_hydrated_from_snapshot` (a dedicated flag) present → hydration already
  ran; a second call within the same session (a Streamlit rerun) is a no-op even
  if the user later cleared individual keys.

### Latest-date selection

`load_all_meta()` returns the full `MetaRecord` history **sorted ascending by
date**, so the most recent snapshot is `metas[-1]`. Opportunities
(`load_all_opportunities()` returns all days) are filtered to **that date only** —
older days are never mixed in.

### Atomic commit

Every value (`macro_regime_result`, `cockpit_fragility`, `cockpit_opportunities`)
is built in **local variables first**; `session_state` is mutated only **after**
all of them are constructed without error. A failure partway through therefore
leaves `session_state` completely untouched — there is no half-populated state.

### `why_now` crash guard (rationale)

The snapshot record (`opportunity_ranker._card_snapshot_record`) persists
`why_now` as reason-**code strings**:

```python
"why_now": [r.code if hasattr(r, "code") else r for r in card.why_now]  # → ["rs_breakout_5d", ...]
```

But Section C's `_render_opportunity_card` iterates that list as **dicts**:

```python
_txt = " · ".join((r.get(f"text_{lang}") or r.get("text_en", "")) for r in _why[:3])
```

Calling `.get(...)` on a string raises `AttributeError`, which would crash the
whole card loop (the render is not individually wrapped). Hydration therefore
**drops non-dict elements**:

```python
card["why_now"] = [r for r in card.get("why_now", []) if isinstance(r, dict)]
```

This is a *guard*, not an injection: it removes the unsafe strings so the render
can't raise, and it injects **no placeholder/error text**. The card simply shows
no why-now line — which is honest, because the LLM-polished sentence
(`why_now_polished_*`) was never persisted to the snapshot either. (Section C's
existing `card.get("why_now_polished_{lang}", "")` default already handles that
missing polished text gracefully.)

---

## 3. What IS hydrated

### Section A — `macro_regime_result` (written as a raw dict)

| key | source |
|-----|--------|
| `regime` | `meta.macro_regime` |
| `confidence` | `meta.confidence` |
| `key_signals` | `meta.key_signals` |
| `opportunity_posture` | `meta.opportunity_posture` |
| `horizon_bias` | `meta.raw["horizon_bias"]` |
| `fragility_level` | `meta.fragility_level` |

> **Why a raw dict, not `save_regime_to_state`?** That helper's serializer
> (`macro_state.serialize_regime`) keeps only its canonical field set and would
> **strip the non-canonical `fragility_level`**. Section A still reads the
> canonical fields (`regime` / `confidence` / `key_signals` /
> `opportunity_posture` / `horizon_bias`) through `get_regime_field`, which
> normalises the dict on read, so direct assignment is safe and preserves the
> extra key.

### Section A — `cockpit_fragility`

Rebuilt by lifting the flat fragility-snapshot keys (mirroring
`market_internals.fragility_snapshot`: `fragility_level`,
`distribution_days_spy/qqq`, `breadth_above_sma20[_prev]`, `good_news_sold`,
`earnings_evaluated`, `earnings_degrade_reason`, …) back out of `MetaRecord.raw`
(the fragility block was merged flat into the `_meta` header at write time). Set
**only when the snapshot actually carried fragility** (`"fragility_level" in
meta.raw`); older files predating fragility leave the key unset, and Section A
shows its "internals unavailable" caption.

### Section C — `cockpit_opportunities`

A list of card dicts reconstructed from `OpportunityRecord.raw` for the latest
date only, each passed through the `why_now` crash guard above. The raw snapshot
record carries every field Section C reads (grades, `setup`, `status_by_horizon`,
`next_trigger_by_horizon`, `blockers` as dicts, `days_to_earnings`,
`days_to_fomc`/`days_to_cpi`, `rs_*`, scores).

### Timestamp / status

* `cockpit_last_refresh` = the snapshot date. The hydration call runs **before the
  header** so the header timestamp shows the snapshot date instead of "Never".
* `cockpit_hydrated_from_snapshot` = the snapshot date (also the once-per-session
  guard flag).
* `cockpit_status` is **left as-is** — the status badges honestly read "stale"
  (we loaded a snapshot, not live data).

---

## 4. What is NOT hydrated, and why

* **`macro_regime_agent_output`** — the `AgentOutput` carries `valid_until` = end
  of day. Re-showing an expired agent output as current would misrepresent it, so
  it is never hydrated from the snapshot. (It is also not persisted there.)
* **Section B** (`theme_momentum_results`) — not in the snapshot.
* **Section D** (`equity_research_results`) — not in the snapshot; equity research
  is on-demand.
* **Section E** (`cockpit_triple_signals`) and `cockpit_all_signals` — not in the
  snapshot.

Sections B / D / E therefore render their existing "not loaded" placeholders after
a cold start, exactly as before the manual refresh.

---

## 5. Bilingual banner design

Rendered by the page immediately after the hydration call, only when hydration
returned a date (i.e. only on successful hydration — never on the no-snapshot or
failure path):

```python
_hydrated_date = hydrate_cockpit_from_snapshot(st.session_state)
if _hydrated_date:
    _hydr_lang = st.session_state.get("language", "en")
    _hydr_banner = {
        "msg_en": f"📁 Showing snapshot data from {_hydrated_date} · Click refresh for live data",
        "msg_zh": f"📁 显示 {_hydrated_date} 快照数据 · 点击刷新获取最新",
    }
    st.info(bi(_hydr_banner, "msg", _hydr_lang))
```

* Uses the existing **`bi()`** helper (reads `msg_zh` / `msg_en` by language).
* Language is read from `session_state["language"]` — never hardcoded.
* Shows the snapshot date and prompts a refresh for live data.
* Placed **before** the header so the header's last-refresh caption reflects the
  snapshot date in the same run.

---

## 6. Fail-closed discipline

* The entire function body is wrapped in `try/except Exception` returning `None`.
* No `st.error` / `st.warning` is ever emitted from the hydration path.
* `session_state` is mutated only after the atomic build succeeds, so any failure
  (missing file, parse error, `KeyError`, a loader raising) leaves it untouched
  and the page renders its placeholders.
* **No `st.rerun()`** is called from the hydration path.
* The page-side call is a single statement; a `None` return simply means no banner.

---

## 7. Codex review

**1 pass, 0 findings — APPROVED.** The review confirmed: the cold-start gate,
latest-date selection, all five Section-A fields, Section C using
`OpportunityRecord.raw` for the latest date only with the `why_now` guard,
`macro_regime_agent_output` and Sections B/D/E left unpopulated, the bilingual
banner shown only on success, `cockpit_last_refresh` set to the snapshot date, the
atomic fail-closed body with no `st.rerun()`, and the `§CS-7` mutation probe being
genuinely discriminating.

---

## 8. UI verification

Cold-start (fresh session) verified manually:

* Section A shows the persisted regime + confidence + `key_signals` +
  `opportunity_posture` + fragility line.
* Section C shows the opportunity cards from the latest snapshot.
* Bilingual banner renders with the snapshot date (EN and ZH).
* The header last-refresh caption shows the snapshot date (not "Never").
* Sections B / D / E show their "not loaded" placeholders.
* After a manual **Refresh All**, the banner disappears (live
  `macro_regime_result` now present → no re-hydration) and live data replaces the
  snapshot view.

---

## 9. Tests and regression

**`scripts/test_cockpit_cold_start.py` — 10 tests** (offline, Streamlit-free;
real `MetaRecord` / `OpportunityRecord` fixtures via injected loaders; no
`AppTest`, no real `data/snapshots/` read):

| case | guards |
|------|--------|
| §CS-1 | no snapshot → no population, no banner (`None`), no error |
| §CS-2 | `macro_regime_result` carries regime / `key_signals` / `opportunity_posture` / `confidence` / `fragility_level`; `cockpit_fragility` rebuilt |
| §CS-3 | `cockpit_opportunities` from `raw`, **latest date only** (older excluded) |
| §CS-4 | `cockpit_hydrated_from_snapshot` == `meta.date` (+ `cockpit_last_refresh`) |
| §CS-5 | runs at most once; a live `macro_regime_result` also blocks hydration |
| §CS-6 | loader raising (meta or opportunities) → no mutation, no exception |
| §CS-7 | **mutation probe** — distinctive `key_signals` must flow through |
| extra | `why_now` code-strings dropped; dict elements survive |
| extra | no `cockpit_fragility` when the snapshot predates fragility |

**Mutation probe confirmed discriminating:** with the `key_signals` mapping
removed, `§CS-2` and `§CS-7` both go RED (sentinel `__PROBE_SIGNAL_42__` — a value
no default could produce). Verified by temporary mutation + restore.

**Regression (no edits to `audit_query` / `opportunity_ranker` / `ui_utils` /
`_run_refresh`):** audit-query **10/10**, cockpit-rebuild **47/47**.

---

## 10. Commit

* Feature commit: `cbe2ae880`
* `--no-ff` merge to `main`: `3eb4a8912` (pushed)
