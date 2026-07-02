"""
lib/degradation_view.py

Degradation-Visibility Layer — a small, LLM-free, network-free ENABLER module
(same spirit as ``lib/candidate_eligibility.py``). It reads already-persisted
``AgentOutput`` records and produces a normalized, comparable "degradation
view" per agent (or per theme, for CandidateScreeningAgent).

It does NOT compute anything new about markets. It only re-describes what each
agent already wrote into its own ``supporting_data``, in a shape a UI can
render uniformly across six structurally different agents.

DESIGN CONSTRAINTS (enforced here):
  * ZERO imports from ``lib.reliability``. The ``AgentOutput`` objects consumed
    here have already been reconstructed by ``lib.agent_framework.agent_output``
    before this module ever sees them.
  * ZERO network calls. ZERO LLM calls.
  * Every read from a record's ``supporting_data`` dict uses ``.get()`` with a
    default. ``supporting_data`` has NO schema validation on deserialization
    (``agent_output_from_dict`` does ``d.get("supporting_data") or {}`` with no
    further checking), and historical records may predate later fields being
    added. Never assume a key exists.
  * NEVER raise. A record this module cannot make sense of degrades to an
    ``"other:<raw>"`` bucket, not an exception.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

# Runtime import is safe: agent_output performs NO lib.reliability import at
# module load (it lazy-imports reliability inside from_dict). Importing this
# module therefore never triggers the heavy reliability package __init__.
from lib.agent_framework.agent_output import load_agent_outputs

if TYPE_CHECKING:  # annotations only
    from lib.agent_framework.agent_output import AgentOutput


# ---------------------------------------------------------------------------
# Canonical agent identity
# ---------------------------------------------------------------------------

#: The six foundation agents this layer knows how to describe, in display order.
CANONICAL_AGENT_IDS: tuple[str, ...] = (
    "MacroRegimeAgent",
    "MoneyFlowAgent",
    "MarketStructureAgent",
    "SectorRotationAgent",
    "ThemeIntelligenceAgent",
    "CandidateScreeningAgent",
)


# ---------------------------------------------------------------------------
# Defensive-flag allow-list
# ---------------------------------------------------------------------------

# STARTER list, deliberately small and human-editable — NOT exhaustive. A flag
# NOT in this set is treated as NON-defensive on purpose: this layer fails
# closed / favors visibility (matching project philosophy), so an ambiguous or
# unknown flag pushes ``likely_bug`` true rather than being silently excused.
#
# Explicitly NOT added here: "gex_dex_degraded", "dark_pool_insufficient",
# "regime_degraded", "adjacency_degraded". Whether those are benign depends on
# which optional API keys are configured — something this module does NOT
# introspect in v1 (that refinement is the "runtime zero-degradation acceptance
# protocol" future work, ROADMAP §5.10, not this phase). A human who knows their
# own key configuration makes the final call for those on the review page.
KNOWN_DEFENSIVE_FLAGS: frozenset[str] = frozenset({
    "unavailable:short_crowding",
    "unavailable:options_structure",
    "vintage_mismatch",
})


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# Shared signal_basis-style vocabulary → normalized state. Used by EVERY agent
# that keys off a signal_basis string; do NOT duplicate this mapping per agent.
#
# The three signal_basis-emitting agents were audited exhaustively (every string
# literal each ``_compute_signal_basis`` can return is enumerated in
# docs/reliability_degradation_visibility_layer.md); all are mapped below:
#   MarketStructureAgent  : signal_present / degraded_insufficient / full_data_no_signal
#   SectorRotationAgent   : signal_present / degraded_insufficient / no_clear_leadership
#   ThemeIntelligenceAgent: signal_present / degraded_insufficient / no_role_signal
# Plus CandidateScreeningAgent's per-horizon vocabulary (no_clear_winner).
_BASIS_MAP: dict[str, str] = {
    "signal_present": "ok",
    "degraded_insufficient": "degraded",
    "no_clear_winner": "no_winner",       # CandidateScreeningAgent vocabulary
    "no_role_signal": "no_signal",        # ThemeIntelligenceAgent neutral/wait
    # MarketStructureAgent's normal "data present, no warning" state — a genuine
    # neutral/wait read, identical in kind to no_role_signal. Mapped to the same
    # neutral bucket so it does NOT fall into other:* and false-trip likely_bug.
    "full_data_no_signal": "no_signal",
    # Confirmed present in lib/agents/sector_rotation_agent.py::_compute_signal_basis
    # as a genuine neutral / wait state (data present, no confirmed stage / wave).
    "no_clear_leadership": "no_leadership",
}

# Non-alphanumeric runs collapse to a single underscore for "other:<raw>".
_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def _sanitize(raw: str) -> str:
    """Lowercase, collapse non-alphanumerics to underscores, strip edges."""
    return _SANITIZE_RE.sub("_", raw.strip().lower()).strip("_") or "unknown"


def normalize_basis(raw: Optional[str]) -> str:
    """Map an agent's raw signal_basis token to a normalized state string.

    Known tokens map per ``_BASIS_MAP``. ``None`` maps to ``"other:missing"``.
    Anything else maps to ``"other:<sanitized>"``. Never raises.
    """
    if raw is None:
        return "other:missing"
    if not isinstance(raw, str):
        return "other:" + _sanitize(str(raw))
    key = raw.strip()
    if key in _BASIS_MAP:
        return _BASIS_MAP[key]
    low = key.lower()
    if low in _BASIS_MAP:
        return _BASIS_MAP[low]
    return "other:" + _sanitize(key)


# Severity precedence (worst → best):
#   "degraded" > "other:*" > "no_winner"/"no_signal"/"no_leadership" > "ok"
# "missing" (placeholder only) sits below "ok" and is never combined.
_NEUTRAL_STATES = frozenset({"no_winner", "no_signal", "no_leadership"})


def _severity_rank(state: str) -> int:
    if state == "degraded":
        return 4
    if state.startswith("other:"):
        return 3
    if state in _NEUTRAL_STATES:
        return 2
    if state == "ok":
        return 1
    return 0  # "missing" / anything unexpected


def _worst_basis(states: list[str]) -> str:
    """Return the worst state of the set per the severity precedence."""
    return max(states, key=_severity_rank)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentDegradationView:
    agent_id: str
    theme_key: Optional[str]           # None for the five single-record agents;
                                       # the theme string for CandidateScreeningAgent
    has_output: bool
    basis_state: str                   # normalized; "missing" when has_output=False
    horizon_basis: Optional[dict]      # e.g. {"short": "ok", "mid": "no_winner"};
                                       # populated ONLY for CandidateScreeningAgent
    coverage: Optional[object]         # agent-specific meaning. A float for the
                                       # five single-record agents; a
                                       # {"short": ..., "mid": ...} DICT for
                                       # CandidateScreeningAgent (two meaningful
                                       # confidences). None when unavailable.
                                       # Page-side code must handle both shapes.
    degrade_flags: list               # machine tags, per per-agent rules
    judgment_source: Optional[str]     # "llm_proposed"|"rule_based"|"human"|None
    likely_bug: bool
    detail: dict = field(default_factory=dict)   # free-form display-only extras
                                                 # (no_trade_reason_*, runner_error);
                                                 # NOT used in any judgment/severity logic
    source: "Optional[AgentOutput]" = None       # underlying record (judgment /
                                                 # evidence_refs / timestamp /
                                                 # valid_until / raw supporting_data);
                                                 # None iff has_output is False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _last(records: "list[AgentOutput]") -> "Optional[AgentOutput]":
    """The latest record (load_agent_outputs returns ascending by timestamp)."""
    return records[-1] if records else None


def _as_float(value: object) -> Optional[float]:
    """Coerce to float, or None if not coercible. Never raises."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _add_runner_error(detail: dict, sd: dict) -> None:
    """Pass a truthy runner_error into ``detail`` (display-only)."""
    err = sd.get("runner_error")
    if err:
        detail["runner_error"] = err


def _placeholder(agent_id: str, theme_key: Optional[str] = None) -> AgentDegradationView:
    """A has_output=False view for an agent/date that produced nothing."""
    return AgentDegradationView(
        agent_id=agent_id,
        theme_key=theme_key,
        has_output=False,
        basis_state="missing",
        horizon_basis=None,
        coverage=None,
        degrade_flags=[],
        judgment_source=None,
        likely_bug=True,
        detail={},
        source=None,
    )


def _make_view(
    agent_id: str,
    rec: "AgentOutput",
    basis_state: str,
    horizon_basis: Optional[dict],
    coverage: Optional[object],
    degrade_flags: list,
    detail: dict,
    theme_key: Optional[str] = None,
) -> AgentDegradationView:
    """Assemble a has_output=True view and compute ``likely_bug``.

    likely_bug OR-combines every signal (all computed, first-true-wins is
    irrelevant since they are OR'd):
      * judgment_source == "rule_based"
      * basis_state == "degraded"   (kept even when it looks redundant with a
        flag: an agent can report a degraded basis WITHOUT appending a named
        flag — e.g. MarketStructureAgent's signal_basis alone can say
        degraded_insufficient with no vintage_mismatch — so relying only on the
        flags list would silently under-report this case)
      * basis_state.startswith("other:")   (unrecognized / missing basis)
      * any degrade flag not in KNOWN_DEFENSIVE_FLAGS
    """
    js = getattr(rec, "judgment_source", None)
    likely_bug = (
        js == "rule_based"
        or basis_state == "degraded"
        or basis_state.startswith("other:")
        or any(flag not in KNOWN_DEFENSIVE_FLAGS for flag in degrade_flags)
    )
    return AgentDegradationView(
        agent_id=agent_id,
        theme_key=theme_key,
        has_output=True,
        basis_state=basis_state,
        horizon_basis=horizon_basis,
        coverage=coverage,
        degrade_flags=list(degrade_flags),
        judgment_source=js,
        likely_bug=likely_bug,
        detail=detail,
        source=rec,
    )


# ---------------------------------------------------------------------------
# Per-agent build functions
# ---------------------------------------------------------------------------
# Each takes the list[AgentOutput] returned by load_agent_outputs(agent_id,
# date=...) and returns list[AgentDegradationView] with AT LEAST one view
# (a has_output=False placeholder when the input is empty). Only
# CandidateScreeningAgent can return more than one view (one per theme_key).

def build_view_macro_regime(records: "list[AgentOutput]") -> list[AgentDegradationView]:
    rec = _last(records)
    if rec is None:
        return [_placeholder("MacroRegimeAgent")]
    sd = rec.supporting_data or {}
    raw_regime = sd.get("regime")
    if raw_regime in {"degraded", "unknown"}:
        basis = "degraded"
    elif raw_regime is None:
        basis = "other:missing"
    else:
        basis = "ok"
    coverage = _as_float(sd.get("data_coverage"))
    flags: list[str] = ["regime_degraded"] if basis == "degraded" else []
    detail: dict = {}
    _add_runner_error(detail, sd)
    return [_make_view("MacroRegimeAgent", rec, basis, None, coverage, flags, detail)]


def build_view_money_flow(records: "list[AgentOutput]") -> list[AgentDegradationView]:
    rec = _last(records)
    if rec is None:
        return [_placeholder("MoneyFlowAgent")]
    sd = rec.supporting_data or {}
    raw_degraded = sd.get("degraded")
    if raw_degraded is True:
        basis = "degraded"
    elif raw_degraded is False:
        basis = "ok"
    else:
        basis = "other:missing"
    sac = sd.get("signals_agree_count")
    sac_f = _as_float(sac)
    coverage = (sac_f / 3.0) if sac_f is not None else None
    flags: list[str] = []
    if raw_degraded is True:
        flags.append("gex_dex_degraded")
    if sd.get("dark_pool_direction") == "insufficient_data":
        flags.append("dark_pool_insufficient")
    detail: dict = {}
    _add_runner_error(detail, sd)
    return [_make_view("MoneyFlowAgent", rec, basis, None, coverage, flags, detail)]


def build_view_market_structure(records: "list[AgentOutput]") -> list[AgentDegradationView]:
    rec = _last(records)
    if rec is None:
        return [_placeholder("MarketStructureAgent")]
    sd = rec.supporting_data or {}
    basis = normalize_basis(sd.get("signal_basis"))
    coverage = _as_float(sd.get("short_confidence"))
    # KNOWN FOLLOW-UP: MarketStructureAgent computes vintage_mismatch /
    # adjacency_degraded into its health_payload ToolResult but does NOT persist
    # them into supporting_data, so reading them here would ALWAYS miss on real
    # records. Per the no-agent-change rule we do not read them — degrade_flags
    # stays empty for now, and basis_state alone still expresses
    # degraded_insufficient, so likely_bug correctness is unaffected. See the
    # phase doc for the follow-up that would persist these fields.
    detail: dict = {}
    _add_runner_error(detail, sd)
    return [_make_view("MarketStructureAgent", rec, basis, None, coverage, [], detail)]


def build_view_sector_rotation(records: "list[AgentOutput]") -> list[AgentDegradationView]:
    rec = _last(records)
    if rec is None:
        return [_placeholder("SectorRotationAgent")]
    sd = rec.supporting_data or {}
    basis = normalize_basis(sd.get("signal_basis"))
    coverage = _as_float(sd.get("short_confidence"))
    detail: dict = {}
    _add_runner_error(detail, sd)
    return [_make_view("SectorRotationAgent", rec, basis, None, coverage, [], detail)]


def build_view_theme_intelligence(records: "list[AgentOutput]") -> list[AgentDegradationView]:
    rec = _last(records)
    if rec is None:
        return [_placeholder("ThemeIntelligenceAgent")]
    sd = rec.supporting_data or {}
    basis = normalize_basis(sd.get("signal_basis"))
    coverage = _as_float(sd.get("short_confidence"))
    detail: dict = {}
    _add_runner_error(detail, sd)
    return [_make_view("ThemeIntelligenceAgent", rec, basis, None, coverage, [], detail)]


def build_view_candidate_screening(records: "list[AgentOutput]") -> list[AgentDegradationView]:
    # No records at all that day → a single placeholder (there is no theme to
    # report when nothing ran).
    if not records:
        return [_placeholder("CandidateScreeningAgent")]

    # Group by theme_key, keeping the LAST record per theme. records are already
    # ascending by timestamp, so a plain overwrite yields last-wins per theme,
    # while dict insertion order preserves first-seen theme order for display.
    latest_by_theme: dict = {}
    for rec in records:
        sd = rec.supporting_data or {}
        latest_by_theme[sd.get("theme_key")] = rec

    views: list[AgentDegradationView] = []
    for _tk, rec in latest_by_theme.items():
        sd = rec.supporting_data or {}
        short_basis = normalize_basis(sd.get("signal_basis_short"))
        mid_basis = normalize_basis(sd.get("signal_basis_mid"))
        horizon_basis = {"short": short_basis, "mid": mid_basis}
        basis = _worst_basis([short_basis, mid_basis])
        # NOTE: coverage is a DICT here (two meaningful confidences), unlike the
        # float every other agent produces. The page handles both shapes.
        coverage = {
            "short": sd.get("short_confidence"),
            "mid": sd.get("mid_confidence"),
        }
        flags = [f"unavailable:{item}" for item in (sd.get("unavailable_dimensions") or [])]
        detail: dict = {}
        # no_trade_reason is INFORMATIONAL (it accompanies the no_winner neutral
        # state); it is NOT itself a degradation flag.
        ntr_short = (sd.get("short_slate") or {}).get("no_trade_reason")
        ntr_mid = (sd.get("mid_slate") or {}).get("no_trade_reason")
        if ntr_short:
            detail["no_trade_reason_short"] = ntr_short
        if ntr_mid:
            detail["no_trade_reason_mid"] = ntr_mid
        _add_runner_error(detail, sd)
        views.append(_make_view(
            "CandidateScreeningAgent", rec, basis, horizon_basis, coverage,
            flags, detail, theme_key=sd.get("theme_key"),
        ))
    return views


# Dispatch table: canonical agent_id → build function.
_BUILDERS = {
    "MacroRegimeAgent": build_view_macro_regime,
    "MoneyFlowAgent": build_view_money_flow,
    "MarketStructureAgent": build_view_market_structure,
    "SectorRotationAgent": build_view_sector_rotation,
    "ThemeIntelligenceAgent": build_view_theme_intelligence,
    "CandidateScreeningAgent": build_view_candidate_screening,
}


# ---------------------------------------------------------------------------
# Top-level entry points
# ---------------------------------------------------------------------------

def load_and_build_all_views(
    date: str,
    base_dir: str = "data/agent_outputs",
) -> dict:
    """Load + build degradation views for all six canonical agents on ``date``.

    Returns a dict keyed by the six canonical ``agent_id`` strings. Every value
    is a NON-EMPTY list (at minimum one has_output=False placeholder). ``date``
    is REQUIRED (``YYYYMMDD`` / ``YYYY-MM-DD``, same acceptance as
    ``load_agent_outputs``). It is deliberately NOT optional: an all-dates load
    would let build_view_candidate_screening merge the same theme_key across
    different dates (it groups by theme only), so the public signature forbids
    that footgun structurally rather than guarding against it. Never raises.
    """
    out: dict = {}
    for agent_id, builder in _BUILDERS.items():
        try:
            records = load_agent_outputs(agent_id, base_dir=base_dir, date=date)
        except Exception:  # defensive: loader is fail-closed, but never propagate
            records = []
        try:
            views = builder(records)
        except Exception:  # a record we truly cannot make sense of → placeholder
            views = [_placeholder(agent_id)]
        if not views:
            views = [_placeholder(agent_id)]
        out[agent_id] = views
    return out


def list_available_dates(base_dir: str = "data/agent_outputs") -> list[str]:
    """Sorted union of every ``*.jsonl`` filename stem across the six agent dirs.

    Filenames on disk are already ``YYYY-MM-DD`` stems. A missing ``base_dir``
    or a missing/unreadable subdir contributes nothing rather than raising.
    Never raises.
    """
    dates: set[str] = set()
    for agent_id in CANONICAL_AGENT_IDS:
        sub = os.path.join(base_dir, agent_id)
        if not os.path.isdir(sub):
            continue
        try:
            names = os.listdir(sub)
        except OSError:
            continue
        for name in names:
            if name.endswith(".jsonl"):
                dates.add(name[: -len(".jsonl")])
    return sorted(dates)
