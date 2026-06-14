"""Thesis Ingestion — a thesis card library for manually-curated external research.

External research articles / interviews are fed in by the user, extracted into
structured cards by one LLM call per card, stored as local JSON files, and
browsed through the Thesis Library Streamlit page.

ISOLATION INVARIANT (load-bearing): this package has **zero interaction** with
the scoring, ranking, snapshot, or anchor systems. Nothing here is imported by
``opportunity_ranker``, ``signal_engine``, ``candidate_generator``,
``market_internals``, ``macro_regime``, ``anchor_cache``, ``anchor_archive`` or
any snapshot writer. The only I/O is local file reads/writes plus the Anthropic
client the caller passes in. No paid API, no broker / order / execution field.

Submodules:
  * ``schema``    — ThesisCard / ScenarioCard contracts + deterministic builders
  * ``store``     — card read/write, ingest log, staleness, status management
  * ``validator`` — deterministic post-extraction validation
  * ``extractor`` — LLM preview + per-argument extraction; document reading
"""

from __future__ import annotations

from . import schema, store, validator  # noqa: F401  (re-export submodules)

# ``extractor`` is imported lazily (it is only needed on the ingest path and
# pulls the Anthropic client) — access via ``lib.thesis_ingestion.extractor``.
__all__ = ["schema", "store", "validator"]
