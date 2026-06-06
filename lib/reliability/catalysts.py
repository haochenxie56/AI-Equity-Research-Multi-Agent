"""
lib/reliability/catalysts.py

Standalone schema models, helper functions, and ToolResult wrappers for
catalyst, earnings, and estimate revision data.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no file I/O.
  - Reuses EvidenceRef and ToolResult from lib.reliability.schemas.
  - Reuses make_evidence_id and stable_hash_payload from lib.reliability.adapters.
  - All functions are deterministic and pure — they do not fetch real data.
  - No Catalyst Agent, Earnings Agent, or Estimate Revision Agent is implemented.
  - No live earnings calendar, estimate, analyst, or catalyst API integration.
  - No UI/cockpit is implemented in this phase.
  - Live data connectors and existing data-fetch behaviour are unmodified.

See docs/reliability_phase_2g_catalyst_earnings_revision_schema.md for full
design rationale and rollout context.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import EvidenceRef, ToolResult


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

CatalystType = Literal[
    "earnings",
    "guidance",
    "analyst_day",
    "investor_day",
    "product_launch",
    "fda_regulatory",
    "macro_event",
    "management_change",
    "m_and_a",
    "litigation",
    "dividend",
    "buyback",
    "financing",
    "index_inclusion",
    "sector_event",
    "other",
    "unknown",
]

CatalystTiming = Literal[
    "past",
    "upcoming",
    "ongoing",
    "unknown",
]

CatalystMateriality = Literal[
    "low",
    "medium",
    "high",
    "unknown",
]

CatalystSourceType = Literal[
    "company",
    "sec_filing",
    "news",
    "analyst",
    "exchange",
    "macro_calendar",
    "manual",
    "synthetic",
    "other",
]

EarningsStatus = Literal[
    "confirmed",
    "estimated",
    "reported",
    "unknown",
]

EarningsSurpriseDirection = Literal[
    "beat",
    "miss",
    "inline",
    "unknown",
]

EstimateMetric = Literal[
    "eps",
    "revenue",
    "ebitda",
    "operating_margin",
    "gross_margin",
    "free_cash_flow",
    "price_target",
    "rating",
    "other",
]

RevisionDirection = Literal[
    "upward",
    "downward",
    "mixed",
    "unchanged",
    "unknown",
]

RevisionSourceType = Literal[
    "analyst",
    "consensus",
    "company_guidance",
    "model",
    "manual",
    "synthetic",
    "other",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_CATALYST_TOOL_NAME: str = "catalyst_snapshot"
_CATALYST_METRIC_GROUP: str = "catalyst_snapshot"

# Simple analyst rating rank for revision direction inference
_RATING_RANK: dict[str, int] = {
    "sell": 0,
    "underperform": 1,
    "hold": 2,
    "neutral": 3,
    "market perform": 3,
    "sector perform": 3,
    "buy": 4,
    "outperform": 5,
    "strong buy": 6,
    "overweight": 5,
    "underweight": 1,
}


# ---------------------------------------------------------------------------
# 1. CatalystEvent
# ---------------------------------------------------------------------------

class CatalystEvent(BaseModel):
    """
    One sourced catalyst event for a stock/company.

    Fields:
        catalyst_id:      Non-empty unique identifier for this catalyst.
        ticker:           Non-empty underlying ticker symbol.
        catalyst_type:    Category of catalyst; defaults to ``"unknown"``.
        title:            Non-empty short title for the catalyst.
        description:      Optional extended description.
        event_date:       Optional ISO date string; may be absent for unknown/ongoing.
        timing:           Timing classification; defaults to ``"unknown"``.
        materiality:      Materiality classification; defaults to ``"unknown"``.
        source_type:      Source classification; defaults to ``"synthetic"``.
        source_name:      Optional source or publisher name.
        url:              Optional reference URL.
        related_symbols:  Related ticker symbols.
        evidence_refs:    EvidenceRef list (may be empty at schema level).
        raw_payload:      Original source payload preserved without mutation.
        metadata:         Arbitrary key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    catalyst_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    catalyst_type: CatalystType = "unknown"
    title: str = Field(min_length=1)
    description: Optional[str] = None
    event_date: Optional[str] = None
    timing: CatalystTiming = "unknown"
    materiality: CatalystMateriality = "unknown"
    source_type: CatalystSourceType = "synthetic"
    source_name: Optional[str] = None
    url: Optional[str] = None
    related_symbols: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "CatalystEvent":
        for field_name in ("catalyst_id", "ticker", "title"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 2. EarningsEvent
# ---------------------------------------------------------------------------

class EarningsEvent(BaseModel):
    """
    One earnings event snapshot for a stock/company.

    Fields:
        earnings_id:            Non-empty unique identifier for this event.
        ticker:                 Non-empty underlying ticker symbol.
        fiscal_period:          Optional fiscal period label (e.g. ``"Q1 2026"``).
        fiscal_year:            Optional fiscal year (> 1900 if provided).
        report_date:            Optional scheduled/actual report date string.
        status:                 Earnings status; defaults to ``"unknown"``.
        consensus_eps:          Optional consensus EPS estimate.
        actual_eps:             Optional reported EPS.
        eps_surprise_pct:       Optional EPS surprise percentage (can be negative).
        consensus_revenue:      Optional consensus revenue estimate (>= 0).
        actual_revenue:         Optional actual revenue (>= 0).
        revenue_surprise_pct:   Optional revenue surprise percentage (can be negative).
        guidance_summary:       Optional guidance summary text.
        implied_move_pct:       Optional implied options move percentage (>= 0).
        price_reaction_1d_pct:  Optional 1-day post-earnings price reaction (can be negative).
        source_type:            Source classification; defaults to ``"synthetic"``.
        source_name:            Optional source name.
        evidence_refs:          EvidenceRef list.
        raw_payload:            Original payload.
        metadata:               Arbitrary metadata.
    """

    model_config = ConfigDict(extra="forbid")

    earnings_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    fiscal_period: Optional[str] = None
    fiscal_year: Optional[int] = Field(default=None, gt=1900)
    report_date: Optional[str] = None
    status: EarningsStatus = "unknown"
    consensus_eps: Optional[float] = None
    actual_eps: Optional[float] = None
    eps_surprise_pct: Optional[float] = None
    consensus_revenue: Optional[float] = Field(default=None, ge=0)
    actual_revenue: Optional[float] = Field(default=None, ge=0)
    revenue_surprise_pct: Optional[float] = None
    guidance_summary: Optional[str] = None
    implied_move_pct: Optional[float] = Field(default=None, ge=0)
    price_reaction_1d_pct: Optional[float] = None
    source_type: CatalystSourceType = "synthetic"
    source_name: Optional[str] = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "EarningsEvent":
        for field_name in ("earnings_id", "ticker"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 3. EstimateRevision
# ---------------------------------------------------------------------------

class EstimateRevision(BaseModel):
    """
    One analyst/consensus estimate revision for a stock/company.

    Fields:
        revision_id:    Non-empty unique identifier for this revision.
        ticker:         Non-empty underlying ticker symbol.
        metric:         The financial metric being revised.
        period:         Optional period label (e.g. ``"FY2026"``).
        previous_value: Previous estimate value (numeric or rating string).
        revised_value:  Revised estimate value (numeric or rating string).
        revision_pct:   Optional computed revision percentage (can be negative).
        direction:      Revision direction; defaults to ``"unknown"``.
        revision_date:  Optional date of this revision.
        source_type:    Source classification; defaults to ``"synthetic"``.
        source_name:    Optional source name.
        analyst_firm:   Optional analyst firm name.
        analyst_name:   Optional individual analyst name.
        evidence_refs:  EvidenceRef list.
        raw_payload:    Original payload.
        metadata:       Arbitrary metadata.
    """

    model_config = ConfigDict(extra="forbid")

    revision_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    metric: EstimateMetric
    period: Optional[str] = None
    previous_value: Optional[Union[float, str]] = None
    revised_value: Optional[Union[float, str]] = None
    revision_pct: Optional[float] = None
    direction: RevisionDirection = "unknown"
    revision_date: Optional[str] = None
    source_type: RevisionSourceType = "synthetic"
    source_name: Optional[str] = None
    analyst_firm: Optional[str] = None
    analyst_name: Optional[str] = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "EstimateRevision":
        for field_name in ("revision_id", "ticker"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 4. CatalystSnapshot
# ---------------------------------------------------------------------------

class CatalystSnapshot(BaseModel):
    """
    Container for catalyst events, earnings events, and estimate revisions
    for one ticker at a given point in time.

    Fields:
        snapshot_id:        Non-empty unique identifier for this snapshot.
        ticker:             Non-empty underlying ticker symbol.
        schema_version:     Version of this snapshot schema contract.
        as_of:              Non-empty snapshot date/datetime string.
        catalysts:          List of CatalystEvent instances (may be empty).
        earnings_events:    List of EarningsEvent instances (may be empty).
        estimate_revisions: List of EstimateRevision instances (may be empty).
        warnings:           Advisory warnings about coverage or data quality.
        metadata:           Arbitrary key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    catalysts: list[CatalystEvent] = Field(default_factory=list)
    earnings_events: list[EarningsEvent] = Field(default_factory=list)
    estimate_revisions: list[EstimateRevision] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "CatalystSnapshot":
        for field_name in ("snapshot_id", "ticker", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 5. CatalystCoverageSummary
# ---------------------------------------------------------------------------

class CatalystCoverageSummary(BaseModel):
    """
    Concise coverage summary for a CatalystSnapshot.

    Fields:
        ticker:                   Non-empty ticker symbol.
        catalyst_count:           Total catalysts (>= 0).
        upcoming_catalyst_count:  Catalysts with timing == "upcoming" (>= 0).
        high_materiality_count:   Catalysts with materiality == "high" (>= 0).
        earnings_event_count:     Total earnings events (>= 0).
        estimate_revision_count:  Total estimate revisions (>= 0).
        upward_revision_count:    Revisions with direction == "upward" (>= 0).
        downward_revision_count:  Revisions with direction == "downward" (>= 0).
        categories_present:       Unique CatalystType values seen.
        revision_metrics_present: Unique EstimateMetric values seen.
        warnings:                 Advisory warnings.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    catalyst_count: int = Field(ge=0)
    upcoming_catalyst_count: int = Field(ge=0)
    high_materiality_count: int = Field(ge=0)
    earnings_event_count: int = Field(ge=0)
    estimate_revision_count: int = Field(ge=0)
    upward_revision_count: int = Field(ge=0)
    downward_revision_count: int = Field(ge=0)
    categories_present: list[CatalystType] = Field(default_factory=list)
    revision_metrics_present: list[EstimateMetric] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper 1: infer_catalyst_timing
# ---------------------------------------------------------------------------

def infer_catalyst_timing(
    event_date: Optional[str],
    as_of: Optional[str] = None,
) -> CatalystTiming:
    """
    Infer CatalystTiming from an event_date and reference as_of date.

    Uses ISO date string comparison (YYYY-MM-DD prefix only).
    No external data fetching.

    Returns:
        - ``"past"``     if event_date < as_of
        - ``"ongoing"``  if event_date == as_of
        - ``"upcoming"`` if event_date > as_of
        - ``"unknown"``  if either date is missing or unparseable

    Examples::

        infer_catalyst_timing("2026-01-01", "2026-05-22")  # → "past"
        infer_catalyst_timing("2026-12-31", "2026-05-22")  # → "upcoming"
        infer_catalyst_timing("2026-05-22", "2026-05-22")  # → "ongoing"
        infer_catalyst_timing(None, "2026-05-22")          # → "unknown"
    """
    if not event_date or not as_of:
        return "unknown"

    # Extract YYYY-MM-DD prefix only; reject if too short
    try:
        ev = event_date.strip()[:10]
        ref = as_of.strip()[:10]
        if len(ev) < 10 or len(ref) < 10:
            return "unknown"
        # Validate basic format (digits and hyphens)
        if not (ev[4] == "-" and ev[7] == "-" and ref[4] == "-" and ref[7] == "-"):
            return "unknown"
        # Validate all non-hyphen chars are digits
        ev_digits = ev.replace("-", "")
        ref_digits = ref.replace("-", "")
        if not (ev_digits.isdigit() and ref_digits.isdigit()):
            return "unknown"
    except Exception:
        return "unknown"

    if ev < ref:
        return "past"
    elif ev == ref:
        return "ongoing"
    else:
        return "upcoming"


# ---------------------------------------------------------------------------
# Helper 2: infer_earnings_surprise_direction
# ---------------------------------------------------------------------------

def infer_earnings_surprise_direction(
    eps_surprise_pct: Optional[float] = None,
    revenue_surprise_pct: Optional[float] = None,
) -> EarningsSurpriseDirection:
    """
    Infer EarningsSurpriseDirection from EPS and/or revenue surprise percentages.

    No LLM. Pure numeric comparison.

    Rules:
        - If either clearly positive (> 0) and none clearly negative: ``"beat"``
        - If either clearly negative (< 0) and none clearly positive: ``"miss"``
        - If both are exactly zero or very close to zero: ``"inline"``
        - If mixed signs (one positive, one negative): ``"unknown"``
        - If both are None: ``"unknown"``

    Examples::

        infer_earnings_surprise_direction(5.2, 3.1)    # → "beat"
        infer_earnings_surprise_direction(-2.0, -1.5)  # → "miss"
        infer_earnings_surprise_direction(0.0, 0.0)    # → "inline"
        infer_earnings_surprise_direction(3.0, -1.5)   # → "unknown"
        infer_earnings_surprise_direction(None, None)  # → "unknown"
    """
    values = [(v, v is not None) for v in (eps_surprise_pct, revenue_surprise_pct)]
    provided = [(v, tag) for v, tag in values if tag]

    if not provided:
        return "unknown"

    has_positive = any(v > 0 for v, _ in provided)
    has_negative = any(v < 0 for v, _ in provided)

    if has_positive and has_negative:
        return "unknown"
    if has_positive:
        return "beat"
    if has_negative:
        return "miss"
    # All are exactly 0
    return "inline"


# ---------------------------------------------------------------------------
# Helper 3: infer_revision_direction
# ---------------------------------------------------------------------------

def infer_revision_direction(
    previous_value: Optional[Union[float, str]],
    revised_value: Optional[Union[float, str]],
) -> RevisionDirection:
    """
    Infer RevisionDirection from previous and revised values.

    For numeric values:
        - revised > previous → ``"upward"``
        - revised < previous → ``"downward"``
        - revised == previous → ``"unchanged"``

    For string values (analyst ratings):
        - Uses a simple rank: sell < underperform < hold / neutral / market perform
          / sector perform < buy < outperform / overweight < strong buy
        - If both strings resolve to known ranks: applies numeric comparison.
        - If either string is not in the rank table: ``"unknown"``.

    If either value is missing or types are incompatible: ``"unknown"``.

    Examples::

        infer_revision_direction(2.50, 2.75)          # → "upward"
        infer_revision_direction(2.75, 2.50)          # → "downward"
        infer_revision_direction(2.50, 2.50)          # → "unchanged"
        infer_revision_direction("hold", "buy")       # → "upward"
        infer_revision_direction("buy", "sell")       # → "downward"
        infer_revision_direction(None, 2.75)          # → "unknown"
    """
    if previous_value is None or revised_value is None:
        return "unknown"

    # Numeric comparison
    if isinstance(previous_value, (int, float)) and isinstance(revised_value, (int, float)):
        prev = float(previous_value)
        rev = float(revised_value)
        if rev > prev:
            return "upward"
        elif rev < prev:
            return "downward"
        else:
            return "unchanged"

    # String (rating) comparison
    if isinstance(previous_value, str) and isinstance(revised_value, str):
        prev_rank = _RATING_RANK.get(previous_value.lower().strip())
        rev_rank = _RATING_RANK.get(revised_value.lower().strip())
        if prev_rank is None or rev_rank is None:
            return "unknown"
        if rev_rank > prev_rank:
            return "upward"
        elif rev_rank < prev_rank:
            return "downward"
        else:
            return "unchanged"

    return "unknown"


# ---------------------------------------------------------------------------
# Helper 4: calculate_revision_pct
# ---------------------------------------------------------------------------

def calculate_revision_pct(
    previous_value: Optional[Union[float, str]],
    revised_value: Optional[Union[float, str]],
) -> Optional[float]:
    """
    Calculate the percentage change from previous to revised value.

    Formula: (revised - previous) / abs(previous) * 100

    Returns None if:
        - Either value is None.
        - Either value is not numeric.
        - previous_value is zero (division by zero).

    Examples::

        calculate_revision_pct(2.00, 2.50)   # → 25.0
        calculate_revision_pct(2.50, 2.00)   # → -20.0
        calculate_revision_pct(0.0, 2.00)    # → None (zero previous)
        calculate_revision_pct(None, 2.00)   # → None
        calculate_revision_pct("hold", "buy") # → None (non-numeric)
    """
    if previous_value is None or revised_value is None:
        return None
    try:
        prev = float(previous_value)  # type: ignore[arg-type]
        rev = float(revised_value)    # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if prev == 0.0:
        return None
    return (rev - prev) / abs(prev) * 100.0


# ---------------------------------------------------------------------------
# Helper 5: catalyst_snapshot_from_components
# ---------------------------------------------------------------------------

def catalyst_snapshot_from_components(
    snapshot_id: str,
    ticker: str,
    as_of: str,
    catalysts: Optional[list[CatalystEvent]] = None,
    earnings_events: Optional[list[EarningsEvent]] = None,
    estimate_revisions: Optional[list[EstimateRevision]] = None,
    warnings: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> CatalystSnapshot:
    """
    Build a CatalystSnapshot from provided components.

    Does not fetch data.  Does not mutate input lists or dicts.

    Args:
        snapshot_id:        Non-empty unique identifier.
        ticker:             Non-empty ticker symbol.
        as_of:              Non-empty date/datetime string.
        catalysts:          Optional list of CatalystEvent instances (shallow-copied).
        earnings_events:    Optional list of EarningsEvent instances (shallow-copied).
        estimate_revisions: Optional list of EstimateRevision instances (shallow-copied).
        warnings:           Optional list of advisory warnings (shallow-copied).
        metadata:           Optional metadata dict (shallow-copied).

    Returns:
        A new CatalystSnapshot instance.

    Examples::

        snap = catalyst_snapshot_from_components("snap_001", "NVDA", "2026-05-22")
        assert snap.ticker == "NVDA"
    """
    return CatalystSnapshot(
        snapshot_id=snapshot_id,
        ticker=ticker,
        as_of=as_of,
        catalysts=list(catalysts) if catalysts is not None else [],
        earnings_events=list(earnings_events) if earnings_events is not None else [],
        estimate_revisions=list(estimate_revisions) if estimate_revisions is not None else [],
        warnings=list(warnings) if warnings is not None else [],
        metadata=dict(metadata) if metadata is not None else {},
    )


# ---------------------------------------------------------------------------
# Helper 6: catalyst_tool_result_from_snapshot
# ---------------------------------------------------------------------------

def catalyst_tool_result_from_snapshot(
    run_id: str,
    snapshot: CatalystSnapshot,
    target: Optional[str] = None,
    calculation_version: str = "catalyst_schema_v1",
) -> ToolResult:
    """
    Wrap a CatalystSnapshot into the existing ToolResult model.

    The resulting ToolResult is suitable for submission to
    EvidenceStore.add_tool_result().  The caller is responsible for
    persisting it — this function does not write to disk.

    Args:
        run_id:              Run context ID (from create_run_context).
        snapshot:            CatalystSnapshot to wrap.
        target:              Research target string; defaults to snapshot.ticker.
        calculation_version: Schema/version tag embedded in outputs.

    Returns:
        A ToolResult with:
        - tool_name = "catalyst_snapshot" (stable)
        - evidence_id — deterministic hash of outputs.
        - outputs — full serialised snapshot dict plus calculation_version.
        - inputs — {snapshot_id, ticker, as_of, calculation_version}.
        - ticker = snapshot.ticker.
        - description — includes snapshot_id, ticker, event counts.

    Determinism guarantee:
        Calling this function twice with the same run_id and snapshot
        (identical field values) produces the same evidence_id.

    Examples::

        tr = catalyst_tool_result_from_snapshot("run_001", snap)
        assert tr.tool_name == "catalyst_snapshot"
        assert snap.ticker in tr.evidence_id
    """
    effective_target = target if target else snapshot.ticker

    snapshot_dict = snapshot.model_dump()
    outputs: dict[str, Any] = {
        **snapshot_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_CATALYST_TOOL_NAME,
        target=effective_target,
        metric_group=_CATALYST_METRIC_GROUP,
        payload=outputs,
    )

    description_parts: list[str] = [
        f"CatalystSnapshot {snapshot.snapshot_id!r} ticker={snapshot.ticker!r}"
        f" as_of={snapshot.as_of!r}"
        f" ({len(snapshot.catalysts)} catalyst(s),"
        f" {len(snapshot.earnings_events)} earnings event(s),"
        f" {len(snapshot.estimate_revisions)} revision(s))"
    ]
    if snapshot.warnings:
        description_parts.append("warnings: " + "; ".join(snapshot.warnings))

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_CATALYST_TOOL_NAME,
        run_id=run_id,
        ticker=snapshot.ticker,
        inputs={
            "snapshot_id": snapshot.snapshot_id,
            "ticker": snapshot.ticker,
            "as_of": snapshot.as_of,
            "calculation_version": calculation_version,
        },
        outputs=outputs,
        description="; ".join(description_parts),
    )


# ---------------------------------------------------------------------------
# Helper 7: extract_catalyst_event_paths
# ---------------------------------------------------------------------------

def extract_catalyst_event_paths(snapshot: CatalystSnapshot) -> list[str]:
    """
    Return field paths suitable for EvidenceRef.field_path suggestions.

    Paths use dot-notation with zero-based integer indices for list elements.
    This function is deterministic and stable for the same snapshot.

    Paths cover:
        - catalysts.N.title, description, event_date, catalyst_type
        - earnings_events.N.report_date, consensus_eps, actual_eps,
          eps_surprise_pct, consensus_revenue, actual_revenue,
          revenue_surprise_pct, implied_move_pct, price_reaction_1d_pct
        - estimate_revisions.N.metric, previous_value, revised_value,
          revision_pct, direction

    Examples::

        paths = extract_catalyst_event_paths(snap)
        assert "catalysts.0.title" in paths
    """
    paths: list[str] = []

    for i, _ in enumerate(snapshot.catalysts):
        prefix = f"catalysts.{i}"
        paths.extend([
            f"{prefix}.title",
            f"{prefix}.description",
            f"{prefix}.event_date",
            f"{prefix}.catalyst_type",
        ])

    for i, _ in enumerate(snapshot.earnings_events):
        prefix = f"earnings_events.{i}"
        paths.extend([
            f"{prefix}.report_date",
            f"{prefix}.consensus_eps",
            f"{prefix}.actual_eps",
            f"{prefix}.eps_surprise_pct",
            f"{prefix}.consensus_revenue",
            f"{prefix}.actual_revenue",
            f"{prefix}.revenue_surprise_pct",
            f"{prefix}.implied_move_pct",
            f"{prefix}.price_reaction_1d_pct",
        ])

    for i, _ in enumerate(snapshot.estimate_revisions):
        prefix = f"estimate_revisions.{i}"
        paths.extend([
            f"{prefix}.metric",
            f"{prefix}.previous_value",
            f"{prefix}.revised_value",
            f"{prefix}.revision_pct",
            f"{prefix}.direction",
        ])

    return paths


# ---------------------------------------------------------------------------
# Helper 8: summarize_catalyst_snapshot_coverage
# ---------------------------------------------------------------------------

def summarize_catalyst_snapshot_coverage(
    snapshot: CatalystSnapshot,
) -> CatalystCoverageSummary:
    """
    Build a CatalystCoverageSummary for a CatalystSnapshot.

    Behavior:
        - Counts total catalysts.
        - Counts upcoming catalysts (timing == "upcoming").
        - Counts high materiality catalysts (materiality == "high").
        - Counts earnings events.
        - Counts estimate revisions.
        - Counts upward/downward revisions.
        - Lists unique CatalystType values present.
        - Lists unique EstimateMetric values present.
        - Warns if all three sections are empty.

    Examples::

        summary = summarize_catalyst_snapshot_coverage(snap)
        assert summary.catalyst_count >= 0
    """
    warnings_out: list[str] = []

    catalysts = snapshot.catalysts
    earnings_events = snapshot.earnings_events
    revisions = snapshot.estimate_revisions

    if not catalysts and not earnings_events and not revisions:
        warnings_out.append(
            "CatalystSnapshot is empty: no catalysts, earnings events, or estimate revisions."
        )

    catalyst_count = len(catalysts)
    upcoming_catalyst_count = sum(1 for c in catalysts if c.timing == "upcoming")
    high_materiality_count = sum(1 for c in catalysts if c.materiality == "high")

    earnings_event_count = len(earnings_events)

    estimate_revision_count = len(revisions)
    upward_revision_count = sum(1 for r in revisions if r.direction == "upward")
    downward_revision_count = sum(1 for r in revisions if r.direction == "downward")

    categories_present: list[CatalystType] = sorted(  # type: ignore[assignment]
        set(c.catalyst_type for c in catalysts)
    )
    revision_metrics_present: list[EstimateMetric] = sorted(  # type: ignore[assignment]
        set(r.metric for r in revisions)
    )

    return CatalystCoverageSummary(
        ticker=snapshot.ticker,
        catalyst_count=catalyst_count,
        upcoming_catalyst_count=upcoming_catalyst_count,
        high_materiality_count=high_materiality_count,
        earnings_event_count=earnings_event_count,
        estimate_revision_count=estimate_revision_count,
        upward_revision_count=upward_revision_count,
        downward_revision_count=downward_revision_count,
        categories_present=categories_present,
        revision_metrics_present=revision_metrics_present,
        warnings=warnings_out,
    )


# ---------------------------------------------------------------------------
# Helper 9: validate_catalyst_snapshot
# ---------------------------------------------------------------------------

def validate_catalyst_snapshot(snapshot: CatalystSnapshot) -> list[str]:
    """
    Perform lightweight advisory validation on a CatalystSnapshot.

    Returns warning strings for soft issues.  Does not raise exceptions.
    Does not integrate with ValidationReport in this phase.

    Checked conditions:

    1.  No catalysts, earnings events, or estimate revisions.
    2.  Catalyst ticker mismatch with snapshot ticker.
    3.  Earnings event ticker mismatch with snapshot ticker.
    4.  Estimate revision ticker mismatch with snapshot ticker.
    5.  Catalyst with no evidence_refs.
    6.  Earnings event with no evidence_refs.
    7.  Estimate revision with no evidence_refs.
    8.  High materiality catalyst missing event_date.
    9.  Upcoming catalyst missing event_date.
    10. Earnings event with reported status missing actual EPS or revenue.
    11. Earnings event with confirmed/estimated status missing report_date.
    12. Estimate revision direction conflicts with numeric previous/revised values.
    13. Estimate revision missing revision_date.
    14. Duplicate catalyst title/date pairs.
    15. Duplicate earnings report_date/fiscal_period pairs.
    16. Duplicate revision metric/period/date pairs.

    Examples::

        warnings = validate_catalyst_snapshot(snap)
        # [] for a clean snapshot
    """
    from collections import Counter

    warnings_out: list[str] = []

    catalysts = snapshot.catalysts
    earnings_events = snapshot.earnings_events
    revisions = snapshot.estimate_revisions

    # 1. Empty snapshot
    if not catalysts and not earnings_events and not revisions:
        warnings_out.append(
            "CatalystSnapshot has no catalysts, earnings events, or estimate revisions."
        )

    # 2. Catalyst ticker mismatch
    mismatch_cat = [c.catalyst_id for c in catalysts if c.ticker != snapshot.ticker]
    if mismatch_cat:
        warnings_out.append(
            f"Catalyst ticker does not match snapshot ticker {snapshot.ticker!r}: "
            f"catalyst_ids={mismatch_cat}."
        )

    # 3. Earnings ticker mismatch
    mismatch_earn = [e.earnings_id for e in earnings_events if e.ticker != snapshot.ticker]
    if mismatch_earn:
        warnings_out.append(
            f"Earnings event ticker does not match snapshot ticker {snapshot.ticker!r}: "
            f"earnings_ids={mismatch_earn}."
        )

    # 4. Revision ticker mismatch
    mismatch_rev = [r.revision_id for r in revisions if r.ticker != snapshot.ticker]
    if mismatch_rev:
        warnings_out.append(
            f"Estimate revision ticker does not match snapshot ticker {snapshot.ticker!r}: "
            f"revision_ids={mismatch_rev}."
        )

    # 5. Catalyst with no evidence_refs
    no_ev_cat = [c.catalyst_id for c in catalysts if not c.evidence_refs]
    if no_ev_cat:
        warnings_out.append(
            f"Catalysts with no evidence_refs: catalyst_ids={no_ev_cat}."
        )

    # 6. Earnings event with no evidence_refs
    no_ev_earn = [e.earnings_id for e in earnings_events if not e.evidence_refs]
    if no_ev_earn:
        warnings_out.append(
            f"Earnings events with no evidence_refs: earnings_ids={no_ev_earn}."
        )

    # 7. Estimate revision with no evidence_refs
    no_ev_rev = [r.revision_id for r in revisions if not r.evidence_refs]
    if no_ev_rev:
        warnings_out.append(
            f"Estimate revisions with no evidence_refs: revision_ids={no_ev_rev}."
        )

    # 8. High materiality catalyst missing event_date
    high_no_date = [
        c.catalyst_id for c in catalysts
        if c.materiality == "high" and not c.event_date
    ]
    if high_no_date:
        warnings_out.append(
            f"High materiality catalysts missing event_date: catalyst_ids={high_no_date}."
        )

    # 9. Upcoming catalyst missing event_date
    upcoming_no_date = [
        c.catalyst_id for c in catalysts
        if c.timing == "upcoming" and not c.event_date
    ]
    if upcoming_no_date:
        warnings_out.append(
            f"Upcoming catalysts missing event_date: catalyst_ids={upcoming_no_date}."
        )

    # 10. Reported earnings missing actual EPS or revenue
    reported_missing = [
        e.earnings_id for e in earnings_events
        if e.status == "reported" and (e.actual_eps is None or e.actual_revenue is None)
    ]
    if reported_missing:
        warnings_out.append(
            f"Earnings events with reported status missing actual EPS or revenue: "
            f"earnings_ids={reported_missing}."
        )

    # 11. Confirmed/estimated earnings missing report_date
    confirmed_no_date = [
        e.earnings_id for e in earnings_events
        if e.status in ("confirmed", "estimated") and not e.report_date
    ]
    if confirmed_no_date:
        warnings_out.append(
            f"Confirmed/estimated earnings events missing report_date: "
            f"earnings_ids={confirmed_no_date}."
        )

    # 12. Revision direction conflicts with numeric values
    for rev in revisions:
        if (
            rev.previous_value is not None
            and rev.revised_value is not None
            and isinstance(rev.previous_value, (int, float))
            and isinstance(rev.revised_value, (int, float))
            and rev.direction not in ("unknown", "mixed")
        ):
            inferred = infer_revision_direction(rev.previous_value, rev.revised_value)
            if inferred != "unknown" and inferred != rev.direction:
                warnings_out.append(
                    f"Estimate revision {rev.revision_id!r}: stated direction "
                    f"{rev.direction!r} conflicts with inferred direction "
                    f"{inferred!r} from numeric values "
                    f"({rev.previous_value} → {rev.revised_value})."
                )

    # 13. Revision missing revision_date
    rev_no_date = [r.revision_id for r in revisions if not r.revision_date]
    if rev_no_date:
        warnings_out.append(
            f"Estimate revisions missing revision_date: revision_ids={rev_no_date}."
        )

    # 14. Duplicate catalyst title/date pairs
    cat_keys = [(c.title, c.event_date or "") for c in catalysts]
    cat_key_counts = Counter(cat_keys)
    dup_cat_keys = [k for k, count in cat_key_counts.items() if count > 1]
    if dup_cat_keys:
        warnings_out.append(
            f"Duplicate catalyst title/date pairs detected: {dup_cat_keys[:3]}"
            f"{'...' if len(dup_cat_keys) > 3 else ''}."
        )

    # 15. Duplicate earnings report_date/fiscal_period pairs
    earn_keys = [(e.report_date or "", e.fiscal_period or "") for e in earnings_events]
    earn_key_counts = Counter(earn_keys)
    dup_earn_keys = [k for k, count in earn_key_counts.items() if count > 1]
    if dup_earn_keys:
        warnings_out.append(
            f"Duplicate earnings report_date/fiscal_period pairs detected: "
            f"{dup_earn_keys[:3]}{'...' if len(dup_earn_keys) > 3 else ''}."
        )

    # 16. Duplicate revision metric/period/date pairs
    rev_keys = [(r.metric, r.period or "", r.revision_date or "") for r in revisions]
    rev_key_counts = Counter(rev_keys)
    dup_rev_keys = [k for k, count in rev_key_counts.items() if count > 1]
    if dup_rev_keys:
        warnings_out.append(
            f"Duplicate revision metric/period/date pairs detected: "
            f"{dup_rev_keys[:3]}{'...' if len(dup_rev_keys) > 3 else ''}."
        )

    return warnings_out
