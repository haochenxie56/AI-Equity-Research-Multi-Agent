"""
lib/theme_transmission.py — Phase 7C: AI industry-chain transmission mapping.

Purpose
-------
Add a deterministic **transmission chain** layer on top of the existing theme
basket system (``lib/theme_baskets.THEME_BASKETS``). It represents:

  1. The capital **propagation order** across themes (``transmission_order``,
     1-4). This is a *sequence*, NOT a strength / quality ranking. order=1
     moves first; order=4 has the longest lag. Same order value = same wave.
  2. The **cluster** that subdivides same-order themes by demand vs. supply
     logic (``transmission_cluster``).
  3. The per-ticker **role** in the chain (``leader``,
     ``second_derivative_beneficiary``, ``supplier``, ``platform``,
     ``speculative``, ``laggard``, ``unknown``) reusing the
     ``phase5_theme_intelligence.ThemeCandidateRole`` literal.

Unassessed tickers (those absent from the seed map) get ``role="unknown"``
automatically — this module never raises on an unknown ticker and never skips a
constituent.

Design
------
- Standalone, deterministic, offline. No network, no LLM, no Streamlit.
- Reuses the Phase 5J Pydantic schema (``phase5_theme_intelligence``) rather
  than introducing a parallel schema.
- The seed data (``THEME_TRANSMISSION_ORDER`` / ``TICKER_ROLE_MAP``) is a
  manually curated June-2026 snapshot; ``seed_source`` is always ``"manual"``
  in v1.

Disclaimer: outputs are for research / educational purposes only and do not
constitute investment advice.
"""

from __future__ import annotations

from lib.theme_baskets import THEME_BASKETS
from lib.reliability.phase5_theme_intelligence import (
    IndustryChainNode,
    ThemeCandidateRole,
    ThemeCandidateTicker,
    ThemeRecord,
    SubthemeRecord,
    ThemeIntelligenceSnapshot,
    ThemeUniverseSnapshot,
    make_theme_id,
    make_chain_node_id,
    make_subtheme_id,
    make_theme_intelligence_snapshot_id,
    validate_theme_intelligence_snapshot,
    attach_validation_summary,
)

# Isolation invariant: theme_transmission must never import from
# opportunity_ranker, thesis_ingestion, anchor_cache, or any pages/.
# It may import: theme_baskets, lib.reliability.phase5_theme_intelligence.
# (ThemeUniverseSnapshot / make_theme_intelligence_snapshot_id are also pulled
# from phase5_theme_intelligence — same allowed module — to assemble the
# snapshot; the task's listed subset was illustrative, not exhaustive.)


# ---------------------------------------------------------------------------
# 1A — Seed data (manually curated, June 2026)
# ---------------------------------------------------------------------------

# Capital propagation SEQUENCE across themes (NOT a strength ranking).
# order 1 moves first; order 4 is the longest-lag node. Same order = same wave;
# the cluster subdivides a wave by demand vs. supply logic.
THEME_TRANSMISSION_ORDER: list[dict] = [
    {"theme": "ai_chips",            "order": 1, "cluster": "compute_core"},
    {"theme": "semiconductor_mfg",   "order": 2, "cluster": "supply_chain"},
    {"theme": "hbm_memory",          "order": 2, "cluster": "supply_chain"},
    {"theme": "networking_optical",  "order": 3, "cluster": "infrastructure"},
    {"theme": "ai_servers_infra",    "order": 3, "cluster": "infrastructure"},
    {"theme": "datacenter_power",    "order": 4, "cluster": "physical_buildout"},
    {"theme": "cloud_hyperscaler",   "order": 2, "cluster": "demand_application"},
    {"theme": "data_infrastructure", "order": 3, "cluster": "demand_application"},
    {"theme": "ai_software",         "order": 3, "cluster": "demand_application"},
    {"theme": "cybersecurity",       "order": 3, "cluster": "defense_security"},
    {"theme": "edge_ai_devices",     "order": 4, "cluster": "endpoint_diffusion"},
    {"theme": "robotics_autonomous", "order": 3, "cluster": "adjacent_cycle"},
]

# Per-(theme, ticker) role within the chain. Roles are exactly the
# phase5_theme_intelligence.ThemeCandidateRole literals. Tickers absent here
# fall back to "unknown" (see get_ticker_role).
TICKER_ROLE_MAP: dict[str, dict[str, str]] = {
    "ai_chips": {
        "NVDA": "leader", "AVGO": "leader", "AMD": "leader",
        "MRVL": "second_derivative_beneficiary",
        "ARM": "second_derivative_beneficiary",
        "ALAB": "supplier", "QCOM": "platform", "INTC": "laggard",
        "MCHP": "supplier", "NXPI": "supplier",
    },
    "semiconductor_mfg": {
        "ASML": "leader", "TSM": "leader",
        "AMAT": "second_derivative_beneficiary",
        "LRCX": "second_derivative_beneficiary",
        "KLAC": "second_derivative_beneficiary",
        "SNPS": "platform", "CDNS": "platform",
        "TER": "supplier", "ONTO": "supplier", "ASX": "supplier",
    },
    "hbm_memory": {
        "MU": "leader", "MRVL": "second_derivative_beneficiary",
        "WDC": "platform", "STX": "platform", "PSTG": "platform",
        "NTAP": "platform",
        "SNDK": "supplier", "SIMO": "supplier", "DELL": "laggard",
    },
    "networking_optical": {
        "ANET": "leader", "COHR": "leader",
        "MRVL": "second_derivative_beneficiary",
        "AVGO": "second_derivative_beneficiary",
        "FN": "supplier", "LITE": "supplier", "GLW": "supplier",
        "CIEN": "platform",
        "CSCO": "laggard", "NOK": "laggard", "ERIC": "laggard",
    },
    "ai_servers_infra": {
        "SMCI": "leader", "CLS": "leader",
        "DELL": "second_derivative_beneficiary",
        "HPE": "second_derivative_beneficiary",
        "SANM": "supplier", "JBL": "supplier",
        "PSTG": "platform", "NTAP": "platform",
        "WDC": "supplier", "STX": "supplier",
    },
    "datacenter_power": {
        "VRT": "leader", "ETN": "leader",
        "PWR": "second_derivative_beneficiary",
        "EME": "second_derivative_beneficiary",
        "GEV": "second_derivative_beneficiary",
        "TT": "supplier", "CARR": "supplier", "JCI": "supplier",
        "CEG": "platform", "VST": "platform",
        "OKLO": "speculative",
    },
    "cloud_hyperscaler": {
        "MSFT": "leader", "GOOGL": "leader", "AMZN": "leader", "META": "leader",
        "ORCL": "second_derivative_beneficiary",
        "CRM": "platform", "IBM": "platform", "BABA": "platform",
        "SAP": "platform",
    },
    "data_infrastructure": {
        "SNOW": "leader", "PLTR": "leader",
        "DDOG": "second_derivative_beneficiary",
        "MDB": "second_derivative_beneficiary",
        "NET": "second_derivative_beneficiary",
        "CFLT": "supplier", "ESTC": "supplier",
        "GTLB": "platform", "S": "platform", "ORCL": "platform",
    },
    "ai_software": {
        "MSFT": "leader", "NOW": "leader",
        "CRM": "second_derivative_beneficiary",
        "INTU": "second_derivative_beneficiary",
        "ADBE": "second_derivative_beneficiary",
        "WDAY": "platform", "HUBS": "platform", "SHOP": "platform",
        "APPF": "platform",
        "DUOL": "speculative",
    },
    "cybersecurity": {
        "CRWD": "leader", "PANW": "leader",
        "ZS": "second_derivative_beneficiary",
        "NET": "second_derivative_beneficiary",
        "S": "second_derivative_beneficiary",
        "OKTA": "platform", "CYBR": "platform", "FTNT": "platform",
        "TENB": "supplier", "VRNS": "supplier",
    },
    "edge_ai_devices": {
        "AAPL": "leader", "QCOM": "leader",
        "NVDA": "second_derivative_beneficiary",
        "AMD": "second_derivative_beneficiary",
        "MSFT": "platform", "DELL": "platform",
        "INTC": "laggard",
        "HPQ": "supplier", "LOGI": "supplier", "STM": "supplier",
        "NXPI": "supplier",
    },
    "robotics_autonomous": {
        "TSLA": "leader", "ISRG": "leader",
        "SYM": "second_derivative_beneficiary",
        "TER": "second_derivative_beneficiary",
        "ROK": "platform", "HON": "platform", "ABBNY": "platform",
        "FANUY": "platform", "RR": "platform",
        "MBLY": "supplier", "OUST": "supplier",
    },
}


# ---------------------------------------------------------------------------
# Derived lookups (deterministic; built once at import)
# ---------------------------------------------------------------------------

_ORDER_BY_THEME: dict[str, int] = {
    e["theme"]: int(e["order"]) for e in THEME_TRANSMISSION_ORDER
}
_CLUSTER_BY_THEME: dict[str, str] = {
    e["theme"]: str(e["cluster"]) for e in THEME_TRANSMISSION_ORDER
}
# Preserve THEME_TRANSMISSION_ORDER declaration order for deterministic output.
_THEME_SEQUENCE: list[str] = [e["theme"] for e in THEME_TRANSMISSION_ORDER]


def _node_id(theme_key: str) -> str:
    """Deterministic chain-node id for a theme's single transmission node."""
    return make_chain_node_id(theme_key, theme_key)


def _themes_at_order(order: int) -> list[str]:
    """Theme keys at ``order`` in declaration order (deterministic)."""
    return [tk for tk in _THEME_SEQUENCE if _ORDER_BY_THEME.get(tk) == order]


# ---------------------------------------------------------------------------
# 1B — Build: baskets + seed maps -> phase5 ThemeIntelligenceSnapshot
# ---------------------------------------------------------------------------

# Roles surfaced in get_theme_transmission_summary, in a stable display order.
_SUMMARY_ROLE_ORDER: tuple[str, ...] = (
    "leader",
    "second_derivative_beneficiary",
    "supplier",
    "platform",
    "speculative",
    "laggard",
    "unknown",
)

_SNAPSHOT_CACHE: ThemeIntelligenceSnapshot | None = None


def build_theme_transmission_snapshot() -> ThemeIntelligenceSnapshot:
    """Map THEME_BASKETS + seed maps onto the Phase 5J theme-intelligence schema.

    For each theme in ``THEME_BASKETS`` we build exactly one
    ``IndustryChainNode`` (the theme's transmission node), one
    ``ThemeCandidateTicker`` per constituent, one ``SubthemeRecord`` per
    transmission cluster present (one per theme in v1), and one ``ThemeRecord``.

    Cross-theme transmission links live in each node's
    ``upstream_node_ids`` / ``downstream_node_ids``: a node's upstream is every
    theme one order earlier (``this_order - 1``) and its downstream is every
    theme one order later (``this_order + 1``), derived deterministically from
    ``THEME_TRANSMISSION_ORDER``. (The Phase 5J validator only checks
    ``subtheme`` / ``candidate`` chain refs *within* a theme, so these
    cross-theme links never trip the dangling-ref check — by design they cross
    theme boundaries.)

    The snapshot's ``validation_summary`` is populated; a non-zero
    dangling-chain-node-ref count is a build-time integrity failure and raises
    ``ValueError``.
    """
    themes: list[ThemeRecord] = []

    for theme_key, cfg in THEME_BASKETS.items():
        theme_id = make_theme_id(theme_key)
        node_id = _node_id(theme_key)
        constituents = list(cfg.get("constituents", []))

        this_order = _ORDER_BY_THEME.get(theme_key)
        cluster = _CLUSTER_BY_THEME.get(theme_key, "")

        # Cross-theme upstream / downstream by adjacent order level.
        upstream_ids: list[str] = []
        downstream_ids: list[str] = []
        if this_order is not None:
            upstream_ids = [_node_id(tk) for tk in _themes_at_order(this_order - 1)]
            downstream_ids = [_node_id(tk) for tk in _themes_at_order(this_order + 1)]

        node = IndustryChainNode(
            node_id=node_id,
            parent_theme_id=theme_id,
            name=cfg.get("label_en", theme_key) or theme_key,
            role_in_chain=cluster,
            upstream_node_ids=upstream_ids,
            downstream_node_ids=downstream_ids,
            representative_tickers=constituents,
        )

        # One candidate per constituent; role from seed map or "unknown".
        candidates: list[ThemeCandidateTicker] = []
        role_table = TICKER_ROLE_MAP.get(theme_key, {})
        for ticker in constituents:
            candidates.append(
                ThemeCandidateTicker(
                    ticker=ticker,
                    theme_id=theme_id,
                    role=role_table.get(ticker, "unknown"),
                )
            )

        # One subtheme per distinct cluster present (one per theme in v1).
        subthemes: list[SubthemeRecord] = []
        if cluster:
            subthemes.append(
                SubthemeRecord(
                    subtheme_id=make_subtheme_id(theme_id, cluster),
                    parent_theme_id=theme_id,
                    name=cluster,
                    description=(
                        f"Transmission cluster '{cluster}' for theme "
                        f"'{theme_key}'."
                    ),
                    chain_node_ids=[node_id],
                )
            )

        themes.append(
            ThemeRecord(
                theme_id=theme_id,
                name=cfg.get("label_en", theme_key) or theme_key,
                description=cfg.get("description_en", "") or "",
                industry_chain_nodes=[node],
                candidate_tickers=candidates,
                subthemes=subthemes,
            )
        )

    snapshot = ThemeIntelligenceSnapshot(
        snapshot_id=make_theme_intelligence_snapshot_id("theme_transmission_v1"),
        description=(
            "Phase 7C AI industry-chain transmission mapping built from "
            "THEME_BASKETS + manually curated transmission order / role seeds."
        ),
        universe=ThemeUniverseSnapshot(
            description="AI transmission-chain theme universe (Phase 7C).",
            themes=themes,
        ),
    )

    summary = validate_theme_intelligence_snapshot(snapshot)
    if summary.dangling_chain_node_ref_count:
        raise ValueError(
            "theme_transmission build integrity check failed: "
            f"{summary.dangling_chain_node_ref_count} dangling chain-node "
            f"ref(s): {summary.issues}"
        )
    return attach_validation_summary(snapshot)


def get_transmission_snapshot() -> ThemeIntelligenceSnapshot:
    """Return the cached transmission snapshot, building it on first call."""
    global _SNAPSHOT_CACHE
    if _SNAPSHOT_CACHE is None:
        _SNAPSHOT_CACHE = build_theme_transmission_snapshot()
    return _SNAPSHOT_CACHE


# ---------------------------------------------------------------------------
# 1C — Query functions (public API)
# ---------------------------------------------------------------------------


def get_transmission_order(theme: str) -> int | None:
    """Return capital propagation order (1-4) for a theme, or None."""
    return _ORDER_BY_THEME.get(theme)


def get_transmission_cluster(theme: str) -> str | None:
    """Return cluster string for a theme, or None."""
    return _CLUSTER_BY_THEME.get(theme)


def get_ticker_role(theme: str, ticker: str) -> str:
    """Return the ThemeCandidateRole for ``ticker`` in ``theme``.

    Returns ``"unknown"`` if the (theme, ticker) pair is not in the seed map.
    Never raises.
    """
    return TICKER_ROLE_MAP.get(theme, {}).get(ticker, "unknown")


def get_theme_transmission_summary(theme: str) -> dict:
    """Return a display-ready transmission summary for ``theme``.

    Constituents (from ``THEME_BASKETS``) are bucketed by role; constituents
    absent from the seed map land in the ``"unknown"`` bucket. ``upstream`` /
    ``downstream`` / ``same_wave`` themes are derived purely from the
    transmission order. ``seed_source`` is always ``"manual"`` in v1.
    """
    order = get_transmission_order(theme)
    cluster = get_transmission_cluster(theme)

    roles: dict[str, list[str]] = {r: [] for r in _SUMMARY_ROLE_ORDER}
    cfg = THEME_BASKETS.get(theme, {}) or {}
    for ticker in cfg.get("constituents", []) or []:
        roles[get_ticker_role(theme, ticker)].append(ticker)

    if order is None:
        upstream_themes: list[str] = []
        downstream_themes: list[str] = []
        same_wave_themes: list[str] = []
    else:
        upstream_themes = _themes_at_order(order - 1)
        downstream_themes = _themes_at_order(order + 1)
        same_wave_themes = [
            tk for tk in _themes_at_order(order) if tk != theme
        ]

    return {
        "theme": theme,
        "transmission_order": order,
        "transmission_cluster": cluster,
        "roles": roles,
        "upstream_themes": upstream_themes,
        "downstream_themes": downstream_themes,
        "same_wave_themes": same_wave_themes,
        "seed_source": "manual",
    }


def get_diffusion_context(themes_with_momentum: dict[str, float]) -> dict:
    """Deterministic capital-diffusion context from current momentum scores.

    ``themes_with_momentum`` maps theme_key -> momentum score (0-1), typically
    from ``compute_all_themes``. We average momentum per transmission order,
    pick the order with the highest average as the ``active_order`` (ties break
    to the lowest order number), report the clusters of the active-order themes,
    the next order and its themes (the potential next wave), and the
    active-order themes whose momentum trails their wave's average (laggards
    within the hot wave). Pure arithmetic — no LLM, no network.
    """
    empty = {
        "active_order": None,
        "active_clusters": [],
        "next_order": None,
        "next_order_themes": [],
        "lagging_themes": [],
    }
    if not themes_with_momentum:
        return empty

    # Group input momentum by transmission order (only known themes count).
    by_order: dict[int, list[tuple[str, float]]] = {}
    for theme, score in themes_with_momentum.items():
        order = _ORDER_BY_THEME.get(theme)
        if order is None:
            continue
        try:
            val = float(score)
        except (TypeError, ValueError):
            continue
        by_order.setdefault(order, []).append((theme, val))

    if not by_order:
        return empty

    # Highest average momentum wins; ties -> lowest order number.
    def _avg(pairs: list[tuple[str, float]]) -> float:
        return sum(v for _, v in pairs) / len(pairs) if pairs else 0.0

    active_order = min(
        by_order.keys(),
        key=lambda o: (-_avg(by_order[o]), o),
    )

    active_pairs = by_order[active_order]
    active_clusters = sorted(
        {_CLUSTER_BY_THEME[tk] for tk, _ in active_pairs if tk in _CLUSTER_BY_THEME}
    )

    next_order_themes = _themes_at_order(active_order + 1)
    next_order = active_order + 1 if next_order_themes else None

    wave_avg = _avg(active_pairs)
    lagging_themes = [
        tk for tk in _THEME_SEQUENCE
        if any(t == tk for t, _ in active_pairs)
        and dict(active_pairs)[tk] < wave_avg
    ]

    return {
        "active_order": active_order,
        "active_clusters": active_clusters,
        "next_order": next_order,
        "next_order_themes": next_order_themes,
        "lagging_themes": lagging_themes,
    }
