from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from pathlib import Path
import json


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    source: str
    event_time: str
    run_id: str | None
    nf: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class CorrelatedWindow:
    window_id: str
    start: str
    end: str
    events: tuple[NormalizedEvent, ...]
    context: dict[str, Any]


class DCCF:
    """Prototype data-collection/correlation boundary, not a 3GPP service claim."""

    def normalize(
        self,
        events: Iterable[dict[str, Any]],
        *,
        source: str,
        run_id: str | None = None,
        nf: str | None = None,
    ) -> list[NormalizedEvent]:
        normalized: list[NormalizedEvent] = []
        for index, event in enumerate(events):
            normalized.append(
                NormalizedEvent(
                    event_id=str(event.get("event_id") or f"{source}-{index}"),
                    source=source,
                    event_time=str(event.get("event_time") or datetime.now(timezone.utc).isoformat()),
                    run_id=event.get("run_id") or run_id,
                    nf=event.get("nf_type") or event.get("nf") or nf,
                    payload=dict(event),
                )
            )
        return normalized

    def correlate(
        self,
        events: Iterable[NormalizedEvent],
        *,
        window_id: str,
        start: str,
        end: str,
        context: dict[str, Any] | None = None,
    ) -> CorrelatedWindow:
        return CorrelatedWindow(
            window_id=window_id,
            start=start,
            end=end,
            events=tuple(events),
            context=context or {},
        )

    def collect_run(self, run_dir: str | Path, *, run_id: str | None = None) -> CorrelatedWindow:
        """Collect and correlate all available event streams from one run directory."""
        root = Path(run_dir)
        run_id = run_id or root.name
        events: list[NormalizedEvent] = []
        for source in ("linux", "sbi", "pfcp", "free5gc"):
            path = root / source / "events.jsonl"
            if not path.exists():
                continue
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            events.extend(self.normalize(rows, source=source, run_id=run_id))
        timeline_path = root / "timeline.json"
        timeline = json.loads(timeline_path.read_text(encoding="utf-8")) if timeline_path.exists() else {}
        marks = timeline.get("timeline", {}) if isinstance(timeline, dict) else {}
        return self.correlate(
            events,
            window_id=run_id,
            start=str(marks.get("T0", "unknown")),
            end=str(marks.get("T4", "unknown")),
            context={"run_id": run_id, "sources": sorted({event.source for event in events})},
        )