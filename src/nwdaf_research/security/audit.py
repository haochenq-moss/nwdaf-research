from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    """Append structured request and decision events to an optional JSONL file."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else None
        self.events: list[dict[str, Any]] = []

    def record(self, event: dict[str, Any]) -> dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        self.events.append(entry)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry