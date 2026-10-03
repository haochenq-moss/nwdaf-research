import importlib.util
import unittest
from pathlib import Path


class RetrospectiveRecoveryTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "scripts/recover_rnas0001_logs.py"
        spec = importlib.util.spec_from_file_location("recovery", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.remote = {"__name__": "test_fixture"}
        exec(compile(module.REMOTE, "recovery_remote", "exec"), self.remote)

    def test_nanosecond_boundaries_are_not_rounded_to_microseconds(self):
        parse = self.remote["timestamp_ns"]
        self.assertEqual(parse("2026-10-02T20:58:34.634928027+08:00") - parse("2026-10-02T12:58:34.634928000Z"), 27)

    def test_sanitization_and_context_phases(self):
        parse = self.remote["timestamp_ns"]
        payload = b'\n'.join([
            b'time="2026-10-02T12:58:34Z" msg="SCTP shutdown SECRET" CAT="SCTP" NF="AMF"',
            b'time="2026-10-02T12:58:35Z" msg="| 404 | private-ip | GET | /subscriber-secret | key | SECRET" CAT="GIN" NF="UDR"',
            b'time="2026-10-02T12:58:42Z" msg="handleHeartbeatRequest SECRET" CAT="PFCP" NF="UPF"',
        ])
        rows, counts, malformed = self.remote["extract"](payload, parse("2026-10-02T12:58:34.634928027Z"), parse("2026-10-02T12:58:41.040804795Z"))
        self.assertEqual([row["phase"] for row in rows], ["before", "during", "after"])
        self.assertEqual(rows[1]["http_status"], 404)
        self.assertEqual(counts["during/sbi"], 1)
        self.assertNotIn("SECRET", str(rows))
        self.assertNotIn("subscriber-secret", str(rows))
        self.assertEqual(malformed, 0)