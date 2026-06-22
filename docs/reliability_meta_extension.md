# Reliability — `_meta` Extension: key_signals / opportunity_posture / confidence

**Status:** COMPLETE · Codex APPROVED (2 passes, 0 findings) · merged to `main`
via `--no-ff` @ `ffe9e1e2` (feature commit `7a76bcb3`), pushed · 2026-06-21

---

## Objective & Motivation

Persist three macro-regime fields into the daily snapshot `_meta` block (line 1 of
`data/snapshots/opportunities_YYYYMMDD.jsonl`) so they are available for **cold-start
hydration** of the Investment Cockpit. Today the Cockpit's Section A renders the
macro regime summary (`key_signals`, `opportunity_posture`, `confidence`) only from
live `session_state` produced by a fresh refresh. On app restart with an empty
`session_state` those three fields are gone, so Section A cannot be rebuilt from the
snapshot alone. This phase is the **prerequisite** for the next task (Cockpit
cold-start hydration): with these fields in the snapshot, a restart can repopulate
the full Section A (regime + fragility + the three fields) without a manual refresh.

All three are **deterministic outputs of `lib.macro_regime.classify_regime`** — rule-
based, computed from macro indicators. **No LLM is involved**, so this introduces no
risk of model-invented values into the snapshot audit trail.

---

## The three fields

| Field | Type | Source | Typical shape |
|-------|------|--------|---------------|
| `key_signals` | `list[str]` | `classify_regime` → `MacroRegimeResult.key_signals` | canonical English signal tags, e.g. `["vix_low — risk appetite firm", ...]`; may be `[]` |
| `opportunity_posture` | `str` | `classify_regime` → `MacroRegimeResult.opportunity_posture` | canonical English posture sentence; may be `""` |
| `confidence` | `str` | `classify_regime` → `MacroRegimeResult.confidence` | one of `low` / `medium` / `high` |

**Canonical ENGLISH is persisted.** Section A translates `key_signals` /
`opportunity_posture` to Chinese for display (via `_macro_zh` / `translate_str_list`),
but translation is a **view concern** — the snapshot stores the canonical English
forms, and hydration re-applies translation at render time.

---

## Changes

### `lib/opportunity_ranker.py` — `write_daily_snapshot`
- Three new keyword args with **safe defaults**: `key_signals: Optional[list] = None`,
  `opportunity_posture: str = ""`, `confidence: str = ""`. Existing callers that omit
  them are unaffected (defaults `[] / "" / ""`).
- The `_meta` dict writes all three: `"key_signals": key_signals or []`,
  `"opportunity_posture": opportunity_posture`, `"confidence": confidence`.
- **Pre-`try` collision guard** (see Design decisions).

### `lib/audit_query.py` — `MetaRecord`
- Three new fields (`key_signals: list = field(default_factory=list)`,
  `opportunity_posture: str = ""`, `confidence: str = ""`) declared **after `raw`**.
- `from_dict` reads them with `.get()` defaults:
  `key_signals=d.get("key_signals", [])`, `opportunity_posture=d.get(..., "")`,
  `confidence=d.get(..., "")`. Old snapshots predating the keys parse cleanly.

### `pages/7_Investment_Cockpit.py` — `_run_refresh` (Step 4)
- The `write_daily_snapshot` call site passes the three values read from
  `session_state` via `get_regime_field("key_signals", [])`,
  `get_regime_field("opportunity_posture", "")`, `get_regime_field("confidence", "")`.
  No other change.

---

## Design decisions

1. **Safe defaults so existing callers are unaffected.** Every test caller and the
   live Cockpit path that omit the new kwargs continue to write a valid `_meta` (the
   three keys present with empty values). No call site outside the Cockpit needed a
   change.

2. **Streamlit-free lib.** `write_daily_snapshot` does **not** reach into
   `session_state`; the three values are passed as kwargs from the page. The
   `lib/` boundary stays importable without a Streamlit runtime.

3. **Dataclass field ordering — new fields after `raw`.** `MetaRecord`'s existing
   fields have no class-body defaults (including `raw: dict`, declared last).
   Inserting defaulted fields *before* a non-default field is a `TypeError`
   ("non-default argument follows default argument"). Giving `raw` a default would
   change an existing field. So the three defaulted fields are declared **after
   `raw`**. `from_dict` constructs by keyword, so body order is purely structural —
   no behavioural effect.

4. **Collision guard placed BEFORE the `try/except` block — key architectural
   decision.** `write_daily_snapshot` builds `meta`, then does
   `if fragility: meta.update(fragility)`. If a `fragility` dict ever carried a key
   named `key_signals` / `opportunity_posture` / `confidence` it would **silently
   overwrite** the macro-regime value — a data-corruption bug. A guard rejects this:

   ```python
   _PROTECTED_META_KEYS = {"key_signals", "opportunity_posture", "confidence"}
   if fragility:
       _collision = _PROTECTED_META_KEYS & set(fragility.keys())
       if _collision:
           raise ValueError(
               f"write_daily_snapshot: fragility dict contains keys that would "
               f"overwrite protected _meta fields: {sorted(_collision)}")
   ```

   **Critically, the guard sits BEFORE the function's broad
   `try/except Exception: return ""`.** The function is best-effort / fail-closed for
   I/O — any exception inside the `try` is swallowed into a `""` return. A guard
   placed *inside* the `try` (at the literal `meta.update` site) would be swallowed,
   silently returning `""` instead of failing loudly — defeating the purpose. Placed
   as a **precondition before the `try`**, the `ValueError` propagates to the caller
   (a caller programming error should be loud), while genuine best-effort I/O failures
   stay fail-closed. This is the single most important correctness decision in the
   phase and the subject of the second Codex pass. `fragility_snapshot` never carries
   these keys today, so the guard is a forward-looking invariant, not a live path.

---

## Tests — `scripts/test_reliability_phase_7b_rotation_internals.py`

7 new checks (suite total **226/226**):

| Check | What it proves |
|-------|----------------|
| `18.24` | **Live-path**: the REAL `_run_refresh` (driven via AppTest, network mocked) threads all three fields into the persisted `_meta`, equal to the seeded regime. Presence proves the call-site wiring (a dropped wire ⇒ key ABSENT, not defaulted). |
| `§18-meta-new-1/2/3` | Direct-drive with **non-empty** values: `_meta["key_signals"/"opportunity_posture"/"confidence"]` equal the values passed to `write_daily_snapshot`. Strong value discrimination. |
| `§18-meta-new-4` | `MetaRecord.from_dict(written_meta)` round-trips all three onto `.key_signals` / `.opportunity_posture` / `.confidence`. |
| `§18-meta-new-5` | **Old-snapshot simulation**: a `_meta` dict with the three keys *stripped from a real written header* parses cleanly with defaults `[] / "" / ""` (asserts genuine absence before parsing — the fixture cannot misrepresent production shape). |
| `§18-meta-new-6` | **Collision guard**: `write_daily_snapshot(..., fragility={..., "confidence": "high"})` raises `ValueError` whose message names the colliding key. |

- **Mutation probe** on `§18-meta-new-1`: temporarily writing a wrong `key_signals`
  value turned `new-1` AND `new-4` RED (223/225 at the time) → confirmed
  discriminating; reverted to green.
- The `§18` structural completeness check (`FIELD_RENDER ∪ EXCLUSIONS == _SNAP_KEYS`)
  is **untouched** — it is scoped to fragility-snapshot keys, and the three new
  fields are not fragility fields, so no `FIELD_RENDER` / `EXCLUSIONS` entry is
  needed.

**Regression:** 7b **226/226** · 7a **115/115** · 7d **10/10** · anchor_archive
**77/77**. No consumer of `MetaRecord` (Audit Review page 11, `macro_regime_agent`'s
`load_all_meta` history walk) is affected — the additive fields default cleanly.

---

## Codex review history

- **Pass 1 (meta-extension):** reviewed the three lib/page changes + the five tests.
  0 findings.
- **Pass 2 (collision guard):** reviewed the pre-`try` guard placement and
  `§18-meta-new-6`. Confirmed the guard propagates (is not swallowed) and the test is
  discriminating. 0 findings.

**Total: 2 passes, 0 findings, APPROVED.**

---

## Determinism note

The change preserves deterministic computation. The three persisted values are
rule-based `classify_regime` outputs — no LLM inference, no invented numbers. The
snapshot remains a faithful, replayable audit record; `MetaRecord` continues to use
`.get()`-defaulted parsing tolerant of additive schema drift across the file history.

---

**Feature commit:** `7a76bcb3` · **Merge:** `ffe9e1e2` (`--no-ff`, pushed)
