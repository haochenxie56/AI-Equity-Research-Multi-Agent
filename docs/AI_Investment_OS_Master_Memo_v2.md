# AI Investment OS — Master Architecture, Roadmap, and Project Memory Memo

**Version:** Master Memo v2 (updated 2026-06-17)
**Generated:** 2026-06-15 (updated 2026-06-17)
**Purpose:** Cross-session migration, architecture preservation, roadmap alignment, and phase-planning baseline.
**Scope:** Consolidates completed work through Phase 7C Theme Transmission Mapping. Supersedes Master Memo v2 (2026-06-15).
**Status convention:** `README.md` and `ROADMAP.md` are treated as the current authoritative sources. This memo is P1 context — it explains and records, but yields to live docs on any conflict.

> **Disclaimer:** This project is a research and decision-support system. It does not provide investment advice, does not place orders, and must remain review-only unless a future phase explicitly changes the scope under separate safety review.

---

## 0. How to Use This Memo

This memo solves the project's recurring context-drift problem. It is usable as:

1. **A new-session startup context** for Claude / Claude Code / Codex.
2. **A project architecture map** for understanding the live product path, reliability stack, data flows, UI surfaces, and persistence.
3. **A roadmap memory source** for why each phase existed, what problem it solved, and what it must not be confused with.
4. **A design-principle guardrail document** to prevent future phases from weakening review-only safety, evidence discipline, data-vintage discipline, or auditability.
5. **A portfolio / resume narrative source** for describing the project as an AI investment decision-support system rather than a generic stock picker.

### 0.1 Source Authority Rules

| Priority | Source | How to Use |
|---|---|---|
| P0 | Latest `README.md` | Current product definition, feature inventory, architecture, safety principles, technical stack. |
| P0 | Latest `ROADMAP.md` | Current roadmap, collaboration discipline, completed state snapshot, current next phase, future phase ledger. |
| P1 | This memo (v2) | Cross-session context, design rationale, phase history, anti-drift guardrails. Yields to P0 on any conflict. |
| P2 | Codex architecture audit report | Independent repository-level reality check. |
| P3 | Historical roadmap PDFs, phase backup files, README(v3) | Historical evolution only. Do not override current README/ROADMAP. |

### 0.2 Important Supersession Rules

Older documents that say "Phase 6 not started," "fixture-only," "demo-only," or "Phase 5S awaiting review" are historical. Current truth:

- Phase 6A–6C, 7A–7B, Valuation Refactor v1, Anchor Intelligence v2–v2.5: all closed and merged.
- Thesis Ingestion MVP: closed and merged (main @ b323c09).
- Latest baseline: `main @ 79433d5` (Phase 7C merge, June 2026).
- Legacy Red Suite Archival: closed (`4f39838` + `8e6f891`).
- Phase 7C Theme Transmission Mapping: closed (`bbdf5b0` + `32c0f5e`,
  merged `79433d5`).

This memo (v2) supersedes v1 (dated 2026-06-12, baseline 372dd25). Any statement in v1 that contradicts v2 should be treated as stale.

---

## 1. One-Sentence Project Definition

**AI Investment OS is a personal US-equity investment operating system that evolved from a five-step GenAI-assisted research workflow into a review-only decision-support stack combining deterministic market/valuation/technical computation, horizon-aware opportunity ranking, market-internals fragility monitoring, type-routed valuation anchors, thesis monitoring, a structured external research card library, and local audit trails inside an Investment Cockpit.**

The project is not merely a "stock picker." The real problem it solves is automating as much of the personal investment research workflow as possible while keeping final judgment and execution under human control.

---

## 2. Product Philosophy

### 2.1 Core Thesis

> **Deterministic computation for facts and numbers; evidence-constrained LLM judgment for interpretation; explicit human confirmation for decisions; append-only audit trails for accountability.**

The corrected boundary:

- **Numerical/Quantitative side:** always deterministic code.
- **Judgment/Qualitative side:** LLM may propose evidence-bound judgments, but only with explicit evidence references, `unknown` when unsupported, and human confirmation before the judgment becomes authoritative.

### 2.2 Review-Only by Design

The system must remain review-only:

- no broker execution; no order submission; no broker payload; no account ID; no quantity-to-execute field; no time-in-force execution field.
- `approved_for_execution` must be false or absent.
- Outputs are research queues, opportunity cards, trade-plan drafts, risk overlays, thesis reviews, and monitoring prompts — not execution instructions.

### 2.3 Opportunity-First Instead of Ticker-First

Correct flow:
```
Macro regime → Theme heat / market leadership → Value-chain layer / subtheme
→ Candidate universe → Horizon-specific opportunity queue
→ Research snapshot → Evidence / debate / thesis / trade plan → Human review
```

Incorrect flow: User manually chooses ticker → System displays another company research page.

### 2.4 Horizon-Aware by Default

The same ticker may have different conclusions across horizons. A stock can be a long-term compounder but a bad short-term entry. Short / mid / long horizon scores and statuses exist independently.

### 2.5 Not an Autonomous Agent Runtime Yet

The live product path and the reliability/evidence stack are selectively integrated, not yet a single mandatory runtime. This is a known architectural reality, not a flaw to hide.

---

## 3. Current System Architecture

### 3.1 High-Level Architecture

```
User
 ↓
Streamlit UI
 ├─ Overview / Legacy AI Workflow
 ├─ Sector / Rotation Workbench
 ├─ Scanner / Candidate Generation
 ├─ Equity / Company Research
 ├─ Financial / Statements + Valuation
 ├─ PriceVolume / Technicals
 ├─ Investment Cockpit / Opportunity Ranking
 ├─ Macro Dashboard / Regime + Internals
 ├─ Trading Desk / Entry + Thesis Monitor
 └─ Thesis Library / Research Card Library  ← NEW (Thesis Ingestion MVP)

Live Product Path
 ├─ macro_data / macro_regime
 ├─ market_internals
 ├─ theme_baskets
 ├─ rotation
 ├─ candidate_generator
 ├─ signal_engine
 ├─ opportunity_ranker
 ├─ relative_strength
 ├─ order_advisor
 ├─ thesis_monitor
 ├─ equity_valuation / valuation_router / valuation_diagnosis
 ├─ anchor_cache / anchor_archive / anchor_migration / anchor_backfill
 ├─ holdings / workflow_state / cache_manager
 └─ thesis_ingestion/  ← NEW (schema / store / extractor / validator)
 └─ theme_transmission  ← NEW (Phase 7C: transmission order + role seed map)

Reliability / Audit Stack
 ├─ ToolResult / AgentResult / EvidenceRef / DataSnapshot
 ├─ validators / staleness / critic
 ├─ horizon_synthesis / debate / decision_packet
 ├─ human_review / review_loop
 ├─ memory schemas
 └─ evaluation fixtures

Local Persistence
 ├─ data/snapshots/*.jsonl
 ├─ data/anchor_cache.json
 ├─ data/anchor_archive/<TICKER>.jsonl
 ├─ data/holdings.json
 ├─ data/thesis_library/cards/<card_id>.json  ← NEW
 ├─ data/thesis_library/ingest_log.jsonl      ← NEW
 ├─ local Parquet cache
 └─ research/.workflow_state.json
```

### 3.2 Current User-Facing Pages

**Decision Layer:**

| Page | Role | Status |
|---|---|---|
| `7_Investment_Cockpit.py` | Main entry. Macro regime, internals, theme rotation, opportunity ranking. Contextual thesis card jump buttons on theme and signal cards. | Live |
| `8_Macro_Dashboard.py` | Macro regime + Market Internals workbench. | Live |
| `9_Trading_Desk.py` | Entry strategy v4, order narrative, thesis monitor. Review-only. | Live |
| `2_Sector.py` | Rotation workbench: GICS outer ring + AI theme inner ring. | Live |

**Research Layer:**

| Page | Role |
|---|---|
| `10_Thesis_Library.py` | Research card library. Ingest mode + Library mode. Per-category tabs (宏观/行业/主题/个股). Context-aware jump target from Cockpit. **NEW** |
| `1_Overview.py` | Legacy five-step AI workflow. |
| `3_Scanner.py` | Four-strategy scan + AI cross-strategy evaluation. |
| `4_Equity.py` | Company research, moat, peers, valuation summary, diagnostic cards. |
| `5_Financial.py` | Statements, DCF, relative valuation. |
| `6_PriceVolume.py` | Candlestick + technical indicators + support/resistance. |

---

## 4. Design Principles and Non-Negotiable Invariants

### 4.1 Numerical Firewall

LLM must not invent: valuation numbers, technical indicators, market data, scores, price targets, probabilities, hidden thresholds, fabricated analyst consensus. All numeric facts from deterministic code or explicit source extraction.

### 4.2 Evidence-Constrained Judgment

LLM may suggest judgment only when: (1) judgment cites evidence, (2) unsupported fields marked `unknown`, (3) user can explicitly accept/reject/overwrite, (4) judgment provenance is recorded.

### 4.3 Exclude, Do Not Down-Weight

When an anchor is untrustworthy, exclude it and label why. No continuous weighting knobs that hide uncertainty.

### 4.4 Never Fabricate Numbers

Historical backfill only recomputes anchors computable from available data under filing-lag rules. Analyst anchors are never invented for historical dates. **Thesis extraction: if the author did not state a number, the field goes into `unspecified_numerics` with `direction` only — no proxy value is invented.**

### 4.5 Filing-Lag Look-Ahead Defense

Historical anchor recomputation must apply disclosure lag: annual reports `period_end + 75 days`; quarterly reports `period_end + 45 days`.

### 4.6 Access-Path-Matrix First

Before unifying a producer or refactoring a data path, define the caller-contract matrix (who needs network, who needs historical range, who can write cache, who can touch snapshots).

### 4.7 Append-Only Audit Trail

Do not rewrite old snapshots or anchor archive lines. If correction is needed, append a new record with provenance. **Thesis card library: cards are write-once; re-extraction overwrites after explicit confirmation only; ingest_log is append-only.**

### 4.8 Tighten-Only Market Internals

Market internals / fragility can annotate, tighten short-term entry, warn. It cannot flip macro regime, loosen entry conditions, override deterministic scoring, or authorize buying.

### 4.9 Degradation Vocabulary

Unavailable data must produce explicit degradation labels: `finnhub_unavailable`, `no_reports_in_window`, `partial_frame_coverage`, `implausible_count`, `fixture`, `rs_stale`, `vintage_mismatch`, `extraction_rejected_missing_provenance`, `extraction_rejected_fabricated_numeric`. No component should disappear silently.

### 4.10 Thesis Ingestion Boundary (New)

The thesis card library must not interact with the ranking, scoring, or snapshot systems. Specifically:

- `opportunity_ranker`, `signal_engine`, `candidate_generator`, `market_internals`, `macro_regime`, `anchor_cache`, `anchor_archive`, and all snapshot writers must never import `thesis_ingestion`.
- Ingestion is the only LLM face in the feature. All downstream use of cards is read-only and deterministic.
- `current_evidence_status` on scenario cards is always `"unknown"` in MVP — no code path may write another value. This field is reserved for Phase 9.

---

## 5. Thesis Ingestion MVP — Completed Architecture

This section records the design decisions made during implementation, as a reference for future phases that will consume the card library.

### 5.1 What It Is

Manually curated external research articles / interviews → one LLM extraction → local JSON structured thesis cards → browsable / filterable card library.

MVP is zero-consumer. It builds the library. No automatic downstream consumption.

### 5.2 What It Is Not

- Not a holding monitor (that is Phase 6D).
- Not a ranking input (ranking knows nothing about the library).
- Not a RAG / vector database.
- Not a macro hypothesis auto-tracker.
- Not an automatic news scraper.

### 5.3 Ingestion Pipeline

```
User selects article (manual curation)
 ↓
Upload file → LLM lightweight preview (list of distinct arguments)
 ↓
User selects which arguments to extract and sets horizon_type per argument
 ↓
One LLM extraction call per argument → deterministic code validates
 ↓
User reviews draft card → confirms → card saved to data/thesis_library/cards/
```

Supported formats: PDF (`pdfplumber`), DOCX (`python-docx`), PPTX (`python-pptx`), TXT, MD. Image formats not supported.

### 5.4 ThesisCard Schema (v1.0)

Key fields:

- `card_id`: `doc_hash[:16] + "-" + extraction_seq`
- `source.doc_hash`: sha256 of file bytes — deduplication key
- `source.doc_path`: path to local backup copy
- `horizon_type`: `"short" | "mid" | "long"` — set by user, not LLM
- `coi.status`: always `"coi_unassessed"` at extraction time
- `card_status`: `"active" | "silenced" | "unavailable"`
- `core_claims[]`: `claim_text_en`, `claim_text_zh`, `claim_type`, `related_tickers`, `related_themes`
- `numeric_claims[]`: `metric`, `value`, `unit` (free-form string), `provenance` (`"stated_by_author" | "inferred"`), `source_quote`
- `unspecified_numerics[]`: `metric`, `direction`, `note` — no `value` field ever
- `scenarios[]`: embedded ScenarioCard (sparse fill allowed)
- `extraction_meta`: `llm_model`, `prompt_version`, `extracted_at`, `extraction_seq`

Bilingual: all prose fields use `field_en` / `field_zh` parallel keys, rendered via `bi()`. Verbatim author text (`source_quote`, `note`, `assumptions`) stays in source language.

### 5.5 ScenarioCard Schema (v1.0, shared)

Shared structure for thesis cards, future macro event interpretations, and Phase 8 debate invalidation conditions:

- `event_or_hypothesis_en` / `event_or_hypothesis_zh`
- `transmission_chain[]`: `step`, `from_node`, `to_node`, `mechanism_en`, `mechanism_zh`, `provenance`
- `affected_horizons[]`: `"short" | "mid" | "long"` only
- `affected_themes[]`: must come from existing `theme_baskets` names
- `unmapped_themes[]`: themes not in baskets — stored as free text, no mapping
- `confirmation_conditions[]` / `falsification_conditions[]`: `condition_text_en`, `condition_text_zh`, `observable` (`"machine_checkable" | "human_judgment" | "unspecified"`), `provenance`
- `current_evidence_status`: always `"unknown"` in MVP
- `evidence_refs`: always `[]` in MVP

### 5.6 Staleness and Active Logic

| Horizon | Time condition | Logic condition | Active when |
|---|---|---|---|
| Short | ≤ 30 days | — | Time only |
| Mid | ≤ 180 days | Logic not falsified | Both |
| Long | — | Logic not falsified | Logic only |

Mid 90–180 days shows "偏旧" warning but remains active. "Logic not falsified" is always True in MVP (no mechanism to write a falsification). Publication date null → `not_applicable` for time tier, still active.

### 5.7 Key Implementation Lessons (for future phases)

**JSON parsing robustness:** LLM responses in Chinese-heavy extractions frequently embed unescaped ASCII double-quotes inside string values, breaking standard JSON parsing. The `_parse_json` function uses a three-strategy approach: (1) strip fences + parse at first brace only, (2) `json-repair` library repair + parse, (3) lenient fallback scan. A post-parse guard verifies the result contains expected top-level keys and raises `ExtractionError` if it looks like an inner object was returned. The `json-repair` library (`>=0.30.0`) is now in `requirements.txt`.

**Enum normalisation:** LLM returns boolean `true/false` for `observable`, Chinese strings for `affected_horizons`, non-enum values for `direction`, and `None` for `provenance`. Normalisation functions (`_normalise_observable`, `_normalise_horizon`, `_normalise_direction`, `_normalise_provenance`) are applied at assembly time before the validator sees the output.

**`_parse_json` architecture note:** `_decode_at_first_brace` is a local function inside `_parse_json` — it cannot be imported directly from outside the module. This is intentional; only `_parse_json` itself is the public interface.

**`load_dotenv` isolation:** The thesis feature is import-isolated from core pipeline modules (by design). Those modules happen to call `load_dotenv()` as a side effect. Extractor calls `load_dotenv(explicit_repo_root_path)` explicitly to avoid depending on this side effect.

**Multi-card extraction from one document:** All cards from one document share the same `doc_hash`. The overwrite confirmation is scoped to the `doc_hash` (stored as `thesis_ing_overwrite_hash` in session state), not a per-card boolean. This ensures the confirmation persists for the whole batch without re-arming between cards.

**Cockpit navigation:** `st.page_link` with `query_params` does not work reliably in the current Streamlit version. All Cockpit-to-Library navigation uses `st.button` + `st.session_state` mutation + `st.switch_page`. The Library page's query-param reader (`?ticker=`, `?theme=`, `?category=`) is retained as a secondary entry path for bookmarked URLs.

### 5.8 Test Suite

80 tests in `scripts/test_reliability_thesis_ingestion.py`, covering:

- Schema and validation (Group 1): 25+ assertions including empty core_claims rejection, numeric fabrication rejection, evidence status tamper detection, inner-object mis-parse detection, JSON repair path.
- Staleness and active computation (Group 2): 20+ assertions.
- Storage isolation (Group 3): 15+ assertions including round-trip, atomic write, unavailable scan, multi-card dedup.
- Isolation invariants (Group 4): static import checks confirming core pipeline modules never import thesis_ingestion.

### 5.9 Parity Baseline History

**After Thesis Ingestion MVP + UI verification batch (`b323c09`):**
- 80 thesis reliability tests (new)
- 79 `test_reliability_*` suites, 14,039 passed / 220 failed
- 13 RED suites (legacy Phase-5, scheduled for archival)

**After Legacy Red Suite Archival (`4f39838` + `8e6f891`):**
- 13 legacy RED suites moved to `scripts/archive/`
- Active parity baseline: 67 GREEN / 0 RED
- Environment note: baseline measured with system Python user-site
  (pandas 3.0.3 / numpy 2.4.4 / pytest 9.1); `.venv` is a non-functional
  stub; use `python3 scripts/test_reliability_<name>.py` directly

**After Phase 7C (`79433d5`):**
- `test_reliability_theme_transmission.py` added (11 tests, ALL PASSED)
- Active parity suites: 68 GREEN / 0 RED

---

## 6. Completed Phase History

### 6.1 Pre-Phase-7 Foundation

Original five-step AI workflow → Phase 0–4M reliability/validation/debate/memory → Phase 5 opportunity-first cockpit productization → Phase 6A live macro → Phase 6B signal layers → Phase 6C Trading Desk and Cockpit rebuild → Phase 7A opportunity ranking → Phase 7B rotation + market internals → Valuation Stop-the-Bleed → Valuation Refactor v1 → Anchor Intelligence v2–v2.5 → June 12 banner/data cleanup batch.

See Master Memo v1 (2026-06-12) for detailed rationale on each of these phases.

### 6.2 Thesis Ingestion MVP (June 2026)

**Problem solved:** The system was strong on "what is the market doing" (market-derived signals) but had no structured storage for "why does a theme or stock matter" (causal reasoning chains from external research). These chains lived in the user's memory or scattered articles and degraded silently over time.

**Solution:** A structured card library storing the "cause" side — author claims, transmission chains, assumptions, falsification conditions, numeric evidence with provenance.

**Completion:** `main @ b323c09`. 80 tests. UI verification batch completed including sidebar navigation, contextual jump buttons on Cockpit theme and signal cards, backup folder auto-setup, docx/pdf/pptx format support, JSON repair for LLM malformation, enum normalisation, multi-card dedup fix, and overwrite logic scoped to doc_hash.

**What it unlocks:**
- Phase 7C can now read thesis cards to understand transmission chains within theme layers.
- Phase 8 debate layer has a card library to draw evidence from.
- Phase 9 Judgment Console has a structured judgment object (`current_evidence_status`, `evidence_refs`) ready to receive human-confirmed updates.

### 6.3 Legacy Red Suite Archival (June 2026)

**Problem solved:** 13 Phase-5-era test suites permanently RED, producing noise in every Codex Step 4 sweep and requiring manual baseline verification each cycle.

**Solution:** `git mv` to `scripts/archive/`. No implementation changes. Purely documentary.

**Completion:** commits `4f39838` + `8e6f891`, pushed to `origin/main`. New baseline: 67 active suites, GREEN=67 / RED=0.

### 6.4 Phase 7C — Theme Transmission Mapping (June 2026)

**Problem solved:** `theme_baskets` mapped themes to flat ticker lists. The system knew NVDA was in `ai_chips` but not that `ai_chips` is a Wave 1 node that capital rotates through before reaching `hbm_memory` (Wave 2) or `datacenter_power` (Wave 4). This was information loss in the opportunity ranking and Sector page.

**Solution:** `lib/theme_transmission.py` — thin bridge producer that maps `THEME_BASKETS` onto the existing `phase5_theme_intelligence` schema (`IndustryChainNode`, `ThemeCandidateRole`). Two static seed tables:
- `THEME_TRANSMISSION_ORDER`: 12 themes → `transmission_order` (1–4) + `transmission_cluster` (8 cluster types)
- `TICKER_ROLE_MAP`: per-ticker role (`leader` / `second_derivative_beneficiary` / `supplier` / `platform` / `speculative` / `laggard` / `unknown`)

**Key design decisions:**
- `transmission_order` = capital propagation sequence, NOT strength ranking
- Same-order themes subdivided by `transmission_cluster` (e.g. `supply_chain` vs `demand_application` both at Wave 2)
- Reuses `phase5_theme_intelligence.py` schema — no duplication
- Naming: "transmission_order" avoids collision with `rotation.py` "tier"
- All seed data human-curated; no LLM auto-assignment in v1
- Scoring firewall: transmission data is display/rationale only, never enters three-period scoring algorithm

**UI changes:**
- Cockpit: transmission row on each theme card (波次 badge + downstream)
- Sector: Market Themes tab redesigned as wave-based card layout (4 waves, 横向 columns per wave); Cockpit-style thumbnail; role distribution + ticker lists in expanded body

**Completion:** `main @ 79433d5` (merge of `phase-7c-theme-transmission`). 11 tests ALL PASSED. Mutation probes verified (isolation, role integrity, never-raises). `phase5_theme_intelligence.py` and `theme_baskets.py` untouched.

**What it unlocks:**
- `get_diffusion_context()` shows which wave capital is currently in and which wave is next — foundation for Phase 7D calibration
- Phase 8 debate layer knows a ticker's chain position
- Judgment Console (Phase 9) can surface tier suggestions

---

## 7. Future Roadmap Ledger

The value chain from here:

```
Thesis Ingestion MVP (DONE)
→ Legacy Red Suite Archival (DONE — 4f39838)
→ Phase 7C Theme Transmission Mapping (DONE — 79433d5)
→ 7D Feedback / Recommendation Quality Evaluation
→ Phase 8 Evidence Infrastructure
→ Phase 9 Judgment Console
→ Phase 6D Holding-Side Loop
```

### 7.1 Legacy Red Suite Archival (DONE — 4f39838)

**Status: COMPLETE.** See §6.3 for full record.

**Why:** These Phase 5 fixture-based suites have drifted from the real implementation. They produce noise in every Codex review's Step 4 sweep and require manual baseline verification each time.

**How:** Move files, update scan script, rerun, record new baseline, update PROJECT_STATE.md. No Codex review needed — purely documentary.

### 7.2 Phase 7C — Theme Transmission Mapping (DONE — 79433d5)

**Status: COMPLETE.** See §6.4 for full record.

Upgrades theme → ticker mapping from flat basket membership to a tiered transmission chain. Deterministic tier schema, manual seed mapping, `tier_unassessed` for uncovered names. Must not use LLM for automatic tier assignment in v1.

### 7.3 Phase 7D — Feedback Loop / Recommendation Quality Evaluation

Turns "did this work?" into audit-snapshot-based evaluation. Evaluates from snapshots only — never rolling recomputation. Tracks author/source quality for thesis cards. Foundation for calibrating ranking weights and LLM judgment scorecards.

### 7.4 Phase 8 — Evidence Infrastructure

Builds evidence packs and first true evidence-consuming debate layer. Three consumers: (1) valuation debate with reverse DCF and bull/bear/risk evidence packs, (2) macro event/attribution with conditional scenarios (no fake probabilities), (3) research evidence from thesis card library. Must not let LLM generate numerics or override regime.

### 7.5 Phase 9 — Judgment Console

UI/workflow layer where LLM-suggested judgments are shown, cited, accepted/rejected/overwritten by the human, and persisted with provenance. First form = human-in-the-loop. Thesis card `current_evidence_status` and `evidence_refs` fields are the consumption target — Phase 9 is the first thing that may write non-default values to those fields, and only after human confirmation.

Must not become: auto-approval, hidden state mutation, execution authorization, unsourced LLM opinion.

### 7.6 Phase 6D — Holding-Side Loop

Completes the loop from "what to buy/watch" to "what changed after I hold it." Binds thesis / invalidation conditions to holdings. Uses Phase 7D / 8 / 9 data. Must not become broker automation or auto-sell trigger.

---

## 8. Known Risks and Design Debt

### 8.1 Split-Brain Architecture

Live app and reliability stack are not fully unified. Recommended path: identify highest-value live LLM outputs, wrap in minimal evidence-bound objects, add validators, add review UI, preserve existing deterministic path.

### 8.2 `llm_orchestrator.py` JSON Parsing

The same `_first_obj` lenient scanner that caused the thesis extractor's `core_claims` silent-loss bug also exists in `llm_orchestrator.py`. It is guarded only by callers' per-key checks and the structured stub fallback. If a caller's fallback is insufficiently defensive, the same silent inner-object return could happen. Flagged as a latent issue; not yet fixed in `llm_orchestrator.py`.

### 8.3 Marginal Buyer Gap

The biggest selection-quality gap is not more technical indicators. It is understanding who buys next, what evidence says that buyer is active, what catalyst makes buying urgent, whether the setup is crowded, and how long the buying impulse persists.

### 8.4 Portfolio / Monitoring Limitations

No broker import, no scheduler, no alert system, limited current-price portfolio valuation, no tax / margin / options exposure, no factor/correlation optimizer.

### 8.5 Calibration Debt

vol_shrink / weak-bounce component definition, forward EPS data hygiene for recovery names, valuation_role mapping edge cases, peer-match boundary values, fragility thresholds after more snapshots.

---

## 9. Development and Collaboration Protocol

### 9.1 Roles

| Actor | Role |
|---|---|
| User / John | Product owner, architecture direction, final approval, Chinese discussion |
| Claude | Architecture discussion partner, prompt engineer, phase planner, reviewer of Codex feedback |
| Claude Code | Implementation actor |
| Codex | Independent reviewer, mutation-probe validator, audit response |

### 9.2 Standard Phase Flow

```
1. User defines need in Chinese
2. Claude clarifies architecture and scope
3. Claude writes English implementation prompt for Claude Code (in a code block)
4. Claude Code implements in main worktree
5. User posts implementation result
6. Claude writes Codex review prompt (in a code block) with PREFLIGHT
7. Codex reviews with mutation probe discriminability as first-class requirement
8. User posts verdict
9. Claude decides: accept / request fixes / narrow re-review
10. After explicit APPROVE with "what this unlocks," Claude Code does closeout
11. Docs updated: PROJECT_STATE.md, CURRENT_TASK.md, phase doc, README.md
12. UI VERIFICATION: before final closeout, user manually tests any visible UI changes
    and reports results; issues become a fix batch before pushing
```

### 9.3 Prompt Formatting Rule

All prompts given to Claude Code and Codex must be in a single code block. Inner code examples use 4-space indentation, not nested backtick fences.

### 9.4 Git Discipline

- Implementation in primary worktree with venv. Review in standing review worktree.
- Merge with `--no-ff`. No rebase / force push.
- POSIX heredoc for commit messages (not PowerShell here-string).
- Stop and report on unexpected git state.
- Push only after explicit approval.

### 9.5 Testing Discipline

Codex review must test whether tests are discriminating. A test that stays green when the bug exists is more dangerous than no test. Mutation probes are first-class.

### 9.6 Documentation Discipline

Each phase closeout must sync: `PROJECT_STATE.md`, `CURRENT_TASK.md`, phase-specific doc, `README.md` if user-facing behavior / principles / architecture / file structure changes.

### 9.7 Phase 0–5 Ground-Work Scan (New, June 2026)

Before starting any new phase, STEP 0 recon must explicitly scan Phase 0–5 legacy code for reusable structures, data types, or partial implementations. Reuse over rebuild. If existing ground work can serve as a foundation, extend it rather than duplicating it.

Example: Phase 7C reused `phase5_theme_intelligence.py`'s `IndustryChainNode` and `ThemeCandidateRole` instead of inventing a parallel tier/role taxonomy — saving ~1,500 lines of vetted contract.

---

## 10. Cross-Session Startup Context

Use this block when starting a new Claude / Claude Code / Codex session.

```
We are continuing the AI Investment OS project.

Current authoritative sources are the latest README.md and ROADMAP.md.
This memo (Master Memo v2, 2026-06-15) is supplementary context.

Current baseline:
- main @ 79433d5
- Legacy Red Suite Archival closed (June 2026)
- Phase 7C Theme Transmission Mapping closed (June 2026)
- Active parity suites: 68 GREEN / 0 RED
- 80 thesis reliability tests + 11 theme_transmission tests passing

Current product:
- AI Investment OS, not merely a five-step research workflow
- Review-only, never places orders
- Deterministic code computes all numbers
- LLM can suggest evidence-bound judgments, but human confirmation required
- Main pages: Investment Cockpit, Macro Dashboard, Trading Desk, Sector,
  Scanner, Equity, Financial, PriceVolume, Overview, Thesis Library (NEW)
- Main live modules: macro_regime, market_internals, theme_baskets,
  rotation, candidate_generator, signal_engine, opportunity_ranker,
  relative_strength, order_advisor, thesis_monitor, equity_valuation,
  valuation_router, valuation_diagnosis, anchor_cache, anchor_archive,
  anchor_migration, anchor_backfill, thesis_ingestion (NEW)

Completed major work:
- Original five-step AI workflow
- Phase 0–4M reliability, validation, debate, memory, feedback foundations
- Phase 5 opportunity-first, horizon-aware cockpit productization
- Phase 6A live macro
- Phase 6B signal layers
- Phase 6C Trading Desk and Cockpit rebuild
- Phase 7A opportunity ranking
- Phase 7B rotation and market internals
- Valuation Stop-the-Bleed
- Valuation Refactor v1
- Anchor Intelligence v2–v2.5
- June 12 banner/data cleanup
- Thesis Ingestion MVP + UI verification batch (b323c09)
- Legacy Red Suite Archival (June 2026)
- Phase 7C Theme Transmission Mapping (June 2026, 79433d5)

Current next task:
- Phase 7D Feedback Loop / Recommendation Quality Evaluation, OR
- Phase 8 Evidence Infrastructure
- Confirm with architect which to prioritize

Future ledger (in order):
- 7D feedback / recommendation quality evaluation
- Phase 8 evidence infrastructure and valuation/macro debate
- Phase 9 Judgment Console (LLM proposes, human disposes, thesis cards consumed)
- 6D holding-side loop

Key invariants to never violate:
- approved_for_execution is always False
- LLM never invents numeric values
- thesis_ingestion is never imported by ranking/snapshot/anchor modules
- theme_transmission is display/rationale only; never imported by
  scoring, snapshot, or anchor modules
- current_evidence_status on scenario cards is always "unknown" until Phase 9
- Append-only: snapshots, anchor archive, thesis ingest_log never rewritten
- Tighten-only: market internals never flip macro regime or loosen conditions
- All prompts to LLM are in English; bilingual output via field_en/field_zh + bi()
```

---

## 11. The Most Important Things Not to Forget

1. The project is not a stock picker. It is an investment workflow operating system.
2. The central product path is opportunity-first, not ticker-first.
3. Horizon awareness is mandatory across all features.
4. Review-only safety is non-negotiable. `approved_for_execution` is always False.
5. The LLM boundary is corrected: no numeric fabrication, but evidence-bound judgment suggestions are allowed with human confirmation.
6. Live product path and reliability stack are selectively integrated, not fully unified.
7. Current biggest selection gap is marginal-buyer / catalyst / exposure evidence, not more RSI indicators.
8. Thesis card library is zero-consumer in MVP. It builds the library. Phase 9 is the first thing that may update `current_evidence_status`.
9. Thesis cards store what the **author** said. The extraction must not add, infer, or embellish. Numbers the author did not give go into `unspecified_numerics` with no proxy value.
10. Daily snapshots and anchor archive are append-only audit trails. Future evaluation must use audit snapshots, not rolling recomputation.
11. README and ROADMAP are authoritative. This memo is P1 context that yields to them on any conflict.
12. Every future phase must specify: what it is / why it exists / completion criteria / what it must not become / who uses it.
13. All prompts to Claude Code and Codex must be in a single copyable code block. Prompt formatting matters for usability.
14. UI verification is now part of every phase's closeout. Visible changes must be manually tested before the final push.
