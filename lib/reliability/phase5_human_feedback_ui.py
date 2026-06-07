"""
lib/reliability/phase5_human_feedback_ui.py — Phase 5Q: Human Feedback UI v0.1.

Session-only / non-persistent / non-executable UI contracts for the Investment
Cockpit's Human Feedback / Review surface. These are **UI and transient-session
contracts only** — they are NOT a persistence layer.

Hard boundaries (enforced by validators + the ``extra="forbid"`` config):

* **Session-only** — every model carries ``is_session_only=True`` /
  ``is_persisted=False``. Nothing here is written to disk, DB, vector store,
  workflow state (``research/.workflow_state.json``), or any broker.
* **Non-executable** — no model declares ``approved_for_execution`` (absent by
  construction), and feedback actions / session records carry
  ``is_executable=False``. No order-ticket / broker-route / account-id /
  time-in-force / execution-id / quantity-to-execute field is declared.
* **No investment advice** — review-only feedback labels; the user reviews
  fixture-backed opportunities and decision-workspace outputs and records a
  *review intent* only.

Relationship to Phase 4M-F (Human Feedback Layer):
  Phase 4M-F (``lib/reliability/human_feedback_memory.py``) is the *memory* /
  audit-record contract (``HumanFeedbackMemoryRecord`` etc.). Phase 5Q is the
  *UI / session* layer above it — it does NOT write Phase 4M-F memory records;
  it only models the transient cockpit review surface. A future controlled
  phase (Phase 5R / shadow integration) could bridge these session records into
  the Phase 4M-F memory layer, but Phase 5Q deliberately does not.

This module is offline / deterministic. Cross-phase fixture builders are
imported lazily inside the fixture function to avoid package import cycles.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import stable_hash_payload

_DETERMINISTIC_TIMESTAMP_DEFAULT: str = "1970-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Literal aliases
# ---------------------------------------------------------------------------

HumanFeedbackActionType = Literal[
    "accept_for_watchlist",
    "reject",
    "modify_thesis",
    "request_more_research",
    "wait_for_pullback",
    "manually_executed_outside_system",
    "skip",
    "review_later",
    "no_trade_confirmed",
]

# Canonical display order for the review-action vocabulary.
HUMAN_FEEDBACK_ACTIONS: tuple[HumanFeedbackActionType, ...] = (
    "accept_for_watchlist",
    "reject",
    "modify_thesis",
    "request_more_research",
    "wait_for_pullback",
    "manually_executed_outside_system",
    "skip",
    "review_later",
    "no_trade_confirmed",
)

HumanFeedbackReviewTargetKind = Literal[
    "opportunity_candidate",
    "horizon",
    "decision_workspace",
    "agent_debate",
    "trade_allocation_plan",
    "option_overlay",
    "no_trade",
    "unknown",
]

# Action → semantic flags (kept tiny + explicit; everything else defaults).
_ACTION_FLAGS: dict[str, dict[str, bool]] = {
    "accept_for_watchlist": {"is_watchlist_only": True},
    "no_trade_confirmed": {"is_no_trade": True},
    "manually_executed_outside_system": {"is_manual_external": True},
}


def _norm_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _target_id(kind: str, *parts: Any) -> str:
    payload = {"kind": kind, "parts": [("" if p is None else str(p)) for p in parts]}
    return f"hft_{stable_hash_payload(payload, length=12)}"


# ---------------------------------------------------------------------------
# Safety banner (session-only / non-executable)
# ---------------------------------------------------------------------------

class HumanFeedbackSafetyBanner(BaseModel):
    """Static safety contract surfaced above the Phase 5Q feedback surface."""

    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1)
    is_session_only: bool = True
    is_persisted: bool = False
    is_non_executable: bool = True
    requires_human_review: bool = True
    no_broker_or_order: bool = True
    no_llm_or_external_api: bool = True
    no_investment_advice: bool = True

    @model_validator(mode="after")
    def _check(self) -> "HumanFeedbackSafetyBanner":
        if self.is_persisted:
            raise ValueError(
                "Phase 5Q feedback is session-only; is_persisted must be False."
            )
        if not self.is_session_only:
            raise ValueError("Phase 5Q feedback must be session-only.")
        if not self.is_non_executable:
            raise ValueError("Phase 5Q feedback must be non-executable.")
        return self


# ---------------------------------------------------------------------------
# Action view (review-only action vocabulary)
# ---------------------------------------------------------------------------

class HumanFeedbackActionView(BaseModel):
    """One review-only feedback action. Never executable."""

    model_config = ConfigDict(extra="forbid")
    action: HumanFeedbackActionType
    translation_key: str = Field(min_length=1)
    description: str = ""
    is_executable: bool = False
    requires_human_review: bool = True
    is_watchlist_only: bool = False
    is_no_trade: bool = False
    is_manual_external: bool = False

    @model_validator(mode="after")
    def _check(self) -> "HumanFeedbackActionView":
        if self.is_executable:
            raise ValueError(
                "Phase 5Q feedback actions are non-executable; is_executable must be False."
            )
        return self


# ---------------------------------------------------------------------------
# Review target (what a piece of feedback is bound to)
# ---------------------------------------------------------------------------

class HumanFeedbackReviewTarget(BaseModel):
    """A fixture-backed object the user can attach review feedback to.

    Carries the *visible connections* required by Phase 5Q: the selected
    opportunity candidate, its horizon, the decision-workspace status, agent
    debate consensus/conflicts, the trade/allocation plan review state, and the
    option-overlay / no_trade state. All fields are descriptive; none is an
    order field.
    """

    model_config = ConfigDict(extra="forbid")
    target_id: str = Field(min_length=1)
    target_kind: HumanFeedbackReviewTargetKind = "unknown"
    label: str = Field(min_length=1)
    ticker: Optional[str] = None
    theme_name: Optional[str] = None
    horizon: Optional[str] = None
    decision_label: Optional[str] = None
    workspace_status: Optional[str] = None
    consensus_level: Optional[str] = None
    conflict_count: Optional[int] = None
    unresolved_conflict_count: Optional[int] = None
    option_state: Optional[str] = None
    is_no_trade: bool = False
    trade_review_needed: Optional[bool] = None
    trade_status: Optional[str] = None
    next_action: Optional[str] = None
    detail: str = ""
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Form state (transient UI form binding)
# ---------------------------------------------------------------------------

class HumanFeedbackFormState(BaseModel):
    """Transient UI form binding — never persisted."""

    model_config = ConfigDict(extra="forbid")
    selected_target_id: Optional[str] = None
    selected_action: Optional[HumanFeedbackActionType] = None
    note: str = ""
    is_valid: bool = False
    validation_messages: list[str] = Field(default_factory=list)
    is_session_only: bool = True
    is_persisted: bool = False

    @model_validator(mode="after")
    def _check(self) -> "HumanFeedbackFormState":
        if self.is_persisted:
            raise ValueError("Phase 5Q form state is session-only; is_persisted must be False.")
        return self


# ---------------------------------------------------------------------------
# Session record (a single submitted review feedback, session-only)
# ---------------------------------------------------------------------------

class HumanFeedbackSessionRecord(BaseModel):
    """A single submitted review feedback held in transient session state.

    NOT a Phase 4M-F memory record and NOT persisted: it lives only in
    ``st.session_state`` for the lifetime of the browser session.
    """

    model_config = ConfigDict(extra="forbid")
    record_id: str = Field(min_length=1)
    target: HumanFeedbackReviewTarget
    action: HumanFeedbackActionType
    note: str = ""
    created_at: str = _DETERMINISTIC_TIMESTAMP_DEFAULT
    is_session_only: bool = True
    is_persisted: bool = False
    is_executable: bool = False
    requires_human_review: bool = True

    @model_validator(mode="after")
    def _check(self) -> "HumanFeedbackSessionRecord":
        if self.is_persisted:
            raise ValueError("Phase 5Q session records are session-only; is_persisted must be False.")
        if self.is_executable:
            raise ValueError("Phase 5Q session records are non-executable; is_executable must be False.")
        return self


# ---------------------------------------------------------------------------
# Validation summary
# ---------------------------------------------------------------------------

class HumanFeedbackValidationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_count: int = 0
    target_count: int = 0
    session_record_count: int = 0
    target_kinds: list[str] = Field(default_factory=list)
    is_session_only: bool = True
    is_persisted: bool = False
    no_execution_authorized: bool = True
    no_broker_or_order: bool = True
    no_order_ticket_fields: bool = True
    approved_for_execution_absent: bool = True
    issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "HumanFeedbackValidationSummary":
        if self.is_persisted:
            raise ValueError("Phase 5Q validation summary is session-only; is_persisted must be False.")
        if not self.no_execution_authorized:
            raise ValueError("Phase 5Q does not authorize execution.")
        return self


# ---------------------------------------------------------------------------
# Top-level UI state
# ---------------------------------------------------------------------------

class HumanFeedbackUIState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ui_state_id: str = Field(min_length=1)
    safety_banner: HumanFeedbackSafetyBanner
    available_actions: list[HumanFeedbackActionView] = Field(default_factory=list)
    review_targets: list[HumanFeedbackReviewTarget] = Field(default_factory=list)
    form_state: HumanFeedbackFormState = Field(default_factory=HumanFeedbackFormState)
    session_records: list[HumanFeedbackSessionRecord] = Field(default_factory=list)
    validation_summary: Optional[HumanFeedbackValidationSummary] = None
    is_session_only: bool = True
    is_persisted: bool = False

    @model_validator(mode="after")
    def _check(self) -> "HumanFeedbackUIState":
        if self.is_persisted:
            raise ValueError("Phase 5Q UI state is session-only; is_persisted must be False.")
        return self


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_human_feedback_safety_banner(message: Optional[str] = None) -> HumanFeedbackSafetyBanner:
    return HumanFeedbackSafetyBanner(
        message=message
        or (
            "Session-only review feedback — not persisted. No broker/order/execution, "
            "no LLM/external API, not investment advice."
        ),
    )


def build_human_feedback_action_views() -> list[HumanFeedbackActionView]:
    """Build the full review-only action vocabulary, in canonical order."""
    views: list[HumanFeedbackActionView] = []
    for action in HUMAN_FEEDBACK_ACTIONS:
        flags = _ACTION_FLAGS.get(action, {})
        views.append(
            HumanFeedbackActionView(
                action=action,
                translation_key=f"cockpit_review_action_{action}",
                is_executable=False,
                requires_human_review=True,
                **flags,
            )
        )
    return views


def _opportunity_targets(queue: Any) -> list[HumanFeedbackReviewTarget]:
    targets: list[HumanFeedbackReviewTarget] = []
    if queue is None:
        return targets
    # Actionable horizon queues plus the no-trade/avoid queue. Watch/research
    # queues are already represented by the decision-workspace targets, so they
    # are intentionally not duplicated here to keep the picker manageable.
    sections = (
        "short_term",
        "mid_term",
        "long_term",
        "no_trade_avoid",
    )
    for attr in sections:
        section = getattr(queue, attr, None)
        if section is None:
            continue
        for cand in getattr(section, "candidates", []) or []:
            ticker = _norm_str(getattr(cand, "ticker", None))
            horizon = _norm_str(getattr(cand, "horizon", None))
            decision = _norm_str(getattr(cand, "decision_label", None))
            theme = _norm_str(getattr(cand, "theme_name", None))
            next_action = _norm_str(getattr(getattr(cand, "next_action", None), "action", None))
            is_nt = attr == "no_trade_avoid" or decision in ("no_trade", "avoid_too_crowded")
            kind: HumanFeedbackReviewTargetKind = "no_trade" if is_nt else "opportunity_candidate"
            label = " · ".join(
                p for p in (ticker, horizon, decision) if p
            ) or (ticker or attr)
            targets.append(
                HumanFeedbackReviewTarget(
                    target_id=_target_id(kind, attr, ticker, horizon, decision),
                    target_kind=kind,
                    label=label,
                    ticker=ticker,
                    theme_name=theme,
                    horizon=horizon,
                    decision_label=decision,
                    next_action=next_action,
                    is_no_trade=bool(is_nt),
                )
            )
    return targets


def _decision_targets(workspace: Any) -> list[HumanFeedbackReviewTarget]:
    targets: list[HumanFeedbackReviewTarget] = []
    if workspace is None:
        return targets
    for view in getattr(workspace, "workspace_views", []) or []:
        ticker = _norm_str(getattr(view, "ticker", None))
        horizon = _norm_str(getattr(view, "horizon", None))
        theme = _norm_str(getattr(view, "theme_name", None))
        status = _norm_str(getattr(view, "status", None))
        decision = _norm_str(getattr(view, "decision_label", None))
        next_action = _norm_str(getattr(getattr(view, "next_action", None), "action", None))
        cs = getattr(view, "consensus_summary", None)
        consensus = _norm_str(getattr(cs, "consensus_level", None)) if cs is not None else None
        total_conflicts = getattr(cs, "total_conflicts", None) if cs is not None else None
        unresolved = getattr(cs, "unresolved_conflict_count", None) if cs is not None else None
        conflicts = getattr(view, "conflicts", None) or []
        conflict_count = (
            int(total_conflicts) if isinstance(total_conflicts, int) else len(conflicts)
        )
        unresolved_count = int(unresolved) if isinstance(unresolved, int) else None
        label = " · ".join(p for p in (ticker, horizon, status) if p) or (ticker or "decision")
        targets.append(
            HumanFeedbackReviewTarget(
                target_id=_target_id("decision_workspace", ticker, horizon, status),
                target_kind="decision_workspace",
                label=label,
                ticker=ticker,
                theme_name=theme,
                horizon=horizon,
                decision_label=decision,
                workspace_status=status,
                consensus_level=consensus,
                conflict_count=conflict_count,
                unresolved_conflict_count=unresolved_count,
                next_action=next_action,
                is_no_trade=status == "no_trade",
            )
        )
    return targets


def _trade_targets(portfolio: Any) -> list[HumanFeedbackReviewTarget]:
    targets: list[HumanFeedbackReviewTarget] = []
    if portfolio is None:
        return targets
    for plan in getattr(portfolio, "trade_plans", []) or []:
        ticker = _norm_str(getattr(plan, "target", None))
        status = _norm_str(getattr(plan, "status", None))
        action = _norm_str(getattr(plan, "action", None))
        horizon = _norm_str(getattr(plan, "horizon", None))
        rt = getattr(plan, "review_trigger", None)
        review_needed = getattr(rt, "review_needed", None) if rt is not None else None
        label = " · ".join(p for p in (ticker, action, status) if p) or (ticker or "trade plan")
        targets.append(
            HumanFeedbackReviewTarget(
                target_id=_target_id("trade_allocation_plan", ticker, action, status),
                target_kind="trade_allocation_plan",
                label=label,
                ticker=ticker,
                horizon=horizon,
                decision_label=action,
                trade_status=status,
                trade_review_needed=bool(review_needed) if review_needed is not None else None,
            )
        )
    return targets


def _option_targets(portfolio: Any) -> list[HumanFeedbackReviewTarget]:
    targets: list[HumanFeedbackReviewTarget] = []
    if portfolio is None:
        return targets
    for overlay in getattr(portfolio, "option_overlays", []) or []:
        ticker = _norm_str(getattr(overlay, "target", None))
        state = _norm_str(getattr(overlay, "state", None))
        status = _norm_str(getattr(overlay, "status", None))
        is_nt = bool(getattr(overlay, "is_no_trade", False))
        label = " · ".join(p for p in (ticker, state) if p) or (ticker or "option overlay")
        targets.append(
            HumanFeedbackReviewTarget(
                target_id=_target_id("option_overlay", ticker, state, status),
                target_kind="option_overlay",
                label=label,
                ticker=ticker,
                option_state=state,
                trade_status=status,
                is_no_trade=is_nt,
            )
        )
    return targets


def build_human_feedback_review_targets(
    *,
    opportunity_queue: Any = None,
    debate_workspace: Any = None,
    portfolio_view: Any = None,
) -> list[HumanFeedbackReviewTarget]:
    """Build review targets from whichever fixture views are provided.

    Duck-typed and defensive: a missing view simply contributes no targets.
    """
    targets: list[HumanFeedbackReviewTarget] = []
    targets.extend(_opportunity_targets(opportunity_queue))
    targets.extend(_decision_targets(debate_workspace))
    targets.extend(_trade_targets(portfolio_view))
    targets.extend(_option_targets(portfolio_view))
    return targets


def make_human_feedback_session_record_id(
    target_id: str,
    action: str,
    note: str,
    created_at: Optional[str] = None,
) -> str:
    payload = {
        "target_id": target_id,
        "action": action,
        "note": note or "",
        "created_at": created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT,
    }
    return f"hfu_{stable_hash_payload(payload, length=12)}"


def build_human_feedback_session_record(
    target: HumanFeedbackReviewTarget,
    action: HumanFeedbackActionType,
    note: str = "",
    created_at: Optional[str] = None,
) -> HumanFeedbackSessionRecord:
    ts = created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT
    record_id = make_human_feedback_session_record_id(
        target_id=target.target_id, action=action, note=note, created_at=ts
    )
    return HumanFeedbackSessionRecord(
        record_id=record_id,
        target=target,
        action=action,
        note=note or "",
        created_at=ts,
        is_session_only=True,
        is_persisted=False,
        is_executable=False,
        requires_human_review=True,
    )


def build_human_feedback_validation_summary(
    actions: list[HumanFeedbackActionView],
    targets: list[HumanFeedbackReviewTarget],
    session_records: list[HumanFeedbackSessionRecord],
) -> HumanFeedbackValidationSummary:
    kinds: list[str] = []
    for tgt in targets:
        if tgt.target_kind not in kinds:
            kinds.append(tgt.target_kind)
    issues: list[str] = []
    for action in actions:
        if action.is_executable:
            issues.append(f"action {action.action!r} marked executable")
    for rec in session_records:
        if rec.is_persisted:
            issues.append(f"session record {rec.record_id!r} marked persisted")
        if rec.is_executable:
            issues.append(f"session record {rec.record_id!r} marked executable")
    return HumanFeedbackValidationSummary(
        action_count=len(actions),
        target_count=len(targets),
        session_record_count=len(session_records),
        target_kinds=kinds,
        is_session_only=True,
        is_persisted=False,
        no_execution_authorized=True,
        no_broker_or_order=True,
        no_order_ticket_fields=True,
        approved_for_execution_absent=True,
        issues=issues,
    )


def build_human_feedback_ui_state(
    *,
    opportunity_queue: Any = None,
    debate_workspace: Any = None,
    portfolio_view: Any = None,
    session_records: Optional[list[HumanFeedbackSessionRecord]] = None,
    form_state: Optional[HumanFeedbackFormState] = None,
    ui_state_id: Optional[str] = None,
) -> HumanFeedbackUIState:
    actions = build_human_feedback_action_views()
    targets = build_human_feedback_review_targets(
        opportunity_queue=opportunity_queue,
        debate_workspace=debate_workspace,
        portfolio_view=portfolio_view,
    )
    records = list(session_records or [])
    summary = build_human_feedback_validation_summary(actions, targets, records)
    sid = ui_state_id or (
        "hfui_"
        + stable_hash_payload(
            {
                "targets": [t.target_id for t in targets],
                "actions": [a.action for a in actions],
            },
            length=12,
        )
    )
    return HumanFeedbackUIState(
        ui_state_id=sid,
        safety_banner=build_human_feedback_safety_banner(),
        available_actions=actions,
        review_targets=targets,
        form_state=form_state or HumanFeedbackFormState(),
        session_records=records,
        validation_summary=summary,
        is_session_only=True,
        is_persisted=False,
    )


def build_default_human_feedback_ui_state() -> HumanFeedbackUIState:
    """Deterministic fixture UI state built from Phase 5K / 5M / 5G fixtures.

    Cross-phase imports are lazy to avoid package import cycles.
    """
    from lib.reliability.phase5_opportunity_queue import (
        build_default_opportunity_queue_view,
    )
    from lib.reliability.phase5_agent_debate import (
        build_default_agent_debate_workspace,
    )
    from lib.reliability.phase5_demo_pack import build_default_cockpit_demo_pack

    queue = build_default_opportunity_queue_view()
    workspace = build_default_agent_debate_workspace()

    portfolio_view = None
    try:
        pack = build_default_cockpit_demo_pack()
        complete = None
        for scenario in pack.scenarios:
            if getattr(scenario.metadata, "scenario_kind", None) == "complete":
                complete = scenario
                break
        if complete is None and pack.scenarios:
            complete = pack.scenarios[0]
        if complete is not None:
            portfolio_view = complete.view_bundle.portfolio_cockpit_view
    except Exception:  # noqa: BLE001 — fixture stays usable without portfolio targets
        portfolio_view = None

    return build_human_feedback_ui_state(
        opportunity_queue=queue,
        debate_workspace=workspace,
        portfolio_view=portfolio_view,
    )


__all__ = [
    "HUMAN_FEEDBACK_ACTIONS",
    "HumanFeedbackActionType",
    "HumanFeedbackActionView",
    "HumanFeedbackFormState",
    "HumanFeedbackReviewTarget",
    "HumanFeedbackReviewTargetKind",
    "HumanFeedbackSafetyBanner",
    "HumanFeedbackSessionRecord",
    "HumanFeedbackUIState",
    "HumanFeedbackValidationSummary",
    "build_default_human_feedback_ui_state",
    "build_human_feedback_action_views",
    "build_human_feedback_review_targets",
    "build_human_feedback_safety_banner",
    "build_human_feedback_session_record",
    "build_human_feedback_ui_state",
    "build_human_feedback_validation_summary",
    "make_human_feedback_session_record_id",
]
