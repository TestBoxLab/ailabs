"""Corpus tooling per BUILD-SPEC §2.8.

- import-ab: convert AB dataset rows (example_id/prompt/answer/info) into T0
  task files with contract_sha256 embedded. AB rows carry no expected_changes;
  imported tasks therefore run assertion-only until someone declares the dual
  invariant — the grader flags invariant_declared=False, never guesses.
- validate: the two CI jobs. no-op (every assertion fails on the pristine
  world) and oracle (the scripted oracle passes where one exists; tasks whose
  assertion types the oracle can't drive are reported oracle=unsupported, loud).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from grader.grade import grade
from grader.noop import validate_task
from runner.arms import OracleArm, _sf_updates_from_assertions
from wb_orchestrator.orchestrator import contract_hash
from wb_world.episode import Episode, load_task_file


def import_ab(domains: list[str], out_dir: str | Path) -> dict[str, Any]:
    from automationbench.domains import get_domain_dataset
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []
    for domain in domains:
        ds = get_domain_dataset(domain)
        for row in ds:
            info = row["info"] if isinstance(row["info"], dict) else json.loads(row["info"])
            task_name = info.get("task_name") or f"{domain}.{row['example_id']}"
            task = {
                "example_id": row["example_id"],
                "task": task_name,
                "prompt": row["prompt"],
                "answer": row.get("answer"),
                "info": {
                    "zapier_tools": info.get("zapier_tools", []),
                    "initial_state": info.get("initial_state", {}),
                    "assertions": info.get("assertions", []),
                    # AB doesn't declare the dual invariant; leave undeclared.
                    "expected_changes": info.get("expected_changes", []),
                    "allowed_changes": info.get("allowed_changes", []),
                },
            }
            task["contract_sha256"] = contract_hash(task)
            path = out / f"{task_name}.json"
            if path.exists() and json.loads(path.read_text()).get("contract_sha256") == task["contract_sha256"]:
                skipped.append(task_name)
                continue
            path.write_text(json.dumps(task, indent=1, default=str))
            written.append(task_name)
    return {"written": len(written), "unchanged": len(skipped),
            "tasks": written[:20] + (["..."] if len(written) > 20 else [])}


def _oracle_supported(task: dict[str, Any]) -> bool:
    try:
        handled = list(_sf_updates_from_assertions(task))
    except (KeyError, TypeError):
        return False   # assertion shape/field outside the scripted oracle's map
    return bool(handled) and len(handled) == len(task["info"].get("assertions", []))


def validate_corpus(task_dir: str | Path) -> dict[str, Any]:
    paths = sorted(Path(task_dir).glob("*.json"))
    results = []
    for p in paths:
        task = load_task_file(p)
        r: dict[str, Any] = {"task": task.get("task", p.stem), "file": p.name}
        embedded = task.get("contract_sha256")
        current = contract_hash(task)
        r["contract_hash"] = current
        r["contract_drift"] = bool(embedded) and embedded != current

        noop = validate_task(task)
        r["noop_ok"] = noop["ok"]
        if not noop["ok"]:
            r["noop_detail"] = {k: v for k, v in noop.items() if k != "ok"}

        r["invariant_declared"] = bool(task["info"].get("expected_changes"))

        if _oracle_supported(task):
            ep = Episode(task, episode_id=f"oracle-ci/{r['task']}")
            try:
                OracleArm().run(ep)
                g = grade(task, ep.snapshot0, ep.finish())
                r["oracle"] = "pass" if g["passed"] else "FAIL"
                if not g["passed"]:
                    r["oracle_detail"] = {"assertions": g["assertions_passed"],
                                          "invariant": g["invariant"]["passed"]}
            except Exception as e:
                r["oracle"] = "FAIL"
                r["oracle_detail"] = str(e)
        else:
            r["oracle"] = "unsupported"
        results.append(r)

    n_noop_bad = sum(not r["noop_ok"] for r in results)
    n_oracle_fail = sum(r["oracle"] == "FAIL" for r in results)
    n_unsupported = sum(r["oracle"] == "unsupported" for r in results)
    n_drift = sum(r["contract_drift"] for r in results)
    return {
        "n_tasks": len(results),
        "noop_failures": n_noop_bad,
        "oracle_failures": n_oracle_fail,
        "oracle_unsupported": n_unsupported,
        "invariant_undeclared": sum(not r["invariant_declared"] for r in results),
        "contract_drift": n_drift,
        "ok": n_noop_bad == 0 and n_oracle_fail == 0 and n_drift == 0,
        "results": results,
    }


def format_validation(v: dict[str, Any], verbose: bool = False) -> str:
    lines = [f"corpus: {v['n_tasks']} tasks | noop failures: {v['noop_failures']} | "
             f"oracle failures: {v['oracle_failures']} | oracle unsupported: {v['oracle_unsupported']} | "
             f"invariant undeclared: {v['invariant_undeclared']} | contract drift: {v['contract_drift']}",
             "OK" if v["ok"] else "FAIL"]
    for r in v["results"]:
        bad = (not r["noop_ok"]) or r["oracle"] == "FAIL" or r["contract_drift"]
        if bad or verbose:
            lines.append(f"  {'!' if bad else ' '} {r['task']}: noop={'ok' if r['noop_ok'] else 'FAIL'} "
                         f"oracle={r['oracle']} invariant_declared={r['invariant_declared']}"
                         + (" CONTRACT-DRIFT" if r["contract_drift"] else ""))
            for k in ("noop_detail", "oracle_detail"):
                if k in r:
                    lines.append(f"      {k}: {json.dumps(r[k], default=str)[:200]}")
    return "\n".join(lines)
