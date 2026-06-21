"""
lib/agents/macro_regime_agent.py

Phase 8B — MacroRegimeAgent, production implementation.

This is the first PRODUCTION agent on the Phase 8A framework. It turns the
deterministic macro regime classification (``lib.macro_regime.classify_regime``)
into a horizon-aware, evidence-backed ``AgentOutput`` for the PM layer:

  raw macro data  ->  classify_regime (deterministic vote tally)
                  ->  deterministic confidence metrics (short / mid / long)
                  ->  two ToolResults into the EvidenceStore (numeric firewall)
                  ->  constrained Claude prompt -> validated AgentResult
                  ->  AgentOutput (JSONL).

Reliability rules honoured here:
  * Every NUMBER the LLM may cite is computed in code and persisted as evidence
    BEFORE the LLM runs. The three confidence metrics, the vote tally, and the
    regime-stability count are all deterministic — the LLM never invents them.
  * Fully fail-closed: ``run_llm_agent`` already returns a rule-based fallback on
    any Claude/parse error; an OUTER guard here guarantees that nothing
    (validation errors, unexpected exceptions) ever propagates to the Cockpit
    caller.

IMPORT DISCIPLINE: no ``lib.reliability`` import at module-load time. Every
reliability helper (``create_run_context``, the runner fallback, ``audit_query``,
``macro_data``, ``macro_regime``) is imported lazily inside the function that
needs it. Only the lightweight ``lib.agent_framework`` siblings are imported at
module level (they themselves keep ``lib.reliability`` lazy).
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from lib.agent_framework.agent_runner import run_llm_agent
from lib.agent_framework.world_adapter import processed_signals_to_tool_result

if TYPE_CHECKING:  # annotations only
    from lib.agent_framework.agent_output import AgentOutput
    from lib.macro_data import MacroDataResult
    from lib.macro_regime import MacroRegimeResult


_log = logging.getLogger("agents.macro_regime_agent")

# Regime tokens that signal "no usable macro read". Mid-term stability and
# short-term agreement both collapse to zero confidence on these — there is no
# regime to be stable in, and no decisive vote was cast.
_DEGRADE_REGIMES = frozenset({"degraded", "unknown"})

# Saturating curve mapping consecutive same-regime snapshot days -> a 0..1
# mid-term stability score. Linear interpolation between breakpoints; clamped to
# the endpoints outside the range. 0 days (today's read but no confirming
# history) is a low-but-nonzero 0.1; 14+ consecutive days is full confidence.
_MID_CONFIDENCE_BREAKPOINTS = [
    (0, 0.1),
    (1, 0.2),
    (3, 0.4),
    (5, 0.6),
    (7, 0.75),
    (10, 0.9),
    (14, 1.0),
]


# ---------------------------------------------------------------------------
# Small dataclass/dict helpers
# ---------------------------------------------------------------------------

def _normalize_to_dict(value):
    """Normalize a dataclass instance to a dict; pass dicts/others through.

    Mirrors ``world_adapter._normalize_to_dict`` so a ``MacroRegimeResult`` (from
    ``classify_regime``) and a plain regime dict are handled identically.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return value


def _field(obj, name: str, default=None):
    """Read ``name`` from a dict (``.get``) or any object (``getattr``)."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def end_of_today_iso() -> str:
    """Return today's date at 23:59:59 UTC as an ISO datetime string."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Deterministic confidence calculations (no LLM)
# ---------------------------------------------------------------------------

def _compute_short_confidence(regime: "MacroRegimeResult | dict") -> float:
    """Vote-agreement ratio from the ``MacroRegimeResult.votes_*`` fields.

    The short horizon trusts the CURRENT signal tally: how decisively the live
    macro indicators agree on a direction. The score is the net agreement margin
    as a fraction of all decisive votes::

        abs(votes_risk_on - votes_risk_off) / votes_total

    A unanimous tally -> 1.0; a perfectly split tally (e.g. 3 vs 3) -> 0.0.

    Accepts either a ``MacroRegimeResult`` dataclass or a normalized dict.

    Edge cases (both return 0.0):
      * ``votes_total == 0`` — the degraded path casts no votes (also covers a
        legacy regime dict that predates the Phase 8B vote fields).
      * ``regime == "degraded"`` — no responsible directional read exists.

    Range: 0.0 .. 1.0.
    """
    if _field(regime, "regime", "") == "degraded":
        return 0.0
    votes_total = int(_field(regime, "votes_total", 0) or 0)
    if votes_total == 0:
        return 0.0
    von = int(_field(regime, "votes_risk_on", 0) or 0)
    voff = int(_field(regime, "votes_risk_off", 0) or 0)
    return abs(von - voff) / votes_total


def _interpolate_mid_confidence(consecutive_days: int) -> float:
    """Map a consecutive-same-regime day count to a 0..1 score via the
    ``_MID_CONFIDENCE_BREAKPOINTS`` saturating curve (linear interpolation,
    clamped at the endpoints)."""
    bps = _MID_CONFIDENCE_BREAKPOINTS
    if consecutive_days <= bps[0][0]:
        return bps[0][1]
    if consecutive_days >= bps[-1][0]:
        return bps[-1][1]
    for (d0, v0), (d1, v1) in zip(bps, bps[1:]):
        if d0 <= consecutive_days <= d1:
            if d1 == d0:
                return v1
            frac = (consecutive_days - d0) / (d1 - d0)
            return v0 + frac * (v1 - v0)
    return bps[-1][1]  # unreachable; defensive


def _count_consecutive_same_regime(metas: list, current_regime: str) -> int:
    """Count the trailing run of snapshot days whose ``macro_regime`` matches
    ``current_regime``.

    ``metas`` is the ascending-by-date ``MetaRecord`` list from
    ``audit_query.load_all_meta``; we walk it from the most-recent end. The run
    breaks on the first mismatch OR on any ``"unknown"`` / ``"degraded"`` history
    record (those are treated as a regime discontinuity, not a continuation).
    """
    count = 0
    for m in reversed(metas):
        rv = (_field(m, "macro_regime", "") or "")
        if rv in _DEGRADE_REGIMES:
            break
        if rv != current_regime:
            break
        count += 1
    return count


def _safe_load_all_meta(snapshot_dir: str) -> list:
    """Load the full ``MetaRecord`` history; fail-closed to ``[]`` on any error
    (a missing snapshot dir, an import failure, or a malformed file)."""
    try:
        from lib.audit_query import load_all_meta

        return load_all_meta(snapshot_dir) or []
    except Exception as exc:  # noqa: BLE001 — never raise from a snapshot read
        _log.warning("_safe_load_all_meta: load_all_meta failed: %s", exc)
        return []


def _compute_mid_confidence(
    current_regime: str,
    snapshot_dir: str = "data/snapshots",
) -> float:
    """Regime-stability score from consecutive same-regime days in snapshot
    history.

    Algorithm:
      1. Load all ``MetaRecord`` via ``audit_query.load_all_meta(snapshot_dir)``.
      2. Walk from the most-recent end (see ``_count_consecutive_same_regime``).
      3. Count days where ``macro_regime == current_regime``; stop on the first
         mismatch OR on an ``"unknown"`` / ``"degraded"`` history record.
      4. Map the count to 0..1 via ``_MID_CONFIDENCE_BREAKPOINTS`` (interp).
      5. Fail-closed: if the load raises OR returns empty -> 0.1 (we still have
         today's read, just no confirming history).
      6. If ``current_regime`` is ``"degraded"`` / ``"unknown"`` -> 0.0.

    Range: 0.0 .. 1.0.
    """
    if current_regime in _DEGRADE_REGIMES or not current_regime:
        return 0.0
    metas = _safe_load_all_meta(snapshot_dir)
    if not metas:
        return 0.1
    days = _count_consecutive_same_regime(metas, current_regime)
    return _interpolate_mid_confidence(days)


def _compute_long_confidence(data_coverage: float, short_confidence: float) -> float:
    """``long_confidence = data_coverage * short_confidence``.

    The long horizon's trust in the macro read is the data foundation
    (``data_coverage``, fraction of metric groups live) discounted by how clearly
    the available data points in one direction (``short_confidence``). A regime
    inferred from half the data, or from a split tally, is a weak long-term anchor.

    Range: 0.0 .. 1.0.
    """
    return float(data_coverage) * float(short_confidence)


# ---------------------------------------------------------------------------
# task_instruction builder
# ---------------------------------------------------------------------------

def _coverage_band(data_coverage: float) -> str:
    """Map a 0..1 coverage fraction to a human band for the prompt."""
    if data_coverage >= 0.8:
        return "high coverage"
    if data_coverage >= 0.5:
        return "moderate coverage"
    return "low coverage (degraded)"


def _build_task_instruction(regime_dict: dict) -> str:
    """Build the dynamic, horizon-aware MacroRegimeAgent task instruction."""
    regime = regime_dict.get("regime", "unknown")
    coverage = float(regime_dict.get("data_coverage", 0.0) or 0.0)
    bias = regime_dict.get("horizon_bias", {}) or {}
    short_bias = bias.get("short", "neutral")
    mid_bias = bias.get("mid", "neutral")
    long_bias = bias.get("long", "neutral")
    return (
        f"You are MacroRegimeAgent. Current macro regime: {regime}. "
        f"Data coverage: {_coverage_band(coverage)}. "
        f"Horizon bias from signals: short={short_bias}, "
        f"mid={mid_bias}, long={long_bias}.\n\n"
        "Based on the evidence packet, provide THREE findings:\n"
        "1. SHORT-TERM (1-4 weeks): one-sentence actionable judgment for "
        "ShortTermPM. What does this regime mean for near-term positioning? "
        "Specify sector implications and entry conditions.\n"
        "2. MID-TERM (1-3 months): one-sentence judgment for MidTermPM. Which "
        "sectors or themes benefit or suffer from this regime over the coming "
        "months?\n"
        "3. LONG-TERM (6-18 months): one-sentence judgment for LongTermPM. How "
        "does this regime affect long-term thesis validity?\n\n"
        "Each finding must cite at least one evidence_id from the packet. No "
        "numeric values in finding text. No vague statements. Specific sector "
        "names, time windows, and conditions required."
    )


# ---------------------------------------------------------------------------
# Main production function
# ---------------------------------------------------------------------------

def run_macro_regime_agent(
    regime_signals: "MacroRegimeResult | dict | None" = None,
    *,
    horizon: str = "cross",
    ticker: str | None = None,
    snapshot_dir: str = "data/snapshots",
    macro_data: "MacroDataResult | None" = None,
) -> "AgentOutput":
    """Production MacroRegimeAgent — see the module docstring for the pipeline.

    If ``regime_signals`` is provided (``MacroRegimeResult`` or dict) it is used
    directly (the Cockpit already computed it in Step 1; tests inject it). If it
    is ``None``, the agent fetches and classifies internally:
    ``classify_regime(macro_data or fetch_all_macro())``.

    The three confidence metrics, the vote tally, and the regime-stability count
    are computed deterministically and persisted as evidence BEFORE the LLM runs.
    The entire pipeline is wrapped in an outer fail-closed guard: a Claude
    failure (or any unexpected error) yields a rule-based fallback AgentOutput,
    never a raised exception.
    """
    # supporting_data is referenced by the outer fallback if we fail early.
    supporting_data: dict = {}
    run_id: str | None = None

    try:
        # 1. Obtain / normalize the regime into a dict (+ keep the source for
        #    direct field reads). When None, fetch + classify internally.
        if regime_signals is None:
            from lib.macro_data import fetch_all_macro
            from lib.macro_regime import classify_regime

            data = macro_data if macro_data is not None else fetch_all_macro()
            regime_obj = classify_regime(data)
            regime_dict = dict(_normalize_to_dict(regime_obj))
        else:
            # _normalize_to_dict handles a dataclass (asdict) or a passthrough
            # dict; copy so we never mutate a caller's dict.
            regime_dict = dict(_normalize_to_dict(regime_signals))

        regime_str = regime_dict.get("regime") or "unknown"

        # 2. Deterministic confidences (computed before any LLM call).
        short_conf = _compute_short_confidence(regime_dict)

        # 3. consecutive_same_regime_days for evidence — load the snapshot meta
        #    history ONCE and derive both the stability count and mid_conf from
        #    it (avoids a second load_all_meta call).
        metas = _safe_load_all_meta(snapshot_dir)
        if regime_str in _DEGRADE_REGIMES:
            consecutive_days = 0
            mid_conf = 0.0
        else:
            consecutive_days = _count_consecutive_same_regime(metas, regime_str)
            mid_conf = 0.1 if not metas else _interpolate_mid_confidence(consecutive_days)

        data_coverage = float(regime_dict.get("data_coverage", 0.0) or 0.0)
        long_conf = _compute_long_confidence(data_coverage, short_conf)

        # Round for clean evidence/serialization (does not affect ordering).
        short_conf = round(short_conf, 6)
        mid_conf = round(mid_conf, 6)
        long_conf = round(long_conf, 6)

        # 4. Mint one run_id and reuse it everywhere (store + packet + runner).
        from lib.reliability.run_context import create_run_context

        ctx = create_run_context(ticker=ticker or "MACRO", task="macro_regime_agent")
        run_id = ctx.run_id

        # 5. Build TWO evidence-backed ToolResults.
        tr_regime = processed_signals_to_tool_result(
            regime_dict,
            run_id=run_id,
            tool_name="classify_regime",
            target="MACRO",
            metric_group="regime_classification",
            description="MacroRegimeResult from classify_regime()",
        )
        confidence_payload = {
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
            "consecutive_same_regime_days": consecutive_days,
            "votes_risk_on": regime_dict.get("votes_risk_on", 0),
            "votes_risk_off": regime_dict.get("votes_risk_off", 0),
            "votes_total": regime_dict.get("votes_total", 0),
        }
        tr_confidence = processed_signals_to_tool_result(
            confidence_payload,
            run_id=run_id,
            tool_name="macro_regime_confidence",
            target="MACRO",
            metric_group="regime_confidence",
            description="Computed confidence metrics for MacroRegimeAgent",
        )

        # 6. Dynamic, horizon-aware task instruction.
        task_instruction = _build_task_instruction(regime_dict)

        # 7. supporting_data carried on the AgentOutput.
        supporting_data = {
            "regime": regime_dict.get("regime"),
            "confidence_label": regime_dict.get("confidence"),
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
            "consecutive_same_regime_days": consecutive_days,
            "data_coverage": data_coverage,
            "horizon_bias": regime_dict.get("horizon_bias", {}),
            "votes_risk_on": regime_dict.get("votes_risk_on", 0),
            "votes_risk_off": regime_dict.get("votes_risk_off", 0),
            "votes_total": regime_dict.get("votes_total", 0),
        }

        # 8. Run the constrained agent (cross-horizon synthesis; EOD validity).
        return run_llm_agent(
            agent_id="MacroRegimeAgent",
            horizon="cross",
            task_instruction=task_instruction,
            tool_results=[tr_regime, tr_confidence],
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
        # (validation errors, snapshot/evidence plumbing, unexpected faults) so a
        # failure here NEVER aborts the Cockpit refresh.
        _log.warning("run_macro_regime_agent failed; returning fallback: %s", exc)
        from lib.agent_framework.agent_runner import _fallback_agent_output

        return _fallback_agent_output(
            "MacroRegimeAgent",
            "cross",
            supporting_data,
            exc,
            valid_until=end_of_today_iso(),
            run_id=run_id,
            target="MACRO",
            ticker=ticker,
        )
