from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nwdaf_research.analytics.baseline import BaselineAnomalyModel


class ResearchAgent:
    """A downstream agent that summarizes validated analytics outputs without inventing runtime facts."""

    def __init__(self, raw_root: str | Path):
        self.raw_root = Path(raw_root)
        self.model = BaselineAnomalyModel(self.raw_root)

    def generate_summary(self) -> dict[str, Any]:
        metrics = self.model.train_and_evaluate()
        ablation = self.model.evaluate_feature_ablation()
        summary = {
            "status": "offline_analytics_validated",
            "metrics": {
                "baseline": metrics,
                "ablation": ablation,
            },
            "recommendation": "Keep the full verified feature set as the working baseline and defer any live runtime or agent integration until this offline pipeline is revalidated.",
        }
        return summary
