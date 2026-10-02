#!/usr/bin/env python3
"""Capture one read-only free5GC telemetry snapshot for an input-test run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nwdaf_research.input_testing.live_capture import capture_live_observation
from nwdaf_research.live.ssh_observer import SSHLiveObserver


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--input-id", required=True)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2222)
    parser.add_argument("--user", default="haochenqin-moss")
    parser.add_argument("--identity-file", default="~/.ssh/id_ecdsa")
    arguments = parser.parse_args()

    observation = capture_live_observation(
        observer=SSHLiveObserver(
            host=arguments.host,
            port=arguments.port,
            user=arguments.user,
            identity_file=arguments.identity_file,
        ),
        run_id=arguments.run_id,
        input_id=arguments.input_id,
        phase=arguments.phase,
        output_path=arguments.output,
    )
    print(json.dumps(observation, indent=2))


if __name__ == "__main__":
    main()