"""
Valuation models for US equities: DCF, comps multiples, and WACC calculation.
All monetary values in USD.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# WACC
# ---------------------------------------------------------------------------

def calc_wacc(
    beta: float,
    market_risk_premium: float = 0.055,
    risk_free_rate: float = 0.045,
    tax_rate: float = 0.21,
    debt: float = 0.0,
    equity: float = 1.0,
    cost_of_debt: float = 0.05,
) -> float:
    """
    WACC = (E/V) * Re + (D/V) * Rd * (1 - Tc)
    Re estimated via CAPM: rf + beta * (rm - rf)
    """
    cost_of_equity = risk_free_rate + beta * market_risk_premium
    v = equity + debt
    if v == 0:
        return cost_of_equity
    wacc = (equity / v) * cost_of_equity + (debt / v) * cost_of_debt * (1 - tax_rate)
    return wacc


# ---------------------------------------------------------------------------
# DCF
# ---------------------------------------------------------------------------

@dataclass
class DCFResult:
    intrinsic_value: float       # per share, USD
    implied_premium: float       # % vs current price
    npv_fcfs: float
    terminal_value_pv: float
    wacc: float
    scenario: str


def dcf_valuation(
    base_fcf: float,             # trailing twelve month FCF, USD
    growth_rates: list[float],   # year-by-year growth for explicit period (e.g. [0.20]*5)
    terminal_growth: float = 0.025,
    wacc: float = 0.10,
    shares_outstanding: float = 1.0,
    net_debt: float = 0.0,       # positive = net debt, negative = net cash
    current_price: Optional[float] = None,
    scenario: str = "base",
) -> DCFResult:
    """Standard two-stage DCF. Returns intrinsic value per share in USD."""
    fcfs = []
    fcf = base_fcf
    for g in growth_rates:
        fcf = fcf * (1 + g)
        fcfs.append(fcf)

    discount_factors = [(1 / (1 + wacc) ** (i + 1)) for i in range(len(fcfs))]
    npv_fcfs = sum(f * d for f, d in zip(fcfs, discount_factors))

    terminal_fcf = fcfs[-1] * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    terminal_value_pv = terminal_value * discount_factors[-1]

    equity_value = npv_fcfs + terminal_value_pv - net_debt
    intrinsic_value = equity_value / shares_outstanding if shares_outstanding > 0 else 0.0

    implied_premium = 0.0
    if current_price and current_price > 0:
        implied_premium = (intrinsic_value - current_price) / current_price

    return DCFResult(
        intrinsic_value=round(intrinsic_value, 2),
        implied_premium=round(implied_premium, 4),
        npv_fcfs=round(npv_fcfs, 0),
        terminal_value_pv=round(terminal_value_pv, 0),
        wacc=round(wacc, 4),
        scenario=scenario,
    )


def dcf_scenarios(
    base_fcf: float,
    wacc: float,
    shares_outstanding: float,
    net_debt: float = 0.0,
    current_price: Optional[float] = None,
) -> dict[str, DCFResult]:
    """Run bear / base / bull DCF scenarios and return all three."""
    scenarios = {
        "bear":  {"growth_rates": [0.05] * 5, "terminal_growth": 0.02},
        "base":  {"growth_rates": [0.12] * 5, "terminal_growth": 0.025},
        "bull":  {"growth_rates": [0.20] * 5, "terminal_growth": 0.03},
    }
    results = {}
    for name, params in scenarios.items():
        results[name] = dcf_valuation(
            base_fcf=base_fcf,
            growth_rates=params["growth_rates"],
            terminal_growth=params["terminal_growth"],
            wacc=wacc,
            shares_outstanding=shares_outstanding,
            net_debt=net_debt,
            current_price=current_price,
            scenario=name,
        )
    return results


# ---------------------------------------------------------------------------
# Relative Valuation (Comps)
# ---------------------------------------------------------------------------

def calc_multiples(
    price: float,
    eps_ttm: Optional[float] = None,
    eps_fwd: Optional[float] = None,
    revenue_ttm: Optional[float] = None,
    ebitda_ttm: Optional[float] = None,
    fcf_ttm: Optional[float] = None,
    book_value: Optional[float] = None,
    shares: Optional[float] = None,
    enterprise_value: Optional[float] = None,
    eps_growth: Optional[float] = None,
) -> dict:
    """Compute common valuation multiples. All inputs per-share or total (consistent)."""
    m = {}
    if eps_ttm and eps_ttm > 0:
        m["P/E_ttm"] = round(price / eps_ttm, 2)
    if eps_fwd and eps_fwd > 0:
        m["P/E_fwd"] = round(price / eps_fwd, 2)
    if eps_fwd and eps_fwd > 0 and eps_growth and eps_growth > 0:
        m["PEG"] = round((price / eps_fwd) / (eps_growth * 100), 2)
    if book_value and book_value > 0:
        m["P/B"] = round(price / book_value, 2)
    if shares and revenue_ttm and revenue_ttm > 0:
        m["P/S"] = round((price * shares) / revenue_ttm, 2)
    if fcf_ttm and fcf_ttm > 0 and shares:
        m["P/FCF"] = round((price * shares) / fcf_ttm, 2)
    if enterprise_value and ebitda_ttm and ebitda_ttm > 0:
        m["EV/EBITDA"] = round(enterprise_value / ebitda_ttm, 2)
    if enterprise_value and revenue_ttm and revenue_ttm > 0:
        m["EV/Revenue"] = round(enterprise_value / revenue_ttm, 2)
    return m


def comps_table(tickers_data: list[dict]) -> pd.DataFrame:
    """
    Build a peer comparison table from a list of ticker metric dicts.
    Each dict should have keys: ticker, price, eps_ttm, revenue_ttm, ebitda_ttm, ...
    """
    rows = []
    for t in tickers_data:
        ticker = t.pop("ticker", "?")
        multiples = calc_multiples(**t)
        multiples["ticker"] = ticker
        rows.append(multiples)
    df = pd.DataFrame(rows).set_index("ticker")
    return df
