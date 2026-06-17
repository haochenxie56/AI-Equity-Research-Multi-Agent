"""
scripts/test_reliability_theme_transmission.py — Phase 7C theme-transmission tests.

Drives the REAL build path (build_theme_transmission_snapshot) — the same call
get_transmission_snapshot() caches — rather than hand-assembling a snapshot, so
the build-time integrity check (zero dangling chain-node refs) and the
schema-mapping are exercised end to end. Offline, deterministic, no network.

Also guards the module's reliability invariants: import isolation (S1), the
opportunity_ranker fail-closed import (S7), absence of any execution field (S8),
and a parity regression that the existing theme_baskets suite still passes (S9).

Run:
    python scripts/test_reliability_theme_transmission.py
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from lib.theme_baskets import THEME_BASKETS
from lib.reliability.phase5_theme_intelligence import (
    THEME_CANDIDATE_ROLES,
    ThemeIntelligenceSnapshot,
)
from lib.theme_transmission import (
    THEME_TRANSMISSION_ORDER,
    TICKER_ROLE_MAP,
    build_theme_transmission_snapshot,
    get_diffusion_context,
    get_theme_transmission_summary,
    get_ticker_role,
    get_transmission_cluster,
    get_transmission_order,
    get_transmission_snapshot,
)

_ORDER_BY_THEME = {e["theme"]: e["order"] for e in THEME_TRANSMISSION_ORDER}


def check(cond, msg: str) -> None:
    """Assert helper used by the S1/S7/S8/S9 reliability-invariant sections."""
    if not cond:
        raise AssertionError(msg)


def test_build_real_path_zero_dangling() -> None:
    """REAL build path: snapshot builds, validates, zero dangling chain refs."""
    snap = build_theme_transmission_snapshot()
    assert isinstance(snap, ThemeIntelligenceSnapshot)
    vs = snap.validation_summary
    assert vs is not None, "validation_summary must be attached"
    assert vs.dangling_chain_node_ref_count == 0, (
        f"unexpected dangling refs: {vs.issues}")
    assert vs.theme_count == len(THEME_BASKETS) == 12
    # One chain node per theme; candidates == total constituents.
    assert vs.chain_node_count == 12
    expected_candidates = sum(len(c["constituents"]) for c in THEME_BASKETS.values())
    assert vs.candidate_ticker_count == expected_candidates, (
        f"{vs.candidate_ticker_count} != {expected_candidates}")
    print(f"  build OK: {vs.theme_count} themes, "
          f"{vs.candidate_ticker_count} candidates, 0 dangling")


def test_schema_mapping_roles_and_links() -> None:
    """Candidate roles are valid literals; node upstream/downstream by order."""
    snap = build_theme_transmission_snapshot()
    by_theme = {t.name: t for t in snap.universe.themes}
    # Every candidate role is a valid ThemeCandidateRole literal.
    for theme in snap.universe.themes:
        for cand in theme.candidate_tickers:
            assert cand.role in THEME_CANDIDATE_ROLES, cand.role
        assert len(theme.industry_chain_nodes) == 1
        node = theme.industry_chain_nodes[0]
        # representative_tickers mirror the basket constituents.
        assert node.representative_tickers  # non-empty

    # ai_chips is order 1 -> empty upstream, downstream = all order-2 nodes.
    ai = by_theme[THEME_BASKETS["ai_chips"]["label_en"]]
    ai_node = ai.industry_chain_nodes[0]
    assert ai_node.upstream_node_ids == [], "order-1 theme must have no upstream"
    n_order2 = sum(1 for o in _ORDER_BY_THEME.values() if o == 2)
    assert len(ai_node.downstream_node_ids) == n_order2, (
        f"{len(ai_node.downstream_node_ids)} != {n_order2}")
    print(f"  schema mapping OK: roles valid; ai_chips downstream={n_order2} order-2 nodes")


def test_query_functions() -> None:
    """order / cluster / role queries, incl. unknown fallbacks (never raise)."""
    assert get_transmission_order("ai_chips") == 1
    assert get_transmission_cluster("ai_chips") == "compute_core"
    assert get_transmission_order("not_a_theme") is None
    assert get_transmission_cluster("not_a_theme") is None

    assert get_ticker_role("ai_chips", "NVDA") == "leader"
    assert get_ticker_role("ai_chips", "INTC") == "laggard"
    # Unassessed ticker / theme -> "unknown", never raises.
    assert get_ticker_role("ai_chips", "ZZZZ") == "unknown"
    assert get_ticker_role("not_a_theme", "NVDA") == "unknown"
    print("  query functions OK (unknown fallbacks never raise)")


def test_role_map_subset_of_constituents() -> None:
    """Every seed-mapped ticker is an actual basket constituent."""
    for theme, roles in TICKER_ROLE_MAP.items():
        consts = set(THEME_BASKETS[theme]["constituents"])
        stray = set(roles) - consts
        assert not stray, f"{theme}: seed tickers not in constituents: {stray}"
    print("  role map ⊆ constituents OK")


def test_summary_structure() -> None:
    """get_theme_transmission_summary returns the documented display shape."""
    s = get_theme_transmission_summary("ai_chips")
    assert s["theme"] == "ai_chips"
    assert s["transmission_order"] == 1
    assert s["transmission_cluster"] == "compute_core"
    assert s["seed_source"] == "manual"
    # All seven role buckets present; NVDA is a leader; buckets union == constituents.
    for role in ("leader", "second_derivative_beneficiary", "supplier",
                 "platform", "speculative", "laggard", "unknown"):
        assert role in s["roles"]
    assert "NVDA" in s["roles"]["leader"]
    bucketed = sorted(t for v in s["roles"].values() for t in v)
    assert bucketed == sorted(THEME_BASKETS["ai_chips"]["constituents"])
    # order 1 -> no upstream; downstream are order-2 themes; same-wave excludes self.
    assert s["upstream_themes"] == []
    assert "semiconductor_mfg" in s["downstream_themes"]
    assert "ai_chips" not in s["same_wave_themes"]

    # Unknown theme -> safe empty-ish summary, no raise.
    su = get_theme_transmission_summary("not_a_theme")
    assert su["transmission_order"] is None
    assert su["roles"]["leader"] == []
    print("  summary structure OK")


def test_diffusion_context() -> None:
    """get_diffusion_context is deterministic arithmetic on momentum scores."""
    # order 1 hottest -> active_order 1, next wave order 2.
    mom = {"ai_chips": 0.9, "semiconductor_mfg": 0.4, "hbm_memory": 0.3,
           "datacenter_power": 0.1}
    ctx = get_diffusion_context(mom)
    assert ctx["active_order"] == 1
    assert ctx["next_order"] == 2
    assert "semiconductor_mfg" in ctx["next_order_themes"]
    assert "compute_core" in ctx["active_clusters"]

    # Empty input -> all-empty safe context.
    empty = get_diffusion_context({})
    assert empty["active_order"] is None
    assert empty["next_order_themes"] == []

    # Lagging: within the active wave, a below-average theme is flagged.
    mom2 = {"semiconductor_mfg": 0.8, "hbm_memory": 0.2}  # both order 2
    ctx2 = get_diffusion_context(mom2)
    assert ctx2["active_order"] == 2
    assert "hbm_memory" in ctx2["lagging_themes"]
    assert "semiconductor_mfg" not in ctx2["lagging_themes"]
    print("  diffusion context OK")


def test_cache_identity() -> None:
    """get_transmission_snapshot caches (same object on repeat calls)."""
    a = get_transmission_snapshot()
    b = get_transmission_snapshot()
    assert a is b, "snapshot should be cached at module level"
    print("  cache identity OK")


def test_s1_import_isolation() -> None:
    """S1 — theme_transmission must not import the forbidden modules."""
    # S1 — Import isolation
    import ast, pathlib
    src = pathlib.Path("lib/theme_transmission.py").read_text()
    tree = ast.parse(src)
    forbidden = {"opportunity_ranker", "thesis_ingestion", "anchor_cache"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if node.module else [])
            )
            for name in names:
                for f in forbidden:
                    check(
                        f not in (name or ""),
                        f"S1: theme_transmission must not import {f} (found in {name})"
                    )
    print("  S1 import isolation OK")


def test_s7_ranker_fail_closed() -> None:
    """S7 — opportunity_ranker guards the theme_transmission import."""
    # S7 — opportunity_ranker fail-closed guard
    import ast, pathlib
    ranker_src = pathlib.Path("lib/opportunity_ranker.py").read_text()
    check(
        "ImportError" in ranker_src and "theme_transmission" in ranker_src,
        "S7: opportunity_ranker must have try/except ImportError guard "
        "around theme_transmission import"
    )
    # Verify the import is inside a try block (not top-level)
    ranker_tree = ast.parse(ranker_src)
    guarded = False
    for node in ast.walk(ranker_tree):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom):
                    if child.module and "theme_transmission" in child.module:
                        guarded = True
    check(guarded, "S7: theme_transmission import must be inside a try block")
    print("  S7 ranker fail-closed guard OK")


def test_s8_no_approved_for_execution() -> None:
    """S8 — no execution field may appear in theme_transmission."""
    # S8 — approved_for_execution guard
    import pathlib
    src = pathlib.Path("lib/theme_transmission.py").read_text()
    check(
        "approved_for_execution" not in src,
        "S8: lib/theme_transmission.py must not contain approved_for_execution"
    )
    print("  S8 no approved_for_execution OK")


def test_s9_theme_baskets_parity() -> None:
    """S9 — the existing theme_baskets suite still exits 0."""
    # S9 — parity regression: theme_baskets suite still exits 0
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "scripts/test_reliability_theme_baskets.py"],
        capture_output=True, text=True
    )
    check(
        result.returncode == 0,
        f"S9: test_reliability_theme_baskets.py exited {result.returncode}; "
        f"stdout tail: {result.stdout[-300:]}"
    )
    print("  S9 theme_baskets parity OK")


def main() -> int:
    tests = [
        test_build_real_path_zero_dangling,
        test_schema_mapping_roles_and_links,
        test_query_functions,
        test_role_map_subset_of_constituents,
        test_summary_structure,
        test_diffusion_context,
        test_cache_identity,
        test_s1_import_isolation,
        test_s7_ranker_fail_closed,
        test_s8_no_approved_for_execution,
        test_s9_theme_baskets_parity,
    ]
    print("Phase 7C theme_transmission tests")
    for tfn in tests:
        print(f"- {tfn.__name__}")
        tfn()
    print(f"\nALL {len(tests)} TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
