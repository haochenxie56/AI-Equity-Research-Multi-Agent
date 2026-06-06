"""lib/valuation_router.py — Phase "Valuation Refactor v1".

Deterministic (no LLM) **company classifier** + **growth-profile peer matching**.
Both feed the routed valuation in :mod:`lib.equity_valuation`: the classifier
picks which valuation METHODS are appropriate for a company type (so a single
PE×EPS formula is no longer applied to every company), and the peer matcher
replaces GICS-sector-median peers with growth-band + size-band matched peers for
the relative / EV-multiple anchors.

The motivation (KTOS-class case): a project-driven defense contractor has lumpy,
backlog-driven earnings, so a trailing-PE relative anchor produces garbage (e.g.
$3 vs a $30 analyst target → irreconcilable). Routing such a company to an
EV/EBITDA + analyst menu (PE excluded) yields a usable, reconcilable anchor set.

Guardrails: pure deterministic code; yfinance / Finnhub fields only (the SAME
``info`` dict already fetched by the valuation path — no new per-ticker network);
fail-closed (ambiguous inputs degrade to the default ``mature_profitable`` path);
review-only. The LLM never classifies or picks peers.

Five company types
------------------
* ``mature_profitable``   — stable margins, moderate growth, positive FCF.
* ``growth_profitable``   — high revenue growth, positive earnings.
* ``growth_unprofitable`` — high revenue growth, negative / near-zero earnings.
* ``project_driven``      — backlog / contract-driven, lumpy revenue (defense,
                            engineering & construction).
* ``cyclical``            — commodity / memory / industrial cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ===========================================================================
# Classifier config — ONE visible block (all thresholds, auditable)
# ===========================================================================

CLASSIFIER_CONFIG: dict = {
    # Revenue-growth bands (fraction, yoy). >= growth_high is "high"; in
    # [growth_moderate, growth_high) is "moderate"; below is "low".
    "growth_high": 0.25,
    "growth_moderate": 0.10,
    # Profitability. A net/operating margin >= margin_floor is "profitable";
    # a margin <= margin_near_zero is treated as unprofitable / near-zero.
    "margin_floor": 0.05,
    "margin_near_zero": 0.02,
    # Free cash flow positivity floor.
    "fcf_positive_floor": 0.0,
    # Volatility (coefficient of variation over the historical revenue / margin
    # series, when available). Lumpy revenue hints project_driven; volatile
    # margins hint cyclical. Both are OPTIONAL inputs (free sources rarely give a
    # clean series) — sector / industry hints are the primary signal.
    "revenue_cov_lumpy": 0.25,
    "margin_cov_cyclical": 0.40,
    # Size bands (market cap, USD).
    "size_large": 10_000_000_000.0,
    "size_mid": 2_000_000_000.0,
    # Borderline band: when the deciding numeric sits within this RELATIVE
    # fraction of its threshold the classification is flagged "borderline"
    # (which routes to the default mature_profitable menu — see select_method_menu).
    "borderline_rel_band": 0.15,
}

# Industry-name substrings (lower-cased contains-match) that mark a company as
# project / backlog driven. Industry is the strong signal; revenue lumpiness is a
# secondary / borderline confirmer.
# Precise industry-name phrases (avoid over-broad single words like
# "infrastructure", which would wrongly catch "Software—Infrastructure").
PROJECT_DRIVEN_INDUSTRY_HINTS: tuple = (
    "aerospace", "defense", "engineering & construction",
    "security & protection", "shipbuilding", "marine shipping",
)

# Sectors / industry substrings that mark a company as cyclical.
CYCLICAL_SECTORS: tuple = ("Energy", "Basic Materials")
# "memory" (not the broad "semiconductor") is the canonical cyclical semi —
# broad-based semiconductor growth names (e.g. NVDA) should route to a growth menu.
CYCLICAL_INDUSTRY_HINTS: tuple = (
    "memory", "steel", "oil", "gas", "mining", "chemical",
    "auto manufacturers", "airlines", "copper", "aluminum", "coal",
)

COMPANY_TYPES: tuple = (
    "mature_profitable", "growth_profitable", "growth_unprofitable",
    "project_driven", "cyclical",
)
DEFAULT_TYPE = "mature_profitable"


# ===========================================================================
# Result dataclass
# ===========================================================================


@dataclass
class CompanyClassification:
    """Deterministic company-type classification with auditable fired rules.

    ``fired_rules`` records, in the spirit of reason codes, each rule that was
    evaluated for the chosen branch with its value / operator / threshold so the
    decision is fully auditable. ``confidence`` is ``clear`` or ``borderline``;
    a borderline classification routes to the default ``mature_profitable`` menu
    (see :func:`select_method_menu`) while still reporting the detected type.
    """

    ticker: str = ""
    company_type: str = DEFAULT_TYPE
    confidence: str = "clear"  # clear | borderline
    fired_rules: list = field(default_factory=list)
    inputs: dict = field(default_factory=dict)
    rationale: str = ""

    @property
    def is_borderline(self) -> bool:
        return self.confidence == "borderline"


# ===========================================================================
# Numeric helpers
# ===========================================================================


def _num(x) -> Optional[float]:
    """Return ``x`` as a finite float, else ``None`` (rejects bool / NaN)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    return None if xf != xf else xf


def _rule(name: str, value, op: str, threshold, fired: bool) -> dict:
    return {"rule": name, "value": value, "op": op, "threshold": threshold,
            "fired": bool(fired)}


def _near(value: Optional[float], threshold: float, rel_band: float) -> bool:
    """True when ``value`` is within ``rel_band`` (relative) of ``threshold``."""
    if value is None or threshold == 0:
        return False
    return abs(value - threshold) <= abs(threshold) * rel_band


def growth_band(g: Optional[float], config: dict = CLASSIFIER_CONFIG) -> str:
    """Return ``high`` / ``moderate`` / ``low`` (``unknown`` when ``g`` is None)."""
    gv = _num(g)
    if gv is None:
        return "unknown"
    if gv >= config["growth_high"]:
        return "high"
    if gv >= config["growth_moderate"]:
        return "moderate"
    return "low"


def size_band(market_cap: Optional[float], config: dict = CLASSIFIER_CONFIG) -> str:
    """Return ``large`` / ``mid`` / ``small`` (``unknown`` when cap is None)."""
    mc = _num(market_cap)
    if mc is None or mc <= 0:
        return "unknown"
    if mc >= config["size_large"]:
        return "large"
    if mc >= config["size_mid"]:
        return "mid"
    return "small"


# ===========================================================================
# Task 1 — Company classifier (deterministic financial rules)
# ===========================================================================


def classify_company(
    *,
    ticker: str = "",
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    revenue_growth: Optional[float] = None,
    profit_margin: Optional[float] = None,
    operating_margin: Optional[float] = None,
    fcf: Optional[float] = None,
    market_cap: Optional[float] = None,
    revenue_cov: Optional[float] = None,
    margin_cov: Optional[float] = None,
    has_backlog: bool = False,
    config: dict = CLASSIFIER_CONFIG,
) -> CompanyClassification:
    """Classify one company into one of :data:`COMPANY_TYPES` (pure, fail-closed).

    Priority order (first match wins): project_driven → cyclical →
    growth_unprofitable → growth_profitable → mature_profitable (default). The
    margin used for profitability is ``profit_margin`` when present else
    ``operating_margin``. Volatility inputs (``revenue_cov`` / ``margin_cov``)
    are OPTIONAL secondary signals; the primary signal for project_driven /
    cyclical is the sector / industry hint.

    A classification is ``borderline`` when the deciding numeric sits within
    ``config["borderline_rel_band"]`` of its threshold, or when a
    project_driven / cyclical call rests on volatility alone (no name hint).
    Borderline classifications route to the default menu (see
    :func:`select_method_menu`) but still report the detected type.
    """
    t = (ticker or "").upper().strip()
    sector_s = (sector or "").strip()
    industry_l = (industry or "").lower().strip()
    g = _num(revenue_growth)
    pm = _num(profit_margin)
    om = _num(operating_margin)
    margin = pm if pm is not None else om
    fcf_v = _num(fcf)
    rcov = _num(revenue_cov)
    mcov = _num(margin_cov)
    gb = growth_band(g, config)
    sb = size_band(market_cap, config)

    inputs = {
        "sector": sector_s, "industry": industry or "",
        "revenue_growth": g, "margin": margin, "fcf": fcf_v,
        "market_cap": _num(market_cap), "revenue_cov": rcov, "margin_cov": mcov,
        "growth_band": gb, "size_band": sb, "has_backlog": bool(has_backlog),
    }

    rel_band = config["borderline_rel_band"]
    fired: list = []

    def _result(ctype: str, confidence: str, rationale: str) -> CompanyClassification:
        return CompanyClassification(
            ticker=t, company_type=ctype, confidence=confidence,
            fired_rules=fired, inputs=inputs, rationale=rationale,
        )

    # --- 1. project_driven: backlog / contract industry hint (or lumpy rev) --
    industry_hint = any(h in industry_l for h in PROJECT_DRIVEN_INDUSTRY_HINTS)
    lumpy = (rcov is not None and rcov >= config["revenue_cov_lumpy"])
    fired.append(_rule("project_industry_hint", industry or "", "contains",
                       PROJECT_DRIVEN_INDUSTRY_HINTS, industry_hint))
    fired.append(_rule("revenue_cov_lumpy", rcov, ">=",
                       config["revenue_cov_lumpy"], lumpy))
    fired.append(_rule("has_backlog", bool(has_backlog), "==", True, bool(has_backlog)))
    if industry_hint or has_backlog or lumpy:
        # Name hint / declared backlog -> clear; volatility-only -> borderline.
        conf = "clear" if (industry_hint or has_backlog) else "borderline"
        return _result("project_driven", conf,
                       "Backlog / contract-driven industry hint"
                       if (industry_hint or has_backlog)
                       else "Lumpy revenue (volatility-only) — borderline")

    # --- 2. cyclical: commodity / memory / industrial-cycle hint -------------
    sector_cyc = sector_s in CYCLICAL_SECTORS
    industry_cyc = any(h in industry_l for h in CYCLICAL_INDUSTRY_HINTS)
    margin_volatile = (mcov is not None and mcov >= config["margin_cov_cyclical"])
    fired.append(_rule("cyclical_sector", sector_s, "in", CYCLICAL_SECTORS, sector_cyc))
    fired.append(_rule("cyclical_industry_hint", industry or "", "contains",
                       CYCLICAL_INDUSTRY_HINTS, industry_cyc))
    fired.append(_rule("margin_cov_cyclical", mcov, ">=",
                       config["margin_cov_cyclical"], margin_volatile))
    if sector_cyc or industry_cyc or margin_volatile:
        conf = "clear" if (sector_cyc or industry_cyc) else "borderline"
        return _result("cyclical", conf,
                       "Commodity / memory / industrial-cycle sector hint"
                       if (sector_cyc or industry_cyc)
                       else "Volatile margins (volatility-only) — borderline")

    # --- 3. growth_unprofitable: high growth + negative/near-zero margin -----
    high_growth = (gb == "high")
    unprofitable = (margin is not None and margin <= config["margin_near_zero"])
    fired.append(_rule("revenue_growth_high", g, ">=", config["growth_high"], high_growth))
    fired.append(_rule("margin_near_zero_or_neg", margin, "<=",
                       config["margin_near_zero"], unprofitable))
    if high_growth and unprofitable:
        # Borderline when growth sits right on the high threshold.
        conf = "borderline" if _near(g, config["growth_high"], rel_band) else "clear"
        return _result("growth_unprofitable", conf,
                       "High revenue growth with negative / near-zero earnings")

    # --- 4. growth_profitable: high growth + positive earnings --------------
    profitable = (margin is not None and margin >= config["margin_floor"])
    fired.append(_rule("margin_profitable", margin, ">=", config["margin_floor"], profitable))
    if high_growth and profitable:
        conf = "clear"
        if (_near(g, config["growth_high"], rel_band)
                or _near(margin, config["margin_floor"], rel_band)):
            conf = "borderline"
        return _result("growth_profitable", conf,
                       "High revenue growth with positive earnings")

    # --- 5. mature_profitable: the default safe path ------------------------
    # A moderate-growth profitable company near the high-growth boundary is
    # flagged borderline (it could plausibly be growth_profitable next quarter).
    borderline = (gb == "moderate" and profitable
                  and g is not None and _near(g, config["growth_high"], rel_band))
    fired.append(_rule("default_mature", margin, "default", None, True))
    return _result("mature_profitable", "borderline" if borderline else "clear",
                   "Default: stable margins / moderate growth / positive FCF")


# ===========================================================================
# Method menu selection (which type's menu to actually USE)
# ===========================================================================


def select_method_menu(classification: CompanyClassification) -> str:
    """Return the company-type KEY whose method menu should be used.

    A ``borderline`` classification routes to the default
    ``mature_profitable`` menu (the prior, conservative behavior), while the
    detected ``company_type`` is still reported for the UI badge.
    """
    if classification is None:
        return DEFAULT_TYPE
    if classification.confidence == "borderline":
        return DEFAULT_TYPE
    ct = classification.company_type
    return ct if ct in COMPANY_TYPES else DEFAULT_TYPE


# ===========================================================================
# Task 3 — Growth-profile peer matching
# ===========================================================================


@dataclass
class PeerMatchResult:
    """Result of growth-profile peer matching.

    ``peer_basis`` is ``growth_matched`` when the matched set met the minimum
    size, else ``sector_fallback`` (matched on sector only). ``median_multiple``
    is the median of ``multiple_field`` over the matched peers (positive finite
    only), or ``None`` when no peer carried a usable multiple.
    """

    peers: list = field(default_factory=list)
    peer_basis: str = "growth_matched"  # growth_matched | sector_fallback
    median_multiple: Optional[float] = None
    multiple_field: str = ""
    matched_count: int = 0
    fallback_count: int = 0


def _median(vals: list) -> Optional[float]:
    nums = sorted(float(v) for v in vals)
    if not nums:
        return None
    n = len(nums)
    mid = n // 2
    if n % 2 == 1:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2.0


def match_growth_profile_peers(
    target: dict,
    candidates: list,
    *,
    multiple_field: str = "forwardPE",
    min_peers: int = 4,
    config: dict = CLASSIFIER_CONFIG,
) -> PeerMatchResult:
    """Match ``target`` to growth-profile peers from ``candidates`` (pure).

    A peer matches when it shares the target's **sector** AND **revenue-growth
    band** (``growth_band``) AND **size band** (``size_band``). When fewer than
    ``min_peers`` match, the matcher falls back to **sector-only** peers and sets
    ``peer_basis="sector_fallback"`` (honest about the weaker basis).

    ``candidates`` are the peer ``info`` dicts already fetched for the Equity
    page peer table (no new per-ticker network). Each should carry ``sector``,
    ``revenue_growth`` (or ``revenueGrowth``), ``market_cap`` (or ``marketCap``),
    and the chosen ``multiple_field`` (e.g. ``forwardPE``,
    ``priceToSalesTrailing12Months``). The target itself, if present in
    ``candidates``, is excluded by ticker.
    """
    tgt_sector = str(target.get("sector") or "").strip()
    tgt_growth = target.get("revenue_growth", target.get("revenueGrowth"))
    tgt_cap = target.get("market_cap", target.get("marketCap"))
    tgt_ticker = str(target.get("ticker") or "").upper().strip()
    tgt_gb = growth_band(tgt_growth, config)
    tgt_sb = size_band(tgt_cap, config)

    def _peer_field(p: dict, *names):
        for nm in names:
            if nm in p and p[nm] is not None:
                return p[nm]
        return None

    sector_peers: list = []
    growth_matched: list = []
    for p in candidates or []:
        if not isinstance(p, dict):
            continue
        p_ticker = str(p.get("ticker") or "").upper().strip()
        if p_ticker and tgt_ticker and p_ticker == tgt_ticker:
            continue
        p_sector = str(p.get("sector") or "").strip()
        if not p_sector or p_sector != tgt_sector:
            continue
        sector_peers.append(p)
        p_gb = growth_band(_peer_field(p, "revenue_growth", "revenueGrowth"), config)
        p_sb = size_band(_peer_field(p, "market_cap", "marketCap"), config)
        if p_gb == tgt_gb and tgt_gb != "unknown" and p_sb == tgt_sb and tgt_sb != "unknown":
            growth_matched.append(p)

    if len(growth_matched) >= min_peers:
        chosen, basis = growth_matched, "growth_matched"
    else:
        chosen, basis = sector_peers, "sector_fallback"

    mults = []
    for p in chosen:
        v = _peer_field(p, multiple_field)
        try:
            vf = float(v)
        except (TypeError, ValueError):
            continue
        if vf == vf and vf > 0:
            mults.append(vf)
    median_mult = _median(mults)

    return PeerMatchResult(
        peers=chosen,
        peer_basis=basis,
        median_multiple=(round(median_mult, 4) if median_mult is not None else None),
        multiple_field=multiple_field,
        matched_count=len(growth_matched),
        fallback_count=len(sector_peers),
    )
