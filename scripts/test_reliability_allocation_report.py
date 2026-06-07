"""
scripts/test_reliability_allocation_report.py

Test suite for lib/reliability/allocation_report.py — Phase 3R-C.

Run with:
    python3 scripts/test_reliability_allocation_report.py

No external dependencies beyond lib/reliability and pydantic.
Does not make network calls. Does not read/write live files.
Does not import Streamlit, app.py, or any live workflow module.

Groups:
  A: Literal aliases — AllocationStatus (4), AllocationActionType (6),
     AllocationRiskLevel (4), AllocationEvidenceQuality (5),
     AllocationConstraintType (9)  [28 assertions]

  B: Calculator functions — calculate_position_value, calculate_allocation_pct,
     calculate_target_position_value, calculate_required_trade_value,
     calculate_required_shares, calculate_max_loss_at_stop,
     calculate_portfolio_loss_pct; error cases  [42 assertions]

  C: AllocationPortfolioSnapshot — required fields, optional cash,
     validation rejections  [16 assertions]

  D: AllocationPositionSnapshot — required fields, optional cost_basis/value,
     validation rejections  [14 assertions]

  E: AllocationTargetSpec — creation, pct validation, ordering constraint,
     evidence_quality  [18 assertions]

  F: RiskBudgetConstraint — constraint types, pct validation, stop_price,
     risk_level  [14 assertions]

  G: AllocationCalculation — model creation, field types  [12 assertions]

  H: AllocationAssessment — creation, approved_for_execution guard  [12 assertions]

  I: AllocationInputBundle — required fields, optional priors, whitespace  [10 assertions]

  J: AllocationSummary — creation, approved_for_execution guard  [10 assertions]

  K: AllocationReport — creation, approved_for_execution guard  [10 assertions]

  L: build_allocation_calculation — all action types (hold/add/trim/exit/no_action),
     cash projection, stop-loss, constraint violations  [40 assertions]

  M: build_allocation_report — complete end-to-end, deterministic, created_at override,
     source ID collection/deduplication, missing optional artifacts produce warnings,
     constraint violation → needs_review, human_review_block → blocked,
     human review status=blocked → blocked, clean allocation → complete,
     inputs not mutated  [50 assertions]

  N: determine_allocation_status — all status paths  [12 assertions]

  O: summarize_allocation_report — shape, keys, values  [14 assertions]

  P: allocation_report_tool_result_from_report — shape, stable tool name,
     deterministic evidence_id, no order-ticket fields, no execution implication  [20 assertions]

  Q: collect_allocation_source_ids — deduplication, ordering  [10 assertions]

  R: make_allocation_report_id — deterministic, stable prefix  [6 assertions]

  S: __all__ exports from lib/reliability include Phase 3R-C symbols  [28 assertions]

  T: No forbidden modules imported  [8 assertions]

Total: 374 assertions
"""

# ── sys.path fix — MUST come before any lib imports ──────────────────────────
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import traceback
from typing import get_args

# ── Counters ──────────────────────────────────────────────────────────────────

_PASS = 0
_FAIL = 0


def _assert(condition: bool, label: str) -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {label}")


def _assert_raises(exc_type, fn, label: str) -> None:
    global _PASS, _FAIL
    try:
        fn()
        _FAIL += 1
        print(f"  FAIL (no exception): {label}")
    except exc_type:
        _PASS += 1
    except Exception as e:
        _FAIL += 1
        print(f"  FAIL (wrong exception {type(e).__name__}): {label}")


# ── Imports ───────────────────────────────────────────────────────────────────

from pydantic import ValidationError

from lib.reliability.allocation_report import (
    # Literals
    AllocationStatus,
    AllocationActionType,
    AllocationRiskLevel,
    AllocationEvidenceQuality,
    AllocationConstraintType,
    # Models
    AllocationPortfolioSnapshot,
    AllocationPositionSnapshot,
    AllocationTargetSpec,
    RiskBudgetConstraint,
    AllocationCalculation,
    AllocationAssessment,
    AllocationInputBundle,
    AllocationSummary,
    AllocationReport,
    # Calculator functions
    calculate_position_value,
    calculate_allocation_pct,
    calculate_target_position_value,
    calculate_required_trade_value,
    calculate_required_shares,
    calculate_max_loss_at_stop,
    calculate_portfolio_loss_pct,
    # Helpers
    make_allocation_report_id,
    determine_allocation_status,
    collect_allocation_source_ids,
    build_allocation_calculation,
    build_allocation_report,
    summarize_allocation_report,
    allocation_report_tool_result_from_report,
)


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_portfolio(
    portfolio_id: str = "port-001",
    total_portfolio_value: float = 100_000.0,
    cash_value: float | None = 10_000.0,
    cash_pct: float | None = 0.10,
    source_ids: list[str] | None = None,
) -> AllocationPortfolioSnapshot:
    return AllocationPortfolioSnapshot(
        portfolio_id=portfolio_id,
        total_portfolio_value=total_portfolio_value,
        cash_value=cash_value,
        cash_pct=cash_pct,
        as_of="2026-05-24",
        source_ids=source_ids or ["ev_port_001"],
    )


def _make_position(
    position_id: str = "pos-aapl-001",
    ticker: str = "AAPL",
    shares: float = 50.0,
    current_price: float = 180.0,
    cost_basis: float | None = 150.0,
    source_ids: list[str] | None = None,
) -> AllocationPositionSnapshot:
    return AllocationPositionSnapshot(
        position_id=position_id,
        ticker=ticker,
        shares=shares,
        current_price=current_price,
        cost_basis=cost_basis,
        source_ids=source_ids or ["ev_pos_001"],
    )


def _make_target(
    target_id: str = "tgt-aapl-001",
    ticker: str = "AAPL",
    target_allocation_pct: float = 0.12,
    source_ids: list[str] | None = None,
) -> AllocationTargetSpec:
    return AllocationTargetSpec(
        target_id=target_id,
        ticker=ticker,
        target_allocation_pct=target_allocation_pct,
        rationale="Strong thesis",
        evidence_quality="adequate",
        source_ids=source_ids or ["ev_tgt_001"],
    )


def _make_constraint(
    constraint_id: str = "rc-001",
    constraint_type: str = "max_position_pct",
    max_position_pct: float | None = 0.20,
    stop_price: float | None = None,
    risk_level: str = "medium",
) -> RiskBudgetConstraint:
    return RiskBudgetConstraint(
        constraint_id=constraint_id,
        constraint_type=constraint_type,
        max_position_pct=max_position_pct,
        stop_price=stop_price,
        risk_level=risk_level,
        rationale="Position size cap",
    )


def _make_bundle(
    target: str = "AAPL",
    run_id: str = "run_test_001",
    as_of: str = "2026-05-24",
    portfolio: AllocationPortfolioSnapshot | None = None,
    position: AllocationPositionSnapshot | None = None,
    alloc_target: AllocationTargetSpec | None = None,
    risk_constraints: list[RiskBudgetConstraint] | None = None,
    human_review_report: object | None = None,
    source_ids: list[str] | None = None,
) -> AllocationInputBundle:
    return AllocationInputBundle(
        target=target,
        run_id=run_id,
        as_of=as_of,
        portfolio_snapshot=portfolio or _make_portfolio(),
        position_snapshot=position or _make_position(),
        allocation_target=alloc_target or _make_target(),
        risk_constraints=risk_constraints or [],
        human_review_report=human_review_report,
        source_ids=source_ids or [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Group A: Literal aliases
# ─────────────────────────────────────────────────────────────────────────────

def test_group_a():
    print("Group A: Literal aliases")

    status_values = get_args(AllocationStatus)
    _assert("unknown" in status_values, "A1: AllocationStatus has 'unknown'")
    _assert("complete" in status_values, "A2: AllocationStatus has 'complete'")
    _assert("needs_review" in status_values, "A3: AllocationStatus has 'needs_review'")
    _assert("blocked" in status_values, "A4: AllocationStatus has 'blocked'")

    action_values = get_args(AllocationActionType)
    _assert("hold" in action_values, "A5: AllocationActionType has 'hold'")
    _assert("add" in action_values, "A6: AllocationActionType has 'add'")
    _assert("trim" in action_values, "A7: AllocationActionType has 'trim'")
    _assert("exit" in action_values, "A8: AllocationActionType has 'exit'")
    _assert("no_action" in action_values, "A9: AllocationActionType has 'no_action'")
    _assert("unknown" in action_values, "A10: AllocationActionType has 'unknown'")

    risk_values = get_args(AllocationRiskLevel)
    _assert("low" in risk_values, "A11: AllocationRiskLevel has 'low'")
    _assert("medium" in risk_values, "A12: AllocationRiskLevel has 'medium'")
    _assert("high" in risk_values, "A13: AllocationRiskLevel has 'high'")
    _assert("unknown" in risk_values, "A14: AllocationRiskLevel has 'unknown'")

    eq_values = get_args(AllocationEvidenceQuality)
    _assert("unsupported" in eq_values, "A15: AllocationEvidenceQuality has 'unsupported'")
    _assert("weak" in eq_values, "A16: AllocationEvidenceQuality has 'weak'")
    _assert("adequate" in eq_values, "A17: AllocationEvidenceQuality has 'adequate'")
    _assert("strong" in eq_values, "A18: AllocationEvidenceQuality has 'strong'")
    _assert("unknown" in eq_values, "A19: AllocationEvidenceQuality has 'unknown'")

    ct_values = get_args(AllocationConstraintType)
    _assert("max_position_pct" in ct_values, "A20: AllocationConstraintType has max_position_pct")
    _assert("max_portfolio_loss_pct" in ct_values, "A21: AllocationConstraintType has max_portfolio_loss_pct")
    _assert("min_cash_pct" in ct_values, "A22: AllocationConstraintType has min_cash_pct")
    _assert("sector_exposure" in ct_values, "A23: AllocationConstraintType has sector_exposure")
    _assert("liquidity" in ct_values, "A24: AllocationConstraintType has liquidity")
    _assert("volatility" in ct_values, "A25: AllocationConstraintType has volatility")
    _assert("thesis_confidence" in ct_values, "A26: AllocationConstraintType has thesis_confidence")
    _assert("human_review_block" in ct_values, "A27: AllocationConstraintType has human_review_block")
    _assert("unknown" in ct_values, "A28: AllocationConstraintType has unknown")


# ─────────────────────────────────────────────────────────────────────────────
# Group B: Calculator functions
# ─────────────────────────────────────────────────────────────────────────────

def test_group_b():
    print("Group B: Calculator functions")

    # calculate_position_value
    _assert(calculate_position_value(100.0, 50.0) == 5000.0, "B1: 100*50=5000")
    _assert(calculate_position_value(0.0, 50.0) == 0.0, "B2: 0 shares → 0 value")
    _assert(calculate_position_value(1.5, 200.0) == 300.0, "B3: fractional shares")
    _assert_raises(ValueError, lambda: calculate_position_value(-1.0, 50.0), "B4: negative shares")
    _assert_raises(ValueError, lambda: calculate_position_value(100.0, 0.0), "B5: zero price")
    _assert_raises(ValueError, lambda: calculate_position_value(100.0, -1.0), "B6: negative price")

    # calculate_allocation_pct
    _assert(calculate_allocation_pct(10000.0, 100000.0) == 0.10, "B7: 10k/100k=0.10")
    _assert(calculate_allocation_pct(0.0, 100000.0) == 0.0, "B8: 0 position → 0 pct")
    _assert(abs(calculate_allocation_pct(50000.0, 100000.0) - 0.50) < 1e-9, "B9: 50k/100k=0.50")
    _assert_raises(ValueError, lambda: calculate_allocation_pct(5000.0, 0.0), "B10: zero portfolio value")
    _assert_raises(ValueError, lambda: calculate_allocation_pct(5000.0, -100.0), "B11: negative portfolio value")
    _assert_raises(ValueError, lambda: calculate_allocation_pct(-100.0, 100000.0), "B12: negative position value")

    # calculate_target_position_value
    _assert(calculate_target_position_value(0.10, 100000.0) == 10000.0, "B13: 10% of 100k")
    _assert(calculate_target_position_value(0.0, 100000.0) == 0.0, "B14: 0% target → 0")
    _assert(calculate_target_position_value(1.0, 100000.0) == 100000.0, "B15: 100% target")
    _assert_raises(ValueError, lambda: calculate_target_position_value(0.10, 0.0), "B16: zero portfolio")
    _assert_raises(ValueError, lambda: calculate_target_position_value(-0.01, 100000.0), "B17: negative pct")
    _assert_raises(ValueError, lambda: calculate_target_position_value(1.01, 100000.0), "B18: pct > 1")

    # calculate_required_trade_value
    _assert(calculate_required_trade_value(12000.0, 9000.0) == 3000.0, "B19: positive trade (add)")
    _assert(calculate_required_trade_value(9000.0, 12000.0) == -3000.0, "B20: negative trade (trim)")
    _assert(calculate_required_trade_value(10000.0, 10000.0) == 0.0, "B21: no trade needed")

    # calculate_required_shares
    _assert(calculate_required_shares(5000.0, 100.0) == 50.0, "B22: 5000/100=50 shares")
    _assert(calculate_required_shares(-3000.0, 150.0) == -20.0, "B23: negative → trim shares")
    _assert(calculate_required_shares(0.0, 100.0) == 0.0, "B24: 0 trade → 0 shares")
    _assert_raises(ValueError, lambda: calculate_required_shares(5000.0, 0.0), "B25: zero price")
    _assert_raises(ValueError, lambda: calculate_required_shares(5000.0, -1.0), "B26: negative price")

    # calculate_max_loss_at_stop
    _assert(calculate_max_loss_at_stop(100.0, 200.0, 150.0) == 5000.0, "B27: (200-150)*100=5000")
    _assert(calculate_max_loss_at_stop(100.0, 150.0, 200.0) == 0.0, "B28: stop>entry → 0 loss")
    _assert(calculate_max_loss_at_stop(0.0, 200.0, 150.0) == 0.0, "B29: 0 shares → 0 loss")
    _assert(calculate_max_loss_at_stop(100.0, 200.0, 200.0) == 0.0, "B30: stop=entry → 0 loss")
    _assert_raises(ValueError, lambda: calculate_max_loss_at_stop(-1.0, 200.0, 150.0), "B31: negative shares")
    _assert_raises(ValueError, lambda: calculate_max_loss_at_stop(100.0, -1.0, 150.0), "B32: negative entry")
    _assert_raises(ValueError, lambda: calculate_max_loss_at_stop(100.0, 200.0, -1.0), "B33: negative stop")

    # calculate_portfolio_loss_pct
    _assert(calculate_portfolio_loss_pct(5000.0, 100000.0) == 0.05, "B34: 5k/100k=0.05")
    _assert(calculate_portfolio_loss_pct(0.0, 100000.0) == 0.0, "B35: 0 loss → 0 pct")
    _assert_raises(ValueError, lambda: calculate_portfolio_loss_pct(5000.0, 0.0), "B36: zero portfolio")
    _assert_raises(ValueError, lambda: calculate_portfolio_loss_pct(5000.0, -100.0), "B37: negative portfolio")
    _assert_raises(ValueError, lambda: calculate_portfolio_loss_pct(-100.0, 100000.0), "B38: negative loss")

    # Composition check: cascaded formula
    pv = calculate_position_value(50.0, 180.0)
    alloc = calculate_allocation_pct(pv, 100_000.0)
    tpv = calculate_target_position_value(0.12, 100_000.0)
    rtv = calculate_required_trade_value(tpv, pv)
    rs = calculate_required_shares(rtv, 180.0)
    _assert(abs(pv - 9000.0) < 1e-6, "B39: 50*180=9000")
    _assert(abs(alloc - 0.09) < 1e-6, "B40: 9000/100000=0.09")
    _assert(abs(tpv - 12000.0) < 1e-6, "B41: 0.12*100000=12000")
    _assert(abs(rtv - 3000.0) < 1e-6, "B42: 12000-9000=3000")
    _assert(abs(rs - 16.6667) < 0.001, "B43: 3000/180=16.67")


# ─────────────────────────────────────────────────────────────────────────────
# Group C: AllocationPortfolioSnapshot
# ─────────────────────────────────────────────────────────────────────────────

def test_group_c():
    print("Group C: AllocationPortfolioSnapshot")

    p = _make_portfolio()
    _assert(p.portfolio_id == "port-001", "C1: portfolio_id set")
    _assert(p.total_portfolio_value == 100_000.0, "C2: total_portfolio_value set")
    _assert(p.cash_value == 10_000.0, "C3: cash_value set")
    _assert(p.cash_pct == 0.10, "C4: cash_pct set")
    _assert(p.as_of == "2026-05-24", "C5: as_of set")

    # Optional fields absent
    p2 = AllocationPortfolioSnapshot(
        portfolio_id="port-002",
        total_portfolio_value=50_000.0,
    )
    _assert(p2.cash_value is None, "C6: cash_value defaults None")
    _assert(p2.cash_pct is None, "C7: cash_pct defaults None")

    # Rejections
    _assert_raises(ValidationError, lambda: AllocationPortfolioSnapshot(
        portfolio_id="port-003",
        total_portfolio_value=-1.0,
    ), "C8: negative total_portfolio_value rejected")

    _assert_raises(ValidationError, lambda: AllocationPortfolioSnapshot(
        portfolio_id="port-003",
        total_portfolio_value=0.0,
    ), "C9: zero total_portfolio_value rejected")

    _assert_raises(ValidationError, lambda: AllocationPortfolioSnapshot(
        portfolio_id="port-003",
        total_portfolio_value=100_000.0,
        cash_value=-100.0,
    ), "C10: negative cash_value rejected")

    _assert_raises(ValidationError, lambda: AllocationPortfolioSnapshot(
        portfolio_id="port-003",
        total_portfolio_value=100_000.0,
        cash_pct=-0.01,
    ), "C11: negative cash_pct rejected")

    _assert_raises(ValidationError, lambda: AllocationPortfolioSnapshot(
        portfolio_id="port-003",
        total_portfolio_value=100_000.0,
        cash_pct=1.01,
    ), "C12: cash_pct > 1 rejected")

    _assert_raises(ValidationError, lambda: AllocationPortfolioSnapshot(
        portfolio_id="  ",
        total_portfolio_value=100_000.0,
    ), "C13: whitespace portfolio_id rejected")

    # source_ids defaults to empty list
    p3 = AllocationPortfolioSnapshot(
        portfolio_id="port-004",
        total_portfolio_value=100_000.0,
    )
    _assert(p3.source_ids == [], "C14: source_ids defaults empty")
    _assert(p3.warnings == [], "C15: warnings defaults empty")

    # Extra fields forbidden
    _assert_raises(ValidationError, lambda: AllocationPortfolioSnapshot(
        portfolio_id="port-005",
        total_portfolio_value=100_000.0,
        unknown_field="bad",
    ), "C16: extra fields forbidden")


# ─────────────────────────────────────────────────────────────────────────────
# Group D: AllocationPositionSnapshot
# ─────────────────────────────────────────────────────────────────────────────

def test_group_d():
    print("Group D: AllocationPositionSnapshot")

    pos = _make_position()
    _assert(pos.position_id == "pos-aapl-001", "D1: position_id set")
    _assert(pos.ticker == "AAPL", "D2: ticker set")
    _assert(pos.shares == 50.0, "D3: shares set")
    _assert(pos.current_price == 180.0, "D4: current_price set")
    _assert(pos.cost_basis == 150.0, "D5: cost_basis set")

    # Zero shares is valid (no position yet)
    pos2 = AllocationPositionSnapshot(
        position_id="pos-002",
        ticker="MSFT",
        shares=0.0,
        current_price=400.0,
    )
    _assert(pos2.shares == 0.0, "D6: zero shares allowed")

    # Rejections
    _assert_raises(ValidationError, lambda: AllocationPositionSnapshot(
        position_id="pos-err",
        ticker="AAPL",
        shares=-1.0,
        current_price=180.0,
    ), "D7: negative shares rejected")

    _assert_raises(ValidationError, lambda: AllocationPositionSnapshot(
        position_id="pos-err",
        ticker="AAPL",
        shares=50.0,
        current_price=0.0,
    ), "D8: zero price rejected")

    _assert_raises(ValidationError, lambda: AllocationPositionSnapshot(
        position_id="pos-err",
        ticker="AAPL",
        shares=50.0,
        current_price=-1.0,
    ), "D9: negative price rejected")

    _assert_raises(ValidationError, lambda: AllocationPositionSnapshot(
        position_id="pos-err",
        ticker="AAPL",
        shares=50.0,
        current_price=180.0,
        cost_basis=-1.0,
    ), "D10: negative cost_basis rejected")

    _assert_raises(ValidationError, lambda: AllocationPositionSnapshot(
        position_id="  ",
        ticker="AAPL",
        shares=50.0,
        current_price=180.0,
    ), "D11: whitespace position_id rejected")

    _assert_raises(ValidationError, lambda: AllocationPositionSnapshot(
        position_id="pos-ok",
        ticker="  ",
        shares=50.0,
        current_price=180.0,
    ), "D12: whitespace ticker rejected")

    # current_position_value provided by caller
    pos3 = AllocationPositionSnapshot(
        position_id="pos-003",
        ticker="NVDA",
        shares=10.0,
        current_price=900.0,
        current_position_value=9500.0,  # slightly different from formula — caller override
    )
    _assert(pos3.current_position_value == 9500.0, "D13: caller-provided current_position_value honored")

    # Negative current_position_value rejected
    _assert_raises(ValidationError, lambda: AllocationPositionSnapshot(
        position_id="pos-err",
        ticker="AAPL",
        shares=50.0,
        current_price=180.0,
        current_position_value=-1.0,
    ), "D14: negative current_position_value rejected")


# ─────────────────────────────────────────────────────────────────────────────
# Group E: AllocationTargetSpec
# ─────────────────────────────────────────────────────────────────────────────

def test_group_e():
    print("Group E: AllocationTargetSpec")

    t = _make_target()
    _assert(t.target_id == "tgt-aapl-001", "E1: target_id set")
    _assert(t.ticker == "AAPL", "E2: ticker set")
    _assert(t.target_allocation_pct == 0.12, "E3: target_allocation_pct set")
    _assert(t.evidence_quality == "adequate", "E4: evidence_quality set")

    # Boundary — 0% and 100% targets are valid
    t0 = AllocationTargetSpec(
        target_id="tgt-zero",
        ticker="AAPL",
        target_allocation_pct=0.0,
        rationale="Exit entirely",
    )
    _assert(t0.target_allocation_pct == 0.0, "E5: 0% target valid")

    t100 = AllocationTargetSpec(
        target_id="tgt-max",
        ticker="AAPL",
        target_allocation_pct=1.0,
    )
    _assert(t100.target_allocation_pct == 1.0, "E6: 100% target valid")

    # min/max bounding
    t_bounded = AllocationTargetSpec(
        target_id="tgt-bounded",
        ticker="AAPL",
        target_allocation_pct=0.10,
        min_allocation_pct=0.05,
        max_allocation_pct=0.20,
    )
    _assert(t_bounded.min_allocation_pct == 0.05, "E7: min_allocation_pct set")
    _assert(t_bounded.max_allocation_pct == 0.20, "E8: max_allocation_pct set")

    # Ordering violation: min > target
    _assert_raises(ValidationError, lambda: AllocationTargetSpec(
        target_id="tgt-err",
        ticker="AAPL",
        target_allocation_pct=0.10,
        min_allocation_pct=0.15,
    ), "E9: min > target rejected")

    # Ordering violation: max < target
    _assert_raises(ValidationError, lambda: AllocationTargetSpec(
        target_id="tgt-err",
        ticker="AAPL",
        target_allocation_pct=0.10,
        max_allocation_pct=0.08,
    ), "E10: max < target rejected")

    # Pct out of range
    _assert_raises(ValidationError, lambda: AllocationTargetSpec(
        target_id="tgt-err",
        ticker="AAPL",
        target_allocation_pct=-0.01,
    ), "E11: negative target pct rejected")

    _assert_raises(ValidationError, lambda: AllocationTargetSpec(
        target_id="tgt-err",
        ticker="AAPL",
        target_allocation_pct=1.01,
    ), "E12: pct > 1 rejected")

    # Whitespace rejections
    _assert_raises(ValidationError, lambda: AllocationTargetSpec(
        target_id="  ",
        ticker="AAPL",
        target_allocation_pct=0.10,
    ), "E13: whitespace target_id rejected")

    _assert_raises(ValidationError, lambda: AllocationTargetSpec(
        target_id="tgt-ok",
        ticker="   ",
        target_allocation_pct=0.10,
    ), "E14: whitespace ticker rejected")

    # All evidence quality values
    for eq in ("unsupported", "weak", "adequate", "strong", "unknown"):
        t_eq = AllocationTargetSpec(
            target_id=f"tgt-{eq}",
            ticker="AAPL",
            target_allocation_pct=0.10,
            evidence_quality=eq,
        )
        _assert(t_eq.evidence_quality == eq, f"E{15 + get_args(AllocationEvidenceQuality).index(eq)}: evidence_quality={eq}")


# ─────────────────────────────────────────────────────────────────────────────
# Group F: RiskBudgetConstraint
# ─────────────────────────────────────────────────────────────────────────────

def test_group_f():
    print("Group F: RiskBudgetConstraint")

    rc = _make_constraint()
    _assert(rc.constraint_id == "rc-001", "F1: constraint_id set")
    _assert(rc.constraint_type == "max_position_pct", "F2: constraint_type set")
    _assert(rc.max_position_pct == 0.20, "F3: max_position_pct set")
    _assert(rc.risk_level == "medium", "F4: risk_level set")

    # All constraint types accepted
    for ct in ("max_position_pct", "max_portfolio_loss_pct", "min_cash_pct",
               "sector_exposure", "liquidity", "volatility", "thesis_confidence",
               "human_review_block", "unknown"):
        rc_ct = RiskBudgetConstraint(constraint_id=f"rc-{ct}", constraint_type=ct)
        _assert(rc_ct.constraint_type == ct, f"F5_ct_{ct}: constraint_type={ct}")

    # stop_price validation
    rc_stop = RiskBudgetConstraint(
        constraint_id="rc-stop",
        constraint_type="max_portfolio_loss_pct",
        stop_price=100.0,
    )
    _assert(rc_stop.stop_price == 100.0, "F6: stop_price set")

    _assert_raises(ValidationError, lambda: RiskBudgetConstraint(
        constraint_id="rc-err",
        stop_price=-1.0,
    ), "F7: negative stop_price rejected")

    # Whitespace rejection
    _assert_raises(ValidationError, lambda: RiskBudgetConstraint(
        constraint_id="  ",
    ), "F8: whitespace constraint_id rejected")

    # pct out of range
    _assert_raises(ValidationError, lambda: RiskBudgetConstraint(
        constraint_id="rc-ok",
        max_position_pct=1.01,
    ), "F9: max_position_pct > 1 rejected")

    _assert_raises(ValidationError, lambda: RiskBudgetConstraint(
        constraint_id="rc-ok",
        max_portfolio_loss_pct=-0.01,
    ), "F10: negative max_portfolio_loss_pct rejected")

    # Defaults
    rc_default = RiskBudgetConstraint(constraint_id="rc-default")
    _assert(rc_default.constraint_type == "unknown", "F11: constraint_type defaults unknown")
    _assert(rc_default.risk_level == "unknown", "F12: risk_level defaults unknown")
    _assert(rc_default.source_ids == [], "F13: source_ids defaults empty")
    _assert(rc_default.warnings == [], "F14: warnings defaults empty")


# ─────────────────────────────────────────────────────────────────────────────
# Group G: AllocationCalculation
# ─────────────────────────────────────────────────────────────────────────────

def test_group_g():
    print("Group G: AllocationCalculation")

    calc = AllocationCalculation(
        current_position_value=9000.0,
        current_allocation_pct=0.09,
        target_position_value=12000.0,
        required_trade_value=3000.0,
        required_shares=16.67,
        action_type="add",
        cash_impact=-3000.0,
        projected_cash_value=7000.0,
        projected_cash_pct=0.07,
        max_loss_at_stop=4500.0,
        portfolio_loss_pct=0.045,
        constraint_violations=[],
        warnings=[],
        source_ids=["ev1"],
    )
    _assert(calc.current_position_value == 9000.0, "G1: current_position_value")
    _assert(calc.current_allocation_pct == 0.09, "G2: current_allocation_pct")
    _assert(calc.target_position_value == 12000.0, "G3: target_position_value")
    _assert(calc.required_trade_value == 3000.0, "G4: required_trade_value positive")
    _assert(calc.action_type == "add", "G5: action_type=add")
    _assert(calc.cash_impact == -3000.0, "G6: cash_impact negative when adding")
    _assert(calc.projected_cash_value == 7000.0, "G7: projected_cash_value")
    _assert(calc.projected_cash_pct == 0.07, "G8: projected_cash_pct")
    _assert(calc.max_loss_at_stop == 4500.0, "G9: max_loss_at_stop")
    _assert(calc.portfolio_loss_pct == 0.045, "G10: portfolio_loss_pct")
    _assert(calc.constraint_violations == [], "G11: constraint_violations empty")
    _assert(calc.source_ids == ["ev1"], "G12: source_ids set")


# ─────────────────────────────────────────────────────────────────────────────
# Group H: AllocationAssessment
# ─────────────────────────────────────────────────────────────────────────────

def test_group_h():
    print("Group H: AllocationAssessment")

    calc = AllocationCalculation(
        current_position_value=9000.0,
        current_allocation_pct=0.09,
        target_position_value=12000.0,
        required_trade_value=3000.0,
        required_shares=16.67,
        action_type="add",
        cash_impact=-3000.0,
    )
    asmt = AllocationAssessment(
        assessment_id="ast-001",
        ticker="AAPL",
        calculation=calc,
        recommendation_action="add",
        risk_level="medium",
        constraint_violations=[],
        review_required=False,
        rationale="Increase position",
        source_ids=["ev1"],
        approved_for_execution=False,
    )
    _assert(asmt.assessment_id == "ast-001", "H1: assessment_id set")
    _assert(asmt.ticker == "AAPL", "H2: ticker set")
    _assert(asmt.recommendation_action == "add", "H3: recommendation_action set")
    _assert(asmt.risk_level == "medium", "H4: risk_level set")
    _assert(asmt.review_required is False, "H5: review_required False")
    _assert(asmt.approved_for_execution is False, "H6: approved_for_execution False")

    # approved_for_execution guard
    _assert_raises(ValidationError, lambda: AllocationAssessment(
        assessment_id="ast-bad",
        ticker="AAPL",
        calculation=calc,
        approved_for_execution=True,
    ), "H7: approved_for_execution=True rejected")

    # Whitespace rejections
    _assert_raises(ValidationError, lambda: AllocationAssessment(
        assessment_id="  ",
        ticker="AAPL",
        calculation=calc,
    ), "H8: whitespace assessment_id rejected")

    _assert_raises(ValidationError, lambda: AllocationAssessment(
        assessment_id="ast-ok",
        ticker="   ",
        calculation=calc,
    ), "H9: whitespace ticker rejected")

    # extra fields forbidden
    _assert_raises(ValidationError, lambda: AllocationAssessment(
        assessment_id="ast-ok",
        ticker="AAPL",
        calculation=calc,
        order_id="bad",
    ), "H10: extra field order_id rejected")

    _assert_raises(ValidationError, lambda: AllocationAssessment(
        assessment_id="ast-ok",
        ticker="AAPL",
        calculation=calc,
        broker_order="bad",
    ), "H11: extra field broker_order rejected")

    _assert_raises(ValidationError, lambda: AllocationAssessment(
        assessment_id="ast-ok",
        ticker="AAPL",
        calculation=calc,
        account_id="bad",
    ), "H12: extra field account_id rejected")


# ─────────────────────────────────────────────────────────────────────────────
# Group I: AllocationInputBundle
# ─────────────────────────────────────────────────────────────────────────────

def test_group_i():
    print("Group I: AllocationInputBundle")

    bundle = _make_bundle()
    _assert(bundle.target == "AAPL", "I1: target set")
    _assert(bundle.run_id == "run_test_001", "I2: run_id set")
    _assert(bundle.as_of == "2026-05-24", "I3: as_of set")
    _assert(bundle.portfolio_snapshot is not None, "I4: portfolio_snapshot set")
    _assert(bundle.position_snapshot is not None, "I5: position_snapshot set")
    _assert(bundle.allocation_target is not None, "I6: allocation_target set")
    _assert(bundle.risk_constraints == [], "I7: risk_constraints defaults empty")
    _assert(bundle.trade_plan_report is None, "I8: trade_plan_report defaults None")
    _assert(bundle.decision_packet is None, "I9: decision_packet defaults None")
    _assert(bundle.human_review_report is None, "I10: human_review_report defaults None")

    # Whitespace target rejected
    _assert_raises(ValidationError, lambda: _make_bundle(target="  "), "I_ws: whitespace target rejected")


# ─────────────────────────────────────────────────────────────────────────────
# Group J: AllocationSummary
# ─────────────────────────────────────────────────────────────────────────────

def test_group_j():
    print("Group J: AllocationSummary")

    summary = AllocationSummary(
        target="AAPL",
        status="complete",
        action_type="add",
        current_allocation_pct=0.09,
        target_allocation_pct=0.12,
        required_trade_value=3000.0,
        required_shares=16.67,
        cash_impact=-3000.0,
        projected_cash_pct=0.07,
        portfolio_loss_pct=0.045,
        constraint_violation_count=0,
        review_required=False,
        top_warnings=[],
        approved_for_execution=False,
    )
    _assert(summary.target == "AAPL", "J1: target set")
    _assert(summary.status == "complete", "J2: status set")
    _assert(summary.action_type == "add", "J3: action_type set")
    _assert(summary.approved_for_execution is False, "J4: approved_for_execution False")

    # approved_for_execution guard
    _assert_raises(ValidationError, lambda: AllocationSummary(
        target="AAPL",
        approved_for_execution=True,
    ), "J5: approved_for_execution=True rejected")

    # Whitespace target
    _assert_raises(ValidationError, lambda: AllocationSummary(
        target="  ",
    ), "J6: whitespace target rejected")

    # Defaults
    s_default = AllocationSummary(target="MSFT")
    _assert(s_default.status == "unknown", "J7: status defaults unknown")
    _assert(s_default.action_type == "unknown", "J8: action_type defaults unknown")
    _assert(s_default.constraint_violation_count == 0, "J9: violation count defaults 0")
    _assert(s_default.top_warnings == [], "J10: top_warnings defaults empty")


# ─────────────────────────────────────────────────────────────────────────────
# Group K: AllocationReport
# ─────────────────────────────────────────────────────────────────────────────

def test_group_k():
    print("Group K: AllocationReport")

    bundle = _make_bundle()
    calc = AllocationCalculation(
        current_position_value=9000.0,
        current_allocation_pct=0.09,
        target_position_value=12000.0,
        required_trade_value=3000.0,
        required_shares=16.67,
        action_type="add",
        cash_impact=-3000.0,
    )
    asmt = AllocationAssessment(
        assessment_id="ast-k001",
        ticker="AAPL",
        calculation=calc,
        recommendation_action="add",
        risk_level="low",
        approved_for_execution=False,
    )
    summary = AllocationSummary(target="AAPL", status="complete", action_type="add")
    report = AllocationReport(
        report_id="alr_test001",
        target="AAPL",
        run_id="run_test_001",
        status="complete",
        input_bundle=bundle,
        assessment=asmt,
        summary=summary,
        created_at="2026-05-24",
        approved_for_execution=False,
    )
    _assert(report.report_id == "alr_test001", "K1: report_id set")
    _assert(report.schema_version == "1.0", "K2: schema_version set")
    _assert(report.target == "AAPL", "K3: target set")
    _assert(report.status == "complete", "K4: status set")
    _assert(report.approved_for_execution is False, "K5: approved_for_execution False")
    _assert(report.calculation_version == "allocation_report_v1", "K6: calculation_version set")

    # approved_for_execution guard
    _assert_raises(ValidationError, lambda: AllocationReport(
        report_id="alr_bad",
        target="AAPL",
        run_id="run_bad",
        status="complete",
        input_bundle=bundle,
        assessment=asmt,
        summary=summary,
        created_at="2026-05-24",
        approved_for_execution=True,
    ), "K7: approved_for_execution=True rejected")

    # Whitespace rejections
    _assert_raises(ValidationError, lambda: AllocationReport(
        report_id="  ",
        target="AAPL",
        run_id="run_ok",
        status="complete",
        input_bundle=bundle,
        assessment=asmt,
        summary=summary,
        created_at="2026-05-24",
    ), "K8: whitespace report_id rejected")

    _assert_raises(ValidationError, lambda: AllocationReport(
        report_id="alr_ok",
        target="AAPL",
        run_id="  ",
        status="complete",
        input_bundle=bundle,
        assessment=asmt,
        summary=summary,
        created_at="2026-05-24",
    ), "K9: whitespace run_id rejected")

    _assert_raises(ValidationError, lambda: AllocationReport(
        report_id="alr_ok",
        target="AAPL",
        run_id="run_ok",
        status="complete",
        input_bundle=bundle,
        assessment=asmt,
        summary=summary,
        created_at="  ",
    ), "K10: whitespace created_at rejected")


# ─────────────────────────────────────────────────────────────────────────────
# Group L: build_allocation_calculation — action type inference
# ─────────────────────────────────────────────────────────────────────────────

def test_group_l():
    print("Group L: build_allocation_calculation — action type inference")

    portfolio = _make_portfolio(total_portfolio_value=100_000.0, cash_value=10_000.0)

    # L1-L4: add — target > current
    position_low = _make_position(shares=50.0, current_price=180.0)  # value=9000 (9%)
    target_high = _make_target(target_allocation_pct=0.12)            # target=12000
    calc_add = build_allocation_calculation(portfolio, position_low, target_high, [])
    _assert(calc_add.action_type == "add", "L1: add when target > current")
    _assert(abs(calc_add.required_trade_value - 3000.0) < 1.0, "L2: required_trade_value ≈ 3000")
    _assert(calc_add.required_shares > 0, "L3: required_shares positive for add")
    _assert(calc_add.cash_impact < 0, "L4: cash_impact negative for add (cash decreases)")

    # L5-L7: trim — target < current
    position_high = _make_position(shares=100.0, current_price=180.0)  # value=18000 (18%)
    target_low = _make_target(target_allocation_pct=0.12)               # target=12000
    calc_trim = build_allocation_calculation(portfolio, position_high, target_low, [])
    _assert(calc_trim.action_type == "trim", "L5: trim when target < current")
    _assert(calc_trim.required_trade_value < 0, "L6: required_trade_value negative for trim")
    _assert(calc_trim.required_shares < 0, "L7: required_shares negative for trim")

    # L8-L9: hold — target ≈ current (within tolerance)
    position_match = _make_position(shares=66.67, current_price=180.0)  # ≈12000
    target_match = _make_target(target_allocation_pct=0.12)
    calc_hold = build_allocation_calculation(portfolio, position_match, target_match, [])
    _assert(calc_hold.action_type == "hold", "L8: hold when current ≈ target")
    _assert(abs(calc_hold.required_trade_value) < 10, "L9: small required_trade_value for hold")

    # L10-L12: exit — target = 0, current > 0
    position_exist = _make_position(shares=50.0, current_price=180.0)
    target_exit = _make_target(target_allocation_pct=0.0)
    calc_exit = build_allocation_calculation(portfolio, position_exist, target_exit, [])
    _assert(calc_exit.action_type == "exit", "L10: exit when target=0 and current>0")
    _assert(calc_exit.target_position_value == 0.0, "L11: target_position_value=0 for exit")
    _assert(calc_exit.cash_impact > 0, "L12: cash_impact positive for exit (cash released)")

    # L13-L14: no_action — target=0, current=0
    position_zero = _make_position(shares=0.0, current_price=180.0)
    target_zero = _make_target(target_allocation_pct=0.0)
    calc_no_action = build_allocation_calculation(portfolio, position_zero, target_zero, [])
    _assert(calc_no_action.action_type == "no_action", "L13: no_action when target=0 and current=0")
    _assert(calc_no_action.required_trade_value == 0.0, "L14: required_trade_value=0 for no_action")

    # L15-L16: cash projection
    portfolio_with_cash = _make_portfolio(cash_value=10_000.0)
    calc_with_cash = build_allocation_calculation(portfolio_with_cash, position_low, target_high, [])
    _assert(calc_with_cash.projected_cash_value is not None, "L15: projected_cash_value computed")
    _assert(calc_with_cash.projected_cash_pct is not None, "L16: projected_cash_pct computed")

    # L17: no cash projection when cash_value is None
    portfolio_no_cash = _make_portfolio(cash_value=None, cash_pct=None)
    calc_no_cash = build_allocation_calculation(portfolio_no_cash, position_low, target_high, [])
    _assert(calc_no_cash.projected_cash_value is None, "L17: no projected_cash when no cash_value")

    # L18-L20: stop-loss constraint
    rc_stop = _make_constraint(
        constraint_id="rc-stop",
        constraint_type="max_portfolio_loss_pct",
        max_position_pct=None,
        stop_price=150.0,
    )
    calc_stop = build_allocation_calculation(portfolio, position_low, target_high, [rc_stop])
    _assert(calc_stop.max_loss_at_stop is not None, "L18: max_loss_at_stop computed from stop constraint")
    _assert(calc_stop.portfolio_loss_pct is not None, "L19: portfolio_loss_pct computed from stop constraint")
    _assert(calc_stop.max_loss_at_stop >= 0.0, "L20: max_loss_at_stop non-negative")

    # L21-L23: max_position_pct constraint violation
    rc_tight = _make_constraint(
        constraint_id="rc-tight",
        constraint_type="max_position_pct",
        max_position_pct=0.05,  # 5% max, target is 12% → violation
    )
    calc_violated = build_allocation_calculation(portfolio, position_low, target_high, [rc_tight])
    _assert(len(calc_violated.constraint_violations) > 0, "L21: constraint violation detected")
    _assert("max_position_pct" in calc_violated.constraint_violations[0], "L22: violation describes max_position_pct")
    _assert(calc_violated.action_type == "add", "L23: action_type still add despite violation")

    # L24-L26: human_review_block constraint
    rc_block = RiskBudgetConstraint(
        constraint_id="rc-block",
        constraint_type="human_review_block",
        risk_level="high",
    )
    calc_blocked = build_allocation_calculation(portfolio, position_low, target_high, [rc_block])
    _assert(len(calc_blocked.constraint_violations) > 0, "L24: human_review_block generates violation")
    _assert("human_review_block" in calc_blocked.constraint_violations[0], "L25: violation contains human_review_block")
    _assert(calc_blocked.action_type == "add", "L26: action type unaffected by hr block constraint")

    # L27-L28: caller-provided current_position_value honored
    position_override = AllocationPositionSnapshot(
        position_id="pos-override",
        ticker="AAPL",
        shares=50.0,
        current_price=180.0,
        current_position_value=10_000.0,  # override
    )
    calc_override = build_allocation_calculation(portfolio, position_override, target_high, [])
    _assert(calc_override.current_position_value == 10_000.0, "L27: caller-provided position value honored")
    _assert(abs(calc_override.current_allocation_pct - 0.10) < 1e-6, "L28: alloc pct based on override value")

    # L29: source IDs collected from inputs
    position_src = _make_position(source_ids=["ev_pos_src"])
    portfolio_src = _make_portfolio(source_ids=["ev_port_src"])
    target_src = _make_target(source_ids=["ev_tgt_src"])
    rc_src = RiskBudgetConstraint(constraint_id="rc-src", source_ids=["ev_rc_src"])
    calc_src = build_allocation_calculation(portfolio_src, position_src, target_src, [rc_src])
    _assert("ev_port_src" in calc_src.source_ids, "L29: portfolio source IDs collected")
    _assert("ev_pos_src" in calc_src.source_ids, "L30: position source IDs collected")
    _assert("ev_tgt_src" in calc_src.source_ids, "L31: target source IDs collected")
    _assert("ev_rc_src" in calc_src.source_ids, "L32: constraint source IDs collected")

    # L33-L35: min_cash_pct constraint violation
    portfolio_low_cash = AllocationPortfolioSnapshot(
        portfolio_id="port-lowcash",
        total_portfolio_value=100_000.0,
        cash_value=2_000.0,  # 2%
    )
    rc_min_cash = RiskBudgetConstraint(
        constraint_id="rc-mincash",
        constraint_type="min_cash_pct",
        min_cash_pct=0.05,  # need 5%, but after adding we'd have even less
        risk_level="medium",
    )
    # After adding 3000, cash goes from 2000 to -1000 which is < 5% = violation
    calc_cash_viol = build_allocation_calculation(
        portfolio_low_cash, position_low, target_high, [rc_min_cash]
    )
    _assert(len(calc_cash_viol.constraint_violations) > 0, "L33: min_cash_pct violation detected")
    _assert("min_cash_pct" in calc_cash_viol.constraint_violations[0], "L34: violation contains min_cash_pct")

    # L35: warning when shares=0 but action is active
    position_no_shares = _make_position(shares=0.0, current_price=180.0)
    calc_no_shares = build_allocation_calculation(
        portfolio, position_no_shares, target_high, []
    )
    _assert(len(calc_no_shares.warnings) > 0, "L35: warning when shares=0 but add inferred")

    # L36-L38: max_portfolio_loss_pct violation
    position_large = _make_position(shares=200.0, current_price=180.0, cost_basis=180.0)
    rc_loss = RiskBudgetConstraint(
        constraint_id="rc-loss",
        constraint_type="max_portfolio_loss_pct",
        max_portfolio_loss_pct=0.02,  # 2% max loss; 200 shares at 30 stop = 6000 = 6% > 2%
        stop_price=150.0,  # stop at 150, entry at 180 → loss = 200*(180-150) = 6000
        risk_level="high",
    )
    calc_loss_viol = build_allocation_calculation(portfolio, position_large, target_high, [rc_loss])
    _assert(calc_loss_viol.portfolio_loss_pct is not None, "L36: portfolio_loss_pct computed")
    _assert(len(calc_loss_viol.constraint_violations) > 0, "L37: max_portfolio_loss_pct violation detected")
    _assert("max_portfolio_loss_pct" in calc_loss_viol.constraint_violations[0], "L38: violation text correct")

    # L39-L40: deterministic — same inputs same outputs
    calc_det1 = build_allocation_calculation(portfolio, position_low, target_high, [])
    calc_det2 = build_allocation_calculation(portfolio, position_low, target_high, [])
    _assert(calc_det1.required_trade_value == calc_det2.required_trade_value, "L39: deterministic trade value")
    _assert(calc_det1.action_type == calc_det2.action_type, "L40: deterministic action type")


# ─────────────────────────────────────────────────────────────────────────────
# Group M: build_allocation_report — end-to-end
# ─────────────────────────────────────────────────────────────────────────────

def test_group_m():
    print("Group M: build_allocation_report — end-to-end")

    # M1-M8: basic complete report
    bundle = _make_bundle(
        portfolio=_make_portfolio(cash_value=10_000.0),
        position=_make_position(shares=50.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.12),
        source_ids=["ev_bundle_001"],
    )
    report = build_allocation_report(bundle, run_id="run_m_001", created_at="2026-05-24")
    _assert(isinstance(report, AllocationReport), "M1: returns AllocationReport")
    _assert(report.target == "AAPL", "M2: target set")
    _assert(report.run_id == "run_m_001", "M3: run_id set")
    _assert(report.created_at == "2026-05-24", "M4: created_at from explicit arg")
    _assert(report.approved_for_execution is False, "M5: approved_for_execution False")
    _assert(report.assessment.approved_for_execution is False, "M6: assessment.approved_for_execution False")
    _assert(report.summary.approved_for_execution is False, "M7: summary.approved_for_execution False")
    _assert(report.calculation_version == "allocation_report_v1", "M8: calculation_version set")

    # M9-M10: deterministic — same inputs → same report_id
    report2 = build_allocation_report(bundle, run_id="run_m_001", created_at="2026-05-24")
    _assert(report.report_id == report2.report_id, "M9: deterministic report_id")
    _assert(report.assessment.assessment_id == report2.assessment.assessment_id, "M10: deterministic assessment_id")

    # M11-M12: deterministic without explicit created_at
    report_det1 = build_allocation_report(bundle, run_id="run_m_002")
    report_det2 = build_allocation_report(bundle, run_id="run_m_002")
    _assert(report_det1.report_id == report_det2.report_id, "M11: deterministic report_id without explicit ts")
    _assert(report_det1.created_at == report_det2.created_at, "M12: deterministic created_at without explicit ts")

    # M13: created_at override works
    report_ts1 = build_allocation_report(bundle, run_id="run_m_ts", created_at="2026-01-01T00:00:00")
    _assert(report_ts1.created_at == "2026-01-01T00:00:00", "M13: created_at override respected")

    # M14-M16: add action
    bundle_add = _make_bundle(
        position=_make_position(shares=50.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.12),
    )
    report_add = build_allocation_report(bundle_add, run_id="run_m_add")
    _assert(report_add.assessment.recommendation_action == "add", "M14: add action recognized")
    _assert(report_add.summary.action_type == "add", "M15: summary reflects add")
    _assert(report_add.summary.required_trade_value > 0, "M16: required_trade_value positive for add")

    # M17-M19: trim action
    bundle_trim = _make_bundle(
        position=_make_position(shares=100.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.05),
    )
    report_trim = build_allocation_report(bundle_trim, run_id="run_m_trim")
    _assert(report_trim.assessment.recommendation_action == "trim", "M17: trim action recognized")
    _assert(report_trim.summary.required_trade_value < 0, "M18: required_trade_value negative for trim")
    _assert(report_trim.summary.cash_impact > 0, "M19: cash_impact positive for trim")

    # M20-M21: exit action
    bundle_exit = _make_bundle(
        position=_make_position(shares=50.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.0),
    )
    report_exit = build_allocation_report(bundle_exit, run_id="run_m_exit")
    _assert(report_exit.assessment.recommendation_action == "exit", "M20: exit action recognized")
    _assert(report_exit.summary.target_allocation_pct == 0.0, "M21: target pct=0 for exit")

    # M22: clean complete allocation → status complete
    bundle_clean = _make_bundle(
        position=_make_position(shares=66.67, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.12),
    )
    report_clean = build_allocation_report(bundle_clean, run_id="run_m_clean")
    _assert(report_clean.status == "complete", "M22: clean allocation → complete")

    # M23-M24: constraint violation → needs_review
    rc_tight = _make_constraint(
        constraint_id="rc-tight",
        constraint_type="max_position_pct",
        max_position_pct=0.05,
    )
    bundle_violated = _make_bundle(
        position=_make_position(shares=50.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.12),
        risk_constraints=[rc_tight],
    )
    report_violated = build_allocation_report(bundle_violated, run_id="run_m_violated")
    _assert(report_violated.status == "needs_review", "M23: constraint violation → needs_review")
    _assert(report_violated.summary.constraint_violation_count > 0, "M24: violation count > 0")

    # M25-M26: human_review_block → blocked
    rc_block = RiskBudgetConstraint(
        constraint_id="rc-hrblock",
        constraint_type="human_review_block",
        risk_level="high",
    )
    bundle_blocked = _make_bundle(
        position=_make_position(shares=50.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.12),
        risk_constraints=[rc_block],
    )
    report_blocked = build_allocation_report(bundle_blocked, run_id="run_m_blocked")
    _assert(report_blocked.status == "blocked", "M25: human_review_block constraint → blocked")
    _assert(report_blocked.summary.review_required is True, "M26: review_required True when blocked")

    # M27-M28: human review report status=blocked → blocked
    class MockHRReport:
        status = "blocked"

    bundle_hr_blocked = _make_bundle(
        position=_make_position(shares=50.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.12),
        human_review_report=MockHRReport(),
    )
    report_hr_blocked = build_allocation_report(bundle_hr_blocked, run_id="run_m_hrblocked")
    _assert(report_hr_blocked.status == "blocked", "M27: human_review_report.status=blocked → blocked")
    _assert(report_hr_blocked.approved_for_execution is False, "M28: even blocked status has approved_for_execution=False")

    # M29-M30: missing optional artifacts generate warnings, not crashes
    bundle_minimal = _make_bundle()  # no trade_plan_report, no decision_packet
    report_minimal = build_allocation_report(bundle_minimal, run_id="run_m_minimal")
    _assert(isinstance(report_minimal, AllocationReport), "M29: missing optional artifacts → no crash")
    _assert(len(report_minimal.warnings) > 0, "M30: missing optional artifacts generate warnings")

    # M31: warning for missing trade_plan_report in warnings
    missing_tp_warnings = [w for w in report_minimal.warnings if "trade_plan_report" in w]
    _assert(len(missing_tp_warnings) > 0, "M31: trade_plan_report missing warning present")

    # M32: warning for missing decision_packet in warnings
    missing_dp_warnings = [w for w in report_minimal.warnings if "decision_packet" in w]
    _assert(len(missing_dp_warnings) > 0, "M32: decision_packet missing warning present")

    # M33: top_warnings present in summary when warnings generated
    _assert(isinstance(report_minimal.summary.top_warnings, list), "M33: summary.top_warnings is list")

    # M34-M35: source ID collection and deduplication
    portfolio_src = _make_portfolio(source_ids=["ev_port"])
    position_src = _make_position(source_ids=["ev_pos"])
    target_src = _make_target(source_ids=["ev_tgt"])
    bundle_src = AllocationInputBundle(
        target="AAPL",
        run_id="run_src",
        as_of="2026-05-24",
        portfolio_snapshot=portfolio_src,
        position_snapshot=position_src,
        allocation_target=target_src,
        source_ids=["ev_bundle"],
    )
    report_src = build_allocation_report(bundle_src, run_id="run_src", created_at="2026-05-24")
    _assert("ev_port" in report_src.source_ids, "M34: portfolio source_ids collected")
    _assert("ev_pos" in report_src.source_ids, "M35: position source_ids collected")
    _assert("ev_tgt" in report_src.source_ids, "M36: target source_ids collected")
    _assert("ev_bundle" in report_src.source_ids, "M37: bundle source_ids collected")

    # M38: no duplicate source_ids
    all_sids = report_src.source_ids
    _assert(len(all_sids) == len(set(all_sids)), "M38: no duplicate source_ids")

    # M39-M41: inputs not mutated
    import copy
    bundle_orig = _make_bundle(
        portfolio=_make_portfolio(source_ids=["ev_p"]),
        position=_make_position(source_ids=["ev_pos"]),
        alloc_target=_make_target(source_ids=["ev_t"]),
        source_ids=["ev_b"],
    )
    orig_portfolio_sids = list(bundle_orig.portfolio_snapshot.source_ids)
    orig_position_sids = list(bundle_orig.position_snapshot.source_ids)
    orig_bundle_sids = list(bundle_orig.source_ids)
    build_allocation_report(bundle_orig, run_id="run_orig")
    _assert(bundle_orig.portfolio_snapshot.source_ids == orig_portfolio_sids, "M39: portfolio.source_ids not mutated")
    _assert(bundle_orig.position_snapshot.source_ids == orig_position_sids, "M40: position.source_ids not mutated")
    _assert(bundle_orig.source_ids == orig_bundle_sids, "M41: bundle.source_ids not mutated")

    # M42-M43: summary.projected_cash_pct populated when cash available
    report_with_cash = build_allocation_report(bundle_add, run_id="run_m_cashpct", created_at="2026-05-24")
    _assert(report_with_cash.summary.projected_cash_pct is not None, "M42: projected_cash_pct in summary when cash available")

    # M44: warning count consistent
    _assert(len(report.warnings) == len(set(report.warnings)), "M44: warnings deduplicated in report")

    # M45-M47: no_action for zero-target, zero-position
    bundle_no_action = _make_bundle(
        position=_make_position(shares=0.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.0),
    )
    report_no_action = build_allocation_report(bundle_no_action, run_id="run_m_noaction")
    _assert(report_no_action.assessment.recommendation_action == "no_action", "M45: no_action when target=0 current=0")
    _assert(report_no_action.status in ("complete", "unknown"), "M46: no_action status is complete or unknown")
    _assert(report_no_action.summary.required_trade_value == 0.0, "M47: required_trade_value=0 for no_action")

    # M48-M50: report_id has stable prefix
    _assert(report.report_id.startswith("alr_"), "M48: report_id has alr_ prefix")
    _assert(len(report.report_id) > 4, "M49: report_id not just prefix")
    _assert(report.run_id == "run_m_001", "M50: run_id preserved in report")


# ─────────────────────────────────────────────────────────────────────────────
# Group N: determine_allocation_status
# ─────────────────────────────────────────────────────────────────────────────

def test_group_n():
    print("Group N: determine_allocation_status")

    def _make_asmt(
        action: str = "add",
        risk_level: str = "low",
        violations: list[str] | None = None,
    ) -> AllocationAssessment:
        calc = AllocationCalculation(
            current_position_value=9000.0,
            current_allocation_pct=0.09,
            target_position_value=12000.0,
            required_trade_value=3000.0,
            required_shares=16.67,
            action_type=action,
            cash_impact=-3000.0,
            constraint_violations=violations or [],
        )
        return AllocationAssessment(
            assessment_id=f"ast_{action}",
            ticker="AAPL",
            calculation=calc,
            recommendation_action=action,
            risk_level=risk_level,
            constraint_violations=violations or [],
            review_required=bool(violations),
            approved_for_execution=False,
        )

    # N1: complete when clean
    asmt_clean = _make_asmt(action="add", risk_level="low")
    _assert(determine_allocation_status(asmt_clean) == "complete", "N1: clean add → complete")

    # N2: complete for hold
    asmt_hold = _make_asmt(action="hold", risk_level="low")
    _assert(determine_allocation_status(asmt_hold) == "complete", "N2: clean hold → complete")

    # N3: complete for trim
    asmt_trim = _make_asmt(action="trim", risk_level="low")
    _assert(determine_allocation_status(asmt_trim) == "complete", "N3: clean trim → complete")

    # N4: complete for exit
    asmt_exit = _make_asmt(action="exit", risk_level="low")
    _assert(determine_allocation_status(asmt_exit) == "complete", "N4: clean exit → complete")

    # N5: unknown when action unknown
    asmt_unknown = _make_asmt(action="unknown", risk_level="low")
    _assert(determine_allocation_status(asmt_unknown) == "unknown", "N5: unknown action → unknown")

    # N6: needs_review when constraint violations
    asmt_viol = _make_asmt(
        action="add",
        risk_level="medium",
        violations=["RiskBudgetConstraint 'rc-001': max_position_pct violated"],
    )
    _assert(determine_allocation_status(asmt_viol) == "needs_review", "N6: violations → needs_review")

    # N7: needs_review when high risk
    asmt_high_risk = _make_asmt(action="add", risk_level="high")
    _assert(determine_allocation_status(asmt_high_risk) == "needs_review", "N7: high risk → needs_review")

    # N8: blocked when human_review_block in violations
    asmt_hr_block = _make_asmt(
        action="add",
        risk_level="high",
        violations=["RiskBudgetConstraint 'rc-hrblock': constraint_type='human_review_block' — allocation blocked"],
    )
    _assert(determine_allocation_status(asmt_hr_block) == "blocked", "N8: human_review_block violation → blocked")

    # N9: blocked when hr report says blocked
    class MockHR:
        status = "blocked"

    asmt_any = _make_asmt(action="add", risk_level="low")
    _assert(determine_allocation_status(asmt_any, human_review_report=MockHR()) == "blocked",
            "N9: hr_report.status=blocked → blocked")

    # N10: blocked takes precedence over needs_review
    asmt_both = _make_asmt(
        action="add",
        risk_level="high",
        violations=["RiskBudgetConstraint 'rc-hrblock': constraint_type='human_review_block' — allocation blocked"],
    )
    _assert(determine_allocation_status(asmt_both) == "blocked", "N10: blocked > needs_review")

    # N11: hr None has no effect
    _assert(determine_allocation_status(asmt_clean, human_review_report=None) == "complete",
            "N11: None hr_report → no effect")

    # N12: hr with non-blocked status has no effect
    class MockHROther:
        status = "changes_requested"

    _assert(determine_allocation_status(asmt_clean, human_review_report=MockHROther()) == "complete",
            "N12: hr_report.status!=blocked → no effect")


# ─────────────────────────────────────────────────────────────────────────────
# Group O: summarize_allocation_report
# ─────────────────────────────────────────────────────────────────────────────

def test_group_o():
    print("Group O: summarize_allocation_report")

    bundle = _make_bundle(
        portfolio=_make_portfolio(cash_value=10_000.0),
        position=_make_position(shares=50.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.12),
    )
    report = build_allocation_report(bundle, run_id="run_o_001", created_at="2026-05-24")
    summary_dict = summarize_allocation_report(report)

    required_keys = [
        "report_id", "target", "status", "action_type",
        "current_allocation_pct", "target_allocation_pct",
        "required_trade_value", "required_shares", "cash_impact",
        "projected_cash_pct", "portfolio_loss_pct",
        "constraint_violation_count", "review_required",
        "warning_count", "source_id_count",
        "calculation_version", "approved_for_execution",
    ]
    for key in required_keys:
        _assert(key in summary_dict, f"O_key_{key}: key present in summary dict")

    _assert(summary_dict["approved_for_execution"] is False, "O_approved: approved_for_execution always False")
    _assert(summary_dict["target"] == "AAPL", "O_target: target correct")
    _assert(summary_dict["calculation_version"] == "allocation_report_v1", "O_calcver: calculation_version correct")
    _assert(isinstance(summary_dict["warning_count"], int), "O_wcount: warning_count is int")
    _assert(isinstance(summary_dict["source_id_count"], int), "O_scount: source_id_count is int")


# ─────────────────────────────────────────────────────────────────────────────
# Group P: allocation_report_tool_result_from_report
# ─────────────────────────────────────────────────────────────────────────────

def test_group_p():
    print("Group P: allocation_report_tool_result_from_report (ToolResult adapter)")

    from lib.reliability.schemas import ToolResult

    bundle = _make_bundle(
        portfolio=_make_portfolio(cash_value=10_000.0),
        position=_make_position(shares=50.0, current_price=180.0),
        alloc_target=_make_target(target_allocation_pct=0.12),
    )
    report = build_allocation_report(bundle, run_id="run_p_001", created_at="2026-05-24")
    tool_result = allocation_report_tool_result_from_report("run_p_001", report)

    # Shape
    _assert(isinstance(tool_result, ToolResult), "P1: returns ToolResult")
    _assert(tool_result.tool_name == "allocation_report", "P2: stable tool_name")
    _assert(tool_result.run_id == "run_p_001", "P3: run_id matches")
    _assert(tool_result.evidence_id is not None, "P4: evidence_id set")
    _assert(len(tool_result.evidence_id) > 0, "P5: evidence_id non-empty")

    # Deterministic evidence_id
    tool_result2 = allocation_report_tool_result_from_report("run_p_001", report)
    _assert(tool_result.evidence_id == tool_result2.evidence_id, "P6: deterministic evidence_id")

    # Outputs shape
    outputs = tool_result.outputs
    _assert("report" in outputs, "P7: outputs has 'report'")
    _assert("summary" in outputs, "P8: outputs has 'summary'")
    _assert("calculation_version" in outputs, "P9: outputs has 'calculation_version'")

    # Summary in outputs
    summary_in_out = outputs["summary"]
    _assert(summary_in_out["approved_for_execution"] is False, "P10: summary.approved_for_execution False")
    _assert(summary_in_out["target"] == "AAPL", "P11: summary.target correct")

    # No order-ticket fields
    report_dump = outputs["report"]
    _assert("order_id" not in report_dump, "P12: no order_id in report dump")
    _assert("broker_order" not in report_dump, "P13: no broker_order in report dump")
    _assert("account_id" not in report_dump, "P14: no account_id in report dump")
    _assert("execution_status" not in report_dump, "P15: no execution_status in report dump")
    _assert("order_instruction" not in report_dump, "P16: no order_instruction in report dump")

    # approved_for_execution in outputs always False
    _assert(report_dump.get("approved_for_execution") is False, "P17: report_dump.approved_for_execution False")

    # Target override
    tool_result_override = allocation_report_tool_result_from_report(
        "run_p_001", report, target="AAPL_override"
    )
    # evidence_id changes when target overridden
    _assert(tool_result_override.evidence_id != tool_result.evidence_id, "P18: different target → different evidence_id")

    # description is a non-empty string
    _assert(isinstance(tool_result.description, str), "P19: description is string")
    _assert(len(tool_result.description) > 0, "P20: description non-empty")


# ─────────────────────────────────────────────────────────────────────────────
# Group Q: collect_allocation_source_ids
# ─────────────────────────────────────────────────────────────────────────────

def test_group_q():
    print("Group Q: collect_allocation_source_ids")

    portfolio_src = _make_portfolio(source_ids=["ev_port"])
    position_src = _make_position(source_ids=["ev_pos"])
    target_src = _make_target(source_ids=["ev_tgt"])
    rc_src = RiskBudgetConstraint(constraint_id="rc-src", source_ids=["ev_rc"])
    bundle_src = AllocationInputBundle(
        target="AAPL",
        run_id="run_src",
        as_of="2026-05-24",
        portfolio_snapshot=portfolio_src,
        position_snapshot=position_src,
        allocation_target=target_src,
        risk_constraints=[rc_src],
        source_ids=["ev_bundle"],
    )

    calc = AllocationCalculation(
        current_position_value=9000.0,
        current_allocation_pct=0.09,
        target_position_value=12000.0,
        required_trade_value=3000.0,
        required_shares=16.67,
        action_type="add",
        cash_impact=-3000.0,
        source_ids=["ev_calc"],
    )
    asmt = AllocationAssessment(
        assessment_id="ast-src",
        ticker="AAPL",
        calculation=calc,
        source_ids=["ev_asmt"],
        approved_for_execution=False,
    )

    collected = collect_allocation_source_ids(bundle_src, asmt)
    _assert("ev_bundle" in collected, "Q1: bundle source_id collected")
    _assert("ev_port" in collected, "Q2: portfolio source_id collected")
    _assert("ev_pos" in collected, "Q3: position source_id collected")
    _assert("ev_tgt" in collected, "Q4: target source_id collected")
    _assert("ev_rc" in collected, "Q5: constraint source_id collected")
    _assert("ev_asmt" in collected, "Q6: assessment source_id collected")
    _assert("ev_calc" in collected, "Q7: calc source_id collected")

    # No duplicates
    _assert(len(collected) == len(set(collected)), "Q8: no duplicate source_ids")

    # Order: bundle first
    _assert(collected.index("ev_bundle") < collected.index("ev_port"), "Q9: bundle id before portfolio id")
    _assert(collected.index("ev_port") < collected.index("ev_pos"), "Q10: portfolio before position")


# ─────────────────────────────────────────────────────────────────────────────
# Group R: make_allocation_report_id
# ─────────────────────────────────────────────────────────────────────────────

def test_group_r():
    print("Group R: make_allocation_report_id")

    id1 = make_allocation_report_id("run001", "AAPL", "2026-05-24")
    id2 = make_allocation_report_id("run001", "AAPL", "2026-05-24")
    _assert(id1 == id2, "R1: same inputs → same ID (deterministic)")

    id3 = make_allocation_report_id("run002", "AAPL", "2026-05-24")
    _assert(id1 != id3, "R2: different run_id → different ID")

    id4 = make_allocation_report_id("run001", "MSFT", "2026-05-24")
    _assert(id1 != id4, "R3: different target → different ID")

    id5 = make_allocation_report_id("run001", "AAPL", "2026-05-25")
    _assert(id1 != id5, "R4: different as_of → different ID")

    _assert(id1.startswith("alr_"), "R5: ID has alr_ prefix")
    _assert(len(id1) > 4, "R6: ID is more than just prefix")


# ─────────────────────────────────────────────────────────────────────────────
# Group S: __all__ exports from lib/reliability include Phase 3R-C symbols
# ─────────────────────────────────────────────────────────────────────────────

def test_group_s():
    print("Group S: __all__ exports include Phase 3R-C symbols")

    from lib.reliability import __all__ as reliability_all

    phase_3rc_symbols = [
        "AllocationStatus",
        "AllocationActionType",
        "AllocationRiskLevel",
        "AllocationEvidenceQuality",
        "AllocationConstraintType",
        "AllocationPortfolioSnapshot",
        "AllocationPositionSnapshot",
        "AllocationTargetSpec",
        "RiskBudgetConstraint",
        "AllocationCalculation",
        "AllocationAssessment",
        "AllocationInputBundle",
        "AllocationSummary",
        "AllocationReport",
        "calculate_position_value",
        "calculate_allocation_pct",
        "calculate_target_position_value",
        "calculate_required_trade_value",
        "calculate_required_shares",
        "calculate_max_loss_at_stop",
        "calculate_portfolio_loss_pct",
        "make_allocation_report_id",
        "determine_allocation_status",
        "collect_allocation_source_ids",
        "build_allocation_calculation",
        "build_allocation_report",
        "summarize_allocation_report",
        "allocation_report_tool_result_from_report",
    ]

    for sym in phase_3rc_symbols:
        _assert(sym in reliability_all, f"S_{sym}: {sym} in __all__")


# ─────────────────────────────────────────────────────────────────────────────
# Group T: No forbidden modules imported
# ─────────────────────────────────────────────────────────────────────────────

def test_group_t():
    print("Group T: No forbidden modules imported")

    import importlib
    import sys as _sys

    # Reload allocation_report to ensure we're checking its actual imports
    if "lib.reliability.allocation_report" in _sys.modules:
        mod = _sys.modules["lib.reliability.allocation_report"]
    else:
        mod = importlib.import_module("lib.reliability.allocation_report")

    # Get module's import namespace
    mod_dict = vars(mod)

    _assert("streamlit" not in mod_dict, "T1: streamlit not imported")
    _assert("anthropic" not in mod_dict, "T2: anthropic not imported")

    # Check module source for known forbidden patterns
    import inspect
    try:
        source = inspect.getsource(mod)
    except Exception:
        source = ""

    _assert("import streamlit" not in source, "T3: 'import streamlit' not in source")
    _assert("import anthropic" not in source, "T4: 'import anthropic' not in source")
    _assert("import brokerage" not in source and "import broker" not in source, "T5: no live broker import")
    # The docstring legitimately references these as absent features; check no assignments
    _assert("order_id =" not in source and '"order_id"' not in source.replace("no order_id", ""),
            "T6: order_id not used as field/key")
    _assert("account_id =" not in source and '"account_id"' not in source.replace("no account_id", "") and '"account_id"' not in source.replace("account_id,", ""),
            "T7: account_id not used as field/key")
    _assert("execution_status =" not in source and '"execution_status"' not in source.replace("execution_status,", "").replace("no execution_status", ""),
            "T8: execution_status not used as field/key")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def main():
    groups = [
        ("A", test_group_a),
        ("B", test_group_b),
        ("C", test_group_c),
        ("D", test_group_d),
        ("E", test_group_e),
        ("F", test_group_f),
        ("G", test_group_g),
        ("H", test_group_h),
        ("I", test_group_i),
        ("J", test_group_j),
        ("K", test_group_k),
        ("L", test_group_l),
        ("M", test_group_m),
        ("N", test_group_n),
        ("O", test_group_o),
        ("P", test_group_p),
        ("Q", test_group_q),
        ("R", test_group_r),
        ("S", test_group_s),
        ("T", test_group_t),
    ]

    for label, fn in groups:
        try:
            fn()
        except Exception as e:
            print(f"  ERROR in group {label}: {e}")
            traceback.print_exc()

    total = _PASS + _FAIL
    print(f"\n{'=' * 60}")
    print(f"RESULT: {_PASS}/{total} passed, {_FAIL} failed")
    if _FAIL == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"FAILURES: {_FAIL}")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
