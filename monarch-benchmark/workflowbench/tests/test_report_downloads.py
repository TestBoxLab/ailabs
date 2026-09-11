"""Authenticated evidence downloads read retained inputs without rewriting history."""
import base64
import hashlib
import json

from tests.test_studio_reports import studio, finished_run
from tests.test_studio_app import server_for, request


def record(studio):
    job = finished_run(studio)
    folder = studio.directory / job["id"]
    saved = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    saved["settings"]["arms"][1]["name"] = "monarch-lab-private"
    (folder / "job.json").write_text(json.dumps(saved), encoding="utf-8")
    task = saved["settings"]["tasks"][0]
    studio.emit(job["id"], "model_prompt", model="oracle", task=task,
                arguments={"system": "Retained system. api_key=never-share", "brief": "Retained request, not the current task."})
    studio.emit(job["id"], "node_finished", model="oracle", task=task, output=json.dumps({
        "authorization": "Bearer never-share", "result": "Observed tool value", "snapshot0": "ANSWER KEY"}),
        reasoning=["PRIVATE REASONING"], credentials={"password": "never-share"})
    studio.emit(job["id"], "model_prompt", model="sloppy", task=task, arguments={"system": "HIDDEN PROMPT", "brief": "HIDDEN PROMPT"})
    studio.emit(job["id"], "job_config", settings={"password": "CONFIG SECRET"})
    return job, folder


def test_downloads_use_existing_get_authentication(studio, monkeypatch):
    job = finished_run(studio)
    monkeypatch.setenv("STUDIO_AUTH_USER", "reader")
    monkeypatch.setenv("STUDIO_AUTH_PASSWORD", "test-password")
    auth = "Basic " + base64.b64encode(b"reader:test-password").decode()
    path = f"/api/reports/run/{job['id']}/downloads/logs"
    with server_for(studio) as port:
        assert request(port, "GET", path)[0] == 401
        assert request(port, "GET", path, headers={"Authorization": auth, "Origin": "https://foreign.example"})[0] == 403
        status, headers, body = request(port, "GET", path, headers={"Authorization": auth})
        assert status == 200
        assert headers["Content-Type"].startswith("application/json")
        assert "attachment;" in headers["Content-Disposition"] and headers["Cache-Control"] == "no-store"
        assert json.loads(body)["kind"] == "logs"


def test_public_downloads_filter_prose_and_redact_without_reading_current_tasks(studio):
    from wb_studio.report_downloads import download
    job, folder = record(studio)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}
    studio.tasks = {}  # No replacement current task text may be consulted.
    logs = download(studio, job["id"], "logs", "public")
    prompts = download(studio, job["id"], "prompts", "public")
    text = json.dumps([logs, prompts])
    assert "Observed tool value" in text and "Retained request, not the current task." in text
    for excluded in ("HIDDEN PROMPT", "PRIVATE REASONING", "never-share", "CONFIG SECRET", "ANSWER KEY", "monarch-lab-private"):
        assert excluded not in text
    assert prompts["coverage"]["full_native_context"] == "unavailable"
    assert prompts["prompts"] and "Retained system" in json.dumps(prompts["prompts"])
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    internal = download(studio, job["id"], "prompts", "internal")
    assert "HIDDEN PROMPT" in json.dumps(internal)


def test_canonical_attempt_requests_are_downloaded_and_outside_paths_refused(studio, tmp_path, monkeypatch):
    from wb_studio.report_downloads import download
    job, folder = record(studio)
    evidence = folder / "evidence" / "canonical"
    evidence.mkdir(parents=True)
    (evidence / "turns.jsonl").write_text(json.dumps({"turn": 0, "request": {"messages": [
        {"role": "system", "content": "Original retained API system"}, {"role": "user", "content": "Original retained API request"}]},
        "response": {"text": "Finished"}}) + "\n" + json.dumps({"frame": {"goal": "Retained Monarch goal"}}) + "\n", encoding="utf-8")
    (evidence / "snapshot0.json").write_text('{"answer":"DO NOT EXPORT"}', encoding="utf-8")
    attempt = evidence / "attempt-000"
    attempt.mkdir()
    (attempt / "turns.live.jsonl").write_bytes((evidence / "turns.jsonl").read_bytes())
    (evidence / "front-door.jsonl").write_text('{"method":"GET","path":"/retained-api-call","status":200}\n', encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "turns.jsonl").write_text('{"request":{"system":"OUTSIDE SECRET"}}\n', encoding="utf-8")
    original_job = studio.job(job["id"])
    original_job["results"] = [{**r, "episode_id": f"{job['id']}/retained-attempt-{i}", "artifacts_uri": str(evidence if i == 0 else outside)}
                               for i, r in enumerate(original_job["results"])]
    monkeypatch.setattr(studio, "job", lambda identity: original_job)
    monkeypatch.setattr("wb_studio.report_inputs.saved_rows", lambda *args: [])
    prompts = download(studio, job["id"], "prompts")
    assert "Original retained API request" in json.dumps(prompts)
    assert "OUTSIDE SECRET" not in json.dumps(prompts) and "DO NOT EXPORT" not in json.dumps(prompts)
    assert prompts["coverage"]["omitted_artifact_locations"] > 0
    goals = [p for p in prompts["prompts"] if p.get("input_kind") == "monarch_goal"]
    assert len(goals) == 1 and goals[0]["request"] == {"goal": "Retained Monarch goal"}
    original = [p for p in prompts["prompts"] if "Original retained API request" in json.dumps(p)]
    assert len(original) == 1 and len(original[0]["sources"]) == 2
    logs = download(studio, job["id"], "logs")
    assert logs["version"] == prompts["version"] == 2
    assert "/retained-api-call" in json.dumps(logs)
    linked = {event["log_id"]: event for event in logs["events"]}
    assert len(linked) == len(logs["events"])
    assert original[0]["attempt_id"] == original_job["results"][0]["episode_id"]
    assert len(original[0]["log_ids"]) == 2 and set(original[0]["log_ids"]) == {s["log_id"] for s in original[0]["sources"]}
    for log_id in original[0]["log_ids"]:
        assert linked[log_id]["attempt_id"] == original[0]["attempt_id"]
        assert "Original retained API request" in json.dumps(linked[log_id]["record"])
    internal = download(studio, job["id"], "logs", "internal")
    assert set(linked) <= {event["log_id"] for event in internal["events"]}
    assert prompts["coverage"]["missing_prompt_attempts"]


def test_journal_linkage_requires_an_explicit_exact_attempt(studio, monkeypatch):
    from wb_studio.report_downloads import download
    job = finished_run(studio)
    task = job["settings"]["tasks"][0]
    trial_rows = [{"model": "oracle", "task": task, "trial": trial, "episode_id": f"{job['id']}/{task}/oracle/t{trial}"}
                  for trial in (0, 1)]
    monkeypatch.setattr("wb_studio.report_inputs.saved_rows", lambda *args: trial_rows)
    for label, identity in (("unidentified", {}), ("trial-linked", {"trial": 1}),
                            ("episode-linked", {"episode_id": trial_rows[0]["episode_id"]}),
                            ("wrong-episode", {"episode_id": "not-recorded"})):
        studio.emit(job["id"], "model_prompt", model="oracle", task=task, label=label,
                    arguments={"brief": "Same retained prompt"}, **identity)
    logs = download(studio, job["id"], "logs")
    events = {event["record"].get("label"): event for event in logs["events"]}
    assert events["trial-linked"]["attempt_id"] == trial_rows[1]["episode_id"]
    assert events["episode-linked"]["attempt_id"] == trial_rows[0]["episode_id"]
    assert events["unidentified"]["attempt_id"] is None and events["unidentified"]["linkage"] == "unavailable"
    assert events["wrong-episode"]["attempt_id"] is None
    prompts = download(studio, job["id"], "prompts")
    assert all(prompt["log_ids"] for prompt in prompts["prompts"])
    assert {event["log_id"] for event in events.values()} >= {log_id for prompt in prompts["prompts"] for log_id in prompt["log_ids"]}
    assert prompts["coverage"]["missing_prompt_attempts"] == []


def test_token_fields_and_bearer_tokens_are_fully_redacted():
    from wb_studio.report_downloads import clean
    value = {"token": "secret-token", "X-Studio-Token": "secret-session", "output": "Bearer secret-bearer and sk-secretapikey",
             "input": "token=secret-inline"}
    assert "secret-" not in json.dumps(clean(value, "internal"))
    assert "SYNTHETIC_SECRET_VALUE" not in clean("GOOGLE_API_KEY=SYNTHETIC_SECRET_VALUE AWS_SECRET_ACCESS_KEY=SYNTHETIC_SECRET_VALUE Cookie: session=SYNTHETIC_SECRET_VALUE", "internal")


def test_public_downloads_remove_typed_provider_reasoning_from_request_histories():
    from wb_studio.report_downloads import clean
    value = {"request": {"messages": [{"type": "reasoning", "summary": [{"text": "PRIVATE OPENAI"}], "encrypted_content": "PRIVATE ENCRYPTED"},
        {"type": "thinking", "thinking": "PRIVATE ANTHROPIC", "signature": "PRIVATE SIGNATURE"},
        {"role": "assistant", "channel": "analysis", "content": "PRIVATE ANALYSIS"},
        {"thought": True, "text": "PRIVATE GEMINI", "thoughtSignature": "PRIVATE SIGNATURE"},
        {"role": "assistant", "content": "Visible answer", "reasoning_content": "PRIVATE DEEPSEEK"}]}}
    public = clean(value, "public")
    assert "PRIVATE" not in json.dumps(public) and "Visible answer" in json.dumps(public)
    assert "PRIVATE OPENAI" in json.dumps(clean(value, "internal"))


def test_missing_prompts_are_reported_instead_of_reconstructed(studio):
    from wb_studio.report_downloads import download
    job = finished_run(studio)
    prompts = download(studio, job["id"], "prompts")
    assert prompts["prompts"] == []
    assert prompts["coverage"]["retained_prompt_records"] == 0
    assert prompts["coverage"]["missing_prompt_tasks"]
