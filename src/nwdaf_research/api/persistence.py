from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class APIState:
    """Small SQLite state store for subscriptions and mitigation replay IDs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS subscriptions (subscription_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY)")
            connection.commit()

    def save_subscription(self, subscription_id: str, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO subscriptions(subscription_id, payload) VALUES (?, ?)",
                (subscription_id, json.dumps(payload)),
            )
            connection.commit()

    def subscriptions(self) -> list[tuple[str, dict[str, Any]]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute("SELECT subscription_id, payload FROM subscriptions ORDER BY subscription_id").fetchall()
        return [(subscription_id, json.loads(payload)) for subscription_id, payload in rows]

    def claim_decision(self, decision_id: str) -> bool:
        try:
            with sqlite3.connect(self.path) as connection:
                connection.execute("INSERT INTO decisions(decision_id) VALUES (?)", (decision_id,))
                connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False