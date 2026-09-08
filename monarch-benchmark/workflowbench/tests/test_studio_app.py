"""Studio comparison lifecycle, retained evidence and localhost HTTP boundary."""
import http.client
import json
import threading
from contextlib import contextmanager
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from wb_results.evidence import verify_manifest
from wb_results.store import Store
from wb_studio.app import ROOT, Studio, handler
from wb_world.episode import load_suite


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    def forbidden_gateway(*args, **kwargs):
        pytest.fail("An offline Studio test attempted paid dispatch")
    return Studio(tmp_path / "studio", tasks=load_suite(ROOT / "tasks")[:1],
                  gateway_factory=forbidden_gateway)


def payload(studio, **changes):
    return {"request_id": "comparison-1", "models": ["oracle", "sloppy"],
            "tasks": list(studio.tasks), "maximum_usd": "1.00", **changes}


@pytest.mark.parametrize("changes", [
    {"request_id": "../escape"}, {"models": []}, {"models": ["oracle", "oracle"]},
    {"models": ["claude-code"]}, {"tasks": []}, {"tasks": ["unknown-task"]},
    {"tasks": ["same", "same"]}, {"maximum_usd": "0"},
    {"maximum_usd": "300.01"}, {"maximum_usd": "NaN"}, {"maximum_usd": "0.001"},
])
def test_invalid_comparison_is_rejected_before_creating_job(studio, changes):
    with pytest.raises(ValueError):
        studio.create(payload(studio, **changes), start=False)
    assert studio.jobs() == []
    assert Decimal(studio.budget()["held"]) == 0


def test_duplicate_request_id_returns_original_without_dispatch_or_events(studio, monkeypatch):
    launches = []
    class Thread:
        def __init__(self, **kwargs):
            launches.append(kwargs)
        def start(self):
            pass
    monkeypatch.setattr("wb_studio.app.threading.Thread", Thread)
    first = studio.create(payload(studio))
    second = studio.create(payload(studio))
    assert second == first
    assert len(launches) == 1
    assert [e["type"] for e in studio.events(first["id"])] == ["queued"]
    with pytest.raises(ValueError, match="different comparison"):
        studio.create(payload(studio, models=["oracle"]))
    assert len(launches) == 1


def test_scripted_comparison_retains_real_verdicts_tool_nodes_and_verified_evidence(studio):
    job = studio.create(payload(studio), start=False)
    studio.execute(job["id"])
    complete = studio.job(job["id"])
    assert complete["status"] == "completed", complete
    assert complete["completed"] == complete["total"] == 2
    results = {r["model"]: r for r in complete["results"]}
    assert results["oracle"]["passed"] is True
    assert results["sloppy"]["passed"] is False
    assert all(r["checks"] and r["tool_calls"] > 0 and r["output"] for r in results.values())
    events = studio.events(job["id"])
    assert [e["id"] for e in events] == list(range(1, len(events) + 1))
    assert events[-1]["type"] == "finished"
    assert events[-1]["job"] == complete
    started = [e for e in events if e["type"] == "node_started"]
    finished = [e for e in events if e["type"] == "node_finished"]
    assert {(e["model"], e["node"]) for e in started} == {(e["model"], e["node"]) for e in finished}
    assert all("arguments" in e for e in started)
    assert all("output" in e for e in finished)
    store = Store(studio.directory / job["id"] / "results.sqlite3")
    try:
        rows = store.episodes(run=job["id"])["rows"]
        assert len(rows) == 2
        for row in rows:
            artifacts = store.artifacts(row["episode_id"])
            verify_manifest(artifacts["manifest"], episode_id=row["episode_id"], contract_sha256=row["contract_sha256"])
            attempt = Path(artifacts["manifest"]).parent / "attempt-000"
            live = [json.loads(line) for line in (attempt / "events.live.jsonl").read_text().splitlines()]
            assert live
    finally:
        store.close()
    assert Decimal(studio.budget()["held"]) == 0
    assert Decimal(studio.budget()["actual"]) == 0


def test_cancellation_before_execution_prevents_any_attempt(studio):
    job = studio.create(payload(studio), start=False)
    assert studio.cancel(job["id"])["status"] == "cancelling"
    studio.execute(job["id"])
    complete = studio.job(job["id"])
    assert complete["status"] == "cancelled"
    assert complete["completed"] == 0
    assert complete["results"] == []
    assert not any(e["type"] == "attempt_started" for e in studio.events(job["id"]))


@pytest.mark.parametrize("status", ["queued", "running", "cancelling"])
def test_restart_interrupts_unfinished_work_without_replay(studio, status):
    job = studio.create(payload(studio), start=False)
    job["status"] = status
    studio.save(job)
    before = studio.events(job["id"])
    restarted = Studio(studio.directory, tasks=list(studio.tasks.values()), gateway_factory=studio.gateway_factory)
    assert restarted.job(job["id"])["status"] == "interrupted"
    assert restarted.job(job["id"])["completed"] == 0
    assert restarted.events(job["id"]) == before
    assert restarted.create(payload(restarted))["status"] == "interrupted"
    assert restarted.events(job["id"]) == before


@contextmanager
def server_for(studio):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(studio))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def request(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode()
    finally:
        connection.close()


def test_sse_reconnect_replays_only_events_after_cursor(studio):
    job = studio.create(payload(studio), start=False)
    studio.emit(job["id"], "node_started", node="node-1")
    studio.emit(job["id"], "node_finished", node="node-1", output="retained")
    job["status"] = "completed"
    studio.save(job)
    with server_for(studio) as port:
        status, headers, body = request(port, "GET", f"/api/jobs/{job['id']}/events?after=1")
        assert status == 200
        assert headers["Content-Type"] == "text/event-stream"
        values = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
        assert [v["id"] for v in values] == [2, 3]
        assert values[1]["output"] == "retained"
        status, _, body = request(port, "GET", f"/api/jobs/{job['id']}/events?after=0", headers={"Last-Event-ID": "2"})
        assert status == 200
        assert "id: 3\n" in body and "id: 2\n" not in body and "id: 1\n" not in body


def test_http_rejects_foreign_origin_host_and_missing_session_before_mutation(studio):
    job = studio.create(payload(studio), start=False)
    with server_for(studio) as port:
        endpoint = f"/api/jobs/{job['id']}/cancel"
        for headers in ({}, {"X-Studio-Token": "wrong"},
                        {"X-Studio-Token": studio.token, "Origin": "https://evil.example"},
                        {"X-Studio-Token": studio.token, "Host": "evil.example"}):
            status, _, _ = request(port, "POST", endpoint, "{}", headers)
            assert status == 403
            assert studio.job(job["id"])["status"] == "queued"
        for headers in ({"Origin": "https://evil.example"}, {"Host": "evil.example"}):
            status, _, body = request(port, "GET", "/api/state", headers=headers)
            assert status == 403
            assert studio.token not in body
        status, _, _ = request(port, "POST", endpoint, "{}", {
            "X-Studio-Token": studio.token, "Origin": f"http://127.0.0.1:{port}"})
        assert status == 200
        assert studio.job(job["id"])["status"] == "cancelling"


def test_static_allowlist_never_exposes_secrets_or_evidence(studio, tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    for name in ("index.html", "app.js", "style.css"):
        (static / name).write_text("safe-" + name)
    (tmp_path / ".env").write_text("PRIVATE_SECRET=must-not-leak")
    monkeypatch.setattr("wb_studio.app.STATIC", static)
    with server_for(studio) as port:
        for path in ("/.env", "/../.env", "/%2e%2e/.env", "/evidence/result.json", "/api/unknown"):
            status, _, body = request(port, "GET", path)
            assert status == 404
            assert "must-not-leak" not in body
        for path, expected in (("/", "index.html"), ("/app.js", "app.js"), ("/style.css", "style.css")):
            status, headers, body = request(port, "GET", path)
            assert status == 200 and body == "safe-" + expected
            assert headers["X-Content-Type-Options"] == "nosniff"
            assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_fake_api_control_streams_tool_output_and_final_text_with_usage(studio, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-placeholder")
    requests = []
    class FakeGateway:
        def __init__(self, ledger, model):
            assert ledger is studio.ledger
            assert model == "gemini-3.7-flash"
        def request(self, contents, system, tools, **kwargs):
            requests.append(json.loads(json.dumps({"contents": contents, "system": system,
                                                  "tools": tools, "bounds": kwargs}, default=str)))
            parts = ([{"functionCall": {"id": "call-123", "name": "base64_encode", "args": {"text": "visible output"}}}]
                     if len(requests) == 1 else [{"text": "Finished the requested demonstration."}])
            return {"candidates": [{"content": {"parts": parts}, "finishReason": "STOP"}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4, "thoughtsTokenCount": 2},
                    "_billing": {"actual_usd": "0.01"}}
    studio.gateway_factory = FakeGateway
    job = studio.create(payload(studio, models=["gemini-3.7-flash"], maximum_usd="2.00"), start=False)
    studio.execute(job["id"])
    complete = studio.job(job["id"])
    assert complete["status"] == "completed", complete
    result = complete["results"][0]
    assert result["output"] == "Finished the requested demonstration."
    assert result["tokens"] == {"prompt": 20, "cached": 0, "cache_write": 0, "output": 12}
    assert result["cost_usd"] == pytest.approx(.02)
    assert result["tool_calls"] == 1
    assert result["passed"] is False  # Prose and a harmless tool call do not complete the business task.
    assert len(requests) == 2
    assert requests[0]["bounds"]["scope_id"] == job["id"]
    assert requests[0]["bounds"]["scope_limit_usd"] == "2.00"
    assert requests[0]["bounds"]["request_id"] != requests[1]["bounds"]["request_id"]
    assert requests[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]["result"] == "dmlzaWJsZSBvdXRwdXQ="
    assert requests[1]["contents"][-1]["parts"][0]["functionResponse"]["id"] == "call-123"
    events = studio.events(job["id"])
    assert [e["output"] for e in events if e["type"] == "node_finished"] == ["dmlzaWJsZSBvdXRwdXQ="]
    assert [e["output"] for e in events if e["type"] == "model_finished"][-1] == result["output"]
    assert len([e for e in events if e["type"] == "billing"]) == 2


def test_execution_claim_prevents_second_dispatch(studio):
    job = studio.create(payload(studio), start=False)
    studio.execute(job["id"])
    before = studio.events(job["id"])
    studio.execute(job["id"])
    assert studio.events(job["id"]) == before
    assert studio.job(job["id"])["completed"] == 2


def test_production_uses_one_ledger_even_with_custom_output(tmp_path, monkeypatch):
    monkeypatch.setattr("wb_studio.app.REPO", tmp_path / "repository")
    first = Studio(tmp_path / "first", tasks=load_suite(ROOT / "tasks")[:1])
    second = Studio(tmp_path / "second", tasks=load_suite(ROOT / "tasks")[:1])
    assert first.ledger.path == second.ledger.path == (tmp_path / "repository" / "research" / "budget.sqlite3").resolve()
    first.ledger.reserve("shared-hold", "290", scope_id="one")
    assert second.budget()["available"] == "10.000000"


# -- hosted Studio: basic auth, public host names, data folder (unblock plan D4) -----------

def test_basic_auth_challenges_until_the_credentials_match(studio, monkeypatch):
    import base64
    monkeypatch.setenv("STUDIO_AUTH_USER", "admin")
    monkeypatch.setenv("STUDIO_AUTH_PASSWORD", "pw")
    with server_for(studio) as port:
        status, headers, body = request(port, "GET", "/api/state")
        assert status == 401 and headers["WWW-Authenticate"].startswith("Basic") and studio.token not in body
        wrong = base64.b64encode(b"admin:nope").decode()
        assert request(port, "GET", "/api/state", headers={"Authorization": f"Basic {wrong}"})[0] == 401
        assert request(port, "GET", "/api/state", headers={"Authorization": "Basic not-base64!"})[0] == 401
        right = base64.b64encode(b"admin:pw").decode()
        status, _, body = request(port, "GET", "/api/state", headers={"Authorization": f"Basic {right}"})
        assert status == 200 and studio.token in body
        status, _, _ = request(port, "POST", "/api/jobs/nope/cancel", "{}", {"Authorization": f"Basic {right}"})
        assert status == 403, "the session token is still required for writes"
        assert request(port, "POST", "/api/jobs/nope/cancel", "{}")[0] == 401


def test_without_the_auth_pair_the_studio_stays_open_on_localhost(studio, monkeypatch):
    monkeypatch.delenv("STUDIO_AUTH_USER", raising=False)
    monkeypatch.delenv("STUDIO_AUTH_PASSWORD", raising=False)
    with server_for(studio) as port:
        assert request(port, "GET", "/")[0] == 200


def test_public_host_allowlist_accepts_the_hosted_name_over_https(studio, monkeypatch):
    monkeypatch.setenv("STUDIO_PUBLIC_HOSTS", "studio.example.app, Other.Example.App")
    with server_for(studio) as port:
        assert request(port, "GET", "/", headers={"Host": "studio.example.app"})[0] == 200
        assert request(port, "GET", "/", headers={"Host": "studio.example.app",
                                                   "Origin": "https://studio.example.app"})[0] == 200
        assert request(port, "GET", "/", headers={"Host": "other.example.app"})[0] == 200
        assert request(port, "GET", "/", headers={"Host": "evil.example.app"})[0] == 403
        assert request(port, "GET", "/", headers={"Host": "studio.example.app",
                                                   "Origin": "https://evil.example.app"})[0] == 403


def test_data_dir_moves_the_jobs_folder_and_the_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path / "data"))
    hosted = Studio(tasks=[])
    assert hosted.directory == tmp_path / "data" / "studio"
    assert hosted.ledger.path == (tmp_path / "data" / "research" / "budget.sqlite3").resolve()


def test_main_refuses_a_public_bind_without_the_auth_pair(monkeypatch):
    from wb_studio.app import main
    monkeypatch.delenv("STUDIO_AUTH_USER", raising=False)
    monkeypatch.delenv("STUDIO_AUTH_PASSWORD", raising=False)
    with pytest.raises(SystemExit):
        main(["--host", "0.0.0.0", "--port", "0"])
