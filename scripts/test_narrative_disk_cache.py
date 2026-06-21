#!/usr/bin/env python3
"""
scripts/test_narrative_disk_cache.py

Step 3 — Narrative Disk Cache test suite.

Verifies the disk-backed cold-start persistence layer added UNDER the in-memory
``@st.cache_data`` hot path of ``lib.signal_engine.llm_narrative_match``. The
disk layer must:

  * persist a real LLM narrative result atomically on a miss,
  * serve a fresh, fingerprint-matched entry WITHOUT calling the LLM,
  * treat an expired (>24h) entry as a miss,
  * treat a fingerprint mismatch (news changed) as a miss,
  * silently degrade to the live LLM call on ANY read/write failure
    (corrupt JSON, permission error) — never raise, never alter the result.

This test runs **entirely without real network or LLM calls**: Finnhub news is
mocked, the API-key check is mocked True, and the LLM JSON call is mocked with a
counter so we can assert exactly when the LLM is (not) invoked. The cache
directory is redirected to a throwaway temp dir (monkeypatching the module
global ``NARRATIVE_CACHE_DIR``), so no tracked path is touched.

Usage:
    python3 -B scripts/test_narrative_disk_cache.py
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


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


_se = importlib.import_module("lib.signal_engine")
_llm = importlib.import_module("lib.llm_orchestrator")
NarrativeResult = _se.NarrativeResult


# ---------------------------------------------------------------------------
# Fixtures (no network / no LLM)
# ---------------------------------------------------------------------------

# Two distinct news lists -> two distinct fingerprints.
NEWS_A = [
    {"headline": "AlphaCorp wins federal defense contract", "summary": "big award", "datetime": 0},
    {"headline": "AlphaCorp unveils next-gen inference chip", "summary": "ai launch", "datetime": 0},
]
NEWS_B = [
    {"headline": "AlphaCorp faces unrelated lawsuit", "summary": "legal noise", "datetime": 0},
]

# A parseable LLM payload that maps to a LIVE NarrativeResult (stage "early").
PAYLOAD_LIVE = {
    "theme_tags": ["AI"],
    "narrative_stage": "early",
    "macro_alignment": "aligned",
    "narrative_strength": "strong",
    "reasoning": "fresh accelerating AI story",
    "catalyst_summary": "federal contract award",
    "catalyst_horizon": ["short"],
    "catalyst_recency": "recent",
    "already_priced_in": False,
}

# A DIFFERENT parseable payload (distinct stage/reasoning) used to prove the
# disk hit returns the cached value, not a freshly-computed LLM value.
PAYLOAD_DIFF = {
    "theme_tags": ["semiconductor"],
    "narrative_stage": "early",
    "macro_alignment": "neutral",
    "narrative_strength": "moderate",
    "reasoning": "LLM-FRESH-VALUE",
    "catalyst_summary": "",
    "catalyst_horizon": [],
    "catalyst_recency": "none",
    "already_priced_in": False,
}


def _drive(ticker: str, regime: str, news: list, payload: dict, api_key: bool = True):
    """Run ONE ``llm_narrative_match`` call with all deps mocked.

    Clears the in-memory ``@st.cache_data`` hot layer FIRST so the call actually
    consults the disk layer. Returns ``(result, n_llm_calls)``.
    """
    state = {"calls": 0}

    def _fake_json_call(client, max_tokens, system, user):
        state["calls"] += 1
        return payload

    try:
        _se.llm_narrative_match.clear()
    except Exception:  # noqa: BLE001
        pass
    with mock.patch.object(_se, "fetch_company_news", lambda *a, **k: news), \
            mock.patch.object(_se, "_has_llm_api_key", lambda: api_key), \
            mock.patch.object(_llm, "_get_client", lambda: object()), \
            mock.patch.object(_llm, "_llm_json_call", _fake_json_call):
        res = _se.llm_narrative_match(ticker, regime)
    return res, state["calls"]


def _load(path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _dump(path, entry: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(entry, fh)


# ---------------------------------------------------------------------------
# Run all cases inside a redirected (throwaway) cache dir
# ---------------------------------------------------------------------------

_tmp = tempfile.mkdtemp(prefix="narrative_cache_test_")
_orig_dir = _se.NARRATIVE_CACHE_DIR
_se.NARRATIVE_CACHE_DIR = _se._Path(_tmp)
try:
    # ----- §NC-1  Cache miss -> LLM called -> result written to disk ---------
    res, n = _drive("AAA", "risk_on", NEWS_A, PAYLOAD_LIVE)
    check("§NC-1a miss calls the LLM exactly once", n == 1, f"n={n}")
    check("§NC-1b LLM result returned (data_source live, stage early)",
          res.data_source == "live" and res.narrative_stage == "early", str(res))
    _fp_a = _se._news_fingerprint(NEWS_A)
    _path_a = _se._narrative_cache_path("AAA", "risk_on", _fp_a)
    check("§NC-1c disk file written at the fingerprinted path", _path_a.exists(),
          str(_path_a))
    if _path_a.exists():
        _entry = _load(_path_a)
        check("§NC-1d entry schema is complete + correct",
              _entry.get("ticker") == "AAA"
              and _entry.get("macro_regime") == "risk_on"
              and _entry.get("news_fingerprint") == _fp_a
              and isinstance(_entry.get("cached_at"), str)
              and isinstance(_entry.get("result"), dict)
              and _entry["result"].get("narrative_stage") == "early",
              str(_entry))

    # ----- §NC-2  Cache hit (fresh, fingerprint matches) -> LLM NOT called ---
    # Same ticker/regime/news; in-memory layer is cleared by _drive, so a no-LLM
    # result can ONLY have come from the disk layer written in §NC-1.
    res2, n2 = _drive("AAA", "risk_on", NEWS_A, PAYLOAD_LIVE)
    check("§NC-2a fresh hit does NOT call the LLM", n2 == 0, f"n={n2}")
    check("§NC-2b cached result returned (stage early)",
          res2.narrative_stage == "early" and res2.data_source == "live", str(res2))

    # ----- §NC-3  Cache hit but TTL expired (>24h) -> miss, LLM called -------
    res, n = _drive("BBB", "risk_on", NEWS_A, PAYLOAD_LIVE)  # populate
    check("§NC-3 setup populates the cache (LLM called once)", n == 1, f"n={n}")
    _fp_b = _se._news_fingerprint(NEWS_A)
    _path_b = _se._narrative_cache_path("BBB", "risk_on", _fp_b)
    _entry = _load(_path_b)
    _entry["cached_at"] = (datetime.utcnow() - timedelta(hours=25)).isoformat()
    _dump(_path_b, _entry)
    res3, n3 = _drive("BBB", "risk_on", NEWS_A, PAYLOAD_LIVE)
    check("§NC-3a expired entry treated as a miss (LLM called)", n3 == 1, f"n={n3}")
    _entry2 = _load(_path_b)
    _fresh = datetime.utcnow() - datetime.fromisoformat(_entry2["cached_at"])
    check("§NC-3b a fresh entry is rewritten on the miss",
          _fresh < timedelta(hours=1), f"age={_fresh}")

    # ----- §NC-4  Fingerprint mismatch (news changed) -> miss, LLM called ----
    res, n = _drive("CCC", "risk_on", NEWS_A, PAYLOAD_LIVE)  # populate at fp(A)
    _fp_c = _se._news_fingerprint(NEWS_A)
    _path_c = _se._narrative_cache_path("CCC", "risk_on", _fp_c)
    # (i) Corrupt the INTERNAL fingerprint at the same path -> internal check miss.
    _entry = _load(_path_c)
    _entry["news_fingerprint"] = "deadbeef"
    _dump(_path_c, _entry)
    res4, n4 = _drive("CCC", "risk_on", NEWS_A, PAYLOAD_LIVE)
    check("§NC-4a internal fingerprint mismatch -> miss (LLM called)",
          n4 == 1, f"n={n4}")
    # (ii) News actually changes -> different fingerprint -> different path miss.
    res4b, n4b = _drive("CCC", "risk_on", NEWS_B, PAYLOAD_LIVE)
    _fp_c2 = _se._news_fingerprint(NEWS_B)
    check("§NC-4b changed news yields a different fingerprint", _fp_c2 != _fp_c,
          f"{_fp_c2} vs {_fp_c}")
    check("§NC-4c changed-news fingerprint is a miss (LLM called)", n4b == 1,
          f"n={n4b}")

    # ----- §NC-5  Disk read failure (corrupt JSON) -> silent fallthrough -----
    _fp_d = _se._news_fingerprint(NEWS_A)
    _path_d = _se._narrative_cache_path("DDD", "risk_on", _fp_d)
    _path_d.parent.mkdir(parents=True, exist_ok=True)
    _path_d.write_text("{ this is not valid json", encoding="utf-8")
    res5, n5 = _drive("DDD", "risk_on", NEWS_A, PAYLOAD_LIVE)
    check("§NC-5a corrupt JSON read -> silent miss (LLM called, no raise)",
          n5 == 1, f"n={n5}")
    check("§NC-5b correct result still returned", res5.narrative_stage == "early",
          str(res5))
    _entry = _load(_path_d)  # must now be valid JSON (overwritten by the miss-write)
    check("§NC-5c corrupt file was overwritten with a valid entry",
          _entry.get("result", {}).get("narrative_stage") == "early", str(_entry))

    # ----- §NC-6  Disk write failure (permission error) -> silently swallowed -
    _state = {"calls": 0}

    def _fake_json_call(client, max_tokens, system, user):
        _state["calls"] += 1
        return PAYLOAD_LIVE

    try:
        _se.llm_narrative_match.clear()
    except Exception:  # noqa: BLE001
        pass
    with mock.patch.object(_se, "fetch_company_news", lambda *a, **k: NEWS_A), \
            mock.patch.object(_se, "_has_llm_api_key", lambda: True), \
            mock.patch.object(_llm, "_get_client", lambda: object()), \
            mock.patch.object(_llm, "_llm_json_call", _fake_json_call), \
            mock.patch.object(_se.os, "replace", side_effect=PermissionError("denied")):
        res6 = _se.llm_narrative_match("EEE", "risk_on")
    check("§NC-6a write failure does not prevent the LLM call", _state["calls"] == 1,
          f"n={_state['calls']}")
    check("§NC-6b correct result still returned despite write failure",
          res6.narrative_stage == "early" and res6.data_source == "live", str(res6))
    _fp_e = _se._news_fingerprint(NEWS_A)
    _path_e = _se._narrative_cache_path("EEE", "risk_on", _fp_e)
    check("§NC-6c failed atomic write leaves no final cache file",
          not _path_e.exists(), str(_path_e))

    # ----- §NC-7  Mutation probe: cached value (not LLM value) is returned ----
    # Pre-seed a DISTINCTIVE cached result, then mock the LLM to return a
    # DIFFERENT value. A hit must return the cached sentinel and never call LLM.
    _sentinel = NarrativeResult(
        theme_tags=["AI"],
        narrative_stage="mature",
        macro_alignment="neutral",
        narrative_strength="weak",
        reasoning="CACHED-SENTINEL",
        data_source="live",
        catalyst_summary="cached catalyst",
        catalyst_horizon=["long"],
        catalyst_recency="moderate",
        already_priced_in=True,
    )
    _fp_f = _se._news_fingerprint(NEWS_A)
    _se._write_narrative_cache("FFF", "risk_on", _fp_f, _sentinel)
    res7, n7 = _drive("FFF", "risk_on", NEWS_A, PAYLOAD_DIFF)
    check("§NC-7a hit bypasses the LLM entirely", n7 == 0, f"n={n7}")
    check("§NC-7b returned value is the CACHED sentinel, not the LLM value",
          res7.reasoning == "CACHED-SENTINEL" and res7.reasoning != PAYLOAD_DIFF["reasoning"],
          str(res7))
    check("§NC-7c full cached object fidelity (stage/flags reconstructed)",
          res7.narrative_stage == "mature" and res7.already_priced_in is True
          and res7.catalyst_horizon == ["long"], str(res7))

    # ----- §NC-8  Fingerprint: separator + prompt-scope alignment ------------
    _fp = _se._news_fingerprint
    # (a) Record separator prevents boundary collisions across headlines.
    collide_x = [{"headline": "ab", "summary": ""}, {"headline": "c", "summary": ""}]
    collide_y = [{"headline": "a", "summary": ""}, {"headline": "bc", "summary": ""}]
    check("§NC-8a headline boundary shift -> different fingerprint",
          _fp(collide_x) != _fp(collide_y), f"{_fp(collide_x)} vs {_fp(collide_y)}")
    # (b) Field separator prevents headline/summary boundary collisions.
    field_x = [{"headline": "ab", "summary": "c"}]
    field_y = [{"headline": "a", "summary": "bc"}]
    check("§NC-8b headline/summary boundary shift -> different fingerprint",
          _fp(field_x) != _fp(field_y), f"{_fp(field_x)} vs {_fp(field_y)}")
    # (c) Summary IS part of the key (a summary edit changes the prompt).
    summ_a = [{"headline": "h", "summary": "alpha"}]
    summ_b = [{"headline": "h", "summary": "beta"}]
    check("§NC-8c summary change -> different fingerprint (no stale hit)",
          _fp(summ_a) != _fp(summ_b), f"{_fp(summ_a)} vs {_fp(summ_b)}")
    # (d) A change BEYOND the news[:25] slice does NOT alter the key (the prompt
    #     never sees item 25+), so it must not cause an unnecessary miss.
    base25 = [{"headline": f"h{i}", "summary": f"s{i}"} for i in range(25)]
    extra_same = base25 + [{"headline": "EXTRA", "summary": "BEYOND-SLICE"}]
    extra_diff = base25 + [{"headline": "OTHER", "summary": "ALSO-BEYOND"}]
    check("§NC-8d items past index 25 do not affect the fingerprint",
          _fp(base25) == _fp(extra_same) == _fp(extra_diff),
          f"{_fp(base25)} / {_fp(extra_same)} / {_fp(extra_diff)}")
    # (e) A summary edit BEYOND char 160 does NOT alter the prompt (it truncates
    #     summary to [:160]) and so must not alter the key.
    long_a = [{"headline": "h", "summary": "x" * 160 + "AAAAA"}]
    long_b = [{"headline": "h", "summary": "x" * 160 + "BBBBB"}]
    check("§NC-8e summary change past char 160 does not affect the fingerprint",
          _fp(long_a) == _fp(long_b), f"{_fp(long_a)} vs {_fp(long_b)}")
    # (f) A literal "|" in a field cannot collide across the headline/summary
    #     boundary (json.dumps serialization, not a raw "|" delimiter).
    pipe_x = [{"headline": "a|b", "summary": "c"}]
    pipe_y = [{"headline": "a", "summary": "b|c"}]
    check("§NC-8f literal '|' in a field -> different fingerprint (no field collision)",
          _fp(pipe_x) != _fp(pipe_y), f"{_fp(pipe_x)} vs {_fp(pipe_y)}")
finally:
    _se.NARRATIVE_CACHE_DIR = _orig_dir
    try:
        _se.llm_narrative_match.clear()
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(_tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n".join(_failures))
print(f"\n{'=' * 60}")
print(f"Narrative Disk Cache (Step 3):  {PASS} passed, {FAIL} failed")
print(f"{'=' * 60}")
sys.exit(1 if FAIL else 0)
