#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5k_opportunity_queue.py

Phase 5K — Horizon-aware Opportunity Queue ViewModel — test suite.

Phase 5K converts Phase 5J Theme Intelligence / Market Heat records into
deterministic, horizon-aware opportunity-queue view models (short / mid / long
horizon queues plus cross-cutting watch-wait / research-more / no-trade-avoid
queues). It is a view-model contract layer only: it does not decide final
trades, does not produce order instructions, and does not bypass the future
research / debate / decision-packet phases.

This test verifies:
  - The default opportunity queue builds from the Phase 5J default theme
    snapshot (deterministically).
  - Short / mid / long queues exist and are deterministic.
  - The same ticker can appear in multiple horizons with different labels.
  - High theme heat does NOT automatically produce trade_now.
  - High crowding downgrades to wait_for_pullback / too_extended /
    avoid_too_crowded.
  - Momentum candidates may enter the short-term queue.
  - Mid / long-term labels require stronger evidence beyond momentum.
  - Partial evidence produces research_more / insufficient_evidence /
    watch_wait.
  - The empty theme snapshot returns safe empty queues.
  - The degraded theme fixture produces warnings.
  - Candidate source refs / theme IDs / subtheme IDs / chain node IDs are
    preserved.
  - No approved_for_execution=True is positively authorized.
  - No buy/sell/order-ticket fields are introduced.
  - No forbidden imports (app.py / pages/* / Streamlit / lib/workflow_state.py /
    lib/llm_orchestrator.py / external APIs / broker / order modules).
  - Serialization is deterministic.

It does NOT spin up Streamlit and does NOT call any external API or LLM.

Usage:
    python3 scripts/test_reliability_phase_5k_opportunity_queue.py
"""

from __future__ import annotations

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


PASS = 0
FAIL = 0
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


def _raises(fn) -> bool:
    """True if calling ``fn`` raises any exception."""
    try:
        fn()
        return False
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from lib.reliability.phase5_opportunity_queue import (  # noqa: E402
    CROSS_CUTTING_DECISION_LABELS,
    CrossHorizonCandidateComparison,
    CrossHorizonEntry,
    CrowdingRiskBadge,
    EntryQualityScore,
    EvidenceCoverageBadge,
    HorizonAwareOpportunityQueueView,
    HorizonCandidateView,
    HorizonFitScore,
    LONG_TERM_DECISION_LABELS,
    LongTermInvestmentQueue,
    MID_TERM_DECISION_LABELS,
    MidTermPositionQueue,
    NoTradeAvoidQueue,
    OPPORTUNITY_HORIZONS,
    OpportunityCandidateView,
    OpportunityNextAction,
    OpportunityQueueValidationSummary,
    OpportunityQueueView,
    OpportunityQueueWarning,
    OpportunitySourceSummary,
    QUEUE_KINDS,
    ResearchMoreQueue,
    SHORT_TERM_DECISION_LABELS,
    ShortTermTradeQueue,
    ThemeHeatBadge,
    WatchWaitQueue,
    build_default_opportunity_queue_view,
    build_degraded_opportunity_queue_view,
    build_empty_opportunity_queue_view,
    build_horizon_aware_opportunity_queue,
    build_horizon_candidate_views,
    build_long_term_candidate_view,
    build_mid_term_candidate_view,
    build_opportunity_candidate_from_theme_candidate,
    build_opportunity_queue_from_default_theme_snapshot,
    build_short_term_candidate_view,
    make_opportunity_queue_id,
)
from lib.reliability.phase5_theme_intelligence import (  # noqa: E402
    FundamentalConfirmationSignal,
    ThemeCandidateTicker,
    ThemeEvidenceSummary,
    ThemeHeatScore,
    ThemeHeatSignal,
    ThemeIntelligenceSnapshot,
    ThemeRecord,
    ThemeUniverseSnapshot,
    build_default_theme_intelligence_snapshot,
    build_theme_heat_score,
)

# Re-import via package to confirm exports are wired.
import lib.reliability as reliability_pkg  # noqa: E402

MODULE_PATH = os.path.join(
    _REPO_ROOT, "lib", "reliability", "phase5_opportunity_queue.py"
)
DOC_PATH = os.path.join(
    _REPO_ROOT,
    "docs",
    "reliability_phase_5k_horizon_aware_opportunity_queue.md",
)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# Helper builders for synthetic edge-case candidates / themes.
def _hot_theme(candidate, *, lifecycle="accelerating", confirm="confirming",
               strength="strong", price="strong") -> ThemeRecord:
    fund = (
        [FundamentalConfirmationSignal(confirmation_type="revenue",
                                       confirmation_direction=confirm,
                                       strength=strength)]
        if confirm != "none"
        else []
    )
    return ThemeRecord(
        theme_id="theme_syn",
        name="Synthetic",
        lifecycle_stage=lifecycle,
        heat_score=build_theme_heat_score(
            price_momentum_component=0.9, volume_component=0.85,
            breadth_component=0.7, narrative_component=0.9,
            fundamental_confirmation_component=0.8, freshness_component=0.85,
        ),
        source_signals=[ThemeHeatSignal(signal_type="price_momentum",
                                        source_type="scanner", strength=price)],
        fundamental_confirmation_signals=fund,
        candidate_tickers=[candidate],
    )


def _cand(ticker, *, role="leader", crowding="moderate", coverage="complete",
          hc=0.9, refs=("e1",)) -> ThemeCandidateTicker:
    return ThemeCandidateTicker(
        ticker=ticker, theme_id="theme_syn", role=role, heat_contribution=hc,
        crowding_level=crowding,
        evidence=ThemeEvidenceSummary(coverage_status=coverage,
                                      evidence_refs=list(refs)),
    )


# ---------------------------------------------------------------------------
# Section 1 — Default queue builds deterministically
# ---------------------------------------------------------------------------

q = build_default_opportunity_queue_view()
check("1.1 default queue is HorizonAwareOpportunityQueueView",
      isinstance(q, HorizonAwareOpportunityQueueView))
check("1.2 default queue has a queue_id", bool(q.queue_id))
check("1.3 default queue references source theme snapshot id",
      bool(q.source_theme_snapshot_id))
check("1.4 default queue has a validation summary",
      isinstance(q.validation_summary, OpportunityQueueValidationSummary))
check("1.5 default queue not safe-empty",
      q.validation_summary is not None and not q.validation_summary.is_safe_empty)
check("1.6 default queue is a fixture", q.is_fixture is True)
check("1.7 build_opportunity_queue_from_default_theme_snapshot is the alias",
      isinstance(build_opportunity_queue_from_default_theme_snapshot(),
                 HorizonAwareOpportunityQueueView))
check("1.8 make_opportunity_queue_id deterministic",
      make_opportunity_queue_id("default") == make_opportunity_queue_id("default"))
check("1.9 schema_version set", q.schema_version == "phase5_opportunity_queue_v1")

# Deterministic across builds.
d1 = build_default_opportunity_queue_view().model_dump(mode="json")
d2 = build_default_opportunity_queue_view().model_dump(mode="json")
check("1.10 two default builds dump-equal", d1 == d2)


# ---------------------------------------------------------------------------
# Section 2 — Six queues exist; horizons are exactly three
# ---------------------------------------------------------------------------

check("2.1 short queue type", isinstance(q.short_term, ShortTermTradeQueue))
check("2.2 mid queue type", isinstance(q.mid_term, MidTermPositionQueue))
check("2.3 long queue type", isinstance(q.long_term, LongTermInvestmentQueue))
check("2.4 watch_wait queue type", isinstance(q.watch_wait, WatchWaitQueue))
check("2.5 research_more queue type", isinstance(q.research_more, ResearchMoreQueue))
check("2.6 no_trade_avoid queue type", isinstance(q.no_trade_avoid, NoTradeAvoidQueue))
check("2.7 exactly three horizons", OPPORTUNITY_HORIZONS ==
      ("short_term", "mid_term", "long_term"))
check("2.8 exactly six queue kinds", len(QUEUE_KINDS) == 6)
check("2.9 short queue kind", q.short_term.queue_kind == "short_term_trade")
check("2.10 short queue horizon", q.short_term.horizon == "short_term")
check("2.11 queue counts match candidate lists",
      q.short_term.count == len(q.short_term.candidates)
      and q.mid_term.count == len(q.mid_term.candidates)
      and q.long_term.count == len(q.long_term.candidates))
check("2.12 short queue is populated (momentum candidates land here)",
      q.short_term.count >= 1)


# ---------------------------------------------------------------------------
# Section 3 — Same ticker appears in multiple horizons with different labels
# ---------------------------------------------------------------------------

comparisons = {c.ticker: c for c in q.cross_horizon_comparisons}
check("3.1 NVDA has a cross-horizon comparison", "NVDA" in comparisons)
nvda = comparisons.get("NVDA")
check("3.2 NVDA evaluated across all three horizons",
      nvda is not None and set(nvda.decisions_by_horizon.keys()) ==
      {"short_term", "mid_term", "long_term"})
check("3.3 NVDA has divergent decisions across horizons",
      nvda is not None and nvda.has_divergent_decisions)
check("3.4 NVDA short != mid != long (distinct decisions)",
      nvda is not None and
      len(set(nvda.decisions_by_horizon.values())) >= 2)
check("3.5 validation summary counts multi-horizon tickers",
      q.validation_summary is not None
      and q.validation_summary.multi_horizon_ticker_count >= 1)


# ---------------------------------------------------------------------------
# Section 4 — High theme heat does not automatically produce trade_now
# ---------------------------------------------------------------------------

# NVDA is the hottest, most-crowded leader; it must NOT be trade_now short-term.
check("4.1 NVDA (hot + crowded leader) short decision is not trade_now",
      nvda is not None and nvda.decisions_by_horizon["short_term"] != "trade_now",
      detail=str(nvda.decisions_by_horizon if nvda else None))
# Any trade_now that exists must have passed the entry-quality + crowding gate.
for v in q.short_term.candidates:
    if v.decision_label == "trade_now":
        check(f"4.2 trade_now {v.ticker} has good+ entry quality",
              v.entry_quality_score.band in ("good", "strong"),
              detail=v.entry_quality_score.band)
        check(f"4.3 trade_now {v.ticker} crowding not elevated",
              not v.crowding_risk.is_elevated)
check("4.4 validation summary asserts no unsafe trade_now",
      q.validation_summary is not None and q.validation_summary.no_unsafe_trade_now)


# ---------------------------------------------------------------------------
# Section 5 — High crowding downgrades (wait_for_pullback / too_extended /
#             avoid_too_crowded)
# ---------------------------------------------------------------------------

# elevated crowding -> wait_for_pullback (NVDA in default).
check("5.1 NVDA short is wait_for_pullback (elevated crowding downgrade)",
      nvda is not None and nvda.decisions_by_horizon["short_term"] == "wait_for_pullback")

# high crowding + red-hot heat -> too_extended.
c_high = _cand("HI", crowding="high")
v_high = build_short_term_candidate_view(c_high, _hot_theme(c_high))
check("5.2 high crowding + red_hot -> too_extended",
      v_high.decision_label == "too_extended", detail=v_high.decision_label)

# extreme crowding -> avoid_too_crowded (all horizons).
c_ext = _cand("EX", crowding="extreme")
v_ext_s = build_short_term_candidate_view(c_ext, _hot_theme(c_ext))
v_ext_m = build_mid_term_candidate_view(c_ext, _hot_theme(c_ext))
v_ext_l = build_long_term_candidate_view(c_ext, _hot_theme(c_ext))
check("5.3 extreme crowding short -> avoid_too_crowded",
      v_ext_s.decision_label == "avoid_too_crowded")
check("5.4 extreme crowding mid -> avoid_too_crowded",
      v_ext_m.decision_label == "avoid_too_crowded")
check("5.5 extreme crowding long -> avoid_too_crowded",
      v_ext_l.decision_label == "avoid_too_crowded")
# avoid_too_crowded routes to no_trade_avoid queue.
ext_snap = ThemeIntelligenceSnapshot(
    snapshot_id="themeintel_ext", universe=ThemeUniverseSnapshot(
        themes=[_hot_theme(c_ext)]))
ext_q = build_horizon_aware_opportunity_queue(ext_snap, label="ext")
check("5.6 avoid_too_crowded routes to no_trade_avoid queue",
      ext_q.no_trade_avoid.count >= 1
      and all(v.decision_label == "avoid_too_crowded"
              for v in ext_q.no_trade_avoid.candidates))


# ---------------------------------------------------------------------------
# Section 6 — Momentum candidates may enter the short-term queue
# ---------------------------------------------------------------------------

short_tickers = {v.ticker for v in q.short_term.candidates}
check("6.1 momentum candidates present in short queue", len(short_tickers) >= 2)
check("6.2 short queue decisions are short-horizon-native labels",
      all(v.decision_label in SHORT_TERM_DECISION_LABELS
          for v in q.short_term.candidates),
      detail=str(sorted({v.decision_label for v in q.short_term.candidates})))
check("6.3 every short-queue candidate has horizon == short_term",
      all(v.horizon == "short_term" for v in q.short_term.candidates))


# ---------------------------------------------------------------------------
# Section 7 — Mid / long-term labels require stronger evidence beyond momentum
# ---------------------------------------------------------------------------

# MU / VRT are momentum names with only PARTIAL candidate evidence: they may
# enter short-term but must NOT become mid/long position/investment candidates.
mu = comparisons.get("MU")
check("7.1 MU present in comparisons", mu is not None)
check("7.2 MU (partial evidence) mid is research_more, not position_candidate",
      mu is not None and mu.decisions_by_horizon["mid_term"] == "research_more")
check("7.3 MU (partial evidence) long is research_more, not investment_candidate",
      mu is not None and mu.decisions_by_horizon["long_term"] == "research_more")

# A momentum-strong candidate with no fundamental confirmation must NOT get a
# mid-term position_candidate label even though short-term momentum is strong.
c_noconf = _cand("NC", crowding="moderate", coverage="complete")
t_noconf = _hot_theme(c_noconf, confirm="none")
v_nc_short = build_short_term_candidate_view(c_noconf, t_noconf)
v_nc_mid = build_mid_term_candidate_view(c_noconf, t_noconf)
v_nc_long = build_long_term_candidate_view(c_noconf, t_noconf)
check("7.4 momentum-only short can be actionable-watch",
      v_nc_short.decision_label in SHORT_TERM_DECISION_LABELS)
check("7.5 momentum-only mid (no confirmation) is not position_candidate",
      v_nc_mid.decision_label != "position_candidate",
      detail=v_nc_mid.decision_label)
check("7.6 momentum-only long (no confirmation) is not investment_candidate",
      v_nc_long.decision_label != "investment_candidate",
      detail=v_nc_long.decision_label)
# Mid queue, when populated, only carries mid-native labels.
check("7.7 mid queue carries only mid-native labels",
      all(v.decision_label in MID_TERM_DECISION_LABELS
          for v in q.mid_term.candidates),
      detail=str(sorted({v.decision_label for v in q.mid_term.candidates})))
check("7.8 long queue carries only long-native labels",
      all(v.decision_label in LONG_TERM_DECISION_LABELS
          for v in q.long_term.candidates),
      detail=str(sorted({v.decision_label for v in q.long_term.candidates})))


# ---------------------------------------------------------------------------
# Section 8 — Partial / missing evidence -> research_more / insufficient_evidence
# ---------------------------------------------------------------------------

fixspec = comparisons.get("FIXSPEC")
check("8.1 FIXSPEC (no evidence speculative) short -> research_more",
      fixspec is not None and fixspec.decisions_by_horizon["short_term"] == "research_more")
check("8.2 FIXSPEC mid -> insufficient_evidence",
      fixspec is not None and
      fixspec.decisions_by_horizon["mid_term"] == "insufficient_evidence")
check("8.3 research_more queue is populated",
      q.research_more.count >= 1)
check("8.4 research_more queue carries cross-cutting labels",
      all(v.decision_label in CROSS_CUTTING_DECISION_LABELS
          or v.decision_label in ("thesis_unconfirmed", "thesis_insufficient")
          for v in q.research_more.candidates),
      detail=str(sorted({v.decision_label for v in q.research_more.candidates})))

# watch_wait: heat unknown, weak momentum, partial evidence.
c_ww = ThemeCandidateTicker(
    ticker="WW", theme_id="theme_w", role="laggard", heat_contribution=0.0,
    crowding_level="moderate",
    evidence=ThemeEvidenceSummary(coverage_status="partial"))
t_ww = ThemeRecord(theme_id="theme_w", name="W", lifecycle_stage="unknown",
                   heat_score=ThemeHeatScore(), source_signals=[],
                   fundamental_confirmation_signals=[], candidate_tickers=[c_ww])
v_ww = build_short_term_candidate_view(c_ww, t_ww)
check("8.5 weak/unknown candidate short -> watch_wait",
      v_ww.decision_label == "watch_wait", detail=v_ww.decision_label)
ww_q = build_horizon_aware_opportunity_queue(
    ThemeIntelligenceSnapshot(snapshot_id="themeintel_ww",
                              universe=ThemeUniverseSnapshot(themes=[t_ww])),
    label="ww")
check("8.6 watch_wait routes to watch_wait queue",
      any(v.decision_label == "watch_wait" for v in ww_q.watch_wait.candidates))


# ---------------------------------------------------------------------------
# Section 9 — Empty snapshot returns safe empty queues
# ---------------------------------------------------------------------------

empty = build_empty_opportunity_queue_view()
check("9.1 empty queue builds", isinstance(empty, HorizonAwareOpportunityQueueView))
check("9.2 empty queue safe-empty", empty.validation_summary is not None
      and empty.validation_summary.is_safe_empty)
check("9.3 empty queue all sections empty",
      empty.short_term.count == 0 and empty.mid_term.count == 0
      and empty.long_term.count == 0 and empty.watch_wait.count == 0
      and empty.research_more.count == 0 and empty.no_trade_avoid.count == 0)
check("9.4 empty queue has no candidates / comparisons",
      len(empty.candidates) == 0 and len(empty.cross_horizon_comparisons) == 0)
check("9.5 empty queue still carries safety warning(s)", len(empty.warnings) >= 1)


# ---------------------------------------------------------------------------
# Section 10 — Degraded theme fixture produces warnings (no fabricated trades)
# ---------------------------------------------------------------------------

deg = build_degraded_opportunity_queue_view()
check("10.1 degraded queue builds", isinstance(deg, HorizonAwareOpportunityQueueView))
check("10.2 degraded queue has no short/mid/long actionable trades",
      deg.short_term.count == 0 and deg.mid_term.count == 0
      and deg.long_term.count == 0)
check("10.3 degraded queue routes candidate(s) to research_more",
      deg.research_more.count >= 1)
deg_warned = any(v.warnings for v in deg.research_more.candidates)
check("10.4 degraded candidate carries warnings", deg_warned)
check("10.5 degraded candidate preserves a missing-evidence warning",
      any(w.warning_type == "missing_evidence"
          for v in deg.research_more.candidates for w in v.warnings))


# ---------------------------------------------------------------------------
# Section 11 — Source refs / theme / subtheme / chain node ids preserved
# ---------------------------------------------------------------------------

ai = build_default_theme_intelligence_snapshot().universe.themes[0]
ai_nvda = next(c for c in ai.candidate_tickers if c.ticker == "NVDA")
norm = build_opportunity_candidate_from_theme_candidate(ai_nvda, ai)
check("11.1 normalized candidate preserves theme_id",
      norm.theme_id == ai_nvda.theme_id)
check("11.2 normalized candidate preserves subtheme_ids",
      norm.subtheme_ids == ai_nvda.subtheme_ids and len(norm.subtheme_ids) >= 1)
check("11.3 normalized candidate preserves chain_node_ids",
      norm.chain_node_ids == ai_nvda.chain_node_ids and len(norm.chain_node_ids) >= 1)
check("11.4 normalized candidate preserves evidence refs",
      norm.evidence_refs == ai_nvda.evidence.evidence_refs)
check("11.5 normalized candidate preserves source refs",
      norm.source_refs == ai_nvda.evidence.source_refs)
check("11.6 normalized candidate preserves role + company name",
      norm.candidate_role == ai_nvda.role and norm.company_name == ai_nvda.company_name)

views = build_horizon_candidate_views(ai_nvda, ai)
check("11.7 build_horizon_candidate_views returns 3 horizon views",
      len(views) == 3 and {v.horizon for v in views} == set(OPPORTUNITY_HORIZONS))
check("11.8 horizon views preserve subtheme + chain node ids",
      all(v.subtheme_ids == ai_nvda.subtheme_ids
          and v.chain_node_ids == ai_nvda.chain_node_ids for v in views))
check("11.9 horizon views carry separate heat + entry-quality scores",
      all(isinstance(v.theme_heat, ThemeHeatBadge)
          and isinstance(v.entry_quality_score, EntryQualityScore) for v in views))
check("11.10 source signal summary carries theme provenance",
      all(isinstance(v.source_signal_summary, OpportunitySourceSummary)
          for v in views))


# ---------------------------------------------------------------------------
# Section 12 — Heat is separate from entry quality; not a buy signal
# ---------------------------------------------------------------------------

nvda_short = next(v for v in views if v.horizon == "short_term")
check("12.1 theme heat badge is_buy_signal is False",
      nvda_short.theme_heat.is_buy_signal is False)
check("12.2 entry quality is_heat_score is False (separate from heat)",
      nvda_short.entry_quality_score.is_heat_score is False)
check("12.3 ThemeHeatBadge rejects is_buy_signal=True",
      _raises(lambda: ThemeHeatBadge(is_buy_signal=True)))
check("12.4 EntryQualityScore rejects is_heat_score=True",
      _raises(lambda: EntryQualityScore(is_heat_score=True)))
check("12.5 NVDA heat band is hot/red_hot but decision is not trade_now",
      nvda_short.theme_heat.band in ("hot", "red_hot")
      and nvda_short.decision_label != "trade_now")


# ---------------------------------------------------------------------------
# Section 13 — No approved_for_execution / order-ticket / buy-sell fields
# ---------------------------------------------------------------------------

ALL_MODELS = [
    ThemeHeatBadge, EntryQualityScore, HorizonFitScore, CrowdingRiskBadge,
    EvidenceCoverageBadge, OpportunityNextAction, OpportunityQueueWarning,
    OpportunitySourceSummary, OpportunityCandidateView, HorizonCandidateView,
    OpportunityQueueView, ShortTermTradeQueue, MidTermPositionQueue,
    LongTermInvestmentQueue, WatchWaitQueue, ResearchMoreQueue,
    NoTradeAvoidQueue, CrossHorizonEntry, CrossHorizonCandidateComparison,
    OpportunityQueueValidationSummary, HorizonAwareOpportunityQueueView,
]
FORBIDDEN_FIELDS = {
    "approved_for_execution", "order_type", "order_id", "time_in_force",
    "broker_route", "broker_payload", "account_id", "execution_id",
    "quantity_to_execute", "limit_price", "stop_price", "fill_price",
    "buy", "sell", "buy_now", "sell_now",
}
for m in ALL_MODELS:
    bad = set(m.model_fields.keys()) & FORBIDDEN_FIELDS
    check(f"13.1 {m.__name__} declares no forbidden field", not bad, detail=str(bad))

check("13.2 queue rejects approved_for_execution kwarg (extra=forbid)",
      _raises(lambda: HorizonAwareOpportunityQueueView(
          queue_id="x", approved_for_execution=True)))

dump_str = json.dumps(d1).lower()
# The safety flag `approved_for_execution_absent` is allowed; a positive
# `approved_for_execution` key set true is not.
check("13.3 serialized default queue does not authorize approved_for_execution",
      '"approved_for_execution": true' not in dump_str
      and '"approved_for_execution":true' not in dump_str
      and '"approved_for_execution":' not in dump_str)
check("13.4 validation summary asserts execution-safety invariants",
      q.validation_summary is not None
      and q.validation_summary.no_executable_order_fields
      and q.validation_summary.approved_for_execution_absent
      and q.validation_summary.no_buy_signal_fields)
check("13.5 no candidate carries an actionable buy/sell order field",
      '"order_type"' not in dump_str and '"broker_route"' not in dump_str)


# ---------------------------------------------------------------------------
# Section 14 — Module source forbidden-import / determinism checks
# ---------------------------------------------------------------------------

module_src = _read_text(MODULE_PATH)
FORBIDDEN_IMPORT_SUBSTRINGS = [
    "import streamlit", "import anthropic", "import openai", "from app",
    "import app\n", "lib.workflow_state", "lib.llm_orchestrator",
    "lib.data_fetcher", "from pages", "import requests", "import httpx",
    "import urllib", "yfinance", "polygon", "finnhub",
]
for sub in FORBIDDEN_IMPORT_SUBSTRINGS:
    check(f"14.1 module does not reference {sub!r}", sub not in module_src, detail=sub)
check("14.2 module does not read research/.workflow_state.json",
      ".workflow_state.json" not in module_src)
check("14.3 module does not open files for persistence",
      "open(" not in module_src and "Path(" not in module_src)
check("14.4 module does not use wall-clock time / randomness",
      "datetime.now" not in module_src and "time.time(" not in module_src
      and "import random" not in module_src)


# ---------------------------------------------------------------------------
# Section 15 — Serialization deterministic + round-trip
# ---------------------------------------------------------------------------

j1 = json.dumps(d1, sort_keys=True)
j2 = json.dumps(build_default_opportunity_queue_view().model_dump(mode="json"),
                sort_keys=True)
check("15.1 JSON serialization deterministic across builds", j1 == j2)
rt = HorizonAwareOpportunityQueueView.model_validate(d1)
check("15.2 round-trip re-validates",
      isinstance(rt, HorizonAwareOpportunityQueueView))
check("15.3 round-trip dump-equal", rt.model_dump(mode="json") == d1)
# decisions_by_horizon ordering deterministic.
check("15.4 decisions_by_horizon ordered short->mid->long",
      nvda is not None
      and list(nvda.decisions_by_horizon.keys()) ==
      ["short_term", "mid_term", "long_term"])


# ---------------------------------------------------------------------------
# Section 16 — Package exports wired
# ---------------------------------------------------------------------------

EXPECTED_EXPORTS = [
    "HorizonAwareOpportunityQueueView",
    "OpportunityQueueView",
    "OpportunityCandidateView",
    "HorizonCandidateView",
    "HorizonFitScore",
    "EntryQualityScore",
    "ThemeHeatBadge",
    "CrowdingRiskBadge",
    "EvidenceCoverageBadge",
    "OpportunityNextAction",
    "OpportunityQueueWarning",
    "OpportunitySourceSummary",
    "CrossHorizonCandidateComparison",
    "OpportunityQueueValidationSummary",
    "ShortTermTradeQueue",
    "MidTermPositionQueue",
    "LongTermInvestmentQueue",
    "WatchWaitQueue",
    "ResearchMoreQueue",
    "NoTradeAvoidQueue",
    "OPPORTUNITY_HORIZONS",
    "QUEUE_KINDS",
    "build_horizon_aware_opportunity_queue",
    "build_opportunity_candidate_from_theme_candidate",
    "build_horizon_candidate_views",
    "build_short_term_candidate_view",
    "build_mid_term_candidate_view",
    "build_long_term_candidate_view",
    "build_cross_horizon_candidate_comparison",
    "build_opportunity_queue_validation_summary",
    "build_default_opportunity_queue_view",
    "build_opportunity_queue_from_default_theme_snapshot",
    "build_degraded_opportunity_queue_view",
]
for name in EXPECTED_EXPORTS:
    check(f"16.1 lib.reliability exports {name!r}", hasattr(reliability_pkg, name))
    check(f"16.2 {name!r} in lib.reliability.__all__", name in reliability_pkg.__all__)


# ---------------------------------------------------------------------------
# Section 17 — Documentation present with required sections
# ---------------------------------------------------------------------------

check("17.1 Phase 5K doc exists", os.path.isfile(DOC_PATH), detail=DOC_PATH)
doc = _read_text(DOC_PATH) if os.path.isfile(DOC_PATH) else ""
dlc = doc.lower()
REQUIRED_DOC_TOPICS = [
    "Purpose", "Phase 5I", "Phase 5J", "horizon-aware", "short_term",
    "mid_term", "long_term", "Watch", "Research More", "No Trade",
    "HorizonFitScore", "EntryQualityScore", "ThemeHeatScore",
    "CrowdingRiskBadge", "EvidenceCoverageBadge", "not a buy signal",
    "final trade", "Fixture", "degraded", "Non-goals", "Guardrails",
    "Acceptance criteria", "Phase 5L",
]
for topic in REQUIRED_DOC_TOPICS:
    check(f"17.2 Phase 5K doc covers {topic!r}", topic in doc or topic.lower() in dlc)
check("17.3 doc keeps approved_for_execution False/absent",
      "approved_for_execution" in doc and ("false" in dlc or "absent" in dlc))
check("17.4 doc keeps Phase 5L as a future dependency, not started",
      "phase 5l" in dlc and ("future" in dlc or "not started" in dlc or "next" in dlc))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("Phase 5K — Horizon-aware Opportunity Queue ViewModel — test results")
print("=" * 70)

if _failures:
    print()
    for line in _failures:
        print(line)

print()
print(f"Passed: {PASS}")
print(f"Failed: {FAIL}")
print(f"Total:  {PASS + FAIL}")
print()

if FAIL == 0:
    print("RESULT: PASS — Phase 5K horizon-aware opportunity queue verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
