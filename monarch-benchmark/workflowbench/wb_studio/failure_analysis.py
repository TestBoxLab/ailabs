"""Read-only, deterministic outcome diagnostics; never a causal model review."""
from collections import Counter, defaultdict

from wb_studio.narrative import MODES, run_story
from wb_studio.reports import outcome_report


BUCKETS = dict(MODES)
# Our own checker could not answer. That is a fact about our run, not an outcome the
# competitor produced, and it must not sit in the same list as "missing action": the
# engineer loop reads these buckets to choose what to write a spec against, and a
# grader crash bucketed as `unclassified` becomes a round's headline failure mode.
BUCKETS["ungraded"] = "Not graded (our checker could not answer)"
# The same buckets in the two or three words a chart axis can hold.
SHORT_LABELS = {
    "ungraded": "Not graded",
    "missing_action": "Missing action",
    "wrong_result": "Wrong result",
    "forbidden_action": "Forbidden action",
    "scope_violation": "Out of scope",
    "tool_error": "Tool error",
    "stopped_short": "Stopped short",
    "ran_out": "Ran out",
    "infrastructure": "Infrastructure",
    "unclassified": "Unclassified",
}
LIMITATION = (
    "Buckets describe recorded outcomes, not proven causes. The earliest cited error is an "
    "observation, not the first causal mistake. Missing trace events do not prove missing actions."
)


def _percentages(counts, denominator):
    """Largest remainder rounding keeps the exclusive failed-attempt partition at 100%."""
    if not denominator:
        return [None for _ in counts]
    units = [count * 10000 // denominator for count in counts]
    missing = 10000 - sum(units)
    order = sorted(range(len(counts)), key=lambda i: (-(counts[i] * 10000 % denominator), i))
    for index in order[:missing]:
        units[index] += 1
    return [value / 100 for value in units]


def _bucket(result, report):
    if result.get("passed"):
        return "success"
    from wb_studio.measures import is_ungraded
    # Before any outcome mode: the attempt has no measured outcome to classify. It reaches
    # here looking like a normal completed failure -- termination is `completed` and the
    # checks list is empty -- so the story fell through to `unclassified`.
    if is_ungraded(result):
        return "ungraded"
    story = report.get("story") or {}
    mode = story.get("mode")
    if mode in MODES:
        return mode
    return "unclassified"


def _attempt(result, trace, report, index):
    bucket = _bucket(result, report)
    titles = {r["check_index"]: r["title"] for r in report["requirements"]}
    checks = [{"name": check["type"], "title": titles.get(i, check["type"]),
               "passed": check["passed"], "check_index": i}
              for i, check in enumerate(result.get("checks", []))]
    finish_ids = [e["id"] for e in trace if e["type"] in ("attempt_finished", "result")]
    facts = [{"text": "Recorded termination: " + result["termination"] + ".",
              "event_ids": finish_ids, "check_names": [], "source": "result.termination"}]
    for check in checks:
        verdict = "Passed" if check["passed"] is True else "Failed" if check["passed"] is False else "Not evaluated"
        facts.append({"text": verdict + ": " + check["title"], "event_ids": finish_ids,
                      "check_names": [check["name"]], "check_index": check["check_index"], "source": "result.checks"})
    writes = [a for a in report["actions"] if a.get("method") not in (None, "GET")]
    for change, raw in zip(report["change_summaries"], report["unexpected_changes"]):
        facts.append({"text": change, "event_ids": finish_ids,
                      "check_names": ["allowed_changes_only"], "source": "result.unexpected_changes"})
        suspects = [w for w in writes if str(raw.get("service", "")).split("_")[0].lower() in str(w.get("url", "")).lower()] or writes
        if suspects:
            facts.append({"text": "Writes that could have made this change: " + "; ".join(
                              f'{w["method"]} {w["url"]}' for w in suspects) + ".",
                          "event_ids": [w["event_id"] for w in suspects], "check_names": ["allowed_changes_only"],
                          "source": "trace.api_fetch"})
    errors = [e for e in trace if e["type"] == "attempt_error" or
              (e["type"] in ("node_finished", "model_finished", "step_finished") and e.get("status") == "error")]
    first = errors[0] if errors else next((e for e in trace if e["type"] in ("attempt_finished", "result") and not result["passed"]), None)
    earliest = None if first is None else {
        "event_id": first["id"], "type": first["type"],
        "text": "Recorded failure verdict." if first["type"] in ("attempt_finished", "result") else "Recorded error event; its causal connection to the final outcome is unverified.",
    }
    unmet = [c["title"] for c in checks if c["passed"] is False and c["name"] != "allowed_changes_only"]
    passed = [c["title"] for c in checks if c["passed"] is True and c["name"] != "allowed_changes_only"]
    if bucket == "success":
        headline = "Task passed its recorded evaluator checks"
        narrative = "Satisfied: " + "; ".join(passed) + "." if passed else "The recorded overall verdict passed; no individual requirement checks were retained."
    else:
        headline = BUCKETS.get(bucket, "Failed")
        story = report.get("story") or {}
        story_verdict = story.get("verdict")
        if bucket == "infrastructure":
            narrative = "Execution ended with " + str(result.get("termination", "")) + "; this attempt is not a valid model-quality measurement."
        elif bucket == "ran_out":
            narrative = story_verdict or ("Execution stopped at the recorded limit: " + str(result.get("termination", "")) + ".")
        elif bucket == "scope_violation":
            narrative = story_verdict or "The evaluator recorded changes outside permitted scope."
            if report.get("change_summaries"):
                narrative += " " + " ".join(report["change_summaries"])
            if unmet:
                narrative += " Unmet: " + "; ".join(unmet) + "."
        elif bucket in ("missing_action", "wrong_result", "forbidden_action", "stopped_short", "tool_error"):
            narrative = story_verdict or ("Unmet: " + "; ".join(unmet) + "." if unmet else BUCKETS[bucket])
        else:
            narrative = "The overall verdict failed, but retained checks and termination do not support a more specific outcome category."
    if result.get("error"):
        facts.append({"text": "Recorded error message: " + str(result["error"]), "event_ids": finish_ids,
                      "check_names": [], "source": "result.error"})
    return {"id": "attempt-" + str(index + 1), "task": result["task"], "model": result["model"],
            "passed": result["passed"], "infrastructure": report["infrastructure"], "bucket": bucket,
            "headline": headline, "narrative": narrative, "termination": result["termination"],
            "checks": checks, "observed_facts": facts, "earliest_supported_evidence": earliest, "story": report.get("story"),
            "event_ids": [e["id"] for e in trace], "causal_hypotheses": [], "limitations": LIMITATION,
            **{key: result[key] for key in ("invariant_passed", "unexpected_changes", "count_violations", "receipt_source") if key in result}}


def analysis(studio, identity):
    """Analyze only saved completed attempts, including failures; never dispatch or write."""
    job = studio.job(identity)
    events = studio.events(identity)
    from wb_studio.report_receipts import enrich
    results = enrich(studio, identity, job["results"])
    # Separate repeated task/model attempts at journal completion boundaries. A partial
    # later attempt must never lend its errors to an earlier completed result.
    grouped, pending, episodes = defaultdict(list), defaultdict(list), defaultdict(list)
    identified_pairs = set()
    for event in events:
        key = (event.get("task"), event.get("model"))
        if event.get("episode_id"):
            episodes[event["episode_id"]].append(event)
            identified_pairs.add(key)
        if None in key:
            continue
        pending[key].append(event)
        if event["type"] in ("attempt_finished", "result"):
            grouped[key].append(pending.pop(key))
    counts = Counter((r["task"], r["model"]) for r in results)
    occurrences, attempts = Counter(), []
    for index, result in enumerate(results):
        key = (result["task"], result["model"])
        occurrence = occurrences[key]
        occurrences[key] += 1
        segments = grouped[key]
        episode = result.get("episode_id")
        if episode and (episode in episodes or key in identified_pairs):
            # Imported/resumed receipts may repeat or arrive out of order. An
            # explicit episode identity always takes precedence over chronology.
            trace = [event for event in episodes[episode]
                     if event.get("task", key[0]) == key[0] and event.get("model", key[1]) == key[1]]
        else:
            trace = segments[occurrence] if occurrence < len(segments) else pending[key] if counts[key] == 1 and not segments else []
        # Missing legacy fields were filled from exact read-only receipts. Avoid
        # opening Store here: its initialization can migrate/write the results DB.
        report = outcome_report({"id": identity, "results": [result]}, trace, studio.tasks)["attempts"][0]
        attempts.append(_attempt(result, trace, report, index))
    failed = sum(not attempt["passed"] for attempt in attempts)
    bucket_counts = Counter(a["bucket"] for a in attempts if not a["passed"])
    percentages = _percentages([bucket_counts[k] for k in BUCKETS], failed)
    buckets = [{"id": key, "label": label, "short_label": SHORT_LABELS[key],
                "count": bucket_counts[key], "percent_failed": percentages[i],
                "percent_all": round(bucket_counts[key] * 100 / len(attempts), 2) if attempts else None,
                "attempt_ids": [a["id"] for a in attempts if a["bucket"] == key]}
               for i, (key, label) in enumerate(BUCKETS.items())]
    settings = job.get("settings", {})
    models = [arm["id"] for arm in settings["arms"]] if settings.get("arms") else settings.get("models", [])
    planned_pairs = {(task, model) for task in settings.get("tasks", []) for model in models}
    planned = len(planned_pairs)
    unrecorded = len(planned_pairs - set(counts))
    return {"version": 1, "run": identity, "basis": "Recorded results, deterministic evaluator checks and trace events; no model review",
            "summary": {"recorded_attempts": len(attempts), "successful_attempts": len(attempts) - failed,
                        "failed_attempts": failed, "infrastructure_attempts": sum(a["infrastructure"] for a in attempts),
                        "planned_attempts": planned, "unrecorded_attempts": unrecorded},
            "denominators": {"percent_failed": "All recorded failed attempts, including infrastructure interruptions",
                             "percent_all": "All recorded attempts, including successes and infrastructure interruptions",
                             "unrecorded_attempts": "Planned attempts without saved results; excluded from outcome percentages"},
            "classification_policy": "One bucket per failed attempt: explicit budget/timeout, infrastructure, scope violation, unmet requirement, then unclassified. These are outcome categories, not causal attributions.",
            "buckets": buckets, "attempts": attempts, "limitations": LIMITATION, "story": run_story(attempts)}
