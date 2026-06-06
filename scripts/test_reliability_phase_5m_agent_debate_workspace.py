#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5m_agent_debate_workspace.py

Phase 5M — Agent Debate / Decision Workspace Contract — test suite.

Phase 5M structures agent debate and decision-workspace review AFTER a Phase 5L
research pack has been assembled. It is a contract only: it does NOT run real
agents, call any LLM/external API, fetch live data, persist anything, or produce
an executable trade/allocation/option decision. Agent roles are deterministic
records; the decision workspace is review-only.

This test verifies:
  - The default debate workspace builds from the Phase 5L default research pack.
  - Bull / Bear / Risk / Critic / Allocation / Option roles exist.
  - Agent stances preserve ticker / horizon / theme / source research pack refs.
  - Conflict records appear when stances disagree.
  - The Critic does not hide an unresolved conflict.
  - Risk can downgrade the decision-workspace state.
  - Option no_trade remains a first-class state.
  - The allocation perspective has no executable allocation / order field.
  - A degraded research pack produces research_more / insufficient-evidence.
  - An empty research pack produces a safe no_decision / empty workspace.
  - The consensus summary supports the required levels.
  - Decision-workspace next actions are review-only.
  - No approved_for_execution=True is positively authorized.
  - No buy/sell/order-ticket fields are introduced; no forbidden imports.
  - Serialization is deterministic.
  - Package exports are wired; documentation is present.
  - Phase 5L and Phase 5K shared exports still pass.

It does NOT spin up Streamlit and does NOT call any external API or LLM.

Usage:
    python3 scripts/test_reliability_phase_5m_agent_debate_workspace.py
"""

from __future__ import annotations

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


PASS = 0
FAIL = 0
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from lib.reliability.phase5_agent_debate import (  # noqa: E402
    AGENT_ROLES,
    DEBATE_CONSENSUS_LEVELS,
    DEBATE_STANCE_ROLES,
    DECISION_WORKSPACE_STATUSES,
    AgentDebateParticipant,
    AgentDebateRound,
    AgentDebateSession,
    AgentDebateWorkspace,
    AgentStanceRecord,
    AllocationPerspectiveView,
    BearCaseView,
    BullCaseView,
    CriticReviewView,
    DebateConflictRecord,
    DebateConsensusSummary,
    DebateEvidenceCoverage,
    DecisionWorkspaceNextAction,
    DecisionWorkspaceRecommendationState,
    DecisionWorkspaceSafetyBanner,
    DecisionWorkspaceValidationSummary,
    DecisionWorkspaceView,
    OptionPerspectiveView,
    RiskCaseView,
    build_agent_debate_workspace,
    build_conflict_agent_debate_session,
    build_debate_session_from_research_pack,
    build_decision_workspace_view,
    build_default_agent_debate_workspace,
    build_degraded_agent_debate_workspace,
    build_empty_agent_debate_workspace,
    build_no_trade_option_agent_debate_session,
    build_research_more_agent_debate_session,
    make_debate_session_id,
)
from lib.reliability.phase5_research_pack import (  # noqa: E402
    build_default_research_pack_bundle,
)

import lib.reliability as reliability_pkg  # noqa: E402

MODULE_PATH = os.path.join(
    _REPO_ROOT, "lib", "reliability", "phase5_agent_debate.py"
)
DOC_PATH = os.path.join(
    _REPO_ROOT,
    "docs",
    "reliability_phase_5m_agent_debate_decision_workspace.md",
)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Section 1 — Default debate workspace builds from default research pack
# ---------------------------------------------------------------------------

w = build_default_agent_debate_workspace()
check("1.1 default workspace is AgentDebateWorkspace",
      isinstance(w, AgentDebateWorkspace))
check("1.2 default workspace has an id", bool(w.workspace_id))
check("1.3 default workspace references source boundary id",
      bool(w.source_boundary_id))
check("1.4 default workspace references source queue id", bool(w.source_queue_id))
check("1.5 default workspace has sessions", len(w.sessions) >= 1)
check("1.6 sessions and views are 1:1",
      len(w.sessions) == len(w.workspace_views))
check("1.7 default workspace has a validation summary",
      isinstance(w.validation_summary, DecisionWorkspaceValidationSummary))
check("1.8 default workspace is not safe-empty",
      w.validation_summary is not None and not w.validation_summary.is_safe_empty)
check("1.9 schema_version set", w.schema_version == "phase5_agent_debate_v1")
check("1.10 every session is an AgentDebateSession",
      all(isinstance(s, AgentDebateSession) for s in w.sessions))
check("1.11 every view is a DecisionWorkspaceView",
      all(isinstance(v, DecisionWorkspaceView) for v in w.workspace_views))
# Built from the Phase 5L default bundle: one session per pack bundle.
boundary = build_default_research_pack_bundle()
check("1.12 one session per Phase 5L pack bundle",
      len(w.sessions) == len(boundary.pack_bundles))
# Deterministic across builds.
d1 = build_default_agent_debate_workspace().model_dump(mode="json")
d2 = build_default_agent_debate_workspace().model_dump(mode="json")
check("1.13 two default builds dump-equal", d1 == d2)
check("1.14 seven participant roles", len(AGENT_ROLES) == 7)
check("1.15 make_debate_session_id deterministic",
      make_debate_session_id("AAA", "t", "short_term", "trade_now")
      == make_debate_session_id("AAA", "t", "short_term", "trade_now"))


# ---------------------------------------------------------------------------
# Section 2 — Bull/Bear/Risk/Critic/Allocation/Option roles exist
# ---------------------------------------------------------------------------

sess0 = w.sessions[0]
check("2.1 session has 7 participants", len(sess0.participants) == 7)
participant_roles = {p.agent_role for p in sess0.participants}
for role in ("bull", "bear", "risk", "critic", "allocation", "option", "synthesis"):
    check(f"2.2 participant role {role} present", role in participant_roles)
check("2.3 participants are not live agents",
      all(p.is_live_agent is False for p in sess0.participants))
stance_roles = {s.agent_role for s in sess0.stances}
for role in DEBATE_STANCE_ROLES:
    check(f"2.4 stance role {role} present", role in stance_roles)
check("2.5 bull_case is BullCaseView", isinstance(sess0.bull_case, BullCaseView))
check("2.6 bear_case is BearCaseView", isinstance(sess0.bear_case, BearCaseView))
check("2.7 risk_case is RiskCaseView", isinstance(sess0.risk_case, RiskCaseView))
check("2.8 critic_review is CriticReviewView",
      isinstance(sess0.critic_review, CriticReviewView))
check("2.9 allocation_perspective is AllocationPerspectiveView",
      isinstance(sess0.allocation_perspective, AllocationPerspectiveView))
check("2.10 option_perspective is OptionPerspectiveView",
      isinstance(sess0.option_perspective, OptionPerspectiveView))
check("2.11 session has at least one debate round",
      len(sess0.rounds) >= 1 and isinstance(sess0.rounds[0], AgentDebateRound))
check("2.12 round holds the six stance records",
      len(sess0.rounds[0].stances) == len(DEBATE_STANCE_ROLES))


# ---------------------------------------------------------------------------
# Section 3 — Stances preserve ticker / horizon / theme / source pack refs
# ---------------------------------------------------------------------------

all_stances: list[AgentStanceRecord] = [s for sess in w.sessions for s in sess.stances]
check("3.1 every stance has a ticker", all(bool(s.ticker) for s in all_stances))
check("3.2 every stance has a horizon",
      all(s.horizon in ("short_term", "mid_term", "long_term") for s in all_stances))
check("3.3 every stance preserves theme_id",
      all(bool(s.theme_id) for s in all_stances))
check("3.4 every stance references a source research pack id",
      all(len(s.source_research_pack_ids) >= 1 for s in all_stances))
check("3.5 stance source pack id matches its session pack request",
      all(
          s.source_research_pack_ids[0] == sess.source_pack_request_id
          for sess in w.sessions
          for s in sess.stances
      ))
check("3.6 every stance is not live agent output",
      all(s.is_live_agent_output is False for s in all_stances))
check("3.7 every stance carries supporting OR missing evidence accounting",
      all(
          (len(s.supporting_evidence_refs) + len(s.missing_evidence_reasons)) >= 1
          for s in all_stances
      ))
check("3.8 stance ticker matches its session ticker",
      all(s.ticker == sess.ticker for sess in w.sessions for s in sess.stances))


# ---------------------------------------------------------------------------
# Section 4 — Conflict records appear when stances disagree
# ---------------------------------------------------------------------------

conflict = build_conflict_agent_debate_session()
check("4.1 conflict session is constructive on the bull side",
      conflict.bull_case is not None and conflict.bull_case.stance_label == "constructive")
check("4.2 conflict session bear flags overextension/crowding",
      conflict.bear_case is not None
      and conflict.bear_case.stance_label in ("crowded_trade", "overextended", "valuation_risk"))
check("4.3 conflict session risk is high/unacceptable",
      conflict.risk_case is not None
      and conflict.risk_case.stance_label in ("high", "unacceptable"))
check("4.4 conflict session has explicit conflict records",
      len(conflict.conflicts) >= 1
      and all(isinstance(c, DebateConflictRecord) for c in conflict.conflicts))
check("4.5 a bull/bear disagreement conflict is recorded",
      any(c.conflict_type == "bull_bear_disagreement" for c in conflict.conflicts))
check("4.6 a risk_override conflict is recorded",
      any(c.conflict_type == "risk_override" for c in conflict.conflicts))
check("4.7 conflicts are unresolved (not silently hidden/resolved)",
      all(c.is_resolved is False for c in conflict.conflicts))
check("4.8 default workspace surfaces at least one conflict",
      w.validation_summary is not None and w.validation_summary.total_conflicts >= 1)


# ---------------------------------------------------------------------------
# Section 5 — Critic does not hide unresolved conflict
# ---------------------------------------------------------------------------

cr = conflict.critic_review
unresolved_in_session = sum(1 for c in conflict.conflicts if not c.is_resolved)
check("5.1 critic acknowledges every unresolved conflict",
      cr is not None and cr.unresolved_conflict_count == unresolved_in_session)
check("5.2 critic lists acknowledged conflict ids",
      cr is not None and len(cr.acknowledged_conflict_ids) == unresolved_in_session)
check("5.3 critic hides_unresolved_conflict flag is False",
      cr is not None and cr.hides_unresolved_conflict is False)
check("5.4 critic stance is conflict_unresolved when conflict + risk elevated",
      cr is not None and cr.stance_label == "conflict_unresolved")
check("5.5 critic surfaces a conflict_unresolved warning",
      cr is not None and any(wn.warning_type == "conflict_unresolved" for wn in cr.warnings))
# Validation-summary level invariant.
check("5.6 validation summary asserts critic_hides_no_conflict",
      w.validation_summary is not None and w.validation_summary.critic_hides_no_conflict)


# ---------------------------------------------------------------------------
# Section 6 — Risk can downgrade decision workspace state
# ---------------------------------------------------------------------------

conflict_view = build_decision_workspace_view(conflict)
check("6.1 conflict workspace is not ready_for_review",
      conflict_view.status != "ready_for_review", detail=conflict_view.status)
check("6.2 conflict workspace requires human review",
      conflict_view.requires_human_review is True)
check("6.3 conflict workspace next action is review-only / escalation",
      conflict_view.next_action.action in (
          "research_more", "escalate_to_human", "wait_for_pullback"))
check("6.4 risk case can_downgrade_decision is True for high risk",
      conflict.risk_case is not None and conflict.risk_case.can_downgrade_decision is True)
# A constructive decision with high risk but no unresolved evidence gap downgrades
# to wait_for_pullback (risk override), proving risk downgrades the state.
from lib.reliability.phase5_agent_debate import _fixture_bundle, _fixture_gap  # noqa: E402
risk_only_bundle = _fixture_bundle(
    ticker="RKDWN", theme_id="theme_risk", theme_name="Risk Downgrade",
    horizon="short_term", decision="trade_now",
    gaps=[_fixture_gap("crowding_risk", "high",
                       "Crowded positioning.", ("price_volume_analysis", "risk_review"))],
    is_review_only=False,
)
risk_sess = build_debate_session_from_research_pack(risk_only_bundle)
risk_view = build_decision_workspace_view(risk_sess)
check("6.5 high-risk constructive candidate is downgraded (not ready_for_review)",
      risk_view.status in ("wait_for_pullback", "research_more"),
      detail=risk_view.status)


# ---------------------------------------------------------------------------
# Section 7 — Option no_trade remains first-class
# ---------------------------------------------------------------------------

nt = build_no_trade_option_agent_debate_session()
check("7.1 no_trade session option perspective is no_trade",
      nt.option_perspective is not None and nt.option_perspective.stance_label == "no_trade")
check("7.2 option perspective is_no_trade flag True",
      nt.option_perspective is not None and nt.option_perspective.is_no_trade is True)
check("7.3 option perspective is_executable_order is False",
      nt.option_perspective is not None and nt.option_perspective.is_executable_order is False)
nt_view = build_decision_workspace_view(nt)
check("7.4 no_trade workspace status is no_trade", nt_view.status == "no_trade")
check("7.5 no_trade workspace next action is no_trade",
      nt_view.next_action.action == "no_trade")
check("7.6 OptionPerspectiveView default stance is no_trade (first-class default)",
      OptionPerspectiveView(ticker="X", horizon="short_term").stance_label == "no_trade")


# ---------------------------------------------------------------------------
# Section 8 — Allocation perspective has no executable allocation/order fields
# ---------------------------------------------------------------------------

alloc_views = [sess.allocation_perspective for sess in w.sessions
               if sess.allocation_perspective is not None]
check("8.1 every allocation perspective is_executable_allocation is False",
      all(a.is_executable_allocation is False for a in alloc_views))
ALLOC_FORBIDDEN = {
    "order_type", "order_id", "quantity_to_execute", "shares", "notional",
    "position_size_to_execute", "broker_route", "account_id", "approved_for_execution",
}
alloc_fields = set(AllocationPerspectiveView.model_fields.keys())
check("8.2 AllocationPerspectiveView declares no executable field",
      not (alloc_fields & ALLOC_FORBIDDEN),
      detail=str(alloc_fields & ALLOC_FORBIDDEN))
check("8.3 AllocationPerspectiveView rejects executable kwargs (extra=forbid)",
      _raises(lambda: AllocationPerspectiveView(
          ticker="X", horizon="short_term", quantity_to_execute=100)))


# ---------------------------------------------------------------------------
# Section 9 — Degraded research pack produces research_more / insufficient
# ---------------------------------------------------------------------------

deg = build_degraded_agent_debate_workspace()
check("9.1 degraded workspace builds", isinstance(deg, AgentDebateWorkspace))
check("9.2 degraded workspace has sessions", len(deg.sessions) >= 1)
check("9.3 degraded sessions are marked degraded",
      all(s.is_degraded for s in deg.sessions))
check("9.4 degraded workspace statuses are research_more / blocked",
      all(v.status in ("research_more", "blocked") for v in deg.workspace_views),
      detail=str([v.status for v in deg.workspace_views]))
check("9.5 degraded consensus is insufficient_evidence",
      all(
          s.consensus_summary is not None
          and s.consensus_summary.consensus_level == "insufficient_evidence"
          for s in deg.sessions
      ))
check("9.6 degraded sessions carry degraded_upstream warnings",
      all(any(wn.warning_type == "degraded_upstream" for wn in s.warnings)
          for s in deg.sessions))
rm = build_research_more_agent_debate_session()
check("9.7 research_more session critic is needs_more_evidence",
      rm.critic_review is not None and rm.critic_review.stance_label == "needs_more_evidence")
rm_view = build_decision_workspace_view(rm)
check("9.8 research_more session workspace status is research_more",
      rm_view.status == "research_more")
check("9.9 research_more next action is research_more (review-only)",
      rm_view.next_action.action == "research_more")


# ---------------------------------------------------------------------------
# Section 10 — Empty research pack produces safe no_decision / empty workspace
# ---------------------------------------------------------------------------

emp = build_empty_agent_debate_workspace()
check("10.1 empty workspace builds", isinstance(emp, AgentDebateWorkspace))
check("10.2 empty workspace has no sessions / views",
      len(emp.sessions) == 0 and len(emp.workspace_views) == 0)
check("10.3 empty workspace is safe-empty",
      emp.validation_summary is not None and emp.validation_summary.is_safe_empty)
check("10.4 empty workspace carries an empty_pack warning",
      any(wn.warning_type == "empty_pack" for wn in emp.warnings))
check("10.5 empty workspace has a safety banner",
      isinstance(emp.safety_banner, DecisionWorkspaceSafetyBanner))


# ---------------------------------------------------------------------------
# Section 11 — Consensus summary supports required levels
# ---------------------------------------------------------------------------

check("11.1 five consensus levels defined", len(DEBATE_CONSENSUS_LEVELS) == 5)
for level in ("strong_consensus", "moderate_consensus", "mixed",
              "conflict_unresolved", "insufficient_evidence"):
    check(f"11.2 consensus level {level} supported", level in DEBATE_CONSENSUS_LEVELS)
# The default + fixtures exercise multiple levels.
default_levels = {
    s.consensus_summary.consensus_level
    for s in w.sessions
    if s.consensus_summary is not None
}
check("11.3 default workspace exercises strong_consensus",
      "strong_consensus" in default_levels, detail=str(sorted(default_levels)))
check("11.4 default workspace exercises insufficient_evidence",
      "insufficient_evidence" in default_levels)
check("11.5 conflict session consensus is conflict_unresolved",
      conflict.consensus_summary is not None
      and conflict.consensus_summary.consensus_level == "conflict_unresolved")
check("11.6 consensus summary reports unresolved conflict count",
      conflict.consensus_summary is not None
      and conflict.consensus_summary.unresolved_conflict_count >= 1)


# ---------------------------------------------------------------------------
# Section 12 — Decision workspace next actions are review-only
# ---------------------------------------------------------------------------

REVIEW_ONLY_ACTIONS = {
    "review", "research_more", "wait_for_pullback", "watch", "skip",
    "no_trade", "escalate_to_human",
}
all_views = list(w.workspace_views) + list(deg.workspace_views) + [
    conflict_view, nt_view, rm_view, risk_view
]
check("12.1 every workspace next action is review-only",
      all(v.next_action.action in REVIEW_ONLY_ACTIONS for v in all_views),
      detail=str(sorted({v.next_action.action for v in all_views})))
EXEC_VERBS = {"buy", "sell", "submit", "execute", "order", "place_order", "fill"}
check("12.2 no next action is an execution verb",
      all(v.next_action.action not in EXEC_VERBS for v in all_views))
check("12.3 every workspace status is a known DecisionWorkspaceStatus",
      all(v.status in DECISION_WORKSPACE_STATUSES for v in all_views))
check("12.4 every workspace view is non-executable",
      all(v.is_executable_decision is False for v in all_views))
check("12.5 every recommendation state requires human review + non-executable",
      all(v.recommendation_state.requires_human_review is True
          and v.recommendation_state.is_executable is False for v in all_views))
check("12.6 nine workspace statuses defined", len(DECISION_WORKSPACE_STATUSES) == 9)
for st in ("ready_for_review", "research_more", "wait_for_pullback", "watchlist",
           "no_decision", "no_trade", "blocked", "invalidated", "unknown"):
    check(f"12.7 status {st} supported", st in DECISION_WORKSPACE_STATUSES)


# ---------------------------------------------------------------------------
# Section 13 — No forbidden imports / determinism in module source
# ---------------------------------------------------------------------------

module_src = _read_text(MODULE_PATH)
FORBIDDEN_IMPORT_SUBSTRINGS = [
    "import streamlit", "import anthropic", "import openai", "from app",
    "import app\n", "lib.workflow_state", "lib.llm_orchestrator",
    "lib.data_fetcher", "from pages", "import requests", "import httpx",
    "import urllib", "yfinance", "polygon", "finnhub",
]
for sub in FORBIDDEN_IMPORT_SUBSTRINGS:
    check(f"13.1 module does not reference {sub!r}", sub not in module_src, detail=sub)
check("13.2 module does not read research/.workflow_state.json",
      ".workflow_state.json" not in module_src)
check("13.3 module does not open files for persistence",
      "open(" not in module_src and "Path(" not in module_src)
check("13.4 module does not use wall-clock time / randomness",
      "datetime.now" not in module_src and "time.time(" not in module_src
      and "import random" not in module_src)


# ---------------------------------------------------------------------------
# Section 14 — No approved_for_execution / order-ticket / buy-sell fields
# ---------------------------------------------------------------------------

ALL_MODELS = [
    DecisionWorkspaceSafetyBanner, DebateConflictRecord, DebateConsensusSummary,
    DebateEvidenceCoverage, AgentDebateParticipant, AgentStanceRecord,
    BullCaseView, BearCaseView, RiskCaseView, CriticReviewView,
    AllocationPerspectiveView, OptionPerspectiveView, AgentDebateRound,
    AgentDebateSession, DecisionWorkspaceNextAction,
    DecisionWorkspaceRecommendationState, DecisionWorkspaceView,
    DecisionWorkspaceValidationSummary, AgentDebateWorkspace,
]
FORBIDDEN_FIELDS = {
    "approved_for_execution", "order_type", "order_id", "time_in_force",
    "broker_route", "broker_payload", "account_id", "execution_id",
    "quantity_to_execute", "limit_price", "stop_price", "fill_price",
    "buy", "sell", "buy_now", "sell_now",
}
for m in ALL_MODELS:
    bad = set(m.model_fields.keys()) & FORBIDDEN_FIELDS
    check(f"14.1 {m.__name__} declares no forbidden field", not bad, detail=str(bad))

check("14.2 workspace rejects approved_for_execution kwarg (extra=forbid)",
      _raises(lambda: AgentDebateWorkspace(
          workspace_id="x", approved_for_execution=True)))
check("14.3 session rejects approved_for_execution kwarg (extra=forbid)",
      _raises(lambda: AgentDebateSession(
          session_id="x", ticker="AAA", horizon="short_term",
          approved_for_execution=True)))
check("14.4 view rejects approved_for_execution kwarg (extra=forbid)",
      _raises(lambda: DecisionWorkspaceView(
          workspace_view_id="x", ticker="AAA", horizon="short_term",
          approved_for_execution=True)))

dump_str = json.dumps(d1).lower()
check("14.5 serialized default workspace does not authorize approved_for_execution",
      '"approved_for_execution": true' not in dump_str
      and '"approved_for_execution":true' not in dump_str
      and '"approved_for_execution":' not in dump_str)
check("14.6 serialized default workspace has no order-ticket fields",
      '"order_type"' not in dump_str and '"broker_route"' not in dump_str
      and '"account_id"' not in dump_str and '"time_in_force"' not in dump_str)
check("14.7 validation summary asserts execution-safety invariants",
      w.validation_summary is not None
      and w.validation_summary.no_executable_order_fields
      and w.validation_summary.approved_for_execution_absent
      and w.validation_summary.no_live_agent_calls
      and w.validation_summary.no_final_recommendation
      and w.validation_summary.all_stances_fixture)
check("14.8 safety banner asserts no_execution_authorized + no_orders + review",
      w.safety_banner.no_execution_authorized is True
      and w.safety_banner.no_orders is True
      and w.safety_banner.no_final_recommendation is True
      and w.safety_banner.requires_human_review is True)


# ---------------------------------------------------------------------------
# Section 15 — Serialization deterministic + round-trip
# ---------------------------------------------------------------------------

j1 = json.dumps(d1, sort_keys=True)
j2 = json.dumps(build_default_agent_debate_workspace().model_dump(mode="json"),
                sort_keys=True)
check("15.1 JSON serialization deterministic across builds", j1 == j2)
rt = AgentDebateWorkspace.model_validate(d1)
check("15.2 round-trip re-validates", isinstance(rt, AgentDebateWorkspace))
check("15.3 round-trip dump-equal", rt.model_dump(mode="json") == d1)
# View derivation deterministic.
v_a = build_decision_workspace_view(conflict).model_dump(mode="json")
v_b = build_decision_workspace_view(build_conflict_agent_debate_session()).model_dump(mode="json")
check("15.4 decision workspace view deterministic", v_a == v_b)


# ---------------------------------------------------------------------------
# Section 16 — Package exports wired
# ---------------------------------------------------------------------------

EXPECTED_EXPORTS = [
    "AgentDebateWorkspace",
    "AgentDebateSession",
    "AgentDebateRound",
    "AgentDebateParticipant",
    "AgentStanceRecord",
    "BullCaseView",
    "BearCaseView",
    "RiskCaseView",
    "CriticReviewView",
    "AllocationPerspectiveView",
    "OptionPerspectiveView",
    "DebateConflictRecord",
    "DebateConsensusSummary",
    "DebateEvidenceCoverage",
    "DecisionWorkspaceView",
    "DecisionWorkspaceStatus",
    "DecisionWorkspaceRecommendationState",
    "DecisionWorkspaceNextAction",
    "DecisionWorkspaceSafetyBanner",
    "DecisionWorkspaceValidationSummary",
    "build_agent_debate_workspace",
    "build_debate_session_from_research_pack",
    "build_bull_case_view",
    "build_bear_case_view",
    "build_risk_case_view",
    "build_critic_review_view",
    "build_allocation_perspective_view",
    "build_option_perspective_view",
    "build_debate_consensus_summary",
    "build_decision_workspace_view",
    "build_decision_workspace_validation_summary",
    "build_default_agent_debate_workspace",
    "build_degraded_agent_debate_workspace",
    "build_empty_agent_debate_workspace",
]
for name in EXPECTED_EXPORTS:
    check(f"16.1 lib.reliability exports {name!r}", hasattr(reliability_pkg, name))
    check(f"16.2 {name!r} in lib.reliability.__all__", name in reliability_pkg.__all__)


# ---------------------------------------------------------------------------
# Section 17 — Documentation present with required sections
# ---------------------------------------------------------------------------

check("17.1 Phase 5M doc exists", os.path.isfile(DOC_PATH), detail=DOC_PATH)
doc = _read_text(DOC_PATH) if os.path.isfile(DOC_PATH) else ""
dlc = doc.lower()
REQUIRED_DOC_TOPICS = [
    "Purpose", "Phase 5I", "Phase 5J", "Phase 5K", "Phase 5L",
    "contract-only", "participant", "bull", "bear", "risk", "critic",
    "allocation", "option", "synthesis", "stance label", "conflict",
    "consensus", "decision workspace", "review-only", "no_trade",
    "research_more", "no_decision", "evidence", "degraded",
    "Non-goals", "Guardrails", "Acceptance criteria", "Phase 5N",
]
for topic in REQUIRED_DOC_TOPICS:
    check(f"17.2 Phase 5M doc covers {topic!r}", topic in doc or topic.lower() in dlc)
check("17.3 doc keeps approved_for_execution False/absent",
      "approved_for_execution" in doc and ("false" in dlc or "absent" in dlc))
check("17.4 doc keeps Phase 5N as a future dependency, not started",
      "phase 5n" in dlc and ("future" in dlc or "not started" in dlc
                             or "later" in dlc or "next" in dlc))


# ---------------------------------------------------------------------------
# Section 18 — Phase 5L / Phase 5K shared regression (exports still importable)
# ---------------------------------------------------------------------------

check("18.1 Phase 5L default research pack still builds",
      len(build_default_research_pack_bundle().pack_bundles) >= 1)
check("18.2 Phase 5L exports still present on package",
      hasattr(reliability_pkg, "build_default_research_pack_bundle")
      and hasattr(reliability_pkg, "AutoResearchPackOrchestrationBoundary"))
check("18.3 Phase 5K exports still present on package",
      hasattr(reliability_pkg, "build_default_opportunity_queue_view")
      and hasattr(reliability_pkg, "HorizonAwareOpportunityQueueView"))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("Phase 5M — Agent Debate / Decision Workspace Contract — test results")
print("=" * 70)

if _failures:
    print()
    for line in _failures:
        print(line)

print()
print(f"Passed: {PASS}")
print(f"Failed: {FAIL}")
print(f"Total:  {PASS + FAIL}")
print()

if FAIL == 0:
    print("RESULT: PASS — Phase 5M agent debate / decision workspace contract verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
