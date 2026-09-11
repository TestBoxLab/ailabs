"""The story of an attempt, written from the record alone.

A postmortem, not a verdict: the verdict is the grader's. This module reads
the trace (prompt, model replies with their reasoning summaries, tool calls),
the checks and the recorded changes, and writes what happened in order, what
went right, what went wrong, where the outcome was fixed, and one failure mode
from a short fixed list. Every sentence cites the events it rests on.

The shape follows what the agent-evaluation literature converged on in 2025:
a factual timeline first (the postmortem backbone); requirements met and
unmet with the action that met or missed them; the earliest recorded step
after which the outcome could not change (AgentRx's first unrecoverable step,
TRAIL's error location); a failure category specific enough that someone else
would label it the same way (Hamel Husain's axial codes, Terminal-Bench's
single-agent reading of MAST); and the run-level check that when every setup
fails a task the same way, the task is the first suspect, not the models
(Anthropic, "Demystifying evals for AI agents").
"""
from __future__ import annotations

import re
from collections import Counter

# ponytail: nine modes, named so a person would pick the same one; extend only
# when a run shows a failure none of these describes.
MODES = {
    "missing_action": "Never made the required change",
    "wrong_result": "Changed the right place, but not as required",
    "forbidden_action": "Did something the task ruled out",
    "scope_violation": "Changed more than the task asked",
    "tool_error": "A tool error it did not recover from",
    "stopped_short": "Stopped without changing anything",
    "ran_out": "Ran out of turns, time or budget",
    "infrastructure": "Infrastructure interruption",
    "unclassified": "Failed for a reason the record does not show",
}
RAN_OUT = {"infra:attempt_cap", "infra:weekly_budget", "timeout", "infra:timeout"}
DONE_WORDS = re.compile(r"\b(done|completed?|updated|sent|created|finished|approved|processed|resolved)\b", re.I)
NORMAL_STOPS = {None, "", "STOP", "stop", "end_turn", "tool_calls", "tool_use", "completed"}
LIMITS = ("Written from the record: the timeline is what was observed, the reasoning is the provider's own summary, "
          "and the turning point is the earliest recorded step after which the outcome could not change, not a proven cause.")


def service_of(assertion: dict) -> str:
    """The service a check names, as the word an API address would contain."""
    words = str(assertion.get("type", "")).split("_")
    if not words or not words[0]:
        return ""
    return words[1] if words[0] == "google" and len(words) > 1 else words[0]


def _on(service: str, action: dict) -> bool:
    return bool(service) and service.lower() in str(action.get("url", "")).lower()


def _clip(text, n=240) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def turns(trace: list[dict], actions: dict[int, dict]) -> list[dict]:
    """Model replies in order, each with the tool calls it made."""
    out, current, open_nodes = [], None, {}
    for e in trace:
        if e["type"] == "model_finished":
            current = {"turn": len(out) + 1, "event_ids": [e["id"]], "reasoning": _clip(" ".join(e.get("reasoning") or [])),
                       "said": _clip(e.get("output")), "stop_reason": e.get("stop_reason"),
                       "status": e.get("status"), "actions": []}
            out.append(current)
        elif e["type"] == "node_started" and current is not None:
            a = actions.get(e["id"], {})
            action = {"event_id": e["id"], "title": a.get("title", e.get("label", "tool call")),
                      "detail": a.get("detail", ""), "method": a.get("method"), "url": a.get("url"),
                      "status": "pending", "error": None}
            current["actions"].append(action)
            current["event_ids"].append(e["id"])
            open_nodes[e.get("node")] = action
        elif e["type"] == "node_finished" and e.get("node") in open_nodes:
            action = open_nodes.pop(e["node"])
            known = actions.get(action["event_id"])
            if known and known.get("status") in ("error", "observed"):
                action["status"], action["error"] = known["status"], _clip(known.get("error"), 160) if known.get("error") else None
            else:
                failed = e.get("status") == "error"
                action["status"] = "error" if failed else "observed"
                action["error"] = _clip(e.get("output"), 160) if failed else None
    return out


def _sentence(t: dict) -> str:
    parts = [f"Turn {t['turn']}"]
    if t["reasoning"]:
        parts.append("thought: " + _clip(t["reasoning"], 160))
    for a in t["actions"]:
        parts.append(a["title"].lower() + (" (" + _clip(a["detail"], 80) + ")" if a["detail"] else "")
                     + (" — failed: " + a["error"] if a["status"] == "error" else ""))
    if not t["actions"] and t["said"]:
        parts.append("replied: " + _clip(t["said"], 160))
    if t["stop_reason"] not in NORMAL_STOPS:
        parts.append("stopped: " + str(t["stop_reason"]))
    return " · ".join(parts) + "."


def story(result: dict, trace: list[dict], report: dict, assertions: list[dict] | None = None) -> dict:
    assertions = list(assertions or [])
    actions = {a["event_id"]: a for a in report.get("actions", [])}
    timeline = turns(trace, actions)
    writes = [a for a in report.get("actions", []) if a.get("method") not in (None, "GET")]
    reads = [a for a in report.get("actions", []) if a.get("method") == "GET"]
    errors = [a for t in timeline for a in t["actions"] if a["status"] == "error"]
    finish = [e["id"] for e in trace if e["type"] == "attempt_finished"]
    last = timeline[-1] if timeline else None
    reqs = report.get("requirements", [])
    met = [r for r in reqs if r["passed"] is True]
    unmet = [r for r in reqs if r["passed"] is False]
    changes = report.get("unexpected_changes", [])
    summaries = report.get("change_summaries", [])
    infra = bool(report.get("infrastructure"))
    termination = result.get("termination", "")

    def service_for(req):
        i = req.get("check_index")
        return service_of(assertions[i]) if i is not None and i < len(assertions) else ""

    def negative(req):
        i = req.get("check_index")
        return i is not None and i < len(assertions) and "_not_" in str(assertions[i].get("type", ""))

    right, wrong = [], []
    for r in met:
        hits = [w for w in writes if _on(service_for(r), w)]
        right.append({"text": "Met: " + r["title"] + ("." if not hits else ", by " + "; ".join(dict.fromkeys(w["title"].lower() for w in hits)) + "."),
                      "event_ids": [w["event_id"] for w in hits] or finish})
    if reqs and not changes and not infra:
        right.append({"text": "Nothing changed outside the request.", "event_ids": finish})
    host = lambda a: (a.get("url") or "").split("/")[2:3]
    checked = [w for w in writes if any(host(rd) == host(w) and rd["event_id"] < w["event_id"] for rd in reads)]
    if writes and len(checked) == len(writes):
        right.append({"text": "Read each application before changing it.", "event_ids": [w["event_id"] for w in writes]})
    calls = sum(len(t["actions"]) for t in timeline)
    if calls and not errors:
        right.append({"text": f"Every tool call succeeded ({calls} in {len(timeline)} turns).", "event_ids": [t["event_ids"][0] for t in timeline]})

    claimed = bool(last and not last["actions"] and unmet and DONE_WORDS.search(last["said"] or ""))
    for r in unmet:
        svc = service_for(r)
        hits = [w for w in writes if _on(svc, w)]
        if negative(r):
            wrong.append({"text": "The task ruled this out and it happened anyway: " + r["title"] + "."
                          + (" The write that did it: " + "; ".join(f'{w["method"]} {w["url"]}' for w in hits[:3]) + "." if hits else ""),
                          "event_ids": [w["event_id"] for w in hits] or finish})
        elif hits:
            wrong.append({"text": "Not met: " + r["title"] + ". The closest write: " + "; ".join(w["title"].lower() + (" (" + _clip(w["detail"], 80) + ")" if w.get("detail") else "") for w in hits[:3]) + ".",
                          "event_ids": [w["event_id"] for w in hits]})
        else:
            wrong.append({"text": "Not met: " + r["title"] + ". No write to " + (svc.title() if svc else "that application") + " was recorded.",
                          "event_ids": finish})
    for summary, raw in zip(summaries, changes):
        svc = str(raw.get("service", "")).split("_")[0]
        suspects = [w for w in writes if _on(svc, w)] or writes
        wrong.append({"text": summary + (" Writes that could have made it: " + "; ".join(f'{w["method"]} {w["url"]}' for w in suspects[:3]) + "." if suspects else ""),
                      "event_ids": [w["event_id"] for w in suspects] or finish})
    if errors:
        wrong.append({"text": f"{len(errors)} tool call{'s' if len(errors) > 1 else ''} failed; the first: {errors[0]['title'].lower()} — {errors[0]['error']}",
                      "event_ids": [a["event_id"] for a in errors]})
    if claimed:
        wrong.append({"text": "The final reply reported the work as done while requirements were unmet: “" + _clip(last["said"], 160) + "”",
                      "event_ids": last["event_ids"][:1]})
    if last and last["stop_reason"] not in NORMAL_STOPS:
        wrong.append({"text": "The model stopped for a reason other than finishing: " + str(last["stop_reason"]) + ".", "event_ids": last["event_ids"][:1]})
    if result.get("error"):
        wrong.append({"text": "Recorded error: " + _clip(result["error"], 200), "event_ids": finish})

    # One failure mode, in the order a reader would rule them out.
    if result.get("passed"):
        mode = "passed"
    elif infra or (termination.startswith("infra:") and termination not in RAN_OUT):
        mode = "infrastructure"
    elif termination in RAN_OUT or "turn limit" in str(result.get("error", "")).lower():
        mode = "ran_out"
    elif errors and (last_action := next((a for t in reversed(timeline) for a in reversed(t["actions"])), None)) and last_action["status"] == "error":
        mode = "tool_error"
    elif any(negative(r) for r in unmet):
        mode = "forbidden_action"
    elif changes:
        mode = "scope_violation"
    elif unmet and not writes:
        mode = "stopped_short"
    elif unmet and any(_on(service_for(r), w) for r in unmet for w in writes):
        mode = "wrong_result"
    elif unmet:
        mode = "missing_action"
    else:
        mode = "unclassified"

    turning = None
    if mode == "tool_error":
        turning = {"event_id": errors[0]["event_id"], "text": "The first tool error, never recovered from: " + errors[0]["title"].lower() + "."}
    elif mode in ("scope_violation", "forbidden_action"):
        first = next((f for f in wrong if f["event_ids"] and f["event_ids"] != finish), None)
        if first:
            turning = {"event_id": min(first["event_ids"]), "text": "The first write outside the request."}
    elif mode == "wrong_result":
        hit = next((w for r in unmet for w in writes if _on(service_for(r), w)), None)
        if hit:
            turning = {"event_id": hit["event_id"], "text": "The write that reached the right place with the wrong content: " + hit["title"].lower() + "."}
    elif mode in ("missing_action", "stopped_short") and last:
        turning = {"event_id": last["event_ids"][0], "text": "The final reply, made without the required change" + (", and reporting the work done" if claimed else "") + "."}
    elif mode == "ran_out" and last:
        turning = {"event_id": last["event_ids"][0], "text": "The last turn before the limit."}

    if result.get("passed"):
        verdict = f"Passed: {len(met)} of {len(reqs)} requirements met and nothing else changed" + (f", in {calls} tool calls." if calls else ".")
    elif mode == "infrastructure":
        verdict = "Not measured: the attempt ended with " + termination + " before it could be judged."
    else:
        verdict = (f"Failed: {len(met)} of {len(reqs)} requirements met" + (f", {len(changes)} change{'s' if len(changes) != 1 else ''} outside the request" if changes else "")
                   + ". " + MODES[mode] + ".")
    return {"verdict": verdict, "mode": mode, "mode_label": MODES.get(mode, "Passed"), "claimed_done": claimed,
            "timeline": [{**t, "sentence": _sentence(t)} for t in timeline], "went_right": right, "went_wrong": wrong,
            "turning_point": turning, "limits": LIMITS}


def without_reasoning(s: dict | None) -> dict | None:
    """The same story for readers outside the lab: the provider's reasoning
    summaries stay internal, the observed timeline does not."""
    if not s:
        return s
    timeline = [{**t, "reasoning": ""} for t in s.get("timeline", [])]
    return {**s, "timeline": [{**t, "sentence": _sentence(t)} for t in timeline]}


def run_story(attempts: list[dict], names: dict[str, str] | None = None) -> dict:
    """What a run's failures have in common, by setup and by task."""
    names = names or {}
    name = lambda m: names.get(m, m)
    setups = list(dict.fromkeys(a["model"] for a in attempts))
    by_setup = []
    for s in setups:
        mine = [a for a in attempts if a["model"] == s]
        failed = [a for a in mine if not a["passed"]]
        counts = Counter(a["story"]["mode"] for a in failed if a.get("story"))
        by_setup.append({"setup": s, "name": name(s), "attempts": len(mine), "failed": len(failed),
                         "modes": [{"mode": m, "label": MODES.get(m, m), "count": c,
                                    "tasks": list(dict.fromkeys(a["task"] for a in failed if (a.get("story") or {}).get("mode") == m))}
                                   for m, c in counts.most_common()]})
    by_task: dict[str, list[dict]] = {}
    for a in attempts:
        by_task.setdefault(a["task"], []).append(a)
    suspect, separating, clean = [], [], []
    for task, rows in by_task.items():
        # A setup may repeat a task; name each setup once, on the side where it finished.
        modes = {(a.get("story") or {}).get("mode") for a in rows if not a["passed"]}
        passed_by = list(dict.fromkeys(name(a["model"]) for a in rows if a["passed"]))
        failed_by = list(dict.fromkeys(name(a["model"]) for a in rows if not a["passed"]))
        if not failed_by:
            clean.append(task)
        elif passed_by:
            separating.append({"task": task, "passed": passed_by, "failed": failed_by})
        elif len(failed_by) >= 2 and len(modes) == 1 and next(iter(modes)) not in (None, "infrastructure", "ran_out"):
            suspect.append({"task": task, "mode_label": MODES[next(iter(modes))], "setups": failed_by})
    paragraphs = []
    for s in by_setup:
        if not s["attempts"]:
            continue
        if not s["failed"]:
            paragraphs.append(f"{s['name']} passed every one of its {s['attempts']} attempts.")
            continue
        ways = ", ".join(f"{m['count']} {'time' if m['count'] == 1 else 'times'} it {m['label'][0].lower() + m['label'][1:]}" for m in s["modes"][:3])
        paragraphs.append(f"{s['name']} failed {s['failed']} of {s['attempts']} attempts: {ways}.")
    if suspect:
        paragraphs.append(f"{len(suspect)} task{'s' if len(suspect) > 1 else ''} failed for every setup in the same way ("
                          + ", ".join(t["task"] for t in suspect) + "): suspect the task or its answer key before the models.")
    if separating:
        paragraphs.append(f"{len(separating)} task{'s' if len(separating) > 1 else ''} separated the setups: "
                          + "; ".join(f"{t['task']} passed by {', '.join(t['passed'])} and failed by {', '.join(t['failed'])}" for t in separating[:5]) + ".")
    if clean and len(by_task) > 1:
        paragraphs.append(f"{len(clean)} of {len(by_task)} tasks passed for every setup.")
    return {"setups": by_setup, "suspect_tasks": suspect, "separating_tasks": separating, "clean_tasks": clean, "paragraphs": paragraphs}
