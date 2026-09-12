"""Paired stats per BUILD-SPEC §2.5. Stdlib only.

- McNemar (continuity-corrected) from per-(task, trial) W/L on the identical
  task set; b and c reported alongside p.
- pass_hat_k = comb(s, k) / comb(n, k) per task (tau2 verbatim), infra
  episodes excluded.
- SEM beside every mean; cluster bootstrap over an arbitrary cluster key
  (task_template x tenant for REAL mode).
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any, Callable, Iterable


def _chi2_sf_1df(x: float) -> float:
    # Survival function of chi-square with 1 df: erfc(sqrt(x/2)).
    return math.erfc(math.sqrt(x / 2.0))


def mcnemar(b: int, c: int) -> dict[str, Any]:
    """Continuity-corrected McNemar. b = A-pass/B-fail, c = A-fail/B-pass."""
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "statistic": 0.0, "p": 1.0}
    stat = (abs(b - c) - 1) ** 2 / n if n > 0 else 0.0
    stat = max(stat, 0.0)
    return {"b": b, "c": c, "statistic": round(stat, 6), "p": round(_chi2_sf_1df(stat), 6)}


def _is_infra(row: dict) -> bool:
    return str(row.get("termination", "")).startswith("infra:")


def _is_ungraded(row: dict) -> bool:
    return bool(row.get("ungraded")) or "grading=ungraded" in (row.get("flags") or [])


def _excluded(row: dict) -> bool:
    return _is_infra(row) or _is_ungraded(row)


def paired_wl(rows_a: list[dict], rows_b: list[dict]) -> dict[str, Any]:
    """Per-(task, trial) pairing on the identical task set. Infra episodes on
    either side drop the pair (the pair wasn't a fair comparison); so does an
    ungraded one, counted separately.

    Both drops are counted apart because they say different things to a reader.
    Infra is our machine failing; ungraded is a checker that could not answer. A
    round whose grading broke, reported as forty infra-dropped pairs, sends
    whoever reads it to look at the wrong thing -- and `arm_summary` already
    keeps the two apart.
    """
    suites = {r.get("suite") for r in rows_a + rows_b if r.get("suite")}
    if len(suites) > 1:
        raise ValueError("cannot pair different products/suites: " + ", ".join(sorted(suites)))
    key = lambda r: (r["task_id"], r["trial"])
    a = {key(r): r for r in rows_a}
    bmap = {key(r): r for r in rows_b}
    common = sorted(set(a) & set(bmap))
    b = c = both = neither = dropped_infra = dropped_ungraded = 0
    per_task: dict[str, dict[str, int]] = defaultdict(lambda: {"w": 0, "l": 0, "t": 0})
    for k in common:
        ra, rb = a[k], bmap[k]
        if _is_infra(ra) or _is_infra(rb):
            dropped_infra += 1
            continue
        if _is_ungraded(ra) or _is_ungraded(rb):
            dropped_ungraded += 1
            continue
        pa, pb = bool(ra["passed"]), bool(rb["passed"])
        if pa and not pb:
            b += 1; per_task[k[0]]["w"] += 1
        elif pb and not pa:
            c += 1; per_task[k[0]]["l"] += 1
        elif pa:
            both += 1; per_task[k[0]]["t"] += 1
        else:
            neither += 1; per_task[k[0]]["t"] += 1
    return {"pairs": len(common) - dropped_infra - dropped_ungraded,
            "dropped_infra": dropped_infra, "dropped_ungraded": dropped_ungraded,
            "wins": b, "losses": c, "both_pass": both, "neither_pass": neither,
            "mcnemar": mcnemar(b, c), "per_task": dict(per_task)}


def pass_hat_k(rows: list[dict], k: int) -> dict[str, Any]:
    """Per-task pass_hat_k, infra excluded; mean +/- SEM over tasks."""
    by_task: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        if not _excluded(r):
            by_task[r["task_id"]].append(bool(r["passed"]))
    per_task = {}
    for task, outcomes in sorted(by_task.items()):
        n, s = len(outcomes), sum(outcomes)
        if n < k:
            per_task[task] = None      # not enough non-infra trials; never guess
            continue
        per_task[task] = math.comb(s, k) / math.comb(n, k) if s >= k else 0.0
    vals = [v for v in per_task.values() if v is not None]
    return {"k": k, "per_task": per_task,
            "mean": round(sum(vals) / len(vals), 6) if vals else None,
            "sem": round(sem(vals), 6) if len(vals) > 1 else None,
            "n_tasks": len(vals)}


def sem(values: Iterable[float]) -> float:
    vals = list(values)
    n = len(vals)
    if n < 2:
        return 0.0
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return math.sqrt(var / n)


def mean_sem(values: Iterable[float]) -> dict[str, float | None]:
    vals = list(values)
    if not vals:
        return {"mean": None, "sem": None, "n": 0}
    return {"mean": round(sum(vals) / len(vals), 6),
            "sem": round(sem(vals), 6) if len(vals) > 1 else None, "n": len(vals)}


def cluster_bootstrap(rows: list[dict], value: Callable[[dict], float],
                      cluster: Callable[[dict], Any], n_boot: int = 2000,
                      seed: int = 0) -> dict[str, Any]:
    """Bootstrap the mean of value(row), resampling whole clusters
    (task_template x tenant for REAL mode)."""
    groups: dict[Any, list[float]] = defaultdict(list)
    for r in rows:
        groups[cluster(r)].append(value(r))
    keys = sorted(groups, key=str)
    if not keys:
        return {"mean": None, "ci95": None, "n_clusters": 0}
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample: list[float] = []
        for _ in keys:
            sample.extend(groups[rng.choice(keys)])
        means.append(sum(sample) / len(sample))
    means.sort()
    all_vals = [v for g in groups.values() for v in g]
    return {"mean": round(sum(all_vals) / len(all_vals), 6),
            "ci95": [round(means[int(0.025 * n_boot)], 6),
                     round(means[min(int(0.975 * n_boot), n_boot - 1)], 6)],
            "n_clusters": len(keys)}


def arm_summary(rows: list[dict]) -> dict[str, Any]:
    """Per-arm headline block: strict pass +/- SEM (clustered by task), cost,
    cache hit rate, infra rate. The report builder consumes this verbatim."""
    non_infra = [r for r in rows if not _excluded(r)]
    by_task: dict[str, list[float]] = defaultdict(list)
    for r in non_infra:
        by_task[r["task_id"]].append(1.0 if r["passed"] else 0.0)
    task_rates = [sum(v) / len(v) for v in by_task.values()]
    tp = sum((r.get("tokens") or {}).get("prompt", 0) for r in rows)
    tc = sum((r.get("tokens") or {}).get("cached", 0) for r in rows)
    cost = sum(r.get("cost_usd") or 0.0 for r in rows)
    return {"episodes": len(rows), "infra_episodes": sum(_is_infra(r) for r in rows),
            "ungraded_episodes": sum(_is_ungraded(r) for r in rows),
            "infra_rate": round(sum(_is_infra(r) for r in rows) / len(rows), 4) if rows else None,
            "strict_pass": mean_sem(task_rates),
            "cost_usd": round(cost, 6),
            "cost_per_episode": round(cost / len(rows), 6) if rows else None,
            "tokens_prompt": tp, "tokens_cached": tc,
            "cache_hit_rate": round(tc / tp, 4) if tp else None}
