"""Measures for reports: pure functions over stored results and events.

Nothing here grades. The grader's verdict, checks and recorded changes are
counted as they were stored; unknown stays unknown. Every function takes plain
dicts (job results, journal events) so reports and tests share one path.

Vocabulary: a *setup* is one competitor in a run (`result["model"]`, the arm
id); an *attempt* is one task by one setup once; *evaluated* attempts exclude
infrastructure interruptions, which are counted separately.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from itertools import combinations

class Sentinel:
    """Distinct singleton sentinel for measures where 0, None, and unknown must not collide."""
    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return f"<{self.name}>"

    def __str__(self) -> str:
        return self.name

    def __bool__(self) -> bool:
        return False


NOT_APPLICABLE = Sentinel("not_applicable")
not_applicable = NOT_APPLICABLE
UNKNOWN = Sentinel("unknown")
unknown = UNKNOWN


def is_not_applicable(val) -> bool:
    return val is NOT_APPLICABLE or val == "not_applicable" or val == "n/a"


def is_unknown(val) -> bool:
    return val is UNKNOWN or val == "unknown"


DONE_CLAIM = re.compile(r"\b(done|completed?|finished|success(?:ful|fully)?|updated|created|sent|resolved|processed)\b", re.I)
BARE_HINT = re.compile(r"\bbare\b", re.I)



def is_infrastructure(result) -> bool:
    return str(result.get("termination", "")).startswith("infra:")


def known_cost(result):
    value = result.get("cost_usd")
    flags = result.get("flags") or []
    if value is None or "billing=unknown" in flags or "cost_missing" in flags:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def wilson(passed: int, attempts: int, z: float = 1.96):
    """95 % Wilson score interval as (low, high); None when nothing was evaluated."""
    if attempts <= 0:
        return None, None
    p = passed / attempts
    denominator = 1 + z * z / attempts
    centre = (p + z * z / (2 * attempts)) / denominator
    margin = z * math.sqrt(p * (1 - p) / attempts + z * z / (4 * attempts * attempts)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def by_setup(results):
    groups = defaultdict(list)
    for result in results:
        groups[result["model"]].append(result)
    return dict(groups)


def evaluated(rows):
    return [r for r in rows if not is_infrastructure(r)]


def pass_rate(rows) -> dict:
    valid = evaluated(rows)
    passed = sum(bool(r.get("passed")) for r in valid)
    low, high = wilson(passed, len(valid))
    return {"passed": passed, "attempts": len(valid), "infrastructure": len(rows) - len(valid),
            "rate": passed / len(valid) if valid else None, "low": low, "high": high}


def pass_k(rows) -> dict:
    """Share of tasks whose every repetition passed. Only meaningful when a
    setup ran each task more than once; otherwise k is None and the report
    says so instead of showing a trivial value."""
    per_task = defaultdict(list)
    for r in evaluated(rows):
        per_task[r["task"]].append(bool(r.get("passed")))
    if not per_task:
        return {"k": None, "tasks": 0, "all_passed": 0, "rate": None}
    k = min(len(v) for v in per_task.values())
    if k < 2:
        return {"k": None, "tasks": len(per_task), "all_passed": None, "rate": None}
    all_passed = sum(all(v) for v in per_task.values())
    return {"k": k, "tasks": len(per_task), "all_passed": all_passed, "rate": all_passed / len(per_task)}


def objective_share(rows) -> dict:
    """Checks passed over checks defined, per attempt, then averaged. The
    scope check (allowed_changes_only) is a separate measure."""
    shares = []
    for r in evaluated(rows):
        checks = [c for c in (r.get("checks") or []) if c.get("type") != "allowed_changes_only"]
        if checks:
            shares.append(sum(bool(c.get("passed")) for c in checks) / len(checks))
    return {"attempts": len(shares), "mean": sum(shares) / len(shares) if shares else None}


def violations(rows) -> dict:
    valid = evaluated(rows)
    count = sum(len(r.get("unexpected_changes") or []) for r in valid)
    with_any = sum(bool(r.get("unexpected_changes")) for r in valid)
    return {"changes": count, "attempts_with_changes": with_any, "attempts": len(valid),
            "per_attempt": count / len(valid) if valid else None}


def claims_completion(result: dict) -> bool:
    """Whether a failed attempt's competitor-produced output claims completion.

    Restricted to competitor-produced output:
    - Excludes attempts that did not complete normally (e.g. agent_error, turn limit, timeout),
      which produce no completion claim.
    - Excludes request/prompt text echoed back alongside or instead of output.
    """
    if result.get("passed"):
        return False
    if result.get("termination") != "completed":
        return False
    output = result.get("output")
    if not isinstance(output, str) or not output.strip():
        return False
    prompt = result.get("prompt") or result.get("request") or result.get("brief") or result.get("input")
    if prompt:
        prompt_text = prompt[1].get("content") if isinstance(prompt, list) and len(prompt) > 1 and isinstance(prompt[1], dict) else str(prompt)
        if output.strip() == prompt_text.strip():
            return False
        output = output.replace(prompt_text, "")
    return bool(DONE_CLAIM.search(output))


def false_completion(rows) -> dict:
    """Failed attempts whose final message claims the work was done. The claim
    is a wording heuristic over competitor-produced output, named as such."""
    failed = [r for r in evaluated(rows) if not r.get("passed")]
    claimed = [r for r in failed if claims_completion(r)]
    return {"count": len(claimed), "failed": len(failed), "rate": len(claimed) / len(failed) if failed else None,
            "basis": "wording heuristic over the recorded final output"}


def turns(rows, events) -> dict:
    """Model turns (model_finished events) and tool calls per evaluated attempt."""
    per_attempt = defaultdict(int)
    for e in events:
        if e.get("type") == "model_finished" and e.get("task") and e.get("model"):
            per_attempt[(e["task"], e["model"])] += 1
    valid = evaluated(rows)
    tool_calls = [int(r.get("tool_calls") or 0) for r in valid]
    turn_counts = [per_attempt.get((r["task"], r["model"]), 0) for r in valid]
    return {"attempts": len(valid),
            "turns_mean": sum(turn_counts) / len(valid) if valid else None,
            "tool_calls_mean": sum(tool_calls) / len(valid) if valid else None,
            "turns_recorded": any(per_attempt.values())}


def cost(rows) -> dict:
    valid = evaluated(rows)
    known = [known_cost(r) for r in rows]
    unknown = sum(c is None for c in known)
    total = None if unknown else sum(known)
    passed = sum(bool(r.get("passed")) for r in valid)
    tokens = {"prompt": 0, "cached": 0, "cache_write": 0, "output": 0}
    for r in rows:
        for key in tokens:
            tokens[key] += int((r.get("tokens") or {}).get(key) or 0)
    tokens["uncached"] = max(0, tokens["prompt"] - tokens["cached"])
    return {"total": total, "unknown_attempts": unknown, "attempts": len(rows),
            "per_attempt": total / len(rows) if total is not None and rows else None,
            "per_pass": total / passed if total is not None and passed else None,
            "tokens": tokens}


def time(rows) -> dict:
    seconds = sorted(float(r.get("seconds") or 0) for r in evaluated(rows))
    if not seconds:
        return {"attempts": 0, "median": None, "p90": None, "max": None, "values": []}
    def quantile(q):
        index = min(len(seconds) - 1, max(0, int(round(q * (len(seconds) - 1)))))
        return seconds[index]
    return {"attempts": len(seconds), "median": quantile(.5), "p90": quantile(.9), "max": seconds[-1], "values": seconds}


def solved_tasks(rows) -> set:
    return {r["task"] for r in evaluated(rows) if r.get("passed")}


def overlap(groups) -> list:
    """Jaccard overlap of solved task sets for every pair of setups."""
    out = []
    for a, b in combinations(sorted(groups), 2):
        solved_a, solved_b = solved_tasks(groups[a]), solved_tasks(groups[b])
        union = solved_a | solved_b
        out.append({"a": a, "b": b, "both": len(solved_a & solved_b), "either": len(union),
                    "only_a": len(solved_a - solved_b), "only_b": len(solved_b - solved_a),
                    "jaccard": len(solved_a & solved_b) / len(union) if union else None})
    return out


def sign_test(wins: int, losses: int):
    """Two-sided sign test p-value for paired wins against losses; ties dropped."""
    n = wins + losses
    if n == 0:
        return None
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired(rows, baseline_rows, task_hashes=None, baseline_hashes=None) -> dict:
    """Per-task pass difference against a baseline on identical task sets.
    A task counts once per side: passed if any evaluated repetition passed
    matches pass rate semantics only when k is 1, so repetitions are compared
    by per-task pass share."""
    def share(group):
        per_task = defaultdict(list)
        for r in evaluated(group):
            per_task[r["task"]].append(bool(r.get("passed")))
        return {t: sum(v) / len(v) for t, v in per_task.items()}
    mine, theirs = share(rows), share(baseline_rows)
    common = sorted(set(mine) & set(theirs))
    identical = set(mine) == set(theirs) and bool(common)
    if task_hashes is not None and baseline_hashes is not None:
        identical = identical and all(task_hashes.get(t) == baseline_hashes.get(t) for t in common)
    if not identical:
        return {"comparable": False, "reason": "task sets differ" if set(mine) != set(theirs) else "task definitions differ",
                "tasks": len(common), "wins": None, "losses": None, "ties": None, "delta": None, "p_value": None, "per_task": []}
    per_task = [{"task": t, "setup": mine[t], "baseline": theirs[t], "delta": mine[t] - theirs[t]} for t in common]
    wins = sum(p["delta"] > 0 for p in per_task)
    losses = sum(p["delta"] < 0 for p in per_task)
    ties = len(per_task) - wins - losses
    delta = sum(p["delta"] for p in per_task) / len(per_task)
    return {"comparable": True, "reason": None, "tasks": len(common), "wins": wins, "losses": losses, "ties": ties,
            "delta": delta, "p_value": sign_test(wins, losses), "per_task": per_task}


def baseline_id(job):
    """The Bare setup of a run when there is one: a native harness without an
    architecture, else the API control, else nothing."""
    arms = [a for a in (job.get("settings") or {}).get("arms") or [] if a.get("kind") != "scripted" and a.get("id") not in ("oracle", "sloppy", "null")]
    for arm in arms:
        if arm.get("kind") == "native" and arm.get("version") == "without-monarch":
            return arm["id"]
    for arm in arms:
        if arm.get("kind") == "native" or BARE_HINT.search(str(arm.get("name", ""))) or BARE_HINT.search(str(arm.get("id", ""))):
            return arm["id"]
    for arm in arms:
        if arm.get("id") == "without-monarch" or arm.get("version") == "without-monarch":
            return arm["id"]
    return None


def setup_names(job) -> dict:
    """The name a report prints for each competitor. An id nobody named is
    resolved the same way the rest of the Studio resolves it, so an internal
    token (`oracle`) never reaches a page."""
    from wb_studio.runtime_registry import display_name
    settings = job.get("settings") or {}
    names = {arm["id"]: arm.get("name") or display_name(arm["id"]) for arm in settings.get("arms") or []}
    for model in settings.get("models") or []:
        names.setdefault(model, display_name(model))
    return names


def run_measures(job, events) -> dict:
    """Every measure for one run, per setup, plus pairs against the baseline."""
    results = job.get("results") or []
    groups = by_setup(results)
    settings = job.get("settings") or {}
    setups = [arm["id"] for arm in settings.get("arms") or []] or list(settings.get("models") or []) or sorted(groups)
    names = setup_names(job)
    baseline = baseline_id(job)
    planned = len(settings.get("tasks") or []) * len(setups)
    recorded = {(r["task"], r["model"]) for r in results}
    per_setup = {}
    for setup in setups:
        rows = groups.get(setup, [])
        per_setup[setup] = {
            "id": setup, "name": names.get(setup, setup), "is_baseline": setup == baseline,
            "pass": pass_rate(rows), "pass_k": pass_k(rows), "objective_share": objective_share(rows),
            "violations": violations(rows), "false_completion": false_completion(rows),
            "turns": turns(rows, events), "cost": cost(rows), "time": time(rows),
            "solved": sorted(solved_tasks(rows)),
            "paired": paired(rows, groups.get(baseline, [])) if baseline and setup != baseline and baseline in groups else None,
        }
    return {"version": 1, "run": job.get("id"), "baseline": baseline, "setups": per_setup, "order": setups,
            "overlap": overlap({s: groups.get(s, []) for s in setups}),
            "planned_attempts": planned, "recorded_attempts": len(results),
            "unrecorded_attempts": max(0, planned - len({k for k in recorded if k[1] in setups})),
            "repetitions": max((pass_k(groups.get(s, [])).get("k") or 1) for s in setups) if setups else 1}

def run_counts(job, events) -> dict:
    """The Runs table's two numbers: mean model turns per evaluated attempt
    (None until a run records model turns) and attempts whose verdict recorded
    changes outside the permitted scope."""
    rows = job.get("results") or []
    turn, violation = turns(rows, events), violations(rows)
    return {"turns": turn["turns_mean"] if turn["turns_recorded"] else None,
            "violations": violation["attempts_with_changes"], "attempts": violation["attempts"]}
