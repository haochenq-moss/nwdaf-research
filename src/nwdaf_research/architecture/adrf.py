from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class ADRFStore:
    """Durable analytics/evidence store; not a standardized 3GPP ADRF service."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS analytics_records (record_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.commit()

    def put(self, record_id: str, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO analytics_records(record_id, payload) VALUES (?, ?)",
                (record_id, json.dumps(payload)),
            )
            connection.commit()

    def get(self, record_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT payload FROM analytics_records WHERE record_id = ?", (record_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, record_type: str | None = None) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute("SELECT record_id, payload FROM analytics_records ORDER BY record_id").fetchall()
        records = [{"record_id": record_id, **json.loads(payload)} for record_id, payload in rows]
        if record_type is not None:
            records = [record for record in records if record.get("type") == record_type]
        return records