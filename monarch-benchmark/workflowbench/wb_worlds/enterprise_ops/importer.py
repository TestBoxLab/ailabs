"""Freeze unmodified source rows plus reviewed WorkflowBench permitted-change rules."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import yaml

from wb_world.episode import contract_hash

SOURCE_REVISION = "271f2c357f763376997dfd16807fcde2474ae41b"
DATASET_REVISION = "c8e538eae8a6205294f0a86675fefdc1fac408f6"
RUNTIME_IMAGES = {"gym-itsm-mcp": "shivakrishnareddyma225/enterpriseops-gym-mcp-itsm@sha256:a234ae3fb7cee196ba25e6b9957969dea829919b6e8271dddae128f065aaf39f"}
DOMAINS = ("calendar", "csm", "drive", "email", "hr", "hybrid", "itsm", "teams")
MODES = ("oracle", "plus_5_tools", "plus_10_tools", "plus_15_tools")


def _list(value):
    return json.loads(value) if isinstance(value, str) else value


def _save(path, value):
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    if path.exists():
        raise ValueError(f"refusing to replace frozen input {path}; choose a new output directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _download(domain, mode, revision):
    # This optional import belongs only to acquisition, never runtime or grading.
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("EnterpriseOps import needs the datasets package or explicit recorded rows") from exc
    return list(load_dataset("ServiceNow-AI/EnterpriseOps-Gym", mode, split=domain, revision=revision))


def import_eog(domains, out_dir, *, mode="oracle", limit=None, reviewed_rules=None,
               revision=DATASET_REVISION, source_revision=SOURCE_REVISION,
               rows=None, seed_root=None):
    """Refuse mutable pins and exclude tasks with no reviewed approval rule.

    Source checks and source prompts remain byte-for-byte strings from the row.
    The manifest is next to, rather than inside, the task directory so normal
    task enumeration cannot mistake an import report for a benchmark task.
    """
    if not all(re.fullmatch(r"[0-9a-f]{40}", str(pin)) for pin in (revision, source_revision)):
        raise ValueError("source and dataset revision must be immutable full Git commits")
    if domains == ["all"]:
        domains = list(DOMAINS)
    if not domains or set(domains) - set(DOMAINS):
        raise ValueError(f"domains must be drawn from {DOMAINS}")
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    if isinstance(reviewed_rules, (str, Path)):
        reviewed_rules = yaml.safe_load(Path(reviewed_rules).read_text(encoding="utf-8"))
    rules = reviewed_rules or {}
    if not isinstance(rules, dict):
        raise ValueError("reviewed_rules must map source task IDs to reviewed rules")
    root = Path(seed_root or os.environ.get("WB_EOG_DBS", ".external/enterprise-ops-dbs")).resolve()
    result = {"written": [], "unchanged": [], "excluded": []}
    frozen = []
    for domain in domains:
        candidates = [r.get("row", r) for r in rows] if rows is not None else _download(domain, mode, revision)
        count = 0
        for row in sorted(candidates, key=lambda r: r["task_id"]):
            if row.get("domain") != domain:
                continue
            task_id = row["task_id"]
            rule = rules.get(task_id)
            try:
                if not rule or not rule.get("reviewed_by") or not rule.get("rationale"):
                    raise ValueError("missing reviewed rule with reviewer and rationale")
                if rule.get("exclude"):
                    raise ValueError(rule["exclude"])
                if not isinstance(rule.get("expected_changes"), list) or not isinstance(rule.get("allowed_changes", []), list):
                    raise ValueError("reviewed rule needs explicit expected_changes and allowed_changes lists")
                servers = _list(row.get("gym_servers_config"))
                if not servers:
                    raise ValueError("missing server configuration")
                hashes = {}
                for server in servers:
                    relative = server.get("seed_database_file")
                    seed = (root / (relative or "")).resolve()
                    if not relative or not seed.is_relative_to(root) or not seed.is_file():
                        raise ValueError(f"missing seed database {relative}")
                    hashes[server["mcp_server_name"]] = hashlib.sha256(seed.read_bytes()).hexdigest()
                verifiers = _list(row.get("verifiers"))
                if not verifiers:
                    raise ValueError("missing verifier")
                for check in verifiers:
                    if check.get("verifier_type") != "database_state":
                        raise ValueError("unsupported verifier: initial import accepts database_state only")
                    cfg = check.get("validation_config") or {}
                    if not cfg.get("query"):
                        raise ValueError("missing query in database_state verifier")
                    if cfg.get("comparison_type", "equals") not in ("equals", "greater_than", "less_than", "contains"):
                        raise ValueError("unsupported verifier comparison")
                    if check.get("gym_name") and check["gym_name"] not in hashes:
                        raise ValueError("verifier names a server absent from the task")
                task = {"task": task_id,
                        "prompt": [{"role": "system", "content": row["system_prompt"]},
                                   {"role": "user", "content": row["user_prompt"]}],
                        "apps": [], "assertions": [],
                        "source_ref": {"task_id": task_id, "domain": domain, "mode": mode,
                            "dataset": "ServiceNow-AI/EnterpriseOps-Gym", "dataset_revision": revision,
                            "source_revision": source_revision, "servers": servers, "verifiers": verifiers,
                            "selected_tools": _list(row.get("selected_tools", [])),
                            "restricted_tools": _list(row.get("restricted_tools", [])),
                            "seed_sha256": hashes,
                            "runtime_images": {s: RUNTIME_IMAGES[s] for s in hashes if s in RUNTIME_IMAGES}},
                        "info": {"world": {"package": "enterprise-ops-gym", "version": source_revision,
                                            "revision": revision, "split": f"{domain}/{mode}"},
                            "expected_changes": rule["expected_changes"],
                            "allowed_changes": rule.get("allowed_changes", []),
                            "approval_rule_reviewed": {"reviewed_by": rule["reviewed_by"], "rationale": rule["rationale"]}}}
                task["contract_sha256"] = contract_hash(task)
            except (ValueError, KeyError, TypeError) as exc:
                result["excluded"].append({"task": task_id, "reason": str(exc)})
                continue
            if limit is not None and count >= limit:
                result["excluded"].append({"task": task_id, "reason": "outside requested import limit"})
                continue
            dest = Path(str(out_dir).format(domain=domain)) / f"{task_id}.json"
            result["written" if _save(dest, task) else "unchanged"].append(str(dest))
            frozen.append({"task": task_id, "path": str(dest), "contract_sha256": task["contract_sha256"]})
            count += 1
    # Stable across idempotent calls; written/unchanged is call output only.
    manifest = Path(str(out_dir).replace("{domain}", "all") + ".manifest.yaml")
    _save(manifest, {"benchmark": "enterprise-ops-gym", "source_revision": source_revision,
                    "dataset_revision": revision, "mode": mode, "tasks": frozen,
                    "excluded": result["excluded"]})
    result["manifest"] = str(manifest)
    return result
