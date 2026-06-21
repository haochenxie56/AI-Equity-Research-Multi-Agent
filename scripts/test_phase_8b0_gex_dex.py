#!/usr/bin/env python3
"""
scripts/test_phase_8b0_gex_dex.py

Phase 8B-0 — GEX/DEX deterministic calculator test suite.

Pure unit tests: builds OptionChainSnapshot fixtures (the existing Phase 2E
schema) and asserts GEX/DEX signs and magnitudes, wall detection, the
gamma-squeeze monitor, degradation, and the no-numerics regime_summary
contract. Several cases include a DISCRIMINATING flip that would go RED on a
sign/logic regression.

Usage:
    python3 scripts/test_phase_8b0_gex_dex.py
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from lib.reliability.options import OptionChainSnapshot, OptionContractSnapshot  # noqa: E402
from lib.gex_dex import (  # noqa: E402
    GexDexResult,
    compute_gex_dex,
    find_walls,
    gex_dex_to_signals,
)


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


_AS_OF = "2026-06-20T12:00:00+00:00"


def _c(option_type, strike, *, gamma=0.01, delta=None, oi=1000,
       expiration="2026-06-27"):
    """Build an OptionContractSnapshot with sensible test defaults."""
    if delta is None:
        delta = 0.5 if option_type == "call" else -0.5
    return OptionContractSnapshot(
        underlying="SPY",
        option_type=option_type,
        expiration=expiration,
        strike=float(strike),
        bid=0.0,
        ask=0.0,
        open_interest=oi,
        gamma=gamma,
        delta=delta,
        as_of=_AS_OF,
        source="test",
    )


def _chain(contracts, underlying_price=100.0):
    return OptionChainSnapshot(
        underlying="SPY",
        underlying_price=float(underlying_price),
        expirations=sorted({c.expiration for c in contracts}) or ["2026-06-27"],
        contracts=contracts,
        as_of=_AS_OF,
        source="test",
    )


# ---------------------------------------------------------------------------
# §8B0-G1 — empty chain -> degraded
# ---------------------------------------------------------------------------
def test_g1():
    chain = _chain([], underlying_price=100.0)
    r = compute_gex_dex(chain)
    check("§8B0-G1 empty chain -> degraded + zero GEX",
          r.degraded is True and r.gex_total == 0.0 and r.contracts_used == 0,
          repr(r))


# ---------------------------------------------------------------------------
# §8B0-G2 — GEX sign (with discriminating flip)
# ---------------------------------------------------------------------------
def test_g2():
    price = 100.0
    calls = [_c("call", 100, gamma=0.05, oi=1000),
             _c("call", 105, gamma=0.05, oi=1000)]
    put = _c("put", 95, gamma=0.03, oi=2000)
    chain = _chain(calls + [put], underlying_price=price)
    r = compute_gex_dex(chain)

    # call: 0.05 * 1000 * 100 * 100^2 * 0.01 = 500_000 each -> +1_000_000
    # put:  -(0.03 * 2000 * 100 * 100^2 * 0.01) = -600_000
    expected = 1_000_000.0 - 600_000.0  # = 400_000
    ok = abs(r.gex_total - expected) < 0.01 and r.gex_sign == "positive"
    check("§8B0-G2 GEX magnitude + positive sign", ok,
          f"gex_total={r.gex_total} sign={r.gex_sign} expected={expected}")

    # DISCRIMINATING: flip the put gamma to 0.10 -> put = -2_000_000 -> total negative.
    put2 = _c("put", 95, gamma=0.10, oi=2000)
    r2 = compute_gex_dex(_chain(calls + [put2], underlying_price=price))
    check("§8B0-G2 DISCRIMINATING flipped put gamma -> negative sign",
          r2.gex_sign == "negative" and r2.gex_total < 0,
          f"gex_total={r2.gex_total} sign={r2.gex_sign}")


# ---------------------------------------------------------------------------
# §8B0-G3 — DEX magnitude
# ---------------------------------------------------------------------------
def test_g3():
    price = 200.0
    call = _c("call", 200, gamma=0.01, delta=0.6, oi=1000)
    put = _c("put", 200, gamma=0.01, delta=-0.4, oi=1000)
    r = compute_gex_dex(_chain([call, put], underlying_price=price))
    # (0.6*1000*100*200) + (-0.4*1000*100*200) = 12_000_000 - 8_000_000
    expected = 4_000_000.0
    check("§8B0-G3 DEX magnitude", abs(r.dex_total - expected) < 0.01,
          f"dex_total={r.dex_total} expected={expected}")


# ---------------------------------------------------------------------------
# §8B0-G4 — wall detection (with discriminating swap)
# ---------------------------------------------------------------------------
def test_g4():
    calls = [_c("call", 550, oi=1000), _c("call", 560, oi=5000),
             _c("call", 570, oi=2000)]
    puts = [_c("put", 540, oi=3000), _c("put", 550, oi=8000),
            _c("put", 560, oi=1000)]
    walls = find_walls(_chain(calls + puts))
    ok = walls["call_wall"] == 560 and walls["put_wall"] == 550
    check("§8B0-G4 call_wall=560 put_wall=550", ok, repr(walls))

    # DISCRIMINATING: move the OI peaks and verify the walls move too.
    calls2 = [_c("call", 550, oi=5000), _c("call", 560, oi=1000),
              _c("call", 570, oi=2000)]
    puts2 = [_c("put", 540, oi=1000), _c("put", 550, oi=3000),
             _c("put", 560, oi=8000)]
    walls2 = find_walls(_chain(calls2 + puts2))
    check("§8B0-G4 DISCRIMINATING walls move w/ OI",
          walls2["call_wall"] == 550 and walls2["put_wall"] == 560, repr(walls2))


# ---------------------------------------------------------------------------
# §8B0-G5 — squeeze probability "mid" when 2 conditions met
# ---------------------------------------------------------------------------
def test_g5():
    # Single put with positive gamma -> negative GEX (condition A).
    # put_wall=100, underlying=102 is within 3% above put_wall (condition B).
    put = _c("put", 100, gamma=0.05, delta=-0.5, oi=1000)
    r = compute_gex_dex(_chain([put], underlying_price=102.0))
    check("§8B0-G5 two conditions -> squeeze 'mid'",
          r.squeeze_probability == "mid",
          f"prob={r.squeeze_probability} conds={r.squeeze_trigger_conditions} "
          f"gex_sign={r.gex_sign} put_wall={r.put_wall}")


# ---------------------------------------------------------------------------
# §8B0-G6 — skip None-gamma contracts and degrade
# ---------------------------------------------------------------------------
def test_g6():
    good = [_c("call", 100, gamma=0.05, oi=1000),
            _c("put", 95, gamma=0.05, oi=1000)]
    bad = [_c("call", 105, gamma=None, oi=1000),
           _c("put", 90, gamma=None, oi=1000)]
    r = compute_gex_dex(_chain(good + bad, underlying_price=100.0))
    check("§8B0-G6 None-gamma skipped + degraded",
          r.degraded is True and r.contracts_used == 2 and r.contracts_used < 4,
          f"used={r.contracts_used} degraded={r.degraded}")


# ---------------------------------------------------------------------------
# §8B0-G7 — regime_summary has no numeric values
# ---------------------------------------------------------------------------
def test_g7():
    calls = [_c("call", 100, gamma=0.05, oi=1000)]
    put = _c("put", 95, gamma=0.03, oi=1000)
    r = compute_gex_dex(_chain(calls + [put], underlying_price=100.0))
    sig = gex_dex_to_signals(r)
    summary = sig["regime_summary"]
    no_digits = not any(ch.isdigit() for ch in summary)
    check("§8B0-G7 regime_summary contains no digits", no_digits, repr(summary))

    # DISCRIMINATING: a polluted summary MUST be detected (guard goes RED).
    polluted = "GEX=1234"
    detects = any(ch.isdigit() for ch in polluted)
    check("§8B0-G7 DISCRIMINATING digit-detector flags 'GEX=1234'", detects,
          polluted)


def _prior_with_dex(dex_total: float) -> GexDexResult:
    """Minimal prior GexDexResult carrying only a dex_total baseline."""
    return GexDexResult(
        ticker="SPY",
        as_of=_AS_OF,
        underlying_price=102.0,
        gex_total=0.0,
        gex_sign="neutral",
        gex_call=0.0,
        gex_put=0.0,
        dex_total=dex_total,
        dex_sign="neutral",
        dex_call=0.0,
        dex_put=0.0,
    )


# ---------------------------------------------------------------------------
# §8B0-G8 — prior_result triggers condition C -> "high" (with discriminating flip)
# ---------------------------------------------------------------------------
def test_g8():
    # Conditions A (negative GEX) + B (price within 3% above put_wall) met,
    # same construction as G5.
    put = _c("put", 100, gamma=0.05, delta=-0.5, oi=1000)
    chain = _chain([put], underlying_price=102.0)

    current = compute_gex_dex(chain)  # baseline dex_total (A+B -> "mid")
    prior_rising = _prior_with_dex(current.dex_total - 1000.0)  # current > prior
    r = compute_gex_dex(chain, prior_result=prior_rising)
    check("§8B0-G8 condition C -> squeeze 'high'",
          r.squeeze_probability == "high"
          and "dex_trend_rising" in r.squeeze_trigger_conditions,
          f"prob={r.squeeze_probability} conds={r.squeeze_trigger_conditions}")

    # DISCRIMINATING: prior dex higher than current (DEX falling) -> C unmet -> "mid".
    prior_falling = _prior_with_dex(current.dex_total + 1000.0)
    r2 = compute_gex_dex(chain, prior_result=prior_falling)
    check("§8B0-G8 DISCRIMINATING DEX falling -> 'mid'",
          r2.squeeze_probability == "mid",
          f"prob={r2.squeeze_probability} conds={r2.squeeze_trigger_conditions}")


# ---------------------------------------------------------------------------
# §8B0-G9 — prior_result=None keeps condition C unmet (no regression)
# ---------------------------------------------------------------------------
def test_g9():
    put = _c("put", 100, gamma=0.05, delta=-0.5, oi=1000)
    chain = _chain([put], underlying_price=102.0)
    r = compute_gex_dex(chain, prior_result=None)
    check("§8B0-G9 prior=None -> squeeze 'mid' (not 'high')",
          r.squeeze_probability == "mid",
          f"prob={r.squeeze_probability} conds={r.squeeze_trigger_conditions}")


def main() -> int:
    test_g1()
    test_g2()
    test_g3()
    test_g4()
    test_g5()
    test_g6()
    test_g7()
    test_g8()
    test_g9()

    print(f"\n{'=' * 60}")
    print(f"test_phase_8b0_gex_dex.py  —  PASS={PASS}  FAIL={FAIL}")
    print(f"{'=' * 60}")
    for f in _failures:
        print(f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
