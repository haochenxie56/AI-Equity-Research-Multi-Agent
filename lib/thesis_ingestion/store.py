"""Thesis Ingestion — storage layer.

Local JSON card storage, append-only ingest log, deterministic staleness /
active computation, and card-status management for the Thesis Card Library.

Storage layout (under the *library root*)::

    data/thesis_library/
    ├── cards/
    │   └── <card_id>.json     # one file per card, write-once after confirmation
    ├── ingest_log.jsonl       # append-only: one JSON line per ingest event
    └── config.json            # UI settings (e.g. thesis_backup_folder)

The library root defaults to ``<repo>/data/thesis_library`` but is overridable
via :func:`set_library_root` (used by the reliability test suite to redirect all
writes into a ``tempfile.TemporaryDirectory``) or the ``THESIS_LIBRARY_ROOT``
environment variable. This keeps every public function signature exactly as the
spec defines while still allowing fully isolated, ``data/``-free tests.

This module performs **only local filesystem I/O** — no network, and no import
of any scoring / ranking / snapshot / anchor module. All staleness/active math
is deterministic and computed at read time (never stored on the card).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path

_log = logging.getLogger("thesis_ingestion.store")

# Repo root = lib/thesis_ingestion/store.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_ROOT = _REPO_ROOT / "data" / "thesis_library"

# Process-level override (set via set_library_root); env var takes precedence.
_library_root: Path | None = None


class CardExistsError(Exception):
    """Raised when save_card() would overwrite an existing card without consent."""


# ── Library-root resolution ──────────────────────────────────────────────────
def set_library_root(path) -> None:
    """Redirect all thesis-library I/O to *path* (test isolation hook)."""
    global _library_root
    _library_root = Path(path) if path is not None else None


def get_library_root() -> Path:
    """Resolve the active library root: env var > process override > default."""
    env = os.environ.get("THESIS_LIBRARY_ROOT")
    if env:
        return Path(env)
    if _library_root is not None:
        return _library_root
    return DEFAULT_LIBRARY_ROOT


def _cards_dir() -> Path:
    return get_library_root() / "cards"


def _ingest_log_path() -> Path:
    return get_library_root() / "ingest_log.jsonl"


def _config_path() -> Path:
    return get_library_root() / "config.json"


def _card_path(card_id: str) -> Path:
    return _cards_dir() / f"{card_id}.json"


def _ensure_dirs() -> None:
    _cards_dir().mkdir(parents=True, exist_ok=True)


# ── Hashing / IDs ────────────────────────────────────────────────────────────
def compute_doc_hash(file_bytes: bytes) -> str:
    """sha256 of the raw file bytes, hex digest (the deduplication key)."""
    return hashlib.sha256(file_bytes).hexdigest()


def card_id_from_hash(doc_hash: str, seq: int) -> str:
    """First 16 chars of doc_hash + "-" + str(seq)."""
    return f"{doc_hash[:16]}-{seq}"


# ── Card read / write ────────────────────────────────────────────────────────
def load_card(card_id: str) -> dict | None:
    """Read and parse ``cards/<card_id>.json``. Return None if not found."""
    path = _card_path(card_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001 — corrupt file behaves as missing
        _log.warning("load_card(%s): failed to parse (%s)", card_id, exc)
        return None


def save_card(card: dict, overwrite: bool = False) -> None:
    """Write *card* to ``cards/<card_id>.json`` using an atomic temp-then-rename.

    Raises :class:`CardExistsError` if the file exists and ``overwrite`` is
    False. With ``overwrite=True`` an existing file is replaced silently.
    """
    card_id = card.get("card_id")
    if not card_id:
        raise ValueError("save_card: card is missing 'card_id'")
    _ensure_dirs()
    path = _card_path(card_id)
    if path.exists() and not overwrite:
        raise CardExistsError(f"card already exists: {card_id}")
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(card, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # atomic on POSIX & Windows


def delete_card(card_id: str) -> None:
    """Delete ``cards/<card_id>.json`` (user action on an unavailable card)."""
    path = _card_path(card_id)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def list_cards() -> list[dict]:
    """Return all parsed card dicts; skip (and warn on) any file that fails."""
    cards: list[dict] = []
    cdir = _cards_dir()
    if not cdir.exists():
        return cards
    for path in sorted(cdir.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as fh:
                cards.append(json.load(fh))
        except Exception as exc:  # noqa: BLE001
            _log.warning("list_cards: skipping unparseable %s (%s)", path.name, exc)
    return cards


# ── Ingest log ───────────────────────────────────────────────────────────────
_INGEST_ACTIONS = ("created", "overwritten", "duplicate_skipped")


def append_ingest_log(entry: dict) -> None:
    """Append one JSON line to ``ingest_log.jsonl``.

    Entry must include ``doc_hash``, ``card_id``, ``timestamp`` and ``action``
    (one of created / overwritten / duplicate_skipped).
    """
    missing = [k for k in ("doc_hash", "card_id", "timestamp", "action") if k not in entry]
    if missing:
        raise ValueError(f"append_ingest_log: entry missing keys {missing}")
    if entry["action"] not in _INGEST_ACTIONS:
        raise ValueError(f"append_ingest_log: invalid action {entry['action']!r}")
    _ensure_dirs()
    with _ingest_log_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def check_existing_by_hash(doc_hash: str) -> dict | None:
    """Most recent ingest-log entry for *doc_hash* with a 'live' action.

    Scans ``ingest_log.jsonl`` and returns the last entry whose ``doc_hash``
    matches and whose ``action`` is in ``["created", "overwritten"]`` (a
    ``duplicate_skipped`` event does not create a card, so it is ignored).
    Returns None if there is no such entry.
    """
    path = _ingest_log_path()
    if not path.exists():
        return None
    found: dict | None = None
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001 — skip corrupt lines
                    continue
                if rec.get("doc_hash") == doc_hash and rec.get("action") in (
                    "created", "overwritten",
                ):
                    found = rec  # keep scanning → last match wins (most recent)
    except Exception as exc:  # noqa: BLE001
        _log.warning("check_existing_by_hash: read error (%s)", exc)
        return None
    return found


# ── Status management / availability scan ────────────────────────────────────
def scan_unavailable(cards: list[dict]) -> list[str]:
    """Return card_ids whose ``source.doc_path`` no longer exists on disk.

    Does NOT modify any card — the caller decides whether to flip status.
    Cards with an empty/missing doc_path are skipped (nothing to verify).
    """
    missing: list[str] = []
    for card in cards:
        doc_path = (card.get("source") or {}).get("doc_path") or ""
        if not doc_path:
            continue
        if not Path(doc_path).exists():
            cid = card.get("card_id")
            if cid:
                missing.append(cid)
    return missing


def update_card_status(card_id: str, new_status: str) -> None:
    """Load the card, set ``card_status`` and re-save (overwrite).

    Valid values: active | silenced | unavailable. Raises ValueError otherwise.
    """
    if new_status not in ("active", "silenced", "unavailable"):
        raise ValueError(f"update_card_status: invalid status {new_status!r}")
    card = load_card(card_id)
    if card is None:
        raise ValueError(f"update_card_status: card not found {card_id!r}")
    card["card_status"] = new_status
    save_card(card, overwrite=True)


# ── Config (backup folder etc.) ──────────────────────────────────────────────
def load_config() -> dict:
    """Read ``config.json`` (returns {} if absent / unparseable)."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        _log.warning("load_config: failed to parse (%s)", exc)
        return {}


def save_config(config: dict) -> None:
    """Persist *config* to ``config.json`` atomically."""
    _ensure_dirs()
    path = _config_path()
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_backup_folder() -> str:
    """Read the persisted ``thesis_backup_folder`` setting (default "")."""
    return str(load_config().get("thesis_backup_folder", "") or "")


def set_backup_folder(folder: str) -> None:
    """Persist the ``thesis_backup_folder`` setting."""
    cfg = load_config()
    cfg["thesis_backup_folder"] = folder or ""
    save_config(cfg)


# ── Deterministic staleness / active computation (read-time, never stored) ────
# Day thresholds per horizon.
_SHORT_FRESH_MAX = 30      # short: fresh <= 30, expired > 30
_MID_FRESH_MAX = 90        # mid: fresh <= 90 (no warning)
_MID_AGING_MAX = 180       # mid: aging 91-180 (warning), expired > 180


def _parse_pub_date(card: dict):
    """Return a ``date`` from ``source.publication_date`` or None."""
    raw = (card.get("source") or {}).get("publication_date")
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001 — unparseable date behaves as null
        return None


def compute_staleness(card: dict, *, today: date | None = None) -> dict:
    """Deterministic staleness classification at read time (never stored).

    Returns ``{"tier", "days_since_publication", "show_aging_warning"}``.

    Rules:
      * short:  fresh <= 30 days, expired > 30 days.
      * mid:    fresh <= 90 (no warning), aging 91-180 (warning), expired > 180.
      * long:   tier always "not_applicable", warning always False.
      * null publication_date: "not_applicable" for all horizon types.
    """
    today = today or date.today()
    horizon = card.get("horizon_type")
    pub = _parse_pub_date(card)

    if horizon == "long" or pub is None:
        return {
            "tier": "not_applicable",
            "days_since_publication": None if pub is None else (today - pub).days,
            "show_aging_warning": False,
        }

    days = (today - pub).days

    if horizon == "short":
        tier = "fresh" if days <= _SHORT_FRESH_MAX else "expired"
        return {"tier": tier, "days_since_publication": days,
                "show_aging_warning": False}

    if horizon == "mid":
        if days <= _MID_FRESH_MAX:
            tier, warn = "fresh", False
        elif days <= _MID_AGING_MAX:
            tier, warn = "aging", True
        else:
            tier, warn = "expired", False
        return {"tier": tier, "days_since_publication": days,
                "show_aging_warning": warn}

    # Unknown horizon → treat as not applicable (fail-closed, never crash).
    return {"tier": "not_applicable", "days_since_publication": days,
            "show_aging_warning": False}


def compute_is_active(card: dict, staleness: dict) -> bool:
    """Deterministic active flag from card_status + staleness.

    Rules:
      * card_status in [silenced, unavailable] -> False immediately.
      * publication_date null (short/mid) -> treat as not_applicable -> True
        (a card is not deactivated merely because its date is unknown).
      * short: active iff staleness tier == "fresh".
      * mid:   active iff staleness tier != "expired" (logic falsification is
               always False in the MVP).
      * long:  active always.
    """
    if card.get("card_status") in ("silenced", "unavailable"):
        return False

    horizon = card.get("horizon_type")
    pub = _parse_pub_date(card)

    # Null-date override: never deactivate solely for an unknown date.
    if pub is None:
        return True

    tier = staleness.get("tier")
    if horizon == "short":
        return tier == "fresh"
    if horizon == "mid":
        return tier != "expired"
    if horizon == "long":
        return True
    # Unknown horizon → fail-closed to active (it has content, date is known).
    return True


__all__ = [
    "CardExistsError",
    "set_library_root",
    "get_library_root",
    "compute_doc_hash",
    "card_id_from_hash",
    "load_card",
    "save_card",
    "delete_card",
    "list_cards",
    "append_ingest_log",
    "check_existing_by_hash",
    "scan_unavailable",
    "update_card_status",
    "load_config",
    "save_config",
    "get_backup_folder",
    "set_backup_folder",
    "compute_staleness",
    "compute_is_active",
]
