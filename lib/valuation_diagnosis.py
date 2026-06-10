"""lib/valuation_diagnosis.py — Anchor Intelligence v2.4 valuation diagnosis card.

A **pure, deterministic** assembly (no LLM, no new anchor math, no I/O) of a
structured :class:`ValuationDiagnosis` from fields that ALREADY exist on an
:class:`lib.equity_valuation.AppFairValue` plus the v2.3 anchor-migration readout
(:func:`lib.anchor_migration.compute_migration`). It answers, in one readable
object, "why is this valuation what it is" — which methods applied, which were
rejected and why, whether the anchors cluster or one is an outlier, the endorsed
range (or the honest "irreconcilable" state), the confidence, and — the one NEW
deterministic mapping this round — a ``valuation_role`` token that is the interface
between the valuation layer and the 7A three-horizon view.

Reliability discipline:

* **No anchor math.** Every number comes straight off ``AppFairValue`` / the
  migration readout; nothing is recomputed or invented here.
* **No I/O.** ``build_valuation_diagnosis`` and ``classify_valuation_role`` are pure
  functions of their arguments — the card never triggers a compute or a fetch on any
  path (see the v2.4 STEP 0 Matrix A in ``docs/reliability_anchor_intel_v2.md``).
* **Language-neutral data.** The diagnosis carries stable TOKENS + numbers; the
  pages map tokens → bilingual text via ``t()`` (numbers by code, language by LLM/UI
  — the project's first design principle).
* **Never-fabricate placeholders.** Reverse-DCF (A4) and narrative catalysts (A3-ii)
  are explicit, NAMED Phase-8-pending slots — present and labelled, never silently
  populated with invented content this round.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# valuation_role — the NEW deterministic mapping (A2). VISIBLE CONFIG BLOCK.
# ---------------------------------------------------------------------------
# Maps (confidence × anchor_consistency × upside-vs-price) → a role token the 7A
# three-horizon view can consume. Fully deterministic, no LLM. Tune the thresholds /
# sets HERE — the ladder in ``classify_valuation_role`` reads only these constants.

VALUATION_ROLE_INFORMATIONAL = "informational"        # context only; not a driver
VALUATION_ROLE_MID = "mid_term_supportive"            # supports a mid-horizon view
VALUATION_ROLE_LONG = "long_term_eligible"            # eligible as a long-horizon driver

# Upside (fair_value_mid vs current price) required to elevate a high-confidence,
# consistent valuation to long_term_eligible.
VALUATION_ROLE_UPSIDE_LONG_MIN = 0.15  # +15%

# Confidence tiers that can rise ABOVE informational (low never does).
_ROLE_CONF_SUPPORTIVE = ("medium", "high")
# anchor_consistency states that count as "consistent enough" to support a role.
# A lone anchor or an irreconcilable/empty band is NOT consistent corroboration.
_ROLE_CONSISTENT_STATES = ("consistent",)

# ---------------------------------------------------------------------------
# anchor_consistency states (derived from AppFairValue; stable tokens).
# ---------------------------------------------------------------------------
CONSISTENCY_CONSISTENT = "consistent"          # >=2 anchors blended within dispersion
CONSISTENCY_SINGLE = "single_anchor"           # only one anchor entered the blend
CONSISTENCY_IRRECONCILABLE = "irreconcilable"  # anchors disagreed beyond threshold
CONSISTENCY_NO_ANCHOR = "no_anchor"            # no real anchor (band on current price)

# Outlier sentinel: the producer flagged disagreement but did NOT unambiguously name a
# single outlier (e.g. two anchors at equal deviation, or no per-anchor exclusion
# signal). We report the ambiguity HONESTLY rather than picking one by list order —
# the same never-fabricate discipline applied to classification.
NO_CLEAR_OUTLIER = "no_clear_outlier"

# ---------------------------------------------------------------------------
# what_would_change — MECHANICAL condition tokens (A3-i). Falsifiable conditions
# in the same shape thesis_monitor uses (a checkable statement + a current truth).
# ---------------------------------------------------------------------------
COND_PRICE_ABOVE_RANGE = "price_above_endorsed_range"   # price > endorsed high
COND_PRICE_BELOW_RANGE = "price_below_endorsed_range"   # price < endorsed low
COND_ANALYST_POOL_DETERIORATING = "analyst_pool_migration_deteriorating"

_BLEND_IRRECONCILABLE = "anchors_irreconcilable"
_BLEND_NONE = "no_anchor"


# ---------------------------------------------------------------------------
# Structured pieces
# ---------------------------------------------------------------------------


@dataclass
class RejectedMethod:
    """One method/anchor computed-or-applicable but NOT in the blend, with a reason."""

    name: str = ""
    value: Optional[float] = None
    reason: str = ""   # stable token: "cycle_distorted" | "excluded_anchor" |
                       # "dcf_unavailable" | "implausible_vs_price" | ...
    detail: str = ""   # optional human basis (e.g. fv.dcf_note) — tooltip text


@dataclass
class AnchorConsistency:
    """Which anchors cluster, which (if any) is the outlier, and the dispersion."""

    state: str = CONSISTENCY_NO_ANCHOR
    clustered: list = field(default_factory=list)   # anchor names that agree
    outlier: str = ""                               # name of the disagreeing anchor
    dispersion: Optional[float] = None              # max/min ratio across raw anchors


@dataclass
class EndorsedRange:
    """The blended low/high the system endorses, or the honest degrade state."""

    state: str = "unavailable"   # "endorsed" | "irreconcilable" | "unavailable"
    low: Optional[float] = None
    mid: Optional[float] = None
    high: Optional[float] = None


@dataclass
class MechanicalCondition:
    """A falsifiable, deterministic condition that would move the diagnosis/role."""

    id: str = ""
    threshold: Optional[float] = None   # the boundary value (e.g. endorsed high)
    current: Optional[float] = None     # the current observed value (e.g. price)
    met: bool = False                   # is the condition currently satisfied?
    basis: str = ""                     # provenance: "endorsed_range" | "migration_readout"


@dataclass
class WhatWouldChange:
    """Conditions/catalysts that would change the valuation read (A3)."""

    # (i) MECHANICAL — implemented now, deterministic, falsifiable.
    mechanical: list = field(default_factory=list)   # list[MechanicalCondition]
    # (ii) NARRATIVE catalysts (margin guidance, etc.) — Phase-8 PLACEHOLDER.
    narrative_catalysts: list = field(default_factory=list)
    narrative_pending: bool = True   # populated in Phase 8, not this round


@dataclass
class ReverseDCFSlot:
    """A4 — named Phase-8-pending reverse-DCF slot in the method menu (NOT computed)."""

    status: str = "phase_8_pending"
    implied_growth: Optional[float] = None   # filled in Phase 8


@dataclass
class ValuationDiagnosis:
    """The full structured diagnosis card (pure assembly; render-time only).

    Language-neutral: tokens + numbers. The pages map tokens → bilingual copy.
    """

    ticker: str = ""
    company_type: str = ""
    applicable_methods: list = field(default_factory=list)
    rejected_methods: list = field(default_factory=list)      # list[RejectedMethod]
    anchor_consistency: AnchorConsistency = field(default_factory=AnchorConsistency)
    endorsed_range: EndorsedRange = field(default_factory=EndorsedRange)
    confidence: str = "low"
    upside_pct: float = 0.0
    valuation_role: str = VALUATION_ROLE_INFORMATIONAL
    # Anchor Intelligence v2.5 — multi-dimensional peer match quality. Sourced
    # (never recomputed) from AppFairValue: "high" / "low" / "" (not assessed, e.g.
    # the network-free path supplied no peers). On "low" the peer-multiple anchors
    # were EXCLUDED from the blend (the rejected_methods list shows them with reason
    # insufficient_comparable_peers) — the card surfaces WHY.
    peer_match_quality: str = ""
    peer_match_reason: str = ""
    what_would_change: WhatWouldChange = field(default_factory=WhatWouldChange)
    reverse_dcf: ReverseDCFSlot = field(default_factory=ReverseDCFSlot)
    caveats: list = field(default_factory=list)
    computed_at: str = ""


# ---------------------------------------------------------------------------
# valuation_role classifier (pure, deterministic — A2)
# ---------------------------------------------------------------------------


def classify_valuation_role(confidence: str, anchor_consistency: str,
                            upside_pct: float, blend_state: str) -> str:
    """Map (confidence × consistency × upside) → a valuation_role token.

    Deterministic ladder over the visible config block above (no LLM):

    * ``anchors_irreconcilable`` → ``informational`` (no trustworthy band).
    * ``confidence == low`` → ``informational`` (regardless of the rest).
    * consistent anchors + ``confidence in {medium, high}`` → at least
      ``mid_term_supportive``.
    * additionally ``confidence == high`` AND ``upside > VALUATION_ROLE_UPSIDE_LONG_MIN``
      → ``long_term_eligible``.
    * everything else (single/no anchor, or high-conf-but-low-upside without
      consistency) → ``informational``.
    """
    conf = str(confidence or "low").lower()
    cons = str(anchor_consistency or "").lower()
    if str(blend_state or "") == _BLEND_IRRECONCILABLE:
        return VALUATION_ROLE_INFORMATIONAL
    if conf == "low":
        return VALUATION_ROLE_INFORMATIONAL
    if cons in _ROLE_CONSISTENT_STATES and conf in _ROLE_CONF_SUPPORTIVE:
        try:
            up = float(upside_pct)
        except (TypeError, ValueError):
            up = 0.0
        if conf == "high" and up > VALUATION_ROLE_UPSIDE_LONG_MIN:
            return VALUATION_ROLE_LONG
        return VALUATION_ROLE_MID
    return VALUATION_ROLE_INFORMATIONAL


# ---------------------------------------------------------------------------
# Internal derivations (pure)
# ---------------------------------------------------------------------------


def _g(fv, name, default=None):
    return getattr(fv, name, default)


def _rejected_methods(fv) -> list:
    """Build the rejected-method list from existing AppFairValue fields (no new math).

    Sources, all already present:
    * ``excluded_anchors`` — computed-but-not-blended anchors, each
      ``{name, value, basis, flag}``; the ``flag`` (e.g. ``cycle_distorted``) is the
      reason token, else ``excluded_anchor``.
    * DCF unavailable — when ``dcf_value is None`` the ``dcf_note`` carries the
      reason (e.g. FCF unavailable, or "DCF excluded for type"); surfaced as a
      rejected method so the menu shows WHY DCF is absent.
    """
    out: list = []
    for a in (_g(fv, "excluded_anchors", []) or []):
        if not isinstance(a, dict):
            continue
        flag = str(a.get("flag", "") or "")
        out.append(RejectedMethod(
            name=str(a.get("name", "") or ""),
            value=(float(a["value"]) if isinstance(a.get("value"), (int, float))
                   and not isinstance(a.get("value"), bool) else None),
            reason=flag or "excluded_anchor",
            detail=str(a.get("basis", "") or ""),
        ))
    if _g(fv, "dcf_value", None) is None:
        note = str(_g(fv, "dcf_note", "") or "")
        # Only record DCF as "rejected" when it wasn't already an applicable method.
        if "dcf" not in [str(m).lower() for m in (_g(fv, "methods_used", []) or [])]:
            out.append(RejectedMethod(name="dcf", value=None,
                                      reason="dcf_unavailable", detail=note))
    return out


def _anchor_consistency(fv) -> AnchorConsistency:
    """Read (do NOT recompute) the producer's anchor-consistency classification.

    Assembly-only — the card never derives a fresh outlier metric (F-A1). Every field
    is SOURCED from what the producer already decided:

    * ``state`` ← ``blend_state`` (irreconcilable / no_anchor / single / blended) +
      the ``single_anchor_blend`` caveat.
    * ``clustered`` ← the anchor names the producer kept (its ``anchors`` list).
    * ``dispersion`` ← the producer's ``anchor_dispersion`` (max/min ratio it already
      computed) — passed through, not recomputed.
    * ``outlier`` ← the producer's ONLY per-anchor "this one is off" signal,
      ``excluded_anchors``. An outlier is reported ONLY when the producer excluded
      EXACTLY ONE anchor (an unambiguous, producer-made judgment). When the producer
      flagged the SET as irreconcilable but named no single culprit — or excluded
      none, or excluded several — we report :data:`NO_CLEAR_OUTLIER` (irreconcilable)
      or ``""`` (otherwise). We NEVER pick an outlier by list order or by a
      card-side distance metric: an ambiguous classification is reported as ambiguous
      (never-fabricate).
    """
    blend_state = str(_g(fv, "blend_state", "") or "")
    anchors = [a for a in (_g(fv, "anchors", []) or []) if isinstance(a, dict)]
    names = [str(a.get("name", "") or "") for a in anchors]
    dispersion = _g(fv, "anchor_dispersion", None)
    caveats = [str(c) for c in (_g(fv, "caveats", []) or [])]

    # Producer-flagged outlier = exactly one excluded anchor (unambiguous).
    excluded_names = [str(a.get("name", "") or "")
                      for a in (_g(fv, "excluded_anchors", []) or [])
                      if isinstance(a, dict) and a.get("name")]

    # --- state (sourced from blend_state + the single-anchor caveat) ---
    if blend_state == _BLEND_IRRECONCILABLE:
        state = CONSISTENCY_IRRECONCILABLE
    elif blend_state == _BLEND_NONE or _g(fv, "fair_value_mid", 0.0) in (None, 0.0):
        state = CONSISTENCY_NO_ANCHOR
    elif len(anchors) <= 1 or "single_anchor_blend" in caveats:
        state = CONSISTENCY_SINGLE
    else:
        state = CONSISTENCY_CONSISTENT

    # --- outlier (sourced from excluded_anchors; ambiguity reported honestly) ---
    if len(excluded_names) == 1:
        outlier = excluded_names[0]
    elif state == CONSISTENCY_IRRECONCILABLE:
        # The producer refused to blend due to dispersion across the raw anchors but
        # did NOT designate a single one. Report the ambiguity — do not pick by order.
        outlier = NO_CLEAR_OUTLIER
    else:
        outlier = ""

    # --- clustered (the anchors NOT singled out, sourced — no recompute) ---
    if outlier and outlier != NO_CLEAR_OUTLIER:
        clustered = [n for n in names if n != outlier]
    elif state in (CONSISTENCY_CONSISTENT, CONSISTENCY_SINGLE):
        clustered = list(names)
    else:
        clustered = []

    return AnchorConsistency(state=state, clustered=clustered, outlier=outlier,
                             dispersion=dispersion)


def _endorsed_range(fv) -> EndorsedRange:
    blend_state = str(_g(fv, "blend_state", "") or "")
    mid = _g(fv, "fair_value_mid", 0.0) or 0.0
    if blend_state == _BLEND_IRRECONCILABLE:
        return EndorsedRange(state="irreconcilable")
    if mid <= 0:
        return EndorsedRange(state="unavailable")
    return EndorsedRange(state="endorsed",
                         low=float(_g(fv, "fair_value_low", 0.0) or 0.0),
                         mid=float(mid),
                         high=float(_g(fv, "fair_value_high", 0.0) or 0.0))


def _mechanical_conditions(endorsed: EndorsedRange, current_price: Optional[float],
                           migration: Optional[dict]) -> list:
    """Deterministic, falsifiable conditions from the endorsed range + migration."""
    out: list = []
    cp = None
    if isinstance(current_price, (int, float)) and not isinstance(current_price, bool):
        cp = float(current_price)
    if endorsed.state == "endorsed" and cp is not None:
        out.append(MechanicalCondition(
            id=COND_PRICE_ABOVE_RANGE, threshold=endorsed.high, current=cp,
            met=(endorsed.high is not None and cp > endorsed.high),
            basis="endorsed_range"))
        out.append(MechanicalCondition(
            id=COND_PRICE_BELOW_RANGE, threshold=endorsed.low, current=cp,
            met=(endorsed.low is not None and cp < endorsed.low),
            basis="endorsed_range"))
    if isinstance(migration, dict):
        out.append(MechanicalCondition(
            id=COND_ANALYST_POOL_DETERIORATING, threshold=None, current=None,
            met=bool(migration.get("deteriorating")),
            basis="migration_readout"))
    return out


# ---------------------------------------------------------------------------
# Public assembler (pure — no I/O, no anchor math)
# ---------------------------------------------------------------------------


def build_valuation_diagnosis(fv, *, migration: Optional[dict] = None,
                              current_price: Optional[float] = None) -> ValuationDiagnosis:
    """Assemble a :class:`ValuationDiagnosis` from an ``AppFairValue`` + migration.

    Pure: reads only fields already on ``fv`` (duck-typed via ``getattr`` — tolerant
    of test stand-ins) and the optional migration readout dict. Never raises; never
    computes a fair value or fetches. Returns a fully deterministic object.
    """
    if fv is None:
        return ValuationDiagnosis()

    blend_state = str(_g(fv, "blend_state", "") or "")
    confidence = str(_g(fv, "confidence", "low") or "low")
    consistency = _anchor_consistency(fv)
    endorsed = _endorsed_range(fv)
    try:
        upside = float(_g(fv, "upside_pct", 0.0) or 0.0)
    except (TypeError, ValueError):
        upside = 0.0

    role = classify_valuation_role(confidence, consistency.state, upside, blend_state)

    return ValuationDiagnosis(
        ticker=str(_g(fv, "ticker", "") or ""),
        company_type=str(_g(fv, "company_type", "") or ""),
        applicable_methods=list(_g(fv, "methods_used", []) or []),
        rejected_methods=_rejected_methods(fv),
        anchor_consistency=consistency,
        endorsed_range=endorsed,
        confidence=confidence,
        upside_pct=upside,
        valuation_role=role,
        peer_match_quality=str(_g(fv, "peer_match_quality", "") or ""),
        peer_match_reason=str(_g(fv, "peer_match_reason", "") or ""),
        what_would_change=WhatWouldChange(
            mechanical=_mechanical_conditions(endorsed, current_price, migration),
            narrative_catalysts=[], narrative_pending=True),
        reverse_dcf=ReverseDCFSlot(),  # Phase-8-pending (A4)
        caveats=list(_g(fv, "caveats", []) or []),
        computed_at=str(_g(fv, "computed_at", "") or ""),
    )
