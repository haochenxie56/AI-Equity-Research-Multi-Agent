"""
lib/agents/sector_rotation_agent.py

Phase 8B — SectorRotationAgent, production implementation.

The fourth PRODUCTION agent on the Phase 8A framework. It turns the deterministic
theme-momentum + transmission readout (``lib.theme_baskets.compute_all_themes`` ->
``list[ThemeMomentumResult]`` and ``lib.theme_transmission.get_diffusion_context``)
plus the injected GICS offense/defense reading (now carried whole on
``FragilityReading.offense_defense``) into a horizon-aware, evidence-backed
``AgentOutput`` for the PM layer:

  theme momentum     ->  compute_all_themes (deterministic, in Cockpit Step 2)
  offense/defense    ->  FragilityReading.offense_defense (injected, Step 4)
                     ->  get_diffusion_context (pure arithmetic, here)
                     ->  deterministic confidence metrics (short / mid / long)
                     ->  THREE ToolResults into the EvidenceStore (numeric firewall)
                     ->  constrained Claude prompt -> validated AgentResult
                     ->  AgentOutput (JSONL).

Reliability rules honoured here (mirrors MarketStructureAgent):
  * Every NUMBER the LLM may cite is computed in code and persisted as evidence
    BEFORE the LLM runs. The three confidence metrics, the coverage / clarity /
    dispersion decomposition, and the diffusion wave context are all
    deterministic — the LLM never invents them.
  * No new fetches: ``themes`` is the already-computed Step-2 list and
    ``offense_defense`` is the already-computed reading injected from Step 4.
    ``get_diffusion_context`` is pure arithmetic over the momentum scores.
  * Fully fail-closed: ``run_llm_agent`` already returns a rule-based fallback on
    any Claude/parse error; an OUTER guard here guarantees that nothing (evidence
    plumbing, validation errors, unexpected exceptions) ever propagates to the
    Cockpit caller.

IMPORT DISCIPLINE: NO ``lib.reliability`` AND NO ``lib.agent_framework`` import at
module-load time. Every such helper (``create_run_context``, ``run_llm_agent``,
``processed_signals_to_tool_result``, ``_fallback_agent_output``) and
``get_diffusion_context`` is imported lazily inside the function that needs it.
Only stdlib is imported at module level.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # annotations only — never imported at runtime here
    from lib.agent_framework.agent_output import AgentOutput


_log = logging.getLogger("agents.sector_rotation_agent")

# Long-horizon rationale (recorded in the confidence ToolResult description and
# emitted in the TR3 payload). Theme rotation / sector momentum are tactical
# short-to-mid signals; they carry no long-horizon information.
_LONG_RATIONALE = (
    "Theme rotation and sector momentum are tactical short-to-mid "
    "signals; not meaningful beyond ~2 months — long horizon "
    "defers to MacroRegimeAgent."
)

# The Cockpit computes themes with regime="unknown" (Step 2), so the theme
# breadth lens is always the 1M window. Recorded in TR2 for honesty.
_ACTIVE_WINDOW = "1m"


def end_of_today_iso() -> str:
    """Return today's date at 23:59:59 UTC as an ISO datetime string.

    Mirrors ``market_structure_agent.end_of_today_iso``; defined locally so this
    module pulls in no ``lib.agent_framework`` dependency at import time.
    """
    now = datetime.now(timezone.utc)
    return now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Small field readers (tolerate a dataclass OR a dict fixture)
# ---------------------------------------------------------------------------

def _tattr(theme, name: str, default=None):
    """Read ``name`` off a ThemeMomentumResult (getattr) or a dict fixture."""
    if isinstance(theme, dict):
        return theme.get(name, default)
    return getattr(theme, name, default)


def _num(value, default: float = 0.0) -> float:
    """Coerce to float, mapping None / non-numeric to ``default``."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _live(themes: list) -> list:
    """Themes with real (non-fixture) price history. Unknown source -> fixture."""
    return [t for t in (themes or [])
            if _tattr(t, "data_source", "fixture") != "fixture"]


# ---------------------------------------------------------------------------
# Deterministic confidence terms (single source for the confidence funcs + TR3)
# ---------------------------------------------------------------------------

def _theme_coverage(themes: list) -> float:
    """Fraction of themes with live (non-fixture) data. Range 0.0..1.0."""
    if not themes:
        return 0.0
    return len(_live(themes)) / len(themes)


def _n_confirmed(themes: list) -> int:
    """How many LIVE themes carry a breadth-confirmed divergence stage."""
    return sum(1 for t in _live(themes) if bool(_tattr(t, "stage_confirmed", False)))


def _short_clarity(themes: list) -> float:
    """Fraction of LIVE themes whose divergence stage is breadth-confirmed."""
    live = _live(themes)
    if not live:
        return 0.0
    return _n_confirmed(themes) / len(live)


def _dispersion(themes: list) -> float:
    """Momentum-score separation of the leader from the live field (0.0..1.0).

    ``max(momentum_score) - mean(momentum_score)`` over the live themes. A flat
    field (all scores equal) -> 0.0; a clearly-led field -> larger.
    """
    live = _live(themes)
    if not live:
        return 0.0
    scores = [_num(_tattr(t, "momentum_score", 0.0)) for t in live]
    return max(scores) - (sum(scores) / len(scores))


def _wave_clear(diffusion: dict) -> float:
    """1.0 when the diffusion context identified a leading wave, else 0.0."""
    return 1.0 if (diffusion or {}).get("active_order") is not None else 0.0


def _compute_short_confidence(themes: list, diffusion: dict) -> float:
    """Live-signal confidence = theme_coverage x short_clarity.

    Confidence in the short-term rotation read is how much of the leading,
    breadth-CONFIRMED rotation the live themes actually show, discounted by how
    much of the data was live. Both terms are deterministic, computed before any
    LLM call.

    Edge cases (all -> 0.0):
      * no themes at all, or every theme is fixture -> coverage path -> 0.0.
      * no live theme has a confirmed stage -> clarity == 0 -> 0.0.

    Range: 0.0..1.0 (rounded to 6 dp).
    """
    if not themes or not _live(themes):
        return 0.0
    return round(_theme_coverage(themes) * _short_clarity(themes), 6)


def _compute_mid_confidence(themes: list, diffusion: dict) -> float:
    """Wave-leadership confidence = theme_coverage x dispersion x wave_clear.

    The 2-6 week rotation read is trustworthy when there is a clearly-led wave
    (``active_order`` set) AND the leader is separated from the field
    (``dispersion`` > 0), discounted by live coverage. Deterministic.

    Edge cases (all -> 0.0):
      * every theme is fixture -> 0.0.
      * no leading wave identified -> wave_clear == 0 -> 0.0.
      * flat momentum field -> dispersion == 0 -> 0.0.

    Range: 0.0..1.0 (rounded to 6 dp).
    """
    if not _live(themes):
        return 0.0
    return round(
        _theme_coverage(themes) * _dispersion(themes) * _wave_clear(diffusion), 6)


def _compute_long_confidence() -> float:
    """Always 0.0 — see ``_LONG_RATIONALE``.

    Theme rotation / sector momentum are tactical short-to-mid signals; they carry
    no long-horizon information, so the long confidence is structurally zero
    (mirrors ``MarketStructureAgent._compute_long_confidence``).
    """
    return 0.0


def _compute_signal_basis(themes: list, diffusion: dict) -> str:
    """Three-way classifier distinguishing the meaning of a low/zero short read.

      * ``"signal_present"``       — a confirmed rotation stage fired AND a leading
                                     wave was identified.
      * ``"degraded_insufficient"`` — too little live data to assess (no live
                                     themes, or fewer than half the themes are
                                     live) — must NOT be read as "no rotation".
      * ``"no_clear_leadership"``  — data IS present but neither a confirmed stage
                                     nor a clear wave emerged (a genuine neutral /
                                     wait state, NOT directional).
    """
    live = _live(themes)
    n_confirmed = _n_confirmed(themes)
    if n_confirmed > 0 and (diffusion or {}).get("active_order") is not None:
        return "signal_present"
    if not live or len(live) < len(themes) // 2:
        return "degraded_insufficient"
    return "no_clear_leadership"


# ---------------------------------------------------------------------------
# task_instruction builder
# ---------------------------------------------------------------------------

def _qual_context(themes: list, diffusion: dict, offense_defense: dict,
                  signal_basis: str) -> str:
    """Build the QUALITATIVE (number-free) context block for the prompt.

    Only level words, theme/cluster NAMES, stage labels, the offense/defense
    direction/magnitude words, and the signal_basis are interpolated — never a
    numeric value — so the model is never handed a number to echo.
    """
    live = _live(themes)
    leading = [str(_tattr(t, "label_en", _tattr(t, "theme_key", "")))
               for t in live
               if _tattr(t, "stage", "") in ("leading", "rotating_in")
               and bool(_tattr(t, "stage_confirmed", False))]
    fading = [str(_tattr(t, "label_en", _tattr(t, "theme_key", "")))
              for t in live
              if _tattr(t, "stage", "") in ("rotating_out", "out_of_favor")]
    clusters = [str(c) for c in (diffusion or {}).get("active_clusters", []) or []]
    next_themes = [str(x) for x in (diffusion or {}).get("next_order_themes", []) or []]
    lagging = [str(x) for x in (diffusion or {}).get("lagging_themes", []) or []]
    od_dir = str((offense_defense or {}).get("direction", "") or "balanced")
    od_mag = str((offense_defense or {}).get("magnitude", "") or "mild")

    return (
        f"Confirmed leading/rotating-in themes: {', '.join(leading) or 'none'}. "
        f"Rotating-out / out-of-favor themes: {', '.join(fading) or 'none'}. "
        f"Active-wave clusters: {', '.join(clusters) or 'none'}. "
        f"Potential next-wave themes: {', '.join(next_themes) or 'none'}. "
        f"Lagging themes within the active wave: {', '.join(lagging) or 'none'}. "
        f"Offense/defense character: {od_dir} ({od_mag}). "
        f"Signal basis: {signal_basis}."
    )


def _build_task_instruction(themes: list, diffusion: dict,
                            offense_defense: dict, signal_basis: str) -> str:
    """Build the dynamic, horizon-aware SectorRotationAgent task instruction.

    All interpolated context is QUALITATIVE (theme/cluster names, stage words,
    direction/magnitude words, signal_basis) — never numeric. The REQUIRED OUTPUT
    FORMAT block uses 4-space indentation (NOT triple-backtick fences, which
    confuse the JSON extractor in agent_runner).
    """
    return (
        "You are SectorRotationAgent. Synthesize deterministic theme-momentum "
        "rotation signals and the GICS sector offense/defense reading into "
        "actionable ROTATION context for the PM agents. Theme rotation describes "
        "where capital is flowing across the AI industry chain and whether the "
        "broad market favors offense or defense.\n\n"
        f"{_qual_context(themes, diffusion, offense_defense, signal_basis)}\n\n"
        "Based on the evidence packet, provide THREE findings:\n"
        "1. SHORT-TERM (1-3 weeks): one-sentence actionable judgment for "
        "ShortTermPM. Name which themes are actively rotating IN with breadth "
        "confirmation and which are rotating OUT or out of favor; state the "
        "current offense/defense character and whether the windows confirm it; "
        "give the specific sector/theme implication for near-term positioning. "
        "If signal basis is \"no_clear_leadership\", you MUST state that no clear "
        "rotation leadership is present and treat it as a neutral / wait state — "
        "do NOT fabricate a rotation direction and do NOT present it as bullish "
        "or bearish. If signal basis is \"degraded_insufficient\", you MUST state "
        "explicitly that data coverage is insufficient to assess rotation.\n"
        "2. MID-TERM (2-6 weeks): one-sentence judgment for MidTermPM. State which "
        "wave is currently leading and which themes form the potential next wave, "
        "whether momentum is concentrated in a clear leader or spread across a "
        "flat field, the implication for 2-6 week rotation positioning, and which "
        "themes lag within the active wave.\n"
        "3. LONG-TERM (6-18 months): one-sentence judgment for LongTermPM. ALWAYS "
        "state that theme rotation and sector momentum are tactical short-to-mid "
        "signals only and that long-horizon sector-cycle context should defer to "
        "MacroRegimeAgent.\n\n"
        "RULES (never violate):\n"
        "- NEVER present \"no_clear_leadership\" as a bullish or bearish call; it "
        "is a neutral / wait state.\n"
        "- NEVER invent a rotation stage, wave, or direction not supported by the "
        "evidence packet.\n"
        "- NEVER override or contradict the macro regime; defer regime calls to "
        "MacroRegimeAgent.\n"
        "- NEVER invent numbers — cite evidence_ids only.\n\n"
        "Each finding must cite at least one evidence_id from the packet. No "
        "numeric values in finding text. No dollar signs, percentages, or metric "
        "tokens.\n\n"
        # REQUIRED OUTPUT FORMAT — 4-space indentation, NOT triple-backtick
        # fences (fences confuse the JSON extractor in agent_runner). Plain
        # (NON-f) string literals: the braces below are literal.
        "REQUIRED OUTPUT FORMAT — you must respond with ONLY valid JSON\n"
        "matching this exact structure. No prose, no markdown fences.\n\n"
        "    {\n"
        "      \"agent_name\": \"SectorRotationAgent\",\n"
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
        "- agent_name must be exactly \"SectorRotationAgent\"\n"
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

def run_sector_rotation_agent(
    themes: list,
    offense_defense: dict,
    ticker: str = "MARKET",
    *,
    snapshot_dir: str = "data/snapshots",
) -> "AgentOutput":
    """Production SectorRotationAgent — see the module docstring for the pipeline.

    ``themes`` is the ALREADY-COMPUTED ``list[ThemeMomentumResult]`` (the Cockpit
    computes it once in Step 2 and injects it here). ``offense_defense`` is the
    ALREADY-COMPUTED GICS offense/defense reading dict injected from
    ``FragilityReading.offense_defense`` (Step 4). This function performs NO new
    fetch — ``get_diffusion_context`` is pure arithmetic over the momentum scores.

    Derives three deterministic confidences plus the signal-basis classifier, then
    persists three evidence-backed ToolResults BEFORE the constrained LLM call.

    The entire body is wrapped in an outer fail-closed guard: any unexpected error
    yields a rule-based fallback AgentOutput, never a raised exception.
    """
    offense_defense = offense_defense or {}
    # supporting_data is referenced by the outer fallback if we fail early.
    supporting_data: dict = {
        "offense_defense_direction": offense_defense.get("direction", ""),
    }
    run_id: Optional[str] = None

    try:
        # 1. Diffusion context (pure arithmetic; NO network, NO LLM).
        from lib.theme_transmission import get_diffusion_context

        diffusion = get_diffusion_context(
            {_tattr(t, "theme_key", ""): _num(_tattr(t, "momentum_score", 0.0))
             for t in (themes or [])}
        ) or {}

        # 2. Deterministic confidences (computed BEFORE any LLM call).
        short_conf = _compute_short_confidence(themes, diffusion)
        mid_conf = _compute_mid_confidence(themes, diffusion)
        long_conf = _compute_long_confidence()

        # 3. Signal-basis classifier + the exposed coverage/clarity/dispersion terms.
        signal_basis = _compute_signal_basis(themes, diffusion)
        theme_coverage = round(_theme_coverage(themes), 6)
        short_clarity = round(_short_clarity(themes), 6)
        dispersion = round(_dispersion(themes), 6)
        wave_clear = _wave_clear(diffusion)
        mid_clarity = round(dispersion * wave_clear, 6)
        n_confirmed = _n_confirmed(themes)
        live = _live(themes)

        # 4. Mint one run_id and reuse it everywhere (store + packet + runner).
        from lib.reliability.run_context import create_run_context

        run_context = create_run_context(ticker=ticker, task="sector_rotation_agent")
        run_id = run_context.run_id

        # 5. Build THREE evidence-backed ToolResults.
        from lib.agent_framework.world_adapter import (
            processed_signals_to_tool_result,
        )

        # Top themes by momentum_score (fixtures sort last at 0.0). Numbers live in
        # structured fields the LLM reads only as evidence, never echoes.
        sorted_themes = sorted(
            (themes or []),
            key=lambda t: _num(_tattr(t, "momentum_score", 0.0)), reverse=True)
        top_themes = [{
            "theme_key": _tattr(t, "theme_key", ""),
            "label_en": _tattr(t, "label_en", ""),
            "stage": _tattr(t, "stage", ""),
            "stage_confirmed": bool(_tattr(t, "stage_confirmed", False)),
            "momentum_score": _num(_tattr(t, "momentum_score", 0.0)),
            "excess_3m": _tattr(t, "excess_3m", None),
            "breadth_beat_pct": _tattr(t, "breadth_beat_pct", None),
        } for t in sorted_themes[:5]]

        # TR1 — theme momentum + rotation wave + offense/defense signals (the
        # qualitative read; numbers live in structured fields as evidence only).
        signals_payload = {
            "top_themes": top_themes,
            "active_order": diffusion.get("active_order"),
            "active_clusters": list(diffusion.get("active_clusters", []) or []),
            "next_order": diffusion.get("next_order"),
            "next_order_themes": list(diffusion.get("next_order_themes", []) or []),
            "lagging_themes": list(diffusion.get("lagging_themes", []) or []),
            "offense_defense_direction": offense_defense.get("direction", ""),
            "offense_defense_magnitude": offense_defense.get("magnitude", ""),
            "od_avg_diff": offense_defense.get("avg_diff", 0.0),
            "od_confirming_windows": list(
                offense_defense.get("confirming_windows", []) or []),
            "od_n_windows": offense_defense.get("n_windows", 0),
        }
        tr_signals = processed_signals_to_tool_result(
            signals_payload,
            run_id=run_id,
            tool_name="sector_rotation_signals",
            target=ticker,
            metric_group="rotation",
            description="Theme momentum and rotation wave signals",
        )

        # TR2 — data coverage + signal basis (so the LLM can honestly express
        # "insufficient" / "no clear leadership" rather than false reassurance).
        health_payload = {
            "n_themes": len(themes or []),
            "n_live": len(live),
            "n_fixture": len(themes or []) - len(live),
            "fixture_theme_keys": [
                _tattr(t, "theme_key", "") for t in (themes or [])
                if _tattr(t, "data_source", "fixture") == "fixture"],
            "theme_coverage": theme_coverage,
            "active_window": _ACTIVE_WINDOW,
            "signal_basis": signal_basis,
            "od_available": bool(offense_defense),
        }
        tr_health = processed_signals_to_tool_result(
            health_payload,
            run_id=run_id,
            tool_name="sector_rotation_health",
            target=ticker,
            metric_group="data_health",
            description="Data coverage and signal basis for sector rotation",
        )

        # TR3 — deterministic confidence scores (computed before the LLM).
        confidence_payload = {
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
            "theme_coverage": theme_coverage,
            "short_clarity": short_clarity,
            "mid_clarity": mid_clarity,
            "dispersion": dispersion,
            "wave_clear": wave_clear,
            "long_rationale": _LONG_RATIONALE,
        }
        tr_confidence = processed_signals_to_tool_result(
            confidence_payload,
            run_id=run_id,
            tool_name="sector_rotation_confidence",
            target=ticker,
            metric_group="confidence",
            description=(
                "Deterministic confidence scores (computed before LLM). "
                + _LONG_RATIONALE
            ),
        )

        # 6. Dynamic, horizon-aware task instruction.
        task_instruction = _build_task_instruction(
            themes, diffusion, offense_defense, signal_basis)

        # 7. supporting_data carried on the AgentOutput.
        supporting_data = {
            "active_order": diffusion.get("active_order"),
            "next_order": diffusion.get("next_order"),
            "n_confirmed_themes": n_confirmed,
            "signal_basis": signal_basis,
            "offense_defense_direction": offense_defense.get("direction", ""),
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
        }

        # 8. Run the constrained agent (cross-horizon synthesis; EOD validity).
        from lib.agent_framework.agent_runner import run_llm_agent

        return run_llm_agent(
            agent_id="SectorRotationAgent",
            horizon="cross",
            task_instruction=task_instruction,
            tool_results=[tr_signals, tr_health, tr_confidence],
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
        # (diffusion compute, evidence plumbing, validation errors, unexpected
        # faults) so a failure here NEVER aborts the Cockpit refresh.
        _log.warning(
            "run_sector_rotation_agent failed; returning fallback: %s", exc)
        from lib.agent_framework.agent_runner import _fallback_agent_output

        return _fallback_agent_output(
            "SectorRotationAgent",
            "cross",
            supporting_data,
            exc,
            valid_until=end_of_today_iso(),
            run_id=run_id,
            target=ticker,
            ticker=ticker,
        )
