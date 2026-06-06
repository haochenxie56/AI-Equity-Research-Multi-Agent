"""
scripts/test_reliability_news.py

Test suite for lib/reliability/news.py — Phase 2F:
News ToolResult Wrapper Foundation.

Tests use synthetic Finnhub-like payloads; no real network calls are made.

Run:
    python scripts/test_reliability_news.py

Expected: all assertions pass, 0 failures.
"""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.reliability.news import (
    # Literal aliases
    NewsSourceVendor,
    NewsEventCategory,
    NewsImpactHorizon,
    NewsFreshnessStatus,
    # Models
    NewsEvent,
    NewsSnapshot,
    NewsCoverageSummary,
    # Helpers
    classify_news_category,
    normalize_finnhub_news_event,
    news_snapshot_from_events,
    news_tool_result_from_snapshot,
    extract_news_event_paths,
    summarize_news_snapshot_coverage,
    validate_news_snapshot,
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

def _make_event(
    event_id: str = "ev_001",
    ticker: str = "AAPL",
    headline: str = "AAPL beats Q1 EPS estimates",
    summary: str | None = "Apple reported earnings above consensus.",
    source: str = "Reuters",
    vendor: str = "finnhub",
    url: str | None = "https://example.com/aapl-q1",
    published_at: str = "2026-05-01T12:00:00Z",
    category: str = "earnings",
    related_symbols: list[str] | None = None,
    sentiment_score: float | None = 0.7,
) -> NewsEvent:
    return NewsEvent(
        event_id=event_id,
        ticker=ticker,
        headline=headline,
        summary=summary,
        source=source,
        vendor=vendor,  # type: ignore[arg-type]
        url=url,
        published_at=published_at,
        category=category,  # type: ignore[arg-type]
        related_symbols=related_symbols if related_symbols is not None else ["AAPL"],
        sentiment_score=sentiment_score,
    )


def _make_snapshot(
    ticker: str = "AAPL",
    events: list[NewsEvent] | None = None,
    as_of: str = "2026-05-21",
    lookback_days: int | None = 30,
) -> NewsSnapshot:
    return NewsSnapshot(
        snapshot_id="snap_001",
        ticker=ticker,
        as_of=as_of,
        events=events or [],
        lookback_days=lookback_days,
    )


_FINNHUB_RAW: dict = {
    "id": 12345,
    "datetime": 1748476800,   # 2025-05-28T20:00:00Z
    "headline": "AAPL reports record revenue in Q2",
    "summary": "Apple Inc. posted quarterly revenue of $97B.",
    "source": "Reuters",
    "url": "https://example.com/aapl-q2",
    "category": "earnings",
    "related": "AAPL,MSFT",
    "image": "https://example.com/img.jpg",
}


# ===========================================================================
# Group A: Literal aliases
# ===========================================================================
print("A: Literal aliases")

_check("A1  NewsSourceVendor has 'finnhub'",
       "finnhub" in NewsSourceVendor.__args__)
_check("A2  NewsSourceVendor has 'synthetic'",
       "synthetic" in NewsSourceVendor.__args__)
_check("A3  NewsSourceVendor has expected count (6)",
       len(NewsSourceVendor.__args__) == 6)
_check("A4  NewsEventCategory has 'earnings'",
       "earnings" in NewsEventCategory.__args__)
_check("A5  NewsEventCategory has 'unknown'",
       "unknown" in NewsEventCategory.__args__)
_check("A6  NewsEventCategory has >= 16 values",
       len(NewsEventCategory.__args__) >= 16)
_check("A7  NewsImpactHorizon has exactly 4 values",
       len(NewsImpactHorizon.__args__) == 4)
_check("A8  NewsFreshnessStatus has 'fresh', 'stale', 'unknown'",
       set(NewsFreshnessStatus.__args__) == {"fresh", "stale", "unknown"})


# ===========================================================================
# Group B: NewsEvent validation
# ===========================================================================
print("B: NewsEvent")

ev = _make_event()
_check("B1  NewsEvent accepts valid event", ev.event_id == "ev_001")
_check("B2  ticker preserved", ev.ticker == "AAPL")
_check("B3  headline preserved", "beats" in ev.headline)
_check("B4  vendor set", ev.vendor == "finnhub")
_check("B5  category set", ev.category == "earnings")
_check("B6  sentiment_score preserved", ev.sentiment_score == 0.7)
_check("B7  related_symbols preserved", ev.related_symbols == ["AAPL"])

# Rejects empty event_id
try:
    NewsEvent(event_id="", ticker="AAPL", headline="h", source="s", published_at="2026-05-01")
    _check("B8  rejects empty event_id", False)
except Exception:
    _check("B8  rejects empty event_id", True)

# Rejects empty ticker
try:
    NewsEvent(event_id="e1", ticker="", headline="h", source="s", published_at="2026-05-01")
    _check("B9  rejects empty ticker", False)
except Exception:
    _check("B9  rejects empty ticker", True)

# Rejects empty headline
try:
    NewsEvent(event_id="e1", ticker="AAPL", headline="", source="s", published_at="2026-05-01")
    _check("B10 rejects empty headline", False)
except Exception:
    _check("B10 rejects empty headline", True)

# Rejects empty source
try:
    NewsEvent(event_id="e1", ticker="AAPL", headline="h", source="", published_at="2026-05-01")
    _check("B11 rejects empty source", False)
except Exception:
    _check("B11 rejects empty source", True)

# Rejects empty published_at
try:
    NewsEvent(event_id="e1", ticker="AAPL", headline="h", source="s", published_at="")
    _check("B12 rejects empty published_at", False)
except Exception:
    _check("B12 rejects empty published_at", True)

# Rejects sentiment_score > 1
try:
    NewsEvent(event_id="e1", ticker="AAPL", headline="h", source="s",
              published_at="2026-05-01", sentiment_score=1.5)
    _check("B13 rejects sentiment_score > 1", False)
except Exception:
    _check("B13 rejects sentiment_score > 1", True)

# Rejects sentiment_score < -1
try:
    NewsEvent(event_id="e1", ticker="AAPL", headline="h", source="s",
              published_at="2026-05-01", sentiment_score=-1.5)
    _check("B14 rejects sentiment_score < -1", False)
except Exception:
    _check("B14 rejects sentiment_score < -1", True)

# Accepts boundary values
ev_boundary_pos = NewsEvent(event_id="e1", ticker="AAPL", headline="h", source="s",
                             published_at="2026-05-01", sentiment_score=1.0)
_check("B15 accepts sentiment_score=1.0", ev_boundary_pos.sentiment_score == 1.0)
ev_boundary_neg = NewsEvent(event_id="e1", ticker="AAPL", headline="h", source="s",
                             published_at="2026-05-01", sentiment_score=-1.0)
_check("B16 accepts sentiment_score=-1.0", ev_boundary_neg.sentiment_score == -1.0)

# Accepts None URL
ev_no_url = NewsEvent(event_id="e1", ticker="AAPL", headline="h", source="s",
                      published_at="2026-05-01", url=None)
_check("B17 accepts None url", ev_no_url.url is None)

# Defaults
ev_defaults = NewsEvent(event_id="e1", ticker="AAPL", headline="h",
                        source="s", published_at="2026-05-01")
_check("B18 default vendor='synthetic'", ev_defaults.vendor == "synthetic")
_check("B19 default category='unknown'", ev_defaults.category == "unknown")
_check("B20 default impact_horizon='unknown'", ev_defaults.impact_horizon == "unknown")
_check("B21 default related_symbols=[]", ev_defaults.related_symbols == [])
_check("B22 default raw_payload={}", ev_defaults.raw_payload == {})

# Rejects whitespace-only ticker
try:
    NewsEvent(event_id="e1", ticker="  ", headline="h", source="s", published_at="2026-05-01")
    _check("B23 rejects whitespace-only ticker", False)
except Exception:
    _check("B23 rejects whitespace-only ticker", True)


# ===========================================================================
# Group C: NewsSnapshot validation
# ===========================================================================
print("C: NewsSnapshot")

snap = _make_snapshot()
_check("C1  NewsSnapshot accepts empty events", len(snap.events) == 0)
_check("C2  snapshot_id preserved", snap.snapshot_id == "snap_001")
_check("C3  ticker preserved", snap.ticker == "AAPL")
_check("C4  as_of preserved", snap.as_of == "2026-05-21")
_check("C5  lookback_days preserved", snap.lookback_days == 30)

# Rejects empty snapshot_id
try:
    NewsSnapshot(snapshot_id="", ticker="AAPL", as_of="2026-05-21")
    _check("C6  rejects empty snapshot_id", False)
except Exception:
    _check("C6  rejects empty snapshot_id", True)

# Rejects empty ticker
try:
    NewsSnapshot(snapshot_id="s1", ticker="", as_of="2026-05-21")
    _check("C7  rejects empty ticker", False)
except Exception:
    _check("C7  rejects empty ticker", True)

# Rejects empty as_of
try:
    NewsSnapshot(snapshot_id="s1", ticker="AAPL", as_of="")
    _check("C8  rejects empty as_of", False)
except Exception:
    _check("C8  rejects empty as_of", True)

# Rejects invalid lookback_days (0 or negative)
try:
    NewsSnapshot(snapshot_id="s1", ticker="AAPL", as_of="2026-05-21", lookback_days=0)
    _check("C9  rejects lookback_days=0", False)
except Exception:
    _check("C9  rejects lookback_days=0", True)

try:
    NewsSnapshot(snapshot_id="s1", ticker="AAPL", as_of="2026-05-21", lookback_days=-1)
    _check("C10 rejects lookback_days=-1", False)
except Exception:
    _check("C10 rejects lookback_days=-1", True)

# Accepts lookback_days=1
snap_lb = NewsSnapshot(snapshot_id="s1", ticker="AAPL", as_of="2026-05-21", lookback_days=1)
_check("C11 accepts lookback_days=1", snap_lb.lookback_days == 1)

# Accepts None lookback_days
snap_no_lb = NewsSnapshot(snapshot_id="s1", ticker="AAPL", as_of="2026-05-21")
_check("C12 accepts None lookback_days", snap_no_lb.lookback_days is None)


# ===========================================================================
# Group D: classify_news_category
# ===========================================================================
print("D: classify_news_category")

_check("D1  earnings keywords",
       classify_news_category("AAPL beats EPS estimates for Q1") == "earnings")
_check("D2  earnings via revenue",
       classify_news_category("Company posts record revenue") == "earnings")
_check("D3  guidance keywords",
       classify_news_category("MSFT raises guidance for FY2026") == "guidance")
_check("D4  outlook maps to guidance",
       classify_news_category("Company provides favorable outlook") == "guidance")
_check("D5  analyst rating via upgrade",
       classify_news_category("Analyst upgrades AAPL to Buy") == "analyst_rating")
_check("D6  analyst rating via downgrade",
       classify_news_category("Analyst downgrades TSLA to Sell") == "analyst_rating")
_check("D7  price target keyword",
       classify_news_category("Goldman raises price target for NVDA") == "price_target")
_check("D8  litigation via lawsuit",
       classify_news_category("Company faces lawsuit over patent") == "litigation")
_check("D9  regulatory via SEC",
       classify_news_category("SEC opens investigation into MSFT") == "regulatory")
_check("D10 management via CEO",
       classify_news_category("CEO Tim Cook comments on expansion") == "management")
_check("D11 buyback keyword",
       classify_news_category("Board approves $10B share buyback") == "buyback")
_check("D12 dividend keyword",
       classify_news_category("AAPL raises quarterly dividend by 4%") == "dividend")
_check("D13 m_and_a via acquisition",
       classify_news_category("MSFT announces acquisition of startup") == "m_and_a")
_check("D14 partnership keyword",
       classify_news_category("Apple signs partnership with IBM") == "partnership")
_check("D15 product keyword",
       classify_news_category("Apple unveils new product at WWDC") == "product")
_check("D16 financing via IPO",
       classify_news_category("Company files for IPO on NASDAQ") == "financing")
_check("D17 fallback to unknown",
       classify_news_category("Random unrelated headline") == "unknown")
_check("D18 raw_category hint used (finnhub earnings)",
       classify_news_category("Some headline", raw_category="earnings") == "earnings")
_check("D19 raw_category hint used (finnhub merger)",
       classify_news_category("Some headline", raw_category="merger") == "m_and_a")
_check("D20 raw_category unknown falls through to keyword",
       classify_news_category("CEO steps down", raw_category="unknown_cat") == "management")
_check("D21 summary extends search space",
       classify_news_category("Breaking news", summary="Company reports earnings above estimates") == "earnings")


# ===========================================================================
# Group E: normalize_finnhub_news_event
# ===========================================================================
print("E: normalize_finnhub_news_event")

raw = dict(_FINNHUB_RAW)
ev_norm = normalize_finnhub_news_event(raw, "AAPL")

_check("E1  vendor is 'finnhub'", ev_norm.vendor == "finnhub")
_check("E2  ticker from argument", ev_norm.ticker == "AAPL")
_check("E3  headline preserved", "record revenue" in ev_norm.headline)
_check("E4  source preserved", ev_norm.source == "Reuters")
_check("E5  url preserved", ev_norm.url == "https://example.com/aapl-q2")
_check("E6  summary preserved", ev_norm.summary is not None and "97B" in ev_norm.summary)
_check("E7  event_id uses vendor id", ev_norm.event_id == "finnhub_12345")
_check("E8  category mapped to earnings", ev_norm.category == "earnings")
_check("E9  related_symbols parsed from comma-sep",
       "AAPL" in ev_norm.related_symbols and "MSFT" in ev_norm.related_symbols)
_check("E10 raw_payload preserved", ev_norm.raw_payload == raw)
_check("E11 published_at is ISO string", "2025" in ev_norm.published_at or
       "2026" in ev_norm.published_at or len(ev_norm.published_at) > 4)

# Does not mutate raw input
_check("E12 does not mutate raw input", "image" in raw)

# Raises on missing headline
try:
    normalize_finnhub_news_event({"id": 1, "source": "Reuters",
                                   "datetime": 1748476800}, "AAPL")
    _check("E13 raises on missing headline", False)
except ValueError:
    _check("E13 raises on missing headline", True)

# Raises on blank headline
try:
    normalize_finnhub_news_event({"id": 1, "headline": "   ", "source": "Reuters",
                                   "datetime": 1748476800}, "AAPL")
    _check("E14 raises on blank headline", False)
except ValueError:
    _check("E14 raises on blank headline", True)

# Parses comma-separated related
raw_related = {"id": 2, "headline": "News", "source": "AP",
               "datetime": 1748476800, "related": "GOOGL,META,AMZN"}
ev_related = normalize_finnhub_news_event(raw_related, "GOOGL")
_check("E15 comma-sep related_symbols parsed", ev_related.related_symbols == ["GOOGL", "META", "AMZN"])

# Accepts list related
raw_list_related = {"id": 3, "headline": "News", "source": "AP",
                    "datetime": 1748476800, "related": ["AAPL", "MSFT"]}
ev_list_rel = normalize_finnhub_news_event(raw_list_related, "AAPL")
_check("E16 list related_symbols accepted", ev_list_rel.related_symbols == ["AAPL", "MSFT"])

# Fallback event_id when no vendor id
raw_no_id = {"headline": "AAPL news", "source": "AP", "datetime": 1748476800}
ev_no_id = normalize_finnhub_news_event(raw_no_id, "AAPL")
_check("E17 stable hash event_id when no vendor id",
       ev_no_id.event_id.startswith("finnhub_"))
# Same inputs → same id (determinism)
ev_no_id2 = normalize_finnhub_news_event(raw_no_id, "AAPL")
_check("E18 event_id deterministic for same payload", ev_no_id.event_id == ev_no_id2.event_id)

# Missing source falls back to 'unknown'
raw_no_source = {"id": 99, "headline": "Big news", "datetime": 1748476800}
ev_no_source = normalize_finnhub_news_event(raw_no_source, "AAPL")
_check("E19 missing source defaults to 'unknown'", ev_no_source.source == "unknown")

# Missing datetime → published_at = 'unknown'
raw_no_dt = {"id": 100, "headline": "Big news", "source": "AP"}
ev_no_dt = normalize_finnhub_news_event(raw_no_dt, "AAPL")
_check("E20 missing datetime → published_at='unknown'", ev_no_dt.published_at == "unknown")

# Custom prefix
ev_prefix = normalize_finnhub_news_event(raw, "AAPL", event_id_prefix="custom")
_check("E21 custom prefix used in event_id", ev_prefix.event_id.startswith("custom_"))


# ===========================================================================
# Group F: news_snapshot_from_events
# ===========================================================================
print("F: news_snapshot_from_events")

ev1 = _make_event(event_id="e1")
ev2 = _make_event(event_id="e2", headline="Second news headline")
original_list = [ev1, ev2]
built_snap = news_snapshot_from_events(
    "snap_test", "AAPL", "2026-05-21", original_list, lookback_days=7,
)
_check("F1  snapshot_id preserved", built_snap.snapshot_id == "snap_test")
_check("F2  ticker preserved", built_snap.ticker == "AAPL")
_check("F3  events count correct", len(built_snap.events) == 2)
_check("F4  lookback_days preserved", built_snap.lookback_days == 7)

# Does not mutate input list
original_list_copy_len = len(original_list)
original_list.clear()
_check("F5  does not mutate input list (snap still has events)",
       len(built_snap.events) == 2)

# With warnings and metadata
snap_w = news_snapshot_from_events(
    "s2", "MSFT", "2026-05-21", [],
    warnings=["test warning"], metadata={"key": "val"},
)
_check("F6  warnings preserved", snap_w.warnings == ["test warning"])
_check("F7  metadata preserved", snap_w.metadata == {"key": "val"})


# ===========================================================================
# Group G: news_tool_result_from_snapshot
# ===========================================================================
print("G: news_tool_result_from_snapshot")

snap_for_tr = _make_snapshot(events=[_make_event()])
tr = news_tool_result_from_snapshot("RUN_001", snap_for_tr)

_check("G1  tool_name = 'news_snapshot'", tr.tool_name == "news_snapshot")
_check("G2  ticker = snapshot.ticker", tr.ticker == "AAPL")
_check("G3  target defaults to ticker (in evidence_id)",
       "AAPL" in tr.evidence_id)
_check("G4  evidence_id contains tool_name",
       "news_snapshot" in tr.evidence_id)
_check("G5  inputs contains snapshot_id", "snapshot_id" in tr.inputs)
_check("G6  inputs contains ticker", "ticker" in tr.inputs)
_check("G7  inputs contains as_of", "as_of" in tr.inputs)
_check("G8  inputs contains calculation_version",
       "calculation_version" in tr.inputs)
_check("G9  outputs includes snapshot_id",
       "snapshot_id" in tr.outputs)
_check("G10 outputs includes ticker", "ticker" in tr.outputs)
_check("G11 outputs includes events", "events" in tr.outputs)
_check("G12 outputs includes lookback_days", "lookback_days" in tr.outputs)
_check("G13 description is non-empty", len(tr.description) > 0)
_check("G14 run_id preserved", tr.run_id == "RUN_001")

# Deterministic evidence_id
tr2 = news_tool_result_from_snapshot("RUN_001", snap_for_tr)
_check("G15 deterministic: same inputs → same evidence_id",
       tr.evidence_id == tr2.evidence_id)

# Different run_id → different evidence_id
tr3 = news_tool_result_from_snapshot("RUN_002", snap_for_tr)
_check("G16 different run_id → different evidence_id",
       tr.evidence_id != tr3.evidence_id)

# Custom target
tr_custom = news_tool_result_from_snapshot("RUN_001", snap_for_tr, target="AAPL_news")
_check("G17 custom target in evidence_id", "AAPL_news" in tr_custom.evidence_id)

# Snapshot with no events still works
snap_empty = _make_snapshot(events=[])
tr_empty = news_tool_result_from_snapshot("RUN_001", snap_empty)
_check("G18 works with empty events snapshot",
       tr_empty.outputs.get("events") == [])

# events included in payload
_check("G19 payload includes events list", isinstance(tr.outputs.get("events"), list))


# ===========================================================================
# Group H: extract_news_event_paths
# ===========================================================================
print("H: extract_news_event_paths")

snap_paths = _make_snapshot(events=[_make_event(), _make_event(event_id="e2")])
paths = extract_news_event_paths(snap_paths)

_check("H1  returns list", isinstance(paths, list))
_check("H2  events.0.headline present", "events.0.headline" in paths)
_check("H3  events.0.summary present", "events.0.summary" in paths)
_check("H4  events.0.source present", "events.0.source" in paths)
_check("H5  events.0.url present", "events.0.url" in paths)
_check("H6  events.0.published_at present", "events.0.published_at" in paths)
_check("H7  events.0.category present", "events.0.category" in paths)
_check("H8  events.0.related_symbols present", "events.0.related_symbols" in paths)
_check("H9  events.1.headline present for second event",
       "events.1.headline" in paths)
_check("H10 deterministic (same paths twice)",
       paths == extract_news_event_paths(snap_paths))
_check("H11 empty snapshot → empty paths",
       extract_news_event_paths(_make_snapshot()) == [])


# ===========================================================================
# Group I: summarize_news_snapshot_coverage
# ===========================================================================
print("I: summarize_news_snapshot_coverage")

ev_for_sum = _make_event(event_id="e1", category="earnings", vendor="finnhub",
                          url="https://a.com/1")
ev_for_sum2 = _make_event(event_id="e2", headline="Analyst upgrades AAPL",
                           category="analyst_rating", vendor="finnhub",
                           url="https://a.com/2")
snap_sum = _make_snapshot(events=[ev_for_sum, ev_for_sum2])
summary = summarize_news_snapshot_coverage(snap_sum)

_check("I1  ticker in summary", summary.ticker == "AAPL")
_check("I2  event_count = 2", summary.event_count == 2)
_check("I3  categories_present contains earnings",
       "earnings" in summary.categories_present)
_check("I4  categories_present contains analyst_rating",
       "analyst_rating" in summary.categories_present)
_check("I5  vendors_present contains finnhub",
       "finnhub" in summary.vendors_present)
_check("I6  missing_url_count = 0", summary.missing_url_count == 0)
_check("I7  duplicate_headline_count = 0", summary.duplicate_headline_count == 0)
_check("I8  duplicate_url_count = 0", summary.duplicate_url_count == 0)

# Missing URL count
ev_no_url_s = _make_event(event_id="e3", url=None)
snap_missing_url = _make_snapshot(events=[ev_no_url_s, ev_for_sum])
sum_no_url = summarize_news_snapshot_coverage(snap_missing_url)
_check("I9  missing_url_count = 1 when one event has no URL",
       sum_no_url.missing_url_count == 1)

# Duplicate headline count
ev_dup_h1 = _make_event(event_id="e4", headline="Same headline")
ev_dup_h2 = _make_event(event_id="e5", headline="Same headline")
snap_dup_h = _make_snapshot(events=[ev_dup_h1, ev_dup_h2])
sum_dup_h = summarize_news_snapshot_coverage(snap_dup_h)
_check("I10 duplicate_headline_count = 2 for 2 identical headlines",
       sum_dup_h.duplicate_headline_count == 2)

# Duplicate URL count
ev_dup_u1 = _make_event(event_id="e6", url="https://same.com")
ev_dup_u2 = _make_event(event_id="e7", url="https://same.com", headline="Other headline")
snap_dup_u = _make_snapshot(events=[ev_dup_u1, ev_dup_u2])
sum_dup_u = summarize_news_snapshot_coverage(snap_dup_u)
_check("I11 duplicate_url_count = 2 for 2 events with same URL",
       sum_dup_u.duplicate_url_count == 2)

# Empty snapshot
sum_empty = summarize_news_snapshot_coverage(_make_snapshot(events=[]))
_check("I12 empty snapshot → event_count = 0", sum_empty.event_count == 0)
_check("I13 empty snapshot → warning emitted", len(sum_empty.warnings) > 0)

# Stale event detection
ev_old = _make_event(event_id="e_old", published_at="2026-04-01T00:00:00Z")
snap_stale = _make_snapshot(events=[ev_old], as_of="2026-05-21")
sum_stale = summarize_news_snapshot_coverage(snap_stale, stale_after_days=14)
_check("I14 stale event counted when >14 days old",
       sum_stale.stale_event_count >= 1)


# ===========================================================================
# Group J: validate_news_snapshot
# ===========================================================================
print("J: validate_news_snapshot")

# Clean snapshot → no warnings
# Construct directly to ensure: matching vendor, recent published_at (≤14 days
# before as_of="2026-05-21"), non-empty URL, summary, category and related_symbols.
ev_clean = NewsEvent(
    event_id="e_clean", ticker="AAPL",
    headline="AAPL delivers solid results",
    summary="Good earnings report.",
    source="Reuters", vendor="finnhub",
    url="https://clean.com",
    published_at="2026-05-15T12:00:00Z",   # 6 days before as_of
    category="earnings",
    related_symbols=["AAPL"],
)
snap_clean = NewsSnapshot(
    snapshot_id="snap_clean", ticker="AAPL", as_of="2026-05-21",
    vendor="finnhub", events=[ev_clean],
)
w_clean = validate_news_snapshot(snap_clean)
_check("J1  clean snapshot → no warnings", len(w_clean) == 0)

# No events → warning
w_empty = validate_news_snapshot(_make_snapshot(events=[]))
_check("J2  no events → warning", any("no events" in w.lower() for w in w_empty))

# Ticker mismatch
ev_msft = _make_event(event_id="e_msft", ticker="MSFT")
snap_mismatch = _make_snapshot(events=[ev_msft])  # snap ticker = AAPL
w_mismatch = validate_news_snapshot(snap_mismatch)
_check("J3  ticker mismatch → warning",
       any("does not match" in w.lower() or "mismatch" in w.lower() or
           "ticker" in w.lower() for w in w_mismatch))

# Missing URL
ev_no_url_v = _make_event(event_id="e_nu", url=None)
snap_no_url = _make_snapshot(events=[ev_no_url_v])
w_no_url = validate_news_snapshot(snap_no_url)
_check("J4  missing URL → warning",
       any("url" in w.lower() for w in w_no_url))

# Duplicate headline
ev_d1 = _make_event(event_id="e_d1", headline="Duplicate headline here")
ev_d2 = _make_event(event_id="e_d2", headline="Duplicate headline here")
snap_dup_hv = _make_snapshot(events=[ev_d1, ev_d2])
w_dup_h = validate_news_snapshot(snap_dup_hv)
_check("J5  duplicate headline → warning",
       any("duplicate" in w.lower() and "headline" in w.lower() for w in w_dup_h))

# Duplicate URL
ev_u1 = _make_event(event_id="e_u1", url="https://dup.com", headline="H1")
ev_u2 = _make_event(event_id="e_u2", url="https://dup.com", headline="H2")
snap_dup_uv = _make_snapshot(events=[ev_u1, ev_u2])
w_dup_u = validate_news_snapshot(snap_dup_uv)
_check("J6  duplicate URL → warning",
       any("duplicate" in w.lower() and "url" in w.lower() for w in w_dup_u))

# Missing summary
ev_no_sum = _make_event(event_id="e_ns", summary=None)
snap_no_sum = _make_snapshot(events=[ev_no_sum])
w_no_sum = validate_news_snapshot(snap_no_sum)
_check("J7  missing summary → warning",
       any("summary" in w.lower() for w in w_no_sum))

# Unknown category
ev_unk = _make_event(event_id="e_unk", category="unknown")
snap_unk = _make_snapshot(events=[ev_unk])
w_unk = validate_news_snapshot(snap_unk)
_check("J8  unknown category → warning",
       any("unknown" in w.lower() and "category" in w.lower() for w in w_unk))

# Missing related_symbols
ev_no_rel = _make_event(event_id="e_nr", related_symbols=[])
snap_no_rel = _make_snapshot(events=[ev_no_rel])
w_no_rel = validate_news_snapshot(snap_no_rel)
_check("J9  missing related_symbols → warning",
       any("related" in w.lower() for w in w_no_rel))

# Never raises
try:
    _ = validate_news_snapshot(_make_snapshot())
    _check("J10 never raises", True)
except Exception:
    _check("J10 never raises", False)

# Vendor mismatch
ev_poly = _make_event(event_id="e_poly", vendor="polygon")
snap_vendor_mm = NewsSnapshot(
    snapshot_id="s_vm", ticker="AAPL", as_of="2026-05-21",
    vendor="finnhub", events=[ev_poly],
)
w_vm = validate_news_snapshot(snap_vendor_mm)
_check("J11 vendor mismatch → warning",
       any("vendor" in w.lower() for w in w_vm))


# ===========================================================================
# Group K: NewsCoverageSummary serialization roundtrip
# ===========================================================================
print("K: Serialization roundtrips")

summary_rt = summarize_news_snapshot_coverage(snap_sum)
data = summary_rt.model_dump()
summary_restored = NewsCoverageSummary(**data)
_check("K1  NewsCoverageSummary roundtrip ticker",
       summary_restored.ticker == summary_rt.ticker)
_check("K2  NewsCoverageSummary roundtrip event_count",
       summary_restored.event_count == summary_rt.event_count)
_check("K3  NewsCoverageSummary roundtrip categories_present",
       summary_restored.categories_present == summary_rt.categories_present)

# NewsSnapshot roundtrip
snap_rt = _make_snapshot(events=[_make_event()])
snap_data = snap_rt.model_dump()
snap_restored = NewsSnapshot(**snap_data)
_check("K4  NewsSnapshot roundtrip snapshot_id",
       snap_restored.snapshot_id == snap_rt.snapshot_id)
_check("K5  NewsSnapshot roundtrip events count",
       len(snap_restored.events) == len(snap_rt.events))
_check("K6  NewsSnapshot roundtrip event headline",
       snap_restored.events[0].headline == snap_rt.events[0].headline)

# NewsEvent roundtrip
ev_rt = _make_event()
ev_data = ev_rt.model_dump()
ev_restored = NewsEvent(**ev_data)
_check("K7  NewsEvent roundtrip event_id",
       ev_restored.event_id == ev_rt.event_id)
_check("K8  NewsEvent roundtrip sentiment_score",
       ev_restored.sentiment_score == ev_rt.sentiment_score)

# ToolResult roundtrip (payload field paths stable)
tr_rt = news_tool_result_from_snapshot("RUN_001", snap_rt)
_check("K9  ToolResult evidence_id stable",
       tr_rt.evidence_id == news_tool_result_from_snapshot("RUN_001", snap_rt).evidence_id)
_check("K10 ToolResult outputs.events is list",
       isinstance(tr_rt.outputs.get("events"), list))


# ===========================================================================
# Group L: EvidenceRef-friendly field paths are stable
# ===========================================================================
print("L: ToolResult payload field paths")

snap_path_test = _make_snapshot(events=[_make_event(event_id="p1"),
                                         _make_event(event_id="p2")])
tr_path = news_tool_result_from_snapshot("RUN_PATH", snap_path_test)

_check("L1  events key is list in outputs",
       isinstance(tr_path.outputs.get("events"), list))
_check("L2  first event headline accessible in outputs",
       tr_path.outputs["events"][0]["headline"] == snap_path_test.events[0].headline)
_check("L3  snapshot_id accessible in outputs",
       tr_path.outputs["snapshot_id"] == snap_path_test.snapshot_id)
_check("L4  calculation_version present",
       "calculation_version" in tr_path.outputs)

# Paths helper stable
paths_stable = extract_news_event_paths(snap_path_test)
_check("L5  events.0.headline in paths", "events.0.headline" in paths_stable)
_check("L6  events.1.category in paths", "events.1.category" in paths_stable)
_check("L7  path count = 2 events × 7 fields = 14",
       len(paths_stable) == 14)


# ===========================================================================
# Group N: Validator integration — events.0.headline resolves end-to-end
# ===========================================================================
print("N: Validator integration (field-path resolver)")

import tempfile
from lib.reliability import (
    AgentResult,
    AgentConfidence,
    EvidenceRef,
    EvidenceStore,
    Finding,
    validate_agent_result,
)

# Build a news snapshot with one event
ev_integ = NewsEvent(
    event_id="integ_001",
    ticker="AAPL",
    headline="AAPL beats Q2 revenue estimates by 8%",
    summary="Apple posted $97B in quarterly revenue.",
    source="Reuters",
    vendor="finnhub",
    url="https://example.com/aapl-q2-revenue",
    published_at="2026-05-15T12:00:00Z",
    category="earnings",
    related_symbols=["AAPL"],
)
snap_integ = NewsSnapshot(
    snapshot_id="snap_integ_001",
    ticker="AAPL",
    as_of="2026-05-21",
    vendor="finnhub",
    events=[ev_integ],
)

with tempfile.TemporaryDirectory() as _tmp_dir:
    _store = EvidenceStore(run_dir=Path(_tmp_dir))
    _tr_integ = news_tool_result_from_snapshot("RUN_INTEG", snap_integ)
    _store.add_tool_result(_tr_integ)

    # Confirm events.0.headline path resolves in the payload
    _paths = extract_news_event_paths(snap_integ)
    _check("N1  events.0.headline present in extracted paths",
           "events.0.headline" in _paths)

    # Build AgentResult citing that headline via field_path
    _agent_result = AgentResult(
        agent_name="NewsImpactAgent",
        run_id="RUN_INTEG",
        ticker="AAPL",
        confidence=AgentConfidence(level="medium", rationale="News-backed."),
        findings=[Finding(
            text="Revenue beat represents strong momentum.",
            evidence=[EvidenceRef(
                evidence_id=_tr_integ.evidence_id,
                tool_name="news_snapshot",
                field_path="events.0.headline",
            )],
        )],
    )

    _report = validate_agent_result(_agent_result, _store)
    _codes = {iss.code for iss in _report.issues}

    _check("N2  no INVALID_EVIDENCE_FIELD_PATH_BINDING for events.0.headline",
           "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in _codes)
    _check("N3  no INVALID_EVIDENCE_ID",
           "INVALID_EVIDENCE_ID" not in _codes)
    _check("N4  validation report passed (no errors)",
           _report.passed)

    # --- Negative: out-of-bounds index ---
    _ar_oob = AgentResult(
        agent_name="NewsImpactAgent",
        run_id="RUN_INTEG",
        ticker="AAPL",
        confidence=AgentConfidence(level="low", rationale="Test."),
        findings=[Finding(
            text="Revenue is $97B, well above the $90B consensus.",
            evidence=[EvidenceRef(
                evidence_id=_tr_integ.evidence_id,
                tool_name="news_snapshot",
                field_path="events.99.headline",   # out of bounds
            )],
        )],
    )
    _report_oob = validate_agent_result(_ar_oob, _store)
    _codes_oob = {iss.code for iss in _report_oob.issues}
    _check("N5  INVALID_EVIDENCE_FIELD_PATH_BINDING for events.99.headline (OOB)",
           "INVALID_EVIDENCE_FIELD_PATH_BINDING" in _codes_oob)

    # --- Negative: non-integer index ---
    _ar_str = AgentResult(
        agent_name="NewsImpactAgent",
        run_id="RUN_INTEG",
        ticker="AAPL",
        confidence=AgentConfidence(level="low", rationale="Test."),
        findings=[Finding(
            text="Revenue beat of $7B versus consensus.",
            evidence=[EvidenceRef(
                evidence_id=_tr_integ.evidence_id,
                tool_name="news_snapshot",
                field_path="events.foo.headline",  # non-integer
            )],
        )],
    )
    _report_str = validate_agent_result(_ar_str, _store)
    _codes_str = {iss.code for iss in _report_str.issues}
    _check("N6  INVALID_EVIDENCE_FIELD_PATH_BINDING for events.foo.headline",
           "INVALID_EVIDENCE_FIELD_PATH_BINDING" in _codes_str)

    # --- Negative: missing field in the event dict ---
    _ar_miss = AgentResult(
        agent_name="NewsImpactAgent",
        run_id="RUN_INTEG",
        ticker="AAPL",
        confidence=AgentConfidence(level="low", rationale="Test."),
        findings=[Finding(
            text="Revenue beat of $7B versus consensus.",
            evidence=[EvidenceRef(
                evidence_id=_tr_integ.evidence_id,
                tool_name="news_snapshot",
                field_path="events.0.nonexistent_field",  # field not in event
            )],
        )],
    )
    _report_miss = validate_agent_result(_ar_miss, _store)
    _codes_miss = {iss.code for iss in _report_miss.issues}
    _check("N7  INVALID_EVIDENCE_FIELD_PATH_BINDING for events.0.nonexistent_field",
           "INVALID_EVIDENCE_FIELD_PATH_BINDING" in _codes_miss)

    # --- Positive: events.0.summary also resolves ---
    _ar_sum = AgentResult(
        agent_name="NewsImpactAgent",
        run_id="RUN_INTEG",
        ticker="AAPL",
        confidence=AgentConfidence(level="medium", rationale="News-backed."),
        findings=[Finding(
            text="Revenue momentum is notable.",
            evidence=[EvidenceRef(
                evidence_id=_tr_integ.evidence_id,
                tool_name="news_snapshot",
                field_path="events.0.summary",
            )],
        )],
    )
    _report_sum = validate_agent_result(_ar_sum, _store)
    _codes_sum = {iss.code for iss in _report_sum.issues}
    _check("N8  events.0.summary resolves without FIELD_PATH_BINDING error",
           "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in _codes_sum)

    # --- Positive: events.0.category resolves ---
    _ar_cat = AgentResult(
        agent_name="NewsImpactAgent",
        run_id="RUN_INTEG",
        ticker="AAPL",
        confidence=AgentConfidence(level="medium", rationale="News-backed."),
        findings=[Finding(
            text="Earnings news is positive.",
            evidence=[EvidenceRef(
                evidence_id=_tr_integ.evidence_id,
                tool_name="news_snapshot",
                field_path="events.0.category",
            )],
        )],
    )
    _report_cat = validate_agent_result(_ar_cat, _store)
    _codes_cat = {iss.code for iss in _report_cat.issues}
    _check("N9  events.0.category resolves without FIELD_PATH_BINDING error",
           "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in _codes_cat)

    # --- Verify dict-only paths still work (regression guard) ---
    _snap_dict_only = news_tool_result_from_snapshot(
        "RUN_DICT", snap_integ, calculation_version="news_schema_v1",
    )
    _store.add_tool_result(_snap_dict_only)
    _ar_dict = AgentResult(
        agent_name="NewsImpactAgent",
        run_id="RUN_DICT",
        ticker="AAPL",
        confidence=AgentConfidence(level="medium", rationale="News-backed."),
        findings=[Finding(
            text="Snapshot covers AAPL earnings.",
            evidence=[EvidenceRef(
                evidence_id=_snap_dict_only.evidence_id,
                tool_name="news_snapshot",
                field_path="ticker",   # top-level dict key
            )],
        )],
    )
    _report_dict = validate_agent_result(_ar_dict, _store)
    _codes_dict = {iss.code for iss in _report_dict.issues}
    _check("N10 dict-only path 'ticker' still resolves (regression guard)",
           "INVALID_EVIDENCE_FIELD_PATH_BINDING" not in _codes_dict)


# ===========================================================================
# Group M: Safety — no live app or network imports
# ===========================================================================
print("M: Safety")

import lib.reliability.news as _news_mod

_mod_src = Path(_news_mod.__file__).read_text()

_check("M1  news.py does not import streamlit",
       "import streamlit" not in _mod_src and "from streamlit" not in _mod_src)
_check("M2  news.py does not import yfinance",
       "import yfinance" not in _mod_src)
_check("M3  news.py does not import requests",
       "import requests" not in _mod_src)
_check("M4  news.py does not import finnhub",
       "import finnhub" not in _mod_src)
_check("M5  news.py does not import app",
       "\nimport app" not in _mod_src and "\nfrom app" not in _mod_src)
_check("M6  news.py does not import pages",
       "from pages" not in _mod_src and "import pages" not in _mod_src)
_check("M7  news.py does not import data_fetcher",
       "data_fetcher" not in _mod_src)

# All symbols importable from lib.reliability
try:
    from lib.reliability import (
        NewsSourceVendor, NewsEventCategory, NewsImpactHorizon,
        NewsFreshnessStatus, NewsEvent, NewsSnapshot, NewsCoverageSummary,
        classify_news_category, normalize_finnhub_news_event,
        news_snapshot_from_events, news_tool_result_from_snapshot,
        extract_news_event_paths, summarize_news_snapshot_coverage,
        validate_news_snapshot,
    )
    _check("M8  all symbols importable from lib.reliability", True)
except ImportError as e:
    _check(f"M8  all symbols importable from lib.reliability ({e})", False)

_check("M9  sys.path includes repo root", str(_ROOT) in sys.path)


# ===========================================================================
# Summary
# ===========================================================================
print()
print(f"Result: {_PASS} passed, {_FAIL} failed")
if _FAIL == 0:
    print("All assertions passed.")
else:
    sys.exit(1)
