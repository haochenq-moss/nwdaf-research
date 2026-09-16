import unittest
from pathlib import Path

from nwdaf_research.agent import ResearchAgent
from nwdaf_research.nemoir import NEMOIRNarrative


class Phase6AgentTests(unittest.TestCase):
    def setUp(self):
        self.raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"

    def test_research_agent_generates_grounded_summary(self):
        agent = ResearchAgent(self.raw_root)
        summary = agent.generate_summary()
        self.assertIn("status", summary)
        self.assertIn("metrics", summary)
        self.assertIn("recommendation", summary)
        self.assertIn("baseline", summary["metrics"])

    def test_nemoir_narrative_generates_evidence_based_summary(self):
        narrative = NEMOIRNarrative(self.raw_root)
        report = narrative.generate_report()
        self.assertIn("summary", report)
        self.assertIn("evidence", report)
        self.assertIn("next_step", report)
        self.assertTrue(report["summary"])


if __name__ == "__main__":
    unittest.main()
