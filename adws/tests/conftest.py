"""Isolated verification fixtures. Only temporary artifacts and loopback HTTP."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADWS = ROOT / "adws"
sys.path.insert(0, str(ADWS))


@dataclass
class Lab:
    root: Path
    env: dict[str, str]

    @property
    def db(self):
        return self.root / "adw.db"

    @property
    def registry(self):
        return self.root / "registry.json"

    def invoke(self, argv, *, expected=None):
        result = subprocess.run(
            [sys.executable, *map(str, argv)], cwd=ROOT, env=self.env,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25,
        )
        print(f"COMMAND: python {' '.join(map(str, argv))}\nEXIT: {result.returncode}")
        print(result.stdout + result.stderr)
        if expected is not None:
            assert result.returncode == expected, result.stdout + result.stderr
        return result

    def build(self, request="adws/fixtures/requests/toy_complete.md", *, run_id="verify", extra=(), wrapper=None):
        argv = [ADWS / "adw_workflow_builder.py", "--request", request,
                "--fixtures", "--stub-agents", "--db", self.db,
                "--reports-dir", self.root / "reports", "--run-id", run_id, *extra]
        if wrapper:
            argv = ["-c", wrapper, *argv[1:]]
        return self.invoke(argv)

    def entry(self):
        record = json.loads(self.registry.read_text())["workflows"][0]
        return self.root / "built" / record["id"] / Path(record["entrypoint"]).name


@pytest.fixture(autouse=True)
def restore_sockets_and_remove_credentials(monkeypatch):
    # The existing core socket test mutates module globals. Restore them per test.
    connect = socket.socket.connect
    def loopback_only(sock, address):
        if isinstance(address, tuple):
            assert address[0] in {"127.0.0.1", "localhost", "::1"}, "external network forbidden"
        return connect(sock, address)
    monkeypatch.setattr(socket.socket, "connect", loopback_only)
    monkeypatch.setattr(socket, "create_connection", socket.create_connection)
    for key in list(os.environ):
        if any(term in key.upper() for term in ("API_KEY", "AUTH_TOKEN", "ACCESS_TOKEN", "BEARER_TOKEN")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    guard = tmp_path / "network_guard"
    guard.mkdir()
    attempts = tmp_path / "socket-attempts.txt"
    (guard / "sitecustomize.py").write_text('''import socket, os
from pathlib import Path
_original = socket.socket
class NoNetworkSocket(_original):
    def __init__(self, family=socket.AF_INET, *args, **kwargs):
        if family in (socket.AF_INET, socket.AF_INET6):
            with Path(os.environ["VERIFY_SOCKET_ATTEMPTS"]).open("a") as f:
                f.write("network socket attempted\\n")
            raise RuntimeError("verification forbids every INET socket")
        super().__init__(family, *args, **kwargs)
socket.socket = NoNetworkSocket
''')
    values = {
        "ADW_BUILT_ROOT": str(tmp_path / "built"),
        "ADW_REGISTRY_PATH": str(tmp_path / "registry.json"),
        "ADW_DB": str(tmp_path / "adw.db"),
        "ADW_QUEUE_DIR": str(tmp_path / "queue"),
        "ADW_LAUNCH_DB": str(tmp_path / "launches.db"),
        "ADW_LAUNCH_REPORTS": str(tmp_path / "launches"),
        "ADW_PROMPTS_DIR": str(ADWS / "prompts"),
        "ADW_FIXTURES_DIR": str(ADWS / "fixtures"),
        "ADW_PYTHON": sys.executable,
        "PI_OFFLINE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(guard),
        "VERIFY_SOCKET_ATTEMPTS": str(attempts),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    yield Lab(tmp_path, dict(os.environ))
    assert not attempts.exists(), "a stub subprocess attempted to create an INET socket"


@pytest.fixture
def accepted(lab):
    result = lab.build()
    assert result.returncode == 0, result.stdout + result.stderr
    return lab
