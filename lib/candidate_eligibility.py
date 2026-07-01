"""lib/candidate_eligibility.py — Phase 8B deterministic candidate eligibility gate.

The LLM-FREE numeric-firewall enabler that runs BEFORE CandidateScreeningAgent's
LLM stage. It classifies a single candidate (one ``OpportunityCard`` + its matching
``CandidateSignal``) into a four-state eligibility verdict per horizon::

    eligible    -> may become primary / secondary / watch
    conditional -> may become watch only (never primary)
    ineligible  -> rejected (known-bad)
    unknown     -> rejected (cannot certify a required gate)

Design rules (mirrors the prior deterministic enablers — constituent_rs,
FragilityReading.offense_defense):

* **Numeric firewall.** This module computes deterministic eligibility ONLY. No
  LLM, no probabilities, no fabricated values. Missing data maps to the explicit
  ``unknown`` state — NEVER to a silent pass ("never default to pass" invariant).
* **Read-only.** It READS ``OpportunityCard`` (lib.opportunity_ranker) and
  ``CandidateSignal`` (lib.signal_engine) fields and never mutates them. Inputs may
  be the real dataclasses OR plain dicts (tolerated via ``_field``).
* **Stdlib only at module load.** NO ``lib.reliability``, NO
  ``lib.llm_orchestrator``, NO network. Importable with zero heavy side effects.

Two tiers of gates feed a fixed aggregation precedence (see ``compute_eligibility``):

    HARD gates (may produce ineligible): thesis, eps, valuation, event
    SOFT gates (never ineligible; pass / conditional / unknown): liquidity, distribution

Each gate maps already-computed deterministic fields into one of
``pass | conditional | fail | unknown`` plus a reason code from the frozen
vocabulary below. The gates are intentionally proxy gates where no first-class
field exists (liquidity, distribution) — documented per gate.
"""

from __future__ import annotations

import numbers
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# ===========================================================================
# Reason-code vocabulary (frozen named constants — never emit ad-hoc strings)
# ===========================================================================

# Liquidity (SOFT gate) -----------------------------------------------------
LIQUIDITY_FUNNEL_VERIFIED = "LIQUIDITY_FUNNEL_VERIFIED"   # funnel liquidity filter satisfied at generation
LIQUIDITY_UNVERIFIED_ALT = "LIQUIDITY_UNVERIFIED_ALT"     # ALT_SIGNAL — bypassed the funnel liquidity filter
LIQUIDITY_UNKNOWN = "LIQUIDITY_UNKNOWN"                   # candidate_type missing -> provenance unknown

# Thesis (HARD gate) --------------------------------------------------------
THESIS_AVOID_CHASING = "THESIS_AVOID_CHASING"            # status_by_horizon == "Avoid Chasing"
THESIS_RISK_OVERLAY_FAILED = "THESIS_RISK_OVERLAY_FAILED"  # a "risk_overlay_failed" blocker present
THESIS_STATUS_UNKNOWN = "THESIS_STATUS_UNKNOWN"          # status_by_horizon[horizon] is None (not enriched)

# EPS revision (HARD gate) --------------------------------------------------
EPS_DETERIORATING = "EPS_DETERIORATING"                  # eps_revision_direction == "deteriorating"
EPS_UNKNOWN = "EPS_UNKNOWN"                              # eps unknown / signal absent

# Valuation (HARD gate) -----------------------------------------------------
VALUATION_PROHIBITED = "VALUATION_PROHIBITED"            # percentile >= _VALUATION_PROHIBITED_PCT
VALUATION_ELEVATED = "VALUATION_ELEVATED"               # _ELEVATED <= percentile < _PROHIBITED
VALUATION_UNKNOWN = "VALUATION_UNKNOWN"                 # percentile missing / defaulted (provenance fixture)

# Distribution (SOFT gate; proxy) -------------------------------------------
DISTRIBUTION_PROXY_AVOID = "DISTRIBUTION_PROXY_AVOID"     # entry_quality_label == "avoid"
DISTRIBUTION_PROXY_EXTENDED = "DISTRIBUTION_PROXY_EXTENDED"  # entry_quality_label == "extended"
DISTRIBUTION_UNKNOWN = "DISTRIBUTION_UNKNOWN"            # entry_quality_label missing / signal absent

# Event / earnings proximity (HARD gate) ------------------------------------
EVENT_EARNINGS_IMMINENT = "EVENT_EARNINGS_IMMINENT"      # short: days_to_earnings <= _IMMINENT
EVENT_EARNINGS_WITHIN_WINDOW = "EVENT_EARNINGS_WITHIN_WINDOW"  # short: _IMMINENT < d2e <= _WINDOW
EVENT_EARNINGS_PENDING_MID = "EVENT_EARNINGS_PENDING_MID"  # mid: days_to_earnings <= _IMMINENT
EVENT_EARNINGS_DATE_UNKNOWN = "EVENT_EARNINGS_DATE_UNKNOWN"  # short: days_to_earnings is None


# ===========================================================================
# Threshold constants (named, tunable, documented)
# ===========================================================================

# Grounds to lib.opportunity_ranker._VALUATION_HIGH_PCT (== 0.70). NOTE: the prompt
# located this in signal_engine; it actually lives in opportunity_ranker, value 0.70.
_VALUATION_ELEVATED_PCT = 0.70
# NEW prohibited-band ceiling. CALIBRATION DEBT: 0.85 is an unvalidated first guess
# with no upstream anchor — revisit once the agent phase produces real slate outcomes.
_VALUATION_PROHIBITED_PCT = 0.85
# Earnings imminence (calendar days-until from days_to_earnings).
_EARNINGS_IMMINENT_DAYS = 2
# Grounds to the existing earnings_within_window blocker (<= 7 days) in opportunity_ranker.
_EARNINGS_WINDOW_DAYS = 7


# Horizons handled by this gate.
_HORIZONS = ("short", "mid", "long")

# Status strings + blocker code mirrored LOCALLY (kept verbatim to avoid importing
# opportunity_ranker — stdlib-only at module load). Confirmed against
# opportunity_ranker.STATUS_AVOID ("Avoid Chasing") and _CRITICAL_GATE_CODES.
_STATUS_AVOID = "Avoid Chasing"
_RISK_OVERLAY_FAILED_CODE = "risk_overlay_failed"

# Gate tiers.
_HARD = "hard"
_SOFT = "soft"


# ===========================================================================
# Verdict dataclass (frozen, deterministic; reason tuples always sorted)
# ===========================================================================

@dataclass(frozen=True)
class EligibilityVerdict:
    """The deterministic four-state eligibility verdict for one (ticker, horizon).

    ``blockers`` / ``conditions`` / ``unknowns`` are sorted tuples of reason codes
    from the frozen vocabulary above, collected from ALL gates (not just the
    dominant one) so the reason lists are complete and byte-stable.
    """

    ticker: str
    horizon: str          # "short" | "mid" | "long"
    strategy_type: str    # card.setup passthrough (for the agent's per-strategy logic)
    status: str           # "eligible" | "conditional" | "ineligible" | "unknown"
    blockers: tuple       # reason codes from gates whose state == "fail" (sorted)
    conditions: tuple     # reason codes from gates whose state == "conditional" (sorted)
    unknowns: tuple       # reason codes from gates whose state == "unknown" (sorted)
    data_quality: str     # "live" | "partial" | "degraded"
    as_of: str            # ISO date (YYYY-MM-DD)


# ===========================================================================
# Field access (card / signal may be a dataclass OR a plain dict)
# ===========================================================================

def _field(obj, name: str, default=None):
    """Read ``name`` off a dataclass/object (getattr) or a dict (.get).

    Returns ``default`` when the attribute/key is absent. A present-but-None value
    is returned as None (NOT coerced to the default) so callers can distinguish
    "field set to None" from "field absent" where it matters (e.g. candidate_type).
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _to_float(value) -> Optional[float]:
    """Coerce to float; bool/None/non-numeric -> None (so callers gate on None)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN -> None


def _to_int(value) -> Optional[int]:
    """Coerce to int; bool/None/non-numeric -> None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ===========================================================================
# Valuation provenance (distinguish a REAL 0.5 read from a defaulted 0.5)
# ===========================================================================

def _locate_fundamental(signal):
    """Find a FundamentalResult-ish object carrying valuation provenance.

    Order: ``signal.track_a.layer3_fundamental`` (the funnel path), then a flat
    ``signal.fundamental`` / dict ``fundamental`` / ``layer3_fundamental``. Returns
    None when none is reachable (e.g. a directly-constructed CandidateSignal in a
    test, or an ALT_SIGNAL whose track_a is None).
    """
    track_a = _field(signal, "track_a", None)
    if track_a is not None:
        fund = _field(track_a, "layer3_fundamental", None)
        if fund is not None:
            return fund
    for key in ("fundamental", "layer3_fundamental"):
        fund = _field(signal, key, None)
        if fund is not None:
            return fund
    return None


def _has_field(obj, name: str) -> bool:
    """True if ``name`` is a present attribute/key on ``obj`` (dataclass or dict)."""
    if obj is None:
        return False
    if isinstance(obj, dict):
        return name in obj
    return hasattr(obj, name)


def _forward_pe_is_usable(value) -> bool:
    """A forward P/E is usable only if it is a real, positive number.

    Returns False for None, non-numeric, ``bool`` (bool is an int subclass — a
    True/False forward_pe is a data error, NOT 1/0), or any value <= 0. This mirrors
    the EXACT conditions under which ``signal_engine._valuation_percentile`` defaults
    the percentile to 0.5 (invalid / non-positive / missing forwardPE) — the case
    ``fetch_fundamental`` still stamps ``data_source["valuation"]="live"`` for.
    """
    if value is None or isinstance(value, bool):
        return False
    if not isinstance(value, numbers.Real):
        return False
    try:
        return float(value) > 0.0
    except (TypeError, ValueError):
        return False


def _valuation_missing(signal) -> bool:
    """True on any POSITIVE "not a certified-live valuation" signal.

    The numeric value 0.5 alone is ambiguous (a real "median" read vs a default), so
    this never trusts the value — it inspects provenance and the underlying
    forward_pe. Returns True when a fundamental is reachable AND either:
      * its ``data_source["valuation"]`` reads ``"fixture"`` or is absent/None
        (no certified-live valuation), OR
      * its ``forward_pe`` is present but UNUSABLE (None / non-numeric / bool / <= 0).
        This closes the firewall leak: ``fetch_fundamental`` marks valuation "live"
        whenever ``info`` is truthy even when ``forwardPE`` is invalid, and
        ``_valuation_percentile`` then returns a defaulted 0.5 — which must NOT be
        read as a real valuation.
    Returns False when no fundamental is reachable -> the percentile is treated as a
    REAL read (the bare-percentile path: a directly-constructed signal with no
    provenance and no reachable forward_pe stays a real read; test #5 relies on this).
    """
    fund = _locate_fundamental(signal)
    if fund is None:
        return False
    # Provenance must positively certify a LIVE valuation; fixture / absent -> missing.
    ds = _field(fund, "data_source", None)
    prov = ds.get("valuation") if isinstance(ds, dict) else None
    if prov in ("fixture", None):
        return True
    # Provenance says "live" but the forward P/E it was derived from is unusable ->
    # the percentile was defaulted, so the valuation is not real (firewall guard).
    if _has_field(fund, "forward_pe") and not _forward_pe_is_usable(
            _field(fund, "forward_pe", None)):
        return True
    return False


# ===========================================================================
# Gates — each returns (state, reason_code|None). state in pass/conditional/fail/unknown.
# ===========================================================================

def _gate_liquidity(card):
    """SOFT, horizon-uniform. PROXY: a "pass" means the funnel liquidity filter was
    satisfied at GENERATION (market-cap + $ADV in passes_layer1), NOT a fresh
    liquidity re-read. Never emits fail."""
    ctype = _field(card, "candidate_type", None)
    if ctype in ("FUNNEL", "BOTH"):
        return ("pass", LIQUIDITY_FUNNEL_VERIFIED)
    if ctype == "ALT_SIGNAL":
        return ("conditional", LIQUIDITY_UNVERIFIED_ALT)
    return ("unknown", LIQUIDITY_UNKNOWN)


def _gate_thesis(card, horizon: str):
    """HARD, per-horizon via status_by_horizon[horizon].

    A "risk_overlay_failed" blocker code fails all horizons (defensive: the current
    ranker surfaces a risk-overlay failure as the "Avoid Chasing" status rather than
    this blocker code, but we honor both)."""
    # DEAD-TODAY / FORWARD-COMPATIBLE branch: the current opportunity_ranker never
    # attaches a Blocker with code "risk_overlay_failed" to a card — a risk-overlay
    # failure surfaces as status_by_horizon[h] == "Avoid Chasing" (handled below).
    # This branch is kept as a defensive guard in case the ranker later emits that
    # code; its test feeds a manually-constructed Blocker (no production card hits it).
    for b in (_field(card, "blockers", None) or []):
        if _field(b, "code", "") == _RISK_OVERLAY_FAILED_CODE:
            return ("fail", THESIS_RISK_OVERLAY_FAILED)
    sbh = _field(card, "status_by_horizon", None) or {}
    status = _field(sbh, horizon, None)
    if status == _STATUS_AVOID:
        return ("fail", THESIS_AVOID_CHASING)
    if status is None:
        return ("unknown", THESIS_STATUS_UNKNOWN)
    return ("pass", None)


def _gate_eps(signal, horizon: str):
    """HARD, horizon-asymmetric. Deteriorating EPS is a caution (conditional) for
    SHORT but a hard fail for MID/LONG. Unknown / absent signal -> unknown."""
    if signal is None:
        return ("unknown", EPS_UNKNOWN)
    eps = _field(signal, "eps_revision_direction", "unknown")
    if eps == "deteriorating":
        if horizon == "short":
            return ("conditional", EPS_DETERIORATING)
        return ("fail", EPS_DETERIORATING)
    if eps == "unknown" or eps is None:
        return ("unknown", EPS_UNKNOWN)
    return ("pass", None)  # inflecting_up / improving / stable


def _gate_valuation(signal, horizon: str):
    """HARD, horizon-asymmetric. Requires a REAL percentile (see _valuation_missing
    — a defaulted 0.5 is unknown, not a pass). Prohibited band fails MID/LONG (only
    conditional for SHORT); elevated band is conditional for MID/LONG only."""
    if signal is None or _valuation_missing(signal):
        return ("unknown", VALUATION_UNKNOWN)
    pct = _to_float(_field(signal, "valuation_percentile", None))
    if pct is None:
        return ("unknown", VALUATION_UNKNOWN)
    if pct >= _VALUATION_PROHIBITED_PCT:
        if horizon == "short":
            return ("conditional", VALUATION_PROHIBITED)
        return ("fail", VALUATION_PROHIBITED)
    if pct >= _VALUATION_ELEVATED_PCT:
        if horizon == "short":
            return ("pass", None)
        return ("conditional", VALUATION_ELEVATED)
    return ("pass", None)


def _gate_distribution(signal):
    """SOFT, horizon-uniform. PROXY: there is NO per-ticker distribution-day field
    (that signal is market-wide in MarketStructure). A "pass" means "no proxy
    distribution flag", NOT a confirmed absence of distribution. Never emits fail."""
    if signal is None:
        return ("unknown", DISTRIBUTION_UNKNOWN)
    label = _field(signal, "entry_quality_label", None)
    if label == "avoid":
        return ("conditional", DISTRIBUTION_PROXY_AVOID)
    if label == "extended":
        return ("conditional", DISTRIBUTION_PROXY_EXTENDED)
    if label is None:
        return ("unknown", DISTRIBUTION_UNKNOWN)
    return ("pass", None)


def _gate_event(card, horizon: str):
    """HARD, horizon-asymmetric — THE canonical horizon gate. A single earnings
    print is noise over 6-18 months, so LONG always passes.

    DELIBERATE EXCLUSION: days_to_fomc / days_to_cpi are NOT consulted. They are
    market-wide and identical across every candidate in a theme, so they cannot
    differentiate A vs B in the relative comparison — that is MarketStructure's lane.
    """
    if horizon == "long":
        return ("pass", None)
    d2e = _field(card, "days_to_earnings", None)
    if d2e is None:
        if horizon == "short":
            return ("unknown", EVENT_EARNINGS_DATE_UNKNOWN)
        return ("pass", None)  # mid: earnings date unknown is not a hard gate
    d2e = _to_int(d2e)
    if d2e is None:  # non-int garbage in the field -> treat the date as unknown
        if horizon == "short":
            return ("unknown", EVENT_EARNINGS_DATE_UNKNOWN)
        return ("pass", None)
    if d2e <= _EARNINGS_IMMINENT_DAYS:
        if horizon == "short":
            return ("conditional", EVENT_EARNINGS_IMMINENT)
        return ("conditional", EVENT_EARNINGS_PENDING_MID)
    if d2e <= _EARNINGS_WINDOW_DAYS:
        if horizon == "short":
            return ("conditional", EVENT_EARNINGS_WITHIN_WINDOW)
        return ("pass", None)  # mid: outside the imminent band -> not blocking
    return ("pass", None)


# ===========================================================================
# Public API
# ===========================================================================

def compute_eligibility(card, signal=None, *, horizon: str,
                        as_of: Optional[str] = None) -> EligibilityVerdict:
    """Classify one (card, signal) into a four-state ``EligibilityVerdict`` for one
    horizon. Deterministic, LLM-free, network-free; tolerates dataclass-or-dict
    inputs. Fields that live only on ``signal`` (eps / valuation / entry quality)
    evaluate to their UNKNOWN state when ``signal`` is None — never to a pass.

    Aggregation precedence (the core invariant, discriminable by tests):
      1. any HARD gate fail        -> "ineligible"
      2. elif any HARD gate unknown -> "unknown" (a required gate could not certify)
      3. elif any gate conditional  -> "conditional" (hard OR soft)
      4. elif any SOFT gate unknown -> "conditional" (soft uncertainty is a caveat, watchable)
      5. else                       -> "eligible"
    """
    if horizon not in _HORIZONS:
        raise ValueError(
            f"compute_eligibility: horizon must be one of {_HORIZONS}, got {horizon!r}."
        )
    as_of = as_of or _today_iso()
    strategy_type = str(_field(card, "setup", "") or "")
    ticker = str(_field(card, "ticker", "") or "")

    # (tier, state, reason_code) for every gate.
    results = [
        (_HARD,) + _gate_thesis(card, horizon),
        (_HARD,) + _gate_eps(signal, horizon),
        (_HARD,) + _gate_valuation(signal, horizon),
        (_HARD,) + _gate_event(card, horizon),
        (_SOFT,) + _gate_liquidity(card),
        (_SOFT,) + _gate_distribution(signal),
    ]

    # Complete reason lists from ALL gates (sorted, de-duplicated, byte-stable).
    blockers = tuple(sorted({c for _t, s, c in results if s == "fail" and c}))
    conditions = tuple(sorted({c for _t, s, c in results if s == "conditional" and c}))
    unknowns = tuple(sorted({c for _t, s, c in results if s == "unknown" and c}))

    hard_states = [s for t, s, _c in results if t == _HARD]
    soft_states = [s for t, s, _c in results if t == _SOFT]

    if any(s == "fail" for s in hard_states):
        status = "ineligible"
    elif any(s == "unknown" for s in hard_states):
        status = "unknown"
    elif any(s == "conditional" for _t, s, _c in results):
        status = "conditional"
    elif any(s == "unknown" for s in soft_states):
        status = "conditional"
    else:
        status = "eligible"

    # data_quality is independent of the gate verdict — it describes the input data.
    rs_degraded = bool(_field(card, "rs_degraded", False))
    enriched = bool(_field(card, "enriched", False))
    if rs_degraded or not enriched:
        data_quality = "degraded"
    elif unknowns:
        data_quality = "partial"
    else:
        data_quality = "live"

    return EligibilityVerdict(
        ticker=ticker,
        horizon=horizon,
        strategy_type=strategy_type,
        status=status,
        blockers=blockers,
        conditions=conditions,
        unknowns=unknowns,
        data_quality=data_quality,
        as_of=as_of,
    )


def eligibility_by_horizon(card, signal=None, *,
                           as_of: Optional[str] = None) -> dict:
    """Return ``{"short": EligibilityVerdict, "mid": ..., "long": ...}`` — one
    verdict per horizon over the SAME (card, signal) and a single ``as_of`` stamp."""
    as_of = as_of or _today_iso()
    return {
        h: compute_eligibility(card, signal, horizon=h, as_of=as_of)
        for h in _HORIZONS
    }
