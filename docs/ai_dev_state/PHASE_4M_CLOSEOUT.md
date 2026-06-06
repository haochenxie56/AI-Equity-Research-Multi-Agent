# Phase 4M Closeout — Roadmap v4 Phase 4 Memory + Human Feedback + Review

**Date**: 2026-05-27 (test matrix rerun and design docs reconciled 2026-05-27 after Codex review; subsequent counter-bump to 307/307 reflected after Phase 5P Section 31 update)
**Status**: **Accepted** — Phase 4M Closeout (Phase 4M-H) accepted; Phase 4 Memory mainline complete. The wording in earlier drafts of this document that referred to "awaiting Codex re-review" is historical and has been reconciled below. Phase 5 has formally opened with the separately-tracked Phase 5P — Phase 5 Roadmap Decision / Planning task (see `docs/reliability_phase_5p_roadmap_decision.md`); Phase 5A implementation has not started.

---

## 1. Phase 4M Summary

Phase 4M implements **Roadmap v4 Phase 4 — Memory + Human Feedback + Review**
as a **schema/helper-only, offline, deterministic reliability layer**.

Phase 4M is the Roadmap-aligned mainline implementation of Phase 4 Memory.
It records decision trails, memory records, human feedback, and agent
evaluation artifacts entirely as in-memory Pydantic models and pure helper
functions, with **no persistence engine, no live integration, and no
investment-execution authority**.

Key positioning facts:

- **Phase 4A Integration Boundary remains accepted early infrastructure**, not
  the Memory mainline. Phase 4A is frozen in its current standalone state and
  is not wired into the live Streamlit app.
- **Phase 4M is the Roadmap-aligned Phase 4 Memory mainline.** It does not
  replace, extend, or wire Phase 4A into anything.
- Phase 4M does **not** persist to a database, file store, vector store, or
  live app.
- Phase 4M records decision trails, memory records, human feedback, and agent
  evaluation artifacts.
- Phase 4M outputs are **research / review / audit artifacts only**.
- Phase 4M does not call the Claude API or any external API.
- Phase 4M does not import live brokerage, portfolio, option-chain, news,
  earnings, estimate-revision, or market data.
- Phase 4M does not authorize execution; `approved_for_execution` remains
  `False` wherever it appears.

Phase 4M is composed on top of the previously accepted Phase 3 reliability
composition backbone (Orchestration, DecisionPacket, Human Review / Feedback
Schema, Review Loop / Reliability Run Report) and the Phase 3R roadmap backfill
(Event Intelligence, Trade Plan, Allocation, Option Expression).

**Historical acceptance context (Phase 4M-H closeout pass).** Codex review of
the initial Phase 4M-H closeout returned PASS on the closeout document, roadmap
coverage, scope safety, execution / persistence / model-mutation safety, and
export/import sanity, with the only blocking issue being a stale state-file
assertion inside `scripts/test_reliability_agent_evaluation.py` that still
expected Phase 4M-G CURRENT_TASK.md to say "awaiting Codex re-review" even
though Phase 4M-G is accepted. That assertion was rewritten to match the
then-current accepted state, the design-doc status reconciliation noted above
was applied, and the test matrix in Section 7 was rerun (4213 tests, 0
failures at that time). Phase 4M-H was subsequently accepted by Codex on the
basis of those fixes; **Phase 4M Closeout is therefore Accepted**. No runtime
implementation behavior was changed.

**Post-acceptance reconciliation (Phase 5P).** After Phase 4M-H acceptance,
the separately-tracked Phase 5P planning pass updated Section 31 of
`scripts/test_reliability_agent_evaluation.py` again (state-file assertion
phrasing only — no module / runtime change) so the assertions match the newly
accepted Phase 4M-H state plus the newly active Phase 5P planning phase. That
update added three more assertions, bumping the agent-evaluation test count
from 304 to 307. The Section 7 matrix below reflects the post-Phase-5P
current counts (Phase 4M subtotal 2193, total 4216).

---

## 2. Accepted Phase 4M Subphases

| Subphase | Name | Status |
|----------|------|--------|
| Phase 4M-A | Research Run Memory Schema | **Accepted** |
| Phase 4M-B | Thesis Memory by Horizon | **Accepted** |
| Phase 4M-C | Catalyst / News / Earnings Memory | **Accepted** |
| Phase 4M-D | Allocation Decision Memory | **Accepted** |
| Phase 4M-E | Option Trade Plan Memory | **Accepted** |
| Phase 4M-F | Human Feedback Layer | **Accepted** |
| Phase 4M-G | Agent Evaluation | **Accepted** |
| Phase 4M-H | Phase 4 Memory Closeout | **Accepted** (this document) |

Phase 4M-G was accepted with no minor suggestions; no minor-suggestion
implementation was required in this closeout. Phase 4M-H itself was
subsequently accepted by Codex on the basis of the closeout fixes recorded
in Section 1 and Section 7, completing the Phase 4M mainline.

---

## 3. Roadmap v4 Phase 4 Coverage Map

### Roadmap v4 Phase 4 Memory + Human Feedback + Review

| Roadmap v4 Phase 4 Capability | Delivered In |
|-------------------------------|-------------|
| Research Run Memory | Phase 4M-A |
| Thesis Memory by Horizon | Phase 4M-B |
| Catalyst / News / Earnings Memory | Phase 4M-C |
| Allocation Decision Memory | Phase 4M-D |
| Option Trade Plan Memory | Phase 4M-E |
| Human Feedback Layer | Phase 4M-F |
| Agent Evaluation | Phase 4M-G |

### Phase 3 reliability composition backbone (accepted prior to Phase 4M)

Phase 4M is composed on top of these previously accepted Phase 3 components:

- Orchestration Skeleton (Phase 3A)
- DecisionPacket / Decision Synthesis Skeleton (Phase 3E)
- Human Review / Feedback Schema Skeleton (Phase 3F)
- Offline Review Loop / Reliability Run Report (Phase 3G)

### Phase 3R roadmap backfill (accepted prior to Phase 4M)

Phase 4M memory records reference artifacts produced by these Phase 3R
components:

- Event Intelligence (Phase 3R-A)
- Trade Plan (Phase 3R-B)
- Allocation (Phase 3R-C)
- Option Expression (Phase 3R-D)

Phase 4M never re-fetches or invents data for these upstream artifacts; it
only records caller-supplied references and caller-supplied analysis fields.

---

## 4. Key Artifacts

### Runtime files

| File | Phase | Description |
|------|-------|-------------|
| `lib/reliability/research_memory.py` | 4M-A | Research Run Memory Schema (5 Literal aliases, 6 Pydantic models, 11 helpers) |
| `lib/reliability/thesis_memory.py` | 4M-B | Thesis Memory by Horizon (8 Literal aliases, 7 Pydantic models, 12 helpers) |
| `lib/reliability/event_memory.py` | 4M-C | Catalyst / News / Earnings Memory (8 Literal aliases, 6 Pydantic models, 12 helpers) |
| `lib/reliability/allocation_memory.py` | 4M-D | Allocation Decision Memory (7 Literal aliases, 7 Pydantic models, 13 helpers) |
| `lib/reliability/option_trade_memory.py` | 4M-E | Option Trade Plan Memory (8 Literal aliases, 7 Pydantic models, 13 helpers) |
| `lib/reliability/human_feedback_memory.py` | 4M-F | Human Feedback Layer (7 Literal aliases, 8 Pydantic models, 14 helpers) |
| `lib/reliability/agent_evaluation.py` | 4M-G | Agent Evaluation (8 Literal aliases, 9 Pydantic models, 15 helpers) |
| `lib/reliability/__init__.py` | Cross-phase | Package entry point — all Phase 0–4M exports |

### Test scripts

| File | Phase | Result |
|------|-------|--------|
| `scripts/test_reliability_research_memory.py` | 4M-A | 165/165 |
| `scripts/test_reliability_thesis_memory.py` | 4M-B | 291/291 |
| `scripts/test_reliability_event_memory.py` | 4M-C | 307/307 |
| `scripts/test_reliability_allocation_memory.py` | 4M-D | 418/418 |
| `scripts/test_reliability_option_trade_memory.py` | 4M-E | 448/448 |
| `scripts/test_reliability_human_feedback_memory.py` | 4M-F | 257/257 |
| `scripts/test_reliability_agent_evaluation.py` | 4M-G | 307/307 |

### Design docs

| File | Phase |
|------|-------|
| `docs/reliability_phase_4m_research_memory.md` | 4M-A |
| `docs/reliability_phase_4m_thesis_memory.md` | 4M-B |
| `docs/reliability_phase_4m_event_memory.md` | 4M-C |
| `docs/reliability_phase_4m_allocation_memory.md` | 4M-D |
| `docs/reliability_phase_4m_option_trade_memory.md` | 4M-E |
| `docs/reliability_phase_4m_human_feedback_memory.md` | 4M-F |
| `docs/reliability_phase_4m_agent_evaluation.md` | 4M-G |

---

## 5. Architectural Boundaries

All Phase 4M subphases honor the following constraints:

- **Offline / mock-only.** No Phase 4M module performs any live behavior.
- **Schema / helper-only.** All Phase 4M code is composed of Pydantic models,
  Literal type aliases, and deterministic helper functions.
- **Does not modify Streamlit app behavior.** `app.py` and `pages/*` are
  untouched.
- **Does not modify live LLM orchestration behavior.** `lib/llm_orchestrator.py`
  is untouched.
- **Does not call the Claude API.** No `anthropic` SDK usage anywhere in
  Phase 4M.
- **Does not call external APIs.** No network calls, no HTTP, no data fetching.
- **Does not import live brokerage, portfolio, option-chain, news, earnings,
  or market data.** All upstream artifact references are caller-supplied IDs.
- **Does not write to a database.** No database engine, no ORM, no schema
  migration, no DB connection string consumed.
- **Does not write files as persistence.** No `open(..., "w")` for persistence;
  no JSON / Parquet / CSV write paths; no on-disk memory store.
- **Does not create or use a vector store.** No embedding pipeline, no
  similarity index, no vector DB.
- **Does not introduce broker / order / trade execution logic.** No order
  schema, no account schema, no execution fields.
- **Does not authorize execution.** `approved_for_execution` remains `False`
  wherever it appears in Phase 4M outputs; schema-enforced where applicable.
- **Phase 4M outputs are research / review / audit artifacts only.**
- **Phase 4A remains accepted as early integration infrastructure but is not
  wired into the live app.** No Phase 4M module imports `integration_boundary`
  in a way that changes live behavior.
- **No prompt / model / agent-definition mutation** is introduced by Agent
  Evaluation. Evaluation records are purely descriptive and never feed back
  into prompts, model selection, or `.claude/agents/*`.
- All helper functions are deterministic: same inputs → same outputs, no side
  effects, no mutation of input objects.

---

## 6. Safety-Specific Notes by Module

### Research Run Memory (Phase 4M-A)

- Records **decision-trail references only**.
- No persistence engine: memory records are returned to the caller as Pydantic
  models / ToolResult payloads; the caller is free to use them as research /
  audit artifacts in-process.
- Status precedence: `blocked > needs_review > incomplete > recorded > unknown`.
- `approved_for_execution` is permanently `False` where applicable.

### Thesis Memory (Phase 4M-B)

- Stores **horizon-specific thesis assumptions, invalidation conditions, and
  status** per ticker / horizon.
- Records evolution / archival events; **does not execute** anything.
- Status precedence: `blocked > needs_review > invalidated > active > archived > unknown`.
- `initial_status` override applied only as a safe fallback; never overrides
  stronger conditions.
- `approved_for_execution` is permanently `False` where applicable.

### Event Memory (Phase 4M-C)

- Records **catalyst / news / earnings / guidance / estimate-revision** memory
  drawn from caller-supplied upstream assessments.
- No live API calls. No Finnhub. No news provider. No earnings provider. No
  estimate-revision provider.
- `source_refs` are deduplicated deterministically; no fetching.

### Allocation Memory (Phase 4M-D)

- Records **allocation decisions, risk-budget snapshots, cash impact, and
  outcome placeholders**.
- No brokerage import. No live portfolio import. No order ticket. No cash
  reconciliation against a real account.
- Record IDs are content-sensitive but deterministic.

### Option Trade Memory (Phase 4M-E)

- Records **option expression strategy, risk, exit, PnL, and lesson memory**.
- No option-chain API. No order ticket. No broker. No live greeks fetcher.
- `snapshot_id` hash covers all 18 material fields, so memory entries are
  reproducible from inputs.
- `approved_for_execution` remains permanently `False`.

### Human Feedback Memory (Phase 4M-F)

- Records human-review decisions: `accepted`, `rejected`, `overrode`,
  `skipped`, `deferred`, `needs_revision`, `executed_manually`.
- **`executed_manually` is a memory-only label.** Recording it does **not**
  authorize execution, mutate brokerage state, or imply any live action; it
  records that a human reported having executed manually outside this system.
- `overrode` decisions require a non-blank `override_reason` (Codex fix from
  4M-F acceptance — schema-enforced via Pydantic validator).

### Agent Evaluation (Phase 4M-G)

- Records **offline evaluation, calibration, FP/FN, override, and rejection
  analysis** of agent outputs.
- **No model retraining.** No weight update. No model selection change.
- **No prompt mutation.** Evaluation records are descriptive only; they never
  rewrite, append to, or alter any prompt, agent definition, model selection,
  or `.claude/agents/*` file.
- **No live agent update.** Evaluation does not push results to any agent
  orchestrator or model provider.
- Record-level status precedence:
  `blocked > needs_review > incomplete > evaluated > archived > unknown`.
- `initial_status` is a safe fallback and never masks stronger conditions
  (Codex fix from 4M-G acceptance).
- `AgentEvaluationCalibration` and `AgentEvaluationSummary` carry explicit
  `rejection_count` / `rejection_rate`, surfaced via the ToolResult adapter
  (Codex fix from 4M-G acceptance).

---

## 7. Test Matrix (confirmed passing — rerun 2026-05-27 after Codex fixes; counts reflect post-Phase-5P Section 31 update)

> **Historical update note (2026-05-27, Phase 4M-H closeout pass)**: after
> Codex review flagged a stale state-file assertion in
> `scripts/test_reliability_agent_evaluation.py` (which had expected Phase
> 4M-G CURRENT_TASK.md to still say "awaiting Codex re-review" even though
> Phase 4M-G has been accepted), Section 31 of that test was rewritten to
> assert the then-current accepted state instead:
>
> - Phase 4M-G Agent Evaluation accepted under PROJECT_STATE / CURRENT_TASK,
>   and no longer in the "Implemented — Awaiting Codex Review" section.
> - Phase 4M-H Closeout awaiting Codex review *at that point in time*.
> - Phase 5 not started.
>
> The full closeout matrix was rerun after the fix. The agent evaluation
> count grew from `298` to `304` because the rewritten Section 31 contained
> 10 assertions (vs. 4 previously); no other test counts changed in that
> pass.
>
> **Post-acceptance update (Phase 5P)**: after Phase 4M-H was accepted by
> Codex, Phase 5P updated Section 31 again so the state-file assertions
> reflect Phase 4M-H as Accepted and Phase 5P as the new
> "Implemented — Awaiting Codex Review" entry. That update added three
> further state-file assertions, bumping the agent-evaluation count from
> `304` to `307`. Phase 4M subtotal therefore became `2193` and the closeout
> total became `4216`. **No module / runtime change.** The counts shown
> below are post-Phase-5P current counts.

### Phase 4M primary tests

| Script | Tests | Result |
|--------|-------|--------|
| `python3 scripts/test_reliability_research_memory.py` | 165 | PASS |
| `python3 scripts/test_reliability_thesis_memory.py` | 291 | PASS |
| `python3 scripts/test_reliability_event_memory.py` | 307 | PASS |
| `python3 scripts/test_reliability_allocation_memory.py` | 418 | PASS |
| `python3 scripts/test_reliability_option_trade_memory.py` | 448 | PASS |
| `python3 scripts/test_reliability_human_feedback_memory.py` | 257 | PASS |
| `python3 scripts/test_reliability_agent_evaluation.py` | 307 | PASS |
| **Phase 4M subtotal** | **2193** | **PASS** |

### Phase 3 + Phase 3R regression (confirmed passing — 2026-05-27)

| Script | Tests | Result |
|--------|-------|--------|
| `python3 scripts/test_reliability_option_expression.py` | 277 | PASS |
| `python3 scripts/test_reliability_allocation_report.py` | 392 | PASS |
| `python3 scripts/test_reliability_trade_plan.py` | 880 | PASS |
| `python3 scripts/test_reliability_review_loop.py` | 151 | PASS |
| `python3 scripts/test_reliability_human_review.py` | 113 | PASS |
| `python3 scripts/test_reliability_decision_packet.py` | 58 | PASS |
| `python3 scripts/test_reliability_event_intelligence.py` | 152 | PASS |
| **Regression subtotal** | **2023** | **PASS** |

**Total executed in this closeout (rerun 2026-05-27, post-Phase-5P state-file update): 4216 tests, 0 failures.** (The initial Phase 4M-H closeout rerun was 4213; the +3 delta reflects the Phase 5P state-file assertion additions described above. No module / runtime change.)

---

## 8. Known Non-Blocking Notes

- **Broader worktree dirty / untracked**: a repository hygiene checkpoint
  found the broader worktree dirty / untracked, but **forbidden live runtime
  paths remain clean**. Repository hygiene cleanup is intentionally **not**
  performed in Phase 4M-H per task scope (no commits, no staging, no stash,
  no reset, no `.gitignore` changes).
- **Phase 4A Integration Boundary remains accepted early infrastructure**, not
  wired into the live app. It is frozen in its current standalone state.
- **No actual persistence layer exists yet** for Phase 4M memory records.
  Persistence should be a future explicitly-scoped phase if desired.
- **No live UI integration exists yet** for Phase 4M memory records. A UI /
  cockpit should be a future explicitly-scoped phase if desired.
- **Carry-forward from 4M-G acceptance**: no minor suggestions were left
  outstanding. No additional clean-up is required here.
- **Phase 4M per-phase design docs reconciled (2026-05-27)**: the per-phase
  design docs `docs/reliability_phase_4m_research_memory.md`,
  `docs/reliability_phase_4m_thesis_memory.md`,
  `docs/reliability_phase_4m_event_memory.md`,
  `docs/reliability_phase_4m_allocation_memory.md`,
  `docs/reliability_phase_4m_option_trade_memory.md`, and
  `docs/reliability_phase_4m_agent_evaluation.md` previously contained
  header-status and "Future Subphases" tables drafted before later Phase 4M
  subphases were accepted (e.g., "awaiting Codex re-review", "Pending",
  "(future)"). Those status sections have been updated to reflect current
  accepted state (4M-A through 4M-H all accepted; Phase 4 Memory mainline
  complete).
  Historical implementation descriptions in those docs were not rewritten;
  they remain accurate descriptions of each accepted subphase. This
  reconciliation is documentation-only and does not change any module,
  schema, helper, or test.

None of these were blockers for Phase 4M Closeout acceptance, which has now been granted.

---

## 9. Phase 5 Readiness / Next-Phase Recommendation

Phase 4M was accepted by Codex; this closeout (Phase 4M-H) is therefore
accepted and the project moved on to Phase 5 planning. The recommendation
originally drafted in this section (a "Persistence Boundary / Memory Store
Interface Contract" Phase 5A) was **superseded** by the dedicated Phase 5
roadmap-decision pass, **Phase 5P**, which evaluated five candidate Phase
5A shapes and ultimately recommended a different Phase 5A — **Existing
Workflow Memory Adapter + Fixture-backed Memory Query Contract**. The
authoritative Phase 5 plan now lives in
`docs/reliability_phase_5p_roadmap_decision.md`. Phase 5A implementation
has not started; it is gated on Phase 5P acceptance.

### Recommended next phase (historical — superseded by Phase 5P)

> **Historical content below.** Preserved for traceability. The
> authoritative Phase 5A recommendation now lives in
> `docs/reliability_phase_5p_roadmap_decision.md`.

**Phase 5A — Persistence Boundary / Memory Store Interface Contract**

Rationale:

- All Phase 4M memory schemas (research run, thesis, event, allocation, option
  trade, human feedback, agent evaluation) are currently **in-memory only**.
- The "Known Non-Blocking Notes" in this document and in `PHASE_3R_CLOSEOUT.md`
  explicitly flag persistence as the natural next explicitly-scoped phase.
- A persistence-boundary **contract** (analogous to Phase 4A's integration
  boundary) is the conservative next step: it defines an interface for a
  memory store without choosing a concrete backend, without writing data, and
  without wiring into the live app.

Conservative scope guardrails for Phase 5A (historical — superseded by Phase 5P):

- Define a `MemoryStore` interface (typed Pydantic / Protocol) describing
  add / get / list semantics.
- Provide an `OfflineMemoryStore` implementation that is **in-memory only**
  (dict-backed) — equivalent to Phase 4A's `DISABLED` default.
- **Do not** introduce SQL, NoSQL, file persistence, or vector store backends
  in Phase 5A.
- **Do not** wire the store into the live app.
- **Do not** wire Phase 4A into the live app.
- Continue to keep Phase 4M outputs as research / review / audit artifacts.

### Strict reminders (still in force)

- **Do not start Phase 5A implementation from inside this closeout document.**
- **Do not wire memory into the live app in this closeout.**
- **Do not add DB / vector store / persistence in this closeout.**
- **Do not connect Phase 4A Integration Boundary to the live app in this
  closeout.**

---

## Global Guardrails (repeated from Phase 3R Closeout)

Do **not** modify:

- `app.py`, `pages/*`, `lib/llm_orchestrator.py`
- `.claude/agents/*`, existing live prompt files
- `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`
- `lib/data_fetcher.py`, `lib/workflow_state.py`
- Existing Streamlit UI or live workflow behavior

Do **not** introduce (unless explicitly scoped):

- Live app integration, Streamlit UI changes, live LLM calls
- Live API / data fetching, broker integration, order placement
- Any pathway that sets `approved_for_execution = True`
- Database, file persistence, or vector store backends before Phase 5A is
  explicitly scoped and accepted
