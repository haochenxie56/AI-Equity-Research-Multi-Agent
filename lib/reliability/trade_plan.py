"""
lib/reliability/trade_plan.py

Phase 3R-B: Trade Plan Drafting Agent Skeleton.

Design principles:
  - Standalone, deterministic, offline.
  - No live LLM calls, no live data fetching, no app integration.
  - No broker / order / execution behavior.
  - Consumes typed research artifacts from prior phases via source IDs.
  - Produces structured TradePlanDraft objects for:
      advisory entry, add, trim, target, stop reference, review trigger, horizon.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell recommendations, or
    individual security recommendations.
  - approved_for_execution is ALWAYS False. No pathway to set it True exists.
  - Mock/dry-run only; all outputs are explicitly evidence-aware.
  - Missing optional prior artifacts produce warnings, not crashes.
  - No-trade is a valid and complete output.

Relationship to Roadmap v4 Phase 3H:
  - Phase 3R-B implements the Trade Plan Drafting Agent skeleton specified
    in Roadmap v4 Phase 3H.
  - All price zones, risk controls, and review triggers are research-only
    advisory references. They are NOT executable orders.
  - approved_for_execution is permanently False (schema-enforced).

Phase 3R-B is part of the Roadmap v4 Phase 3 backfill sequence.

See docs/reliability_phase_3r_trade_plan.md for design.

Disclaimer: All outputs are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import ToolResult


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Literal type aliases (enums)
# ---------------------------------------------------------------------------

TradePlanStatus = Literal[
    "unknown",
    "draft",
    "complete",
    "needs_review",
    "blocked",
]

TradePlanActionType = Literal[
    "watch",
    "enter",
    "add",
    "trim",
    "hold",
    "exit",
    "no_trade",
    "unknown",
]

TradePlanHorizon = Literal[
    "short",
    "medium",
    "long",
    "multi_horizon",
    "unknown",
]

TradePlanTriggerType = Literal[
    "price_level",
    "valuation_gap",
    "technical_confirmation",
    "earnings",
    "catalyst",
    "news",
    "estimate_revision",
    "macro_regime",
    "thesis_invalidation",
    "risk_limit",
    "review_date",
    "unknown",
]

TradePlanRiskLevel = Literal[
    "low",
    "medium",
    "high",
    "unknown",
]

TradePlanEvidenceQuality = Literal[
    "unsupported",
    "weak",
    "adequate",
    "strong",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_TRADE_PLAN_TOOL_NAME: str = "trade_plan_report"
_TRADE_PLAN_METRIC_GROUP: str = "trade_plan_report"
_CALCULATION_VERSION: str = "trade_plan_report_v1"

# Active action types that require evidence support
_ACTIVE_ACTION_TYPES: frozenset[str] = frozenset({"enter", "add", "trim", "exit"})

# Adequate evidence quality levels
_ADEQUATE_EVIDENCE: frozenset[str] = frozenset({"adequate", "strong"})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TradePlanPriceZone(BaseModel):
    """
    Research-only advisory price zone or reference level.

    This is NOT an executable order price or a broker instruction.
    All bounds are research reference levels for analysis purposes only.
    """

    model_config = ConfigDict(extra="forbid")

    zone_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    trigger_type: TradePlanTriggerType = "unknown"
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    reference_price: Optional[float] = None
    rationale: str = ""
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "TradePlanPriceZone":
        for fn in ("zone_id", "label"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _check_bounds(self) -> "TradePlanPriceZone":
        if self.lower_bound is not None and self.lower_bound < 0:
            raise ValueError(f"lower_bound must be non-negative; got {self.lower_bound}.")
        if self.upper_bound is not None and self.upper_bound < 0:
            raise ValueError(f"upper_bound must be non-negative; got {self.upper_bound}.")
        if self.reference_price is not None and self.reference_price < 0:
            raise ValueError(
                f"reference_price must be non-negative; got {self.reference_price}."
            )
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError(
                f"lower_bound ({self.lower_bound}) must be <= upper_bound ({self.upper_bound})."
            )
        return self


class TradePlanRiskControl(BaseModel):
    """
    Research-only risk control reference for a trade plan draft.

    stop_reference and max_loss_reference are research-level references,
    NOT broker stop orders or margin calls. This model does not imply
    broker stop order placement or execution authorization.
    """

    model_config = ConfigDict(extra="forbid")

    risk_control_id: str = Field(min_length=1)
    stop_reference: Optional[float] = None
    invalidation_condition: str = ""
    max_loss_reference: Optional[float] = None
    risk_level: TradePlanRiskLevel = "unknown"
    review_required: bool = False
    rationale: str = ""
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "TradePlanRiskControl":
        v = self.risk_control_id
        if not v.strip():
            raise ValueError(f"'risk_control_id' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _check_numeric(self) -> "TradePlanRiskControl":
        if self.stop_reference is not None and self.stop_reference < 0:
            raise ValueError(
                f"stop_reference must be non-negative; got {self.stop_reference}."
            )
        if self.max_loss_reference is not None and self.max_loss_reference < 0:
            raise ValueError(
                f"max_loss_reference must be non-negative; got {self.max_loss_reference}."
            )
        return self


class TradePlanReviewTrigger(BaseModel):
    """
    A condition that, if met, requires re-evaluation of the trade plan.

    Not a trade signal or execution instruction — this is a research
    monitoring reference only.
    """

    model_config = ConfigDict(extra="forbid")

    trigger_id: str = Field(min_length=1)
    trigger_type: TradePlanTriggerType = "unknown"
    description: str = ""
    affected_horizon: TradePlanHorizon = "unknown"
    review_required: bool = True
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "TradePlanReviewTrigger":
        v = self.trigger_id
        if not v.strip():
            raise ValueError(f"'trigger_id' must not be whitespace-only; got {v!r}.")
        return self


class TradePlanDraft(BaseModel):
    """
    Research-only trade plan draft for one target and horizon.

    All price zones, risk controls, and review triggers in this draft
    are advisory research references ONLY. They do NOT constitute:
      - Buy/sell/hold recommendations
      - Executable orders or instructions
      - Broker, account, or execution authorizations
      - Investment advice

    approved_for_execution is ALWAYS False.
    No pathway to set it True exists in this skeleton.

    If action_type == 'no_trade', no_trade_reason must be non-empty.
    If action_type is enter/add/trim/exit, the plan is still non-executable.
    """

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    horizon: TradePlanHorizon = "unknown"
    action_type: TradePlanActionType = "unknown"
    thesis_summary: str = ""
    entry_zones: list[TradePlanPriceZone] = Field(default_factory=list)
    add_zones: list[TradePlanPriceZone] = Field(default_factory=list)
    trim_zones: list[TradePlanPriceZone] = Field(default_factory=list)
    target_zones: list[TradePlanPriceZone] = Field(default_factory=list)
    risk_controls: list[TradePlanRiskControl] = Field(default_factory=list)
    review_triggers: list[TradePlanReviewTrigger] = Field(default_factory=list)
    no_trade_reason: Optional[str] = None
    evidence_quality: TradePlanEvidenceQuality = "unknown"
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "TradePlanDraft":
        for fn in ("plan_id", "ticker"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _no_trade_requires_reason(self) -> "TradePlanDraft":
        if self.action_type == "no_trade" and not (self.no_trade_reason or "").strip():
            raise ValueError(
                "TradePlanDraft with action_type='no_trade' must have a "
                "non-empty no_trade_reason."
            )
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "TradePlanDraft":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-B. "
                "This layer does not authorize execution."
            )
        return self


class TradePlanInputBundle(BaseModel):
    """
    Input context bundle for one trade plan drafting pass.

    Holds optional prior-phase research artifacts for evidence tracing.
    All prior artifact fields are duck-typed (Any) — only source_ids and
    status attributes are read by the builder. Missing optional artifacts
    produce warnings, not crashes.

    This bundle is research context only. It does not contain or imply
    any execution authorization.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    as_of: str = ""
    decision_packet: Optional[Any] = None
    horizon_synthesis: Optional[Any] = None
    debate_report: Optional[Any] = None
    event_intelligence_report: Optional[Any] = None
    human_review_report: Optional[Any] = None
    validation_aggregate: Optional[Any] = None
    staleness_report: Optional[Any] = None
    critic_result: Optional[Any] = None
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "TradePlanInputBundle":
        v = self.target
        if not v.strip():
            raise ValueError(f"'target' must not be whitespace-only; got {v!r}.")
        return self


class TradePlanSummary(BaseModel):
    """
    Deterministic summary of one trade plan drafting pass.

    Computed from the list of TradePlanDraft objects and resolved status.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    status: TradePlanStatus = "unknown"
    plan_count: int = 0
    action_counts: dict[str, int] = Field(default_factory=dict)
    horizons_covered: list[str] = Field(default_factory=list)
    no_trade_count: int = 0
    review_trigger_count: int = 0
    high_risk_count: int = 0
    missing_evidence_count: int = 0
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "TradePlanSummary":
        v = self.target
        if not v.strip():
            raise ValueError(f"'target' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "TradePlanSummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-B. "
                "This layer does not authorize execution."
            )
        return self


class TradePlanReport(BaseModel):
    """
    Full trade plan drafting report for one analysis pass.

    Composes all TradePlanDraft objects into a single auditable research artifact.

    approved_for_execution is ALWAYS False. This report is a research
    artifact only and does not constitute investment advice or authorize
    any form of execution. No pathway to approve execution exists in
    Phase 3R-B.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    report_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    target: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: TradePlanStatus = "unknown"
    input_bundle: TradePlanInputBundle
    plans: list[TradePlanDraft] = Field(default_factory=list)
    summary: TradePlanSummary
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "TradePlanReport":
        for fn in ("report_id", "target", "run_id", "created_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "TradePlanReport":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3R-B. "
                "This layer does not authorize execution."
            )
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generator
# ---------------------------------------------------------------------------

def make_trade_plan_report_id(
    run_id: str,
    target: str,
    as_of: str,
) -> str:
    """Return a deterministic stable hash ID for a TradePlanReport."""
    payload = {"run_id": run_id, "target": target, "as_of": as_of}
    h = stable_hash_payload(payload, length=16)
    return f"tpr_{h}"


# ---------------------------------------------------------------------------
# Helper: status determination
# ---------------------------------------------------------------------------

def determine_trade_plan_status(
    plans: list[TradePlanDraft],
    human_review_report: Any = None,
) -> TradePlanStatus:
    """
    Derive TradePlanStatus from the list of plans and optional human review report.

    Priority (highest wins):
      blocked      — human_review_report.status == "blocked".
      needs_review — missing evidence for active plans (enter/add/trim/exit),
                     or any high-risk plan without adequate evidence.
      complete     — all plans pass a clean-check (no_trade with reason,
                     or advisory action with adequate/strong evidence, or
                     watch/hold type actions).
      draft        — plans exist but all action_type == "unknown".
      unknown      — no plans.

    Does not mutate any input. No network calls. No LLM calls.
    approved_for_execution is never implied by any status value.
    """
    if not plans:
        return "unknown"

    # blocked: human review says blocked
    if human_review_report is not None:
        hr_status = getattr(human_review_report, "status", None)
        if hr_status == "blocked":
            return "blocked"

    # needs_review: missing evidence for active actions, or high-risk without evidence
    for plan in plans:
        if plan.action_type in _ACTIVE_ACTION_TYPES:
            if plan.evidence_quality not in _ADEQUATE_EVIDENCE:
                return "needs_review"
        for rc in plan.risk_controls:
            if rc.risk_level == "high" and plan.evidence_quality not in _ADEQUATE_EVIDENCE:
                return "needs_review"

    # draft: all plans have unknown action type (no meaningful intent declared)
    if all(p.action_type == "unknown" for p in plans):
        return "draft"

    # complete: passed all checks above
    return "complete"


# ---------------------------------------------------------------------------
# Helper: source ID collection
# ---------------------------------------------------------------------------

def collect_trade_plan_source_ids(
    input_bundle: TradePlanInputBundle,
    plans: list[TradePlanDraft],
) -> list[str]:
    """
    Collect all source/evidence IDs from the input bundle and plans deterministically.

    Collection order:
      1. Bundle-level source_ids.
      2. Per-plan source_ids (in order).
      3. Per-plan entry_zones, add_zones, trim_zones, target_zones source_ids.
      4. Per-plan risk_controls source_ids.
      5. Per-plan review_triggers source_ids.

    Deduplicates preserving first-occurrence order.
    Does not mutate any input.
    """
    seen: set[str] = set()
    ids: list[str] = []

    def _add(eid: str) -> None:
        if eid and eid not in seen:
            seen.add(eid)
            ids.append(eid)

    for sid in input_bundle.source_ids:
        _add(sid)

    for plan in plans:
        for sid in plan.source_ids:
            _add(sid)
        for zone in [*plan.entry_zones, *plan.add_zones, *plan.trim_zones, *plan.target_zones]:
            for sid in zone.source_ids:
                _add(sid)
        for rc in plan.risk_controls:
            for sid in rc.source_ids:
                _add(sid)
        for rt in plan.review_triggers:
            for sid in rt.source_ids:
                _add(sid)

    return ids


# ---------------------------------------------------------------------------
# Private: warning generation
# ---------------------------------------------------------------------------

def _generate_trade_plan_warnings(
    input_bundle: TradePlanInputBundle,
    plans: list[TradePlanDraft],
) -> list[str]:
    """
    Generate derived (report-level) warnings for missing artifacts or low-quality evidence.

    Returns ONLY newly generated warnings — does NOT include bundle.warnings.
    Callers are responsible for combining with bundle.warnings when assembling
    the final report.warnings list.

    Does not crash on missing optional artifacts. Does not mutate inputs.
    """
    generated: list[str] = []

    # Missing optional prior artifacts
    if input_bundle.decision_packet is None:
        generated.append(
            "TradePlanInputBundle: decision_packet is missing. "
            "Trade plan drafts may lack decision rationale."
        )
    if input_bundle.horizon_synthesis is None:
        generated.append(
            "TradePlanInputBundle: horizon_synthesis is missing. "
            "Horizon coverage may be incomplete."
        )

    # Missing evidence for active plans
    for plan in plans:
        if plan.action_type in _ACTIVE_ACTION_TYPES:
            if plan.evidence_quality not in _ADEQUATE_EVIDENCE:
                generated.append(
                    f"TradePlanDraft '{plan.plan_id}' has action_type='{plan.action_type}' "
                    f"but evidence_quality='{plan.evidence_quality}'. "
                    "Manual review required."
                )

    # High-risk plans without adequate evidence
    for plan in plans:
        for rc in plan.risk_controls:
            if rc.risk_level == "high" and plan.evidence_quality not in _ADEQUATE_EVIDENCE:
                generated.append(
                    f"TradePlanDraft '{plan.plan_id}' has high-risk control "
                    f"'{rc.risk_control_id}' but evidence_quality='{plan.evidence_quality}'. "
                    "High-risk plans require adequate evidence."
                )

    if not plans:
        generated.append(
            "TradePlanReport has no plans. Status will be 'unknown'."
        )

    return generated


# ---------------------------------------------------------------------------
# Helper: summary builder
# ---------------------------------------------------------------------------

def summarize_trade_plans(
    target: str,
    status: TradePlanStatus,
    plans: list[TradePlanDraft],
    source_ids: list[str],
    extra_warnings: Optional[list[str]] = None,
) -> TradePlanSummary:
    """
    Build a deterministic TradePlanSummary from plans and status.

    extra_warnings: optional list of generated (report-level) warnings to include
    in top_warnings. Pass the combined output of bundle.warnings and
    _generate_trade_plan_warnings() here so they appear in the summary.

    top_warnings is assembled from plan.warnings + extra_warnings,
    deduplicated preserving first-occurrence order, capped at 5.

    Does not mutate inputs. approved_for_execution is always False.
    """
    # action_counts
    action_counts: dict[str, int] = {}
    for plan in plans:
        action_counts[plan.action_type] = action_counts.get(plan.action_type, 0) + 1

    # horizons_covered — union, deduplicated, preserving first-occurrence order
    seen_h: set[str] = set()
    horizons_covered: list[str] = []
    for plan in plans:
        if plan.horizon not in seen_h:
            seen_h.add(plan.horizon)
            horizons_covered.append(plan.horizon)

    # no_trade_count
    no_trade_count = sum(1 for p in plans if p.action_type == "no_trade")

    # review_trigger_count
    review_trigger_count = sum(len(p.review_triggers) for p in plans)

    # high_risk_count: plans with at least one high-risk control
    high_risk_count = sum(
        1
        for p in plans
        for rc in p.risk_controls
        if rc.risk_level == "high"
    )

    # missing_evidence_count: active plans without adequate evidence
    missing_evidence_count = sum(
        1
        for p in plans
        if p.action_type in _ACTIVE_ACTION_TYPES and p.evidence_quality not in _ADEQUATE_EVIDENCE
    )

    # top_warnings — plan warnings + extra_warnings, deduped, first 5
    all_warnings: list[str] = []
    for plan in plans:
        all_warnings.extend(plan.warnings)
    if extra_warnings:
        all_warnings.extend(extra_warnings)
    seen_w: set[str] = set()
    deduped_warnings: list[str] = []
    for w in all_warnings:
        if w not in seen_w:
            seen_w.add(w)
            deduped_warnings.append(w)
    top_warnings = deduped_warnings[:5]

    return TradePlanSummary(
        target=target,
        status=status,
        plan_count=len(plans),
        action_counts=action_counts,
        horizons_covered=horizons_covered,
        no_trade_count=no_trade_count,
        review_trigger_count=review_trigger_count,
        high_risk_count=high_risk_count,
        missing_evidence_count=missing_evidence_count,
        top_warnings=top_warnings,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Helper: main report builder
# ---------------------------------------------------------------------------

def build_trade_plan_report(
    input_bundle: TradePlanInputBundle,
    plans: list[TradePlanDraft],
    run_id: str,
    created_at: Optional[str] = None,
) -> TradePlanReport:
    """
    Build a complete TradePlanReport from the input bundle and pre-built plans.

    Steps:
      1. Extract human_review_report from input bundle (duck-typed).
      2. Generate derived warnings for missing artifacts and evidence quality issues.
      3. Assemble full report warnings (bundle.warnings + generated), deduplicated.
      4. Collect source IDs deterministically.
      5. Determine run status.
      6. Build summary — includes bundle and generated warnings in top_warnings.
      7. Build report with stable deterministic report_id.

    Deterministic: identical inputs → identical outputs.
    created_at defaults to input_bundle.as_of when not supplied (or run_id if
    as_of is empty), making the full report output deterministic without an
    explicit timestamp argument.
    Pass created_at explicitly to override (e.g. for tests or audit records).

    No network calls. No LLM calls. No mutation of inputs.
    Does not constitute investment advice.
    approved_for_execution is always False.
    """
    # 1. Extract human_review_report for status determination
    human_review_report = input_bundle.human_review_report

    # 2. Generated (derived) warnings
    generated_warnings = _generate_trade_plan_warnings(input_bundle, plans)

    # 3. Full report warnings = bundle.warnings + generated, deduplicated
    _raw_report_warnings = list(input_bundle.warnings) + generated_warnings
    seen_rw: set[str] = set()
    report_warnings: list[str] = []
    for w in _raw_report_warnings:
        if w not in seen_rw:
            seen_rw.add(w)
            report_warnings.append(w)

    # 4. Source IDs
    source_ids = collect_trade_plan_source_ids(input_bundle, plans)

    # 5. Status
    status = determine_trade_plan_status(plans, human_review_report)

    # 6. Summary — pass bundle + generated warnings so they appear in top_warnings
    _summary_extra = list(input_bundle.warnings) + generated_warnings
    summary = summarize_trade_plans(
        target=input_bundle.target,
        status=status,
        plans=plans,
        source_ids=source_ids,
        extra_warnings=_summary_extra,
    )

    # 7. Report ID — use as_of from bundle, fallback to run_id if empty
    _as_of = input_bundle.as_of or run_id
    report_id = make_trade_plan_report_id(
        run_id=run_id,
        target=input_bundle.target,
        as_of=_as_of,
    )

    # Deterministic created_at: derive from bundle.as_of unless explicitly supplied.
    _created_at = created_at if created_at is not None else _as_of

    return TradePlanReport(
        report_id=report_id,
        target=input_bundle.target,
        run_id=run_id,
        status=status,
        input_bundle=input_bundle,
        plans=plans,
        summary=summary,
        source_ids=source_ids,
        warnings=report_warnings,
        created_at=_created_at,
        calculation_version=_CALCULATION_VERSION,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Helper: ToolResult adapter
# ---------------------------------------------------------------------------

def trade_plan_tool_result_from_report(
    run_id: str,
    report: TradePlanReport,
    target: Optional[str] = None,
    calculation_version: str = _CALCULATION_VERSION,
) -> ToolResult:
    """
    Wrap a TradePlanReport as a ToolResult for evidence-aware pipelines.

    - tool_name is stable: "trade_plan_report".
    - target defaults to report.target.
    - outputs includes the full report (serialized), summary, and calculation_version.
    - evidence_id is deterministic and content-sensitive.
    - Does not mutate report.
    - approved_for_execution is always False in the payload.
    - No live execution implication.
    - Does not look like an order ticket; contains no order_id, broker_order,
      account_id, execution_status, or live order instruction.
    """
    _target: str = target or report.target

    _report_dict = report.model_dump()
    _summary_dict: dict[str, Any] = {
        "report_id": report.report_id,
        "target": report.target,
        "run_id": report.run_id,
        "status": report.status,
        "plan_count": report.summary.plan_count,
        "action_counts": report.summary.action_counts,
        "horizons_covered": report.summary.horizons_covered,
        "no_trade_count": report.summary.no_trade_count,
        "review_trigger_count": report.summary.review_trigger_count,
        "high_risk_count": report.summary.high_risk_count,
        "missing_evidence_count": report.summary.missing_evidence_count,
        "warning_count": len(report.warnings),
        "source_id_count": len(report.source_ids),
        "approved_for_execution": False,  # Always False
    }

    outputs: dict[str, Any] = {
        "report": _report_dict,
        "summary": _summary_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_TRADE_PLAN_TOOL_NAME,
        target=_target,
        metric_group=_TRADE_PLAN_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_TRADE_PLAN_TOOL_NAME,
        run_id=run_id,
        ticker=report.target if report.target else None,
        inputs={"as_of": report.input_bundle.as_of, "target": _target},
        outputs=outputs,
        description=(
            f"TradePlanReport for {report.target}: "
            f"status={report.status}, "
            f"plans={report.summary.plan_count}, "
            f"no_trade={report.summary.no_trade_count}, "
            f"review_triggers={report.summary.review_trigger_count}, "
            f"high_risk={report.summary.high_risk_count}, "
            f"missing_evidence={report.summary.missing_evidence_count}, "
            f"source_ids={len(report.source_ids)}, "
            f"warnings={len(report.warnings)}."
        ),
    )
