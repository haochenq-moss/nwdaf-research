#!/usr/bin/env python3
"""Prepare hash-bound pending review evidence or validate a separately supplied analyst decision."""

import argparse
import json
from pathlib import Path

from nwdaf_research.live.analyst_review import REVIEW_CHECKS, prepare_pair_review, validate_analyst_decision


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-dir", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--output-dir", type=Path, help="Create a NEW directory with pending packet and unsigned decision draft")
    modes.add_argument("--decision", type=Path, help="Validate an existing external decision; never modify acquisition labels")
    args = parser.parse_args(argv)
    try:
        if args.decision:
            report = validate_analyst_decision(args.pair_dir, json.loads(args.decision.read_text(encoding="utf-8")))
        else:
            packet = prepare_pair_review(args.pair_dir)
            report = {
                "pair_id": packet["pair_id"], "review_status": packet["review_status"],
                "packet_binding_sha256": packet["packet_binding_sha256"],
                "parser_provenance": packet["parser_provenance"],
                "artifact_count": len(packet["artifact_sha256"]), "model_approved": False,
            }
            if args.output_dir:
                if args.pair_dir.resolve() == args.output_dir.resolve() or args.pair_dir.resolve() in args.output_dir.resolve().parents:
                    raise ValueError("review output must be separate from acquisition evidence")
                args.output_dir.mkdir(parents=True, exist_ok=False)
                draft = {
                    "schema_version": "benign-pair-analyst-decision-v1",
                    "packet_binding_sha256": packet["packet_binding_sha256"],
                    "reviewer_id": "", "reviewed_at": None, "independence_declared": False,
                    "decision": "inconclusive", "rationale": "",
                    "checks": dict.fromkeys(REVIEW_CHECKS, False),
                }
                for name, document in (("review_packet.json", packet), ("analyst_decision.draft.json", draft)):
                    with (args.output_dir / name).open("x", encoding="utf-8") as stream:
                        json.dump(document, stream, indent=2, sort_keys=True, allow_nan=False)
                        stream.write("\n")
                report["output_dir"] = str(args.output_dir)
        print(json.dumps(report, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()