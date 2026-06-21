#!/usr/bin/env python3
"""
scripts/test_phase_8b0_quiver.py

Phase 8B-0 — Quiver Quantitative ingestion layer test suite.

Runs entirely without real network. ``requests.get`` is patched and the
QUIVER_API_KEY module global is forced empty/non-empty per case, so every
fetcher exercises its fail-closed / parse path. ``compute_dark_pool_signal`` is
tested against a mocked ``fetch_dark_pool``.

Usage:
    python3 scripts/test_phase_8b0_quiver.py
"""

from __future__ import annotations

import os
import sys
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import requests  # noqa: E402

import lib.quiver_fetcher as qf  # noqa: E402


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
    """Clear the @st.cache_data caches so each case re-executes the body."""
    for fn in (qf.fetch_dark_pool, qf.fetch_congress_trades,
               qf.fetch_insider_trades, qf.fetch_hedge_fund_positions):
        try:
            fn.clear()
        except Exception:  # noqa: BLE001
            pass


class _Resp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


_ORIG_KEY = qf.QUIVER_API_KEY


# ---------------------------------------------------------------------------
# §8B0-Q1 — fetch_dark_pool returns [] when key is empty
# ---------------------------------------------------------------------------
def test_q1():
    _clear()
    qf.QUIVER_API_KEY = ""
    try:
        result = qf.fetch_dark_pool("AAPL")
    finally:
        qf.QUIVER_API_KEY = _ORIG_KEY
    check("§8B0-Q1 empty key -> []", result == [], repr(result))


# ---------------------------------------------------------------------------
# §8B0-Q2 — fetch_dark_pool returns [] on network error
# ---------------------------------------------------------------------------
def test_q2():
    _clear()
    qf.QUIVER_API_KEY = "test_key"

    def _boom(*a, **k):
        raise ConnectionError("network disabled in test")

    try:
        with mock.patch.object(requests, "get", _boom):
            result = qf.fetch_dark_pool("AAPL")
    finally:
        qf.QUIVER_API_KEY = _ORIG_KEY
    check("§8B0-Q2 network error -> []", result == [], repr(result))


# ---------------------------------------------------------------------------
# §8B0-Q3 — fetch_dark_pool parses response correctly
# ---------------------------------------------------------------------------
def test_q3():
    _clear()
    qf.QUIVER_API_KEY = "test_key"
    payload = [{
        "Date": "2026-06-20", "Ticker": "AAPL", "Price": 195.0,
        "Size": 10000, "Amount": 1950000,
    }]

    def _ok(*a, **k):
        return _Resp(payload)

    try:
        with mock.patch.object(requests, "get", _ok):
            result = qf.fetch_dark_pool("AAPL")
    finally:
        qf.QUIVER_API_KEY = _ORIG_KEY

    ok = (
        isinstance(result, list)
        and len(result) == 1
        and result[0].get("source") == "quiver_dark_pool"
        and result[0].get("ticker") == "AAPL"
        and abs(result[0].get("price", 0) - 195.0) < 1e-9
        and result[0].get("size") == 10000
        and abs(result[0].get("amount", 0) - 1950000.0) < 1e-6
    )
    check("§8B0-Q3 parses one record w/ source", ok, repr(result))


# ---------------------------------------------------------------------------
# §8B0-Q4 — compute_dark_pool_signal insufficient_data when < 3 records
# ---------------------------------------------------------------------------
def test_q4():
    recs = [
        {"date": "d1", "ticker": "AAPL", "price": 10.0, "size": 1,
         "amount": 100.0, "prev_close": 9.0, "source": "quiver_dark_pool"},
        {"date": "d2", "ticker": "AAPL", "price": 11.0, "size": 1,
         "amount": 100.0, "prev_close": 9.0, "source": "quiver_dark_pool"},
    ]
    with mock.patch.object(qf, "fetch_dark_pool", lambda *a, **k: recs):
        result = qf.compute_dark_pool_signal("AAPL")
    check(
        "§8B0-Q4 <3 records -> insufficient_data + degraded",
        result["net_direction"] == "insufficient_data" and result["degraded"] is True,
        repr(result),
    )


# ---------------------------------------------------------------------------
# §8B0-Q5 — compute_dark_pool_signal detects bullish
# ---------------------------------------------------------------------------
def test_q5():
    # 4 buy prints (price > prev_close) of 100 + 1 sell of 50 -> ratio ~0.89.
    recs = (
        [{"date": f"d{i}", "ticker": "AAPL", "price": 10.0, "size": 1,
          "amount": 100.0, "prev_close": 9.0, "source": "quiver_dark_pool"}
         for i in range(4)]
        + [{"date": "d5", "ticker": "AAPL", "price": 8.0, "size": 1,
            "amount": 50.0, "prev_close": 9.0, "source": "quiver_dark_pool"}]
    )
    with mock.patch.object(qf, "fetch_dark_pool", lambda *a, **k: recs):
        result = qf.compute_dark_pool_signal("AAPL")
    check(
        "§8B0-Q5 buy_ratio>0.65 -> bullish",
        result["net_direction"] == "bullish",
        repr(result),
    )


# ---------------------------------------------------------------------------
# §8B0-Q6 — compute_dark_pool_signal detects bearish
# ---------------------------------------------------------------------------
def test_q6():
    # 1 buy of 50 + 4 sell prints (price < prev_close) of 100 -> ratio ~0.11.
    recs = (
        [{"date": "d0", "ticker": "AAPL", "price": 10.0, "size": 1,
          "amount": 50.0, "prev_close": 9.0, "source": "quiver_dark_pool"}]
        + [{"date": f"d{i}", "ticker": "AAPL", "price": 8.0, "size": 1,
            "amount": 100.0, "prev_close": 9.0, "source": "quiver_dark_pool"}
           for i in range(1, 5)]
    )
    with mock.patch.object(qf, "fetch_dark_pool", lambda *a, **k: recs):
        result = qf.compute_dark_pool_signal("AAPL")
    check(
        "§8B0-Q6 buy_ratio<0.35 -> bearish",
        result["net_direction"] == "bearish",
        repr(result),
    )


def main() -> int:
    test_q1()
    test_q2()
    test_q3()
    test_q4()
    test_q5()
    test_q6()

    print(f"\n{'=' * 60}")
    print(f"test_phase_8b0_quiver.py  —  PASS={PASS}  FAIL={FAIL}")
    print(f"{'=' * 60}")
    for f in _failures:
        print(f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
