import json
import stat
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import api
import install


SID = "a" * 64
TELEMETRY = {"used": 250, "window": 1000, "soft": 200, "warning": 350, "force": 400, "level": "soft"}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state" / "sessions.sqlite"
        self.token = self.root / "config" / "token"
        self.server = api.make_server(port=0, state=self.state, token_file=self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def call(self, route, payload=None, authorized=True):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer " + api.token(self.token)
        request = urllib.request.Request(self.url + route, body, headers,
                                         method="POST" if payload is not None else "GET")
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.load(response)

    def test_auth_queue_and_result(self):
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.call("/v1/sessions", authorized=False)
        self.assertEqual(denied.exception.code, 401)
        denied.exception.close()
        self.assertTrue(self.call(f"/v1/sessions/{SID}", TELEMETRY)["ok"])
        self.assertEqual(self.call("/v1/sessions")["sessions"][0]["used"], 250)
        self.assertTrue(self.call(f"/v1/sessions/{SID}/compact", {})["ok"])
        self.assertTrue(self.call(f"/v1/sessions/{SID}/claim", {})["compact"])
        self.assertFalse(self.call(f"/v1/sessions/{SID}/claim", {})["compact"])
        self.call(f"/v1/sessions/{SID}/result", {"status": "completed"})
        self.assertEqual(self.call(f"/v1/sessions/{SID}")["session"]["result"], "completed")
        self.assertEqual(stat.S_IMODE(self.token.stat().st_mode), 0o600)

    def test_rejects_content_and_invalid_telemetry(self):
        for payload in ({**TELEMETRY, "prompt": "secret"}, {**TELEMETRY, "used": "many"},
                        {**TELEMETRY, "force": 1100}):
            with self.subTest(payload=payload), self.assertRaises(urllib.error.HTTPError) as bad:
                self.call(f"/v1/sessions/{SID}", payload)
            self.assertEqual(bad.exception.code, 400)
            bad.exception.close()
        self.assertEqual(self.call("/v1/sessions")["sessions"], [])
        self.assertNotIn(b"secret", self.state.read_bytes())

    def test_installer_adds_one_global_entry_without_changing_other_settings(self):
        settings = self.root / "settings.json"
        settings.write_text('{"packages":["existing"],"extensions":["other.ts"]}')
        extension = self.root / "self-compact.ts"
        self.assertTrue(install.install_pi_settings(settings, extension))
        self.assertFalse(install.install_pi_settings(settings, extension))
        data = json.loads(settings.read_text())
        self.assertEqual(data["packages"], ["existing"])
        self.assertEqual(data["extensions"], ["other.ts", str(extension)])


if __name__ == "__main__":
    unittest.main()
