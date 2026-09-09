"""Schema-versioned executable runtime manifests.

A manifest names exactly what would execute for one comparison version: the
source revision and build inputs, the evaluation track, provider/model/effort
and harness identity, the treatment artifacts (graph, contract, retrieval,
prompts, compiler) and the public tool/world surface. It is frozen before a
launch and its identity hash moves whenever any executable input moves.

Readiness is reported on three separate axes so that a resolved revision is
never mistaken for a served build, and a published definition is never
mistaken for an executed architecture:

    source       resolved | frozen | source_required | unavailable | not_applicable
    publication  published | draft | not_applicable
    runtime      ready | adapter_required | blocked | unsupported | source_required | preparation_required

Only ``runtime == "ready"`` makes a version launchable. Nothing in this module
launches, builds or contacts a provider.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

SCHEMA_VERSION = "ailabs-runtime-manifest-v1"
EVIDENCE_SCHEMA_VERSION = "workflowbench-evidence@1"

IDENTITIES = ("without-monarch", "default-monarch-enterprise", "bridge-v2-v9.12", "blueprint")
TRACKS = ("agentic-request", "create-and-run")
SOURCE_STATES = ("resolved", "frozen", "source_required", "unavailable", "not_applicable")
PUBLICATION_STATES = ("published", "draft", "not_applicable")
RUNTIME_STATES = ("ready", "adapter_required", "blocked", "unsupported", "source_required", "preparation_required")
EFFORTS = ("default", "none", "low", "medium", "high", "xhigh", "max")

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Fields that carry executable identity. Everything else (readiness, notes,
# timestamps, display URLs) may change without changing what would execute.
_IDENTITY_FIELDS = ("identity", "source", "runtime", "evaluation", "artifacts", "public_surface", "budget_policy")


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def readiness(source: str, publication: str, runtime: str, reasons=()) -> dict:
    """One readiness record; unknown states are rejected rather than displayed."""
    if source not in SOURCE_STATES:
        raise ValueError(f"Unknown source readiness {source!r}")
    if publication not in PUBLICATION_STATES:
        raise ValueError(f"Unknown publication readiness {publication!r}")
    if runtime not in RUNTIME_STATES:
        raise ValueError(f"Unknown runtime readiness {runtime!r}")
    reasons = [str(r) for r in reasons if str(r).strip()]
    if runtime != "ready" and not reasons:
        raise ValueError("A version that cannot launch must say why")
    return {"source": source, "publication": publication, "runtime": runtime,
            "launchable": runtime == "ready", "reasons": reasons}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_source(source: dict) -> None:
    _require(isinstance(source, dict), "Manifest source must be an object")
    kind = source.get("kind")
    _require(kind in ("git", "local", "none"), "Manifest source kind must be git, local or none")
    if kind == "git":
        _require(isinstance(source.get("repository"), str) and source["repository"].startswith("https://"),
                 "Git sources need an https repository URL")
        commit = source.get("commit")
        _require(commit is None or (isinstance(commit, str) and _COMMIT.fullmatch(commit)),
                 "Git source commits must be full 40-hex SHAs")
    for key in ("patch_sha256", "image_digest"):
        value = source.get(key)
        _require(value is None or (isinstance(value, str) and value), f"Manifest source {key} must be a non-empty string or null")
    lockfile = source.get("lockfile")
    if lockfile is not None:
        _require(isinstance(lockfile, dict) and isinstance(lockfile.get("path"), str), "Lockfile records need a path")


def _validate_evaluation(evaluation: dict) -> None:
    _require(isinstance(evaluation, dict), "Manifest evaluation must be an object")
    _require(evaluation.get("track") in TRACKS, "Unknown evaluation track")
    for key in ("provider", "model", "harness"):
        value = evaluation.get(key)
        _require(value is None or (isinstance(value, str) and value.strip()), f"Evaluation {key} must be a non-empty string or null")
    _require(evaluation.get("effort") in EFFORTS, "Unsupported reasoning effort")
    settings = evaluation.get("settings", {})
    _require(isinstance(settings, dict), "Evaluation settings must be an object of non-default settings")


def _validate_artifacts(artifacts: dict) -> None:
    _require(isinstance(artifacts, dict), "Manifest artifacts must be an object")
    for name, record in artifacts.items():
        _require(isinstance(name, str) and name, "Artifact names must be strings")
        _require(isinstance(record, dict), f"Artifact {name} must be an object")
        digest = record.get("sha256")
        _require(digest is None or (isinstance(digest, str) and _SHA256.fullmatch(digest)), f"Artifact {name} sha256 must be 64 hex characters or null")
        _require(record.get("status") in ("present", "missing", "reconstructed"), f"Artifact {name} needs a status: present, missing or reconstructed")
        if record["status"] == "present":
            _require(digest is not None, f"A present artifact ({name}) must carry its hash")


def validate(manifest: dict) -> dict:
    _require(isinstance(manifest, dict), "Manifest must be an object")
    _require(manifest.get("schema_version") == SCHEMA_VERSION, "Unsupported manifest schema")
    _require(manifest.get("identity") in IDENTITIES, "Unknown manifest identity")
    _validate_source(manifest.get("source"))
    _validate_evaluation(manifest.get("evaluation"))
    _validate_artifacts(manifest.get("artifacts", {}))
    runtime = manifest.get("runtime", {})
    _require(isinstance(runtime, dict), "Manifest runtime must be an object")
    closure = runtime.get("dependency_closure", [])
    _require(isinstance(closure, list) and all(isinstance(c, dict) and isinstance(c.get("path"), str) for c in closure),
             "Dependency closure entries need a path")
    surface = manifest.get("public_surface", {})
    _require(isinstance(surface, dict), "Manifest public surface must be an object")
    for key, value in surface.items():
        _require(value is None or (isinstance(value, str) and _SHA256.fullmatch(value)), f"Public surface {key} must be a sha256 or null")
    ready = manifest.get("readiness")
    readiness(ready["source"], ready["publication"], ready["runtime"], ready.get("reasons", []))
    _require(manifest.get("identity_sha256") == identity_hash(manifest), "Manifest identity hash does not match its executable inputs")
    return manifest


def identity_hash(manifest: dict) -> str:
    """Hash of every executable input; readiness and timestamps never move it."""
    return sha256_json({key: manifest.get(key) for key in _IDENTITY_FIELDS})


def build(identity: str, *, source: dict, evaluation: dict, readiness_record: dict, runtime: dict | None = None,
          artifacts: dict | None = None, public_surface: dict | None = None, budget_policy: dict | None = None,
          parent: str | None = None, notes: str = "") -> dict:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "identity": identity,
        "source": deepcopy(source),
        "runtime": deepcopy(runtime or {"entrypoint": None, "dependency_closure": []}),
        "evaluation": {"settings": {}, "harness": None, "harness_version": None, **deepcopy(evaluation)},
        "artifacts": deepcopy(artifacts or {}),
        "public_surface": deepcopy(public_surface or {}),
        "budget_policy": deepcopy(budget_policy or {}),
        "parent": parent,
        "notes": str(notes)[:2000],
        "readiness": deepcopy(readiness_record),
        "frozen": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest["identity_sha256"] = identity_hash(manifest)
    return validate(manifest)


def freeze(manifest: dict) -> dict:
    """Pin a manifest before launch: moving refs are refused, identity recomputed.

    A frozen manifest is what a run records; a later refresh produces a new
    manifest rather than mutating this one.
    """
    validate(manifest)
    source = manifest["source"]
    if source["kind"] == "git":
        _require(isinstance(source.get("commit"), str), "Cannot freeze a git source without a full commit SHA")
    frozen = deepcopy(manifest)
    frozen["frozen"] = True
    frozen["frozen_at"] = datetime.now(timezone.utc).isoformat()
    if frozen["readiness"]["source"] == "resolved":
        frozen["readiness"]["source"] = "frozen"
    frozen["identity_sha256"] = identity_hash(frozen)
    return frozen


def assert_unchanged(manifest: dict) -> None:
    """Refuse to continue on a manifest whose executable inputs drifted."""
    if manifest.get("identity_sha256") != identity_hash(manifest):
        raise ValueError("Runtime manifest changed after it was recorded; refusing to continue on a moved identity")
