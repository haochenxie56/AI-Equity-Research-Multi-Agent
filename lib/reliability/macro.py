"""
lib/reliability/macro.py

Standalone schema models and helper functions for macro research data.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no file I/O.
  - Reuses EvidenceRef and AgentConfidence from lib.reliability.schemas.
  - Reuses make_evidence_id and stable_hash_payload from lib.reliability.adapters.
  - Reuses ToolResult from lib.reliability.schemas.
  - Nine explicit macro data categories: rates, yield_curve, inflation, growth,
    liquidity, credit_spread, volatility, market_breadth, macro_regime.
  - Schemas define the data contract only — they do not fetch real data,
    manage positions, or call the Claude API.
  - No live macro data fetching is implemented in this phase.
  - No Macro Agent is implemented in this phase.
  - No macro UI/dashboard is implemented in this phase.
  - Live data connectors belong to later data integration phases.
  - UI dashboard belongs to the Investment Cockpit phase.

See docs/reliability_phase_2c_macro_toolresult_schema.md for full design
rationale and rollout context.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from lib.reliability.adapters import make_evidence_id
from lib.reliability.schemas import AgentConfidence, EvidenceRef, ToolResult


# ---------------------------------------------------------------------------
# Macro data category type alias
# ---------------------------------------------------------------------------

MacroDataCategory = Literal[
    "rates",
    "yield_curve",
    "inflation",
    "growth",
    "liquidity",
    "credit_spread",
    "volatility",
    "market_breadth",
    "macro_regime",
]

_ALL_MACRO_CATEGORIES: tuple[str, ...] = (
    "rates",
    "yield_curve",
    "inflation",
    "growth",
    "liquidity",
    "credit_spread",
    "volatility",
    "market_breadth",
    "macro_regime",
)

# Categories whose absence should trigger a warning in validate_macro_snapshot.
_MAJOR_MACRO_CATEGORIES: frozenset[str] = frozenset(
    {"rates", "yield_curve", "inflation", "volatility", "market_breadth"}
)

_MACRO_TOOL_NAME: str = "macro_snapshot"
_MACRO_METRIC_GROUP: str = "macro_snapshot"


# ---------------------------------------------------------------------------
# MacroRegimeSignal sub-type aliases (defined early for reuse)
# ---------------------------------------------------------------------------

MacroRegimeCategory = Literal[
    "risk_on_risk_off",
    "rates",
    "liquidity",
    "growth",
    "inflation",
    "credit",
    "volatility",
    "breadth",
]

MacroRegimeSignalValue = Literal[
    "risk_on",
    "risk_off",
    "neutral",
    "tightening",
    "easing",
    "expansion",
    "contraction",
    "high",
    "low",
    "mixed",
    "unknown",
]


# ---------------------------------------------------------------------------
# 1. MacroIndicator
# ---------------------------------------------------------------------------

class MacroIndicator(BaseModel):
    """
    One sourced macro datapoint.

    Fields:
        name:             Non-empty label for the indicator
                          (e.g. ``"fed_funds_rate"``).
        category:         One of the nine ``MacroDataCategory`` values.
        value:            The indicator value; may be numeric or a string label
                          (e.g. ``5.25``, ``"expanding"``).
        unit:             Optional unit description (e.g. ``"%"``, ``"bps"``).
        as_of:            Non-empty date/datetime string indicating data vintage.
        source:           Non-empty source name (e.g. ``"FRED"``, ``"Bloomberg"``).
        description:      Optional human-readable description.
        frequency:        Optional update frequency (e.g. ``"daily"``,
                          ``"monthly"``).
        stale_after_days: Optional integer — number of days before this reading
                          should be considered stale.  If provided, should be
                          positive (``>= 1``); the advisory validator warns if
                          ``<= 0``.
        metadata:         Optional arbitrary key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    category: MacroDataCategory
    # Union ordered bool-first so that True/False are not coerced to int/float.
    value: Union[bool, int, float, str]
    unit: Optional[str] = None
    as_of: str = Field(min_length=1)
    source: str = Field(min_length=1)
    description: Optional[str] = None
    frequency: Optional[str] = None
    stale_after_days: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 2. MacroSnapshot
# ---------------------------------------------------------------------------

class MacroSnapshot(BaseModel):
    """
    Container for macro indicators for one research run.

    Fields:
        snapshot_id:    Non-empty unique identifier for this snapshot.
        schema_version: Version of this snapshot schema contract.
        as_of:          Non-empty date/datetime string for the snapshot vintage.
        indicators:     List of ``MacroIndicator`` instances (may be partial).
        notes:          Optional free-text notes from the researcher.
        warnings:       Advisory warnings about snapshot quality or coverage.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    indicators: list[MacroIndicator] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 3. MacroRegimeSignal
# ---------------------------------------------------------------------------

class MacroRegimeSignal(BaseModel):
    """
    A deterministic or analyst-defined regime signal based on macro indicators.

    Fields:
        regime_name:  Non-empty name for this regime signal
                      (e.g. ``"rate_environment"``).
        category:     One of the eight ``MacroRegimeCategory`` values.
        signal:       One of the eleven ``MacroRegimeSignalValue`` values.
        rationale:    Non-empty human-readable rationale for the signal.
        evidence_refs: Optional ToolResult evidence supporting the signal.
        confidence:   Optional agent confidence assessment.
    """

    model_config = ConfigDict(extra="forbid")

    regime_name: str = Field(min_length=1)
    category: MacroRegimeCategory
    signal: MacroRegimeSignalValue
    rationale: str = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: Optional[AgentConfidence] = None


# ---------------------------------------------------------------------------
# 4. MacroRegimeAssessment
# ---------------------------------------------------------------------------

class MacroRegimeAssessment(BaseModel):
    """
    Container for macro regime interpretation-ready outputs.

    Partial signals are allowed — not all regime categories need data.

    Fields:
        target:         Non-empty research target; defaults to ``"macro"``.
        schema_version: Version of this assessment schema contract.
        as_of:          Non-empty date/datetime string.
        signals:        List of ``MacroRegimeSignal`` instances.
        summary:        Optional free-text regime summary.
        warnings:       Advisory warnings about signal quality or coverage.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(default="macro", min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    signals: list[MacroRegimeSignal] = Field(default_factory=list)
    summary: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper 1: default_macro_staleness_rules
# ---------------------------------------------------------------------------

def default_macro_staleness_rules() -> dict[str, int]:
    """
    Return recommended ``stale_after_days`` values by ``MacroDataCategory``.

    These are schema-level advisory defaults only — they are not live
    validation rules.  Operators may override them per deployment context.

    Returns:
        ``dict[str, int]`` mapping each category string to its recommended
        maximum age in days.

    Rationale for defaults:

    +------------------+------+-------------------------------------------+
    | Category         | Days | Rationale                                 |
    +==================+======+===========================================+
    | rates            | 2    | Central bank rate decisions are infrequent|
    |                  |      | but market rates move daily                |
    +------------------+------+-------------------------------------------+
    | yield_curve      | 2    | Curve moves every trading day             |
    +------------------+------+-------------------------------------------+
    | inflation        | 45   | CPI/PCE released monthly                  |
    +------------------+------+-------------------------------------------+
    | growth           | 45   | GDP released quarterly; proxy monthly      |
    +------------------+------+-------------------------------------------+
    | liquidity        | 7    | Fed balance sheet weekly                  |
    +------------------+------+-------------------------------------------+
    | credit_spread    | 3    | IG/HY spreads move daily                  |
    +------------------+------+-------------------------------------------+
    | volatility       | 2    | VIX and realized vol update daily         |
    +------------------+------+-------------------------------------------+
    | market_breadth   | 2    | A/D data daily                            |
    +------------------+------+-------------------------------------------+
    | macro_regime     | 7    | Regime calls are weekly or event-driven   |
    +------------------+------+-------------------------------------------+

    Examples::

        rules = default_macro_staleness_rules()
        assert rules["inflation"] == 45
        assert set(rules.keys()) >= {"rates", "yield_curve", "inflation"}
    """
    return {
        "rates": 2,
        "yield_curve": 2,
        "inflation": 45,
        "growth": 45,
        "liquidity": 7,
        "credit_spread": 3,
        "volatility": 2,
        "market_breadth": 2,
        "macro_regime": 7,
    }


# ---------------------------------------------------------------------------
# Helper 2: macro_snapshot_from_indicators
# ---------------------------------------------------------------------------

def macro_snapshot_from_indicators(
    snapshot_id: str,
    as_of: str,
    indicators: list[MacroIndicator],
    notes: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
) -> MacroSnapshot:
    """
    Build a ``MacroSnapshot`` from provided indicators.

    Does not fetch data.  Does not mutate inputs.

    Args:
        snapshot_id: Non-empty unique identifier.
        as_of:       Non-empty date/datetime string.
        indicators:  List of ``MacroIndicator`` instances.  A shallow copy
                     is taken; the original list is not mutated.
        notes:       Optional list of notes (shallow-copied).
        warnings:    Optional list of warnings (shallow-copied).

    Returns:
        A new ``MacroSnapshot`` instance.

    Examples::

        ind = MacroIndicator(name="fed_rate", category="rates",
                             value=5.25, as_of="2026-05-01", source="FRED")
        snap = macro_snapshot_from_indicators("snap_001", "2026-05-01", [ind])
        assert snap.snapshot_id == "snap_001"
        assert len(snap.indicators) == 1
    """
    return MacroSnapshot(
        snapshot_id=snapshot_id,
        as_of=as_of,
        indicators=list(indicators),
        notes=list(notes) if notes is not None else [],
        warnings=list(warnings) if warnings is not None else [],
    )


# ---------------------------------------------------------------------------
# Helper 3: macro_tool_result_from_snapshot
# ---------------------------------------------------------------------------

def macro_tool_result_from_snapshot(
    run_id: str,
    snapshot: MacroSnapshot,
    target: str = "macro",
    calculation_version: str = "macro_schema_v1",
) -> ToolResult:
    """
    Wrap a ``MacroSnapshot`` into the existing ``ToolResult`` model.

    The resulting ``ToolResult`` is suitable for submission to
    ``EvidenceStore.add_tool_result()``.  The caller is responsible for
    persisting it — this function does not write to disk.

    Args:
        run_id:              Run context ID (from ``create_run_context``).
        snapshot:            ``MacroSnapshot`` to wrap.
        target:              Research target string; defaults to ``"macro"``.
        calculation_version: Schema/version tag embedded in outputs for
                             auditability.

    Returns:
        A ``ToolResult`` with:

        - ``tool_name = "macro_snapshot"``
        - ``evidence_id`` — deterministic hash of outputs.
        - ``outputs`` — serialised snapshot dict plus calculation_version.
        - ``inputs`` — ``{snapshot_id, as_of, calculation_version}``.
        - ``ticker = None`` — macro data is not ticker-specific.
        - ``description`` — includes snapshot_id, as_of, and any warnings.

    Determinism guarantee:
        Calling this function twice with the same ``run_id`` and ``snapshot``
        (identical field values) produces the same ``evidence_id``.

    Examples::

        tr = macro_tool_result_from_snapshot("run_001", snap)
        assert tr.tool_name == "macro_snapshot"
        assert "macro_snapshot" in tr.evidence_id
    """
    # Serialise snapshot deterministically (no time-based fields on MacroSnapshot)
    snapshot_dict = snapshot.model_dump()
    outputs: dict[str, Any] = {
        **snapshot_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_MACRO_TOOL_NAME,
        target=target,
        metric_group=_MACRO_METRIC_GROUP,
        payload=outputs,
    )

    description_parts: list[str] = [
        f"MacroSnapshot {snapshot.snapshot_id!r} as_of {snapshot.as_of!r}"
        f" ({len(snapshot.indicators)} indicator(s))"
    ]
    if snapshot.warnings:
        description_parts.append("warnings: " + "; ".join(snapshot.warnings))

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_MACRO_TOOL_NAME,
        run_id=run_id,
        ticker=None,  # Macro data is not ticker-specific
        inputs={
            "snapshot_id": snapshot.snapshot_id,
            "as_of": snapshot.as_of,
            "calculation_version": calculation_version,
        },
        outputs=outputs,
        description="; ".join(description_parts),
    )


# ---------------------------------------------------------------------------
# Helper 4: extract_macro_indicator_paths
# ---------------------------------------------------------------------------

def extract_macro_indicator_paths(snapshot: MacroSnapshot) -> list[str]:
    """
    Return field paths suitable for ``EvidenceRef.field_path`` suggestions.

    Paths use dot-notation with zero-based integer indices for list elements.
    This function is deterministic and stable for the same snapshot.

    Args:
        snapshot: ``MacroSnapshot`` to extract paths from.

    Returns:
        A list of field path strings, e.g.:

        - ``"indicators.0.name"``
        - ``"indicators.0.category"``
        - ``"indicators.0.value"``
        - ``"indicators.0.as_of"``
        - ``"indicators.0.source"``

    Examples::

        paths = extract_macro_indicator_paths(snap)
        assert "indicators.0.value" in paths
    """
    paths: list[str] = []
    for i, _ in enumerate(snapshot.indicators):
        prefix = f"indicators.{i}"
        paths.extend([
            f"{prefix}.name",
            f"{prefix}.category",
            f"{prefix}.value",
            f"{prefix}.as_of",
            f"{prefix}.source",
        ])
    return paths


# ---------------------------------------------------------------------------
# Helper 5: summarize_macro_snapshot_coverage
# ---------------------------------------------------------------------------

def summarize_macro_snapshot_coverage(snapshot: MacroSnapshot) -> dict[str, Any]:
    """
    Return a concise coverage summary for *snapshot*.

    Returns:
        A ``dict`` with:

        - ``"categories_present"`` (list[str]): Unique categories in the
          snapshot, sorted alphabetically.
        - ``"categories_missing"`` (list[str]): Categories from
          ``_ALL_MACRO_CATEGORIES`` not represented in the snapshot, sorted.
        - ``"indicator_count"`` (int): Total number of indicators.
        - ``"stale_rule_categories_available"`` (list[str]): Keys from
          ``default_macro_staleness_rules()``.
        - ``"warnings_count"`` (int): Number of snapshot-level warnings.

    Examples::

        summary = summarize_macro_snapshot_coverage(snap)
        summary["indicator_count"]          # → int
        summary["categories_missing"]       # → ["credit_spread", ...]
    """
    present = sorted({ind.category for ind in snapshot.indicators})
    all_cats = set(_ALL_MACRO_CATEGORIES)
    missing = sorted(all_cats - set(present))
    staleness_keys = list(default_macro_staleness_rules().keys())

    return {
        "categories_present": present,
        "categories_missing": missing,
        "indicator_count": len(snapshot.indicators),
        "stale_rule_categories_available": staleness_keys,
        "warnings_count": len(snapshot.warnings),
    }


# ---------------------------------------------------------------------------
# Helper 6: validate_macro_snapshot
# ---------------------------------------------------------------------------

def validate_macro_snapshot(snapshot: MacroSnapshot) -> list[str]:
    """
    Perform lightweight advisory validation on *snapshot*.

    Returns warning strings for soft issues.  Does not raise exceptions.
    Does not integrate with ``ValidationReport`` in this phase.

    Checked conditions:

    +----------------------------------------------------------------------+
    | Condition                                                            |
    +======================================================================+
    | No indicators at all                                                 |
    +----------------------------------------------------------------------+
    | Duplicate indicator names within the same category                   |
    +----------------------------------------------------------------------+
    | Missing major categories: rates, yield_curve, inflation,             |
    | volatility, market_breadth                                           |
    +----------------------------------------------------------------------+
    | ``stale_after_days <= 0`` if provided                                |
    +----------------------------------------------------------------------+
    | String value that is empty or blank                                  |
    +----------------------------------------------------------------------+

    Args:
        snapshot: ``MacroSnapshot`` to validate.

    Returns:
        List of warning strings (may be empty for a clean snapshot).

    Examples::

        warnings = validate_macro_snapshot(snap)
        assert all(isinstance(w, str) for w in warnings)
    """
    warnings: list[str] = []

    if not snapshot.indicators:
        warnings.append(
            "MacroSnapshot has no indicators. "
            "At least one macro indicator is expected for useful analysis."
        )
        # No point continuing other checks if there are no indicators.
        return warnings

    # Duplicate name within same category
    seen: set[tuple[str, str]] = set()
    for ind in snapshot.indicators:
        key = (ind.category, ind.name)
        if key in seen:
            warnings.append(
                f"Duplicate indicator name='{ind.name}' within "
                f"category='{ind.category}'. "
                "Each indicator name should be unique within its category."
            )
        seen.add(key)

    # Missing major categories
    present_categories = {ind.category for ind in snapshot.indicators}
    for cat in sorted(_MAJOR_MACRO_CATEGORIES):
        if cat not in present_categories:
            warnings.append(
                f"Major macro category '{cat}' is not represented in this snapshot. "
                "Consider adding at least one indicator for this category."
            )

    # stale_after_days <= 0
    for ind in snapshot.indicators:
        if ind.stale_after_days is not None and ind.stale_after_days <= 0:
            warnings.append(
                f"Indicator '{ind.name}' (category='{ind.category}') has "
                f"stale_after_days={ind.stale_after_days} which is not positive. "
                "stale_after_days should be >= 1 if provided."
            )

    # Blank string values
    for ind in snapshot.indicators:
        if isinstance(ind.value, str) and not ind.value.strip():
            warnings.append(
                f"Indicator '{ind.name}' (category='{ind.category}') has an "
                "empty or blank string value. "
                "String values should be non-blank descriptions."
            )

    return warnings
