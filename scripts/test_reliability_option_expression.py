"""
scripts/test_reliability_option_expression.py

Phase 3R-D: Option Expression Agent v0.1 Non-live — comprehensive test suite.

Tests cover:
  1. Deterministic calculator functions
  2. Schema / model validation
  3. Report / helper functions
  4. ToolResult adapter
  5. Export smoke tests
  6. No forbidden dependency tests

All tests use offline/mock-only inputs. No live data, no Claude API, no brokers.

Run with:
    python scripts/test_reliability_option_expression.py
"""

from __future__ import annotations

# ── sys.path fix — must come before any lib imports ───────────────────────────
from pathlib import Path as _Path
import sys as _sys

_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))
# ─────────────────────────────────────────────────────────────────────────────

import sys
import types
import importlib
from typing import Any

# ---------------------------------------------------------------------------
# Test counter
# ---------------------------------------------------------------------------

_PASS = 0
_FAIL = 0
_ERRORS: list[str] = []


def _ok(label: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  PASS  {label}")


def _fail(label: str, reason: str) -> None:
    global _FAIL
    _FAIL += 1
    _ERRORS.append(f"{label}: {reason}")
    print(f"  FAIL  {label}: {reason}")


def assert_eq(label: str, actual: Any, expected: Any) -> None:
    if actual == expected:
        _ok(label)
    else:
        _fail(label, f"expected {expected!r}, got {actual!r}")


def assert_approx(label: str, actual: float, expected: float, tol: float = 1e-6) -> None:
    if abs(actual - expected) <= tol:
        _ok(label)
    else:
        _fail(label, f"expected ~{expected}, got {actual}")


def assert_true(label: str, cond: bool) -> None:
    if cond:
        _ok(label)
    else:
        _fail(label, "expected True")


def assert_false(label: str, cond: bool) -> None:
    if not cond:
        _ok(label)
    else:
        _fail(label, "expected False")


def assert_raises(label: str, exc_type: type, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
        _fail(label, f"expected {exc_type.__name__} but no exception raised")
    except exc_type:
        _ok(label)
    except Exception as e:
        _fail(label, f"expected {exc_type.__name__} but got {type(e).__name__}: {e}")


def assert_in(label: str, item: Any, container: Any) -> None:
    if item in container:
        _ok(label)
    else:
        _fail(label, f"{item!r} not found in container")


def assert_not_in(label: str, item: Any, container: Any) -> None:
    if item not in container:
        _ok(label)
    else:
        _fail(label, f"{item!r} unexpectedly found in container")


def assert_none(label: str, val: Any) -> None:
    if val is None:
        _ok(label)
    else:
        _fail(label, f"expected None, got {val!r}")


def assert_not_none(label: str, val: Any) -> None:
    if val is not None:
        _ok(label)
    else:
        _fail(label, "expected non-None value")


# ---------------------------------------------------------------------------
# Imports from the module under test
# ---------------------------------------------------------------------------

from lib.reliability.option_expression import (
    # Literal type aliases
    OptionExpressionStatus,
    OptionExpressionDecision,
    OptionExpressionStrategyType,
    OptionRiskLevel,
    OptionLiquidityLevel,
    OptionExpressionEventRiskLevel,
    OptionEvidenceQuality,
    OptionNoTradeReason,
    OptionLegType,
    OptionLegSide,
    # Models
    OptionExpressionLeg,
    OptionMarketSnapshot,
    OptionStrategyCalculation,
    OptionExpressionCandidate,
    OptionExpressionInputBundle,
    OptionExpressionAssessment,
    OptionExpressionSummary,
    OptionExpressionReport,
    # Calculators
    calculate_long_call_breakeven,
    calculate_long_put_breakeven,
    calculate_long_option_max_loss,
    calculate_call_debit_spread_max_loss,
    calculate_call_debit_spread_max_gain,
    calculate_put_debit_spread_breakeven,
    calculate_put_debit_spread_max_loss,
    calculate_cash_secured_put_cash_required,
    calculate_cash_secured_put_breakeven,
    calculate_covered_call_effective_sale_price,
    calculate_covered_call_upside_cap,
    calculate_risk_reward_ratio,
    # Helpers
    make_option_expression_report_id,
    determine_option_expression_status,
    collect_option_expression_source_ids,
    build_option_strategy_calculation,
    build_option_expression_report,
    summarize_option_expression_report,
    option_expression_tool_result_from_report,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_no_trade_candidate(
    candidate_id: str = "c_no_trade",
    ticker: str = "AAPL",
    no_trade_reason: str = "missing_required_inputs",
    evidence_quality: str = "adequate",
    source_ids: list[str] | None = None,
) -> OptionExpressionCandidate:
    return OptionExpressionCandidate(
        candidate_id=candidate_id,
        ticker=ticker,
        strategy_type="no_trade",
        no_trade_reason=no_trade_reason,
        evidence_quality=evidence_quality,
        rationale="No valid expression context.",
        source_ids=source_ids or ["ev_001"],
    )


def _make_long_call_leg(
    leg_id: str = "leg_long_call",
    strike: float = 150.0,
    premium: float = 5.0,
    contracts: int = 1,
) -> OptionExpressionLeg:
    return OptionExpressionLeg(
        leg_id=leg_id,
        option_type="call",
        position_side="long",
        strike=strike,
        premium=premium,
        contracts=contracts,
        source_ids=["ev_leg_001"],
    )


def _make_long_call_candidate(
    candidate_id: str = "c_long_call",
    ticker: str = "AAPL",
    evidence_quality: str = "adequate",
) -> OptionExpressionCandidate:
    leg = _make_long_call_leg()
    calc = build_option_strategy_calculation(
        strategy_type="long_call",
        legs=[leg],
        run_id="run_test",
        target=ticker,
    )
    return OptionExpressionCandidate(
        candidate_id=candidate_id,
        ticker=ticker,
        strategy_type="long_call",
        legs=[leg],
        calculation=calc,
        thesis_alignment="Bullish thesis aligned.",
        horizon_alignment="3-month horizon.",
        liquidity_level="good",
        event_risk_level="low",
        risk_level="medium",
        evidence_quality=evidence_quality,
        rationale="Long call to capture upside with defined risk.",
        exit_rule="Exit if stock drops below $140 or premium doubles.",
        source_ids=["ev_thesis_001", "ev_market_001"],
    )


def _make_market_snapshot(
    ticker: str = "AAPL",
    underlying_price: float = 155.0,
    liquidity_level: str = "good",
    event_risk_level: str = "low",
) -> OptionMarketSnapshot:
    return OptionMarketSnapshot(
        snapshot_id="snap_001",
        ticker=ticker,
        underlying_price=underlying_price,
        as_of="2026-05-24",
        implied_volatility=0.28,
        iv_rank=0.45,
        bid_ask_spread_pct=0.02,
        open_interest=5000,
        volume=2000,
        liquidity_level=liquidity_level,
        event_risk_level=event_risk_level,
        source_ids=["ev_market_001"],
    )


def _make_input_bundle(
    target: str = "AAPL",
    candidates: list[OptionExpressionCandidate] | None = None,
    market_snapshot: OptionMarketSnapshot | None = None,
    validated_thesis_reference: Any = None,
    trade_plan_report: Any = None,
    allocation_report: Any = None,
    human_review_report: Any = None,
    as_of: str = "2026-05-24",
) -> OptionExpressionInputBundle:
    return OptionExpressionInputBundle(
        target=target,
        run_id="run_test_001",
        as_of=as_of,
        market_snapshot=market_snapshot,
        validated_thesis_reference=validated_thesis_reference,
        trade_plan_report=trade_plan_report,
        allocation_report=allocation_report,
        human_review_report=human_review_report,
        candidate_strategies=candidates or [],
        source_ids=["ev_bundle_001"],
    )


class _MockThesis:
    """Minimal mock thesis reference."""
    thesis_id = "thesis_001"
    ticker = "AAPL"
    source_ids = ["ev_thesis_001"]


class _MockBlockedHumanReview:
    """Minimal mock human review report with blocked status."""
    status = "blocked"
    report_id = "hr_blocked_001"


class _MockApprovedHumanReview:
    """Minimal mock human review report with approved status."""
    status = "approved"
    report_id = "hr_approved_001"


# ===========================================================================
# SECTION 1: Calculator tests
# ===========================================================================

print("\n--- SECTION 1: Calculator Tests ---")


def test_long_call_breakeven_basic():
    result = calculate_long_call_breakeven(150.0, 5.0)
    assert_approx("long_call_breakeven basic", result, 155.0)


def test_long_call_breakeven_zero_premium():
    result = calculate_long_call_breakeven(100.0, 0.0)
    assert_approx("long_call_breakeven zero_premium", result, 100.0)


def test_long_put_breakeven_basic():
    result = calculate_long_put_breakeven(150.0, 5.0)
    assert_approx("long_put_breakeven basic", result, 145.0)


def test_long_put_breakeven_zero_premium():
    result = calculate_long_put_breakeven(100.0, 0.0)
    assert_approx("long_put_breakeven zero_premium", result, 100.0)


def test_long_option_max_loss_basic():
    result = calculate_long_option_max_loss(5.0, 2)
    assert_approx("long_option_max_loss basic (5 * 2 * 100 = 1000)", result, 1000.0)


def test_long_option_max_loss_one_contract():
    result = calculate_long_option_max_loss(3.5, 1)
    assert_approx("long_option_max_loss 1 contract (3.5 * 100 = 350)", result, 350.0)


def test_long_option_max_loss_zero_contracts():
    result = calculate_long_option_max_loss(5.0, 0)
    assert_approx("long_option_max_loss zero_contracts", result, 0.0)


def test_call_debit_spread_max_loss_basic():
    result = calculate_call_debit_spread_max_loss(3.0, 2)
    assert_approx("call_debit_spread_max_loss (3 * 2 * 100 = 600)", result, 600.0)


def test_call_debit_spread_max_gain_basic():
    # (110 - 100 - 3) * 2 * 100 = 7 * 2 * 100 = 1400
    result = calculate_call_debit_spread_max_gain(100.0, 110.0, 3.0, 2)
    assert_approx("call_debit_spread_max_gain (7 * 2 * 100 = 1400)", result, 1400.0)


def test_call_debit_spread_max_gain_net_debit_equals_width():
    # (105 - 100 - 5) * 1 * 100 = 0 → max_gain = 0
    result = calculate_call_debit_spread_max_gain(100.0, 105.0, 5.0, 1)
    assert_approx("call_debit_spread_max_gain zero_gain (spread_width == net_debit)", result, 0.0)


def test_put_debit_spread_breakeven_basic():
    result = calculate_put_debit_spread_breakeven(150.0, 3.0)
    assert_approx("put_debit_spread_breakeven (150 - 3 = 147)", result, 147.0)


def test_put_debit_spread_max_loss_basic():
    result = calculate_put_debit_spread_max_loss(3.0, 2)
    assert_approx("put_debit_spread_max_loss (3 * 2 * 100 = 600)", result, 600.0)


def test_cash_secured_put_cash_required_basic():
    result = calculate_cash_secured_put_cash_required(95.0, 1)
    assert_approx("cash_secured_put_cash_required (95 * 1 * 100 = 9500)", result, 9500.0)


def test_cash_secured_put_breakeven_basic():
    result = calculate_cash_secured_put_breakeven(95.0, 3.0)
    assert_approx("cash_secured_put_breakeven (95 - 3 = 92)", result, 92.0)


def test_covered_call_effective_sale_price_basic():
    result = calculate_covered_call_effective_sale_price(110.0, 3.0)
    assert_approx("covered_call_effective_sale_price (110 + 3 = 113)", result, 113.0)


def test_covered_call_upside_cap_basic():
    result = calculate_covered_call_upside_cap(110.0, 100.0, 3.0)
    assert_approx("covered_call_upside_cap (110 - 100 + 3 = 13)", result, 13.0)


def test_covered_call_upside_cap_zero_gain():
    result = calculate_covered_call_upside_cap(100.0, 103.0, 3.0)
    assert_approx("covered_call_upside_cap (100 - 103 + 3 = 0)", result, 0.0)


def test_covered_call_upside_cap_negative():
    # When cost_basis > strike + premium, upside_cap is negative
    result = calculate_covered_call_upside_cap(100.0, 110.0, 3.0)
    assert_approx("covered_call_upside_cap negative (100 - 110 + 3 = -7)", result, -7.0)


def test_risk_reward_ratio_basic():
    result = calculate_risk_reward_ratio(1400.0, 600.0)
    assert_not_none("risk_reward_ratio not None", result)
    assert_approx("risk_reward_ratio (1400/600 ≈ 2.333)", result, 1400.0 / 600.0)


def test_risk_reward_ratio_zero_max_loss():
    result = calculate_risk_reward_ratio(1000.0, 0.0)
    assert_none("risk_reward_ratio zero max_loss → None", result)


def test_risk_reward_ratio_none_max_gain():
    result = calculate_risk_reward_ratio(None, 500.0)
    assert_none("risk_reward_ratio None max_gain → None", result)


def test_risk_reward_ratio_none_max_loss():
    result = calculate_risk_reward_ratio(500.0, None)
    assert_none("risk_reward_ratio None max_loss → None", result)


def test_risk_reward_ratio_both_none():
    result = calculate_risk_reward_ratio(None, None)
    assert_none("risk_reward_ratio both None → None", result)


def test_calculator_invalid_negative_strike():
    assert_raises(
        "long_call_breakeven negative strike",
        ValueError,
        calculate_long_call_breakeven, -1.0, 5.0,
    )


def test_calculator_invalid_negative_premium():
    assert_raises(
        "long_put_breakeven negative premium",
        ValueError,
        calculate_long_put_breakeven, 100.0, -1.0,
    )


def test_calculator_invalid_negative_contracts():
    assert_raises(
        "long_option_max_loss negative contracts",
        ValueError,
        calculate_long_option_max_loss, 5.0, -1,
    )


def test_call_spread_short_strike_less_than_long():
    assert_raises(
        "call_debit_spread_max_gain short_strike < long_strike",
        ValueError,
        calculate_call_debit_spread_max_gain, 110.0, 100.0, 3.0, 1,
    )


def test_covered_call_upside_negative_cost_basis():
    assert_raises(
        "covered_call_upside_cap negative cost_basis",
        ValueError,
        calculate_covered_call_upside_cap, 110.0, -5.0, 3.0,
    )


def test_risk_reward_ratio_negative_max_gain():
    assert_raises(
        "risk_reward_ratio negative max_gain",
        ValueError,
        calculate_risk_reward_ratio, -100.0, 500.0,
    )


test_long_call_breakeven_basic()
test_long_call_breakeven_zero_premium()
test_long_put_breakeven_basic()
test_long_put_breakeven_zero_premium()
test_long_option_max_loss_basic()
test_long_option_max_loss_one_contract()
test_long_option_max_loss_zero_contracts()
test_call_debit_spread_max_loss_basic()
test_call_debit_spread_max_gain_basic()
test_call_debit_spread_max_gain_net_debit_equals_width()
test_put_debit_spread_breakeven_basic()
test_put_debit_spread_max_loss_basic()
test_cash_secured_put_cash_required_basic()
test_cash_secured_put_breakeven_basic()
test_covered_call_effective_sale_price_basic()
test_covered_call_upside_cap_basic()
test_covered_call_upside_cap_zero_gain()
test_covered_call_upside_cap_negative()
test_risk_reward_ratio_basic()
test_risk_reward_ratio_zero_max_loss()
test_risk_reward_ratio_none_max_gain()
test_risk_reward_ratio_none_max_loss()
test_risk_reward_ratio_both_none()
test_calculator_invalid_negative_strike()
test_calculator_invalid_negative_premium()
test_calculator_invalid_negative_contracts()
test_call_spread_short_strike_less_than_long()
test_covered_call_upside_negative_cost_basis()
test_risk_reward_ratio_negative_max_gain()


# ===========================================================================
# SECTION 2: Schema / Model Validation Tests
# ===========================================================================

print("\n--- SECTION 2: Schema/Model Tests ---")


def test_option_expression_leg_valid():
    leg = OptionExpressionLeg(
        leg_id="leg_001",
        option_type="call",
        position_side="long",
        strike=150.0,
        premium=5.0,
        contracts=2,
    )
    assert_eq("OptionExpressionLeg valid leg_id", leg.leg_id, "leg_001")
    assert_eq("OptionExpressionLeg valid option_type", leg.option_type, "call")
    assert_eq("OptionExpressionLeg approved_for_execution absent", hasattr(leg, "approved_for_execution"), False)


def test_option_expression_leg_invalid_strike():
    assert_raises(
        "OptionExpressionLeg negative strike",
        Exception,
        OptionExpressionLeg,
        leg_id="x", option_type="call", position_side="long", strike=-1.0, premium=5.0,
    )


def test_option_expression_leg_invalid_premium():
    assert_raises(
        "OptionExpressionLeg negative premium",
        Exception,
        OptionExpressionLeg,
        leg_id="x", option_type="put", position_side="long", strike=100.0, premium=-1.0,
    )


def test_option_expression_leg_invalid_contracts():
    assert_raises(
        "OptionExpressionLeg negative contracts",
        Exception,
        OptionExpressionLeg,
        leg_id="x", option_type="call", position_side="long", strike=100.0,
        premium=5.0, contracts=-1,
    )


def test_option_expression_leg_invalid_underlying_shares():
    assert_raises(
        "OptionExpressionLeg negative underlying_shares",
        Exception,
        OptionExpressionLeg,
        leg_id="x", option_type="stock", position_side="long", underlying_shares=-100.0,
    )


def test_option_expression_leg_whitespace_id():
    assert_raises(
        "OptionExpressionLeg whitespace leg_id",
        Exception,
        OptionExpressionLeg,
        leg_id="   ", option_type="call", position_side="long",
    )


def test_option_market_snapshot_valid():
    snap = _make_market_snapshot()
    assert_eq("OptionMarketSnapshot valid ticker", snap.ticker, "AAPL")
    assert_approx("OptionMarketSnapshot underlying_price", snap.underlying_price, 155.0)
    assert_eq("OptionMarketSnapshot liquidity_level", snap.liquidity_level, "good")


def test_option_market_snapshot_invalid_price():
    assert_raises(
        "OptionMarketSnapshot zero underlying_price",
        Exception,
        OptionMarketSnapshot,
        snapshot_id="s", ticker="AAPL", underlying_price=0.0,
    )


def test_option_market_snapshot_invalid_iv_rank():
    assert_raises(
        "OptionMarketSnapshot iv_rank > 1",
        Exception,
        OptionMarketSnapshot,
        snapshot_id="s", ticker="AAPL", underlying_price=100.0, iv_rank=1.5,
    )


def test_option_market_snapshot_invalid_negative_oi():
    assert_raises(
        "OptionMarketSnapshot negative open_interest",
        Exception,
        OptionMarketSnapshot,
        snapshot_id="s", ticker="AAPL", underlying_price=100.0, open_interest=-10,
    )


def test_option_strategy_calculation_valid():
    calc = OptionStrategyCalculation(
        calculation_id="calc_001",
        strategy_type="long_call",
        breakeven=155.0,
        max_loss=500.0,
        net_debit=500.0,
    )
    assert_eq("OptionStrategyCalculation valid strategy_type", calc.strategy_type, "long_call")
    assert_approx("OptionStrategyCalculation breakeven", calc.breakeven, 155.0)
    assert_approx("OptionStrategyCalculation max_loss", calc.max_loss, 500.0)


def test_option_strategy_calculation_no_order_fields():
    calc = OptionStrategyCalculation(
        calculation_id="calc_002",
        strategy_type="long_put",
        breakeven=145.0,
        max_loss=350.0,
    )
    assert_false(
        "OptionStrategyCalculation no order_id field",
        hasattr(calc, "order_id"),
    )
    assert_false(
        "OptionStrategyCalculation no account_id field",
        hasattr(calc, "account_id"),
    )
    assert_false(
        "OptionStrategyCalculation no execution_status field",
        hasattr(calc, "execution_status"),
    )


def test_option_expression_candidate_valid_no_trade():
    c = _make_no_trade_candidate()
    assert_eq("OptionExpressionCandidate no_trade strategy_type", c.strategy_type, "no_trade")
    assert_eq("OptionExpressionCandidate no_trade reason", c.no_trade_reason, "missing_required_inputs")
    assert_false("OptionExpressionCandidate approved_for_execution=False", c.approved_for_execution)


def test_option_expression_candidate_no_trade_requires_reason():
    assert_raises(
        "OptionExpressionCandidate no_trade without reason",
        Exception,
        OptionExpressionCandidate,
        candidate_id="x", ticker="AAPL", strategy_type="no_trade",
        # no_trade_reason is missing / None
    )


def test_option_expression_candidate_long_call_requires_legs():
    assert_raises(
        "OptionExpressionCandidate long_call without legs",
        Exception,
        OptionExpressionCandidate,
        candidate_id="x", ticker="AAPL", strategy_type="long_call",
        legs=[],  # empty legs not allowed for real strategy types
    )


def test_option_expression_candidate_approved_for_execution_rejected():
    assert_raises(
        "OptionExpressionCandidate approved_for_execution=True rejected",
        Exception,
        OptionExpressionCandidate,
        candidate_id="x", ticker="AAPL", strategy_type="no_trade",
        no_trade_reason="unknown", approved_for_execution=True,
    )


def test_option_expression_candidate_no_broker_fields():
    c = _make_no_trade_candidate()
    for field in ("order_id", "account_id", "broker_order", "execution_status"):
        assert_false(
            f"OptionExpressionCandidate no {field} field",
            hasattr(c, field),
        )


def test_option_expression_assessment_approved_for_execution_rejected():
    assert_raises(
        "OptionExpressionAssessment approved_for_execution=True rejected",
        Exception,
        OptionExpressionAssessment,
        assessment_id="x", ticker="AAPL", decision="no_trade",
        candidate_count=0, approved_for_execution=True,
    )


def test_option_expression_summary_approved_for_execution_rejected():
    assert_raises(
        "OptionExpressionSummary approved_for_execution=True rejected",
        Exception,
        OptionExpressionSummary,
        target="AAPL", status="complete", decision="no_trade",
        candidate_count=0, approved_for_execution=True,
    )


def test_option_expression_report_approved_for_execution_rejected():
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "run_001", created_at="2026-05-24")
    assert_raises(
        "OptionExpressionReport approved_for_execution=True rejected",
        Exception,
        OptionExpressionReport,
        report_id=report.report_id,
        target=report.target,
        run_id=report.run_id,
        status=report.status,
        input_bundle=report.input_bundle,
        assessment=report.assessment,
        summary=report.summary,
        created_at=report.created_at,
        approved_for_execution=True,
    )


def test_option_expression_report_no_broker_fields():
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "run_001", created_at="2026-05-24")
    for field in ("order_id", "account_id", "broker_order", "execution_status"):
        assert_false(
            f"OptionExpressionReport no {field} field",
            hasattr(report, field),
        )


test_option_expression_leg_valid()
test_option_expression_leg_invalid_strike()
test_option_expression_leg_invalid_premium()
test_option_expression_leg_invalid_contracts()
test_option_expression_leg_invalid_underlying_shares()
test_option_expression_leg_whitespace_id()
test_option_market_snapshot_valid()
test_option_market_snapshot_invalid_price()
test_option_market_snapshot_invalid_iv_rank()
test_option_market_snapshot_invalid_negative_oi()
test_option_strategy_calculation_valid()
test_option_strategy_calculation_no_order_fields()
test_option_expression_candidate_valid_no_trade()
test_option_expression_candidate_no_trade_requires_reason()
test_option_expression_candidate_long_call_requires_legs()
test_option_expression_candidate_approved_for_execution_rejected()
test_option_expression_candidate_no_broker_fields()
test_option_expression_assessment_approved_for_execution_rejected()
test_option_expression_summary_approved_for_execution_rejected()
test_option_expression_report_approved_for_execution_rejected()
test_option_expression_report_no_broker_fields()


# ===========================================================================
# SECTION 3: build_option_strategy_calculation Tests
# ===========================================================================

print("\n--- SECTION 3: Strategy Calculation Builder Tests ---")


def test_build_calc_long_call():
    leg = _make_long_call_leg(strike=150.0, premium=5.0, contracts=2)
    calc = build_option_strategy_calculation("long_call", [leg])
    assert_approx("long_call calc breakeven (155)", calc.breakeven, 155.0)
    assert_approx("long_call calc max_loss (1000)", calc.max_loss, 1000.0)
    assert_approx("long_call calc net_debit (1000)", calc.net_debit, 1000.0)
    assert_none("long_call calc risk_reward_ratio is None (unlimited)", calc.risk_reward_ratio)


def test_build_calc_long_put():
    leg = OptionExpressionLeg(
        leg_id="leg_lp", option_type="put", position_side="long",
        strike=150.0, premium=5.0, contracts=1,
    )
    calc = build_option_strategy_calculation("long_put", [leg])
    assert_approx("long_put calc breakeven (145)", calc.breakeven, 145.0)
    assert_approx("long_put calc max_loss (500)", calc.max_loss, 500.0)
    # max_gain = (150 - 5) * 1 * 100 = 14500
    assert_approx("long_put calc max_gain (14500)", calc.max_gain, 14500.0)
    assert_not_none("long_put calc risk_reward_ratio not None", calc.risk_reward_ratio)


def test_build_calc_call_debit_spread():
    long_leg = OptionExpressionLeg(
        leg_id="leg_long", option_type="call", position_side="long",
        strike=100.0, premium=5.0, contracts=2,
    )
    short_leg = OptionExpressionLeg(
        leg_id="leg_short", option_type="call", position_side="short",
        strike=110.0, premium=2.0, contracts=2,
    )
    calc = build_option_strategy_calculation("call_debit_spread", [long_leg, short_leg])
    # net_debit = 5 - 2 = 3; max_loss = 3 * 2 * 100 = 600
    assert_approx("call_debit_spread max_loss (600)", calc.max_loss, 600.0)
    # max_gain = (10 - 3) * 2 * 100 = 1400
    assert_approx("call_debit_spread max_gain (1400)", calc.max_gain, 1400.0)
    # breakeven = 100 + 3 = 103
    assert_approx("call_debit_spread breakeven (103)", calc.breakeven, 103.0)
    assert_not_none("call_debit_spread risk_reward_ratio", calc.risk_reward_ratio)


def test_build_calc_put_debit_spread():
    long_leg = OptionExpressionLeg(
        leg_id="leg_lp", option_type="put", position_side="long",
        strike=150.0, premium=5.0, contracts=1,
    )
    short_leg = OptionExpressionLeg(
        leg_id="leg_sp", option_type="put", position_side="short",
        strike=140.0, premium=2.0, contracts=1,
    )
    calc = build_option_strategy_calculation("put_debit_spread", [long_leg, short_leg])
    # net_debit = 5 - 2 = 3; breakeven = 150 - 3 = 147
    assert_approx("put_debit_spread breakeven (147)", calc.breakeven, 147.0)
    # max_loss = 3 * 1 * 100 = 300
    assert_approx("put_debit_spread max_loss (300)", calc.max_loss, 300.0)
    # max_gain = (10 - 3) * 1 * 100 = 700
    assert_approx("put_debit_spread max_gain (700)", calc.max_gain, 700.0)


def test_build_calc_cash_secured_put():
    short_put = OptionExpressionLeg(
        leg_id="leg_csp", option_type="put", position_side="short",
        strike=95.0, premium=3.0, contracts=1,
    )
    calc = build_option_strategy_calculation("cash_secured_put", [short_put])
    assert_approx("csp cash_required (9500)", calc.cash_required, 9500.0)
    assert_approx("csp breakeven (92)", calc.breakeven, 92.0)
    assert_approx("csp max_gain (300 = 3 * 100)", calc.max_gain, 300.0)


def test_build_calc_covered_call():
    short_call = OptionExpressionLeg(
        leg_id="leg_cc_call", option_type="call", position_side="short",
        strike=110.0, premium=3.0, contracts=2,
    )
    # stock leg with cost_basis as strike
    stock_leg = OptionExpressionLeg(
        leg_id="leg_cc_stock", option_type="stock", position_side="long",
        strike=100.0,  # cost_basis per share
        underlying_shares=200.0,
    )
    calc = build_option_strategy_calculation("covered_call", [stock_leg, short_call])
    assert_approx("covered_call effective_sale_price (113)", calc.effective_sale_price, 113.0)
    # upside_cap = 110 - 100 + 3 = 13
    assert_approx("covered_call upside_cap (13)", calc.upside_cap, 13.0)
    assert_not_none("covered_call net_credit", calc.net_credit)


def test_build_calc_no_trade():
    calc = build_option_strategy_calculation("no_trade", [])
    assert_eq("no_trade calc strategy_type", calc.strategy_type, "no_trade")
    assert_true("no_trade calc has warning", len(calc.warnings) > 0)
    assert_none("no_trade calc breakeven is None", calc.breakeven)


def test_build_calc_missing_leg_generates_warning():
    # long_call with no legs → warning
    calc = build_option_strategy_calculation("long_call", [])
    assert_true("missing leg generates warning", len(calc.warnings) > 0)


def test_build_calc_deterministic():
    leg = _make_long_call_leg()
    c1 = build_option_strategy_calculation("long_call", [leg], run_id="r1", target="AAPL")
    c2 = build_option_strategy_calculation("long_call", [leg], run_id="r1", target="AAPL")
    assert_eq("build_calc deterministic calculation_id", c1.calculation_id, c2.calculation_id)
    assert_eq("build_calc deterministic breakeven", c1.breakeven, c2.breakeven)


test_build_calc_long_call()
test_build_calc_long_put()
test_build_calc_call_debit_spread()
test_build_calc_put_debit_spread()
test_build_calc_cash_secured_put()
test_build_calc_covered_call()
test_build_calc_no_trade()
test_build_calc_missing_leg_generates_warning()
test_build_calc_deterministic()


# ===========================================================================
# SECTION 4: Report / Helper Tests
# ===========================================================================

print("\n--- SECTION 4: Report/Helper Tests ---")


def test_build_complete_report_no_trade():
    """Complete no_trade report with good context."""
    candidates = [_make_no_trade_candidate(no_trade_reason="missing_required_inputs")]
    bundle = _make_input_bundle(candidates=candidates, as_of="2026-05-24")
    report = build_option_expression_report(bundle, "run_001", created_at="2026-05-24")
    assert_eq("complete no_trade report target", report.target, "AAPL")
    assert_eq("complete no_trade decision", report.assessment.decision, "no_trade")
    assert_not_none("complete no_trade report_id", report.report_id)
    assert_false("complete no_trade approved_for_execution", report.approved_for_execution)
    assert_eq("complete no_trade assessment approved_for_execution", report.assessment.approved_for_execution, False)
    assert_eq("complete no_trade summary approved_for_execution", report.summary.approved_for_execution, False)


def test_build_complete_report_option_strategy():
    """Complete option strategy report with full context."""
    candidates = [_make_long_call_candidate(evidence_quality="adequate")]
    market = _make_market_snapshot(liquidity_level="good", event_risk_level="low")
    bundle = _make_input_bundle(
        candidates=candidates,
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_002", created_at="2026-05-24")
    assert_eq("option strategy decision", report.assessment.decision, "option")
    assert_eq("option strategy selected_strategy_type", report.summary.selected_strategy_type, "long_call")
    assert_false("option strategy approved_for_execution", report.approved_for_execution)


def test_deterministic_output_without_created_at():
    """Same inputs → same output when created_at is not provided."""
    candidates = [_make_no_trade_candidate()]
    bundle1 = _make_input_bundle(candidates=candidates, as_of="2026-05-24")
    bundle2 = _make_input_bundle(candidates=candidates, as_of="2026-05-24")
    r1 = build_option_expression_report(bundle1, "run_d1")
    r2 = build_option_expression_report(bundle2, "run_d1")
    assert_eq("deterministic report_id", r1.report_id, r2.report_id)
    assert_eq("deterministic assessment_id", r1.assessment.assessment_id, r2.assessment.assessment_id)
    assert_eq("deterministic status", r1.status, r2.status)
    assert_eq("deterministic decision", r1.assessment.decision, r2.assessment.decision)


def test_explicit_created_at_override():
    """Explicit created_at is used verbatim."""
    candidates = [_make_no_trade_candidate()]
    bundle = _make_input_bundle(candidates=candidates, as_of="2026-05-24")
    report = build_option_expression_report(bundle, "run_x", created_at="2099-01-01T00:00:00")
    assert_eq("explicit created_at", report.created_at, "2099-01-01T00:00:00")


def test_source_id_collection_deduplication():
    """Source IDs from multiple layers are deduplicated."""
    candidates = [_make_long_call_candidate()]
    market = _make_market_snapshot()
    bundle = _make_input_bundle(
        candidates=candidates,
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_sid", created_at="2026-05-24")
    # Check no duplicate source IDs
    assert_eq(
        "source_ids no duplicates",
        len(report.source_ids),
        len(set(report.source_ids)),
    )
    assert_true("source_ids non-empty", len(report.source_ids) > 0)


def test_missing_optional_artifacts_create_warnings():
    """Missing thesis/trade_plan/allocation/market_snapshot create warnings."""
    bundle = _make_input_bundle(
        candidates=[_make_no_trade_candidate()],
        # No market_snapshot, no thesis, no trade_plan, no allocation
    )
    report = build_option_expression_report(bundle, "run_warn", created_at="2026-05-24")
    # Should have warnings about missing artifacts
    warning_text = " ".join(report.warnings)
    assert_true("warning for missing market_snapshot", "market_snapshot" in warning_text)
    assert_true("warning for missing validated_thesis", "validated_thesis_reference" in warning_text)
    assert_true("warning for missing trade_plan_report", "trade_plan_report" in warning_text)
    assert_true("warning for missing allocation_report", "allocation_report" in warning_text)


def test_warnings_appear_in_summary_top_warnings():
    """Generated warnings propagate to summary.top_warnings."""
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "run_sw", created_at="2026-05-24")
    assert_true("top_warnings non-empty for missing artifacts", len(report.summary.top_warnings) > 0)


def test_no_trade_valid_and_complete():
    """no_trade decision with full context can resolve as 'complete'."""
    no_trade = _make_no_trade_candidate(
        no_trade_reason="event_risk_too_high",
        evidence_quality="strong",
    )
    market = _make_market_snapshot(liquidity_level="good", event_risk_level="low")
    bundle = _make_input_bundle(
        candidates=[no_trade],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_nt", created_at="2026-05-24")
    assert_eq("no_trade valid decision", report.assessment.decision, "no_trade")
    assert_eq("no_trade valid status", report.status, "complete")
    assert_false("no_trade approved_for_execution", report.approved_for_execution)


def test_no_trade_reason_preserved():
    """no_trade_reason from candidate propagates to assessment and summary."""
    no_trade = _make_no_trade_candidate(no_trade_reason="liquidity_too_poor")
    bundle = _make_input_bundle(
        candidates=[no_trade],
        market_snapshot=_make_market_snapshot(liquidity_level="good", event_risk_level="low"),
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_ntr", created_at="2026-05-24")
    assert_eq("no_trade_reason in assessment", report.assessment.no_trade_reason, "liquidity_too_poor")
    assert_eq("no_trade_reason in summary", report.summary.no_trade_reason, "liquidity_too_poor")


def test_poor_liquidity_causes_needs_review():
    """Poor liquidity causes needs_review status."""
    candidate = _make_long_call_candidate(evidence_quality="adequate")
    market = _make_market_snapshot(liquidity_level="poor", event_risk_level="low")
    bundle = _make_input_bundle(
        candidates=[candidate],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_pl", created_at="2026-05-24")
    assert_true(
        "poor liquidity → needs_review or no_trade",
        report.status in ("needs_review", "no_trade"),
    )
    assert_true(
        "poor liquidity → review_required",
        report.assessment.review_required,
    )


def test_high_event_risk_causes_needs_review():
    """High event risk causes needs_review status."""
    candidate = _make_long_call_candidate(evidence_quality="adequate")
    market = _make_market_snapshot(liquidity_level="good", event_risk_level="high")
    bundle = _make_input_bundle(
        candidates=[candidate],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_er", created_at="2026-05-24")
    assert_eq("high event risk → needs_review", report.status, "needs_review")
    assert_true("high event risk → review_required", report.assessment.review_required)


def test_missing_validated_thesis_discourages_option():
    """Missing validated thesis with option candidates → no_trade or needs_review."""
    candidate = _make_long_call_candidate(evidence_quality="adequate")
    no_trade = _make_no_trade_candidate(no_trade_reason="thesis_not_validated")
    bundle = _make_input_bundle(
        candidates=[candidate, no_trade],
        market_snapshot=_make_market_snapshot(),
        validated_thesis_reference=None,  # No thesis
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_nt_thesis", created_at="2026-05-24")
    assert_eq(
        "missing thesis with option candidate → no_trade decision",
        report.assessment.decision,
        "no_trade",
    )
    assert_eq(
        "missing thesis → thesis_not_validated reason",
        report.assessment.no_trade_reason,
        "thesis_not_validated",
    )


def test_missing_thesis_no_option_candidates():
    """Missing thesis, only no_trade candidates → no_trade decision."""
    no_trade = _make_no_trade_candidate(no_trade_reason="thesis_not_validated")
    bundle = _make_input_bundle(
        candidates=[no_trade],
        validated_thesis_reference=None,
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_nt2", created_at="2026-05-24")
    assert_eq("no thesis + no_trade only → no_trade", report.assessment.decision, "no_trade")


def test_human_review_blocked_causes_blocked():
    """Human review with blocked status → blocked report."""
    candidates = [_make_long_call_candidate(evidence_quality="adequate")]
    bundle = _make_input_bundle(
        candidates=candidates,
        market_snapshot=_make_market_snapshot(liquidity_level="good", event_risk_level="low"),
        validated_thesis_reference=_MockThesis(),
        human_review_report=_MockBlockedHumanReview(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_hrb", created_at="2026-05-24")
    assert_eq("human review blocked → blocked", report.status, "blocked")


def test_clean_adequate_option_strategy_can_complete():
    """Clean strategy with adequate evidence and full context → complete."""
    candidate = _make_long_call_candidate(evidence_quality="strong")
    market = _make_market_snapshot(liquidity_level="good", event_risk_level="low")
    bundle = _make_input_bundle(
        candidates=[candidate],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_clean", created_at="2026-05-24")
    assert_eq("clean strategy → complete", report.status, "complete")
    assert_eq("clean strategy → option decision", report.assessment.decision, "option")
    assert_false("clean strategy approved_for_execution", report.approved_for_execution)


def test_weak_evidence_causes_needs_review():
    """Weak evidence quality causes needs_review."""
    candidate = _make_long_call_candidate(evidence_quality="weak")
    market = _make_market_snapshot(liquidity_level="good", event_risk_level="low")
    bundle = _make_input_bundle(
        candidates=[candidate],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_weak", created_at="2026-05-24")
    assert_true(
        "weak evidence → needs_review",
        report.status in ("needs_review",),
    )


def test_empty_candidates_unknown_decision():
    """Empty candidate list → unknown decision."""
    bundle = _make_input_bundle(candidates=[], as_of="2026-05-24")
    report = build_option_expression_report(bundle, "run_empty", created_at="2026-05-24")
    assert_eq("empty candidates → unknown decision", report.assessment.decision, "unknown")
    assert_eq("empty candidates → unknown status", report.status, "unknown")


def test_inputs_not_mutated():
    """Build function does not mutate input bundle or candidates."""
    candidate = _make_long_call_candidate(evidence_quality="adequate")
    original_source_ids = list(candidate.source_ids)
    original_warnings = list(candidate.warnings)
    market = _make_market_snapshot()
    bundle = _make_input_bundle(
        candidates=[candidate],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    original_bundle_source_ids = list(bundle.source_ids)
    _ = build_option_expression_report(bundle, "run_mut", created_at="2026-05-24")
    assert_eq("candidate source_ids not mutated", candidate.source_ids, original_source_ids)
    assert_eq("candidate warnings not mutated", candidate.warnings, original_warnings)
    assert_eq("bundle source_ids not mutated", bundle.source_ids, original_bundle_source_ids)


def test_make_report_id_deterministic():
    """make_option_expression_report_id is deterministic."""
    id1 = make_option_expression_report_id("run_001", "AAPL", "2026-05-24")
    id2 = make_option_expression_report_id("run_001", "AAPL", "2026-05-24")
    assert_eq("report_id deterministic", id1, id2)
    assert_true("report_id starts with oer_", id1.startswith("oer_"))


def test_make_report_id_varies_by_input():
    """Different inputs → different report IDs."""
    id1 = make_option_expression_report_id("run_001", "AAPL", "2026-05-24")
    id2 = make_option_expression_report_id("run_001", "TSLA", "2026-05-24")
    assert_true("report_id varies by ticker", id1 != id2)


def test_determine_status_blocked_by_human_review():
    """Human review blocked → blocked status."""
    assessment = OptionExpressionAssessment(
        assessment_id="a1", ticker="AAPL", decision="option",
        candidate_count=1,
    )
    status = determine_option_expression_status(assessment, _MockBlockedHumanReview())
    assert_eq("status blocked by HR", status, "blocked")


def test_determine_status_complete_no_trade():
    """Clean no_trade assessment → complete status."""
    assessment = OptionExpressionAssessment(
        assessment_id="a2", ticker="AAPL", decision="no_trade",
        candidate_count=1, no_trade_reason="thesis_not_validated",
        review_required=False, risk_level="low",
    )
    status = determine_option_expression_status(assessment, None)
    assert_eq("status complete no_trade", status, "complete")


def test_determine_status_unknown():
    """Unknown decision → unknown status."""
    assessment = OptionExpressionAssessment(
        assessment_id="a3", ticker="AAPL", decision="unknown",
        candidate_count=0,
    )
    status = determine_option_expression_status(assessment, None)
    assert_eq("status unknown", status, "unknown")


def test_determine_status_needs_review_high_risk():
    """High risk level → needs_review."""
    assessment = OptionExpressionAssessment(
        assessment_id="a4", ticker="AAPL", decision="option",
        candidate_count=1, risk_level="high",
    )
    status = determine_option_expression_status(assessment, None)
    assert_eq("status needs_review for high risk", status, "needs_review")


def test_summarize_report():
    """summarize_option_expression_report returns correct keys."""
    candidate = _make_long_call_candidate(evidence_quality="strong")
    market = _make_market_snapshot(liquidity_level="good", event_risk_level="low")
    bundle = _make_input_bundle(
        candidates=[candidate],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_sum", created_at="2026-05-24")
    summary_dict = summarize_option_expression_report(report)
    for key in (
        "report_id", "target", "status", "decision", "selected_strategy_type",
        "candidate_count", "risk_level", "review_required", "warning_count",
        "source_id_count", "calculation_version", "approved_for_execution",
    ):
        assert_in(f"summarize_report has key '{key}'", key, summary_dict)
    assert_false("summarize_report approved_for_execution=False", summary_dict["approved_for_execution"])


def test_collect_source_ids_deduplication():
    """collect_option_expression_source_ids deduplicates across all layers."""
    candidate = _make_long_call_candidate()
    market = _make_market_snapshot()
    bundle = _make_input_bundle(
        candidates=[candidate],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_csi", created_at="2026-05-24")
    assert_eq(
        "source_ids no duplicates",
        len(report.source_ids),
        len(set(report.source_ids)),
    )


def test_status_precedence_blocked_over_needs_review():
    """blocked takes precedence over needs_review."""
    # High risk would normally be needs_review, but HR block overrides
    assessment = OptionExpressionAssessment(
        assessment_id="a5", ticker="AAPL", decision="option",
        candidate_count=1, risk_level="high", review_required=True,
    )
    status = determine_option_expression_status(assessment, _MockBlockedHumanReview())
    assert_eq("blocked > needs_review", status, "blocked")


def test_candidate_count_in_report():
    """candidate_count matches the number of candidates in the input bundle."""
    candidates = [
        _make_no_trade_candidate(candidate_id="c1", no_trade_reason="unknown"),
        _make_no_trade_candidate(candidate_id="c2", no_trade_reason="event_risk_too_high"),
    ]
    bundle = _make_input_bundle(candidates=candidates, as_of="2026-05-24")
    report = build_option_expression_report(bundle, "run_cnt", created_at="2026-05-24")
    assert_eq("candidate_count in report", report.assessment.candidate_count, 2)
    assert_eq("candidate_count in summary", report.summary.candidate_count, 2)


def test_calculation_version_in_report():
    """calculation_version matches the module constant."""
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "run_cv", created_at="2026-05-24")
    assert_eq("calculation_version", report.calculation_version, "option_expression_v1")


test_build_complete_report_no_trade()
test_build_complete_report_option_strategy()
test_deterministic_output_without_created_at()
test_explicit_created_at_override()
test_source_id_collection_deduplication()
test_missing_optional_artifacts_create_warnings()
test_warnings_appear_in_summary_top_warnings()
test_no_trade_valid_and_complete()
test_no_trade_reason_preserved()
test_poor_liquidity_causes_needs_review()
test_high_event_risk_causes_needs_review()
test_missing_validated_thesis_discourages_option()
test_missing_thesis_no_option_candidates()
test_human_review_blocked_causes_blocked()
test_clean_adequate_option_strategy_can_complete()
test_weak_evidence_causes_needs_review()
test_empty_candidates_unknown_decision()
test_inputs_not_mutated()
test_make_report_id_deterministic()
test_make_report_id_varies_by_input()
test_determine_status_blocked_by_human_review()
test_determine_status_complete_no_trade()
test_determine_status_unknown()
test_determine_status_needs_review_high_risk()
test_summarize_report()
test_collect_source_ids_deduplication()
test_status_precedence_blocked_over_needs_review()
test_candidate_count_in_report()
test_calculation_version_in_report()


# ===========================================================================
# SECTION 5: ToolResult adapter tests
# ===========================================================================

print("\n--- SECTION 5: ToolResult Adapter Tests ---")


def test_tool_result_stable_tool_name():
    """ToolResult uses the stable tool name 'option_expression_report'."""
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "run_tr", created_at="2026-05-24")
    tr = option_expression_tool_result_from_report("run_tr", report)
    assert_eq("ToolResult tool_name", tr.tool_name, "option_expression_report")


def test_tool_result_deterministic_evidence_id():
    """Same inputs → same evidence_id."""
    bundle1 = _make_input_bundle(candidates=[_make_no_trade_candidate()], as_of="2026-05-24")
    bundle2 = _make_input_bundle(candidates=[_make_no_trade_candidate()], as_of="2026-05-24")
    r1 = build_option_expression_report(bundle1, "run_tr2", created_at="2026-05-24")
    r2 = build_option_expression_report(bundle2, "run_tr2", created_at="2026-05-24")
    tr1 = option_expression_tool_result_from_report("run_tr2", r1)
    tr2 = option_expression_tool_result_from_report("run_tr2", r2)
    assert_eq("ToolResult deterministic evidence_id", tr1.evidence_id, tr2.evidence_id)


def test_tool_result_no_execution_implication():
    """ToolResult payload does not contain execution-implicating fields."""
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "run_tr3", created_at="2026-05-24")
    tr = option_expression_tool_result_from_report("run_tr3", report)
    summary = tr.outputs.get("summary", {})
    assert_false(
        "ToolResult summary approved_for_execution=False",
        summary.get("approved_for_execution", True),
    )


def test_tool_result_not_order_ticket():
    """ToolResult outputs do not look like an option order ticket."""
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "run_tr4", created_at="2026-05-24")
    tr = option_expression_tool_result_from_report("run_tr4", report)
    payload_str = str(tr.outputs)
    for forbidden in ("order_id", "broker_order", "account_id", "execution_status"):
        assert_not_in(f"ToolResult payload no '{forbidden}'", forbidden, payload_str)


def test_tool_result_custom_target():
    """Custom target overrides report.target in evidence_id."""
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()], as_of="2026-05-24")
    report = build_option_expression_report(bundle, "run_tr5", created_at="2026-05-24")
    tr = option_expression_tool_result_from_report("run_tr5", report, target="CUSTOM_TARGET")
    assert_in("ToolResult custom_target in evidence_id", "CUSTOM_TARGET", tr.evidence_id)


def test_tool_result_has_calculation_version():
    """ToolResult outputs include calculation_version."""
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "run_tr6", created_at="2026-05-24")
    tr = option_expression_tool_result_from_report("run_tr6", report)
    assert_in("ToolResult has calculation_version key", "calculation_version", tr.outputs)


test_tool_result_stable_tool_name()
test_tool_result_deterministic_evidence_id()
test_tool_result_no_execution_implication()
test_tool_result_not_order_ticket()
test_tool_result_custom_target()
test_tool_result_has_calculation_version()


# ===========================================================================
# SECTION 6: Export / Smoke Tests
# ===========================================================================

print("\n--- SECTION 6: Export / Smoke Tests ---")


def test_all_exports_in_all():
    """All Phase 3R-D public symbols are present in lib.reliability.__all__."""
    import lib.reliability as pkg
    all_names = set(pkg.__all__)
    expected = [
        "OptionExpressionStatus",
        "OptionExpressionDecision",
        "OptionExpressionStrategyType",
        "OptionRiskLevel",
        "OptionLiquidityLevel",
        "OptionExpressionEventRiskLevel",
        "OptionEvidenceQuality",
        "OptionNoTradeReason",
        "OptionLegType",
        "OptionLegSide",
        "OptionExpressionLeg",
        "OptionMarketSnapshot",
        "OptionStrategyCalculation",
        "OptionExpressionCandidate",
        "OptionExpressionInputBundle",
        "OptionExpressionAssessment",
        "OptionExpressionSummary",
        "OptionExpressionReport",
        "calculate_long_call_breakeven",
        "calculate_long_put_breakeven",
        "calculate_long_option_max_loss",
        "calculate_call_debit_spread_max_loss",
        "calculate_call_debit_spread_max_gain",
        "calculate_put_debit_spread_breakeven",
        "calculate_put_debit_spread_max_loss",
        "calculate_cash_secured_put_cash_required",
        "calculate_cash_secured_put_breakeven",
        "calculate_covered_call_effective_sale_price",
        "calculate_covered_call_upside_cap",
        "calculate_risk_reward_ratio",
        "make_option_expression_report_id",
        "determine_option_expression_status",
        "collect_option_expression_source_ids",
        "build_option_strategy_calculation",
        "build_option_expression_report",
        "summarize_option_expression_report",
        "option_expression_tool_result_from_report",
    ]
    for name in expected:
        assert_in(f"__all__ contains '{name}'", name, all_names)


def test_no_streamlit_dependency():
    """option_expression module does not import streamlit."""
    import lib.reliability.option_expression as mod
    src = mod.__file__
    with open(src) as f:
        content = f.read()
    # Check for actual import lines only, not docstring references
    assert_not_in("no 'import streamlit'", "import streamlit", content)
    assert_not_in("no 'from streamlit'", "from streamlit", content)


def test_no_claude_api_dependency():
    """option_expression module does not import anthropic or Claude API."""
    import lib.reliability.option_expression as mod
    src = mod.__file__
    with open(src) as f:
        content = f.read()
    assert_not_in("no anthropic import", "import anthropic", content)
    assert_not_in("no anthropic from-import", "from anthropic", content)


def test_no_broker_execution_dependency():
    """option_expression module does not import broker/brokerage modules."""
    import lib.reliability.option_expression as mod
    src = mod.__file__
    with open(src) as f:
        content = f.read()
    # Check for actual import statements, not docstring "we do not use X" clauses
    for term in ("import broker", "import brokerage", "import alpaca",
                 "import ibkr", "import tastytrade", "import ib_insync"):
        assert_not_in(f"no '{term}' import statement", term, content.lower())
    # Execution-function names that would indicate live trading
    assert_not_in("no place_order function", "place_order(", content)
    assert_not_in("no submit_order function", "submit_order(", content)
    assert_not_in("no execute_order function", "execute_order(", content)


def test_approved_for_execution_never_set_true():
    """The module never assigns approved_for_execution = True (only False)."""
    import lib.reliability.option_expression as mod
    src = mod.__file__
    with open(src) as f:
        content = f.read()
    # The only valid assignment is approved_for_execution=False or the
    # validator that rejects True. Look for any actual True assignment
    # (field default or keyword argument).
    # Note: docstrings/comments may mention =True in denial context; we
    # check for actual Python assignment patterns only.
    import re
    true_assignments = re.findall(r"approved_for_execution\s*=\s*True", content)
    # The validator tests 'if self.approved_for_execution:' — that is not an
    # assignment and is fine.  Any pattern matching '= True' would be a bug.
    assert_eq(
        "no approved_for_execution = True assignment in source",
        len(true_assignments),
        0,
    )


def test_module_importable_without_live_dependencies():
    """Module imports successfully with no live/external dependencies."""
    try:
        import lib.reliability.option_expression  # noqa: F401
        _ok("module imports without live dependencies")
    except ImportError as e:
        _fail("module imports without live dependencies", str(e))


def test_phase2e_symbols_not_overwritten_in_all():
    """Phase 2E option symbols remain accessible from lib.reliability.__all__."""
    import lib.reliability as pkg
    all_names = set(pkg.__all__)
    for sym in ("OptionStrategyType", "OptionLeg", "OptionStrategyCandidate", "OptionEventRiskLevel"):
        assert_in(f"Phase 2E symbol '{sym}' still in __all__", sym, all_names)


test_all_exports_in_all()
test_no_streamlit_dependency()
test_no_claude_api_dependency()
test_no_broker_execution_dependency()
test_approved_for_execution_never_set_true()
test_module_importable_without_live_dependencies()
test_phase2e_symbols_not_overwritten_in_all()


# ===========================================================================
# SECTION 7: Additional edge-case and boundary tests
# ===========================================================================

print("\n--- SECTION 7: Additional Edge Case Tests ---")


def test_call_debit_spread_max_gain_wide_spread():
    # (150 - 100 - 5) * 1 * 100 = 45 * 100 = 4500
    result = calculate_call_debit_spread_max_gain(100.0, 150.0, 5.0, 1)
    assert_approx("call_debit_spread wide spread max_gain (4500)", result, 4500.0)


def test_cash_secured_put_two_contracts():
    result = calculate_cash_secured_put_cash_required(90.0, 2)
    assert_approx("csp two contracts (90 * 2 * 100 = 18000)", result, 18000.0)


def test_long_option_max_loss_large_premium():
    result = calculate_long_option_max_loss(10.0, 5)
    assert_approx("long_option max_loss large (10 * 5 * 100 = 5000)", result, 5000.0)


def test_covered_call_no_stock_leg():
    """Covered call without stock leg → no upside_cap but effective_sale_price is set."""
    short_call = OptionExpressionLeg(
        leg_id="leg_cc_only", option_type="call", position_side="short",
        strike=110.0, premium=3.0, contracts=1,
    )
    calc = build_option_strategy_calculation("covered_call", [short_call])
    assert_approx("covered_call no_stock_leg effective_sale_price (113)", calc.effective_sale_price, 113.0)
    assert_none("covered_call no_stock_leg upside_cap is None", calc.upside_cap)


def test_put_debit_spread_same_strike():
    """Put debit spread with same strikes → zero spread_width → zero max_gain."""
    long_put = OptionExpressionLeg(
        leg_id="lp", option_type="put", position_side="long",
        strike=100.0, premium=3.0, contracts=1,
    )
    short_put = OptionExpressionLeg(
        leg_id="sp", option_type="put", position_side="short",
        strike=100.0, premium=1.0, contracts=1,
    )
    calc = build_option_strategy_calculation("put_debit_spread", [long_put, short_put])
    # spread_width = 0 → max_gain = max(0 - 2, 0) * 100 = 0
    assert_approx("put_debit_spread same_strike max_gain (0)", calc.max_gain, 0.0)


def test_input_bundle_no_candidates_warning():
    """Input bundle with empty candidates includes a warning."""
    bundle = _make_input_bundle(candidates=[])
    report = build_option_expression_report(bundle, "run_nc", created_at="2026-05-24")
    warning_text = " ".join(report.warnings)
    assert_true("empty candidates warning", "candidate_strategies" in warning_text)


def test_multiple_no_trade_candidates_selects_first():
    """When multiple no_trade candidates, selects the first one."""
    c1 = _make_no_trade_candidate(candidate_id="c1", no_trade_reason="liquidity_too_poor")
    c2 = _make_no_trade_candidate(candidate_id="c2", no_trade_reason="event_risk_too_high")
    bundle = _make_input_bundle(
        candidates=[c1, c2],
        validated_thesis_reference=_MockThesis(),
        market_snapshot=_make_market_snapshot(liquidity_level="poor"),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_multi_nt", created_at="2026-05-24")
    assert_eq("first no_trade selected", report.assessment.no_trade_reason, "liquidity_too_poor")


def test_assessment_has_candidate_count():
    """Assessment candidate_count reflects total candidates."""
    candidates = [
        _make_long_call_candidate(candidate_id="c1"),
        _make_no_trade_candidate(candidate_id="c2"),
    ]
    bundle = _make_input_bundle(
        candidates=candidates,
        validated_thesis_reference=_MockThesis(),
        market_snapshot=_make_market_snapshot(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_cnt2", created_at="2026-05-24")
    assert_eq("assessment candidate_count=2", report.assessment.candidate_count, 2)


def test_option_market_snapshot_no_optional_fields():
    """OptionMarketSnapshot with minimal required fields is valid."""
    snap = OptionMarketSnapshot(
        snapshot_id="min_snap",
        ticker="TSLA",
        underlying_price=200.0,
    )
    assert_eq("minimal snapshot ticker", snap.ticker, "TSLA")
    assert_eq("minimal snapshot liquidity_level default", snap.liquidity_level, "unknown")


def test_option_expression_candidate_unknown_strategy():
    """OptionExpressionCandidate with strategy_type='unknown' doesn't require legs."""
    c = OptionExpressionCandidate(
        candidate_id="c_unknown",
        ticker="AAPL",
        strategy_type="unknown",
        rationale="Undetermined strategy.",
    )
    assert_eq("unknown strategy type", c.strategy_type, "unknown")
    assert_eq("unknown strategy legs empty", c.legs, [])


def test_report_schema_version():
    """OptionExpressionReport has schema_version '1.0'."""
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "run_sv", created_at="2026-05-24")
    assert_eq("schema_version", report.schema_version, "1.0")


def test_report_run_id_preserved():
    """OptionExpressionReport.run_id matches the provided run_id."""
    bundle = _make_input_bundle(candidates=[_make_no_trade_candidate()])
    report = build_option_expression_report(bundle, "my_run_id_xyz", created_at="2026-05-24")
    assert_eq("run_id preserved", report.run_id, "my_run_id_xyz")


def test_call_debit_spread_missing_short_leg():
    """call_debit_spread with only a long leg → warning."""
    long_leg = OptionExpressionLeg(
        leg_id="lone_long", option_type="call", position_side="long",
        strike=100.0, premium=5.0, contracts=1,
    )
    calc = build_option_strategy_calculation("call_debit_spread", [long_leg])
    assert_true("call_debit_spread missing short → warning", len(calc.warnings) > 0)


def test_cash_secured_put_zero_premium():
    """Cash secured put with zero premium → breakeven == strike."""
    result = calculate_cash_secured_put_breakeven(95.0, 0.0)
    assert_approx("csp zero_premium breakeven == strike", result, 95.0)


def test_long_call_breakeven_large_values():
    result = calculate_long_call_breakeven(1000.0, 50.0)
    assert_approx("long_call large values breakeven (1050)", result, 1050.0)


test_call_debit_spread_max_gain_wide_spread()
test_cash_secured_put_two_contracts()
test_long_option_max_loss_large_premium()
test_covered_call_no_stock_leg()
test_put_debit_spread_same_strike()
test_input_bundle_no_candidates_warning()
test_multiple_no_trade_candidates_selects_first()
test_assessment_has_candidate_count()
test_option_market_snapshot_no_optional_fields()
test_option_expression_candidate_unknown_strategy()
test_report_schema_version()
test_report_run_id_preserved()
test_call_debit_spread_missing_short_leg()
test_cash_secured_put_zero_premium()
test_long_call_breakeven_large_values()


# ===========================================================================
# SECTION 8: Codex-required fix tests
#   Fix 1 — First-class stock expression path
#   Fix 2 — Status precedence: needs_review beats unknown
#   Fix 3 — no_trade_reason consistency in assessment and summary
# ===========================================================================

print("\n--- SECTION 8: Codex Required Fix Tests ---")


# ---- Fix 1: Stock expression path ----------------------------------------

def _make_stock_candidate(
    candidate_id: str = "c_stock",
    ticker: str = "AAPL",
    evidence_quality: str = "adequate",
) -> OptionExpressionCandidate:
    """Stock candidate — no option legs required."""
    return OptionExpressionCandidate(
        candidate_id=candidate_id,
        ticker=ticker,
        strategy_type="stock",
        legs=[],  # stock expression does not require option legs
        thesis_alignment="Bullish thesis — express via stock, not options.",
        horizon_alignment="3-month horizon.",
        liquidity_level="good",
        event_risk_level="low",
        risk_level="low",
        evidence_quality=evidence_quality,
        rationale="Stock expression chosen: express validated thesis via equity rather than options.",
        source_ids=["ev_thesis_001"],
    )


def test_stock_candidate_no_legs_required():
    """Stock candidate is valid without option legs."""
    c = _make_stock_candidate()
    assert_eq("stock candidate strategy_type", c.strategy_type, "stock")
    assert_eq("stock candidate legs empty", c.legs, [])
    assert_false("stock candidate approved_for_execution=False", c.approved_for_execution)


def test_stock_candidate_no_broker_fields():
    """Stock candidate has no broker/order/account/execution fields."""
    c = _make_stock_candidate()
    for field in ("order_id", "account_id", "broker_order", "execution_status"):
        assert_false(f"stock candidate no {field}", hasattr(c, field))


def test_stock_expression_builder_path():
    """Normal builder path can select a stock expression candidate."""
    stock = _make_stock_candidate(evidence_quality="adequate")
    market = _make_market_snapshot(liquidity_level="good", event_risk_level="low")
    bundle = _make_input_bundle(
        candidates=[stock],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_stock", created_at="2026-05-24")
    assert_eq("stock builder path decision", report.assessment.decision, "stock")
    assert_eq("stock builder path strategy_type", report.summary.selected_strategy_type, "stock")
    assert_eq("stock builder path summary decision", report.summary.decision, "stock")


def test_stock_expression_approved_for_execution_false():
    """Stock expression report always has approved_for_execution=False."""
    stock = _make_stock_candidate()
    bundle = _make_input_bundle(
        candidates=[stock],
        validated_thesis_reference=_MockThesis(),
        market_snapshot=_make_market_snapshot(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_stock_exec", created_at="2026-05-24")
    assert_false("stock report approved_for_execution", report.approved_for_execution)
    assert_false("stock assessment approved_for_execution", report.assessment.approved_for_execution)
    assert_false("stock summary approved_for_execution", report.summary.approved_for_execution)


def test_stock_expression_no_order_fields_in_payload():
    """Stock expression ToolResult payload has no broker/order/execution fields."""
    stock = _make_stock_candidate()
    bundle = _make_input_bundle(
        candidates=[stock],
        validated_thesis_reference=_MockThesis(),
        market_snapshot=_make_market_snapshot(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_stock_payload", created_at="2026-05-24")
    tr = option_expression_tool_result_from_report("run_stock_payload", report)
    payload_str = str(tr.outputs)
    for forbidden in ("order_id", "broker_order", "account_id", "execution_status"):
        assert_not_in(f"stock ToolResult payload no '{forbidden}'", forbidden, payload_str)


def test_stock_candidate_with_adequate_evidence_selected_over_weak_option():
    """Adequate stock candidate selected over weak option candidate."""
    weak_option = _make_long_call_candidate(candidate_id="c_weak_opt", evidence_quality="weak")
    adequate_stock = _make_stock_candidate(candidate_id="c_stock", evidence_quality="adequate")
    bundle = _make_input_bundle(
        candidates=[weak_option, adequate_stock],
        validated_thesis_reference=_MockThesis(),
        market_snapshot=_make_market_snapshot(liquidity_level="good", event_risk_level="low"),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_stock_vs_opt", created_at="2026-05-24")
    # adequate_stock should win because it's first adequate expression candidate
    assert_true(
        "adequate stock or option selected (adequate wins)",
        report.assessment.decision in ("stock", "option"),
    )
    assert_eq("adequate stock selected", report.assessment.decision, "stock")


def test_stock_strategy_type_in_literal():
    """'stock' is a valid OptionExpressionStrategyType value."""
    from lib.reliability.option_expression import OptionExpressionStrategyType
    from typing import get_args
    args = get_args(OptionExpressionStrategyType)
    assert_in("'stock' in OptionExpressionStrategyType", "stock", args)


def test_stock_decision_in_literal():
    """'stock' is a valid OptionExpressionDecision value."""
    from lib.reliability.option_expression import OptionExpressionDecision
    from typing import get_args
    args = get_args(OptionExpressionDecision)
    assert_in("'stock' in OptionExpressionDecision", "stock", args)


test_stock_candidate_no_legs_required()
test_stock_candidate_no_broker_fields()
test_stock_expression_builder_path()
test_stock_expression_approved_for_execution_false()
test_stock_expression_no_order_fields_in_payload()
test_stock_candidate_with_adequate_evidence_selected_over_weak_option()
test_stock_strategy_type_in_literal()
test_stock_decision_in_literal()


# ---- Fix 2: Status precedence — needs_review beats unknown ---------------

def test_status_unknown_plus_review_required_gives_needs_review():
    """unknown decision + review_required=True => needs_review."""
    assessment = OptionExpressionAssessment(
        assessment_id="fx2_a1", ticker="AAPL", decision="unknown",
        candidate_count=0, review_required=True,
    )
    status = determine_option_expression_status(assessment, None)
    assert_eq("unknown + review_required => needs_review", status, "needs_review")


def test_status_unknown_plus_high_risk_gives_needs_review():
    """unknown decision + risk_level=high => needs_review."""
    assessment = OptionExpressionAssessment(
        assessment_id="fx2_a2", ticker="AAPL", decision="unknown",
        candidate_count=0, risk_level="high",
    )
    status = determine_option_expression_status(assessment, None)
    assert_eq("unknown + high risk => needs_review", status, "needs_review")


def test_status_plain_unknown_no_flags_remains_unknown():
    """Plain unknown with no risk or review flags stays unknown."""
    assessment = OptionExpressionAssessment(
        assessment_id="fx2_a3", ticker="AAPL", decision="unknown",
        candidate_count=0, risk_level="unknown", review_required=False,
    )
    status = determine_option_expression_status(assessment, None)
    assert_eq("plain unknown with no flags stays unknown", status, "unknown")


def test_status_unknown_plus_review_plus_blocked_gives_blocked():
    """blocked overrides even unknown + review_required."""
    assessment = OptionExpressionAssessment(
        assessment_id="fx2_a4", ticker="AAPL", decision="unknown",
        candidate_count=0, review_required=True, risk_level="high",
    )
    status = determine_option_expression_status(assessment, _MockBlockedHumanReview())
    assert_eq("blocked overrides unknown+review", status, "blocked")


test_status_unknown_plus_review_required_gives_needs_review()
test_status_unknown_plus_high_risk_gives_needs_review()
test_status_plain_unknown_no_flags_remains_unknown()
test_status_unknown_plus_review_plus_blocked_gives_blocked()


# ---- Fix 3: no_trade_reason consistency in assessment and summary ---------

def test_assessment_no_trade_without_reason_fails():
    """Assessment with decision='no_trade' and no no_trade_reason fails validation."""
    assert_raises(
        "Assessment no_trade without reason fails",
        Exception,
        OptionExpressionAssessment,
        assessment_id="fx3_a1", ticker="AAPL", decision="no_trade",
        candidate_count=1, no_trade_reason=None,
    )


def test_summary_no_trade_without_reason_fails():
    """Summary with decision='no_trade' and no no_trade_reason fails validation."""
    assert_raises(
        "Summary no_trade without reason fails",
        Exception,
        OptionExpressionSummary,
        target="AAPL", status="complete", decision="no_trade",
        candidate_count=1, no_trade_reason=None,
    )


def test_report_no_trade_includes_reason_in_assessment_and_summary():
    """build_option_expression_report for no_trade includes reason in both assessment and summary."""
    no_trade = _make_no_trade_candidate(no_trade_reason="event_risk_too_high")
    market = _make_market_snapshot(liquidity_level="good", event_risk_level="low")
    bundle = _make_input_bundle(
        candidates=[no_trade],
        market_snapshot=market,
        validated_thesis_reference=_MockThesis(),
        as_of="2026-05-24",
    )
    report = build_option_expression_report(bundle, "run_fx3", created_at="2026-05-24")
    assert_eq("report no_trade assessment has reason", report.assessment.no_trade_reason, "event_risk_too_high")
    assert_eq("report no_trade summary has reason", report.summary.no_trade_reason, "event_risk_too_high")


def test_assessment_no_trade_with_reason_valid():
    """Assessment with decision='no_trade' and valid no_trade_reason is accepted."""
    a = OptionExpressionAssessment(
        assessment_id="fx3_a3", ticker="AAPL", decision="no_trade",
        candidate_count=1, no_trade_reason="thesis_not_validated",
    )
    assert_eq("assessment no_trade with reason valid", a.no_trade_reason, "thesis_not_validated")


def test_summary_no_trade_with_reason_valid():
    """Summary with decision='no_trade' and valid no_trade_reason is accepted."""
    s = OptionExpressionSummary(
        target="AAPL", status="complete", decision="no_trade",
        candidate_count=1, no_trade_reason="thesis_not_validated",
    )
    assert_eq("summary no_trade with reason valid", s.no_trade_reason, "thesis_not_validated")


def test_candidate_no_trade_reason_still_required():
    """Candidate-level no_trade_reason requirement is preserved."""
    assert_raises(
        "Candidate no_trade without reason still fails",
        Exception,
        OptionExpressionCandidate,
        candidate_id="x", ticker="AAPL", strategy_type="no_trade",
    )


test_assessment_no_trade_without_reason_fails()
test_summary_no_trade_without_reason_fails()
test_report_no_trade_includes_reason_in_assessment_and_summary()
test_assessment_no_trade_with_reason_valid()
test_summary_no_trade_with_reason_valid()
test_candidate_no_trade_reason_still_required()


# ===========================================================================
# Final report
# ===========================================================================

print(f"\n{'='*60}")
print(f"Phase 3R-D: Option Expression Agent — Test Results")
print(f"  PASSED: {_PASS}")
print(f"  FAILED: {_FAIL}")
print(f"  TOTAL:  {_PASS + _FAIL}")
if _ERRORS:
    print("\nFailed tests:")
    for e in _ERRORS:
        print(f"  - {e}")
print('='*60)

sys.exit(0 if _FAIL == 0 else 1)
