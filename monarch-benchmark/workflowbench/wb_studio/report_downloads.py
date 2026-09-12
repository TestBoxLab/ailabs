"""Read-only, redacted downloads of retained execution observations."""
import json
import hashlib
from pathlib import Path
import re

from wb_studio.memory import CREDENTIAL
from wb_studio.report_data import lab_setups, setup_ids
from wb_studio.measures import setup_names


SECRET_KEY = re.compile(r"(?:authorization|cookie|password|secret|credential|api.?key|token$)", re.I)
SECRET_TEXT = re.compile(r"\b(?:Bearer|Basic)\s+[^\s\"',;]+|\b(?:authorization|(?:set-)?cookie)\s*:\s*[^\r\n]+|"
                         r"\b[A-Za-z0-9_-]*?(?:api[_-]?key|secret[_-]?access[_-]?key|password|secret|token)\s*[=:]\s*[\"']?[^\s\"',;}]+", re.I)
OMIT = {"snapshot0", "snapshot1", "snapshot", "world", "grading", "checks", "check_results", "assertions",
        "approval_rule", "contract", "expected_answer", "expected_result", "billing", "budget", "env", "environment"}
JOURNAL_FIELDS = {"id", "at", "type", "model", "task", "trial", "node", "step", "label", "arguments", "output",
                  "status", "turn", "text", "message", "error", "reasoning", "stop_reason", "request", "response",
                  "tool", "tool_calls", "result", "rendered", "http_status", "error_code", "category", "phase"}
ARTIFACTS = ("events.jsonl", "turns.jsonl", "events.live.jsonl", "turns.live.jsonl", "front-door.jsonl")
REASONING_FIELDS = {"reasoning", "thinking", "thoughts", "reasoning_content", "encrypted_content", "signature", "thoughtsignature", "thought_signature"}


def private_block(value):
    return isinstance(value, dict) and (value.get("type") in ("reasoning", "thinking", "analysis", "redacted_thinking")
                                       or value.get("channel") == "analysis" or value.get("thought") is True)


def clean(value):
    """Reuse the credential pattern and remove structured secret/evaluator fields.

    JSON embedded in tool-output strings is cleaned structurally too. Arbitrary
    natural-language secrets cannot be exhaustively recognized by patterns.
    """
    if isinstance(value, dict):
        if private_block(value):
            return {"omitted": "Provider reasoning"}
        return {key: "[redacted]" if SECRET_KEY.search(key) else clean(item)
                for key, item in value.items() if key.lower() not in OMIT
                and not (key.lower() in REASONING_FIELDS)}
    if isinstance(value, list):
        return [clean(item) for item in value if not private_block(item)]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                return json.dumps(clean(json.loads(value)), ensure_ascii=False)
            except (ValueError, RecursionError):
                pass
        return CREDENTIAL.sub("[redacted]", SECRET_TEXT.sub("[redacted]", value))
    return value


def export_setups(job):
    """Keep the single report scope and refuse all exports carrying a lab build."""
    shown = setup_ids(job)
    names = setup_names(job)
    if lab_setups(shown, {sid: {"name": names.get(sid, sid)} for sid in shown}):
        raise PermissionError("Reports containing lab builds cannot be exported.")
    return shown


def download(studio, identity, kind):
    """Return JSON-ready logs or prompts; never load current task definitions.

    Only canonical result artifact locations inside this run can be read. Live
    and finalized journals retain their own provenance and may overlap.
    """
    if kind not in ("logs", "prompts"):
        raise ValueError("Unknown evidence download")
    job = studio.job(identity)
    folder = (studio.directory / identity).resolve()
    shown = export_setups(job)
    from wb_studio.report_inputs import saved_rows
    rows = saved_rows(folder / "results.sqlite3", identity) or job.get("results") or []
    records, sources, omitted, invalid = [], set(), 0, 0
    for position, event in enumerate(studio.events(identity), 1):
        if event.get("model") in shown and event.get("task"):
            matches = [row for row in rows if row.get("arm", row.get("model")) == event["model"]
                       and row.get("task_id", row.get("task")) == event["task"]
                       and (row.get("episode_id") == event["episode_id"] if event.get("episode_id") else
                            type(event.get("trial")) is int and row.get("trial") == event["trial"])
                       and (event.get("trial") is None or type(event["trial"]) is int and row.get("trial") == event["trial"])]
            attempt_id = matches[0].get("episode_id") if len(matches) == 1 else None
            records.append({"source": "events.jsonl", "task": event["task"], "model": event["model"],
                            **({"event_id": event["id"]} if event.get("id") is not None else {"source_position": position}),
                            "attempt_id": attempt_id if isinstance(attempt_id, str) and attempt_id else None,
                            "trial": event.get("trial"), "record": {k: v for k, v in event.items() if k in JOURNAL_FIELDS}})
    for row in rows:
        model, task = row.get("arm", row.get("model")), row.get("task_id", row.get("task"))
        if model not in shown or not task or not row.get("artifacts_uri"):
            continue
        root = Path(row["artifacts_uri"]).resolve()
        if not root.is_relative_to(folder):
            omitted += 1
            continue
        attempts = sorted(path for path in root.glob("attempt-*") if path.is_dir())
        for directory in [root, *attempts]:
            for filename in ARTIFACTS:
                path = (directory / filename).resolve()
                if not path.is_relative_to(folder):
                    omitted += 1
                    continue
                if path in sources or not path.is_file():
                    continue
                sources.add(path)
                with path.open(encoding="utf-8") as stream:
                    for line_number, line in enumerate(stream, 1):
                        if not line.strip():
                            continue
                        try:
                            value = json.loads(line)
                        except ValueError:
                            invalid += 1
                            continue
                        if isinstance(value, dict):
                            records.append({"source": path.relative_to(folder).as_posix(), "line": line_number,
                                            "attempt_id": row.get("episode_id") if isinstance(row.get("episode_id"), str) and row["episode_id"] else None,
                                            "task": task, "model": model, "trial": row.get("trial"), "record": value})
    unique_prompts, prompt_observations = {}, 0
    for entry in records:
        location = [identity, entry["source"], entry.get("line"), entry.get("event_id"), entry.get("source_position")]
        entry["log_id"] = "log-" + hashlib.sha256(json.dumps(location, separators=(",", ":")).encode()).hexdigest()
        entry["linkage"] = "recorded_attempt" if entry["attempt_id"] else "unavailable"
        record = entry["record"]
        request = record.get("request")
        input_kind = "retained_request"
        if record.get("type") == "model_prompt":
            request = record.get("arguments")
        frame = record.get("frame")
        if isinstance(frame, dict) and isinstance(frame.get("goal"), str) and frame["goal"].strip():
            request, input_kind = {"goal": frame["goal"]}, "monarch_goal"
        if isinstance(request, dict):
            retained = {k: request[k] for k in ("messages", "system", "brief", "input", "instructions", "prompt", "goal") if k in request}
            if retained:
                prompt_observations += 1
                digest = hashlib.sha256(json.dumps(retained, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                key = (entry["attempt_id"], entry["task"], entry["model"], entry["trial"], record.get("step"),
                       record.get("turn") if input_kind != "monarch_goal" else None, digest)
                prompt = unique_prompts.setdefault(key, {"task": entry["task"], "model": entry["model"], "trial": entry["trial"],
                                                        "attempt_id": entry["attempt_id"], "linkage": entry["linkage"], "log_ids": [],
                                                        "input_kind": input_kind, "request": retained, "sources": []})
                prompt["log_ids"].append(entry["log_id"])
                prompt["sources"].append({k: v for k, v in entry.items() if k not in ("record", "task", "model", "trial")})
    prompts = list(unique_prompts.values())
    covered = {(entry["task"], entry["model"]) for entry in prompts}
    covered_attempts = {(entry["task"], entry["model"], entry["trial"]) for entry in prompts}
    covered_ids = {entry["attempt_id"] for entry in prompts if entry["attempt_id"]}
    missing_attempts = [{"task": row.get("task_id", row.get("task")), "model": row.get("arm", row.get("model")), "trial": row.get("trial"),
                         "attempt_id": row.get("episode_id")}
                        for row in rows if row.get("arm", row.get("model")) in shown and
                        (row["episode_id"] not in covered_ids if row.get("episode_id") else
                         (row.get("task_id", row.get("task")), row.get("arm", row.get("model")), row.get("trial")) not in covered_attempts)]
    expected = {(task, model) for task in (job.get("settings") or {}).get("tasks") or [] for model in shown}
    result = {"version": 2, "run": identity, "kind": kind,
              "coverage": {"retained_log_records": len(records), "retained_prompt_records": len(prompts),
                           "unlinked_log_records": sum(entry["attempt_id"] is None for entry in records),
                           "unlinked_prompt_records": sum(entry["attempt_id"] is None for entry in prompts),
                           "prompt_observations_before_deduplication": prompt_observations, "missing_prompt_attempts": missing_attempts,
                           "artifact_files": len(sources), "omitted_artifact_locations": omitted, "invalid_json_lines": invalid,
                           "full_native_context": "unavailable",
                           "missing_prompt_tasks": [{"task": t, "model": m} for t, m in sorted(expected - covered)]},
              "limitations": ["Contains only retained observations and input records; current task text is never substituted for missing prompts.",
                              "Join prompts.log_ids to events.log_id. attempt_id is the recorded episode_id; journal events without an explicit, uniquely matched episode or trial leave attempt linkage unavailable. Log IDs identify source locations and remain stable across repeated downloads.",
                              "Native harness internals and complete system context are not guaranteed to have been recorded. A retained request may omit separately supplied system instructions.",
                              "Monarch goals are retained user objectives from builder frames, not the builder's system prompt. Identical input records for the same task, competitor, trial and turn are combined with every source reference retained.",
                              "Live and finalized journals may overlap; source paths and line numbers distinguish observations. Missing or invalid records are not reconstructed.",
                              "Snapshot, evaluator, environment and billing fields are excluded. Credential-shaped fields and common token patterns are redacted; arbitrary secrets embedded in prose may not be recognizable.",
                              "Downloads omit provider reasoning fields. Reports containing lab builds cannot be exported."],
              "events" if kind == "logs" else "prompts": records if kind == "logs" else prompts}
    return clean(result)
