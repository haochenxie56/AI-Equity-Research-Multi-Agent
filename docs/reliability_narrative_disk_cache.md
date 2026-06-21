# Step 3 — Narrative Disk Cache

**Status:** COMPLETE — Codex APPROVED (three review passes).
**Merged:** `main` @ `a2e43cd3` (feature commit `083e8535`), 2026-06-21, pushed.
**Scope:** `lib/signal_engine.py`, `.gitignore`, `scripts/test_narrative_disk_cache.py`.

---

## 1. Objective & motivation

`llm_narrative_match` (Layer 2 of the Phase 6B dual-track signal engine) is the
**only** LLM call in `lib/signal_engine.py`. It judges a ticker's narrative stage
+ catalyst from the last 30 days of Finnhub company news, one Claude call per
top-N candidate. It is memoized with `@st.cache_data(ttl=3600)` keyed on
`(ticker, macro_regime)`.

That in-memory cache is the hot path, but it dies with the process. During
iterative development the Streamlit server restarts constantly, and every restart
re-pays the full Layer-2 LLM cost — on the order of ~50 Claude calls to re-warm a
single scan universe, even when neither the news nor the regime has changed.

**Goal:** add a disk-backed persistence layer *underneath* the in-memory layer so
LLM narrative results survive process restarts. A cold start with unchanged inputs
should serve from disk and skip the LLM entirely, dropping restart cost from ~50
calls to near-zero.

**Non-goals / hard constraints:** the in-memory `@st.cache_data` layer stays the
hot path and is left completely untouched; the function signature does not change;
the disk layer is acceleration-only and must **never** block or alter the result
of a normal refresh.

---

## 2. Design decisions

### 2.1 Cache key — `(ticker, macro_regime, news_fingerprint)`

Disk layout mirrors the per-ticker sharding used elsewhere in the project:

```
data/narrative_cache/<TICKER>/<macro_regime>_<news_fingerprint>.json
```

- `<TICKER>` — upper-cased.
- `<macro_regime>` — sanitized for the filename by `_sanitize_regime`: spaces,
  `/`, and `\` → `_`, then lowercased. (`macro_regime` is already part of the
  in-memory key, so it must be part of the disk key too — the same news under a
  different regime is a different judgment.)
- `<news_fingerprint>` — first 8 hex chars of the md5 over the exact prompt-fed
  news content (§2.2).

Both the regime and the fingerprint are encoded in the **filename**, so the read
builds the exact path and checks existence — a changed regime or changed news
naturally lands on a different path. The entry JSON also stores `news_fingerprint`
and the read re-checks it (defense-in-depth against a forged/corrupt file at the
expected path).

### 2.2 Fingerprint design — exact alignment with the LLM prompt

The fingerprint must change **iff** the content the LLM actually sees changes —
*nothing more, nothing less*. The Layer-2 prompt builder consumes:

```python
for item in news[:25]:
    head = (item.get("headline") or "").strip()
    summ = (item.get("summary") or "").strip()
    line = head if not summ else f"{head} — {summ[:160]}"
```

`_news_fingerprint` mirrors this verbatim: the **`news[:25]` slice**, each item's
`.strip()`-ed **`headline`** plus **`summary` truncated to `[:160]`**, each record
serialized with `json.dumps([head, summ], ensure_ascii=False)`, records joined
with `"\n"`, md5, first 8 hex.

Consequences (all test-locked):
- A **summary edit within** the prompt window changes the key (no stale hit).
- A summary edit **past char 160** does *not* change the key (the prompt never
  sees it → an unnecessary miss would be wrong).
- A change to an item **past index 25** does *not* change the key (outside the
  slice).
- **Collision-resistant** against `|`, `\n`, brackets, and quotes appearing inside
  a headline or summary — `json.dumps` of a two-element list escapes those, so no
  field-boundary or record-boundary ambiguity is possible regardless of content.

### 2.3 TTL — 24h, expiry-as-miss

`NARRATIVE_CACHE_TTL_HOURS = 24`. An entry is valid iff
`datetime.utcnow() - cached_at < timedelta(hours=24)`. An expired entry is
treated as a **miss** (re-call the LLM, rewrite a fresh entry), never an error.
`utcnow()` is used on both the write (`cached_at = datetime.utcnow().isoformat()`)
and the read for UTC consistency.

### 2.4 Atomic write — temp + `os.replace`

`_write_narrative_cache` creates the parent dirs (`mkdir(parents=True,
exist_ok=True)`), writes the JSON to a sibling `*.tmp` file, then `os.replace`s it
into place. A reader can therefore never observe a half-written file.

### 2.5 Fail-closed discipline

Every disk operation — path build, `exists`, `open`, `json.load`,
`fromisoformat`, `NarrativeResult(**result)` reconstruction, `mkdir`,
`json.dump`, `os.replace` — is wrapped in `try/except Exception`. Any failure
(missing file, corrupt JSON, permission error, write error) is **silently
swallowed**: the read returns `None` (a miss → fall through to the live LLM
call), and the write is a no-op. No `st.warning` / `st.error` / `st.info`, no
`raise`. The cache is an acceleration layer only; it can never change or block the
result of a normal refresh.

### 2.6 Neutral-results-not-written rule

The disk read is wired in **before** the `_has_llm_api_key()` gate, so a fresh
fingerprint-matched hit is served even when no API key is present. The atomic
write happens **only** on the successful live path, after a real Claude call
produces a `data_source="live"` result. Neutral fallbacks (`neutral_narrative()`
— no news, no key, parse failure) are **never persisted**, so a transient outage
can't poison the cache with empty judgments.

### 2.7 Untouched surfaces

The `@st.cache_data(ttl=_LLM_CACHE_TTL, show_spinner=False)` decorator and the
`llm_narrative_match(ticker, macro_regime)` signature are unchanged. No new public
function/class is added (five private helpers + two module constants only).
`lib/candidate_generator.py` and every other file are untouched. `.gitignore`
gains an explicit `data/narrative_cache/` line (already covered by the broader
`data/` rule; added for clarity).

---

## 3. Codex review history (3 passes)

| Pass | Outcome | Findings → fixes |
|------|---------|------------------|
| **1 — initial review** | Changes requested (2) | **F1** `_news_fingerprint` concatenated headlines with no separator → boundary collision (`["ab","c"]` vs `["a","bc"]`). **F2** fingerprint scope misaligned with the prompt: it covered *all* fetched headlines only, while the prompt consumes `news[:25]` with **both** headline and summary → a summary change could give a stale hit, and a change past item 25 an unnecessary miss. Fix: slice to `news[:25]`, include `headline` + `summary[:160]`, join with `"\n"`. |
| **2 — fix round** | Changes requested (1) | **F3** the `f"{head}|{summ}"` record format was still ambiguous when a field contained a literal `"|"` (`headline="a|b", summary="c"` vs `headline="a", summary="b|c"` both hashed `"a|b|c"`). Fix: serialize each record with `json.dumps([head, summ], ensure_ascii=False)` — brackets/quotes/commas inside the strings are escaped, so no content can cause a field-boundary collision. |
| **3 — re-review** | **APPROVED** | Clean. |

Each fix round added a discriminating regression assertion (§NC-8a–8e in round 1,
§NC-8f in round 2) so the specific collision/scope bug cannot silently return.

---

## 4. Tests & regression

### `scripts/test_narrative_disk_cache.py` — 27/27

All network and LLM calls mocked (`fetch_company_news`, `_has_llm_api_key`,
`llm_orchestrator._get_client` / `_llm_json_call`); the cache dir is redirected to
a throwaway temp dir via the module global `NARRATIVE_CACHE_DIR`; the in-memory
`@st.cache_data` layer is cleared before each driven call so the disk layer is
genuinely exercised.

- **§NC-1** miss → LLM called once → result written to disk (schema verified).
- **§NC-2** fresh, fingerprint-matched hit → LLM **not** called, cached result
  returned.
- **§NC-3** TTL expired (>24h) → treated as a miss → LLM called → fresh entry
  rewritten.
- **§NC-4** fingerprint mismatch → miss: (a) corrupted internal fingerprint at the
  same path, (b) genuinely changed news → different fingerprint → different path.
- **§NC-5** corrupt JSON read → silent fallthrough to the LLM (no exception),
  correct result still returned, corrupt file overwritten with a valid entry.
- **§NC-6** disk write failure (`os.replace` → `PermissionError`) → silently
  swallowed, correct result still returned, no final cache file left.
- **§NC-7** mutation probe: a distinctive cached sentinel is returned on a hit
  while the LLM mock would return a *different* value — proves the cache bypasses
  the LLM rather than coincidentally matching it.
- **§NC-8a–8f** fingerprint collision/scope: record separator, field separator,
  summary-in-key, past-slice no-op, past-160 no-op, literal-`|` no-collision.

### Regression (no change)

- `scripts/test_reliability_phase_6b_v3_horizon_scoring.py` — **189/189**.
- `scripts/test_reliability_phase_6b_v2_dual_track.py` — **217/217**.

Run via the project convention (WSL, system python3):

```bash
python3 -B scripts/test_narrative_disk_cache.py
```

---

## 5. Commit / merge record

- Feature commit: `083e8535` — `feat: Step 3 narrative disk cache — disk-backed
  persistence for llm_narrative_match`.
- Merge commit: **`a2e43cd3`** — `--no-ff` merge of
  `feature/narrative-disk-cache` into `main`, pushed to origin; feature branch
  retired (local deleted; never existed on remote).
- Files: `lib/signal_engine.py` (+constants, +5 helpers, +read/write wiring),
  `.gitignore` (+`data/narrative_cache/`), `scripts/test_narrative_disk_cache.py`
  (new, 27 checks).
