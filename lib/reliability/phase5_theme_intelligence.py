"""
lib/reliability/phase5_theme_intelligence.py

Phase 5J: Theme Intelligence / Market Heat Schema.

Purpose
-------
Defines deterministic, evidence-first Pydantic schema / contracts for:

  1. Detecting market **themes** (cross-sector narratives such as AI, space,
     robotics, nuclear, quantum, biotech).
  2. Measuring **market heat** at theme / subtheme level (a container of
     scored components — NOT a live calculator and NOT a buy signal).
  3. Decomposing a theme into its **industry chain** (compute -> memory ->
     optical -> power/cooling -> platform -> applications, etc.).
  4. Representing **candidate tickers** mapped to a theme / subtheme / chain
     node with a role (leader / second-derivative beneficiary / laggard /
     supplier / platform / speculative / unknown), evidence coverage, heat
     contribution, and crowding context.

This module is the **upstream input layer** for the future Phase 5K
Horizon-aware Opportunity Queue ViewModel. It deliberately does **not**:

- decide buy / sell;
- generate a final opportunity queue or ranked candidate list;
- compute entry quality (a future Phase 5K concept — referenced here only as
  a non-calculated placeholder);
- fetch any live data or call any LLM / external API;
- introduce any database / vector store / production persistence;
- introduce any broker / order / execution capability.

Design principles
-----------------
- Standalone, deterministic, offline / mock-only.
- No live LLM calls.
- No live data fetching, no Streamlit, no Anthropic SDK calls.
- No database writes, no file persistence, no vector store.
- No reading of the live workflow state JSON file.
- No import of ``app.py``, ``pages/*``, ``lib/llm_orchestrator.py``, or
  ``lib/workflow_state.py``.
- No broker / order / execution behavior; no executable order fields.
- No ``approved_for_execution`` field on any Phase 5J model. Every model sets
  ``extra="forbid"``, so an ``approved_for_execution`` (or any order-ticket)
  field cannot be smuggled in via construction; the invariant holds by
  construction.

Heat vs. entry quality (read this)
----------------------------------
**Theme Heat Score is NOT a buy signal and is NOT entry quality.** A theme can
be very hot (high heat score) while being a poor place to enter (crowded,
valuation-stretched, late-lifecycle). High heat is a reason to *research*, not
a reason to *buy*. ``CrowdingSignal`` is kept deliberately separate from
``ThemeHeatScore``. Entry-quality scoring and any buy/sell decisioning are
explicitly deferred to Phase 5K (see ``EntryQualityScorePlaceholder``).

Fixtures
--------
All ``build_*_fixture`` / ``build_default_theme_intelligence_snapshot`` outputs
are **deterministic examples**. Sample ticker symbols are illustrative fixture
examples only — they are **not** live market claims, recommendations, or
current facts. No API is called to produce them.

Disclaimer: outputs are for research / educational purposes only and do not
constitute investment advice.

See ``docs/reliability_phase_5j_theme_intelligence_market_heat_schema.md``.
"""

from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Deterministic fixture timestamp (no wall-clock time -> deterministic output)
# ---------------------------------------------------------------------------

SAMPLE_THEME_AS_OF: str = "2026-05-20T00:00:00Z"

_SCHEMA_VERSION: str = "phase5_theme_intelligence_v1"


# ---------------------------------------------------------------------------
# Literal aliases
# ---------------------------------------------------------------------------

ThemeLifecycleStage = Literal[
    "emerging",
    "accelerating",
    "consensus",
    "crowded",
    "fading",
    "unknown",
]

THEME_LIFECYCLE_STAGES: tuple[ThemeLifecycleStage, ...] = (
    "emerging",
    "accelerating",
    "consensus",
    "crowded",
    "fading",
    "unknown",
)

# Status of a heat score container. "complete" = all material components
# present; "partial" = some present; "unknown" = none present / not assessed.
ThemeHeatScoreStatus = Literal["complete", "partial", "unknown"]

# Role of a candidate ticker within a theme / chain node.
ThemeCandidateRole = Literal[
    "leader",
    "second_derivative_beneficiary",
    "laggard",
    "supplier",
    "platform",
    "speculative",
    "unknown",
]

THEME_CANDIDATE_ROLES: tuple[ThemeCandidateRole, ...] = (
    "leader",
    "second_derivative_beneficiary",
    "laggard",
    "supplier",
    "platform",
    "speculative",
    "unknown",
)

# Type of an aggregate heat signal feeding a theme.
ThemeHeatSignalType = Literal[
    "price_momentum",
    "volume",
    "breadth",
    "fund_flow",
    "search_interest",
    "options_activity",
    "narrative",
    "fundamental_confirmation",
    "unknown",
]

# Where a theme / signal was discovered (deterministic, fixture-only origins).
ThemeSourceType = Literal[
    "macro",
    "sector_rotation",
    "scanner",
    "narrative",
    "fund_flow",
    "news",
    "earnings",
    "manual_fixture",
    "unknown",
]

# Generic strength bucket for a signal.
SignalStrength = Literal["weak", "moderate", "strong", "unknown"]

# Direction of a fundamental confirmation signal relative to the narrative.
ConfirmationDirection = Literal[
    "confirming",
    "mixed",
    "disconfirming",
    "unconfirmed",
    "unknown",
]

FundamentalConfirmationType = Literal[
    "revenue",
    "eps",
    "guidance",
    "estimate_revision",
    "orders",
    "backlog",
    "capex_commentary",
    "unknown",
]

# Crowding level bucket (kept separate from heat score on purpose).
CrowdingLevel = Literal[
    "low",
    "moderate",
    "elevated",
    "high",
    "extreme",
    "unknown",
]

ThemeRiskWarningType = Literal[
    "crowding",
    "valuation_stretch",
    "narrative_only",
    "missing_evidence",
    "late_cycle",
    "low_breadth",
    "unconfirmed_fundamentals",
    "unknown",
]

ThemeRiskSeverity = Literal["info", "low", "medium", "high", "unknown"]

EvidenceCoverageStatus = Literal["complete", "partial", "none", "unknown"]


# ---------------------------------------------------------------------------
# Internal helpers (deterministic)
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    """Lowercase alnum slug; non-alnum runs collapse to single underscores."""
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
    """Deterministic 8-char hex digest. No randomness, no time."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:8]


def make_theme_id(name: str) -> str:
    """Deterministic, content-sensitive theme id."""
    return f"theme_{_slug(name)}_{_short_hash('theme::' + str(name))}"


def make_subtheme_id(parent_theme_id: str, name: str) -> str:
    """Deterministic, content-sensitive subtheme id (scoped to parent)."""
    return (
        f"subtheme_{_slug(name)}_"
        f"{_short_hash('subtheme::' + str(parent_theme_id) + '::' + str(name))}"
    )


def make_chain_node_id(parent_theme_id: str, name: str) -> str:
    """Deterministic, content-sensitive industry-chain node id."""
    return (
        f"chain_{_slug(name)}_"
        f"{_short_hash('chain::' + str(parent_theme_id) + '::' + str(name))}"
    )


def make_theme_intelligence_snapshot_id(label: str) -> str:
    """Deterministic snapshot id from a stable label (no timestamp input)."""
    return f"themeintel_{_slug(label)}_{_short_hash('snapshot::' + str(label))}"


# ---------------------------------------------------------------------------
# Signal models
# ---------------------------------------------------------------------------


class ThemeDiscoverySource(BaseModel):
    """Where a theme (or a theme signal) was surfaced from. Fixture-only."""

    model_config = ConfigDict(extra="forbid")

    source_type: ThemeSourceType = "unknown"
    description: str = ""
    evidence_ref: Optional[str] = None


class ThemeHeatSignal(BaseModel):
    """An aggregate momentum / attention / flow signal feeding a theme.

    This is a *container* describing a signal; it does not compute the signal
    from live data.
    """

    model_config = ConfigDict(extra="forbid")

    signal_type: ThemeHeatSignalType = "unknown"
    source_type: ThemeSourceType = "unknown"
    strength: SignalStrength = "unknown"
    # Freshness / observation timestamp if the fixture provides one.
    timestamp: Optional[str] = None
    explanation: str = ""
    evidence_ref: Optional[str] = None


class NarrativeSignal(BaseModel):
    """Strength / recency of a narrative cluster (news, social, sell-side)."""

    model_config = ConfigDict(extra="forbid")

    narrative_cluster: str = Field(min_length=1)
    mention_intensity: SignalStrength = "unknown"
    source_type: ThemeSourceType = "narrative"
    timestamp: Optional[str] = None
    explanation: str = ""
    evidence_ref: Optional[str] = None


class FundamentalConfirmationSignal(BaseModel):
    """Whether earnings / revenue / guidance / orders confirm the narrative.

    Fixture-only commentary container; no live fundamentals are fetched.
    """

    model_config = ConfigDict(extra="forbid")

    confirmation_type: FundamentalConfirmationType = "unknown"
    confirmation_direction: ConfirmationDirection = "unknown"
    strength: SignalStrength = "unknown"
    explanation: str = ""
    evidence_ref: Optional[str] = None


class CrowdingSignal(BaseModel):
    """Positioning / froth measure — kept SEPARATE from ``ThemeHeatScore``.

    All quantitative fields are fixture-only *placeholders* (string
    descriptors), not computed indicator values. Crowding is an argument
    *against* chasing a hot theme; it is not part of the heat score.
    """

    model_config = ConfigDict(extra="forbid")

    crowding_level: CrowdingLevel = "unknown"
    # Qualitative placeholders (fixture-only; not computed indicators).
    momentum_overextension: Optional[str] = None
    valuation_stretch: Optional[str] = None
    volume_climax: Optional[str] = None
    rsi_placeholder: Optional[str] = None
    adx_placeholder: Optional[str] = None
    ma_distance_placeholder: Optional[str] = None
    explanation: str = ""
    evidence_ref: Optional[str] = None


class ThemeRiskWarning(BaseModel):
    """A non-fatal risk / caveat attached to a theme, subtheme, or candidate."""

    model_config = ConfigDict(extra="forbid")

    warning_type: ThemeRiskWarningType = "unknown"
    severity: ThemeRiskSeverity = "info"
    message: str = ""


class ThemeEvidenceSummary(BaseModel):
    """Evidence coverage for a theme / subtheme / candidate (by reference).

    Evidence is represented as opaque evidence-id / source-ref strings so the
    schema stays offline and store-agnostic. Missing evidence yields
    ``coverage_status`` ``"partial"`` / ``"none"`` — never fabricated
    completion.
    """

    model_config = ConfigDict(extra="forbid")

    coverage_status: EvidenceCoverageStatus = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Scoring containers (NOT live calculators, NOT buy signals)
# ---------------------------------------------------------------------------


class ThemeHeatScore(BaseModel):
    """Deterministic container of heat-score components.

    This is **not** a live calculator and **not** a buy signal. Components are
    populated from upstream deterministic tools / fixtures. ``score_status``
    reflects how complete the component set is:

    - ``complete``  : all material components present.
    - ``partial``   : some components present.
    - ``unknown``   : no components present / not assessed.

    There are intentionally **no** ``buy``, ``sell``, ``trade_now``,
    ``approved_for_execution``, or order-ticket fields on this model. High heat
    does not authorize a trade — see ``EntryQualityScorePlaceholder`` and
    ``CrowdingSignal``.
    """

    model_config = ConfigDict(extra="forbid")

    score_status: ThemeHeatScoreStatus = "unknown"
    total_score: Optional[float] = None
    price_momentum_component: Optional[float] = None
    volume_component: Optional[float] = None
    breadth_component: Optional[float] = None
    narrative_component: Optional[float] = None
    fundamental_confirmation_component: Optional[float] = None
    freshness_component: Optional[float] = None
    # Crowding is surfaced here only as a *penalty/adjustment* magnitude; the
    # full crowding assessment lives on the separate ``CrowdingSignal`` model.
    crowding_adjustment: Optional[float] = None
    # Explicit, assertable marker: heat is not a buy signal.
    is_buy_signal: Literal[False] = False
    notes: str = ""


# Material components considered when deriving heat score status.
_HEAT_COMPONENT_FIELDS: tuple[str, ...] = (
    "price_momentum_component",
    "volume_component",
    "breadth_component",
    "narrative_component",
    "fundamental_confirmation_component",
    "freshness_component",
)


class EntryQualityScorePlaceholder(BaseModel):
    """Non-calculated placeholder for a FUTURE Phase 5K concept.

    Entry-quality scoring (timing / structure / pullback / confirmation) is the
    decision that turns an *interesting* theme into a *buyable* candidate. It is
    explicitly **out of scope for Phase 5J** and is **not computed here**. This
    placeholder exists only so the schema can reference the forthcoming concept
    without implying it has been calculated.
    """

    model_config = ConfigDict(extra="forbid")

    computed: Literal[False] = False
    deferred_to_phase: str = "5K"
    note: str = (
        "Entry quality scoring is a future Phase 5K concept; it is not "
        "calculated in Phase 5J. Theme heat is not entry quality."
    )


def derive_heat_score_status(score: ThemeHeatScore) -> ThemeHeatScoreStatus:
    """Deterministically classify a heat score by component presence.

    Pure inspection of an in-memory container (no market data, no time).
    """
    present = [
        getattr(score, f) is not None for f in _HEAT_COMPONENT_FIELDS
    ]
    if all(present):
        return "complete"
    if any(present):
        return "partial"
    return "unknown"


def build_theme_heat_score(
    *,
    price_momentum_component: Optional[float] = None,
    volume_component: Optional[float] = None,
    breadth_component: Optional[float] = None,
    narrative_component: Optional[float] = None,
    fundamental_confirmation_component: Optional[float] = None,
    freshness_component: Optional[float] = None,
    crowding_adjustment: Optional[float] = None,
    total_score: Optional[float] = None,
    notes: str = "",
) -> ThemeHeatScore:
    """Build a deterministic heat-score container.

    ``score_status`` is derived from which components are present. If
    ``total_score`` is not supplied and the status is ``complete``, a
    deterministic sum of the provided components minus any crowding adjustment
    is used (simple arithmetic on the supplied inputs — not a market
    calculation). Otherwise ``total_score`` is left as supplied (possibly
    ``None``) so partial / unknown states never fabricate a total.
    """
    score = ThemeHeatScore(
        price_momentum_component=price_momentum_component,
        volume_component=volume_component,
        breadth_component=breadth_component,
        narrative_component=narrative_component,
        fundamental_confirmation_component=fundamental_confirmation_component,
        freshness_component=freshness_component,
        crowding_adjustment=crowding_adjustment,
        total_score=total_score,
        notes=notes,
    )
    status = derive_heat_score_status(score)
    score.score_status = status
    if total_score is None and status == "complete":
        components_sum = sum(
            float(getattr(score, f)) for f in _HEAT_COMPONENT_FIELDS
        )
        adj = float(crowding_adjustment) if crowding_adjustment is not None else 0.0
        score.total_score = round(components_sum - adj, 6)
    return score


# ---------------------------------------------------------------------------
# Candidate / chain / theme models
# ---------------------------------------------------------------------------


class ThemeCandidateTicker(BaseModel):
    """A ticker mapped to a theme (and optionally subthemes / chain nodes).

    A candidate MAY appear under multiple subthemes and multiple chain nodes
    (``subtheme_ids`` / ``chain_node_ids`` are lists). A single theme may host
    leaders, second-derivative beneficiaries, laggards, suppliers, platforms,
    and speculative names side by side.

    There is no buy/sell field and no executable order field here: this is an
    input record for the future Phase 5K opportunity queue, not a decision.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_name: Optional[str] = None
    theme_id: str = Field(min_length=1)
    subtheme_ids: list[str] = Field(default_factory=list)
    chain_node_ids: list[str] = Field(default_factory=list)
    role: ThemeCandidateRole = "unknown"
    evidence: ThemeEvidenceSummary = Field(default_factory=ThemeEvidenceSummary)
    # Qualitative contribution of this name to theme heat (fixture-only).
    heat_contribution: Optional[float] = None
    # Crowding risk is carried as its own signal, separate from heat.
    crowding_level: CrowdingLevel = "unknown"
    crowding_signal: Optional[CrowdingSignal] = None
    warnings: list[ThemeRiskWarning] = Field(default_factory=list)
    notes: str = ""
    # Fixture marker: this ticker is an illustrative example, not a live claim.
    is_fixture_example: bool = True


class IndustryChainNode(BaseModel):
    """A node in a theme's value chain (e.g. compute, memory, optical, power).

    Upstream / downstream relationships are expressed as lists of sibling node
    ids; an optional ``parent_node_id`` allows nesting.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    parent_theme_id: str = Field(min_length=1)
    parent_node_id: Optional[str] = None
    name: str = Field(min_length=1)
    role_in_chain: str = ""
    upstream_node_ids: list[str] = Field(default_factory=list)
    downstream_node_ids: list[str] = Field(default_factory=list)
    representative_tickers: list[str] = Field(default_factory=list)
    notes: str = ""


class SubthemeRecord(BaseModel):
    """A bounded slice of a theme (e.g. AI -> HBM memory)."""

    model_config = ConfigDict(extra="forbid")

    subtheme_id: str = Field(min_length=1)
    parent_theme_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    heat_score: ThemeHeatScore = Field(default_factory=ThemeHeatScore)
    lifecycle_stage: ThemeLifecycleStage = "unknown"
    chain_node_ids: list[str] = Field(default_factory=list)
    candidate_tickers: list[ThemeCandidateTicker] = Field(default_factory=list)
    warnings: list[ThemeRiskWarning] = Field(default_factory=list)


class ThemeRecord(BaseModel):
    """A macro narrative spanning multiple sectors (e.g. AI, space).

    Aggregates discovery sources, heat / narrative / fundamental / crowding
    signals, subthemes, industry-chain nodes, and candidate tickers, with
    evidence coverage and non-fatal risk warnings.
    """

    model_config = ConfigDict(extra="forbid")

    theme_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    lifecycle_stage: ThemeLifecycleStage = "unknown"
    heat_score: ThemeHeatScore = Field(default_factory=ThemeHeatScore)
    discovery_sources: list[ThemeDiscoverySource] = Field(default_factory=list)
    source_signals: list[ThemeHeatSignal] = Field(default_factory=list)
    narrative_signals: list[NarrativeSignal] = Field(default_factory=list)
    fundamental_confirmation_signals: list[FundamentalConfirmationSignal] = Field(
        default_factory=list
    )
    crowding_signals: list[CrowdingSignal] = Field(default_factory=list)
    subthemes: list[SubthemeRecord] = Field(default_factory=list)
    industry_chain_nodes: list[IndustryChainNode] = Field(default_factory=list)
    candidate_tickers: list[ThemeCandidateTicker] = Field(default_factory=list)
    evidence: ThemeEvidenceSummary = Field(default_factory=ThemeEvidenceSummary)
    warnings: list[ThemeRiskWarning] = Field(default_factory=list)


class ThemeUniverseSnapshot(BaseModel):
    """A collection of theme records as of a point in time."""

    model_config = ConfigDict(extra="forbid")

    as_of: Optional[str] = None
    description: str = ""
    themes: list[ThemeRecord] = Field(default_factory=list)


class ThemeIntelligenceValidationSummary(BaseModel):
    """Deterministic, safe summary of a theme intelligence snapshot.

    Reports counts and invariant flags. ``is_safe_empty`` is True for an empty
    universe (a valid, safe state). ``issues`` carries non-fatal observations
    (e.g. dangling chain-node references); it never makes the snapshot a
    decision and never fabricates completion for missing evidence.
    """

    model_config = ConfigDict(extra="forbid")

    theme_count: int = 0
    subtheme_count: int = 0
    chain_node_count: int = 0
    candidate_ticker_count: int = 0
    complete_heat_score_count: int = 0
    partial_heat_score_count: int = 0
    unknown_heat_score_count: int = 0
    themes_with_warnings: int = 0
    unknown_lifecycle_count: int = 0
    dangling_chain_node_ref_count: int = 0
    is_safe_empty: bool = True
    # Safety invariants (always True for a well-formed Phase 5J snapshot).
    no_buy_signal_fields: bool = True
    no_executable_order_fields: bool = True
    approved_for_execution_absent: bool = True
    issues: list[str] = Field(default_factory=list)


class ThemeIntelligenceSnapshot(BaseModel):
    """Top-level Phase 5J contract: a theme universe + validation summary.

    Fixture / mock-only. Carries no buy/sell decision, no opportunity queue,
    no entry-quality computation, and no executable order field.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    as_of: Optional[str] = None
    schema_version: str = _SCHEMA_VERSION
    description: str = ""
    universe: ThemeUniverseSnapshot = Field(default_factory=ThemeUniverseSnapshot)
    validation_summary: Optional[ThemeIntelligenceValidationSummary] = None
    # Forward reference only; not computed in Phase 5J.
    entry_quality_placeholder: EntryQualityScorePlaceholder = Field(
        default_factory=EntryQualityScorePlaceholder
    )
    is_fixture: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_theme_intelligence_snapshot(
    snapshot: ThemeIntelligenceSnapshot,
) -> ThemeIntelligenceValidationSummary:
    """Produce a deterministic, safe validation summary for a snapshot.

    Counts themes / subthemes / chain nodes / candidates and heat-score status
    distribution; flags an empty universe as a *safe empty* state; records
    non-fatal observations (dangling chain-node references) in ``issues``.
    Missing evidence is reflected as partial/unknown status, never fabricated.
    """
    themes = list(snapshot.universe.themes)
    summary = ThemeIntelligenceValidationSummary(
        is_safe_empty=(len(themes) == 0),
    )

    issues: list[str] = []

    def _tally_heat(score: ThemeHeatScore) -> None:
        st = score.score_status
        if st == "complete":
            summary.complete_heat_score_count += 1
        elif st == "partial":
            summary.partial_heat_score_count += 1
        else:
            summary.unknown_heat_score_count += 1

    for theme in themes:
        summary.theme_count += 1
        if theme.lifecycle_stage == "unknown":
            summary.unknown_lifecycle_count += 1
        if theme.warnings:
            summary.themes_with_warnings += 1
        _tally_heat(theme.heat_score)

        known_node_ids = {n.node_id for n in theme.industry_chain_nodes}
        summary.chain_node_count += len(theme.industry_chain_nodes)

        for sub in theme.subthemes:
            summary.subtheme_count += 1
            if sub.lifecycle_stage == "unknown":
                summary.unknown_lifecycle_count += 1
            _tally_heat(sub.heat_score)
            for nid in sub.chain_node_ids:
                if nid not in known_node_ids:
                    summary.dangling_chain_node_ref_count += 1
                    issues.append(
                        f"subtheme {sub.subtheme_id!r} references unknown "
                        f"chain node {nid!r}"
                    )
            for cand in sub.candidate_tickers:
                summary.candidate_ticker_count += 1

        for cand in theme.candidate_tickers:
            summary.candidate_ticker_count += 1
            for nid in cand.chain_node_ids:
                if nid not in known_node_ids:
                    summary.dangling_chain_node_ref_count += 1
                    issues.append(
                        f"candidate {cand.ticker!r} references unknown chain "
                        f"node {nid!r}"
                    )

    summary.issues = issues
    return summary


def attach_validation_summary(
    snapshot: ThemeIntelligenceSnapshot,
) -> ThemeIntelligenceSnapshot:
    """Return ``snapshot`` with its ``validation_summary`` populated."""
    snapshot.validation_summary = validate_theme_intelligence_snapshot(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Fixtures — deterministic examples only (NOT live market claims)
# ---------------------------------------------------------------------------

_FIXTURE_EVIDENCE_PREFIX = "fixev"


def _ev(label: str) -> str:
    """Deterministic fixture evidence-id string (opaque; no real store)."""
    return f"{_FIXTURE_EVIDENCE_PREFIX}_{_short_hash(label)}"


def build_ai_theme_fixture() -> ThemeRecord:
    """Deterministic AI theme fixture with subthemes + industry-chain nodes.

    Sample tickers are illustrative fixture examples only — not live claims.
    Demonstrates a complete heat score, multiple candidate roles, and a
    candidate mapped to multiple subthemes / chain nodes.
    """
    name = "Artificial Intelligence"
    theme_id = make_theme_id(name)

    # --- industry chain nodes ---
    node_defs = [
        ("compute", "compute (accelerators, CPUs)"),
        ("memory", "memory / HBM"),
        ("optical", "optical / networking"),
        ("dc_power", "data-center power / cooling"),
        ("cloud", "cloud / platform"),
        ("enterprise_sw", "enterprise software"),
        ("applications", "applications"),
        ("edge_robotics", "edge / robotics"),
    ]
    node_ids: dict[str, str] = {
        key: make_chain_node_id(theme_id, label) for key, label in node_defs
    }

    nodes: list[IndustryChainNode] = []
    # Linear-ish chain: compute <- memory/optical/power feed compute;
    # compute -> cloud -> enterprise_sw -> applications; edge_robotics downstream.
    chain_topology = {
        "compute": (["memory", "optical", "dc_power"], ["cloud", "edge_robotics"]),
        "memory": ([], ["compute"]),
        "optical": ([], ["compute"]),
        "dc_power": ([], ["compute"]),
        "cloud": (["compute"], ["enterprise_sw", "applications"]),
        "enterprise_sw": (["cloud"], ["applications"]),
        "applications": (["cloud", "enterprise_sw"], []),
        "edge_robotics": (["compute"], []),
    }
    rep_tickers = {
        "compute": ["NVDA", "AMD"],
        "memory": ["MU", "FIXHBM"],
        "optical": ["AVGO", "COHR"],
        "dc_power": ["VRT", "ETN"],
        "cloud": ["MSFT", "AMZN"],
        "enterprise_sw": ["CRM", "NOW"],
        "applications": ["FIXAPP"],
        "edge_robotics": ["FIXEDGE"],
    }
    for key, label in node_defs:
        up_keys, down_keys = chain_topology[key]
        nodes.append(
            IndustryChainNode(
                node_id=node_ids[key],
                parent_theme_id=theme_id,
                name=label,
                role_in_chain=key,
                upstream_node_ids=[node_ids[k] for k in up_keys],
                downstream_node_ids=[node_ids[k] for k in down_keys],
                representative_tickers=rep_tickers[key],
            )
        )

    # --- subthemes ---
    sub_compute_id = make_subtheme_id(theme_id, "AI Compute")
    sub_memory_id = make_subtheme_id(theme_id, "HBM Memory")
    sub_power_id = make_subtheme_id(theme_id, "Data-Center Power and Cooling")

    # A candidate mapped to MULTIPLE subthemes and MULTIPLE chain nodes.
    nvda = ThemeCandidateTicker(
        ticker="NVDA",
        company_name="NVIDIA Corporation",
        theme_id=theme_id,
        subtheme_ids=[sub_compute_id, sub_power_id],
        chain_node_ids=[node_ids["compute"], node_ids["edge_robotics"]],
        role="leader",
        evidence=ThemeEvidenceSummary(
            coverage_status="complete",
            evidence_refs=[_ev("nvda_rev"), _ev("nvda_guide")],
            source_refs=["scanner", "equity_research"],
            notes="Fixture example only; not a live market claim.",
        ),
        heat_contribution=0.9,
        crowding_level="elevated",
        crowding_signal=CrowdingSignal(
            crowding_level="elevated",
            momentum_overextension="price far above rising 50DMA (placeholder)",
            valuation_stretch="forward multiple above 3yr range (placeholder)",
            explanation="Fixture crowding placeholder; not computed.",
        ),
        notes="Compute leader; also exposed to edge/robotics.",
    )
    mu = ThemeCandidateTicker(
        ticker="MU",
        company_name="Micron Technology",
        theme_id=theme_id,
        subtheme_ids=[sub_memory_id],
        chain_node_ids=[node_ids["memory"]],
        role="second_derivative_beneficiary",
        evidence=ThemeEvidenceSummary(
            coverage_status="partial",
            evidence_refs=[_ev("mu_hbm")],
            source_refs=["news"],
        ),
        heat_contribution=0.6,
        crowding_level="moderate",
        notes="HBM beneficiary of compute demand.",
    )
    vrt = ThemeCandidateTicker(
        ticker="VRT",
        company_name="Vertiv Holdings",
        theme_id=theme_id,
        subtheme_ids=[sub_power_id],
        chain_node_ids=[node_ids["dc_power"]],
        role="supplier",
        evidence=ThemeEvidenceSummary(
            coverage_status="partial",
            evidence_refs=[_ev("vrt_cooling")],
            source_refs=["sector_rotation"],
        ),
        heat_contribution=0.5,
        crowding_level="moderate",
        notes="Data-center power / cooling supplier.",
    )
    msft = ThemeCandidateTicker(
        ticker="MSFT",
        company_name="Microsoft Corporation",
        theme_id=theme_id,
        subtheme_ids=[sub_compute_id],
        chain_node_ids=[node_ids["cloud"]],
        role="platform",
        evidence=ThemeEvidenceSummary(
            coverage_status="complete",
            evidence_refs=[_ev("msft_cloud")],
            source_refs=["equity_research"],
        ),
        heat_contribution=0.55,
        crowding_level="moderate",
        notes="Cloud / platform beneficiary.",
    )
    fixspec = ThemeCandidateTicker(
        ticker="FIXSPEC",
        company_name="Fixture Speculative AI Co (example)",
        theme_id=theme_id,
        subtheme_ids=[sub_compute_id],
        chain_node_ids=[node_ids["applications"]],
        role="speculative",
        evidence=ThemeEvidenceSummary(
            coverage_status="none",
            notes="No fundamental confirmation; narrative-only fixture name.",
        ),
        heat_contribution=0.2,
        crowding_level="high",
        warnings=[
            ThemeRiskWarning(
                warning_type="narrative_only",
                severity="medium",
                message="Speculative example with no fundamental confirmation.",
            )
        ],
        notes="Fictional speculative example.",
    )
    fixlag = ThemeCandidateTicker(
        ticker="FIXLAG",
        company_name="Fixture Laggard Co (example)",
        theme_id=theme_id,
        subtheme_ids=[sub_compute_id],
        chain_node_ids=[node_ids["enterprise_sw"]],
        role="laggard",
        evidence=ThemeEvidenceSummary(coverage_status="partial"),
        heat_contribution=0.1,
        crowding_level="low",
        notes="Fictional laggard example.",
    )

    subthemes = [
        SubthemeRecord(
            subtheme_id=sub_compute_id,
            parent_theme_id=theme_id,
            name="AI Compute",
            description="Accelerators and CPUs powering AI training/inference.",
            heat_score=build_theme_heat_score(
                price_momentum_component=0.9,
                volume_component=0.8,
                breadth_component=0.6,
                narrative_component=0.9,
                fundamental_confirmation_component=0.7,
                freshness_component=0.8,
                crowding_adjustment=0.2,
            ),
            lifecycle_stage="accelerating",
            chain_node_ids=[node_ids["compute"], node_ids["edge_robotics"]],
            candidate_tickers=[nvda, msft, fixspec, fixlag],
        ),
        SubthemeRecord(
            subtheme_id=sub_memory_id,
            parent_theme_id=theme_id,
            name="HBM Memory",
            description="High-bandwidth memory feeding AI compute.",
            heat_score=build_theme_heat_score(
                price_momentum_component=0.7,
                volume_component=0.6,
                breadth_component=0.4,
                narrative_component=0.7,
                # fundamental confirmation deliberately missing -> partial
                freshness_component=0.6,
            ),
            lifecycle_stage="accelerating",
            chain_node_ids=[node_ids["memory"]],
            candidate_tickers=[mu],
        ),
        SubthemeRecord(
            subtheme_id=sub_power_id,
            parent_theme_id=theme_id,
            name="Data-Center Power and Cooling",
            description="Power delivery and thermal management for AI data centers.",
            heat_score=build_theme_heat_score(
                price_momentum_component=0.6,
                volume_component=0.5,
                breadth_component=0.5,
                narrative_component=0.6,
                fundamental_confirmation_component=0.6,
                freshness_component=0.6,
                crowding_adjustment=0.1,
            ),
            lifecycle_stage="accelerating",
            chain_node_ids=[node_ids["dc_power"]],
            candidate_tickers=[vrt],
        ),
    ]

    return ThemeRecord(
        theme_id=theme_id,
        name=name,
        description=(
            "Cross-sector AI theme spanning compute, memory, optical/networking, "
            "data-center power, cloud, enterprise software, applications, and "
            "edge/robotics. Deterministic fixture example."
        ),
        lifecycle_stage="accelerating",
        heat_score=build_theme_heat_score(
            price_momentum_component=0.85,
            volume_component=0.75,
            breadth_component=0.6,
            narrative_component=0.9,
            fundamental_confirmation_component=0.7,
            freshness_component=0.8,
            crowding_adjustment=0.2,
        ),
        discovery_sources=[
            ThemeDiscoverySource(
                source_type="macro",
                description="Liquidity + capex super-cycle backdrop (fixture).",
                evidence_ref=_ev("ai_macro"),
            ),
            ThemeDiscoverySource(
                source_type="narrative",
                description="Persistent AI narrative across news / sell-side.",
                evidence_ref=_ev("ai_narrative"),
            ),
            ThemeDiscoverySource(
                source_type="fund_flow",
                description="Concentrated flows into AI complex (fixture).",
                evidence_ref=_ev("ai_flow"),
            ),
        ],
        source_signals=[
            ThemeHeatSignal(
                signal_type="price_momentum",
                source_type="scanner",
                strength="strong",
                timestamp=SAMPLE_THEME_AS_OF,
                explanation="Broad upside momentum across compute names (fixture).",
                evidence_ref=_ev("ai_mom"),
            ),
            ThemeHeatSignal(
                signal_type="fund_flow",
                source_type="fund_flow",
                strength="strong",
                timestamp=SAMPLE_THEME_AS_OF,
                explanation="Heavy inflows into AI-linked ETFs (fixture).",
                evidence_ref=_ev("ai_flow2"),
            ),
            ThemeHeatSignal(
                signal_type="breadth",
                source_type="scanner",
                strength="moderate",
                timestamp=SAMPLE_THEME_AS_OF,
                explanation="Participation broadening down the chain (fixture).",
            ),
        ],
        narrative_signals=[
            NarrativeSignal(
                narrative_cluster="AI capex super-cycle",
                mention_intensity="strong",
                source_type="narrative",
                timestamp=SAMPLE_THEME_AS_OF,
                explanation="High and sustained mention intensity (fixture).",
                evidence_ref=_ev("ai_narr_capex"),
            ),
        ],
        fundamental_confirmation_signals=[
            FundamentalConfirmationSignal(
                confirmation_type="revenue",
                confirmation_direction="confirming",
                strength="strong",
                explanation="Datacenter revenue growth confirms narrative (fixture).",
                evidence_ref=_ev("ai_rev_confirm"),
            ),
            FundamentalConfirmationSignal(
                confirmation_type="capex_commentary",
                confirmation_direction="confirming",
                strength="moderate",
                explanation="Hyperscaler capex guidance raised (fixture).",
            ),
        ],
        crowding_signals=[
            CrowdingSignal(
                crowding_level="elevated",
                momentum_overextension="leadership extended vs trend (placeholder)",
                valuation_stretch="rich multiples in leaders (placeholder)",
                volume_climax="no climax yet (placeholder)",
                explanation="Elevated but not extreme crowding (fixture placeholder).",
            ),
        ],
        subthemes=subthemes,
        industry_chain_nodes=nodes,
        candidate_tickers=[nvda, mu, vrt, msft, fixspec, fixlag],
        evidence=ThemeEvidenceSummary(
            coverage_status="complete",
            evidence_refs=[_ev("ai_macro"), _ev("ai_rev_confirm")],
            source_refs=["macro", "scanner", "equity_research", "news"],
            notes="Deterministic fixture evidence; not a live data pull.",
        ),
        warnings=[
            ThemeRiskWarning(
                warning_type="crowding",
                severity="medium",
                message=(
                    "Theme is hot but increasingly crowded; high heat is not a "
                    "buy signal and does not imply good entry."
                ),
            ),
        ],
    )


def build_space_theme_fixture() -> ThemeRecord:
    """Deterministic Space theme fixture with subthemes + industry-chain nodes.

    Sample tickers are illustrative fixture examples only — not live claims.
    """
    name = "Space Economy"
    theme_id = make_theme_id(name)

    node_defs = [
        ("launch", "launch"),
        ("sat_mfg", "satellite manufacturing"),
        ("satcom", "satellite communications"),
        ("eo", "earth observation"),
        ("defense_space", "defense space"),
        ("components", "components / materials"),
        ("ground", "ground stations / data services"),
    ]
    node_ids = {key: make_chain_node_id(theme_id, label) for key, label in node_defs}

    chain_topology = {
        "components": ([], ["sat_mfg", "launch"]),
        "launch": (["components"], ["sat_mfg", "satcom", "eo"]),
        "sat_mfg": (["components", "launch"], ["satcom", "eo", "defense_space"]),
        "satcom": (["sat_mfg", "launch"], ["ground"]),
        "eo": (["sat_mfg", "launch"], ["ground"]),
        "defense_space": (["sat_mfg"], []),
        "ground": (["satcom", "eo"], []),
    }
    rep_tickers = {
        "launch": ["RKLB", "FIXLNCH"],
        "sat_mfg": ["FIXSATM"],
        "satcom": ["IRDM", "GSAT"],
        "eo": ["FIXEO"],
        "defense_space": ["LMT", "NOC"],
        "components": ["FIXCMP"],
        "ground": ["FIXGND"],
    }
    nodes = []
    for key, label in node_defs:
        up_keys, down_keys = chain_topology[key]
        nodes.append(
            IndustryChainNode(
                node_id=node_ids[key],
                parent_theme_id=theme_id,
                name=label,
                role_in_chain=key,
                upstream_node_ids=[node_ids[k] for k in up_keys],
                downstream_node_ids=[node_ids[k] for k in down_keys],
                representative_tickers=rep_tickers[key],
            )
        )

    sub_launch_id = make_subtheme_id(theme_id, "Launch")
    sub_satcom_id = make_subtheme_id(theme_id, "Satellite Communications")
    sub_defense_id = make_subtheme_id(theme_id, "Defense Space")

    rklb = ThemeCandidateTicker(
        ticker="RKLB",
        company_name="Rocket Lab USA",
        theme_id=theme_id,
        subtheme_ids=[sub_launch_id],
        chain_node_ids=[node_ids["launch"], node_ids["sat_mfg"]],
        role="leader",
        evidence=ThemeEvidenceSummary(
            coverage_status="partial",
            evidence_refs=[_ev("rklb_launch")],
            source_refs=["news"],
        ),
        heat_contribution=0.7,
        crowding_level="elevated",
        notes="Launch leader; also satellite manufacturing exposure.",
    )
    irdm = ThemeCandidateTicker(
        ticker="IRDM",
        company_name="Iridium Communications",
        theme_id=theme_id,
        subtheme_ids=[sub_satcom_id],
        chain_node_ids=[node_ids["satcom"], node_ids["ground"]],
        role="second_derivative_beneficiary",
        evidence=ThemeEvidenceSummary(coverage_status="partial"),
        heat_contribution=0.4,
        crowding_level="moderate",
        notes="Satellite communications beneficiary.",
    )
    lmt = ThemeCandidateTicker(
        ticker="LMT",
        company_name="Lockheed Martin",
        theme_id=theme_id,
        subtheme_ids=[sub_defense_id],
        chain_node_ids=[node_ids["defense_space"]],
        role="platform",
        evidence=ThemeEvidenceSummary(
            coverage_status="partial",
            source_refs=["sector_rotation"],
        ),
        heat_contribution=0.35,
        crowding_level="low",
        notes="Defense space platform exposure.",
    )

    subthemes = [
        SubthemeRecord(
            subtheme_id=sub_launch_id,
            parent_theme_id=theme_id,
            name="Launch",
            description="Orbital launch capacity and cadence.",
            heat_score=build_theme_heat_score(
                price_momentum_component=0.7,
                volume_component=0.6,
                breadth_component=0.4,
                narrative_component=0.8,
                fundamental_confirmation_component=0.4,
                freshness_component=0.6,
            ),
            lifecycle_stage="accelerating",
            chain_node_ids=[node_ids["launch"]],
            candidate_tickers=[rklb],
        ),
        SubthemeRecord(
            subtheme_id=sub_satcom_id,
            parent_theme_id=theme_id,
            name="Satellite Communications",
            description="LEO/GEO connectivity and data relay.",
            heat_score=build_theme_heat_score(
                price_momentum_component=0.4,
                volume_component=0.3,
                # partial: breadth + narrative missing
                fundamental_confirmation_component=0.4,
            ),
            lifecycle_stage="emerging",
            chain_node_ids=[node_ids["satcom"]],
            candidate_tickers=[irdm],
        ),
        SubthemeRecord(
            subtheme_id=sub_defense_id,
            parent_theme_id=theme_id,
            name="Defense Space",
            description="Government / defense space programs.",
            heat_score=build_theme_heat_score(
                price_momentum_component=0.3,
                volume_component=0.3,
                breadth_component=0.3,
                narrative_component=0.4,
                fundamental_confirmation_component=0.5,
                freshness_component=0.4,
            ),
            lifecycle_stage="consensus",
            chain_node_ids=[node_ids["defense_space"]],
            candidate_tickers=[lmt],
        ),
    ]

    return ThemeRecord(
        theme_id=theme_id,
        name=name,
        description=(
            "Cross-sector space theme spanning launch, satellite manufacturing, "
            "satellite communications, earth observation, defense space, "
            "components/materials, and ground stations/data services. "
            "Deterministic fixture example."
        ),
        lifecycle_stage="emerging",
        heat_score=build_theme_heat_score(
            price_momentum_component=0.6,
            volume_component=0.5,
            breadth_component=0.4,
            narrative_component=0.7,
            fundamental_confirmation_component=0.4,
            freshness_component=0.6,
        ),
        discovery_sources=[
            ThemeDiscoverySource(
                source_type="narrative",
                description="Rising space-economy narrative (fixture).",
                evidence_ref=_ev("space_narrative"),
            ),
            ThemeDiscoverySource(
                source_type="news",
                description="Launch cadence + defense budget headlines (fixture).",
            ),
        ],
        source_signals=[
            ThemeHeatSignal(
                signal_type="narrative",
                source_type="narrative",
                strength="moderate",
                timestamp=SAMPLE_THEME_AS_OF,
                explanation="Growing but uneven narrative strength (fixture).",
            ),
            ThemeHeatSignal(
                signal_type="price_momentum",
                source_type="scanner",
                strength="moderate",
                timestamp=SAMPLE_THEME_AS_OF,
                explanation="Selective momentum concentrated in launch (fixture).",
            ),
        ],
        narrative_signals=[
            NarrativeSignal(
                narrative_cluster="space economy / launch cadence",
                mention_intensity="moderate",
                source_type="narrative",
                timestamp=SAMPLE_THEME_AS_OF,
                explanation="Moderate, rising mentions (fixture).",
            ),
        ],
        fundamental_confirmation_signals=[
            FundamentalConfirmationSignal(
                confirmation_type="backlog",
                confirmation_direction="mixed",
                strength="moderate",
                explanation="Backlogs growing but profitability uneven (fixture).",
            ),
        ],
        crowding_signals=[
            CrowdingSignal(
                crowding_level="moderate",
                explanation="Pockets of crowding in launch leaders (fixture).",
            ),
        ],
        subthemes=subthemes,
        industry_chain_nodes=nodes,
        candidate_tickers=[rklb, irdm, lmt],
        evidence=ThemeEvidenceSummary(
            coverage_status="partial",
            evidence_refs=[_ev("space_narrative")],
            source_refs=["narrative", "news", "sector_rotation"],
            notes="Deterministic fixture evidence; partial coverage.",
        ),
        warnings=[
            ThemeRiskWarning(
                warning_type="unconfirmed_fundamentals",
                severity="medium",
                message="Narrative ahead of fundamentals in parts of the chain.",
            ),
        ],
    )


def build_degraded_theme_fixture() -> ThemeRecord:
    """Deterministic degraded / emerging theme fixture (embodied AI).

    Demonstrates partial evidence and unknown lifecycle / unknown heat-score
    handling: the theme has only narrative-stage signals, no fundamental
    confirmation, an ``unknown`` lifecycle stage, and an ``unknown`` heat score.
    Sample tickers are fictional fixture examples only.
    """
    name = "Embodied AI / Humanoid Robotics"
    theme_id = make_theme_id(name)

    node_label = "humanoid platforms"
    node_id = make_chain_node_id(theme_id, node_label)
    node = IndustryChainNode(
        node_id=node_id,
        parent_theme_id=theme_id,
        name=node_label,
        role_in_chain="platform",
        representative_tickers=["FIXBOT"],
        notes="Single emerging node; chain not yet decomposed (fixture).",
    )

    sub_id = make_subtheme_id(theme_id, "Humanoid Robotics")
    fixbot = ThemeCandidateTicker(
        ticker="FIXBOT",
        company_name="Fixture Humanoid Robotics Co (example)",
        theme_id=theme_id,
        subtheme_ids=[sub_id],
        chain_node_ids=[node_id],
        role="speculative",
        evidence=ThemeEvidenceSummary(
            coverage_status="none",
            notes="No fundamental confirmation; emerging narrative only.",
        ),
        crowding_level="unknown",
        warnings=[
            ThemeRiskWarning(
                warning_type="missing_evidence",
                severity="high",
                message="Insufficient evidence; do not treat as actionable.",
            ),
        ],
        notes="Fictional emerging-theme example.",
    )

    subtheme = SubthemeRecord(
        subtheme_id=sub_id,
        parent_theme_id=theme_id,
        name="Humanoid Robotics",
        description="Early-stage humanoid robotics narrative (fixture).",
        # Heat score deliberately unknown (no components) -> status "unknown".
        heat_score=ThemeHeatScore(),
        lifecycle_stage="unknown",
        chain_node_ids=[node_id],
        candidate_tickers=[fixbot],
        warnings=[
            ThemeRiskWarning(
                warning_type="narrative_only",
                severity="high",
                message="Narrative-only; no fundamental confirmation yet.",
            ),
        ],
    )

    return ThemeRecord(
        theme_id=theme_id,
        name=name,
        description=(
            "Emerging embodied-AI / humanoid-robotics theme with partial "
            "evidence and unknown lifecycle / heat. Deterministic fixture."
        ),
        lifecycle_stage="unknown",
        heat_score=ThemeHeatScore(),  # unknown status by construction
        discovery_sources=[
            ThemeDiscoverySource(
                source_type="narrative",
                description="Early narrative; sparse data (fixture).",
            ),
        ],
        source_signals=[
            ThemeHeatSignal(
                signal_type="narrative",
                source_type="narrative",
                strength="weak",
                timestamp=SAMPLE_THEME_AS_OF,
                explanation="Weak, early narrative signal (fixture).",
            ),
        ],
        narrative_signals=[
            NarrativeSignal(
                narrative_cluster="humanoid robots",
                mention_intensity="weak",
                source_type="narrative",
                explanation="Sparse, emerging mentions (fixture).",
            ),
        ],
        fundamental_confirmation_signals=[
            FundamentalConfirmationSignal(
                confirmation_type="unknown",
                confirmation_direction="unconfirmed",
                strength="unknown",
                explanation="No fundamental confirmation available (fixture).",
            ),
        ],
        crowding_signals=[],
        subthemes=[subtheme],
        industry_chain_nodes=[node],
        candidate_tickers=[fixbot],
        evidence=ThemeEvidenceSummary(
            coverage_status="none",
            notes="No fundamental confirmation; emerging narrative only.",
        ),
        warnings=[
            ThemeRiskWarning(
                warning_type="missing_evidence",
                severity="high",
                message=(
                    "Emerging theme with insufficient evidence; lifecycle and "
                    "heat are unknown, not zero."
                ),
            ),
        ],
    )


def build_default_theme_intelligence_snapshot() -> ThemeIntelligenceSnapshot:
    """Deterministic default snapshot: AI + Space + degraded embodied-AI theme.

    Includes a populated ``validation_summary``. All content is a deterministic
    fixture example — not a live market claim and not investment advice.
    """
    universe = ThemeUniverseSnapshot(
        as_of=SAMPLE_THEME_AS_OF,
        description=(
            "Deterministic Phase 5J fixture theme universe (AI, Space, and an "
            "emerging embodied-AI theme). Examples only; not live data."
        ),
        themes=[
            build_ai_theme_fixture(),
            build_space_theme_fixture(),
            build_degraded_theme_fixture(),
        ],
    )
    snapshot = ThemeIntelligenceSnapshot(
        snapshot_id=make_theme_intelligence_snapshot_id("default"),
        as_of=SAMPLE_THEME_AS_OF,
        description=(
            "Default Phase 5J Theme Intelligence / Market Heat fixture snapshot. "
            "Upstream input layer for the future Phase 5K Opportunity Queue. "
            "Heat is not a buy signal; entry quality is deferred to Phase 5K."
        ),
        universe=universe,
    )
    return attach_validation_summary(snapshot)


def build_empty_theme_intelligence_snapshot() -> ThemeIntelligenceSnapshot:
    """Deterministic, safe EMPTY snapshot (valid empty theme universe)."""
    snapshot = ThemeIntelligenceSnapshot(
        snapshot_id=make_theme_intelligence_snapshot_id("empty"),
        as_of=SAMPLE_THEME_AS_OF,
        description="Safe empty Phase 5J theme intelligence snapshot.",
        universe=ThemeUniverseSnapshot(
            as_of=SAMPLE_THEME_AS_OF,
            description="Empty theme universe.",
        ),
    )
    return attach_validation_summary(snapshot)
