"""lib/gex_dex.py — Phase 8B-0 dealer gamma/delta exposure calculator.

Pure deterministic calculator: takes an options chain snapshot (duck-typed —
anything exposing ``.contracts`` / ``.underlying_price`` / ``.underlying`` /
``.as_of`` like ``lib.reliability.options.OptionChainSnapshot``) and returns a
``GexDexResult``. NO network, NO LLM, and deliberately NO import from
``lib.reliability`` (keeps this module eager-import-cheap).

GEX (gamma exposure, $ per 1% move) per contract::

    base = gamma * open_interest * 100 * (underlying_price ** 2) * 0.01
    call -> +base   (dealers long gamma on calls they are short)
    put  -> -base

DEX (delta exposure, $) per contract::

    contract_dex = delta * open_interest * 100 * underlying_price
    (call delta is positive, put delta is negative, so the sign falls out
     of the delta itself — no extra negation.)

Scoping note: GEX/DEX are summed over ALL contracts present in the chain, and
walls are detected over the same set. The chain is expected to have already
been scoped to the desired expiry window by the fetcher
(``fetch_options_chain(ticker, expiry_filter)``); the ``expiry_filter``
argument here is recorded on the result for provenance.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

# Per-contract share multiplier (one option contract controls 100 shares).
_MULTIPLIER = 100
# GEX scales a full move down to a 1% move.
_ONE_PCT = 0.01
# Squeeze condition B: price is "within 3% above" the put wall.
_NEAR_WALL_PCT = 0.03


@dataclass
class GexDexResult:
    ticker: str
    as_of: str  # ISO datetime
    underlying_price: float

    # GEX fields
    gex_total: float  # net gamma exposure ($ / 1% move)
    gex_sign: str  # "positive" | "negative" | "neutral"
    gex_call: float  # call-side GEX contribution
    gex_put: float  # put-side GEX contribution

    # DEX fields
    dex_total: float  # net delta exposure ($)
    dex_sign: str  # "positive" | "negative" | "neutral"
    dex_call: float
    dex_put: float

    # Walls
    call_wall: Optional[float] = None  # strike with highest call OI
    put_wall: Optional[float] = None  # strike with highest put OI
    call_wall_oi: Optional[int] = None
    put_wall_oi: Optional[int] = None

    # Gamma squeeze monitor
    squeeze_probability: str = "unknown"  # "low" | "mid" | "high" | "unknown"
    squeeze_direction: Optional[str] = None  # "up" | "down" | None
    squeeze_trigger_conditions: list[str] = field(default_factory=list)

    # Meta
    contracts_used: int = 0
    degraded: bool = False
    degraded_reasons: list[str] = field(default_factory=list)
    expiry_filter: str = "this_week"


def _sign(x: float) -> str:
    if x > 0.0:
        return "positive"
    if x < 0.0:
        return "negative"
    return "neutral"


def find_walls(chain, expiry: str = "this_week") -> dict:
    """Return the highest-open-interest call and put strikes in *chain*.

    Walls use ``open_interest`` only (independent of Greeks), so contracts with
    missing Greeks still contribute. On a tie the lower strike wins
    (deterministic — strikes are scanned in ascending order).
    """
    contracts = list(getattr(chain, "contracts", []) or [])

    call_oi: dict[float, int] = {}
    put_oi: dict[float, int] = {}
    for c in contracts:
        oi = getattr(c, "open_interest", None)
        if oi is None:
            continue
        strike = getattr(c, "strike", None)
        if strike is None:
            continue
        if getattr(c, "option_type", None) == "call":
            call_oi[strike] = call_oi.get(strike, 0) + int(oi)
        elif getattr(c, "option_type", None) == "put":
            put_oi[strike] = put_oi.get(strike, 0) + int(oi)

    def _peak(oi_by_strike: dict):
        if not oi_by_strike:
            return None, None
        # max OI; tie broken by lowest strike (ascending scan).
        best_strike = None
        best_oi = None
        for strike in sorted(oi_by_strike.keys()):
            oi = oi_by_strike[strike]
            if best_oi is None or oi > best_oi:
                best_oi = oi
                best_strike = strike
        return best_strike, best_oi

    call_wall, call_wall_oi = _peak(call_oi)
    put_wall, put_wall_oi = _peak(put_oi)

    return {
        "call_wall": call_wall,
        "put_wall": put_wall,
        "call_wall_oi": call_wall_oi,
        "put_wall_oi": put_wall_oi,
    }


def compute_gex_dex(
    chain,
    expiry_filter: str = "this_week",
    prior_result: Optional["GexDexResult"] = None,
) -> GexDexResult:
    """Compute net dealer GEX/DEX, walls, and the gamma-squeeze monitor.

    Contracts missing ``gamma`` or ``delta`` are skipped from the GEX/DEX sums
    and the result is marked ``degraded``. Walls (OI-based) are unaffected by
    missing Greeks. Never raises — always returns a ``GexDexResult``.

    *prior_result*: a previous ``GexDexResult`` for the same ticker. When
    supplied, squeeze condition C (DEX trend rising) is evaluated as
    ``dex_total > prior_result.dex_total``; when ``None`` condition C is
    unreachable (cannot rise above an unknown baseline).
    """
    ticker = getattr(chain, "underlying", "") or ""
    as_of = getattr(chain, "as_of", "") or datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    underlying_price = float(getattr(chain, "underlying_price", 0.0) or 0.0)
    contracts = list(getattr(chain, "contracts", []) or [])

    gex_call = 0.0
    gex_put = 0.0
    dex_call = 0.0
    dex_put = 0.0
    contracts_used = 0
    degraded = False
    degraded_reasons: list[str] = []

    for c in contracts:
        gamma = getattr(c, "gamma", None)
        delta = getattr(c, "delta", None)
        oi = getattr(c, "open_interest", None)
        otype = getattr(c, "option_type", None)
        strike = getattr(c, "strike", None)

        if gamma is None or delta is None:
            degraded = True
            degraded_reasons.append(
                f"missing_greeks: {otype} {strike} "
                f"(gamma={'None' if gamma is None else 'ok'}, "
                f"delta={'None' if delta is None else 'ok'})"
            )
            continue
        if oi is None:
            degraded = True
            degraded_reasons.append(f"missing_oi: {otype} {strike}")
            continue

        oi_i = int(oi)
        base_gex = gamma * oi_i * _MULTIPLIER * (underlying_price ** 2) * _ONE_PCT
        contract_dex = delta * oi_i * _MULTIPLIER * underlying_price

        if otype == "call":
            gex_call += base_gex  # dealer long-gamma convention: calls positive
            dex_call += contract_dex
        elif otype == "put":
            gex_put -= base_gex  # puts contribute negative gamma
            dex_put += contract_dex  # put delta already negative
        else:
            degraded = True
            degraded_reasons.append(f"unknown_option_type: {otype} {strike}")
            continue

        contracts_used += 1

    gex_total = gex_call + gex_put
    dex_total = dex_call + dex_put

    walls = find_walls(chain, expiry="this_week")
    call_wall = walls["call_wall"]
    put_wall = walls["put_wall"]

    # ---- Fully-degraded short circuit (nothing usable) --------------------
    if contracts_used == 0:
        if not contracts:
            degraded_reasons.append("empty_chain")
        degraded = True
        return GexDexResult(
            ticker=ticker,
            as_of=as_of,
            underlying_price=underlying_price,
            gex_total=0.0,
            gex_sign="neutral",
            gex_call=0.0,
            gex_put=0.0,
            dex_total=0.0,
            dex_sign="neutral",
            dex_call=0.0,
            dex_put=0.0,
            call_wall=call_wall,
            put_wall=put_wall,
            call_wall_oi=walls["call_wall_oi"],
            put_wall_oi=walls["put_wall_oi"],
            squeeze_probability="unknown",
            squeeze_direction=None,
            squeeze_trigger_conditions=[],
            contracts_used=0,
            degraded=True,
            degraded_reasons=degraded_reasons,
            expiry_filter=expiry_filter,
        )

    gex_sign = _sign(gex_total)
    dex_sign = _sign(dex_total)

    # ---- Gamma squeeze monitor (deterministic rules) ----------------------
    # Condition A: net GEX is negative (dealers amplify moves).
    # Condition B: price is within 3% ABOVE the put wall (rising into the call
    #              concentration from below).
    # Condition C: DEX is rising vs the prior snapshot (only when one is given).
    conditions: list[str] = []

    condition_a_met = gex_sign == "negative"
    if condition_a_met:
        conditions.append("negative_gex")

    condition_b_met = (
        put_wall is not None
        and put_wall > 0
        and put_wall <= underlying_price <= put_wall * (1.0 + _NEAR_WALL_PCT)
    )
    if condition_b_met:
        conditions.append("price_near_put_wall")

    condition_c_met = False
    if prior_result is not None:
        condition_c_met = dex_total > prior_result.dex_total
        if condition_c_met:
            conditions.append("dex_trend_rising")

    conditions_met = sum([condition_a_met, condition_b_met, condition_c_met])
    if conditions_met >= 3:
        squeeze_probability = "high"
    elif conditions_met == 2:
        squeeze_probability = "mid"
    else:  # 0 or 1
        squeeze_probability = "low"

    squeeze_direction: Optional[str]
    if call_wall is not None and call_wall > underlying_price:
        squeeze_direction = "up"
    elif put_wall is not None and put_wall < underlying_price:
        squeeze_direction = "down"
    else:
        squeeze_direction = None

    return GexDexResult(
        ticker=ticker,
        as_of=as_of,
        underlying_price=underlying_price,
        gex_total=gex_total,
        gex_sign=gex_sign,
        gex_call=gex_call,
        gex_put=gex_put,
        dex_total=dex_total,
        dex_sign=dex_sign,
        dex_call=dex_call,
        dex_put=dex_put,
        call_wall=call_wall,
        put_wall=put_wall,
        call_wall_oi=walls["call_wall_oi"],
        put_wall_oi=walls["put_wall_oi"],
        squeeze_probability=squeeze_probability,
        squeeze_direction=squeeze_direction,
        squeeze_trigger_conditions=conditions,
        contracts_used=contracts_used,
        degraded=degraded,
        degraded_reasons=degraded_reasons,
        expiry_filter=expiry_filter,
    )


def gex_dex_to_signals(result: GexDexResult) -> dict:
    """Flatten a ``GexDexResult`` into a signal dict for agent consumption.

    ``regime_summary`` is a one-line human string that contains NO numeric
    values — all numbers live in the structured ``call_wall`` / ``put_wall``
    fields. Downstream renderers compose numbers in from those fields.
    """
    if result.degraded and result.contracts_used == 0:
        regime_summary = (
            "Options data degraded: dealer positioning signal unavailable."
        )
    elif result.gex_sign == "positive":
        regime_summary = (
            "Positive GEX regime: dealers dampen volatility and price tends to "
            "pin between the put wall and the call wall."
        )
    elif result.gex_sign == "negative":
        regime_summary = (
            "Negative GEX regime: dealers amplify moves and squeeze risk is "
            "elevated"
        )
        if result.squeeze_direction == "up":
            regime_summary += " toward the call wall."
        elif result.squeeze_direction == "down":
            regime_summary += " toward the put wall."
        else:
            regime_summary += "."
    else:
        regime_summary = (
            "Neutral GEX regime: balanced dealer positioning with no clear pin."
        )

    return {
        "gex_sign": result.gex_sign,
        "dex_sign": result.dex_sign,
        "call_wall": result.call_wall,
        "put_wall": result.put_wall,
        "squeeze_probability": result.squeeze_probability,
        "squeeze_direction": result.squeeze_direction,
        "squeeze_trigger_conditions": result.squeeze_trigger_conditions,
        "degraded": result.degraded,
        "regime_summary": regime_summary,
    }
