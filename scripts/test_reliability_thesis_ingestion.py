#!/usr/bin/env python3
"""Reliability test suite — Thesis Ingestion MVP.

Self-contained (stdlib ``unittest`` only). NO network. NO writes under ``data/``
— every storage test redirects the library root into a
``tempfile.TemporaryDirectory`` via ``store.set_library_root``.

Groups:
  1. Schema & validation        (>= 25 assertions)
  2. Staleness & active compute  (>= 20 assertions)
  3. Storage isolation           (>= 15 assertions, temp library root)
  4. Isolation invariants        (>= 10 assertions, negative guards)

Run:
    python scripts/test_reliability_thesis_ingestion.py -v
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock
from datetime import date, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))

from lib.thesis_ingestion import schema, store, validator  # noqa: E402


# ── Shared fixtures ───────────────────────────────────────────────────────────
def _doc_hash(seed: bytes = b"the article raw bytes v1") -> str:
    return hashlib.sha256(seed).hexdigest()


def valid_card(seed: bytes = b"the article raw bytes v1", *, horizon: str = "mid",
               publication_date: str | None = "2026-05-01") -> dict:
    """A schema-complete card that passes ``validate_card`` cleanly."""
    h = _doc_hash(seed)
    cid = store.card_id_from_hash(h, 1)
    scenario = schema.new_scenario_card(
        event_or_hypothesis_en="AI capex accelerates through 2026.",
        event_or_hypothesis_zh="AI 资本开支在 2026 年持续加速。",
        transmission_chain=[{
            "step": 1, "from_node": "hyperscaler capex", "to_node": "GPU demand",
            "mechanism_en": "more datacenter spend lifts accelerator orders",
            "mechanism_zh": "数据中心支出增加带动加速卡订单",
            "provenance": "stated_by_author",
        }],
        affected_horizons=["mid"],
        affected_themes=["ai_chips"],
        affected_tickers=["NVDA"],
        confirmation_conditions=[{
            "condition_text_en": "Hyperscaler capex guidance raised next quarter.",
            "condition_text_zh": "下季度超大规模厂商资本开支指引上调。",
            "observable": "machine_checkable", "provenance": "stated_by_author",
        }],
        falsification_conditions=[{
            "condition_text_en": "Capex guidance cut.",
            "condition_text_zh": "资本开支指引下调。",
            "observable": "human_judgment", "provenance": "inferred",
        }],
    )
    return schema.new_thesis_card(
        card_id=cid,
        source=schema.new_source(
            doc_hash=h, doc_path="", doc_type="research_report",
            title="AI capex thesis", author="Jane Analyst",
            publication_date=publication_date,
            publication_date_provenance="stated_in_document", language="en",
        ),
        horizon_type=horizon,
        extraction_meta={
            "llm_model": "claude-sonnet-4-6",
            "prompt_version": "thesis-extract-v1",
            "extracted_at": "2026-05-02T10:00:00",
            "extraction_seq": 1,
        },
        core_claims=[{
            "claim_id": cid + "-c1",
            "claim_text_en": "AI capex keeps rising.",
            "claim_text_zh": "AI 资本开支持续上升。",
            "claim_type": "thesis",
            "related_tickers": ["NVDA"],
            "related_themes": ["ai_chips"],
        }],
        numeric_claims=[{
            "metric": "capex_growth", "value": 35.0, "unit": "pct",
            "applies_to": "hyperscalers", "time_reference": "2026",
            "provenance": "stated_by_author", "source_quote": "capex up 35% this year",
        }],
        unspecified_numerics=[{
            "metric": "gross_margin", "direction": "up",
            "note": "margins should improve as scale grows",
        }],
        assumptions=["Demand for accelerators stays supply-constrained."],
        scenarios=[scenario],
    )


def _card_for_staleness(horizon: str, days_ago, today: date) -> dict:
    """Minimal card carrying a publication_date `days_ago` before `today`."""
    pub = None if days_ago is None else (today - timedelta(days=days_ago)).isoformat()
    return {
        "horizon_type": horizon,
        "card_status": "active",
        "source": {"publication_date": pub},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Group 1 — Schema & validation
# ═══════════════════════════════════════════════════════════════════════════════
class TestSchemaValidation(unittest.TestCase):
    def _codes(self, errors):
        return [e.split(":", 1)[0] for e in errors]

    def assertHasCode(self, errors, code):
        self.assertIn(code, self._codes(errors), f"expected {code} in {errors}")

    def test_valid_card_passes(self):
        ok, errors = validator.validate_card(valid_card())
        self.assertTrue(ok, f"valid card rejected: {errors}")
        self.assertEqual(errors, [])

    def test_invalid_card_status(self):
        c = valid_card(); c["card_status"] = "deleted"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_card_status")

    def test_invalid_horizon_type(self):
        c = valid_card(); c["horizon_type"] = "weekly"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_horizon_type")

    def test_invalid_doc_type(self):
        c = valid_card(); c["source"]["doc_type"] = "tweet"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_doc_type")

    def test_invalid_language(self):
        c = valid_card(); c["source"]["language"] = "fr"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_language")

    def test_evidence_status_tampered_top_level(self):
        c = valid_card(); c["current_evidence_status"] = "confirmed"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "evidence_status_tampered")

    def test_evidence_status_tampered_scenario(self):
        c = valid_card(); c["scenarios"][0]["current_evidence_status"] = "refuted"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "evidence_status_tampered")

    def test_evidence_refs_tampered(self):
        c = valid_card(); c["scenarios"][0]["evidence_refs"] = ["ev_1"]
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "evidence_refs_tampered")

    def test_invalid_coi_status(self):
        c = valid_card(); c["coi"]["status"] = "conflicted"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_coi_status")

    def test_coi_disclosed_is_allowed(self):
        c = valid_card(); c["coi"] = {"status": "coi_disclosed", "notes": "author holds NVDA"}
        ok, errors = validator.validate_card(c)
        self.assertTrue(ok, f"coi_disclosed should be valid: {errors}")

    def test_numeric_claim_missing_provenance(self):
        c = valid_card(); c["numeric_claims"][0].pop("provenance")
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "extraction_rejected_missing_provenance")

    def test_numeric_claim_null_value(self):
        c = valid_card(); c["numeric_claims"][0]["value"] = None
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "extraction_rejected_missing_provenance")

    def test_numeric_claim_invalid_provenance(self):
        c = valid_card(); c["numeric_claims"][0]["provenance"] = "guessed"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_provenance")

    def test_unspecified_numeric_with_value(self):
        c = valid_card(); c["unspecified_numerics"][0]["value"] = 12.0
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "extraction_rejected_fabricated_numeric")

    def test_transmission_step_missing_node(self):
        c = valid_card(); c["scenarios"][0]["transmission_chain"][0]["to_node"] = ""
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_transmission_step")

    def test_transmission_step_invalid_provenance(self):
        c = valid_card(); c["scenarios"][0]["transmission_chain"][0]["provenance"] = "maybe"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_transmission_step")

    def test_condition_invalid_observable(self):
        c = valid_card(); c["scenarios"][0]["confirmation_conditions"][0]["observable"] = "vibes"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_condition")

    def test_mechanism_missing_both_languages(self):
        c = valid_card()
        step = c["scenarios"][0]["transmission_chain"][0]
        step.pop("mechanism_en", None); step.pop("mechanism_zh", None)
        step.pop("mechanism", None)
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_transmission_step")

    def test_mechanism_en_only_is_valid(self):
        c = valid_card()
        step = c["scenarios"][0]["transmission_chain"][0]
        step.pop("mechanism_zh", None)
        ok, errors = validator.validate_card(c)
        self.assertTrue(ok, f"mechanism_en alone should satisfy presence: {errors}")

    def test_condition_text_missing_both_languages(self):
        c = valid_card()
        cond = c["scenarios"][0]["confirmation_conditions"][0]
        cond.pop("condition_text_en", None); cond.pop("condition_text_zh", None)
        cond.pop("condition_text", None)
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_condition")

    def test_legacy_bare_mechanism_still_valid(self):
        # Backward compat: a pre-bilingual card with a bare `mechanism` validates.
        c = valid_card()
        step = c["scenarios"][0]["transmission_chain"][0]
        step.pop("mechanism_en", None); step.pop("mechanism_zh", None)
        step["mechanism"] = "legacy single-language mechanism"
        cond = c["scenarios"][0]["confirmation_conditions"][0]
        cond.pop("condition_text_en", None); cond.pop("condition_text_zh", None)
        cond["condition_text"] = "legacy single-language condition"
        ok, errors = validator.validate_card(c)
        self.assertTrue(ok, f"legacy bare fields should validate: {errors}")

    def test_invalid_doc_hash(self):
        c = valid_card(); c["source"]["doc_hash"] = "abc123"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_doc_hash")

    def test_invalid_card_id_prefix(self):
        c = valid_card(); c["card_id"] = "deadbeefdeadbeef-1"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_card_id")

    def test_core_claim_missing_zh(self):
        c = valid_card(); c["core_claims"][0]["claim_text_zh"] = ""
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_core_claim")

    def test_core_claim_missing_en(self):
        c = valid_card(); c["core_claims"][0]["claim_text_en"] = ""
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_core_claim")

    def test_empty_core_claims_rejected(self):
        c = valid_card(); c["core_claims"] = []
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_core_claims")

    def test_observable_boolean_coercion(self):
        from lib.thesis_ingestion.extractor import _normalise_observable
        self.assertEqual(_normalise_observable(True), "machine_checkable")
        self.assertEqual(_normalise_observable("true"), "machine_checkable")
        self.assertEqual(_normalise_observable(False), "unspecified")
        self.assertEqual(_normalise_observable("false"), "unspecified")
        # valid strings pass through unchanged
        self.assertEqual(_normalise_observable("machine_checkable"), "machine_checkable")
        self.assertEqual(_normalise_observable("human_judgment"), "human_judgment")
        self.assertEqual(_normalise_observable("unspecified"), "unspecified")
        # anything else degrades to "unspecified"
        self.assertEqual(_normalise_observable("garbage"), "unspecified")

    def test_horizon_normalisation(self):
        from lib.thesis_ingestion.extractor import _normalise_horizon
        self.assertEqual(_normalise_horizon("中期"), "mid")
        self.assertEqual(_normalise_horizon("短期"), "short")
        self.assertEqual(_normalise_horizon("长期"), "long")
        self.assertEqual(_normalise_horizon("medium-term"), "mid")
        self.assertEqual(_normalise_horizon("SHORT"), "short")
        # decorated forms map via prefix matching
        self.assertEqual(_normalise_horizon("中期（12–24个月）"), "mid")
        self.assertEqual(_normalise_horizon("short-term (0-3 months)"), "short")
        # genuinely unrecognised values are still dropped (return None)
        self.assertIsNone(_normalise_horizon("quarterly"))

    def test_direction_normalisation(self):
        from lib.thesis_ingestion.extractor import _normalise_direction
        self.assertEqual(_normalise_direction("upside_risk"), "up")
        self.assertEqual(_normalise_direction("downside_risk"), "down")
        self.assertEqual(_normalise_direction("up"), "up")
        self.assertEqual(_normalise_direction("下行"), "down")
        # unknown → unspecified
        self.assertEqual(_normalise_direction("sideways"), "unspecified")
        self.assertEqual(_normalise_direction(None), "unspecified")

    def test_parse_json_repairs_unescaped_quotes(self):
        from lib.thesis_ingestion.extractor import _parse_json
        # Simulate the exact failure mode: unescaped quotes in notes_zh
        # make the top-level object fail to parse on Strategy 1.
        bad_json = (
            '{"core_claims": [{"claim_text_en": "test", '
            '"claim_text_zh": "test", "claim_type": "thesis", '
            '"related_tickers": [], "related_themes": []}], '
            '"numeric_claims": [], "scenarios": [], "assumptions": [], '
            '"coi": {"status": "coi_unassessed", "notes": ""}, '
            '"notes_zh": "文中"CXMT"指中际旭创。", '
            '"notes_en": "CXMT is a company."}'
        )
        result = _parse_json(bad_json)
        self.assertIn("core_claims", result,
            "Strategy 2 should repair unescaped quotes and return top-level object")
        self.assertEqual(len(result["core_claims"]), 1)

    def test_inner_object_parse_raises_extraction_error(self):
        # Regression: when the LLM emits unescaped quotes, the top-level JSON is
        # undecodable and _parse_json's scanner falls through to the first inner
        # object (a core_claims item). extract_card must turn that silent
        # data-loss into a visible ExtractionError, not assemble an empty card.
        from lib.thesis_ingestion import extractor as ex

        inner = {  # keys of a single core_claims ITEM, not a card
            "claim_text_en": "x", "claim_text_zh": "y", "claim_type": "thesis",
            "related_tickers": [], "related_themes": [],
        }
        with mock.patch.object(ex, "_call", return_value='{"junk": 1}'), \
             mock.patch.object(ex, "_parse_json", return_value=inner):
            with self.assertRaises(ex.ExtractionError):
                ex.extract_card(
                    file_text="text", argument_index=1, argument_headline="h",
                    horizon_type="mid", doc_meta={"doc_hash": "a" * 64},
                    llm_client=None, extraction_seq=1,
                )

    def test_valid_top_level_parse_does_not_raise(self):
        # A genuine card object (has core_claims at top level) must NOT trip the
        # inner-object guard.
        from lib.thesis_ingestion import extractor as ex

        card_like = {
            "core_claims": [{"claim_text_en": "a", "claim_text_zh": "b"}],
            "numeric_claims": [], "unspecified_numerics": [],
            "assumptions": [], "scenarios": [], "coi": {"status": "coi_unassessed"},
        }
        with mock.patch.object(ex, "_call", return_value="{}"), \
             mock.patch.object(ex, "_parse_json", return_value=card_like):
            card = ex.extract_card(
                file_text="text", argument_index=1, argument_headline="h",
                horizon_type="mid", doc_meta={"doc_hash": "a" * 64},
                llm_client=None, extraction_seq=1,
            )
        self.assertEqual(len(card["core_claims"]), 1)

    def test_invalid_prompt_version(self):
        c = valid_card(); c["extraction_meta"]["prompt_version"] = "v0"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        self.assertHasCode(errors, "invalid_prompt_version")

    def test_multiple_errors_no_short_circuit(self):
        c = valid_card()
        c["card_status"] = "nope"
        c["horizon_type"] = "nope"
        c["source"]["language"] = "nope"
        c["extraction_meta"]["prompt_version"] = "nope"
        ok, errors = validator.validate_card(c)
        self.assertFalse(ok)
        codes = self._codes(errors)
        self.assertIn("invalid_card_status", codes)
        self.assertIn("invalid_horizon_type", codes)
        self.assertIn("invalid_language", codes)
        self.assertIn("invalid_prompt_version", codes)
        self.assertGreaterEqual(len(errors), 4)

    def test_builders_set_invariants(self):
        sc = schema.new_scenario_card(event_or_hypothesis="x")
        self.assertEqual(sc["current_evidence_status"], "unknown")
        self.assertEqual(sc["evidence_refs"], [])
        self.assertEqual(sc["schema_version"], "scenario-1.0")
        card = valid_card()
        self.assertEqual(card["schema_version"], "thesis-1.0")
        self.assertEqual(card["coi"]["status"], "coi_unassessed")


# ═══════════════════════════════════════════════════════════════════════════════
# Group 2 — Staleness & active computation
# ═══════════════════════════════════════════════════════════════════════════════
class TestStalenessActive(unittest.TestCase):
    T0 = date(2026, 6, 1)

    def _stale(self, horizon, days_ago):
        return store.compute_staleness(
            _card_for_staleness(horizon, days_ago, self.T0), today=self.T0
        )

    def test_short_fresh_day0(self):
        self.assertEqual(self._stale("short", 0)["tier"], "fresh")

    def test_short_fresh_day29(self):
        self.assertEqual(self._stale("short", 29)["tier"], "fresh")

    def test_short_fresh_boundary_day30(self):
        self.assertEqual(self._stale("short", 30)["tier"], "fresh")

    def test_short_expired_day31(self):
        self.assertEqual(self._stale("short", 31)["tier"], "expired")

    def test_short_no_aging_warning(self):
        self.assertFalse(self._stale("short", 31)["show_aging_warning"])

    def test_mid_fresh_day89(self):
        s = self._stale("mid", 89)
        self.assertEqual(s["tier"], "fresh")
        self.assertFalse(s["show_aging_warning"])

    def test_mid_aging_day91_warns(self):
        s = self._stale("mid", 91)
        self.assertEqual(s["tier"], "aging")
        self.assertTrue(s["show_aging_warning"])

    def test_mid_aging_boundary_day180(self):
        s = self._stale("mid", 180)
        self.assertEqual(s["tier"], "aging")
        self.assertTrue(s["show_aging_warning"])

    def test_mid_expired_day181(self):
        s = self._stale("mid", 181)
        self.assertEqual(s["tier"], "expired")
        self.assertFalse(s["show_aging_warning"])

    def test_long_always_not_applicable(self):
        for d in (0, 50, 400):
            s = self._stale("long", d)
            self.assertEqual(s["tier"], "not_applicable")
            self.assertFalse(s["show_aging_warning"])

    def test_null_date_not_applicable_all_horizons(self):
        for h in ("short", "mid", "long"):
            s = self._stale(h, None)
            self.assertEqual(s["tier"], "not_applicable")
            self.assertIsNone(s["days_since_publication"])
            self.assertFalse(s["show_aging_warning"])

    def test_days_since_publication_value(self):
        self.assertEqual(self._stale("mid", 45)["days_since_publication"], 45)

    def _active(self, card):
        return store.compute_is_active(card, store.compute_staleness(card, today=self.T0))

    def test_silenced_inactive(self):
        c = _card_for_staleness("short", 0, self.T0); c["card_status"] = "silenced"
        self.assertFalse(self._active(c))

    def test_unavailable_inactive(self):
        c = _card_for_staleness("short", 0, self.T0); c["card_status"] = "unavailable"
        self.assertFalse(self._active(c))

    def test_short_fresh_active(self):
        self.assertTrue(self._active(_card_for_staleness("short", 10, self.T0)))

    def test_short_expired_inactive(self):
        self.assertFalse(self._active(_card_for_staleness("short", 60, self.T0)))

    def test_mid_aging_active_day91(self):
        self.assertTrue(self._active(_card_for_staleness("mid", 91, self.T0)))

    def test_mid_expired_inactive_day181(self):
        self.assertFalse(self._active(_card_for_staleness("mid", 181, self.T0)))

    def test_long_always_active(self):
        self.assertTrue(self._active(_card_for_staleness("long", 999, self.T0)))

    def test_null_date_short_active(self):
        self.assertTrue(self._active(_card_for_staleness("short", None, self.T0)))

    def test_null_date_mid_active(self):
        self.assertTrue(self._active(_card_for_staleness("mid", None, self.T0)))


# ═══════════════════════════════════════════════════════════════════════════════
# Group 3 — Storage isolation (temp library root)
# ═══════════════════════════════════════════════════════════════════════════════
class TestStorage(unittest.TestCase):
    def setUp(self):
        os.environ.pop("THESIS_LIBRARY_ROOT", None)  # ensure no external override
        self._tmp = tempfile.TemporaryDirectory()
        store.set_library_root(self._tmp.name)

    def tearDown(self):
        store.set_library_root(None)
        self._tmp.cleanup()

    def test_root_is_temp(self):
        self.assertEqual(store.get_library_root(), Path(self._tmp.name))

    def test_round_trip(self):
        card = valid_card()
        store.save_card(card)
        loaded = store.load_card(card["card_id"])
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded, card)

    def test_load_missing_returns_none(self):
        self.assertIsNone(store.load_card("nope-1"))

    def test_overwrite_false_raises(self):
        card = valid_card()
        store.save_card(card)
        with self.assertRaises(store.CardExistsError):
            store.save_card(card, overwrite=False)

    def test_overwrite_true_succeeds(self):
        card = valid_card()
        store.save_card(card)
        card["card_status"] = "silenced"
        store.save_card(card, overwrite=True)
        self.assertEqual(store.load_card(card["card_id"])["card_status"], "silenced")

    def test_ingest_log_parseable(self):
        entry = {"doc_hash": _doc_hash(), "card_id": "x-1",
                 "timestamp": "2026-06-01T00:00:00", "action": "created"}
        store.append_ingest_log(entry)
        log_path = Path(self._tmp.name) / "ingest_log.jsonl"
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), entry)

    def test_ingest_log_invalid_action_rejected(self):
        with self.assertRaises(ValueError):
            store.append_ingest_log({"doc_hash": "h", "card_id": "c",
                                     "timestamp": "t", "action": "frobnicated"})

    def test_check_existing_by_hash(self):
        h = _doc_hash()
        self.assertIsNone(store.check_existing_by_hash(h))
        store.append_ingest_log({"doc_hash": h, "card_id": "h16-1",
                                 "timestamp": "2026-06-01T00:00:00", "action": "created"})
        found = store.check_existing_by_hash(h)
        self.assertIsNotNone(found)
        self.assertEqual(found["card_id"], "h16-1")

    def test_check_existing_ignores_duplicate_skipped(self):
        h = _doc_hash(b"only-skip")
        store.append_ingest_log({"doc_hash": h, "card_id": "z-1",
                                 "timestamp": "t", "action": "duplicate_skipped"})
        self.assertIsNone(store.check_existing_by_hash(h))

    def test_check_existing_returns_most_recent(self):
        h = _doc_hash(b"multi")
        store.append_ingest_log({"doc_hash": h, "card_id": "m-1",
                                 "timestamp": "t1", "action": "created"})
        store.append_ingest_log({"doc_hash": h, "card_id": "m-1",
                                 "timestamp": "t2", "action": "overwritten"})
        self.assertEqual(store.check_existing_by_hash(h)["action"], "overwritten")

    def test_delete_card(self):
        card = valid_card()
        store.save_card(card)
        self.assertIsNotNone(store.load_card(card["card_id"]))
        store.delete_card(card["card_id"])
        self.assertIsNone(store.load_card(card["card_id"]))

    def test_list_cards(self):
        store.save_card(valid_card(b"a"))
        store.save_card(valid_card(b"b"))
        self.assertEqual(len(store.list_cards()), 2)

    def test_list_cards_skips_corrupt(self):
        store.save_card(valid_card(b"good"))
        bad = Path(self._tmp.name) / "cards" / "broken-1.json"
        bad.write_text("{ not json", encoding="utf-8")
        self.assertEqual(len(store.list_cards()), 1)

    def test_scan_unavailable_identifies_missing(self):
        present_file = Path(self._tmp.name) / "present.txt"
        present_file.write_text("hi", encoding="utf-8")
        c_present = valid_card(b"present")
        c_present["source"]["doc_path"] = str(present_file)
        c_missing = valid_card(b"missing")
        c_missing["source"]["doc_path"] = str(Path(self._tmp.name) / "gone.txt")
        c_nopath = valid_card(b"nopath")  # doc_path == "" -> skipped
        missing = store.scan_unavailable([c_present, c_missing, c_nopath])
        self.assertIn(c_missing["card_id"], missing)
        self.assertNotIn(c_present["card_id"], missing)
        self.assertNotIn(c_nopath["card_id"], missing)

    def test_update_card_status_valid(self):
        card = valid_card()
        store.save_card(card)
        store.update_card_status(card["card_id"], "silenced")
        self.assertEqual(store.load_card(card["card_id"])["card_status"], "silenced")

    def test_update_card_status_invalid_raises(self):
        card = valid_card()
        store.save_card(card)
        with self.assertRaises(ValueError):
            store.update_card_status(card["card_id"], "archived")

    def test_backup_folder_config_persists(self):
        store.set_backup_folder("/tmp/some/folder")
        self.assertEqual(store.get_backup_folder(), "/tmp/some/folder")
        cfg = Path(self._tmp.name) / "config.json"
        self.assertTrue(cfg.exists())


# ═══════════════════════════════════════════════════════════════════════════════
# Group 4 — Isolation invariants (negative guards)
# ═══════════════════════════════════════════════════════════════════════════════
class TestIsolationInvariants(unittest.TestCase):
    GUARDED = [
        "lib.opportunity_ranker",
        "lib.signal_engine",
        "lib.candidate_generator",
        "lib.market_internals",
    ]

    def _assert_no_thesis_reference(self, modname):
        mod = importlib.import_module(modname)
        # (a) no attribute name references the thesis feature
        for name in dir(mod):
            self.assertNotIn("thesis_library", name.lower(),
                             f"{modname}.{name} references thesis_library")
            self.assertNotIn("thesis_ingestion", name.lower(),
                             f"{modname}.{name} references thesis_ingestion")
        # (b) no attribute *value* is a thesis submodule
        for name in dir(mod):
            val = getattr(mod, name)
            if isinstance(val, types.ModuleType):
                nm = getattr(val, "__name__", "").lower()
                self.assertNotIn("thesis_ingestion", nm,
                                 f"{modname}.{name} is the thesis_ingestion module")
        # (c) the source file does not import the thesis feature
        src_file = getattr(mod, "__file__", None)
        if src_file and os.path.exists(src_file):
            src = Path(src_file).read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("thesis_ingestion", src,
                             f"{modname} source imports thesis_ingestion")
            self.assertNotIn("thesis_library", src,
                             f"{modname} source references thesis_library")

    def test_opportunity_ranker_isolated(self):
        self._assert_no_thesis_reference("lib.opportunity_ranker")

    def test_signal_engine_isolated(self):
        self._assert_no_thesis_reference("lib.signal_engine")

    def test_candidate_generator_isolated(self):
        self._assert_no_thesis_reference("lib.candidate_generator")

    def test_market_internals_isolated(self):
        self._assert_no_thesis_reference("lib.market_internals")

    def _dir_signature(self, p: Path):
        """A stable signature of a directory's files + sizes (or None if absent)."""
        if not p.exists():
            return None
        return sorted((f.name, f.stat().st_size) for f in p.iterdir() if f.is_file())

    def test_save_card_does_not_touch_snapshots_or_anchor_cache(self):
        # Redirect the library root into a temp dir, then prove a save_card()
        # leaves the real data/ artifacts (if present) byte-for-byte unchanged.
        snapshots = _REPO_ROOT / "data" / "snapshots"
        anchor_cache = _REPO_ROOT / "data" / "anchor_cache.json"

        snap_before = self._dir_signature(snapshots)
        anchor_before = anchor_cache.read_bytes() if anchor_cache.exists() else None

        os.environ.pop("THESIS_LIBRARY_ROOT", None)
        with tempfile.TemporaryDirectory() as tmp:
            store.set_library_root(tmp)
            try:
                store.save_card(valid_card(b"isolation-probe"))
                store.append_ingest_log({
                    "doc_hash": _doc_hash(b"isolation-probe"),
                    "card_id": store.card_id_from_hash(_doc_hash(b"isolation-probe"), 1),
                    "timestamp": "2026-06-01T00:00:00", "action": "created",
                })
            finally:
                store.set_library_root(None)

        snap_after = self._dir_signature(snapshots)
        anchor_after = anchor_cache.read_bytes() if anchor_cache.exists() else None

        self.assertEqual(snap_before, snap_after, "save_card mutated data/snapshots/")
        self.assertEqual(anchor_before, anchor_after, "save_card mutated data/anchor_cache.json")
        # The temp library dir is gone, confirming writes were redirected there.
        self.assertFalse(Path(tmp).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
