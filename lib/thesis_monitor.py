"""lib/thesis_monitor.py — Phase 6C-A Thesis Invalidation Monitor.

For each active :class:`lib.holdings.HoldingRecord`, this module checks four
independent signals and derives a deterministic ``thesis_status`` describing
whether the original thesis is still intact, worth watching, weakening, or
broken. The single product question it answers is:

    "I recorded a position in MU with a thesis. I open the app the next day —
     is the thesis intact or weakening, and why?"

The four signals (each fail-closed):

* **A. News** — one LLM call per holding reads the last 7 days of Finnhub
  company-news headlines and returns ``news_sentiment`` / ``thesis_relevant`` /
  ``key_development``. Cached TTL=14400 (4h) keyed on ``(ticker, date)``. This is
  the ONLY place this module uses an LLM — and the LLM only *interprets* news; it
  computes no levels and invents no numbers.
* **B. EPS revision** — reuses ``signal_engine.fetch_fundamental_signals`` and
  flags a deteriorating EPS revision direction. Cached TTL=86400 (24h) by the
  signal engine.
* **C. Technical breakdown** — reads ``lib.technical.snapshot()`` and flags real
  thesis-break conditions (loss of the 200-day SMA, an oversold breakdown, or a
  strong downtrend against the position). These are distinguished from a NORMAL
  pullback (price down but still above the 200-day SMA with a mid-range RSI).
* **D. Macro regime change** — reads the shared ``macro_regime_result`` and flags
  a risk-off / transition regime for short/mid-horizon holdings only.

Guardrails: free sources only (yfinance + Finnhub free tier); no paid API; no
broker / order / execution; no ``approved_for_execution`` field; no DB / vector
store / persistence (the 4-hour result cache is in-process only). Every fetch is
fail-closed; functions never raise to the page.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Cache TTLs (seconds). The full-result cache and the news LLM call are 4 hours;
# the EPS signal is effectively 24 hours via the signal-engine layer.
_NEWS_TTL = 14400  # 4 hours
_RESULT_TTL = 14400  # 4 hours
_MAX_WORKERS = 4

_VALID_SENTIMENT = ("positive", "neutral", "negative", "unknown")

# In-process TTL cache for the full monitor run (keyed on holding-signature +
# regime + date). NOT persisted to disk — purely a same-process memoization so a
# page rerun within the 4-hour window does not re-call the LLM.
_RESULT_CACHE: dict = {}


@dataclass
class ThesisCheckResult:
    """Per-holding thesis-invalidation assessment (review-only).

    ``thesis_status`` is computed DETERMINISTICALLY by :func:`compute_thesis_status`
    from the four signal flags; the LLM never decides the status. ``summary`` is a
    one-sentence, CODE-generated description (not LLM text).
    """

    holding_id: str = ""
    ticker: str = ""
    checked_at: str = ""  # ISO timestamp
    # --- A. news ---
    news_sentiment: str = "unknown"  # positive|neutral|negative|unknown
    thesis_relevant: bool = False
    key_development: str = ""
    # --- B. eps ---
    eps_revision_direction: str = "unknown"
    # --- C. technical ---
    technical_breakdown: bool = False
    technical_breakdown_reasons: list = field(default_factory=list)
    # --- D. macro ---
    macro_regime_flag: bool = False
    macro_regime_note: str = ""
    # --- D2. market-internals fragility (Phase 7B Task 3) — a WATCH-level
    #         annotation on signal D's area. It NEVER changes thesis_status (the
    #         monitor's existing semantics are intact); it only adds a note. ---
    fragility_level: str = "normal"
    fragility_watch: bool = False
    fragility_note: str = ""
    # --- derived ---
    thesis_status: str = "intact"  # intact|watch|weakening|broken
    price_vs_entry: float = 0.0  # (current / cost_basis - 1) * 100
    is_normal_pullback: bool = False
    summary: str = ""


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------


def _finite(x) -> Optional[float]:
    """Return ``x`` as a float, or ``None`` if missing / NaN / non-numeric."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    return None if xf != xf else xf  # NaN != NaN


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _regime_of(macro_result) -> str:
    """Extract a regime string from a MacroRegimeResult / dict / str (fail-closed)."""
    if macro_result is None:
        return "unknown"
    if isinstance(macro_result, str):
        return macro_result.strip().lower() or "unknown"
    if isinstance(macro_result, dict):
        return str(macro_result.get("regime", "unknown")).strip().lower() or "unknown"
    return str(getattr(macro_result, "regime", "unknown")).strip().lower() or "unknown"


# ---------------------------------------------------------------------------
# Deterministic thesis_status (the contract the test pins)
# ---------------------------------------------------------------------------


def compute_thesis_status(
    news_flag: bool,
    eps_flag: bool,
    technical_breakdown: bool,
    macro_regime_flag: bool,
    news_sentiment: str = "unknown",
    thesis_relevant: bool = False,
) -> str:
    """Map the four signal flags to a deterministic thesis status.

    Rules (evaluated in order):

    * **broken** — ``technical_breakdown`` is True on its own (a confirmed loss of
      trend is decisive), OR ``news_sentiment == "negative"`` AND
      ``thesis_relevant`` (the news directly refutes the thesis), OR 3+ flags
      triggered.
    * **weakening** — exactly 2 flags triggered.
    * **watch** — exactly 1 flag triggered.
    * **intact** — no flags triggered.

    ``news_flag`` is the general news concern flag and is True precisely when the
    news is negative AND thesis-relevant, so a single decisive news flag resolves
    to ``broken`` via the override above (matching the spec).
    """
    # Decisive single-signal "broken" overrides.
    if technical_breakdown:
        return "broken"
    if news_sentiment == "negative" and thesis_relevant:
        return "broken"

    n = sum(
        1
        for flag in (news_flag, eps_flag, technical_breakdown, macro_regime_flag)
        if bool(flag)
    )
    if n >= 3:
        return "broken"
    if n == 2:
        return "weakening"
    if n == 1:
        return "watch"
    return "intact"


# ---------------------------------------------------------------------------
# A. News signal (LLM interpretation; fail-closed; cached 4h)
# ---------------------------------------------------------------------------


def _news_default() -> dict:
    return {"news_sentiment": "unknown", "thesis_relevant": False, "key_development": ""}


def news_signal(ticker: str, thesis_text: str) -> dict:
    """Public wrapper around the cached news-signal LLM read (fail-closed)."""
    try:
        return _news_signal_cached((ticker or "").upper().strip(),
                                   (thesis_text or "")[:500], _today_str())
    except Exception:  # noqa: BLE001 — fail-closed
        return _news_default()


def _news_signal_cached(ticker: str, thesis_text: str, date: str) -> dict:
    """One LLM call interpreting the last 7 days of company news vs the thesis.

    Returns ``{"news_sentiment","thesis_relevant","key_development"}``. Fails
    closed to the neutral default on no Finnhub key / no news / no LLM key / any
    parse error. The ``date`` argument participates in the cache key so the read
    refreshes daily.
    """
    try:
        from lib.signal_engine import fetch_company_news, _has_llm_api_key
    except Exception:  # noqa: BLE001
        return _news_default()

    try:
        news = fetch_company_news(ticker, days=7)
        if not news or not _has_llm_api_key():
            return _news_default()

        lines = []
        for item in news[:20]:
            head = (item.get("headline") or "").strip()
            summ = (item.get("summary") or "").strip()
            line = head if not summ else f"{head} — {summ[:160]}"
            if line:
                lines.append(f"- {line}")
        news_block = "\n".join(lines) if lines else "(no headlines)"

        from lib import llm_orchestrator

        system = (
            "You are an equity analyst monitoring whether a stock's investment "
            "THESIS still holds. Read the recent company-news headlines and judge, "
            "relative to the user's stated thesis: (1) overall news sentiment, "
            "(2) whether the news is RELEVANT to the thesis (could it confirm or "
            "invalidate it), and (3) the single most important development. "
            "Output PURE JSON (no markdown) with exactly these fields: "
            '{"news_sentiment": "positive"|"neutral"|"negative"|"unknown", '
            '"thesis_relevant": true|false, '
            '"key_development": "one sentence, or empty string if none"}'
        )
        user = (
            f"Ticker: {ticker}\n"
            f"Thesis: {thesis_text or '(none given)'}\n\n"
            f"Last 7 days of company news (most recent first):\n{news_block}\n\n"
            "Return the JSON object only."
        )

        client = llm_orchestrator._get_client()
        parsed = llm_orchestrator._llm_json_call(client, 400, system, user)
        if not isinstance(parsed, dict):
            return _news_default()

        sentiment = parsed.get("news_sentiment")
        sentiment = sentiment if sentiment in _VALID_SENTIMENT else "unknown"
        relevant = bool(parsed.get("thesis_relevant", False))
        dev = parsed.get("key_development")
        dev = str(dev)[:300] if isinstance(dev, str) else ""
        return {
            "news_sentiment": sentiment,
            "thesis_relevant": relevant,
            "key_development": dev,
        }
    except Exception:  # noqa: BLE001 — fail-closed
        return _news_default()


# Wrap with st.cache_data when Streamlit is importable (offline tests still work
# because the body is fail-closed and the cache simply executes it).
try:  # pragma: no cover - cache decoration is environment dependent
    import streamlit as _st

    _news_signal_cached = _st.cache_data(ttl=_NEWS_TTL, show_spinner=False)(_news_signal_cached)
except Exception:  # noqa: BLE001
    pass


# ---------------------------------------------------------------------------
# B. EPS revision signal (reuses signal_engine; fail-closed)
# ---------------------------------------------------------------------------


def eps_signal(ticker: str) -> str:
    """Return the EPS revision/surprise direction for ``ticker`` (fail-closed).

    Reuses ``signal_engine.fetch_fundamental_signals`` (Finnhub /stock/earnings,
    cached TTL=1800 by the engine; effectively a daily signal in practice). The
    EPS flag fires when this direction is ``"deteriorating"`` — i.e. the earnings
    revision trend has turned DOWN versus the prior trend, which threatens a
    fundamentals-based thesis. Returns one of the engine's trend labels, or
    ``"unknown"`` on any failure.
    """
    try:
        from lib.signal_engine import fetch_fundamental_signals

        sig = fetch_fundamental_signals((ticker or "").upper().strip())
        return getattr(sig, "eps_surprise_trend", "unknown") or "unknown"
    except Exception:  # noqa: BLE001 — fail-closed
        return "unknown"


# ---------------------------------------------------------------------------
# C. Technical breakdown signal (deterministic; reads technical snapshot)
# ---------------------------------------------------------------------------


def technical_breakdown_signal(snap: dict, cost_basis: float) -> dict:
    """Deterministic thesis-break vs normal-pullback judgment from a snapshot.

    ``snap`` is the dict from ``lib.technical.snapshot()``. Returns
    ``{"technical_breakdown","reasons","is_normal_pullback","price_vs_entry","current_price"}``.

    Thesis-break conditions (any one triggers ``technical_breakdown``):

    * **broke_below_sma200** — price is below the 200-day SMA having (by the
      cost_basis proxy) been at/above it on entry. Losing the long-term trend line
      is a structural break, not noise.
    * **rsi_oversold_breakdown** — RSI(14) < 30: a momentum breakdown, not a mild dip.
    * **strong_downtrend_vs_entry** — ADX > 30 AND price is more than 10% below the
      cost basis: a confirmed strong trend running against the position.

    A NORMAL pullback (``is_normal_pullback``) is the explicit non-break case:
    price is below cost basis BUT still above the 200-day SMA with RSI in 35–50 —
    ordinary price noise within an intact uptrend.
    """
    snap = snap or {}
    price = _finite(snap.get("price"))
    sma200 = _finite(snap.get("SMA_200"))
    rsi = _finite(snap.get("RSI_14"))
    adx = _finite(snap.get("ADX"))
    above_sma200 = bool(snap.get("above_SMA200", False))
    cb = _finite(cost_basis)

    price_vs_entry = 0.0
    if price is not None and cb is not None and cb > 0:
        price_vs_entry = round((price / cb - 1.0) * 100.0, 2)

    reasons: list = []
    # broke below the 200-day SMA (entered at/above it, per the cost-basis proxy).
    if (
        price is not None
        and sma200 is not None
        and price < sma200
        and (cb is None or cb >= sma200)
    ):
        reasons.append("broke_below_sma200")
    # oversold momentum breakdown.
    if rsi is not None and rsi < 30.0:
        reasons.append("rsi_oversold_breakdown")
    # strong downtrend against the position (>10% under cost with a strong ADX).
    if adx is not None and adx > 30.0 and price_vs_entry < -10.0:
        reasons.append("strong_downtrend_vs_entry")

    technical_breakdown = len(reasons) > 0

    # Normal pullback: below cost, still above the 200DMA, RSI mid-low (35–50).
    is_normal_pullback = bool(
        cb is not None
        and price is not None
        and price < cb
        and above_sma200
        and rsi is not None
        and 35.0 <= rsi <= 50.0
    )

    return {
        "technical_breakdown": technical_breakdown,
        "reasons": reasons,
        "is_normal_pullback": is_normal_pullback,
        "price_vs_entry": price_vs_entry,
        "current_price": price if price is not None else 0.0,
    }


# ---------------------------------------------------------------------------
# D. Macro regime change signal (deterministic)
# ---------------------------------------------------------------------------


def short_time_stop_signal(holding, current_price: float) -> dict:
    """SHORT-horizon time stop: flag a stalled short-horizon position.

    For a ``horizon == "short"`` holding, if ``>= 5`` days have elapsed since
    ``entry_date`` AND the current price is still ``<= cost_basis × 1.02`` (no
    meaningful momentum), the short-horizon timing thesis has failed and we flag a
    technical time stop. Returns ``{"flag","reason"}``. Fail-closed -> no flag.
    """
    try:
        if (getattr(holding, "horizon", "mid") or "mid").strip().lower() != "short":
            return {"flag": False, "reason": ""}
        cb = _finite(getattr(holding, "cost_basis", None))
        cp = _finite(current_price)
        entry_date = (getattr(holding, "entry_date", "") or "").strip()
        if cb is None or cb <= 0 or cp is None or not entry_date:
            return {"flag": False, "reason": ""}
        try:
            entry = datetime.strptime(entry_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return {"flag": False, "reason": ""}
        days = (datetime.now(timezone.utc) - entry).days
        if days >= 5 and cp <= cb * 1.02:
            return {
                "flag": True,
                "reason": (
                    "SHORT position: 5+ days without momentum, consider time stop"
                ),
            }
        return {"flag": False, "reason": ""}
    except Exception:  # noqa: BLE001 — fail-closed
        return {"flag": False, "reason": ""}


def macro_regime_signal(regime: str, horizon: str) -> dict:
    """Flag a risk-off / transition regime for short/mid-horizon holdings.

    A long-horizon holding is NOT flagged by a macro regime change alone (the
    accumulation thesis tolerates short-term macro stress). Returns
    ``{"flag","note"}``.
    """
    r = (regime or "unknown").strip().lower()
    h = (horizon or "mid").strip().lower()
    if r in ("risk_off", "transition") and h in ("short", "mid"):
        return {
            "flag": True,
            "note": (
                f"Macro regime is {r}; unfavorable for a {h}-horizon position."
            ),
        }
    return {"flag": False, "note": ""}


# ---------------------------------------------------------------------------
# Per-holding assembly + summary
# ---------------------------------------------------------------------------


def _summary(result: "ThesisCheckResult") -> str:
    """One-sentence, code-generated summary (NOT LLM)."""
    status = result.thesis_status
    pv = result.price_vs_entry
    base = {
        "intact": "Thesis intact",
        "watch": "Thesis worth watching",
        "weakening": "Thesis weakening",
        "broken": "Thesis broken",
    }.get(status, "Thesis status unknown")
    parts = [f"{result.ticker}: {base} ({pv:+.1f}% vs entry)"]
    if result.is_normal_pullback and status in ("intact", "watch"):
        parts.append("normal pullback, not a thesis break")
    if result.technical_breakdown_reasons:
        parts.append("technical: " + ", ".join(result.technical_breakdown_reasons))
    if result.macro_regime_flag:
        parts.append("macro headwind")
    return "; ".join(parts) + "."


def _fragility_annotation(level: str) -> tuple:
    """(fragility_watch, bilingual note) for a fragility level. Annotation only —
    NEVER touches thesis_status. High → a watch-level note on the holding."""
    lvl = str(level or "normal").lower()
    if lvl == "high":
        return True, ("市场内部结构高度脆弱——关注持仓风险 | Market internals "
                      "fragility HIGH — watch holding risk")
    if lvl == "elevated":
        return False, ("市场内部结构转弱（关注） | Market internals fragility "
                       "elevated (watch)")
    return False, ""


def check_holding(holding, macro_result=None, regime: Optional[str] = None,
                  fragility_level: str = "normal") -> "ThesisCheckResult":
    """Run all four signals for one active holding and assemble the result.

    Fail-closed: any sub-signal that errors degrades to its neutral default; the
    function always returns a well-formed :class:`ThesisCheckResult`.

    ``fragility_level`` (Phase 7B Task 3) is a WATCH-level annotation on signal D:
    high fragility adds a note to the holding but NEVER escalates ``thesis_status``.
    """
    ticker = (getattr(holding, "ticker", "") or "").upper().strip()
    cost_basis = getattr(holding, "cost_basis", 0.0) or 0.0
    horizon = getattr(holding, "horizon", "mid") or "mid"
    thesis_text = getattr(holding, "thesis_text", "") or ""
    if regime is None:
        regime = _regime_of(macro_result)

    # A. news
    news = news_signal(ticker, thesis_text)
    news_flag = news["news_sentiment"] == "negative" and bool(news["thesis_relevant"])

    # B. eps
    eps_dir = eps_signal(ticker)
    eps_flag = eps_dir == "deteriorating"

    # C. technical
    try:
        from lib.signal_engine import _technical_snapshot

        snap = _technical_snapshot(ticker)
    except Exception:  # noqa: BLE001 — fail-closed
        snap = {}
    tech = technical_breakdown_signal(snap, cost_basis)

    # C2. SHORT-horizon time stop — a stalled short-horizon position (5+ days
    # without momentum) is a technical break; merge it into the technical signal.
    time_stop = short_time_stop_signal(holding, tech.get("current_price", 0.0))
    if time_stop["flag"]:
        reasons = list(tech.get("reasons", []))
        if "time_stop" not in reasons:
            reasons.append("time_stop")
        tech["reasons"] = reasons
        tech["technical_breakdown"] = True

    # D. macro
    macro = macro_regime_signal(regime, horizon)

    status = compute_thesis_status(
        news_flag=news_flag,
        eps_flag=eps_flag,
        technical_breakdown=tech["technical_breakdown"],
        macro_regime_flag=macro["flag"],
        news_sentiment=news["news_sentiment"],
        thesis_relevant=news["thesis_relevant"],
    )

    result = ThesisCheckResult(
        holding_id=getattr(holding, "id", "") or "",
        ticker=ticker,
        checked_at=_now_iso(),
        news_sentiment=news["news_sentiment"],
        thesis_relevant=bool(news["thesis_relevant"]),
        key_development=news["key_development"],
        eps_revision_direction=eps_dir,
        technical_breakdown=tech["technical_breakdown"],
        technical_breakdown_reasons=list(tech["reasons"]),
        macro_regime_flag=macro["flag"],
        macro_regime_note=macro["note"],
        thesis_status=status,
        price_vs_entry=tech["price_vs_entry"],
        is_normal_pullback=tech["is_normal_pullback"],
    )
    # D2 — fragility annotation (watch-level only; thesis_status untouched).
    fw, fnote = _fragility_annotation(fragility_level)
    result.fragility_level = str(fragility_level or "normal")
    result.fragility_watch = fw
    result.fragility_note = fnote
    result.summary = _summary(result)
    return result


# ---------------------------------------------------------------------------
# Full monitor run (parallel; 4-hour in-process result cache)
# ---------------------------------------------------------------------------


def _holdings_signature(active: list) -> tuple:
    """A hashable signature capturing the thesis-relevant fields of each holding."""
    sig = []
    for h in active:
        sig.append(
            (
                getattr(h, "id", ""),
                (getattr(h, "ticker", "") or "").upper().strip(),
                round(float(getattr(h, "cost_basis", 0.0) or 0.0), 4),
                getattr(h, "horizon", "mid"),
                (getattr(h, "thesis_text", "") or "")[:200],
            )
        )
    return tuple(sig)


def run_thesis_monitor(holdings: list, macro_result=None,
                       fragility_level: str = "normal") -> list:
    """Run the thesis monitor for every active holding (parallel; fail-closed).

    Uses a ``ThreadPoolExecutor(max_workers=4)`` so the per-holding LLM/news/EPS/
    technical fetches overlap. Results are memoized in-process for
    ``_RESULT_TTL`` (4 hours) keyed on ``(holdings signature, macro regime, date)``
    so a page rerun within the window does not re-call the LLM. Returns a
    ``list[ThesisCheckResult]`` aligned to the active holdings; never raises.
    """
    try:
        active = [h for h in (holdings or []) if getattr(h, "status", "active") == "active"]
    except Exception:  # noqa: BLE001
        return []
    if not active:
        return []

    regime = _regime_of(macro_result)
    date = _today_str()
    key = (_holdings_signature(active), regime, str(fragility_level or "normal"), date)

    now = time.time()
    cached = _RESULT_CACHE.get(key)
    if cached is not None and (now - cached[0]) < _RESULT_TTL:
        return cached[1]

    def _one(h):
        try:
            return check_holding(h, macro_result, regime, fragility_level)
        except Exception:  # noqa: BLE001 — never let one holding break the run
            return ThesisCheckResult(
                holding_id=getattr(h, "id", "") or "",
                ticker=(getattr(h, "ticker", "") or "").upper().strip(),
                checked_at=_now_iso(),
                thesis_status="intact",
                summary="Thesis check unavailable; treated as intact.",
            )

    results: list = []
    try:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            results = list(pool.map(_one, active))
    except Exception:  # noqa: BLE001 — pool failure -> sequential fallback
        results = [_one(h) for h in active]

    try:
        _RESULT_CACHE[key] = (now, results)
    except Exception:  # noqa: BLE001
        pass
    return results
