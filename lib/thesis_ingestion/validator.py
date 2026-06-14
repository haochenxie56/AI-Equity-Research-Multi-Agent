"""Thesis Ingestion — deterministic post-extraction validation.

``validate_card(raw)`` enforces every structural / provenance / invariant rule
on a freshly-extracted card BEFORE it may be saved. It is pure and deterministic
(no I/O, no network, no LLM). Each failing check appends a message to the error
list **without short-circuiting**, so the UI can surface every problem at once.

The validator is the firewall behind the project's numeric-honesty rule: it
rejects any card where a numeric claim lacks provenance, where an
``unspecified_numerics`` entry smuggles in a ``value``, or where the
``current_evidence_status`` / ``evidence_refs`` invariants have been tampered.
"""

from __future__ import annotations

# Enumerations (local copies so the validator is self-contained / importable in
# the test harness without pulling schema's TypedDict machinery).
CARD_STATUS_VALID = {"active", "silenced", "unavailable"}
HORIZON_VALID = {"short", "mid", "long"}
PROVENANCE_VALID = {"stated_by_author", "inferred"}
OBSERVABLE_VALID = {"machine_checkable", "human_judgment", "unspecified"}
DOC_TYPE_VALID = {"interview", "research_report", "article", "transcript", "other"}
LANGUAGE_VALID = {"zh", "en", "mixed"}
COI_STATUS_VALID = {"coi_unassessed", "coi_disclosed"}


def _nonempty_str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def validate_card(raw: dict) -> tuple[bool, list[str]]:
    """Validate an extracted thesis card.

    Returns ``(is_valid, errors)``. When ``is_valid`` is False the card must not
    be saved. Error messages are prefixed with a stable error code so callers /
    tests can assert on the code regardless of the human-readable suffix.
    """
    errors: list[str] = []

    if not isinstance(raw, dict):
        return False, ["invalid_card_not_a_dict: card must be a JSON object"]

    source = raw.get("source") or {}
    if not isinstance(source, dict):
        source = {}
        errors.append("invalid_source: source must be an object")

    # ── card_status ──
    if raw.get("card_status") not in CARD_STATUS_VALID:
        errors.append(
            f"invalid_card_status: {raw.get('card_status')!r} not in {sorted(CARD_STATUS_VALID)}"
        )

    # ── horizon_type ──
    if raw.get("horizon_type") not in HORIZON_VALID:
        errors.append(
            f"invalid_horizon_type: {raw.get('horizon_type')!r} not in {sorted(HORIZON_VALID)}"
        )

    # ── source.doc_type ──
    if source.get("doc_type") not in DOC_TYPE_VALID:
        errors.append(
            f"invalid_doc_type: {source.get('doc_type')!r} not in {sorted(DOC_TYPE_VALID)}"
        )

    # ── source.language ──
    if source.get("language") not in LANGUAGE_VALID:
        errors.append(
            f"invalid_language: {source.get('language')!r} not in {sorted(LANGUAGE_VALID)}"
        )

    # ── current_evidence_status invariant ──
    if raw.get("current_evidence_status", "unknown") != "unknown":
        # Default to "unknown" if absent (the field lives on scenarios in the
        # schema, but guard the top level too in case a flat card is passed).
        errors.append(
            f"evidence_status_tampered: current_evidence_status must be 'unknown', "
            f"got {raw.get('current_evidence_status')!r}"
        )

    # ── evidence_refs invariant ──
    if "evidence_refs" in raw and raw.get("evidence_refs") != []:
        errors.append(
            f"evidence_refs_tampered: evidence_refs must be an empty list, "
            f"got {raw.get('evidence_refs')!r}"
        )

    # ── coi.status ──
    coi = raw.get("coi") or {}
    if not isinstance(coi, dict) or coi.get("status") not in COI_STATUS_VALID:
        errors.append(
            f"invalid_coi_status: {(coi or {}).get('status')!r} not in {sorted(COI_STATUS_VALID)}"
        )

    # ── numeric_claims: value + provenance ──
    numeric_claims = raw.get("numeric_claims") or []
    if not isinstance(numeric_claims, list):
        errors.append("invalid_numeric_claims: numeric_claims must be a list")
        numeric_claims = []
    for i, nc in enumerate(numeric_claims):
        if not isinstance(nc, dict):
            errors.append(f"invalid_numeric_claim: numeric_claims[{i}] must be an object")
            continue
        if nc.get("value") is None:
            errors.append(
                f"extraction_rejected_missing_provenance: numeric_claims[{i}] has null value"
            )
        prov = nc.get("provenance")
        if not _nonempty_str(prov):
            errors.append(
                f"extraction_rejected_missing_provenance: numeric_claims[{i}] missing provenance"
            )
        elif prov not in PROVENANCE_VALID:
            errors.append(
                f"invalid_provenance: numeric_claims[{i}] provenance {prov!r} "
                f"not in {sorted(PROVENANCE_VALID)}"
            )

    # ── unspecified_numerics: must NOT carry a value ──
    unspecified = raw.get("unspecified_numerics") or []
    if not isinstance(unspecified, list):
        errors.append("invalid_unspecified_numerics: unspecified_numerics must be a list")
        unspecified = []
    for i, un in enumerate(unspecified):
        if isinstance(un, dict) and "value" in un:
            errors.append(
                f"extraction_rejected_fabricated_numeric: unspecified_numerics[{i}] "
                f"must not contain a 'value' key"
            )

    # ── transmission_chain (lives on each scenario) ──
    scenarios = raw.get("scenarios") or []
    if not isinstance(scenarios, list):
        errors.append("invalid_scenarios: scenarios must be a list")
        scenarios = []
    for si, sc in enumerate(scenarios):
        if not isinstance(sc, dict):
            errors.append(f"invalid_scenario: scenarios[{si}] must be an object")
            continue
        chain = sc.get("transmission_chain") or []
        for ci, step in enumerate(chain if isinstance(chain, list) else []):
            if not isinstance(step, dict):
                errors.append(
                    f"invalid_transmission_step: scenarios[{si}].transmission_chain[{ci}] "
                    f"must be an object"
                )
                continue
            if not _nonempty_str(step.get("from_node")):
                errors.append(
                    f"invalid_transmission_step: scenarios[{si}].transmission_chain[{ci}] "
                    f"missing from_node"
                )
            if not _nonempty_str(step.get("to_node")):
                errors.append(
                    f"invalid_transmission_step: scenarios[{si}].transmission_chain[{ci}] "
                    f"missing to_node"
                )
            if not _nonempty_str(step.get("mechanism")):
                errors.append(
                    f"invalid_transmission_step: scenarios[{si}].transmission_chain[{ci}] "
                    f"missing mechanism"
                )
            if step.get("provenance") not in PROVENANCE_VALID:
                errors.append(
                    f"invalid_transmission_step: scenarios[{si}].transmission_chain[{ci}] "
                    f"provenance {step.get('provenance')!r} not in {sorted(PROVENANCE_VALID)}"
                )

        # confirmation / falsification conditions: observable + provenance
        for field in ("confirmation_conditions", "falsification_conditions"):
            conds = sc.get(field) or []
            for ki, cond in enumerate(conds if isinstance(conds, list) else []):
                if not isinstance(cond, dict):
                    errors.append(
                        f"invalid_condition: scenarios[{si}].{field}[{ki}] must be an object"
                    )
                    continue
                if cond.get("observable") not in OBSERVABLE_VALID:
                    errors.append(
                        f"invalid_condition: scenarios[{si}].{field}[{ki}] observable "
                        f"{cond.get('observable')!r} not in {sorted(OBSERVABLE_VALID)}"
                    )
                if cond.get("provenance") not in PROVENANCE_VALID:
                    errors.append(
                        f"invalid_condition: scenarios[{si}].{field}[{ki}] provenance "
                        f"{cond.get('provenance')!r} not in {sorted(PROVENANCE_VALID)}"
                    )

        # scenario-level invariants
        if sc.get("current_evidence_status", "unknown") != "unknown":
            errors.append(
                f"evidence_status_tampered: scenarios[{si}].current_evidence_status "
                f"must be 'unknown', got {sc.get('current_evidence_status')!r}"
            )
        if "evidence_refs" in sc and sc.get("evidence_refs") != []:
            errors.append(
                f"evidence_refs_tampered: scenarios[{si}].evidence_refs must be an empty list, "
                f"got {sc.get('evidence_refs')!r}"
            )

    # ── doc_hash: non-empty sha256 hex (length 64) ──
    doc_hash = source.get("doc_hash")
    if not (isinstance(doc_hash, str) and len(doc_hash) == 64):
        errors.append(
            f"invalid_doc_hash: source.doc_hash must be a 64-char sha256 hex string, "
            f"got {doc_hash!r}"
        )

    # ── card_id must start with first 16 chars of doc_hash ──
    card_id = raw.get("card_id")
    if isinstance(doc_hash, str) and len(doc_hash) >= 16:
        if not (isinstance(card_id, str) and card_id.startswith(doc_hash[:16])):
            errors.append(
                f"invalid_card_id: card_id {card_id!r} must start with "
                f"doc_hash[:16] ({doc_hash[:16]!r})"
            )
    elif not _nonempty_str(card_id):
        errors.append("invalid_card_id: card_id must be a non-empty string")

    # ── core_claims: bilingual text required ──
    core_claims = raw.get("core_claims") or []
    if not isinstance(core_claims, list):
        errors.append("invalid_core_claims: core_claims must be a list")
        core_claims = []
    for i, cc in enumerate(core_claims):
        if not isinstance(cc, dict):
            errors.append(f"invalid_core_claim: core_claims[{i}] must be an object")
            continue
        if not _nonempty_str(cc.get("claim_text_en")):
            errors.append(f"invalid_core_claim: core_claims[{i}] missing claim_text_en")
        if not _nonempty_str(cc.get("claim_text_zh")):
            errors.append(f"invalid_core_claim: core_claims[{i}] missing claim_text_zh")

    # ── extraction_meta.prompt_version ──
    meta = raw.get("extraction_meta") or {}
    if not isinstance(meta, dict) or meta.get("prompt_version") != "thesis-extract-v1":
        errors.append(
            f"invalid_prompt_version: extraction_meta.prompt_version must be "
            f"'thesis-extract-v1', got {(meta or {}).get('prompt_version')!r}"
        )

    return (len(errors) == 0), errors


__all__ = [
    "validate_card",
    "CARD_STATUS_VALID",
    "HORIZON_VALID",
    "PROVENANCE_VALID",
    "OBSERVABLE_VALID",
    "DOC_TYPE_VALID",
    "LANGUAGE_VALID",
    "COI_STATUS_VALID",
]
