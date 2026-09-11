"""Prepare an exact-byte config repository; never touches tasks or publishes."""
import argparse
import hashlib
import json
from pathlib import Path

from wb_orchestrator.config_repository import safe_path, validate_files


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Migration destination must be empty")
    if destination == source or source in destination.parents:
        raise ValueError("Migration destination must be outside the source tree")
    files = {}
    for file in sorted(source.rglob("*")):
        if file.is_symlink():
            raise ValueError("Migration source cannot contain symlinks")
        if file.is_file():
            name = safe_path("config/" + file.relative_to(source).as_posix())
            files[name] = file.read_bytes()
    if not files:
        raise ValueError("Migration source has no configuration files")
    warnings = validate_files({name: raw.decode("utf-8") for name, raw in files.items()})
    # Preserve historical incomplete plans; list every issue rather than repairing
    # or silently excluding artifacts during migration.
    expected = {f"config/plans/achievable-50-{kind}.yaml: missing harness monarch-{variant}"
                for kind in ("request", "workflow") for variant in ("stock", "lab")}
    if any(w not in expected for w in warnings):
        raise ValueError("Migration validation failed: " + "; ".join(warnings))
    manifest = {"repository": "TestBoxLab/ailabls-benchmark-config", "files": {}, "warnings": warnings}
    for name, raw in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
        manifest["files"][name] = digest
    (destination / "migration.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Existing config directory")
    parser.add_argument("--destination", required=True, help="Empty associated repository directory")
    args = parser.parse_args()
    manifest = prepare(args.source, args.destination)
    print(json.dumps({"files": len(manifest["files"]), "warnings": manifest["warnings"]}, indent=2))
