import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nwdaf_research.adapters.http_nf import HTTPNFAdapter
from nwdaf_research.policy.engine import PolicyEngine


class Handler(BaseHTTPRequestHandler):
    payload = None

    def do_POST(self):
        Handler.payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        body = json.dumps({"status": "accepted", "action": Handler.payload["action"]}).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


class HTTPNFAdapterTests(unittest.TestCase):
    def test_posts_policy_decision_to_agent(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            decision = PolicyEngine().evaluate(
                decision_id="http-1",
                target_nf="SMF",
                target={"supi": "imsi-1"},
                action="alert_operator",
                duration=None,
                reason="test",
                confidence=0.95,
            )
            result = HTTPNFAdapter(
                f"http://127.0.0.1:{server.server_port}", "secret"
            ).execute(decision)
            self.assertEqual(result["status"], "accepted")
            self.assertEqual(Handler.payload["decisionId"], "http-1")
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()