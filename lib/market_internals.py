"""lib/market_internals.py — Phase 7B Task 3: Market-Internals Fragility Layer.

Answers **"where are we HEADING"** while the regime layer
(``lib.macro_regime``) keeps answering "where are we CONFIRMED to be". The
regime classifier reads priced-in stress (VIX, spreads) and only flips AFTER a
drawdown; market internals (strong earnings sold, shrinking volume in leading
themes, narrowing breadth, distribution days, a defensive offense/defense
differential) deteriorate for days beforehand. This module turns those
internals into a single fragility level — *normal / elevated / high* — with
**hysteresis** so a single-day spike never escalates.

Hard contract — **STRICT tighten-only**:

* The regime classifier is **FROZEN**. This module never imports, calls, mutates,
  or overrides ``lib.macro_regime``. Fragility NEVER changes the regime label,
  never flips risk_on→off, never relaxes any gate.
* The only effect is to **tighten**: at the gating level (default ``high``) the
  SHORT horizon's in-zone "Actionable Now" degrades to a wait state with the
  reason code ``internals_deteriorating`` (mirrors the calendar gate). ``elevated``
  only annotates.

Every component is deterministic, computed from cached / free data, and reported
with its own value so the composite is attributable. Fully fail-closed: missing
inputs degrade (and are listed in ``degraded``) rather than raising. No LLM. The
computation path performs **no network I/O** — callers pass already-fetched
(cache-only) frames and a single benchmark fetch, exactly as the 7A ranking
contract requires.

Review-only context; not investment advice.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional

# ── Visible config (all windows / thresholds here for later calibration) ──────
INTERNALS_CONFIG = {
    # Distribution days (IBD-style): a down day on higher volume than the prior
    # session, counted over a rolling lookback.
    "distribution_day_lookback": 25,
    "distribution_day_pct": 0.002,      # min close-to-close drop to count (0.2%)
    "distribution_days_elevated": 4,    # >= → contributes to elevated
    "distribution_days_high": 6,        # >= → contributes to high

    # Breadth (% of universe above SMA20 / SMA50).
    "breadth_weak_pct": 0.40,           # below → weak-breadth flag
    "breadth_slope_drop": 0.08,         # breadth fell >= this (pp, as fraction)
                                        # vs the lookback reading → narrowing flag
    "leading_theme_breadth_drop": 0.10,  # leading-theme internal breadth drop

    # Earnings reaction quality.
    "good_news_sold_reaction_pp": 0.0,  # a BEAT whose next-session return <= this
                                        # (pp/100, i.e. 0.0 = closed red) is "sold"
    "good_news_sold_elevated": 1,       # >= good-news-sold instances → elevated
    "good_news_sold_high": 2,           # >= → high
    "earnings_lookback_sessions": 5,    # a report counts when this many sessions
                                        # (or fewer) have passed since it printed

    # Volume character / rally quality.
    "rally_down_day_pct": -0.01,        # a session <= this defines the down day
    "volume_shrink_ratio": 0.90,        # bounce volume < this × down-day volume

    # Leading-theme BUYER-WITHDRAWAL volume signature ("buying drying up" in the
    # leaders). REPLACES the old total-dollar-volume recent/baseline ratio — see the
    # ``leading_theme_volume_shrink`` docstring for the calibration rationale (the
    # old ratio is structurally unable to fire during distribution after a parabolic
    # run). Per the top leader/ex-leader themes, decompose constituent DOLLAR volume
    # (Close×Volume, normalizes across price levels) into UP-day vs DOWN-day buckets
    # over a recent window vs a trailing baseline; the flag fires when up-day volume
    # CONTRACTS while down-day volume EXPANDS — rising prices on thinning volume,
    # selling on rising volume (composite weight +1, tighten-only, see
    # ``_score_components``).
    "leading_theme_count": 3,             # how many leader/ex-leader themes to inspect
    "leading_theme_vol_recent_days": 10,  # recent window (sessions)
    "leading_theme_vol_baseline_days": 25,  # trailing baseline window (sessions)
    "leading_theme_up_day_pct": 0.0,      # a constituent session return > this is an up day
    "leading_theme_down_day_pct": 0.0,    # a constituent session return < this is a down day
    "leading_theme_up_vol_contract_ratio": 0.90,   # recent up-vol < this × baseline up-vol → contracting
    "leading_theme_down_vol_expand_ratio": 1.10,   # recent down-vol > this × baseline down-vol → expanding
    "leading_theme_min_constituents": 5,  # data floor; below → flag stays degraded

    # Composite point thresholds.
    "elevated_points": 2,
    "high_points": 4,

    # Hysteresis: escalation requires the raw condition to hold for N consecutive
    # sessions (single-day spikes never escalate); de-escalation is faster.
    "hysteresis_escalate_sessions": 2,
    "hysteresis_deescalate_sessions": 1,
    # "Consecutive" means consecutive TRADING sessions, decided PRIMARILY by the
    # benchmark (SPY/QQQ) trading-date index — no new dependency, no network. This
    # calendar-day bound is only the FALLBACK when that index can't cover the
    # snapshot dates (cache miss/stale); using it flags adjacency_degraded. A
    # broken chain can only DELAY escalation, never fabricate it.
    "hysteresis_max_calendar_gap_days": 4,

    # Rolling raw-reading series (Task A): recompute raw fragility "as of" each of
    # the past N trading days from cached OHLCV, so hysteresis consumes what the
    # MARKET did (the signal trail) rather than what the system RECORDED (the audit
    # trail). breadth_slope is derived from this computed series (no day-one null).
    "rolling_window_sessions": 10,
    "breadth_slope_lookback_sessions": 5,

    # WSL clock-drift defense: WSL2's clock can lag after a Windows sleep/resume,
    # mis-dating snapshots. The system date is sanity-checked against the latest
    # cached benchmark trading date; EARLIER than it, or more than this many
    # calendar days AHEAD, is "clock_suspect" (warn + flag, never block the write).
    "clock_drift_max_ahead_days": 7,
}

LEVELS = ("normal", "elevated", "high")
_LEVEL_RANK = {"normal": 0, "elevated": 1, "high": 2}

# Which horizons each fragility level GATES (tighten-only). Default: high gates
# SHORT; elevated only annotates (gates nothing).
GATE_BY_LEVEL = {
    "normal": (),
    "elevated": (),
    "high": ("short",),
}

# Reason code emitted when fragility gates a horizon.
INTERNALS_REASON_CODE = "internals_deteriorating"
INTERNALS_REASON_EN = "Market internals deteriorating — wait for confirmation"
INTERNALS_REASON_ZH = "市场内部结构转弱——等待确认"


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class FragilityComponents:
    """Every component value (attributable composite)."""

    distribution_days_spy: Optional[int] = None
    distribution_days_qqq: Optional[int] = None
    breadth_above_sma20: Optional[float] = None
    breadth_above_sma50: Optional[float] = None
    breadth_above_sma20_prev: Optional[float] = None
    breadth_slope: Optional[float] = None  # current − prior (fraction)
    leading_theme_breadth_narrowing: bool = False
    leading_theme_volume_shrinking: bool = False
    good_news_sold: Optional[int] = None
    earnings_evaluated: int = 0
    # Report-tickers in the (scan) universe + lookback window whose OHLCV frame was
    # NOT cache-resident this refresh, so their reaction could not be evaluated
    # network-free. skipped > evaluated → partial_frame_coverage degrade reason.
    earnings_skipped: int = 0
    weak_bounce: Optional[bool] = None
    offense_defense_direction: str = ""
    offense_defense_magnitude: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FragilityReading:
    """Composite fragility level + attributable component detail."""

    level: str = "normal"        # post-hysteresis (the effective level)
    raw_level: str = "normal"    # today's raw condition (pre-hysteresis)
    points: int = 0
    triggered: list = field(default_factory=list)  # component codes that fired
    components: FragilityComponents = field(default_factory=FragilityComponents)
    degraded: list = field(default_factory=list)
    consecutive_raw: int = 1     # consecutive sessions at/above raw_level
    # True when the trading-calendar adjacency check fell back to a calendar-day
    # bound (benchmark index missing / out-of-range) for any evaluated pair.
    adjacency_degraded: bool = False
    # WHY the earnings-reaction component degraded (Item 2): "" = evaluated;
    # "finnhub_unavailable" (the calendar call failed / no key) vs
    # "no_reports_in_window" (call succeeded, nothing in the scan universe + window)
    # vs "partial_frame_coverage" (scan-universe reports WERE in window but their
    # frames were not cache-resident, so skipped > evaluated — the network-free
    # cost of the broad scan scope) vs "earnings_source_absent" (no calendar source
    # supplied) vs "implausible_count" — distinct situations we tell apart in
    # snapshot history. Note: partial_frame_coverage can co-exist with a reported
    # number (evaluated > 0 but skipped still exceeded it).
    earnings_degrade_reason: str = ""
    # How hysteresis resolved the effective level (Task A): "rolling" = from raw
    # readings recomputed for past trading days (the intended "condition held N
    # sessions" meaning); "snapshot" = fallback to recorded snapshot history when
    # cache depth was insufficient. The rolling raw series + the window used.
    hysteresis_source: str = "snapshot"
    rolling_window: int = 0
    rolling_raw_series: list = field(default_factory=list)  # [(date, raw_level, points), ...]
    # The single data vintage of this refresh: the last trading date common to the
    # frames actually used. ``vintage_mismatch`` is True when the benchmark and the
    # universe frames disagree on their last date (stale on-disk cache vs fresh
    # fetch) — the rolling series then DEGRADES to the snapshot path rather than
    # replaying a different-vintage market.
    data_vintage: str = ""
    vintage_mismatch: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def gated_horizons(self) -> tuple:
        return GATE_BY_LEVEL.get(self.level, ())


# ── Pure component helpers (no I/O) ───────────────────────────────────────────

def _finite(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def _seq(x) -> list:
    try:
        return [v for v in (_finite(i) for i in list(x)) if v is not None]
    except TypeError:
        return []


def count_distribution_days(closes, volumes, lookback: Optional[int] = None,
                            pct: Optional[float] = None) -> Optional[int]:
    """IBD-style distribution-day count over the trailing ``lookback`` sessions.

    A distribution day = a session that closes down at least ``pct`` versus the
    prior close AND on higher volume than the prior session. Returns ``None`` when
    there is not enough history."""
    cfg = INTERNALS_CONFIG
    lookback = cfg["distribution_day_lookback"] if lookback is None else lookback
    pct = cfg["distribution_day_pct"] if pct is None else pct
    c = _seq(closes)
    v = _seq(volumes)
    if len(c) < 2 or len(v) < 2:
        return None
    n = min(len(c), len(v))
    c, v = c[-n:], v[-n:]
    # Evaluate the last ``lookback`` sessions that have a prior session.
    start = max(1, n - lookback)
    count = 0
    for i in range(start, n):
        if c[i - 1] <= 0:
            continue
        ret = c[i] / c[i - 1] - 1.0
        if ret <= -abs(pct) and v[i] > v[i - 1]:
            count += 1
    return count


def breadth_above_sma(frames: dict, period: int) -> Optional[float]:
    """Fraction of the universe whose last close is at/above its SMA(period).

    ``frames`` is ``{ticker: OHLCV frame|None}`` (DataFrame with ``Close`` or a
    dict of sequences). Tickers without enough history are skipped. Returns
    ``None`` when no ticker is usable."""
    used = above = 0
    for df in (frames or {}).values():
        try:
            closes = _seq(df["Close"])
        except Exception:  # noqa: BLE001
            closes = []
        if len(closes) < period:
            continue
        sma = sum(closes[-period:]) / period
        used += 1
        if closes[-1] >= sma:
            above += 1
    if used == 0:
        return None
    return round(above / used, 4)


def count_good_news_sold(earnings_reactions, reaction_pp: Optional[float] = None):
    """Count "good news sold" instances (the AVGO pattern).

    ``earnings_reactions`` is an iterable of records with a result ``direction``
    ("beat"/"miss") and a ``next_session_return`` (fraction). A beat whose
    next-session return is at/below ``reaction_pp`` is counted. Returns
    ``(count, n_evaluated)``; records missing either field are skipped."""
    reaction_pp = (INTERNALS_CONFIG["good_news_sold_reaction_pp"]
                   if reaction_pp is None else reaction_pp)
    count = evaluated = 0
    for r in earnings_reactions or []:
        direction = (r.get("direction") if isinstance(r, dict)
                     else getattr(r, "direction", None))
        nxt = (r.get("next_session_return") if isinstance(r, dict)
               else getattr(r, "next_session_return", None))
        nxt = _finite(nxt)
        if direction is None or nxt is None:
            continue
        evaluated += 1
        if str(direction).lower() == "beat" and nxt <= reaction_pp:
            count += 1
    return count, evaluated


def detect_weak_bounce(closes, volumes, down_day_pct: Optional[float] = None,
                       shrink_ratio: Optional[float] = None) -> Optional[bool]:
    """After the most recent down day ≥ threshold, was the next-session bounce on
    SHRINKING volume? ``None`` when no qualifying down-day/bounce pair exists."""
    cfg = INTERNALS_CONFIG
    down_day_pct = cfg["rally_down_day_pct"] if down_day_pct is None else down_day_pct
    shrink_ratio = cfg["volume_shrink_ratio"] if shrink_ratio is None else shrink_ratio
    c = _seq(closes)
    v = _seq(volumes)
    n = min(len(c), len(v))
    if n < 3:
        return None
    c, v = c[-n:], v[-n:]
    # Walk backwards for the most recent down day that HAS a following session.
    for i in range(n - 2, 0, -1):
        if c[i - 1] <= 0:
            continue
        ret = c[i] / c[i - 1] - 1.0
        if ret <= down_day_pct:
            nxt = c[i + 1] / c[i] - 1.0 if c[i] > 0 else 0.0
            if nxt > 0:  # it was a bounce
                return bool(v[i + 1] < shrink_ratio * v[i])
            return False  # next session was not a bounce → not a weak bounce
    return None


def _theme_buyer_withdrawal(constituent_frames: dict, recent_days: int,
                            baseline_days: int, min_constituents: int,
                            cfg: dict):
    """(detail | None, n_used) for one theme's buyer-withdrawal volume signature.

    The signature = UP-day dollar volume CONTRACTING in the recent window while
    DOWN-day dollar volume EXPANDS (rising prices on thinning volume; selling on
    rising volume). Per constituent: dollar volume = Close × Volume (normalizes
    across price levels); each session is classified up/down by its close-to-close
    return (``leading_theme_up_day_pct`` / ``leading_theme_down_day_pct``). Within
    the recent window (last ``recent_days`` sessions) and the baseline window (the
    ``baseline_days`` immediately before it), the per-bucket MEAN dollar volume is
    summed across the constituents with enough history (≥ recent+baseline+1 bars AND
    at least one up day and one down day in BOTH windows, so each bucket is
    comparable). Returns (None, n) when fewer than ``min_constituents`` constituents
    are usable or a baseline bucket sum is ≤ 0.

    Fires iff  recent_up   <  up_contract_ratio  × baseline_up    (up-day contraction)
          AND  recent_down >  down_expand_ratio × baseline_down  (down-day expansion).
    """
    need = recent_days + baseline_days
    up_contract = float(cfg["leading_theme_up_vol_contract_ratio"])
    down_expand = float(cfg["leading_theme_down_vol_expand_ratio"])
    up_pct = float(cfg["leading_theme_up_day_pct"])
    down_pct = float(cfg["leading_theme_down_day_pct"])
    r_up = r_down = b_up = b_down = 0.0
    used = 0

    def _mean(xs):
        return (sum(xs) / len(xs)) if xs else None

    for df in (constituent_frames or {}).values():
        closes, volumes = _close_volume_lists(df)
        closes, volumes = _seq(closes), _seq(volumes)
        n = min(len(closes), len(volumes))
        # need one prior close for the first window return → need+1 bars.
        if n < need + 1:
            continue
        closes, volumes = closes[-(need + 1):], volumes[-(need + 1):]
        # Returns + dollar volume aligned to sessions 1..need (each has a prior bar).
        rets = [(closes[i] / closes[i - 1] - 1.0) if closes[i - 1] > 0 else 0.0
                for i in range(1, need + 1)]
        dollar = [closes[i] * volumes[i] for i in range(1, need + 1)]
        # First baseline_days = baseline window; last recent_days = recent window.
        base_r, base_d = rets[:baseline_days], dollar[:baseline_days]
        rec_r, rec_d = rets[-recent_days:], dollar[-recent_days:]
        ru = _mean([d for r, d in zip(rec_r, rec_d) if r > up_pct])
        rd = _mean([d for r, d in zip(rec_r, rec_d) if r < down_pct])
        bu = _mean([d for r, d in zip(base_r, base_d) if r > up_pct])
        bd = _mean([d for r, d in zip(base_r, base_d) if r < down_pct])
        # Both day types must exist in BOTH windows for a comparable constituent.
        if None in (ru, rd, bu, bd):
            continue
        used += 1
        r_up += ru
        r_down += rd
        b_up += bu
        b_down += bd
    if used < min_constituents or b_up <= 0 or b_down <= 0:
        return None, used
    up_ratio = r_up / b_up
    down_ratio = r_down / b_down
    fired = (up_ratio < up_contract) and (down_ratio > down_expand)
    return ({"up_ratio": round(up_ratio, 4), "down_ratio": round(down_ratio, 4),
             "n_used": used, "fired": bool(fired)}, used)


def _select_leading_themes(themes, count: int) -> list:
    """The top ``count`` CURRENT-or-RECENT leaders to watch for volume distribution:
    the stage set ``{leading, rotating_out}`` ranked by momentum_score (desc).

    Rationale (polish round 3 — Item 3): the volume-shrink signal catches *buying
    drying up in the leaders*. A leader that just flipped to ``rotating_out`` (the
    ai_chips / AVGO case — still high momentum, breadth bleeding) is the **prime**
    subject, so excluding it (the old leading/rotating_in-only rule) blinded the
    monitor to exactly the distribution it exists to catch. ``rotating_in`` (a new
    entrant, no distribution history yet) and ``out_of_favor`` (already gone) are
    excluded. Falls back to all themes by momentum when no stage labels are set."""
    eligible = [th for th in (themes or [])
                if str(getattr(th, "stage", "") or "") in ("leading", "rotating_out")]
    pool = eligible if eligible else list(themes or [])
    return sorted(pool, key=lambda th: float(getattr(th, "momentum_score", 0.0) or 0.0),
                  reverse=True)[:max(0, count)]


def leading_theme_volume_shrink(themes, frame_loader, config: Optional[dict] = None):
    """(shrinking_flag, degraded, detail) for the top leading themes.

    Decomposes constituent dollar volume into UP-day vs DOWN-day buckets from the
    SAME cached OHLCV the breadth computation uses (``frame_loader``, cache-only — no
    new fetch, no per-ticker network on the ranking path). The flag fires when ANY
    inspected leading theme shows the **buyer-withdrawal signature** — up-day volume
    CONTRACTING (recent up-vol < ``leading_theme_up_vol_contract_ratio`` × baseline
    up-vol) while down-day volume EXPANDS (recent down-vol >
    ``leading_theme_down_vol_expand_ratio`` × baseline down-vol). ``degraded`` is
    True when NO inspected theme had enough usable constituents.

    Calibration-driven amendment (this round): this REPLACES the old total-dollar-
    volume recent/baseline ratio (``leading_theme_vol_shrink_ratio``). The old metric
    lumped up-day and down-day volume into a single sum, so it is **structurally
    unable to fire during distribution after a parabolic run**: late-stage
    distribution prints heavy DOWN-day volume that inflates the recent total, holding
    (or raising) the recent/baseline ratio ABOVE the shrink threshold exactly when
    buyers are withdrawing. The 30-day backfill confirmed this — the old ratio read
    1.4–1.8 (expansion, never shrinking) right through the mid-May AVGO/ai_chips
    distribution. Splitting the buckets isolates the real signal: buyers thinning out
    on up days *and* sellers showing up on down days. Tighten-only semantics are
    unchanged (the flag can only ADD a fragility point, never relax anything)."""
    cfg = config or INTERNALS_CONFIG
    if not themes or frame_loader is None:
        return False, True, {}
    recent_days = int(cfg["leading_theme_vol_recent_days"])
    baseline_days = int(cfg["leading_theme_vol_baseline_days"])
    min_const = int(cfg["leading_theme_min_constituents"])
    leaders = _select_leading_themes(themes, int(cfg["leading_theme_count"]))

    shrinking = False
    any_evaluable = False
    detail: dict = {}
    for th in leaders:
        constituents = getattr(th, "constituents", None) or []
        frames = {}
        for tk in constituents:
            try:
                frames[tk] = frame_loader(tk)
            except Exception:  # noqa: BLE001
                frames[tk] = None
        sig, used = _theme_buyer_withdrawal(
            frames, recent_days, baseline_days, min_const, cfg)
        key = getattr(th, "theme_key", "?")
        if sig is None:
            detail[key] = {"signature": None, "n_used": used}
            continue
        any_evaluable = True
        detail[key] = dict(sig)
        if sig["fired"]:
            shrinking = True
    return shrinking, (not any_evaluable), detail


# ── Composite scoring ─────────────────────────────────────────────────────────

def _score_components(comp: FragilityComponents, cfg: dict) -> tuple:
    """(points, triggered codes) from the component values."""
    points = 0
    triggered: list = []

    dd = max([x for x in (comp.distribution_days_spy, comp.distribution_days_qqq)
              if x is not None], default=None)
    if dd is not None:
        if dd >= cfg["distribution_days_high"]:
            points += 2
            triggered.append("distribution_days_high")
        elif dd >= cfg["distribution_days_elevated"]:
            points += 1
            triggered.append("distribution_days_elevated")

    if comp.good_news_sold is not None:
        if comp.good_news_sold >= cfg["good_news_sold_high"]:
            points += 2
            triggered.append("good_news_sold_high")
        elif comp.good_news_sold >= cfg["good_news_sold_elevated"]:
            points += 1
            triggered.append("good_news_sold_elevated")

    if comp.breadth_above_sma20 is not None and comp.breadth_above_sma20 < cfg["breadth_weak_pct"]:
        points += 1
        triggered.append("breadth_weak")
    if comp.breadth_slope is not None and comp.breadth_slope <= -abs(cfg["breadth_slope_drop"]):
        points += 1
        triggered.append("breadth_narrowing")
    if comp.leading_theme_breadth_narrowing:
        points += 1
        triggered.append("leading_theme_breadth_narrowing")
    if comp.leading_theme_volume_shrinking:
        points += 1
        triggered.append("leading_theme_volume_shrinking")
    if comp.weak_bounce:
        points += 1
        triggered.append("weak_bounce")

    if comp.offense_defense_direction == "defense":
        if comp.offense_defense_magnitude == "strong":
            points += 2
            triggered.append("offense_defense_defensive_strong")
        elif comp.offense_defense_magnitude in ("moderate", "mild"):
            points += 1
            triggered.append("offense_defense_defensive")

    return points, triggered


def _raw_level_from_points(points: int, cfg: dict) -> str:
    if points >= cfg["high_points"]:
        return "high"
    if points >= cfg["elevated_points"]:
        return "elevated"
    return "normal"


def _parse_iso(d) -> "Optional[object]":
    """date.fromisoformat(d) or None (accepts a date/datetime/ISO string)."""
    import datetime as _dt
    if d is None:
        return None
    # datetime / pandas.Timestamp (a datetime subclass) → normalize to a pure date
    # so date-vs-Timestamp comparisons never raise.
    if isinstance(d, _dt.datetime):
        return d.date()
    if isinstance(d, _dt.date):
        return d
    try:
        return _dt.date.fromisoformat(str(d)[:10])
    except Exception:  # noqa: BLE001
        return None


def _calendar_gap_days(a, b) -> Optional[int]:
    """|a - b| in calendar days, or None when either date is unparseable."""
    da, db = _parse_iso(a), _parse_iso(b)
    if da is None or db is None:
        return None
    return abs((da - db).days)


def _index_dates(benchmark_index) -> list:
    """Sorted unique list of date objects from a benchmark date index.

    Accepts a pandas DatetimeIndex, a pandas Series (its index is used), or any
    iterable of dates / ISO strings. Fail-closed → []."""
    if benchmark_index is None:
        return []
    idx = benchmark_index
    # A pandas Series/DataFrame → use its (non-callable) .index; a DatetimeIndex or
    # plain list is iterated directly. (A list's ``.index`` is a METHOD — skip it.)
    cand = getattr(idx, "index", None)
    if cand is not None and not callable(cand):
        idx = cand
    out = set()
    try:
        for d in idx:
            pd_ = _parse_iso(d)
            if pd_ is not None:
                out.add(pd_)
    except TypeError:
        return []
    return sorted(out)


def is_adjacent_session(d1, d2, benchmark_index) -> Optional[bool]:
    """Are ``d1`` and ``d2`` consecutive TRADING sessions per the benchmark index?

    The cached SPY/QQQ OHLCV date index IS the trading calendar (no new dependency,
    no network). Two dates are consecutive iff **no benchmark trading date lies
    strictly between them**. Returns ``None`` when the index cannot cover the dates
    (cache miss / stale / out-of-range) so the caller falls back to a calendar-day
    bound and flags ``adjacency_degraded`` — never silently assumes adjacency."""
    a, b = _parse_iso(d1), _parse_iso(d2)
    if a is None or b is None:
        return None
    if a == b:
        return False  # a same-session duplicate record never extends a chain
    lo, hi = (a, b) if a <= b else (b, a)
    days = _index_dates(benchmark_index)
    if not days or lo < days[0] or hi > days[-1]:
        return None  # not covered → caller falls back
    return not any(lo < d < hi for d in days)


def _adjacent(prev_date, d, benchmark_index, max_gap: int) -> tuple:
    """(is_adjacent, used_fallback) between two snapshot dates.

    Primary source: the benchmark trading calendar (:func:`is_adjacent_session`).
    Fallback (flagged): a max-calendar-gap bound when the index can't cover the
    dates."""
    res = is_adjacent_session(prev_date, d, benchmark_index)
    if res is not None:
        return res, False
    gap = _calendar_gap_days(prev_date, d)
    if gap is None:
        return False, True  # cannot determine at all → break the chain, degraded
    return gap <= max_gap, True


def apply_hysteresis(today_raw: str, prior_level: str, recent_raw_levels,
                     cfg: Optional[dict] = None, recent_dates=None,
                     today_date=None, benchmark_index=None,
                     out_flags: Optional[dict] = None) -> tuple:
    """Return (effective_level, consecutive_raw_count).

    Escalation to a higher effective level happens only when the raw level has
    been at/above the new level for ``hysteresis_escalate_sessions`` **consecutive
    trading sessions** (including today) — a single-day spike never escalates.
    De-escalation requires ``hysteresis_deescalate_sessions`` consecutive sessions
    below the prior level (default 1 → faster/immediate, gap-irrelevant).

    ``recent_raw_levels`` is the prior sessions' RAW levels, most-recent-first,
    NOT including today. When ``recent_dates`` (parallel, most-recent-first) and
    ``today_date`` are supplied, adjacency is decided by the **benchmark trading
    calendar** (``benchmark_index`` — the cached SPY/QQQ date index): two snapshot
    dates are consecutive iff no trading date lies strictly between them. A break
    restarts escalation counting, so gapped snapshots can only DELAY escalation,
    never fabricate it. When the index can't cover the dates, a calendar-day bound
    (``hysteresis_max_calendar_gap_days``) is used as a fallback and
    ``out_flags['adjacency_degraded']`` is set (never silently assumes adjacency)."""
    cfg = cfg or INTERNALS_CONFIG
    esc = max(1, int(cfg["hysteresis_escalate_sessions"]))
    deesc = max(1, int(cfg["hysteresis_deescalate_sessions"]))
    max_gap = int(cfg.get("hysteresis_max_calendar_gap_days", 4))
    prior = prior_level if prior_level in _LEVEL_RANK else "normal"
    t_rank = _LEVEL_RANK[today_raw]
    p_rank = _LEVEL_RANK[prior]
    recent = [lv for lv in (recent_raw_levels or []) if lv in _LEVEL_RANK]
    dates = list(recent_dates) if recent_dates is not None else None
    check_adjacency = dates is not None and today_date is not None
    adjacency_degraded = False

    # Consecutive sessions (incl today) whose raw is at/above today's raw level,
    # walking back only while snapshot records remain trading-session-adjacent.
    consec = 1
    prev_date = today_date
    for i, lv in enumerate(recent):
        if check_adjacency:
            d = dates[i] if i < len(dates) else None
            adj, used_fallback = _adjacent(prev_date, d, benchmark_index, max_gap)
            adjacency_degraded = adjacency_degraded or used_fallback
            if not adj:
                break  # a missed trading session breaks the consecutive chain
        if _LEVEL_RANK[lv] >= t_rank:
            consec += 1
            if check_adjacency:
                prev_date = dates[i]
        else:
            break

    if out_flags is not None:
        out_flags["adjacency_degraded"] = adjacency_degraded

    if t_rank > p_rank:
        return (today_raw, consec) if consec >= esc else (prior, consec)
    if t_rank < p_rank:
        # De-escalation is immediate on a fresh lower reading (gap-irrelevant).
        below = 1
        for lv in recent:
            if _LEVEL_RANK[lv] < p_rank:
                below += 1
            else:
                break
        return (today_raw, consec) if below >= deesc else (prior, consec)
    return (prior, consec)


def compute_fragility(*, components: Optional[FragilityComponents] = None,
                      offense_defense: Optional[dict] = None,
                      prior_level: str = "normal",
                      recent_raw_levels=None,
                      recent_dates=None,
                      today_date=None,
                      benchmark_index=None,
                      degraded=None,
                      config: Optional[dict] = None,
                      **component_kwargs) -> FragilityReading:
    """Compute the fragility reading from component values (or a components obj).

    Either pass a prebuilt :class:`FragilityComponents` (``components=``) or the
    individual component values as keyword args. ``offense_defense`` is the Task 2
    reading dict (``{"direction","magnitude",...}``) — component (e). Hysteresis is
    applied against ``prior_level`` + ``recent_raw_levels`` (the snapshot history is
    the memory). Fully fail-closed."""
    cfg = config or INTERNALS_CONFIG
    comp = components or FragilityComponents(**component_kwargs)
    if offense_defense:
        comp.offense_defense_direction = str(offense_defense.get("direction", "") or "")
        comp.offense_defense_magnitude = str(offense_defense.get("magnitude", "") or "")
    if comp.breadth_slope is None and (
            comp.breadth_above_sma20 is not None
            and comp.breadth_above_sma20_prev is not None):
        comp.breadth_slope = round(
            comp.breadth_above_sma20 - comp.breadth_above_sma20_prev, 4)

    points, triggered = _score_components(comp, cfg)
    raw_level = _raw_level_from_points(points, cfg)
    _flags: dict = {}
    level, consec = apply_hysteresis(
        raw_level, prior_level, recent_raw_levels or [], cfg,
        recent_dates=recent_dates, today_date=today_date,
        benchmark_index=benchmark_index, out_flags=_flags)
    degraded_list = list(degraded or [])
    adjacency_degraded = bool(_flags.get("adjacency_degraded"))
    if adjacency_degraded and "hysteresis_adjacency" not in degraded_list:
        degraded_list.append("hysteresis_adjacency")

    return FragilityReading(
        level=level,
        raw_level=raw_level,
        points=points,
        triggered=triggered,
        components=comp,
        degraded=degraded_list,
        consecutive_raw=consec,
        adjacency_degraded=adjacency_degraded,
    )


# ── Tighten-only gating helper (mirrors the calendar gate) ────────────────────

def gated_horizons(level: str) -> tuple:
    """Horizons that the given fragility level GATES (tighten-only)."""
    return GATE_BY_LEVEL.get(str(level or "normal"), ())


def internals_reason() -> dict:
    """The ``internals_deteriorating`` status-reason record (bilingual)."""
    return {"code": INTERNALS_REASON_CODE,
            "en": INTERNALS_REASON_EN, "zh": INTERNALS_REASON_ZH}


# ── WSL clock-drift defense ───────────────────────────────────────────────────

def detect_clock_drift(today, benchmark_index, config: Optional[dict] = None):
    """(clock_suspect: bool, reason: str) from the system date vs the trading
    calendar. ``benchmark_index`` is the cached SPY/QQQ date index (the latest
    trading date). Suspect when the system date is EARLIER than that date, or more
    than ``clock_drift_max_ahead_days`` calendar days ahead of it. Cannot be
    determined (no index / unparseable date) → (False, "") — never blocks."""
    cfg = config or INTERNALS_CONFIG
    max_ahead = int(cfg.get("clock_drift_max_ahead_days", 7))
    days = _index_dates(benchmark_index)
    t = _parse_iso(today)
    if not days or t is None:
        return False, ""
    latest = days[-1]
    if t < latest:
        return True, (f"system date {t} is EARLIER than the latest cached trading "
                      f"date {latest} (clock likely lagging)")
    ahead = (t - latest).days
    if ahead > max_ahead:
        return True, (f"system date {t} is {ahead} calendar days ahead of the latest "
                      f"cached trading date {latest} (> {max_ahead})")
    return False, ""


# ── Snapshot serialization (the snapshot is the memory) ───────────────────────

def fragility_snapshot(reading: FragilityReading, date_str: str) -> dict:
    """Flat, JSON-serializable daily record: level + every component + flags.

    This is MANDATORY — fragility's lead / false-positive rate will be judged from
    snapshot history later."""
    c = reading.components
    return {
        "date": date_str,
        "fragility_level": reading.level,
        "fragility_raw_level": reading.raw_level,
        "fragility_points": reading.points,
        "fragility_triggered": list(reading.triggered),
        "fragility_consecutive_raw": reading.consecutive_raw,
        "fragility_degraded": list(reading.degraded),
        "fragility_adjacency_degraded": reading.adjacency_degraded,
        "earnings_degrade_reason": reading.earnings_degrade_reason,
        "hysteresis_source": reading.hysteresis_source,
        "rolling_window": reading.rolling_window,
        "data_vintage": reading.data_vintage,
        "vintage_mismatch": reading.vintage_mismatch,
        # every component value, attributable
        "distribution_days_spy": c.distribution_days_spy,
        "distribution_days_qqq": c.distribution_days_qqq,
        "breadth_above_sma20": c.breadth_above_sma20,
        "breadth_above_sma50": c.breadth_above_sma50,
        "breadth_above_sma20_prev": c.breadth_above_sma20_prev,
        "breadth_slope": c.breadth_slope,
        "leading_theme_breadth_narrowing": c.leading_theme_breadth_narrowing,
        "leading_theme_volume_shrinking": c.leading_theme_volume_shrinking,
        "good_news_sold": c.good_news_sold,
        "earnings_evaluated": c.earnings_evaluated,
        "earnings_skipped": c.earnings_skipped,
        "weak_bounce": c.weak_bounce,
        "offense_defense_direction": c.offense_defense_direction,
        "offense_defense_magnitude": c.offense_defense_magnitude,
    }


def read_recent_meta(snapshot_dir, before_date: Optional[str] = None,
                     limit: int = 10) -> list:
    """Read the ``_meta`` header line of recent ``opportunities_*.jsonl`` snapshots.

    Returns up to ``limit`` most-recent _meta dicts (each carries the persisted
    fragility fields). Best-effort / fail-closed → ``[]``. No network."""
    import json
    from pathlib import Path
    try:
        base = Path(snapshot_dir)
        files = sorted(base.glob("opportunities_*.jsonl"), reverse=True)
    except Exception:  # noqa: BLE001
        return []
    out: list = []
    for f in files:
        if len(out) >= limit:
            break
        try:
            with f.open("r", encoding="utf-8") as fh:
                first = fh.readline()
            meta = json.loads(first)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(meta, dict) or not meta.get("_meta"):
            continue
        if before_date is not None and str(meta.get("date", "")) >= str(before_date):
            continue
        out.append(meta)
    return out


def _frame_date_index(df):
    """The Close column's date index from an OHLCV frame, or None. Fail-closed."""
    try:
        return df["Close"].index
    except Exception:  # noqa: BLE001
        return None


def _close_volume_lists(df):
    """(closes, volumes) lists from a frame/dict, fail-closed → ([], [])."""
    try:
        closes = list(df["Close"])
    except Exception:  # noqa: BLE001
        closes = []
    try:
        volumes = list(df["Volume"])
    except Exception:  # noqa: BLE001
        volumes = []
    return closes, volumes


def _next_session_reaction(df, report_date, today, window_sessions: int):
    """(next-session return after the report, in_window) from a cached frame.

    The next-session reaction is the close-to-close return of the first trading
    session strictly AFTER ``report_date`` (the gap+day move off the pre-report
    close). ``in_window`` is True when at most ``window_sessions`` trading dates lie
    in ``(report_date, today]``. Returns (None, in_window) when the reaction can't
    be computed; (None, False) when the frame/date is unusable."""
    rd = _parse_iso(report_date)
    if rd is None or df is None:
        return None, False
    try:
        close = df["Close"]
        idx = _index_dates(getattr(close, "index", None))
        closes = _seq(close)
    except Exception:  # noqa: BLE001
        return None, False
    if not idx or len(idx) != len(closes) or len(closes) < 2:
        return None, False
    t = _parse_iso(today) or idx[-1]
    sessions_since = sum(1 for d in idx if rd < d <= t)
    in_window = sessions_since <= int(window_sessions)
    # first bar strictly after the report date → reaction vs the prior close.
    j = next((i for i, d in enumerate(idx) if d > rd), None)
    if j is None or j == 0 or closes[j - 1] in (None, 0):
        return None, in_window
    return (closes[j] / closes[j - 1] - 1.0), in_window


def build_earnings_reactions(universe, frame_loader, calendar_fn, today_str: str,
                             config: Optional[dict] = None):
    """(reactions, degrade_reason) for the good-news-sold component.

    ``calendar_fn()`` is the single, skippable bulk earnings-calendar call — it
    returns recent reports ``[{ticker, report_date, direction}]`` (``direction`` =
    "beat"/"miss") and RAISES on a genuine source failure (no key / network). The
    per-report next-session reaction is read from cached OHLCV (``frame_loader``),
    so no per-ticker network is added. A report counts only when its ticker is in
    ``universe`` and it falls within ``earnings_lookback_sessions``.

    Degrade reasons (distinct, for snapshot history): ``earnings_source_absent``
    (no calendar_fn), ``finnhub_unavailable`` (call raised), ``no_reports_in_window``
    (call returned but nothing usable in window/universe)."""
    cfg = config or INTERNALS_CONFIG
    if calendar_fn is None:
        return [], "earnings_source_absent"
    try:
        reports = calendar_fn() or []
    except Exception:  # noqa: BLE001 — the bulk call failed → genuinely unavailable
        return [], "finnhub_unavailable"
    uni = {str(t).upper().strip() for t in (universe or [])}
    window = int(cfg["earnings_lookback_sessions"])
    reactions: list = []
    for rep in reports:
        tk = str((rep.get("ticker") if isinstance(rep, dict) else "") or "").upper().strip()
        if uni and tk not in uni:
            continue
        direction = rep.get("direction") if isinstance(rep, dict) else None
        report_date = rep.get("report_date") if isinstance(rep, dict) else None
        if direction is None or report_date is None:
            continue
        try:
            df = frame_loader(tk) if frame_loader is not None else None
        except Exception:  # noqa: BLE001
            df = None
        nxt, in_window = _next_session_reaction(df, report_date, today_str, window)
        if not in_window or nxt is None:
            continue
        reactions.append({"ticker": tk, "direction": direction,
                          "next_session_return": nxt})
    if reactions:
        return reactions, ""
    return [], "no_reports_in_window"


# ── Rolling raw-reading series (Task A — the SIGNAL trail) ────────────────────

def _dated_arrays(df):
    """(dates, closes, volumes) sorted by date from a dated frame, or None.

    ``dates`` are pure ``datetime.date`` (so date-vs-date comparisons never raise).
    Returns None when the frame is undated/empty (→ rolling unavailable for it)."""
    try:
        close = df["Close"]
        idx = getattr(close, "index", None)
        dates = _index_dates(idx)
        closes = _seq(close)
        volumes = _seq(df["Volume"])
    except Exception:  # noqa: BLE001
        return None
    if not dates or len(dates) != len(closes):
        return None
    if len(volumes) != len(closes):
        volumes = volumes + [0.0] * (len(closes) - len(volumes))
    return dates, closes, volumes


def _pos_le(dates, as_of):
    """Index of the last date <= as_of (dates sorted ascending), or None."""
    import bisect
    d = _parse_iso(as_of)
    if d is None or not dates:
        return None
    pos = bisect.bisect_right(dates, d) - 1
    return pos if pos >= 0 else None


def _breadth_above_sma_asof(arrays_by_tk: dict, period: int, as_of):
    """Fraction of the universe at/above SMA(period) AS OF ``as_of``, or None."""
    used = above = 0
    for arr in (arrays_by_tk or {}).values():
        if arr is None:
            continue
        dates, closes, _ = arr
        pos = _pos_le(dates, as_of)
        if pos is None or pos + 1 < period:
            continue
        seg = closes[:pos + 1]
        sma = sum(seg[-period:]) / period
        used += 1
        if seg[-1] >= sma:
            above += 1
    return round(above / used, 4) if used else None


def _reaction_records(reports, frame_loader, bench_dates, today_str, cfg,
                      universe=None):
    """Per-report (ticker, reaction_date, return, direction) computed ONCE.

    The reaction_date is the first benchmark trading session strictly after the
    report; the return is read from the ticker's cached frame. Used to evaluate
    earnings "as of" any past day without re-fetching. **Filtered to ``universe``**
    (round 2 fix — without it the bulk calendar's whole-market reports were
    counted, and every non-universe ticker was also fetched)."""
    out = []
    uni = {str(t).upper().strip() for t in (universe or [])}
    for rep in reports or []:
        tk = str((rep.get("ticker") if isinstance(rep, dict) else "") or "").upper().strip()
        if uni and tk not in uni:
            continue
        direction = rep.get("direction") if isinstance(rep, dict) else None
        rd = _parse_iso(rep.get("report_date") if isinstance(rep, dict) else None)
        if not tk or direction is None or rd is None:
            continue
        try:
            df = frame_loader(tk) if frame_loader is not None else None
        except Exception:  # noqa: BLE001
            df = None
        nxt, _inw = _next_session_reaction(df, rd, today_str, 10 ** 6)
        if nxt is None:
            continue
        # reaction session = first benchmark date strictly after the report.
        rxn = next((d for d in bench_dates if d > rd), None)
        if rxn is None:
            continue
        out.append({"ticker": tk, "direction": direction,
                    "reaction_date": rxn, "next_session_return": nxt})
    return out


def _earnings_components_asof(reaction_records, bench_dates, as_of, cfg):
    """(good_news_sold, evaluated) AS OF ``as_of`` — reports whose reaction session
    is on/before ``as_of`` and within ``earnings_lookback_sessions`` of it."""
    d = _parse_iso(as_of)
    if d is None:
        return None, 0
    window = int(cfg["earnings_lookback_sessions"])
    in_window = []
    for rec in reaction_records or []:
        rxn = rec["reaction_date"]
        if rxn > d:
            continue
        sessions_since = sum(1 for bd in bench_dates if rxn < bd <= d)
        if sessions_since <= window:
            in_window.append(rec)
    if not in_window:
        return None, 0
    return count_good_news_sold(in_window, cfg["good_news_sold_reaction_pp"])


def _count_frameless_in_window(reports, frame_loader, bench_dates, as_of, cfg,
                               universe=None):
    """Coverage tally for the broad (scan-universe) earnings scope: how many
    report-tickers are in ``universe`` AND fall in the lookback window AS OF
    ``as_of`` but whose OHLCV frame is NOT cache-resident (``frame_loader`` returns
    None/empty), so their reaction could not be evaluated network-free. These are
    the "skipped" reports behind ``partial_frame_coverage``. Window logic mirrors
    :func:`_earnings_components_asof` exactly, so skipped + evaluated partition the
    same in-window report set."""
    uni = {str(t).upper().strip() for t in (universe or [])}
    window = int(cfg["earnings_lookback_sessions"])
    today_d = _parse_iso(as_of) or (bench_dates[-1] if bench_dates else None)
    if today_d is None:
        return 0
    skipped = 0
    for rep in reports or []:
        tk = str((rep.get("ticker") if isinstance(rep, dict) else "") or "").upper().strip()
        if uni and tk not in uni:
            continue
        direction = rep.get("direction") if isinstance(rep, dict) else None
        rd = _parse_iso(rep.get("report_date") if isinstance(rep, dict) else None)
        if not tk or direction is None or rd is None:
            continue
        rxn = next((d for d in bench_dates if d > rd), None)
        if rxn is None or rxn > today_d:
            continue
        sessions_since = sum(1 for bd in bench_dates if rxn < bd <= today_d)
        if sessions_since > window:
            continue
        try:
            df = frame_loader(tk) if frame_loader is not None else None
        except Exception:  # noqa: BLE001
            df = None
        if df is None or (hasattr(df, "empty") and df.empty):
            skipped += 1
    return skipped


def _replay_hysteresis(raw_chrono: list, cfg: dict):
    """Replay hysteresis over a CONTIGUOUS recomputed raw series (chronological).

    Trading-day adjacency is inherent (the series is indexed by the benchmark
    calendar), so escalation means "the raw condition held N consecutive
    recomputed sessions" — the originally intended meaning. Returns
    (effective_level, consecutive_today)."""
    effective = "normal"
    consec = 1
    for i, raw in enumerate(raw_chrono):
        recent = list(reversed(raw_chrono[:i]))  # most-recent-first, all adjacent
        effective, consec = apply_hysteresis(raw, effective, recent, cfg)
    return effective, consec


def _trunc_loader(frame_loader, as_of):
    """Wrap a frame loader so it returns each frame truncated to bars <= as_of."""
    def _loader(tk):
        try:
            df = frame_loader(tk)
        except Exception:  # noqa: BLE001
            return None
        if df is None:
            return None
        try:
            return df.loc[:str(as_of)]
        except Exception:  # noqa: BLE001
            return df
    return _loader


def _od_asof(sector_arrays: dict, as_of):
    """Offense/defense reading AS OF ``as_of`` from preloaded sector close arrays."""
    if not sector_arrays:
        return None
    import pandas as pd

    def _loader(tk):
        arr = sector_arrays.get(str(tk).upper().strip())
        if arr is None:
            return None
        dates, closes, _ = arr
        pos = _pos_le(dates, as_of)
        if pos is None or pos < 1:
            return None
        return pd.Series(closes[:pos + 1])

    try:
        from lib import rotation as _rot
        return _rot.offense_defense_reading(_rot.build_sector_excess(_loader))
    except Exception:  # noqa: BLE001
        return None


def _components_asof(as_of, *, bench_arr, qqq_arr, universe_arrays, sector_arrays,
                     frame_loader, themes, reaction_records, bench_dates, cfg):
    """A :class:`FragilityComponents` recomputed AS OF a past trading day from
    cached data (the backfillable subset). Reused by the rolling raw series and
    the calibration backfill tool."""
    comp = FragilityComponents()
    if bench_arr is not None:
        d, c, v = bench_arr
        pos = _pos_le(d, as_of)
        if pos is not None:
            comp.distribution_days_spy = count_distribution_days(
                c[:pos + 1], v[:pos + 1], cfg["distribution_day_lookback"],
                cfg["distribution_day_pct"])
            comp.weak_bounce = detect_weak_bounce(c[:pos + 1], v[:pos + 1])
    if qqq_arr is not None:
        d, c, v = qqq_arr
        pos = _pos_le(d, as_of)
        if pos is not None:
            comp.distribution_days_qqq = count_distribution_days(
                c[:pos + 1], v[:pos + 1], cfg["distribution_day_lookback"],
                cfg["distribution_day_pct"])
    comp.breadth_above_sma20 = _breadth_above_sma_asof(universe_arrays, 20, as_of)
    comp.breadth_above_sma50 = _breadth_above_sma_asof(universe_arrays, 50, as_of)
    lb = int(cfg["breadth_slope_lookback_sessions"])
    pos = _pos_le(bench_dates, as_of)
    if pos is not None and pos - lb >= 0:
        prev = _breadth_above_sma_asof(universe_arrays, 20, bench_dates[pos - lb])
        comp.breadth_above_sma20_prev = prev
        if comp.breadth_above_sma20 is not None and prev is not None:
            comp.breadth_slope = round(comp.breadth_above_sma20 - prev, 4)
    gns, ev = _earnings_components_asof(reaction_records, bench_dates, as_of, cfg)
    comp.good_news_sold, comp.earnings_evaluated = gns, ev
    od = _od_asof(sector_arrays, as_of)
    if od:
        comp.offense_defense_direction = od.get("direction", "")
        comp.offense_defense_magnitude = od.get("magnitude", "")
    if themes and frame_loader is not None:
        shrink, vdeg, _ = leading_theme_volume_shrink(
            themes, _trunc_loader(frame_loader, as_of), cfg)
        comp.leading_theme_volume_shrinking = bool(shrink and not vdeg)
    return comp


def _raw_level_asof(as_of, **kw):
    """The raw fragility level recomputed AS OF a past trading day from cached data."""
    cfg = kw["cfg"]
    comp = _components_asof(as_of, **kw)
    points, _ = _score_components(comp, cfg)
    return _raw_level_from_points(points, cfg)


def compute_rolling_raw_series(window, *, bench_arr, qqq_arr, universe_arrays,
                               sector_arrays, frame_loader, themes,
                               reaction_records, bench_dates, today_str, cfg):
    """The recomputed raw level for each of the last ``window`` trading days
    (chronological ``[(date_str, raw_level, points), ...]``) from cached data — the
    SIGNAL trail hysteresis consumes. Empty when the benchmark calendar is unusable."""
    if not bench_dates:
        return []
    anchor = today_str or str(bench_dates[-1])
    pos_today = _pos_le(bench_dates, anchor)
    if pos_today is None:
        return []
    start = max(0, pos_today - int(window) + 1)
    series = []
    for i in range(start, pos_today + 1):
        d = bench_dates[i]
        comp = _components_asof(
            d, bench_arr=bench_arr, qqq_arr=qqq_arr, universe_arrays=universe_arrays,
            sector_arrays=sector_arrays, frame_loader=frame_loader, themes=themes,
            reaction_records=reaction_records, bench_dates=bench_dates, cfg=cfg)
        points, _ = _score_components(comp, cfg)
        series.append((str(d), _raw_level_from_points(points, cfg), points))
    return series


def _preload_sector_arrays(frame_loader) -> dict:
    """{TICKER: (dates, closes, vols)} for SPY + the offense/defense sector ETFs,
    loaded ONCE so offense/defense can be recomputed as-of any past day."""
    if frame_loader is None:
        return {}
    try:
        from lib import rotation as _rot
        tickers = {"SPY"}
        for s in list(_rot.OFFENSE_SECTORS) + list(_rot.DEFENSE_SECTORS):
            c = _rot.SECTOR_CONFIG.get(s)
            if c and c.get("etf"):
                tickers.add(str(c["etf"]).upper().strip())
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for tk in tickers:
        try:
            df = frame_loader(tk)
        except Exception:  # noqa: BLE001
            df = None
        arr = _dated_arrays(df) if df is not None else None
        if arr is not None:
            out[tk] = arr
    return out


def compute_market_fragility(*, universe=None, frame_loader=None,
                             benchmark_loader=None, sector_loader=None,
                             themes=None, earnings_reactions=None,
                             earnings_calendar_fn=None,
                             earnings_universe=None, earnings_frame_loader=None,
                             snapshot_dir=None, today_str: str = "",
                             config: Optional[dict] = None) -> FragilityReading:
    """Best-effort, network-free orchestration of the fragility components.

    All inputs are injectable so this is fully testable; each component degrades
    independently (and is listed in ``reading.degraded``) when its data is absent.
    ``frame_loader(ticker)`` and ``benchmark_loader(ticker)`` return cached OHLCV
    frames (cache-only on the ranking path); ``snapshot_dir`` is read for the
    hysteresis history. This NEVER touches the frozen regime classifier.

    Earnings scope (round 4): good-news-sold is a MARKET-internals signal, so its
    universe is the broad **scan** universe (``earnings_universe``, ~100-150
    tickers the candidate generator scanned this refresh), NOT the ranked top-N
    breadth ``universe``. Because the scan did not fetch 1y frames for every
    name, ``earnings_frame_loader`` is a CACHE-ONLY loader: report-tickers without
    a cache-resident frame are skipped+counted (``partial_frame_coverage`` when
    skipped > evaluated) rather than fetched. Both default to ``universe`` /
    ``frame_loader`` for backward compatibility (breadth-universe scope, no skips)."""
    cfg = config or INTERNALS_CONFIG
    degraded: list = []
    comp = FragilityComponents()
    # Earnings (good-news-sold) runs over the SCAN universe with a cache-only
    # loader; both fall back to the breadth universe / loader for old callers/tests.
    _earn_uni = earnings_universe if earnings_universe is not None else universe
    _earn_loader = earnings_frame_loader if earnings_frame_loader is not None else frame_loader

    # (c) distribution days on SPY/QQQ + (d) weak bounce on SPY.
    bl = benchmark_loader or frame_loader
    spy_c = spy_v = None
    _spy_frame = _qqq_frame = None
    bench_index = None  # the trading calendar for hysteresis adjacency (SPY, then QQQ)
    if bl is not None:
        try:
            _spy_frame = bl("SPY")
            spy_c, spy_v = _close_volume_lists(_spy_frame)
            bench_index = _frame_date_index(_spy_frame)
        except Exception:  # noqa: BLE001
            spy_c = spy_v = None
        try:
            _qqq_frame = bl("QQQ")
            qqq_c, qqq_v = _close_volume_lists(_qqq_frame)
            if bench_index is None:
                bench_index = _frame_date_index(_qqq_frame)
        except Exception:  # noqa: BLE001
            qqq_c = qqq_v = None
        comp.distribution_days_spy = count_distribution_days(spy_c, spy_v, cfg["distribution_day_lookback"], cfg["distribution_day_pct"]) if spy_c else None
        comp.distribution_days_qqq = count_distribution_days(qqq_c, qqq_v, cfg["distribution_day_lookback"], cfg["distribution_day_pct"]) if qqq_c else None
        if spy_c:
            comp.weak_bounce = detect_weak_bounce(spy_c, spy_v)
    if comp.distribution_days_spy is None and comp.distribution_days_qqq is None:
        degraded.append("distribution_days")
    if comp.weak_bounce is None:
        degraded.append("weak_bounce")

    # (b) breadth over the universe.
    if universe and frame_loader is not None:
        frames = {}
        for tk in universe:
            try:
                frames[tk] = frame_loader(tk)
            except Exception:  # noqa: BLE001
                frames[tk] = None
        comp.breadth_above_sma20 = breadth_above_sma(frames, 20)
        comp.breadth_above_sma50 = breadth_above_sma(frames, 50)
    if comp.breadth_above_sma20 is None:
        degraded.append("breadth")

    # Benchmark trading calendar (dates) for the rolling recomputation (Task A).
    bench_arr = _dated_arrays(_spy_frame) if _spy_frame is not None else None
    qqq_arr = _dated_arrays(_qqq_frame) if _qqq_frame is not None else None
    bench_dates = (bench_arr[0] if bench_arr else (qqq_arr[0] if qqq_arr else []))

    # (a) earnings reaction quality. ONE bulk earnings-calendar call → reports;
    # per-report reactions are computed once (with reaction date) so any past day
    # can be evaluated for the rolling series (Item 2 + Task A). The degrade REASON
    # is recorded distinctly (source failed vs no reports in window).
    earnings_degrade_reason = ""
    reaction_records: list = []
    if not earnings_reactions:
        reports = None
        if earnings_calendar_fn is not None:
            try:
                reports = earnings_calendar_fn() or []
            except Exception:  # noqa: BLE001 — the bulk call failed
                reports = None
        if reports is None:
            earnings_degrade_reason = ("finnhub_unavailable"
                                       if earnings_calendar_fn is not None
                                       else "earnings_source_absent")
        elif bench_dates:
            _asof = today_str or str(bench_dates[-1])
            reaction_records = _reaction_records(
                reports, _earn_loader, bench_dates, today_str, cfg, universe=_earn_uni)
            gns, ev = _earnings_components_asof(reaction_records, bench_dates,
                                                _asof, cfg)
            # Network-free coverage tally: scan-universe reports IN the window whose
            # frame was not cache-resident (skipped, not fetched).
            comp.earnings_skipped = _count_frameless_in_window(
                reports, _earn_loader, bench_dates, _asof, cfg, universe=_earn_uni)
            if ev:
                comp.good_news_sold, comp.earnings_evaluated = gns, ev
                # Thin coverage is a NOTE on a real reading, not a full degrade.
                if comp.earnings_skipped > ev:
                    earnings_degrade_reason = "partial_frame_coverage"
            elif comp.earnings_skipped > 0:
                # Reports WERE in window but no frame could be loaded → distinct
                # from "nothing in the window" (do not overload no_reports_in_window).
                earnings_degrade_reason = "partial_frame_coverage"
            else:
                earnings_degrade_reason = "no_reports_in_window"
        else:
            # No benchmark calendar → today-only fallback (round-3 path).
            earnings_reactions, earnings_degrade_reason = build_earnings_reactions(
                _earn_uni, _earn_loader, earnings_calendar_fn, today_str, cfg)
    if earnings_reactions and comp.earnings_evaluated == 0:
        gns, ev = count_good_news_sold(earnings_reactions, cfg["good_news_sold_reaction_pp"])
        comp.good_news_sold, comp.earnings_evaluated = gns, ev
    # Sanity bound (round 2, rescoped round 4): more reports evaluated than the SCAN
    # universe has tickers is impossible within the lookback window → degrade with a
    # distinct reason rather than report a wrong figure (the 39/92 market-wide leak).
    _uni_n = len(set(str(t).upper().strip() for t in (_earn_uni or [])))
    if _uni_n and comp.earnings_evaluated > _uni_n:
        comp.good_news_sold, comp.earnings_evaluated = None, 0
        earnings_degrade_reason = "implausible_count"
        reaction_records = []
    if comp.earnings_evaluated == 0:
        degraded.append("earnings_reaction")
        if earnings_degrade_reason:
            degraded.append(earnings_degrade_reason)

    # Leading-theme volume shrink (top-2 leaders) — from the same cached OHLCV,
    # no new fetch. Breadth-narrowing for leading themes stays SCAFFOLDED: it needs
    # per-theme historical internal breadth that the snapshot does not yet persist,
    # so it remains False and is listed in ``degraded``.
    shrink, vol_degraded, _vol_detail = leading_theme_volume_shrink(
        themes, frame_loader, cfg)
    comp.leading_theme_volume_shrinking = bool(shrink and not vol_degraded)
    if vol_degraded:
        degraded.append("leading_theme_volume")
    degraded.append("leading_theme_breadth_narrowing")  # scaffolded (no history)

    # (e) offense/defense reading (Task 2 outer ring), cache-only.
    offense_defense = None
    try:
        from lib import rotation as _rot
        _loader = sector_loader
        if _loader is None and frame_loader is not None:
            def _loader(tk):  # adapt a frame loader → Close Series
                df = frame_loader(tk)
                return None if df is None else df["Close"]
        if _loader is not None:
            offense_defense = _rot.offense_defense_reading(_rot.build_sector_excess(_loader))
    except Exception:  # noqa: BLE001
        offense_defense = None
    if not offense_defense:
        degraded.append("offense_defense")

    # ── Rolling raw-reading series (Task A — the SIGNAL trail) ────────────────
    # Recompute raw readings for the past N trading days from cached data; derive
    # today's breadth slope from this computed series (no day-one null) and let
    # hysteresis consume "what the market did". Snapshot history is the FALLBACK.
    rolling_series: list = []
    rolling_effective = rolling_consec = None
    universe_arrays = {tk: (_dated_arrays(df) if df is not None else None)
                       for tk, df in (locals().get("frames") or {}).items()}
    sector_arrays = _preload_sector_arrays(frame_loader)

    # ── Single data vintage guard (fix round) ────────────────────────────────
    # The benchmark and the universe frames must share their last trading date;
    # a mismatch (e.g. fresh benchmark fetch vs a stale on-disk universe cache)
    # means the rolling series would replay a DIFFERENT-vintage market, so it
    # degrades to the snapshot path + flags vintage_mismatch.
    _bench_last = bench_dates[-1] if bench_dates else None
    _uni_lasts = [a[0][-1] for a in universe_arrays.values() if a and a[0]]
    _uni_last = max(_uni_lasts) if _uni_lasts else None
    vintage_mismatch = bool(_bench_last and _uni_last and _bench_last != _uni_last)
    _vintage_candidates = [d for d in (_bench_last, _uni_last) if d is not None]
    data_vintage = str(min(_vintage_candidates)) if _vintage_candidates else ""
    if bench_dates:
        lb = int(cfg["breadth_slope_lookback_sessions"])
        pos_today = _pos_le(bench_dates, today_str or str(bench_dates[-1]))
        if pos_today is not None and pos_today - lb >= 0 and universe_arrays:
            _prev = _breadth_above_sma_asof(universe_arrays, 20, bench_dates[pos_today - lb])
            if _prev is not None:
                comp.breadth_above_sma20_prev = _prev
                if comp.breadth_above_sma20 is not None:
                    comp.breadth_slope = round(comp.breadth_above_sma20 - _prev, 4)
    try:
        rolling_series = compute_rolling_raw_series(
            int(cfg["rolling_window_sessions"]), bench_arr=bench_arr, qqq_arr=qqq_arr,
            universe_arrays=universe_arrays, sector_arrays=sector_arrays,
            frame_loader=frame_loader, themes=themes,
            reaction_records=reaction_records, bench_dates=bench_dates,
            today_str=today_str, cfg=cfg)
    except Exception:  # noqa: BLE001 — rolling unavailable → snapshot fallback
        rolling_series = []
    # A vintage mismatch forbids trusting the rolling replay (different market).
    if (not vintage_mismatch
            and len(rolling_series) >= int(cfg["hysteresis_escalate_sessions"])):
        rolling_effective, rolling_consec = _replay_hysteresis(
            [t[1] for t in rolling_series], cfg)

    # Hysteresis history from the snapshot memory (FALLBACK when the rolling series
    # is too shallow; with dates so gapped snapshots can't fabricate a run).
    prior_level, recent_raw, recent_dates = "normal", [], []
    if snapshot_dir is not None:
        metas = read_recent_meta(snapshot_dir, before_date=today_str or None)
        prior_level, recent_raw, recent_dates = history_from_snapshots(
            metas, before_date=today_str or None)
        if metas and comp.breadth_above_sma20_prev is None:
            comp.breadth_above_sma20_prev = metas[0].get("breadth_above_sma20")

    reading = compute_fragility(
        components=comp, offense_defense=offense_defense,
        prior_level=prior_level, recent_raw_levels=recent_raw,
        recent_dates=recent_dates, today_date=today_str or None,
        benchmark_index=bench_index,
        degraded=degraded, config=cfg)
    reading.earnings_degrade_reason = earnings_degrade_reason
    reading.rolling_window = int(cfg["rolling_window_sessions"])
    reading.rolling_raw_series = rolling_series
    reading.data_vintage = data_vintage
    reading.vintage_mismatch = vintage_mismatch
    if rolling_effective is not None:
        # Rolling is authoritative: escalation = condition held N recomputed
        # sessions (the intended meaning), adjacency inherent.
        reading.level = rolling_effective
        reading.consecutive_raw = rolling_consec
        reading.adjacency_degraded = False
        reading.hysteresis_source = "rolling"
    else:
        reading.hysteresis_source = "snapshot"
    return reading


def history_from_snapshots(meta_records, before_date: Optional[str] = None) -> tuple:
    """(prior_level, recent_raw_levels, recent_dates) from snapshot _meta records.

    ``meta_records`` is an iterable of prior days' snapshot header dicts (each with
    ``date`` + the fragility fields). Returns the most-recent prior persisted level,
    the list of prior RAW levels most-recent-first, and the parallel list of dates
    (so the hysteresis adjacency check can tell trading-day-adjacent records from
    gapped ones). Excludes records on/after ``before_date``. Fail-closed →
    ("normal", [], [])."""
    rows = []
    for m in meta_records or []:
        if not isinstance(m, dict):
            continue
        d = m.get("date")
        if before_date is not None and d is not None and str(d) >= str(before_date):
            continue
        raw = m.get("fragility_raw_level")
        lvl = m.get("fragility_level")
        if raw is None and lvl is None:
            continue
        rows.append((str(d or ""), lvl or "normal", raw or lvl or "normal"))
    rows.sort(key=lambda r: r[0], reverse=True)  # most recent first
    if not rows:
        return "normal", [], []
    prior_level = rows[0][1]
    recent_raw = [r[2] for r in rows]
    recent_dates = [r[0] for r in rows]
    return prior_level, recent_raw, recent_dates
