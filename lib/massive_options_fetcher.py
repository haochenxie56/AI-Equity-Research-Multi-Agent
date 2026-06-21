"""lib/massive_options_fetcher.py — Phase 8B-0 Massive Options ingestion layer.

Fetches an options chain (with Greeks / IV / OI when the plan provides them)
from Massive Options, which is Polygon under the hood (same base URL and the
v3 options-snapshot response shape).

This fetcher's ONLY job is network I/O + mapping the raw snapshot into the
existing Phase 2E schema (``OptionChainSnapshot`` / ``OptionContractSnapshot``)
with ``source="massive"`` — so the entire 2E payoff / liquidity / evidence
layer works unchanged downstream. It performs NO GEX/DEX computation (that is
lib/gex_dex.py).

Plan tiers:
* Starter plan -> real-time Greeks + daily OI present.
* Free tier    -> NO Greeks and NO OI. The fetcher maps what is available,
  leaves ``delta/gamma/theta/vega`` as ``None``, and records a warning. It
  never raises — the GEX/DEX calculator detects the ``None`` Greeks and
  degrades gracefully.

Conventions: key loaded module-level via ``os.getenv``; ``@st.cache_data``;
fail-closed (a degraded ``OptionChainSnapshot`` is returned, never an
exception).
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Optional

import requests
import streamlit as st
from dotenv import load_dotenv

from lib.reliability.options import OptionChainSnapshot, OptionContractSnapshot

# Load .env from the project root (one level up from lib/).
load_dotenv(Path(__file__).parent.parent / ".env")

MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "")
MASSIVE_BASE_URL = "https://api.polygon.io"  # Massive = Polygon, same base URL

_TIMEOUT = 15  # seconds
_PER_PAGE = 250  # v3 snapshot max page size
_MAX_PAGES = 5  # runaway-loop guard
# Placeholder used for underlying_price when no live price is available. The
# OptionChainSnapshot schema requires underlying_price > 0, so we cannot use
# 0.0; the accompanying warnings + metadata flag mark the value as unknown.
_PRICE_PLACEHOLDER = 0.01


# ---------------------------------------------------------------------------
# Expiry window mapping
# ---------------------------------------------------------------------------

def _expiry_window(expiry_filter: str, today: Optional[datetime.date] = None):
    """Map an *expiry_filter* label to an inclusive (gte, lte) ISO-date range.

    Returns ``(None, None)`` for ``"all"`` (no server-side date filter).
    Ranges are computed relative to *today* (defaults to the system date).
    """
    today = today or datetime.date.today()
    wd = today.weekday()  # Mon=0 .. Sun=6

    if expiry_filter == "this_week":
        # Friday of the current week (or the coming Friday on the weekend).
        friday = today + datetime.timedelta(days=(4 - wd) % 7)
        return today.isoformat(), friday.isoformat()
    if expiry_filter == "next_week":
        next_monday = today + datetime.timedelta(days=(7 - wd))
        next_friday = next_monday + datetime.timedelta(days=4)
        return next_monday.isoformat(), next_friday.isoformat()
    if expiry_filter == "monthly":
        return today.isoformat(), (today + datetime.timedelta(days=35)).isoformat()
    # "all" or anything unrecognized -> no date filter.
    return None, None


# ---------------------------------------------------------------------------
# Contract mapping
# ---------------------------------------------------------------------------

def _map_contract(
    raw: dict, ticker: str, as_of: str
) -> tuple[Optional[OptionContractSnapshot], Optional[str]]:
    """Map one raw v3 snapshot contract -> ``OptionContractSnapshot``.

    Returns a ``(contract, warning)`` tuple:

    * ``(contract, None)`` — mapped cleanly.
    * ``(contract, "greeks_unavailable: free tier")`` — mapped, but Greeks are
      absent (free tier).
    * ``(None, "contract_skipped: ...")`` — required fields missing/invalid OR
      any exception while mapping. The whole body is wrapped so a single bad
      contract never aborts the chain; the caller skips ``None`` and records
      the warning.
    """
    try:
        details = raw.get("details") or {}
        ctype = details.get("contract_type")
        if ctype not in ("call", "put"):
            return None, f"contract_skipped: bad contract_type {ctype!r}"

        strike = float(details.get("strike_price"))
        if strike <= 0.0:
            return None, f"contract_skipped: non-positive strike {strike!r}"

        expiration = details.get("expiration_date")
        if not expiration:
            return None, "contract_skipped: missing expiration_date"

        day = raw.get("day") or {}
        open_ = day.get("open")
        close_ = day.get("close")

        # bid ~ day.open, ask ~ day.close (approximation — the v3 snapshot has
        # no explicit NBBO bid/ask). The schema requires ask >= bid >= 0, so
        # coerce and swap if the day's open exceeded its close.
        bid = open_ if open_ is not None else close_
        ask = close_ if close_ is not None else open_
        bid = max(0.0, float(bid)) if bid is not None else 0.0
        ask = max(0.0, float(ask)) if ask is not None else 0.0
        if ask < bid:
            bid, ask = ask, bid

        last = None
        if close_ is not None:
            last = max(0.0, float(close_))

        volume = day.get("volume")
        volume = int(volume) if isinstance(volume, (int, float)) and volume >= 0 else None

        oi = raw.get("open_interest")
        oi = int(oi) if isinstance(oi, (int, float)) and oi >= 0 else None

        iv = raw.get("implied_volatility")
        iv = float(iv) if isinstance(iv, (int, float)) and iv >= 0 else None

        greeks = raw.get("greeks") or {}

        def _g(name):
            v = greeks.get(name)
            return float(v) if v is not None else None

        delta = _g("delta")
        # delta must be within [-1, 1] per schema; out-of-range -> drop to None.
        if delta is not None and not (-1.0 <= delta <= 1.0):
            delta = None
        gamma = _g("gamma")
        theta = _g("theta")
        vega = _g("vega")

        contract = OptionContractSnapshot(
            underlying=ticker,
            option_type=ctype,
            expiration=str(expiration),
            strike=strike,
            bid=bid,
            ask=ask,
            last=last,
            volume=volume,
            open_interest=oi,
            implied_volatility=iv,
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            as_of=as_of,
            source="massive",
        )
        warning = "greeks_unavailable: free tier" if gamma is None else None
        return contract, warning
    except Exception as e:  # noqa: BLE001 — skip a single unmappable contract
        return None, f"contract_skipped: {e}"


def _empty_chain(ticker: str, as_of: str, warning: str, source: str) -> OptionChainSnapshot:
    """Build a degraded, empty chain snapshot (schema requires price > 0)."""
    return OptionChainSnapshot(
        underlying=ticker,
        underlying_price=_PRICE_PLACEHOLDER,
        expirations=[],
        contracts=[],
        as_of=as_of,
        source=source,
        warnings=[warning],
        metadata={"underlying_price_unavailable": True},
    )


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def fetch_options_chain(
    ticker: str, expiry_filter: str = "this_week"
) -> OptionChainSnapshot:
    """Fetch an options chain for *ticker* into an ``OptionChainSnapshot``.

    *expiry_filter*: ``"this_week" | "next_week" | "monthly" | "all"``.

    Pagination: the v3 endpoint returns up to 250 contracts per page with a
    ``next_url`` continuation; up to ``_MAX_PAGES`` pages are fetched. TTL 15m.

    Fail-closed: a degraded (empty-contracts) snapshot is returned on missing
    key or API error — never an exception.
    """
    as_of = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if not MASSIVE_API_KEY:
        return _empty_chain(
            ticker, as_of, "massive_api_key_missing", "massive_unavailable"
        )

    try:
        gte, lte = _expiry_window(expiry_filter)
        params: Optional[dict] = {
            "apiKey": MASSIVE_API_KEY,
            "limit": _PER_PAGE,
        }
        if gte and lte:
            params["expiration_date.gte"] = gte
            params["expiration_date.lte"] = lte

        url: Optional[str] = f"{MASSIVE_BASE_URL}/v3/snapshot/options/{ticker}"
        raw_contracts: list[dict] = []
        pages = 0
        while url and pages < _MAX_PAGES:
            if pages == 0:
                resp = requests.get(url, params=params, timeout=_TIMEOUT)
            else:
                # next_url already carries the query; only the key is appended.
                resp = requests.get(
                    url, params={"apiKey": MASSIVE_API_KEY}, timeout=_TIMEOUT
                )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") if isinstance(data, dict) else None
            if results:
                raw_contracts.extend(results)
            url = data.get("next_url") if isinstance(data, dict) else None
            pages += 1

        contracts: list[OptionContractSnapshot] = []
        underlying_price: Optional[float] = None
        warnings: list[str] = []

        for raw in raw_contracts:
            if not isinstance(raw, dict):
                continue
            if underlying_price is None:
                ua = raw.get("underlying_asset") or {}
                p = ua.get("price")
                if isinstance(p, (int, float)) and p > 0:
                    underlying_price = float(p)
            contract, warning = _map_contract(raw, ticker, as_of)
            # Dedup the (chain-wide) "greeks_unavailable" warning; keep each
            # distinct "contract_skipped: ..." message.
            if warning and warning not in warnings:
                warnings.append(warning)
            if contract is not None:
                contracts.append(contract)

        if not contracts:
            # Nothing usable came back; degrade but do not raise.
            return _empty_chain(
                ticker, as_of, "massive_no_contracts", "massive_unavailable"
            )

        expirations = sorted({c.expiration for c in contracts})

        if underlying_price is None:
            warnings.append("underlying_price_unavailable")
            price = _PRICE_PLACEHOLDER
            metadata = {"underlying_price_unavailable": True}
        else:
            price = underlying_price
            metadata = {}

        return OptionChainSnapshot(
            underlying=ticker,
            underlying_price=price,
            expirations=expirations,
            contracts=contracts,
            as_of=as_of,
            source="massive",
            warnings=warnings,
            metadata=metadata,
        )

    except Exception as e:  # noqa: BLE001 — fail-closed
        return _empty_chain(
            ticker, as_of, f"massive_api_error: {e}", "massive_unavailable"
        )
