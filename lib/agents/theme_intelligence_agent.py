"""
lib/agents/theme_intelligence_agent.py

Phase 8B — ThemeIntelligenceAgent, production implementation.

The fifth PRODUCTION agent on the Phase 8A framework. It is DISTINCT from
SectorRotationAgent: where SRA answers "which wave / sector character leads
right now" (within-wave rotation + GICS offense/defense), TIA answers two
different questions on the SAME deterministic theme readout:

  1. ROLE — within each top-momentum theme, which constituents are the live
     LEADERS vs LAGGARDS vs 2nd-derivative beneficiaries, by crossing the
     live ``constituent_rs`` active-window excess ranking against the seed
     transmission ROLE map. Live ranking that DIVERGES from a constituent's
     seed role (e.g. a seed-leader showing laggard RS) is a deterioration
     signal.
  2. ASYMMETRY — which themes are structurally EARLY in the transmission
     chain (low ``wave_order`` AND an early ``stage``) and therefore represent
     un-crowded, asymmetric upside. This is a CROSS-WAVE angle — explicitly
     NOT the same as SRA's "lagging WITHIN the active wave".

Pipeline (mirrors SectorRotationAgent exactly):

  theme momentum + constituent_rs ->  compute_all_themes (deterministic, Step 2)
  transmission roles / order      ->  lib.theme_transmission (pure lookups)
                                  ->  get_diffusion_context (pure arithmetic)
                                  ->  deterministic confidence metrics
                                  ->  THREE ToolResults into the EvidenceStore
                                  ->  constrained Claude prompt -> AgentResult
                                  ->  AgentOutput (JSONL).

Reliability rules honoured here (mirrors SectorRotationAgent):
  * Every NUMBER the LLM may cite is computed in code and persisted as evidence
    BEFORE the LLM runs (the three confidences, their coverage / role-resolution
    / asymmetry-strength decomposition, the per-ticker rankings, the asymmetric
    / late-stage theme sets). The LLM never invents them.
  * No new fetches: ``themes`` is the already-computed Step-2 list; every
    theme_transmission lookup and ``get_diffusion_context`` is pure arithmetic
    over data already in hand.
  * Fully fail-closed: ``run_llm_agent`` already returns a rule-based fallback
    on any Claude/parse error; an OUTER guard here guarantees nothing (evidence
    plumbing, validation, unexpected faults) ever propagates to the Cockpit.

IMPORT DISCIPLINE: NO ``lib.reliability``, NO ``lib.agent_framework`` and NO
``lib.theme_transmission`` import at module-load time. Every such helper is
imported lazily inside the function that needs it. Only stdlib at module level.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # annotations only — never imported at runtime here
    from lib.agent_framework.agent_output import AgentOutput


_log = logging.getLogger("agents.theme_intelligence_agent")


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Only "rotating_in" counts as early-stage for asymmetry detection.
# "" (empty string) = data missing, NOT early. "leading" = already crowded.
_EARLY_STAGES = frozenset({"rotating_in"})

# Wave orders 1-2 are structurally early in the transmission chain.
_EARLY_WAVE_ORDERS = frozenset({1, 2})

# Stages that indicate an already-crowded / past-peak theme (TR2 contrast set).
_LATE_STAGES = frozenset({"leading", "rotating_out", "out_of_favor"})

_LONG_RATIONALE = (
    "Theme transmission roles and asymmetric opportunity are tactical "
    "short-to-mid signals; long-horizon role assessment requires "
    "individual stock deep research — defers to StockResearchAgent."
)

# Number of top themes (by momentum_score) to include in TR1 role detail.
_TOP_N_THEMES = 5


def end_of_today_iso() -> str:
    """Return today's date at 23:59:59 UTC as an ISO datetime string.

    Defined locally (mirrors ``sector_rotation_agent.end_of_today_iso``) so this
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
    """Themes with real (non-fixture) data. Unknown source -> fixture."""
    return [t for t in (themes or [])
            if _tattr(t, "data_source", "fixture") != "fixture"]


# ---------------------------------------------------------------------------
# Helper: intra-theme ticker ranking
# ---------------------------------------------------------------------------

def _rank_theme_constituents(result, n_top: int = 5) -> list:
    """Rank a theme's constituents by live ``constituent_rs`` active excess.

    For a single ThemeMomentumResult, rank constituents by their
    ``constituent_rs[ticker]["active"]`` excess (descending) and cross each with
    ``get_ticker_role`` to label it. Returns the top ``n_top`` as a list of
    ``{ticker, role, active_excess, rank}`` dicts.

    Tickers with a missing / None active excess are filtered out. If
    ``constituent_rs`` is empty or missing -> returns ``[]`` (fixture-fallback
    themes never carry constituent_rs, so they always rank to []).

    All imports are lazy; this function NEVER raises.
    """
    try:
        from lib.theme_transmission import get_ticker_role

        rs = _tattr(result, "constituent_rs", {}) or {}
        if not rs:
            return []
        theme_key = _tattr(result, "theme_key", "")

        rows: list = []
        for ticker, windows in rs.items():
            active = (windows or {}).get("active")
            if active is None:
                continue
            rows.append({
                "ticker": ticker,
                "role": get_ticker_role(theme_key, ticker),
                "active_excess": active,
            })
        rows.sort(key=lambda r: r["active_excess"], reverse=True)

        ranked: list = []
        for i, row in enumerate(rows[:n_top], start=1):
            ranked.append({**row, "rank": i})
        return ranked
    except Exception:  # noqa: BLE001 — never raise from a ranking helper
        return []


# ---------------------------------------------------------------------------
# Deterministic confidence terms (single source for the confidence funcs + TR3)
# ---------------------------------------------------------------------------

def _theme_coverage(themes: list) -> float:
    """Fraction of themes with live (non-fixture) data. Range 0.0..1.0."""
    if not themes:
        return 0.0
    return len(_live(themes)) / len(themes)


def _role_resolution(themes: list) -> float:
    """Fraction of ALL live-theme constituents that carry a NAMED live role.

    Numerator: constituents that have a valid ``constituent_rs[...]["active"]``
    excess AND a seed role != "unknown". Denominator: ALL constituents across
    every LIVE theme (honest coverage — NOT just those with RS data). Range
    0.0..1.0.
    """
    from lib.theme_transmission import get_ticker_role

    live = _live(themes)
    total_constituents = sum(len(_tattr(t, "constituents", []) or []) for t in live)
    if total_constituents == 0:
        return 0.0

    named_roles = 0
    for t in live:
        rs = _tattr(t, "constituent_rs", {}) or {}
        theme_key = _tattr(t, "theme_key", "")
        for tk in _tattr(t, "constituents", []) or []:
            if rs.get(tk, {}).get("active") is not None:
                if get_ticker_role(theme_key, tk) != "unknown":
                    named_roles += 1
    return named_roles / total_constituents


def _asymmetry_strength(themes: list) -> float:
    """Fraction of ordered LIVE themes that are structurally early + early-stage.

    A theme is asymmetric when its ``wave_order`` is in {1, 2} AND its ``stage``
    is in ``_EARLY_STAGES`` ({"rotating_in"} — empty string excluded).
    Denominator: LIVE themes that have a transmission order. Range 0.0..1.0.
    """
    from lib.theme_transmission import get_transmission_order

    live = _live(themes)
    ordered_live = [
        t for t in live
        if get_transmission_order(_tattr(t, "theme_key", "")) is not None
    ]
    if not ordered_live:
        return 0.0

    early_asymmetric = sum(
        1 for t in ordered_live
        if get_transmission_order(_tattr(t, "theme_key", "")) in _EARLY_WAVE_ORDERS
        and _tattr(t, "stage", "") in _EARLY_STAGES
    )
    return early_asymmetric / len(ordered_live)


# ---------------------------------------------------------------------------
# Deterministic confidences (computed BEFORE any LLM call)
# ---------------------------------------------------------------------------

def _compute_short_confidence(themes: list, diffusion: dict) -> float:
    """Role-resolution confidence = theme_coverage x role_resolution.

    Confidence in the short-term per-ticker role read is how many of the live
    constituents we can actually pin to a NAMED role (vs the whole live field),
    discounted by how much of the data was live. Deterministic.

    Edge cases (all -> 0.0):
      * no themes at all, or every theme is fixture -> 0.0.
      * no live constituent has a named role + active excess -> resolution 0 -> 0.0.

    Range: 0.0..1.0 (rounded to 6 dp).
    """
    live = _live(themes)
    if not themes or not live:
        return 0.0
    return round(_theme_coverage(themes) * _role_resolution(themes), 6)


def _compute_mid_confidence(themes: list, diffusion: dict) -> float:
    """Asymmetry confidence = theme_coverage x asymmetry_strength.

    The 2-6 week asymmetry read is trustworthy in proportion to how much of the
    ordered live field is structurally early (low wave_order AND early stage),
    discounted by live coverage. Deterministic.

    Edge cases (all -> 0.0):
      * every theme is fixture -> 0.0.
      * no live theme has a transmission order -> 0.0.
      * no ordered live theme is early-wave + early-stage -> strength 0 -> 0.0.

    Range: 0.0..1.0 (rounded to 6 dp).
    """
    live = _live(themes)
    if not live:
        return 0.0
    return round(_theme_coverage(themes) * _asymmetry_strength(themes), 6)


def _compute_long_confidence() -> float:
    """Always 0.0 — see ``_LONG_RATIONALE``.

    Theme transmission roles / asymmetry are tactical short-to-mid signals; they
    carry no long-horizon information, so the long confidence is structurally
    zero (mirrors ``SectorRotationAgent._compute_long_confidence``).
    """
    return 0.0


def _compute_signal_basis(themes: list, diffusion: dict,
                          short_conf: float, mid_conf: float) -> str:
    """Three-way classifier distinguishing the meaning of a low/zero read.

      * ``"signal_present"``        — at least one confidence is positive (a
                                      named live role and/or an asymmetric theme
                                      was found).
      * ``"degraded_insufficient"`` — too little live data to assess (no live
                                      themes, or fewer than half the themes are
                                      live) — must NOT be read as "no signal".
      * ``"no_role_signal"``        — data IS present but neither a named role
                                      nor an asymmetric theme emerged (seed-map
                                      coverage too sparse or all themes already
                                      late-stage). NOT a bearish call.
    """
    live = _live(themes)
    if short_conf > 0.0 or mid_conf > 0.0:
        return "signal_present"
    if not live or len(live) < len(themes) // 2:
        return "degraded_insufficient"
    return "no_role_signal"


# ---------------------------------------------------------------------------
# task_instruction builder
# ---------------------------------------------------------------------------

def _qual_context(top_themes: list, asymmetric_themes: list,
                  late_stage_themes: list, signal_basis: str) -> str:
    """Build the QUALITATIVE (number-free) context block for the prompt.

    Only theme NAMES, role words, stage labels, and the signal_basis are
    interpolated — never a numeric value (no wave_order ints, no excess
    figures) — so the model is never handed a number to echo.
    """
    leaders: list = []
    laggards: list = []
    for tt in top_themes:
        label = str(tt.get("label_en") or tt.get("theme_key") or "")
        for rc in tt.get("ranked_constituents", []) or []:
            role = str(rc.get("role") or "")
            tk = str(rc.get("ticker") or "")
            if role in ("leader", "second_derivative_beneficiary"):
                leaders.append(f"{tk} ({role} in {label})")
            elif role == "laggard":
                laggards.append(f"{tk} (laggard in {label})")

    asym = [str(a.get("label_en") or a.get("theme_key") or "")
            for a in asymmetric_themes]
    late = [str(l.get("label_en") or l.get("theme_key") or "")
            for l in late_stage_themes]

    return (
        f"Top-theme live leaders / 2nd-derivative names: "
        f"{', '.join(leaders) or 'none'}. "
        f"Top-theme live laggard names: {', '.join(laggards) or 'none'}. "
        f"Structurally-early asymmetric themes (early wave + early stage): "
        f"{', '.join(asym) or 'none'}. "
        f"Already-late / crowded themes: {', '.join(late) or 'none'}. "
        f"Signal basis: {signal_basis}."
    )


def _build_task_instruction(top_themes: list, asymmetric_themes: list,
                            late_stage_themes: list, signal_basis: str) -> str:
    """Build the dynamic, horizon-aware ThemeIntelligenceAgent task instruction.

    All interpolated context is QUALITATIVE (theme/role/stage names, signal
    basis) — never numeric. The REQUIRED OUTPUT FORMAT block uses 4-space
    indentation (NOT triple-backtick fences, which confuse the JSON extractor
    in agent_runner).
    """
    return (
        "You are ThemeIntelligenceAgent. Synthesize the deterministic theme "
        "transmission-chain structure and the live constituent ranking into "
        "ROLE-AWARE and ASYMMETRY-AWARE investment intelligence for the PM "
        "agents. Your lane is (a) each ticker's live ROLE within its theme "
        "(leader / 2nd-derivative / supplier / laggard) and (b) CROSS-WAVE "
        "asymmetric opportunity — themes that are structurally early in the "
        "chain and not yet crowded.\n\n"
        f"{_qual_context(top_themes, asymmetric_themes, late_stage_themes, signal_basis)}\n\n"
        "Based on the evidence packet, provide THREE findings:\n"
        "1. SHORT-TERM (role): within the top-momentum themes, name which "
        "tickers are live LEADERS vs LAGGARDS vs 2nd-derivative beneficiaries "
        "by crossing the live constituent ranking with the seed roles. Call out "
        "where the live ranking DIVERGES from the seed role (e.g. a seed-leader "
        "showing laggard relative strength is a deterioration signal). If the "
        "signal basis is \"no_role_signal\" or \"degraded_insufficient\", you "
        "MUST state that explicitly and you MUST NOT fabricate any role "
        "assignment.\n"
        "2. MID-TERM (asymmetry, 2-6 weeks): name which themes are structurally "
        "EARLY (low wave order AND an early stage) and therefore represent "
        "asymmetric upside that is NOT YET crowded; contrast them with the "
        "already-late-stage themes; state what the active-wave context implies "
        "for 2-6 week positioning, and reference the upstream / downstream "
        "propagation direction from the evidence. This CROSS-WAVE asymmetry is "
        "NOT the same as a laggard within the active wave — do not conflate "
        "them.\n"
        "3. LONG-TERM: ALWAYS state that role assessment and asymmetric "
        "opportunity are tactical short-to-mid signals only, and that deep role "
        "conviction requires individual stock research — defer to "
        "StockResearchAgent.\n\n"
        "RULES (never violate):\n"
        "- NEVER present \"no_role_signal\" as bearish; it means the seed-map "
        "coverage is sparse, NOT that the themes are weak.\n"
        "- NEVER invent a role label that is not supported by the evidence "
        "packet.\n"
        "- NEVER conflate cross-wave asymmetric upside (early wave + early "
        "stage) with a within-wave laggard (SectorRotationAgent's concept).\n"
        "- NEVER invent numbers — cite evidence_ids only.\n\n"
        "Each finding must cite at least one evidence_id from the packet. No "
        "numeric values in finding text. No dollar signs, percentages, or "
        "metric tokens.\n\n"
        # REQUIRED OUTPUT FORMAT — 4-space indentation, NOT triple-backtick
        # fences (fences confuse the JSON extractor in agent_runner). Plain
        # (NON-f) string literals: the braces below are literal.
        "REQUIRED OUTPUT FORMAT — you must respond with ONLY valid JSON\n"
        "matching this exact structure. No prose, no markdown fences.\n\n"
        "    {\n"
        "      \"agent_name\": \"ThemeIntelligenceAgent\",\n"
        "      \"run_id\": \"<use the run_id from the evidence packet header>\",\n"
        "      \"findings\": [\n"
        "        {\n"
        "          \"text\": \"<SHORT-TERM role judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        },\n"
        "        {\n"
        "          \"text\": \"<MID-TERM asymmetry judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        },\n"
        "        {\n"
        "          \"text\": \"<LONG-TERM judgment — no numbers>\",\n"
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
        "- agent_name must be exactly \"ThemeIntelligenceAgent\"\n"
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

def run_theme_intelligence_agent(
    themes: list,
    ticker: str = "MARKET",
    *,
    snapshot_dir: str = "data/snapshots",
) -> "AgentOutput":
    """Production ThemeIntelligenceAgent — see the module docstring for the pipeline.

    ``themes`` is the ALREADY-COMPUTED ``list[ThemeMomentumResult]`` (the Cockpit
    computes it once in Step 2 and injects it here). This function performs NO new
    fetch — every theme_transmission lookup and ``get_diffusion_context`` is pure
    arithmetic over data already in hand.

    Derives three deterministic confidences plus the signal-basis classifier, then
    persists three evidence-backed ToolResults BEFORE the constrained LLM call.

    The entire body is wrapped in an outer fail-closed guard: any unexpected error
    yields a rule-based fallback AgentOutput, never a raised exception.
    """
    # supporting_data is referenced by the outer fallback if we fail early.
    supporting_data: dict = {}
    run_id: Optional[str] = None

    try:
        # 1. Lazy theme_transmission imports (pure lookups; NO network, NO LLM).
        from lib.theme_transmission import (
            get_diffusion_context,
            get_theme_transmission_summary,
            get_transmission_cluster,
            get_transmission_order,
        )

        # 2. Diffusion context (pure arithmetic over the momentum scores).
        diffusion = get_diffusion_context(
            {_tattr(t, "theme_key", ""): _num(_tattr(t, "momentum_score", 0.0))
             for t in (themes or [])}
        ) or {}

        # 3. Deterministic confidences (computed BEFORE any LLM call).
        short_conf = _compute_short_confidence(themes, diffusion)
        mid_conf = _compute_mid_confidence(themes, diffusion)
        long_conf = _compute_long_confidence()

        # 4. Signal-basis classifier + exposed decomposition terms.
        signal_basis = _compute_signal_basis(themes, diffusion, short_conf, mid_conf)
        theme_coverage = round(_theme_coverage(themes), 6)
        role_resolution = round(_role_resolution(themes), 6)
        asymmetry_strength = round(_asymmetry_strength(themes), 6)
        live = _live(themes)
        n_live = len(live)
        n_fixture = len(themes or []) - n_live

        # 5. Mint one run_id and reuse it everywhere (store + packet + runner).
        from lib.reliability.run_context import create_run_context

        run_context = create_run_context(
            ticker=ticker, task="theme_intelligence_agent")
        run_id = run_context.run_id

        # 6. Build the structured payloads (numbers live in structured fields the
        #    LLM reads only as evidence, never echoes).
        from lib.agent_framework.world_adapter import (
            processed_signals_to_tool_result,
        )

        # Top N LIVE themes by momentum_score (fixtures excluded from the role read).
        top_live = sorted(
            live, key=lambda t: _num(_tattr(t, "momentum_score", 0.0)),
            reverse=True)[:_TOP_N_THEMES]

        top_themes: list = []
        upstream_downstream: dict = {}
        for t in top_live:
            tk = _tattr(t, "theme_key", "")
            top_themes.append({
                "theme_key": tk,
                "label_en": _tattr(t, "label_en", ""),
                "wave_order": get_transmission_order(tk),
                "cluster": get_transmission_cluster(tk),
                "stage": _tattr(t, "stage", ""),
                "stage_confirmed": bool(_tattr(t, "stage_confirmed", False)),
                "momentum_score": _num(_tattr(t, "momentum_score", 0.0)),
                "ranked_constituents": _rank_theme_constituents(t, n_top=5),
            })
            summary = get_theme_transmission_summary(tk) or {}
            upstream_downstream[tk] = {
                "upstream_themes": list(summary.get("upstream_themes", []) or []),
                "downstream_themes": list(summary.get("downstream_themes", []) or []),
                "same_wave_themes": list(summary.get("same_wave_themes", []) or []),
            }

        # Asymmetric themes: LIVE, wave_order in {1,2} AND stage in _EARLY_STAGES.
        asymmetric_themes: list = []
        for t in live:
            tk = _tattr(t, "theme_key", "")
            order = get_transmission_order(tk)
            if order in _EARLY_WAVE_ORDERS and _tattr(t, "stage", "") in _EARLY_STAGES:
                summary = get_theme_transmission_summary(tk) or {}
                asymmetric_themes.append({
                    "theme_key": tk,
                    "label_en": _tattr(t, "label_en", ""),
                    "wave_order": order,
                    "cluster": get_transmission_cluster(tk),
                    "stage": _tattr(t, "stage", ""),
                    "stage_confirmed": bool(_tattr(t, "stage_confirmed", False)),
                    "momentum_score": _num(_tattr(t, "momentum_score", 0.0)),
                    "upstream_themes": list(summary.get("upstream_themes", []) or []),
                })
        # Sort by wave_order asc, then momentum_score desc.
        asymmetric_themes.sort(
            key=lambda a: (a["wave_order"], -_num(a["momentum_score"])))

        # Late-stage / crowded themes (contrast set): LIVE, stage in _LATE_STAGES.
        late_stage_themes: list = []
        for t in live:
            if _tattr(t, "stage", "") in _LATE_STAGES:
                tk = _tattr(t, "theme_key", "")
                late_stage_themes.append({
                    "theme_key": tk,
                    "label_en": _tattr(t, "label_en", ""),
                    "wave_order": get_transmission_order(tk),
                    "cluster": get_transmission_cluster(tk),
                    "stage": _tattr(t, "stage", ""),
                    "momentum_score": _num(_tattr(t, "momentum_score", 0.0)),
                })

        n_asymmetric = len(asymmetric_themes)
        n_late_stage = len(late_stage_themes)

        # TR1 — per-ticker role ranking within the top themes.
        roles_payload = {
            "top_themes": top_themes,
            "upstream_downstream": upstream_downstream,
        }
        tr_roles = processed_signals_to_tool_result(
            roles_payload,
            run_id=run_id,
            tool_name="theme_intelligence_roles",
            target=ticker,
            metric_group="theme_roles",
            description="Per-ticker role ranking within top themes",
        )

        # TR2 — cross-wave asymmetric opportunity set + late-stage contrast.
        asymmetry_payload = {
            "asymmetric_themes": asymmetric_themes,
            "late_stage_themes": late_stage_themes,
            "active_wave_context": {
                "active_order": diffusion.get("active_order"),
                "next_order": diffusion.get("next_order"),
                "next_order_themes": list(
                    diffusion.get("next_order_themes", []) or []),
            },
            "signal_basis": signal_basis,
        }
        tr_asymmetry = processed_signals_to_tool_result(
            asymmetry_payload,
            run_id=run_id,
            tool_name="theme_intelligence_asymmetry",
            target=ticker,
            metric_group="asymmetry",
            description="Cross-wave asymmetric opportunity set",
        )

        # TR3 — deterministic confidence scores (computed before the LLM).
        confidence_payload = {
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
            "theme_coverage": theme_coverage,
            "role_resolution": role_resolution,
            "asymmetry_strength": asymmetry_strength,
            "n_live": n_live,
            "n_fixture": n_fixture,
            "n_asymmetric": n_asymmetric,
            "n_late_stage": n_late_stage,
            "long_rationale": _LONG_RATIONALE,
        }
        tr_confidence = processed_signals_to_tool_result(
            confidence_payload,
            run_id=run_id,
            tool_name="theme_intelligence_confidence",
            target=ticker,
            metric_group="confidence",
            description=(
                "Deterministic confidence scores (computed before LLM). "
                + _LONG_RATIONALE
            ),
        )

        # 7. Dynamic, horizon-aware task instruction.
        task_instruction = _build_task_instruction(
            top_themes, asymmetric_themes, late_stage_themes, signal_basis)

        # 8. supporting_data carried on the AgentOutput.
        supporting_data = {
            "signal_basis": signal_basis,
            "n_asymmetric": n_asymmetric,
            "active_order": diffusion.get("active_order"),
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
        }

        # 9. Run the constrained agent (cross-horizon synthesis; EOD validity).
        from lib.agent_framework.agent_runner import run_llm_agent

        return run_llm_agent(
            agent_id="ThemeIntelligenceAgent",
            horizon="cross",
            task_instruction=task_instruction,
            tool_results=[tr_roles, tr_asymmetry, tr_confidence],
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
            "run_theme_intelligence_agent failed; returning fallback: %s", exc)
        from lib.agent_framework.agent_runner import _fallback_agent_output

        return _fallback_agent_output(
            "ThemeIntelligenceAgent",
            "cross",
            supporting_data,
            exc,
            valid_until=end_of_today_iso(),
            run_id=run_id,
            target=ticker,
            ticker=ticker,
        )
