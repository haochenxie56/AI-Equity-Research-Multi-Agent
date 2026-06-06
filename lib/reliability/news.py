"""
lib/reliability/news.py

Standalone schema models, helper functions, and ToolResult wrappers for
stock/company news data.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no file I/O.
  - Reuses EvidenceRef and ToolResult from lib.reliability.schemas.
  - Reuses make_evidence_id and stable_hash_payload from lib.reliability.adapters.
  - Normalises Finnhub-like news payloads into stable, vendor-agnostic schemas.
  - All functions are deterministic and pure — they do not fetch real data.
  - No News Agent is implemented in this phase.
  - No news UI/cockpit is implemented in this phase.
  - Live data connectors and existing Finnhub fetch behaviour are unmodified.
  - UI dashboard belongs to the Investment Cockpit phase.

See docs/reliability_phase_2f_news_toolresult_wrapper.md for full design
rationale and rollout context.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import EvidenceRef, ToolResult


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

NewsSourceVendor = Literal[
    "finnhub",
    "polygon",
    "alpha_vantage",
    "manual",
    "synthetic",
    "other",
]

NewsEventCategory = Literal[
    "earnings",
    "guidance",
    "analyst_rating",
    "price_target",
    "product",
    "partnership",
    "m_and_a",
    "regulatory",
    "macro",
    "litigation",
    "management",
    "financing",
    "dividend",
    "buyback",
    "sector",
    "sentiment",
    "other",
    "unknown",
]

NewsImpactHorizon = Literal[
    "short_term",
    "medium_term",
    "long_term",
    "unknown",
]

NewsFreshnessStatus = Literal[
    "fresh",
    "stale",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_NEWS_TOOL_NAME: str = "news_snapshot"
_NEWS_METRIC_GROUP: str = "news_snapshot"

# Finnhub raw category → NewsEventCategory mapping
_FINNHUB_CATEGORY_MAP: dict[str, NewsEventCategory] = {
    "earnings": "earnings",
    "merger": "m_and_a",
    "mergers": "m_and_a",
    "m&a": "m_and_a",
    "analyst": "analyst_rating",
    "rating": "analyst_rating",
    "upgrade": "analyst_rating",
    "downgrade": "analyst_rating",
    "price target": "price_target",
    "dividend": "dividend",
    "buyback": "buyback",
    "repurchase": "buyback",
    "regulatory": "regulatory",
    "fda": "regulatory",
    "sec": "regulatory",
    "lawsuit": "litigation",
    "litigation": "litigation",
    "ipo": "financing",
    "financing": "financing",
    "partnership": "partnership",
    "collaboration": "partnership",
    "product": "product",
    "launch": "product",
    "management": "management",
    "ceo": "management",
    "cfo": "management",
    "macro": "macro",
    "general": "other",
    "company news": "other",
    "technology": "sector",
    "sector": "sector",
    "sentiment": "sentiment",
    "guidance": "guidance",
    "outlook": "guidance",
}


# ---------------------------------------------------------------------------
# 1. NewsEvent
# ---------------------------------------------------------------------------

class NewsEvent(BaseModel):
    """
    One sourced news event for a stock/company.

    Fields:
        event_id:        Non-empty unique identifier for this event.
        ticker:          Non-empty underlying ticker symbol.
        headline:        Non-empty headline text.
        summary:         Optional extended body / summary.
        source:          Non-empty source/publisher name (e.g. ``"Reuters"``).
        vendor:          News data vendor; defaults to ``"synthetic"``.
        url:             Optional article URL.
        published_at:    Non-empty publication timestamp string.
        category:        Event category; defaults to ``"unknown"``.
        related_symbols: List of related ticker symbols; may be empty.
        sentiment_score: Optional numeric sentiment in [-1.0, 1.0].
        impact_horizon:  Expected impact duration; defaults to ``"unknown"``.
        raw_payload:     Original vendor payload preserved without mutation.
        metadata:        Arbitrary key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    summary: Optional[str] = None
    source: str = Field(min_length=1)
    vendor: NewsSourceVendor = "synthetic"
    url: Optional[str] = None
    published_at: str = Field(min_length=1)
    category: NewsEventCategory = "unknown"
    related_symbols: list[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    impact_horizon: NewsImpactHorizon = "unknown"
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "NewsEvent":
        for field_name in ("event_id", "ticker", "headline", "source", "published_at"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 2. NewsSnapshot
# ---------------------------------------------------------------------------

class NewsSnapshot(BaseModel):
    """
    Container for a set of news events for one ticker over a lookback window.

    Fields:
        snapshot_id:    Non-empty unique identifier for this snapshot.
        ticker:         Non-empty underlying ticker symbol.
        schema_version: Version of this snapshot schema contract.
        as_of:          Non-empty snapshot date/datetime string.
        vendor:         Primary news data vendor.
        events:         List of ``NewsEvent`` instances (may be partial/empty).
        lookback_days:  Optional lookback window in days; if provided, must be > 0.
        warnings:       Advisory warnings about coverage or data quality.
        metadata:       Arbitrary key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    vendor: NewsSourceVendor = "synthetic"
    events: list[NewsEvent] = Field(default_factory=list)
    lookback_days: Optional[int] = Field(default=None, gt=0)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "NewsSnapshot":
        for field_name in ("snapshot_id", "ticker", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 3. NewsCoverageSummary
# ---------------------------------------------------------------------------

class NewsCoverageSummary(BaseModel):
    """
    Concise coverage summary for a ``NewsSnapshot``.

    Fields:
        ticker:                  Non-empty ticker symbol.
        event_count:             Total events in the snapshot (>= 0).
        categories_present:      Unique ``NewsEventCategory`` values seen.
        vendors_present:         Unique ``NewsSourceVendor`` values seen.
        missing_url_count:       Events with no URL (>= 0).
        duplicate_headline_count: Events with the same headline as another (>= 0).
        duplicate_url_count:     Events sharing a URL with another (>= 0).
        stale_event_count:       Events older than stale_after_days threshold (>= 0).
        warnings:                Advisory warnings from the summariser.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    event_count: int = Field(ge=0)
    categories_present: list[NewsEventCategory] = Field(default_factory=list)
    vendors_present: list[NewsSourceVendor] = Field(default_factory=list)
    missing_url_count: int = Field(default=0, ge=0)
    duplicate_headline_count: int = Field(default=0, ge=0)
    duplicate_url_count: int = Field(default=0, ge=0)
    stale_event_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper 1: classify_news_category
# ---------------------------------------------------------------------------

# Keyword → category, checked in order (first match wins)
_CATEGORY_KEYWORDS: list[tuple[NewsEventCategory, list[str]]] = [
    ("earnings",       ["earnings", " eps", "revenue", "profit", "quarterly results",
                        "annual results", "beat estimates", "missed estimates"]),
    ("guidance",       ["guidance", "outlook", "forecast", "raised guidance",
                        "lowered guidance", "full-year", "next quarter"]),
    ("price_target",   ["price target", "pt raised", "pt lowered", "target raised",
                        "target lowered", "target price"]),
    ("analyst_rating", ["upgrade", "downgrade", "outperform", "underperform",
                        "neutral", "buy rating", "sell rating", "hold rating",
                        "analyst", "rating"]),
    ("regulatory",     ["fda", "sec", "regulatory", "approval", "approved",
                        "rejected", "investigation", "probe", "compliance",
                        "antitrust"]),
    ("litigation",     ["lawsuit", "litigation", "sued", "settlement", "class action",
                        "legal action", "court", "verdict"]),
    ("management",     ["ceo", "cfo", "coo", "chief executive", "chief financial",
                        "management", "executive", "board of directors", "resign",
                        "appointed", "director"]),
    ("buyback",        ["buyback", "repurchase", "share repurchase", "stock repurchase"]),
    ("dividend",       ["dividend", "payout", "distribution", "yield"]),
    ("m_and_a",        ["acquisition", "merger", "acquires", "takeover", "buyout",
                        "acquired by", "deal", "combines with", "combines with"]),
    ("partnership",    ["partnership", "collaboration", "joint venture", "agreement",
                        "strategic alliance", "ally", "cooperat"]),
    ("product",        ["product", "launch", "release", "unveiled", "introduces",
                        "new model", "innovation", "rollout"]),
    ("financing",      ["ipo", "offering", "shares issued", "secondary", "debt",
                        "bond", "credit facility", "fundrais", "capital raise"]),
    ("macro",          ["federal reserve", "fed", "interest rate", "inflation",
                        "gdp", "unemployment", "economic", "macro"]),
    ("sentiment",      ["sentiment", "investor mood", "bullish", "bearish",
                        "market sentiment"]),
    ("sector",         ["sector", "industry", "technology", "healthcare", "energy",
                        "financials", "utilities", "materials"]),
]


def classify_news_category(
    headline: str,
    summary: Optional[str] = None,
    raw_category: Optional[str] = None,
) -> NewsEventCategory:
    """
    Classify a news event into a ``NewsEventCategory`` using keyword matching.

    This is a deterministic, LLM-free heuristic.  It is not exhaustive —
    unmatched events fall back to ``"unknown"``.

    Priority:
    1. Check ``raw_category`` first against ``_FINNHUB_CATEGORY_MAP`` (case-insensitive).
    2. Search ``headline`` (and optionally ``summary``) for category keywords
       (case-insensitive, first match wins).
    3. Fall back to ``"unknown"``.

    Args:
        headline:     Non-empty headline string.
        summary:      Optional summary/body to supplement keyword search.
        raw_category: Optional raw vendor category string (e.g. Finnhub category).

    Returns:
        A ``NewsEventCategory`` literal value.

    Examples::

        classify_news_category("AAPL beats EPS estimates")    # → "earnings"
        classify_news_category("CEO resigns from MSFT")       # → "management"
        classify_news_category("random news")                  # → "unknown"
    """
    # 1. Try raw_category map first
    if raw_category:
        mapped = _FINNHUB_CATEGORY_MAP.get(raw_category.lower().strip())
        if mapped is not None:
            return mapped

    # 2. Keyword search in combined text
    text = headline.lower()
    if summary:
        text = text + " " + summary.lower()

    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return category

    return "unknown"


# ---------------------------------------------------------------------------
# Helper 2: normalize_finnhub_news_event
# ---------------------------------------------------------------------------

def normalize_finnhub_news_event(
    raw: dict[str, Any],
    ticker: str,
    event_id_prefix: str = "finnhub",
) -> NewsEvent:
    """
    Normalize a Finnhub-like raw news payload into a ``NewsEvent``.

    Expected Finnhub-like keys (all optional except ``headline``):
        - ``id``        — vendor integer/string ID
        - ``datetime``  — Unix timestamp (int) or ISO date string
        - ``headline``  — Article headline (required; raises on missing/blank)
        - ``summary``   — Article body
        - ``source``    — Publisher name
        - ``url``       — Article URL
        - ``category``  — Finnhub category string
        - ``related``   — Comma-separated related tickers or list
        - ``image``     — Thumbnail URL (preserved in raw_payload only)

    Behavior:
        - Does **not** fetch data.
        - Does **not** mutate ``raw``.
        - ``event_id`` is deterministic: derived from vendor ``id`` when present;
          otherwise a stable hash of ``ticker``, ``headline``, ``url``, and
          ``datetime`` from the raw payload.
        - ``ticker`` always comes from the function argument.
        - ``vendor`` is always ``"finnhub"``.
        - ``published_at`` uses ``datetime`` field from raw if present.
          Unix timestamps are converted to ISO-8601 UTC strings.
          If absent, defaults to ``"unknown"``.
        - ``category`` is mapped via ``classify_news_category`` with the
          Finnhub raw category as a hint.
        - ``related_symbols`` parses comma-separated strings or accepts lists.
        - ``raw_payload`` stores a shallow copy of ``raw`` for full provenance.

    Args:
        raw:              Finnhub-like dict payload.
        ticker:           Underlying ticker symbol (non-empty).
        event_id_prefix:  Prefix for the generated event_id; defaults to
                          ``"finnhub"``.

    Returns:
        A normalised ``NewsEvent``.

    Raises:
        ValueError: If ``headline`` is missing or blank in ``raw``.

    Examples::

        ev = normalize_finnhub_news_event(
            {"id": 123, "headline": "AAPL beats Q1 EPS", "source": "Reuters",
             "datetime": 1748476800, "category": "earnings"},
            ticker="AAPL",
        )
        assert ev.vendor == "finnhub"
        assert ev.category == "earnings"
    """
    # Do not mutate caller's dict
    raw_copy = dict(raw)

    # --- headline (required) ---
    headline = raw_copy.get("headline", "")
    if not isinstance(headline, str) or not headline.strip():
        raise ValueError(
            f"normalize_finnhub_news_event: 'headline' is required and must be "
            f"non-blank; got {headline!r}."
        )
    headline = headline.strip()

    # --- event_id ---
    vendor_id = raw_copy.get("id")
    if vendor_id is not None:
        event_id = f"{event_id_prefix}_{vendor_id}"
    else:
        # Stable hash from key fields
        hash_payload = {
            "ticker": ticker,
            "headline": headline,
            "url": raw_copy.get("url", ""),
            "datetime": str(raw_copy.get("datetime", "")),
        }
        hash_suffix = stable_hash_payload(hash_payload, length=12)
        event_id = f"{event_id_prefix}_{hash_suffix}"

    # --- published_at ---
    raw_dt = raw_copy.get("datetime")
    published_at: str
    if raw_dt is None:
        published_at = "unknown"
    elif isinstance(raw_dt, (int, float)):
        try:
            dt_obj = datetime.fromtimestamp(raw_dt, tz=timezone.utc)
            published_at = dt_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            published_at = str(raw_dt)
    else:
        published_at = str(raw_dt).strip() or "unknown"

    # --- source ---
    raw_source = raw_copy.get("source", "")
    source = str(raw_source).strip() if raw_source else "unknown"

    # --- url ---
    raw_url = raw_copy.get("url")
    url: Optional[str] = str(raw_url).strip() if raw_url else None

    # --- summary ---
    raw_summary = raw_copy.get("summary")
    summary: Optional[str] = str(raw_summary).strip() if raw_summary else None

    # --- category ---
    raw_cat = raw_copy.get("category")
    raw_cat_str = str(raw_cat).strip() if raw_cat else None
    category = classify_news_category(
        headline=headline,
        summary=summary,
        raw_category=raw_cat_str,
    )

    # --- related_symbols ---
    raw_related = raw_copy.get("related", [])
    related_symbols: list[str]
    if isinstance(raw_related, str):
        related_symbols = [
            s.strip() for s in raw_related.split(",") if s.strip()
        ]
    elif isinstance(raw_related, list):
        related_symbols = [str(s).strip() for s in raw_related if str(s).strip()]
    else:
        related_symbols = []

    return NewsEvent(
        event_id=event_id,
        ticker=ticker,
        headline=headline,
        summary=summary,
        source=source,
        vendor="finnhub",
        url=url,
        published_at=published_at,
        category=category,
        related_symbols=related_symbols,
        raw_payload=raw_copy,  # shallow copy, not mutated
    )


# ---------------------------------------------------------------------------
# Helper 3: news_snapshot_from_events
# ---------------------------------------------------------------------------

def news_snapshot_from_events(
    snapshot_id: str,
    ticker: str,
    as_of: str,
    events: list[NewsEvent],
    vendor: NewsSourceVendor = "synthetic",
    lookback_days: Optional[int] = None,
    warnings: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> NewsSnapshot:
    """
    Build a ``NewsSnapshot`` from provided events.

    Does not fetch data.  Does not mutate inputs.

    Args:
        snapshot_id:   Non-empty unique identifier.
        ticker:        Non-empty ticker symbol.
        as_of:         Non-empty date/datetime string.
        events:        List of ``NewsEvent`` instances (shallow-copied).
        vendor:        Primary vendor for this snapshot.
        lookback_days: Optional lookback window in days (must be > 0 if given).
        warnings:      Optional list of advisory warnings (shallow-copied).
        metadata:      Optional metadata dict (shallow-copied).

    Returns:
        A new ``NewsSnapshot`` instance.

    Examples::

        ev = NewsEvent(event_id="e1", ticker="AAPL", headline="AAPL rallies",
                       source="Reuters", published_at="2026-05-21")
        snap = news_snapshot_from_events("snap_001", "AAPL", "2026-05-21", [ev])
        assert len(snap.events) == 1
    """
    return NewsSnapshot(
        snapshot_id=snapshot_id,
        ticker=ticker,
        as_of=as_of,
        vendor=vendor,
        events=list(events),
        lookback_days=lookback_days,
        warnings=list(warnings) if warnings is not None else [],
        metadata=dict(metadata) if metadata is not None else {},
    )


# ---------------------------------------------------------------------------
# Helper 4: news_tool_result_from_snapshot
# ---------------------------------------------------------------------------

def news_tool_result_from_snapshot(
    run_id: str,
    snapshot: NewsSnapshot,
    target: Optional[str] = None,
    calculation_version: str = "news_schema_v1",
) -> ToolResult:
    """
    Wrap a ``NewsSnapshot`` into the existing ``ToolResult`` model.

    The resulting ``ToolResult`` is suitable for submission to
    ``EvidenceStore.add_tool_result()``.  The caller is responsible for
    persisting it — this function does not write to disk.

    Args:
        run_id:              Run context ID (from ``create_run_context``).
        snapshot:            ``NewsSnapshot`` to wrap.
        target:              Research target string; defaults to
                             ``snapshot.ticker``.
        calculation_version: Schema/version tag embedded in outputs for
                             auditability.

    Returns:
        A ``ToolResult`` with:

        - ``tool_name = "news_snapshot"``
        - ``evidence_id`` — deterministic hash of outputs.
        - ``outputs`` — full serialised snapshot dict plus
          ``calculation_version``.
        - ``inputs`` — ``{snapshot_id, ticker, as_of, calculation_version}``.
        - ``ticker = snapshot.ticker``.
        - ``description`` — includes snapshot_id, ticker, event count, and
          any warnings.

    Determinism guarantee:
        Calling this function twice with the same ``run_id`` and ``snapshot``
        (identical field values) produces the same ``evidence_id``.

    Examples::

        tr = news_tool_result_from_snapshot("run_001", snap)
        assert tr.tool_name == "news_snapshot"
        assert snap.ticker in tr.evidence_id
    """
    effective_target = target if target else snapshot.ticker

    snapshot_dict = snapshot.model_dump()
    outputs: dict[str, Any] = {
        **snapshot_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_NEWS_TOOL_NAME,
        target=effective_target,
        metric_group=_NEWS_METRIC_GROUP,
        payload=outputs,
    )

    description_parts: list[str] = [
        f"NewsSnapshot {snapshot.snapshot_id!r} ticker={snapshot.ticker!r}"
        f" as_of={snapshot.as_of!r} ({len(snapshot.events)} event(s))"
    ]
    if snapshot.warnings:
        description_parts.append("warnings: " + "; ".join(snapshot.warnings))

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_NEWS_TOOL_NAME,
        run_id=run_id,
        ticker=snapshot.ticker,
        inputs={
            "snapshot_id": snapshot.snapshot_id,
            "ticker": snapshot.ticker,
            "as_of": snapshot.as_of,
            "calculation_version": calculation_version,
        },
        outputs=outputs,
        description="; ".join(description_parts),
    )


# ---------------------------------------------------------------------------
# Helper 5: extract_news_event_paths
# ---------------------------------------------------------------------------

def extract_news_event_paths(snapshot: NewsSnapshot) -> list[str]:
    """
    Return field paths suitable for ``EvidenceRef.field_path`` suggestions.

    Paths use dot-notation with zero-based integer indices for list elements.
    This function is deterministic and stable for the same snapshot.

    Args:
        snapshot: ``NewsSnapshot`` to extract paths from.

    Returns:
        A list of field path strings, e.g.:

        - ``"events.0.headline"``
        - ``"events.0.summary"``
        - ``"events.0.source"``
        - ``"events.0.url"``
        - ``"events.0.published_at"``
        - ``"events.0.category"``
        - ``"events.0.related_symbols"``

    Examples::

        paths = extract_news_event_paths(snap)
        assert "events.0.headline" in paths
    """
    paths: list[str] = []
    for i, _ in enumerate(snapshot.events):
        prefix = f"events.{i}"
        paths.extend([
            f"{prefix}.headline",
            f"{prefix}.summary",
            f"{prefix}.source",
            f"{prefix}.url",
            f"{prefix}.published_at",
            f"{prefix}.category",
            f"{prefix}.related_symbols",
        ])
    return paths


# ---------------------------------------------------------------------------
# Helper 6: summarize_news_snapshot_coverage
# ---------------------------------------------------------------------------

def _try_parse_date(date_str: str) -> Optional[datetime]:
    """
    Attempt to parse a date/datetime string.  Returns None on failure.
    Tries ISO-8601 and a few common Finnhub-style formats.
    """
    if not date_str or date_str == "unknown":
        return None
    # Try common formats
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    # Try fromisoformat (Python 3.11+)
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


def summarize_news_snapshot_coverage(
    snapshot: NewsSnapshot,
    stale_after_days: int = 14,
) -> NewsCoverageSummary:
    """
    Build a ``NewsCoverageSummary`` for a ``NewsSnapshot``.

    Behavior:
        - Counts total events.
        - Lists unique ``NewsEventCategory`` values (sorted).
        - Lists unique ``NewsSourceVendor`` values (sorted).
        - Counts events missing a URL.
        - Counts events with a duplicate headline (case-insensitive).
        - Counts events with a duplicate URL (ignoring ``None`` URLs).
        - Counts stale events (``published_at`` parseable and older than
          ``stale_after_days`` before ``snapshot.as_of``).  If date parsing
          fails, ``stale_event_count`` remains 0 and a warning is added.
        - Returns warnings for empty snapshots or unparseable timestamps.

    Args:
        snapshot:        ``NewsSnapshot`` to summarise.
        stale_after_days: Number of days before ``as_of`` at which an event
                          is considered stale (default 14).

    Returns:
        A ``NewsCoverageSummary`` instance.

    Examples::

        summary = summarize_news_snapshot_coverage(snap)
        summary["event_count"]              # → int
        summary["duplicate_headline_count"] # → int
    """
    warnings_out: list[str] = []
    events = snapshot.events

    if not events:
        warnings_out.append("No news events in snapshot.")
        return NewsCoverageSummary(
            ticker=snapshot.ticker,
            event_count=0,
            warnings=warnings_out,
        )

    # --- categories and vendors ---
    categories_present: list[NewsEventCategory] = sorted(
        set(e.category for e in events)  # type: ignore[arg-type]
    )
    vendors_present: list[NewsSourceVendor] = sorted(
        set(e.vendor for e in events)  # type: ignore[arg-type]
    )

    # --- missing URLs ---
    missing_url_count = sum(1 for e in events if not e.url)

    # --- duplicate headlines (case-insensitive) ---
    from collections import Counter
    headline_counts = Counter(e.headline.lower().strip() for e in events)
    duplicate_headline_count = sum(
        count for count in headline_counts.values() if count > 1
    )

    # --- duplicate URLs (ignore None) ---
    urls_with_value = [e.url for e in events if e.url]
    url_counts = Counter(urls_with_value)
    duplicate_url_count = sum(
        count for count in url_counts.values() if count > 1
    )

    # --- stale events ---
    stale_event_count = 0
    as_of_dt = _try_parse_date(snapshot.as_of)
    staleness_checked = False

    if as_of_dt is not None:
        staleness_checked = True
        # Remove timezone info for comparison if as_of_dt is naive
        as_of_naive = as_of_dt.replace(tzinfo=None) if as_of_dt.tzinfo else as_of_dt
        for ev in events:
            ev_dt = _try_parse_date(ev.published_at)
            if ev_dt is None:
                staleness_checked = False  # at least one event is unparseable
                continue
            ev_naive = ev_dt.replace(tzinfo=None) if ev_dt.tzinfo else ev_dt
            age_days = (as_of_naive - ev_naive).days
            if age_days > stale_after_days:
                stale_event_count += 1

    if not staleness_checked:
        warnings_out.append(
            "Staleness not fully evaluated: one or more event timestamps "
            "could not be parsed."
        )

    return NewsCoverageSummary(
        ticker=snapshot.ticker,
        event_count=len(events),
        categories_present=categories_present,
        vendors_present=vendors_present,
        missing_url_count=missing_url_count,
        duplicate_headline_count=duplicate_headline_count,
        duplicate_url_count=duplicate_url_count,
        stale_event_count=stale_event_count,
        warnings=warnings_out,
    )


# ---------------------------------------------------------------------------
# Helper 7: validate_news_snapshot
# ---------------------------------------------------------------------------

def validate_news_snapshot(snapshot: NewsSnapshot) -> list[str]:
    """
    Perform lightweight advisory validation on *snapshot*.

    Returns warning strings for soft issues.  Does not raise exceptions.
    Does not integrate with ``ValidationReport`` in this phase.

    Checked conditions:

    1. No events.
    2. Event ticker mismatch with snapshot ticker.
    3. Missing URL.
    4. Duplicate headline (case-insensitive).
    5. Duplicate URL (non-None).
    6. Missing summary.
    7. Unknown category (``"unknown"``).
    8. Missing related symbols (empty list).
    9. Stale event if date comparison is safely possible.
    10. Inconsistent vendor between snapshot and events.

    Args:
        snapshot: ``NewsSnapshot`` to validate.

    Returns:
        List of warning strings (may be empty for a clean snapshot).

    Examples::

        warnings = validate_news_snapshot(snap)
        # [] for a clean snapshot
    """
    from collections import Counter

    warnings_out: list[str] = []
    events = snapshot.events

    # 1. No events
    if not events:
        warnings_out.append("NewsSnapshot has no events.")
        return warnings_out

    # 2. Ticker mismatch
    mismatched_tickers = [
        e.event_id for e in events if e.ticker != snapshot.ticker
    ]
    if mismatched_tickers:
        warnings_out.append(
            f"Event ticker does not match snapshot ticker {snapshot.ticker!r}: "
            f"event_ids={mismatched_tickers}."
        )

    # 3. Missing URL
    missing_url_ids = [e.event_id for e in events if not e.url]
    if missing_url_ids:
        warnings_out.append(
            f"Events missing URL: event_ids={missing_url_ids}."
        )

    # 4. Duplicate headlines
    headline_counts = Counter(e.headline.lower().strip() for e in events)
    dup_headlines = [h for h, count in headline_counts.items() if count > 1]
    if dup_headlines:
        warnings_out.append(
            f"Duplicate headlines detected ({len(dup_headlines)} distinct): "
            f"{dup_headlines[:3]}{'...' if len(dup_headlines) > 3 else ''}."
        )

    # 5. Duplicate URLs
    urls_with_value = [e.url for e in events if e.url]
    url_counts = Counter(urls_with_value)
    dup_urls = [u for u, count in url_counts.items() if count > 1]
    if dup_urls:
        warnings_out.append(
            f"Duplicate URLs detected ({len(dup_urls)} distinct): "
            f"{dup_urls[:3]}{'...' if len(dup_urls) > 3 else ''}."
        )

    # 6. Missing summary
    no_summary_ids = [e.event_id for e in events if not e.summary]
    if no_summary_ids:
        warnings_out.append(
            f"Events missing summary: event_ids={no_summary_ids}."
        )

    # 7. Unknown category
    unknown_cat_ids = [e.event_id for e in events if e.category == "unknown"]
    if unknown_cat_ids:
        warnings_out.append(
            f"Events with unknown category: event_ids={unknown_cat_ids}."
        )

    # 8. Missing related symbols
    no_related_ids = [e.event_id for e in events if not e.related_symbols]
    if no_related_ids:
        warnings_out.append(
            f"Events with no related_symbols: event_ids={no_related_ids}."
        )

    # 9. Stale events (best-effort)
    as_of_dt = _try_parse_date(snapshot.as_of)
    if as_of_dt is not None:
        as_of_naive = as_of_dt.replace(tzinfo=None) if as_of_dt.tzinfo else as_of_dt
        stale_ids: list[str] = []
        for ev in events:
            ev_dt = _try_parse_date(ev.published_at)
            if ev_dt is None:
                continue
            ev_naive = ev_dt.replace(tzinfo=None) if ev_dt.tzinfo else ev_dt
            age_days = (as_of_naive - ev_naive).days
            if age_days > 14:
                stale_ids.append(ev.event_id)
        if stale_ids:
            warnings_out.append(
                f"Stale events (>14 days before as_of): event_ids={stale_ids}."
            )

    # 10. Vendor inconsistency
    event_vendors = {e.vendor for e in events}
    if len(event_vendors) > 1:
        warnings_out.append(
            f"Inconsistent vendors in events: {sorted(event_vendors)}. "
            f"Snapshot vendor is {snapshot.vendor!r}."
        )
    elif event_vendors and list(event_vendors)[0] != snapshot.vendor:
        warnings_out.append(
            f"Event vendor {list(event_vendors)[0]!r} does not match "
            f"snapshot vendor {snapshot.vendor!r}."
        )

    return warnings_out
