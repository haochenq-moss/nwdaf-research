import tempfile
import unittest
from pathlib import Path

from nwdaf_research.live.runtime_socket_observer import RuntimeSocketObserver


class RuntimeSocketObserverTests(unittest.TestCase):
    def test_reports_socket_metadata_without_opening_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.sock"
            path.write_text("fixture", encoding="utf-8")
            result = RuntimeSocketObserver((str(path),)).observe()
            self.assertEqual(result.status, "measured")
            self.assertFalse(result.evidence["opened_socket"])
            self.assertEqual(result.sockets[0]["path"], str(path))


if __name__ == "__main__":
    unittest.main()