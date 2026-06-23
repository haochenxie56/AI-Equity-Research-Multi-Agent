"""
lib/agents/market_structure_agent.py

Phase 8B — MarketStructureAgent, production implementation.

The third PRODUCTION agent on the Phase 8A framework. It turns the
deterministic market-internals fragility reading
(``lib.market_internals.compute_market_fragility`` -> ``FragilityReading``)
into a horizon-aware, evidence-backed ``AgentOutput`` for the PM layer:

  market internals  ->  compute_market_fragility (deterministic, in Cockpit)
                    ->  FragilityReading INJECTED here (no second compute)
                    ->  deterministic confidence metrics (short / mid / long)
                    ->  THREE ToolResults into the EvidenceStore (numeric firewall)
                    ->  constrained Claude prompt -> validated AgentResult
                    ->  AgentOutput (JSONL).

Reliability rules honoured here (mirrors MacroRegimeAgent / MoneyFlowAgent):
  * Every NUMBER the LLM may cite is computed in code and persisted as evidence
    BEFORE the LLM runs. The three confidence metrics, the coverage/clarity
    decomposition, and the trailing-deterioration run are all deterministic —
    the LLM never invents them.
  * TIGHTEN-ONLY semantics are preserved end to end. Market internals are a
    leading CAUTION layer: the agent's prompt forbids any bullish / add-exposure
    / loosen recommendation, forbids overriding the (frozen) MacroRegime read,
    and forbids implying a ``normal``-but-degraded reading means "market is
    healthy". The deterministic fragility gate (high -> SHORT only) is unchanged
    and untouched; this agent only INTERPRETS, it never gates.
  * Fully fail-closed: ``run_llm_agent`` already returns a rule-based fallback on
    any Claude/parse error; an OUTER guard here guarantees that nothing
    (evidence plumbing, validation errors, unexpected exceptions) ever propagates
    to the Cockpit caller.

IMPORT DISCIPLINE: NO ``lib.reliability`` AND NO ``lib.agent_framework`` import
at module-load time. Every such helper (``create_run_context``,
``run_llm_agent``, ``processed_signals_to_tool_result``,
``_fallback_agent_output``) is imported lazily inside the function that needs it.
Only stdlib is imported at module level. This keeps the module eager-import-cheap
and lets tests patch any dependency at its source module.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # annotations only — never imported at runtime here
    from lib.agent_framework.agent_output import AgentOutput
    from lib.market_internals import FragilityReading


_log = logging.getLogger("agents.market_structure_agent")

# The five CORE data components whose absence reduces the live signal coverage.
# ``leading_theme_breadth_narrowing`` is DELIBERATELY excluded — it is permanently
# scaffolded (no persisted theme-breadth history) so it is always degraded and
# always False; counting it would falsely floor coverage on every refresh.
_CORE_DEGRADE_CODES = frozenset({
    "distribution_days",
    "breadth",
    "earnings_reaction",
    "offense_defense",
    "leading_theme_volume",
})
_N_CORE_DATA_COMPONENTS = 5      # len(_CORE_DEGRADE_CODES); the coverage denominator
_HIGH_POINTS_THRESHOLD = 4       # points >= 4 -> high level (mirrors INTERNALS_CONFIG)

# trailing elevated+ sessions -> mid_confidence (same saturating linear
# interpolation pattern as MacroRegimeAgent._MID_CONFIDENCE_BREAKPOINTS).
_MID_CONFIDENCE_BREAKPOINTS = [(0, 0.0), (2, 0.4), (4, 0.7), (6, 1.0)]

# fragility level rank (mirrors lib.market_internals._LEVEL_RANK). The mid-horizon
# trend counts the trailing run of sessions at/above ELEVATED (rank >= 1).
_LEVEL_RANK = {"normal": 0, "elevated": 1, "high": 2}
_ELEVATED_RANK = 1

# Long-horizon rationale (recorded in the confidence ToolResult description and
# emitted in the TR3 payload). Market internals are short-to-mid signals; they
# carry no long-horizon information.
_LONG_RATIONALE = (
    "Market internals are short-to-mid caution signals; "
    "not meaningful beyond ~1 month — long horizon defers "
    "to MacroRegimeAgent."
)


def end_of_today_iso() -> str:
    """Return today's date at 23:59:59 UTC as an ISO datetime string.

    Mirrors ``macro_regime_agent.end_of_today_iso`` / ``money_flow_agent``;
    defined locally so this module pulls in no ``lib.agent_framework``
    dependency at import time.
    """
    now = datetime.now(timezone.utc)
    return now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Small field readers (tolerate a dataclass OR a dict fixture)
# ---------------------------------------------------------------------------

def _attr(obj, name: str, default=None):
    """Read ``name`` from a dataclass/object (``getattr``) or a dict (``.get``)."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _series_raw_level(entry) -> str:
    """The raw fragility level out of one rolling-series entry.

    The producer emits each entry as a ``(date_str, raw_level, points)`` tuple
    (see ``market_internals.compute_rolling_raw_series``); we also tolerate a
    dict fixture. Fail-closed -> "normal".
    """
    if isinstance(entry, dict):
        return str(entry.get("raw_level", entry.get("fragility_raw_level", "normal")))
    try:
        return str(entry[1])
    except (TypeError, IndexError, KeyError):
        return "normal"


def _count_core_degraded(reading: "FragilityReading") -> int:
    """How many of the five CORE data components are degraded in this reading."""
    degraded = _attr(reading, "degraded", None) or []
    try:
        present = set(degraded)
    except TypeError:
        return 0
    return sum(1 for code in _CORE_DEGRADE_CODES if code in present)


def _trailing_elevated_run(reading: "FragilityReading") -> int:
    """Trailing run of rolling-series sessions at/above ELEVATED (most recent end).

    Counts consecutive entries from the END of ``rolling_raw_series`` whose raw
    level rank is >= ``_ELEVATED_RANK`` (elevated or high). 0 when the series is
    empty or the most-recent entry is ``normal``.
    """
    series = _attr(reading, "rolling_raw_series", None) or []
    run = 0
    for entry in reversed(list(series)):
        if _LEVEL_RANK.get(_series_raw_level(entry), 0) >= _ELEVATED_RANK:
            run += 1
        else:
            break
    return run


# ---------------------------------------------------------------------------
# Deterministic confidence + classifier (no LLM)
# ---------------------------------------------------------------------------

def _coverage(reading: "FragilityReading") -> float:
    """Fraction of the five CORE data components that are present (not degraded).

    ``coverage = 1.0 - n_degraded_core / _N_CORE_DATA_COMPONENTS``. Range 0.0..1.0.
    All five core components degraded -> 0.0.
    """
    return 1.0 - (_count_core_degraded(reading) / _N_CORE_DATA_COMPONENTS)


def _clarity(reading: "FragilityReading") -> float:
    """How decisively the live internals fired, saturating at the high threshold.

    ``clarity = min(points, _HIGH_POINTS_THRESHOLD) / _HIGH_POINTS_THRESHOLD``.
    Range 0.0..1.0; ``points == 0`` -> 0.0; points >= 4 -> 1.0 (saturates).
    """
    points = int(_attr(reading, "points", 0) or 0)
    return min(points, _HIGH_POINTS_THRESHOLD) / _HIGH_POINTS_THRESHOLD


def _compute_short_confidence(reading: "FragilityReading") -> float:
    """Live-signal confidence = coverage x clarity.

    Confidence in the short-term CAUTION read is how decisively the internals
    fired (``clarity``) discounted by how much of the underlying data was present
    (``coverage``). Both terms are deterministic, computed before any LLM call.

    Edge cases (all -> 0.0):
      * ``points == 0`` (no signal) -> ``clarity == 0`` -> 0.0, regardless of
        coverage. With empty ``degraded`` this is "full data, no signal", NOT a
        degraded path (see ``_compute_signal_basis``).
      * all five core components degraded -> ``coverage == 0`` -> 0.0.

    Range: 0.0..1.0 (rounded to 6 dp).
    """
    return round(_coverage(reading) * _clarity(reading), 6)


def _compute_mid_confidence(reading: "FragilityReading") -> float:
    """Fragility-trend persistence over the rolling raw series.

    The mid horizon trusts a PERSISTENT deterioration, not a single-day spike:
    it counts the trailing run of sessions at/above ELEVATED and maps it through
    ``_MID_CONFIDENCE_BREAKPOINTS`` (linear interpolation, clamped at the ends:
    run 0 -> 0.0, 2 -> 0.4, 4 -> 0.7, >=6 -> 1.0).

    Degraded paths:
      * empty ``rolling_raw_series`` -> 0.0 (no signal trail at all).
      * the trail cannot be trusted to replay the right market —
        ``vintage_mismatch`` is True OR ``hysteresis_source != "rolling"`` (the
        producer fell back to the snapshot audit trail). The trailing run is
        still interpolated normally and the result is then CAPPED at 0.1 (a cap,
        NOT a floor): a flat ``normal`` trail (run 0) still yields 0.0, while a
        deteriorating trail is trusted at most a little (<= 0.1).

    Range: 0.0..1.0 (rounded to 6 dp).
    """
    series = _attr(reading, "rolling_raw_series", None) or []
    if not series:
        return 0.0
    run = _trailing_elevated_run(reading)
    interpolated = _interpolate(run, _MID_CONFIDENCE_BREAKPOINTS)
    if (bool(_attr(reading, "vintage_mismatch", False))
            or _attr(reading, "hysteresis_source", "") != "rolling"):
        return round(min(interpolated, 0.1), 6)  # cap at 0.1, NOT a floor
    return round(interpolated, 6)


def _compute_long_confidence() -> float:
    """Always 0.0 — see ``_LONG_RATIONALE``.

    Market internals are intraday-to-~1-month caution signals; they carry no
    long-horizon information, so the long confidence is structurally zero (mirrors
    ``MoneyFlowAgent._compute_long_confidence``).
    """
    return 0.0


def _compute_signal_basis(reading: "FragilityReading") -> str:
    """Three-way classifier distinguishing the meaning of a low/zero short read.

    A ``normal`` level + zero points is ambiguous: it can mean the data is
    present and constructive, OR that the internals could not be assessed. This
    classifier resolves the two so the prompt can speak honestly:

      * ``"signal_present"``       — points fired AND something triggered.
      * ``"degraded_insufficient"`` — no signal AND >= 3 core components degraded
                                      (data coverage too thin to assess — must NOT
                                      be read as "market healthy").
      * ``"full_data_no_signal"``  — no signal but the data IS present (genuinely
                                      constructive structure).
    """
    points = int(_attr(reading, "points", 0) or 0)
    triggered = _attr(reading, "triggered", None) or []
    if points > 0 and triggered:
        return "signal_present"
    if _count_core_degraded(reading) >= 3:
        return "degraded_insufficient"
    return "full_data_no_signal"


def _interpolate(x: float, breakpoints: list) -> float:
    """Saturating linear interpolation of ``x`` through ``(in, out)`` breakpoints.

    Mirrors ``MacroRegimeAgent._interpolate_mid_confidence``: clamped to the
    endpoints outside the range, linear between adjacent breakpoints.
    """
    if x <= breakpoints[0][0]:
        return breakpoints[0][1]
    if x >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for (x0, y0), (x1, y1) in zip(breakpoints, breakpoints[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            frac = (x - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0)
    return breakpoints[-1][1]  # unreachable; defensive


# ---------------------------------------------------------------------------
# task_instruction builder
# ---------------------------------------------------------------------------

def _trend_descriptor(reading: "FragilityReading") -> str:
    """Qualitative fragility trend (rising / falling / stable) over the series."""
    series = list(_attr(reading, "rolling_raw_series", None) or [])
    if len(series) < 2:
        return "insufficient history"
    first = _LEVEL_RANK.get(_series_raw_level(series[0]), 0)
    last = _LEVEL_RANK.get(_series_raw_level(series[-1]), 0)
    if last > first:
        return "rising"
    if last < first:
        return "falling"
    return "stable"


def _build_task_instruction(reading: "FragilityReading", signal_basis: str) -> str:
    """Build the dynamic, horizon-aware MarketStructureAgent task instruction.

    All interpolated context is QUALITATIVE (level words, triggered component
    names, trend direction, signal_basis) — never numeric — so the model is never
    handed a number to echo. The REQUIRED OUTPUT FORMAT block uses 4-space
    indentation (NOT triple-backtick fences, which confuse the JSON extractor in
    agent_runner).
    """
    level = str(_attr(reading, "level", "normal") or "normal")
    raw_level = str(_attr(reading, "raw_level", "normal") or "normal")
    triggered = list(_attr(reading, "triggered", None) or [])
    triggered_str = ", ".join(triggered) if triggered else "none"
    trend = _trend_descriptor(reading)

    return (
        "You are MarketStructureAgent. Synthesize deterministic market-internals "
        "fragility signals into actionable STRUCTURAL CAUTION context for the PM "
        "agents. Market internals are a leading-caution layer: they warn when "
        "the market's internal structure is deteriorating BEFORE price confirms.\n\n"
        f"Current fragility level: {level} (raw, pre-hysteresis: {raw_level}). "
        f"Components that fired: {triggered_str}. "
        f"Recent-session trend: {trend}. "
        f"Signal basis: {signal_basis}.\n\n"
        "Based on the evidence packet, provide THREE findings:\n"
        "1. SHORT-TERM (intraday-2 weeks): one-sentence actionable judgment for "
        "ShortTermPM. State the current fragility level and what it means for "
        "near-term entry decisions, and name which components fired and their "
        "directional implication for caution. If signal basis is "
        "\"full_data_no_signal\", you MUST state that no warning signal was "
        "detected and the market structure appears constructive (do NOT stay "
        "silent). If signal basis is \"degraded_insufficient\", you MUST state "
        "explicitly that data coverage is insufficient to assess internals and "
        "MUST NOT imply the market is healthy.\n"
        "2. MID-TERM (2-6 weeks): one-sentence judgment for MidTermPM. Describe "
        "the fragility trend over recent sessions (rising / stable / falling) and "
        "whether any deterioration is persistent or an isolated spike, with the "
        "implication for 2-6 week positioning.\n"
        "3. LONG-TERM (6-18 months): one-sentence judgment for LongTermPM. ALWAYS "
        "state that market internals are short-to-mid caution signals only and "
        "that long-horizon context should defer to MacroRegimeAgent.\n\n"
        "TIGHTEN-ONLY RULES (never violate):\n"
        "- NEVER produce a bullish, add-exposure, or loosen-risk recommendation. "
        "Internals can only counsel caution, patience, or tightening — never "
        "green-light risk.\n"
        "- NEVER override or contradict the macro regime; defer regime calls to "
        "MacroRegimeAgent.\n"
        "- NEVER imply that a normal level WITH degraded coverage means the "
        "market is healthy — say the signal is insufficient instead.\n"
        "- NEVER imply internals tighten anything beyond the SHORT horizon.\n"
        "- NEVER invent numbers — cite evidence_ids only.\n\n"
        "Each finding must cite at least one evidence_id from the packet. No "
        "numeric values in finding text. No dollar signs, percentages, or metric "
        "tokens.\n\n"
        # REQUIRED OUTPUT FORMAT — concrete fill-in example so the model nests
        # finding-level fields inside findings[] and emits confidence as an object
        # (not a top-level {text, evidence, confidence:float}). Plain (NON-f)
        # string literals: the braces below are literal, never .format() fields.
        # 4-space indentation, NOT triple-backtick fences (fences confuse the JSON
        # extractor in agent_runner).
        "REQUIRED OUTPUT FORMAT — you must respond with ONLY valid JSON\n"
        "matching this exact structure. No prose, no markdown fences.\n\n"
        "    {\n"
        "      \"agent_name\": \"MarketStructureAgent\",\n"
        "      \"run_id\": \"<use the run_id from the evidence packet header>\",\n"
        "      \"findings\": [\n"
        "        {\n"
        "          \"text\": \"<SHORT-TERM one-sentence judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        },\n"
        "        {\n"
        "          \"text\": \"<MID-TERM one-sentence judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        },\n"
        "        {\n"
        "          \"text\": \"<LONG-TERM one-sentence judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        }\n"
        "      ],\n"
        "      \"confidence\": {\n"
        "        \"level\": \"<high|medium|low>\",\n"
        "        \"rationale\": \"<one sentence explaining confidence level>\",\n"
        "        \"score\": <float between 0.0 and 1.0>\n"
        "      }\n"
        "    }\n\n"
        "Rules:\n"
        "- agent_name must be exactly \"MarketStructureAgent\"\n"
        "- run_id must be copied verbatim from the evidence packet\n"
        "- findings must be a list, never a flat object\n"
        "- each finding must have \"text\" and \"evidence\" keys\n"
        "- confidence must be an object with level/rationale/score, never a float\n"
        "- evidence_id must be an id from the provided evidence packet\n"
        "- no numeric values in any finding text field"
    )


# ---------------------------------------------------------------------------
# Main production function
# ---------------------------------------------------------------------------

def run_market_structure_agent(
    reading: "FragilityReading",
    fragility_series: list,
    clock_suspect: tuple = (False, ""),
    ticker: str = "MARKET",
    *,
    snapshot_dir: str = "data/snapshots",
) -> "AgentOutput":
    """Production MarketStructureAgent — see the module docstring for the pipeline.

    ``reading`` is the ALREADY-COMPUTED ``FragilityReading`` (the Cockpit computes
    it once in Step 4 and injects it here — this function NEVER calls
    ``compute_market_fragility``, avoiding a second compute and a vintage
    divergence). ``fragility_series`` is the reading's ``rolling_raw_series`` as a
    list; ``clock_suspect`` is the ``(suspect: bool, reason: str)`` tuple from the
    Cockpit's WSL clock-drift check.

    Derives three deterministic confidences plus the signal-basis classifier, then
    persists three evidence-backed ToolResults BEFORE the constrained LLM call.

    The entire body is wrapped in an outer fail-closed guard: any unexpected error
    yields a rule-based fallback AgentOutput, never a raised exception.
    """
    # supporting_data is referenced by the outer fallback if we fail early.
    supporting_data: dict = {"fragility_level": _attr(reading, "level", "normal")}
    run_id: Optional[str] = None

    try:
        # 1. Deterministic confidences (computed BEFORE any LLM call).
        short_conf = _compute_short_confidence(reading)
        mid_conf = _compute_mid_confidence(reading)
        long_conf = _compute_long_confidence()

        # 2. Signal-basis classifier + the exposed coverage/clarity/trend terms.
        signal_basis = _compute_signal_basis(reading)
        coverage = round(_coverage(reading), 6)
        clarity = round(_clarity(reading), 6)
        trailing_run = _trailing_elevated_run(reading)
        triggered = list(_attr(reading, "triggered", None) or [])
        n_triggered = len(triggered)

        # 3. Mint one run_id and reuse it everywhere (store + packet + runner).
        from lib.reliability.run_context import create_run_context

        run_context = create_run_context(ticker=ticker, task="market_structure_agent")
        run_id = run_context.run_id

        # 4. Build THREE evidence-backed ToolResults.
        from lib.agent_framework.world_adapter import (
            processed_signals_to_tool_result,
        )

        clock_tuple = clock_suspect or (False, "")
        clock_suspect_bool = bool(clock_tuple[0]) if len(clock_tuple) >= 1 else False
        clock_suspect_reason = str(clock_tuple[1]) if len(clock_tuple) >= 2 else ""

        # TR1 — fragility level + component signals (the qualitative read; numbers
        # live in structured fields the LLM reads only as evidence, never echoes).
        fragility_payload = {
            "fragility_level": _attr(reading, "level", "normal"),
            "fragility_raw_level": _attr(reading, "raw_level", "normal"),
            "fragility_points": int(_attr(reading, "points", 0) or 0),
            "fragility_triggered": triggered,
            "consecutive_raw": int(_attr(reading, "consecutive_raw", 1) or 1),
            "distribution_days_spy": _component(reading, "distribution_days_spy"),
            "distribution_days_qqq": _component(reading, "distribution_days_qqq"),
            "breadth_above_sma20": _component(reading, "breadth_above_sma20"),
            "breadth_slope": _component(reading, "breadth_slope"),
            "good_news_sold": _component(reading, "good_news_sold"),
            "weak_bounce": _component(reading, "weak_bounce"),
            "offense_defense_direction": _component(reading, "offense_defense_direction", ""),
            "offense_defense_magnitude": _component(reading, "offense_defense_magnitude", ""),
            "leading_theme_volume_shrinking": _component(
                reading, "leading_theme_volume_shrinking", False),
        }
        tr_fragility = processed_signals_to_tool_result(
            fragility_payload,
            run_id=run_id,
            tool_name="market_fragility_signals",
            target=ticker,
            metric_group="fragility",
            description="Market-internals fragility level and component signals",
        )

        # TR2 — data coverage + degrade state (so the LLM can honestly express
        # "insufficient signal" rather than false reassurance). Carries the
        # signal_basis classifier.
        health_payload = {
            "fragility_degraded": list(_attr(reading, "degraded", None) or []),
            "earnings_degrade_reason": _attr(reading, "earnings_degrade_reason", ""),
            "hysteresis_source": _attr(reading, "hysteresis_source", ""),
            "vintage_mismatch": bool(_attr(reading, "vintage_mismatch", False)),
            "adjacency_degraded": bool(_attr(reading, "adjacency_degraded", False)),
            "data_vintage": _attr(reading, "data_vintage", ""),
            "clock_suspect": clock_suspect_bool,
            "clock_suspect_reason": clock_suspect_reason,
            "signal_basis": signal_basis,
        }
        tr_health = processed_signals_to_tool_result(
            health_payload,
            run_id=run_id,
            tool_name="market_fragility_health",
            target=ticker,
            metric_group="data_health",
            description="Data coverage and degrade state for market internals",
        )

        # TR3 — deterministic confidence scores (computed before the LLM).
        confidence_payload = {
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
            "n_triggered": n_triggered,
            "coverage": coverage,
            "clarity": clarity,
            "trailing_run": trailing_run,
            "long_rationale": _LONG_RATIONALE,
        }
        tr_confidence = processed_signals_to_tool_result(
            confidence_payload,
            run_id=run_id,
            tool_name="market_structure_confidence",
            target=ticker,
            metric_group="confidence",
            description=(
                "Deterministic confidence scores (computed before LLM). "
                + _LONG_RATIONALE
            ),
        )

        # 5. Dynamic, horizon-aware task instruction.
        task_instruction = _build_task_instruction(reading, signal_basis)

        # 6. supporting_data carried on the AgentOutput.
        supporting_data = {
            "fragility_level": _attr(reading, "level", "normal"),
            "fragility_points": int(_attr(reading, "points", 0) or 0),
            "n_triggered": n_triggered,
            "signal_basis": signal_basis,
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
        }

        # 7. Run the constrained agent (cross-horizon synthesis; EOD validity).
        from lib.agent_framework.agent_runner import run_llm_agent

        return run_llm_agent(
            agent_id="MarketStructureAgent",
            horizon="cross",
            task_instruction=task_instruction,
            tool_results=[tr_fragility, tr_health, tr_confidence],
            supporting_data=supporting_data,
            requires_human_confirmation=True,
            judgment_source="llm_proposed",
            valid_until=end_of_today_iso(),
            ticker=ticker,
            max_tokens=1024,
            run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001 — outer fail-closed guard
        # run_llm_agent is itself fail-closed; this guards everything else
        # (evidence plumbing, validation errors, unexpected faults) so a failure
        # here NEVER aborts the Cockpit refresh.
        _log.warning(
            "run_market_structure_agent failed; returning fallback: %s", exc)
        from lib.agent_framework.agent_runner import _fallback_agent_output

        return _fallback_agent_output(
            "MarketStructureAgent",
            "cross",
            supporting_data,
            exc,
            valid_until=end_of_today_iso(),
            run_id=run_id,
            target=ticker,
            ticker=ticker,
        )


def _component(reading: "FragilityReading", name: str, default=None):
    """Read a component value off ``reading.components`` (or a dict fixture).

    ``FragilityReading.components`` is a ``FragilityComponents`` dataclass; a dict
    fixture may flatten the component fields onto the reading itself. Try the
    nested object first, then fall back to a flat read.
    """
    comp = _attr(reading, "components", None)
    if comp is not None:
        val = _attr(comp, name, None)
        if val is not None:
            return val
    flat = _attr(reading, name, None)
    return flat if flat is not None else default
