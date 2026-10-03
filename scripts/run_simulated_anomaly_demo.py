#!/usr/bin/env python3
"""Standalone offline demonstration with synthetic non-NAS inputs and no live actions."""

import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nwdaf_research.input_testing.anomaly_dataset import FEATURES, evaluate_anomaly_dataset
from nwdaf_research.input_testing.protocol_evidence import STAGES
from nwdaf_research.live.telemetry_window import BASELINE_CONTRACT, TelemetryWindow


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def reference(root, name, value):
    data = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True) + "\n").encode()
    (root / name).write_bytes(data)
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest()}


def run_demo(output: Path, *, seed: int = 42) -> dict:
    if output.exists():
        raise FileExistsError("refusing to overwrite demo directory")
    output.mkdir(parents=True)
    rng = random.Random(seed)
    plan = {
        "schema_version": "fuzz-anomaly-analysis-plan-v1", "contract": BASELINE_CONTRACT,
        "feature_names": list(FEATURES), "model": "random_forest_200_seed42", "threshold": 0.5,
        "frozen": True, "frozen_at": "2030-01-02T00:00:00Z", "simulation_only": True,
        "timestamp_basis": "Virtual test clock, not actual collection time",
        "collection_semantics": "observation_time_cursor_reads_excluding_preexisting_history",
    }
    write_json(output / "plan.json", plan)
    entries = []
    for split, per_class, day in (("train", 12, 1), ("held_out", 6, 3)):
        for label in ("normal", "expected_rejection", "anomalous"):
            for index in range(per_class):
                identity = f"sim-{split}-{label}-{index:02d}"
                root = output / identity
                root.mkdir()
                start = datetime(2030, 1, day, tzinfo=timezone.utc) + timedelta(minutes=len(entries))
                end = start + timedelta(seconds=10)
                input_ref = reference(root, "input.bin", f"SYNTHETIC NON-NAS SCENARIO {identity}".encode())
                observation = reference(root, "observation.json", {
                    "simulation_only": True, "scenario_label": label,
                    "source": "generator, not a real software failure or network measurement",
                })
                manifest = {
                    "schema_version": "fuzz-case-evidence-v1", "simulation_only": True,
                    "input_id": identity, "run_id": identity, "free5gc_commit": "0" * 40,
                    "revision_basis": "Simulation placeholder, not tested free5GC revision",
                    "window_start": start.isoformat(), "window_end": end.isoformat(),
                    "input": input_ref, "stages": {},
                }
                window = TelemetryWindow(start, duration_sec=10, contract=BASELINE_CONTRACT)
                counters = dict.fromkeys(window.counter_sources, 0)
                samples = []
                base_load = rng.uniform(0.2, 1.2) if label != "anomalous" else rng.uniform(2.0, 5.0)
                for offset in range(11):
                    timestamp = (start + timedelta(seconds=offset)).isoformat()
                    if offset:
                        counters["linux_event_count"] += 1
                        sbi_count = rng.randint(0, 2 if label == "normal" else 4)
                        counters["sbi_event_count"] += sbi_count
                        counters["sbi_error_event_count"] += (0 if label == "normal" else rng.randint(0, sbi_count))
                        pfcp_count = rng.randint(0, 1)
                        counters["pfcp_event_count"] += pfcp_count
                        counters["pfcp_request_count"] += pfcp_count
                    total = 2 * 1024 ** 3
                    fraction = rng.uniform(0.40, 0.65) if label != "anomalous" else rng.uniform(0.08, 0.28)
                    samples.append({
                        "type": "snapshot", "simulation_only": True,
                        "run_id": identity, "input_sha256": input_ref["sha256"],
                        "observed_at": timestamp, "counters": dict(counters),
                        "linux_sample": {"load_1m": max(0, base_load + rng.uniform(-0.1, 0.1)),
                                         "memory_total": total, "memory_available": int(total * fraction)},
                        "collectors": {source: {"heartbeat_at": timestamp, "observed_through": timestamp,
                                                "collector_healthy": True, "telemetry_source_synced": True}
                                       for source in window.primary_sources},
                    })
                samples.append({"type": "seal", "simulation_only": True, "run_id": identity,
                                "input_sha256": input_ref["sha256"], "observed_at": end.isoformat()})
                snapshot_ref = reference(root, "snapshots.jsonl", b"".join(json.dumps(row).encode() + b"\n" for row in samples))
                for stage in STAGES:
                    record = {
                        "simulation_only": True, "input_id": identity, "run_id": identity,
                        "free5gc_commit": "0" * 40, "input_sha256": input_ref["sha256"],
                        "window_start": start.isoformat(), "window_end": end.isoformat(),
                        "observed_outcome": "SIMULATED: " + label, "evidence_refs": [observation],
                        "reviewer_id": "simulated-review-placeholder-not-a-person",
                        "reviewed_at": (end + timedelta(seconds=1)).isoformat(), "decision": "approved",
                        "rationale": "Mock decision for plumbing demonstration only; not a human approval",
                    }
                    if stage == "telemetry_bundle":
                        record.update(contract=BASELINE_CONTRACT, snapshots_ref=snapshot_ref,
                                      evidence_refs=[observation, snapshot_ref],
                                      clock_domain="simulated-host/virtual-boot/CLOCK_MONOTONIC",
                                      collection_semantics=plan["collection_semantics"])
                    if stage == "analyst_decision":
                        record.update(outcome_label=label, label_basis="synthetic_generator_scenario", independence_declared=False)
                    manifest["stages"][stage] = reference(root, stage + ".json", record)
                write_json(root / "case_evidence.json", manifest)
                entries.append({"bundle_path": identity, "split": split, "unseen_declared": split == "held_out",
                                "input_family": identity, "episode_group": identity})
    write_json(output / "dataset.json", {
        "schema_version": "fuzz-anomaly-dataset-v1", "simulation_only": True,
        "analysis_plan_sha256": hashlib.sha256((output / "plan.json").read_bytes()).hexdigest(), "runs": entries,
    })
    results = evaluate_anomaly_dataset(output / "dataset.json", output / "plan.json", allow_simulation=True)
    write_json(output / "results.json", results)
    alerts = [{"run_id": row["run_id"], "simulation_only": True, "status": "SIMULATED_REVIEW_REQUIRED",
               "anomaly_probability": row["anomaly_probability"], "network_action": "NONE", "actionable": False}
              for row in results["held_out_predictions"] if row["predicted_anomalous"]]
    write_json(output / "simulated_alerts.json", alerts)
    summary = {"simulation_only": True, "research_result": False, "seed": seed,
               "train_runs": results["training_run_count"], "held_out_runs": results["held_out_run_count"],
               "feature_count": len(FEATURES), "metrics": results["metrics"], "alert_count": len(alerts),
               "real_nas_data_modified": False, "live_actions_executed": False,
               "conclusion": "Offline pipeline demonstration only; easy generator-defined separation is not measured security efficacy."}
    write_json(output / "demo_summary.json", summary)
    (output / "README.md").write_text(
        "# SIMULATION ONLY\n\nGenerated non-NAS inputs, virtual clocks, simulated collectors and mock review decisions.\n"
        "No real free5GC behavior, independent review or live detection is demonstrated.\n"
        "Do not merge with historical research data or publish the scores as research findings.\n",
        encoding="utf-8",
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(run_demo(args.output_dir, seed=args.seed), indent=2))


if __name__ == "__main__":
    main()