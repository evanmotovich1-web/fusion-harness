"""Actual loopback endpoint checks with a joined, port-0 server thread."""
from __future__ import annotations

import http.client
import importlib.util
import json
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from conftest import ADWS

spec = importlib.util.spec_from_file_location("verification_adw_desk", ADWS / "server.py")
desk_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desk_module)


@pytest.fixture
def desk(lab):
    server = ThreadingHTTPServer(("127.0.0.1", 0), desk_module.make_handler())
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=False)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive(), "server thread was not joined"


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, body=json.dumps(body) if body is not None else None,
                     headers={"Content-Type": "application/json"} if body is not None else {})
        response = conn.getresponse()
        raw = response.read().decode()
        print(f"HTTP {method} {path}: {response.status}\n{raw}")
        return response.status, raw
    finally:
        conn.close()


def test_workflows_matches_registry_without_restart(accepted, desk):
    status, raw = request(desk, "GET", "/api/workflows")
    body = json.loads(raw)
    assert status == 200
    recorded = json.loads(accepted.registry.read_text())["workflows"]
    assert len(body["workflows"]) == len(recorded)
    for served, entry in zip(body["workflows"], recorded):
        assert all(served.get(key) == value for key, value in entry.items())  # registry fields untouched
        assert served["desk_status"] in {"verified", "blocked", "incomplete"}
    assert isinstance(body.get("seats"), list) and isinstance(body.get("incomplete"), list)
    assert accepted.build(run_id="refreshed").returncode == 0
    status, refreshed = request(desk, "GET", "/api/workflows")
    body = json.loads(refreshed)
    assert body["workflows"][0]["build_run_id"] == "refreshed"
    assert body["workflows"][0]["desk_status"] == "verified"


def test_desk_status_labels_come_from_real_data(lab, accepted, desk):
    # verified: the accepted build's registry entry
    status, raw = request(desk, "GET", "/api/workflows")
    labels = {w["id"]: w["desk_status"] for w in json.loads(raw)["workflows"]}
    assert labels["echo-check"] == "verified"

    # blocked: a test-double registry entry carrying a blocked requirement
    record = json.loads(accepted.registry.read_text())
    record["workflows"].append({
        "id": "partial-check", "name": "Partial Check", "version": 1,
        "entrypoint": "adws/built/partial-check/adw_partial_check.py",
        "spec_path": "adws/built/partial-check/config.json",
        "built_at": "2026-10-01T00:00:00+00:00", "build_run_id": "test-double",
        "status": "validated",
        "acceptance": {"requirements_total": 2, "verified": 1, "blocked": 1},
        "source_request": "test double, never built",
    })
    accepted.registry.write_text(json.dumps(record, indent=2) + "\n")
    # incomplete: a queued-but-unconsumed request and a needs_human build row
    text = (ADWS / "fixtures/requests/toy_vague.md").read_text().strip()
    status, raw = request(desk, "POST", "/api/builds", {"request": text})
    assert status == 200
    result = lab.build("adws/fixtures/requests/toy_vague.md", run_id="vague-run")
    assert result.returncode == 3
    with sqlite3.connect(lab.db) as conn:  # a builder that died mid-run leaves 'running'
        conn.execute("INSERT INTO runs (run_id, request_ref, config_hash, started_at, run_status, "
                     "acceptance_status) VALUES ('ghost-run', 'r', 'h', '2026-10-01T00:00:00+00:00', "
                     "'running', 'pending')")
        conn.commit()

    status, raw = request(desk, "GET", "/api/workflows")
    body = json.loads(raw)
    labels = {w["id"]: w["desk_status"] for w in body["workflows"]}
    assert labels == {"echo-check": "verified", "partial-check": "blocked"}
    incomplete = body["incomplete"]
    assert any(i["status"] == "queued" and i["source"] == "queue" for i in incomplete)
    assert any(i["status"] == "needs_human" and i["run_id"] == "vague-run" for i in incomplete)
    assert any(i["status"] == "running" and i["run_id"] == "ghost-run" for i in incomplete)


def test_seats_lane_gemini_oauth_never_verified_while_login_absent(lab, desk, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)
    monkeypatch.setattr(desk_module, "_seat_auth_check", lambda provider: "ok")
    status, raw = request(desk, "GET", "/api/workflows")
    seat = json.loads(raw)["seats"][0]
    assert status == 200
    assert seat["name"] == "gemini-oauth" and seat["role"] == "Main"
    assert seat["provider_model"] == "google-vertex/gemini-3.7-flash"
    assert seat["stack"] == ".pi/fusion-harness/model-stack-gemini-oauth.yaml"
    assert seat["recipe"] == "just fusion-gemini" and seat["display_only"] is True
    assert seat["tokens"] == "unknown" and seat["cost"] == "unknown"  # never 0
    assert all(isinstance(value, (bool, str)) for value in seat["checks"].values())
    assert seat["status"] == "not_ready"  # env absent: verified is impossible

    # every real check green -> verified; login absent -> not_ready even then
    adc = lab.root / "adc-fixture.json"
    adc.write_text('{"client_token": "SENTINEL-not-a-real-credential"}\n')
    monkeypatch.setenv("ADW_ADC_CREDENTIALS", str(adc))
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "fixture-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    status, raw = request(desk, "GET", "/api/workflows")
    seat = json.loads(raw)["seats"][0]
    assert seat["status"] == "verified"
    assert "SENTINEL" not in raw  # credential VALUES are never read or echoed
    monkeypatch.setattr(desk_module, "_seat_auth_check", lambda provider: "failed")
    status, raw = request(desk, "GET", "/api/workflows")
    assert json.loads(raw)["seats"][0]["status"] == "not_ready"


def test_post_build_queues_consumable_record(lab, desk):
    text = (ADWS / "fixtures/requests/toy_complete.md").read_text().strip()
    status, raw = request(desk, "POST", "/api/builds", {"request": text})
    body = json.loads(raw)
    assert status == 200 and body["queued"] is True
    path = Path(body["file"])
    assert path.parent == lab.root / "queue" and path.read_text() == text + "\n"
    status, raw = request(desk, "GET", "/api/builds")
    assert status == 200 and json.loads(raw)["queued"][0]["file"] == path.name
    assert lab.build(str(path)).returncode == 0
    status, raw = request(desk, "GET", "/api/builds/verify")
    detail = json.loads(raw)
    assert status == 200 and detail["build"]["status"] == "accepted"
    assert len(detail["agents"]) == 4


def test_build_telemetry_is_visible_with_unknown_fields(accepted, desk):
    status, raw = request(desk, "GET", "/api/builds")
    assert status == 200
    build = json.loads(raw)["builds"][0]
    assert build["run_id"] == "verify" and build["acceptance_status"] == "accepted"
    for agent in build["agents"]:
        assert agent["tools"] and agent["tool_calls"] > 0
        assert agent["tool_errors"] == 0 and agent["duration_ms"] > 0
        assert agent["model"] == "unknown"
        assert all(v == "unknown" for v in agent["tokens"].values())
        assert agent["cost"]["total"] == "unknown"


def test_launch_is_stub_only_and_bounded(accepted, desk):
    status, raw = request(desk, "POST", "/api/launch", {"id": "echo-check"})
    body = json.loads(raw)
    assert status == 200 and body["mode"] == "stub" and body["exit"] == 0
    assert "AGENT greeter → GATE greeting_nonempty PASS" in body["log_tail"]
    with sqlite3.connect(accepted.root / "launches.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM phase_attempts").fetchone()[0] == 1


@pytest.mark.parametrize("method,path,body,expected", [
    ("POST", "/api/builds", {"request": ""}, 400),
    ("POST", "/api/builds", {"request": 7}, 400),
    ("POST", "/api/launch", {"id": "../escape"}, 400),
    ("POST", "/api/launch", {"id": "missing"}, 404),
    ("GET", "/api/builds/missing", None, 404),
    ("GET", "/api/builds/invalid!", None, 400),
    ("GET", "/api/unknown", None, 404),
])
def test_endpoint_refusals(lab, desk, method, path, body, expected):
    status, raw = request(desk, method, path, body)
    assert status == expected and "error" in json.loads(raw)


def test_cli_refuses_non_loopback_bind(lab):
    result = lab.invoke([ADWS / "server.py", "--host", "0.0.0.0"])
    assert result.returncode == 2 and "127.0.0.1 only" in result.stdout
