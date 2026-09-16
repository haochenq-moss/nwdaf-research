import tempfile
import unittest
from pathlib import Path

from nwdaf_research.api.persistence import APIState


class APIStateTests(unittest.TestCase):
    def test_subscriptions_and_decisions_survive_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            first = APIState(path)
            first.save_subscription("sub-1", {"subscriptionId": "sub-1", "analyticsId": "a"})
            self.assertTrue(first.claim_decision("dec-1"))
            second = APIState(path)
            self.assertEqual(second.subscriptions()[0][0], "sub-1")
            self.assertFalse(second.claim_decision("dec-1"))


if __name__ == "__main__":
    unittest.main()