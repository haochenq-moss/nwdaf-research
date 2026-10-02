from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Collection

from nwdaf_research.input_testing.records import (
    InputCase,
    RunLabel,
    TestOutcome,
    read_jsonl,
    validate_campaign,
)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def materialize_input_test_runs(
    campaign_dir: str | Path,
    *,
    run_ids: Collection[str] | None = None,
) -> list[Path]:
    """Create NWDAF run bundles from one before/after snapshot pair per input run.

    Only measured Linux snapshots become `linux/events.jsonl` samples. SBI/PFCP
    rolling log-tail counts remain in `live_observations.jsonl`; they are not
    misrepresented as per-message event streams.
    """
    campaign = Path(campaign_dir)
    cases = read_jsonl(campaign / "input_cases.jsonl", InputCase)
    outcomes = read_jsonl(campaign / "outcomes.jsonl", TestOutcome)
    labels = read_jsonl(campaign / "run_labels.jsonl", RunLabel)
    validate_campaign(cases, outcomes, labels)
    case_by_id = {case.input_id: case for case in cases}
    labels_by_run = {label.run_id: label for label in labels}
    outcomes_by_run: dict[str, list[TestOutcome]] = {}
    for outcome in outcomes:
        outcomes_by_run.setdefault(outcome.run_id, []).append(outcome)

    snapshots_path = campaign / "live_observations.jsonl"
    if not snapshots_path.exists():
        raise FileNotFoundError(f"Live observation file not found: {snapshots_path}")
    snapshots: list[dict[str, Any]] = []
    with snapshots_path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Malformed snapshot JSON at line {line_number}") from error
            snapshots.append(row)

    runs_root = campaign / "runs"
    selected_run_ids = set(run_ids) if run_ids is not None else None
    output_paths: list[Path] = []
    for run_id, label in labels_by_run.items():
        if selected_run_ids is not None and run_id not in selected_run_ids:
            continue
        if label.label != "input_test":
            continue
        run_outcomes = outcomes_by_run.get(run_id, [])
        if len(run_outcomes) != 1:
            raise ValueError(f"expected exactly one recorded input outcome for run {run_id}")
        outcome = run_outcomes[0]
        case = case_by_id[outcome.input_id]
        linked_snapshots = [
            row for row in snapshots
            if row.get("run_id") == run_id and row.get("input_id") == outcome.input_id
        ]
        before_rows = [row for row in linked_snapshots if row.get("phase") == "before"]
        after_rows = [row for row in linked_snapshots if row.get("phase") == "after"]
        if len(before_rows) != 1 or len(after_rows) != 1:
            raise ValueError(
                f"run {run_id} needs exactly one before and one after snapshot for {outcome.input_id}"
            )
        before, after = before_rows[0], after_rows[0]
        if not (_timestamp(before["observed_at"]) <= _timestamp(outcome.window_start)):
            raise ValueError(f"test window starts before the before-snapshot for run {run_id}")
        if not (_timestamp(outcome.window_end) <= _timestamp(after["observed_at"])):
            raise ValueError(f"test window ends after the after-snapshot for run {run_id}")

        run_dir = runs_root / run_id
        if run_dir.exists():
            raise FileExistsError(f"refusing to overwrite existing run directory: {run_dir}")
        linux_dir = run_dir / "linux"
        linux_dir.mkdir(parents=True)

        linux_events = []
        for index, row in enumerate((before, after)):
            features = row["features"]
            linux_events.append({
                "event_id": f"{run_id}-host-{index}",
                "run_id": run_id,
                "source": "linux",
                "event_type": "host_sample",
                "event_time": row["observed_at"],
                "collection_time": row["observed_at"],
                "host_id": row["host"],
                "load_1m": float(features["linux_load_1m_mean"]),
                "memory_bytes": {
                    "total": float(features["linux_memory_total_mean"]),
                    "available": float(features["linux_memory_available_mean"]),
                },
            })

        (linux_dir / "events.jsonl").write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in linux_events),
            encoding="utf-8",
        )
        (run_dir / "live_observations.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in (before, after)),
            encoding="utf-8",
        )

        t0 = before["observed_at"]
        t1 = outcome.window_start
        t2 = outcome.window_end
        t4 = after["observed_at"]
        duration_seconds = (_timestamp(t4) - _timestamp(t0)).total_seconds()
        _write_json(run_dir / "metadata.json", {
            "run_id": run_id,
            "scenario_id": "NRF_DISCOVERY_INPUT_TEST",
            "load_profile": "uncontrolled_live_lab",
            "created_at": t0,
            "duration_sec": duration_seconds,
            "host_id": before["host"],
            "status": "complete",
            "provenance": {
                "collector_version": "nwdaf-live-snapshot-v1",
                "free5gc_commit": case.free5gc_commit,
                "input_id": case.input_id,
                "input_sha256": case.input_sha256,
                "auth_context": case.auth_context,
            },
            "telemetry_notes": {
                "linux": "two timestamped host snapshots",
                "sbi": "rolling log-tail summary only; no event stream",
                "pfcp": "rolling log-tail summary only; no event stream",
                "ue_namespace": "unavailable to non-interactive observer",
            },
        })
        _write_json(run_dir / "ground_truth.json", {
            "run_id": run_id,
            "scenario_id": "NRF_DISCOVERY_INPUT_TEST",
            "anomalous": False,
            "security": False,
            "class": "input_test",
            "severity": "none",
            "attack_phase": "not_applicable",
            "service_impact": "none",
            "action": None,
        })
        _write_json(run_dir / "timeline.json", {
            "run_id": run_id,
            "timeline": {"T0": t0, "T1": t1, "T2": t2, "T3": t2, "T4": t4},
        })
        output_paths.append(run_dir)
    return output_paths