#!/usr/bin/env python3
"""
scripts/test_phase_8b0_massive.py

Phase 8B-0 — Massive Options ingestion layer test suite.

Runs entirely without real network. ``requests.get`` is patched and the
MASSIVE_API_KEY module global is forced empty/non-empty per case. Verifies the
fail-closed degraded snapshots, single-contract mapping into the existing
Phase 2E OptionChainSnapshot/OptionContractSnapshot schema, and the
free-tier (no-Greeks) warning.

Usage:
    python3 scripts/test_phase_8b0_massive.py
"""

from __future__ import annotations

import os
import sys
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import requests  # noqa: E402

import lib.massive_options_fetcher as mf  # noqa: E402


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


def _clear():
    try:
        mf.fetch_options_chain.clear()
    except Exception:  # noqa: BLE001
        pass


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


_ORIG_KEY = mf.MASSIVE_API_KEY


# ---------------------------------------------------------------------------
# §8B0-M1 — key missing -> degraded snapshot
# ---------------------------------------------------------------------------
def test_m1():
    _clear()
    mf.MASSIVE_API_KEY = ""
    try:
        result = mf.fetch_options_chain("SPY")
    finally:
        mf.MASSIVE_API_KEY = _ORIG_KEY
    check(
        "§8B0-M1 missing key -> empty contracts + warning",
        result.contracts == [] and "massive_api_key_missing" in result.warnings,
        f"contracts={len(result.contracts)} warnings={result.warnings}",
    )


# ---------------------------------------------------------------------------
# §8B0-M2 — API error -> degraded snapshot
# ---------------------------------------------------------------------------
def test_m2():
    _clear()
    mf.MASSIVE_API_KEY = "test_key"

    def _boom(*a, **k):
        raise ConnectionError("network disabled in test")

    try:
        with mock.patch.object(requests, "get", _boom):
            result = mf.fetch_options_chain("SPY")
    finally:
        mf.MASSIVE_API_KEY = _ORIG_KEY
    check(
        "§8B0-M2 API error -> empty contracts + massive_api_error",
        result.contracts == [] and any("massive_api_error" in w for w in result.warnings),
        f"contracts={len(result.contracts)} warnings={result.warnings}",
    )


# ---------------------------------------------------------------------------
# §8B0-M3 — parses a single contract correctly
# ---------------------------------------------------------------------------
def test_m3():
    _clear()
    mf.MASSIVE_API_KEY = "test_key"
    payload = {
        "results": [{
            "details": {
                "contract_type": "call",
                "expiration_date": "2026-06-27",
                "strike_price": 580.0,
                "ticker": "SPY260627C00580000",
            },
            "greeks": {"delta": 0.45, "gamma": 0.03, "theta": -0.12, "vega": 0.8},
            "implied_volatility": 0.18,
            "open_interest": 5000,
            "day": {"close": 3.5, "volume": 1200, "open": 3.2},
            "underlying_asset": {"price": 578.0, "ticker": "SPY"},
        }],
        "next_url": None,
    }

    def _ok(*a, **k):
        return _Resp(payload)

    try:
        with mock.patch.object(requests, "get", _ok):
            result = mf.fetch_options_chain("SPY")
    finally:
        mf.MASSIVE_API_KEY = _ORIG_KEY

    ok = (
        len(result.contracts) == 1
        and abs((result.contracts[0].gamma or -1) - 0.03) < 1e-9
        and result.contracts[0].source == "massive"
        and result.contracts[0].option_type == "call"
        and abs(result.contracts[0].strike - 580.0) < 1e-9
        and result.contracts[0].open_interest == 5000
        and abs(result.underlying_price - 578.0) < 1e-9
    )
    check("§8B0-M3 single-contract mapping", ok, repr(result.contracts))


# ---------------------------------------------------------------------------
# §8B0-M4 — greeks absent -> greeks_unavailable warning
# ---------------------------------------------------------------------------
def test_m4():
    _clear()
    mf.MASSIVE_API_KEY = "test_key"
    payload = {
        "results": [{
            "details": {
                "contract_type": "put",
                "expiration_date": "2026-06-27",
                "strike_price": 560.0,
                "ticker": "SPY260627P00560000",
            },
            # NO "greeks" key (free tier).
            "implied_volatility": 0.20,
            "open_interest": 1500,
            "day": {"close": 2.1, "volume": 800, "open": 2.0},
            "underlying_asset": {"price": 578.0, "ticker": "SPY"},
        }],
        "next_url": None,
    }

    def _ok(*a, **k):
        return _Resp(payload)

    try:
        with mock.patch.object(requests, "get", _ok):
            result = mf.fetch_options_chain("SPY")
    finally:
        mf.MASSIVE_API_KEY = _ORIG_KEY

    ok = (
        len(result.warnings) >= 1
        and "greeks_unavailable" in result.warnings[0]
        and len(result.contracts) == 1
        and result.contracts[0].gamma is None
    )
    check("§8B0-M4 free tier -> greeks_unavailable warning", ok,
          f"warnings={result.warnings}")


# ---------------------------------------------------------------------------
# §8B0-M5 — bad contract is skipped, good contract is retained
# ---------------------------------------------------------------------------
def test_m5():
    _clear()
    mf.MASSIVE_API_KEY = "test_key"
    payload = {
        "results": [
            {  # valid (as in M3)
                "details": {
                    "contract_type": "call",
                    "expiration_date": "2026-06-27",
                    "strike_price": 580.0,
                    "ticker": "SPY260627C00580000",
                },
                "greeks": {"delta": 0.45, "gamma": 0.03, "theta": -0.12, "vega": 0.8},
                "implied_volatility": 0.18,
                "open_interest": 5000,
                "day": {"close": 3.5, "volume": 1200, "open": 3.2},
                "underlying_asset": {"price": 578.0, "ticker": "SPY"},
            },
            {  # invalid: day.open is non-numeric -> ValueError in _map_contract
                "details": {
                    "contract_type": "put",
                    "expiration_date": "2026-06-27",
                    "strike_price": 560.0,
                    "ticker": "SPY260627P00560000",
                },
                "greeks": {"delta": -0.4, "gamma": 0.02, "theta": -0.1, "vega": 0.7},
                "implied_volatility": 0.20,
                "open_interest": 1500,
                "day": {"close": 2.1, "volume": 800, "open": "not-a-number"},
                "underlying_asset": {"price": 578.0, "ticker": "SPY"},
            },
        ],
        "next_url": None,
    }

    def _ok(*a, **k):
        return _Resp(payload)

    try:
        with mock.patch.object(requests, "get", _ok):
            result = mf.fetch_options_chain("SPY")
    finally:
        mf.MASSIVE_API_KEY = _ORIG_KEY

    ok = (
        len(result.contracts) == 1
        and any("contract_skipped" in w for w in result.warnings)
        and abs(result.contracts[0].strike - 580.0) < 1e-9
    )
    check("§8B0-M5 bad contract skipped, good retained", ok,
          f"contracts={len(result.contracts)} warnings={result.warnings}")


def main() -> int:
    test_m1()
    test_m2()
    test_m3()
    test_m4()
    test_m5()

    print(f"\n{'=' * 60}")
    print(f"test_phase_8b0_massive.py  —  PASS={PASS}  FAIL={FAIL}")
    print(f"{'=' * 60}")
    for f in _failures:
        print(f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
