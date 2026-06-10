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

import re
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

# Industry-name hints (token-boundary matched — see industry_has_hint) that mark
# a company as project / backlog driven. Industry is the strong signal; revenue
# lumpiness is a secondary / borderline confirmer. Hints are matched as whole
# tokens / contiguous token runs, so over-broad single words (e.g. the removed
# "infrastructure") cannot match inside longer tokens like "Software—Infrastructure".
PROJECT_DRIVEN_INDUSTRY_HINTS: tuple = (
    "aerospace", "defense", "engineering & construction",
    "security & protection", "shipbuilding", "marine shipping",
)

# Sectors (exact match) / industry hints (token-boundary) that mark a company as
# cyclical.
CYCLICAL_SECTORS: tuple = ("Energy", "Basic Materials")
# "memory" (not the broad "semiconductor") is the canonical cyclical semi —
# broad-based semiconductor growth names (e.g. NVDA) should route to a growth menu.
CYCLICAL_INDUSTRY_HINTS: tuple = (
    "memory", "steel", "oil", "gas", "mining", "chemical",
    "auto manufacturers", "airlines", "copper", "aluminum", "coal",
)

# --- Ticker-level cyclical overrides (fix round 2, X5 — taxonomy WORKAROUND) ---
# EVIDENCE (live yfinance dump, 2026-06): memory / storage cyclicals are NOT
# distinguishable by industry string — yfinance reports MU / NVDA / AVGO / TXN ALL
# as industry "Semiconductors", and WDC / STX as "Computer Hardware". The "memory"
# industry hint therefore NEVER fires in production for MU, and broadening the hint
# to "semiconductor" was already rejected (it would wrongly route NVDA/AVGO/TXN —
# genuine growth names — to the cyclical menu). Oil/gas/materials cyclicals (e.g.
# XOM "Oil & Gas Integrated") DO route correctly via the industry/sector hints, so
# this override set is the SURGICAL workaround for the memory/storage gap only.
# Keep it tight and ticker-specific; do NOT use it as a dumping ground for borderline
# names. Reviewed against the dump: MU (DRAM), WDC + STX (NAND / HDD storage).
CYCLICAL_TICKER_OVERRIDES: frozenset = frozenset({"MU", "WDC", "STX"})

COMPANY_TYPES: tuple = (
    "mature_profitable", "growth_profitable", "growth_unprofitable",
    "project_driven", "cyclical",
)
DEFAULT_TYPE = "mature_profitable"


# ===========================================================================
# Token-boundary hint matching (review fix I8)
# ===========================================================================
#
# Industry / sector strings are matched against the hint lists by TOKEN BOUNDARY,
# not substring containment. A single-word hint must equal a whole token (so
# "gas" no longer matches inside "vegas", and "semiconductor" no longer matches
# "Semiconductors"); a multi-word hint must appear as a contiguous run of tokens.
# Tokenization lower-cases and splits on every non-alphanumeric character —
# including the em-dash used in yfinance industry strings ("Software—Infrastructure"
# → ["software", "infrastructure"]).


def _tokenize(s) -> list:
    """Lower-case ``s`` and split into alphanumeric tokens (em-dash aware)."""
    if not isinstance(s, str):
        return []
    return [tok for tok in re.split(r"[^a-z0-9]+", s.lower()) if tok]


def _hint_matches_tokens(text_tokens: list, hint: str) -> bool:
    """True when ``hint`` (tokenized) appears as a contiguous run in ``text_tokens``."""
    hint_tokens = _tokenize(hint)
    if not hint_tokens:
        return False
    n = len(hint_tokens)
    for i in range(len(text_tokens) - n + 1):
        if text_tokens[i:i + n] == hint_tokens:
            return True
    return False


def industry_has_hint(industry, hints) -> bool:
    """True when any hint in ``hints`` token-matches the ``industry`` string."""
    toks = _tokenize(industry)
    if not toks:
        return False
    return any(_hint_matches_tokens(toks, h) for h in hints)


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
    industry_hint = industry_has_hint(industry_l, PROJECT_DRIVEN_INDUSTRY_HINTS)
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
    # ticker_cyc (X5): a ticker-level override for memory/storage cyclicals that
    # yfinance's taxonomy cannot distinguish by industry string (see
    # CYCLICAL_TICKER_OVERRIDES). A clear, deterministic signal.
    ticker_cyc = t in CYCLICAL_TICKER_OVERRIDES
    sector_cyc = sector_s in CYCLICAL_SECTORS
    industry_cyc = industry_has_hint(industry_l, CYCLICAL_INDUSTRY_HINTS)
    margin_volatile = (mcov is not None and mcov >= config["margin_cov_cyclical"])
    fired.append(_rule("cyclical_ticker_override", t, "in",
                       sorted(CYCLICAL_TICKER_OVERRIDES), ticker_cyc))
    fired.append(_rule("cyclical_sector", sector_s, "in", CYCLICAL_SECTORS, sector_cyc))
    fired.append(_rule("cyclical_industry_hint", industry or "", "contains",
                       CYCLICAL_INDUSTRY_HINTS, industry_cyc))
    fired.append(_rule("margin_cov_cyclical", mcov, ">=",
                       config["margin_cov_cyclical"], margin_volatile))
    if ticker_cyc or sector_cyc or industry_cyc or margin_volatile:
        conf = "clear" if (ticker_cyc or sector_cyc or industry_cyc) else "borderline"
        if ticker_cyc:
            rationale = "Memory / storage cyclical (ticker override — yfinance taxonomy)"
        elif sector_cyc or industry_cyc:
            rationale = "Commodity / memory / industrial-cycle sector hint"
        else:
            rationale = "Volatile margins (volatility-only) — borderline"
        return _result("cyclical", conf, rationale)

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


# ===========================================================================
# Anchor Intelligence v2.5 — multi-dimensional peer profile + match quality
# ===========================================================================
#
# v1's matcher (above) is sector × growth × size with a raw-sector FALLBACK when
# < min_peers. That fallback peers a company to non-comparable names (SNOW to all
# "Software—Application"; KTOS to traditional defense primes). v2.5 replaces the
# fallback with an HONEST DEGRADE: extend the numeric dims (margin / profitability /
# cyclicality), intersect with the curated theme_baskets membership (single source
# of truth, shared with rotation) + a small human-reviewed peer_profiles override,
# and when the QUALIFIED set is still < N do NOT pad — report
# peer_match_quality="low" so the relative (peer-multiple) anchor is EXCLUDED
# downstream. A peer multiple from non-comparable companies is worse than none.
#
# See docs/reliability_anchor_intel_v2.md "Round v2.5" (STEP 0 matrix + decisions).

# Visible config block — peer numeric-dimension bands/thresholds (auditable). The
# growth_band / size_band dims reuse CLASSIFIER_CONFIG; only the NEW dims' bands
# live here.
PEER_DIM_CONFIG: dict = {
    # margin_band over operatingMargins (fallback profitMargins).
    "margin_high": 0.25,   # >= -> "high"
    "margin_mid": 0.10,    # >= -> "mid"
    "margin_low": 0.0,     # >= -> "low"; below -> "negative"
    # profitability_stage reuses the classifier's profitability thresholds so the
    # two stay consistent (one definition of "profitable" across the system).
    "profit_floor": CLASSIFIER_CONFIG["margin_floor"],         # >= -> profitable
    "profit_near_zero": CLASSIFIER_CONFIG["margin_near_zero"],  # < -> unprofitable
}

# Minimum QUALIFIED comparable peers; below this -> peer_match_quality "low".
MIN_QUALIFIED_PEERS = 4

# peer_match_quality tokens.
PEER_MATCH_HIGH = "high"
PEER_MATCH_LOW = "low"
PEER_MATCH_NOT_ASSESSED = ""   # peers not supplied (network-free / Trading-Desk path)
# Reason token surfaced when the qualified set is < MIN_QUALIFIED_PEERS.
REASON_INSUFFICIENT_PEERS = "insufficient_comparable_peers"

# The five numeric dims a candidate must share with the target (band equality).
PEER_NUMERIC_DIMS = (
    "growth_band", "size_band", "margin_band",
    "profitability_stage", "revenue_cyclicality",
)

# ---------------------------------------------------------------------------
# Manual override layer (peer_profiles) — human-reviewed; LLM MAY draft.
# ---------------------------------------------------------------------------
# ``ticker -> {"business_model": (...), "theme_exposure": (...)}`` tag sets for the
# corners theme_baskets do NOT cover. These tags participate in the tag-intersection
# EXACTLY like a basket membership: a candidate is a "tag peer" of the target when
# they share >= 1 tag (basket OR override). The override NEVER loosens the numeric
# dims and NEVER invents a multiple — it only supplies the missing taxonomy tag.
#
# DATA-DRIVEN + MINIMAL seed (the CYCLICAL_TICKER_OVERRIDES discipline): only names
# that (a) genuinely degrade under numeric-dims ∩ baskets AND (b) have an
# identifiable real sub-peer set the baskets miss. A name that degrades with NO good
# peer set is left OUT — it correctly STAYS peer_match_quality="low" (honest degrade,
# not a gap to patch). Expand only as real mismatches surface; never preemptively.
#
# KTOS is in NO theme_basket (there is no defense/unmanned-systems basket); the
# override documents its real peer tag. With no other defense-tech name in the
# universe carrying the tag, KTOS still qualifies < N and STAYS "low" — which is the
# CORRECT outcome (it should not be anchored to ill-fitting peer multiples).
PEER_PROFILES: dict = {
    "KTOS": {
        "business_model": ("defense_tech",),
        "theme_exposure": ("unmanned_systems", "defense_space"),
    },
}


def margin_band(margin: Optional[float], config: dict = PEER_DIM_CONFIG) -> str:
    """Return ``high`` / ``mid`` / ``low`` / ``negative`` (``unknown`` when None)."""
    m = _num(margin)
    if m is None:
        return "unknown"
    if m >= config["margin_high"]:
        return "high"
    if m >= config["margin_mid"]:
        return "mid"
    if m >= config["margin_low"]:
        return "low"
    return "negative"


def profitability_stage(margin: Optional[float], config: dict = PEER_DIM_CONFIG) -> str:
    """Return ``profitable`` / ``transitional`` / ``unprofitable`` (``unknown`` None).

    Reuses the classifier's profitability thresholds (one definition system-wide):
    ``margin >= profit_floor`` -> profitable; ``< profit_near_zero`` -> unprofitable;
    in between -> transitional (approaching break-even)."""
    m = _num(margin)
    if m is None:
        return "unknown"
    if m >= config["profit_floor"]:
        return "profitable"
    if m < config["profit_near_zero"]:
        return "unprofitable"
    return "transitional"


def is_cyclical(ticker: str = "", sector: Optional[str] = None,
                industry: Optional[str] = None) -> bool:
    """True when the name is a commodity / memory / industrial-cycle cyclical.

    Reuses the SAME signals as :func:`classify_company`'s cyclical branch — the
    ticker override, the cyclical sectors, and the cyclical industry hints — so the
    cyclicality dim never diverges from the classifier. Pure; no I/O."""
    t = (ticker or "").upper().strip()
    sector_s = (sector or "").strip()
    industry_l = (industry or "").lower().strip()
    return (t in CYCLICAL_TICKER_OVERRIDES
            or sector_s in CYCLICAL_SECTORS
            or industry_has_hint(industry_l, CYCLICAL_INDUSTRY_HINTS))


def revenue_cyclicality(ticker: str = "", sector: Optional[str] = None,
                        industry: Optional[str] = None) -> str:
    """Return ``cyclical`` or ``non_cyclical`` (never ``unknown`` — always decidable)."""
    return "cyclical" if is_cyclical(ticker, sector, industry) else "non_cyclical"


def _peer_get(p: dict, *names):
    """First non-None value among ``names`` in dict ``p`` (camel/snake tolerant)."""
    for nm in names:
        if nm in p and p[nm] is not None:
            return p[nm]
    return None


def numeric_dims(info: dict, *, ticker: str = "",
                 config: dict = PEER_DIM_CONFIG,
                 classifier_config: dict = CLASSIFIER_CONFIG) -> dict:
    """Compute the five numeric peer dims from an already-fetched ``info`` dict.

    Pure — reads only fields the Equity-page peer table already fetched
    (``sector``/``industry``/``revenueGrowth``/``marketCap``/``operatingMargins``/
    ``profitMargins``); NO new network. Camel-case (yfinance) and snake_case keys are
    both accepted. The operating margin is preferred; profit margin is the fallback."""
    tk = (ticker or str(info.get("ticker") or "")).upper().strip()
    sector = str(info.get("sector") or "")
    industry = str(info.get("industry") or "")
    g = _peer_get(info, "revenue_growth", "revenueGrowth")
    mc = _peer_get(info, "market_cap", "marketCap")
    om = _peer_get(info, "operating_margin", "operatingMargins")
    pmar = _peer_get(info, "profit_margin", "profitMargins")
    margin = _num(om)
    if margin is None:
        margin = _num(pmar)
    return {
        "growth_band": growth_band(g, classifier_config),
        "size_band": size_band(mc, classifier_config),
        "margin_band": margin_band(margin, config),
        "profitability_stage": profitability_stage(margin, config),
        "revenue_cyclicality": revenue_cyclicality(tk, sector, industry),
    }


def _dims_compatible(a: dict, b: dict) -> bool:
    """True when ALL five numeric dims are band-equal and neither side is unknown.

    Band equality is the v1 pattern; an ``unknown`` on either side fails that dim
    (we never match on absence). ``revenue_cyclicality`` is always decidable."""
    for k in PEER_NUMERIC_DIMS:
        av, bv = a.get(k), b.get(k)
        if av in (None, "unknown") or bv in (None, "unknown") or av != bv:
            return False
    return True


def basket_membership() -> dict:
    """``{TICKER: frozenset(basket_keys)}`` from the curated theme_baskets (read-only).

    Lazy + fail-closed: ``theme_baskets`` pulls yfinance / streamlit at import, so it
    is imported HERE (not at module top) to keep ``valuation_router`` cheap to import
    for standalone tests. On any failure returns ``{}`` (matching degrades to
    override-only tags). Single source of truth — the SAME membership the rotation
    pipeline uses; no second classification."""
    try:  # pragma: no cover - exercised via the real page path
        from lib.theme_baskets import THEME_BASKETS
    except Exception:  # noqa: BLE001 - fail-closed
        return {}
    out: dict = {}
    for key, cfg in THEME_BASKETS.items():
        for tk in (cfg.get("constituents") or []):
            out.setdefault(str(tk).upper().strip(), set()).add(key)
    return {k: frozenset(v) for k, v in out.items()}


def peer_tags_for(ticker: str, *, membership: Optional[dict] = None,
                  profiles: dict = PEER_PROFILES) -> frozenset:
    """All taxonomy tags for ``ticker`` = basket memberships ∪ override tags.

    ``membership`` (``{TICKER: frozenset}``) is injectable for determinism tests;
    defaults to the live :func:`basket_membership`. Override tags are the union of
    the ``business_model`` and ``theme_exposure`` sets in ``profiles``."""
    tk = (ticker or "").upper().strip()
    mem = membership if membership is not None else basket_membership()
    tags: set = set(mem.get(tk, frozenset()))
    prof = profiles.get(tk) or {}
    for grp in ("business_model", "theme_exposure"):
        for tag in (prof.get(grp) or ()):  # type: ignore[union-attr]
            tags.add(str(tag))
    return frozenset(tags)


@dataclass
class PeerProfileMatch:
    """Result of v2.5 multi-dimensional peer matching with honest match quality.

    ``peer_match_quality``: ``high`` (>= MIN_QUALIFIED_PEERS qualified), ``low``
    (fewer — the relative anchor should be EXCLUDED, NOT padded), or ``""`` (not
    assessed — no candidates supplied). ``reason`` is
    :data:`REASON_INSUFFICIENT_PEERS` when low. ``multiples`` is the median of each
    requested field OVER THE QUALIFIED SET (``None`` per field when low / no usable
    value) — never a sector-fallback median."""

    qualified_peers: list = field(default_factory=list)   # qualifying candidate dicts
    peer_match_quality: str = PEER_MATCH_NOT_ASSESSED
    reason: str = ""
    matched_count: int = 0
    multiples: dict = field(default_factory=dict)          # {field: median|None}
    target_dims: dict = field(default_factory=dict)        # audit
    target_tags: list = field(default_factory=list)        # audit (sorted)


def assess_peer_match(
    target: dict,
    candidates: list,
    *,
    multiple_fields: tuple = ("priceToSalesTrailing12Months", "enterpriseToEbitda"),
    min_peers: int = MIN_QUALIFIED_PEERS,
    membership: Optional[dict] = None,
    profiles: dict = PEER_PROFILES,
    config: dict = PEER_DIM_CONFIG,
    classifier_config: dict = CLASSIFIER_CONFIG,
) -> PeerProfileMatch:
    """Multi-dimensional peer match + honest ``peer_match_quality`` (pure, v2.5).

    A candidate QUALIFIES when it (1) is numerically compatible — shares ALL five
    :data:`PEER_NUMERIC_DIMS` bands — AND (2) shares >= 1 taxonomy tag (theme basket
    OR ``peer_profiles`` override) with the target. The target itself is excluded by
    ticker. When ``len(qualified) >= min_peers`` -> ``high`` and the median of each
    ``multiple_fields`` over the qualified set is reported; otherwise -> ``low`` +
    :data:`REASON_INSUFFICIENT_PEERS` and the multiples are ``None`` (NO raw-sector
    padding — the v1 fallback is deliberately not taken). Returns ``""`` quality when
    there are no candidates at all (matching was not assessed).

    ``candidates`` are the already-fetched Equity-page peer ``info`` dicts — NO new
    network. ``membership`` / ``profiles`` / ``config`` are injectable for
    determinism tests (fixed inputs -> fixed match)."""
    tgt_ticker = str(target.get("ticker") or "").upper().strip()
    tgt_dims = numeric_dims(target, ticker=tgt_ticker, config=config,
                            classifier_config=classifier_config)
    mem = membership if membership is not None else basket_membership()
    tgt_tags = peer_tags_for(tgt_ticker, membership=mem, profiles=profiles)

    if not candidates:
        return PeerProfileMatch(
            peer_match_quality=PEER_MATCH_NOT_ASSESSED,
            target_dims=tgt_dims, target_tags=sorted(tgt_tags))

    qualified: list = []
    for p in candidates:
        if not isinstance(p, dict):
            continue
        p_ticker = str(p.get("ticker") or "").upper().strip()
        if p_ticker and tgt_ticker and p_ticker == tgt_ticker:
            continue
        p_dims = numeric_dims(p, ticker=p_ticker, config=config,
                              classifier_config=classifier_config)
        if not _dims_compatible(tgt_dims, p_dims):
            continue
        p_tags = peer_tags_for(p_ticker, membership=mem, profiles=profiles)
        if not (tgt_tags and p_tags and (tgt_tags & p_tags)):
            continue
        qualified.append(p)

    matched_count = len(qualified)
    if matched_count >= min_peers:
        quality, reason = PEER_MATCH_HIGH, ""
        multiples = {f: _median(_finite_multiples(qualified, f)) for f in multiple_fields}
    else:
        quality, reason = PEER_MATCH_LOW, REASON_INSUFFICIENT_PEERS
        multiples = {f: None for f in multiple_fields}

    return PeerProfileMatch(
        qualified_peers=qualified,
        peer_match_quality=quality,
        reason=reason,
        matched_count=matched_count,
        multiples={f: (round(v, 4) if isinstance(v, (int, float)) else None)
                   for f, v in multiples.items()},
        target_dims=tgt_dims,
        target_tags=sorted(tgt_tags),
    )


def _finite_multiples(peers: list, field_name: str) -> list:
    """Positive finite values of ``field_name`` across ``peers`` (camel/snake)."""
    out: list = []
    for p in peers:
        v = _peer_get(p, field_name)
        try:
            vf = float(v)
        except (TypeError, ValueError):
            continue
        if vf == vf and vf > 0:
            out.append(vf)
    return out
