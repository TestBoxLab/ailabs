"""Append-only offline grading revisions selected by a hash in the episode row.

Original run artifacts are never rewritten. Publication orders file, artifact
registration, then row selection. A crash can leave an unselected orphan, but
cannot select an unwritten file. This follows Store's single-writer contract;
files and SQLite are not one transaction. Hashes detect accidental corruption,
not coordinated malicious replacement of both database and evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from wb_results.evidence import EvidenceIntegrityError

_PREFIX = "grading_revision="
_REFERENCE = re.compile(r"grading_revision=v1:([0-9a-f]{32}):([0-9a-f]{64})\Z")
_FIELDS = ("passed", "assertions_passed", "invariant_passed", "invariant_declared",
           "check_results", "unexpected_changes", "n_changes", "termination")


def verdict(row: dict) -> dict:
    return {field: row[field] for field in _FIELDS}


def graded_verdict(grading: dict, termination: str) -> dict:
    return {"passed": grading["passed"] and termination == "completed",
            "assertions_passed": grading["assertions_passed"],
            "invariant_passed": grading["invariant"]["passed"],
            "invariant_declared": grading["invariant_declared"],
            "check_results": [{key: check[key] for key in ("type", "passed")}
                              for check in grading["assertion_results"]],
            "unexpected_changes": grading["invariant"]["unexpected_changes"],
            "n_changes": grading["n_changes"], "termination": termination}


def selected_reference(row: dict) -> str | None:
    references = [flag for flag in row.get("flags", []) if flag.startswith(_PREFIX)]
    if len(references) > 1 or (references and not _REFERENCE.fullmatch(references[0])):
        raise EvidenceIntegrityError("invalid grading revision reference")
    return references[0] if references else None


def inputs(artifacts: dict) -> dict:
    """Bind both bytes and selected paths; redirected snapshots are not inputs."""
    bindings = {}
    root = Path(artifacts["manifest"]).resolve().parent if artifacts.get("manifest") else None
    for kind in ("snapshot0", "snapshot1", "manifest", "grading", "result"):
        if kind not in artifacts:
            continue
        path = Path(artifacts[kind]).resolve()
        if root is not None and path != root / (kind + ".json"):
            raise EvidenceIntegrityError(f"redirected original artifact: {kind}")
        data = path.read_bytes()
        bindings[kind] = {"uri": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return bindings


def _original_verdict(artifacts: dict) -> dict | None:
    # Legacy runs without a manifest remain explicitly outside original-evidence
    # verification. New manifest-backed runs must match their frozen result.
    if "manifest" not in artifacts:
        return None
    path = Path(artifacts["manifest"]).parent / "result.json"
    return verdict(json.loads(path.read_text(encoding="utf-8"))["row"])


def validate_current(row: dict, artifacts: dict) -> dict:
    """Validate selected chain and DB verdict; return exact report drilldown."""
    try:
        if "evidence_incomplete" in row.get("flags", []):
            raise EvidenceIntegrityError("episode evidence is incomplete")
        reference = selected_reference(row)
        expected = verdict(row)
        original = _original_verdict(artifacts)
        if original is not None:
            inputs(artifacts)
        if reference is None:
            if original is not None and expected != original:
                raise EvidenceIntegrityError("DB verdict differs from original grading evidence")
            return {"kind": "original", "uri": artifacts.get("grading"),
                    "manifest": artifacts.get("manifest")}
        bindings = inputs(artifacts)
        if not {"snapshot0", "snapshot1"} <= bindings.keys():
            raise EvidenceIntegrityError("regrade snapshots are missing")
        root = Path(bindings["snapshot0"]["uri"]).parent
        seen = set()
        selected = None
        while reference is not None:
            match = _REFERENCE.fullmatch(reference) if isinstance(reference, str) else None
            if match is None or reference in seen:
                raise EvidenceIntegrityError("invalid or cyclic grading revision chain")
            seen.add(reference)
            revision_id, digest = match.groups()
            path = Path(artifacts["regrade:" + revision_id]).resolve()
            if path != root / "regrades" / (revision_id + ".json"):
                raise EvidenceIntegrityError("grading revision path is outside its episode")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise EvidenceIntegrityError("grading revision hash mismatch")
            record = json.loads(data)
            if (record["schema"] != "workflowbench-regrade@1"
                    or record["revision_id"] != revision_id
                    or record["episode_id"] != row["episode_id"]
                    or record["contract_sha256"] != row.get("contract_sha256")
                    or record["inputs"] != bindings or record["verdict"] != expected
                    or graded_verdict(record["grading"], expected["termination"]) != expected
                    or not isinstance(record["provenance"], dict)
                    or not record["provenance"].get("source_sha256")
                    or not isinstance(record["created_at"], str)):
                raise EvidenceIntegrityError("grading revision does not match its evidence or verdict")
            if selected is None:
                selected = {"kind": "regrade", "revision_id": revision_id, "uri": str(path),
                            "sha256": digest, "provenance": record["provenance"],
                            "original_manifest": artifacts.get("manifest")}
            expected = record["before"]
            reference = record["previous"]
        if original is not None and expected != original:
            raise EvidenceIntegrityError("grading chain does not start at original verdict")
        return selected
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise EvidenceIntegrityError(f"invalid grading evidence: {error}") from error


def publish(store, before: dict, row, grading: dict, artifacts: dict,
            input_bindings: dict, provenance: dict) -> None:
    """Write/register revision before selecting it; never overwrite an artifact."""
    validate_current(before, artifacts)
    if inputs(artifacts) != input_bindings:
        raise EvidenceIntegrityError("regrade inputs changed while grading")
    revision_id = uuid.uuid4().hex
    directory = Path(input_bindings["snapshot0"]["uri"]).parent / "regrades"
    directory.mkdir(exist_ok=True)
    path = directory / (revision_id + ".json")
    record = {"schema": "workflowbench-regrade@1", "revision_id": revision_id,
              "episode_id": row.episode_id, "contract_sha256": row.contract_sha256,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "previous": selected_reference(before), "before": verdict(before),
              "inputs": input_bindings, "provenance": provenance,
              "grading": grading, "verdict": verdict(row.model_dump(mode="json"))}
    data = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    reference = f"{_PREFIX}v1:{revision_id}:{hashlib.sha256(data).hexdigest()}"
    store.add_artifact(row.episode_id, "regrade:" + revision_id, str(path))
    row.flags = [flag for flag in row.flags if not flag.startswith(_PREFIX)] + [reference]
    store.record_episode(row)
