"""
lib/reliability/phase5_research_pack.py

Phase 5L: Auto Research Pack Orchestration Boundary.

Purpose
-------
Define the **deterministic contracts** for how a future Investment Cockpit
agent will convert Phase 5K opportunity-queue candidates into structured
research-pack requests and research-pack bundles:

    Phase 5K Opportunity Queue candidate
      -> ResearchPackRequest        (what to research, and why)
      -> ResearchPackPlan           (which conceptual modules, in what order)
      -> ResearchPackBundle/Status  (placeholder result refs + status)
      -> (future) Agent Debate / Decision Packet input  (Phase 5M+)

This module defines the **boundary only**. It does **not**:

- run company research, financial analysis, price-volume analysis, news
  fetches, catalyst/earnings lookups, macro/theme/sector/scanner analysis, or
  any other research module;
- call any LLM or external API;
- fetch any live data;
- read the live workflow state JSON;
- introduce any database / vector store / production persistence;
- introduce any broker / order / execution capability;
- produce a final buy/sell recommendation or an executable trading instruction.

Module requests are **descriptive placeholders** (``is_runtime_call=False``);
module result references are **placeholders** (``is_placeholder=True``,
``result_ref=None``) — never generated analysis.

Product principles preserved
----------------------------
- The Investment Cockpit is **opportunity-first**; candidates come from the
  Phase 5K Opportunity Queue.
- A Research Pack is **automatically assembled** based on horizon, theme,
  evidence gaps, entry-quality needs, and the Phase 5K decision label.
- The Research Pack uses the original app modules as **conceptual source
  modules**, but does **not** call them in this phase.
- A Research Pack output is **not** a final decision. Agent Debate / Decision
  Packet comes later (Phase 5M+).

Source module taxonomy (conceptual only)
----------------------------------------
``macro_context``, ``theme_context``, ``sector_context``, ``scanner_context``,
``company_research``, ``financial_analysis``, ``price_volume_analysis``,
``news_sentiment``, ``catalyst_earnings``, ``risk_review``,
``evidence_validation``.

Safety invariants (by construction)
-----------------------------------
- Every model sets ``extra="forbid"`` — no ``approved_for_execution`` or
  order-ticket field can be smuggled in via construction.
- No model declares ``approved_for_execution`` (it is absent, not False-only),
  no buy/sell field, and no executable order field.
- Module requests carry ``is_runtime_call=False``; module result refs carry
  ``is_placeholder=True`` and never fabricate analysis.

Disclaimer: outputs are for research / educational purposes only and do not
constitute investment advice.

See ``docs/reliability_phase_5l_auto_research_pack_orchestration_boundary.md``.
"""

from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from lib.reliability.phase5_theme_intelligence import ThemeRiskSeverity
from lib.reliability.phase5_opportunity_queue import (
    HorizonAwareOpportunityQueueView,
    HorizonCandidateView,
    OpportunityDecisionLabel,
    OpportunityHorizon,
    build_default_opportunity_queue_view,
    build_degraded_opportunity_queue_view,
    build_empty_opportunity_queue_view,
)

_SCHEMA_VERSION: str = "phase5_research_pack_v1"


# ---------------------------------------------------------------------------
# Literal aliases
# ---------------------------------------------------------------------------

# The eleven conceptual source modules a research pack may request. These map
# to original-app capabilities but are NEVER called in Phase 5L.
ResearchPackSourceModule = Literal[
    "macro_context",
    "theme_context",
    "sector_context",
    "scanner_context",
    "company_research",
    "financial_analysis",
    "price_volume_analysis",
    "news_sentiment",
    "catalyst_earnings",
    "risk_review",
    "evidence_validation",
]

# Canonical ordering used for deterministic module-list emission.
RESEARCH_PACK_SOURCE_MODULES: tuple[ResearchPackSourceModule, ...] = (
    "macro_context",
    "theme_context",
    "sector_context",
    "scanner_context",
    "company_research",
    "financial_analysis",
    "price_volume_analysis",
    "news_sentiment",
    "catalyst_earnings",
    "risk_review",
    "evidence_validation",
)

# Status of a single conceptual module within a pack. Phase 5L mostly produces
# ``planned`` (default fixture) and ``blocked`` (degraded fixture).
ResearchModuleStatus = Literal[
    "planned",
    "waiting_for_data",
    "partial",
    "complete",
    "blocked",
    "skipped",
    "failed",
    "unknown",
]

# Status of a whole research pack (or the orchestration boundary).
ResearchPackStatus = Literal[
    "planned",
    "waiting_for_data",
    "partial",
    "complete",
    "blocked",
    "skipped",
    "failed",
    "unknown",
]

RESEARCH_PACK_STATUSES: tuple[ResearchPackStatus, ...] = (
    "planned",
    "waiting_for_data",
    "partial",
    "complete",
    "blocked",
    "skipped",
    "failed",
    "unknown",
)

# Priority of a research pack / module request.
ResearchPackPriority = Literal["low", "normal", "elevated", "high", "unknown"]

# Why a research pack (or module) was triggered.
ResearchPackTriggerReason = Literal[
    "short_term_timing",
    "mid_term_position_building",
    "long_term_durability",
    "evidence_gap",
    "entry_quality_check",
    "crowding_risk_check",
    "valuation_check",
    "macro_validation",
    "decision_label_followup",
    "watch_wait_monitor",
    "no_trade_review_only",
    "unknown",
]

# Kinds of evidence gap a research pack may need to close.
ResearchPackEvidenceGapType = Literal[
    "incomplete_evidence",
    "missing_fundamental_confirmation",
    "narrative_only",
    "crowding_risk",
    "valuation_stretch",
    "late_cycle",
    "unconfirmed_fundamentals",
    "needs_macro_validation",
    "entry_quality",
    "unknown",
]

# Non-fatal warning types attached to a request / bundle / boundary.
ResearchPackWarningType = Literal[
    "missing_module_ref",
    "missing_candidate_field",
    "degraded_upstream",
    "evidence_gap",
    "no_trade_review_only",
    "empty_queue",
    "unknown",
]


# ---------------------------------------------------------------------------
# Deterministic id helpers (no timestamp, no randomness)
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    out: list[str] = []
    prev_us = False
    for ch in str(text).strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
                prev_us = True
    return "".join(out).strip("_") or "x"


def _short_hash(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:8]


def _dedup(seq) -> list:
    """Order-preserving de-duplication."""
    seen: set = set()
    out: list = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def make_research_pack_request_id(
    ticker: str, theme_id: str, horizon: str, decision: str
) -> str:
    """Deterministic, content-sensitive research-pack request id."""
    payload = f"rpreq::{ticker}::{theme_id}::{horizon}::{decision}"
    return f"rpreq_{_slug(ticker)}_{_slug(horizon)}_{_short_hash(payload)}"


def make_research_pack_bundle_id(pack_request_id: str) -> str:
    """Deterministic research-pack bundle id derived from the request id."""
    return f"rpbundle_{_short_hash('rpbundle::' + str(pack_request_id))}"


def make_auto_research_pack_boundary_id(label: str) -> str:
    """Deterministic orchestration-boundary id from a stable label."""
    return f"arpb_{_slug(label)}_{_short_hash('arpb::' + str(label))}"


def make_opportunity_candidate_ref(
    theme_id: str, ticker: str, horizon: str, decision: str
) -> str:
    """Deterministic reference back to a Phase 5K opportunity candidate.

    Phase 5K ``HorizonCandidateView`` objects do not carry their own ids, so
    this builds a stable, content-sensitive reference string keyed by
    ``(theme_id, ticker, horizon, decision)``.
    """
    payload = f"oppcand::{theme_id}::{ticker}::{horizon}::{decision}"
    return f"oppcand_{_slug(ticker)}_{_slug(horizon)}_{_short_hash(payload)}"


# ---------------------------------------------------------------------------
# Deterministic rule tables (fixture/helper only)
# ---------------------------------------------------------------------------

# Required / optional conceptual modules per horizon (the Phase 5L contract).
_HORIZON_REQUIRED: dict[OpportunityHorizon, tuple[ResearchPackSourceModule, ...]] = {
    "short_term": (
        "price_volume_analysis",
        "news_sentiment",
        "catalyst_earnings",
        "risk_review",
        "evidence_validation",
    ),
    "mid_term": (
        "company_research",
        "financial_analysis",
        "price_volume_analysis",
        "catalyst_earnings",
        "risk_review",
        "evidence_validation",
    ),
    "long_term": (
        "macro_context",
        "theme_context",
        "company_research",
        "financial_analysis",
        "risk_review",
        "evidence_validation",
    ),
}

_HORIZON_OPTIONAL: dict[OpportunityHorizon, tuple[ResearchPackSourceModule, ...]] = {
    "short_term": ("company_research", "financial_analysis"),
    "mid_term": ("news_sentiment", "macro_context"),
    "long_term": ("price_volume_analysis", "catalyst_earnings"),
}

# Review-only packs (no_trade / avoid) get a minimal, non-executable module set.
_REVIEW_ONLY_REQUIRED: tuple[ResearchPackSourceModule, ...] = (
    "risk_review",
    "evidence_validation",
)

# Decision labels that route to a review-only minimal pack (no trade path).
_REVIEW_ONLY_DECISIONS: tuple[str, ...] = ("no_trade", "avoid_too_crowded")

# Decision labels that require price/volume + risk review before any trade plan.
_ENTRY_GATE_DECISIONS: tuple[str, ...] = ("wait_for_pullback", "too_extended")

# Decision labels whose pack should prioritize gap-closing modules as required.
_GAP_PRIORITY_DECISIONS: tuple[str, ...] = (
    "research_more",
    "insufficient_evidence",
    "thesis_unconfirmed",
    "thesis_insufficient",
    "watch_wait",
)

# Conceptual origin descriptions (NOT runtime call targets).
_MODULE_CONCEPTUAL_ORIGIN: dict[ResearchPackSourceModule, str] = {
    "macro_context": (
        "Macro regime / liquidity backdrop (conceptual: macro agent layer). "
        "Not called in Phase 5L."
    ),
    "theme_context": (
        "Theme intelligence / market heat (conceptual: Phase 5J Theme "
        "Intelligence). Not called in Phase 5L."
    ),
    "sector_context": (
        "Sector cycle / rotation context (conceptual: Sector page / "
        "sector-research agent). Not called in Phase 5L."
    ),
    "scanner_context": (
        "Screening / candidate context (conceptual: Scanner page / "
        "stock-scanner agent). Not called in Phase 5L."
    ),
    "company_research": (
        "Business model / moat / management (conceptual: Equity page / "
        "equity-research agent). Not called in Phase 5L."
    ),
    "financial_analysis": (
        "3-statement model / DCF / relative valuation (conceptual: Financial "
        "page / financial-analyst agent). Not called in Phase 5L."
    ),
    "price_volume_analysis": (
        "Chart patterns / momentum / volume timing (conceptual: PriceVolume "
        "page / price-volume-analyst agent). Not called in Phase 5L."
    ),
    "news_sentiment": (
        "News / sentiment context (conceptual: news ToolResult layer). Not "
        "called in Phase 5L."
    ),
    "catalyst_earnings": (
        "Catalyst / earnings / estimate-revision context (conceptual: "
        "catalyst schema layer). Not called in Phase 5L."
    ),
    "risk_review": (
        "Risk / crowding / critic review (conceptual: Critic layer). Not "
        "called in Phase 5L."
    ),
    "evidence_validation": (
        "Evidence coverage / validator gate (conceptual: validators / "
        "evidence store). Not called in Phase 5L."
    ),
}

# Evidence gap -> conceptual modules that would address it.
_GAP_MODULE_MAP: dict[ResearchPackEvidenceGapType, tuple[ResearchPackSourceModule, ...]] = {
    "incomplete_evidence": ("evidence_validation", "company_research"),
    "missing_fundamental_confirmation": ("financial_analysis", "catalyst_earnings"),
    "narrative_only": ("news_sentiment", "evidence_validation"),
    "crowding_risk": ("price_volume_analysis", "risk_review"),
    "valuation_stretch": ("financial_analysis", "risk_review"),
    "late_cycle": ("macro_context", "risk_review"),
    "unconfirmed_fundamentals": ("financial_analysis", "catalyst_earnings"),
    "needs_macro_validation": ("macro_context", "risk_review"),
    "entry_quality": ("price_volume_analysis", "risk_review"),
    "unknown": ("evidence_validation",),
}

# Phase 5K warning type -> evidence gap type (heat_not_buy_signal is NOT a gap).
_WARNING_TO_GAP: dict[str, ResearchPackEvidenceGapType] = {
    "crowding": "crowding_risk",
    "valuation_stretch": "valuation_stretch",
    "missing_evidence": "incomplete_evidence",
    "narrative_only": "narrative_only",
    "late_cycle": "late_cycle",
    "unconfirmed_fundamentals": "unconfirmed_fundamentals",
    "needs_macro_validation": "needs_macro_validation",
    "needs_entry_validation": "entry_quality",
}

# Decision label -> pack priority.
_DECISION_PRIORITY: dict[str, ResearchPackPriority] = {
    "trade_now": "high",
    "breakout_watch": "elevated",
    "event_trade_watch": "elevated",
    "wait_for_pullback": "normal",
    "too_extended": "low",
    "position_candidate": "high",
    "accumulate_on_pullback": "elevated",
    "wait_for_earnings_confirmation": "normal",
    "thesis_improving": "normal",
    "investment_candidate": "high",
    "watch_for_valuation": "normal",
    "compounder_watch": "elevated",
    "quality_but_expensive": "normal",
    "thesis_durable": "elevated",
    "research_more": "elevated",
    "insufficient_evidence": "elevated",
    "thesis_unconfirmed": "normal",
    "thesis_insufficient": "normal",
    "watch_wait": "low",
    "avoid_too_crowded": "low",
    "no_trade": "low",
}

_HORIZON_TRIGGER: dict[OpportunityHorizon, ResearchPackTriggerReason] = {
    "short_term": "short_term_timing",
    "mid_term": "mid_term_position_building",
    "long_term": "long_term_durability",
}


# ---------------------------------------------------------------------------
# Safety banner
# ---------------------------------------------------------------------------


class ResearchPackSafetyBanner(BaseModel):
    """Always-on safety banner. Deliberately omits ``approved_for_execution``.

    The non-authorization of execution is expressed by ``no_execution_authorized``
    (a positive ``True`` flag) and by the *absence* of any ``approved_for_execution``
    field — execution is never positively authorized in Phase 5L.
    """

    model_config = ConfigDict(extra="forbid")

    is_fixture: Literal[True] = True
    no_live_module_calls: Literal[True] = True
    no_external_api: Literal[True] = True
    no_orders: Literal[True] = True
    no_final_recommendation: Literal[True] = True
    no_execution_authorized: Literal[True] = True
    not_investment_advice: Literal[True] = True
    message: str = (
        "Phase 5L orchestration boundary only. Modules are conceptual "
        "placeholders and are not executed. No live data, no LLM, no external "
        "API, no orders, no final recommendation. Not investment advice."
    )


def build_research_pack_safety_banner() -> ResearchPackSafetyBanner:
    """Return the deterministic Phase 5L safety banner."""
    return ResearchPackSafetyBanner()


# ---------------------------------------------------------------------------
# Warning / evidence-gap models
# ---------------------------------------------------------------------------


class ResearchPackWarning(BaseModel):
    """A non-fatal warning attached to a request / bundle / boundary."""

    model_config = ConfigDict(extra="forbid")

    warning_type: ResearchPackWarningType = "unknown"
    severity: ThemeRiskSeverity = "info"
    message: str = ""


class ResearchPackEvidenceGap(BaseModel):
    """An evidence gap the research pack should attempt to close.

    ``addressed_by_modules`` lists the conceptual modules that *would* address
    the gap — they are not executed here.
    """

    model_config = ConfigDict(extra="forbid")

    gap_type: ResearchPackEvidenceGapType = "unknown"
    severity: ThemeRiskSeverity = "info"
    description: str = ""
    addressed_by_modules: list[ResearchPackSourceModule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Module request / result models
# ---------------------------------------------------------------------------


class ResearchModuleRequest(BaseModel):
    """A descriptive request for ONE conceptual research module.

    This is a description of *what would be researched and why*. It is NOT a
    runtime call: ``is_runtime_call`` is hard-coded ``False``.
    """

    model_config = ConfigDict(extra="forbid")

    module: ResearchPackSourceModule
    is_required: bool = True
    priority: ResearchPackPriority = "normal"
    trigger_reasons: list[ResearchPackTriggerReason] = Field(default_factory=list)
    addresses_gaps: list[ResearchPackEvidenceGapType] = Field(default_factory=list)
    conceptual_source: str = ""
    rationale: str = ""
    is_runtime_call: Literal[False] = False
    note: str = ""


class ResearchModuleResultRef(BaseModel):
    """A placeholder reference to a (future) module result.

    Phase 5L never generates analysis: ``result_ref`` is ``None``,
    ``is_placeholder`` is hard-coded ``True``, and ``is_runtime_call`` is
    hard-coded ``False``.
    """

    model_config = ConfigDict(extra="forbid")

    module: ResearchPackSourceModule
    status: ResearchModuleStatus = "planned"
    result_ref: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    is_placeholder: Literal[True] = True
    is_runtime_call: Literal[False] = False
    note: str = ""


# ---------------------------------------------------------------------------
# Horizon coverage / request / plan / bundle models
# ---------------------------------------------------------------------------


class ResearchPackHorizonCoverage(BaseModel):
    """Which modules a pack covers for a horizon (required vs optional)."""

    model_config = ConfigDict(extra="forbid")

    horizon: OpportunityHorizon
    required_modules: list[ResearchPackSourceModule] = Field(default_factory=list)
    optional_modules: list[ResearchPackSourceModule] = Field(default_factory=list)
    is_review_only: bool = False
    note: str = ""


class ResearchPackRequest(BaseModel):
    """A structured request to assemble a research pack for ONE candidate.

    Built from a Phase 5K ``HorizonCandidateView``. Carries no buy/sell field,
    no executable order field, and no ``approved_for_execution`` field.
    """

    model_config = ConfigDict(extra="forbid")

    pack_request_id: str = Field(min_length=1)
    schema_version: str = _SCHEMA_VERSION
    ticker: str = Field(min_length=1)
    company_name: Optional[str] = None
    theme_id: str = Field(min_length=1)
    theme_name: str = ""
    subtheme_ids: list[str] = Field(default_factory=list)
    chain_node_ids: list[str] = Field(default_factory=list)
    horizon: OpportunityHorizon
    decision_label: OpportunityDecisionLabel
    next_action: str = ""
    next_action_description: str = ""
    source_candidate_refs: list[str] = Field(default_factory=list)
    source_queue_id: Optional[str] = None
    source_theme_snapshot_id: Optional[str] = None
    evidence_gaps: list[ResearchPackEvidenceGap] = Field(default_factory=list)
    required_modules: list[ResearchModuleRequest] = Field(default_factory=list)
    optional_modules: list[ResearchModuleRequest] = Field(default_factory=list)
    priority: ResearchPackPriority = "normal"
    trigger_reasons: list[ResearchPackTriggerReason] = Field(default_factory=list)
    is_review_only: bool = False
    safety_banner: ResearchPackSafetyBanner = Field(
        default_factory=ResearchPackSafetyBanner
    )
    warnings: list[ResearchPackWarning] = Field(default_factory=list)
    is_fixture_example: bool = True
    notes: str = ""


class ResearchPackPlan(BaseModel):
    """An ordered conceptual module plan derived from a request."""

    model_config = ConfigDict(extra="forbid")

    pack_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    horizon: OpportunityHorizon
    decision_label: OpportunityDecisionLabel
    module_requests: list[ResearchModuleRequest] = Field(default_factory=list)
    horizon_coverage: ResearchPackHorizonCoverage
    priority: ResearchPackPriority = "normal"
    trigger_reasons: list[ResearchPackTriggerReason] = Field(default_factory=list)
    status: ResearchPackStatus = "planned"
    is_review_only: bool = False
    safety_banner: ResearchPackSafetyBanner = Field(
        default_factory=ResearchPackSafetyBanner
    )
    notes: str = ""


class ResearchPackValidationSummary(BaseModel):
    """Deterministic, safe summary of a set of research-pack requests/bundles.

    ``is_safe_empty`` is True when there are no requests (a valid, safe state).
    Safety invariant flags are always True for a well-formed Phase 5L output.
    """

    model_config = ConfigDict(extra="forbid")

    total_pack_requests: int = 0
    total_bundles: int = 0
    total_module_requests: int = 0
    required_module_count: int = 0
    optional_module_count: int = 0
    planned_module_count: int = 0
    waiting_module_count: int = 0
    partial_module_count: int = 0
    complete_module_count: int = 0
    blocked_module_count: int = 0
    skipped_module_count: int = 0
    failed_module_count: int = 0
    modules_addressing_gaps_count: int = 0
    review_only_pack_count: int = 0
    evidence_gap_count: int = 0
    distinct_tickers: int = 0
    distinct_theme_candidate_packs: int = 0
    is_safe_empty: bool = True
    # Safety invariants (always True for a well-formed Phase 5L output).
    no_executable_order_fields: bool = True
    approved_for_execution_absent: bool = True
    no_live_module_calls: bool = True
    no_final_recommendation: bool = True
    all_modules_descriptive: bool = True
    issues: list[str] = Field(default_factory=list)


class ResearchPackBundle(BaseModel):
    """A request + plan + placeholder module result refs + status.

    No module is executed; ``module_results`` are placeholders only. Carries no
    buy/sell field, no executable order field, no ``approved_for_execution``.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    pack_request_id: str = Field(min_length=1)
    request: ResearchPackRequest
    plan: ResearchPackPlan
    module_results: list[ResearchModuleResultRef] = Field(default_factory=list)
    status: ResearchPackStatus = "planned"
    validation_summary: Optional[ResearchPackValidationSummary] = None
    safety_banner: ResearchPackSafetyBanner = Field(
        default_factory=ResearchPackSafetyBanner
    )
    warnings: list[ResearchPackWarning] = Field(default_factory=list)
    is_fixture: bool = True
    notes: str = ""


class AutoResearchPackOrchestrationBoundary(BaseModel):
    """Top-level Phase 5L contract: requests + bundles built from a Phase 5K queue.

    This is the orchestration *boundary* between the opportunity queue and the
    future Agent Debate / Decision Packet phases. It carries no buy/sell
    decision, no order instruction, no executable order field, and no
    ``approved_for_execution`` field.
    """

    model_config = ConfigDict(extra="forbid")

    boundary_id: str = Field(min_length=1)
    schema_version: str = _SCHEMA_VERSION
    as_of: Optional[str] = None
    source_queue_id: Optional[str] = None
    source_theme_snapshot_id: Optional[str] = None
    description: str = ""
    pack_requests: list[ResearchPackRequest] = Field(default_factory=list)
    pack_bundles: list[ResearchPackBundle] = Field(default_factory=list)
    status: ResearchPackStatus = "planned"
    validation_summary: Optional[ResearchPackValidationSummary] = None
    safety_banner: ResearchPackSafetyBanner = Field(
        default_factory=ResearchPackSafetyBanner
    )
    warnings: list[ResearchPackWarning] = Field(default_factory=list)
    is_fixture: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Evidence-gap derivation
# ---------------------------------------------------------------------------


def build_research_pack_evidence_gaps(
    candidate: HorizonCandidateView,
) -> list[ResearchPackEvidenceGap]:
    """Derive deterministic evidence gaps from a Phase 5K candidate view.

    Gaps come from the candidate's evidence coverage badge (incomplete coverage,
    missing fundamental confirmation) and from its mapped warnings. Heat /
    "not a buy signal" warnings are not gaps. Nothing is fabricated.
    """
    gaps: list[ResearchPackEvidenceGap] = []
    seen: set[str] = set()

    def _add(gap_type: ResearchPackEvidenceGapType, severity: ThemeRiskSeverity,
             description: str) -> None:
        if gap_type in seen:
            return
        seen.add(gap_type)
        gaps.append(
            ResearchPackEvidenceGap(
                gap_type=gap_type,
                severity=severity,
                description=description,
                addressed_by_modules=list(_GAP_MODULE_MAP.get(gap_type, ())),
            )
        )

    cov = candidate.evidence_coverage.coverage
    if cov in ("partial", "none", "unknown"):
        sev: ThemeRiskSeverity = "high" if cov in ("none", "unknown") else "low"
        _add(
            "incomplete_evidence",
            sev,
            f"Evidence coverage is {cov}; close before any decision.",
        )
    if not candidate.evidence_coverage.has_fundamental_confirmation:
        _add(
            "missing_fundamental_confirmation",
            "medium",
            "No complete fundamental confirmation; confirm the thesis.",
        )

    for w in candidate.warnings:
        gap_type = _WARNING_TO_GAP.get(str(w.warning_type))
        if gap_type is None:
            continue
        _add(gap_type, w.severity, w.message or f"{gap_type} flagged by candidate.")

    return gaps


def _gap_module_index(
    gaps: list[ResearchPackEvidenceGap],
) -> dict[ResearchPackSourceModule, list[ResearchPackEvidenceGapType]]:
    """Map each gap-addressing module to the gap types it would address."""
    index: dict[ResearchPackSourceModule, list[ResearchPackEvidenceGapType]] = {}
    for gap in gaps:
        for module in gap.addressed_by_modules:
            index.setdefault(module, [])
            if gap.gap_type not in index[module]:
                index[module].append(gap.gap_type)
    return index


# ---------------------------------------------------------------------------
# Module request building
# ---------------------------------------------------------------------------


def _module_request(
    module: ResearchPackSourceModule,
    *,
    is_required: bool,
    horizon: OpportunityHorizon,
    decision_label: str,
    gap_types: list[ResearchPackEvidenceGapType],
    is_review_only: bool,
) -> ResearchModuleRequest:
    triggers: list[ResearchPackTriggerReason] = [_HORIZON_TRIGGER[horizon]]
    if gap_types:
        triggers.append("evidence_gap")
    if decision_label in _ENTRY_GATE_DECISIONS:
        if module == "price_volume_analysis":
            triggers.append("entry_quality_check")
        if module == "risk_review":
            triggers.append("crowding_risk_check")
    if module == "macro_context":
        triggers.append("macro_validation")
    if module == "financial_analysis" and "valuation_stretch" in gap_types:
        triggers.append("valuation_check")
    if is_review_only:
        triggers.append("no_trade_review_only")

    priority: ResearchPackPriority
    if gap_types and is_required:
        priority = "high"
    elif is_required:
        priority = "normal"
    else:
        priority = "low"

    role = "required" if is_required else "optional"
    rationale = (
        f"{module} is {role} for the {horizon} research pack "
        f"(decision={decision_label}). Conceptual source module only; not "
        "executed in Phase 5L."
    )
    return ResearchModuleRequest(
        module=module,
        is_required=is_required,
        priority=priority,
        trigger_reasons=_dedup(triggers),
        addresses_gaps=_dedup(gap_types),
        conceptual_source=_MODULE_CONCEPTUAL_ORIGIN[module],
        rationale=rationale,
    )


def build_research_module_requests(
    *,
    horizon: OpportunityHorizon,
    decision_label: str,
    evidence_gaps: list[ResearchPackEvidenceGap],
    is_review_only: bool,
) -> tuple[list[ResearchModuleRequest], list[ResearchModuleRequest]]:
    """Deterministically select required/optional module requests.

    Rules (see the design doc):
      - review-only (no_trade / avoid) -> minimal risk_review + evidence_validation;
      - short / mid / long horizons get their base required + optional sets;
      - wait_for_pullback / too_extended force price_volume_analysis + risk_review
        into the required set (entry/risk gate before any trade plan);
      - research_more / insufficient_evidence / thesis_* / watch_wait promote
        gap-closing modules into the required set;
      - evidence_validation is always required (the evidence gate).
    """
    gap_index = _gap_module_index(evidence_gaps)
    gap_modules = list(gap_index.keys())

    if is_review_only:
        required: set[ResearchPackSourceModule] = set(_REVIEW_ONLY_REQUIRED)
        optional: set[ResearchPackSourceModule] = set()
    else:
        required = set(_HORIZON_REQUIRED[horizon])
        optional = set(_HORIZON_OPTIONAL[horizon])
        if decision_label in _ENTRY_GATE_DECISIONS:
            required.update({"price_volume_analysis", "risk_review"})
        if decision_label in _GAP_PRIORITY_DECISIONS:
            required.update(gap_modules)
        required.add("evidence_validation")

    # Anything promoted into required must not also remain optional.
    optional -= required

    required_list = [m for m in RESEARCH_PACK_SOURCE_MODULES if m in required]
    optional_list = [m for m in RESEARCH_PACK_SOURCE_MODULES if m in optional]

    req_objs = [
        _module_request(
            m,
            is_required=True,
            horizon=horizon,
            decision_label=decision_label,
            gap_types=gap_index.get(m, []),
            is_review_only=is_review_only,
        )
        for m in required_list
    ]
    opt_objs = [
        _module_request(
            m,
            is_required=False,
            horizon=horizon,
            decision_label=decision_label,
            gap_types=gap_index.get(m, []),
            is_review_only=is_review_only,
        )
        for m in optional_list
    ]
    return req_objs, opt_objs


def _pack_trigger_reasons(
    *,
    horizon: OpportunityHorizon,
    decision_label: str,
    has_gaps: bool,
    is_review_only: bool,
) -> list[ResearchPackTriggerReason]:
    triggers: list[ResearchPackTriggerReason] = [
        _HORIZON_TRIGGER[horizon],
        "decision_label_followup",
    ]
    if has_gaps:
        triggers.append("evidence_gap")
    if decision_label in _ENTRY_GATE_DECISIONS:
        triggers.append("entry_quality_check")
        triggers.append("crowding_risk_check")
    if decision_label == "watch_wait":
        triggers.append("watch_wait_monitor")
    if is_review_only:
        triggers.append("no_trade_review_only")
    return _dedup(triggers)


# ---------------------------------------------------------------------------
# Request / plan / bundle builders
# ---------------------------------------------------------------------------


def build_research_pack_request_from_opportunity_candidate(
    candidate: HorizonCandidateView,
    *,
    source_queue_id: Optional[str] = None,
    source_theme_snapshot_id: Optional[str] = None,
    source_candidate_refs: Optional[list[str]] = None,
) -> ResearchPackRequest:
    """Build a deterministic research-pack request from a Phase 5K candidate.

    Preserves ticker / company / theme / subtheme / chain-node ids, horizon,
    decision label, next action, source refs, evidence gaps, required + optional
    module requests, priority, trigger reasons, and safety metadata. Missing
    fields produce warnings, never fabricated data.
    """
    horizon = candidate.horizon
    decision = str(candidate.decision_label)
    is_review_only = decision in _REVIEW_ONLY_DECISIONS

    gaps = build_research_pack_evidence_gaps(candidate)
    req_objs, opt_objs = build_research_module_requests(
        horizon=horizon,
        decision_label=decision,
        evidence_gaps=gaps,
        is_review_only=is_review_only,
    )

    if source_candidate_refs is None:
        source_candidate_refs = [
            make_opportunity_candidate_ref(
                candidate.theme_id, candidate.ticker, horizon, decision
            )
        ]

    warnings: list[ResearchPackWarning] = []
    if candidate.company_name is None:
        warnings.append(
            ResearchPackWarning(
                warning_type="missing_candidate_field",
                severity="info",
                message=(
                    "Candidate company_name is missing; left empty (not "
                    "fabricated)."
                ),
            )
        )
    if gaps:
        warnings.append(
            ResearchPackWarning(
                warning_type="evidence_gap",
                severity="low",
                message=(
                    f"{len(gaps)} evidence gap(s) drive required research "
                    "modules before any decision."
                ),
            )
        )
    if is_review_only:
        warnings.append(
            ResearchPackWarning(
                warning_type="no_trade_review_only",
                severity="info",
                message=(
                    "Review-only pack: no executable research-to-trade path is "
                    "generated for a no-trade / avoid candidate."
                ),
            )
        )

    pack_request_id = make_research_pack_request_id(
        candidate.ticker, candidate.theme_id, horizon, decision
    )

    return ResearchPackRequest(
        pack_request_id=pack_request_id,
        ticker=candidate.ticker,
        company_name=candidate.company_name,
        theme_id=candidate.theme_id,
        theme_name=candidate.theme_name,
        subtheme_ids=list(candidate.subtheme_ids),
        chain_node_ids=list(candidate.chain_node_ids),
        horizon=horizon,
        decision_label=candidate.decision_label,
        next_action=str(candidate.next_action.action),
        next_action_description=candidate.next_action.description,
        source_candidate_refs=list(source_candidate_refs),
        source_queue_id=source_queue_id,
        source_theme_snapshot_id=source_theme_snapshot_id,
        evidence_gaps=gaps,
        required_modules=req_objs,
        optional_modules=opt_objs,
        priority=_DECISION_PRIORITY.get(decision, "normal"),
        trigger_reasons=_pack_trigger_reasons(
            horizon=horizon,
            decision_label=decision,
            has_gaps=bool(gaps),
            is_review_only=is_review_only,
        ),
        is_review_only=is_review_only,
        warnings=warnings,
        notes=(
            "Auto-assembled research-pack request (Phase 5L boundary). Modules "
            "are conceptual; not executed. Not a final decision."
        ),
    )


def build_research_pack_plan(request: ResearchPackRequest) -> ResearchPackPlan:
    """Build the ordered conceptual module plan from a request."""
    modules = list(request.required_modules) + list(request.optional_modules)
    coverage = ResearchPackHorizonCoverage(
        horizon=request.horizon,
        required_modules=[m.module for m in request.required_modules],
        optional_modules=[m.module for m in request.optional_modules],
        is_review_only=request.is_review_only,
        note=(
            "Review-only minimal coverage; no trade path."
            if request.is_review_only
            else f"Horizon-specific module coverage for {request.horizon}."
        ),
    )
    return ResearchPackPlan(
        pack_id=request.pack_request_id,
        ticker=request.ticker,
        horizon=request.horizon,
        decision_label=request.decision_label,
        module_requests=modules,
        horizon_coverage=coverage,
        priority=request.priority,
        trigger_reasons=list(request.trigger_reasons),
        status="planned",
        is_review_only=request.is_review_only,
        notes="Conceptual module plan only; nothing is executed in Phase 5L.",
    )


def determine_research_pack_status(
    module_results: list[ResearchModuleResultRef],
) -> ResearchPackStatus:
    """Deterministically classify a pack status from its module result refs."""
    if not module_results:
        return "skipped"
    statuses = {m.status for m in module_results}
    if statuses == {"planned"}:
        return "planned"
    if statuses <= {"complete"}:
        return "complete"
    if statuses == {"blocked"}:
        return "blocked"
    if statuses == {"skipped"}:
        return "skipped"
    if statuses == {"failed"}:
        return "failed"
    if statuses <= {"complete", "planned", "partial", "waiting_for_data"}:
        return "partial"
    return "partial"


def _build_validation_summary(
    requests: list[ResearchPackRequest],
    module_results_lists: list[list[ResearchModuleResultRef]],
    *,
    is_empty: bool,
) -> ResearchPackValidationSummary:
    required_count = sum(len(r.required_modules) for r in requests)
    optional_count = sum(len(r.optional_modules) for r in requests)
    gaps_count = sum(len(r.evidence_gaps) for r in requests)
    review_only = sum(1 for r in requests if r.is_review_only)
    modules_addressing_gaps = sum(
        1
        for r in requests
        for m in (list(r.required_modules) + list(r.optional_modules))
        if m.addresses_gaps
    )

    status_counts: dict[str, int] = {s: 0 for s in RESEARCH_PACK_STATUSES}
    for results in module_results_lists:
        for m in results:
            status_counts[m.status] = status_counts.get(m.status, 0) + 1

    issues: list[str] = []
    for r in requests:
        if not r.is_review_only and not r.required_modules:
            issues.append(
                f"request {r.pack_request_id!r} has no required modules"
            )

    distinct_tickers = len({r.ticker for r in requests})
    distinct_packs = len(
        {(r.theme_id, r.ticker, r.horizon) for r in requests}
    )

    return ResearchPackValidationSummary(
        total_pack_requests=len(requests),
        total_bundles=len(module_results_lists),
        total_module_requests=required_count + optional_count,
        required_module_count=required_count,
        optional_module_count=optional_count,
        planned_module_count=status_counts.get("planned", 0),
        waiting_module_count=status_counts.get("waiting_for_data", 0),
        partial_module_count=status_counts.get("partial", 0),
        complete_module_count=status_counts.get("complete", 0),
        blocked_module_count=status_counts.get("blocked", 0),
        skipped_module_count=status_counts.get("skipped", 0),
        failed_module_count=status_counts.get("failed", 0),
        modules_addressing_gaps_count=modules_addressing_gaps,
        review_only_pack_count=review_only,
        evidence_gap_count=gaps_count,
        distinct_tickers=distinct_tickers,
        distinct_theme_candidate_packs=distinct_packs,
        is_safe_empty=is_empty,
        issues=issues,
    )


def build_research_pack_validation_summary(
    *,
    requests: list[ResearchPackRequest],
    bundles: list[ResearchPackBundle],
    is_empty: bool = False,
) -> ResearchPackValidationSummary:
    """Build the aggregate validation summary across requests + bundles."""
    return _build_validation_summary(
        requests,
        [list(b.module_results) for b in bundles],
        is_empty=is_empty or not requests,
    )


def build_research_pack_bundle_from_fixture(
    request: ResearchPackRequest,
    *,
    degraded: bool = False,
) -> ResearchPackBundle:
    """Build a deterministic research-pack bundle (placeholder results only).

    In the default case every module result is ``planned`` with a ``None``
    ``result_ref``. In the degraded case results are ``blocked`` placeholders
    and the bundle carries warnings — missing module refs are handled safely
    (no analysis is fabricated).
    """
    plan = build_research_pack_plan(request)

    results: list[ResearchModuleResultRef] = []
    for mreq in plan.module_requests:
        if degraded:
            note = (
                "Degraded fixture: upstream module data unavailable; result "
                "ref is a safe placeholder (no analysis fabricated)."
            )
            status: ResearchModuleStatus = "blocked"
        else:
            note = (
                "Planned placeholder; module not executed in Phase 5L "
                "(boundary only)."
            )
            status = "planned"
        results.append(
            ResearchModuleResultRef(
                module=mreq.module,
                status=status,
                result_ref=None,
                note=note,
            )
        )

    warnings: list[ResearchPackWarning] = list(request.warnings)
    if degraded:
        warnings.append(
            ResearchPackWarning(
                warning_type="degraded_upstream",
                severity="medium",
                message=(
                    "Degraded fixture: module result refs are unavailable "
                    "placeholders; no analysis is fabricated."
                ),
            )
        )
        warnings.append(
            ResearchPackWarning(
                warning_type="missing_module_ref",
                severity="low",
                message=(
                    "One or more module result refs are missing; handled "
                    "safely as placeholders."
                ),
            )
        )

    status = determine_research_pack_status(results)
    validation = _build_validation_summary([request], [results], is_empty=False)

    return ResearchPackBundle(
        bundle_id=make_research_pack_bundle_id(request.pack_request_id),
        pack_request_id=request.pack_request_id,
        request=request,
        plan=plan,
        module_results=results,
        status=status,
        validation_summary=validation,
        warnings=warnings,
        notes=(
            "Research-pack bundle (Phase 5L boundary). Module results are "
            "placeholders; nothing is executed. Not a final decision."
        ),
    )


# ---------------------------------------------------------------------------
# Orchestration boundary builder
# ---------------------------------------------------------------------------


def _collect_queue_candidates(
    queue: HorizonAwareOpportunityQueueView,
) -> list[HorizonCandidateView]:
    """Collect every horizon candidate view across the six queue sections.

    Each Phase 5K horizon view routes to exactly one queue, so the union across
    the six sections is the full, de-duplicated set of horizon candidate views.
    Iteration order is deterministic (queue order, then in-section order).
    """
    candidates: list[HorizonCandidateView] = []
    for section in (
        queue.short_term,
        queue.mid_term,
        queue.long_term,
        queue.watch_wait,
        queue.research_more,
        queue.no_trade_avoid,
    ):
        candidates.extend(section.candidates)
    return candidates


def build_auto_research_pack_orchestration_boundary(
    queue: HorizonAwareOpportunityQueueView,
    *,
    label: str = "default",
    degraded: bool = False,
) -> AutoResearchPackOrchestrationBoundary:
    """Build the full Phase 5L orchestration boundary from a Phase 5K queue.

    Deterministic and offline. An empty queue yields a safe empty boundary.
    Each candidate yields one ``ResearchPackRequest`` + one
    ``ResearchPackBundle``; the same ticker can appear across horizons with
    different decisions (and therefore different packs).
    """
    candidates = _collect_queue_candidates(queue)

    requests: list[ResearchPackRequest] = []
    bundles: list[ResearchPackBundle] = []
    for candidate in candidates:
        request = build_research_pack_request_from_opportunity_candidate(
            candidate,
            source_queue_id=queue.queue_id,
            source_theme_snapshot_id=queue.source_theme_snapshot_id,
        )
        requests.append(request)
        bundles.append(
            build_research_pack_bundle_from_fixture(request, degraded=degraded)
        )

    validation = build_research_pack_validation_summary(
        requests=requests, bundles=bundles, is_empty=not requests
    )

    all_results: list[ResearchModuleResultRef] = [
        r for b in bundles for r in b.module_results
    ]
    boundary_status = determine_research_pack_status(all_results)

    warnings: list[ResearchPackWarning] = [
        ResearchPackWarning(
            warning_type="no_trade_review_only",
            severity="info",
            message=(
                "This is an orchestration boundary only. Research packs are "
                "conceptual; modules are not executed. No final buy/sell "
                "decision, no order instruction, no execution. Agent Debate / "
                "Decision Packet come later (Phase 5M+). Not investment advice."
            ),
        )
    ]
    if not requests:
        warnings.append(
            ResearchPackWarning(
                warning_type="empty_queue",
                severity="info",
                message="Empty opportunity queue; safe empty research pack boundary.",
            )
        )
    if degraded:
        warnings.append(
            ResearchPackWarning(
                warning_type="degraded_upstream",
                severity="medium",
                message=(
                    "Degraded fixture: module result refs are unavailable "
                    "placeholders across all packs; no analysis fabricated."
                ),
            )
        )

    return AutoResearchPackOrchestrationBoundary(
        boundary_id=make_auto_research_pack_boundary_id(label),
        as_of=queue.as_of,
        source_queue_id=queue.queue_id,
        source_theme_snapshot_id=queue.source_theme_snapshot_id,
        description=(
            "Auto Research Pack orchestration boundary derived from a Phase 5K "
            "horizon-aware opportunity queue. Opportunity-first, horizon-aware, "
            "evidence-gap-driven. Modules are conceptual source modules and are "
            "not executed. This is not a final trade recommendation."
        ),
        pack_requests=requests,
        pack_bundles=bundles,
        status=boundary_status,
        validation_summary=validation,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Fixtures — deterministic examples only (NOT live claims)
# ---------------------------------------------------------------------------


def build_default_research_pack_bundle() -> AutoResearchPackOrchestrationBoundary:
    """Default Phase 5L boundary built from the Phase 5K default opportunity queue.

    "Bundle" here means the full set of per-candidate research-pack bundles held
    by the orchestration boundary. Demonstrates short-term technical/news/
    catalyst/risk/evidence packs, mid-term company/financial/technical/catalyst/
    risk/evidence packs, long-term macro/theme/company/financial/risk/evidence
    packs, gap-driven research_more packs, and review-only no-trade packs.
    """
    return build_auto_research_pack_orchestration_boundary(
        build_default_opportunity_queue_view(), label="default"
    )


def build_degraded_research_pack_bundle() -> AutoResearchPackOrchestrationBoundary:
    """Degraded Phase 5L boundary built from the degraded opportunity queue.

    All module result refs are unavailable placeholders (``blocked``) and each
    bundle carries warnings — missing module refs are handled safely.
    """
    return build_auto_research_pack_orchestration_boundary(
        build_degraded_opportunity_queue_view(), label="degraded", degraded=True
    )


def build_empty_research_pack_bundle() -> AutoResearchPackOrchestrationBoundary:
    """Safe empty Phase 5L boundary built from the empty opportunity queue."""
    return build_auto_research_pack_orchestration_boundary(
        build_empty_opportunity_queue_view(), label="empty"
    )
