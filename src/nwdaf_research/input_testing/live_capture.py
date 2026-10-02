from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nwdaf_research.live.ssh_observer import SSHLiveObserver


def capture_live_observation(
    *,
    observer: SSHLiveObserver,
    run_id: str,
    input_id: str,
    phase: str,
    output_path: str | Path,
) -> dict[str, Any]:
    """Append one read-only live snapshot linked to a campaign input and run."""
    if not run_id.strip() or not input_id.strip():
        raise ValueError("run_id and input_id must not be empty")
    if phase not in {"before", "after"}:
        raise ValueError("phase must be 'before' or 'after'")

    observation = observer.observe()
    record = {
        "run_id": run_id,
        "input_id": input_id,
        "phase": phase,
        "observed_at": observation.observed_at,
        "host": observation.host,
        "features": observation.features,
        "evidence": observation.evidence,
        "unavailable_features": observation.unavailable_features,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8", newline="\n") as destination:
        destination.write(json.dumps(record, sort_keys=True) + "\n")
    return record