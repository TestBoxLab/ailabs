"""Run and round reports, assembled from stored records only.

A report reads verdict first: a grade against the Bare baseline, findings with
one number and one evidence link each, then the figures, the failures, the
cost, the caveats and the method. Numbers are always inserted by code; the
model narrative (analysis.json, when a run has one) fills prose slots and every
claim in it cites recorded events.

There is one report. Every setup that ran appears in it, and every reader sees
the same page.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from wb_studio import caveats, measures
from wb_studio.leaderboard import contract_note, evaluation_contract, exclusion_reason, full_benchmark_run
from wb_studio.reports import CATEGORIES
from wb_world.episode import contract_hash
from wb_world.source import product_of

GRADES = ("Improvement", "Regression", "Tradeoff", "Tie", "Undecided", "Not comparable")
FINISHED = ("completed", "failed", "cancelled", "interrupted")


def setup_ids(job) -> list:
    """Every setup the run recorded. A report hides none of them."""
    settings = job.get("settings") or {}
    return [arm["id"] for arm in settings.get("arms") or []] or list(settings.get("models") or [])


def is_lab(name) -> bool:
    """A lab build: Lucas's own experiment, not a released version.

    This is now the only such predicate in the repository. The CLI had one, guarding which
    competitors an audience could render; that gate and its audiences file went on 11 September,
    when Lucas ruled there is one report and every reader sees it whole. What survived the ruling
    is narrower and lives here: the report shows a lab build, and the interface refuses to let a
    report carrying one leave the machine (`lab_setups` below, `labGate` in `static/reports.js`).
    """
    return str(name or "").startswith("monarch-lab")


def lab_setups(order, setups) -> list:
    """Which setups in this report are lab builds, by id and by name.

    The report shows them: Lucas's ruling of 11 September is one report with no differentiation
    (display yes). What they may not do is leave the machine (export no) — the same rule the
    retired audiences file stated as "a lab competitor can never reach an exportable artifact",
    kept because that is the half about sharing rather than about who may look.

    The list is computed here, once, rather than sniffed out of the rendered page, because a gate
    that reads the DOM is a gate that misses a label in a chart.
    """
    found = []
    for sid in order or []:
        name = ((setups or {}).get(sid) or {}).get("name") or sid
        if is_lab(sid) or is_lab(name):
            found.append({"id": sid, "name": name})
    return found


def grade(setup, baseline) -> dict:
    """One word for the whole comparison, with its reason."""
    if not baseline or not setup or not setup.get("paired") or not setup["paired"]["comparable"]:
        reason = "no Bare baseline to compare against" if not baseline else ((setup or {}).get("paired") or {}).get("reason") or "no paired attempts"
        return {"grade": "Not comparable", "reason": reason}
    p = setup["paired"]
    cost_a, cost_b = setup["cost"]["per_attempt"], baseline["cost"]["per_attempt"]
    cost_worse = cost_a is not None and cost_b is not None and cost_b > 0 and cost_a > cost_b * 1.25
    cost_better = cost_a is not None and cost_b is not None and cost_a > 0 and cost_b > cost_a * 1.25
    better, worse = p["wins"] > p["losses"], p["losses"] > p["wins"]
    tally = f"better than Bare on {p['wins']} {'task' if p['wins'] == 1 else 'tasks'}, worse on {p['losses']}, the same on {p['ties']}"
    p_value = p.get("p_value")
    if (better or worse) and p_value is not None and p_value >= 0.05:
        # The word carries the same certainty as the sentence: a direction the sign test cannot support is not a grade.
        cost_note = ", and each attempt cost more than 1.25 times what Bare's did" if cost_worse else (", and each attempt cost less than 0.8 times what Bare's did" if cost_better else "")
        return {"grade": "Undecided", "reason": f"{tally}; too few tasks differ to tell them apart (sign test p = {p_value:.2f}){cost_note}"}
    if better and cost_worse:
        return {"grade": "Tradeoff", "reason": f"{tally}, but each attempt cost more than 1.25 times what Bare's did"}
    if worse and cost_better:
        return {"grade": "Tradeoff", "reason": f"{tally}, but each attempt cost less than 0.8 times what Bare's did"}
    if better:
        return {"grade": "Improvement", "reason": tally}
    if worse:
        return {"grade": "Regression", "reason": tally}
    return {"grade": "Tie", "reason": tally}


def trend_title_for(names) -> str:
    """The over-time figure's title, written from the series it draws.

    One or two setups are named outright; more than that would not fit a figure title,
    so it says how many. An empty trend still returns a sentence rather than None, so a
    caller never has to invent one (feature 024, FR-015).
    """
    names = [n for n in (names or []) if n]
    if not names:
        return "Pass rate by run"
    if len(names) == 1:
        return f"{names[0]}: pass rate by run"
    if len(names) == 2:
        return f"{names[0]} and {names[1]}: pass rate by run"
    return f"Pass rate by run, {len(names)} setups"


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
        if product_of(other) != product_of(job):
            continue
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


def rate_phrase(p) -> str:
    """Count, rate and interval in one clause: "6 of 10 tasks (60%, 95% CI 31 to 83)"."""
    return f"{count_phrase(p['passed'], p['attempts'])} tasks ({pct(p['rate'])}%, 95% CI {pct(p['low'])} to {pct(p['high'])})"


def certainty(pr, baseline_name) -> str:
    """One sentence from a closed set, chosen from the paired test by code, never by a model.

    probably: the sign test is below 0.05 and the direction is clear.
    may: the direction is clear but the test is between 0.05 and 0.5.
    cannot tell: the test is 0.5 or above, or too few tasks differ.
    """
    p_value = pr.get("p_value")
    wins, losses = pr["wins"], pr["losses"]
    if not (wins or losses) or p_value is None or p_value >= 0.5 or (wins + losses) < 3:
        return "This run cannot tell them apart."
    more = "more" if wins > losses else "fewer"
    word = "probably" if p_value < 0.05 else "may"
    verb = "passes" if word == "probably" else "pass"
    return f"It {word} {verb} {more} tasks than {baseline_name} on this set."


def harm_sentence(subject) -> str:
    v = subject.get("violations") or {}
    if v.get("attempts_with_changes"):
        return f"It changed something outside the task in {v['attempts_with_changes']} of {v['attempts']} attempts."
    if v.get("attempts"):
        return "It changed nothing outside the task."
    return ""


def verdict_text(subject, baseline, g, task_count, reused=None) -> str:
    """Three sentences: the outcome with its interval, what changed that should not have, the cost. Numbers from measures only."""
    p = subject["pass"]
    if p["attempts"]:
        parts = [f"{subject['name']} passed {rate_phrase(p)}" + (f"; {baseline['name']} passed {rate_phrase(baseline['pass'])}." if baseline and baseline["pass"]["attempts"] else ".")]
    else:
        parts = [f"{subject['name']} has no evaluated attempts."]
    harm = harm_sentence(subject)
    if harm:
        parts.append(harm)
    if subject["cost"]["per_attempt"] is not None:
        cost = f"Each attempt cost {fmt_money(subject['cost']['per_attempt'])}"
        if baseline and baseline["cost"]["per_attempt"] is not None:
            cost += f", against {fmt_money(baseline['cost']['per_attempt'])} for {baseline['name']}"
        parts.append(cost + ".")
    if reused and baseline:
        parts.append(f"The Bare figures were recorded earlier, in the run \"{reused['title']}\" on {str(reused['finished_at'])[:10]}, with the same model, thinking setting and tasks.")
    return " ".join(parts)


def code_findings(m, shown, baseline_id, fa) -> list:
    """Findings with one number and one evidence link, in descending weight."""
    out = []
    setups = [m["setups"][s] for s in shown if s in m["setups"]]
    baseline = m["setups"].get(baseline_id) if baseline_id else None
    ranked = sorted([s for s in setups if s["pass"]["attempts"]], key=lambda s: (-(s["pass"]["rate"] or 0), s["name"]))
    # Harms first (rule 14): what changed that should not have, or that nothing did.
    violators = [(s, s["violations"]) for s in setups if s["violations"]["attempts_with_changes"]]
    for s, v in sorted(violators, key=lambda x: -x[1]["attempts_with_changes"])[:1]:
        out.append({"kind": "violations", "text": f"{s['name']} changed something outside the task in {v['attempts_with_changes']} of {v['attempts']} attempts.",
                    "number": v["per_attempt"], "evidence": {"kind": "bucket", "ref": "scope_violation", "setup": s["id"]}})
    if ranked:
        top = ranked[0]
        lead = f"{top['name']} had the highest pass rate: " if len(ranked) > 1 else f"{top['name']} passed "
        out.append({"kind": "count", "text": f"{lead}{rate_phrase(top['pass'])}.",
                    "number": top["pass"]["rate"], "evidence": {"kind": "table", "ref": "hero", "setup": top["id"]}})
    for s in setups:
        pr = s.get("paired")
        if pr and pr["comparable"] and (pr["wins"] or pr["losses"]):
            tasks = [t["task"] for t in pr["per_task"] if t["delta"] != 0]
            out.append({"kind": "paired", "text": f"On the same {pr['tasks']} tasks, {s['name']} did better than {baseline['name']} on {pr['wins']} and worse on {pr['losses']} ({pct(pr['delta']):+d} points of pass rate). {certainty(pr, baseline['name'])}",
                        "number": pr["delta"], "evidence": {"kind": "matrix", "ref": "matrix", "tasks": tasks[:5]}})
    claims = [(s, s["false_completion"]) for s in setups if s["false_completion"]["count"]]
    for s, fc in sorted(claims, key=lambda x: -x[1]["count"])[:1]:
        out.append({"kind": "false_completion", "text": f"{s['name']} said the work was done when it was not, in {fc['count']} of {fc['failed']} failed attempts (inferred from wording).",
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


def short_name(name: str) -> str:
    """The part of a setup name a figure label can hold; the build token and the
    full identifier drop to the method section, keeping the identifying segments
    (architecture, version and model)."""
    from wb_studio.runtime_registry import display_name, fit_name
    raw = str(name or "").strip()
    if not raw:
        return ""
    head, sep, tail = raw.partition(" · ")
    if " / " in head:
        segs = [s.strip() for s in head.split(" / ")]
        if len(segs) >= 3:
            return fit_name(f"{' / '.join(segs[:-1])} · {segs[-1]}", 44)
        if len(segs) == 2:
            return fit_name(f"{segs[0]} / {segs[1]}", 44)
    return fit_name(display_name(name), 44)


def hero_rows(m, shown):
    rows = []
    for sid in shown:
        s = m["setups"].get(sid)
        if not s:
            continue
        p = s["pass"]
        rows.append({"id": sid, "label": short_name(s["name"]), "baseline": s["is_baseline"], "value": p["rate"], "low": p["low"], "high": p["high"],
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


def task_liveness(task_id: str, stored_hash: str | None, tasks: dict) -> str:
    """Compare a stored task hash against the live corpus, emitting live / superseded / absent."""
    if task_id not in tasks:
        return "absent"
    current_hash = contract_hash(tasks[task_id])
    if not stored_hash or stored_hash != current_hash:
        return "superseded"
    return "live"


def matrix_cells(job, shown, tasks):
    cells = {}
    per = defaultdict(list)
    task_hashes = job.get("task_hashes") or {}
    for r in job.get("results") or []:
        if r["model"] in shown:
            per[(r["task"], r["model"])].append(r)
    for (task, sid), rows in per.items():
        valid = [r for r in rows if not measures.is_infrastructure(r)]
        reps = [bool(r.get("passed")) for r in valid]
        stored_hash = next((r.get("contract_sha256") for r in rows if r.get("contract_sha256")), None) or task_hashes.get(task)
        liveness = task_liveness(task, stored_hash, tasks)
        cells[f"{task} {sid}"] = {
            "rate": (sum(reps) / len(reps)) if reps else None,
            "reps": reps,
            "infra": len(rows) - len(valid),
            "liveness": liveness,
            "comparable": (liveness == "live"),
        }
    return cells


def task_rows(job, tasks):
    out = []
    task_hashes = job.get("task_hashes") or {}
    for task_id in (job.get("settings") or {}).get("tasks") or []:
        task = tasks.get(task_id)
        title = " ".join(task["prompt"][1]["content"].split()) if task else task_id
        stored_hash = task_hashes.get(task_id)
        liveness = task_liveness(task_id, stored_hash, tasks)
        out.append({
            "id": task_id,
            "title": title if len(title) <= 120 else title[:117].rsplit(" ", 1)[0] + "...",
            "category": category_of(task_id),
            "liveness": liveness,
            "comparable": (liveness == "live"),
        })
    return out


def narrative_status(folder) -> dict:
    publication = folder / "report-publication.json"
    if publication.exists():
        try:
            data = json.loads(publication.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("status") == "completed":
                return {**data, "model": "Genesis"}
        except ValueError:
            pass
        return {"status": "failed", "model": "Genesis", "reason": "The published report could not be read."}
    work = folder / "report-work.json"
    if work.exists():
        try:
            data = json.loads(work.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                failed = data.get("stage") in ("failed", "interrupted", "cancelled", "published")
                return {"status": "failed" if failed else "pending", "model": "Genesis",
                        "reason": data.get("reason") or "Genesis is preparing this report.",
                        "askable": failed, "stage": data.get("stage")}
        except ValueError:
            return {"status": "failed", "model": "Genesis", "reason": "The report work record could not be read."}
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
        return {"status": "pending", "reason": "The reading was dispatched and has not returned yet.", "askable": False}
    return {"status": "pending", "reason": "The reading has not run yet.", "askable": True}


def task_set_id(job) -> str:
    hashes = job.get("task_hashes") or {}
    return hashlib.sha256(json.dumps(sorted(hashes.items()), separators=(",", ":")).encode()).hexdigest()[:12]


def break_even_block(groups, shown, baseline_id, names) -> dict:
    """FR-029. The curve, for every setup that builds something reusable.

    Only a competitor with an `authoring` phase has an artefact to reuse; a bare model
    pays per request by construction, and plotting it as though it configured something
    once would invent the very asymmetry the figure exists to measure. A round with no
    such competitor gets the sentence, not an empty chart.
    """
    if not baseline_id or baseline_id not in groups:
        return {"available": False, "reason": "This round has no baseline to compare against."}
    comparator = groups[baseline_id]
    curves = []
    for sid in shown:
        if sid == baseline_id or sid not in groups:
            continue
        rows = groups[sid]
        if not any("authoring" in (r.get("phases") or {}) for r in rows):
            continue          # nothing is configured once here, so there is no curve
        out = measures.curve(rows, comparator)
        out.update({"id": sid, "name": names.get(sid, sid),
                    "title": f"What {names.get(sid, sid)} costs against running the workflow again",
                    "comparator_name": names.get(baseline_id, baseline_id)})
        curves.append(out)
    if not curves:
        return {"available": False, "reason":
                "No competitor in this round builds a workflow it can run again, so there "
                "is nothing to plot a break-even against. The curve compares configuring "
                "once and executing N times with paying for every request."}
    return {"available": True, "curves": curves, "comparator": baseline_id}


EVIDENCE_KINDS = ("confirmed-result", "code-reading")
AUDIENCES = ("engine-team", "lab", "executive")


def gap_item(id: str, statement: str, evidence_kind: str, evidence=(), confirmed: bool = False) -> dict:
    """One gap between the product and the frontier, with what it rests on.

    `evidence_kind` is the load-bearing field. A `confirmed-result` was measured; a
    `code-reading` is somebody reading Monarch's source. They are never rendered as
    peers, because a reader shown one list weighs them the same — and a code reading
    is also internal-only, per the standing rule that facts from Monarch's code do
    not leave the lab.
    """
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError(f"evidence_kind must be one of {', '.join(EVIDENCE_KINDS)}, not {evidence_kind!r}")
    return {"id": id, "statement": statement, "evidence_kind": evidence_kind,
            "evidence": list(evidence), "confirmed": bool(confirmed),
            "internal_only": evidence_kind == "code-reading"}


def _rendering(item: dict, audience: str) -> str:
    """The same fact, in the words that reader needs. Never a different fact."""
    statement = item["statement"].rstrip(".")
    if audience == "engine-team":
        return statement + "." if item["confirmed"] else statement + " — not yet confirmed."
    if audience == "lab":
        return ("Confirmed: " if item["confirmed"] else "To confirm: ") + statement + "."
    # An executive reads the distance to the frontier, not the defect.
    return (statement + ", and the measurement holds on the held-out set."
            if item["confirmed"] else statement + ", on evidence that is not yet settled.")


def gap_list(items, audience: str = "lab", exported: bool = False) -> dict:
    """FR-031, FR-032. One evidence base, three renderings, two tiers that never merge.

    There is deliberately no flat `items` key: a caller cannot render the two tiers as
    peers by reaching for the obvious field. `confirmed` is true only after a held-out
    confirmation, so an unconfirmed measured result is an indication like a code
    reading is — same tier, different caveat.

    `exported` drops code readings and says how many went, because a silent omission
    reads as "there were none".
    """
    if audience not in AUDIENCES:
        raise ValueError(f"audience must be one of {', '.join(AUDIENCES)}, not {audience!r}")
    confirmed, indications, withheld = [], [], 0
    for item in items:
        shown = dict(item, text=_rendering(item, audience), audience=audience)
        if item["confirmed"] and item["evidence_kind"] == "confirmed-result":
            confirmed.append(shown)
            continue
        if exported and item["internal_only"]:
            withheld += 1
            continue
        shown["caveat"] = ("Read from Monarch's code; never measured."
                           if item["evidence_kind"] == "code-reading"
                           else "Measured, but not confirmed on the held-out set.")
        indications.append(shown)
    note = ""
    if withheld:
        note = (f"{withheld} item{'s' if withheld > 1 else ''} read from Monarch's code "
                "are not shown here; facts from the code stay in the lab.")
    return {"audience": audience, "confirmed": confirmed, "indications": indications,
            "withheld": withheld, "withheld_note": note}


def run_report(studio, identity) -> dict:
    from wb_studio.performance import performance_report
    from wb_studio.failure_analysis import analysis as failure_analysis
    from wb_studio.narrative import run_story
    from wb_studio.report_patterns import patterns
    from wb_studio import genesis_reports
    job = studio.job(identity)
    events = studio.events(identity)
    task_hashes = job.get("task_hashes") or {}
    results = job.get("results") or []
    settings = job.get("settings") or {}
    tasks_list = settings.get("tasks") or []

    live_results = [
        r for r in results
        if task_liveness(r.get("task"), r.get("contract_sha256") or task_hashes.get(r.get("task")), studio.tasks) == "live"
    ]
    live_tasks = [
        t for t in tasks_list
        if task_liveness(t, task_hashes.get(t), studio.tasks) == "live"
    ]
    live_job = {
        **job,
        "results": live_results,
        "settings": {**settings, "tasks": live_tasks},
    }

    m = measures.run_measures(live_job, events)
    shown = setup_ids(job)
    baseline_id = m["baseline"] if m["baseline"] in shown else None
    baseline = m["setups"].get(baseline_id) if baseline_id else None
    fa = failure_analysis(studio, identity)
    fa_attempts = [a for a in fa["attempts"] if a["model"] in shown]
    for a in fa_attempts:
        h = a.get("contract_sha256") or task_hashes.get(a.get("task"))
        liv = task_liveness(a.get("task"), h, studio.tasks)
        a["liveness"] = liv
        a["comparable"] = (liv == "live")

    candidates = [m["setups"][s] for s in shown if s in m["setups"] and s != baseline_id and m["setups"][s]["pass"]["attempts"]]
    subject = max(candidates, key=lambda s: (s["pass"]["rate"] or 0, s["name"])) if candidates else (baseline or (m["setups"][shown[0]] if shown and shown[0] in m["setups"] else None))
    reused = historical_baseline(studio, live_job, subject["id"]) if subject and baseline_id is None else None
    if reused:
        live_job = with_baseline(live_job, reused)
        m = measures.run_measures(live_job, events)
        shown = setup_ids(live_job)
        baseline_id = m["baseline"]
        baseline = m["setups"].get(baseline_id)
        subject = m["setups"][subject["id"]]
    if subject and baseline and subject["id"] == baseline["id"]:
        # Only the Bare baseline ran: nothing to compare it with, least of all itself.
        baseline = None
        g = {"grade": "Not comparable", "reason": "only the Bare baseline ran"}
    else:
        g = grade(subject, baseline) if subject else {"grade": "Not comparable", "reason": "no evaluated attempts"}
    narrative = narrative_status(studio.directory / identity)
    aliases_back = {alias: m["setups"].get(real, {}).get("name", real) for real, alias in (narrative.get("aliases") or {}).items()}
    tasks = task_rows(job, studio.tasks)
    return {
        "version": 1, "run": identity, "title": job.get("title"), "status": job.get("status"),
        "created_at": job.get("created_at"), "finished_at": job.get("finished_at"), "track": settings.get("track", "agentic-request"),
        "grade": g, "subject": subject["id"] if subject else None, "baseline": baseline_id,
        "baseline_source": {"run": reused["run"], "title": reused["title"], "finished_at": reused["finished_at"]} if reused else None,
        "verdict": verdict_text(subject, baseline, g, len(live_tasks), reused) if subject else "This run has no evaluated attempts.",
        "findings": [f for f in code_findings(m, shown, baseline_id, {**fa, "attempts": fa_attempts})
                     if not (subject and f["kind"] in ("count", "violations") and (f.get("evidence") or {}).get("setup") == subject["id"])],
        "authored": genesis_reports.published(studio, identity),
        "report_work": (genesis_reports.status(studio.genesis, {"run": identity}) if getattr(studio, "genesis", None) else {"stage": "none", "run": identity}),
        "patterns": patterns(fa_attempts, {sid: m["setups"].get(sid, {}).get("name", sid) for sid in shown}, identity),
        "model_findings": model_findings(narrative, aliases_back),
        "narrative": {k: v for k, v in narrative.items() if k in ("status", "reason", "shortfall", "askable", "summary", "what_went_right", "what_went_wrong", "next_experiment", "limitations", "model", "effort", "basis")},
        "story": run_story(fa_attempts, {sid: m["setups"][sid]["name"] for sid in shown if sid in m["setups"]}),
        "hero": hero_rows(m, shown), "paired": paired_table(live_job, m, shown, baseline_id),
        "lab_setups": lab_setups(shown, m["setups"]),
        "full_benchmark": full_benchmark_run(job),
        "exclusion_reason": exclusion_reason(job),
        "setups": {sid: {**m["setups"][sid], "short_name": short_name(m["setups"][sid]["name"])} for sid in shown if sid in m["setups"]}, "order": shown,
        "overlap": [o for o in m["overlap"] if o["a"] in shown and o["b"] in shown],
        "failures": {"summary": fa["summary"], "buckets": fa["buckets"], "attempts": fa_attempts, "limitations": fa["limitations"]},
        "tasks": tasks, "matrix": matrix_cells(job, shown, studio.tasks),
        "performance": performance_report(job, events),
        "caveats": caveats.for_run(job, m, narrative, reused=reused),
        "method": {"task_set": task_set_id(job), "task_count": len(settings.get("tasks") or []), "live_task_count": len(live_tasks), "task_hashes": job.get("task_hashes") or {},
                   "benchmark": (job.get("benchmark") or {}).get("id"), "repetitions": m["repetitions"], "track": settings.get("track", "agentic-request"),
                   "judge": (job.get("component_manifest") or {}).get("judge"), "components": job.get("component_manifest"),
                   "world": job.get("world_manifest"), "configuration": settings.get("configuration"), "concurrency": settings.get("concurrency", 1),
                   "maximum_usd": settings.get("maximum_usd"), "fork": caveats.fork_version(), "runs": [identity],
                   "planned_attempts": m["planned_attempts"], "recorded_attempts": m["recorded_attempts"]},
    }


def cohorts(studio) -> dict:
    """Runs grouped by frozen task set and track; the unit a round report covers."""
    groups = {}
    for job in studio.jobs():
        if job.get("status") not in FINISHED or not job.get("task_hashes"):
            continue
        settings = job.get("settings") or {}
        # The whole evaluation contract, not task hashes and track alone. This keyed on
        # two of the six, so a round could pool runs graded by different judges, or on
        # different world revisions, and rank them against each other as one
        # measurement (feature 024, FR-016). The rule lives in one place now.
        contract = evaluation_contract(job, job.get("task_hashes") or {})
        key = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
        cohort = groups.setdefault(key, {"id": key, "task_set": task_set_id(job), "task_count": len(job["task_hashes"]), "track": contract["track"],
                                         "tasks": settings.get("tasks") or [], "task_hashes": job.get("task_hashes") or {}, "runs": [], "full_benchmark": False,
                                         "contract": contract, "note": contract_note(contract),
                                         "benchmark": (job.get("benchmark") or {}).get("id")})
        cohort["runs"].append({"id": job["id"], "title": job.get("title"), "status": job["status"], "created_at": job.get("created_at"), "finished_at": job.get("finished_at"),
                               "full_benchmark": full_benchmark_run(job), "exclusion_reason": exclusion_reason(job)})
        cohort["full_benchmark"] = cohort["full_benchmark"] or full_benchmark_run(job)
    for cohort in groups.values():
        cohort["runs"].sort(key=lambda r: r["created_at"] or "", reverse=True)
        cohort["latest"] = cohort["runs"][0]["created_at"] if cohort["runs"] else None
        cohort["first"] = cohort["runs"][-1]["created_at"] if cohort["runs"] else None
    return groups


def pooled_job(studio, cohort) -> dict:
    """One synthetic job whose results pool every run in the cohort, so the
    measures see repetitions across runs as repetitions."""
    arms, seen, results, events = [], set(), [], []
    products = []
    for entry in cohort["runs"]:
        job = studio.job(entry["id"])
        products.append(product_of(job))
        if any(p != products[0] for p in products):
            raise ValueError("Cannot pool different benchmark products")
        for arm in (job.get("settings") or {}).get("arms") or [{"id": m, "name": m, "kind": "runner"} for m in (job.get("settings") or {}).get("models") or []]:
            if arm["id"] not in seen:
                seen.add(arm["id"])
                arms.append(arm)
        results.extend(job.get("results") or [])
        events.extend(studio.events(entry["id"]))
    return {"id": cohort["id"], "settings": {"tasks": cohort["tasks"], "models": [a["id"] for a in arms], "arms": arms, "track": cohort["track"], **({"product":products[0]} if products and products[0] else {})},
            "task_hashes": cohort["task_hashes"], "results": results, "events": events}


def round_report(studio, cohort_id) -> dict:
    from wb_studio.failure_analysis import analysis as failure_analysis
    from wb_studio.report_patterns import patterns
    from wb_studio import genesis_reports
    cohort = cohorts(studio).get(cohort_id)
    if cohort is None:
        raise ValueError("Unknown task set")
    from wb_studio.leaderboard import exclusion_reason, pairings, uncertainty
    job = pooled_job(studio, cohort)
    m = measures.run_measures(job, job["events"])
    groups = measures.by_setup(job["results"])
    shown = setup_ids(job)
    baseline_id = m["baseline"] if m["baseline"] in shown else None
    baseline = m["setups"].get(baseline_id) if baseline_id else None
    standings = [m["setups"][s] for s in shown if s in m["setups"] and m["setups"][s]["pass"]["attempts"]]
    # Rank the way LMArena and SEAL do: one plus the number of setups whose whole interval sits above this one;
    # the far end of the spread counts every setup this one cannot be told apart from.
    #
    # Ranked on the interval the row actually prints. It used to rank on
    # measures.pass_rate's Wilson-over-attempts bounds while showing
    # leaderboard.uncertainty's clustered ones, and with repetitions those disagree —
    # so a reader saw a rank derived from an interval that was not on the page
    # (feature 024, FR-016). The clustered estimator is the one to keep: it counts
    # tasks, not retries, which AI-LABS-DIRECTION.md:132 asks for.
    intervals = {s["id"]: uncertainty(groups.get(s["id"], [])) for s in standings}
    def low(s):
        u = intervals[s["id"]]
        return u["low"] if u["low"] is not None else (u["rate"] if u["rate"] is not None else (s["pass"]["rate"] or 0))
    def high(s):
        u = intervals[s["id"]]
        return u["high"] if u["high"] is not None else (u["rate"] if u["rate"] is not None else (s["pass"]["rate"] or 0))
    ranks = {s["id"]: 1 + sum(1 for o in standings if o is not s and low(o) > high(s)) for s in standings}
    spread = {s["id"]: sum(1 for o in standings if high(o) >= low(s)) for s in standings}
    standings.sort(key=lambda s: (ranks[s["id"]], -(s["pass"]["rate"] or 0), s["cost"]["per_attempt"] if s["cost"]["per_attempt"] is not None else float("inf"), s["name"]))
    rows = []
    for s in standings:
        rank = ranks[s["id"]]
        rows.append({"rank": rank, "rank_high": max(rank, spread[s["id"]]), "id": s["id"], "name": short_name(s["name"]), "is_baseline": s["is_baseline"], "pass": s["pass"], "pass_k": s["pass_k"], "cost": s["cost"],
                     "paired": s["paired"], "grade": grade(s, baseline) if not s["is_baseline"] else None, "runs": sorted({r["id"] for r in cohort["runs"]}),
                     "interval": intervals[s["id"]], "rank_basis": "interval"})
    # Every setup that ran, not only the ones named "monarch". The filter meant a round
    # comparing anything else produced no over-time figure at all, and the figure that
    # did appear was titled by a constant — asserting the programme's headline subject
    # onto whatever the cohort happened to contain (feature 024, FR-015).
    trend = []
    for entry in sorted(cohort["runs"], key=lambda r: r["created_at"] or ""):
        run_job = studio.job(entry["id"])
        rm = measures.run_measures(run_job, [])
        for sid, s in rm["setups"].items():
            if sid in shown and s["pass"]["attempts"]:
                trend.append({"series": s["name"], "x": (entry["created_at"] or "")[:10], "run": entry["id"], "y": s["pass"]["rate"], "low": s["pass"]["low"], "high": s["pass"]["high"]})
    # The lines read as names, unless two setups of this round resolve to the same one —
    # two builds of Monarch drawn as one line would be a series the round never ran.
    labels = {name: short_name(name) for name in {p["series"] for p in trend}}
    if len(set(labels.values())) == len(labels):
        for point in trend:
            point["series"] = labels[point["series"]]
    trend_title = trend_title_for(sorted({p["series"] for p in trend}))
    pattern_attempts, run_analyses = [], []
    for entry in cohort["runs"]:
        run_id = entry["id"]
        source_job = studio.job(run_id)
        hashes = source_job.get("task_hashes") or {}
        for attempt in failure_analysis(studio, run_id)["attempts"]:
            pattern_attempts.append({**attempt, "run": run_id,
                                     "liveness": task_liveness(attempt.get("task"), hashes.get(attempt.get("task")), studio.tasks)})
        run_analyses.append({"run": run_id, "title": entry.get("title"),
                             "authored": genesis_reports.published(studio, run_id),
                             "report_work": (genesis_reports.status(studio.genesis, {"run": run_id}) if getattr(studio, "genesis", None) else {"stage": "none", "run": run_id})})
    return {"version": 1, "cohort": cohort_id, "task_set": cohort["task_set"], "task_count": cohort["task_count"], "track": cohort["track"],
            "full_benchmark": cohort["full_benchmark"], "runs": cohort["runs"], "latest": cohort.get("latest"), "first": cohort.get("first"),
            "baseline": baseline_id, "standings": rows, "hero": hero_rows(m, shown),
            "patterns": patterns(pattern_attempts, {sid: m["setups"].get(sid, {}).get("name", sid) for sid in shown}),
            "run_analyses": run_analyses,
            "lab_setups": lab_setups(shown, m["setups"]),
            "pairings": pairings({sid: groups[sid] for sid in shown if sid in groups}),
            "excluded": [{"id": r["id"], "title": r.get("title"), "reason": exclusion_reason(studio.job(r["id"]))} for r in cohort["runs"] if not r["full_benchmark"]],
            "paired": paired_table(job, m, shown, baseline_id), "matrix": matrix_cells(job, shown, studio.tasks), "tasks": task_rows(job, studio.tasks),
            "overlap": [o for o in m["overlap"] if o["a"] in shown and o["b"] in shown],
            "setups": {sid: {**m["setups"][sid], "short_name": short_name(m["setups"][sid]["name"])} for sid in shown if sid in m["setups"]}, "order": shown,
            "trend": trend, "trend_title": trend_title, "repetitions": m["repetitions"],
            # The round's argument: accuracy with its uncertainty above, then what it
            # costs to configure once and run again (FR-029, FR-030).
            "curve": break_even_block(groups, shown, baseline_id, {s["id"]: short_name(s["name"]) for s in standings}),
            "caveats": caveats.for_round({**cohort, "baseline": baseline_id}),
            "note": cohort.get("note"),
            "method": {"task_set": cohort["task_set"], "task_count": cohort["task_count"], "task_hashes": cohort["task_hashes"], "runs": [r["id"] for r in cohort["runs"]],
                       "repetitions": m["repetitions"], "fork": caveats.fork_version(), "benchmark": cohort.get("benchmark")}}


def index(studio) -> dict:
    """The Reports front door: rounds newest first, each with its runs and grades."""
    groups = sorted(cohorts(studio).values(), key=lambda c: c["latest"] or "", reverse=True)
    rounds = []
    for cohort in groups:
        job = pooled_job(studio, cohort)
        m = measures.run_measures(job, [])
        shown = setup_ids(job)
        baseline_id = m["baseline"] if m["baseline"] in shown else None
        baseline = m["setups"].get(baseline_id) if baseline_id else None
        best = max([m["setups"][s] for s in shown if s in m["setups"] and s != baseline_id and m["setups"][s]["pass"]["attempts"]], key=lambda s: (s["pass"]["rate"] or 0), default=None)
        rounds.append({"id": cohort["id"], "task_count": cohort["task_count"], "track": cohort["track"], "full_benchmark": cohort["full_benchmark"], "latest": cohort["latest"],
                       "runs": cohort["runs"], "setups": len(shown), "best": {"name": best["name"], "rate": best["pass"]["rate"], "passed": best["pass"]["passed"], "attempts": best["pass"]["attempts"]} if best else None,
                       "grade": grade(best, baseline) if best else {"grade": "Not comparable", "reason": "no evaluated attempts"}})
    return {"rounds": rounds, "generated_at": datetime.now(timezone.utc).isoformat()}
