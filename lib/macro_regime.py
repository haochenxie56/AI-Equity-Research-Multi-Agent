"""lib/macro_regime.py — Phase 6A deterministic macro regime classification.

This module turns a :class:`lib.macro_data.MacroDataResult` (live or
fixture-backed) into a :class:`MacroRegimeResult` using **fully deterministic
code** — no LLM, no external call. Every classification rule and threshold is
documented inline so the logic is auditable.

Output regimes:

* ``risk_on``    — supportive backdrop (calm vol, tight credit, positive breadth).
* ``risk_off``   — defensive backdrop (elevated vol, wide credit, weak breadth).
* ``transition`` — mixed / unconfirmed signals; no clear risk lean.
* ``degraded``   — insufficient live data coverage to classify (see the hard
                   guard below).

Localization note: ``key_signals`` and ``opportunity_posture`` are the canonical
**English** contract fields (kept for evidence / non-UI consumers). For bilingual
UI rendering, this module ALSO emits a parallel ``signals`` list of structured
records — ``{"code": str, "values": dict}`` — so the presentation layer
(``pages/8_Macro_Dashboard.py``) can render localized (EN/ZH) text via ``t()``
without re-deriving any classification logic. ``signals`` and ``key_signals`` are
parallel (same order / length).

The result is **review-only context**: it never authorizes execution, never
emits a buy/sell instruction, and carries no ``approved_for_execution`` field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid a hard runtime import cycle / dependency for typing only
    from lib.macro_data import MacroDataResult


# Horizon-bias vocabulary (review-only posture leanings).
HORIZON_BIAS_VALUES = ("favorable", "neutral", "cautious", "unfavorable")
REGIME_VALUES = ("risk_on", "risk_off", "transition", "degraded")
CONFIDENCE_VALUES = ("high", "medium", "low")

# Hard guard: below this live-data coverage fraction we cannot responsibly
# classify a regime, so we return "degraded" regardless of any other signal.
_MIN_COVERAGE = 0.5


@dataclass
class MacroRegimeResult:
    """Deterministic macro regime classification (review-only)."""

    regime: str  # one of REGIME_VALUES
    confidence: str  # one of CONFIDENCE_VALUES
    horizon_bias: dict = field(default_factory=dict)  # {"short","mid","long"} -> bias
    key_signals: list = field(default_factory=list)  # canonical English strings
    opportunity_posture: str = ""  # canonical English posture summary
    data_coverage: float = 0.0
    # Structured, localizable signals parallel to key_signals:
    #   [{"code": "vix_low", "values": {"vix": 15.0}}, ...]
    signals: list = field(default_factory=list)


def _bias(short: str, mid: str, long: str) -> dict:
    return {"short": short, "mid": mid, "long": long}


def _emit(signals: list, key_signals: list, code: str, en_text: str, **values) -> None:
    """Append a signal to both the structured list and the English list."""
    signals.append({"code": code, "values": values})
    key_signals.append(en_text)


def classify_regime(data: "MacroDataResult") -> MacroRegimeResult:
    """Classify the macro regime from a MacroDataResult.

    The classification is a transparent signal tally. Each macro reading votes
    ``risk_on`` or ``risk_off`` against documented thresholds; the net vote
    decides the regime, and the agreement strength decides the confidence.
    """
    coverage = float(getattr(data, "data_coverage", 0.0) or 0.0)

    # ----- Hard guard: degraded when live coverage < 50% -------------------
    # With less than half the metric groups live, we refuse to assert a regime
    # and surface a neutral/unknown posture. This is the single most important
    # safety rule in this module.
    if coverage < _MIN_COVERAGE:
        signals: list = []
        key_signals: list = []
        _emit(
            signals,
            key_signals,
            "degraded",
            f"Live data coverage {coverage:.0%} is below the 50% threshold; "
            "regime classification is degraded/unknown.",
            coverage_pct=f"{coverage:.0%}",
        )
        return MacroRegimeResult(
            regime="degraded",
            confidence="low",
            horizon_bias=_bias("neutral", "neutral", "neutral"),
            key_signals=key_signals,
            opportunity_posture=(
                "Macro data coverage is insufficient to classify a regime. Treat "
                "macro context as unknown and rely on bottom-up review only. This "
                "is review-only context, not a buy/sell decision."
            ),
            data_coverage=coverage,
            signals=signals,
        )

    risk_on = 0
    risk_off = 0
    signals = []
    key_signals = []

    vix = data.vix
    rates = data.rates
    credit = data.credit
    dollar = data.dollar
    etf = data.etf_returns

    # ----- Rule 1: VIX level ----------------------------------------------
    # VIX < 18 = calm (risk-on); VIX > 27 = stressed (risk-off). The 18/27
    # band brackets the long-run "complacent" and "fear" zones.
    if vix is not None and vix.value is not None:
        if vix.value < 18:
            risk_on += 1
            _emit(signals, key_signals, "vix_low",
                  f"VIX {vix.value} is low (<18): calm volatility, risk-on.",
                  vix=vix.value)
        elif vix.value > 27:
            risk_off += 1
            _emit(signals, key_signals, "vix_high",
                  f"VIX {vix.value} is elevated (>27): stress, risk-off.",
                  vix=vix.value)
        else:
            _emit(signals, key_signals, "vix_mid",
                  f"VIX {vix.value} is mid-range (18–27): neutral volatility.",
                  vix=vix.value)

    # ----- Rule 2: VIX-derived fear/greed proxy ---------------------------
    # >60 = greed (risk-on lean, with crowding caution); <40 = fear (risk-off).
    if vix is not None and vix.fear_greed is not None:
        if vix.fear_greed > 60:
            risk_on += 1
            _emit(signals, key_signals, "fg_greed",
                  f"Fear/greed proxy {vix.fear_greed} signals greed (>60): risk-on "
                  "(watch for crowding).",
                  fg=vix.fear_greed)
        elif vix.fear_greed < 40:
            risk_off += 1
            _emit(signals, key_signals, "fg_fear",
                  f"Fear/greed proxy {vix.fear_greed} signals fear (<40): risk-off.",
                  fg=vix.fear_greed)

    # ----- Rule 3: HY credit spread ---------------------------------------
    # Tight HY OAS (< 3.5 pp) = healthy credit (risk-on); wide (> 5.0 pp) =
    # credit stress (risk-off). These bracket benign vs stressed HY regimes.
    if credit is not None and credit.hy_spread is not None:
        if credit.hy_spread < 3.5:
            risk_on += 1
            _emit(signals, key_signals, "credit_tight",
                  f"HY credit spread {credit.hy_spread}pp is tight (<3.5): risk-on.",
                  hy=credit.hy_spread)
        elif credit.hy_spread > 5.0:
            risk_off += 1
            _emit(signals, key_signals, "credit_wide",
                  f"HY credit spread {credit.hy_spread}pp is wide (>5.0): credit stress, risk-off.",
                  hy=credit.hy_spread)

    # ----- Rule 4: Yield-curve slope (10Y-2Y) -----------------------------
    # Inversion (< 0) is a recession-risk / caution signal (risk-off lean);
    # a clearly positive slope (> 0.5 pp) is expansion-friendly (risk-on).
    if rates is not None and rates.spread_10y_2y is not None:
        if rates.spread_10y_2y < 0:
            risk_off += 1
            _emit(signals, key_signals, "curve_inverted",
                  f"10Y-2Y spread {rates.spread_10y_2y}pp is inverted (<0): recession-risk caution.",
                  spread=rates.spread_10y_2y)
        elif rates.spread_10y_2y > 0.5:
            risk_on += 1
            _emit(signals, key_signals, "curve_steep",
                  f"10Y-2Y spread {rates.spread_10y_2y}pp is positively sloped (>0.5): expansion-friendly.",
                  spread=rates.spread_10y_2y)

    # ----- Rule 5: Equity breadth / leadership (SPY + IWM 1M returns) ------
    # Positive SPY + IWM = broad participation (risk-on); both negative =
    # broad weakness (risk-off). IWM (small caps) is the breadth proxy.
    r1 = getattr(etf, "returns_1m", {}) if etf is not None else {}
    spy = r1.get("SPY")
    iwm = r1.get("IWM")
    if spy is not None and iwm is not None:
        if spy > 0 and iwm > 0:
            risk_on += 1
            _emit(signals, key_signals, "breadth_broad",
                  f"SPY {spy}% and IWM {iwm}% 1M returns are both positive: broad participation, risk-on.",
                  spy=spy, iwm=iwm)
        elif spy < 0 and iwm < 0:
            risk_off += 1
            _emit(signals, key_signals, "breadth_weak",
                  f"SPY {spy}% and IWM {iwm}% 1M returns are both negative: broad weakness, risk-off.",
                  spy=spy, iwm=iwm)
        else:
            _emit(signals, key_signals, "breadth_mixed",
                  f"SPY {spy}% vs IWM {iwm}% 1M returns diverge: mixed breadth.",
                  spy=spy, iwm=iwm)

    # ----- Rule 6: Dollar trend -------------------------------------------
    # A sharply stronger broad dollar (> +2% 1M) tightens global liquidity
    # (risk-off lean); a weaker dollar (< -2% 1M) eases it (risk-on lean).
    if dollar is not None and dollar.change_1m is not None:
        if dollar.change_1m > 2.0:
            risk_off += 1
            _emit(signals, key_signals, "dollar_strong",
                  f"Broad dollar +{dollar.change_1m}% 1M: tightening liquidity, risk-off lean.",
                  chg=dollar.change_1m)
        elif dollar.change_1m < -2.0:
            risk_on += 1
            _emit(signals, key_signals, "dollar_weak",
                  f"Broad dollar {dollar.change_1m}% 1M: easing liquidity, risk-on lean.",
                  chg=dollar.change_1m)

    # ----- Net vote -> regime ---------------------------------------------
    # A 2-vote net margin is required for a directional call; otherwise the
    # backdrop is judged a "transition" (mixed / unconfirmed).
    net = risk_on - risk_off
    if net >= 2:
        regime = "risk_on"
    elif net <= -2:
        regime = "risk_off"
    else:
        regime = "transition"

    # ----- Confidence ------------------------------------------------------
    # High: strong agreement (|net| >= 3) and high coverage (>= 0.8).
    # Medium: a clear directional margin. Low: weak / mixed margin.
    if abs(net) >= 3 and coverage >= 0.8:
        confidence = "high"
    elif abs(net) >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # ----- Horizon bias ----------------------------------------------------
    # risk_on favors short + mid (momentum / continuation), long stays neutral
    # (valuation/cycle-dependent). transition is cautious across all horizons.
    # risk_off is unfavorable for short + mid, long neutral (accumulation window
    # may emerge). Degraded was already handled above.
    if regime == "risk_on":
        horizon_bias = _bias("favorable", "favorable", "neutral")
        posture = (
            "Risk-on backdrop favors momentum and continuation setups short- and "
            "mid-term; keep long-term entries valuation-disciplined. Review-only "
            "context, not a buy/sell decision."
        )
    elif regime == "risk_off":
        horizon_bias = _bias("unfavorable", "unfavorable", "neutral")
        posture = (
            "Risk-off backdrop is unfavorable for fresh short- and mid-term risk; "
            "favor capital preservation and watch for a later accumulation window. "
            "Review-only context, not a buy/sell decision."
        )
    else:  # transition
        horizon_bias = _bias("cautious", "cautious", "cautious")
        posture = (
            "Transitional backdrop with mixed/unconfirmed signals; stay cautious "
            "across horizons and wait for confirmation. Review-only context, not a "
            "buy/sell decision."
        )

    if not signals:
        _emit(signals, key_signals, "default",
              "No decisive macro signals available; classified by default margin.")

    return MacroRegimeResult(
        regime=regime,
        confidence=confidence,
        horizon_bias=horizon_bias,
        key_signals=key_signals,
        opportunity_posture=posture,
        data_coverage=coverage,
        signals=signals,
    )
