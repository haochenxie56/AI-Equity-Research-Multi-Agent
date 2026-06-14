"""Thesis Ingestion — schema definitions.

Structured card schema for the Thesis Card Library (manually curated external
research articles / interviews extracted into structured cards by one LLM call
per card).

This module is **pure type/contract definitions plus deterministic builders**.
It performs no I/O, no network calls, and imports nothing from the scoring /
ranking / snapshot / anchor systems. Field names match the architecture spec
exactly.

Invariant fields (``current_evidence_status`` / ``evidence_refs`` / schema
versions / ``coi.status`` defaults / IDs) are set deterministically by the
builders here and by ``extractor.py`` — never by free-form LLM output — in line
with the project rule *"Deterministic computation, agentic interpretation."*
"""

from __future__ import annotations

from typing import TypedDict

# ── Version / invariant constants ────────────────────────────────────────────
SCHEMA_VERSION_THESIS = "thesis-1.0"
SCHEMA_VERSION_SCENARIO = "scenario-1.0"
PROMPT_VERSION = "thesis-extract-v1"

# current_evidence_status may ONLY ever be this value anywhere in this feature.
EVIDENCE_STATUS_FIXED = "unknown"

# Enumerations (mirrored by validator.py — kept here as the single source).
CARD_STATUS_VALID = ("active", "silenced", "unavailable")
HORIZON_VALID = ("short", "mid", "long")
PROVENANCE_VALID = ("stated_by_author", "inferred")
OBSERVABLE_VALID = ("machine_checkable", "human_judgment", "unspecified")
DOC_TYPE_VALID = ("interview", "research_report", "article", "transcript", "other")
LANGUAGE_VALID = ("zh", "en", "mixed")
COI_STATUS_VALID = ("coi_unassessed", "coi_disclosed")


# ── ScenarioCard sub-structures ──────────────────────────────────────────────
class TransmissionStep(TypedDict, total=False):
    step: int
    from_node: str   # "from_node" not "from" — "from" is a Python keyword
    to_node: str
    mechanism: str       # legacy single-language (optional, backward compat)
    mechanism_en: str    # bilingual UI-facing description
    mechanism_zh: str
    provenance: str  # "stated_by_author" | "inferred"


class Condition(TypedDict, total=False):
    condition_text: str       # legacy single-language (optional, backward compat)
    condition_text_en: str    # bilingual UI-facing description
    condition_text_zh: str
    observable: str   # "machine_checkable" | "human_judgment" | "unspecified"
    provenance: str   # "stated_by_author" | "inferred"


class ScenarioCard(TypedDict, total=False):
    schema_version: str                      # "scenario-1.0"
    scenario_id: str                         # sha256 of normalised content, first 16
    event_or_hypothesis: str                 # legacy bare (optional, backward compat)
    event_or_hypothesis_en: str              # bilingual UI-facing one-sentence event
    event_or_hypothesis_zh: str
    transmission_chain: list[TransmissionStep]
    affected_horizons: list[str]             # subset of ["short", "mid", "long"]
    affected_themes: list[str]               # from existing theme_baskets names
    unmapped_themes: list[str]               # author themes not in baskets
    affected_tickers: list[str]              # uppercase tickers explicitly named
    confirmation_conditions: list[Condition]
    falsification_conditions: list[Condition]
    current_evidence_status: str             # always "unknown"
    evidence_refs: list                      # always empty list in MVP
    notes: str                               # legacy bare (optional, backward compat)
    notes_en: str                            # bilingual UI-facing notes
    notes_zh: str


# ── ThesisCard sub-structures ────────────────────────────────────────────────
class CardSource(TypedDict, total=False):
    doc_hash: str                  # sha256 of raw file bytes — dedup key
    doc_path: str                  # absolute path to local backup copy
    doc_type: str                  # interview|research_report|article|transcript|other
    title: str
    author: str                    # "unknown" if not found
    author_affiliation: str        # "unknown" if not found
    publication_date: str | None   # "YYYY-MM-DD" or null
    publication_date_provenance: str  # stated_in_document|inferred_from_content|unspecified
    language: str                  # "zh" | "en" | "mixed"
    ingested_at: str               # ISO timestamp


class CardCOI(TypedDict, total=False):
    status: str   # "coi_unassessed" at extraction time
    notes: str    # empty unless author explicitly discloses


class CoreClaim(TypedDict, total=False):
    claim_id: str                  # card_id + "-c" + str(n)
    claim_text_en: str
    claim_text_zh: str
    claim_type: str                # thesis|risk_warning|timing_call|structural_observation
    related_tickers: list[str]
    related_themes: list[str]


class NumericClaim(TypedDict, total=False):
    metric: str
    value: float
    unit: str                      # ratio|usd|pct|count|other
    applies_to: str
    time_reference: str            # author's stated time frame, "unspecified" if absent
    provenance: str                # "stated_by_author" | "inferred"
    source_quote: str              # original text excerpt, max one sentence


class UnspecifiedNumeric(TypedDict, total=False):
    metric: str
    direction: str                 # "up" | "down" | "unspecified"
    note: str                      # original text excerpt — never fill a proxy value


class ExtractionMeta(TypedDict, total=False):
    llm_model: str
    prompt_version: str            # "thesis-extract-v1"
    extracted_at: str              # ISO timestamp
    extraction_seq: int            # 1 for first extraction of a given doc_hash


class ThesisCard(TypedDict, total=False):
    schema_version: str            # "thesis-1.0"
    card_id: str                   # first 16 of doc_hash + "-" + str(extraction_seq)
    source: CardSource
    horizon_type: str              # short|mid|long — set by user, not LLM
    coi: CardCOI
    card_status: str               # active|silenced|unavailable
    core_claims: list[CoreClaim]
    numeric_claims: list[NumericClaim]
    unspecified_numerics: list[UnspecifiedNumeric]
    assumptions: list[str]
    scenarios: list[ScenarioCard]
    extraction_meta: ExtractionMeta


# ── Deterministic builders ───────────────────────────────────────────────────
# These fill the structural / invariant fields with safe defaults so that no
# code path can accidentally write a forbidden value. LLM-derived *content*
# (claims, numeric_claims, transmission chains, ...) is merged on top by the
# extractor; the invariant fields below are then re-forced.

def empty_coi() -> CardCOI:
    """COI block at extraction time — always unassessed, no notes."""
    return {"status": "coi_unassessed", "notes": ""}


def new_scenario_card(
    *,
    scenario_id: str = "",
    event_or_hypothesis: str = "",
    event_or_hypothesis_en: str = "",
    event_or_hypothesis_zh: str = "",
    transmission_chain: list | None = None,
    affected_horizons: list | None = None,
    affected_themes: list | None = None,
    unmapped_themes: list | None = None,
    affected_tickers: list | None = None,
    confirmation_conditions: list | None = None,
    falsification_conditions: list | None = None,
    notes: str = "",
    notes_en: str = "",
    notes_zh: str = "",
) -> ScenarioCard:
    """Build a schema-complete ScenarioCard.

    ``event_or_hypothesis`` and ``notes`` are bilingual: the canonical keys are
    ``*_en`` / ``*_zh``. For convenience the legacy bare ``event_or_hypothesis`` /
    ``notes`` params seed BOTH language keys when the explicit ``*_en`` / ``*_zh``
    are not given. ``current_evidence_status`` is forced to ``"unknown"`` and
    ``evidence_refs`` to ``[]`` — these two are never caller-overridable.
    """
    return {
        "schema_version": SCHEMA_VERSION_SCENARIO,
        "scenario_id": scenario_id,
        "event_or_hypothesis_en": event_or_hypothesis_en or event_or_hypothesis,
        "event_or_hypothesis_zh": event_or_hypothesis_zh or event_or_hypothesis,
        "transmission_chain": list(transmission_chain or []),
        "affected_horizons": list(affected_horizons or []),
        "affected_themes": list(affected_themes or []),
        "unmapped_themes": list(unmapped_themes or []),
        "affected_tickers": list(affected_tickers or []),
        "confirmation_conditions": list(confirmation_conditions or []),
        "falsification_conditions": list(falsification_conditions or []),
        "current_evidence_status": EVIDENCE_STATUS_FIXED,
        "evidence_refs": [],
        "notes_en": notes_en or notes,
        "notes_zh": notes_zh or notes,
    }


def new_source(
    *,
    doc_hash: str,
    doc_path: str = "",
    doc_type: str = "other",
    title: str = "",
    author: str = "unknown",
    author_affiliation: str = "unknown",
    publication_date: str | None = None,
    publication_date_provenance: str = "unspecified",
    language: str = "en",
    ingested_at: str = "",
) -> CardSource:
    """Build a schema-complete card ``source`` block."""
    return {
        "doc_hash": doc_hash,
        "doc_path": doc_path,
        "doc_type": doc_type,
        "title": title,
        "author": author,
        "author_affiliation": author_affiliation,
        "publication_date": publication_date,
        "publication_date_provenance": publication_date_provenance,
        "language": language,
        "ingested_at": ingested_at,
    }


def new_thesis_card(
    *,
    card_id: str,
    source: CardSource,
    horizon_type: str,
    extraction_meta: ExtractionMeta,
    core_claims: list | None = None,
    numeric_claims: list | None = None,
    unspecified_numerics: list | None = None,
    assumptions: list | None = None,
    scenarios: list | None = None,
    coi: CardCOI | None = None,
    card_status: str = "active",
) -> ThesisCard:
    """Build a schema-complete ThesisCard with safe structural defaults.

    The schema version and ``coi`` default are forced here; content lists are
    copied so callers cannot mutate shared references.
    """
    return {
        "schema_version": SCHEMA_VERSION_THESIS,
        "card_id": card_id,
        "source": dict(source),
        "horizon_type": horizon_type,
        "coi": dict(coi) if coi else empty_coi(),
        "card_status": card_status,
        "core_claims": list(core_claims or []),
        "numeric_claims": list(numeric_claims or []),
        "unspecified_numerics": list(unspecified_numerics or []),
        "assumptions": list(assumptions or []),
        "scenarios": list(scenarios or []),
        "extraction_meta": dict(extraction_meta),
    }


__all__ = [
    "SCHEMA_VERSION_THESIS",
    "SCHEMA_VERSION_SCENARIO",
    "PROMPT_VERSION",
    "EVIDENCE_STATUS_FIXED",
    "CARD_STATUS_VALID",
    "HORIZON_VALID",
    "PROVENANCE_VALID",
    "OBSERVABLE_VALID",
    "DOC_TYPE_VALID",
    "LANGUAGE_VALID",
    "COI_STATUS_VALID",
    "TransmissionStep",
    "Condition",
    "ScenarioCard",
    "CardSource",
    "CardCOI",
    "CoreClaim",
    "NumericClaim",
    "UnspecifiedNumeric",
    "ExtractionMeta",
    "ThesisCard",
    "empty_coi",
    "new_scenario_card",
    "new_source",
    "new_thesis_card",
]
