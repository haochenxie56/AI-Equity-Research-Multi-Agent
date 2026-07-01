"""
lib/agents/candidate_screening_agent.py

Phase 8B — CandidateScreeningAgent, production implementation.

The SIXTH production agent on the Phase 8A framework, and the CONSUMER of the
already-merged deterministic eligibility gate (``lib.candidate_eligibility``).

================================================================================
STRATEGY IDENTITY — v1 is ONE fixed strategy: MOMENTUM / RS-GAP.
================================================================================
The PRIMARY ranking key is the per-horizon relative-strength (RS) composite gap
WITHIN a single theme. Future strategies (leader play, high-beta elasticity) will
be SEPARATE agents (e.g. LeaderScreeningAgent), NOT parameters of this one. There
is deliberately NO pluggable strategy interface in v1.

================================================================================
WHAT THIS AGENT IS / IS NOT.
================================================================================
IS: a PER-THEME RELATIVE screener. For ONE active theme it takes the theme's
candidates, runs each through the deterministic eligibility gate, builds a
deterministic comparison table over the ELIGIBLE set, computes a deterministic
frontrunner per horizon, decides ``no_clear_winner`` in CODE, and asks the LLM
ONLY to explain which differences are decisive and translate trade-offs into
horizon fit + invalidation conditions. Output answers "which one or two tickers
are worth ADVANCING to the next trade-construction step."

IS NOT: a cross-theme ranker (PM's job), an entry-timing engine (TechnicalEntry),
a money-flow validator (ticker-level MoneyFlow — a future Stage-2 pass on the
primary/secondary only), or a deep-conviction fundamental agent (StockResearch).
It does NOT pick the market's best name; it picks a THEME's best name. The tone is
"LITE is the strongest candidate to advance to short-term trade construction;
final entry depends on money-flow, technical entry, and portfolio risk checks" —
NEVER "buy LITE now."

================================================================================
NUMERIC FIREWALL.
================================================================================
CODE computes EVERY number: ranks, RS gaps, tiers, the frontrunner, the
``no_clear_winner`` decision, the confidences, and the ``signal_basis``. The LLM
emits NO number, does NOT choose the primary (code did), and does NOT override
``no_clear_winner``. Missing dimension data maps to an explicit
``"unavailable"`` / ``"unknown"`` marker — never a fabricated value, never a
silent pass. The comparison table + slate skeleton + confidences are put on the
AgentOutput ``supporting_data`` BEFORE the LLM runs, so they persist verbatim via
``append_agent_output`` (no second file).

================================================================================
DOWN-SCOPED DIMENSIONS (no backing field at screening time — PREFLIGHT).
================================================================================
* ``short_crowding``   — no short-interest / days-to-cover / % float field is
  reachable on OpportunityCard or CandidateSignal -> "unavailable", EXCLUDED from
  the frontrunner key (never fabricated).
* ``options_structure`` — GEX / call-put-wall proximity is not reachable per
  ticker at screening -> "unavailable", EXCLUDED (this is Stage-2 MoneyFlow's lane).
* ``market_cap`` for tradability — reachable only on the v1 ``FundamentalSignals``
  shim, which is generally absent in production, so ``market_cap_tier`` is usually
  "unknown"; it is read opportunistically when a ``market_cap`` attribute IS present.
  The reachable tradability signal is ``liquidity_tier`` from ``candidate_type``
  (FUNNEL/BOTH -> ample; ALT_SIGNAL -> marginal — the penny-stock guard).

IMPORT DISCIPLINE: only stdlib + the local eligibility gate's PUBLIC constants are
touched at module import indirectly; every ``lib.reliability`` /
``lib.agent_framework`` / ``lib.candidate_eligibility`` / ``lib.theme_transmission``
symbol is imported LAZILY inside the function that needs it (mirrors the five
shipped agents). Importing this module triggers NO heavy reliability __init__ and
NO network.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # annotations only — never imported at runtime here
    from lib.agent_framework.agent_output import AgentOutput


_log = logging.getLogger("agents.candidate_screening_agent")


# ===========================================================================
# Calibration constants (named + documented as calibration debt)
# ===========================================================================

# Minimum lead the frontrunner must hold over the runner-up on the PRIMARY key
# (the per-horizon RS composite, a 0..1 score) to call a decisive winner. Below
# this the code sets no_clear_winner. CALIBRATION DEBT: 0.08 is a first guess with
# no upstream anchor — revisit once real slate outcomes exist.
_RS_GAP_DECISIVE_PCT = 0.08

# Market-cap "ample" ceiling for the tradability credibility layer. Leader-vs-barely
# ABOVE the $2B funnel floor already enforced at candidate generation. CALIBRATION
# DEBT: $10B is an unvalidated first guess; market_cap is usually unreachable at
# screening anyway (-> tier "unknown"). Revisit if a live market_cap channel lands.
_MCAP_AMPLE = 10_000_000_000.0

# rs vol_ratio strictly above this -> volume-confirmed leg. Matches the existing
# lib.relative_strength surge cutoff (1.2). CALIBRATION DEBT only in that it is
# duplicated here to keep the module stdlib-only at import.
_VOL_CONFIRM_RATIO = 1.2

# Coverage floor below which the theme read is "degraded_insufficient" regardless
# of any frontrunner. CALIBRATION DEBT: 0.34 (~one third of the theme usable).
_COVERAGE_MIN = 0.34

# Long-horizon rationale — this agent is a short/mid tactical screener; deep
# long-horizon conviction defers to StockResearch / ValuationDebate.
_LONG_RATIONALE = (
    "Relative-strength candidate screening is a short-to-mid tactical read; "
    "long-horizon conviction defers to StockResearch / ValuationDebate."
)

# The horizons this agent actually screens (long is not_applicable).
_SCREEN_HORIZONS = ("short", "mid")


# ===========================================================================
# Named label / marker vocabulary (never emit ad-hoc strings)
# ===========================================================================

# Dimension availability markers.
_UNAVAILABLE = "unavailable"   # NO backing field exists at all (down-scoped dim)
_UNKNOWN = "unknown"           # a field exists but is missing/degraded for this ticker
_KNOWN = "known"

# Tradability tiers.
_TIER_AMPLE = "ample"
_TIER_MARGINAL = "marginal"
_TIER_UNKNOWN = "unknown"

# Volume-confirmation labels.
_VOL_CONFIRMED = "confirmed"
_VOL_UNCONFIRMED = "unconfirmed"
_VOL_DIVERGENT = "divergent"

# Catalyst-proximity labels.
_CAT_IMMINENT = "imminent"
_CAT_NEAR = "near"
_CAT_FAR = "far"
_CAT_UNKNOWN = "unknown"

# signal_basis (three-way, matches the shipped agents' neutral-vs-degraded split).
_BASIS_PRESENT = "signal_present"
_BASIS_NO_WINNER = "no_clear_winner"
_BASIS_DEGRADED = "degraded_insufficient"

# no_trade_reason codes.
_NT_EMPTY = "no_eligible_candidates"
_NT_THIN_GAP = "rs_gap_below_decisive"
_NT_CAPPED = "frontrunner_quality_capped_without_decisive_lead"

# Long-horizon status token.
_LONG_STATUS = "not_applicable"

# Strategy identity token (recorded in supporting_data + TR2).
_STRATEGY = "momentum_rs_gap"


def end_of_today_iso() -> str:
    """Today at 23:59:59 UTC as an ISO datetime string.

    Defined locally so this module pulls in no ``lib.agent_framework`` dependency
    at import time (mirrors ``sector_rotation_agent.end_of_today_iso``).
    """
    now = datetime.now(timezone.utc)
    return now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()


# ===========================================================================
# Field readers (card / signal may be a dataclass OR a dict fixture)
# ===========================================================================

def _field(obj, name: str, default=None):
    """Read ``name`` off a dataclass/object (getattr) or a dict (.get)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _num(value, default: Optional[float] = None) -> Optional[float]:
    """Coerce to float; bool/None/non-numeric/NaN -> ``default``."""
    if value is None or isinstance(value, bool):
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if f == f else default


def _card_theme(card) -> str:
    return str(_field(card, "theme", "") or "")


def _card_ticker(card) -> str:
    return str(_field(card, "ticker", "") or "")


# ===========================================================================
# Deterministic per-ticker comparison profile
# ===========================================================================

@dataclass(frozen=True)
class CandidateProfile:
    """One ELIGIBLE-set comparison profile (fully deterministic, LLM-free).

    A-dimensions keep the cleaned gap material (rs composites + raw excess, the
    valuation percentile) so the LLM can judge MAGNITUDE from evidence — but every
    A-dim also carries ``quality_capped`` so a thin-float ticker's large gap is
    never read as genuine leadership. B-dimensions carry only a category label.
    Down-scoped dims carry an explicit availability marker, never a value.
    """

    ticker: str
    # Per-horizon eligibility status (from the gate).
    short_status: str
    mid_status: str
    long_status: str
    data_quality: str
    # A1 — relative strength (PRIMARY momentum key). Composites are the ranking
    # material; the raw per-window excess lives in ``rs_excess`` (evidence only).
    rs_short: float
    rs_mid: float
    rs_available: bool          # non-degraded AND non-stale RS
    rs_excess: dict             # raw vs-benchmark excess (evidence, NOT LLM prose)
    # A2 — valuation elasticity (lower percentile = more margin). ``valuation_state``
    # is _UNKNOWN when provenance cannot certify a real read (never imputed).
    valuation_percentile: Optional[float]
    valuation_state: str        # _KNOWN | _UNKNOWN
    # A3 — short crowding: NO backing field -> _UNAVAILABLE for all (excluded from key).
    short_crowding_state: str
    # B4 — theme role (from the transmission seed map; _UNKNOWN if unseeded).
    theme_role: str
    # B5 — volume confirmation.
    volume_confirmation: str
    # B6 — options structure: not reachable at screening -> _UNAVAILABLE (Stage-2 lane).
    options_structure_state: str
    # B7 — catalyst proximity (bucketed from days_to_earnings).
    catalyst_proximity: str
    # B8 / cross-cutting tradability credibility layer.
    market_cap_tier: str
    liquidity_tier: str
    quality_capped: bool

    def to_dict(self) -> dict:
        return asdict(self)

    def rs_for(self, horizon: str) -> float:
        return self.rs_short if horizon == "short" else self.rs_mid

    def status_for(self, horizon: str) -> str:
        return {"short": self.short_status, "mid": self.mid_status,
                "long": self.long_status}[horizon]


@dataclass(frozen=True)
class CandidateSlate:
    """The deterministic slate SKELETON for one (theme, horizon).

    The machine-readable primary/secondary/watch/rejected is CODE-decided; the LLM
    only explains WHY the code's frontrunner wins. ``rejected`` is a tuple of
    ``{ticker, status, reasons}`` dicts carrying the gate's reason codes.
    """

    theme_id: str
    horizon: str
    primary: Optional[str]
    secondary: tuple
    watch: tuple
    rejected: tuple
    no_clear_winner: bool
    no_trade_reason: Optional[str]
    signal_basis: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Dimension computations (each pure, deterministic, from a named field)
# ---------------------------------------------------------------------------

def _rs_composite(card, horizon: str) -> float:
    """The per-horizon RS composite off ``card.rs`` (neutral 0.5 when absent)."""
    rs = _field(card, "rs", None) or {}
    key = "rs_short" if horizon == "short" else "rs_mid"
    v = _num(_field(rs, key, None), None)
    if v is None:
        v = _num(_field(rs, "rs_composite", None), 0.5)
    return float(v if v is not None else 0.5)


def _rs_is_available(card) -> bool:
    """RS is usable only when it is neither a cache MISS (rs_degraded) nor a
    silent stale cache-hit (rs_stale)."""
    return not bool(_field(card, "rs_degraded", False)) and not bool(
        _field(card, "rs_stale", False))


def _rs_excess(card) -> dict:
    """Raw per-window excess-vs-benchmark values — EVIDENCE ONLY (never LLM prose)."""
    rs = _field(card, "rs", None) or {}
    keys = ("ret_5d_vs_spy", "ret_1m_vs_spy", "ret_3m_vs_spy", "ret_6m_vs_spy",
            "ret_5d_vs_qqq", "ret_1m_vs_qqq")
    return {k: _num(_field(rs, k, None), None) for k in keys}


def _volume_confirmation(card) -> str:
    """confirmed / unconfirmed / divergent from rs vol_ratio + above_sma flags.

    * confirmed  — a volume surge (vol_ratio > _VOL_CONFIRM_RATIO) AND price above
      both SMA20 and SMA50 (a clean, volume-backed advance).
    * divergent  — a volume surge but price is NOT above both SMAs (heavy volume
      into weakness — a distribution/divergence caution).
    * unconfirmed — no volume surge (or vol_ratio missing).
    """
    rs = _field(card, "rs", None) or {}
    vol = _num(_field(rs, "vol_ratio", None), None)
    above20 = _field(rs, "above_sma20", None) is True
    above50 = _field(rs, "above_sma50", None) is True
    if vol is None or vol <= _VOL_CONFIRM_RATIO:
        return _VOL_UNCONFIRMED
    if above20 and above50:
        return _VOL_CONFIRMED
    return _VOL_DIVERGENT


def _catalyst_proximity(card) -> str:
    """imminent / near / far / unknown, bucketed from days_to_earnings using the
    gate's OWN earnings-window constants (kept in lock-step with the gate)."""
    from lib.candidate_eligibility import (
        _EARNINGS_IMMINENT_DAYS,
        _EARNINGS_WINDOW_DAYS,
    )

    d2e = _field(card, "days_to_earnings", None)
    if d2e is None or isinstance(d2e, bool):
        return _CAT_UNKNOWN
    try:
        d = int(d2e)
    except (TypeError, ValueError):
        return _CAT_UNKNOWN
    if d <= _EARNINGS_IMMINENT_DAYS:
        return _CAT_IMMINENT
    if d <= _EARNINGS_WINDOW_DAYS:
        return _CAT_NEAR
    return _CAT_FAR


def _theme_role(theme_key: str, ticker: str) -> str:
    """The seed role of the ticker within the theme's transmission chain."""
    try:
        from lib.theme_transmission import get_ticker_role

        return str(get_ticker_role(theme_key, ticker) or _UNKNOWN)
    except Exception:  # noqa: BLE001 — fail-closed to unknown, never fabricate
        return _UNKNOWN


def _market_cap_tier(card, signal) -> str:
    """ample / marginal / unknown from any reachable market_cap.

    market_cap is generally NOT reachable at screening (only the v1
    FundamentalSignals shim carries it, usually absent), so this is usually
    ``unknown``. Read opportunistically from ``signal.market_cap`` /
    ``signal.fundamental.market_cap`` / ``card.market_cap`` when present, for
    forward-compat + testability. ``unknown`` NEVER caps (only positive marginal
    evidence caps)."""
    mc = _num(_field(signal, "market_cap", None), None)
    if mc is None:
        fund = _field(signal, "fundamental", None)
        mc = _num(_field(fund, "market_cap", None), None)
    if mc is None:
        mc = _num(_field(card, "market_cap", None), None)
    if mc is None:
        return _TIER_UNKNOWN
    return _TIER_AMPLE if mc >= _MCAP_AMPLE else _TIER_MARGINAL


def _liquidity_tier(card) -> str:
    """ample / marginal / unknown from candidate_type (PROXY — documented).

    FUNNEL / BOTH passed the funnel's market-cap + $ADV floor at generation
    (ample). ALT_SIGNAL entered via the Track-B standalone trigger and BYPASSED
    that floor -> marginal (the reachable penny-stock guard). Missing -> unknown."""
    ctype = _field(card, "candidate_type", None)
    if ctype in ("FUNNEL", "BOTH"):
        return _TIER_AMPLE
    if ctype == "ALT_SIGNAL":
        return _TIER_MARGINAL
    return _TIER_UNKNOWN


def _valuation_state(signal) -> tuple:
    """(percentile|None, _KNOWN|_UNKNOWN) — respects the gate's provenance rule.

    Uses the gate's OWN ``_valuation_missing`` so a DEFAULTED 0.5 (fixture / unusable
    forward P/E) is _UNKNOWN, not a real read. Never imputes a value."""
    if signal is None:
        return (None, _UNKNOWN)
    try:
        from lib.candidate_eligibility import _valuation_missing

        if _valuation_missing(signal):
            return (None, _UNKNOWN)
    except Exception:  # noqa: BLE001 — if the probe fails, degrade to unknown
        return (None, _UNKNOWN)
    pct = _num(_field(signal, "valuation_percentile", None), None)
    if pct is None:
        return (None, _UNKNOWN)
    return (pct, _KNOWN)


def _build_profile(card, signal, theme_key: str, verdicts: dict) -> CandidateProfile:
    """Assemble ONE deterministic CandidateProfile from real card+signal fields."""
    ticker = _card_ticker(card)
    val_pct, val_state = _valuation_state(signal)
    mcap_tier = _market_cap_tier(card, signal)
    liq_tier = _liquidity_tier(card)
    quality_capped = (mcap_tier == _TIER_MARGINAL) or (liq_tier == _TIER_MARGINAL)
    # data_quality: worst across horizons is fine — the gate stamps it per verdict
    # and it is identical across horizons for the same (card, signal).
    dq = verdicts["short"].data_quality
    return CandidateProfile(
        ticker=ticker,
        short_status=verdicts["short"].status,
        mid_status=verdicts["mid"].status,
        long_status=verdicts["long"].status,
        data_quality=dq,
        rs_short=_rs_composite(card, "short"),
        rs_mid=_rs_composite(card, "mid"),
        rs_available=_rs_is_available(card),
        rs_excess=_rs_excess(card),
        valuation_percentile=val_pct,
        valuation_state=val_state,
        short_crowding_state=_UNAVAILABLE,   # no backing field (PREFLIGHT)
        theme_role=_theme_role(theme_key, ticker),
        volume_confirmation=_volume_confirmation(card),
        options_structure_state=_UNAVAILABLE,  # not reachable at screening (Stage-2)
        catalyst_proximity=_catalyst_proximity(card),
        market_cap_tier=mcap_tier,
        liquidity_tier=liq_tier,
        quality_capped=quality_capped,
    )


# ---------------------------------------------------------------------------
# Deterministic ranking + frontrunner + no_clear_winner
# ---------------------------------------------------------------------------

_VOL_RANK = {_VOL_CONFIRMED: 0, _VOL_UNCONFIRMED: 1, _VOL_DIVERGENT: 2}


def _sort_key(p: CandidateProfile, horizon: str) -> tuple:
    """The deterministic momentum ordering key (PRIMARY = RS composite gap).

    Ordered, documented tie-break AFTER the RS composite, using only the AVAILABLE
    dimensions (never short_crowding / options_structure — both _UNAVAILABLE):
      1. RS composite (higher first)
      2. volume_confirmation  (confirmed > unconfirmed > divergent)
      3. valuation elasticity (lower percentile better; _UNKNOWN sorts last)
      4. tradability          (quality_capped False before True)
      5. ticker               (byte-stable final tie-break)
    """
    val = p.valuation_percentile if p.valuation_state == _KNOWN else 1.0
    return (
        -p.rs_for(horizon),
        _VOL_RANK.get(p.volume_confirmation, 1),
        val if val is not None else 1.0,
        1 if p.quality_capped else 0,
        p.ticker,
    )


def _rank_eligible(profiles: list, horizon: str) -> list:
    """Eligible-only profiles ordered by the momentum key for ``horizon``."""
    elig = [p for p in profiles if p.status_for(horizon) == "eligible"]
    return sorted(elig, key=lambda p: _sort_key(p, horizon))


def _frontrunner_decision(ordered: list, horizon: str) -> dict:
    """Deterministic frontrunner + lead + no_clear_winner for ONE horizon.

    ``lead`` is the frontrunner's RS-composite margin over the runner-up (None when
    there is exactly one eligible name — a lone eligible name has no contest)."""
    if not ordered:
        return {"frontrunner": None, "lead": None, "no_clear_winner": True,
                "no_trade_reason": _NT_EMPTY}
    top = ordered[0]
    if len(ordered) == 1:
        lead = None
    else:
        lead = round(top.rs_for(horizon) - ordered[1].rs_for(horizon), 6)

    # CODE decides no_clear_winner; the LLM can NEVER flip it to a pick.
    if lead is not None and lead < _RS_GAP_DECISIVE_PCT:
        return {"frontrunner": top, "lead": lead, "no_clear_winner": True,
                "no_trade_reason": _NT_THIN_GAP}
    # A quality_capped frontrunner without a DECISIVE lead is the penny-stock guard:
    # a lone capped name (lead is None) is also refused. Its cap dilutes credibility.
    if top.quality_capped and (lead is None or lead < _RS_GAP_DECISIVE_PCT):
        return {"frontrunner": top, "lead": lead, "no_clear_winner": True,
                "no_trade_reason": _NT_CAPPED}
    return {"frontrunner": top, "lead": lead, "no_clear_winner": False,
            "no_trade_reason": None}


def _conditional_tickers(profiles: list, horizon: str) -> list:
    return sorted(p.ticker for p in profiles if p.status_for(horizon) == "conditional")


def _rejected_entries(profiles: list, verdict_map: dict, horizon: str) -> list:
    """ineligible + unknown, each with the gate's reason codes (byte-stable)."""
    out = []
    for p in profiles:
        status = p.status_for(horizon)
        if status not in ("ineligible", "unknown"):
            continue
        v = verdict_map[p.ticker][horizon]
        reasons = list(v.blockers) if status == "ineligible" else list(v.unknowns)
        out.append({"ticker": p.ticker, "status": status, "reasons": reasons})
    return sorted(out, key=lambda e: e["ticker"])


def _build_slate(profiles: list, verdict_map: dict, theme_key: str,
                 horizon: str, decision: dict, signal_basis: str) -> CandidateSlate:
    """Assemble the deterministic slate SKELETON for one (theme, horizon)."""
    ordered = _rank_eligible(profiles, horizon)
    elig_tickers = [p.ticker for p in ordered]
    no_clear = decision["no_clear_winner"]
    primary = elig_tickers[0] if (elig_tickers and not no_clear) else None
    if primary is not None:
        secondary = tuple(t for t in elig_tickers if t != primary)[:2]
    else:
        secondary = ()
    chosen = {primary} | set(secondary)
    watch = tuple([t for t in elig_tickers if t not in chosen]
                  + _conditional_tickers(profiles, horizon))
    rejected = tuple(_rejected_entries(profiles, verdict_map, horizon))
    return CandidateSlate(
        theme_id=theme_key,
        horizon=horizon,
        primary=primary,
        secondary=secondary,
        watch=watch,
        rejected=rejected,
        no_clear_winner=no_clear,
        no_trade_reason=decision["no_trade_reason"],
        signal_basis=signal_basis,
    )


# ---------------------------------------------------------------------------
# Deterministic confidence + signal_basis
# ---------------------------------------------------------------------------

def _coverage(profiles: list, horizon: str) -> float:
    """Fraction of the theme's candidates that are eligible-or-conditional for the
    horizon AND carry live (non-degraded) RS. 0.0 when the theme is empty."""
    total = len(profiles)
    if total == 0:
        return 0.0
    usable = sum(
        1 for p in profiles
        if p.status_for(horizon) in ("eligible", "conditional") and p.rs_available)
    return usable / total


def _clarity(decision: dict) -> float:
    """How decisive the top RS gap is: min(lead / _RS_GAP_DECISIVE_PCT, 1.0); 1.0
    for a lone decisive eligible name; 0.0 whenever no_clear_winner is set."""
    if decision["no_clear_winner"]:
        return 0.0
    lead = decision["lead"]
    if lead is None:            # lone eligible name that survived the guard
        return 1.0
    return min(lead / _RS_GAP_DECISIVE_PCT, 1.0)


def _signal_basis(profiles: list, horizon: str, decision: dict,
                  coverage: float) -> str:
    """Three-way basis classifier for ONE horizon.

    * degraded_insufficient — no eligible frontrunner, or coverage too thin to assess.
    * no_clear_winner       — eligible candidates exist but no decisive separation
                              (a NEUTRAL / WAIT state — never bearish, never "sell").
    * signal_present        — an eligible frontrunner exists with a decisive gap.
    """
    if decision["frontrunner"] is None or coverage < _COVERAGE_MIN:
        return _BASIS_DEGRADED
    if decision["no_clear_winner"]:
        return _BASIS_NO_WINNER
    return _BASIS_PRESENT


# ---------------------------------------------------------------------------
# Public deterministic entrypoint (LLM-free) — used directly by tests
# ---------------------------------------------------------------------------

def compute_screening(cards: list, signals=None, *, theme_key: str,
                      as_of: Optional[str] = None) -> dict:
    """Run the FULL deterministic layer for one theme (NO LLM, NO network).

    Returns a dict with: ``profiles`` (list[CandidateProfile]), ``verdict_map``
    ({ticker: {horizon: EligibilityVerdict}}), per-horizon ``decisions``,
    ``slates`` ({"short": CandidateSlate, "mid": CandidateSlate}), ``confidence``
    ({short, mid, long, decomposition}), and ``signal_basis`` ({short, mid}).
    Everything here is deterministic and byte-stable for identical inputs.
    """
    from lib.candidate_eligibility import eligibility_by_horizon

    sig_map = _signal_map(signals)
    theme_cards = [c for c in (cards or []) if _card_theme(c) == theme_key]

    profiles: list = []
    verdict_map: dict = {}
    for card in theme_cards:
        ticker = _card_ticker(card)
        sig = sig_map.get(ticker)
        verdicts = eligibility_by_horizon(card, sig, as_of=as_of)
        verdict_map[ticker] = verdicts
        profiles.append(_build_profile(card, sig, theme_key, verdicts))
    # Byte-stable ordering of the profile list itself.
    profiles.sort(key=lambda p: p.ticker)

    decisions: dict = {}
    slates: dict = {}
    signal_basis: dict = {}
    confidence: dict = {}
    for h in _SCREEN_HORIZONS:
        ordered = _rank_eligible(profiles, h)
        decision = _frontrunner_decision(ordered, h)
        cov = _coverage(profiles, h)
        basis = _signal_basis(profiles, h, decision, cov)
        clarity = _clarity(decision)
        decisions[h] = decision
        signal_basis[h] = basis
        slates[h] = _build_slate(profiles, verdict_map, theme_key, h, decision, basis)
        confidence[h] = round(cov * clarity, 6)
        confidence[f"{h}_coverage"] = round(cov, 6)
        confidence[f"{h}_clarity"] = round(clarity, 6)
    confidence["long"] = 0.0
    confidence["long_status"] = _LONG_STATUS
    confidence["long_rationale"] = _LONG_RATIONALE

    return {
        "theme_key": theme_key,
        "strategy": _STRATEGY,
        "profiles": profiles,
        "verdict_map": verdict_map,
        "decisions": decisions,
        "slates": slates,
        "signal_basis": signal_basis,
        "confidence": confidence,
    }


def _signal_map(signals) -> dict:
    """Normalize ``signals`` (list[CandidateSignal] | dict | None) to {ticker: sig}."""
    if signals is None:
        return {}
    if isinstance(signals, dict):
        return {str(k): v for k, v in signals.items()}
    out: dict = {}
    for s in signals:
        t = str(_field(s, "ticker", "") or "")
        if t:
            out[t] = s
    return out


# ===========================================================================
# task_instruction builder (QUALITATIVE tokens only — never a number)
# ===========================================================================

def _horizon_context(slate: CandidateSlate, decision: dict,
                     profile_map: dict, basis: str) -> str:
    """Build the number-free context line for ONE horizon.

    Only ticker symbols, role/tier/label words, and the signal_basis are
    interpolated — never an RS value, percentile, cap, or gap magnitude."""
    fr = decision["frontrunner"]
    if fr is None:
        return (f"{slate.horizon.upper()}: no eligible frontrunner "
                f"(basis {basis}); watch {', '.join(slate.watch) or 'none'}.")
    p = profile_map[fr.ticker]
    runner = slate.secondary[0] if slate.secondary else None
    runner_role = profile_map[runner].theme_role if runner else "none"
    capped = "capped" if p.quality_capped else "uncapped"
    winner = slate.primary or "none (no_clear_winner)"
    return (
        f"{slate.horizon.upper()}: code frontrunner {fr.ticker} "
        f"(role {p.theme_role}, volume {p.volume_confirmation}, "
        f"valuation {p.valuation_state}, tradability {capped}); "
        f"runner-up {runner or 'none'} (role {runner_role}); "
        f"code-decided primary {winner}; basis {basis}."
    )


def _build_task_instruction(theme_key: str, theme_context: dict,
                            result: dict) -> str:
    """Dynamic, horizon-aware task instruction. All interpolated context is
    QUALITATIVE. The REQUIRED OUTPUT FORMAT block uses 4-space indentation (NOT
    triple-backtick fences, which confuse the JSON extractor in agent_runner)."""
    profile_map = {p.ticker: p for p in result["profiles"]}
    stage = str((theme_context or {}).get("stage", "") or "unknown")
    stage_conf = bool((theme_context or {}).get("stage_confirmed", False))
    label = str((theme_context or {}).get("label_en", "") or theme_key)
    ctx_lines = "\n".join(
        _horizon_context(result["slates"][h], result["decisions"][h],
                         profile_map, result["signal_basis"][h])
        for h in _SCREEN_HORIZONS
    )
    return (
        "You are CandidateScreeningAgent, a PER-THEME relative momentum screener "
        "(strategy: relative-strength gap within ONE theme). The deterministic "
        "eligibility gate, comparison table, per-horizon frontrunner, and the "
        "no_clear_winner decision have ALREADY been computed in code. Your ONLY job "
        "is to EXPLAIN which differences are decisive and translate trade-offs into "
        "horizon fit and invalidation conditions. You do NOT pick the primary (code "
        "did) and you do NOT override no_clear_winner.\n\n"
        f"Theme: {label} (stage {stage}, "
        f"breadth {'confirmed' if stage_conf else 'unconfirmed'}).\n"
        f"{ctx_lines}\n\n"
        "Provide THREE findings:\n"
        "1. SHORT-TERM: explain WHICH differences make the code's SHORT frontrunner "
        "win over the runner-up (e.g. earlier RS inflection, more direct chain role, "
        "cleaner volume), and give its HORIZON FIT and an INVALIDATION condition "
        "(the observable that would flip the read). If the SHORT basis is "
        "\"no_clear_winner\", you MUST state the theme is attractive but NO "
        "constituent is decisively actionable, and you MUST NOT manufacture a pick. "
        "If the basis is \"degraded_insufficient\", state coverage is insufficient "
        "to advance any name. If the frontrunner's tradability is \"capped\", you "
        "MUST NOT present its magnitude as genuine leadership.\n"
        "2. MID-TERM: same task for the MID frontrunner (it MAY be a different "
        "ticker than short — a faster RS leader short vs a better chain-position or "
        "valuation name mid). Explain the trade-off and the horizon fit.\n"
        "3. LONG-TERM: ALWAYS state that relative-strength screening is a short-to-"
        "mid tactical read and long-horizon conviction defers to StockResearch / "
        "ValuationDebate.\n\n"
        "TONE: frame every pick as \"worth ADVANCING to trade construction,\" with "
        "final entry deferring to money-flow, technical entry, and portfolio-risk "
        "checks. NEVER say \"buy X.\"\n\n"
        "RULES (never violate):\n"
        "- NEVER present \"no_clear_winner\" as bullish or bearish; it is a neutral "
        "/ wait state.\n"
        "- NEVER flip a code-decided no_clear_winner into a pick, and NEVER name a "
        "primary the code did not choose.\n"
        "- NEVER read a \"capped\" ticker's magnitude as genuine leadership.\n"
        "- NEVER invent numbers — cite evidence_ids only.\n\n"
        "Each finding must cite at least one evidence_id from the packet. No numeric "
        "values in finding text. No dollar signs, percentages, or metric tokens.\n\n"
        # REQUIRED OUTPUT FORMAT — 4-space indentation, NOT triple-backtick fences.
        # Plain (NON-f) string literal: the braces below are literal.
        "REQUIRED OUTPUT FORMAT — you must respond with ONLY valid JSON\n"
        "matching this exact structure. No prose, no markdown fences.\n\n"
        "    {\n"
        "      \"agent_name\": \"CandidateScreeningAgent\",\n"
        "      \"run_id\": \"<use the run_id from the evidence packet header>\",\n"
        "      \"findings\": [\n"
        "        {\n"
        "          \"text\": \"<SHORT-TERM decisive-factor judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        },\n"
        "        {\n"
        "          \"text\": \"<MID-TERM decisive-factor judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        },\n"
        "        {\n"
        "          \"text\": \"<LONG-TERM defer judgment — no numbers>\",\n"
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
        "- agent_name must be exactly \"CandidateScreeningAgent\"\n"
        "- run_id must be copied verbatim from the evidence packet\n"
        "- findings must be a list, never a flat object\n"
        "- each finding must have \"text\" and \"evidence\" keys\n"
        "- confidence must be an object with level/rationale/score, never a float\n"
        "- evidence_id must be an id from the provided evidence packet\n"
        "- no numeric values in any finding text field"
    )


# ===========================================================================
# ToolResult payload builders (numeric firewall — numbers live here as evidence)
# ===========================================================================

def _comparison_payload(result: dict) -> dict:
    """TR1 — the per-ticker comparison table (ranks, tiers, labels, capped flags,
    availability markers; raw RS excess as evidence)."""
    profiles = result["profiles"]
    rank_by_h = {h: {p.ticker: i + 1 for i, p in enumerate(_rank_eligible(profiles, h))}
                 for h in _SCREEN_HORIZONS}
    rows = []
    for p in profiles:
        rows.append({
            **p.to_dict(),
            "short_rank": rank_by_h["short"].get(p.ticker),
            "mid_rank": rank_by_h["mid"].get(p.ticker),
        })
    return {
        "theme_key": result["theme_key"],
        "strategy": result["strategy"],
        "n_candidates": len(profiles),
        "unavailable_dimensions": ["short_crowding", "options_structure"],
        "comparison_table": rows,
    }


def _slate_payload(result: dict) -> dict:
    """TR2 — the deterministic slate skeleton + basis (code-decided, not LLM)."""
    return {
        "theme_key": result["theme_key"],
        "strategy": result["strategy"],
        "short_slate": result["slates"]["short"].to_dict(),
        "mid_slate": result["slates"]["mid"].to_dict(),
        "long_status": _LONG_STATUS,
        "signal_basis_short": result["signal_basis"]["short"],
        "signal_basis_mid": result["signal_basis"]["mid"],
    }


def _confidence_payload(result: dict) -> dict:
    """TR3 — short/mid/long confidence + decomposition + long rationale."""
    c = result["confidence"]
    return {
        "short_confidence": c["short"],
        "mid_confidence": c["mid"],
        "long_confidence": c["long"],
        "short_coverage": c["short_coverage"],
        "short_clarity": c["short_clarity"],
        "mid_coverage": c["mid_coverage"],
        "mid_clarity": c["mid_clarity"],
        "long_status": _LONG_STATUS,
        "long_rationale": _LONG_RATIONALE,
    }


def _supporting_data(result: dict) -> dict:
    """The deterministic layer carried VERBATIM on AgentOutput.supporting_data
    (serialized by append_agent_output — the slate's canonical persistence)."""
    c = result["confidence"]
    return {
        "theme_key": result["theme_key"],
        "strategy": result["strategy"],
        "comparison_table": _comparison_payload(result)["comparison_table"],
        "unavailable_dimensions": ["short_crowding", "options_structure"],
        "short_slate": result["slates"]["short"].to_dict(),
        "mid_slate": result["slates"]["mid"].to_dict(),
        "signal_basis_short": result["signal_basis"]["short"],
        "signal_basis_mid": result["signal_basis"]["mid"],
        "short_confidence": c["short"],
        "mid_confidence": c["mid"],
        "long_confidence": c["long"],
        "long_status": _LONG_STATUS,
    }


# ===========================================================================
# Main production function (ONE AgentOutput per theme)
# ===========================================================================

def run_candidate_screening_agent(
    cards: list,
    *,
    theme_key: str,
    signals=None,
    theme_context: Optional[dict] = None,
    as_of: Optional[str] = None,
    snapshot_dir: str = "data/snapshots",
) -> "AgentOutput":
    """Production CandidateScreeningAgent for ONE theme — see the module docstring.

    ``cards`` is the theme's OpportunityCard subset (or the full list, filtered by
    ``theme_key`` here). ``signals`` (list[CandidateSignal] | dict | None) supplies
    the eps / valuation / entry-quality fields the eligibility gate reads — the
    OpportunityCard does NOT carry them, so without signals every card degrades to
    a hard-unknown gate verdict (documented deviation from the cards-only sketch;
    the Cockpit passes the live CandidateSignal list). Matched to cards by ticker.

    Returns ONE evidence-backed AgentOutput whose ``ticker`` is the ``theme_key``.
    The full deterministic comparison table + slate skeleton + confidences are on
    ``supporting_data`` BEFORE the LLM runs. Wrapped in an outer fail-closed guard:
    any unexpected error yields a rule-based fallback AgentOutput, never a raise.
    """
    supporting_data: dict = {"theme_key": theme_key, "strategy": _STRATEGY}
    run_id: Optional[str] = None

    try:
        # 1. Deterministic layer (NO LLM, NO network).
        result = compute_screening(cards, signals, theme_key=theme_key, as_of=as_of)
        supporting_data = _supporting_data(result)

        # 2. Mint one run_id and reuse it everywhere (store + packet + runner).
        from lib.reliability.run_context import create_run_context

        run_context = create_run_context(
            ticker=theme_key, task="candidate_screening_agent")
        run_id = run_context.run_id

        # 3. Build THREE evidence-backed ToolResults (numbers live here as evidence).
        from lib.agent_framework.world_adapter import (
            processed_signals_to_tool_result,
        )

        tr_comparison = processed_signals_to_tool_result(
            _comparison_payload(result),
            run_id=run_id,
            tool_name="candidate_screening_comparison",
            target=theme_key,
            metric_group="screening",
            description="Per-ticker deterministic comparison table for the theme",
        )
        tr_slate = processed_signals_to_tool_result(
            _slate_payload(result),
            run_id=run_id,
            tool_name="candidate_screening_slate",
            target=theme_key,
            metric_group="slate",
            description="Deterministic slate skeleton (code-decided primary/secondary)",
        )
        tr_confidence = processed_signals_to_tool_result(
            _confidence_payload(result),
            run_id=run_id,
            tool_name="candidate_screening_confidence",
            target=theme_key,
            metric_group="confidence",
            description=(
                "Deterministic confidence scores (computed before LLM). "
                + _LONG_RATIONALE
            ),
        )

        # 4. Dynamic, horizon-aware task instruction (qualitative tokens only).
        task_instruction = _build_task_instruction(theme_key, theme_context, result)

        # 5. Run the constrained agent (per-theme identity; EOD validity).
        from lib.agent_framework.agent_runner import run_llm_agent

        return run_llm_agent(
            agent_id="CandidateScreeningAgent",
            horizon="cross",
            task_instruction=task_instruction,
            tool_results=[tr_comparison, tr_slate, tr_confidence],
            supporting_data=supporting_data,
            requires_human_confirmation=True,
            judgment_source="llm_proposed",
            valid_until=end_of_today_iso(),
            ticker=theme_key,
            max_tokens=1024,
            run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001 — outer fail-closed guard
        _log.warning(
            "run_candidate_screening_agent[%s] failed; returning fallback: %s",
            theme_key, exc)
        from lib.agent_framework.agent_runner import _fallback_agent_output

        return _fallback_agent_output(
            "CandidateScreeningAgent",
            "cross",
            supporting_data,
            exc,
            valid_until=end_of_today_iso(),
            run_id=run_id,
            target=theme_key,
            ticker=theme_key,
        )
