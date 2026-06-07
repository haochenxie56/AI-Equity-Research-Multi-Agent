# Phase 5M — Agent Debate / Decision Workspace Contract

**Status:** Implemented — awaiting Codex review.

**Module:** `lib/reliability/phase5_agent_debate.py`
**Test:** `scripts/test_reliability_phase_5m_agent_debate_workspace.py`
**Exports:** additive in `lib/reliability/__init__.py`

> Disclaimer: outputs are for research / educational purposes only and do not
> constitute investment advice.

---

## Purpose

Phase 5M defines the **deterministic contracts** for how a future Investment
Cockpit will structure **agent debate** and **decision-workspace review** after a
Phase 5L Research Pack has been assembled:

```
Phase 5K Opportunity Candidate
  -> Phase 5L Research Pack (ResearchPackBundle / boundary)
  -> Phase 5M Agent Debate / Decision Workspace   (this phase)
  -> (future) Phase 5N Cockpit UI v0.2
```

It defines **debate records, agent stance outputs, decision-workspace view
models, evidence handling, conflict tracking, consensus, and safety boundaries**.
It is a **contract only** — no real agent is run.

---

## Relationship to Phase 5I (Product Logic Reconciliation)

Phase 5I established the cockpit as **opportunity-first**, **macro-theme-aware**,
and **horizon-aware**, and separated the *source research modules* from the
*cockpit decision layer*. Phase 5M is the decision-layer step *after* research is
assembled: it takes the structured research pack and organizes a transparent,
evidence-first debate whose output is a **review-only** decision workspace, never
an executable order. This preserves Phase 5I's auditability principle: every step
from "interesting opportunity" → "research pack" → "debate" → "decision state" is
explicit and reviewable.

## Relationship to Phase 5J (Theme Intelligence / Market Heat)

Phase 5J is the upstream **input layer** (themes, subthemes, industry-chain
nodes, candidate tickers, heat / narrative / fundamental / crowding signals). Its
identifiers (`theme_id`, `theme_name`) flow through Phase 5K and Phase 5L and are
preserved on every Phase 5M stance, session, and workspace view. Phase 5M reads no
Phase 5J record directly and recomputes nothing; **heat is never a buy signal**.

## Relationship to Phase 5K (Horizon-aware Opportunity Queue)

Phase 5K produces the horizon-aware candidates (`HorizonCandidateView`) and the
**decision labels** (`trade_now`, `wait_for_pullback`, `research_more`,
`no_trade`, …) that Phase 5L carries onto each `ResearchPackRequest`. Phase 5M
reads those decision labels and the candidate's evidence gaps to derive the
agents' stances. The Phase 5K invariant — same ticker, different decisions per
horizon — is preserved: Phase 5M emits **one debate session per (ticker,
horizon)**.

## Relationship to Phase 5L (Auto Research Pack)

Phase 5L is the **direct input**. Each `ResearchPackBundle` (request + plan +
placeholder module results + status) becomes one `AgentDebateSession` and one
`DecisionWorkspaceView`. Phase 5M reads only the bundle's declarative content
(decision label, horizon, evidence gaps, review-only flag, bundle status). Because
Phase 5L executes nothing (`is_runtime_call=False`, `is_placeholder=True`), the
debate's evidence is **planned, not realized** — which is exactly why missing
evidence pushes the workspace toward `research_more` / `no_decision`.

---

## Why this is contract-only, not a live Agent runtime

The cockpit's value is auditability and safety. Phase 5M deliberately stops at the
*contract* boundary so that:

- the **debate structure** (roles, stances, conflicts, consensus) is
  deterministic, inspectable, and testable;
- **no live agent is invoked** — `AgentDebateParticipant.is_live_agent` and
  `AgentStanceRecord.is_live_agent_output` are hard-coded `False`;
- the decision workspace **summarizes** debate state but never executes anything —
  `DecisionWorkspaceView.is_executable_decision` is hard-coded `False` and
  `requires_human_review` is hard-coded `True`;
- the handoff into the Phase 5N Cockpit UI is a clean, schema-typed object.

No Phase 5M output is an order, an order ticket, a broker payload, or an execution
instruction. `approved_for_execution` never appears on any Phase 5M model and is
never positively authorized.

---

## Debate participant roles

Seven deterministic role records (`AGENT_ROLES`). They are **records, not live
agents**:

| Role | Responsibility |
|------|----------------|
| `bull` | Constructive case for the opportunity. |
| `bear` | Skeptical case against the opportunity. |
| `risk` | Risk / crowding / drawdown assessment; can downgrade the workspace state. |
| `critic` | Evidence referee; surfaces unresolved conflicts (never hides them). |
| `allocation` | Review-only sizing perspective; never an executable allocation. |
| `option` | Review-only option-expression perspective; `no_trade` is first-class. |
| `synthesis` | Consensus synthesizer; expressed through `DebateConsensusSummary`. |

The six **stance roles** (`DEBATE_STANCE_ROLES`) — bull / bear / risk / critic /
allocation / option — each emit an `AgentStanceRecord`. `synthesis` is expressed
through the consensus summary rather than a stance record.

---

## Stance labels

Each role uses its own label vocabulary; the union is `AgentStanceLabel`.

- **Bull** (`BullStanceLabel`): `constructive`, `bullish_with_conditions`,
  `wait_for_better_entry`, `insufficient_evidence`.
- **Bear** (`BearStanceLabel`): `overextended`, `valuation_risk`, `thesis_weak`,
  `crowded_trade`, `insufficient_evidence`.
- **Risk** (`RiskStanceLabel`): `acceptable`, `elevated`, `high`, `unacceptable`,
  `unknown`.
- **Critic** (`CriticStanceLabel`): `pass_with_warnings`, `needs_more_evidence`,
  `conflict_unresolved`, `reject_for_now`, `no_decision`.
- **Allocation** (`AllocationStanceLabel`): `no_allocation`, `watchlist_only`,
  `small_starter`, `position_candidate`, `avoid`.
- **Option** (`OptionStanceLabel`): `no_trade`, `stock_preferred`,
  `option_candidate`, `insufficient_liquidity`, `event_risk_too_high`.

Each `AgentStanceRecord` preserves: `agent_role`, `ticker`, `theme_id` /
`theme_name`, `horizon`, `stance_label`, `confidence`, `key_claims`,
`supporting_evidence_refs`, `missing_evidence_refs`, `missing_evidence_reasons`,
`risks`, `invalidation_conditions`, `review_triggers`,
`source_research_pack_ids`, `warnings`, and a `created_from_fixture` /
`is_live_agent_output=False` provenance pair.

---

## Bull / Bear / Risk / Critic semantics

- **Bull** reads the Phase 5K decision label optimistically. A strongly
  constructive label (`trade_now`, `position_candidate`, `investment_candidate`,
  `thesis_durable`) with no incomplete-evidence gap yields `constructive`; the
  same label with an incomplete / unconfirmed-fundamentals gap yields
  `bullish_with_conditions`; wait-style labels yield `wait_for_better_entry`;
  research / no-trade / degraded states yield `insufficient_evidence`.
- **Bear** reads the same inputs skeptically. `too_extended` → `overextended`; a
  crowding gap or `avoid_too_crowded` → `crowded_trade`; a valuation-stretch gap
  or `quality_but_expensive` / `watch_for_valuation` → `valuation_risk`;
  `no_trade` / `thesis_unconfirmed` / `thesis_insufficient` → `thesis_weak`. When
  nothing is flagged, the bear concedes with `insufficient_evidence` (no bear
  case) — so a genuinely clean constructive candidate does **not** manufacture a
  conflict.
- **Risk** can **downgrade** the workspace state. `avoid_too_crowded` →
  `unacceptable`; `no_trade` or a high-severity crowding gap → `high`;
  `too_extended` / crowding / valuation gap → `elevated`; a clean constructive
  candidate → `acceptable`; degraded / research states → `unknown`. A `high` /
  `unacceptable` risk read on an otherwise-constructive decision downgrades the
  workspace status to `wait_for_pullback` (or `research_more`).
- **Critic** is the evidence referee. Insufficient evidence →
  `needs_more_evidence`; review-only no-trade → `reject_for_now`; an unresolved
  bull/bear or risk-override conflict → `conflict_unresolved`; otherwise
  `pass_with_warnings`. The critic **never hides** an unresolved conflict:
  `CriticReviewView.hides_unresolved_conflict` is hard-coded `False`, and
  `acknowledged_conflict_ids` / `unresolved_conflict_count` mirror the session's
  conflict records.

---

## Allocation / Option perspective boundaries

Both are **review-only planning** perspectives:

- **Allocation** maps consensus + risk to a sizing *posture*
  (`no_allocation` / `watchlist_only` / `small_starter` / `position_candidate` /
  `avoid`). `AllocationPerspectiveView.is_executable_allocation` is hard-coded
  `False`. No order / quantity-to-execute / broker / account field is declared.
  The allocation perspective **cannot create an executable allocation**.
- **Option** maps the case to an option *posture*. `no_trade` is preserved as a
  **first-class state** (it is the default and is never silently substituted with
  another strategy). `OptionPerspectiveView.is_executable_order` is hard-coded
  `False`. No option leg / order field is declared.

---

## Conflict handling

Disagreement is **explicit**, never hidden, via `DebateConflictRecord`:

- **`bull_bear_disagreement`** — bull is positive (`constructive` /
  `bullish_with_conditions`) while bear is actively opposing (`overextended` /
  `crowded_trade` / `valuation_risk` / `thesis_weak`). Sub-typed as
  `crowding_dispute` / `valuation_dispute` / `evidence_dispute`.
- **`risk_override`** — bull is positive while risk is `high` / `unacceptable`.
- **`option_disagreement`** — allocation suggests a position while option says
  `no_trade` (minor, expression-vehicle disagreement).

Conflicts default to `is_resolved=False`. Phase 5M does **not** silently resolve
disagreement; an unresolved conflict drives the workspace toward `research_more`
and the next action toward `escalate_to_human`. The critic acknowledges every
unresolved conflict.

---

## Consensus summary semantics

`DebateConsensusSummary.consensus_level` (`DEBATE_CONSENSUS_LEVELS`):

| Level | Meaning |
|-------|---------|
| `strong_consensus` | Bull constructive, bear has no case, risk acceptable, critic pass_with_warnings. |
| `moderate_consensus` | Roles mostly align, with caveats, and no conflicts. |
| `mixed` | Conflicts exist but are not decision-blocking on their own. |
| `conflict_unresolved` | A medium/high unresolved conflict (or critic `conflict_unresolved`) blocks a review-ready state. |
| `insufficient_evidence` | Evidence is insufficient (degraded / research / critic needs more evidence). |

The summary also reports `agreeing_roles`, `dissenting_roles`, `neutral_roles`,
`total_conflicts`, and `unresolved_conflict_count`.

---

## Decision Workspace states

`DecisionWorkspaceStatus` (`DECISION_WORKSPACE_STATUSES`) — **review states only,
not execution commands**:

`ready_for_review`, `research_more`, `wait_for_pullback`, `watchlist`,
`no_decision`, `no_trade`, `blocked`, `invalidated`, `unknown`.

Deterministic precedence: empty → `no_decision`; failed bundle → `invalidated`;
degraded bundle → `blocked`; review-only / no-trade decision → `no_trade`;
needs-more-evidence / unresolved-conflict / research decision → `research_more`;
high/unacceptable risk on a constructive/wait/watch decision → `wait_for_pullback`
(risk downgrade); wait decision → `wait_for_pullback`; watch decision →
`watchlist`; ready decision → `ready_for_review`; otherwise `unknown`.

The state is wrapped in a `DecisionWorkspaceRecommendationState`
(`is_executable=False`, `requires_human_review=True`, no `approved_for_execution`
field).

---

## Review-only next actions

`DecisionWorkspaceNextActionType`: `review`, `research_more`, `wait_for_pullback`,
`watch`, `skip`, `no_trade`, `escalate_to_human`. **None** of these is an order
instruction. An unresolved conflict on a `research_more` state escalates the next
action to `escalate_to_human` rather than forcing a decision.

---

## Evidence / missing evidence behavior

Phase 5M is **evidence-first**. Because the Phase 5L research pack is *planned*
(not executed), stances reference planned-module evidence
(`planned_module::<module>`) and record `missing_evidence_reasons` derived from the
research pack's evidence gaps. `DebateEvidenceCoverage` aggregates supporting vs.
missing accounting. Missing or insufficient evidence pushes the debate to
`needs_more_evidence` / `insufficient_evidence` and the workspace to
`research_more` — it never fabricates a decision.

---

## No-trade behavior

`no_trade` is first-class throughout: it is the default `OptionPerspectiveView`
stance, a valid `DecisionWorkspaceStatus`, and a valid review-only next action. A
review-only (no-trade / avoid) research pack yields an allocation `avoid`, an
option `no_trade`, a critic `reject_for_now`, and a workspace `no_trade` state —
with **no executable research-to-trade path**.

---

## Safe / degraded states

- **Empty research pack boundary** → safe empty workspace
  (`validation_summary.is_safe_empty == True`), no sessions, an `empty_pack`
  warning, and a `no_decision`-friendly posture.
- **Degraded upstream** (blocked bundle) → sessions marked `is_degraded`, stances
  `insufficient_evidence` with low confidence, consensus `insufficient_evidence`,
  workspace status `blocked` / `research_more`, `degraded_upstream` warnings; no
  analysis is fabricated.
- **Missing evidence** → `research_more` / `insufficient_evidence`.
- **Conflicting agent views** → never produce a final executable recommendation.

---

## Fixtures

Deterministic fixture builders:

- `build_default_agent_debate_workspace()` — full workspace from the Phase 5L
  default research pack bundle (exercises `strong_consensus`,
  `insufficient_evidence`, conflicts, and multiple workspace states).
- `build_degraded_agent_debate_workspace()` — from the degraded research pack
  bundle (research_more / blocked, insufficient-evidence stances).
- `build_empty_agent_debate_workspace()` — safe empty workspace from the empty
  research pack bundle.
- `build_conflict_agent_debate_session()` — bull `constructive` while bear /
  risk flag overextension / crowding; explicit unresolved conflicts.
- `build_no_trade_option_agent_debate_session()` — option `no_trade` first-class.
- `build_research_more_agent_debate_session()` — missing-evidence-driven
  `research_more`.

---

## Non-goals

- No real agent runtime; no Claude / OpenAI / LLM call; no live agent loop.
- No final buy/sell recommendation; no executable trading instruction / order
  ticket / broker payload / execution id / account id.
- No Auto Research runtime, Macro Dashboard, UI redesign, sidebar cleanup, or
  read-only shadow integration.
- No Phase 5N Cockpit UI v0.2 (a later, not-yet-started phase).
- No live data, LLM, or external API calls.
- No DB / vector store / production persistence.

---

## Guardrails

- Offline / mock-only, deterministic; schema / helper / view-model / fixture only.
- Every model sets `extra="forbid"`; no `approved_for_execution` or order-ticket
  field can be smuggled in via construction. `approved_for_execution` is **absent**
  (not declared) on every Phase 5M model and is never positively authorized.
- Participants carry `is_live_agent=False`; stances carry
  `is_live_agent_output=False`; allocation carries
  `is_executable_allocation=False`; option carries `is_executable_order=False`;
  the workspace view carries `is_executable_decision=False` and
  `requires_human_review=True`.
- Does not import or modify `app.py`, `pages/*`, `ui_utils.py`, Streamlit,
  `lib/workflow_state.py`, `lib/llm_orchestrator.py`, `lib/data_fetcher.py`,
  `.claude/agents/*`, or any live data-fetch / broker / order module.
- Does not read `research/.workflow_state.json`.
- Phase 4A is not wired in.

---

## Acceptance criteria

1. The default debate workspace builds deterministically from the Phase 5L default
   research pack (one session + one decision-workspace view per bundle).
2. Bull / Bear / Risk / Critic / Allocation / Option roles exist (plus a synthesis
   participant).
3. Agent stances preserve ticker / horizon / theme / source research-pack refs.
4. Conflict records appear when stances disagree (bull/bear, risk override).
5. The critic does not hide unresolved conflicts.
6. Risk can downgrade the decision-workspace state.
7. Option `no_trade` remains a first-class state.
8. The allocation perspective declares no executable allocation / order field.
9. A degraded research pack produces `research_more` / insufficient-evidence.
10. An empty research pack produces a safe `no_decision` / empty workspace.
11. The consensus summary supports all five required levels.
12. Decision-workspace next actions are review-only.
13. No `approved_for_execution=True` is positively authorized; no buy/sell/order
    fields are introduced; no forbidden imports; serialization is deterministic.
14. The test suite
    `scripts/test_reliability_phase_5m_agent_debate_workspace.py` passes; the
    Phase 5L and Phase 5K tests still pass.

---

## Future Phase 5N dependency

The next phase, **Phase 5N — Cockpit UI v0.2 Opportunity-first Redesign** (a
future, not-yet-started phase), will consume the Phase 5M decision-workspace views
as the structured input to the redesigned opportunity-first cockpit UI. Phase 5M
deliberately stops at the debate / decision-workspace contract so that the debate
state — and *whether* it leads to a decision — remains explicit, review-only, and
auditable. **Phase 5N has not started.**
