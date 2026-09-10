"""Versioned local evidence. Hashes detect corruption, not malicious replacement.

Live JSONL observations are flushed and fsynced before returning to the arm.
Snapshots use fsynced temporary files and atomic replacement. A process exit can
leave a running attempt and a partial last JSONL record: only complete records
and snapshot.observed.json are evidence, never proof of a final world. The files
are not a cross-file transaction, and this does not promise storage hardware or
power-loss durability. Native/provider messages exist only if a harness records
them through Episode.record_agent_event; private reasoning remains unavailable.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import tempfile
import time
import threading


class EvidenceIntegrityError(RuntimeError):
    pass


SOURCE_ROOT = Path(__file__).resolve().parents[1]
LIVE_ARTIFACTS = ("events.live.jsonl", "turns.live.jsonl", "snapshot.observed.json")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _long(path: Path) -> Path:
    """Windows refuses paths past 260 characters unless they carry the extended prefix; evidence folders are deep."""
    text = str(path)
    if os.name == "nt" and len(text) > 230 and not text.startswith("\\\\?\\"):
        return Path("\\\\?\\" + os.path.abspath(text))
    return path


def _plain(path: Path) -> str:
    """One comparable form for a path with or without the extended prefix."""
    text = str(path)
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normcase(os.path.abspath(text))


def _atomic_text(path: Path, text: str) -> None:
    path = _long(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        _replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _replace(temporary, path) -> None:
    """Atomic replacement. On Windows a reader that still holds the target open makes
    os.replace raise PermissionError for a moment; the write waits it out."""
    for attempt in range(40):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 39:
                raise
            time.sleep(0.05 * (attempt + 1))


def write_json(path: Path, value) -> None:
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def write_events(path: Path, events: list[dict]) -> None:
    _atomic_text(path, "".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in events))


def provenance() -> dict:
    """Hash the working sources actually used, including uncommitted repairs.

    The installed AutomationBench version is recorded, not a complete identity
    of its editable dependency tree. Source hashes do not identify that tree.
    """
    return {"python_version": platform.python_version(),
            "automation_bench_version": importlib.metadata.version("automation-bench"),
            "dependency_identity_scope": "installed_version_only",
            "source_sha256": {name: hashlib.sha256((SOURCE_ROOT / name).read_bytes()).hexdigest()
                              for name in ("grader/grade.py", "grader/invariant.py", "wb_world/episode.py")}}


class AttemptJournal:
    """Append-only observations for one new attempt, never reused on resume."""

    def __init__(self, directory: Path, snapshot0: dict):
        self.directory = _long(Path(directory))
        self.directory.mkdir(parents=True, exist_ok=False)
        self._lock = threading.RLock()
        self._next_id = 0
        self.closed = False
        write_json(self.directory / "attempt.json", {
            "schema": "workflowbench-attempt@1", "index": int(self.directory.name.rsplit("-", 1)[-1]),
            "status": "running", "completion": "incomplete", "final_world_state": "unavailable",
            "journal": True, "started_at": _timestamp(),
        })
        for name in LIVE_ARTIFACTS[:2]:
            with (self.directory / name).open("xb") as stream:
                stream.flush()
                os.fsync(stream.fileno())
        write_json(self.directory / "snapshot0.json", snapshot0)
        self._snapshot(snapshot0, None)

    def _append(self, filename: str, entry: dict) -> int:
        if self.closed:
            raise RuntimeError("cannot append to a finalized attempt")
        record = {**copy.deepcopy(entry), "observation_id": self._next_id,
                  "recorded_at": _timestamp()}
        with (self.directory / filename).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._next_id += 1
        return record["observation_id"]

    def _snapshot(self, world: dict, observation_id: int | None) -> None:
        write_json(self.directory / "snapshot.observed.json", {
            "schema": "workflowbench-observed-world@1", "observation_id": observation_id,
            "observed_at": _timestamp(), "final": False, "world": world,
        })

    def tool(self, event: dict, snapshot=None) -> None:
        with self._lock:
            event_type = {"running": "tool_started", "completed": "tool_completed", "error": "tool_error"}
            observation_id = self._append("events.live.jsonl", {
                **event, "type": event_type[event["status"]],
            })
            if snapshot is not None:
                self._snapshot(snapshot(), observation_id)

    def agent(self, entry: dict) -> None:
        with self._lock:
            self._append("turns.live.jsonl", {"type": "agent_observation", **entry, "kind": "agent"})


def write_attempt(root: Path, index: int, ep, result, termination: str, error: str | None) -> None:
    directory = root / f"attempt-{index:03d}"
    journal = getattr(ep, "_journal", None)
    if journal is None:
        directory = _long(directory)
        directory.mkdir(exist_ok=False)
        write_json(directory / "snapshot0.json", ep.snapshot0)
    elif _plain(journal.directory) != _plain(directory) or journal.closed:
        raise EvidenceIntegrityError("attempt finalization does not match its open journal")
    write_json(directory / "snapshot1.json", ep.snapshot())
    write_events(directory / "events.jsonl", ep.events)
    write_events(directory / "turns.jsonl", result.turn_log)
    phases = {name: metrics.model_dump(mode="json") if hasattr(metrics, "model_dump")
              else asdict(metrics) if is_dataclass(metrics) else metrics
              for name, metrics in result.phases.items()}
    # This marker is last. A crash before it cannot claim a finalized world,
    # even if a snapshot1 file was already atomically installed.
    write_json(directory / "attempt.json", {
        "schema": "workflowbench-attempt@1", "index": index,
        "status": "finalized", "completion": "complete", "final_world_state": "recorded",
        "journal": journal is not None, "finished_at": _timestamp(),
        "termination": termination, "error": error,
        "cost_usd": result.cost_usd, "flags": result.flags,
        "final_text": result.final_text, "phases": phases,
        "tokens": {"prompt": result.tokens_prompt, "cached": result.tokens_cached,
                   "cache_write": result.tokens_cache_write, "output": result.tokens_output},
        "turns": result.turns, "tool_calls": result.tool_calls,
    })
    if journal is not None:
        journal.closed = True


def write_manifest(root: Path, *, episode_id: str, contract_sha256: str,
                   agent_messages: str) -> dict:
    paths = [root / name for name in (
        "snapshot0.json", "snapshot1.json", "events.jsonl", "turns.jsonl",
        "grading.json", "result.json")]
    attempts = sorted(root.glob("attempt-*"))
    journaled_attempts = []
    for directory in attempts:
        paths.extend(directory / name for name in (
            "snapshot0.json", "snapshot1.json", "events.jsonl", "turns.jsonl", "attempt.json"))
        metadata_path = directory / "attempt.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
        if metadata.get("journal") or any((directory / name).exists() for name in LIVE_ARTIFACTS):
            journaled_attempts.append(directory.name)
            paths.extend(directory / name for name in LIVE_ARTIFACTS)
    artifacts, missing = [], []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if not path.is_file():
            missing.append(relative)
            continue
        data = path.read_bytes()
        artifacts.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(),
                          "bytes": len(data)})
    manifest = {
        "schema": "workflowbench-evidence@1", "episode_id": episode_id,
        "contract_sha256": contract_sha256, "attempt_count": len(attempts),
        "coverage": {"tool_events": "recorded", "agent_messages": agent_messages,
                     "private_reasoning": "unavailable",
                     "live_journals": ("recorded" if len(journaled_attempts) == len(attempts) and attempts
                                       else "partial" if journaled_attempts else "unavailable")},
        "journaled_attempts": journaled_attempts, "provenance": provenance(),
        "artifacts": artifacts, "missing": missing,
    }
    write_json(root / "manifest.json", manifest)
    return manifest


def verify_manifest(path: str | Path, *, episode_id: str | None = None,
                    contract_sha256: str | None = None) -> list[dict]:
    path = Path(path)
    root = path.parent.resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [{"path": path.name, "reason": "invalid_manifest"}]
    if not isinstance(manifest, dict) or manifest.get("schema") != "workflowbench-evidence@1":
        return [{"path": path.name, "reason": "invalid_manifest"}]
    if not isinstance(manifest.get("artifacts"), list) or not isinstance(manifest.get("missing", []), list):
        return [{"path": path.name, "reason": "invalid_manifest"}]
    if (not isinstance(manifest.get("episode_id"), str) or not manifest["episode_id"]
            or not isinstance(manifest.get("contract_sha256"), str)
            or type(manifest.get("attempt_count")) is not int or manifest["attempt_count"] < 1
            or not isinstance(manifest.get("coverage"), dict)):
        return [{"path": path.name, "reason": "invalid_manifest"}]
    problems = [{"path": p, "reason": "missing"} for p in manifest.get("missing", [])]
    if episode_id is not None and episode_id != manifest["episode_id"]:
        problems.append({"path": path.name, "reason": "episode_mismatch"})
    if contract_sha256 is not None and contract_sha256 != manifest["contract_sha256"]:
        problems.append({"path": path.name, "reason": "contract_mismatch"})
    seen = set()
    for item in manifest.get("artifacts", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            problems.append({"path": path.name, "reason": "invalid_manifest"})
            continue
        name = item["path"]
        try:
            target = (root / name).resolve()
        except (OSError, ValueError):
            problems.append({"path": name, "reason": "invalid_path"})
            continue
        if name in seen or not target.is_relative_to(root) or target == path.resolve():
            problems.append({"path": name, "reason": "invalid_path"})
            continue
        seen.add(name)
        try:
            data = target.read_bytes()
        except OSError:
            problems.append({"path": name, "reason": "missing"})
            continue
        if hashlib.sha256(data).hexdigest() != item.get("sha256") or len(data) != item.get("bytes"):
            problems.append({"path": name, "reason": "hash_mismatch"})
    required = {"snapshot0.json", "snapshot1.json", "events.jsonl", "turns.jsonl",
                "grading.json", "result.json"}
    for index in range(manifest["attempt_count"]):
        required.update(f"attempt-{index:03d}/{name}" for name in
                        ("snapshot0.json", "snapshot1.json", "events.jsonl", "turns.jsonl", "attempt.json"))
    journaled = manifest.get("journaled_attempts", [])
    attempt_names = {f"attempt-{index:03d}" for index in range(manifest["attempt_count"])}
    if (not isinstance(journaled, list) or any(not isinstance(name, str) or name not in attempt_names
                                             for name in journaled)
            or len(set(journaled)) != len(journaled)):
        problems.append({"path": path.name, "reason": "invalid_manifest"})
        journaled = []
    journaled = set(journaled)
    if manifest["coverage"].get("live_journals") == "recorded":
        journaled.update(attempt_names)
    # The hashed attempt metadata also binds the live artifacts, so dropping
    # only the coverage declaration cannot silently erase required journals.
    for name in attempt_names:
        try:
            metadata = json.loads((root / name / "attempt.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(metadata, dict) and metadata.get("journal"):
            journaled.add(name)
    for name in journaled:
        required.update(f"{name}/{artifact}" for artifact in LIVE_ARTIFACTS)
    for absent in sorted(required - seen):
        problems.append({"path": absent, "reason": "not_declared"})
    if not seen:
        problems.append({"path": path.name, "reason": "empty_manifest"})
    return problems
