from __future__ import annotations

import argparse
import json

from nwdaf_research.live.benign_control import run_pair


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect one authorized frozen-plan control pair without inference.")
    parser.add_argument("--execute-benign", action="store_true")
    parser.add_argument("--pair-id", type=int, choices=range(1, 13), required=True)
    parser.add_argument("--authorization", help="Required scoped JSON permission for held-out pairs")
    parser.add_argument("--pair-dir", required=True)
    parser.add_argument("--registered-nf-instance-id", required=True)
    args = parser.parse_args(argv)
    if not args.execute_benign:
        parser.error("--execute-benign is required; no action was taken")
    try:
        summary = run_pair(args.pair_dir, pair_id=args.pair_id,
            registered_nf_instance_id=args.registered_nf_instance_id, execute_benign=args.execute_benign,
            authorization_path=args.authorization)
    except Exception as error:
        print(json.dumps({"status": "INCOMPLETE", "error_type": type(error).__name__}))
        return 1
    if args.pair_id >= 5:
        print(json.dumps({
            "pair_id": args.pair_id, "split": "held_out", "status": summary["status"],
            "pair_dir": args.pair_dir, "authorization_sha256": summary["authorization_sha256"],
            "inference_performed": False, "results_withheld": True,
            "collection_status": {condition: row["status"] for condition, row in summary["outcomes"].items()},
        }, allow_nan=False))
    else:
        print(json.dumps(summary, allow_nan=False))
    return 0 if summary["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())