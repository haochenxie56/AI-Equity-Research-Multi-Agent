# Phase 5Q — Human Feedback UI v0.1

**Status:** Implemented — awaiting Codex review.

**Scope:** Product-facing Streamlit UI update to the Investment Cockpit's
**Feedback / Review** tab (`pages/7_Investment_Cockpit.py`) plus a new
session-only contract module (`lib/reliability/phase5_human_feedback_ui.py`),
additive `ui_utils.py` EN/ZH chrome keys, a test, and this document.

> Disclaimer: outputs are for research / educational purposes only and do not
> constitute investment advice.

---

## Purpose

Phase 5Q completes the human-in-the-loop review loop **at the UI level**. It
adds a controlled human-feedback surface to the Investment Cockpit so the user
can review the fixture-backed opportunities, decision-workspace outputs, agent
debate, trade/allocation/option views already surfaced by Phase 5N, and record
**non-persistent, review-only feedback** against them.

The goal is to make the cockpit a place where a human can express a review
intent — *accept for watchlist*, *reject*, *modify thesis*, *request more
research*, *wait for pullback*, *manually executed outside system*, *skip*,
*review later*, *no-trade confirmed* — without any of that feedback being
persisted, executed, or turned into an order.

Phase 5Q is intentionally **session-only**: it closes the loop visually and
interactively, but defers durable persistence and any live shadow integration
to a later controlled phase.

---

## Relationship to Phase 4M-F Human Feedback Layer

Phase 4M-F (`lib/reliability/human_feedback_memory.py`) is the **memory / audit
record** contract for human feedback: `HumanFeedbackMemoryRecord`,
`HumanFeedbackEntry`, `HumanFeedbackMemoryReport`, deterministic record IDs,
status precedence, and a `ToolResult` adapter. It is the durable, auditable
representation of feedback.

Phase 5Q is the **UI / session layer above** Phase 4M-F. It defines transient
view/session contracts (`HumanFeedbackUIState`, `HumanFeedbackActionView`,
`HumanFeedbackReviewTarget`, `HumanFeedbackFormState`,
`HumanFeedbackSessionRecord`, `HumanFeedbackValidationSummary`,
`HumanFeedbackSafetyBanner`). Phase 5Q **does not** build, write, or mutate any
Phase 4M-F memory record — it never persists. The two layers share vocabulary
(decision/action labels, the `approved_for_execution`-is-never-True invariant),
and a future controlled phase could bridge a Phase 5Q `HumanFeedbackSessionRecord`
into a Phase 4M-F `HumanFeedbackMemoryRecord`, but Phase 5Q deliberately stops
at the session boundary.

The existing read-only Phase 4M-F / 4M-G fixture summaries that the Phase 5N
Feedback / Review tab already showed are **retained** (now under an expander),
so nothing previously visible is lost.

## Relationship to Phase 5I product logic

Phase 5I established the cockpit as opportunity-first / macro-theme-aware /
horizon-aware and separated source research modules from the decision layer.
Phase 5Q adds the *human review* endpoint of that decision layer: after the
opportunity queue, decision workspace, agent debate, and trade/option views have
surfaced an auditable picture, the human can record a review intent against a
specific candidate / horizon / decision-workspace / option overlay. This
preserves Phase 5I's auditability principle — every step from "interesting
opportunity" → "research" → "debate" → "decision state" → "human review intent"
is explicit and review-only.

## Relationship to Phase 5M Decision Workspace

Phase 5M produces the review-only `DecisionWorkspaceView`
(`is_executable_decision=False`, `requires_human_review=True`) plus the agent
debate consensus and explicit `DebateConflictRecord`s. Phase 5Q's review targets
read those Phase 5M outputs (workspace status, decision label, consensus level,
conflict counts) so the feedback is **visibly connected** to the decision
workspace status and to the agent debate consensus/conflicts. Phase 5Q recomputes
nothing and never flips `requires_human_review` to a decision.

## Relationship to Phase 5N Cockpit UI v0.2

Phase 5N redesigned the cockpit into ten opportunity-first tabs, including a
**Feedback / Review** tab that, until now, only showed read-only Phase 4M-F /
4M-G fixture summaries. Phase 5Q enhances exactly that tab: it adds the
interactive session-only feedback form (target selector + action control +
optional note + session preview) above the retained read-only summaries. No
other Phase 5N tab is changed; the `apply_theme()` / `render_sidebar()`
bootstrap, the `@st.cache_resource` loaders, the `nav_p7` sidebar entry, and the
`cockpit_*` `ui_utils.t()` namespace are all preserved.

---

## Why feedback is session-only in Phase 5Q

The cockpit's value is auditability and safety. Durable feedback persistence
introduces real concerns — where it is stored, how it is versioned, how it
feeds back into agent evaluation, and whether it could ever become an execution
trigger. Phase 5Q deliberately stops at the **session boundary** so that:

- the review surface (targets, actions, form, preview) is deterministic,
  inspectable, and testable;
- nothing is written to disk, DB, vector store, workflow state, or a broker;
- there is no path from "recorded feedback" to "order" or "execution";
- the durable persistence design (and any live shadow integration) is a separate,
  reviewable phase rather than an implicit side effect of a UI change.

Submitted feedback lives only in `st.session_state` for the lifetime of the
browser session and is lost on refresh/close.

---

## Supported feedback actions

The review-only action vocabulary (`HumanFeedbackActionType`,
`HUMAN_FEEDBACK_ACTIONS`):

| Action | Meaning (review intent only) |
|--------|------------------------------|
| `accept_for_watchlist` | Add the reviewed candidate to a watchlist (no position, no order). |
| `reject` | Reject the candidate / thesis. |
| `modify_thesis` | Note that the thesis should be revised. |
| `request_more_research` | Ask for additional research before deciding. |
| `wait_for_pullback` | Defer; wait for a better entry. |
| `manually_executed_outside_system` | **Label only** — the human acted outside this system. Records nothing executable and triggers no order. |
| `skip` | Skip this candidate. |
| `review_later` | Defer the review itself. |
| `no_trade_confirmed` | Confirm the `no_trade` posture. |

Every action carries `is_executable=False` and `requires_human_review=True`.
None is an order instruction.

---

## Review target semantics

A `HumanFeedbackReviewTarget` binds a piece of feedback to a fixture-backed
object and carries its visible connections. Target kinds
(`HumanFeedbackReviewTargetKind`): `opportunity_candidate`, `horizon`,
`decision_workspace`, `agent_debate`, `trade_allocation_plan`, `option_overlay`,
`no_trade`, `unknown`. The default fixture builds targets from:

- **Phase 5K opportunity queue** → `opportunity_candidate` (and `no_trade` for
  the no-trade/avoid queue), each carrying ticker, theme, **horizon**, decision
  label, and next action.
- **Phase 5M decision workspace** → `decision_workspace`, carrying **workspace
  status**, decision label, **consensus level**, and **conflict / unresolved
  counts** (the agent-debate consensus/conflicts connection).
- **Phase 5D portfolio view (via the Phase 5G demo pack)** → `trade_allocation_plan`
  (carrying the **trade-plan review state**) and `option_overlay` (carrying the
  **option state / `is_no_trade`** flag).

The target builders are duck-typed and defensive: a missing upstream view simply
contributes no targets, so the surface degrades safely.

---

## Non-persistence boundary

- No model is written to disk, DB, vector store, `research/.workflow_state.json`,
  or any production state.
- The page holds submitted feedback only in `st.session_state`
  (`phase5q_feedback_session`), a transient list cleared on demand.
- `HumanFeedbackSafetyBanner`, `HumanFeedbackFormState`,
  `HumanFeedbackSessionRecord`, `HumanFeedbackValidationSummary`, and
  `HumanFeedbackUIState` all carry `is_session_only=True` / `is_persisted=False`,
  and reject construction with `is_persisted=True`.
- No file-open / `json.dump` / `to_parquet` / `to_csv` / pickle / DB / vector
  store call appears in the page or the module.

## Non-execution boundary

- No Phase 5Q model declares `approved_for_execution` (absent by construction);
  it is never positively authorized anywhere.
- Actions and session records carry `is_executable=False`; the safety banner
  carries `is_non_executable=True`.
- No order-ticket / broker-route / account-id / time-in-force / execution-id /
  quantity-to-execute / broker-payload field is declared on any model or shown
  on the page.
- `manually_executed_outside_system` is a **memory-style label only** — it
  records that a human acted elsewhere and creates no order, payload, or
  execution path here.
- `no_trade` / `no_trade_confirmed` is preserved as a first-class state.

---

## Bilingual rules

All new user-facing chrome strings route through `ui_utils.t()`. EN/ZH
translation keys for the new feedback chrome and the nine action labels are added
to `ui_utils.TRANSLATIONS` (additive only; no existing key renamed or removed).
Fixture content (ticker symbols, theme names, run IDs, deterministic fixture
text), schema identifiers (`approved_for_execution`, `no_trade`, target-kind /
action enum values, JSON keys), and `field=value` binding evidence are
intentionally **not** translated. EN and ZH `AppTest` render coverage is
preserved.

---

## Non-goals

- No durable / permanent feedback persistence (no disk, DB, vector store,
  workflow state, or file writes).
- No live shadow integration; no live workflow behavior change.
- No LLM call; no yfinance / Finnhub / FRED / CNN / news / external API call.
- No broker / order / execution capability; no order tickets, broker payloads,
  account IDs, time-in-force, quantity-to-execute, or execution IDs.
- No final buy/sell/order instruction; no `approved_for_execution=True`.
- No Phase 4M-F memory record is written from the UI.
- No UI/UX visual polish (deferred to Phase 5R).
- No changes to `app.py`, pages 1–6, `pages/8_Macro_Dashboard.py` behavior,
  `lib/llm_orchestrator.py`, `lib/workflow_state.py`, or `.claude/agents/*`.

## Guardrails

- Only `pages/7_Investment_Cockpit.py` (UI), `ui_utils.py` (additive translation
  keys), and the new `lib/reliability/phase5_human_feedback_ui.py` contract
  module are added/modified for the live surface, plus the test, this doc, and
  state files.
- The new contract module is offline / deterministic; every model sets
  `extra="forbid"`; `approved_for_execution` is absent on every model.
- Feedback is session-only and non-executable; it fails closed with the rest of
  the page on builder error (no LLM/API fallback).
- Phase 4A is not wired in and not imported.

---

## Acceptance criteria

1. `pages/7_Investment_Cockpit.py` exposes a Feedback / Review surface with a
   target selector, a review-action control, an optional free-text note, and a
   session-only preview, and compiles + renders in EN and ZH via `AppTest`
   without exception (complete and degraded scenarios).
2. The feedback actions include `accept_for_watchlist`, `reject`,
   `modify_thesis`, `request_more_research`, `wait_for_pullback`,
   `manually_executed_outside_system`, `skip`, `review_later`, and
   `no_trade_confirmed`.
3. Feedback is session-only / non-persistent: no file/DB/vector/workflow-state
   write, no broker/order call, and all session contracts carry
   `is_session_only=True` / `is_persisted=False`.
4. No `approved_for_execution=True` is positively authorized; no order-ticket-like
   field is introduced.
5. EN/ZH translation keys exist for all new feedback chrome and action labels and
   are referenced by the page.
6. `scripts/test_reliability_phase_5q_human_feedback_ui.py` passes; the Phase 5N
   cockpit test still passes; the Phase 5M agent-debate test still passes.

---

## Future Phase 5R dependency

The next phase, **Phase 5R — UI/UX Visual Polish + Demo Readiness** (not started),
will refine the visual presentation of the cockpit (including this feedback
surface) and prepare a demo-ready experience. Durable feedback persistence and/or
a controlled bridge from Phase 5Q session records into the Phase 4M-F human
feedback memory layer remain out of scope for Phase 5Q and would be a separate,
explicitly-scoped phase. **Phase 5R has not started.**
