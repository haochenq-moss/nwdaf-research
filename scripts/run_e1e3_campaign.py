#!/usr/bin/env python3
"""Local orchestration driver for the E1-E3 fresh-campaign matrix.

This script never modifies the remote research repository. It only builds the
scenario/load/seed/repetition matrix from configs/campaign_e1e3.yaml, and, when
explicitly requested, invokes the existing unmodified remote
``research.controller.experiment_controller`` module once per cell over SSH.

Safety:
- Default mode is --dry-run: prints the planned matrix and the exact remote
  commands without opening any SSH connection or touching the testbed.
- Real execution requires both --execute and the environment variable
  NWDAF_CAMPAIGN_CONFIRM=I_UNDERSTAND, to avoid an accidental invocation of
  real (bounded, reversible) scenario stimuli on shared infrastructure.
- Cells run strictly sequentially. A failed cell is recorded as invalid and
  the batch continues; it does not retry or overwrite a completed run.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "campaign_e1e3.yaml"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_config(path):
    with Path(path).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def build_matrix(config):
    scenarios = config["scenarios"]
    repetitions = config["repetitions_per_cell"]
    matrix = []
    for partition_name, partition in config["partitions"].items():
        seed_base = partition["seed_base"]
        for scenario_index, scenario in enumerate(scenarios):
            seed = seed_base + scenario_index
            for repetition_index in range(repetitions):
                matrix.append({
                    "campaign_id": config["campaign_id"],
                    "partition": partition_name,
                    "scenario": scenario,
                    "seed": seed,
                    "repetition_index": repetition_index,
                    "load_profile": config["run_defaults"]["load_profile"],
                })
    return matrix


def remote_command(config, cell):
    defaults = config["run_defaults"]
    remote = config["remote"]
    args = [
        "python3", "-m", "research.controller.experiment_controller",
        "--scenario", cell["scenario"],
        "--load", cell["load_profile"],
        "--seed", str(cell["seed"]),
        "--duration", str(defaults["duration_sec"]),
        "--baseline", str(defaults["baseline_sec"]),
        "--output", remote["output_root"],
        "--config", remote["testbed_config"],
        "--traffic-profiles", remote["traffic_profiles"],
        "--traffic-target", defaults["traffic_target"],
    ]
    if defaults.get("require_baseline"):
        args.append("--require-baseline")
    inner = "cd {} && {}".format(remote["repo_root"], " ".join(args))
    ssh = config["ssh"]
    return [
        "ssh", "-T", "-p", str(ssh["port"]),
        "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
        "{}@{}".format(ssh["user"], ssh["host"]),
        inner,
    ]


def run_cell(config, cell, manifest_entries):
    command = remote_command(config, cell)
    started = utc_now()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as error:
        manifest_entries.append({**cell, "started_at": started, "finished_at": utc_now(),
                                  "status": "timeout", "error": str(error)})
        return
    finished = utc_now()
    if result.returncode != 0:
        manifest_entries.append({**cell, "started_at": started, "finished_at": finished,
                                  "status": "failed", "exit_code": result.returncode,
                                  "stderr_tail": result.stderr[-2000:]})
        return
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as error:
        manifest_entries.append({**cell, "started_at": started, "finished_at": finished,
                                  "status": "unparseable_output", "error": str(error),
                                  "stdout_tail": result.stdout[-2000:]})
        return
    manifest_entries.append({**cell, "started_at": started, "finished_at": finished,
                              "status": "ok", "remote_run_id": payload.get("run_id"),
                              "remote_path": payload.get("path"),
                              "remote_status": payload.get("status")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true",
                         help="Actually run the matrix over SSH. Requires NWDAF_CAMPAIGN_CONFIRM=I_UNDERSTAND.")
    parser.add_argument("--manifest-out", type=Path, default=None,
                         help="Local path to write the execution manifest JSON (only used with --execute).")
    args = parser.parse_args()

    config = load_config(args.config)
    matrix = build_matrix(config)

    if not args.execute:
        print(json.dumps({
            "mode": "dry_run",
            "campaign_id": config["campaign_id"],
            "cell_count": len(matrix),
            "matrix": matrix,
            "example_command": " ".join(remote_command(config, matrix[0])) if matrix else None,
        }, indent=2))
        return 0

    if os.environ.get("NWDAF_CAMPAIGN_CONFIRM") != "I_UNDERSTAND":
        print("Refusing to execute: set NWDAF_CAMPAIGN_CONFIRM=I_UNDERSTAND to confirm "
              "you have verified preconditions in configs/campaign_e1e3.yaml.", file=sys.stderr)
        return 2

    manifest_entries = []
    for cell in matrix:
        run_cell(config, cell, manifest_entries)

    manifest_path = args.manifest_out or (
        REPO_ROOT / "data" / "processed" / "{}_manifest.json".format(config["campaign_id"])
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "campaign_id": config["campaign_id"],
        "generated_at": utc_now(),
        "entries": manifest_entries,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Wrote manifest: {}".format(manifest_path))
    failed = [entry for entry in manifest_entries if entry["status"] != "ok"]
    if failed:
        print("{} of {} cells did not complete successfully.".format(len(failed), len(manifest_entries)),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
