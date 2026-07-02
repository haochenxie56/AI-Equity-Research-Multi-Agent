"""
scripts/test_degradation_view.py

Tests for lib/degradation_view.py — the Degradation-Visibility Layer enabler.

REAL-PATH DISCIPLINE: the load-ordering / grouping tests write real AgentOutput
JSONL to a temp ``base_dir`` and drive the REAL ``load_agent_outputs`` →
``build_view_*`` path (the same deserialization + timestamp-sort the review page
triggers), NOT hand-built AgentDegradationView objects. The build-rule tests
construct real ``AgentOutput`` dataclass instances and call the build functions
directly. Fixture VALUES mirror the shapes dumped from real production files.

The eight numbered cases required by the phase spec are each a clearly separated,
individually-named ``test_caseN_*`` function (see the mapping printed at the end
of a run).

Run:
    python scripts/test_degradation_view.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from lib.agent_framework.agent_output import AgentOutput  # noqa: E402
from lib.degradation_view import (  # noqa: E402
    KNOWN_DEFENSIVE_FLAGS,
    build_view_candidate_screening,
    build_view_macro_regime,
    build_view_market_structure,
    build_view_money_flow,
    build_view_sector_rotation,
    build_view_theme_intelligence,
    list_available_dates,
    load_and_build_all_views,
    normalize_basis,
    _severity_rank,
    _worst_basis,
)

_DATE = "2026-07-01"

_ALL_BUILDERS = [
    ("MacroRegimeAgent", build_view_macro_regime),
    ("MoneyFlowAgent", build_view_money_flow),
    ("MarketStructureAgent", build_view_market_structure),
    ("SectorRotationAgent", build_view_sector_rotation),
    ("ThemeIntelligenceAgent", build_view_theme_intelligence),
    ("CandidateScreeningAgent", build_view_candidate_screening),
]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _ao(agent_id: str, supporting_data: dict, *,
        ts: str = f"{_DATE}T12:00:00Z",
        judgment: str = "A qualitative one-sentence judgment.",
        source: str = "llm_proposed") -> AgentOutput:
    """A real AgentOutput dataclass instance (evidence_refs empty is fine — the
    non-empty invariant is enforced only at creation-mapping time, not here)."""
    return AgentOutput(
        agent_id=agent_id,
        timestamp=ts,
        horizon="cross",
        judgment=judgment,
        confidence=0.5,
        evidence_refs=[],
        supporting_data=supporting_data,
        requires_human_confirmation=True,
        judgment_source=source,
        valid_until=f"{_DATE}T23:59:59Z",
    )


def _record(agent_id: str, supporting_data: dict, *,
            ts: str = f"{_DATE}T12:00:00Z",
            judgment: str = "A qualitative one-sentence judgment.",
            source: str = "llm_proposed") -> dict:
    """A minimal-but-valid AgentOutput dict for JSONL (the load path)."""
    return {
        "agent_id": agent_id, "timestamp": ts, "horizon": "cross",
        "judgment": judgment, "confidence": 0.5, "evidence_refs": [],
        "supporting_data": supporting_data, "requires_human_confirmation": True,
        "judgment_source": source, "valid_until": f"{_DATE}T23:59:59Z",
        "agent_result": None, "debate_report": None,
    }


def _write(base_dir: str, agent_id: str, records: list, date: str = _DATE) -> None:
    d = os.path.join(base_dir, agent_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{date}.jsonl"), "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ===========================================================================
# The eight REQUIRED numbered cases
# ===========================================================================

def test_case1_marketstructure_degraded_no_vintage_key():
    """1. signal_basis=degraded_insufficient with NO vintage_mismatch key at all
    → basis_state 'degraded' AND likely_bug True. A naive flags-only check would
    wrongly return likely_bug=False here (degrade_flags is empty)."""
    rec = _ao("MarketStructureAgent", {
        "signal_basis": "degraded_insufficient",
        "short_confidence": 0.1,
        # NOTE: no 'vintage_mismatch' / 'adjacency_degraded' keys present at all.
    })
    v = build_view_market_structure([rec])[0]
    assert v.basis_state == "degraded", v.basis_state
    assert v.degrade_flags == [], v.degrade_flags          # nothing in the flags list
    assert v.likely_bug is True                            # caught by basis=="degraded"
    print("  OK  case 1 — degraded basis w/o a named flag still flags likely_bug")


def test_case2_rule_based_textbook_normal():
    """2. judgment_source=rule_based with textbook-normal supporting_data
    (signal_present, no flags) → likely_bug still True (the source check is a
    true OR, not gated on a bad basis)."""
    rec = _ao("MarketStructureAgent",
              {"signal_basis": "signal_present", "short_confidence": 0.9},
              source="rule_based")
    v = build_view_market_structure([rec])[0]
    assert v.basis_state == "ok"
    assert v.degrade_flags == []
    assert v.likely_bug is True                            # driven solely by source
    print("  OK  case 2 — rule_based fallback flags likely_bug on a clean read")


def test_case3_same_agent_later_timestamp_wins():
    """3. Two records, same agent + date, different timestamps (written OUT of
    order) → the view reflects the LATER record (exercises load's ascending
    sort)."""
    with tempfile.TemporaryDirectory() as base:
        _write(base, "MacroRegimeAgent", [
            _record("MacroRegimeAgent", {"regime": "risk_on", "data_coverage": 1.0},
                    ts=f"{_DATE}T15:00:00Z", judgment="LATER"),      # written first
            _record("MacroRegimeAgent", {"regime": "degraded", "data_coverage": 0.2},
                    ts=f"{_DATE}T09:00:00Z", judgment="EARLIER"),    # written second
        ])
        views = load_and_build_all_views(date=_DATE, base_dir=base)
        v = views["MacroRegimeAgent"][0]
        assert v.source.judgment == "LATER", v.source.judgment
        assert v.basis_state == "ok"                       # later record's regime
    print("  OK  case 3 — later timestamp wins regardless of file order")


def test_case4_candidate_two_themes_later_wins():
    """4. Three CandidateScreening records across two theme_keys (two for theme A
    at different timestamps, one for theme B) → exactly two views (one per
    theme), and theme A reflects its LATER record."""
    with tempfile.TemporaryDirectory() as base:
        _write(base, "CandidateScreeningAgent", [
            _record("CandidateScreeningAgent", {
                "theme_key": "themeA", "signal_basis_short": "no_clear_winner",
                "signal_basis_mid": "no_clear_winner",
                "short_confidence": 0.0, "mid_confidence": 0.0},
                ts=f"{_DATE}T09:00:00Z", judgment="A_EARLY"),
            _record("CandidateScreeningAgent", {
                "theme_key": "themeA", "signal_basis_short": "signal_present",
                "signal_basis_mid": "signal_present",
                "short_confidence": 1.0, "mid_confidence": 1.0},
                ts=f"{_DATE}T15:00:00Z", judgment="A_LATE"),
            _record("CandidateScreeningAgent", {
                "theme_key": "themeB", "signal_basis_short": "no_clear_winner",
                "signal_basis_mid": "no_clear_winner",
                "short_confidence": 0.5, "mid_confidence": 0.5},
                ts=f"{_DATE}T12:00:00Z", judgment="B"),
        ])
        views = load_and_build_all_views(date=_DATE, base_dir=base)
        cvs = views["CandidateScreeningAgent"]
        assert len(cvs) == 2, len(cvs)
        by_theme = {v.theme_key: v for v in cvs}
        assert set(by_theme) == {"themeA", "themeB"}
        assert by_theme["themeA"].source.judgment == "A_LATE"
        assert by_theme["themeA"].basis_state == "ok"       # later record won
    print("  OK  case 4 — two themes → two views, theme A reflects its later record")


def test_case5_unknown_basis_other_bucket():
    """5. A signal_basis string not in the normalization table → normalize_basis
    returns 'other:<value>' (no raise), and the view's likely_bug is True via the
    startswith('other:') branch."""
    assert normalize_basis("some_future_value") == "other:some_future_value"
    rec = _ao("ThemeIntelligenceAgent",
              {"signal_basis": "some_future_value", "short_confidence": 0.5})
    v = build_view_theme_intelligence([rec])[0]
    assert v.basis_state == "other:some_future_value"
    assert v.likely_bug is True
    print("  OK  case 5 — unknown basis → other:<value>, likely_bug via other:*")


def test_case6_empty_supporting_data():
    """6. An empty supporting_data dict on an otherwise well-formed record → every
    build_view_* degrades gracefully to 'other:missing' rather than raising."""
    for agent_id, builder in _ALL_BUILDERS:
        rec = _ao(agent_id, {})
        views = builder([rec])                              # must not raise
        assert len(views) >= 1, agent_id
        v = views[0]
        assert v.has_output is True, agent_id
        assert v.basis_state == "other:missing", (agent_id, v.basis_state)
    print("  OK  case 6 — empty supporting_data degrades to other:missing everywhere")


def test_case7_zero_records_placeholder():
    """7. Zero records for an agent → exactly ONE has_output=False view (not an
    empty list); for CandidateScreeningAgent the placeholder theme_key is None."""
    for agent_id, builder in _ALL_BUILDERS:
        views = builder([])
        assert len(views) == 1, (agent_id, len(views))
        assert views[0].has_output is False, agent_id
        assert views[0].basis_state == "missing", agent_id
        assert views[0].likely_bug is True, agent_id
    csv_placeholder = build_view_candidate_screening([])[0]
    assert csv_placeholder.theme_key is None
    print("  OK  case 7 — zero records → single placeholder (candidate theme_key None)")


def test_case8_defensive_flag_plus_degraded_basis():
    """8. Two flags, BOTH on the KNOWN_DEFENSIVE allow-list, combined with
    signal_basis_short=degraded_insufficient → likely_bug True, driven by the
    basis_state=='degraded' branch (NOT the flags branch). Confirms the two
    triggers are independent, not accidentally coupled."""
    rec = _ao("CandidateScreeningAgent", {
        "theme_key": "ai_chips",
        "signal_basis_short": "degraded_insufficient",     # → degraded
        "signal_basis_mid": "signal_present",              # → ok
        "short_confidence": 0.1, "mid_confidence": 0.9,
        "unavailable_dimensions": ["short_crowding", "options_structure"],
    })
    v = build_view_candidate_screening([rec])[0]
    assert set(v.degrade_flags) == {
        "unavailable:short_crowding", "unavailable:options_structure"}
    # The flags branch ALONE would NOT trip likely_bug (both are defensive)...
    assert all(f in KNOWN_DEFENSIVE_FLAGS for f in v.degrade_flags)
    # ...so likely_bug must come from the independent basis=="degraded" branch.
    assert v.basis_state == "degraded"                     # worst of {degraded, ok}
    assert v.likely_bug is True
    print("  OK  case 8 — degraded basis trips likely_bug independently of defensive flags")


# ===========================================================================
# Supporting tests (kept from the prior suite; none conflict with the 8 cases)
# ===========================================================================

def test_normalize_basis():
    assert normalize_basis("signal_present") == "ok"
    assert normalize_basis("degraded_insufficient") == "degraded"
    assert normalize_basis("no_clear_winner") == "no_winner"
    assert normalize_basis("no_role_signal") == "no_signal"
    assert normalize_basis("full_data_no_signal") == "no_signal"       # market-struct normal day
    assert normalize_basis("no_clear_leadership") == "no_leadership"   # sector 3rd value
    assert normalize_basis(None) == "other:missing"
    assert normalize_basis("Totally Weird!!") == "other:totally_weird"
    assert normalize_basis(1234) == "other:1234"
    assert normalize_basis("") == "other:unknown"
    print("  OK  normalize_basis (incl. no_clear_leadership + other:* fallback)")


def test_severity_precedence():
    assert _severity_rank("degraded") > _severity_rank("other:x")
    assert _severity_rank("other:x") > _severity_rank("no_winner")
    assert _severity_rank("no_leadership") > _severity_rank("ok")
    assert _worst_basis(["ok", "degraded"]) == "degraded"
    assert _worst_basis(["ok", "no_winner"]) == "no_winner"
    assert _worst_basis(["ok", "ok"]) == "ok"
    print("  OK  severity precedence")


def test_integration_real_shapes():
    """Seed all six agents with realistic supporting_data via the load path and
    assert the money-flow degraded shape produces both named flags + likely_bug
    (the exact real 2026-07-01 production shape)."""
    with tempfile.TemporaryDirectory() as base:
        _write(base, "MacroRegimeAgent",
               [_record("MacroRegimeAgent", {"regime": "risk_on", "data_coverage": 1.0})])
        _write(base, "MoneyFlowAgent", [_record("MoneyFlowAgent", {
            "degraded": True, "signals_agree_count": 0,
            "dark_pool_direction": "insufficient_data"}, source="rule_based")])
        _write(base, "MarketStructureAgent", [_record("MarketStructureAgent", {
            "signal_basis": "signal_present", "short_confidence": 0.4,
            "runner_error": ""})])
        _write(base, "SectorRotationAgent", [_record("SectorRotationAgent", {
            "signal_basis": "no_clear_leadership", "short_confidence": 0.5})])
        _write(base, "ThemeIntelligenceAgent", [_record("ThemeIntelligenceAgent", {
            "signal_basis": "signal_present", "short_confidence": 0.97})])
        _write(base, "CandidateScreeningAgent", [_record("CandidateScreeningAgent", {
            "theme_key": "ai_chips", "signal_basis_short": "signal_present",
            "signal_basis_mid": "signal_present", "short_confidence": 1.0,
            "mid_confidence": 1.0,
            "unavailable_dimensions": ["short_crowding", "options_structure"],
            "short_slate": {"no_trade_reason": None}, "mid_slate": {"no_trade_reason": None},
            "runner_error": "RuntimeError: stubbed LLM boundary failure"})])

        views = load_and_build_all_views(date=_DATE, base_dir=base)
        assert set(views) == {a for a, _ in _ALL_BUILDERS}

        mf = views["MoneyFlowAgent"][0]
        assert mf.basis_state == "degraded"
        assert set(mf.degrade_flags) == {"gex_dex_degraded", "dark_pool_insufficient"}
        assert mf.coverage == 0.0
        assert mf.likely_bug is True

        sr = views["SectorRotationAgent"][0]
        assert sr.basis_state == "no_leadership"

        ms = views["MarketStructureAgent"][0]
        assert "runner_error" not in ms.detail            # empty-string dropped

        cs = views["CandidateScreeningAgent"][0]
        assert cs.detail.get("runner_error", "").startswith("RuntimeError")  # truthy kept
        assert isinstance(cs.coverage, dict)
    print("  OK  integration — real supporting_data shapes across all six agents")


def test_missing_agents_placeholders():
    with tempfile.TemporaryDirectory() as base:
        views = load_and_build_all_views(date="2099-01-01", base_dir=base)
        for agent_id, vs in views.items():
            assert len(vs) == 1
            assert vs[0].has_output is False
            assert vs[0].source is None
    print("  OK  missing agents → placeholders (has_output=False, source None)")


def test_malformed_line_and_partial_record():
    with tempfile.TemporaryDirectory() as base:
        d = os.path.join(base, "MacroRegimeAgent")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{_DATE}.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("{ this is not valid json\n")                 # skipped by loader
            fh.write(json.dumps(_record("MacroRegimeAgent", {})) + "\n")
        views = load_and_build_all_views(date=_DATE, base_dir=base)
        v = views["MacroRegimeAgent"][0]
        assert v.has_output is True
        assert v.basis_state == "other:missing"
    print("  OK  malformed line skipped + partial record degrades safely")


def test_list_available_dates():
    with tempfile.TemporaryDirectory() as base:
        _write(base, "MacroRegimeAgent", [_record("MacroRegimeAgent", {})], date="2026-06-30")
        _write(base, "MoneyFlowAgent", [_record("MoneyFlowAgent", {})], date="2026-07-01")
        dates = list_available_dates(base_dir=base)
        assert dates == ["2026-06-30", "2026-07-01"]           # sorted union
        assert list_available_dates(base_dir=os.path.join(base, "nope")) == []
    print("  OK  list_available_dates (sorted union, safe on missing dir)")


def test_full_data_no_signal_neutral():
    """FIX 1 — MarketStructureAgent's normal 'data present, no warning' state
    (full_data_no_signal) maps to the neutral 'no_signal' bucket and must NOT
    false-trip likely_bug on an ordinary no-alert day."""
    assert normalize_basis("full_data_no_signal") == "no_signal"
    rec = _ao("MarketStructureAgent",
              {"signal_basis": "full_data_no_signal", "short_confidence": 0.8})
    v = build_view_market_structure([rec])[0]
    assert v.basis_state == "no_signal"
    assert v.likely_bug is False
    print("  OK  fix1 — full_data_no_signal → no_signal (normal day, not likely_bug)")


def test_marketstructure_ignores_nonpersisted_flags():
    """FIX 2 — vintage_mismatch / adjacency_degraded are NOT persisted into
    MarketStructureAgent.supporting_data, so the reader must not surface them
    even if a record happened to carry them. degrade_flags stays empty."""
    rec = _ao("MarketStructureAgent", {
        "signal_basis": "signal_present", "short_confidence": 0.5,
        "vintage_mismatch": True, "adjacency_degraded": True})
    v = build_view_market_structure([rec])[0]
    assert v.degrade_flags == []
    print("  OK  fix2 — market structure ignores non-persisted vintage/adjacency flags")


def test_lazy_import_no_reliability():
    """FIX 4 — importing lib.degradation_view in a fresh subprocess must NOT
    eagerly load lib.reliability (protects the load-bearing lazy-import
    invariant now that this module is a new agent-framework consumer)."""
    script = (
        "import sys\n"
        "import lib.degradation_view\n"
        "bad = [k for k in sys.modules if k == 'lib.reliability']\n"
        "assert not bad, f'lib.reliability eagerly loaded: {bad}'\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"import guard failed:\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}")
    assert "OK" in proc.stdout
    print("  OK  fix4 — importing lib.degradation_view does not load lib.reliability")


def test_latest_wins_all_builders():
    """FIX 5a — latest-wins for ALL SIX builders: a builder silently switching to
    records[0] must go red. The later same-day record's source is what the view
    reflects."""
    sds = {
        "MacroRegimeAgent": {"regime": "risk_on"},
        "MoneyFlowAgent": {"degraded": False},
        "MarketStructureAgent": {"signal_basis": "signal_present"},
        "SectorRotationAgent": {"signal_basis": "signal_present"},
        "ThemeIntelligenceAgent": {"signal_basis": "signal_present"},
        "CandidateScreeningAgent": {"theme_key": "t1",
                                    "signal_basis_short": "signal_present",
                                    "signal_basis_mid": "signal_present"},
    }
    for agent_id, builder in _ALL_BUILDERS:
        sd = sds[agent_id]
        earlier = _ao(agent_id, sd, ts=f"{_DATE}T09:00:00Z", judgment="EARLIER")
        later = _ao(agent_id, sd, ts=f"{_DATE}T15:00:00Z", judgment="LATER")
        v = builder([earlier, later])[0]     # load returns ascending; last wins
        assert v.source is not None, agent_id
        assert v.source.judgment == "LATER", (agent_id, v.source.judgment)
    print("  OK  fix5a — latest-wins across all six builders (records[-1], not [0])")


def test_candidate_none_or_empty_theme_key():
    """FIX 5b — CandidateScreening grouping tolerates a real record whose
    theme_key is None or an empty string: it groups under that key without
    raising, and the two are distinct group keys."""
    rec_none = _ao("CandidateScreeningAgent", {
        "signal_basis_short": "signal_present", "signal_basis_mid": "signal_present"})
    v_none = build_view_candidate_screening([rec_none])          # must not raise
    assert len(v_none) == 1
    assert v_none[0].has_output is True
    assert v_none[0].theme_key is None

    rec_empty = _ao("CandidateScreeningAgent", {
        "theme_key": "", "signal_basis_short": "signal_present",
        "signal_basis_mid": "signal_present"})
    v_empty = build_view_candidate_screening([rec_empty])
    assert len(v_empty) == 1
    assert v_empty[0].theme_key == ""

    both = build_view_candidate_screening([rec_none, rec_empty])
    assert len(both) == 2, [v.theme_key for v in both]          # None vs "" distinct
    print("  OK  fix5b — candidate grouping tolerates None / empty-string theme_key")


# ===========================================================================
# Runner
# ===========================================================================

_CASE_MAP = [
    ("case 1 — MarketStructure degraded, no vintage_mismatch key",
     "test_case1_marketstructure_degraded_no_vintage_key"),
    ("case 2 — rule_based on a textbook-normal read",
     "test_case2_rule_based_textbook_normal"),
    ("case 3 — later same-day timestamp wins",
     "test_case3_same_agent_later_timestamp_wins"),
    ("case 4 — candidate two themes, theme A later wins",
     "test_case4_candidate_two_themes_later_wins"),
    ("case 5 — unknown basis → other:<value>",
     "test_case5_unknown_basis_other_bucket"),
    ("case 6 — empty supporting_data degrades",
     "test_case6_empty_supporting_data"),
    ("case 7 — zero records → single placeholder",
     "test_case7_zero_records_placeholder"),
    ("case 8 — defensive flags + degraded basis independence",
     "test_case8_defensive_flag_plus_degraded_basis"),
]

_TESTS = [
    test_case1_marketstructure_degraded_no_vintage_key,
    test_case2_rule_based_textbook_normal,
    test_case3_same_agent_later_timestamp_wins,
    test_case4_candidate_two_themes_later_wins,
    test_case5_unknown_basis_other_bucket,
    test_case6_empty_supporting_data,
    test_case7_zero_records_placeholder,
    test_case8_defensive_flag_plus_degraded_basis,
    test_normalize_basis,
    test_severity_precedence,
    test_full_data_no_signal_neutral,
    test_marketstructure_ignores_nonpersisted_flags,
    test_lazy_import_no_reliability,
    test_latest_wins_all_builders,
    test_candidate_none_or_empty_theme_key,
    test_integration_real_shapes,
    test_missing_agents_placeholders,
    test_malformed_line_and_partial_record,
    test_list_available_dates,
]


def main() -> int:
    for fn in _TESTS:
        fn()
    print(f"\nALL {len(_TESTS)} DEGRADATION-VIEW TESTS PASSED")
    print("\nRequired-case → test-function mapping:")
    for label, fn_name in _CASE_MAP:
        print(f"  {label}: {fn_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
