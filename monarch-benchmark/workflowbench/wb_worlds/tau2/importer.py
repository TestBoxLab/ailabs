"""Import Sierra's unchanged task data; the unrelated PyPI tau2 is refused."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

DOMAINS = ("retail", "airline", "telecom")


def source_root(root=None):
    return Path(root or os.environ.get("WB_TAU2_ROOT", ".external/tau2-bench")).resolve()


def source_pin(root, split):
    root = Path(root)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if "github.com/sierra-research/tau2-bench" not in str(project.get("urls", {})):
        raise ValueError("tau2 must be the Sierra Research git checkout, not the unrelated PyPI chemistry package")
    version = project["version"]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (1, 0, 1):
        raise ValueError(f"tau2 {version} is not comparable; source version 1.0.1 or later is required")
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                           check=True, capture_output=True, text=True).stdout.strip()
    if dirty:
        raise ValueError("tau2 source checkout has tracked modifications; restore source integrity before importing")
    return {"package": "tau2", "version": version, "revision": revision, "split": split}


def domain_policy(data, domain):
    if domain == "telecom":
        return ("<main_policy>\n" + (data / "main_policy.md").read_text(encoding="utf-8")
                + "\n</main_policy>\n<tech_support_policy>\n"
                + (data / "tech_support_manual.md").read_text(encoding="utf-8")
                + "\n</tech_support_policy>")
    return (data / "policy.md").read_text(encoding="utf-8")


def convert_task(row, domain, pin, policy, *, approval_rule=None, data_hashes=None):
    basis = (row.get("evaluation_criteria") or {}).get("reward_basis", ["DB", "COMMUNICATE"])
    if "NL_ASSERTION" in basis:
        raise ValueError(f"tau2 task {row['id']} requires a paid natural-language judge; no budgeted source-judge route is configured")
    if not row.get("evaluation_criteria"):
        raise ValueError(f"tau2 task {row['id']} has no source evaluation criteria")
    rule = approval_rule or {}
    identifier = str(row["id"])
    safe_id = identifier
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", identifier):
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", identifier)[:64] + "-" + hashlib.sha256(identifier.encode()).hexdigest()[:16]
    task = {"task": f"tau2.{domain}.{safe_id}", "example_id": str(row["id"]),
            "prompt": [{"role": "system", "content": policy},
                       {"role": "user", "content":
                        f"You are a customer service agent in the {domain} domain. Follow the policy. "
                        f"Use POST /tau2-{domain}/send_message with a message field to greet the simulated customer, "
                        "obtain their request, ask questions, and communicate the outcome. The customer is a "
                        "pinned simulated participant available identically to every competitor. Do not assume "
                        "the request is complete until you have spoken with the customer."}],
            "source_ref": {"domain": domain, "task_id": str(row["id"]), "task": row,
                           "reward_basis": basis, "data_hashes": data_hashes or {}},
            "info": {"world": dict(pin), "initial_state": {}, "assertions": [],
                     "expected_changes": rule.get("expected_changes", []),
                     "allowed_changes": rule.get("allowed_changes", []),
                     "approval_rule_reviewed": bool(approval_rule)}}
    from wb_orchestrator.orchestrator import contract_hash
    task["contract_sha256"] = contract_hash(task)
    return task


def import_tau2(domains, out_dir, *, root=None, split="base", limit=None, task_ids=None, rules=None):
    root = source_root(root)
    domains = list(DOMAINS) if domains == ["all"] else list(domains)
    unknown = set(domains) - set(DOMAINS)
    if unknown:
        raise ValueError(f"unsupported tau2 domains {sorted(unknown)}; supported: {DOMAINS}")
    if len(domains) > 1 and "{domain}" not in str(out_dir):
        raise ValueError("several tau2 domains need {domain} in --out")
    written, excluded = [], []
    for domain in domains:
        pin = source_pin(root, f"{domain}/{split}")
        data = root / "data/tau2/domains" / domain
        rows = json.loads((data / "tasks.json").read_text(encoding="utf-8"))
        splits = json.loads((data / "split_tasks.json").read_text(encoding="utf-8"))
        if split not in splits:
            raise ValueError(f"tau2 {domain} has no split {split!r}; available: {sorted(splits)}")
        selected = set(map(str, splits[split]))
        if task_ids is not None:
            requested = set(map(str, task_ids))
            if requested - selected:
                raise ValueError(f"tau2 tasks {sorted(requested - selected)} are not in {domain}/{split}")
            selected &= requested
        policy = domain_policy(data, domain)
        files = (("db.toml", "user_db.toml", "main_policy.md", "tech_support_manual.md", "tasks.json", "split_tasks.json")
                 if domain == "telecom" else ("db.json", "policy.md", "tasks.json", "split_tasks.json"))
        hashes = {name: hashlib.sha256((data / name).read_bytes()).hexdigest()
                  for name in files}
        out = Path(str(out_dir).replace("{domain}", domain))
        pending, domain_exclusions = [], []
        for row in rows:
            if str(row["id"]) not in selected or (limit is not None and len(pending) >= limit):
                continue
            if str(row["id"]) not in (rules or {}):
                domain_exclusions.append({"task_id": str(row["id"]), "reason": "No reviewed task-specific permitted-change rule"})
                continue
            try:
                task = convert_task(row, domain, pin, policy, approval_rule=(rules or {}).get(str(row["id"])), data_hashes=hashes)
            except ValueError as exc:
                domain_exclusions.append({"task_id": str(row["id"]), "reason": str(exc)})
                continue
            path = out / f"{task['task']}.json"
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != task:
                raise ValueError(f"refusing to overwrite a frozen tau2 task: {path}")
            pending.append((path, task))
        manifest = {"world": pin, "tasks": [path.name for path, _ in pending], "exclusions": domain_exclusions}
        manifest_path = out / "MANIFEST.yaml"
        if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError(f"refusing to overwrite a frozen tau2 manifest: {manifest_path}")
        out.mkdir(parents=True, exist_ok=True)
        for path, task in pending:
            if not path.exists():
                path.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            written.append(str(path))
        if not manifest_path.exists():
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        excluded.extend(domain_exclusions)
    return {"written": len(written), "paths": written, "exclusions": excluded}
