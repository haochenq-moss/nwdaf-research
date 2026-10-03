import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from nwdaf_research.live.telemetry_window import COUNTER_SOURCES, TelemetryWindow


class WindowIngestionTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "ingest_telemetry_window.py"
        spec = importlib.util.spec_from_file_location("ingest_telemetry_window", path)
        assert spec is not None and spec.loader is not None
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)

    def records(self):
        rows = []
        sources = sorted(set(COUNTER_SOURCES.values()))
        for second in range(3):
            timestamp = f"2026-10-03T00:00:0{second}Z"
            counters = {name: 0 for name in COUNTER_SOURCES}
            counters["linux_event_count"] = second
            rows.append({
                "type": "snapshot", "observed_at": timestamp, "counters": counters,
                "linux_sample": {"load_1m": 0.1, "memory_total": 100, "memory_available": 40},
                "collectors": {source: {
                    "heartbeat_at": timestamp, "collector_healthy": True,
                    "telemetry_source_synced": True, "observed_through": timestamp,
                } for source in sources},
            })
        rows.append({"type": "seal", "observed_at": "2026-10-03T00:00:02Z"})
        return rows

    def run_cli(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshots.jsonl"
            content = "".join(json.dumps(row) + "\n" for row in rows)
            path.write_text(content, encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                exit_code = self.cli.main([
                    "--snapshots", str(path), "--window-start", "2026-10-03T00:00:00Z",
                    "--as-of", "2026-10-03T00:00:02Z", "--duration-sec", "2",
                    "--heartbeat-timeout-sec", "1",
                ])
            self.assertEqual(path.read_text(encoding="utf-8"), content)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            return exit_code, json.loads(output.getvalue())

    def test_ready_cli_is_read_only(self):
        exit_code, report = self.run_cli(self.records())
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "READY")
        self.assertEqual([entry["status"] for entry in report["lifecycle"]], ["ACCUMULATING", "READY"])
        self.assertFalse(report["actionable"])

    def test_unsealed_cli_accumulates(self):
        exit_code, report = self.run_cli(self.records()[:-1])
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "ACCUMULATING")

    def test_missing_handshake_cli_returns_unavailable(self):
        rows = self.records()
        del rows[1]["collectors"]["pfcp"]
        exit_code, report = self.run_cli(rows)
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "COLLECTOR_UNAVAILABLE")
        self.assertEqual(report["features"], {})

    def test_malformed_record_reports_line_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text("[]\n", encoding="utf-8")
            window = TelemetryWindow("2026-10-03T00:00:00Z")
            with self.assertRaisesRegex(ValueError, "line 1"):
                self.cli.ingest_records(path, window)

    def test_duplicate_seal_rejected(self):
        rows = self.records()
        rows.append(rows[-1])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate seal"):
                self.cli.ingest_records(path, TelemetryWindow("2026-10-03T00:00:00Z", duration_sec=2))