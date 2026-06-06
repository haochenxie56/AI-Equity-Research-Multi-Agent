"""
scripts/test_reliability_options.py

Test suite for lib/reliability/options.py — Phase 2E (updated contract):
Option Data + Strategy Tool Schema Foundation.

Tests the contract-aware API with underlying/expiration naming,
contract-based calculators, and aggregate liquidity/event-risk assessments.

Run:
    python scripts/test_reliability_options.py

Expected: all assertions pass, 0 failures.
"""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.reliability.options import (
    # Literal aliases
    OptionType,
    OptionPositionSide,
    OptionStrategyType,
    OptionLiquidityStatus,
    OptionEventRiskLevel,
    OptionTradeExpression,
    # Models
    OptionContractSnapshot,
    OptionChainSnapshot,
    OptionLeg,
    OptionStrategyCandidate,
    OptionPayoffResult,
    OptionLiquidityCheck,
    OptionEventRiskCheck,
    OptionStrategyDecisionSet,
    # Calculators
    option_mid_price,
    option_leg_premium,
    calculate_long_call_payoff,
    calculate_long_put_payoff,
    calculate_call_debit_spread_payoff,
    calculate_put_debit_spread_payoff,
    calculate_cash_secured_put_payoff,
    calculate_covered_call_payoff,
    calculate_option_liquidity,
    assess_option_event_risk,
    # Adapter / helpers
    option_strategy_tool_result_from_decision_set,
    summarize_option_strategy_decision_set,
    validate_option_strategy_decision_set,
)

_PASS = 0
_FAIL = 0


def _check(label: str, condition: bool) -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {label}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_call(
    underlying="AAPL",
    strike=150.0,
    expiration="2026-06-20",
    bid=1.50,
    ask=1.70,
    mid=None,
    volume=None,
    open_interest=None,
    as_of="2026-05-21",
    source="synthetic",
) -> OptionContractSnapshot:
    return OptionContractSnapshot(
        underlying=underlying,
        option_type="call",
        strike=strike,
        expiration=expiration,
        bid=bid,
        ask=ask,
        mid=mid,
        volume=volume,
        open_interest=open_interest,
        as_of=as_of,
        source=source,
    )


def _make_put(
    underlying="AAPL",
    strike=140.0,
    expiration="2026-06-20",
    bid=1.20,
    ask=1.40,
    mid=None,
    volume=None,
    open_interest=None,
    as_of="2026-05-21",
) -> OptionContractSnapshot:
    return OptionContractSnapshot(
        underlying=underlying,
        option_type="put",
        strike=strike,
        expiration=expiration,
        bid=bid,
        ask=ask,
        mid=mid,
        volume=volume,
        open_interest=open_interest,
        as_of=as_of,
    )


def _make_chain(
    underlying="AAPL",
    underlying_price=155.0,
    contracts=None,
    as_of="2026-05-21",
) -> OptionChainSnapshot:
    return OptionChainSnapshot(
        underlying=underlying,
        underlying_price=underlying_price,
        contracts=contracts or [],
        as_of=as_of,
    )


def _make_ds(
    underlying="AAPL",
    as_of="2026-05-21",
    chain_snapshot=None,
    candidates=None,
    payoff_results=None,
    liquidity_checks=None,
    event_risk_checks=None,
) -> OptionStrategyDecisionSet:
    return OptionStrategyDecisionSet(
        underlying=underlying,
        as_of=as_of,
        chain_snapshot=chain_snapshot,
        candidates=candidates or [],
        payoff_results=payoff_results or [],
        liquidity_checks=liquidity_checks or [],
        event_risk_checks=event_risk_checks or [],
    )


# ===========================================================================
# Group A: Literal aliases
# ===========================================================================
print("A: Literal aliases")

_check("A1  OptionType has 'call' and 'put'",
       "call" in OptionType.__args__ and "put" in OptionType.__args__)
_check("A2  OptionType exactly 2 values", len(OptionType.__args__) == 2)
_check("A3  OptionPositionSide has 'long' and 'short'",
       "long" in OptionPositionSide.__args__ and "short" in OptionPositionSide.__args__)
_check("A4  OptionStrategyType has >= 10 values",
       len(OptionStrategyType.__args__) >= 10)
_check("A5  OptionStrategyType has 'no_trade'",
       "no_trade" in OptionStrategyType.__args__)
_check("A6  OptionLiquidityStatus has exactly 4 values",
       len(OptionLiquidityStatus.__args__) == 4)
_check("A7  OptionEventRiskLevel has 'low', 'medium', 'high', 'unknown'",
       set(OptionEventRiskLevel.__args__) == {"low", "medium", "high", "unknown"})
_check("A8  OptionTradeExpression has 'undetermined'",
       "undetermined" in OptionTradeExpression.__args__)


# ===========================================================================
# Group B: OptionContractSnapshot
# ===========================================================================
print("B: OptionContractSnapshot")

c_call = OptionContractSnapshot(
    underlying="AAPL", option_type="call", expiration="2026-06-20",
    strike=150.0, bid=1.50, ask=1.70, mid=1.65, volume=200,
    open_interest=1000, implied_volatility=0.28, delta=0.45,
    gamma=0.02, theta=-0.05, vega=0.15, as_of="2026-05-21",
)
_check("B1  underlying set", c_call.underlying == "AAPL")
_check("B2  option_type call", c_call.option_type == "call")
_check("B3  expiration set", c_call.expiration == "2026-06-20")
_check("B4  strike set", c_call.strike == 150.0)
_check("B5  bid set", c_call.bid == 1.50)
_check("B6  ask set", c_call.ask == 1.70)
_check("B7  mid set (optional field)", c_call.mid == 1.65)
_check("B8  volume set", c_call.volume == 200)
_check("B9  open_interest set", c_call.open_interest == 1000)
_check("B10 implied_volatility set", c_call.implied_volatility == 0.28)
_check("B11 delta set", c_call.delta == 0.45)
_check("B12 gamma set", c_call.gamma == 0.02)
_check("B13 theta set", c_call.theta == -0.05)
_check("B14 vega set", c_call.vega == 0.15)
_check("B15 source defaults to 'synthetic'", c_call.source == "synthetic")
_check("B16 metadata defaults to {}", c_call.metadata == {})

c_put = _make_put()
_check("B17 valid put contract", c_put.option_type == "put")

# Rejects empty underlying
try:
    OptionContractSnapshot(underlying="", option_type="call", expiration="2026-06-20",
                           strike=150.0, bid=1.0, ask=1.5, as_of="2026-05-21")
    _check("B18 rejects empty underlying", False)
except Exception:
    _check("B18 rejects empty underlying", True)

# Rejects whitespace-only underlying
try:
    OptionContractSnapshot(underlying="  ", option_type="call", expiration="2026-06-20",
                           strike=150.0, bid=1.0, ask=1.5, as_of="2026-05-21")
    _check("B19 rejects whitespace underlying", False)
except Exception:
    _check("B19 rejects whitespace underlying", True)

# Rejects invalid option_type
try:
    OptionContractSnapshot(underlying="AAPL", option_type="future",  # type: ignore
                           expiration="2026-06-20", strike=150.0,
                           bid=1.0, ask=1.5, as_of="2026-05-21")
    _check("B20 rejects invalid option_type", False)
except Exception:
    _check("B20 rejects invalid option_type", True)

# Rejects non-positive strike
try:
    _make_call(strike=0.0)
    _check("B21 rejects strike=0", False)
except Exception:
    _check("B21 rejects strike=0", True)

# Rejects negative bid
try:
    _make_call(bid=-1.0)
    _check("B22 rejects negative bid", False)
except Exception:
    _check("B22 rejects negative bid", True)

# Rejects ask below bid
try:
    _make_call(bid=2.0, ask=1.0)
    _check("B23 rejects ask < bid", False)
except Exception:
    _check("B23 rejects ask < bid", True)

# Rejects empty expiration
try:
    OptionContractSnapshot(underlying="AAPL", option_type="call", expiration="",
                           strike=150.0, bid=1.0, ask=1.5, as_of="2026-05-21")
    _check("B24 rejects empty expiration", False)
except Exception:
    _check("B24 rejects empty expiration", True)

# Rejects empty as_of
try:
    OptionContractSnapshot(underlying="AAPL", option_type="call", expiration="2026-06-20",
                           strike=150.0, bid=1.0, ask=1.5, as_of="")
    _check("B25 rejects empty as_of", False)
except Exception:
    _check("B25 rejects empty as_of", True)

# Rejects empty source
try:
    OptionContractSnapshot(underlying="AAPL", option_type="call", expiration="2026-06-20",
                           strike=150.0, bid=1.0, ask=1.5, as_of="2026-05-21", source="")
    _check("B26 rejects empty source", False)
except Exception:
    _check("B26 rejects empty source", True)

# Rejects negative mid
try:
    _make_call(mid=-0.5)
    _check("B27 rejects negative mid", False)
except Exception:
    _check("B27 rejects negative mid", True)

# Rejects negative volume
try:
    _make_call(volume=-1)
    _check("B28 rejects negative volume", False)
except Exception:
    _check("B28 rejects negative volume", True)

# Rejects negative open_interest
try:
    _make_call(open_interest=-1)
    _check("B29 rejects negative open_interest", False)
except Exception:
    _check("B29 rejects negative open_interest", True)


# ===========================================================================
# Group C: OptionChainSnapshot
# ===========================================================================
print("C: OptionChainSnapshot")

c1 = _make_call()
c2 = _make_put()
chain = OptionChainSnapshot(
    underlying="AAPL",
    underlying_price=155.0,
    expirations=["2026-06-20", "2026-07-18"],
    contracts=[c1, c2],
    as_of="2026-05-21",
    snapshot_id="AAPL_CHAIN_001",
)
_check("C1  underlying set", chain.underlying == "AAPL")
_check("C2  underlying_price > 0 accepted", chain.underlying_price == 155.0)
_check("C3  expirations list", chain.expirations == ["2026-06-20", "2026-07-18"])
_check("C4  contracts carried", len(chain.contracts) == 2)
_check("C5  snapshot_id (optional) set", chain.snapshot_id == "AAPL_CHAIN_001")

# Rejects non-positive underlying_price
try:
    OptionChainSnapshot(underlying="AAPL", underlying_price=0.0, as_of="2026-05-21")
    _check("C6  rejects underlying_price=0", False)
except Exception:
    _check("C6  rejects underlying_price=0", True)

try:
    OptionChainSnapshot(underlying="AAPL", underlying_price=-10.0, as_of="2026-05-21")
    _check("C7  rejects negative underlying_price", False)
except Exception:
    _check("C7  rejects negative underlying_price", True)

# Empty chain accepted
chain_empty = OptionChainSnapshot(underlying="AAPL", underlying_price=155.0, as_of="2026-05-21")
_check("C8  empty contracts allowed", chain_empty.contracts == [])


# ===========================================================================
# Group D: OptionLeg
# ===========================================================================
print("D: OptionLeg")

c_for_leg = _make_call(bid=1.50, ask=1.70)

# Explicit premium overrides contract mid
leg_explicit = OptionLeg(contract=c_for_leg, side="long", quantity=1, premium=2.50)
_check("D1  explicit premium overrides mid",
       abs(option_leg_premium(leg_explicit) - 2.50) < 1e-9)

# Missing premium falls back to contract mid
leg_no_prem = OptionLeg(contract=c_for_leg, side="short", quantity=2)
mid_expected = (1.50 + 1.70) / 2  # 1.60
_check("D2  missing premium falls back to contract mid",
       abs(option_leg_premium(leg_no_prem) - mid_expected) < 1e-9)

# Rejects quantity=0
try:
    OptionLeg(contract=c_for_leg, side="long", quantity=0)
    _check("D3  rejects quantity=0", False)
except Exception:
    _check("D3  rejects quantity=0", True)

# Rejects negative premium
try:
    OptionLeg(contract=c_for_leg, side="long", quantity=1, premium=-0.5)
    _check("D4  rejects negative premium", False)
except Exception:
    _check("D4  rejects negative premium", True)

# Default quantity=1
leg_default = OptionLeg(contract=c_for_leg, side="long")
_check("D5  default quantity=1", leg_default.quantity == 1)
_check("D6  default premium=None", leg_default.premium is None)


# ===========================================================================
# Group E: option_mid_price
# ===========================================================================
print("E: option_mid_price")

# Uses provided contract.mid
c_with_mid = _make_call(bid=1.50, ask=1.70, mid=1.65)
_check("E1  uses provided contract.mid",
       abs(option_mid_price(c_with_mid) - 1.65) < 1e-9)

# Falls back to (bid + ask) / 2 when mid is None
c_no_mid = _make_call(bid=1.50, ask=1.70, mid=None)
_check("E2  falls back to (bid+ask)/2 when mid is None",
       abs(option_mid_price(c_no_mid) - 1.60) < 1e-9)

# Deterministic
_check("E3  deterministic",
       option_mid_price(c_no_mid) == option_mid_price(c_no_mid))

# bid=ask=0 → mid=0
c_zero = _make_call(bid=0.0, ask=0.0)
_check("E4  bid=ask=0 → mid=0", option_mid_price(c_zero) == 0.0)


# ===========================================================================
# Group F: Long call payoff
# ===========================================================================
print("F: Long call payoff")

call_c = _make_call(strike=150.0, bid=2.80, ask=3.20)  # mid = 3.0

# With explicit premium
lc = calculate_long_call_payoff(call_c, premium=3.0, contracts=1)
_check("F1  strategy_type is long_call", lc.strategy_type == "long_call")
_check("F2  underlying = contract.underlying", lc.underlying == "AAPL")
_check("F3  net_premium = 3.0 × 1 × 100 = 300 (debit)",
       abs(lc.net_premium - 300.0) < 1e-9)
_check("F4  max_loss = net_premium = 300",
       abs(lc.max_loss - 300.0) < 1e-9)
_check("F5  max_gain = None (unlimited)", lc.max_gain is None)
_check("F6  breakeven = strike + premium = 153.0",
       abs(lc.breakeven - 153.0) < 1e-9)
_check("F7  notes include unlimited upside",
       any("unlimited" in n.lower() for n in lc.notes))

# Uses contract mid when premium not provided
lc_mid = calculate_long_call_payoff(call_c)  # mid = 3.0
_check("F8  uses contract mid when premium not given",
       abs(lc_mid.net_premium - 300.0) < 1e-9)

# 2 contracts
lc2 = calculate_long_call_payoff(call_c, premium=3.0, contracts=2)
_check("F9  net_premium for 2 contracts = 600",
       abs(lc2.net_premium - 600.0) < 1e-9)

# Rejects put contract
put_c = _make_put(strike=140.0)
try:
    calculate_long_call_payoff(put_c)
    _check("F10 rejects put contract", False)
except ValueError:
    _check("F10 rejects put contract", True)

# Rejects contracts=0
try:
    calculate_long_call_payoff(call_c, contracts=0)
    _check("F11 rejects contracts=0", False)
except ValueError:
    _check("F11 rejects contracts=0", True)


# ===========================================================================
# Group G: Long put payoff
# ===========================================================================
print("G: Long put payoff")

put_c = _make_put(strike=150.0, bid=2.80, ask=3.20)  # mid = 3.0

lp = calculate_long_put_payoff(put_c, premium=3.0, contracts=1)
_check("G1  strategy_type is long_put", lp.strategy_type == "long_put")
_check("G2  underlying = contract.underlying", lp.underlying == "AAPL")
_check("G3  net_premium = 300 (debit)", abs(lp.net_premium - 300.0) < 1e-9)
_check("G4  max_loss = 300", abs(lp.max_loss - 300.0) < 1e-9)
_check("G5  max_gain = (150-3)×1×100 = 14700",
       abs(lp.max_gain - 14700.0) < 1e-9)
_check("G6  breakeven = 150 - 3 = 147",
       abs(lp.breakeven - 147.0) < 1e-9)
_check("G7  risk_reward = 14700/300 = 49",
       abs(lp.risk_reward_ratio - 49.0) < 1e-6)

# Uses contract mid when premium not provided
lp_mid = calculate_long_put_payoff(put_c)  # mid = 3.0
_check("G8  uses contract mid when premium not given",
       abs(lp_mid.net_premium - 300.0) < 1e-9)

# Rejects call contract
call_c_g = _make_call(strike=150.0)
try:
    calculate_long_put_payoff(call_c_g)
    _check("G9  rejects call contract", False)
except ValueError:
    _check("G9  rejects call contract", True)


# ===========================================================================
# Group H: Call debit spread payoff
# ===========================================================================
print("H: Call debit spread payoff")

long_call = _make_call(underlying="AAPL", strike=145.0, expiration="2026-06-20",
                       bid=4.80, ask=5.20)  # mid = 5.0
short_call = _make_call(underlying="AAPL", strike=155.0, expiration="2026-06-20",
                        bid=1.80, ask=2.20)  # mid = 2.0

cds = calculate_call_debit_spread_payoff(long_call, short_call,
                                          long_premium=5.0, short_premium=2.0, contracts=1)
_check("H1  strategy_type is call_debit_spread", cds.strategy_type == "call_debit_spread")
_check("H2  underlying set", cds.underlying == "AAPL")
_check("H3  net_premium = (5-2)×1×100 = 300 (debit)",
       abs(cds.net_premium - 300.0) < 1e-9)
_check("H4  max_loss = 300", abs(cds.max_loss - 300.0) < 1e-9)
_check("H5  max_gain = (10-3)×1×100 = 700",
       abs(cds.max_gain - 700.0) < 1e-9)
_check("H6  breakeven = 145 + 3 = 148",
       abs(cds.breakeven - 148.0) < 1e-9)
_check("H7  risk_reward = 700/300 ≈ 2.333",
       abs(cds.risk_reward_ratio - 700.0/300.0) < 1e-6)

# Uses contract mids when no premium override
cds_mid = calculate_call_debit_spread_payoff(long_call, short_call)  # 5.0 - 2.0 = 3.0
_check("H8  uses contract mids when no premium override",
       abs(cds_mid.net_premium - 300.0) < 1e-9)

# Rejects put as long_call
put_for_spread = _make_put(underlying="AAPL", strike=145.0, expiration="2026-06-20")
try:
    calculate_call_debit_spread_payoff(put_for_spread, short_call)
    _check("H9  rejects put as long_call", False)
except ValueError:
    _check("H9  rejects put as long_call", True)

# Rejects put as short_call
try:
    calculate_call_debit_spread_payoff(long_call, put_for_spread)
    _check("H10 rejects put as short_call", False)
except ValueError:
    _check("H10 rejects put as short_call", True)

# Rejects wrong strike order (short <= long)
short_lower = _make_call(underlying="AAPL", strike=140.0, expiration="2026-06-20")
try:
    calculate_call_debit_spread_payoff(long_call, short_lower)
    _check("H11 rejects short_strike <= long_strike", False)
except ValueError:
    _check("H11 rejects short_strike <= long_strike", True)

# Rejects mismatched underlying
call_msft = _make_call(underlying="MSFT", strike=155.0, expiration="2026-06-20")
try:
    calculate_call_debit_spread_payoff(long_call, call_msft)
    _check("H12 rejects mismatched underlying", False)
except ValueError:
    _check("H12 rejects mismatched underlying", True)

# Rejects mismatched expiration
call_diff_exp = _make_call(underlying="AAPL", strike=155.0, expiration="2026-07-18")
try:
    calculate_call_debit_spread_payoff(long_call, call_diff_exp)
    _check("H13 rejects mismatched expiration", False)
except ValueError:
    _check("H13 rejects mismatched expiration", True)


# ===========================================================================
# Group I: Put debit spread payoff
# ===========================================================================
print("I: Put debit spread payoff")

long_put = _make_put(underlying="AAPL", strike=155.0, expiration="2026-06-20",
                     bid=4.80, ask=5.20)  # mid = 5.0
short_put = _make_put(underlying="AAPL", strike=145.0, expiration="2026-06-20",
                      bid=1.80, ask=2.20)  # mid = 2.0

pds = calculate_put_debit_spread_payoff(long_put, short_put,
                                         long_premium=5.0, short_premium=2.0, contracts=1)
_check("I1  strategy_type is put_debit_spread", pds.strategy_type == "put_debit_spread")
_check("I2  underlying set", pds.underlying == "AAPL")
_check("I3  net_premium = (5-2)×1×100 = 300 (debit)",
       abs(pds.net_premium - 300.0) < 1e-9)
_check("I4  max_loss = 300", abs(pds.max_loss - 300.0) < 1e-9)
_check("I5  max_gain = (10-3)×1×100 = 700",
       abs(pds.max_gain - 700.0) < 1e-9)
_check("I6  breakeven = 155 - 3 = 152",
       abs(pds.breakeven - 152.0) < 1e-9)
_check("I7  risk_reward = 700/300 ≈ 2.333",
       abs(pds.risk_reward_ratio - 700.0/300.0) < 1e-6)

# Rejects call as long_put
try:
    calculate_put_debit_spread_payoff(_make_call(strike=155.0), short_put)
    _check("I8  rejects call as long_put", False)
except ValueError:
    _check("I8  rejects call as long_put", True)

# Rejects wrong strike order (long <= short)
try:
    calculate_put_debit_spread_payoff(short_put, long_put)  # strikes reversed
    _check("I9  rejects long_strike <= short_strike", False)
except ValueError:
    _check("I9  rejects long_strike <= short_strike", True)

# Rejects mismatched underlying
put_msft = _make_put(underlying="MSFT", strike=145.0, expiration="2026-06-20")
try:
    calculate_put_debit_spread_payoff(long_put, put_msft)
    _check("I10 rejects mismatched underlying", False)
except ValueError:
    _check("I10 rejects mismatched underlying", True)

# Rejects mismatched expiration
put_diff_exp = _make_put(underlying="AAPL", strike=145.0, expiration="2026-07-18")
try:
    calculate_put_debit_spread_payoff(long_put, put_diff_exp)
    _check("I11 rejects mismatched expiration", False)
except ValueError:
    _check("I11 rejects mismatched expiration", True)


# ===========================================================================
# Group J: Cash-secured put payoff
# ===========================================================================
print("J: Cash-secured put payoff")

csp_put = _make_put(underlying="AAPL", strike=150.0, bid=2.80, ask=3.20)  # mid=3.0

csp = calculate_cash_secured_put_payoff(csp_put, premium=3.0, contracts=1)
_check("J1  strategy_type is cash_secured_put", csp.strategy_type == "cash_secured_put")
_check("J2  net_premium = -300 (credit received)",
       abs(csp.net_premium - (-300.0)) < 1e-9)
_check("J3  max_gain = 300", abs(csp.max_gain - 300.0) < 1e-9)
_check("J4  max_loss = (150-3)×100 = 14700",
       abs(csp.max_loss - 14700.0) < 1e-9)
_check("J5  breakeven = 150 - 3 = 147",
       abs(csp.breakeven - 147.0) < 1e-9)
_check("J6  cash_required = 150×1×100 = 15000",
       abs(csp.cash_required - 15000.0) < 1e-9)
_check("J7  collateral_required = cash_required",
       abs(csp.collateral_required - csp.cash_required) < 1e-9)
_check("J8  risk_reward_ratio = 300/14700",
       abs(csp.risk_reward_ratio - 300.0/14700.0) < 1e-9)

# Uses contract mid when no premium override
csp_mid = calculate_cash_secured_put_payoff(csp_put)  # mid = 3.0
_check("J9  uses contract mid when no premium override",
       abs(csp_mid.net_premium - (-300.0)) < 1e-9)

# Rejects call contract
try:
    calculate_cash_secured_put_payoff(_make_call(strike=150.0))
    _check("J10 rejects call contract", False)
except ValueError:
    _check("J10 rejects call contract", True)


# ===========================================================================
# Group K: Covered call payoff
# ===========================================================================
print("K: Covered call payoff")

cc_call = _make_call(underlying="AAPL", strike=155.0, bid=2.80, ask=3.20)  # mid=3.0

# With stock_cost_basis
cc = calculate_covered_call_payoff(
    cc_call, shares_owned=100, stock_cost_basis=145.0, premium=3.0, contracts=1,
)
_check("K1  strategy_type is covered_call", cc.strategy_type == "covered_call")
_check("K2  net_premium = -300 (credit received)",
       abs(cc.net_premium - (-300.0)) < 1e-9)
_check("K3  max_gain = max(155-145,0)×100 + 300 = 1300",
       abs(cc.max_gain - 1300.0) < 1e-9)
_check("K4  max_loss = max(145-3,0)×100 = 14200",
       abs(cc.max_loss - 14200.0) < 1e-9)
_check("K5  breakeven = 145 - 3 = 142",
       abs(cc.breakeven - 142.0) < 1e-9)
_check("K6  notes include capped upside",
       any("capped" in n.lower() for n in cc.notes))

# Without stock_cost_basis — max_gain/max_loss/breakeven are None
cc_no_basis = calculate_covered_call_payoff(
    cc_call, shares_owned=100, stock_cost_basis=None, premium=3.0, contracts=1,
)
_check("K7  max_gain=None without cost_basis", cc_no_basis.max_gain is None)
_check("K8  max_loss=None without cost_basis", cc_no_basis.max_loss is None)
_check("K9  breakeven=None without cost_basis", cc_no_basis.breakeven is None)

# Rejects put contract
try:
    calculate_covered_call_payoff(_make_put(strike=155.0), shares_owned=100)
    _check("K10 rejects put contract", False)
except ValueError:
    _check("K10 rejects put contract", True)

# Rejects insufficient shares
try:
    calculate_covered_call_payoff(cc_call, shares_owned=50, contracts=1)
    _check("K11 rejects shares_owned < contracts×100", False)
except ValueError:
    _check("K11 rejects shares_owned < contracts×100", True)

# Uses contract mid when no premium override
cc_mid = calculate_covered_call_payoff(cc_call, shares_owned=100)  # mid=3.0
_check("K12 uses contract mid when no premium override",
       abs(cc_mid.net_premium - (-300.0)) < 1e-9)


# ===========================================================================
# Group L: Liquidity assessment
# ===========================================================================
print("L: Liquidity assessment")

# Liquid: tight spread (<10%), OI >= 100
c_liq1 = _make_call(bid=2.00, ask=2.18, open_interest=500)
# mid = 2.09, spread = 0.18, spread_pct = 0.18/2.09 ≈ 8.6% < 10%
liq_liquid = calculate_option_liquidity([c_liq1])
_check("L1  liquid: tight spread with OI >= 100",
       liq_liquid.status == "liquid")
_check("L2  contract_count = 1", liq_liquid.contract_count == 1)
_check("L3  max_bid_ask_spread_pct >= 0",
       liq_liquid.max_bid_ask_spread_pct is not None and
       liq_liquid.max_bid_ask_spread_pct >= 0)

# Liquid: tight spread, no OI data (OI unavailable → liquid)
c_liq_nooi = _make_call(bid=2.00, ask=2.18, open_interest=None)
liq_nooi = calculate_option_liquidity([c_liq_nooi])
_check("L4  liquid: tight spread with no OI data (OI unavailable)",
       liq_nooi.status == "liquid")

# Acceptable: moderate spread (between 10% and 15%)
# bid=2.0, ask=2.24 → mid=2.12, spread=0.24, pct=0.24/2.12≈11.3% (>10%, <=15%)
c_acc = _make_call(bid=2.00, ask=2.24)
liq_acc = calculate_option_liquidity([c_acc])
_check("L5  acceptable: moderate spread (>10%, <=15%)",
       liq_acc.status == "acceptable")

# Illiquid: wide spread (>15%)
# bid=1.00, ask=2.00 → mid=1.50, spread=1.00, pct≈66.7% > 15%
c_ill = _make_call(bid=1.00, ask=2.00)
liq_ill = calculate_option_liquidity([c_ill])
_check("L6  illiquid: wide spread (>15%)",
       liq_ill.status == "illiquid")

# Empty contracts → unknown + warning
liq_empty = calculate_option_liquidity([])
_check("L7  empty contracts → status='unknown'",
       liq_empty.status == "unknown")
_check("L8  empty contracts → has warning",
       len(liq_empty.warnings) > 0)
_check("L9  empty contracts → contract_count=0",
       liq_empty.contract_count == 0)

# Missing volume → warning
c_no_vol = _make_call(bid=2.00, ask=2.18, volume=None, open_interest=500)
liq_novol = calculate_option_liquidity([c_no_vol])
_check("L10 missing volume → warning",
       any("volume" in w.lower() for w in liq_novol.warnings))

# Missing open_interest → warning
c_no_oi = _make_call(bid=2.00, ask=2.18, volume=100, open_interest=None)
liq_nooi2 = calculate_option_liquidity([c_no_oi])
_check("L11 missing open_interest → warning",
       any("open_interest" in w.lower() for w in liq_nooi2.warnings))

# Low OI (<100): spread tight but OI too low → acceptable (not liquid)
# OI=50 < 100 threshold → falls to acceptable even if spread tight
c_low_oi = _make_call(bid=2.00, ask=2.18, open_interest=50)
liq_lowoi = calculate_option_liquidity([c_low_oi])
_check("L12 low OI (<100): not liquid even with tight spread",
       liq_lowoi.status == "acceptable")

# Multi-contract: worst spread governs
c_tight = _make_call(bid=2.00, ask=2.18)     # spread_pct ≈ 8.6%
c_wide = _make_call(bid=1.00, ask=2.00)      # spread_pct ≈ 66.7%
liq_multi = calculate_option_liquidity([c_tight, c_wide])
_check("L13 multi-contract: worst spread governs → illiquid",
       liq_multi.status == "illiquid")
_check("L14 multi-contract: contract_count = 2",
       liq_multi.contract_count == 2)


# ===========================================================================
# Group M: Event risk assessment
# ===========================================================================
print("M: Event risk assessment")

# Earnings before expiration → high
erc_high_e = assess_option_event_risk(
    "AAPL", "2026-06-20", event_type="earnings", event_date="2026-06-01",
)
_check("M1  earnings before expiration → risk_level='high'",
       erc_high_e.risk_level == "high")
_check("M2  event_before_expiration=True",
       erc_high_e.event_before_expiration is True)
_check("M3  notes non-empty", len(erc_high_e.notes) > 0)

# major_event before expiration → high
erc_high_m = assess_option_event_risk(
    "AAPL", "2026-06-20", event_type="major_event", event_date="2026-05-30",
)
_check("M4  major_event before expiration → risk_level='high'",
       erc_high_m.risk_level == "high")

# Non-major event before expiration → medium
erc_med = assess_option_event_risk(
    "AAPL", "2026-06-20", event_type="dividend", event_date="2026-06-05",
)
_check("M5  non-major event before expiration → risk_level='medium'",
       erc_med.risk_level == "medium")
_check("M6  event_before_expiration=True for medium",
       erc_med.event_before_expiration is True)

# Event after expiration → low
erc_low = assess_option_event_risk(
    "AAPL", "2026-06-20", event_type="earnings", event_date="2026-07-01",
)
_check("M7  event after expiration → risk_level='low'",
       erc_low.risk_level == "low")
_check("M8  event_before_expiration=False when event after expiration",
       erc_low.event_before_expiration is False)

# Insufficient event data → unknown
erc_unk = assess_option_event_risk("AAPL", "2026-06-20")
_check("M9  no event_type or event_date → risk_level='unknown'",
       erc_unk.risk_level == "unknown")
_check("M10 event_before_expiration=None when unknown",
       erc_unk.event_before_expiration is None)
_check("M11 warning generated for unknown",
       len(erc_unk.warnings) > 0)

# Only event_type provided (no event_date) → unknown
erc_unk2 = assess_option_event_risk("AAPL", "2026-06-20", event_type="earnings")
_check("M12 only event_type, no event_date → unknown",
       erc_unk2.risk_level == "unknown")

# Only event_date provided (no event_type) → unknown
erc_unk3 = assess_option_event_risk("AAPL", "2026-06-20", event_date="2026-06-01")
_check("M13 only event_date, no event_type → unknown",
       erc_unk3.risk_level == "unknown")

# Fields preserved in result
_check("M14 underlying preserved in result",
       erc_high_e.underlying == "AAPL")
_check("M15 expiration preserved in result",
       erc_high_e.expiration == "2026-06-20")
_check("M16 event_type preserved in result",
       erc_high_e.event_type == "earnings")
_check("M17 event_date preserved in result",
       erc_high_e.event_date == "2026-06-01")


# ===========================================================================
# Group N: Decision set validation
# ===========================================================================
print("N: Decision set validation")

# Validate returns list of strings and never raises
ds_empty = _make_ds()
warnings_empty = validate_option_strategy_decision_set(ds_empty)
_check("N1  returns list of strings",
       isinstance(warnings_empty, list) and all(isinstance(w, str) for w in warnings_empty))

# N2: warns no candidates
_check("N2  warns no candidates",
       any("no candidates" in w.lower() for w in warnings_empty))

# N3: warns chain snapshot missing
_check("N3  warns chain snapshot missing",
       any("chain_snapshot" in w.lower() or "chain snapshot" in w.lower()
           for w in warnings_empty))

# N4: non-no_trade candidate with no legs → warning
cand_no_legs = OptionStrategyCandidate(underlying="AAPL", strategy_type="long_call")
pr_for_n = calculate_long_call_payoff(_make_call(strike=150.0), premium=3.0)
ds_no_legs = _make_ds(candidates=[cand_no_legs], payoff_results=[pr_for_n])
w_no_legs = validate_option_strategy_decision_set(ds_no_legs)
_check("N4  non-no_trade candidate with no legs → warning",
       any("no legs" in w.lower() for w in w_no_legs))

# N5: no_trade candidate with no legs → NO warning for this condition
cand_notrade = OptionStrategyCandidate(underlying="AAPL", strategy_type="no_trade")
ds_notrade = _make_ds(candidates=[cand_notrade], payoff_results=[pr_for_n])
w_notrade = validate_option_strategy_decision_set(ds_notrade)
_check("N5  no_trade with no legs → no 'no legs' warning",
       not any("no legs" in w.lower() for w in w_notrade))

# N6: candidate with no evidence_refs → warning
_check("N6  candidate with no evidence_refs → warning",
       any("evidence" in w.lower() for w in w_no_legs))

# N7: illiquid liquidity check → warning
c_ill_n = _make_call(bid=1.00, ask=2.00)
liq_ill_n = calculate_option_liquidity([c_ill_n])
assert liq_ill_n.status == "illiquid"
ds_ill = _make_ds(candidates=[cand_no_legs], payoff_results=[pr_for_n],
                  liquidity_checks=[liq_ill_n])
w_ill = validate_option_strategy_decision_set(ds_ill)
_check("N7  illiquid liquidity check → warning",
       any("illiquid" in w.lower() for w in w_ill))

# N8: high event risk → warning
erc_high_n = assess_option_event_risk(
    "AAPL", "2026-06-20", event_type="earnings", event_date="2026-06-01",
)
ds_high_ev = _make_ds(candidates=[cand_no_legs], payoff_results=[pr_for_n],
                       event_risk_checks=[erc_high_n])
w_high_ev = validate_option_strategy_decision_set(ds_high_ev)
_check("N8  high event risk → warning",
       any("high" in w.lower() for w in w_high_ev))

# N9: chain snapshot underlying mismatch → warning
chain_msft = _make_chain(underlying="MSFT", underlying_price=350.0)
ds_chain_mismatch = _make_ds(underlying="AAPL", chain_snapshot=chain_msft)
w_chain_mm = validate_option_strategy_decision_set(ds_chain_mismatch)
_check("N9  chain_snapshot underlying mismatch → warning",
       any("mismatch" in w.lower() or "does not match" in w.lower()
           for w in w_chain_mm))

# N10: candidate underlying mismatch → warning
cand_msft = OptionStrategyCandidate(underlying="MSFT", strategy_type="long_call")
ds_cand_mm = _make_ds(underlying="AAPL", candidates=[cand_msft],
                       payoff_results=[pr_for_n])
w_cand_mm = validate_option_strategy_decision_set(ds_cand_mm)
_check("N10 candidate underlying mismatch → warning",
       any("does not match" in w.lower() for w in w_cand_mm))

# N11: payoff result underlying mismatch → warning
pr_msft = OptionPayoffResult(strategy_type="long_call", underlying="MSFT",
                              net_premium=300.0, max_loss=300.0)
ds_pr_mm = _make_ds(underlying="AAPL", candidates=[cand_no_legs],
                     payoff_results=[pr_msft])
w_pr_mm = validate_option_strategy_decision_set(ds_pr_mm)
_check("N11 payoff result underlying mismatch → warning",
       any("does not match" in w.lower() for w in w_pr_mm))

# N12: payoff result max_loss=None (non-no_trade) → warning
pr_no_loss = OptionPayoffResult(strategy_type="long_call", underlying="AAPL",
                                 net_premium=300.0, max_loss=None)
ds_no_loss = _make_ds(underlying="AAPL", candidates=[cand_no_legs],
                       payoff_results=[pr_no_loss])
w_no_loss = validate_option_strategy_decision_set(ds_no_loss)
_check("N12 payoff result max_loss=None → warning",
       any("max_loss" in w.lower() for w in w_no_loss))

# N13: never raises
try:
    _ = validate_option_strategy_decision_set(_make_ds())
    _check("N13 never raises", True)
except Exception:
    _check("N13 never raises", False)


# ===========================================================================
# Group O: ToolResult adapter
# ===========================================================================
print("O: ToolResult adapter")

ds_for_tr = _make_ds(chain_snapshot=_make_chain())
tr = option_strategy_tool_result_from_decision_set("RUN_001", ds_for_tr)

_check("O1  tool_name = 'option_strategy_decision_set'",
       tr.tool_name == "option_strategy_decision_set")
_check("O2  ticker = decision_set.underlying",
       tr.ticker == ds_for_tr.underlying)
_check("O3  target defaults to underlying (evidence_id contains it)",
       "AAPL" in tr.evidence_id)
_check("O4  evidence_id contains tool_name",
       "option_strategy_decision_set" in tr.evidence_id)
_check("O5  inputs contains underlying",
       "underlying" in tr.inputs)
_check("O6  inputs contains as_of", "as_of" in tr.inputs)
_check("O7  inputs contains calculation_version",
       "calculation_version" in tr.inputs)
_check("O8  payload includes chain_snapshot",
       "chain_snapshot" in tr.outputs)
_check("O9  payload includes candidates",
       "candidates" in tr.outputs)
_check("O10 payload includes payoff_results",
       "payoff_results" in tr.outputs)
_check("O11 payload includes liquidity_checks",
       "liquidity_checks" in tr.outputs)
_check("O12 payload includes event_risk_checks",
       "event_risk_checks" in tr.outputs)
_check("O13 description is non-empty", len(tr.description) > 0)
_check("O14 run_id preserved", tr.run_id == "RUN_001")

# Deterministic evidence_id
tr2 = option_strategy_tool_result_from_decision_set("RUN_001", ds_for_tr)
_check("O15 deterministic: same inputs → same evidence_id",
       tr.evidence_id == tr2.evidence_id)

# Different run_id → different evidence_id
tr3 = option_strategy_tool_result_from_decision_set("RUN_002", ds_for_tr)
_check("O16 different run_id → different evidence_id",
       tr.evidence_id != tr3.evidence_id)

# Custom target
tr_custom = option_strategy_tool_result_from_decision_set("RUN_001", ds_for_tr,
                                                            target="AAPL_options")
_check("O17 custom target embedded in evidence_id",
       "AAPL_options" in tr_custom.evidence_id)

# chain_snapshot serialized when present
_check("O18 chain_snapshot present in payload when set",
       tr.outputs.get("chain_snapshot") is not None)

# chain_snapshot=None serialized as None
ds_no_chain = _make_ds()
tr_no_chain = option_strategy_tool_result_from_decision_set("RUN_001", ds_no_chain)
_check("O19 chain_snapshot=None in payload when not set",
       tr_no_chain.outputs.get("chain_snapshot") is None)


# ===========================================================================
# Group P: Summary helper
# ===========================================================================
print("P: Summary helper")

cand_lc = OptionStrategyCandidate(underlying="AAPL", strategy_type="long_call")
cand_csp = OptionStrategyCandidate(underlying="AAPL", strategy_type="cash_secured_put")
pr_p = calculate_long_call_payoff(_make_call(strike=150.0), premium=3.0)
liq_p = calculate_option_liquidity([_make_call(bid=2.0, ask=2.18, open_interest=200)])
erc_low_p = assess_option_event_risk("AAPL", "2026-06-20")

ds_full = OptionStrategyDecisionSet(
    underlying="AAPL",
    as_of="2026-05-21",
    chain_snapshot=_make_chain(),
    candidates=[cand_lc, cand_csp],
    payoff_results=[pr_p],
    liquidity_checks=[liq_p],
    event_risk_checks=[erc_low_p],
)
summary = summarize_option_strategy_decision_set(ds_full)

_check("P1  underlying in summary", summary["underlying"] == "AAPL")
_check("P2  as_of in summary", summary["as_of"] == "2026-05-21")
_check("P3  candidate_count = 2", summary["candidate_count"] == 2)
_check("P4  payoff_result_count = 1", summary["payoff_result_count"] == 1)
_check("P5  liquidity_check_count = 1", summary["liquidity_check_count"] == 1)
_check("P6  event_risk_check_count = 1", summary["event_risk_check_count"] == 1)
_check("P7  strategy_types_present contains long_call",
       "long_call" in summary["strategy_types_present"])
_check("P8  strategy_types_present contains cash_secured_put",
       "cash_secured_put" in summary["strategy_types_present"])
_check("P9  warnings_count = 0", summary["warnings_count"] == 0)
_check("P10 has_high_event_risk = False", summary["has_high_event_risk"] is False)
_check("P11 chain_snapshot_present = True", summary["chain_snapshot_present"] is True)

# has_high_event_risk = True when high event risk present
erc_high_p = assess_option_event_risk("AAPL", "2026-06-20", "earnings", "2026-06-01")
ds_highrisk = _make_ds(event_risk_checks=[erc_high_p])
summary_hr = summarize_option_strategy_decision_set(ds_highrisk)
_check("P12 has_high_event_risk = True when risk='high'",
       summary_hr["has_high_event_risk"] is True)

# chain_snapshot_present = False when no chain
ds_no_chain2 = _make_ds()
summary_nc = summarize_option_strategy_decision_set(ds_no_chain2)
_check("P13 chain_snapshot_present = False when no chain",
       summary_nc["chain_snapshot_present"] is False)


# ===========================================================================
# Group Q: EvidenceRef integration
# ===========================================================================
print("Q: EvidenceRef integration")

from lib.reliability.schemas import EvidenceRef

ev_ref = EvidenceRef(
    evidence_id="RUN_001:valuation_model:AAPL:dcf:abc123",
    tool_name="valuation_model",
    field_path="fair_value",
    excerpt="Fair value $185",
)

cand_with_ev = OptionStrategyCandidate(
    underlying="AAPL",
    strategy_type="long_call",
    evidence_refs=[ev_ref],
)
_check("Q1  OptionStrategyCandidate preserves evidence_refs",
       len(cand_with_ev.evidence_refs) == 1)
_check("Q2  evidence_ref evidence_id preserved",
       cand_with_ev.evidence_refs[0].evidence_id == ev_ref.evidence_id)

pr_with_ev = OptionPayoffResult(
    strategy_type="long_call",
    underlying="AAPL",
    net_premium=300.0,
    max_loss=300.0,
    evidence_refs=[ev_ref],
)
_check("Q3  OptionPayoffResult preserves evidence_refs",
       len(pr_with_ev.evidence_refs) == 1)


# ===========================================================================
# Group R: Serialization roundtrip
# ===========================================================================
print("R: Serialization roundtrip")

# OptionContractSnapshot
c_rt = OptionContractSnapshot(
    underlying="AAPL", option_type="call", expiration="2026-06-20",
    strike=150.0, bid=1.50, ask=1.70, mid=1.65, volume=100,
    open_interest=500, implied_volatility=0.28, delta=0.45,
    gamma=0.02, theta=-0.05, vega=0.15, as_of="2026-05-21",
)
c_data = c_rt.model_dump()
c_restored = OptionContractSnapshot(**c_data)
_check("R1  OptionContractSnapshot roundtrip underlying",
       c_restored.underlying == c_rt.underlying)
_check("R2  OptionContractSnapshot roundtrip delta",
       c_restored.delta == c_rt.delta)
_check("R3  OptionContractSnapshot roundtrip gamma",
       c_restored.gamma == c_rt.gamma)

# OptionChainSnapshot
chain_rt = _make_chain(contracts=[c_rt])
chain_data = chain_rt.model_dump()
chain_restored = OptionChainSnapshot(**chain_data)
_check("R4  OptionChainSnapshot roundtrip underlying",
       chain_restored.underlying == chain_rt.underlying)
_check("R5  OptionChainSnapshot roundtrip underlying_price",
       chain_restored.underlying_price == chain_rt.underlying_price)
_check("R6  OptionChainSnapshot roundtrip contracts count",
       len(chain_restored.contracts) == 1)

# OptionPayoffResult (with breakeven as float)
pr_rt = calculate_long_call_payoff(c_rt, premium=3.0)
pr_data = pr_rt.model_dump()
pr_restored = OptionPayoffResult(**pr_data)
_check("R7  OptionPayoffResult roundtrip strategy_type",
       pr_restored.strategy_type == pr_rt.strategy_type)
_check("R8  OptionPayoffResult roundtrip net_premium",
       pr_restored.net_premium == pr_rt.net_premium)
_check("R9  OptionPayoffResult roundtrip breakeven",
       pr_restored.breakeven == pr_rt.breakeven)

# OptionStrategyDecisionSet with chain_snapshot
ds_rt = OptionStrategyDecisionSet(
    underlying="AAPL", as_of="2026-05-21",
    chain_snapshot=chain_rt,
    payoff_results=[pr_rt],
)
ds_data = ds_rt.model_dump()
ds_restored = OptionStrategyDecisionSet(**ds_data)
_check("R10 OptionStrategyDecisionSet roundtrip underlying",
       ds_restored.underlying == ds_rt.underlying)
_check("R11 OptionStrategyDecisionSet roundtrip chain_snapshot present",
       ds_restored.chain_snapshot is not None)
_check("R12 OptionStrategyDecisionSet roundtrip chain underlying",
       ds_restored.chain_snapshot.underlying == "AAPL")
_check("R13 OptionStrategyDecisionSet roundtrip payoff_results count",
       len(ds_restored.payoff_results) == 1)

# OptionLiquidityCheck roundtrip
liq_rt = calculate_option_liquidity([_make_call(bid=2.0, ask=2.18, open_interest=200)])
liq_data = liq_rt.model_dump()
liq_restored = OptionLiquidityCheck(**liq_data)
_check("R14 OptionLiquidityCheck roundtrip status",
       liq_restored.status == liq_rt.status)

# OptionEventRiskCheck roundtrip
erc_rt = assess_option_event_risk("AAPL", "2026-06-20", "earnings", "2026-06-01")
erc_data = erc_rt.model_dump()
erc_restored = OptionEventRiskCheck(**erc_data)
_check("R15 OptionEventRiskCheck roundtrip risk_level",
       erc_restored.risk_level == erc_rt.risk_level)
_check("R16 OptionEventRiskCheck roundtrip event_type",
       erc_restored.event_type == erc_rt.event_type)


# ===========================================================================
# Group S: Safety — no live app imports, runs from repo root
# ===========================================================================
print("S: Safety")

import importlib
import sys as _sys
import lib.reliability.options as _opts_mod

_mod_src = Path(_opts_mod.__file__).read_text()

_check("S1  options.py does not import streamlit",
       "import streamlit" not in _mod_src and "from streamlit" not in _mod_src)
_check("S2  options.py does not import yfinance",
       "import yfinance" not in _mod_src)
_check("S3  options.py does not import requests",
       "import requests" not in _mod_src)
_check("S4  options.py does not import app",
       "\nimport app" not in _mod_src and "\nfrom app" not in _mod_src)
_check("S5  options.py does not import pages",
       "from pages" not in _mod_src and "import pages" not in _mod_src)

# All symbols importable from lib.reliability
try:
    from lib.reliability import (
        OptionType, OptionPositionSide, OptionStrategyType,
        OptionLiquidityStatus, OptionEventRiskLevel, OptionTradeExpression,
        OptionContractSnapshot, OptionChainSnapshot, OptionLeg,
        OptionStrategyCandidate, OptionPayoffResult,
        OptionLiquidityCheck, OptionEventRiskCheck, OptionStrategyDecisionSet,
        option_mid_price, option_leg_premium,
        calculate_long_call_payoff, calculate_long_put_payoff,
        calculate_call_debit_spread_payoff, calculate_put_debit_spread_payoff,
        calculate_cash_secured_put_payoff, calculate_covered_call_payoff,
        calculate_option_liquidity, assess_option_event_risk,
        option_strategy_tool_result_from_decision_set,
        summarize_option_strategy_decision_set,
        validate_option_strategy_decision_set,
    )
    _check("S6  all symbols importable from lib.reliability", True)
except ImportError as e:
    _check(f"S6  all symbols importable from lib.reliability ({e})", False)

# Script runs from repo root (_ROOT check)
_check("S7  sys.path includes repo root", str(_ROOT) in sys.path)


# ===========================================================================
# Summary
# ===========================================================================
print()
print(f"Result: {_PASS} passed, {_FAIL} failed")
if _FAIL == 0:
    print("All assertions passed.")
else:
    sys.exit(1)
