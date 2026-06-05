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

    # Volume character / rally quality.
    "rally_down_day_pct": -0.01,        # a session <= this defines the down day
    "volume_shrink_ratio": 0.90,        # bounce volume < this × down-day volume

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


def compute_market_fragility(*, universe=None, frame_loader=None,
                             benchmark_loader=None, sector_loader=None,
                             themes=None, earnings_reactions=None,
                             snapshot_dir=None, today_str: str = "",
                             config: Optional[dict] = None) -> FragilityReading:
    """Best-effort, network-free orchestration of the fragility components.

    All inputs are injectable so this is fully testable; each component degrades
    independently (and is listed in ``reading.degraded``) when its data is absent.
    ``frame_loader(ticker)`` and ``benchmark_loader(ticker)`` return cached OHLCV
    frames (cache-only on the ranking path); ``snapshot_dir`` is read for the
    hysteresis history. This NEVER touches the frozen regime classifier."""
    cfg = config or INTERNALS_CONFIG
    degraded: list = []
    comp = FragilityComponents()

    # (c) distribution days on SPY/QQQ + (d) weak bounce on SPY.
    bl = benchmark_loader or frame_loader
    spy_c = spy_v = None
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

    # (a) earnings reaction quality.
    if earnings_reactions:
        gns, ev = count_good_news_sold(earnings_reactions, cfg["good_news_sold_reaction_pp"])
        comp.good_news_sold, comp.earnings_evaluated = gns, ev
    else:
        degraded.append("earnings_reaction")

    # leading-theme internal flags — best-effort; degrade when history is absent.
    degraded.append("leading_theme_internals")

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

    # Hysteresis history from the snapshot memory (with dates for the adjacency
    # check — gapped snapshots must not fabricate a "consecutive" run).
    prior_level, recent_raw, recent_dates = "normal", [], []
    if snapshot_dir is not None:
        metas = read_recent_meta(snapshot_dir, before_date=today_str or None)
        prior_level, recent_raw, recent_dates = history_from_snapshots(
            metas, before_date=today_str or None)
        # carry forward a prior breadth reading for the slope, if present.
        if metas and comp.breadth_above_sma20_prev is None:
            comp.breadth_above_sma20_prev = metas[0].get("breadth_above_sma20")

    return compute_fragility(
        components=comp, offense_defense=offense_defense,
        prior_level=prior_level, recent_raw_levels=recent_raw,
        recent_dates=recent_dates, today_date=today_str or None,
        benchmark_index=bench_index,
        degraded=degraded, config=cfg)


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
