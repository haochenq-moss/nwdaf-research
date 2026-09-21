import unittest
from pathlib import Path

from nwdaf_research.models.temporal_gru import TemporalGRUClassifier


class TemporalGRUTests(unittest.TestCase):
    def test_temporal_backend_is_explicitly_optional(self):
        self.assertIsInstance(TemporalGRUClassifier.available(), bool)

    def test_linux_sequence_shape(self):
        import json
        from tempfile import TemporaryDirectory

        from nwdaf_research.models.temporal_gru import linux_event_sequence

        with TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "linux").mkdir()
            (run / "linux" / "events.jsonl").write_text(
                json.dumps({"load_1m": 1.0, "memory_bytes": {"total": 10, "available": 5}}) + "\n"
            )
            sequence = linux_event_sequence(str(run), max_length=4)
            self.assertEqual(sequence.shape, (4, 3))


if __name__ == "__main__":
    unittest.main()