"""
scripts/test_reliability_option_trade_memory.py

Phase 4M-E: Option Trade Plan Memory — comprehensive test suite.

Run: python3 scripts/test_reliability_option_trade_memory.py

All tests are offline/mock-only. No network, DB, vector store, file writes,
Claude API calls, Streamlit, Finnhub, brokerage, broker/order/execution,
live option-chain, or live portfolio dependencies.
"""

import sys
import os

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import types

# ---------------------------------------------------------------------------
# Section 0: guard forbidden imports
# ---------------------------------------------------------------------------

_forbidden_modules = [
    "streamlit",
    "anthropic",
    "requests",
    "httpx",
    "sqlalchemy",
    "psycopg2",
    "pymongo",
    "redis",
    "chromadb",
    "pinecone",
    "weaviate",
    "alpaca_trade_api",
    "ib_insync",
    "robin_stocks",
    "finnhub",
]

_test_count = 0
_fail_count = 0


def _ok(label: str) -> None:
    global _test_count
    _test_count += 1
    print(f"  PASS  {label}")


def _fail(label: str, reason: str) -> None:
    global _test_count, _fail_count
    _test_count += 1
    _fail_count += 1
    print(f"  FAIL  {label}: {reason}")


def _check(label: str, condition: bool, reason: str = "") -> None:
    if condition:
        _ok(label)
    else:
        _fail(label, reason or "condition was False")


def _section(title: str) -> None:
    print(f"\n--- {title} ---")


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from pydantic import ValidationError

from lib.reliability.option_trade_memory import (
    OptionTradeDecision,
    OptionTradeMemoryActorType,
    OptionTradeMemoryEventType,
    OptionTradeMemoryInputBundle,
    OptionTradeMemoryLogEntry,
    OptionTradeMemoryReport,
    OptionTradeMemorySourceRef,
    OptionTradeMemoryStatus,
    OptionTradeMemorySummary,
    OptionTradeOutcome,
    OptionTradeReviewStatus,
    OptionTradeRiskLevel,
    OptionTradeStrategyType,
    OptionTradePlanMemoryRecord,
    OptionTradePlanSnapshot,
    build_option_trade_memory_log_entry,
    build_option_trade_memory_record,
    build_option_trade_memory_report,
    build_option_trade_plan_snapshot,
    collect_option_trade_memory_artifact_refs,
    collect_option_trade_memory_evidence_ids,
    collect_option_trade_memory_source_ids,
    determine_option_trade_memory_status,
    make_option_trade_memory_log_entry_id,
    make_option_trade_memory_record_id,
    make_option_trade_memory_report_id,
    option_trade_memory_tool_result_from_report,
    summarize_option_trade_memory,
)


# ---------------------------------------------------------------------------
# Section 1: OptionTradeMemorySourceRef validation
# ---------------------------------------------------------------------------

_section("1: OptionTradeMemorySourceRef validation")

ref1 = OptionTradeMemorySourceRef(source_id="src_001")
_check("1.1 source_id set", ref1.source_id == "src_001")
_check("1.2 source_type defaults to unknown", ref1.source_type == "unknown")
_check("1.3 artifact_id defaults None", ref1.artifact_id is None)
_check("1.4 evidence_id defaults None", ref1.evidence_id is None)
_check("1.5 field_path defaults None", ref1.field_path is None)
_check("1.6 label defaults None", ref1.label is None)
_check("1.7 metadata defaults empty dict", ref1.metadata == {})
_check("1.8 warnings defaults empty list", ref1.warnings == [])

ref2 = OptionTradeMemorySourceRef(
    source_id="src_002",
    source_type="option_expression_report",
    artifact_id="art_001",
    evidence_id="eid_001",
    field_path="candidates[0].iv_30d",
    label="IV source",
    metadata={"phase": "3R-D"},
    warnings=["test warning"],
)
_check("1.9 full ref fields set", ref2.label == "IV source")
_check("1.10 metadata set", ref2.metadata["phase"] == "3R-D")

# Whitespace-only source_id rejected
try:
    OptionTradeMemorySourceRef(source_id="   ")
    _fail("1.11 whitespace source_id rejected", "should have raised")
except ValidationError:
    _ok("1.11 whitespace source_id rejected")

# extra fields forbidden
try:
    OptionTradeMemorySourceRef(source_id="x", unknown_field="y")
    _fail("1.12 extra fields forbidden", "should have raised")
except ValidationError:
    _ok("1.12 extra fields forbidden")


# ---------------------------------------------------------------------------
# Section 2: OptionTradePlanSnapshot validation
# ---------------------------------------------------------------------------

_section("2: OptionTradePlanSnapshot validation")

_snap_basic = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    expiration="2026-06-20",
    entry_iv=0.55,
    entry_underlying_price=900.0,
    max_loss=500.0,
    max_gain=2500.0,
    breakeven=950.0,
    cash_required=500.0,
    risk_reward_ratio=5.0,
    contracts=1,
    planned_exit_rule="Exit at 50% max gain or 50% max loss.",
    risk_level="high",
    as_of="2026-05-26",
)
_check("2.1 snapshot_id set", _snap_basic.snapshot_id.startswith("otsnap_"))
_check("2.2 target set", _snap_basic.target == "NVDA")
_check("2.3 decision set", _snap_basic.decision == "option")
_check("2.4 strategy_type set", _snap_basic.strategy_type == "long_call")
_check("2.5 expiration set", _snap_basic.expiration == "2026-06-20")
_check("2.6 entry_iv set", _snap_basic.entry_iv == 0.55)
_check("2.7 entry_underlying_price set", _snap_basic.entry_underlying_price == 900.0)
_check("2.8 max_loss set", _snap_basic.max_loss == 500.0)
_check("2.9 max_gain set", _snap_basic.max_gain == 2500.0)
_check("2.10 breakeven set", _snap_basic.breakeven == 950.0)
_check("2.11 cash_required set", _snap_basic.cash_required == 500.0)
_check("2.12 risk_reward_ratio set", _snap_basic.risk_reward_ratio == 5.0)
_check("2.13 contracts set", _snap_basic.contracts == 1)
_check("2.14 planned_exit_rule set", "50%" in _snap_basic.planned_exit_rule)
_check("2.15 risk_level set", _snap_basic.risk_level == "high")

# Negative IV rejected
try:
    OptionTradePlanSnapshot(
        snapshot_id="s1",
        target="NVDA",
        entry_iv=-0.1,
    )
    _fail("2.16 negative entry_iv rejected", "should have raised")
except ValidationError:
    _ok("2.16 negative entry_iv rejected")

# Negative max_loss rejected
try:
    OptionTradePlanSnapshot(
        snapshot_id="s1",
        target="NVDA",
        max_loss=-100.0,
    )
    _fail("2.17 negative max_loss rejected", "should have raised")
except ValidationError:
    _ok("2.17 negative max_loss rejected")

# Negative contracts rejected
try:
    OptionTradePlanSnapshot(
        snapshot_id="s1",
        target="NVDA",
        contracts=-1,
    )
    _fail("2.18 negative contracts rejected", "should have raised")
except ValidationError:
    _ok("2.18 negative contracts rejected")

# Zero contracts OK
snap_zero_contracts = OptionTradePlanSnapshot(
    snapshot_id="s2",
    target="NVDA",
    contracts=0,
)
_check("2.19 zero contracts accepted", snap_zero_contracts.contracts == 0)

# no_trade snapshot with no option metrics is valid
snap_no_trade = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="no_trade",
    strategy_type="no_trade",
    risk_level="low",
    as_of="2026-05-26",
)
_check("2.20 no_trade snapshot valid", snap_no_trade.strategy_type == "no_trade")
_check("2.21 no_trade snapshot entry_iv is None", snap_no_trade.entry_iv is None)
_check("2.22 no_trade snapshot max_loss is None", snap_no_trade.max_loss is None)

# extra fields forbidden
try:
    OptionTradePlanSnapshot(snapshot_id="s3", target="NVDA", broker_account="123")
    _fail("2.23 extra fields forbidden", "should have raised")
except ValidationError:
    _ok("2.23 extra fields forbidden")


# ---------------------------------------------------------------------------
# Section 3: OptionTradeMemoryLogEntry validation
# ---------------------------------------------------------------------------

_section("3: OptionTradeMemoryLogEntry validation")

entry1 = OptionTradeMemoryLogEntry(
    event_id="otlog_001",
    event_type="option_plan_recorded",
    created_at="2026-05-26T09:00:00Z",
    actor="system",
    description="Option trade plan recorded.",
)
_check("3.1 event_id set", entry1.event_id == "otlog_001")
_check("3.2 event_type set", entry1.event_type == "option_plan_recorded")
_check("3.3 created_at set", entry1.created_at == "2026-05-26T09:00:00Z")
_check("3.4 actor set", entry1.actor == "system")
_check("3.5 description set", "recorded" in entry1.description)
_check("3.6 source_ids defaults empty", entry1.source_ids == [])
_check("3.7 evidence_ids defaults empty", entry1.evidence_ids == [])
_check("3.8 metadata defaults empty dict", entry1.metadata == {})
_check("3.9 warnings defaults empty list", entry1.warnings == [])

# whitespace event_id rejected
try:
    OptionTradeMemoryLogEntry(
        event_id="  ",
        event_type="unknown",
        created_at="2026-01-01",
        description="x",
    )
    _fail("3.10 whitespace event_id rejected", "should have raised")
except ValidationError:
    _ok("3.10 whitespace event_id rejected")

# whitespace description rejected
try:
    OptionTradeMemoryLogEntry(
        event_id="e1",
        event_type="unknown",
        created_at="2026-01-01",
        description="   ",
    )
    _fail("3.11 whitespace description rejected", "should have raised")
except ValidationError:
    _ok("3.11 whitespace description rejected")


# ---------------------------------------------------------------------------
# Section 4: OptionTradePlanMemoryRecord validation
# ---------------------------------------------------------------------------

_section("4: OptionTradePlanMemoryRecord validation")

_snap_for_rec = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    entry_iv=0.50,
    max_loss=300.0,
    risk_level="medium",
    as_of="2026-05-26",
)

rec1 = OptionTradePlanMemoryRecord(
    option_trade_memory_id="otmem_001",
    target="NVDA",
    status="active",
    decision="option",
    review_status="not_required",
    outcome="pending",
    plan_snapshot=_snap_for_rec,
    rationale="Strong thesis, initiating long call position.",
    recorded_at="2026-05-26",
)
_check("4.1 option_trade_memory_id set", rec1.option_trade_memory_id == "otmem_001")
_check("4.2 target set", rec1.target == "NVDA")
_check("4.3 status set", rec1.status == "active")
_check("4.4 decision set", rec1.decision == "option")
_check("4.5 review_status set", rec1.review_status == "not_required")
_check("4.6 outcome set", rec1.outcome == "pending")
_check("4.7 rationale set", "long call" in rec1.rationale)
_check("4.8 run_id defaults None", rec1.run_id is None)
_check("4.9 memory_id defaults None", rec1.memory_id is None)
_check("4.10 thesis_id defaults None", rec1.thesis_id is None)
_check("4.11 allocation_memory_id defaults None", rec1.allocation_memory_id is None)
_check("4.12 option_expression_report_id defaults None", rec1.option_expression_report_id is None)
_check("4.13 trade_plan_report_id defaults None", rec1.trade_plan_report_id is None)
_check("4.14 decision_packet_id defaults None", rec1.decision_packet_id is None)
_check("4.15 review_trigger defaults None", rec1.review_trigger is None)
_check("4.16 actual_exit_date defaults None", rec1.actual_exit_date is None)
_check("4.17 pnl_amount defaults None", rec1.pnl_amount is None)
_check("4.18 pnl_pct defaults None", rec1.pnl_pct is None)
_check("4.19 lesson defaults None", rec1.lesson is None)
_check("4.20 reviewed_at defaults None", rec1.reviewed_at is None)
_check("4.21 source_refs defaults empty", rec1.source_refs == [])
_check("4.22 evidence_ids defaults empty", rec1.evidence_ids == [])
_check("4.23 artifact_refs defaults empty", rec1.artifact_refs == [])
_check("4.24 event_log defaults empty", rec1.event_log == [])
_check("4.25 warnings defaults empty", rec1.warnings == [])
_check("4.26 approved_for_execution always False", rec1.approved_for_execution is False)

# approved_for_execution=True rejected
try:
    OptionTradePlanMemoryRecord(
        option_trade_memory_id="otmem_001",
        target="NVDA",
        status="active",
        decision="option",
        review_status="not_required",
        outcome="pending",
        plan_snapshot=_snap_for_rec,
        rationale="x",
        recorded_at="2026-01-01",
        approved_for_execution=True,
    )
    _fail("4.27 approved_for_execution=True rejected", "should have raised")
except ValidationError:
    _ok("4.27 approved_for_execution=True rejected")

# pnl_amount may be signed (negative)
rec_neg_pnl = OptionTradePlanMemoryRecord(
    option_trade_memory_id="otmem_002",
    target="NVDA",
    status="closed",
    decision="option",
    review_status="reviewed",
    outcome="loss",
    plan_snapshot=_snap_for_rec,
    rationale="Loss trade.",
    recorded_at="2026-01-01",
    pnl_amount=-350.0,
    pnl_pct=-0.15,
)
_check("4.28 negative pnl_amount accepted", rec_neg_pnl.pnl_amount == -350.0)
_check("4.29 negative pnl_pct accepted", rec_neg_pnl.pnl_pct == -0.15)

# whitespace target rejected
try:
    OptionTradePlanMemoryRecord(
        option_trade_memory_id="otmem_003",
        target="   ",
        status="active",
        decision="option",
        review_status="not_required",
        outcome="pending",
        plan_snapshot=_snap_for_rec,
        rationale="x",
        recorded_at="2026-01-01",
    )
    _fail("4.30 whitespace target rejected", "should have raised")
except ValidationError:
    _ok("4.30 whitespace target rejected")

# whitespace rationale rejected
try:
    OptionTradePlanMemoryRecord(
        option_trade_memory_id="otmem_004",
        target="NVDA",
        status="active",
        decision="option",
        review_status="not_required",
        outcome="pending",
        plan_snapshot=_snap_for_rec,
        rationale="  ",
        recorded_at="2026-01-01",
    )
    _fail("4.31 whitespace rationale rejected", "should have raised")
except ValidationError:
    _ok("4.31 whitespace rationale rejected")


# ---------------------------------------------------------------------------
# Section 5: OptionTradeMemoryInputBundle validation
# ---------------------------------------------------------------------------

_section("5: OptionTradeMemoryInputBundle validation")

bundle1 = OptionTradeMemoryInputBundle(target="NVDA")
_check("5.1 target set", bundle1.target == "NVDA")
_check("5.2 run_id defaults None", bundle1.run_id is None)
_check("5.3 memory_id defaults None", bundle1.memory_id is None)
_check("5.4 thesis_id defaults None", bundle1.thesis_id is None)
_check("5.5 allocation_memory_id defaults None", bundle1.allocation_memory_id is None)
_check("5.6 as_of defaults None", bundle1.as_of is None)
_check("5.7 research_run_memory_record defaults None", bundle1.research_run_memory_record is None)
_check("5.8 thesis_memory_report defaults None", bundle1.thesis_memory_report is None)
_check("5.9 allocation_memory_report defaults None", bundle1.allocation_memory_report is None)
_check("5.10 option_expression_report defaults None", bundle1.option_expression_report is None)
_check("5.11 trade_plan_report defaults None", bundle1.trade_plan_report is None)
_check("5.12 decision_packet defaults None", bundle1.decision_packet is None)
_check("5.13 human_review_report defaults None", bundle1.human_review_report is None)
_check("5.14 source_ids defaults empty", bundle1.source_ids == [])
_check("5.15 evidence_ids defaults empty", bundle1.evidence_ids == [])
_check("5.16 artifact_refs defaults empty", bundle1.artifact_refs == [])
_check("5.17 warnings defaults empty", bundle1.warnings == [])

# whitespace-only target rejected
try:
    OptionTradeMemoryInputBundle(target="   ")
    _fail("5.18 whitespace target rejected", "should have raised")
except ValidationError:
    _ok("5.18 whitespace target rejected")


# ---------------------------------------------------------------------------
# Section 6: OptionTradeMemorySummary validation
# ---------------------------------------------------------------------------

_section("6: OptionTradeMemorySummary validation")

summ1 = OptionTradeMemorySummary(target="NVDA", status="active")
_check("6.1 target set", summ1.target == "NVDA")
_check("6.2 status set", summ1.status == "active")
_check("6.3 record_count defaults 0", summ1.record_count == 0)
_check("6.4 decision_counts defaults empty dict", summ1.decision_counts == {})
_check("6.5 strategy_counts defaults empty dict", summ1.strategy_counts == {})
_check("6.6 reviewed_count defaults 0", summ1.reviewed_count == 0)
_check("6.7 needs_review_count defaults 0", summ1.needs_review_count == 0)
_check("6.8 blocked_count defaults 0", summ1.blocked_count == 0)
_check("6.9 closed_count defaults 0", summ1.closed_count == 0)
_check("6.10 no_trade_count defaults 0", summ1.no_trade_count == 0)
_check("6.11 high_risk_count defaults 0", summ1.high_risk_count == 0)
_check("6.12 pending_outcome_count defaults 0", summ1.pending_outcome_count == 0)
_check("6.13 profit_count defaults 0", summ1.profit_count == 0)
_check("6.14 loss_count defaults 0", summ1.loss_count == 0)
_check("6.15 total_pnl_amount defaults None", summ1.total_pnl_amount is None)
_check("6.16 avg_pnl_pct defaults None", summ1.avg_pnl_pct is None)
_check("6.17 max_loss_planned defaults None", summ1.max_loss_planned is None)
_check("6.18 top_warnings defaults empty list", summ1.top_warnings == [])
_check("6.19 approved_for_execution always False", summ1.approved_for_execution is False)

# approved_for_execution=True rejected
try:
    OptionTradeMemorySummary(target="NVDA", status="active", approved_for_execution=True)
    _fail("6.20 approved_for_execution=True rejected in summary", "should have raised")
except ValidationError:
    _ok("6.20 approved_for_execution=True rejected in summary")


# ---------------------------------------------------------------------------
# Section 7: OptionTradeMemoryReport validation
# ---------------------------------------------------------------------------

_section("7: OptionTradeMemoryReport validation")

_summ_for_report = OptionTradeMemorySummary(target="NVDA", status="unknown")
rep1 = OptionTradeMemoryReport(
    report_id="otmrep_001",
    target="NVDA",
    status="unknown",
    summary=_summ_for_report,
    created_at="2026-05-26",
    updated_at="2026-05-26",
)
_check("7.1 report_id set", rep1.report_id == "otmrep_001")
_check("7.2 target set", rep1.target == "NVDA")
_check("7.3 run_id defaults None", rep1.run_id is None)
_check("7.4 status set", rep1.status == "unknown")
_check("7.5 records defaults empty", rep1.records == [])
_check("7.6 source_ids defaults empty", rep1.source_ids == [])
_check("7.7 evidence_ids defaults empty", rep1.evidence_ids == [])
_check("7.8 artifact_refs defaults empty", rep1.artifact_refs == [])
_check("7.9 warnings defaults empty", rep1.warnings == [])
_check("7.10 calculation_version set", rep1.calculation_version == "option_trade_memory_v1")
_check("7.11 approved_for_execution always False", rep1.approved_for_execution is False)

# approved_for_execution=True rejected
try:
    OptionTradeMemoryReport(
        report_id="otmrep_002",
        target="NVDA",
        status="unknown",
        summary=_summ_for_report,
        created_at="2026-05-26",
        updated_at="2026-05-26",
        approved_for_execution=True,
    )
    _fail("7.12 approved_for_execution=True rejected in report", "should have raised")
except ValidationError:
    _ok("7.12 approved_for_execution=True rejected in report")

# whitespace report_id rejected
try:
    OptionTradeMemoryReport(
        report_id="  ",
        target="NVDA",
        status="unknown",
        summary=_summ_for_report,
        created_at="2026-05-26",
        updated_at="2026-05-26",
    )
    _fail("7.13 whitespace report_id rejected", "should have raised")
except ValidationError:
    _ok("7.13 whitespace report_id rejected")


# ---------------------------------------------------------------------------
# Section 8: approved_for_execution=True rejected in all models
# ---------------------------------------------------------------------------

_section("8: approved_for_execution=True rejected (all models)")

# OptionTradePlanMemoryRecord
try:
    OptionTradePlanMemoryRecord(
        option_trade_memory_id="x",
        target="NVDA",
        status="active",
        decision="option",
        review_status="not_required",
        outcome="pending",
        plan_snapshot=_snap_for_rec,
        rationale="x",
        recorded_at="2026-01-01",
        approved_for_execution=True,
    )
    _fail("8.1 OptionTradePlanMemoryRecord rejects True", "should have raised")
except ValidationError:
    _ok("8.1 OptionTradePlanMemoryRecord rejects True")

# OptionTradeMemorySummary
try:
    OptionTradeMemorySummary(target="NVDA", status="active", approved_for_execution=True)
    _fail("8.2 OptionTradeMemorySummary rejects True", "should have raised")
except ValidationError:
    _ok("8.2 OptionTradeMemorySummary rejects True")

# OptionTradeMemoryReport
try:
    OptionTradeMemoryReport(
        report_id="r1",
        target="NVDA",
        status="unknown",
        summary=_summ_for_report,
        created_at="2026-01-01",
        updated_at="2026-01-01",
        approved_for_execution=True,
    )
    _fail("8.3 OptionTradeMemoryReport rejects True", "should have raised")
except ValidationError:
    _ok("8.3 OptionTradeMemoryReport rejects True")


# ---------------------------------------------------------------------------
# Section 9: no broker/order/account/execution fields in source module
# ---------------------------------------------------------------------------

_section("9: no broker/order/account/execution fields in source module")

import lib.reliability.option_trade_memory as _otm_module
_otm_src = open(_otm_module.__file__).read()

_check("9.1 no 'import streamlit' in option_trade_memory", "import streamlit" not in _otm_src)
_check("9.2 no 'import anthropic' in option_trade_memory", "import anthropic" not in _otm_src)
_check("9.3 no 'import alpaca' in option_trade_memory", "import alpaca" not in _otm_src)
_check("9.4 no 'execution_id' in option_trade_memory", "execution_id" not in _otm_src)
_check("9.5 no 'brokerage_api' in option_trade_memory", "brokerage_api" not in _otm_src)
_check("9.6 no 'order_id' field name in option_trade_memory", "order_id" not in _otm_src)
_check("9.7 no 'account_id' field name in option_trade_memory", "account_id" not in _otm_src)
_check("9.8 no 'broker' connection in option_trade_memory", "broker.connect" not in _otm_src)
_check("9.9 no live option-chain import", "option_chain_api" not in _otm_src)
_check("9.10 approved_for_execution always False guarded", "approved_for_execution must always be False" in _otm_src)


# ---------------------------------------------------------------------------
# Section 10: build_option_trade_plan_snapshot
# ---------------------------------------------------------------------------

_section("10: build_option_trade_plan_snapshot")

_snap10 = build_option_trade_plan_snapshot(
    target="AAPL",
    decision="option",
    strategy_type="call_debit_spread",
    expiration="2026-07-18",
    entry_iv=0.40,
    exit_iv=0.25,
    entry_underlying_price=200.0,
    max_loss=150.0,
    max_gain=350.0,
    breakeven=205.0,
    cash_required=150.0,
    risk_reward_ratio=2.33,
    contracts=2,
    planned_exit_rule="Exit at 60% max gain or expiration.",
    actual_exit_reason=None,
    risk_level="medium",
    as_of="2026-05-26",
)
_check("10.1 snapshot_id non-empty", bool(_snap10.snapshot_id))
_check("10.2 snapshot_id has correct prefix", _snap10.snapshot_id.startswith("otsnap_"))
_check("10.3 target set", _snap10.target == "AAPL")
_check("10.4 decision set", _snap10.decision == "option")
_check("10.5 strategy_type set", _snap10.strategy_type == "call_debit_spread")
_check("10.6 expiration set", _snap10.expiration == "2026-07-18")
_check("10.7 entry_iv set", _snap10.entry_iv == 0.40)
_check("10.8 exit_iv set", _snap10.exit_iv == 0.25)
_check("10.9 max_loss set", _snap10.max_loss == 150.0)
_check("10.10 max_gain set", _snap10.max_gain == 350.0)
_check("10.11 contracts set", _snap10.contracts == 2)
_check("10.12 risk_reward_ratio set", _snap10.risk_reward_ratio == 2.33)
_check("10.13 risk_level set", _snap10.risk_level == "medium")
_check("10.14 actual_exit_reason None", _snap10.actual_exit_reason is None)

# Deterministic: same inputs → same snapshot_id (all fields identical to _snap10)
_snap10b = build_option_trade_plan_snapshot(
    target="AAPL",
    decision="option",
    strategy_type="call_debit_spread",
    expiration="2026-07-18",
    entry_iv=0.40,
    exit_iv=0.25,
    entry_underlying_price=200.0,
    max_loss=150.0,
    max_gain=350.0,
    breakeven=205.0,
    cash_required=150.0,
    risk_reward_ratio=2.33,
    contracts=2,
    planned_exit_rule="Exit at 60% max gain or expiration.",
    actual_exit_reason=None,
    risk_level="medium",
    as_of="2026-05-26",
)
_check("10.15 same inputs → same snapshot_id", _snap10.snapshot_id == _snap10b.snapshot_id)

# Different entry_iv → different snapshot_id
_snap10c = build_option_trade_plan_snapshot(
    target="AAPL",
    decision="option",
    strategy_type="call_debit_spread",
    expiration="2026-07-18",
    entry_iv=0.60,  # different
    max_loss=150.0,
    risk_level="medium",
    as_of="2026-05-26",
)
_check("10.16 different entry_iv → different snapshot_id", _snap10.snapshot_id != _snap10c.snapshot_id)

# Source refs dedup
_sr_dup = [
    OptionTradeMemorySourceRef(source_id="dup_src", label="first"),
    OptionTradeMemorySourceRef(source_id="dup_src", label="second"),
    OptionTradeMemorySourceRef(source_id="unique_src"),
]
_snap10_dup = build_option_trade_plan_snapshot(
    target="NVDA",
    source_refs=_sr_dup,
    as_of="2026-05-26",
)
_check("10.17 source_refs deduped by source_id", len(_snap10_dup.source_refs) == 2)
_check("10.18 first occurrence wins in dedup", _snap10_dup.source_refs[0].label == "first")


# ---------------------------------------------------------------------------
# Section 11: build_option_trade_memory_record (basic)
# ---------------------------------------------------------------------------

_section("11: build_option_trade_memory_record (basic)")

_bundle11 = OptionTradeMemoryInputBundle(target="NVDA", as_of="2026-05-26T09:00:00Z")
_snap11 = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    entry_iv=0.55,
    max_loss=500.0,
    risk_level="medium",
    as_of="2026-05-26",
)
rec11 = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Strong breakout thesis. Buying long call.",
    plan_snapshot=_snap11,
    review_status="not_required",
    outcome="pending",
    input_bundle=_bundle11,
)
_check("11.1 option_trade_memory_id non-empty", bool(rec11.option_trade_memory_id))
_check("11.2 option_trade_memory_id has prefix", rec11.option_trade_memory_id.startswith("otmem_"))
_check("11.3 target set", rec11.target == "NVDA")
_check("11.4 decision set", rec11.decision == "option")
_check("11.5 status auto-determined", rec11.status == "active")
_check("11.6 review_status set", rec11.review_status == "not_required")
_check("11.7 outcome set", rec11.outcome == "pending")
_check("11.8 rationale set", "long call" in rec11.rationale)
_check("11.9 plan_snapshot set", rec11.plan_snapshot.snapshot_id == _snap11.snapshot_id)
_check("11.10 recorded_at from bundle.as_of", rec11.recorded_at == "2026-05-26T09:00:00Z")
_check("11.11 event_log has at least one entry", len(rec11.event_log) >= 1)
_check("11.12 creation event_type correct", rec11.event_log[0].event_type == "option_plan_recorded")
_check("11.13 approved_for_execution always False", rec11.approved_for_execution is False)
_check("11.14 warnings include missing artifacts", len(rec11.warnings) > 0)

# With no plan_snapshot → auto-generates with warning
rec11_nosnap = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="No snapshot provided.",
    plan_snapshot=None,
    input_bundle=_bundle11,
)
_check("11.15 no snapshot → warning generated", any("No plan_snapshot" in w for w in rec11_nosnap.warnings))
_check("11.16 no snapshot → snapshot auto-generated", rec11_nosnap.plan_snapshot is not None)


# ---------------------------------------------------------------------------
# Section 12: deterministic output without explicit timestamps
# ---------------------------------------------------------------------------

_section("12: deterministic output without explicit timestamps")

_snap12 = build_option_trade_plan_snapshot(
    target="MSFT",
    decision="option",
    strategy_type="put_debit_spread",
    entry_iv=0.30,
    max_loss=200.0,
    risk_level="medium",
    as_of="2026-05-26",
)

def _make_rec12():
    return build_option_trade_memory_record(
        target="MSFT",
        decision="option",
        rationale="Defensive put spread as hedge.",
        plan_snapshot=_snap12,
        review_status="not_required",
        outcome="pending",
    )

rec12a = _make_rec12()
rec12b = _make_rec12()
_check("12.1 option_trade_memory_id stable across calls", rec12a.option_trade_memory_id == rec12b.option_trade_memory_id)
_check("12.2 recorded_at stable (default)", rec12a.recorded_at == rec12b.recorded_at)
_check("12.3 event_log[0].event_id stable", rec12a.event_log[0].event_id == rec12b.event_log[0].event_id)
_check("12.4 recorded_at uses deterministic default", rec12a.recorded_at == "1970-01-01T00:00:00Z")


# ---------------------------------------------------------------------------
# Section 13: explicit timestamp override works
# ---------------------------------------------------------------------------

_section("13: explicit timestamp override works")

_ts_explicit = "2026-05-26T14:00:00Z"
rec13 = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Explicit timestamp test.",
    plan_snapshot=_snap11,
    recorded_at=_ts_explicit,
)
_check("13.1 recorded_at uses explicit timestamp", rec13.recorded_at == _ts_explicit)
_check("13.2 event_log[0].created_at uses explicit timestamp", rec13.event_log[0].created_at == _ts_explicit)

# bundle.as_of used when no explicit
_bundle13 = OptionTradeMemoryInputBundle(target="NVDA", as_of="2026-05-26T08:00:00Z")
rec13b = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Bundle as_of test.",
    plan_snapshot=_snap11,
    input_bundle=_bundle13,
)
_check("13.3 recorded_at uses bundle.as_of when no explicit", rec13b.recorded_at == "2026-05-26T08:00:00Z")

# Explicit overrides bundle.as_of
rec13c = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Explicit overrides bundle.as_of.",
    plan_snapshot=_snap11,
    recorded_at="2026-05-26T12:30:00Z",
    input_bundle=_bundle13,
)
_check("13.4 explicit recorded_at overrides bundle.as_of", rec13c.recorded_at == "2026-05-26T12:30:00Z")

# report timestamps
_bundle13r = OptionTradeMemoryInputBundle(target="NVDA", as_of="2026-05-26T10:00:00Z")
rep13 = build_option_trade_memory_report(_bundle13r, records=[])
_check("13.5 report created_at uses bundle.as_of", rep13.created_at == "2026-05-26T10:00:00Z")
_check("13.6 report updated_at defaults to created_at", rep13.updated_at == rep13.created_at)

rep13_explicit = build_option_trade_memory_report(
    _bundle13r,
    records=[],
    created_at="2026-05-26T11:00:00Z",
    updated_at="2026-05-26T11:30:00Z",
)
_check("13.7 explicit created_at used in report", rep13_explicit.created_at == "2026-05-26T11:00:00Z")
_check("13.8 explicit updated_at used in report", rep13_explicit.updated_at == "2026-05-26T11:30:00Z")


# ---------------------------------------------------------------------------
# Section 14: stable record / report IDs
# ---------------------------------------------------------------------------

_section("14: stable record / report IDs")

_snap14 = build_option_trade_plan_snapshot(
    target="GOOGL",
    decision="stock",
    strategy_type="stock",
    risk_level="low",
    as_of="2026-05-26",
)
_bundle14 = OptionTradeMemoryInputBundle(target="GOOGL", run_id="run_googl_001", as_of="2026-05-26")

rec14a = build_option_trade_memory_record(
    target="GOOGL",
    decision="stock",
    rationale="Buying stock directly.",
    plan_snapshot=_snap14,
    review_status="not_required",
    outcome="pending",
    run_id="run_googl_001",
    recorded_at="2026-05-26",
)
rec14b = build_option_trade_memory_record(
    target="GOOGL",
    decision="stock",
    rationale="Buying stock directly.",
    plan_snapshot=_snap14,
    review_status="not_required",
    outcome="pending",
    run_id="run_googl_001",
    recorded_at="2026-05-26",
)
_check("14.1 identical inputs → stable option_trade_memory_id", rec14a.option_trade_memory_id == rec14b.option_trade_memory_id)
_check("14.2 identical inputs → stable event_id", rec14a.event_log[0].event_id == rec14b.event_log[0].event_id)

rep14a = build_option_trade_memory_report(_bundle14, records=[], created_at="2026-05-26")
rep14b = build_option_trade_memory_report(_bundle14, records=[], created_at="2026-05-26")
_check("14.3 identical inputs → stable report_id", rep14a.report_id == rep14b.report_id)


# ---------------------------------------------------------------------------
# Section 15: materially different inputs → different record IDs
# ---------------------------------------------------------------------------

_section("15: materially different inputs → different record IDs")

_snap15_lc = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    entry_iv=0.55,
    max_loss=500.0,
    risk_level="medium",
    as_of="2026-05-26",
)
_snap15_lp = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_put",  # different strategy
    entry_iv=0.55,
    max_loss=500.0,
    risk_level="medium",
    as_of="2026-05-26",
)

_kwargs15 = dict(target="NVDA", outcome="pending", recorded_at="2026-05-26")

rec15_base = build_option_trade_memory_record(
    decision="option", rationale="Base.", plan_snapshot=_snap15_lc,
    review_status="not_required", **_kwargs15
)

# Different decision
rec15_stock = build_option_trade_memory_record(
    decision="stock", rationale="Base.", plan_snapshot=_snap15_lc,
    review_status="not_required", **_kwargs15
)
_check("15.1 different decision → different ID", rec15_base.option_trade_memory_id != rec15_stock.option_trade_memory_id)

# Different strategy_type (via snapshot)
rec15_lp = build_option_trade_memory_record(
    decision="option", rationale="Base.", plan_snapshot=_snap15_lp,
    review_status="not_required", **_kwargs15
)
_check("15.2 different strategy_type → different ID", rec15_base.option_trade_memory_id != rec15_lp.option_trade_memory_id)

# Different rationale
rec15_rat = build_option_trade_memory_record(
    decision="option", rationale="Different rationale.", plan_snapshot=_snap15_lc,
    review_status="not_required", **_kwargs15
)
_check("15.3 different rationale → different ID", rec15_base.option_trade_memory_id != rec15_rat.option_trade_memory_id)

# Different review_status
rec15_rev = build_option_trade_memory_record(
    decision="option", rationale="Base.", plan_snapshot=_snap15_lc,
    review_status="reviewed", **_kwargs15
)
_check("15.4 different review_status → different ID", rec15_base.option_trade_memory_id != rec15_rev.option_trade_memory_id)

# Different outcome
rec15_out = build_option_trade_memory_record(
    decision="option", rationale="Base.", plan_snapshot=_snap15_lc,
    review_status="not_required",
    target="NVDA", outcome="profit", recorded_at="2026-05-26"
)
_check("15.5 different outcome → different ID", rec15_base.option_trade_memory_id != rec15_out.option_trade_memory_id)

# Different snapshot (same strategy_type, different entry_iv)
_snap15_hi_iv = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    entry_iv=0.80,  # different IV
    max_loss=500.0,
    risk_level="medium",
    as_of="2026-05-26",
)
rec15_snap2 = build_option_trade_memory_record(
    decision="option", rationale="Base.", plan_snapshot=_snap15_hi_iv,
    review_status="not_required", **_kwargs15
)
_check("15.6 different snapshot content → different ID", rec15_base.option_trade_memory_id != rec15_snap2.option_trade_memory_id)

# Verify all six variants have distinct IDs
_ids_15 = {
    rec15_base.option_trade_memory_id,
    rec15_stock.option_trade_memory_id,
    rec15_lp.option_trade_memory_id,
    rec15_rat.option_trade_memory_id,
    rec15_rev.option_trade_memory_id,
    rec15_out.option_trade_memory_id,
}
_check("15.7 all six variants have distinct IDs", len(_ids_15) == 6)


# ---------------------------------------------------------------------------
# Section 16: event log ID stability and difference
# ---------------------------------------------------------------------------

_section("16: event log ID stability and difference")

# Identical records → identical event IDs
rec16a = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Event ID test.",
    plan_snapshot=_snap15_lc,
    review_status="not_required",
    outcome="pending",
    recorded_at="2026-05-26",
)
rec16b = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Event ID test.",
    plan_snapshot=_snap15_lc,
    review_status="not_required",
    outcome="pending",
    recorded_at="2026-05-26",
)
_check("16.1 identical inputs → same event_id for creation entry", rec16a.event_log[0].event_id == rec16b.event_log[0].event_id)

# Different rationale → different record ID → different event ID
rec16c = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Different rationale for event ID test.",
    plan_snapshot=_snap15_lc,
    review_status="not_required",
    outcome="pending",
    recorded_at="2026-05-26",
)
_check("16.2 distinct records → distinct creation event_id", rec16a.event_log[0].event_id != rec16c.event_log[0].event_id)

# make_option_trade_memory_log_entry_id is deterministic
eid1 = make_option_trade_memory_log_entry_id("rec_A", "option_plan_recorded", "2026-01-01")
eid2 = make_option_trade_memory_log_entry_id("rec_A", "option_plan_recorded", "2026-01-01")
_check("16.3 make_option_trade_memory_log_entry_id is deterministic", eid1 == eid2)
_check("16.4 log entry ID has correct prefix", eid1.startswith("otlog_"))

# Different option_trade_memory_id → different log entry ID
eid3 = make_option_trade_memory_log_entry_id("rec_B", "option_plan_recorded", "2026-01-01")
_check("16.5 different record ID → different log entry ID", eid1 != eid3)

# Different event_type → different log entry ID
eid4 = make_option_trade_memory_log_entry_id("rec_A", "review_requested", "2026-01-01")
_check("16.6 different event_type → different log entry ID", eid1 != eid4)


# ---------------------------------------------------------------------------
# Section 17: source / evidence / artifact deduplication
# ---------------------------------------------------------------------------

_section("17: source / evidence / artifact deduplication")

_bundle17 = OptionTradeMemoryInputBundle(
    target="NVDA",
    source_ids=["sid_direct", "sid_direct", "sid_unique"],
    evidence_ids=["e_direct", "e_direct", "e_unique"],
    artifact_refs=["art_direct", "art_direct", "art_unique"],
)
_rec17 = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Dedup test.",
    plan_snapshot=_snap11,
    source_refs=[
        OptionTradeMemorySourceRef(source_id="sid_rec"),
        OptionTradeMemorySourceRef(source_id="sid_rec"),  # dup
        OptionTradeMemorySourceRef(source_id="sid_rec2"),
    ],
    evidence_ids=["e_rec", "e_rec"],  # dup
    artifact_refs=["art_rec", "art_rec"],  # dup
    input_bundle=OptionTradeMemoryInputBundle(target="NVDA"),
)

sids = collect_option_trade_memory_source_ids(_bundle17, [_rec17])
_check("17.1 source_ids from bundle deduped", sids.count("sid_direct") == 1)
_check("17.2 unique source_id from bundle included", "sid_unique" in sids)
_check("17.3 source_ids from record source_refs included", "sid_rec" in sids)
_check("17.4 no duplicates in source_ids result", len(sids) == len(set(sids)))

eids = collect_option_trade_memory_evidence_ids(_bundle17, [_rec17])
_check("17.5 evidence_ids from bundle deduped", eids.count("e_direct") == 1)
_check("17.6 unique evidence_id from bundle included", "e_unique" in eids)
_check("17.7 evidence_ids from record included", "e_rec" in eids)
_check("17.8 no duplicates in evidence_ids result", len(eids) == len(set(eids)))

arts = collect_option_trade_memory_artifact_refs(_bundle17, [_rec17])
_check("17.9 artifact_refs from bundle deduped", arts.count("art_direct") == 1)
_check("17.10 unique artifact_ref from bundle included", "art_unique" in arts)
_check("17.11 artifact_refs from record included", "art_rec" in arts)
_check("17.12 no duplicates in artifact_refs result", len(arts) == len(set(arts)))

# Empty/whitespace artifact refs filtered
_bundle17_ws = OptionTradeMemoryInputBundle(
    target="NVDA",
    artifact_refs=["art_ok", "", "  ", "art_ok2"],
)
arts_filtered = collect_option_trade_memory_artifact_refs(_bundle17_ws)
_check("17.13 empty artifact refs filtered", "" not in arts_filtered)
_check("17.14 whitespace artifact refs filtered", "  " not in arts_filtered)
_check("17.15 valid artifact refs retained", "art_ok" in arts_filtered and "art_ok2" in arts_filtered)


# ---------------------------------------------------------------------------
# Section 18: event log construction
# ---------------------------------------------------------------------------

_section("18: event log construction")

# Record with lesson and terminal outcome → event log has lesson + outcome entries
rec18 = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Profitable trade with lesson.",
    plan_snapshot=_snap11,
    review_status="reviewed",
    outcome="profit",
    pnl_amount=250.0,
    pnl_pct=0.50,
    lesson="Hold to expiration on strong thesis.",
    recorded_at="2026-05-26",
)
event_types18 = [e.event_type for e in rec18.event_log]
_check("18.1 creation event present", "option_plan_recorded" in event_types18)
_check("18.2 outcome_observed event present for profit", "outcome_observed" in event_types18)
_check("18.3 pnl_updated event present when pnl provided", "pnl_updated" in event_types18)
_check("18.4 lesson_added event present", "lesson_added" in event_types18)
_check("18.5 event_log has at least 4 entries", len(rec18.event_log) >= 4)

# Blocked status → review_requested event added
rec18_blocked = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Blocked record.",
    plan_snapshot=build_option_trade_plan_snapshot(
        target="NVDA",
        decision="option",
        strategy_type="long_call",
        risk_level="high",
        as_of="2026-05-26",
    ),
    review_status="blocked",
    recorded_at="2026-05-26",
)
event_types18_blocked = [e.event_type for e in rec18_blocked.event_log]
_check("18.6 blocked status → review_requested event present", "review_requested" in event_types18_blocked)

# No lesson, no outcome → only creation entry
rec18_minimal = build_option_trade_memory_record(
    target="NVDA",
    decision="no_trade",
    rationale="No trade decision.",
    plan_snapshot=snap_no_trade,
    review_status="not_required",
    outcome="no_trade",
    recorded_at="2026-05-26",
)
event_types18_minimal = [e.event_type for e in rec18_minimal.event_log]
_check("18.7 no_trade → creation event present", "option_plan_recorded" in event_types18_minimal)
_check("18.8 no_trade → outcome_observed present (no_trade is terminal)", "outcome_observed" in event_types18_minimal)

# build_option_trade_memory_log_entry
log18 = build_option_trade_memory_log_entry(
    event_type="exit_rule_updated",
    description="Exit rule changed to 40% max gain.",
    option_trade_memory_id="otmem_test",
    created_at="2026-05-26",
    actor="reviewer",
    source_ids=["src_reviewer"],
    metadata={"old_rule": "60%", "new_rule": "40%"},
)
_check("18.9 log entry event_id non-empty", bool(log18.event_id))
_check("18.10 log entry event_id has prefix", log18.event_id.startswith("otlog_"))
_check("18.11 log entry event_type set", log18.event_type == "exit_rule_updated")
_check("18.12 log entry actor set", log18.actor == "reviewer")
_check("18.13 log entry metadata set", log18.metadata["new_rule"] == "40%")


# ---------------------------------------------------------------------------
# Section 19: missing optional artifacts create warnings without crashing
# ---------------------------------------------------------------------------

_section("19: missing optional artifacts create warnings without crashing")

_bundle19 = OptionTradeMemoryInputBundle(
    target="NVDA",
    # all optional artifacts are None by default
)
rec19 = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Missing artifacts test.",
    plan_snapshot=_snap11,
    input_bundle=_bundle19,
)
_check("19.1 record builds without crashing", rec19 is not None)
_check("19.2 warnings include missing option_expression_report", any("option_expression_report" in w for w in rec19.warnings))
_check("19.3 warnings include missing trade_plan_report", any("trade_plan_report" in w for w in rec19.warnings))
_check("19.4 warnings include missing decision_packet", any("decision_packet" in w for w in rec19.warnings))

report19 = build_option_trade_memory_report(_bundle19, records=[rec19])
_check("19.5 report builds without crashing", report19 is not None)
_check("19.6 report warnings include missing human_review_report", any("human_review_report" in w for w in report19.warnings))

# With all artifacts provided (mock)
_mock_oer = types.SimpleNamespace(source_ids=["sid_oer"], report_id="oer_001")
_mock_tpr = types.SimpleNamespace(source_ids=["sid_tpr"], report_id="tpr_001")
_mock_dp = types.SimpleNamespace(source_ids=["sid_dp"], packet_id="dp_001")
_mock_hrr = types.SimpleNamespace(source_ids=["sid_hrr"], report_id="hrr_001", status="approved")
_bundle19_full = OptionTradeMemoryInputBundle(
    target="NVDA",
    option_expression_report=_mock_oer,
    trade_plan_report=_mock_tpr,
    decision_packet=_mock_dp,
    human_review_report=_mock_hrr,
)
report19_full = build_option_trade_memory_report(_bundle19_full, records=[])
_check("19.7 report builds with all artifacts present", report19_full is not None)
# Artifacts provided → no "Missing optional" warning for those specific ones
_check("19.8 no 'Missing optional upstream artifact: option_expression_report' when provided",
       not any("Missing optional upstream artifact: option_expression_report" in w for w in report19_full.warnings))


# ---------------------------------------------------------------------------
# Section 20: human-review blocked causes blocked
# ---------------------------------------------------------------------------

_section("20: human-review blocked causes blocked")

_mock_hrr_blocked = types.SimpleNamespace(status="blocked")

# Single record: HRR blocked → record status blocked
_bundle20_rec = OptionTradeMemoryInputBundle(
    target="NVDA",
    human_review_report=_mock_hrr_blocked,
)
rec20_blocked = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="HRR blocked test.",
    plan_snapshot=_snap11,
    review_status="pending",
    input_bundle=_bundle20_rec,
)
_check("20.1 HRR blocked → single record status is blocked", rec20_blocked.status == "blocked")
_check("20.2 HRR blocked → warning in record", any("blocked" in w.lower() for w in rec20_blocked.warnings))

# Report: HRR blocked → report status blocked
_bundle20_rep = OptionTradeMemoryInputBundle(
    target="NVDA",
    human_review_report=_mock_hrr_blocked,
)
report20 = build_option_trade_memory_report(_bundle20_rep, records=[])
_check("20.3 HRR blocked → report status is blocked", report20.status == "blocked")
_check("20.4 HRR blocked → report summary.blocked_count = 0 (no records)", report20.summary.blocked_count == 0)

# Report: blocked record → report status blocked
_bundle20_nohrr = OptionTradeMemoryInputBundle(target="NVDA")
rec20_blocked2 = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Blocked via review_status.",
    plan_snapshot=_snap11,
    review_status="blocked",
    input_bundle=_bundle20_nohrr,
)
report20b = build_option_trade_memory_report(_bundle20_nohrr, records=[rec20_blocked2])
_check("20.5 blocked record → report status is blocked", report20b.status == "blocked")
_check("20.6 blocked record → summary.blocked_count = 1", report20b.summary.blocked_count == 1)


# ---------------------------------------------------------------------------
# Section 21: high-risk or pending-review causes needs_review
# ---------------------------------------------------------------------------

_section("21: high-risk or pending-review causes needs_review")

_snap21_high = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    risk_level="high",
    as_of="2026-05-26",
)
_bundle21 = OptionTradeMemoryInputBundle(target="NVDA")

# High-risk + not reviewed → needs_review
rec21_high = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="High-risk unreviewed.",
    plan_snapshot=_snap21_high,
    review_status="not_required",
    input_bundle=_bundle21,
)
_check("21.1 high-risk unreviewed → status needs_review", rec21_high.status == "needs_review")
_check("21.2 high-risk unreviewed → warning in record", any("High-risk" in w for w in rec21_high.warnings))

# High-risk + reviewed → reviewed (not needs_review)
rec21_high_reviewed = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="High-risk but reviewed.",
    plan_snapshot=_snap21_high,
    review_status="reviewed",
    input_bundle=_bundle21,
)
_check("21.3 high-risk reviewed → status is reviewed", rec21_high_reviewed.status == "reviewed")

# Pending review → needs_review
_snap21_med = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_put",
    risk_level="medium",
    as_of="2026-05-26",
)
rec21_pending = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Pending review.",
    plan_snapshot=_snap21_med,
    review_status="pending",
    input_bundle=_bundle21,
)
_check("21.4 pending review → status needs_review", rec21_pending.status == "needs_review")

# Report: needs_review record escalates report status
report21 = build_option_trade_memory_report(_bundle21, records=[rec21_high])
_check("21.5 needs_review record → report status is needs_review", report21.status == "needs_review")
_check("21.6 needs_review record → summary.needs_review_count = 1", report21.summary.needs_review_count == 1)

# Report: high-risk active record (not needs_review status but risk_level=high) escalates
_snap21_active_high = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    risk_level="high",
    as_of="2026-05-26",
)
rec21_active_high = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Active high-risk.",
    plan_snapshot=_snap21_active_high,
    review_status="not_required",
    initial_status="active",  # forced to active to test report escalation
    input_bundle=_bundle21,
)
# With initial_status=active but high risk_level → report escalates via high_risk logic
report21b = build_option_trade_memory_report(_bundle21, records=[rec21_active_high])
_check("21.7 high-risk active record → report escalates to needs_review", report21b.status == "needs_review")


# ---------------------------------------------------------------------------
# Section 22: closed / reviewed records produce closed / reviewed status
# ---------------------------------------------------------------------------

_section("22: closed / reviewed records produce closed / reviewed status")

_bundle22 = OptionTradeMemoryInputBundle(target="AAPL", as_of="2026-05-26")
_snap22 = build_option_trade_plan_snapshot(
    target="AAPL",
    decision="option",
    strategy_type="covered_call",
    risk_level="low",
    as_of="2026-05-26",
)

# Profit outcome → auto-closed
rec22_profit = build_option_trade_memory_record(
    target="AAPL",
    decision="option",
    rationale="Profit trade.",
    plan_snapshot=_snap22,
    review_status="not_required",
    outcome="profit",
    pnl_amount=150.0,
    input_bundle=_bundle22,
)
_check("22.1 profit outcome → single record status is closed", rec22_profit.status == "closed")

# Reviewed + terminal → reviewed (reviewed > closed in single record)
rec22_reviewed_profit = build_option_trade_memory_record(
    target="AAPL",
    decision="option",
    rationale="Reviewed and profitable.",
    plan_snapshot=_snap22,
    review_status="reviewed",
    outcome="profit",
    pnl_amount=200.0,
    input_bundle=_bundle22,
)
_check("22.2 reviewed + profit → single record status is reviewed", rec22_reviewed_profit.status == "reviewed")

# All records closed → report status is closed
report22_all_closed = build_option_trade_memory_report(_bundle22, records=[rec22_profit])
_check("22.3 all records closed → report status is closed", report22_all_closed.status == "closed")
_check("22.4 closed record → summary.closed_count = 1", report22_all_closed.summary.closed_count == 1)

# All records reviewed → report status is reviewed
report22_all_reviewed = build_option_trade_memory_report(_bundle22, records=[rec22_reviewed_profit])
_check("22.5 all records reviewed → report status is reviewed", report22_all_reviewed.status == "reviewed")

# Mix of closed + reviewed → reviewed (not all closed)
report22_mix = build_option_trade_memory_report(_bundle22, records=[rec22_profit, rec22_reviewed_profit])
_check("22.6 mix of closed+reviewed → report status is reviewed", report22_mix.status == "reviewed")


# ---------------------------------------------------------------------------
# Section 23: planned / active records produce planned / active status
# ---------------------------------------------------------------------------

_section("23: planned / active records produce planned / active status")

_bundle23 = OptionTradeMemoryInputBundle(target="TSLA", as_of="2026-05-26")
_snap23 = build_option_trade_plan_snapshot(
    target="TSLA",
    decision="option",
    strategy_type="cash_secured_put",
    risk_level="low",
    as_of="2026-05-26",
)

rec23_planned = build_option_trade_memory_record(
    target="TSLA",
    decision="option",
    rationale="Planned trade.",
    plan_snapshot=_snap23,
    review_status="not_required",
    outcome="pending",
    initial_status="planned",
    input_bundle=_bundle23,
)
_check("23.1 initial_status=planned preserved", rec23_planned.status == "planned")

rec23_active = build_option_trade_memory_record(
    target="TSLA",
    decision="option",
    rationale="Active trade.",
    plan_snapshot=_snap23,
    review_status="not_required",
    outcome="pending",
    input_bundle=_bundle23,
)
_check("23.2 default (pending outcome, not reviewed) → status active", rec23_active.status == "active")

# Report: only planned records → planned
report23_planned = build_option_trade_memory_report(_bundle23, records=[rec23_planned])
_check("23.3 all planned records → report status is planned", report23_planned.status == "planned")

# Report: mix of planned + active → active (higher priority)
report23_mix = build_option_trade_memory_report(_bundle23, records=[rec23_planned, rec23_active])
_check("23.4 mix of planned+active → report status is active", report23_mix.status == "active")

# Report: only active → active
report23_active = build_option_trade_memory_report(_bundle23, records=[rec23_active])
_check("23.5 only active records → report status is active", report23_active.status == "active")


# ---------------------------------------------------------------------------
# Section 24: no_trade memory is valid and safe
# ---------------------------------------------------------------------------

_section("24: no_trade memory is valid and safe")

_snap24_nt = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="no_trade",
    strategy_type="no_trade",
    risk_level="undefined",
    as_of="2026-05-26",
)
_bundle24 = OptionTradeMemoryInputBundle(target="NVDA", as_of="2026-05-26")

rec24_nt = build_option_trade_memory_record(
    target="NVDA",
    decision="no_trade",
    rationale="Conditions not favorable. No trade this cycle.",
    plan_snapshot=_snap24_nt,
    review_status="not_required",
    outcome="no_trade",
    input_bundle=_bundle24,
)
_check("24.1 no_trade record builds OK", rec24_nt is not None)
_check("24.2 no_trade decision set", rec24_nt.decision == "no_trade")
_check("24.3 no_trade outcome set", rec24_nt.outcome == "no_trade")
_check("24.4 no_trade snapshot strategy_type is no_trade", rec24_nt.plan_snapshot.strategy_type == "no_trade")
_check("24.5 no_trade approved_for_execution False", rec24_nt.approved_for_execution is False)
_check("24.6 no_trade has no option metrics in snapshot", rec24_nt.plan_snapshot.entry_iv is None)
_check("24.7 no_trade has no max_loss in snapshot", rec24_nt.plan_snapshot.max_loss is None)

# no_trade outcome is in terminal outcomes → record is closed (unless reviewed)
_check("24.8 no_trade outcome → record is closed", rec24_nt.status == "closed")

# Report with no_trade record
report24 = build_option_trade_memory_report(_bundle24, records=[rec24_nt])
_check("24.9 no_trade report builds OK", report24 is not None)
_check("24.10 no_trade_count in summary = 1", report24.summary.no_trade_count == 1)
_check("24.11 no_trade report approved_for_execution False", report24.approved_for_execution is False)

# wait decision
rec24_wait = build_option_trade_memory_record(
    target="NVDA",
    decision="wait",
    rationale="Waiting for better entry.",
    plan_snapshot=_snap24_nt,
    review_status="not_required",
    outcome="pending",
    input_bundle=_bundle24,
)
_check("24.12 wait decision is valid", rec24_wait.decision == "wait")


# ---------------------------------------------------------------------------
# Section 25: pnl_amount / pnl_pct summary handling
# ---------------------------------------------------------------------------

_section("25: pnl_amount / pnl_pct summary handling")

_bundle25 = OptionTradeMemoryInputBundle(target="NVDA", as_of="2026-05-26")
_snap25 = build_option_trade_plan_snapshot(target="NVDA", decision="option", as_of="2026-05-26")

rec25_profit = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Win.",
    plan_snapshot=_snap25, review_status="reviewed", outcome="profit",
    pnl_amount=500.0, pnl_pct=0.50, input_bundle=_bundle25,
)
rec25_loss = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Loss.",
    plan_snapshot=_snap25, review_status="reviewed", outcome="loss",
    pnl_amount=-200.0, pnl_pct=-0.40, input_bundle=_bundle25,
)
rec25_pending = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Open trade.",
    plan_snapshot=_snap25, review_status="not_required", outcome="pending",
    input_bundle=_bundle25,
)
report25 = build_option_trade_memory_report(_bundle25, records=[rec25_profit, rec25_loss, rec25_pending])

_check("25.1 profit_count = 1", report25.summary.profit_count == 1)
_check("25.2 loss_count = 1", report25.summary.loss_count == 1)
_check("25.3 pending_outcome_count = 1", report25.summary.pending_outcome_count == 1)
_check("25.4 total_pnl_amount = 300.0 (500 - 200)", abs(report25.summary.total_pnl_amount - 300.0) < 1e-9)
_check("25.5 avg_pnl_pct = 0.05 ((0.50 - 0.40) / 2)", abs(report25.summary.avg_pnl_pct - 0.05) < 1e-9)
_check("25.6 record_count = 3", report25.summary.record_count == 3)

# No PnL records → summary totals are None
rec25_no_pnl = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="No PnL.",
    plan_snapshot=_snap25, input_bundle=_bundle25,
)
report25_no_pnl = build_option_trade_memory_report(_bundle25, records=[rec25_no_pnl])
_check("25.7 no pnl records → total_pnl_amount is None", report25_no_pnl.summary.total_pnl_amount is None)
_check("25.8 no pnl records → avg_pnl_pct is None", report25_no_pnl.summary.avg_pnl_pct is None)


# ---------------------------------------------------------------------------
# Section 26: max_loss_planned summary handling
# ---------------------------------------------------------------------------

_section("26: max_loss_planned summary handling")

_bundle26 = OptionTradeMemoryInputBundle(target="NVDA", as_of="2026-05-26")
_snap26a = build_option_trade_plan_snapshot(
    target="NVDA", decision="option", strategy_type="long_call",
    max_loss=500.0, risk_level="medium", as_of="2026-05-26",
)
_snap26b = build_option_trade_plan_snapshot(
    target="NVDA", decision="option", strategy_type="long_put",
    max_loss=300.0, risk_level="low", as_of="2026-05-26",
)
_snap26_no_ml = build_option_trade_plan_snapshot(
    target="NVDA", decision="no_trade", strategy_type="no_trade",
    risk_level="undefined", as_of="2026-05-26",
)

rec26a = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="R1.", plan_snapshot=_snap26a, input_bundle=_bundle26
)
rec26b = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="R2.", plan_snapshot=_snap26b, input_bundle=_bundle26
)
rec26_no_ml = build_option_trade_memory_record(
    target="NVDA", decision="no_trade", rationale="No trade.", plan_snapshot=_snap26_no_ml, outcome="no_trade", input_bundle=_bundle26
)
report26 = build_option_trade_memory_report(_bundle26, records=[rec26a, rec26b, rec26_no_ml])

_check("26.1 max_loss_planned = max(500, 300) = 500", abs(report26.summary.max_loss_planned - 500.0) < 1e-9)

# No max_loss in any record
report26_no_ml = build_option_trade_memory_report(_bundle26, records=[rec26_no_ml])
_check("26.2 no max_loss records → max_loss_planned is None", report26_no_ml.summary.max_loss_planned is None)


# ---------------------------------------------------------------------------
# Section 27: inputs are not mutated
# ---------------------------------------------------------------------------

_section("27: inputs are not mutated")

_original_srefs = [OptionTradeMemorySourceRef(source_id="sid_orig")]
_original_eids = ["eid_orig"]
_original_arts = ["art_orig"]
_original_extra_warnings = ["original warning"]

rec27 = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="Mutation test.",
    plan_snapshot=_snap11,
    source_refs=_original_srefs,
    evidence_ids=_original_eids,
    artifact_refs=_original_arts,
    extra_warnings=_original_extra_warnings,
    input_bundle=OptionTradeMemoryInputBundle(target="NVDA"),
)
_check("27.1 original source_refs not mutated", len(_original_srefs) == 1)
_check("27.2 original evidence_ids not mutated", len(_original_eids) == 1)
_check("27.3 original artifact_refs not mutated", len(_original_arts) == 1)
_check("27.4 original extra_warnings not mutated", len(_original_extra_warnings) == 1)


# ---------------------------------------------------------------------------
# Section 28: build_option_trade_memory_report (complete)
# ---------------------------------------------------------------------------

_section("28: build_option_trade_memory_report (complete)")

_bundle28 = OptionTradeMemoryInputBundle(
    target="NVDA",
    run_id="run_nvda_28",
    as_of="2026-05-26T10:00:00Z",
    source_ids=["sid_28_research"],
    evidence_ids=["eid_28_valuation"],
)
_snap28 = build_option_trade_plan_snapshot(
    target="NVDA", decision="option", strategy_type="long_call",
    entry_iv=0.55, max_loss=500.0, risk_level="medium", as_of="2026-05-26",
)
rec28_win = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Won trade.",
    plan_snapshot=_snap28, review_status="reviewed", outcome="profit",
    pnl_amount=300.0, pnl_pct=0.60, input_bundle=_bundle28,
)
rec28_active = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Open trade.",
    plan_snapshot=_snap28, review_status="not_required", outcome="pending",
    input_bundle=_bundle28,
)
report28 = build_option_trade_memory_report(_bundle28, records=[rec28_win, rec28_active])

_check("28.1 report builds OK", report28.target == "NVDA")
_check("28.2 report_id has correct prefix", report28.report_id.startswith("otmrep_"))
_check("28.3 run_id propagated", report28.run_id == "run_nvda_28")
_check("28.4 record_count = 2", report28.summary.record_count == 2)
_check("28.5 reviewed_count = 1", report28.summary.reviewed_count == 1)
_check("28.6 status is active (mix of reviewed + active)", report28.status == "active")
_check("28.7 created_at from bundle.as_of", report28.created_at == "2026-05-26T10:00:00Z")
_check("28.8 calculation_version set", report28.calculation_version == "option_trade_memory_v1")
_check("28.9 approved_for_execution False", report28.approved_for_execution is False)
_check("28.10 source_ids include bundle source_ids", "sid_28_research" in report28.source_ids)
_check("28.11 evidence_ids include bundle evidence_ids", "eid_28_valuation" in report28.evidence_ids)
_check("28.12 decision_counts.option = 2", report28.summary.decision_counts.get("option") == 2)
_check("28.13 strategy_counts.long_call = 2", report28.summary.strategy_counts.get("long_call") == 2)
_check("28.14 profit_count = 1", report28.summary.profit_count == 1)
_check("28.15 pending_outcome_count = 1", report28.summary.pending_outcome_count == 1)

# Empty records → unknown status
report28_empty = build_option_trade_memory_report(_bundle28, records=[])
_check("28.16 empty records → status unknown", report28_empty.status == "unknown")
_check("28.17 empty records → record_count = 0", report28_empty.summary.record_count == 0)


# ---------------------------------------------------------------------------
# Section 29: ToolResult adapter
# ---------------------------------------------------------------------------

_section("29: ToolResult adapter")

_bundle29 = OptionTradeMemoryInputBundle(target="NVDA", as_of="2026-05-26")
_snap29 = build_option_trade_plan_snapshot(
    target="NVDA", decision="option", strategy_type="long_call",
    entry_iv=0.55, max_loss=500.0, risk_level="medium", as_of="2026-05-26",
)
rec29 = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="ToolResult test.",
    plan_snapshot=_snap29, review_status="reviewed", outcome="profit",
    pnl_amount=400.0, input_bundle=_bundle29,
)
report29 = build_option_trade_memory_report(_bundle29, records=[rec29])
tr29 = option_trade_memory_tool_result_from_report(report29)

_check("29.1 ToolResult builds OK", tr29 is not None)
_check("29.2 tool_name is option_trade_memory_report", tr29.tool_name == "option_trade_memory_report")
_check("29.3 ticker set to target", tr29.ticker == "NVDA")
_check("29.4 evidence_id is non-empty", bool(tr29.evidence_id))
_check("29.5 outputs.report_id present", "report_id" in tr29.outputs)
_check("29.6 outputs.summary present", "summary" in tr29.outputs)
_check("29.7 outputs.calculation_version correct", tr29.outputs.get("calculation_version") == "option_trade_memory_v1")
_check("29.8 outputs.record_count correct", tr29.outputs.get("record_count") == 1)
_check("29.9 outputs.reviewed_count correct", tr29.outputs.get("reviewed_count") == 1)
_check("29.10 outputs.approved_for_execution False", tr29.outputs.get("approved_for_execution") is False)
_check("29.11 outputs.report is full report dict", isinstance(tr29.outputs.get("report"), dict))
_check("29.12 outputs.closed_count present", "closed_count" in tr29.outputs)
_check("29.13 outputs.no_trade_count present", "no_trade_count" in tr29.outputs)

# Deterministic evidence_id
tr29b = option_trade_memory_tool_result_from_report(report29)
_check("29.14 evidence_id is deterministic", tr29.evidence_id == tr29b.evidence_id)

# With explicit run_id
tr29_run = option_trade_memory_tool_result_from_report(report29, run_id="explicit_run_29")
_check("29.15 explicit run_id used", tr29_run.run_id == "explicit_run_29")


# ---------------------------------------------------------------------------
# Section 30: ToolResult evidence_id changes when content changes
# ---------------------------------------------------------------------------

_section("30: ToolResult evidence_id changes when content changes")

_bundle30 = OptionTradeMemoryInputBundle(target="NVDA", as_of="2026-05-26")
_snap30 = build_option_trade_plan_snapshot(
    target="NVDA", decision="option", strategy_type="long_call",
    entry_iv=0.55, max_loss=500.0, risk_level="medium", as_of="2026-05-26",
)

# Different plan snapshot
_snap30b = build_option_trade_plan_snapshot(
    target="NVDA", decision="option", strategy_type="long_put",
    entry_iv=0.45, max_loss=300.0, risk_level="low", as_of="2026-05-26",
)
rec30a = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Rec A.", plan_snapshot=_snap30, input_bundle=_bundle30
)
rec30b = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Rec B.", plan_snapshot=_snap30b, input_bundle=_bundle30
)
report30a = build_option_trade_memory_report(_bundle30, records=[rec30a])
report30b = build_option_trade_memory_report(_bundle30, records=[rec30b])
tr30a = option_trade_memory_tool_result_from_report(report30a)
tr30b = option_trade_memory_tool_result_from_report(report30b)
_check("30.1 different records → different evidence_id", tr30a.evidence_id != tr30b.evidence_id)

# Stable evidence_id
tr30a2 = option_trade_memory_tool_result_from_report(report30a)
_check("30.2 same report → stable evidence_id", tr30a.evidence_id == tr30a2.evidence_id)

# Different lesson → different evidence_id
rec30_lesson = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Rec A.", plan_snapshot=_snap30,
    lesson="Lesson added.", input_bundle=_bundle30,
)
report30_lesson = build_option_trade_memory_report(_bundle30, records=[rec30_lesson])
tr30_lesson = option_trade_memory_tool_result_from_report(report30_lesson)
_check("30.3 different lesson → different evidence_id", tr30a.evidence_id != tr30_lesson.evidence_id)

# Different source_refs → different evidence_id
rec30_src = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Rec A.", plan_snapshot=_snap30,
    source_refs=[OptionTradeMemorySourceRef(source_id="new_src")],
    input_bundle=_bundle30,
)
report30_src = build_option_trade_memory_report(_bundle30, records=[rec30_src])
tr30_src = option_trade_memory_tool_result_from_report(report30_src)
_check("30.4 different source_refs → different evidence_id", tr30a.evidence_id != tr30_src.evidence_id)

# Different event_log (different pnl) → different evidence_id
rec30_pnl = build_option_trade_memory_record(
    target="NVDA", decision="option", rationale="Rec A.", plan_snapshot=_snap30,
    outcome="profit", pnl_amount=500.0, pnl_pct=1.0, input_bundle=_bundle30,
)
report30_pnl = build_option_trade_memory_report(_bundle30, records=[rec30_pnl])
tr30_pnl = option_trade_memory_tool_result_from_report(report30_pnl)
_check("30.5 different pnl → different evidence_id", tr30a.evidence_id != tr30_pnl.evidence_id)


# ---------------------------------------------------------------------------
# Section 31: __all__ exports include Phase 4M-E public symbols
# ---------------------------------------------------------------------------

_section("31: __all__ exports include Phase 4M-E public symbols")

from lib.reliability.option_trade_memory import __all__ as _otm_all
from lib.reliability import __all__ as _pkg_all

_expected_module_symbols = [
    # Literal type aliases
    "OptionTradeDecision",
    "OptionTradeMemoryActorType",
    "OptionTradeMemoryEventType",
    "OptionTradeMemoryStatus",
    "OptionTradeOutcome",
    "OptionTradeReviewStatus",
    "OptionTradeRiskLevel",
    "OptionTradeStrategyType",
    # Models
    "OptionTradeMemoryInputBundle",
    "OptionTradeMemoryLogEntry",
    "OptionTradeMemoryReport",
    "OptionTradeMemorySourceRef",
    "OptionTradeMemorySummary",
    "OptionTradePlanMemoryRecord",
    "OptionTradePlanSnapshot",
    # Helpers
    "build_option_trade_memory_log_entry",
    "build_option_trade_memory_record",
    "build_option_trade_memory_report",
    "build_option_trade_plan_snapshot",
    "collect_option_trade_memory_artifact_refs",
    "collect_option_trade_memory_evidence_ids",
    "collect_option_trade_memory_source_ids",
    "determine_option_trade_memory_status",
    "make_option_trade_memory_log_entry_id",
    "make_option_trade_memory_record_id",
    "make_option_trade_memory_report_id",
    "option_trade_memory_tool_result_from_report",
    "summarize_option_trade_memory",
]

for _sym in _expected_module_symbols:
    _check(f"31.module {_sym} in option_trade_memory.__all__", _sym in _otm_all)

for _sym in _expected_module_symbols:
    _check(f"31.pkg {_sym} in reliability.__all__", _sym in _pkg_all)


# ---------------------------------------------------------------------------
# Section 32: no Streamlit / Claude API / external API / brokerage / DB dependency
# ---------------------------------------------------------------------------

_section("32: forbidden dependency checks")

_forbidden_live = [
    "streamlit",
    "anthropic",
    "requests",
    "httpx",
    "sqlalchemy",
    "psycopg2",
    "pymongo",
    "redis",
    "chromadb",
    "pinecone",
    "weaviate",
    "alpaca_trade_api",
    "ib_insync",
    "robin_stocks",
    "finnhub",
]
for _mod in _forbidden_live:
    _check(f"32.x {_mod} not in sys.modules", _mod not in sys.modules)

_check("32.y no 'import streamlit' in option_trade_memory", "import streamlit" not in _otm_src)
_check("32.z no 'import anthropic' in option_trade_memory", "import anthropic" not in _otm_src)
_check("32.aa no brokerage import in option_trade_memory", "import alpaca" not in _otm_src)
_check("32.ab no execution_id field in option_trade_memory", "execution_id" not in _otm_src)
_check("32.ac no order_id field in option_trade_memory", "order_id" not in _otm_src)
_check("32.ad no account_id field in option_trade_memory", "account_id" not in _otm_src)
_check("32.ae no live option-chain import in option_trade_memory", "option_chain_api" not in _otm_src)
_check("32.af no database write in option_trade_memory", "db.write" not in _otm_src and "session.add" not in _otm_src)
_check("32.ag no vector store in option_trade_memory", "chromadb" not in _otm_src and "pinecone" not in _otm_src)
_check("32.ah no file persistence in option_trade_memory",
       "open(" not in _otm_src.replace("open(_otm_module.__file__)", ""))


# ---------------------------------------------------------------------------
# Section 33: end-to-end round-trip
# ---------------------------------------------------------------------------

_section("33: end-to-end round-trip")

_bundle33 = OptionTradeMemoryInputBundle(
    target="NVDA",
    run_id="run_nvda_e2e",
    as_of="2026-05-26T09:30:00Z",
    source_ids=["sid_nvda_research"],
    evidence_ids=["eid_nvda_valuation"],
)

_snap33_lc = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    expiration="2026-07-18",
    entry_iv=0.55,
    entry_underlying_price=900.0,
    max_loss=500.0,
    max_gain=2500.0,
    breakeven=950.0,
    cash_required=500.0,
    risk_reward_ratio=5.0,
    contracts=1,
    planned_exit_rule="Exit at 50% max gain or 50% max loss.",
    risk_level="medium",
    as_of="2026-05-26",
)

rec33_profit = build_option_trade_memory_record(
    target="NVDA",
    decision="option",
    rationale="NVDA GPU cycle thesis. Strong momentum into earnings.",
    plan_snapshot=_snap33_lc,
    review_status="reviewed",
    outcome="profit",
    pnl_amount=1200.0,
    pnl_pct=2.40,
    lesson="Momentum trades in strong trends can yield outsized returns.",
    option_expression_report_id="oer_nvda_001",
    trade_plan_report_id="trep_nvda_001",
    decision_packet_id="dp_nvda_001",
    input_bundle=_bundle33,
)

_snap33_nt = build_option_trade_plan_snapshot(
    target="NVDA",
    decision="no_trade",
    strategy_type="no_trade",
    risk_level="undefined",
    as_of="2026-05-26",
)
rec33_nt = build_option_trade_memory_record(
    target="NVDA",
    decision="no_trade",
    rationale="IV too high. Skipping this cycle.",
    plan_snapshot=_snap33_nt,
    review_status="not_required",
    outcome="no_trade",
    input_bundle=_bundle33,
)

report33 = build_option_trade_memory_report(_bundle33, records=[rec33_profit, rec33_nt])

_check("33.1 e2e report builds OK", report33.target == "NVDA")
_check("33.2 e2e record_count = 2", report33.summary.record_count == 2)
_check("33.3 e2e reviewed_count = 1", report33.summary.reviewed_count == 1)
_check("33.4 e2e profit_count = 1", report33.summary.profit_count == 1)
_check("33.5 e2e no_trade_count = 1", report33.summary.no_trade_count == 1)
_check("33.6 e2e total_pnl_amount = 1200.0", abs(report33.summary.total_pnl_amount - 1200.0) < 1e-9)
_check("33.7 e2e decision_counts.option = 1", report33.summary.decision_counts.get("option") == 1)
_check("33.8 e2e decision_counts.no_trade = 1", report33.summary.decision_counts.get("no_trade") == 1)
_check("33.9 e2e strategy_counts.long_call = 1", report33.summary.strategy_counts.get("long_call") == 1)
_check("33.10 e2e max_loss_planned = 500.0", abs(report33.summary.max_loss_planned - 500.0) < 1e-9)
_check("33.11 e2e approved_for_execution False", report33.approved_for_execution is False)
_check("33.12 e2e source_ids from bundle included", "sid_nvda_research" in report33.source_ids)

tr33 = option_trade_memory_tool_result_from_report(report33)
_check("33.13 e2e ToolResult builds OK", tr33.tool_name == "option_trade_memory_report")
_check("33.14 e2e ToolResult evidence_id non-empty", bool(tr33.evidence_id))
_check("33.15 e2e ToolResult record_count = 2", tr33.outputs.get("record_count") == 2)
_check("33.16 e2e ToolResult approved_for_execution False", tr33.outputs.get("approved_for_execution") is False)

# Round-trip: report dict matches model
_report33_dict = report33.model_dump()
_check("33.17 model_dump target matches", _report33_dict["target"] == "NVDA")
_check("33.18 model_dump approved_for_execution False", _report33_dict["approved_for_execution"] is False)


# ---------------------------------------------------------------------------
# Section 34: planned_exit_rule-only snapshot sensitivity
# ---------------------------------------------------------------------------

_section("34: planned_exit_rule-only snapshot sensitivity")

_base34 = dict(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    entry_iv=0.50,
    exit_iv=0.30,
    entry_underlying_price=900.0,
    max_loss=500.0,
    max_gain=1500.0,
    breakeven=950.0,
    cash_required=500.0,
    risk_reward_ratio=3.0,
    contracts=1,
    risk_level="medium",
    as_of="2026-05-26",
)

_snap34a = build_option_trade_plan_snapshot(**_base34, planned_exit_rule="Exit at 50% max gain.")
_snap34b = build_option_trade_plan_snapshot(**_base34, planned_exit_rule="Exit at 75% max gain.")
_check("34.1 planned_exit_rule-only change → different snapshot_id", _snap34a.snapshot_id != _snap34b.snapshot_id)

_kwargs34 = dict(target="NVDA", outcome="pending", review_status="not_required", recorded_at="2026-05-26")
_rec34a = build_option_trade_memory_record(decision="option", rationale="Trade A.", plan_snapshot=_snap34a, **_kwargs34)
_rec34b = build_option_trade_memory_record(decision="option", rationale="Trade A.", plan_snapshot=_snap34b, **_kwargs34)
_check("34.2 planned_exit_rule-only change → different option_trade_memory_id",
       _rec34a.option_trade_memory_id != _rec34b.option_trade_memory_id)
_check("34.3 planned_exit_rule-only change → different first event_id",
       _rec34a.event_log[0].event_id != _rec34b.event_log[0].event_id)


# ---------------------------------------------------------------------------
# Section 35: actual_exit_reason-only snapshot sensitivity
# ---------------------------------------------------------------------------

_section("35: actual_exit_reason-only snapshot sensitivity")

_base35 = dict(
    target="NVDA",
    decision="option",
    strategy_type="long_call",
    entry_iv=0.50,
    max_loss=400.0,
    risk_level="medium",
    as_of="2026-05-26",
)

_snap35a = build_option_trade_plan_snapshot(**_base35, actual_exit_reason="Exited at 50% loss.")
_snap35b = build_option_trade_plan_snapshot(**_base35, actual_exit_reason="Exited at expiration.")
_check("35.1 actual_exit_reason-only change → different snapshot_id", _snap35a.snapshot_id != _snap35b.snapshot_id)

_kwargs35 = dict(target="NVDA", outcome="loss", review_status="reviewed", recorded_at="2026-05-26")
_rec35a = build_option_trade_memory_record(decision="option", rationale="Trade B.", plan_snapshot=_snap35a, **_kwargs35)
_rec35b = build_option_trade_memory_record(decision="option", rationale="Trade B.", plan_snapshot=_snap35b, **_kwargs35)
_check("35.2 actual_exit_reason-only change → different option_trade_memory_id",
       _rec35a.option_trade_memory_id != _rec35b.option_trade_memory_id)
_check("35.3 actual_exit_reason-only change → different first event_id",
       _rec35a.event_log[0].event_id != _rec35b.event_log[0].event_id)


# ---------------------------------------------------------------------------
# Section 36: other material field sensitivity
# ---------------------------------------------------------------------------

_section("36: other material field sensitivity")

_base36 = dict(
    target="AAPL",
    decision="option",
    strategy_type="call_debit_spread",
    entry_iv=0.40,
    exit_iv=0.25,
    entry_underlying_price=200.0,
    max_loss=150.0,
    max_gain=300.0,
    breakeven=205.0,
    cash_required=150.0,
    risk_reward_ratio=2.0,
    contracts=2,
    risk_level="medium",
    as_of="2026-05-26",
)

_snap36_base = build_option_trade_plan_snapshot(**_base36)

_snap36_exit_iv = build_option_trade_plan_snapshot(**{**_base36, "exit_iv": 0.15})
_check("36.1 exit_iv-only change → different snapshot_id", _snap36_base.snapshot_id != _snap36_exit_iv.snapshot_id)

_snap36_contracts = build_option_trade_plan_snapshot(**{**_base36, "contracts": 5})
_check("36.2 contracts-only change → different snapshot_id", _snap36_base.snapshot_id != _snap36_contracts.snapshot_id)

_snap36_breakeven = build_option_trade_plan_snapshot(**{**_base36, "breakeven": 210.0})
_check("36.3 breakeven-only change → different snapshot_id", _snap36_base.snapshot_id != _snap36_breakeven.snapshot_id)

_snap36_max_gain = build_option_trade_plan_snapshot(**{**_base36, "max_gain": 600.0})
_check("36.4 max_gain-only change → different snapshot_id", _snap36_base.snapshot_id != _snap36_max_gain.snapshot_id)

_snap36_cash = build_option_trade_plan_snapshot(**{**_base36, "cash_required": 300.0})
_check("36.5 cash_required-only change → different snapshot_id", _snap36_base.snapshot_id != _snap36_cash.snapshot_id)


# ---------------------------------------------------------------------------
# Section 37: snapshot and record ID stability
# ---------------------------------------------------------------------------

_section("37: snapshot and record ID stability")

_stab37 = dict(
    target="MSFT",
    decision="option",
    strategy_type="put_debit_spread",
    entry_iv=0.35,
    exit_iv=0.20,
    entry_underlying_price=400.0,
    max_loss=200.0,
    max_gain=500.0,
    breakeven=390.0,
    cash_required=200.0,
    risk_reward_ratio=2.5,
    contracts=3,
    planned_exit_rule="Exit at 60% max gain.",
    actual_exit_reason=None,
    risk_level="low",
    as_of="2026-05-26T10:00:00Z",
)

_snap37a = build_option_trade_plan_snapshot(**_stab37)
_snap37b = build_option_trade_plan_snapshot(**_stab37)
_check("37.1 identical snapshot inputs → identical snapshot_id", _snap37a.snapshot_id == _snap37b.snapshot_id)

_rec37a = build_option_trade_memory_record(
    target="MSFT", decision="option", rationale="Stable test.",
    plan_snapshot=_snap37a, review_status="not_required", outcome="pending",
    recorded_at="2026-05-26",
)
_rec37b = build_option_trade_memory_record(
    target="MSFT", decision="option", rationale="Stable test.",
    plan_snapshot=_snap37b, review_status="not_required", outcome="pending",
    recorded_at="2026-05-26",
)
_check("37.2 identical record inputs → identical option_trade_memory_id",
       _rec37a.option_trade_memory_id == _rec37b.option_trade_memory_id)
_check("37.3 identical record inputs → identical first event_id",
       _rec37a.event_log[0].event_id == _rec37b.event_log[0].event_id)


# ---------------------------------------------------------------------------
# Section 38: upstream artifact evidence_id collection
# ---------------------------------------------------------------------------

_section("38: upstream artifact evidence_id collection")

_mock_oer38 = types.SimpleNamespace(
    source_ids=["sid_oer38"],
    report_id="oer_038",
    evidence_id="eid_from_oer_038",
)
_mock_tpr38 = types.SimpleNamespace(
    source_ids=["sid_tpr38"],
    report_id="tpr_038",
    evidence_id="eid_from_tpr_038",
)
_mock_dp38 = types.SimpleNamespace(
    source_ids=["sid_dp38"],
    packet_id="dp_038",
    evidence_ids=["eid_from_dp_38a", "eid_from_dp_38b"],
)
_mock_rrm38 = types.SimpleNamespace(
    source_ids=["sid_rrm38"],
    memory_id="rrm_038",
    # intentionally no evidence_id or evidence_ids attribute
)

_bundle38 = OptionTradeMemoryInputBundle(
    target="NVDA",
    option_expression_report=_mock_oer38,
    trade_plan_report=_mock_tpr38,
    decision_packet=_mock_dp38,
    research_run_memory_record=_mock_rrm38,
    evidence_ids=["eid_direct_38"],
)

eids38 = collect_option_trade_memory_evidence_ids(_bundle38)

_check("38.1 direct evidence_id included", "eid_direct_38" in eids38)
_check("38.2 oer evidence_id attribute included", "eid_from_oer_038" in eids38)
_check("38.3 tpr evidence_id attribute included", "eid_from_tpr_038" in eids38)
_check("38.4 dp evidence_ids list item (a) included", "eid_from_dp_38a" in eids38)
_check("38.5 dp evidence_ids list item (b) included", "eid_from_dp_38b" in eids38)
_check("38.6 no duplicates in result", len(eids38) == len(set(eids38)))
_check("38.7 missing evidence_id on artifact does not crash and is not included as evidence",
       "rrm_038" not in eids38 and "sid_rrm38" not in eids38)

# Deduplication: artifact evidence_id same as direct evidence_id
_mock_dup38 = types.SimpleNamespace(evidence_id="eid_direct_38")
_bundle38_dup = OptionTradeMemoryInputBundle(
    target="NVDA",
    option_expression_report=_mock_dup38,
    evidence_ids=["eid_direct_38"],
)
eids38_dup = collect_option_trade_memory_evidence_ids(_bundle38_dup)
_check("38.8 duplicate evidence_id deduped deterministically", eids38_dup.count("eid_direct_38") == 1)


# ---------------------------------------------------------------------------
# Section 39: design doc existence
# ---------------------------------------------------------------------------

_section("39: design doc existence")

import os as _os
_doc_path_39 = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "docs",
    "reliability_phase_4m_option_trade_memory.md",
)
_check("39.1 docs/reliability_phase_4m_option_trade_memory.md exists", _os.path.isfile(_doc_path_39))


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"Phase 4M-E Option Trade Memory Tests: {_test_count} total, {_fail_count} failed")
if _fail_count == 0:
    print("ALL TESTS PASSED")
else:
    print(f"FAILURES: {_fail_count}")
print('='*60)

sys.exit(0 if _fail_count == 0 else 1)
