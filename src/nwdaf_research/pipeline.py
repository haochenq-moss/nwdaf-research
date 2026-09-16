from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nwdaf_research.analytics.nwdaf import NWDAFResearchAnalyzer


class NWDAFPipeline:
    """Research pipeline that scores every verified run using the anomaly baseline."""

    def __init__(self, raw_root: str | Path):
        self.raw_root = Path(raw_root)
        self.analyzer = NWDAFResearchAnalyzer(self.raw_root)

    def run(self, output_path: str | Path | None = None) -> dict[str, Any]:
        scores = self.analyzer.batch_score_runs()
        summary = {
            "run_count": len(scores),
            "scores": scores,
            "baseline_metrics": self.analyzer.evaluate(),
        }

        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        return summary
