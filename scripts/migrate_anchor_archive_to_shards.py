#!/usr/bin/env python3
"""scripts/migrate_anchor_archive_to_shards.py

Anchor Intelligence v2.4 (F4 repayment) — one-time, OFFLINE migration of the legacy
single-file anchor archive (``data/anchor_archive.jsonl``) into per-ticker shards
(``data/anchor_archive/<TICKER>.jsonl``).

Why a script (not on startup): v2.4 shards the archive so a read for ticker T touches
only T's bytes (O(T's records) instead of O(total)). Reads do NOT auto-migrate — that
would reintroduce the O(total) scan this round repays. So the one existing single
file is split exactly once, by hand, exactly like ``scripts/backfill_anchors.py`` is
an explicit offline step. ``data/`` is git-ignored, so this touches no tracked file.

Properties:

* **Append-only / never mutates a prior row.** Each legacy record is written to its
  ticker's shard via :func:`lib.anchor_archive.append_record` (atomic append).
* **Idempotent.** A record already present in the shard (same ``ticker`` +
  ``computed_at`` + ``data_vintage``) is skipped, so a re-run writes ZERO duplicates.
* **Non-destructive.** The legacy file is LEFT in place; remove it manually once the
  migration is verified. (Reads no longer consult it.)
* **Semantically faithful (NOT byte-faithful).** Records are parsed (``json.loads``)
  and re-serialized (``json.dumps``) into the shard, so the on-disk BYTE representation
  may differ (JSON key order / whitespace). What IS guaranteed: every record's semantic
  fields are preserved exactly, the total record count is preserved, and the
  append-only invariant holds. The field-level fidelity + count guarantee is enforced
  by ``scripts/test_reliability_anchor_archive.py`` §9.

Usage::

    python3 -B scripts/migrate_anchor_archive_to_shards.py            # default paths
    python3 -B scripts/migrate_anchor_archive_to_shards.py --dry-run
    python3 -B scripts/migrate_anchor_archive_to_shards.py \
        --legacy-path /tmp/anchor_archive.jsonl --root /tmp/shards
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from lib import anchor_archive as aa  # noqa: E402


def _record_key(rec: dict) -> tuple:
    return (
        str(rec.get("ticker", "")).upper().strip(),
        str(rec.get("computed_at", "") or ""),
        str(rec.get("data_vintage", "") or ""),
    )


def migrate(legacy_path: Path, root: Path, *, dry_run: bool = False) -> dict:
    """Split ``legacy_path`` into per-ticker shards under ``root`` (idempotent).

    Returns a summary dict. Pure read of the legacy file + append-only shard writes;
    never mutates a prior row, never deletes the legacy file.
    """
    summary = {
        "legacy_path": str(legacy_path), "root": str(root),
        "legacy_records": 0, "written": 0, "skipped_already_present": 0,
        "tickers": 0, "dry_run": bool(dry_run),
    }
    legacy = list(aa._iter_file(legacy_path))
    summary["legacy_records"] = len(legacy)
    if not legacy:
        return summary

    # Pre-load each touched ticker's existing shard keys once (idempotency guard).
    seen_by_ticker: dict = {}
    tickers = sorted({str(r.get("ticker", "")).upper().strip()
                      for r in legacy if r.get("ticker")})
    summary["tickers"] = len(tickers)
    for tk in tickers:
        seen_by_ticker[tk] = {
            _record_key(r) for r in aa._iter_file(aa.shard_path(tk, root))
        }

    aa.reset_dedup_cache()
    for rec in legacy:
        tk = str(rec.get("ticker", "")).upper().strip()
        if not tk:
            continue
        key = _record_key(rec)
        if key in seen_by_ticker.get(tk, set()):
            summary["skipped_already_present"] += 1
            continue
        if dry_run:
            summary["written"] += 1
            seen_by_ticker.setdefault(tk, set()).add(key)
            continue
        if aa.append_record(rec, path=root):
            summary["written"] += 1
            seen_by_ticker.setdefault(tk, set()).add(key)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--legacy-path", default=str(aa.ANCHOR_ARCHIVE_PATH),
                    help="legacy single-file archive (default data/anchor_archive.jsonl)")
    ap.add_argument("--root", default=str(aa.ANCHOR_ARCHIVE_DIR),
                    help="shard root directory (default data/anchor_archive/)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report counts without writing any shard")
    args = ap.parse_args()

    legacy_path = Path(args.legacy_path)
    root = Path(args.root)
    if not legacy_path.is_file():
        print(f"No legacy archive at {legacy_path} — nothing to migrate.")
        return 0

    s = migrate(legacy_path, root, dry_run=args.dry_run)
    tag = "[dry-run] " if s["dry_run"] else ""
    print(f"{tag}anchor-archive shard migration")
    print(f"  legacy file     : {s['legacy_path']} ({s['legacy_records']} records)")
    print(f"  shard root      : {s['root']}")
    print(f"  tickers         : {s['tickers']}")
    print(f"  written         : {s['written']}")
    print(f"  already present : {s['skipped_already_present']}")
    if not s["dry_run"] and s["written"]:
        print("  (legacy file left in place — remove it manually once verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
