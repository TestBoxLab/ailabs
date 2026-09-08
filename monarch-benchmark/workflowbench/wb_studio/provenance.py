"""Inventory of the BRIDGE v2 + v9.12 dependency closure, hashed in its original layout.

The v9.12 report names one generated graph artifact. Its producer script
resolves every input relative to a project root that sat beside `ATLAS` and
`AutomationBench-repair` inside `Monarch_Main`. This module records, for each
component the producer needs and each record the report relies on, where it
was found, its hash, and whether the found copy can stand for the frozen
revision. It never regenerates the artifact: a regenerated graph only counts as
a historical reproduction when its hash matches the original manifest, and no
original manifest has been recovered.

    uv run --frozen python -m wb_studio.provenance --write

writes research/architectures/bridge-v2-v9.12/{source-manifest.json,provenance-report.md}.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from wb_arms import runtime_manifest as rm
from wb_results.evidence import write_json
from wb_studio.runtime_registry import BRIDGE_SETTINGS, RESEARCH_DIR

SCHEMA_VERSION = "ailabs-historical-bundle-inventory-v1"
DEFAULT_ROOTS = {"monarch_main": "C:/Users/Lucas Wakigawa/Monarch_Main",
                 "codex": "C:/Users/Lucas Wakigawa/Documents/Codex/2026-08-15/continue"}
UPSTREAM_SUITE_COMMIT = "4a8e1061254004d9dac807054eed33fad7d1ff14"

# Report claims are transcribed from Monarch_Report.html; none is recomputed here.
REPORT_CLAIMS = {
    "source": "Monarch_Main/Monarch_Report.html",
    "status": "unverified",
    "treatment": {"name": "Monarch v9.12", "model": "Claude Opus 5", "effort": "medium", "completed": 361, "tasks": 600, "cost_usd": 216.57},
    "control": {"name": "Bare", "model": "Claude Opus 5", "effort": "max", "completed": 289, "tasks": 600, "cost_usd": 235.63},
    "paired": {"wins": 128, "losses": 56},
    "graph_artifact": "config/monarch/graph-inline-v6-evalrepair10.json",
    "graph_coverage": {"actions": 216, "reviewed_tasks": 358},
    "run_manifests": "not recovered; the report says every component is named by hash in the run manifest",
    "separate_records": {
        "bridge_v2_july": "MONARCH_BRIDGE_V2_DIAGRAM.html, measured 7 July; atlas-monarch-v2 (ATLAS/docs/bridge/archive/BRIDGE_V2_PLAN.md)",
        "graph_inline_v8_august": "AUTOMATIONBENCH_ATTEMPTS_CATALOG.md: 322/591 vs 261/591 (Opus max); a different release and denominator",
    },
}

# What the producer script pins, transcribed from vendor-monarch-graph-inline-v6.ts.
RECOVERED_SETTINGS = {
    **BRIDGE_SETTINGS,
    "schema": "monarch-graph-inline-v6-evalrepair10.v1",
    "implementation_revision": "atlas-monarch-v8-1-p0-runtime-record-opus5-graph-inline-v6-evalrepair10-port-v2",
    "historical_treatment": "atlas-monarch-v8-1-p0-runtime-record-opus5-graph-inline-v6",
    "doctrine_constant": "AUTOMATIONBENCH_OPUS5_GRAPH_INLINE_V6_DOCTRINE (ATLAS/backend/scripts/dev/automationbench-shim.ts)",
    "reviewed_extensions": ["slack_find_user_by_id", "quickbooks_create_bank_deposit", "recruitee_jobCreate"],
    "source_freshness_rule": "unchanged actions reuse reviewed v6 cards; changed/added actions receive current source-pinned descriptions; product contexts of changed origins are replaced",
    "runtime_behaviours_not_in_graph": ["operator contract per model family", "declared work list", "write gates", "reconciliation", "pre-run retrieval delivery"],
}

# role, original layout (relative to the producer's project root or to Monarch_Main),
# candidate locations (templated on roots), and what the component is required for.
CLOSURE = [
    {"role": "graph_producer", "required_for": ["regeneration"],
     "layout": "<project-root>/scripts/vendor-monarch-graph-inline-v6.ts",
     "candidates": ["{codex}/vendor-patch-output/scripts/vendor-monarch-graph-inline-v6.ts",
                    "{codex}/vendor-patch-work/scripts/vendor-monarch-graph-inline-v6.ts"]},
    {"role": "source_freshness_audit", "required_for": ["regeneration"],
     "layout": "<project-root>/scripts/audit-monarch-source-freshness.py",
     "candidates": ["{codex}/vendor-patch-output/scripts/audit-monarch-source-freshness.py",
                    "{codex}/vendor-patch-work/scripts/audit-monarch-source-freshness.py"]},
    {"role": "actor_contract", "required_for": ["regeneration"],
     "layout": "<project-root>/.automationbench-local/suite-package-7a08b5047c89/actor/actor-contract.json", "candidates": []},
    {"role": "reviewed_tasks_358", "required_for": ["regeneration", "contamination_audit"],
     "layout": "Monarch_Main/AutomationBench-repair/adjudication/microscopic-brittleness-358-v1.json",
     "candidates": ["{monarch_main}/AutomationBench-repair/adjudication/microscopic-brittleness-358-v1.json",
                    "{monarch_main}/AB-5a0dea3-clean/adjudication/microscopic-brittleness-358-v1.json"]},
    {"role": "capability_manifest", "required_for": ["regeneration"],
     "layout": "Monarch_Main/ATLAS/backend/data/bench/bridge-v8/zapier-wired273-4a8e106-manifest-v1/capability-manifest-v1.json",
     "candidates": ["{monarch_main}/ATLAS/backend/data/bench/bridge-v8/zapier-wired273-4a8e106-manifest-v1/capability-manifest-v1.json"]},
    {"role": "reviewed_catalog", "required_for": ["regeneration"],
     "layout": "Monarch_Main/ATLAS/backend/config/bridge-v8-zapier-hard50-reviewed-capabilities-enriched-4a8e106-v2.json",
     "candidates": ["{monarch_main}/ATLAS/backend/config/bridge-v8-zapier-hard50-reviewed-capabilities-enriched-4a8e106-v2.json"]},
    {"role": "source_provenance", "required_for": ["regeneration"],
     "layout": "<project-root>/config/monarch/source-provenance-evalrepair10.json", "candidates": []},
    {"role": "generated_graph", "required_for": ["reproduction", "context_fixtures"],
     "layout": "<project-root>/config/monarch/graph-inline-v6-evalrepair10.json", "candidates": []},
    {"role": "capability_runtime", "required_for": ["regeneration"],
     "layout": "Monarch_Main/ATLAS/backend/scripts/dev/automationbench-capability-runtime.ts",
     "candidates": ["{monarch_main}/ATLAS/backend/scripts/dev/automationbench-capability-runtime.ts"]},
    {"role": "shim_doctrine", "required_for": ["regeneration", "reproduction"],
     "layout": "Monarch_Main/ATLAS/backend/scripts/dev/automationbench-shim.ts",
     "candidates": ["{monarch_main}/ATLAS/backend/scripts/dev/automationbench-shim.ts"]},
    {"role": "extension_source_slack", "required_for": ["regeneration"], "frozen_revision_sensitive": True,
     "layout": "Monarch_Main/AutomationBench-repair/automationbench/tools/zapier/slack/users.py",
     "candidates": ["{monarch_main}/AutomationBench-repair/automationbench/tools/zapier/slack/users.py"]},
    {"role": "extension_source_quickbooks", "required_for": ["regeneration"], "frozen_revision_sensitive": True,
     "layout": "Monarch_Main/AutomationBench-repair/automationbench/tools/zapier/quickbooks/deposits.py",
     "candidates": ["{monarch_main}/AutomationBench-repair/automationbench/tools/zapier/quickbooks/deposits.py"]},
    {"role": "extension_source_recruitee", "required_for": ["regeneration"], "frozen_revision_sensitive": True,
     "layout": "Monarch_Main/AutomationBench-repair/automationbench/tools/zapier/recruitee/actions.py",
     "candidates": ["{monarch_main}/AutomationBench-repair/automationbench/tools/zapier/recruitee/actions.py"]},
    {"role": "run_manifests_600", "required_for": ["reproduction"],
     "layout": "unknown: per-run manifests naming graph, prompts, grader and provider settings by hash", "candidates": []},
    {"role": "report", "required_for": ["claims"], "layout": "Monarch_Main/Monarch_Report.html",
     "candidates": ["{monarch_main}/Monarch_Report.html"]},
    {"role": "bridge_v2_diagram", "required_for": ["claims"], "layout": "Monarch_Main/MONARCH_BRIDGE_V2_DIAGRAM.html",
     "candidates": ["{monarch_main}/MONARCH_BRIDGE_V2_DIAGRAM.html"]},
    {"role": "attempts_catalog", "required_for": ["claims"], "layout": "Monarch_Main/docs/bridge/AUTOMATIONBENCH_ATTEMPTS_CATALOG.md",
     "candidates": ["{monarch_main}/docs/bridge/AUTOMATIONBENCH_ATTEMPTS_CATALOG.md"]},
    {"role": "smoke12_rehearsal", "required_for": ["claims"],
     "layout": "Monarch_Main/bench-host-state/runs/evalrepair10-smoke12-v1/rehearsal/result.json (zero-provider rehearsal, not scored evidence)",
     "candidates": ["{monarch_main}/bench-host-state/runs/evalrepair10-smoke12-v1/rehearsal/result.json"]},
]

# Git-tracked components: the suite revision the producer names, and the three
# extension sources at candidate commits before the evalrepair.11 cut.
GIT_COMPONENTS = [
    {"role": "suite_revision_evalrepair10", "required_for": ["regeneration", "reproduction"],
     "repository": "{monarch_main}/AB-5a0dea3-clean", "revision": "5a0dea3819d1922413ece8c57cf7aa178629b89c",
     "path": "pyproject.toml", "expect_contains": 'version = "1.0.6+evalrepair.10"'},
]
EXTENSION_PATHS = {"extension_source_slack": "automationbench/tools/zapier/slack/users.py",
                   "extension_source_quickbooks": "automationbench/tools/zapier/quickbooks/deposits.py",
                   "extension_source_recruitee": "automationbench/tools/zapier/recruitee/actions.py"}
CANDIDATE_REVISIONS = ["5a0dea3", "f7acf6a", "00a4fad", "41b0a84", "24588c2", "d18dce7"]


def _git_blob(repository: Path, revision: str, path: str) -> bytes | None:
    try:
        proc = subprocess.run(["git", "-C", str(repository), "show", f"{revision}:{path}"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _file_record(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path), "sha256": rm.file_sha256(path), "bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()}


def inventory(roots: dict | None = None, git=_git_blob) -> dict:
    roots = {k: str(Path(v)) for k, v in {**DEFAULT_ROOTS, **(roots or {})}.items()}
    entries = []
    for component in CLOSURE:
        found = [_file_record(Path(c.format(**roots))) for c in component["candidates"] if Path(c.format(**roots)).is_file()]
        status = "missing" if not found else "present_unpinned" if component.get("frozen_revision_sensitive") else "present"
        entry = {"role": component["role"], "layout": component["layout"], "required_for": component["required_for"],
                 "status": status, "found": found}
        if found and len({f["sha256"] for f in found}) > 1:
            entry["note"] = "Candidate copies differ; the producer's original input is not identified by content."
        entries.append(entry)
    for component in GIT_COMPONENTS:
        repository = Path(component["repository"].format(**roots))
        blob = git(repository, component["revision"], component["path"]) if repository.is_dir() else None
        entry = {"role": component["role"], "layout": f"{component['repository']}@{component['revision'][:7]}:{component['path']}",
                 "required_for": component["required_for"], "found": []}
        if blob is None:
            entry["status"] = "missing"
        else:
            text = blob.decode("utf-8", errors="replace")
            entry["status"] = "present" if component["expect_contains"] in text else "present_unpinned"
            entry["found"] = [{"path": f"{repository}@{component['revision']}:{component['path']}", "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}]
        entries.append(entry)
    repair = Path(roots["monarch_main"]) / "AutomationBench-repair"
    revisions = {}
    for revision in CANDIDATE_REVISIONS:
        hashes = {}
        for role, path in EXTENSION_PATHS.items():
            blob = git(repair, revision, path) if repair.is_dir() else None
            hashes[role] = hashlib.sha256(blob).hexdigest() if blob is not None else None
        revisions[revision] = hashes
    by_role = {e["role"]: e for e in entries}
    for role in EXTENSION_PATHS:
        current = {f["sha256"] for f in by_role[role]["found"]}
        by_role[role]["matching_revisions"] = sorted(r for r, h in revisions.items() if h.get(role) and h[role] in current)
    summary = {"present": sum(e["status"] == "present" for e in entries),
               "present_unpinned": sum(e["status"] == "present_unpinned" for e in entries),
               "missing": sum(e["status"] == "missing" for e in entries)}
    missing_required = [e["role"] for e in entries if e["status"] == "missing" and set(e["required_for"]) & {"regeneration", "reproduction"}]
    reasons = [f"Historical source not fully recovered: {len(missing_required)} required components missing ({', '.join(missing_required)}).",
               "Regenerated bytes need original-manifest hash confirmation before they count as v9.12; the preset stays source_required."]
    readiness = rm.readiness("source_required", "not_applicable", "source_required", reasons)
    artifacts = {}
    for role in ("generated_graph", "actor_contract", "source_provenance", "capability_manifest", "reviewed_catalog", "shim_doctrine", "capability_runtime"):
        entry = by_role[role]
        artifacts[role] = {"status": "present" if entry["found"] else "missing", "sha256": entry["found"][0]["sha256"] if entry["found"] else None, "layout": entry["layout"]}
    manifest = rm.build("bridge-v2-v9.12",
                        source={"kind": "local", "repository": None, "directory": "Monarch_Main (ATLAS + AutomationBench-repair + producer project root)",
                                "commit": None, "patch_sha256": None, "lockfile": None, "image_digest": None,
                                "suite_revision": RECOVERED_SETTINGS["suite_revision"], "suite_upstream_commit": UPSTREAM_SUITE_COMMIT},
                        runtime={"entrypoint": None, "dependency_closure": [{"path": e["layout"], "role": e["role"], "status": e["status"]} for e in entries]},
                        evaluation={"track": "agentic-request", "provider": RECOVERED_SETTINGS["provider"], "model": RECOVERED_SETTINGS["model"],
                                    "effort": RECOVERED_SETTINGS["effort"], "harness": "atlas-automationbench-shim", "harness_version": RECOVERED_SETTINGS["implementation_revision"],
                                    "settings": {"note": "provider route, prompts, retrieval index/model and grader revision not recovered"}},
                        artifacts=artifacts, readiness_record=readiness,
                        notes="Historical identity. Not the stock product and not an Enterprise port.")
    return {"schema_version": SCHEMA_VERSION, "identity": "bridge-v2-v9.12", "generated_at": datetime.now(timezone.utc).isoformat(),
            "roots": roots, "entries": entries, "extension_hashes_by_revision": revisions, "summary": summary,
            "missing_required": missing_required, "readiness": readiness, "report_claims": REPORT_CLAIMS,
            "recovered_settings": RECOVERED_SETTINGS, "runtime_manifest": manifest}


def report(record: dict) -> str:
    lines = ["# BRIDGE v2 + v9.12 provenance inventory", "",
             f"Generated {record['generated_at']}. Identity `{record['identity']}`. Readiness: source `{record['readiness']['source']}`, runtime `{record['readiness']['runtime']}`.",
             "", "Report claims (361/600 vs 289/600) are transcribed, not recomputed. Regeneration without the original manifest hash is a reconstructed candidate, never a reproduction.", "",
             "| Role | Status | Layout | Hash |", "|---|---|---|---|"]
    for entry in record["entries"]:
        digest = ", ".join(f["sha256"][:12] for f in entry["found"]) or "—"
        extra = f" (matches repair revisions: {', '.join(entry['matching_revisions']) or 'none of the candidates'})" if "matching_revisions" in entry else ""
        lines.append(f"| {entry['role']} | {entry['status']} | `{entry['layout']}` | {digest}{extra} |")
    lines += ["", f"Summary: {record['summary']}", "", "Missing components required for regeneration or reproduction: " + (", ".join(record["missing_required"]) or "none"), "",
              "## Recovered settings", ""]
    lines += [f"- {k}: {v}" for k, v in record["recovered_settings"].items()]
    lines += ["", "## Frozen suite revision", "",
              "The producer names suite `1.0.6+evalrepair.10`; `AB-5a0dea3-clean` at 5a0dea3 carries that version string. The repair checkout advanced to evalrepair.17, so its working files cannot stand in for the frozen revision. Extension-source hashes are listed per candidate commit before the evalrepair.11 cut (2026-08-15 19:14) so the exact producer-time revision can be settled by matching the original artifact's recorded hashes.", ""]
    for revision, hashes in record["extension_hashes_by_revision"].items():
        lines.append(f"- {revision}: " + ", ".join(f"{role.split('_')[-1]}={h[:12] if h else 'n/a'}" for role, h in hashes.items()))
    lines += ["", "## Next recovery steps", "",
              "1. Locate the producer's project root (a sibling of ATLAS with `.automationbench-local/suite-package-7a08b5047c89` and `config/monarch/`) in backups or deleted worktrees.",
              "2. Recover `graph-inline-v6-evalrepair10.json` and its `artifactSha256`; recover the 600-task run manifests the report refers to.",
              "3. Only then regenerate with the producer against the frozen revision and compare hashes.", ""]
    return "\n".join(lines)


def write_bundle(directory: Path, roots: dict | None = None) -> dict:
    record = inventory(roots)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "source-manifest.json", record)
    (directory / "provenance-report.md").write_text(report(record), encoding="utf-8", newline="\n")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the research bundle inventory")
    parser.add_argument("--directory", default=str(RESEARCH_DIR / "architectures" / "bridge-v2-v9.12"))
    parser.add_argument("--monarch-main", default=DEFAULT_ROOTS["monarch_main"])
    parser.add_argument("--codex", default=DEFAULT_ROOTS["codex"])
    args = parser.parse_args(argv)
    roots = {"monarch_main": args.monarch_main, "codex": args.codex}
    record = write_bundle(Path(args.directory), roots) if args.write else inventory(roots)
    print(json.dumps({"summary": record["summary"], "missing_required": record["missing_required"], "readiness": record["readiness"]}, indent=2))


if __name__ == "__main__":
    main()
