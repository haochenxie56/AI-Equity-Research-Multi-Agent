"""
scripts/test_reliability_allocation.py

Test suite for lib/reliability/allocation.py — Phase 2D.

Run with:
    python3 scripts/test_reliability_allocation.py

No external dependencies beyond lib/reliability and pydantic.
Does not make network calls. Does not read/write live files.
Does not import Streamlit, app.py, or any live workflow module.

Groups:
  A: Literal aliases — AllocationAction (9), PositionDirection (4),
     RiskBudgetStatus (5)  [18 assertions]
  B: PositionSnapshot — required fields (current_price, as_of, source),
     optional fields, validators  [22 assertions]
  C: PortfolioSnapshot — required fields, source, whitespace rejection  [13]
  D: AllocationTarget — creation, ordering constraint, all actions  [23]
  E: RiskBudget — creation, max_position_allocation_pct, constraints  [10]
  F: PositionSizingResult and StopLossRiskResult — required fields  [18]
  G: AllocationDecisionSet — partial data, risk_budget, defaults  [15]
  H: compute_position_market_value — all cases  [8]
  I: compute_current_allocation_pct — correctness  [6]
  J: calculate_position_sizing — all action cases, action inference  [27]
  K: calculate_cash_released_from_trim and calculate_cash_needed_for_add  [13]
  L: calculate_stop_loss_risk — all budget status cases, position_market_value  [18]
  M: allocation_tool_result_from_decision_set — shape, determinism  [20]
  N: summarize_allocation_decision_set — all keys  [14]
  O: validate_portfolio_snapshot — all warning conditions  [8]
  P: validate_allocation_decision_set — new warning conditions  [10]
  Q: Serialization roundtrip — all model types  [17]
  R: No forbidden modules imported; __init__.py exports  [13]
"""

# ── sys.path fix — MUST come before any lib imports ──────────────────────────
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import traceback

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

from lib.reliability.allocation import (
    # Literals
    AllocationAction,
    PositionDirection,
    RiskBudgetStatus,
    # Models
    PositionSnapshot,
    PortfolioSnapshot,
    AllocationTarget,
    RiskBudget,
    PositionSizingResult,
    StopLossRiskResult,
    AllocationDecisionSet,
    # Calculators
    compute_position_market_value,
    compute_current_allocation_pct,
    calculate_position_sizing,
    calculate_cash_released_from_trim,
    calculate_cash_needed_for_add,
    calculate_stop_loss_risk,
    # Adapter
    allocation_tool_result_from_decision_set,
    # Helpers
    summarize_allocation_decision_set,
    validate_portfolio_snapshot,
    validate_allocation_decision_set,
)
from lib.reliability.schemas import EvidenceRef


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_position(
    ticker: str = "AAPL",
    shares: float = 100.0,
    current_price: float = 150.0,
    as_of: str = "2026-05-21",
    source: str = "synthetic",
) -> PositionSnapshot:
    return PositionSnapshot(
        ticker=ticker,
        shares=shares,
        current_price=current_price,
        as_of=as_of,
        source=source,
    )


def _make_portfolio(
    positions=None,
    cash: float = 10000.0,
    total_value: float = 100000.0,
    as_of: str = "2026-05-21",
    source: str = "synthetic",
) -> PortfolioSnapshot:
    if positions is None:
        positions = [_make_position()]
    return PortfolioSnapshot(
        portfolio_id="port_001",
        as_of=as_of,
        positions=positions,
        cash=cash,
        total_value=total_value,
        source=source,
    )


def _make_target(
    ticker: str = "AAPL",
    target_pct: float = 0.15,
    action: str = "no_action",  # "no_action" so inference tests work correctly
) -> AllocationTarget:
    return AllocationTarget(
        ticker=ticker,
        target_allocation_pct=target_pct,
        action=action,
    )


def _make_risk_budget(
    max_pos_risk: float = 0.02,
    max_sector: float = 0.30,
    max_cash: float = 0.20,
) -> RiskBudget:
    return RiskBudget(
        max_single_position_risk_pct=max_pos_risk,
        max_sector_allocation_pct=max_sector,
        max_cash_pct=max_cash,
    )


def _make_sizing_result(
    ticker: str = "AAPL",
    evidence_refs=None,
    action: str = "add",
) -> PositionSizingResult:
    """Helper to build a valid PositionSizingResult including all required fields."""
    return PositionSizingResult(
        ticker=ticker,
        current_price=150.0,
        current_shares=100.0,
        current_market_value=15000.0,
        current_allocation_pct=0.15,
        target_allocation_pct=0.20,
        target_market_value=20000.0,
        required_trade_value=5000.0,
        cash_impact=-5000.0,
        action=action,
        evidence_refs=evidence_refs if evidence_refs is not None else [],
    )


def _make_stop_loss_result(
    ticker: str = "AAPL",
    status: str = "within_budget",
) -> StopLossRiskResult:
    """Helper to build a valid StopLossRiskResult including all required fields."""
    return StopLossRiskResult(
        ticker=ticker,
        shares=100.0,
        current_price=150.0,
        stop_price=140.0,
        position_market_value=15000.0,
        max_loss_amount=1000.0,
        portfolio_loss_pct=0.01,
        risk_budget_status=status,
    )


# ── Group A: Literal aliases ──────────────────────────────────────────────────

def test_a_literal_aliases():
    print("Group A: Literal aliases")

    from typing import get_args

    # AllocationAction — all 8 values
    valid_actions = get_args(AllocationAction)
    _assert("add" in valid_actions, "A1: AllocationAction includes 'add'")
    _assert("hold" in valid_actions, "A2: AllocationAction includes 'hold'")
    _assert("trim" in valid_actions, "A3: AllocationAction includes 'trim'")
    _assert("exit" in valid_actions, "A4: AllocationAction includes 'exit'")
    _assert("avoid" in valid_actions, "A5: AllocationAction includes 'avoid'")
    _assert("wait" in valid_actions, "A6: AllocationAction includes 'wait'")
    _assert("rebalance" in valid_actions, "A7: AllocationAction includes 'rebalance'")
    _assert("no_action" in valid_actions, "A8: AllocationAction includes 'no_action'")
    _assert(len(valid_actions) == 8, "A9: AllocationAction has exactly 8 values")

    # PositionDirection — all 3 values
    valid_dirs = get_args(PositionDirection)
    _assert("long" in valid_dirs, "A10: PositionDirection includes 'long'")
    _assert("short" in valid_dirs, "A11: PositionDirection includes 'short'")
    _assert("flat" in valid_dirs, "A12: PositionDirection includes 'flat'")
    _assert(len(valid_dirs) == 3, "A13: PositionDirection has exactly 3 values")

    # RiskBudgetStatus — all 4 values
    valid_status = get_args(RiskBudgetStatus)
    _assert("within_budget" in valid_status, "A14: RiskBudgetStatus includes 'within_budget'")
    _assert("near_limit" in valid_status, "A15: RiskBudgetStatus includes 'near_limit'")
    _assert("over_budget" in valid_status, "A16: RiskBudgetStatus includes 'over_budget'")
    _assert("unknown" in valid_status, "A17: RiskBudgetStatus includes 'unknown'")
    _assert(len(valid_status) == 4, "A18: RiskBudgetStatus has exactly 4 values")


# ── Group B: PositionSnapshot ─────────────────────────────────────────────────

def test_b_position_snapshot():
    print("Group B: PositionSnapshot")

    # Basic creation — current_price and as_of are both REQUIRED
    pos = PositionSnapshot(
        ticker="AAPL", shares=100.0, current_price=150.0, as_of="2026-05-21"
    )
    _assert(pos.ticker == "AAPL", "B1: ticker set correctly")
    _assert(pos.shares == 100.0, "B2: shares set correctly")
    _assert(pos.current_price == 150.0, "B3: current_price set correctly")
    _assert(pos.market_value is None, "B4: market_value defaults to None")
    _assert(pos.direction == "long", "B5: direction defaults to 'long'")
    _assert(pos.cost_basis is None, "B6: cost_basis defaults to None")
    _assert(pos.metadata == {}, "B7: metadata defaults to empty dict")
    _assert(pos.as_of == "2026-05-21", "B8: as_of set correctly")
    _assert(pos.source == "synthetic", "B9: source defaults to 'synthetic'")

    # Optional fields
    pos3 = PositionSnapshot(
        ticker="NVDA",
        shares=20.0,
        current_price=500.0,
        as_of="2026-05-21",
        direction="short",
        cost_basis=480.0,
        metadata={"sector": "technology"},
    )
    _assert(pos3.direction == "short", "B10: direction can be 'short'")
    _assert(pos3.cost_basis == 480.0, "B11: cost_basis set correctly")
    _assert(pos3.metadata["sector"] == "technology", "B12: metadata stored correctly")

    # flat direction; zero shares
    pos4 = PositionSnapshot(
        ticker="CASH", shares=0.0, current_price=1.0,
        as_of="2026-05-21", direction="flat"
    )
    _assert(pos4.direction == "flat", "B13: direction can be 'flat'")
    _assert(pos4.shares == 0.0, "B14: zero shares is valid")

    # Validators — current_price <= 0 raises
    _assert_raises(
        Exception,
        lambda: PositionSnapshot(
            ticker="BAD", shares=10.0, current_price=0.0, as_of="2026-05-21"
        ),
        "B15: current_price=0 raises",
    )
    _assert_raises(
        Exception,
        lambda: PositionSnapshot(
            ticker="BAD", shares=10.0, current_price=-1.0, as_of="2026-05-21"
        ),
        "B16: current_price<0 raises",
    )

    # Validators — market_value < 0 raises
    _assert_raises(
        Exception,
        lambda: PositionSnapshot(
            ticker="BAD", shares=10.0, current_price=10.0,
            as_of="2026-05-21", market_value=-100.0
        ),
        "B17: market_value<0 raises",
    )

    # Validators — whitespace-only ticker raises
    _assert_raises(
        Exception,
        lambda: PositionSnapshot(
            ticker="   ", shares=10.0, current_price=10.0, as_of="2026-05-21"
        ),
        "B18: whitespace-only ticker raises",
    )

    # Validators — cost_basis < 0 raises
    _assert_raises(
        Exception,
        lambda: PositionSnapshot(
            ticker="BAD", shares=10.0, current_price=10.0,
            as_of="2026-05-21", cost_basis=-5.0
        ),
        "B19: cost_basis<0 raises",
    )

    # Validators — whitespace-only as_of raises
    _assert_raises(
        Exception,
        lambda: PositionSnapshot(
            ticker="AAPL", shares=10.0, current_price=10.0, as_of="   "
        ),
        "B20: whitespace-only as_of raises",
    )

    # Extra fields forbidden
    _assert_raises(
        Exception,
        lambda: PositionSnapshot(
            ticker="BAD", shares=10.0, current_price=10.0,
            as_of="2026-05-21", unknown_field="x"
        ),
        "B21: extra field raises",
    )

    # cost_basis=0.0 is VALID (constraint is >= 0, not > 0)
    pos_zero_cb = PositionSnapshot(
        ticker="AAPL", shares=10.0, current_price=10.0,
        as_of="2026-05-21", cost_basis=0.0
    )
    _assert(pos_zero_cb.cost_basis == 0.0, "B22: cost_basis=0.0 is valid (>= 0)")


# ── Group C: PortfolioSnapshot ────────────────────────────────────────────────

def test_c_portfolio_snapshot():
    print("Group C: PortfolioSnapshot")

    pos = _make_position()
    port = PortfolioSnapshot(
        portfolio_id="port_001",
        as_of="2026-05-21",
        positions=[pos],
        cash=5000.0,
        total_value=100000.0,
    )
    _assert(port.portfolio_id == "port_001", "C1: portfolio_id set")
    _assert(port.as_of == "2026-05-21", "C2: as_of set")
    _assert(len(port.positions) == 1, "C3: one position stored")
    _assert(port.cash == 5000.0, "C4: cash set")
    _assert(port.total_value == 100000.0, "C5: total_value set")
    _assert(port.source == "synthetic", "C6: source defaults to 'synthetic'")
    _assert(port.metadata == {}, "C7: metadata defaults to empty dict")

    # Empty positions allowed
    port_empty = PortfolioSnapshot(
        portfolio_id="port_002", as_of="2026-05-21",
        positions=[], cash=100000.0, total_value=100000.0,
    )
    _assert(len(port_empty.positions) == 0, "C8: empty positions list is valid")

    # total_value must be > 0
    _assert_raises(
        Exception,
        lambda: PortfolioSnapshot(
            portfolio_id="p", as_of="2026-05-21",
            positions=[], cash=0.0, total_value=0.0,
        ),
        "C9: total_value=0 raises",
    )
    _assert_raises(
        Exception,
        lambda: PortfolioSnapshot(
            portfolio_id="p", as_of="2026-05-21",
            positions=[], cash=0.0, total_value=-1.0,
        ),
        "C10: total_value<0 raises",
    )

    # cash must be >= 0
    _assert_raises(
        Exception,
        lambda: PortfolioSnapshot(
            portfolio_id="p", as_of="2026-05-21",
            positions=[], cash=-1.0, total_value=100.0,
        ),
        "C11: cash<0 raises",
    )

    # Whitespace-only portfolio_id raises
    _assert_raises(
        Exception,
        lambda: PortfolioSnapshot(
            portfolio_id="   ", as_of="2026-05-21",
            positions=[], cash=0.0, total_value=100.0,
        ),
        "C12: whitespace-only portfolio_id raises",
    )

    # Empty portfolio_id raises (min_length=1)
    _assert_raises(
        Exception,
        lambda: PortfolioSnapshot(
            portfolio_id="", as_of="2026-05-21",
            positions=[], cash=0.0, total_value=100.0,
        ),
        "C13: empty portfolio_id raises",
    )


# ── Group D: AllocationTarget ─────────────────────────────────────────────────

def test_d_allocation_target():
    print("Group D: AllocationTarget")

    t = AllocationTarget(ticker="AAPL", target_allocation_pct=0.10)
    _assert(t.ticker == "AAPL", "D1: ticker set")
    _assert(t.target_allocation_pct == 0.10, "D2: target_allocation_pct set")
    _assert(t.min_allocation_pct is None, "D3: min defaults to None")
    _assert(t.max_allocation_pct is None, "D4: max defaults to None")
    _assert(t.action == "hold", "D5: action defaults to 'hold'")
    _assert(t.evidence_refs == [], "D6: evidence_refs defaults to empty")
    _assert(t.rationale is None, "D7: rationale defaults to None")

    # With min/max/rationale
    t2 = AllocationTarget(
        ticker="MSFT",
        target_allocation_pct=0.10,
        min_allocation_pct=0.05,
        max_allocation_pct=0.15,
        action="add",
        rationale="Underweight vs benchmark",
    )
    _assert(t2.min_allocation_pct == 0.05, "D8: min_allocation_pct set")
    _assert(t2.max_allocation_pct == 0.15, "D9: max_allocation_pct set")
    _assert(t2.action == "add", "D10: action='add' accepted")
    _assert(t2.rationale == "Underweight vs benchmark", "D11: rationale set")

    # target=0 is valid (exit target)
    t3 = AllocationTarget(ticker="EXIT", target_allocation_pct=0.0)
    _assert(t3.target_allocation_pct == 0.0, "D12: target_allocation_pct=0 valid")

    # min > target raises
    _assert_raises(
        Exception,
        lambda: AllocationTarget(
            ticker="BAD", target_allocation_pct=0.05, min_allocation_pct=0.10
        ),
        "D13: min > target raises",
    )

    # max < target raises
    _assert_raises(
        Exception,
        lambda: AllocationTarget(
            ticker="BAD", target_allocation_pct=0.15, max_allocation_pct=0.10
        ),
        "D14: max < target raises",
    )

    # target > 1.0 raises
    _assert_raises(
        Exception,
        lambda: AllocationTarget(ticker="BAD", target_allocation_pct=1.5),
        "D15: target_allocation_pct>1.0 raises",
    )

    # All 8 AllocationAction values accepted
    from typing import get_args
    for act in get_args(AllocationAction):
        t_act = AllocationTarget(ticker="TEST", target_allocation_pct=0.05, action=act)
        _assert(t_act.action == act, f"D16+: action='{act}' accepted")


# ── Group E: RiskBudget ───────────────────────────────────────────────────────

def test_e_risk_budget():
    print("Group E: RiskBudget")

    rb = RiskBudget(
        max_single_position_risk_pct=0.02,
        max_sector_allocation_pct=0.30,
        max_cash_pct=0.20,
    )
    _assert(rb.max_single_position_risk_pct == 0.02, "E1: max_single_position_risk_pct set")
    _assert(rb.max_sector_allocation_pct == 0.30, "E2: max_sector_allocation_pct set")
    _assert(rb.max_cash_pct == 0.20, "E3: max_cash_pct set")
    _assert(rb.notes == "", "E4: notes defaults to empty string")
    _assert(rb.max_position_allocation_pct is None,
            "E5: max_position_allocation_pct defaults to None")

    # With optional max_position_allocation_pct
    rb2 = RiskBudget(
        max_single_position_risk_pct=0.01,
        max_sector_allocation_pct=0.25,
        max_cash_pct=0.10,
        max_position_allocation_pct=0.15,
        notes="Conservative risk profile",
    )
    _assert(rb2.max_position_allocation_pct == 0.15,
            "E6: max_position_allocation_pct set to 0.15")
    _assert(rb2.notes == "Conservative risk profile", "E7: notes set")

    # max_single_position_risk_pct must be > 0
    _assert_raises(
        Exception,
        lambda: RiskBudget(
            max_single_position_risk_pct=0.0,
            max_sector_allocation_pct=0.30,
            max_cash_pct=0.20,
        ),
        "E8: max_single_position_risk_pct=0 raises",
    )
    _assert_raises(
        Exception,
        lambda: RiskBudget(
            max_single_position_risk_pct=-0.01,
            max_sector_allocation_pct=0.30,
            max_cash_pct=0.20,
        ),
        "E9: max_single_position_risk_pct<0 raises",
    )

    # Fields must be <= 1.0
    _assert_raises(
        Exception,
        lambda: RiskBudget(
            max_single_position_risk_pct=1.5,
            max_sector_allocation_pct=0.30,
            max_cash_pct=0.20,
        ),
        "E10: max_single_position_risk_pct>1 raises",
    )


# ── Group F: PositionSizingResult and StopLossRiskResult ─────────────────────

def test_f_result_models():
    print("Group F: PositionSizingResult and StopLossRiskResult")

    # PositionSizingResult — current_price is required
    sr = PositionSizingResult(
        ticker="AAPL",
        current_price=150.0,           # REQUIRED in Phase 2D
        current_shares=100.0,
        current_market_value=15000.0,
        current_allocation_pct=0.15,
        target_allocation_pct=0.20,
        target_market_value=20000.0,
        required_trade_value=5000.0,
        required_shares=33.33,
        cash_impact=-5000.0,
        action="add",
    )
    _assert(sr.ticker == "AAPL", "F1: PositionSizingResult ticker set")
    _assert(sr.current_price == 150.0, "F2: current_price set")
    _assert(sr.action == "add", "F3: action='add'")
    _assert(sr.required_shares == 33.33, "F4: required_shares set")
    _assert(sr.cash_impact == -5000.0, "F5: cash_impact set")
    _assert(sr.calculation_version == "allocation_schema_v1", "F6: default calc version")
    _assert(sr.evidence_refs == [], "F7: evidence_refs defaults to empty list")

    # required_shares can be None
    sr2 = PositionSizingResult(
        ticker="AAPL",
        current_price=150.0,
        current_shares=100.0,
        current_market_value=15000.0,
        current_allocation_pct=0.15,
        target_allocation_pct=0.10,
        target_market_value=10000.0,
        required_trade_value=-5000.0,
        required_shares=None,
        cash_impact=5000.0,
        action="trim",
    )
    _assert(sr2.required_shares is None, "F8: required_shares can be None")
    _assert(sr2.action == "trim", "F9: action='trim'")

    # StopLossRiskResult — position_market_value is required
    slr = StopLossRiskResult(
        ticker="AAPL",
        shares=100.0,
        current_price=150.0,
        stop_price=140.0,
        position_market_value=15000.0,   # REQUIRED in Phase 2D
        max_loss_amount=1000.0,
        portfolio_loss_pct=0.01,
        risk_budget_status="within_budget",
    )
    _assert(slr.ticker == "AAPL", "F10: StopLossRiskResult ticker set")
    _assert(slr.position_market_value == 15000.0, "F11: position_market_value set")
    _assert(slr.max_loss_amount == 1000.0, "F12: max_loss_amount set")
    _assert(slr.risk_budget_status == "within_budget", "F13: within_budget")
    _assert(slr.calculation_version == "allocation_schema_v1", "F14: default calc version")

    # All RiskBudgetStatus values accepted
    from typing import get_args
    for status in get_args(RiskBudgetStatus):
        r = StopLossRiskResult(
            ticker="T",
            shares=1.0,
            current_price=10.0,
            stop_price=9.0,
            position_market_value=10.0,
            max_loss_amount=1.0,
            portfolio_loss_pct=0.001,
            risk_budget_status=status,
        )
        _assert(r.risk_budget_status == status, f"F15+: status='{status}' accepted")


# ── Group G: AllocationDecisionSet ───────────────────────────────────────────

def test_g_allocation_decision_set():
    print("Group G: AllocationDecisionSet")

    ds = AllocationDecisionSet(portfolio_id="port_001", as_of="2026-05-21")
    _assert(ds.portfolio_id == "port_001", "G1: portfolio_id set")
    _assert(ds.as_of == "2026-05-21", "G2: as_of set")
    _assert(ds.schema_version == "1.0", "G3: schema_version defaults to '1.0'")
    _assert(ds.risk_budget is None, "G4: risk_budget defaults to None")
    _assert(ds.targets == [], "G5: targets defaults to empty list")
    _assert(ds.sizing_results == [], "G6: sizing_results defaults to empty list")
    _assert(ds.stop_loss_results == [], "G7: stop_loss_results defaults to empty list")
    _assert(ds.notes == [], "G8: notes defaults to empty list")
    _assert(ds.warnings == [], "G9: warnings defaults to empty list")

    # With risk_budget
    rb = _make_risk_budget()
    ds_with_rb = AllocationDecisionSet(
        portfolio_id="p", as_of="2026-05-21", risk_budget=rb
    )
    _assert(ds_with_rb.risk_budget is not None, "G10: risk_budget can be set")
    _assert(
        ds_with_rb.risk_budget.max_cash_pct == 0.20,
        "G11: risk_budget fields preserved",
    )

    # Partial data — only targets and notes
    target = _make_target()
    ds2 = AllocationDecisionSet(
        portfolio_id="port_002",
        as_of="2026-05-21",
        targets=[target],
        notes=["initial draft"],
        warnings=["data may be stale"],
    )
    _assert(len(ds2.targets) == 1, "G12: one target stored")
    _assert(ds2.notes[0] == "initial draft", "G13: notes stored")

    # Empty portfolio_id raises
    _assert_raises(
        Exception,
        lambda: AllocationDecisionSet(portfolio_id="", as_of="2026-05-21"),
        "G14: empty portfolio_id raises",
    )

    # Extra fields forbidden
    _assert_raises(
        Exception,
        lambda: AllocationDecisionSet(
            portfolio_id="p", as_of="2026-05-21", unknown="x"
        ),
        "G15: extra field raises",
    )


# ── Group H: compute_position_market_value ────────────────────────────────────

def test_h_compute_market_value():
    print("Group H: compute_position_market_value")

    # Uses market_value when provided (takes priority over shares * current_price)
    pos_mv = PositionSnapshot(
        ticker="AAPL", shares=100.0, current_price=150.0,
        as_of="2026-05-21", market_value=15200.0
    )
    _assert(
        compute_position_market_value(pos_mv) == 15200.0,
        "H1: uses market_value (15200) over shares*price (15000)",
    )

    # Both set — market_value still wins
    pos_both = PositionSnapshot(
        ticker="AAPL", shares=100.0, current_price=150.0,
        as_of="2026-05-21", market_value=15200.0
    )
    _assert(
        compute_position_market_value(pos_both) == 15200.0,
        "H2: market_value takes priority even when price is also set",
    )

    # Only current_price — falls back to shares * price
    pos_price = PositionSnapshot(
        ticker="MSFT", shares=50.0, current_price=300.0, as_of="2026-05-21"
    )
    _assert(
        compute_position_market_value(pos_price) == 15000.0,
        "H3: shares * current_price fallback = 50 * 300 = 15000",
    )

    # Zero shares
    pos_zero = PositionSnapshot(
        ticker="X", shares=0.0, current_price=100.0, as_of="2026-05-21"
    )
    _assert(compute_position_market_value(pos_zero) == 0.0, "H4: zero shares → 0.0")

    # market_value=0 (closing position)
    pos_closing = PositionSnapshot(
        ticker="X", shares=10.0, current_price=100.0,
        as_of="2026-05-21", market_value=0.0
    )
    _assert(compute_position_market_value(pos_closing) == 0.0, "H5: market_value=0 valid")

    # Determinism
    pos_a = _make_position()
    pos_b = _make_position()
    _assert(
        compute_position_market_value(pos_a) == compute_position_market_value(pos_b),
        "H6: deterministic — same inputs → same output",
    )

    # Fractional shares
    pos_frac = PositionSnapshot(
        ticker="BRK", shares=0.5, current_price=500000.0, as_of="2026-05-21"
    )
    _assert(
        compute_position_market_value(pos_frac) == 250000.0,
        "H7: fractional shares 0.5 * 500000 = 250000",
    )

    # Result is a float
    _assert(
        isinstance(compute_position_market_value(_make_position()), float),
        "H8: return type is float",
    )


# ── Group I: compute_current_allocation_pct ───────────────────────────────────

def test_i_compute_allocation_pct():
    print("Group I: compute_current_allocation_pct")

    portfolio = _make_portfolio(total_value=100000.0)

    # 100 shares @ 150 = 15000; 15000/100000 = 0.15
    pos = _make_position(shares=100.0, current_price=150.0)
    pct = compute_current_allocation_pct(pos, portfolio)
    _assert(abs(pct - 0.15) < 1e-9, "I1: 15000/100000 = 0.15")

    # Zero shares → 0.0 allocation
    pos_zero = PositionSnapshot(
        ticker="AAPL", shares=0.0, current_price=150.0, as_of="2026-05-21"
    )
    pct_zero = compute_current_allocation_pct(pos_zero, portfolio)
    _assert(pct_zero == 0.0, "I2: zero shares → 0.0 allocation pct")

    # Full portfolio in one position (via market_value)
    pos_full = PositionSnapshot(
        ticker="AAPL", shares=1.0, current_price=100000.0,
        as_of="2026-05-21", market_value=100000.0
    )
    pct_full = compute_current_allocation_pct(pos_full, portfolio)
    _assert(abs(pct_full - 1.0) < 1e-9, "I3: 100000/100000 = 1.0")

    # Uses market_value when set
    pos_with_mv = PositionSnapshot(
        ticker="MSFT", shares=50.0, current_price=400.0,
        as_of="2026-05-21", market_value=20000.0
    )
    pct_mv = compute_current_allocation_pct(pos_with_mv, portfolio)
    _assert(abs(pct_mv - 0.20) < 1e-9, "I4: market_value=20000 → 20000/100000 = 0.20")

    # Result scales with price
    pos_low = _make_position(shares=100.0, current_price=50.0)
    pct_low = compute_current_allocation_pct(pos_low, portfolio)
    _assert(abs(pct_low - 0.05) < 1e-9, "I5: 5000/100000 = 0.05")

    # Deterministic
    pct1 = compute_current_allocation_pct(pos, portfolio)
    pct2 = compute_current_allocation_pct(pos, portfolio)
    _assert(pct1 == pct2, "I6: deterministic — same inputs → same output")


# ── Group J: calculate_position_sizing ───────────────────────────────────────

def test_j_calculate_position_sizing():
    print("Group J: calculate_position_sizing")

    # Portfolio: AAPL = 100 shares @ 150 = 15000 (15% of 100000)
    portfolio = _make_portfolio(
        positions=[_make_position(shares=100.0, current_price=150.0)],
        cash=10000.0,
        total_value=100000.0,
    )

    # ── J1-J9: Underweight → add ──
    # target=20% = 20000; trade = 20000-15000=5000; shares=5000/150≈33.33
    target = _make_target(target_pct=0.20)  # action="no_action" → infers
    result = calculate_position_sizing(portfolio, target)

    _assert(result.ticker == "AAPL", "J1: ticker correct")
    _assert(result.current_shares == 100.0, "J2: current_shares = 100")
    _assert(abs(result.current_market_value - 15000.0) < 0.01, "J3: current_mv = 15000")
    _assert(abs(result.current_allocation_pct - 0.15) < 1e-9, "J4: current_pct = 0.15")
    _assert(abs(result.target_market_value - 20000.0) < 0.01, "J5: target_mv = 20000")
    _assert(abs(result.required_trade_value - 5000.0) < 0.01, "J6: trade = 5000")
    _assert(abs(result.required_shares - 33.33333) < 0.001, "J7: required_shares ≈ 33.33")
    _assert(abs(result.cash_impact - (-5000.0)) < 0.01, "J8: cash_impact = -5000")
    _assert(result.action == "add", "J9: action inferred as 'add'")

    # ── J10-J12: Overweight → trim ──
    # target=10% = 10000; trade = 10000-15000 = -5000
    target_trim = _make_target(target_pct=0.10)  # action="no_action" → infers
    result_trim = calculate_position_sizing(portfolio, target_trim)
    _assert(
        abs(result_trim.required_trade_value - (-5000.0)) < 0.01,
        "J10: trade negative for trim",
    )
    _assert(
        abs(result_trim.cash_impact - 5000.0) < 0.01,
        "J11: cash_impact positive for trim",
    )
    _assert(result_trim.action == "trim", "J12: action inferred as 'trim'")

    # ── J13-J14: At target → hold ──
    # target=15% = 15000; trade = 15000-15000 = 0 < tolerance → hold
    target_hold = _make_target(target_pct=0.15)  # action="no_action" → infers
    result_hold = calculate_position_sizing(portfolio, target_hold)
    _assert(abs(result_hold.required_trade_value) < 0.01, "J13: trade ≈ 0 for hold")
    _assert(result_hold.action == "hold", "J14: action inferred as 'hold'")

    # ── J15-J17: Target = 0, existing shares → exit ──
    # target=0% = 0; target_mv=0 < tolerance AND current_shares=100 > 0 → exit
    target_exit = _make_target(target_pct=0.0)  # action="no_action" → infers
    result_exit = calculate_position_sizing(portfolio, target_exit)
    _assert(result_exit.action == "exit", "J15: action inferred as 'exit'")
    _assert(
        abs(result_exit.required_trade_value - (-15000.0)) < 0.01,
        "J16: full sell for exit = -15000",
    )
    _assert(
        abs(result_exit.cash_impact - 15000.0) < 0.01,
        "J17: cash_impact positive for exit",
    )

    # ── J18-J22: New position (ticker not in portfolio) ──
    portfolio_no_msft = _make_portfolio(
        positions=[_make_position("AAPL", 100.0, 150.0)],
        total_value=100000.0,
    )
    target_new = AllocationTarget(
        ticker="MSFT", target_allocation_pct=0.10, action="no_action"
    )
    result_new = calculate_position_sizing(
        portfolio_no_msft, target_new, current_price=300.0
    )
    _assert(result_new.current_shares == 0.0, "J18: new position current_shares = 0")
    _assert(result_new.current_market_value == 0.0, "J19: new position current_mv = 0")
    _assert(result_new.action == "add", "J20: new position action = 'add'")
    _assert(
        abs(result_new.required_trade_value - 10000.0) < 0.01,
        "J21: trade = target_mv for new position (10000)",
    )
    _assert(
        abs(result_new.required_shares - 33.33333) < 0.001,
        "J22: required_shares = 10000/300 ≈ 33.33",
    )

    # ── J23: New position without current_price → raises ──
    _assert_raises(
        ValueError,
        lambda: calculate_position_sizing(
            portfolio_no_msft,
            AllocationTarget(ticker="MSFT", target_allocation_pct=0.10),
        ),
        "J23: new position, no current_price → ValueError",
    )

    # ── J24-J25: Override current_price changes current_mv computation ──
    # With override=160: current_mv = 100*160 = 16000 (not 100*150 = 15000)
    # trade = 20000 - 16000 = 4000; required_shares = 4000/160 = 25.0
    result_override = calculate_position_sizing(portfolio, target, current_price=160.0)
    _assert(
        abs(result_override.current_market_value - 16000.0) < 0.01,
        "J24: override changes current_mv (100 * 160 = 16000)",
    )
    _assert(
        abs(result_override.required_shares - 25.0) < 0.001,
        "J25: required_shares with override = 4000/160 = 25.0",
    )

    # ── J26: cash_impact == -required_trade_value invariant ──
    _assert(
        abs(result.cash_impact + result.required_trade_value) < 0.01,
        "J26: cash_impact = -required_trade_value (invariant)",
    )

    # ── J27: Explicit target.action overrides inference ──
    target_explicit = AllocationTarget(
        ticker="AAPL", target_allocation_pct=0.20, action="hold"
    )
    result_explicit = calculate_position_sizing(portfolio, target_explicit)
    _assert(
        result_explicit.action == "hold",
        "J27: explicit target.action='hold' overrides inferred 'add'",
    )


# ── Group K: calculate_cash_released_from_trim / calculate_cash_needed_for_add

def test_k_cash_calculators():
    print("Group K: Cash calculators")

    # calculate_cash_released_from_trim
    _assert(
        calculate_cash_released_from_trim(50, 100.0) == 5000.0,
        "K1: trim 50 shares @ 100 = 5000",
    )
    _assert(
        calculate_cash_released_from_trim(0.0, 200.0) == 0.0,
        "K2: trim 0 shares = 0",
    )
    _assert(
        abs(calculate_cash_released_from_trim(33.33, 150.0) - 33.33 * 150.0) < 0.001,
        "K3: fractional shares trim",
    )
    _assert_raises(
        ValueError,
        lambda: calculate_cash_released_from_trim(-1, 100.0),
        "K4: negative shares_to_trim raises",
    )
    _assert_raises(
        ValueError,
        lambda: calculate_cash_released_from_trim(10, 0.0),
        "K5: current_price=0 raises in trim",
    )
    _assert_raises(
        ValueError,
        lambda: calculate_cash_released_from_trim(10, -50.0),
        "K6: negative price raises in trim",
    )

    # calculate_cash_needed_for_add
    _assert(
        calculate_cash_needed_for_add(100, 50.0) == 5000.0,
        "K7: add 100 shares @ 50 = 5000",
    )
    _assert(
        calculate_cash_needed_for_add(0.0, 300.0) == 0.0,
        "K8: add 0 shares = 0",
    )
    _assert(
        abs(calculate_cash_needed_for_add(33.33, 300.0) - 33.33 * 300.0) < 0.001,
        "K9: fractional shares add",
    )
    _assert_raises(
        ValueError,
        lambda: calculate_cash_needed_for_add(-1, 100.0),
        "K10: negative shares_to_add raises",
    )
    _assert_raises(
        ValueError,
        lambda: calculate_cash_needed_for_add(10, 0.0),
        "K11: current_price=0 raises in add",
    )
    _assert_raises(
        ValueError,
        lambda: calculate_cash_needed_for_add(10, -100.0),
        "K12: negative price raises in add",
    )

    # Symmetry: trim and add give same value for same inputs
    trim_cash = calculate_cash_released_from_trim(50, 200.0)
    add_cash = calculate_cash_needed_for_add(50, 200.0)
    _assert(trim_cash == add_cash, "K13: trim and add are symmetric")


# ── Group L: calculate_stop_loss_risk ────────────────────────────────────────

def test_l_stop_loss_risk():
    print("Group L: calculate_stop_loss_risk")

    portfolio = _make_portfolio(total_value=100000.0)
    rb = _make_risk_budget(max_pos_risk=0.02)  # 2% of 100000 = $2000 budget

    # ── L1-L5: within_budget ──
    # 100 shares @ 150, stop @ 140 → loss = 10 * 100 = 1000
    # portfolio_loss_pct = 1000/100000 = 1%
    # 1% < 80% of 2% = 1.6% → within_budget
    pos = _make_position(shares=100.0, current_price=150.0)
    result_within = calculate_stop_loss_risk(pos, portfolio, stop_price=140.0,
                                              risk_budget=rb)
    _assert(result_within.ticker == "AAPL", "L1: ticker correct")
    _assert(result_within.max_loss_amount == 1000.0, "L2: max_loss_amount = 1000")
    _assert(
        abs(result_within.portfolio_loss_pct - 0.01) < 1e-9,
        "L3: portfolio_loss_pct = 1%",
    )
    _assert(result_within.risk_budget_status == "within_budget", "L4: within_budget")
    _assert(
        result_within.position_market_value == 15000.0,
        "L5: position_market_value = 100 * 150 = 15000",
    )

    # ── L6-L8: near_limit ──
    # 100 shares @ 150, stop @ 132.5 → loss = 17.5 * 100 = 1750
    # portfolio_loss_pct = 1.75%
    # 80% of 2% = 1.6% <= 1.75% <= 2% → near_limit
    result_near = calculate_stop_loss_risk(pos, portfolio, stop_price=132.5, risk_budget=rb)
    _assert(result_near.max_loss_amount == 1750.0, "L6: max_loss_amount = 1750")
    _assert(
        abs(result_near.portfolio_loss_pct - 0.0175) < 1e-9,
        "L7: portfolio_loss_pct = 1.75%",
    )
    _assert(result_near.risk_budget_status == "near_limit", "L8: near_limit")

    # ── L9-L11: over_budget ──
    # 100 shares @ 150, stop @ 120 → loss = 30 * 100 = 3000
    # portfolio_loss_pct = 3% > 2% → over_budget
    result_over = calculate_stop_loss_risk(pos, portfolio, stop_price=120.0, risk_budget=rb)
    _assert(result_over.max_loss_amount == 3000.0, "L9: max_loss_amount = 3000")
    _assert(
        abs(result_over.portfolio_loss_pct - 0.03) < 1e-9,
        "L10: portfolio_loss_pct = 3%",
    )
    _assert(result_over.risk_budget_status == "over_budget", "L11: over_budget")

    # ── L12-L13: stop above current price → 0 loss ──
    result_above = calculate_stop_loss_risk(pos, portfolio, stop_price=200.0, risk_budget=rb)
    _assert(result_above.max_loss_amount == 0.0, "L12: stop above price → 0 loss")
    _assert(
        result_above.risk_budget_status == "within_budget",
        "L13: 0 loss is within_budget",
    )

    # ── L14-L18: result fields ──
    _assert(result_within.current_price == 150.0, "L14: current_price stored")
    _assert(result_within.stop_price == 140.0, "L15: stop_price stored")
    _assert(result_within.shares == 100.0, "L16: shares stored")
    _assert(
        result_within.calculation_version == "allocation_schema_v1",
        "L17: calculation_version default",
    )
    _assert(result_within.evidence_refs == [], "L18: evidence_refs defaults to empty")


# ── Group M: allocation_tool_result_from_decision_set ────────────────────────

def test_m_tool_result_adapter():
    print("Group M: allocation_tool_result_from_decision_set")

    target = _make_target()
    ds = AllocationDecisionSet(
        portfolio_id="port_001",
        as_of="2026-05-21",
        targets=[target],
    )
    tr = allocation_tool_result_from_decision_set("RUN_001", ds)

    # Shape
    _assert(tr.tool_name == "allocation_model", "M1: tool_name = 'allocation_model'")
    _assert(tr.ticker is None, "M2: ticker is None (not ticker-specific)")
    _assert("allocation_model" in tr.evidence_id, "M3: evidence_id contains tool_name")
    _assert("RUN_001" in tr.evidence_id, "M4: evidence_id contains run_id")
    _assert(tr.run_id == "RUN_001", "M5: run_id set correctly")
    _assert("calculation_version" in tr.outputs, "M6: outputs contains calculation_version")
    _assert(
        tr.outputs["calculation_version"] == "allocation_schema_v1",
        "M7: default calc version",
    )
    _assert("portfolio_id" in tr.outputs, "M8: outputs contains portfolio_id")
    _assert("targets" in tr.outputs, "M9: outputs contains targets list")
    _assert("portfolio_id" in tr.inputs, "M10: inputs contains portfolio_id")
    _assert("as_of" in tr.inputs, "M11: inputs contains as_of")
    _assert("calculation_version" in tr.inputs, "M12: inputs contains calculation_version")

    # Description
    _assert("port_001" in tr.description, "M13: description contains portfolio_id")
    _assert("1 target" in tr.description, "M14: description contains target count")

    # Determinism — same inputs → same evidence_id
    tr2 = allocation_tool_result_from_decision_set("RUN_001", ds)
    _assert(tr.evidence_id == tr2.evidence_id, "M15: deterministic evidence_id")

    # Different run_id → different evidence_id
    tr3 = allocation_tool_result_from_decision_set("RUN_002", ds)
    _assert(tr.evidence_id != tr3.evidence_id, "M16: different run_id → different id")

    # Custom target string
    tr4 = allocation_tool_result_from_decision_set("RUN_001", ds, target="client_portfolio")
    _assert(
        "client_portfolio" in tr4.evidence_id,
        "M17: custom target in evidence_id",
    )

    # Custom calculation_version
    tr5 = allocation_tool_result_from_decision_set(
        "RUN_001", ds, calculation_version="v2"
    )
    _assert(tr5.outputs["calculation_version"] == "v2", "M18: custom calc version")

    # Empty decision set
    ds_empty = AllocationDecisionSet(portfolio_id="empty_port", as_of="2026-05-21")
    tr_empty = allocation_tool_result_from_decision_set("RUN_001", ds_empty)
    _assert(tr_empty.tool_name == "allocation_model", "M19: empty ds tool_name")
    _assert(tr_empty.ticker is None, "M20: empty ds ticker is None")


# ── Group N: summarize_allocation_decision_set ────────────────────────────────

def test_n_summarize():
    print("Group N: summarize_allocation_decision_set")

    target1 = AllocationTarget(ticker="AAPL", target_allocation_pct=0.10)
    target2 = AllocationTarget(ticker="MSFT", target_allocation_pct=0.15)
    sr = _make_sizing_result(ticker="AAPL")
    slr = _make_stop_loss_result(ticker="AAPL")
    ds = AllocationDecisionSet(
        portfolio_id="port_001",
        as_of="2026-05-21",
        targets=[target1, target2],
        sizing_results=[sr],
        stop_loss_results=[slr],
        warnings=["test warning"],
    )

    summary = summarize_allocation_decision_set(ds)
    _assert(summary["portfolio_id"] == "port_001", "N1: portfolio_id in summary")
    _assert(summary["as_of"] == "2026-05-21", "N2: as_of in summary")
    _assert(summary["target_count"] == 2, "N3: target_count = 2")
    _assert(summary["sizing_result_count"] == 1, "N4: sizing_result_count = 1")
    _assert(summary["stop_loss_result_count"] == 1, "N5: stop_loss_result_count = 1")
    _assert("AAPL" in summary["tickers_targeted"], "N6: AAPL in tickers_targeted")
    _assert("MSFT" in summary["tickers_targeted"], "N7: MSFT in tickers_targeted")
    _assert("AAPL" in summary["tickers_sized"], "N8: AAPL in tickers_sized")
    _assert("AAPL" in summary["tickers_stop_loss"], "N9: AAPL in tickers_stop_loss")
    _assert(
        abs(summary["total_target_allocation_pct"] - 0.25) < 1e-9,
        "N10: total_target_allocation_pct = 0.25",
    )
    _assert(summary["warnings_count"] == 1, "N11: warnings_count = 1")

    # Empty decision set
    ds_empty = AllocationDecisionSet(portfolio_id="p", as_of="2026-05-21")
    s_empty = summarize_allocation_decision_set(ds_empty)
    _assert(s_empty["target_count"] == 0, "N12: empty ds target_count = 0")
    _assert(s_empty["total_target_allocation_pct"] == 0.0, "N13: empty ds total_pct = 0.0")
    _assert(s_empty["tickers_targeted"] == [], "N14: empty ds tickers_targeted = []")


# ── Group O: validate_portfolio_snapshot ─────────────────────────────────────

def test_o_validate_portfolio_snapshot():
    print("Group O: validate_portfolio_snapshot")

    # O1: Clean portfolio → no warnings
    pos = _make_position(shares=100.0, current_price=150.0)
    # positions=15000, cash=10000, total=25000 → sum matches
    portfolio_clean = PortfolioSnapshot(
        portfolio_id="p", as_of="2026-05-21",
        positions=[pos], cash=10000.0, total_value=25000.0,
    )
    warnings_clean = validate_portfolio_snapshot(portfolio_clean)
    _assert(len(warnings_clean) == 0, "O1: clean portfolio → no warnings")

    # O2: No positions warning
    portfolio_no_pos = PortfolioSnapshot(
        portfolio_id="p", as_of="2026-05-21",
        positions=[], cash=100000.0, total_value=100000.0,
    )
    w_no_pos = validate_portfolio_snapshot(portfolio_no_pos)
    _assert(
        any("no positions" in w.lower() for w in w_no_pos),
        "O2: no positions → warning",
    )

    # O3: Cash > total_value warning
    portfolio_cash_high = PortfolioSnapshot(
        portfolio_id="p", as_of="2026-05-21",
        positions=[pos], cash=150000.0, total_value=100000.0,
    )
    w_cash = validate_portfolio_snapshot(portfolio_cash_high)
    _assert(any("cash" in w.lower() for w in w_cash), "O3: cash > total_value → warning")

    # O4: Sum mismatch warning (15000 + 30000 = 45000 ≠ 100000, >5%)
    portfolio_mismatch = PortfolioSnapshot(
        portfolio_id="p", as_of="2026-05-21",
        positions=[pos], cash=30000.0, total_value=100000.0,
    )
    w_mismatch = validate_portfolio_snapshot(portfolio_mismatch)
    _assert(
        any("differs materially" in w for w in w_mismatch),
        "O4: sum mismatch → warning",
    )

    # O5: Duplicate ticker warning
    pos2 = _make_position(shares=50.0, current_price=150.0)
    portfolio_dup = PortfolioSnapshot(
        portfolio_id="p", as_of="2026-05-21",
        positions=[pos, pos2], cash=0.0, total_value=22500.0,
    )
    w_dup = validate_portfolio_snapshot(portfolio_dup)
    _assert(
        any("duplicate" in w.lower() for w in w_dup),
        "O5: duplicate ticker → warning",
    )

    # O6: market_value vs price mismatch warning (20000 vs 15000, >1%)
    pos_inconsistent = PositionSnapshot(
        ticker="AAPL", shares=100.0, current_price=150.0,
        as_of="2026-05-21", market_value=20000.0,
    )
    portfolio_inconsistent = PortfolioSnapshot(
        portfolio_id="p", as_of="2026-05-21",
        positions=[pos_inconsistent], cash=80000.0, total_value=100000.0,
    )
    w_mv = validate_portfolio_snapshot(portfolio_inconsistent)
    _assert(
        any("market_value" in w for w in w_mv),
        "O6: market_value vs price mismatch → warning",
    )

    # O7: Returns list of strings
    _assert(all(isinstance(w, str) for w in w_mv), "O7: all warnings are strings")

    # O8: Never raises
    try:
        validate_portfolio_snapshot(portfolio_no_pos)
        _assert(True, "O8: never raises even for empty portfolio")
    except Exception:
        _assert(False, "O8: never raises even for empty portfolio")


# ── Group P: validate_allocation_decision_set ────────────────────────────────

def test_p_validate_allocation_decision_set():
    print("Group P: validate_allocation_decision_set")

    ev = EvidenceRef(evidence_id="ev_001", tool_name="valuation_model")

    # P1: No sizing results → warning
    ds_no_sr = AllocationDecisionSet(portfolio_id="p", as_of="2026-05-21")
    w_no_sr = validate_allocation_decision_set(ds_no_sr)
    _assert(
        any("no sizing_results" in w.lower() or "no sizing" in w.lower()
            for w in w_no_sr),
        "P1: no sizing_results → warning",
    )

    # P2: With sizing results → no sizing-results warning
    sr_with_ev = _make_sizing_result(evidence_refs=[ev])
    ds_with_sr = AllocationDecisionSet(
        portfolio_id="p", as_of="2026-05-21", sizing_results=[sr_with_ev]
    )
    w_with_sr = validate_allocation_decision_set(ds_with_sr)
    _assert(
        not any("no sizing" in w.lower() for w in w_with_sr),
        "P2: sizing results present → no sizing-results warning",
    )

    # P3: Duplicate ticker in targets → warning
    t1 = AllocationTarget(ticker="AAPL", target_allocation_pct=0.10)
    t2 = AllocationTarget(ticker="AAPL", target_allocation_pct=0.05)
    ds_dup = AllocationDecisionSet(
        portfolio_id="p", as_of="2026-05-21", targets=[t1, t2]
    )
    w_dup = validate_allocation_decision_set(ds_dup)
    _assert(
        any("duplicate" in w.lower() for w in w_dup),
        "P3: duplicate target ticker → warning",
    )

    # P4: Target with no evidence_refs → warning
    t_no_ev = AllocationTarget(ticker="AAPL", target_allocation_pct=0.10)
    ds_no_ev = AllocationDecisionSet(
        portfolio_id="p", as_of="2026-05-21", targets=[t_no_ev]
    )
    w_no_ev = validate_allocation_decision_set(ds_no_ev)
    _assert(
        any("no evidence_refs" in w for w in w_no_ev),
        "P4: target with no evidence_refs → warning",
    )

    # P5: Target WITH evidence_refs → no evidence warning for that target
    t_with_ev = AllocationTarget(
        ticker="AAPL", target_allocation_pct=0.10, evidence_refs=[ev]
    )
    ds_ok_ev = AllocationDecisionSet(
        portfolio_id="p", as_of="2026-05-21",
        targets=[t_with_ev], sizing_results=[sr_with_ev],
    )
    w_ok_ev = validate_allocation_decision_set(ds_ok_ev)
    _assert(
        not any("AllocationTarget" in w and "no evidence_refs" in w
                for w in w_ok_ev),
        "P5: target with evidence_refs → no target-evidence warning",
    )

    # P6: Sizing result with no evidence_refs → warning
    sr_no_ev = _make_sizing_result(evidence_refs=[])
    ds_sr_no_ev = AllocationDecisionSet(
        portfolio_id="p", as_of="2026-05-21", sizing_results=[sr_no_ev]
    )
    w_sr_no_ev = validate_allocation_decision_set(ds_sr_no_ev)
    _assert(
        any("PositionSizingResult" in w and "no evidence_refs" in w
            for w in w_sr_no_ev),
        "P6: sizing result with no evidence_refs → warning",
    )

    # P7: Over-budget stop-loss → warning
    slr_over = _make_stop_loss_result(status="over_budget")
    ds_over = AllocationDecisionSet(
        portfolio_id="p", as_of="2026-05-21", stop_loss_results=[slr_over]
    )
    w_over = validate_allocation_decision_set(ds_over)
    _assert(
        any("over_budget" in w for w in w_over),
        "P7: over-budget stop-loss → warning",
    )

    # P8: Target allocation exceeds risk_budget.max_position_allocation_pct → warning
    rb_with_max = RiskBudget(
        max_single_position_risk_pct=0.02,
        max_sector_allocation_pct=0.30,
        max_cash_pct=0.20,
        max_position_allocation_pct=0.10,
    )
    t_big = AllocationTarget(ticker="AAPL", target_allocation_pct=0.20)
    ds_big = AllocationDecisionSet(
        portfolio_id="p", as_of="2026-05-21",
        risk_budget=rb_with_max, targets=[t_big],
    )
    w_big = validate_allocation_decision_set(ds_big)
    _assert(
        any("max_position_allocation_pct" in w for w in w_big),
        "P8: target exceeds max_position_allocation_pct → warning",
    )

    # P9: Returns list of strings
    _assert(all(isinstance(w, str) for w in w_no_sr), "P9: all warnings are strings")

    # P10: Never raises
    try:
        validate_allocation_decision_set(
            AllocationDecisionSet(portfolio_id="p", as_of="2026-05-21")
        )
        _assert(True, "P10: never raises")
    except Exception:
        _assert(False, "P10: never raises")


# ── Group Q: Serialization roundtrip ─────────────────────────────────────────

def test_q_serialization_roundtrip():
    print("Group Q: Serialization roundtrip")

    # PositionSnapshot — dict roundtrip
    pos = PositionSnapshot(
        ticker="AAPL", shares=100.0, current_price=150.0,
        as_of="2026-05-21", direction="long", cost_basis=120.0,
        metadata={"sector": "tech"},
    )
    d = pos.model_dump()
    pos2 = PositionSnapshot.model_validate(d)
    _assert(pos2.ticker == pos.ticker, "Q1: PositionSnapshot ticker roundtrip")
    _assert(pos2.current_price == pos.current_price, "Q2: current_price roundtrip")
    _assert(pos2.as_of == pos.as_of, "Q3: as_of roundtrip")

    # PositionSnapshot — JSON roundtrip
    json_str = pos.model_dump_json()
    pos3 = PositionSnapshot.model_validate_json(json_str)
    _assert(pos3.ticker == pos.ticker, "Q4: PositionSnapshot JSON roundtrip")

    # PortfolioSnapshot
    portfolio = _make_portfolio()
    pd = portfolio.model_dump()
    portfolio2 = PortfolioSnapshot.model_validate(pd)
    _assert(portfolio2.portfolio_id == portfolio.portfolio_id,
            "Q5: PortfolioSnapshot portfolio_id roundtrip")
    _assert(len(portfolio2.positions) == len(portfolio.positions),
            "Q6: positions count preserved")

    # AllocationTarget
    target = AllocationTarget(
        ticker="MSFT", target_allocation_pct=0.10,
        min_allocation_pct=0.05, max_allocation_pct=0.15, action="add",
    )
    td = target.model_dump()
    target2 = AllocationTarget.model_validate(td)
    _assert(target2.ticker == target.ticker, "Q7: AllocationTarget ticker roundtrip")
    _assert(target2.min_allocation_pct == target.min_allocation_pct,
            "Q8: min_allocation_pct roundtrip")
    _assert(target2.max_allocation_pct == target.max_allocation_pct,
            "Q9: max_allocation_pct roundtrip")

    # AllocationDecisionSet
    ds = AllocationDecisionSet(
        portfolio_id="port_001", as_of="2026-05-21",
        targets=[target], notes=["test"], warnings=["w1"],
    )
    dsd = ds.model_dump()
    ds2 = AllocationDecisionSet.model_validate(dsd)
    _assert(ds2.portfolio_id == ds.portfolio_id, "Q10: AllocationDecisionSet roundtrip")
    _assert(len(ds2.targets) == 1, "Q11: targets preserved")
    _assert(ds2.notes == ["test"], "Q12: notes preserved")

    # PositionSizingResult — JSON roundtrip
    sr = _make_sizing_result()
    sr_json = sr.model_dump_json()
    sr2 = PositionSizingResult.model_validate_json(sr_json)
    _assert(sr2.ticker == sr.ticker, "Q13: PositionSizingResult ticker roundtrip")
    _assert(sr2.current_price == sr.current_price,
            "Q14: PositionSizingResult current_price roundtrip")

    # StopLossRiskResult — JSON roundtrip
    slr = _make_stop_loss_result()
    slr_json = slr.model_dump_json()
    slr2 = StopLossRiskResult.model_validate_json(slr_json)
    _assert(slr2.ticker == slr.ticker, "Q15: StopLossRiskResult ticker roundtrip")
    _assert(slr2.position_market_value == slr.position_market_value,
            "Q16: position_market_value roundtrip")

    # RiskBudget — dict roundtrip
    rb = _make_risk_budget()
    rb_dict = rb.model_dump()
    rb2 = RiskBudget.model_validate(rb_dict)
    _assert(
        rb2.max_single_position_risk_pct == rb.max_single_position_risk_pct,
        "Q17: RiskBudget roundtrip",
    )


# ── Group R: No forbidden modules imported ────────────────────────────────────

def test_r_no_forbidden_modules():
    print("Group R: No forbidden modules imported")

    forbidden_live = [
        "app",
        "streamlit",
        "lib.llm_orchestrator",
        "lib.valuation",
        "lib.technical",
        "lib.rotation",
        "lib.data_fetcher",
        "lib.workflow_state",
        "lib.cache_manager",
        "pages",
    ]
    for mod in forbidden_live:
        _assert(mod not in sys.modules, f"R-live: '{mod}' not imported")

    forbidden_network = [
        "requests",
        "urllib.request",
        "httpx",
        "aiohttp",
    ]
    for mod in forbidden_network:
        _assert(mod not in sys.modules, f"R-net: '{mod}' not imported")

    # lib.reliability.allocation loaded cleanly
    _assert(
        "lib.reliability.allocation" in sys.modules,
        "R-import: lib.reliability.allocation is loaded",
    )

    # __init__.py re-exports all allocation symbols
    import lib.reliability as rel
    _assert(hasattr(rel, "AllocationAction"), "R-init: AllocationAction exported")
    _assert(hasattr(rel, "PositionSnapshot"), "R-init: PositionSnapshot exported")
    _assert(hasattr(rel, "PortfolioSnapshot"), "R-init: PortfolioSnapshot exported")
    _assert(hasattr(rel, "AllocationTarget"), "R-init: AllocationTarget exported")
    _assert(hasattr(rel, "RiskBudget"), "R-init: RiskBudget exported")
    _assert(hasattr(rel, "PositionSizingResult"), "R-init: PositionSizingResult exported")
    _assert(hasattr(rel, "StopLossRiskResult"), "R-init: StopLossRiskResult exported")
    _assert(hasattr(rel, "AllocationDecisionSet"), "R-init: AllocationDecisionSet exported")
    _assert(hasattr(rel, "calculate_position_sizing"),
            "R-init: calculate_position_sizing exported")
    _assert(hasattr(rel, "calculate_stop_loss_risk"),
            "R-init: calculate_stop_loss_risk exported")
    _assert(hasattr(rel, "allocation_tool_result_from_decision_set"),
            "R-init: adapter exported")
    _assert(hasattr(rel, "validate_portfolio_snapshot"),
            "R-init: validate_portfolio_snapshot exported")
    _assert(hasattr(rel, "validate_allocation_decision_set"),
            "R-init: validate_allocation_decision_set exported")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    groups = [
        test_a_literal_aliases,
        test_b_position_snapshot,
        test_c_portfolio_snapshot,
        test_d_allocation_target,
        test_e_risk_budget,
        test_f_result_models,
        test_g_allocation_decision_set,
        test_h_compute_market_value,
        test_i_compute_allocation_pct,
        test_j_calculate_position_sizing,
        test_k_cash_calculators,
        test_l_stop_loss_risk,
        test_m_tool_result_adapter,
        test_n_summarize,
        test_o_validate_portfolio_snapshot,
        test_p_validate_allocation_decision_set,
        test_q_serialization_roundtrip,
        test_r_no_forbidden_modules,
    ]

    for fn in groups:
        try:
            fn()
        except Exception:
            print(f"  ERROR in {fn.__name__}:")
            traceback.print_exc()

    print()
    print(f"Results: {_PASS} passed, {_FAIL} failed")
    if _FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
