import json
from datetime import datetime, timezone
from pathlib import Path

from lib.reliability.schemas import ToolResult


class EvidenceStore:
    """
    In-memory evidence map backed by an append-only tool_results.jsonl.

    On construction the store loads any records already persisted to
    tool_results.jsonl so that multiple store instances pointing at the
    same run_dir share a consistent view of which evidence IDs are taken.
    """

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = Path(run_dir)
        self._store: dict[str, ToolResult] = {}
        self._jsonl_path = self._run_dir / "tool_results.jsonl"
        self._load_existing()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_existing(self) -> None:
        if not self._jsonl_path.exists():
            return
        with self._jsonl_path.open("r", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    result = ToolResult.model_validate_json(raw)
                except Exception as exc:
                    raise ValueError(
                        f"Malformed record in {self._jsonl_path} at line {line_no}: {exc}"
                    ) from exc
                if result.evidence_id in self._store:
                    raise ValueError(
                        f"Duplicate evidence_id {result.evidence_id!r} "
                        f"found in {self._jsonl_path} at line {line_no}"
                    )
                self._store[result.evidence_id] = result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_tool_result(self, result: ToolResult) -> str:
        """Register a ToolResult and immediately append it to tool_results.jsonl."""
        if result.evidence_id in self._store:
            raise ValueError(f"Duplicate evidence_id: {result.evidence_id!r}")
        self._store[result.evidence_id] = result
        self._run_dir.mkdir(parents=True, exist_ok=True)
        with self._jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(result.model_dump_json() + "\n")
        return result.evidence_id

    def get(self, evidence_id: str) -> ToolResult | None:
        return self._store.get(evidence_id)

    def all(self) -> list[ToolResult]:
        return list(self._store.values())

    def evidence_ids(self) -> set[str]:
        return set(self._store.keys())

    def save_manifest(self) -> None:
        """Write evidence_manifest.json. tool_results.jsonl is managed by add_tool_result."""
        self._run_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": "0.1",
            "tool_results_count": len(self._store),
            "evidence_ids": sorted(self._store.keys()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "run_dir": str(self._run_dir),
        }
        manifest_path = self._run_dir / "evidence_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
