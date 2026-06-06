"""lib/valuation_anchor.py — Phase 6C-A v2 fair-value anchor (free sources only).

This module computes a conservative **fair-value anchor** for a ticker, used by
the LONG-horizon entry logic in ``lib/order_advisor.py`` to size a
margin-of-safety entry band. Entry Strategy v4 uses a **three-tier valuation
confidence** system over two independent, FREE estimates:

* ``analyst_anchor`` — yfinance ``targetMedianPrice`` (preferred, robust to one
  extreme target) else ``targetMeanPrice`` (the sell-side price target).
* ``relative_anchor`` — the median trailing P/E over the last (≤4) reported
  quarters × the current trailing EPS (a relative-valuation re-rating to the
  stock's own recent multiple).
* ``confidence`` (high / medium / low) combines analyst-coverage breadth
  (``analyst_count``), sell-side disagreement (``dispersion``), and the spread
  between the two methods (``anchor_spread``); ``conservative_anchor`` and
  ``fair_value_anchor`` are derived per tier. A low-confidence ticker falls back
  to a percentile-discounted current price (``valuation_anchor``).

Guardrails (Phase 6C-A v2): yfinance only (no paid API, no key); fail-closed
with a fixture fallback (``data_source="fixture"``); no broker / order /
execution; no DB / vector store; no ``approved_for_execution`` field. The anchor
is a deterministic, code-computed reference level — the LLM never produces it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

_LIVE = "live"
_FIXTURE = "fixture"
_CACHE_TTL = 3600  # 1 hour, keyed on ticker

# Anchor consistency gate (Phase "Valuation stop-the-bleed", Task 1). When the
# analyst and relative anchors disagree by more than this max/min ratio they are
# IRRECONCILABLE: confidence is forced low and conservative_anchor is None, so
# the LONG entry path cannot build a margin-of-safety band off a garbage anchor.
ANCHOR_DISPERSION_THRESHOLD = 3.0

_STATE_BLENDED = "blended"
_STATE_IRRECONCILABLE = "anchors_irreconcilable"
_STATE_NONE = "no_anchor"


@dataclass
class FairValueAnchor:
    """Deterministic, code-computed fair-value anchor for one ticker (no LLM).

    Entry Strategy v4 adds a **three-tier valuation confidence** system. The two
    independent anchors are ``analyst_anchor`` (sell-side price target, median
    preferred) and ``relative_anchor`` (the stock's own recent trailing-P/E
    re-rating). ``dispersion`` measures sell-side disagreement; ``anchor_spread``
    measures how far the two methods diverge; ``analyst_count`` is the breadth of
    coverage. ``confidence`` (high / medium / low) combines these, and
    ``conservative_anchor`` + ``fair_value_anchor`` are derived per tier.
    """

    ticker: str = ""
    analyst_target: Optional[float] = None       # yfinance targetMeanPrice (raw)
    analyst_anchor: Optional[float] = None        # targetMedianPrice, else targetMeanPrice
    relative_anchor: Optional[float] = None       # median trailing PE × trailing EPS
    valuation_anchor: Optional[float] = None       # percentile-discounted price fallback
    dispersion: Optional[float] = None             # (targetHigh − targetLow) / analyst_anchor
    anchor_spread: Optional[float] = None          # |analyst − relative| / min(analyst, relative)
    analyst_count: int = 0                         # numberOfAnalystOpinions (0 if absent)
    confidence: str = "low"                        # "high" | "medium" | "low"
    conservative_anchor: Optional[float] = None    # tier-dependent conservative anchor
    fair_value_anchor: float = 0.0                 # tier-dependent fair value (always > 0)
    # "blended" — the two anchors are consistent (or only one exists);
    # "anchors_irreconcilable" — they disagreed beyond ANCHOR_DISPERSION_THRESHOLD
    # so confidence is forced low and conservative_anchor is None; "no_anchor" —
    # neither method produced an anchor (percentile fallback only).
    anchor_state: str = _STATE_BLENDED
    data_sources: list = field(default_factory=list)  # which inputs contributed
    data_source: str = _FIXTURE                    # "live" | "fixture"


def _finite(x) -> Optional[float]:
    """Return ``x`` as a positive finite float, or ``None`` (rejects NaN / <= 0)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    if xf != xf or xf <= 0:  # NaN or non-positive
        return None
    return xf


def _median(vals: list) -> Optional[float]:
    """Plain median of a non-empty list of floats (no numpy dependency)."""
    nums = sorted(float(v) for v in vals)
    if not nums:
        return None
    n = len(nums)
    mid = n // 2
    if n % 2 == 1:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2.0


def compute_fair_value_anchor(
    ticker: str,
    current_price: float,
    valuation_percentile: float,
) -> FairValueAnchor:
    """Compute the :class:`FairValueAnchor` for ``ticker`` (yfinance only; fail-closed).

    Entry Strategy v4 — three-tier valuation confidence (all FREE / yfinance):

    * ``analyst_anchor`` = ``targetMedianPrice`` if available, else
      ``targetMeanPrice``, else ``None`` (the median is preferred as it is robust
      to one extreme target).
    * ``relative_anchor`` = median trailing P/E over the last ≤4 quarters ×
      ``trailingEps`` (None if either piece is unavailable).
    * ``dispersion`` = ``(targetHighPrice − targetLowPrice) / analyst_anchor``
      (sell-side disagreement; None if ``analyst_anchor`` is unavailable).
    * ``anchor_spread`` = ``|analyst_anchor − relative_anchor| /
      min(analyst_anchor, relative_anchor)`` (None if either anchor unavailable).
    * ``analyst_count`` = ``numberOfAnalystOpinions`` (0 if unavailable).
    * ``confidence`` —
      ``high`` when both anchors exist AND ``analyst_count ≥ 5`` AND
      ``dispersion ≤ 0.30`` AND ``anchor_spread ≤ 0.30``;
      ``medium`` when ``analyst_anchor`` exists AND ``analyst_count ≥ 3`` AND
      ``dispersion ≤ 0.50`` AND (``relative_anchor`` missing OR
      ``anchor_spread > 0.30``); ``low`` otherwise.
    * ``conservative_anchor`` — high: ``min(analyst, relative)``; medium:
      ``analyst_anchor``; low: ``None``.
    * ``fair_value_anchor`` — high: ``conservative × 0.90``; medium:
      ``conservative × 0.85``; low (soft fallback): ``current_price ×
      (1 − valuation_percentile × 0.30)`` (low-confidence — not anchor-backed).

    ``valuation_anchor`` (the percentile-discounted price) is retained for
    reference. Every branch is wrapped fail-closed. Cached TTL=3600 keyed on ticker.
    """
    t = (ticker or "").upper().strip()
    cp = _finite(current_price) or 0.0
    try:
        vp = float(valuation_percentile)
    except (TypeError, ValueError):
        vp = 0.5
    vp = max(0.0, min(1.0, vp))
    try:
        return _compute_cached(t, round(cp, 4), round(vp, 4))
    except Exception:  # noqa: BLE001 — fully fail-closed
        fallback = round((cp if cp > 0 else 100.0) * 0.85, 2)
        return FairValueAnchor(
            ticker=t,
            fair_value_anchor=fallback,
            data_sources=["fallback"],
            data_source=_FIXTURE,
        )


def _compute_cached(ticker: str, current_price: float, valuation_percentile: float) -> FairValueAnchor:
    """Cached worker (fail-closed). Separated so ``st.cache_data`` can wrap it."""
    cp = current_price if current_price and current_price > 0 else 100.0
    analyst_target: Optional[float] = None
    analyst_anchor: Optional[float] = None
    relative_anchor: Optional[float] = None
    dispersion: Optional[float] = None
    anchor_spread: Optional[float] = None
    analyst_count = 0
    sources: list = []
    live = False

    # yfinance is the ONLY external source (free, no key).
    info: dict = {}
    try:
        import yfinance as yf

        raw = yf.Ticker(ticker).info
        info = raw if isinstance(raw, dict) else {}
        if info:
            live = True
    except Exception:  # noqa: BLE001 — fail-closed (no live info)
        info = {}

    # --- 1. Analyst anchor: targetMedianPrice (priority) else targetMeanPrice -
    try:
        analyst_target = _finite(info.get("targetMeanPrice"))  # raw mean (reference)
        # Priority: median is robust to a single extreme target; fall back to mean.
        median_target = _finite(info.get("targetMedianPrice"))
        analyst_anchor = median_target if median_target is not None else analyst_target
        if analyst_anchor is not None:
            sources.append("analyst")
        try:
            analyst_count = int(info.get("numberOfAnalystOpinions") or 0)
        except (TypeError, ValueError):
            analyst_count = 0
    except Exception:  # noqa: BLE001
        analyst_target = None
        analyst_anchor = None
        analyst_count = 0

    # --- 2. Relative anchor: median trailing PE (last ≤4 quarters) × EPS ----
    try:
        eps = _finite(info.get("trailingEps"))
        pe_median = _median_trailing_pe(ticker)
        if eps is not None and pe_median is not None:
            relative_anchor = round(pe_median * eps, 2)
            if relative_anchor is not None and relative_anchor > 0:
                sources.append("relative")
            else:
                relative_anchor = None
    except Exception:  # noqa: BLE001
        relative_anchor = None

    # --- 3. Valuation-percentile fallback discount on current price --------
    valuation_anchor: Optional[float] = None
    try:
        valuation_anchor = round(cp * (1.0 - valuation_percentile * 0.30), 2)
        if valuation_anchor is not None and valuation_anchor > 0:
            sources.append("valuation_percentile")
        else:
            valuation_anchor = None
    except Exception:  # noqa: BLE001
        valuation_anchor = None

    # --- 4. Dispersion + anchor spread -------------------------------------
    try:
        hi = _finite(info.get("targetHighPrice"))
        lo = _finite(info.get("targetLowPrice"))
        if analyst_anchor is not None and hi is not None and lo is not None and hi >= lo:
            dispersion = round((hi - lo) / analyst_anchor, 4)
    except Exception:  # noqa: BLE001
        dispersion = None
    try:
        if analyst_anchor is not None and relative_anchor is not None:
            denom = min(analyst_anchor, relative_anchor)
            if denom > 0:
                anchor_spread = round(abs(analyst_anchor - relative_anchor) / denom, 4)
    except Exception:  # noqa: BLE001
        anchor_spread = None

    # --- 4b. Anchor consistency gate (max/min ratio across the two methods) -
    anchor_state = _STATE_BLENDED
    if analyst_anchor is not None and relative_anchor is not None:
        lo_a, hi_a = min(analyst_anchor, relative_anchor), max(analyst_anchor, relative_anchor)
        if lo_a > 0 and (hi_a / lo_a) > ANCHOR_DISPERSION_THRESHOLD:
            anchor_state = _STATE_IRRECONCILABLE
    elif analyst_anchor is None and relative_anchor is None:
        anchor_state = _STATE_NONE

    # --- 5. Three-tier confidence ------------------------------------------
    # Irreconcilable anchors short-circuit to low confidence — never blend a
    # margin-of-safety band off two estimates that disagree this badly.
    confidence = "low"
    if anchor_state == _STATE_IRRECONCILABLE:
        confidence = "low"
    elif (analyst_anchor is not None and relative_anchor is not None
            and analyst_count >= 5
            and dispersion is not None and dispersion <= 0.30
            and anchor_spread is not None and anchor_spread <= 0.30):
        confidence = "high"
    elif (analyst_anchor is not None and analyst_count >= 3
          and dispersion is not None and dispersion <= 0.50
          and (relative_anchor is None or (anchor_spread is not None and anchor_spread > 0.30))):
        confidence = "medium"

    # --- 6. Conservative anchor + tier-dependent fair value ----------------
    conservative_anchor: Optional[float] = None
    if confidence == "high":
        conservative_anchor = round(min(analyst_anchor, relative_anchor), 2)
        fair_value_anchor = round(conservative_anchor * 0.90, 2)
    elif confidence == "medium":
        conservative_anchor = round(analyst_anchor, 2)
        fair_value_anchor = round(conservative_anchor * 0.85, 2)
    else:  # low confidence — soft, percentile-discounted fallback (not anchor-backed)
        fair_value_anchor = round(cp * (1.0 - valuation_percentile * 0.30), 2)
        sources.append("fallback")
    if not (isinstance(fair_value_anchor, (int, float)) and fair_value_anchor > 0):
        fair_value_anchor = round(cp * 0.85, 2)

    return FairValueAnchor(
        ticker=ticker,
        analyst_target=analyst_target,
        analyst_anchor=(round(analyst_anchor, 2) if analyst_anchor is not None else None),
        relative_anchor=relative_anchor,
        valuation_anchor=valuation_anchor,
        dispersion=dispersion,
        anchor_spread=anchor_spread,
        analyst_count=analyst_count,
        confidence=confidence,
        conservative_anchor=conservative_anchor,
        fair_value_anchor=fair_value_anchor,
        anchor_state=anchor_state,
        data_sources=sources,
        data_source=_LIVE if live else _FIXTURE,
    )


def _median_trailing_pe(ticker: str) -> Optional[float]:
    """Median trailing P/E over the last (≤4) reported quarters (yfinance; fail-closed).

    Reconstructs a per-quarter trailing P/E as ``current price / (4 × quarterly
    diluted EPS)`` is unreliable, so we instead read each quarter's reported
    ``Diluted EPS`` (or ``Basic EPS``) from the quarterly income statement and
    compute the median of ``current_price / (annualized EPS)`` where annualized
    EPS = quarterly EPS × 4. Returns ``None`` when the statement / EPS rows are
    unavailable. Purely fail-closed (no raise).
    """
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        qf = getattr(t, "quarterly_income_stmt", None)
        if qf is None or getattr(qf, "empty", True):
            qf = getattr(t, "quarterly_financials", None)
        if qf is None or getattr(qf, "empty", True):
            return None

        def _row(names):
            for n in names:
                if n in qf.index:
                    return qf.loc[n]
            return None

        eps_row = _row(["Diluted EPS", "DilutedEPS", "Basic EPS", "BasicEPS"])
        if eps_row is None:
            return None
        info = t.info if isinstance(getattr(t, "info", None), dict) else {}
        price = _finite(info.get("currentPrice") or info.get("regularMarketPrice")
                        or info.get("previousClose"))
        if price is None:
            return None
        pes: list = []
        for c in list(qf.columns)[:4]:
            try:
                q_eps = float(eps_row[c])
            except (TypeError, ValueError, KeyError):
                continue
            annual_eps = q_eps * 4.0
            if annual_eps > 0:
                pes.append(price / annual_eps)
        if not pes:
            return None
        return _median(pes)
    except Exception:  # noqa: BLE001 — fail-closed
        return None


# Decorate the cached worker with st.cache_data when Streamlit is importable
# (the body is fail-closed, so offline tests simply execute it once per call).
try:  # pragma: no cover - cache decoration is environment dependent
    import streamlit as _st

    _compute_cached = _st.cache_data(ttl=_CACHE_TTL, show_spinner=False)(_compute_cached)
except Exception:  # noqa: BLE001
    pass
