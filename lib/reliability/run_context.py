import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RunContext:
    run_id: str
    ticker: str
    task: str
    run_dir: Path
    created_at: str


def create_run_context(
    ticker: str | None = None,
    task: str | None = None,
    base_dir: str = "research/runs",
) -> RunContext:
    ticker_part = (ticker or "GENERAL").upper()
    now = datetime.now(timezone.utc)
    short_uuid = uuid.uuid4().hex[:8]
    run_id = f"{ticker_part}_{now.strftime('%Y%m%d_%H%M%S')}_{short_uuid}"
    run_dir = Path(base_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=run_id,
        ticker=ticker_part,
        task=task or "",
        run_dir=run_dir,
        created_at=now.isoformat(),
    )
