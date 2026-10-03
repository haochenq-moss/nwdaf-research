from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nwdaf_research.live.passive_campaign import run_campaign


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded read-only baseline capture; no inference or generated traffic.")
    parser.add_argument("--campaign-dir", required=True)
    parser.add_argument("--window-count", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--duration-sec", type=int, choices=range(2, 11), default=10)
    options = parser.parse_args(argv)
    try:
        summary = run_campaign(options.campaign_dir, window_count=options.window_count, duration_sec=options.duration_sec)
    except Exception as error:
        print(json.dumps({"status": "CAPTURE_FAILED", "blockers": [type(error).__name__]}))
        return 2
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())