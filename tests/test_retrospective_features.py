import json
import tempfile
import unittest
from pathlib import Path

from nwdaf_research.input_testing.retrospective_features import _nanoseconds, build_partial_features


class RetrospectiveFeatureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "recovery.json"
        self.report = {
            "schema_version": "retrospective-nas-log-recovery-v1", "collection_mode": "retrospective_log_extraction",
            "run_id": "fixture", "input_sha256": "a" * 64, "source_log_sha256": "b" * 64,
            "window_start": "2026-10-02T12:58:34.634928027Z", "window_end": "2026-10-02T12:58:41.040804795Z",
            "counts": {"during/sbi": 1}, "events": [{
                "event_time": "2026-10-02T12:58:35Z", "event_time_ns": _nanoseconds("2026-10-02T12:58:35Z"),
                "phase": "during", "source_line": 1, "source": "sbi", "http_status": 404,
            }],
        }

    def write(self):
        self.path.write_text(json.dumps(self.report))

    def test_recovered_fields_do_not_fill_missing_linux_or_health(self):
        self.write()
        result = build_partial_features(self.path)
        self.assertEqual(len(result["feature_values"]), 16)
        self.assertEqual(result["available_field_count"], 6)
        self.assertEqual(result["missing_field_count"], 10)
        self.assertAlmostEqual(result["feature_values"]["duration_sec"], 6.405876768, places=9)
        self.assertEqual(result["feature_values"]["sbi_error_event_count"], 1)
        self.assertIsNone(result["feature_values"]["linux_event_count"])
        self.assertIsNone(result["feature_values"]["pfcp_telemetry_available"])
        self.assertFalse(result["training_ready"])

    def test_modified_counts_or_phase_are_rejected(self):
        for change in ("count", "phase"):
            with self.subTest(change=change):
                if change == "count":
                    self.report["counts"] = {"during/sbi": 999}
                else:
                    self.report["counts"] = {"during/sbi": 1}
                    self.report["events"][0]["phase"] = "after"
                self.write()
                with self.assertRaises(ValueError):
                    build_partial_features(self.path)

    def test_duplicate_log_events_cannot_inflate_counts(self):
        self.report["events"].append(dict(self.report["events"][0]))
        self.report["counts"] = {"during/sbi": 2}
        self.write()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_partial_features(self.path)