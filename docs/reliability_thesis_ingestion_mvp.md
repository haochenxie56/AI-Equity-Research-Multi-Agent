# Thesis Ingestion MVP — Phase Document

**Status:** CLOSED — Codex-approved (two review rounds), committed direct to `main`.
**Closed:** 2026-06-14.
**Approved commits:** `3d1cbd5` (R2 final fix) · `fb80f78` (R1 fixes) · `72fa870` (fix
round) · `ac29fa6` → `20c7fd4` (initial implementation).
**Reliability suite:** `scripts/test_reliability_thesis_ingestion.py` — 71 tests, 0
failures.

> Research/educational use only. Not investment advice.

---

## 1. Phase summary

The Thesis Ingestion MVP adds a **thesis-card library**: a place to manually curate
external research (analyst reports, interviews, articles) and turn each distinct,
independently-falsifiable argument into a structured, machine-readable **thesis card**
via **one LLM call per argument**. Cards are validated deterministically, stored as local
JSON, and browsed/managed through a new Streamlit page (`pages/10_Thesis_Library.py`),
with jump-in buttons from the Investment Cockpit.

**Why.** The live system computes signals, rankings, valuations and snapshots
deterministically. It had no place to capture the *qualitative external theses* a human
curates — the "why" behind a theme or name, with explicit confirmation / falsification
conditions. This feature is the human-curated, machine-structured counterpart to the
deterministic pipeline. It is deliberately **inert** in the MVP: a knowledge base only,
with **zero interaction** with scoring / ranking / snapshot / anchor systems.

**Division of labour (the project's core principle).** Code owns IDs, hashing, schema
invariants, staleness/active math, validation and storage. The LLM only *interprets* the
author's text into structured fields — it never computes, estimates, or fabricates a
number, and never sets an invariant field. The **validator is the enforcement point** for
extraction honesty.

**Package / files.**

| File | Role |
|------|------|
| `lib/thesis_ingestion/schema.py` | `ThesisCard` / `ScenarioCard` TypedDicts + deterministic builders + invariant constants |
| `lib/thesis_ingestion/store.py` | atomic card read/write, append-only `ingest_log.jsonl`, dedup-by-hash, status mgmt, `scan_unavailable`, read-time staleness / `is_active`; configurable library root |
| `lib/thesis_ingestion/extractor.py` | `preview_article` + per-argument `extract_card`; txt/md/pdf/docx reading; theme-name injection; deterministic assembly of IDs/invariants/meta |
| `lib/thesis_ingestion/validator.py` | deterministic post-extraction validation (no short-circuit) |
| `pages/10_Thesis_Library.py` | Library + Ingest UI (bilingual via `bi()`) |
| `pages/7_Investment_Cockpit.py` | three additive `st.page_link` jump buttons |
| `scripts/test_reliability_thesis_ingestion.py` | reliability suite (71 tests) |

---

## 2. Schema definitions (field names + types)

### ThesisCard

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | str | `"thesis-1.0"` |
| `card_id` | str | `doc_hash[:16] + "-" + extraction_seq` |
| `source` | dict | see below |
| `horizon_type` | str | `short` / `mid` / `long` — set by user, not LLM |
| `coi` | dict | `{status, notes}`; status `coi_unassessed` \| `coi_disclosed` |
| `card_status` | str | `active` / `silenced` / `unavailable` |
| `core_claims` | list[dict] | `claim_id, claim_text_en, claim_text_zh, claim_type, related_tickers, related_themes` |
| `numeric_claims` | list[dict] | `metric, value(float), unit, applies_to, time_reference, provenance, source_quote` |
| `unspecified_numerics` | list[dict] | `metric, direction, note` — **never a `value` key** |
| `assumptions` | list[str] | verbatim author text (single-language) |
| `scenarios` | list[ScenarioCard] | sparse fill allowed |
| `extraction_meta` | dict | `llm_model, prompt_version("thesis-extract-v1"), extracted_at, extraction_seq` |

`source`: `doc_hash`(sha256 hex, 64), `doc_path`, `doc_type`
(interview/research_report/article/transcript/other), `title`, `author`,
`author_affiliation`, `publication_date`(`YYYY-MM-DD`|null),
`publication_date_provenance`, `language`(zh/en/mixed), `ingested_at`(ISO).

### ScenarioCard

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | str | `"scenario-1.0"` |
| `scenario_id` | str | sha256(first 16) of normalised event + chain |
| `event_or_hypothesis_en` / `event_or_hypothesis_zh` | str | bilingual (legacy bare `event_or_hypothesis` accepted) |
| `transmission_chain` | list[dict] | `step, from_node, to_node, mechanism_en, mechanism_zh, provenance` |
| `affected_horizons` | list[str] | subset of short/mid/long |
| `affected_themes` | list[str] | from `theme_baskets` names |
| `unmapped_themes` | list[str] | author themes not in baskets |
| `affected_tickers` | list[str] | uppercase tickers |
| `confirmation_conditions` / `falsification_conditions` | list[dict] | `condition_text_en, condition_text_zh, observable, provenance` |
| `current_evidence_status` | str | **always `"unknown"`** |
| `evidence_refs` | list | **always `[]`** |
| `notes_en` / `notes_zh` | str | bilingual (legacy bare `notes` accepted) |

`provenance` ∈ {`stated_by_author`, `inferred`}; `observable` ∈ {`machine_checkable`,
`human_judgment`, `unspecified`}.

---

## 3. Key design decisions

- **Bilingual field classification.** Only *descriptive, UI-facing* prose is bilingual
  (`_en`/`_zh`, rendered with `bi()`): `claim_text`, `mechanism`, `condition_text`,
  `event_or_hypothesis`, scenario `notes`. *Verbatim author text* stays single-language —
  translating it would corrupt the evidence: `source_quote` (numeric_claims), `note`
  (unspecified_numerics), and `assumptions`. Legacy bare keys remain accepted for
  backward compatibility (validator/`bi()` both fall back en → zh → bare).
- **Validator is the enforcement point** for numeric fabrication. The extractor passes the
  LLM's `unspecified_numerics` through untouched; if a `value` key leaks in, the validator
  rejects the card **visibly** (`extraction_rejected_fabricated_numeric`) rather than the
  assembler silently stripping it. Scenario invariants (`current_evidence_status`,
  `evidence_refs`) ARE force-corrected by the extractor — but with a **logged warning** so
  a misbehaving model is observable, never silently corrected.
- **Two-step overwrite.** Saving never silently overwrites. A `CardExistsError` sets a
  pending flag and surfaces a separate **Confirm Overwrite** button — overwrite always
  requires two explicit user actions. (The upload-stage dedup-by-hash gate is the first
  line; this guards the save itself.)
- **Staleness tiers (read-time, never stored).** short: fresh ≤30d, expired >30d. mid:
  fresh ≤90d, aging 91–180d (warning), expired >180d. long: always `not_applicable`. Null
  `publication_date`: `not_applicable` for all horizons.
- **Active logic by horizon.** silenced/unavailable → inactive. Null date (short/mid) →
  active (never deactivate solely for an unknown date). short → active iff `fresh`. mid →
  active iff not `expired` (logic-falsification is always False in the MVP). long → always
  active.
- **Deterministic IDs / invariants.** `doc_hash` = sha256 of raw bytes (dedup key);
  `card_id` = `doc_hash[:16]-seq`; `scenario_id` = sha256 of normalised event+chain. All
  set by code, never by the model.
- **Configurable library root.** `store.set_library_root()` + `THESIS_LIBRARY_ROOT` env
  let the suite redirect all I/O into a temp dir — no public signature changed, no `data/`
  writes in tests.
- **Soft document parsing.** pdf via `pdfplumber`, docx via `python-docx` *if installed*,
  else raw-text fallback. No new dependency added (neither is in `requirements.txt`).

---

## 4. Access-path matrix

The MVP is additive and isolated; the matrix below records every path that touches the
feature and what each is allowed to do.

| Caller / path | LLM | Network | File I/O | Notes |
|---------------|-----|---------|----------|-------|
| `pages/10` Ingest → `preview_article` / `extract_card` | yes (1 call/arg) | Anthropic only | reads upload bytes; writes backup copy | user-initiated |
| `pages/10` Ingest → `save_card` / `append_ingest_log` | no | no | writes `cards/*.json`, `ingest_log.jsonl` | atomic; two-step overwrite |
| `pages/10` Library → `list_cards` / `compute_staleness` / `compute_is_active` / `scan_unavailable` / `update_card_status` / `delete_card` | no | no | read cards; status writes on action | deterministic |
| `validator.validate_card` | no | no | no | pure |
| `pages/7` Cockpit jump buttons (`st.page_link`) | no | no | no | navigation only; no import of the feature |
| `opportunity_ranker` / `signal_engine` / `candidate_generator` / `market_internals` | — | — | — | **never import the feature** (asserted by tests) |

Invariant: the ranking / snapshot / refresh paths reach **none** of this code, and the
feature reaches none of theirs. `save_card` leaves `data/snapshots` and
`data/anchor_cache.json` byte-identical (asserted).

> Note: unlike the Anchor-Intelligence phases, this feature did not require a formal
> pre-coded STEP 0 producer matrix (it is a brand-new isolated surface, not a
> producer-unification). The matrix above documents the access paths as built.

---

## 5. Codex review history

**Round 1 (5 findings, all resolved in `fb80f78`; the validator-enforcement finding was
pre-addressed in `72fa870`):**

1. **C1 — English-only prompts.** Chinese inline example strings in `_PREVIEW_SYSTEM`
   replaced with English descriptions.
2. **C2 + F2 — bilingual field classification.** `_en`/`_zh` added for `mechanism`,
   `condition_text`, `event_or_hypothesis`, scenario `notes`; `source_quote` / `note` /
   `assumptions` confirmed single-language verbatim; schema, prompt, validator and page
   updated; `bi()` rendering wired.
3. **Validator as enforcement point (`72fa870`).** Removed the silent strip of a leaked
   `value` from `unspecified_numerics`; the validator now rejects it visibly.
4. **C5 — evidence_refs warn guard.** Scenario invariant overwrite now logs a warning
   before correcting.
5. **F4 — explicit overwrite.** `CardExistsError` no longer silently retries; a separate
   Confirm Overwrite action is required.

**Round 2 (1 finding, resolved in `3d1cbd5`):** the evidence_refs warning condition
`ev is not None and ev != []` short-circuited on `None`. Changed to `ev != []` so the
warning fires for `None`, `""`, `{}`, `0` and any non-`[]` value.

---

## 6. Test suite summary

`scripts/test_reliability_thesis_ingestion.py` — **71 tests, 0 failures** (stdlib
`unittest`; no network; temp library root; no `data/` writes). Four groups:

1. **Schema & validation** — valid card passes; each invalid field maps to its error
   code; evidence-status/refs tamper; missing/null provenance; fabricated
   `unspecified_numerics` `value`; bilingual mechanism/condition presence + legacy-bare
   backward-compat; multi-error no-short-circuit.
2. **Staleness & active** — short/mid/long boundaries, aging-warning flag, null-date
   `not_applicable`, silenced/unavailable/expired inactivity.
3. **Storage isolation** — round-trip, overwrite gate, ingest-log parse, dedup-by-hash
   most-recent, delete, `scan_unavailable`, status update, config.
4. **Isolation invariants** — `opportunity_ranker` / `signal_engine` /
   `candidate_generator` / `market_internals` carry no thesis attr/submodule/import;
   `save_card` leaves `data/snapshots` & `data/anchor_cache.json` byte-identical.

**Mutation probes (discrimination confirmed during development):** flipping the validator
checks turns the corresponding Group-1 tests red; a value-bearing `unspecified_numerics`
now reaches the validator (no silent strip) and trips
`extraction_rejected_fabricated_numeric`; a card present in both Stock and Theme tabs
surfaced a duplicate-widget-key bug (fixed by tab-scoping keys), caught via AppTest.

---

## 7. What this unlocks

- **Phase 7C (theme beneficiary layers)** can read thesis cards keyed by theme/ticker to
  enrich beneficiary reasoning with curated external arguments (read-only consumption;
  the isolation invariant means 7C imports the library, never the reverse).
- **Phase 8 (debate layer)** gains a structured card library to draw bull/bear material
  from — each card already carries transmission chains and confirmation / falsification
  conditions.
- **Phase 9 (Judgment Console)** has a structured judgment object to update over time:
  `current_evidence_status` and `evidence_refs` are reserved (always `unknown` / `[]` in
  the MVP) precisely so a future human-in-the-loop console can advance a thesis's
  evidence state without schema churn.
