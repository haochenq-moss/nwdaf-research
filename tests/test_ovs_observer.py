import unittest
from unittest.mock import patch

from nwdaf_research.live.ovs_observer import OVSObserver


class OVSObserverTests(unittest.TestCase):
    @patch("nwdaf_research.live.ovs_observer.shutil.which", return_value=None)
    def test_reports_unavailable_without_ovs(self, _which):
        result = OVSObserver().observe()
        self.assertEqual(result.status, "unavailable")


if __name__ == "__main__":
    unittest.main()