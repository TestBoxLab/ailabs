"""Run and round reports, assembled from stored records only.

A report reads verdict first: a grade against the Bare baseline, findings with
one number and one evidence link each, then the figures, the failures, the
cost, the caveats and the method. Numbers are always inserted by code; the
model narrative (analysis.json, when a run has one) fills prose slots and every
claim in it cites recorded events.

Audience: reports render for the public audience by default. Lab competitors
(names starting with `monarch-lab`, the same rule `wb report` enforces) never
appear outside the internal view, which marks them.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from wb_studio import caveats, measures
from wb_studio.reports import CATEGORIES

GRADES = ("Improvement", "Regression", "Tradeoff", "Tie", "Not comparable")
FINISHED = ("completed", "failed", "cancelled", "interrupted")


def is_lab(name) -> bool:
    return str(name or "").startswith("monarch-lab")


def visible_setups(job, audience) -> tuple[list, list]:
    arms = (job.get("settings") or {}).get("arms") or [{"id": m, "name": m, "kind": "runner"} for m in (job.get("settings") or {}).get("models") or []]
    shown, hidden = [], []
    for arm in arms:
        lab = is_lab(arm.get("id")) or is_lab(arm.get("name")) or arm.get("kind") == "lab"
        (hidden if lab and audience != "internal" else shown).append(arm["id"])
    return shown, hidden


def grade(setup, baseline) -> dict:
    """One word for the whole comparison, with its reason."""
    if not baseline or not setup or not setup.get("paired") or not setup["paired"]["comparable"]:
        reason = "no Bare baseline to compare against" if not baseline else (setup or {}).get("paired", {}).get("reason") or "no paired attempts"
        return {"grade": "Not comparable", "reason": reason}
    p = setup["paired"]
    cost_a, cost_b = setup["cost"]["per_attempt"], baseline["cost"]["per_attempt"]
    cost_worse = cost_a is not None and cost_b is not None and cost_b > 0 and cost_a > cost_b * 1.25
    cost_better = cost_a is not None and cost_b is not None and cost_a > 0 and cost_b > cost_a * 1.25
    better, worse = p["wins"] > p["losses"], p["losses"] > p["wins"]
    tally = f"better than Bare on {p['wins']} {'task' if p['wins'] == 1 else 'tasks'}, worse on {p['losses']}, the same on {p['ties']}"
    if better and cost_worse:
        return {"grade": "Tradeoff", "reason": f"{tally}, but each attempt cost more than 1.25 times what Bare's did"}
    if worse and cost_better:
        return {"grade": "Tradeoff", "reason": f"{tally}, but each attempt cost less than 0.8 times what Bare's did"}
    if better:
        return {"grade": "Improvement", "reason": tally}
    if worse:
        return {"grade": "Regression", "reason": tally}
    return {"grade": "Tie", "reason": tally}


def pct(value):
    return None if value is None else round(value * 100)


def fmt_money(value):
    return "unknown" if value is None else (f"${value:.4f}" if 0 < value < 0.01 else f"${value:.2f}")


def count_phrase(passed, attempts):
    return f"{passed} of {attempts}"


def runner_key(studio, arm):
    """(model, thinking) of a setup: the identity a Bare baseline must share to be reused."""
    from wb_studio.leaderboard import comparison_runner
    found = comparison_runner(studio, arm) if arm else None
    return (found["model"], found["effort"]) if found else None


def historical_baseline(studio, job, subject_id):
    """A Bare setup recorded in an earlier finished run on the same frozen tasks, with the
    same model and thinking setting as the subject, when this run has none. The newest
    such run wins; its Bare rows are reused, never re-run."""
    settings = job.get("settings") or {}
    arms = {a["id"]: a for a in settings.get("arms") or []}
    key = runner_key(studio, arms.get(subject_id))
    hashes, tasks = job.get("task_hashes") or {}, set(settings.get("tasks") or [])
    if not key or not hashes or not tasks:
        return None
    best = None
    for listed in studio.jobs():
        if listed["id"] == job.get("id") or listed.get("status") not in FINISHED:
            continue
        other = studio.job(listed["id"])
        other_settings = other.get("settings") or {}
        if other_settings.get("track", "agentic-request") != settings.get("track", "agentic-request"):
            continue
        bare = measures.baseline_id(other)
        if not bare or bare in arms:
            continue
        other_hashes = other.get("task_hashes") or {}
        if any(other_hashes.get(t) != hashes.get(t) for t in tasks):
            continue
        bare_arm = next((a for a in other_settings.get("arms") or [] if a["id"] == bare), None)
        if runner_key(studio, bare_arm) != key:
            continue
        rows = [r for r in other.get("results") or [] if r.get("model") == bare and r.get("task") in tasks]
        if not rows:
            continue
        when = other.get("finished_at") or other.get("created_at") or ""
        if best is None or when > best["finished_at"]:
            best = {"run": other["id"], "title": other.get("title") or other["id"], "finished_at": when, "arm": bare_arm, "results": rows}
    return best


def with_baseline(job, hist) -> dict:
    """This run plus the reused Bare rows: the shape the measures pair on."""
    settings = job.get("settings") or {}
    arms = list(settings.get("arms") or []) + [hist["arm"]]
    return {**job, "settings": {**settings, "arms": arms, "models": list(settings.get("models") or []) + [hist["arm"]["id"]]},
            "results": list(job.get("results") or []) + hist["results"]}


def chance_sentence(p_value: float) -> str:
    """The sign test in words a reader without statistics can weigh."""
    if p_value < 0.01:
        return "A gap this size would come up by chance less than once in 100 times."
    if p_value >= 0.5:
        return "A gap this size comes up by chance as often as not, so it says little on its own."
    return f"A gap this size would come up by chance about {round(p_value * 100)} times in 100."


def verdict_text(subject, baseline, g, task_count, reused=None) -> str:
    """At most 120 words, numbers from measures only."""
    p = subject["pass"]
    if p["attempts"]:
        parts = [f"{subject['name']} passed {count_phrase(p['passed'], p['attempts'])} tasks ({pct(p['rate'])}%).",
                 f"If the same tasks ran again, its pass rate would most likely fall between {pct(p['low'])}% and {pct(p['high'])}%."]
    else:
        parts = [f"{subject['name']} has no evaluated attempts."]
    if baseline and baseline["pass"]["attempts"]:
        b = baseline["pass"]
        parts.append(f"{baseline['name']} passed {count_phrase(b['passed'], b['attempts'])} ({pct(b['rate'])}%).")
    if subject.get("paired") and subject["paired"]["comparable"]:
        pr = subject["paired"]
        parts.append(f"On the same {pr['tasks']} tasks it did better than {baseline['name']} on {pr['wins']}, worse on {pr['losses']} and the same on {pr['ties']}.")
        if pr["p_value"] is not None and (pr["wins"] or pr["losses"]):
            parts.append(chance_sentence(pr["p_value"]))
    if subject["cost"]["per_attempt"] is not None:
        cost = f"Each attempt cost {fmt_money(subject['cost']['per_attempt'])}"
        if baseline and baseline["cost"]["per_attempt"] is not None:
            cost += f", against {fmt_money(baseline['cost']['per_attempt'])} for {baseline['name']}"
        parts.append(cost + ".")
    if reused and baseline:
        parts.append(f"The Bare figures were recorded earlier, in the run \"{reused['title']}\" on {str(reused['finished_at'])[:10]}, with the same model, thinking setting and tasks.")
    parts.append(f"Grade: {g['grade']} ({g['reason']}).")
    return " ".join(parts)


def code_findings(m, shown, baseline_id, fa) -> list:
    """Findings with one number and one evidence link, in descending weight."""
    out = []
    setups = [m["setups"][s] for s in shown if s in m["setups"]]
    baseline = m["setups"].get(baseline_id) if baseline_id else None
    ranked = sorted([s for s in setups if s["pass"]["attempts"]], key=lambda s: (-(s["pass"]["rate"] or 0), s["name"]))
    if ranked:
        top = ranked[0]
        lead = f"{top['name']} had the highest pass rate: " if len(ranked) > 1 else f"{top['name']} passed "
        out.append({"kind": "count", "text": f"{lead}{count_phrase(top['pass']['passed'], top['pass']['attempts'])} ({pct(top['pass']['rate'])}%).",
                    "number": top["pass"]["rate"], "evidence": {"kind": "table", "ref": "hero", "setup": top["id"]}})
    for s in setups:
        pr = s.get("paired")
        if pr and pr["comparable"] and (pr["wins"] or pr["losses"]):
            tasks = [t["task"] for t in pr["per_task"] if t["delta"] != 0]
            out.append({"kind": "paired", "text": f"On the same {pr['tasks']} tasks, {s['name']} did better than {baseline['name']} on {pr['wins']} and worse on {pr['losses']} ({pct(pr['delta']):+d} points of pass rate).",
                        "number": pr["delta"], "evidence": {"kind": "matrix", "ref": "matrix", "tasks": tasks[:5]}})
    violators = [(s, s["violations"]) for s in setups if s["violations"]["attempts_with_changes"]]
    for s, v in sorted(violators, key=lambda x: -x[1]["attempts_with_changes"])[:1]:
        out.append({"kind": "violations", "text": f"{s['name']} changed something outside the permitted scope in {v['attempts_with_changes']} of {v['attempts']} attempts.",
                    "number": v["per_attempt"], "evidence": {"kind": "bucket", "ref": "unintended_changes", "setup": s["id"]}})
    claims = [(s, s["false_completion"]) for s in setups if s["false_completion"]["count"]]
    for s, fc in sorted(claims, key=lambda x: -x[1]["count"])[:1]:
        out.append({"kind": "false_completion", "text": f"{s['name']} said the work was done when it was not, in {fc['count']} of {fc['failed']} failed attempts.",
                    "number": fc["rate"], "evidence": {"kind": "attempts", "ref": "failures", "setup": s["id"]}})
    costed = [s for s in setups if s["cost"]["per_pass"] is not None]
    if len(costed) > 1:
        cheapest = min(costed, key=lambda s: s["cost"]["per_pass"])
        out.append({"kind": "cost", "text": f"{cheapest['name']} had the lowest cost per passed task: {fmt_money(cheapest['cost']['per_pass'])}.",
                    "number": cheapest["cost"]["per_pass"], "evidence": {"kind": "figure", "ref": "cost", "setup": cheapest["id"]}})
    buckets = [b for b in fa.get("buckets", []) if b["count"]]
    if buckets:
        top_bucket = max(buckets, key=lambda b: b["count"])
        out.append({"kind": "failure", "text": f"The most common reason for failing was “{top_bucket['label']}”: {top_bucket['count']} of {fa['summary']['failed_attempts']} failed attempts.",
                    "number": top_bucket["count"], "evidence": {"kind": "bucket", "ref": top_bucket["id"]}})
    return out[:5]


def model_findings(narrative, aliases_back) -> list:
    if not narrative or narrative.get("status") != "completed":
        return []
    out = []
    for finding in narrative.get("findings", []):
        text = finding.get("explanation", "")
        for alias, real in aliases_back.items():
            text = text.replace(alias, real)
        out.append({"kind": "model", "title": finding.get("title", ""), "text": text, "fact": finding.get("kind") == "fact",
                    "evidence": {"kind": "events", "event_ids": finding.get("event_ids", [])}})
    return out


def hero_rows(m, shown):
    rows = []
    for sid in shown:
        s = m["setups"].get(sid)
        if not s:
            continue
        p = s["pass"]
        rows.append({"id": sid, "label": s["name"], "baseline": s["is_baseline"], "value": p["rate"], "low": p["low"], "high": p["high"],
                     "detail": f"{p['passed']} / {p['attempts']} · {pct(p['rate'])}%" if p["attempts"] else "not evaluated", "attempts": p["attempts"], "passed": p["passed"]})
    return rows


def category_of(task_id):
    return CATEGORIES.get(str(task_id).split(".")[0], "Other")


def paired_table(job, m, shown, baseline_id):
    """Categories as rows, setups as columns, cells passed / total with the
    delta against the baseline when the task sets are identical."""
    results = job.get("results") or []
    by_cat = defaultdict(lambda: defaultdict(lambda: {"passed": 0, "attempts": 0}))
    for r in results:
        if measures.is_infrastructure(r) or r["model"] not in shown:
            continue
        cell = by_cat[category_of(r["task"])][r["model"]]
        cell["attempts"] += 1
        cell["passed"] += int(bool(r.get("passed")))
    rows = []
    for category in sorted(by_cat):
        cells = {}
        base = by_cat[category].get(baseline_id) if baseline_id else None
        for sid in shown:
            c = by_cat[category].get(sid)
            if not c:
                cells[sid] = None
                continue
            delta = None
            if base and sid != baseline_id and base["attempts"] == c["attempts"] and c["attempts"]:
                delta = c["passed"] - base["passed"]
            cells[sid] = {"passed": c["passed"], "attempts": c["attempts"], "delta": delta}
        rows.append({"category": category, "cells": cells})
    return rows


def matrix_cells(job, shown, tasks):
    cells = {}
    per = defaultdict(list)
    for r in job.get("results") or []:
        if r["model"] in shown:
            per[(r["task"], r["model"])].append(r)
    for (task, sid), rows in per.items():
        valid = [r for r in rows if not measures.is_infrastructure(r)]
        reps = [bool(r.get("passed")) for r in valid]
        cells[f"{task} {sid}"] = {"rate": (sum(reps) / len(reps)) if reps else None, "reps": reps, "infra": len(rows) - len(valid)}
    return cells


def task_rows(job, tasks):
    out = []
    for task_id in (job.get("settings") or {}).get("tasks") or []:
        task = tasks.get(task_id)
        title = " ".join(task["prompt"][1]["content"].split()) if task else task_id
        out.append({"id": task_id, "title": title if len(title) <= 120 else title[:117].rsplit(" ", 1)[0] + "...", "category": category_of(task_id)})
    return out


def narrative_status(folder) -> dict:
    done = folder / "analysis.json"
    if done.exists():
        try:
            data = json.loads(done.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"status": "failed"}
        except ValueError:
            return {"status": "failed"}
    pending = folder / "analysis.pending.json"
    if pending.exists():
        try:
            return {"status": "pending", **json.loads(pending.read_text(encoding="utf-8"))}
        except ValueError:
            pass
    if (folder / "analysis.claimed").exists():
        return {"status": "pending", "reason": "the analysis was dispatched and has not returned yet."}
    return {"status": "pending", "reason": "the analysis has not run yet."}


def task_set_id(job) -> str:
    hashes = job.get("task_hashes") or {}
    return hashlib.sha256(json.dumps(sorted(hashes.items()), separators=(",", ":")).encode()).hexdigest()[:12]


def run_report(studio, identity, audience="public") -> dict:
    from wb_studio.failure_analysis import analysis as failure_analysis
    job = studio.job(identity)
    events = studio.events(identity)
    m = measures.run_measures(job, events)
    shown, hidden = visible_setups(job, audience)
    baseline_id = m["baseline"] if m["baseline"] in shown else None
    baseline = m["setups"].get(baseline_id) if baseline_id else None
    fa = failure_analysis(studio, identity)
    fa_attempts = [a for a in fa["attempts"] if a["model"] in shown]
    candidates = [m["setups"][s] for s in shown if s in m["setups"] and s != baseline_id and m["setups"][s]["pass"]["attempts"]]
    subject = max(candidates, key=lambda s: (s["pass"]["rate"] or 0, s["name"])) if candidates else (baseline or (m["setups"][shown[0]] if shown and shown[0] in m["setups"] else None))
    reused = historical_baseline(studio, job, subject["id"]) if subject and baseline_id is None else None
    if reused:
        job = with_baseline(job, reused)
        m = measures.run_measures(job, events)
        shown, hidden = visible_setups(job, audience)
        baseline_id = m["baseline"]
        baseline = m["setups"].get(baseline_id)
        subject = m["setups"][subject["id"]]
    g = grade(subject, baseline) if subject else {"grade": "Not comparable", "reason": "no evaluated attempts"}
    narrative = narrative_status(studio.directory / identity)
    aliases_back = {alias: m["setups"].get(real, {}).get("name", real) for real, alias in (narrative.get("aliases") or {}).items()}
    settings = job.get("settings") or {}
    tasks = task_rows(job, studio.tasks)
    return {
        "version": 1, "run": identity, "title": job.get("title"), "status": job.get("status"), "audience": audience,
        "created_at": job.get("created_at"), "finished_at": job.get("finished_at"), "track": settings.get("track", "agentic-request"),
        "grade": g, "subject": subject["id"] if subject else None, "baseline": baseline_id,
        "baseline_source": {"run": reused["run"], "title": reused["title"], "finished_at": reused["finished_at"]} if reused else None,
        "verdict": verdict_text(subject, baseline, g, len(settings.get("tasks") or []), reused) if subject else "This run has no evaluated attempts.",
        "findings": code_findings(m, shown, baseline_id, {**fa, "attempts": fa_attempts}),
        "model_findings": model_findings(narrative, aliases_back),
        "narrative": {k: v for k, v in narrative.items() if k in ("status", "reason", "shortfall", "summary", "next_experiment", "limitations", "model", "effort", "basis")},
        "hero": hero_rows(m, shown), "paired": paired_table(job, m, shown, baseline_id),
        "setups": {sid: m["setups"][sid] for sid in shown if sid in m["setups"]}, "order": shown,
        "hidden_setups": len(hidden), "overlap": [o for o in m["overlap"] if o["a"] in shown and o["b"] in shown],
        "failures": {"summary": fa["summary"], "buckets": fa["buckets"], "attempts": fa_attempts, "limitations": fa["limitations"]},
        "tasks": tasks, "matrix": matrix_cells(job, shown, studio.tasks),
        "caveats": caveats.for_run(job, m, narrative, hidden, audience, reused=reused),
        "method": {"task_set": task_set_id(job), "task_count": len(settings.get("tasks") or []), "task_hashes": job.get("task_hashes") or {},
                   "benchmark": (job.get("benchmark") or {}).get("id"), "repetitions": m["repetitions"], "track": settings.get("track", "agentic-request"),
                   "judge": (job.get("component_manifest") or {}).get("judge"), "components": job.get("component_manifest"),
                   "world": job.get("world_manifest"), "configuration": settings.get("configuration"), "concurrency": settings.get("concurrency", 1),
                   "maximum_usd": settings.get("maximum_usd"), "fork": caveats.fork_version(), "runs": [identity],
                   "planned_attempts": m["planned_attempts"], "recorded_attempts": m["recorded_attempts"]},
    }


def cohorts(studio) -> dict:
    """Runs grouped by frozen task set and track; the unit a round report covers."""
    from wb_studio.leaderboard import full_benchmark_run
    groups = {}
    for job in studio.jobs():
        if job.get("status") not in FINISHED or not job.get("task_hashes"):
            continue
        settings = job.get("settings") or {}
        key = hashlib.sha256(json.dumps([sorted((job.get("task_hashes") or {}).items()), settings.get("track", "agentic-request")], separators=(",", ":")).encode()).hexdigest()[:12]
        cohort = groups.setdefault(key, {"id": key, "task_set": task_set_id(job), "task_count": len(job["task_hashes"]), "track": settings.get("track", "agentic-request"),
                                         "tasks": settings.get("tasks") or [], "task_hashes": job.get("task_hashes") or {}, "runs": [], "full_benchmark": False,
                                         "benchmark": (job.get("benchmark") or {}).get("id")})
        cohort["runs"].append({"id": job["id"], "title": job.get("title"), "status": job["status"], "created_at": job.get("created_at"), "finished_at": job.get("finished_at"),
                               "full_benchmark": full_benchmark_run(job)})
        cohort["full_benchmark"] = cohort["full_benchmark"] or full_benchmark_run(job)
    for cohort in groups.values():
        cohort["runs"].sort(key=lambda r: r["created_at"] or "", reverse=True)
        cohort["latest"] = cohort["runs"][0]["created_at"] if cohort["runs"] else None
    return groups


def pooled_job(studio, cohort) -> dict:
    """One synthetic job whose results pool every run in the cohort, so the
    measures see repetitions across runs as repetitions."""
    arms, seen, results, events = [], set(), [], []
    for entry in cohort["runs"]:
        job = studio.job(entry["id"])
        for arm in (job.get("settings") or {}).get("arms") or [{"id": m, "name": m, "kind": "runner"} for m in (job.get("settings") or {}).get("models") or []]:
            if arm["id"] not in seen:
                seen.add(arm["id"])
                arms.append(arm)
        results.extend(job.get("results") or [])
        events.extend(studio.events(entry["id"]))
    return {"id": cohort["id"], "settings": {"tasks": cohort["tasks"], "models": [a["id"] for a in arms], "arms": arms, "track": cohort["track"]},
            "task_hashes": cohort["task_hashes"], "results": results, "events": events}


def round_report(studio, cohort_id, audience="public") -> dict:
    cohort = cohorts(studio).get(cohort_id)
    if cohort is None:
        raise ValueError("Unknown task set")
    from wb_studio.leaderboard import exclusion_reason, pairings, uncertainty
    job = pooled_job(studio, cohort)
    m = measures.run_measures(job, job["events"])
    groups = measures.by_setup(job["results"])
    shown, hidden = visible_setups(job, audience)
    baseline_id = m["baseline"] if m["baseline"] in shown else None
    baseline = m["setups"].get(baseline_id) if baseline_id else None
    standings = sorted([m["setups"][s] for s in shown if s in m["setups"] and m["setups"][s]["pass"]["attempts"]],
                       key=lambda s: (-(s["pass"]["rate"] or 0), s["cost"]["per_attempt"] if s["cost"]["per_attempt"] is not None else float("inf"), s["name"]))
    rows = []
    previous, rank = None, 0
    for index, s in enumerate(standings):
        if s["pass"]["rate"] != previous:
            rank = index + 1
        previous = s["pass"]["rate"]
        rows.append({"rank": rank, "id": s["id"], "name": s["name"], "is_baseline": s["is_baseline"], "pass": s["pass"], "pass_k": s["pass_k"], "cost": s["cost"],
                     "paired": s["paired"], "grade": grade(s, baseline) if not s["is_baseline"] else None, "runs": sorted({r["id"] for r in cohort["runs"]}),
                     "interval": uncertainty(groups.get(s["id"], []))})
    trend = []
    for entry in sorted(cohort["runs"], key=lambda r: r["created_at"] or ""):
        run_job = studio.job(entry["id"])
        rm = measures.run_measures(run_job, [])
        for sid, s in rm["setups"].items():
            if sid in shown and "monarch" in (s["name"] or "").lower() and s["pass"]["attempts"]:
                trend.append({"series": s["name"], "x": (entry["created_at"] or "")[:10], "run": entry["id"], "y": s["pass"]["rate"], "low": s["pass"]["low"], "high": s["pass"]["high"]})
    return {"version": 1, "cohort": cohort_id, "audience": audience, "task_set": cohort["task_set"], "task_count": cohort["task_count"], "track": cohort["track"],
            "full_benchmark": cohort["full_benchmark"], "runs": cohort["runs"], "baseline": baseline_id, "standings": rows, "hero": hero_rows(m, shown),
            "pairings": pairings({sid: groups[sid] for sid in shown if sid in groups}),
            "excluded": [{"id": r["id"], "title": r.get("title"), "reason": exclusion_reason(studio.job(r["id"]))} for r in cohort["runs"] if not r["full_benchmark"]],
            "paired": paired_table(job, m, shown, baseline_id), "matrix": matrix_cells(job, shown, studio.tasks), "tasks": task_rows(job, studio.tasks),
            "overlap": [o for o in m["overlap"] if o["a"] in shown and o["b"] in shown], "setups": {sid: m["setups"][sid] for sid in shown if sid in m["setups"]}, "order": shown,
            "trend": trend, "hidden_setups": len(hidden), "repetitions": m["repetitions"],
            "caveats": caveats.for_round({**cohort, "baseline": baseline_id}, hidden),
            "method": {"task_set": cohort["task_set"], "task_count": cohort["task_count"], "task_hashes": cohort["task_hashes"], "runs": [r["id"] for r in cohort["runs"]],
                       "repetitions": m["repetitions"], "fork": caveats.fork_version(), "benchmark": cohort.get("benchmark")}}


def index(studio, audience="public") -> dict:
    """The Reports front door: rounds newest first, each with its runs and grades."""
    groups = sorted(cohorts(studio).values(), key=lambda c: c["latest"] or "", reverse=True)
    rounds = []
    for cohort in groups:
        job = pooled_job(studio, cohort)
        m = measures.run_measures(job, [])
        shown, hidden = visible_setups(job, audience)
        baseline_id = m["baseline"] if m["baseline"] in shown else None
        baseline = m["setups"].get(baseline_id) if baseline_id else None
        best = max([m["setups"][s] for s in shown if s in m["setups"] and s != baseline_id and m["setups"][s]["pass"]["attempts"]], key=lambda s: (s["pass"]["rate"] or 0), default=None)
        rounds.append({"id": cohort["id"], "task_count": cohort["task_count"], "track": cohort["track"], "full_benchmark": cohort["full_benchmark"], "latest": cohort["latest"],
                       "runs": cohort["runs"], "setups": len(shown), "best": {"name": best["name"], "rate": best["pass"]["rate"], "passed": best["pass"]["passed"], "attempts": best["pass"]["attempts"]} if best else None,
                       "grade": grade(best, baseline) if best else {"grade": "Not comparable", "reason": "no evaluated attempts"}})
    return {"rounds": rounds, "audience": audience, "generated_at": datetime.now(timezone.utc).isoformat()}
