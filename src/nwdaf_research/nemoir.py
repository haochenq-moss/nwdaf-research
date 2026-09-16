from __future__ import annotations

from pathlib import Path
from typing import Any

from nwdaf_research.agent import ResearchAgent


class NEMOIRNarrative:
    """Downstream narrative layer that is constrained to validated analytics evidence."""

    def __init__(self, raw_root: str | Path):
        self.raw_root = Path(raw_root)
        self.agent = ResearchAgent(self.raw_root)

    def generate_report(self) -> dict[str, Any]:
        summary = self.agent.generate_summary()
        return {
            "summary": "Validated offline NWDAF-style analytics remain the strongest evidence-backed baseline.",
            "evidence": summary["metrics"],
            "next_step": "Continue with research-grade analytics documentation and hold agent/NEMOIR expansion until the verified offline pipeline is further extended.",
        }
