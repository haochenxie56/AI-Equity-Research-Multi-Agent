"""lib/order_advisor.py — Phase 6C-A v2 Entry Strategy (horizon-native, scenario-aware).

This module turns one ticker (optionally an active :class:`lib.holdings.HoldingRecord`
plus its thesis status and the current macro regime) into a review-only **order
recommendation**:

* :func:`compute_price_levels` — PURE CODE (no LLM). From the ``lib.technical``
  snapshot (EMA10 / EMA20 / SMA50 / SMA200 / RSI / ADX / volume / swing
  support-resistance / candlestick) plus the unified
  :class:`lib.equity_valuation.AppFairValue` fair-value producer (Anchor Intel v2,
  U1 — the legacy ``lib.valuation_anchor`` analyst-proxy is retired)
  it derives, per **horizon** (short / mid / long) and **scenario** (initiate vs
  add vs manage), an entry zone, a horizon-differentiated stop-loss level, a
  position-sizing band, an action label, the unmet conditions, the next trigger,
  and a risk note. The LLM is NEVER allowed to compute or override any number.

  Horizon logic (Entry Strategy v3):
    - SHORT uses **EMA10 + EMA20** (fast trend) + a hard volume gate.
    - MID uses **SMA50** with a healthy / neutral / unhealthy volume state.
    - LONG uses **SMA200 + fair_value_anchor** (valuation margin of safety); its
      stop is thesis / valuation driven, not short-term technical.
  Scenario logic:
    - SHORT never averages down a losing position.
    - MID may ``average_down_small`` only when the thesis is intact and EPS is not
      deteriorating.
    - LONG may ``average_down`` when the thesis is intact.

* :func:`generate_order_narrative` — ONE LLM call that only *synthesizes a
  narrative* over the already-computed levels (action rationale, stop reasoning,
  R:R warning, next-trigger note). It invents no numbers.

Guardrails (Phase 6C-A v2): free sources only (yfinance via ``ui_utils.load_ohlcv``
and ``lib.equity_valuation``); fail-closed with a fixture fallback
(``data_source="fixture"``); no paid API; no broker / order / execution; no order
ticket / broker payload; ``approved_for_execution`` is ALWAYS ``False``; produces
no executable instruction — only a suggestion the user must place manually.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Kelly-lite sizing assumptions (documented; clamp 2%–10%)
# ---------------------------------------------------------------------------
# Half-Kelly is used for safety. The win_rate is a fixed, documented ASSUMPTION
# (we do not have a per-name backtested edge); avg_win scales with the computed
# risk/reward ratio and avg_loss is normalized to 1.0 (one risk unit = the
# distance to the stop). The result is clamped to a conservative 2%–10% band.
_KELLY_WIN_RATE = 0.55  # assumed base win rate (documented assumption)
_KELLY_FRACTION = 0.5  # half-Kelly
_POS_MIN = 0.02
_POS_MAX = 0.10

_LIVE = "live"
_FIXTURE = "fixture"

# Bilingual position-sizing labels (zh / en) — documented bands per scenario.
_SIZE_SHORT_INIT = "目标仓位的15%–30% / 15–30% of target"
_SIZE_MID_FULL = "目标仓位的25%–40% / 25–40% of target"
_SIZE_SMALL = "目标仓位的10%–20% / 10–20% of target"
_SIZE_AVG_DOWN_SMALL = "目标仓位的10%–15% / 10–15% of target"
_SIZE_ADD_PARTIAL = "目标仓位的15%–25% / 15–25% of target"
_SIZE_ADD_TINY = "目标仓位的5%–10% / 5–10% of target"
_SIZE_LONG_TRANCHES = "分3–5笔建仓 / Build in 3–5 tranches"
_SIZE_REASSESS = "等待回调后再评估 / Reassess on pullback"
_SIZE_NONE = ""

_BEARISH_CANDLES = ("bearish_engulfing", "shooting_star")
_BULLISH_CANDLES = ("bullish_engulfing", "hammer")


# ---------------------------------------------------------------------------
# Missing-condition registry (Phase 7A final fix — string/constants only)
#
# Single source of truth for the bilingual ``missing_conditions`` strings the
# entry engine emits, each tagged with a STABLE ``code`` and a ``category``
# ("fundamental" | "trigger"). Emission sites reference these entries instead of
# inlining literals, and ``lib.opportunity_ranker`` classifies engine blocks by
# the declared category (substring matching is only a legacy fallback).
#
# STRICT: this is a pure refactor. ``MissingCondition.text`` reproduces the exact
# string each site emitted before, so every consumer that matches display text
# (the LLM order-narrative serializer's "; ".join/split, Trading Desk order
# cards, thesis monitor, existing test fixtures) is unaffected. No numeric logic,
# threshold, gate, or control-flow change.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissingCondition:
    """A registered entry-engine missing-condition (stable code + category)."""

    code: str
    category: str  # "fundamental" | "trigger"
    text_en: str
    text_zh: str

    @property
    def text(self) -> str:
        """The exact bilingual string emitted into ``missing_conditions``."""
        return f"{self.text_en} / {self.text_zh}"


MISSING_CONDITION_REGISTRY: "dict[str, MissingCondition]" = {
    mc.code: mc for mc in (
        # --- SHORT technical-confirmation triggers (not-yet-confirmed entry) ---
        MissingCondition("price_below_ema20", "trigger",
                         "price not above EMA20", "价格未站上EMA20"),
        MissingCondition("ema10_below_ema20", "trigger",
                         "EMA10 below EMA20", "EMA10低于EMA20"),
        MissingCondition("rsi_out_of_band", "trigger",
                         "RSI outside 40–68", "RSI不在40–68"),
        MissingCondition("volume_not_confirmed", "trigger",
                         "volume not confirmed", "量能未确认"),
        MissingCondition("bearish_candlestick", "trigger",
                         "bearish candlestick", "出现看跌K线"),
        # --- Fundamental hard gates (genuine "do not buy") ---
        MissingCondition("eps_deteriorating", "fundamental",
                         "EPS revisions deteriorating", "EPS预期下修"),
        MissingCondition("valuation_stretched", "fundamental",
                         "Valuation stretched (≥70th pct)", "估值偏高(≥70百分位)"),
    )
}

# Reverse index: exact emitted text -> category (consumed by the ranker).
MISSING_CONDITION_TEXT_TO_CATEGORY: "dict[str, str]" = {
    mc.text: mc.category for mc in MISSING_CONDITION_REGISTRY.values()
}


def missing_condition_category(text: str) -> "Optional[str]":
    """Category ('fundamental'|'trigger') for an emitted missing-condition string,
    or ``None`` if the string is not a registered condition."""
    return MISSING_CONDITION_TEXT_TO_CATEGORY.get(str(text))


# ---------------------------------------------------------------------------
# Action definitions (documented inline — the full vocabulary)
# ---------------------------------------------------------------------------
# wait                — no entry; conditions not met (fundamental / technical).
# hold                — already positioned; do nothing now.
# enter_partial_now   — price is inside the zone; start a partial position now.
# enter_on_pullback   — wait for a modest pullback into the zone, then enter.
# enter_or_add_small  — SHORT: small confirmed-trend entry / add near support.
# add_small           — MID: small add while constructively above cost.
# add_partial         — LONG: partial add inside the cost-to-+20% band when cheap.
# add_tiny            — LONG: tiny add when valuation is mid-rich (0.50–0.70 pct).
# average_down_small  — MID: small average-down only with an intact thesis.
# average_down        — LONG: average-down only with an intact thesis.
# wait_for_pullback   — constructive name, but price extended; wait for a dip.
# wait_or_cut         — SHORT losing position; do NOT average down — wait or cut.
# reduce              — trim exposure (risk management).
# reduce_or_exit      — trim materially or exit.
# cut_loss            — exit a losing position on a stop.
# exit                — close the position.
# trim_or_stop_adding — stop adding / trim into strength.
# avoid               — thesis broken; do not enter, reassess the exit.
_ACTIONS_FULL = (
    "wait", "hold", "enter_partial_now", "enter_on_pullback", "enter_or_add_small",
    "add_small", "add_partial", "add_tiny", "average_down_small", "average_down",
    "wait_for_pullback", "wait_or_cut", "reduce", "reduce_or_exit", "cut_loss",
    "exit", "trim_or_stop_adding", "avoid",
)
# Narrative action vocabulary (the LLM synthesis still suggests one of these
# five high-level labels; the computed PriceLevelResult.action carries the full
# fine-grained vocabulary above).
_ACTIONS = ("add", "hold", "trim", "exit", "wait")


@dataclass
class PriceLevelResult:
    """Deterministic, code-computed entry strategy for one ticker (no LLM).

    Entry Strategy v3 fields are horizon-native and scenario-aware. ``stop_loss``,
    ``target_price``, ``position_size_pct``, ``support_levels`` and
    ``resistance_levels`` are RETAINED legacy fields (kept so the existing Trading
    Desk page and the Phase 6C-A regression test continue to work); ``stop_loss``
    mirrors ``stop_loss_level``. ``approved_for_execution`` is ALWAYS ``False``.
    """

    # --- v3 canonical fields ----------------------------------------------
    ticker: str = ""
    scenario: str = "initiate"  # initiate | add | manage
    horizon: str = "mid"  # short | mid | long
    current_price: float = 0.0
    cost_basis: Optional[float] = None
    ema10: Optional[float] = None
    ema20: Optional[float] = None  # EMA21 proxy
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    atr_14: float = 0.0
    nearest_support: Optional[float] = None
    nearest_resistance: Optional[float] = None
    fair_value_anchor: Optional[float] = None
    action: str = "wait"  # see Action definitions above
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss_level: Optional[float] = None
    position_sizing: str = ""
    reason: str = ""
    missing_conditions: list = field(default_factory=list)
    next_trigger: str = ""
    risk_note: str = ""
    # in_zone | above_zone | below_zone | blocked | wait
    entry_status: str = "wait"
    risk_reward_ratio: float = 0.0  # 0.0 if entry blocked / no zone
    data_source: str = _FIXTURE  # live | fixture
    # Provenance of the fair-value anchor driving the entry zone:
    #   "app_computed"   — an external/session AppFairValue band (Equity page hand-off
    #                      or the Cockpit cache) drove the LONG zone.
    #   "app_fair_value" — the locally-computed unified AppFairValue producer
    #                      (lib.equity_valuation.compute_app_fair_value) over live
    #                      data, no external band. Anchor Intel v2 r2 (C5 rename):
    #                      was the misleading "analyst_proxy" — there is no analyst
    #                      proxy anymore, the value is the unified producer's output.
    #   "fixture"        — fail-closed fixture fallback
    fair_value_source: str = "app_fair_value"
    # Anchor Intel v2 (U3) — epoch of the AppFairValue that produced the anchor
    # (ISO-8601). Sourced from the external/session band's computed_at when present,
    # else the locally-computed AppFairValue.computed_at. Surfaced unobtrusively
    # (caption/tooltip) on the Trading Desk so the anchor's freshness is visible.
    fair_value_computed_at: str = ""
    approved_for_execution: bool = False  # ALWAYS False (immutable invariant)
    # --- v4 fields (valuation confidence + scenario risk overlay) ---------
    valuation_confidence: str = "low"  # high | medium | low (LONG anchor confidence)
    conservative_anchor: Optional[float] = None  # tier-dependent conservative anchor
    risk_overlay_passed: bool = True  # add-scenario position/risk overlay verdict
    risk_overlay_note: str = ""  # why the overlay blocked (when not passed)
    portfolio_weight_current: float = 0.0  # current weight of this holding
    portfolio_weight_after_add: float = 0.0  # projected weight after the add
    blended_cost_after_add: Optional[float] = None  # projected blended cost after add
    # --- retained legacy fields (page + 6C-A regression test) -------------
    stop_loss: float = 0.0  # == stop_loss_level (0.0 when None)
    target_price: float = 0.0  # nearest resistance above price, else price + 3*ATR
    position_size_pct: float = 0.0  # Kelly-lite, clamped 0.02–0.10
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)
    volume_trend: str = "neutral"  # increasing|decreasing|neutral|flat
    candlestick_pattern: str = "none"
    entry_blocked: bool = False  # True when there is no entry zone
    entry_blocked_reason: str = ""
    wait_target: str = ""  # shown when above_zone / below_zone / blocked


_NARRATIVE_TEXT_FIELDS = (
    "action_reasoning", "entry_note", "stop_note", "target_note", "risk_warning",
    "next_trigger_note",
)


@dataclass
class OrderNarrative:
    """LLM-synthesized narrative over the computed levels (no numbers invented).

    Every free-text field is stored bilingually: the canonical English value plus
    ``{field}_en`` / ``{field}_zh`` (the LLM emits BOTH languages in its single
    JSON response — no ``lib.translator`` / deep-translator round-trip) so the page
    can switch language WITHOUT re-calling the LLM.
    """

    action_suggestion: str = "hold"  # add|hold|trim|exit|wait
    action_reasoning: str = ""
    entry_note: str = ""
    stop_note: str = ""
    target_note: str = ""
    risk_warning: str = ""
    next_trigger_note: str = ""  # surfaced when entry_zone is None / above_zone
    data_source: str = _FIXTURE  # live (LLM) | fixture (code fallback)
    # --- bilingual cache (filled by _finalize_bilingual) ------------------
    action_reasoning_en: str = ""
    action_reasoning_zh: str = ""
    entry_note_en: str = ""
    entry_note_zh: str = ""
    stop_note_en: str = ""
    stop_note_zh: str = ""
    target_note_en: str = ""
    target_note_zh: str = ""
    risk_warning_en: str = ""
    risk_warning_zh: str = ""
    next_trigger_note_en: str = ""
    next_trigger_note_zh: str = ""


@dataclass
class OrderRecommendation:
    """The full per-holding order recommendation bundle (review-only)."""

    holding: object = None
    price_levels: PriceLevelResult = field(default_factory=PriceLevelResult)
    thesis_check: object = None
    narrative: OrderNarrative = field(default_factory=OrderNarrative)
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def _finite(x) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    return None if xf != xf else xf


def _round(x: Optional[float], n: int = 2) -> float:
    v = _finite(x)
    return round(v, n) if v is not None else 0.0


def _app_conservative_anchor(fv) -> Optional[float]:
    """Tier-dependent conservative anchor mapped from an AppFairValue (Anchor Intel v2 U1).

    Mirrors the retired ``FairValueAnchor.conservative_anchor`` semantics on the
    unified producer — the value BELOW which the LONG three-tier applies its
    margin-of-safety discount (and the surfaced ``PriceLevelResult.conservative_anchor``):

    * high confidence -> ``fair_value_mid`` (the blended central fair value — A's
      analog of B's pre-MoS ``min(analyst, relative)``; using the already-discounted
      ``fair_value_low`` here would DOUBLE-discount against the ×0.90 MoS below);
    * medium confidence -> ``analyst_target`` (1:1 with B's ``analyst_anchor``);
    * low / suppressed band (irreconcilable / no_anchor) -> ``None`` so no
      margin-of-safety zone is built off a non-existent anchor.

    NB: distinct from the ``lib.anchor_cache`` entry's ``conservative_anchor``
    (== ``fair_value_low``), which serves the Cockpit cache's own band-floor role;
    this one preserves B's order-advisor tier semantics.
    """
    if fv is None or str(getattr(fv, "blend_state", "") or "") != "blended":
        return None
    conf = str(getattr(fv, "confidence", "") or "")
    if conf == "high":
        mid = _finite(getattr(fv, "fair_value_mid", None))
        return mid if (mid is not None and mid > 0) else None
    if conf == "medium":
        ana = _finite(getattr(fv, "analyst_target", None))
        return ana if (ana is not None and ana > 0) else None
    return None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Support / resistance + candlestick + volume (pure pandas/code) — RETAINED
# ---------------------------------------------------------------------------


def _significant_levels(df, window: int = 20, lookback: int = 3) -> tuple:
    """Return ``(supports, resistances)`` — up to ``lookback`` recent swing lows /
    highs.

    A *significant low* is a local minimum: a bar whose Low is the lowest within a
    ±2-bar neighborhood; a *significant high* is the symmetric local maximum. We
    scan the most recent ``window`` (default 20) bars and keep the most recent
    ``lookback`` (default 3) of each, rounded to 2 dp. Fail-closed -> ``([], [])``.
    """
    try:
        recent = df.tail(max(window, 5))
        lows = list(recent["Low"].astype(float).values)
        highs = list(recent["High"].astype(float).values)
        n = len(lows)
        sup: list = []
        res: list = []
        for i in range(2, n - 2):
            seg_low = lows[i - 2 : i + 3]
            if lows[i] == min(seg_low):
                sup.append(round(lows[i], 2))
            seg_high = highs[i - 2 : i + 3]
            if highs[i] == max(seg_high):
                res.append(round(highs[i], 2))

        def _dedup_recent(vals):
            out = []
            for v in reversed(vals):
                if v not in out:
                    out.append(v)
                if len(out) >= lookback:
                    break
            return out

        return _dedup_recent(sup), _dedup_recent(res)
    except Exception:  # noqa: BLE001 — fail-closed
        return [], []


def _volume_trend(df) -> str:
    """Classify recent volume as increasing / decreasing / neutral.

    Compares the last 5-bar average volume to the prior 20-bar average: > +20% ->
    "increasing", < -20% -> "decreasing", else "neutral". Fail-closed -> "neutral".
    """
    try:
        vol = df["Volume"].astype(float)
        if len(vol) < 25:
            return "neutral"
        last5 = float(vol.tail(5).mean())
        prior20 = float(vol.tail(25).head(20).mean())
        if prior20 <= 0:
            return "neutral"
        ratio = last5 / prior20
        if ratio > 1.2:
            return "increasing"
        if ratio < 0.8:
            return "decreasing"
        return "neutral"
    except Exception:  # noqa: BLE001 — fail-closed
        return "neutral"


def _candlestick_pattern(df) -> str:
    """Detect a single candlestick pattern from the last (up to 5) candles.

    Detection rules (evaluated on the most recent candle; engulfing also reads the
    prior candle). ``rng = high - low``; ``body = abs(close - open)``:

    * **doji** — ``body <= 0.1 * rng``: open ≈ close (indecision).
    * **bullish_engulfing** — prior candle red (close<open), current green
      (close>open), current body engulfs the prior body
      (``open <= prev_close`` and ``close >= prev_open``).
    * **bearish_engulfing** — prior green, current red, current body engulfs prior
      (``open >= prev_close`` and ``close <= prev_open``).
    * **hammer** — small body in the TOP third of the range with a long lower
      shadow (``lower_shadow >= 2*body`` and ``upper_shadow <= body``).
    * **shooting_star** — small body in the BOTTOM third with a long upper shadow
      (``upper_shadow >= 2*body`` and ``lower_shadow <= body``).
    * **none** — no pattern matches.

    Order of precedence: doji -> engulfing -> hammer/shooting_star -> none.
    Fail-closed -> "none".
    """
    try:
        if len(df) < 2:
            return "none"
        o = float(df["Open"].iloc[-1])
        h = float(df["High"].iloc[-1])
        l = float(df["Low"].iloc[-1])
        c = float(df["Close"].iloc[-1])
        po = float(df["Open"].iloc[-2])
        pc = float(df["Close"].iloc[-2])

        rng = h - l
        if rng <= 0:
            return "none"
        body = abs(c - o)

        if body <= 0.1 * rng:
            return "doji"

        prev_red = pc < po
        prev_green = pc > po
        cur_green = c > o
        cur_red = c < o
        if prev_red and cur_green and o <= pc and c >= po:
            return "bullish_engulfing"
        if prev_green and cur_red and o >= pc and c <= po:
            return "bearish_engulfing"

        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l
        body_top = max(o, c)
        body_bottom = min(o, c)
        if (
            lower_shadow >= 2 * body
            and upper_shadow <= body
            and body_bottom >= l + 0.5 * rng
        ):
            return "hammer"
        if (
            upper_shadow >= 2 * body
            and lower_shadow <= body
            and body_top <= h - 0.5 * rng
        ):
            return "shooting_star"
        return "none"
    except Exception:  # noqa: BLE001 — fail-closed
        return "none"


# ---------------------------------------------------------------------------
# Kelly-lite sizing + risk/reward — RETAINED (tested directly)
# ---------------------------------------------------------------------------


def kelly_lite_position_size(risk_reward_ratio: float) -> float:
    """Half-Kelly position size as a portfolio fraction, clamped 2%–10%.

    win_rate = 0.55 (assumed); avg_win = risk_reward_ratio * 1.0; avg_loss = 1.0.
    kelly = win_rate - (1 - win_rate) / avg_win. position = clamp(kelly * 0.5,
    0.02, 0.10). A non-positive / tiny R:R degrades to the 2% floor.
    """
    rr = _finite(risk_reward_ratio) or 0.0
    avg_win = rr * 1.0
    if avg_win <= 0:
        return _POS_MIN
    kelly = _KELLY_WIN_RATE - (1.0 - _KELLY_WIN_RATE) / avg_win
    pos = kelly * _KELLY_FRACTION
    return round(max(_POS_MIN, min(_POS_MAX, pos)), 4)


def _risk_reward(entry: float, stop: float, target: float) -> float:
    """(target - entry) / (entry - stop), clamped to >= 0. 0.0 on a non-positive
    risk denominator (a stop at/above entry is not a valid long setup)."""
    e = _finite(entry)
    s = _finite(stop)
    tg = _finite(target)
    if e is None or s is None or tg is None:
        return 0.0
    risk = e - s
    if risk <= 0:
        return 0.0
    reward = tg - e
    if reward <= 0:
        return 0.0
    return round(reward / risk, 2)


# ---------------------------------------------------------------------------
# Volume / technical-confirmation helpers (pure code)
# ---------------------------------------------------------------------------


def _volume_trend_from_ratio(vol_ratio: Optional[float]) -> str:
    """Derive a volume_trend label from the 20-day volume ratio (Entry v3 rule).

    ``> 1.1`` -> "increasing", ``< 0.9`` -> "decreasing", else "flat".
    """
    vr = _finite(vol_ratio)
    if vr is None:
        return "flat"
    if vr > 1.1:
        return "increasing"
    if vr < 0.9:
        return "decreasing"
    return "flat"


def _short_confirmation(tech: dict) -> list:
    """Return the list of UNMET SHORT technical-confirmation conditions.

    SHORT requires ALL of: price > EMA20; EMA10 >= EMA20; RSI in [40, 68];
    (Vol_ratio_20d > 1.10 OR volume_trend == "increasing"); candlestick NOT
    bearish. An empty list means fully confirmed.
    """
    cp = tech["current_price"]
    ema10 = tech.get("ema10")
    ema20 = tech.get("ema20")
    rsi = tech.get("rsi")
    vr = _finite(tech.get("vol_ratio"))
    vtrend = tech.get("volume_trend", "flat")
    candle = tech.get("candle", "none")
    missing: list = []
    if ema20 is None or not (cp > ema20):
        missing.append(MISSING_CONDITION_REGISTRY["price_below_ema20"].text)
    if ema10 is None or ema20 is None or not (ema10 >= ema20):
        missing.append(MISSING_CONDITION_REGISTRY["ema10_below_ema20"].text)
    if rsi is None or not (40.0 <= rsi <= 68.0):
        missing.append(MISSING_CONDITION_REGISTRY["rsi_out_of_band"].text)
    if not ((vr is not None and vr > 1.10) or vtrend == "increasing"):
        missing.append(MISSING_CONDITION_REGISTRY["volume_not_confirmed"].text)
    if candle in _BEARISH_CANDLES:
        missing.append(MISSING_CONDITION_REGISTRY["bearish_candlestick"].text)
    return missing


def _mid_volume_state(tech: dict) -> str:
    """MID volume state: "healthy" | "neutral" | "unhealthy" (Entry v3 rule)."""
    rsi = tech.get("rsi")
    vr = _finite(tech.get("vol_ratio"))
    vtrend = tech.get("volume_trend", "flat")
    candle = tech.get("candle", "none")
    bearish = candle in _BEARISH_CANDLES
    vol_ok = (vr is not None and vr > 1.10) or vtrend == "increasing"
    if rsi is not None and 40.0 <= rsi <= 68.0 and vol_ok and not bearish:
        return "healthy"
    if rsi is not None and 35.0 <= rsi <= 70.0 and not bearish:
        return "neutral"
    return "unhealthy"


# ---------------------------------------------------------------------------
# Horizon-differentiated stop-loss helpers (purely technical; no cost basis)
# ---------------------------------------------------------------------------

_RISK_NOTE_SHORT = (
    "Exit if price breaks EMA20 on close, or nearest support with volume, "
    "or after 3–5 days without momentum"
)
_RISK_NOTE_MID = (
    "Reduce if breaks SMA50 - 1.5ATR with volume, or eps_revision deteriorates, "
    "or thesis weakens"
)
_RISK_NOTE_LONG = (
    "LONG止损主要看thesis破坏、估值过高、基本面恶化，不因EMA/SMA短期波动止损 / "
    "LONG stop is thesis/valuation-driven, not short-term technical"
)

# Unified LONG "valuation unreliable — technical reference only" degrade (Phase
# "Valuation stop-the-bleed", fix round). Emitted whenever the LONG entry cannot
# be anchored to a usable fair value — BOTH the irreconcilable-anchors path AND
# the missing / low-confidence anchor path use the SAME reason text + code +
# next_trigger, so the UI and Trading Desk always know WHY there is no LONG zone.
# This is reason/text propagation only — no numeric / threshold change.
_LONG_DEGRADE_CODE = "valuation_unreliable_technical_only"
_LONG_DEGRADE_REASON = (
    "LONG: valuation unreliable — technical reference only / "
    "估值不可靠——仅供技术参考"
)
_LONG_DEGRADE_TRIGGER = (
    "Reconcile valuation anchors before entry / 入场前需先校准估值锚"
)


def _short_stop(cp: float, nearest_support: Optional[float], atr: float) -> float:
    base = nearest_support if nearest_support is not None else (cp - atr)
    stop = max(base, cp - 1.0 * atr)
    return round(_clamp(stop, cp * 0.93, cp * 0.99), 2)


def _mid_stop(cp: float, sma50: Optional[float], atr: float) -> float:
    base = (sma50 - 1.5 * atr) if sma50 is not None else 0.0
    stop = max(base, cp - 2.0 * atr)
    return round(_clamp(stop, cp * 0.80, cp * 0.99), 2)


def _long_stop(cp: float, sma200: Optional[float], atr: float) -> float:
    base = sma200 if sma200 is not None else 0.0
    stop = max(base, cp - 3.0 * atr)
    return round(_clamp(stop, cp * 0.70, cp * 0.99), 2)


# ---------------------------------------------------------------------------
# Logic-result helper (the dict each branch returns)
# ---------------------------------------------------------------------------


def _logic(action: str, *, entry_low=None, entry_high=None, stop=None,
           sizing: str = _SIZE_NONE, reason: str = "",
           missing: Optional[list] = None, next_trigger: str = "",
           risk_note: str = "") -> dict:
    return {
        "action": action,
        "entry_zone_low": round(entry_low, 2) if entry_low is not None else None,
        "entry_zone_high": round(entry_high, 2) if entry_high is not None else None,
        "stop_loss_level": round(stop, 2) if stop is not None else None,
        "position_sizing": sizing,
        "reason": reason,
        "missing_conditions": list(missing or []),
        "next_trigger": next_trigger,
        "risk_note": risk_note,
    }


# ---------------------------------------------------------------------------
# _compute_initiate_logic — build a new position (no cost basis)
# ---------------------------------------------------------------------------


def _compute_initiate_logic(horizon: str, tech: dict) -> dict:
    cp = tech["current_price"]
    atr = tech["atr"]
    ema20 = tech.get("ema20")
    sma50 = tech.get("sma50")
    sma200 = tech.get("sma200")
    nearest_support = tech.get("nearest_support")
    fva = tech.get("fair_value_anchor")
    vr = _finite(tech.get("vol_ratio"))

    if horizon == "short":
        missing = _short_confirmation(tech)
        stop = _short_stop(cp, nearest_support, atr)
        if missing:
            return _logic(
                "wait", stop=stop, missing=missing,
                reason="SHORT: awaiting EMA trend + volume confirmation",
                next_trigger="Wait for EMA trend + volume confirmation",
                risk_note=_RISK_NOTE_SHORT,
            )
        dynamic_support = max(nearest_support or 0.0, ema20 or 0.0)
        if cp <= dynamic_support * 1.03:
            return _logic(
                "enter_or_add_small",
                entry_low=dynamic_support, entry_high=dynamic_support * 1.02,
                stop=stop, sizing=_SIZE_SHORT_INIT,
                reason="SHORT: confirmed fast-trend entry near dynamic support",
                risk_note=_RISK_NOTE_SHORT,
            )
        return _logic(
            "wait_for_pullback", stop=stop, sizing=_SIZE_REASSESS,
            reason="SHORT: trend confirmed but price extended above support",
            next_trigger=f"Wait for pullback to {dynamic_support:.2f}",
            risk_note=_RISK_NOTE_SHORT,
        )

    if horizon == "mid":
        state = _mid_volume_state(tech)
        stop = _mid_stop(cp, sma50, atr)
        base_low = max((sma50 - 0.5 * atr) if sma50 is not None else cp * 0.92, cp * 0.90)
        if state == "healthy":
            return _logic(
                "enter_partial_now", entry_low=base_low, entry_high=cp, stop=stop,
                sizing=_SIZE_MID_FULL,
                reason="MID: healthy volume/price — start a partial position now",
                risk_note=_RISK_NOTE_MID,
            )
        if state == "neutral":
            pullback_low = max((sma50 - atr) if sma50 is not None else cp * 0.90, cp * 0.90)
            pullback_high = max((sma50 + 0.5 * atr) if sma50 is not None else cp * 0.95, cp * 0.93)
            return _logic(
                "enter_on_pullback", entry_low=pullback_low, entry_high=pullback_high,
                stop=stop, sizing=_SIZE_SMALL,
                reason="MID: neutral volume — enter on a pullback toward SMA50",
                risk_note=_RISK_NOTE_MID,
            )
        # unhealthy
        wait_low = max((sma50 - 1.5 * atr) if sma50 is not None else cp * 0.87, cp * 0.85)
        wait_high = max((sma50 - 0.5 * atr) if sma50 is not None else cp * 0.92, cp * 0.90)
        return _logic(
            "wait_for_pullback", entry_low=wait_low, entry_high=wait_high, stop=stop,
            sizing=_SIZE_REASSESS,
            reason="MID: unhealthy volume/price — wait for a deeper pullback",
            next_trigger=f"Wait for pullback to {wait_low:.2f}–{wait_high:.2f}",
            risk_note=_RISK_NOTE_MID,
        )

    # long — Phase "Valuation stop-the-bleed": an irreconcilable / missing
    # valuation anchor degrades the LONG entry EXPLICITLY to a technical-only
    # reference. Never silently blend a garbage mid (e.g. relative $3.23 vs
    # analyst $112.50) into a margin-of-safety entry zone.
    if tech.get("valuation_unreliable"):
        stop = _long_stop(cp, sma200, atr)
        return _logic(
            "wait", stop=stop, sizing=_SIZE_REASSESS,
            reason=_LONG_DEGRADE_REASON,
            next_trigger=_LONG_DEGRADE_TRIGGER,
            risk_note=_RISK_NOTE_LONG,
        )

    # long — Phase 6C-B: when an app-computed fair value is present it overrides
    # the lib/valuation_anchor margin-of-safety band (entry zone high = the
    # conservative app fair_value_low; fair_value_mid is the anchor; the upside
    # target is taken from fair_value_high in _assemble).
    app_fv = tech.get("app_fair_value")
    if app_fv and app_fv.get("low") is not None:
        sma200v = sma200 if sma200 is not None else cp * 0.80
        stop = _long_stop(cp, sma200, atr)
        app_low = app_fv["low"]
        app_mid = app_fv.get("mid")
        entry_high = round(app_low, 2)
        entry_low = max(sma200v, nearest_support or 0.0, cp - 2.0 * atr, cp * 0.85)
        if entry_low >= entry_high:
            return _logic(
                "wait", stop=stop, sizing=_SIZE_NONE,
                reason="LONG: price above the app-computed margin-of-safety band",
                next_trigger=f"Wait for pullback below {entry_high:.2f}",
                risk_note=_RISK_NOTE_LONG,
            )
        action = "enter_partial_now" if cp <= entry_high else "enter_on_pullback"
        return _logic(
            action, entry_low=entry_low, entry_high=entry_high, stop=stop,
            sizing=_SIZE_LONG_TRANCHES,
            reason=(
                "LONG: build into the app-computed margin-of-safety band "
                f"(fair_value_mid≈{app_mid})"
            ),
            next_trigger=("" if action == "enter_partial_now"
                          else f"Wait for pullback to {entry_low:.2f}–{entry_high:.2f}"),
            risk_note=_RISK_NOTE_LONG,
        )

    # X3 (fix round 2): when an external/session band drove the card it is the
    # SINGLE source (F2). If we reach here with an external band set, the ``app_fv``
    # branch above could not form a usable margin-of-safety band (e.g. no
    # conservative floor / ``fair_value_low``). Rather than silently fall back to the
    # LOCAL ``fva_obj`` (the documented leak — confidence / conservative / anchor all
    # read from the local instance while the card claims the external band), degrade
    # to the technical-only reference so ZERO anchor-derived fields are read from the
    # local instance when an external band is present.
    if tech.get("external_band") is not None:
        stop = _long_stop(cp, sma200, atr)
        return _logic(
            "wait", stop=stop, sizing=_SIZE_REASSESS,
            reason=_LONG_DEGRADE_REASON, next_trigger=_LONG_DEGRADE_TRIGGER,
            risk_note=_RISK_NOTE_LONG,
        )

    # long — three-tier valuation-confidence margin-of-safety band (Entry v4).
    fva_obj = tech.get("fva_obj")
    confidence = getattr(fva_obj, "confidence", "low") if fva_obj is not None else "low"
    # Anchor Intel v2 (U1): conservative + analyst anchors mapped from the unified
    # AppFairValue producer (fair_value_low / analyst_target), replacing the retired
    # FairValueAnchor.conservative_anchor / .analyst_anchor. Entry-zone FORMULAS
    # (×0.90 high, ×0.85 medium) are unchanged — only the anchor inputs changed.
    conservative = _app_conservative_anchor(fva_obj)
    analyst = getattr(fva_obj, "analyst_target", None) if fva_obj is not None else None
    vp = tech.get("valuation_percentile", 0.5)
    sma200v = sma200 if sma200 is not None else cp * 0.80
    entry_low = max(sma200v, nearest_support or 0.0, cp - 2.0 * atr, cp * 0.85)
    volume_bonus = 0.05 if (vr is not None and vr >= 1.10) else 0.0
    stop = _long_stop(cp, sma200, atr)
    risk_note = _RISK_NOTE_LONG
    # LONG valuation soft check (non-blocking).
    if isinstance(vp, (int, float)) and vp >= 0.85:
        risk_note = risk_note + (
            " / Valuation percentile ≥ 0.85: consider trim_or_stop_adding "
            "估值≥85百分位：考虑减仓/停止加仓"
        )

    if confidence == "high" and conservative is not None:
        entry_high = min(conservative * (0.90 + volume_bonus), conservative)
        if entry_low >= entry_high:
            return _logic(
                "wait", stop=stop, sizing=_SIZE_NONE,
                reason="Insufficient margin of safety at current price",
                next_trigger=f"Wait for price to fall below {entry_high:.2f}",
                risk_note=risk_note,
            )
        action = "enter_partial_now" if cp <= entry_high else "enter_on_pullback"
        return _logic(
            action, entry_low=entry_low, entry_high=entry_high, stop=stop,
            sizing=_SIZE_LONG_TRANCHES,
            reason="LONG (high-confidence valuation): build into the margin-of-safety band",
            next_trigger=("" if action == "enter_partial_now"
                          else f"Wait for pullback to {entry_low:.2f}–{entry_high:.2f}"),
            risk_note=risk_note,
        )
    if confidence == "medium" and analyst is not None:
        entry_high = analyst * (0.85 + volume_bonus * 0.5)
        if entry_low >= entry_high:
            return _logic(
                "wait", stop=stop, sizing=_SIZE_NONE,
                reason="Insufficient margin of safety at current price",
                next_trigger=f"Wait for price to fall below {entry_high:.2f}",
                risk_note=risk_note,
            )
        action = "enter_partial_now" if cp <= entry_high else "enter_on_pullback"
        return _logic(
            action, entry_low=entry_low, entry_high=entry_high, stop=stop,
            sizing=_SIZE_SMALL,
            reason="LONG (medium-confidence valuation): small starter into the margin-of-safety band",
            next_trigger=("" if action == "enter_partial_now"
                          else f"Wait for pullback to {entry_low:.2f}–{entry_high:.2f}"),
            risk_note=risk_note,
        )
    # low confidence / missing anchor — no usable fair value to anchor a LONG
    # zone. Emit the SAME explicit degrade as the irreconcilable path (unified
    # reason/code) so the UI + Trading Desk always know WHY there is no LONG zone.
    return _logic(
        "wait", stop=stop, sizing=_SIZE_REASSESS,
        reason=_LONG_DEGRADE_REASON,
        next_trigger=_LONG_DEGRADE_TRIGGER,
        risk_note=risk_note,
    )


# ---------------------------------------------------------------------------
# _compute_add_logic — add to an existing position (uses cost basis)
# ---------------------------------------------------------------------------


def _compute_add_logic(horizon: str, cost_basis: float, tech: dict, *,
                       thesis_status: str, eps_revision_direction: str,
                       valuation_percentile: float) -> dict:
    cp = tech["current_price"]
    atr = tech["atr"]
    ema20 = tech.get("ema20")
    sma50 = tech.get("sma50")
    sma200 = tech.get("sma200")
    nearest_support = tech.get("nearest_support")
    cb = cost_basis

    if horizon == "short":
        stop = _short_stop(cp, nearest_support, atr)
        if cp < cb:
            return _logic("wait_or_cut", stop=stop, sizing=_SIZE_NONE,
                          reason="SHORT: never average down losing position",
                          next_trigger="Cut or wait — do not add to a losing short-horizon position",
                          risk_note=_RISK_NOTE_SHORT)
        if cp > cb * 1.15:
            return _logic("wait", stop=stop, sizing=_SIZE_NONE,
                          reason="SHORT: price >15% above cost, no chasing",
                          next_trigger="Wait for a pullback toward cost before adding",
                          risk_note=_RISK_NOTE_SHORT)
        missing = _short_confirmation(tech)
        if cb * 1.03 <= cp <= cb * 1.15 and not missing:
            dynamic_support = max(nearest_support or 0.0, ema20 or 0.0)
            return _logic("enter_or_add_small",
                          entry_low=dynamic_support, entry_high=min(cp, cb * 1.10),
                          stop=stop, sizing=_SIZE_SMALL,
                          reason="SHORT: confirmed trend, small add near support",
                          risk_note=_RISK_NOTE_SHORT)
        return _logic("hold", stop=stop, sizing=_SIZE_NONE,
                      reason="SHORT: hold — add conditions not met",
                      missing=missing, risk_note=_RISK_NOTE_SHORT)

    if horizon == "mid":
        stop = _mid_stop(cp, sma50, atr)
        state = _mid_volume_state(tech)
        if cp > cb * 1.15:
            return _logic("wait", stop=stop, sizing=_SIZE_NONE,
                          reason="MID: price >15% above cost, wait",
                          next_trigger="Wait for a pullback toward cost before adding",
                          risk_note=_RISK_NOTE_MID)
        if cb * 1.05 <= cp <= cb * 1.15 and state == "healthy":
            entry_low = nearest_support if nearest_support is not None else cp * 0.97
            return _logic("add_small", entry_low=entry_low, entry_high=cb * 1.10,
                          stop=stop, sizing=_SIZE_SMALL,
                          reason="MID: healthy volume, small add above cost",
                          risk_note=_RISK_NOTE_MID)
        if cb <= cp < cb * 1.05 and thesis_status == "intact" and state in ("healthy", "neutral"):
            # In-the-money but below the +5% add band: give an actionable
            # add-on-pullback zone toward SMA50 / support (so the card is not empty).
            pullback_low = max((sma50 - atr) if sma50 is not None else cp * 0.95, cp * 0.95)
            pullback_low = min(pullback_low, cp)  # never above current price
            return _logic("enter_on_pullback", entry_low=pullback_low, entry_high=cp,
                          stop=stop, sizing=_SIZE_SMALL,
                          reason="MID: in-the-money but below the add band — add on a pullback toward SMA50/support",
                          next_trigger=f"Add on a pullback to {pullback_low:.2f}, or above {cb * 1.05:.2f} on strength",
                          risk_note=_RISK_NOTE_MID)
        if cp < cb and thesis_status == "intact" and eps_revision_direction != "deteriorating":
            return _logic("average_down_small", entry_low=cp - atr, entry_high=cp,
                          stop=stop, sizing=_SIZE_AVG_DOWN_SMALL,
                          reason="MID: thesis intact, small average-down",
                          risk_note="Reset stop after averaging down")
        return _logic("hold", stop=stop, sizing=_SIZE_NONE,
                      reason="MID: hold — add conditions not met",
                      risk_note=_RISK_NOTE_MID)

    # long
    stop = _long_stop(cp, sma200, atr)
    if thesis_status != "intact":
        return _logic("wait", stop=stop, sizing=_SIZE_NONE,
                      reason="LONG add requires thesis intact",
                      next_trigger="Wait for the thesis to be re-confirmed",
                      risk_note=_RISK_NOTE_LONG)
    if cp > cb * 1.20:
        return _logic("wait", stop=stop, sizing=_SIZE_NONE,
                      reason="LONG: price >20% above cost, wait",
                      next_trigger="Wait for a pullback toward cost before adding",
                      risk_note=_RISK_NOTE_LONG)
    if cp < cb and thesis_status == "intact":
        return _logic("average_down", entry_low=cp - 1.5 * atr, entry_high=cp,
                      stop=stop, sizing=_SIZE_SMALL,
                      reason="LONG: thesis intact, average-down into weakness",
                      risk_note=_RISK_NOTE_LONG)
    if cb <= cp <= cb * 1.20 and valuation_percentile < 0.50:
        anchor = max(sma200 or 0.0, nearest_support or 0.0)
        entry_low = anchor if anchor > 0 else cp * 0.95
        return _logic("add_partial", entry_low=entry_low, entry_high=cp,
                      stop=stop, sizing=_SIZE_ADD_PARTIAL,
                      reason="LONG: cheap valuation, partial add in the cost-to-+20% band",
                      risk_note=_RISK_NOTE_LONG)
    if cb <= cp <= cb * 1.20 and 0.50 <= valuation_percentile < 0.70:
        # 0.50–0.70: mid-rich valuation — a tiny add only (≥0.70 is blocked by the
        # fundamental gate before we reach this branch).
        anchor = max(sma200 or 0.0, nearest_support or 0.0)
        entry_low = anchor if anchor > 0 else cp * 0.95
        return _logic("add_tiny", entry_low=entry_low, entry_high=cp,
                      stop=stop, sizing=_SIZE_ADD_TINY,
                      reason="LONG: mid-rich valuation, tiny add in the cost-to-+20% band",
                      risk_note=_RISK_NOTE_LONG)
    return _logic("hold", stop=stop, sizing=_SIZE_NONE,
                  reason="LONG: hold — add conditions not met",
                  risk_note=_RISK_NOTE_LONG)


# ---------------------------------------------------------------------------
# compute_price_levels — pure code, no LLM
# ---------------------------------------------------------------------------

# Sourced from the registry (above) so the emitted strings stay identical.
_GATE_REASON_EPS = MISSING_CONDITION_REGISTRY["eps_deteriorating"].text
_GATE_REASON_VAL = MISSING_CONDITION_REGISTRY["valuation_stretched"].text


def _normalize_horizon(h) -> str:
    h = (h or "mid").strip().lower()
    return h if h in ("short", "mid", "long") else "mid"


def _read_equity_research_result(ticker: str) -> dict:
    """Read the app-computed fair value for ``ticker`` from session state (Phase 6C-B).

    Returns ``st.session_state["equity_research_results"][ticker]`` (a dict written
    by :func:`lib.equity_valuation.store_equity_research_result`) or ``{}`` when
    absent / no Streamlit runtime. Fully fail-closed — never raises.
    """
    try:
        import streamlit as st

        tk = (ticker or "").upper().strip()
        results = st.session_state.get("equity_research_results", {}) or {}
        rec = results.get(tk, {})
        return rec if isinstance(rec, dict) else {}
    except Exception:  # noqa: BLE001 — fail-closed (no Streamlit runtime / absent)
        return {}


# Add-scenario fine actions that the Existing Position Risk Overlay sizes (the
# market-based zone has already been established; cost_basis enters ONLY here).
_ADDABLE_ACTIONS = (
    "enter_or_add_small", "add_small", "add_partial", "add_tiny",
    "average_down", "average_down_small", "enter_partial_now", "enter_on_pullback",
)


def _gather_portfolio(ticker: str, current_price: float, holding, shares: float) -> dict:
    """Step 0 portfolio context (fail-closed): total assets, this holding's value,
    and its current portfolio weight.

    ``total_assets`` = Σ(active holding shares × price) + cash, where the analyzed
    ticker is valued at ``current_price`` and every OTHER active holding is valued
    at its own cost basis (a deterministic, free, no-fetch proxy — we never call a
    paid API or fetch N more quotes here). Reads are fail-closed; any failure
    returns zeros + default :class:`~lib.holdings.PortfolioSettings`.
    """
    out = {
        "total_assets": 0.0,
        "current_holding_value": 0.0,
        "portfolio_weight_current": 0.0,
        "cash": 0.0,
        "settings": None,
    }
    try:
        from lib.holdings import (
            load_holdings, load_cash_position, load_portfolio_settings, PortfolioSettings,
        )

        settings = load_portfolio_settings()
        if not isinstance(settings, PortfolioSettings):
            settings = PortfolioSettings()
        cash = _finite(load_cash_position()) or 0.0
        total = cash
        active = [h for h in (load_holdings() or [])
                  if getattr(h, "status", "active") == "active"]
        for h in active:
            sh = _finite(getattr(h, "shares", 0.0)) or 0.0
            tk = (getattr(h, "ticker", "") or "").upper().strip()
            price = current_price if tk == ticker else (_finite(getattr(h, "cost_basis", 0.0)) or 0.0)
            total += sh * price
        chv = (shares * current_price) if (holding is not None and shares > 0) else 0.0
        out.update(
            total_assets=total,
            current_holding_value=chv,
            portfolio_weight_current=(chv / total if total > 0 else 0.0),
            cash=cash,
            settings=settings,
        )
    except Exception:  # noqa: BLE001 — fail-closed
        try:
            from lib.holdings import PortfolioSettings
            out["settings"] = PortfolioSettings()
        except Exception:  # noqa: BLE001
            out["settings"] = None
    return out


def _apply_add_overlay(logic: dict, horizon: str, tech: dict, holding,
                       portfolio: dict, thesis_status: str) -> tuple:
    """Existing Position Risk Overlay (add scenario only) — Entry v4 Step 5.

    The market-based entry zone in ``logic`` was computed WITHOUT cost basis; this
    overlay is the ONLY place cost basis + portfolio context enter an add. It sizes
    a share estimate against the single-name position limit and (SHORT/MID) the
    risk-to-stop budget, derives the projected weight and blended cost, and may
    override the action to ``hold`` / ``wait`` when a limit is breached. LONG
    checks the position limit + thesis intactness only (no risk-to-stop).

    Returns ``(logic, overlay)`` where ``overlay`` carries the new
    ``risk_overlay_*`` / ``portfolio_weight_after_add`` / ``blended_cost_after_add``
    fields. Fully fail-closed (a pass-through on any data gap).
    """
    overlay = {
        "risk_overlay_passed": True,
        "risk_overlay_note": "",
        "portfolio_weight_after_add": portfolio.get("portfolio_weight_current", 0.0),
        "blended_cost_after_add": None,
    }
    settings = portfolio.get("settings")
    if settings is None:
        return logic, overlay
    cp = tech["current_price"]
    action = logic.get("action")
    entry_low = logic.get("entry_zone_low")
    stop = logic.get("stop_loss_level")
    total = portfolio.get("total_assets", 0.0) or 0.0
    chv = portfolio.get("current_holding_value", 0.0) or 0.0
    cost_basis = _finite(getattr(holding, "cost_basis", None))
    cur_shares = _finite(getattr(holding, "shares", None)) or 0.0

    # Only size genuine adds that produced a zone; otherwise pass through.
    if action not in _ADDABLE_ACTIONS or entry_low is None or total <= 0 or cp <= 0:
        return logic, overlay

    max_pos = settings.max_position_pct
    new_shares = (total * max_pos - chv) / cp
    if new_shares <= 0:
        logic["action"] = "hold"
        logic["position_sizing"] = _SIZE_NONE
        overlay["risk_overlay_passed"] = False
        overlay["risk_overlay_note"] = "Position at max limit / 仓位已达上限"
        return logic, overlay

    def _weight_and_blend(ns: float) -> None:
        overlay["portfolio_weight_after_add"] = round((chv + ns * cp) / total, 4) if total > 0 else 0.0
        if cost_basis and (cur_shares + ns) > 0:
            overlay["blended_cost_after_add"] = round(
                (cur_shares * cost_basis + ns * cp) / (cur_shares + ns), 2)

    _weight_and_blend(new_shares)

    if horizon in ("short", "mid"):
        max_loss = total * (settings.short_max_loss_pct if horizon == "short"
                            else settings.mid_max_loss_pct)
        if stop is not None and (entry_low - stop) > 0:
            risk_amount = (entry_low - stop) * new_shares
            if risk_amount > max_loss:
                new_shares = max_loss / (entry_low - stop)
                _weight_and_blend(new_shares)
                if new_shares < 1:
                    logic["action"] = "hold"
                    logic["position_sizing"] = _SIZE_NONE
                    overlay["risk_overlay_passed"] = False
                    overlay["risk_overlay_note"] = (
                        "Risk budget exceeded; position size too small / 风险预算超限，仓位过小"
                    )
                    return logic, overlay
    else:  # long — position limit + thesis intactness only (no risk-to-stop stop)
        if overlay["portfolio_weight_after_add"] > max_pos:
            logic["action"] = "hold"
            logic["position_sizing"] = _SIZE_NONE
            overlay["risk_overlay_passed"] = False
            overlay["risk_overlay_note"] = "LONG position at max limit / LONG仓位已达上限"
            return logic, overlay
        if thesis_status != "intact":
            logic["action"] = "wait"
            logic["position_sizing"] = _SIZE_NONE
            overlay["risk_overlay_passed"] = False
            overlay["risk_overlay_note"] = "LONG add requires thesis intact / LONG加仓需逻辑完好"
            return logic, overlay

    logic["position_sizing"] = (
        f"{new_shares:.0f} shares (~{overlay['portfolio_weight_after_add']:.1%} of portfolio) "
        f"/ 约{new_shares:.0f}股"
    )
    return logic, overlay


def compute_price_levels(
    ticker: str,
    holding=None,
    *,
    thesis_status: str = "intact",
    horizon: Optional[str] = None,
    eps_revision_direction: str = "unknown",
    valuation_percentile: float = 0.5,
    scenario: str = "initiate",
    app_fair_value: Optional[dict] = None,
    allow_fetch: bool = False,
) -> PriceLevelResult:
    """Compute the horizon-native, scenario-aware entry strategy for ``ticker``.

    Pure code (no LLM). ``scenario`` is auto-resolved: "add" when ``holding`` is
    not None and ``holding.shares > 0``, else "initiate"; it becomes "manage"
    internally when ``thesis_status == "broken"``. The universal thesis gate
    (Step 1) and fundamental hard gate (Step 2) can block entry on any horizon
    before the initiate/add branch (Step 3); Step 4 runs universal post-compute
    (stop-vs-zone sanity, entry_status, risk_reward_ratio). Fail-closed: on any
    data failure a well-formed ``data_source="fixture"`` result is returned.
    ``approved_for_execution`` is ALWAYS ``False``.

    **Anchor Intel v2 r2 (X1 — fail-closed network discipline):** ``allow_fetch``
    distinguishes the two caller classes and DEFAULTS to ``False`` (fail-closed):

    * Page paths (the Trading Desk — ``pages/9`` — and ``build_order_recommendation``)
      pass ``allow_fetch=True``; ``_gather_technicals`` may then live-compute the
      unified fair value (``compute_app_fair_value`` WITH the cyclical band fetcher).
    * The ranking / Cockpit-refresh path (``opportunity_ranker.rank_opportunities``)
      does NOT pass it, so it stays ``False``: ``_gather_technicals`` NEVER reaches a
      live ``compute_app_fair_value`` / ``fetch_cyclical_band_history``. On that path
      the fair value comes ONLY from a cached anchor band handed in via
      ``app_fair_value``; when none is cached the LONG entry degrades honestly
      (``fair_value_source="anchor_not_cached"``, no zone) rather than fabricating a
      ``current_price``-derived proxy.
    """
    ticker = (ticker or "").upper().strip()
    cost_basis = _finite(getattr(holding, "cost_basis", None))
    shares = _finite(getattr(holding, "shares", None)) or 0.0
    hz = _normalize_horizon(horizon or getattr(holding, "horizon", "mid"))
    try:
        vp = float(valuation_percentile)
    except (TypeError, ValueError):
        vp = 0.5
    status = (thesis_status or "intact").strip().lower()

    # Resolve scenario (add requires a real position).
    if holding is not None and shares > 0 and cost_basis is not None and cost_basis > 0:
        scenario = "add"
    else:
        scenario = "initiate"

    tech = _gather_technicals(ticker, hz, vp, allow_fetch=allow_fetch)
    cp = tech["current_price"]

    # --- Step 0 (cont.) — App-computed fair value (Phase 6C-B + stop-bleed) -
    # Resolve the fair-value band consumed by the LONG path. Priority:
    #   1. ``app_fair_value`` kwarg — the Cockpit cache hand-off (network-free
    #      enrichment passes a fresh cached anchor here).
    #   2. ``st.session_state["equity_research_results"]`` — the Equity page.
    # A high/medium-confidence band overrides the lib/valuation_anchor.py result:
    # fair_value_mid becomes the primary anchor, fair_value_low the conservative
    # entry floor, fair_value_high the upside target (LONG). An
    # ``anchors_irreconcilable`` band (Task 1) NEVER seeds an entry zone — it
    # flags the LONG path to degrade to a technical-only reference.
    band = app_fair_value if (isinstance(app_fair_value, dict) and app_fair_value) else None
    if band is None:
        equity_result = _read_equity_research_result(ticker)
        band = equity_result if equity_result else None
    if band:
        _bstate = str(band.get("blend_state", "") or "").lower()
        _bconf = str(band.get("confidence", "") or "").lower()
        # U3 single-source discipline: when an external/session band drives the
        # card, ITS epoch is the card's epoch (not the local fva_obj's).
        _band_epoch = str(band.get("computed_at") or "")
        if _bstate == "anchors_irreconcilable":
            # Anchor Intel v2 r2 (F2): an external/session irreconcilable band
            # drives the WHOLE card. EVERY anchor-derived field comes from it — the
            # healthy local fva_obj must NOT leak a confident valuation wearing the
            # external timestamp. ``external_band`` is the single marker _assemble
            # reads so confidence, conservative anchor and the fair-value scalar all
            # follow the band, not the local instance. For irreconcilable: no local
            # scalar (anchor None), confidence low (or the band's own), conservative
            # None, epoch from the band, valuation_unreliable degrade.
            tech["valuation_unreliable"] = True
            tech["fair_value_anchor"] = None
            tech["external_band"] = {
                "blend_state": "anchors_irreconcilable",
                "confidence": _bconf or "low",
                "anchor": None,
                "conservative": None,
                "epoch": _band_epoch,
            }
            if _band_epoch:
                tech["fair_value_computed_at"] = _band_epoch
        elif _bconf in ("high", "medium"):
            app_low = _finite(band.get("fair_value_low"))
            app_mid = _finite(band.get("fair_value_mid"))
            app_high = _finite(band.get("fair_value_high"))
            if app_mid is not None and app_mid > 0:
                tech["app_fair_value"] = {
                    "low": app_low,
                    "mid": app_mid,
                    "high": app_high,
                    "confidence": _bconf,
                }
                tech["fair_value_anchor"] = round(app_mid, 2)
                # F2: mark the external band as the single source so _assemble
                # takes confidence + conservative anchor + epoch from THIS band and
                # never reads the local fva_obj for those fields.
                tech["external_band"] = {
                    "blend_state": _bstate or "blended",
                    "confidence": _bconf,
                    "anchor": round(app_mid, 2),
                    "conservative": (app_low if (app_low is not None and app_low > 0)
                                     else None),
                    "epoch": _band_epoch,
                }
                if _band_epoch:
                    tech["fair_value_computed_at"] = _band_epoch

    # X1 (R8): on the network-free ranking / Cockpit-refresh path
    # (``allow_fetch=False``) the fair value can come ONLY from a cached anchor band
    # handed in via ``app_fair_value``. When none was cached (cold cache) there is no
    # anchor to build a LONG margin-of-safety zone from — and we MUST NOT live-compute
    # one here (that would be the R8 network violation). Degrade honestly: flag the
    # LONG path AND record the provenance so the card reads ``anchor_not_cached``,
    # never a fabricated ``current_price``-derived proxy. (The page paths set
    # ``allow_fetch=True`` and have already live-computed ``fva_obj`` above, so this
    # never fires for them.)
    if not allow_fetch and band is None:
        tech["valuation_unreliable"] = True
        tech["anchor_not_cached"] = True
        # R3 (review): a missing anchor must be None, never a back-computed proxy.
        # When OHLCV is unavailable on the cold path ``_gather_technicals`` returns
        # the ``_fixture`` dict, which seeds ``fair_value_anchor=cp*0.85`` so the
        # *technical* logic stays well-formed. That fabricated scalar must NOT ride
        # through under ``anchor_not_cached`` — clear it explicitly so the honest
        # degrade contract holds (anchor None, no zone, valuation_unreliable, token).
        tech["fair_value_anchor"] = None

    # The locally-computed AppFairValue can itself be irreconcilable (its
    # inter-method dispersion gate collapsed the band); that likewise degrades the
    # LONG entry to a technical-only reference. X3 (fix round 2): this LOCAL signal
    # may degrade the card ONLY when NO external/session band drives it. When an
    # external band is present it is the SINGLE source (F2) — a healthy external band
    # must NOT be degraded by a stale / irreconcilable LOCAL instance (the inverse
    # leak the prior round missed: §11 only covered irreconcilable-external + healthy
    # -local, never healthy-external + irreconcilable-local).
    if tech.get("external_band") is None:
        _fva_obj = tech.get("fva_obj")
        if str(getattr(_fva_obj, "blend_state", "") or "") == "anchors_irreconcilable":
            tech["valuation_unreliable"] = True

    # --- Step 0 (cont.) — Portfolio context (fail-closed; cost-free proxy) -
    portfolio = _gather_portfolio(ticker, cp, holding, shares)

    # --- Step 1 — Universal thesis gate -----------------------------------
    if status == "broken":
        logic = _logic(
            "avoid", reason="thesis broken — avoid entry, reassess exit",
            next_trigger="Wait for thesis to be re-established",
            risk_note="Thesis broken: do not add; reassess the exit plan",
        )
        return _assemble(ticker, "manage", hz, cost_basis, tech, logic, portfolio)

    # --- Step 2 — Fundamental hard gate (all horizons) --------------------
    gate_missing: list = []
    gate_trigger = ""
    if eps_revision_direction == "deteriorating":
        gate_missing.append(_GATE_REASON_EPS)
        gate_trigger = "Wait for EPS revisions to stabilize / improve"
    if vp >= 0.70:
        gate_missing.append(_GATE_REASON_VAL)
        gate_trigger = gate_trigger or "Wait for valuation to compress below the 70th percentile"
    if gate_missing:
        logic = _logic(
            "wait", reason="Fundamental gate failed: " + "; ".join(gate_missing),
            missing=gate_missing, next_trigger=gate_trigger,
            risk_note="Fundamentals do not support a new entry here",
        )
        return _assemble(ticker, scenario, hz, cost_basis, tech, logic, portfolio)

    # --- Step 3 — Scenario branch -----------------------------------------
    overlay = None
    if scenario == "add":
        logic = _compute_add_logic(
            hz, cost_basis, tech, thesis_status=status,
            eps_revision_direction=eps_revision_direction, valuation_percentile=vp,
        )
        # --- Step 5 — Existing Position Risk Overlay (cost basis enters here) -
        logic, overlay = _apply_add_overlay(logic, hz, tech, holding, portfolio, status)
    else:
        logic = _compute_initiate_logic(hz, tech)

    return _assemble(ticker, scenario, hz, cost_basis, tech, logic, portfolio, overlay)


def _gather_technicals(ticker: str, hz: str, valuation_percentile: float,
                       *, allow_fetch: bool = False) -> dict:
    """Fetch the technical snapshot + fair-value anchor (Step 0). Fail-closed.

    On any failure returns a deterministic fixture dict (``data_source="fixture"``)
    seeded with a ~$100 price proxy and a ~3% ATR so the downstream logic still
    produces a well-formed result.

    **Anchor Intel v2 r2 (X1):** the OHLCV / technical snapshot is always loaded
    from the local cache (network-free). The fair-value producer
    (``compute_app_fair_value``), however, performs a live ``_fetch_raw`` (and, with
    the cyclical fetcher, a multi-year price fetch). It is therefore invoked ONLY
    when ``allow_fetch`` is ``True`` (the page paths). On the ranking / Cockpit
    -refresh path (``allow_fetch=False``) it is NEVER imported or called: there is no
    live ``fva_obj`` and no fabricated proxy (``fair_value_anchor=None``); the fair
    value, if any, arrives via the cached ``app_fair_value`` band in
    ``compute_price_levels``.
    """
    def _fixture(cp: float = 100.0) -> dict:
        atr = round(cp * 0.03, 2)
        return {
            "current_price": round(cp, 2), "ema10": None, "ema20": None,
            "sma50": None, "sma200": None, "rsi": None, "adx": None, "atr": atr,
            "vol_ratio": None, "volume_trend": "neutral", "candle": "none",
            "nearest_support": None, "nearest_resistance": None,
            "above_sma200": False, "pct_from_52w_high": None,
            "fair_value_anchor": round(cp * 0.85, 2),
            "fva_obj": None, "fair_value_computed_at": "", "valuation_percentile": 0.5,
            "support_levels": [], "resistance_levels": [], "data_source": _FIXTURE,
        }

    try:
        from ui_utils import load_ohlcv
        from lib.technical import snapshot

        df = load_ohlcv(ticker, "6mo")
        if df is None or len(df) < 30:
            return _fixture()

        snap = snapshot(df)
        cp = _finite(snap.get("price"))
        if cp is None or cp <= 0:
            return _fixture()
        atr = _finite(snap.get("ATR_14"))
        if atr is None or atr <= 0:
            atr = round(cp * 0.03, 2)
        vol_ratio = _finite(snap.get("Vol_ratio_20d"))
        supports, resistances = _significant_levels(df)
        # Anchor Intelligence v2 (U1 + r2/F1 + X1): the SINGLE fair-value producer is
        # lib.equity_valuation.compute_app_fair_value (AppFairValue). Calling it does
        # a live ``_fetch_raw`` (network), so it is gated on ``allow_fetch``:
        #   * Page paths (allow_fetch=True) — the Trading-Desk page-path call site, a
        #     page path, so the cyclical band fetch is permitted. We pass
        #     ``cyclical_history_fetcher`` so that when THIS surface is the first
        #     writer of the shared cache entry the band is still cyclical-capable (the
        #     fetcher is an underscore-prefixed param on the cached worker, excluded
        #     from the cache key — the Equity page and the Trading Desk therefore
        #     share one instance + one epoch per ticker).
        #   * Ranking / Cockpit-refresh path (allow_fetch=False) — the producer and
        #     the cyclical fetcher are NEVER imported or invoked here, so the path is
        #     structurally network-free (R8). ``fva_obj`` stays None and there is NO
        #     fabricated proxy (``fva`` None -> ``fair_value_anchor`` None); the fair
        #     value, if any, comes from the cached ``app_fair_value`` band upstream.
        fva_obj = None
        fva = None
        if allow_fetch:
            from lib.equity_valuation import (
                compute_app_fair_value, fetch_cyclical_band_history,
            )
            try:
                fva_obj = compute_app_fair_value(
                    ticker, cp, cyclical_history_fetcher=fetch_cyclical_band_history)
                _mid = _finite(getattr(fva_obj, "fair_value_mid", None))
                fva = _mid if (_mid is not None and _mid > 0) else round(cp * 0.85, 2)
            except Exception:  # noqa: BLE001 — fail-closed
                fva_obj = None
                fva = round(cp * 0.85, 2)
        candle = snap.get("candlestick_pattern") or _candlestick_pattern(df)
        return {
            "fva_obj": fva_obj,
            "fair_value_computed_at": str(getattr(fva_obj, "computed_at", "") or ""),
            "valuation_percentile": valuation_percentile,
            "current_price": round(cp, 2),
            "ema10": _finite(snap.get("EMA_10")),
            "ema20": _finite(snap.get("EMA_20")),
            "sma50": _finite(snap.get("SMA_50")),
            "sma200": _finite(snap.get("SMA_200")),
            "rsi": _finite(snap.get("RSI_14")),
            "adx": _finite(snap.get("ADX")),
            "atr": round(atr, 2),
            "vol_ratio": vol_ratio,
            "volume_trend": _volume_trend_from_ratio(vol_ratio),
            "candle": candle,
            "nearest_support": _finite(snap.get("nearest_support")),
            "nearest_resistance": _finite(snap.get("nearest_resistance")),
            "above_sma200": bool(snap.get("above_SMA200", False)),
            "pct_from_52w_high": _finite(snap.get("pct_from_52w_high")),
            "fair_value_anchor": _finite(fva),
            "support_levels": supports,
            "resistance_levels": resistances,
            "data_source": _LIVE,
        }
    except Exception:  # noqa: BLE001 — fully fail-closed
        return _fixture()


def _assemble(ticker: str, scenario: str, hz: str, cost_basis: Optional[float],
              tech: dict, logic: dict, portfolio: Optional[dict] = None,
              overlay: Optional[dict] = None) -> PriceLevelResult:
    """Universal post-compute (Step 6) + assemble the PriceLevelResult."""
    portfolio = portfolio or {}
    overlay = overlay or {}
    fva_obj = tech.get("fva_obj")
    # Anchor Intel v2 r2 (F2) — SINGLE source per card: when an external/session
    # band drives the card (``tech["external_band"]`` set by compute_price_levels),
    # EVERY anchor-derived field comes from THAT band — confidence, conservative
    # anchor, the fair-value scalar (cleared upstream) and the epoch — and the local
    # fva_obj is NOT read for any of them. This is the audit fix: previously only
    # the high/medium path overrode confidence + conservative, so an external
    # irreconcilable band leaked the healthy local confidence/anchor/conservative
    # while only the epoch + degrade flag switched. For an irreconcilable external
    # band the band carries confidence "low" + conservative None, so the card reads
    # honestly as "anchors irreconcilable", never as a confident local valuation
    # wearing an external timestamp.
    _ext = tech.get("external_band")
    if _ext:
        valuation_confidence = str(_ext.get("confidence") or "low")
        conservative_anchor = _ext.get("conservative")
    else:
        # No external band: the locally-computed AppFairValue drives. conservative
        # anchor == the tier-dependent _app_conservative_anchor mapping (U1); None
        # when the local band is suppressed (irreconcilable / no_anchor / low).
        valuation_confidence = (getattr(fva_obj, "confidence", "low")
                                if fva_obj is not None else "low")
        conservative_anchor = _app_conservative_anchor(fva_obj)
    cp = tech["current_price"]
    atr = tech["atr"]
    action = logic["action"]
    entry_low = logic["entry_zone_low"]
    entry_high = logic["entry_zone_high"]
    stop = logic["stop_loss_level"]
    reason = logic["reason"]

    # --- Step 4a — stop-vs-zone sanity -----------------------------------
    if entry_low is not None and stop is not None and stop >= entry_low:
        stop = round(entry_low * 0.97, 2)
        if stop < cp * 0.70:
            entry_low = entry_high = None
            action = "wait"
            reason = (reason + " / Stop-loss room insufficient").strip(" /")

    # --- legacy target (nearest resistance above price, else price + 3*ATR) -
    nearest_resistance = tech.get("nearest_resistance")
    res_above = [r for r in (tech.get("resistance_levels") or []) if r > cp]
    if nearest_resistance is not None and nearest_resistance > cp:
        target_price = round(nearest_resistance, 2)
    elif res_above:
        target_price = round(min(res_above), 2)
    else:
        target_price = round(cp + 3 * atr, 2)

    # --- Phase 6C-B — app-computed fair value source + upside target -------
    # ``fair_value_source`` provenance tokens:
    #   * "app_computed"   — an external/session AppFairValue band (high/medium)
    #                        drives the card (the Equity-page hand-off / Cockpit
    #                        cache enrichment).
    #   * "app_fair_value" — the locally-computed unified AppFairValue producer on
    #                        live data (Anchor Intel v2 r2 / C5 rename: was the
    #                        misleading "analyst_proxy" — there is no analyst proxy
    #                        anymore, the value comes from the unified producer).
    #   * "anchor_not_cached" — Anchor Intel v2 r2 (X1): the network-free ranking /
    #                        Cockpit-refresh path (allow_fetch=False) found no cached
    #                        anchor band; the LONG entry degraded honestly rather than
    #                        live-computing or fabricating a proxy.
    #   * "fixture"        — fail-closed fixture data.
    app_fv = tech.get("app_fair_value")
    if app_fv:
        fair_value_source = "app_computed"
        app_high = app_fv.get("high")
        if app_high is not None and app_high > cp:
            target_price = round(app_high, 2)  # fair_value_high is the upside target
    elif tech.get("anchor_not_cached"):
        fair_value_source = "anchor_not_cached"
    elif tech.get("data_source") == _LIVE:
        fair_value_source = "app_fair_value"
    else:
        fair_value_source = _FIXTURE

    # --- Step 4b — entry_status -------------------------------------------
    if entry_low is None:
        entry_status = "blocked" if action in ("wait", "avoid", "wait_or_cut") else "wait"
    elif entry_low <= cp <= entry_high:
        entry_status = "in_zone"
    elif cp > entry_high:
        entry_status = "above_zone"
    else:
        entry_status = "below_zone"

    # --- Step 4c — risk_reward_ratio --------------------------------------
    # Entry reference is current_price (legacy-compatible: keeps the Phase 6C-A
    # regression test green and the page's R:R column consistent). 0.0 when there
    # is no entry zone.
    if entry_low is not None and stop is not None:
        risk_reward_ratio = _risk_reward(cp, stop, target_price)
    else:
        risk_reward_ratio = 0.0

    # --- wait_target string for the page (above/below/blocked) ------------
    if entry_status == "above_zone":
        wait_target = logic.get("next_trigger") or (
            f"等待回调至 ${entry_low:.2f}–${entry_high:.2f} / "
            f"Wait for pullback to ${entry_low:.2f}–${entry_high:.2f}"
        )
    elif entry_status == "below_zone":
        wait_target = "等待企稳 / Wait for price stabilization"
    elif entry_low is None:
        wait_target = logic.get("next_trigger", "")
    else:
        wait_target = ""

    stop_field = round(stop, 2) if stop is not None else 0.0
    return PriceLevelResult(
        ticker=ticker,
        scenario=scenario,
        horizon=hz,
        current_price=round(cp, 2),
        cost_basis=cost_basis,
        ema10=tech.get("ema10"),
        ema20=tech.get("ema20"),
        sma50=tech.get("sma50"),
        sma200=tech.get("sma200"),
        atr_14=round(atr, 2),
        nearest_support=tech.get("nearest_support"),
        nearest_resistance=tech.get("nearest_resistance"),
        fair_value_anchor=tech.get("fair_value_anchor"),
        action=action,
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        stop_loss_level=(round(stop, 2) if stop is not None else None),
        position_sizing=logic["position_sizing"],
        reason=reason,
        missing_conditions=list(logic.get("missing_conditions") or []),
        next_trigger=logic.get("next_trigger", ""),
        risk_note=logic.get("risk_note", ""),
        entry_status=entry_status,
        risk_reward_ratio=risk_reward_ratio,
        data_source=tech.get("data_source", _FIXTURE),
        fair_value_source=fair_value_source,
        approved_for_execution=False,
        fair_value_computed_at=tech.get("fair_value_computed_at", ""),
        # --- v4 fields ---
        valuation_confidence=valuation_confidence,
        conservative_anchor=conservative_anchor,
        risk_overlay_passed=overlay.get("risk_overlay_passed", True),
        risk_overlay_note=overlay.get("risk_overlay_note", ""),
        portfolio_weight_current=round(portfolio.get("portfolio_weight_current", 0.0) or 0.0, 4),
        portfolio_weight_after_add=round(
            overlay.get("portfolio_weight_after_add",
                        portfolio.get("portfolio_weight_current", 0.0)) or 0.0, 4),
        blended_cost_after_add=overlay.get("blended_cost_after_add"),
        # --- legacy fields ---
        stop_loss=stop_field,
        target_price=target_price,
        position_size_pct=kelly_lite_position_size(risk_reward_ratio),
        support_levels=tech.get("support_levels", []),
        resistance_levels=tech.get("resistance_levels", []),
        volume_trend=tech.get("volume_trend", "neutral"),
        candlestick_pattern=tech.get("candle", "none"),
        entry_blocked=(entry_low is None),
        entry_blocked_reason=(reason if entry_low is None else ""),
        wait_target=wait_target,
    )


# ---------------------------------------------------------------------------
# Deterministic baseline action (code) — also the fail-closed narrative
# ---------------------------------------------------------------------------


def baseline_action(thesis_status: str, price_levels: PriceLevelResult) -> str:
    """Deterministic high-level action (add|hold|trim|exit|wait) from the levels.

    Maps the fine-grained ``PriceLevelResult.action`` + thesis status + entry
    gate + R:R into the narrative's five-label vocabulary. Used as the cache-key
    seed for the LLM narrative and as the fail-closed fallback.
    """
    status = (thesis_status or "intact").lower()
    rr = _finite(getattr(price_levels, "risk_reward_ratio", 0.0)) or 0.0
    action = getattr(price_levels, "action", "wait")
    if status == "broken" or action == "avoid":
        return "exit"
    # Entry gate: a blocked / out-of-zone price means we cannot buy here.
    if getattr(price_levels, "entry_blocked", False):
        return "wait"
    if getattr(price_levels, "entry_status", "in_zone") not in ("in_zone", ""):
        return "wait"
    if action in ("wait", "wait_for_pullback", "wait_or_cut"):
        return "wait"
    if action in ("reduce", "reduce_or_exit", "trim_or_stop_adding"):
        return "trim"
    if action in ("cut_loss", "exit"):
        return "exit"
    if rr < 1.5:
        return "wait"
    if status == "weakening":
        return "trim"
    if status == "watch":
        return "hold"
    if action in ("enter_partial_now", "enter_on_pullback", "enter_or_add_small",
                  "add_small", "add_partial", "add_tiny", "average_down",
                  "average_down_small"):
        return "add" if rr >= 2.0 else "hold"
    return "hold"


def _fallback_narrative(holding, price_levels: PriceLevelResult,
                        thesis_check, macro_regime: str) -> OrderNarrative:
    """Deterministic, code-only narrative (no LLM). Fail-closed default."""
    status = getattr(thesis_check, "thesis_status", "intact")
    action = baseline_action(status, price_levels)
    rr = _finite(getattr(price_levels, "risk_reward_ratio", 0.0)) or 0.0
    blocked = getattr(price_levels, "entry_blocked", False)
    entry_status = getattr(price_levels, "entry_status", "in_zone")
    next_trigger = getattr(price_levels, "next_trigger", "") or getattr(price_levels, "wait_target", "")
    fine_action = getattr(price_levels, "action", "wait")
    warning = ""
    if rr < 1.5 and not blocked:
        warning = f"Unfavorable risk/reward ({rr:.2f} < 1.5); waiting may be prudent."
    pattern = getattr(price_levels, "candlestick_pattern", "none")
    pat_note = "" if pattern == "none" else f" Recent candle: {pattern}."
    missing = getattr(price_levels, "missing_conditions", []) or []

    if blocked:
        reasoning = (
            f"Computed action is {fine_action}: {getattr(price_levels, 'reason', '')}. "
            f"Do not buy here.{pat_note}"
        )
        if missing:
            reasoning += " Missing: " + "; ".join(missing) + "."
        entry_note = "Entry zone unavailable — entry conditions not met."
    elif entry_status != "in_zone":
        reasoning = (
            f"Price is {entry_status.replace('_', ' ')}; computed action is "
            f"{fine_action}. {next_trigger}{pat_note}"
        )
        entry_note = (
            f"Entry zone {price_levels.entry_zone_low}–{price_levels.entry_zone_high}; "
            f"{next_trigger}"
        )
    else:
        reasoning = (
            f"Thesis is {status}; macro regime {macro_regime}. Computed "
            f"{getattr(price_levels, 'scenario', 'initiate')} action is "
            f"{fine_action} on the {getattr(price_levels, 'horizon', 'mid')} "
            f"horizon.{pat_note}"
        )
        entry_note = (
            f"Entry zone {price_levels.entry_zone_low}–{price_levels.entry_zone_high}."
        )

    return _finalize_bilingual(OrderNarrative(
        action_suggestion=action,
        action_reasoning=reasoning,
        entry_note=entry_note,
        stop_note=(
            f"Stop at {price_levels.stop_loss_level} "
            f"({getattr(price_levels, 'risk_note', '')[:120]})."
        ),
        target_note=f"Target {price_levels.target_price}.",
        risk_warning=warning,
        next_trigger_note=next_trigger,
        data_source=_FIXTURE,
    ))


# ---------------------------------------------------------------------------
# generate_order_narrative — one LLM call (synthesis only; no numbers invented)
# ---------------------------------------------------------------------------


def generate_order_narrative(holding, price_levels: PriceLevelResult,
                             thesis_check, macro_regime: str,
                             lang: str = "en") -> OrderNarrative:
    """One LLM call that synthesizes a narrative over the computed levels.

    The LLM must respect the computed numbers (it invents none): if ``action`` is
    "wait"/"avoid" the suggestion is "wait" and the reasoning explains
    ``missing_conditions``; if ``entry_status`` is "above_zone" it highlights the
    ``next_trigger``; if the risk/reward ratio is below 1.5 it flags it as
    unfavorable. Cached TTL=3600 keyed on
    ``(ticker, thesis_status, baseline_action, macro_regime, lang)``. Translated to
    Chinese when ``lang == "zh"``. Fail-closed to :func:`_fallback_narrative`.
    """
    ticker = getattr(price_levels, "ticker", "") or (getattr(holding, "ticker", "") or "")
    thesis_status = getattr(thesis_check, "thesis_status", "intact")
    code_action = baseline_action(thesis_status, price_levels)
    lang = lang if lang in ("en", "zh") else "en"
    try:
        return _generate_order_narrative_cached(
            ticker, thesis_status, code_action, (macro_regime or "unknown"), lang,
            _levels_payload(price_levels), getattr(holding, "thesis_text", "") or "",
        )
    except Exception:  # noqa: BLE001 — fail-closed
        return _fallback_narrative(holding, price_levels, thesis_check, macro_regime)


def _levels_payload(pl: PriceLevelResult) -> tuple:
    """Hashable snapshot of the computed levels for the cache key + prompt."""
    def _r(x, n=2):
        return round(float(x), n) if isinstance(x, (int, float)) else None

    return (
        _r(pl.current_price),
        _r(pl.entry_zone_low),
        _r(pl.entry_zone_high),
        _r(pl.stop_loss_level),
        _r(pl.target_price),
        _r(pl.atr_14),
        round(float(pl.risk_reward_ratio), 2),
        round(float(pl.position_size_pct), 4),
        pl.volume_trend,
        pl.candlestick_pattern,
        bool(pl.entry_blocked),
        pl.entry_status or "in_zone",
        pl.action or "wait",
        pl.scenario or "initiate",
        pl.horizon or "mid",
        pl.next_trigger or "",
        pl.risk_note or "",
        "; ".join(pl.missing_conditions or []),
        _r(pl.fair_value_anchor),
        pl.reason or "",
        # --- v4 additions (indices 20–24) ---
        pl.valuation_confidence or "low",
        _r(pl.conservative_anchor),
        bool(pl.risk_overlay_passed),
        pl.risk_overlay_note or "",
        round(float(pl.portfolio_weight_after_add or 0.0), 4),
    )


def _has_llm_api_key() -> bool:
    """True if an LLM API key is configured (without importing any LLM SDK)."""
    import os

    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        import streamlit as st

        return bool(st.secrets.get("ANTHROPIC_API_KEY"))
    except Exception:  # noqa: BLE001
        return False


def _generate_order_narrative_cached(ticker: str, thesis_status: str,
                                     code_action: str, macro_regime: str, lang: str,
                                     levels: tuple, thesis_text: str) -> OrderNarrative:
    """Cached LLM narrative synthesis (fail-closed)."""
    # Reconstruct a lightweight PriceLevelResult view for the fallback path.
    pl = PriceLevelResult(
        ticker=ticker,
        current_price=levels[0], entry_zone_low=levels[1], entry_zone_high=levels[2],
        stop_loss_level=levels[3], stop_loss=(levels[3] or 0.0), target_price=levels[4],
        atr_14=levels[5], risk_reward_ratio=levels[6], position_size_pct=levels[7],
        volume_trend=levels[8], candlestick_pattern=levels[9],
        entry_blocked=bool(levels[10]), entry_status=(levels[11] or "in_zone"),
        action=(levels[12] or "wait"), scenario=(levels[13] or "initiate"),
        horizon=(levels[14] or "mid"), next_trigger=(levels[15] or ""),
        risk_note=(levels[16] or ""),
        missing_conditions=[m for m in (levels[17] or "").split("; ") if m],
        fair_value_anchor=levels[18], reason=(levels[19] or ""),
        valuation_confidence=(levels[20] if len(levels) > 20 else "low"),
        conservative_anchor=(levels[21] if len(levels) > 21 else None),
        risk_overlay_passed=(bool(levels[22]) if len(levels) > 22 else True),
        risk_overlay_note=(levels[23] if len(levels) > 23 else ""),
        portfolio_weight_after_add=(levels[24] if len(levels) > 24 else 0.0),
    )

    class _TC:  # minimal thesis_check stand-in for the fallback
        pass

    _tc = _TC()
    _tc.thesis_status = thesis_status

    if not _has_llm_api_key():
        return _fallback_narrative(_FakeHolding(thesis_text), pl, _tc, macro_regime)

    try:
        from lib import llm_orchestrator

        rr = levels[6]
        entry_zone_str = (
            "BLOCKED (no entry zone)" if levels[10] else f"{levels[1]} - {levels[2]}"
        )
        levels_block = (
            f"scenario: {levels[13]}\n"
            f"horizon: {levels[14]}\n"
            f"computed_action: {levels[12]}\n"
            f"current_price: {levels[0]}\n"
            f"entry_zone: {entry_zone_str}\n"
            f"entry_status: {levels[11]}\n"
            f"entry_blocked: {levels[10]}\n"
            f"missing_conditions: {levels[17] or '(none)'}\n"
            f"next_trigger: {levels[15] or '(none)'}\n"
            f"stop_loss_level: {levels[3]} (technical; no cost basis)\n"
            f"risk_note: {levels[16] or '(none)'}\n"
            f"target_price: {levels[4]}\n"
            f"fair_value_anchor: {levels[18]}\n"
            f"valuation_confidence: {levels[20] if len(levels) > 20 else 'low'} (LONG anchor tier)\n"
            f"conservative_anchor: {levels[21] if len(levels) > 21 else None}\n"
            f"risk_overlay_passed: {bool(levels[22]) if len(levels) > 22 else True}\n"
            f"risk_overlay_note: {(levels[23] if len(levels) > 23 else '') or '(none)'}\n"
            f"portfolio_weight_after_add: {levels[24] if len(levels) > 24 else 0.0}\n"
            f"atr_14: {levels[5]}\n"
            f"risk_reward_ratio: {rr}\n"
            f"position_size_pct: {levels[7]}\n"
            f"volume_trend: {levels[8]}\n"
            f"candlestick_pattern: {levels[9]}"
        )
        system = (
            "You are a disciplined trading-desk analyst. You are given price levels "
            "that were ALL computed deterministically by code — you MUST NOT change "
            "any number; only synthesize a narrative over them. "
            "ENTRY GATE (binding): if computed_action is 'wait' or 'avoid', "
            "action_suggestion MUST be 'wait' and action_reasoning MUST explain the "
            "missing_conditions. If entry_status is NOT 'in_zone', action_suggestion "
            "MUST be 'wait'. If entry_status is 'above_zone', next_trigger_note MUST "
            "highlight the next_trigger. RISK OVERLAY (binding): if "
            "risk_overlay_passed is False, action_suggestion MUST be 'hold' or "
            "'wait' and action_reasoning MUST explain the risk_overlay_note. For a "
            "LONG card, reference valuation_confidence and conservative_anchor when "
            "explaining the entry band, and surface portfolio_weight_after_add. If "
            "risk_reward_ratio is below 1.5, flag it "
            "as unfavorable in risk_warning. Explain the stop-loss placement using "
            "the risk_note. Suggest exactly one action from add|hold|trim|exit|wait. "
            "BILINGUAL OUTPUT: for EVERY prose field you MUST output BOTH an English "
            "version ('<field>_en') and a Chinese version ('<field>_zh'). The Chinese "
            "MUST use professional finance / trading-desk terminology — NOT a literal "
            "machine translation. "
            "Output PURE JSON (no markdown) with exactly: "
            '{"action_suggestion": "add"|"hold"|"trim"|"exit"|"wait", '
            '"action_reasoning_en": "2-3 sentences", "action_reasoning_zh": "中文 2-3 句", '
            '"entry_note_en": "one sentence", "entry_note_zh": "中文一句", '
            '"stop_note_en": "one sentence", "stop_note_zh": "中文一句", '
            '"target_note_en": "one sentence", "target_note_zh": "中文一句", '
            '"risk_warning_en": "one sentence or empty string", "risk_warning_zh": "中文一句或空字符串", '
            '"next_trigger_note_en": "one sentence or empty string", "next_trigger_note_zh": "中文一句或空字符串"}'
        )
        user = (
            f"Ticker: {ticker}\n"
            f"Thesis status: {thesis_status}\n"
            f"Thesis: {thesis_text or '(none given)'}\n"
            f"Macro regime: {macro_regime}\n"
            f"Code-suggested baseline action: {code_action}\n\n"
            f"Computed levels (do not alter):\n{levels_block}\n\n"
            "Return the JSON object only."
        )
        client = llm_orchestrator._get_client()
        parsed = llm_orchestrator._llm_json_call(client, 1000, system, user)
        if not isinstance(parsed, dict):
            return _fallback_narrative(_FakeHolding(thesis_text), pl, _tc, macro_regime)

        action = parsed.get("action_suggestion")
        action = action if action in _ACTIONS else code_action
        # Enforce the entry gate in code (never trust the LLM to override it).
        if thesis_status != "broken" and (levels[10] or levels[11] != "in_zone"):
            action = "wait"
        # Enforce the risk overlay in code: a failed overlay can only hold/wait.
        if len(levels) > 22 and not bool(levels[22]) and action not in ("hold", "wait", "exit"):
            action = "hold"
        if levels[12] == "avoid" or thesis_status == "broken":
            action = "exit"
        # Read the LLM's bilingual fields directly (no deep-translator round-trip).
        # Fail-closed per field: blank _zh -> _en; blank _en -> plain field -> "".
        def _pair(field: str, limit: int) -> tuple:
            en = str(parsed.get(f"{field}_en", "") or parsed.get(field, "") or "")[:limit]
            zh = str(parsed.get(f"{field}_zh", "") or "")[:limit]
            return en, (zh or en)

        ar_en, ar_zh = _pair("action_reasoning", 600)
        en_en, en_zh = _pair("entry_note", 300)
        sn_en, sn_zh = _pair("stop_note", 300)
        tn_en, tn_zh = _pair("target_note", 300)
        rw_en, rw_zh = _pair("risk_warning", 300)
        nt_en, nt_zh = _pair("next_trigger_note", 300)
        narrative = OrderNarrative(
            action_suggestion=action,
            action_reasoning=ar_en, action_reasoning_en=ar_en, action_reasoning_zh=ar_zh,
            entry_note=en_en, entry_note_en=en_en, entry_note_zh=en_zh,
            stop_note=sn_en, stop_note_en=sn_en, stop_note_zh=sn_zh,
            target_note=tn_en, target_note_en=tn_en, target_note_zh=tn_zh,
            risk_warning=rw_en, risk_warning_en=rw_en, risk_warning_zh=rw_zh,
            next_trigger_note=nt_en, next_trigger_note_en=nt_en, next_trigger_note_zh=nt_zh,
            data_source=_LIVE,
        )
        # Backfill any blank _en / _zh (no LLM, no translator); page switches instantly.
        return _finalize_bilingual(narrative)
    except Exception:  # noqa: BLE001 — fail-closed
        return _fallback_narrative(_FakeHolding(thesis_text), pl, _tc, macro_regime)


class _FakeHolding:
    def __init__(self, thesis_text: str = "") -> None:
        self.thesis_text = thesis_text


def _finalize_bilingual(n: OrderNarrative) -> OrderNarrative:
    """Backfill ``{field}_en`` / ``{field}_zh`` for every free-text field (no LLM,
    no deep-translator).

    The LLM now emits both languages directly (see the cached narrative call), so
    this only ensures both are populated: a blank ``_en`` falls back to the plain
    field; a blank ``_zh`` falls back to ``_en``. The code fallback narrative is
    English-only, so its ``_zh`` simply mirrors the English — fully fail-closed and
    with zero external translation dependency.
    """
    for f in _NARRATIVE_TEXT_FIELDS:
        base = getattr(n, f, "") or ""
        en = getattr(n, f"{f}_en", "") or base
        zh = getattr(n, f"{f}_zh", "") or en
        setattr(n, f"{f}_en", en)
        setattr(n, f"{f}_zh", zh)
    return n


# Decorate the cached LLM narrative with st.cache_data when available.
try:  # pragma: no cover - cache decoration is environment dependent
    import streamlit as _st

    _generate_order_narrative_cached = _st.cache_data(ttl=3600, show_spinner=False)(
        _generate_order_narrative_cached
    )
except Exception:  # noqa: BLE001
    pass


# ---------------------------------------------------------------------------
# Convenience assembler
# ---------------------------------------------------------------------------


def build_order_recommendation(holding, thesis_check, macro_regime: str = "unknown",
                               lang: str = "en") -> OrderRecommendation:
    """Compute levels (code) + narrative (LLM) and bundle them (fail-closed)."""
    levels = compute_price_levels(
        getattr(holding, "ticker", ""), holding,
        thesis_status=getattr(thesis_check, "thesis_status", "intact"),
        horizon=getattr(holding, "horizon", "mid"),
        eps_revision_direction=getattr(thesis_check, "eps_revision_direction", "unknown"),
        allow_fetch=True,  # X1: order-recommendation builder is a page/desk path
    )
    narrative = generate_order_narrative(holding, levels, thesis_check, macro_regime, lang)
    return OrderRecommendation(
        holding=holding,
        price_levels=levels,
        thesis_check=thesis_check,
        narrative=narrative,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
