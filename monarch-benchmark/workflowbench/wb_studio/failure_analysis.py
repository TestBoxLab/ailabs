"""Read-only, deterministic outcome diagnostics; never a causal model review."""
from collections import Counter, defaultdict

from wb_studio.reports import outcome_report


BUCKETS = {
    "infrastructure": "Infrastructure interruption",
    "budget_limit": "Recorded budget limit",
    "timeout": "Recorded timeout or cancellation",
    "unintended_changes": "Changes outside permitted scope",
    "requirement_unmet": "Recorded requirements unmet",
    "unclassified": "Insufficient evidence to classify",
}
BUDGET_TERMINATIONS = {"infra:attempt_cap", "infra:weekly_budget"}
TIMEOUT_TERMINATIONS = {"timeout", "infra:timeout"}
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
    termination = result["termination"]
    if result["passed"]:
        return "success"
    if termination in BUDGET_TERMINATIONS:
        return "budget_limit"
    if termination in TIMEOUT_TERMINATIONS:
        return "timeout"
    if report["infrastructure"]:
        return "infrastructure"
    if report["scope_respected"] is False or report["unexpected_changes"]:
        return "unintended_changes"
    if any(check["passed"] is False for check in report["requirements"]):
        return "requirement_unmet"
    return "unclassified"


def _attempt(result, trace, report, index):
    bucket = _bucket(result, report)
    titles = {r["check_index"]: r["title"] for r in report["requirements"]}
    checks = [{"name": check["type"], "title": titles.get(i, check["type"]),
               "passed": check["passed"], "check_index": i}
              for i, check in enumerate(result.get("checks", []))]
    finish_ids = [e["id"] for e in trace if e["type"] == "attempt_finished"]
    facts = [{"text": "Recorded termination: " + result["termination"] + ".",
              "event_ids": finish_ids, "check_names": [], "source": "result.termination"}]
    for check in checks:
        verdict = "Passed" if check["passed"] is True else "Failed" if check["passed"] is False else "Not evaluated"
        facts.append({"text": verdict + ": " + check["title"], "event_ids": finish_ids,
                      "check_names": [check["name"]], "check_index": check["check_index"], "source": "result.checks"})
    for change in report["change_summaries"]:
        facts.append({"text": change, "event_ids": finish_ids,
                      "check_names": ["allowed_changes_only"], "source": "result.unexpected_changes"})
    errors = [e for e in trace if e["type"] == "attempt_error" or
              (e["type"] in ("node_finished", "model_finished", "step_finished") and e.get("status") == "error")]
    first = errors[0] if errors else next((e for e in trace if e["type"] == "attempt_finished" and not result["passed"]), None)
    earliest = None if first is None else {
        "event_id": first["id"], "type": first["type"],
        "text": "Recorded failure verdict." if first["type"] == "attempt_finished" else "Recorded error event; its causal connection to the final outcome is unverified.",
    }
    unmet = [c["title"] for c in checks if c["passed"] is False and c["name"] != "allowed_changes_only"]
    passed = [c["title"] for c in checks if c["passed"] is True and c["name"] != "allowed_changes_only"]
    if bucket == "success":
        headline = "Task passed its recorded evaluator checks"
        narrative = "Satisfied: " + "; ".join(passed) + "." if passed else "The recorded overall verdict passed; no individual requirement checks were retained."
    else:
        headline = BUCKETS[bucket]
        narrative = {
            "infrastructure": "Execution ended with " + result["termination"] + "; this attempt is not a valid model-quality measurement.",
            "budget_limit": "Execution stopped at the recorded " + result["termination"] + " admission limit.",
            "timeout": "Execution recorded " + result["termination"] + ". The record does not by itself distinguish deadline exhaustion from cancellation.",
            "unintended_changes": "The evaluator recorded changes outside permitted scope.",
            "requirement_unmet": "Unmet: " + "; ".join(unmet) + ".",
            "unclassified": "The overall verdict failed, but retained checks and termination do not support a more specific outcome category.",
        }[bucket]
        if bucket == "unintended_changes" and report["change_summaries"]:
            narrative += " " + " ".join(report["change_summaries"])
        if unmet and bucket not in ("requirement_unmet", "infrastructure", "budget_limit", "timeout"):
            narrative += " Unmet: " + "; ".join(unmet) + "."
    if result.get("error"):
        facts.append({"text": "Recorded error message: " + str(result["error"]), "event_ids": finish_ids,
                      "check_names": [], "source": "result.error"})
    return {"id": "attempt-" + str(index + 1), "task": result["task"], "model": result["model"],
            "passed": result["passed"], "infrastructure": report["infrastructure"], "bucket": bucket,
            "headline": headline, "narrative": narrative, "termination": result["termination"],
            "checks": checks, "observed_facts": facts, "earliest_supported_evidence": earliest,
            "event_ids": [e["id"] for e in trace], "causal_hypotheses": [], "limitations": LIMITATION}


def analysis(studio, identity):
    """Analyze only saved completed attempts, including failures; never dispatch or write."""
    job = studio.job(identity)
    events = studio.events(identity)
    results = job["results"]
    # Separate repeated task/model attempts at journal completion boundaries. A partial
    # later attempt must never lend its errors to an earlier completed result.
    grouped, pending = defaultdict(list), defaultdict(list)
    for event in events:
        key = (event.get("task"), event.get("model"))
        if None in key:
            continue
        pending[key].append(event)
        if event["type"] == "attempt_finished":
            grouped[key].append(pending.pop(key))
    counts = Counter((r["task"], r["model"]) for r in results)
    occurrences, attempts = Counter(), []
    for index, result in enumerate(results):
        key = (result["task"], result["model"])
        occurrence = occurrences[key]
        occurrences[key] += 1
        segments = grouped[key]
        trace = segments[occurrence] if occurrence < len(segments) else pending[key] if counts[key] == 1 and not segments else []
        # Job results already retain the evaluator checks and scope changes. Avoid
        # opening Store here: its initialization can migrate/write the results DB.
        report = outcome_report({"id": identity, "results": [result]}, trace, studio.tasks)["attempts"][0]
        attempts.append(_attempt(result, trace, report, index))
    failed = sum(not attempt["passed"] for attempt in attempts)
    bucket_counts = Counter(a["bucket"] for a in attempts if not a["passed"])
    percentages = _percentages([bucket_counts[k] for k in BUCKETS], failed)
    buckets = [{"id": key, "label": label, "count": bucket_counts[key], "percent_failed": percentages[i],
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
            "buckets": buckets, "attempts": attempts, "limitations": LIMITATION}
