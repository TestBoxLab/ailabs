"""Exclusive outcome mixes from saved attempts; behavior is the existing story's reading.

No model calls, no grading, no root-cause inference. Every count retains its exact
run and result index, including repetitions and historical, non-regradable rows.
"""
from wb_studio.failure_analysis import SHORT_LABELS, _percentages
from wb_studio.narrative import MODES
from wb_studio.reports import CATEGORIES

BEHAVIOR = {"passed": "Passed", **SHORT_LABELS}
CHECKS = {"passed": "Passed", "scope": "Scope check failed", "requirements": "Requirements unmet",
          "scope_and_requirements": "Scope and requirements failed", "unfinished": "Did not finish normally",
          "infrastructure": "Infrastructure", "ungraded": "Not graded",
          "unclassified": "Unknown from retained checks"}
DENOMINATOR = ("All recorded attempts for this setup, including passes, infrastructure, attempts our "
               "own checker could not grade, and unknown outcomes. Unrecorded attempts are excluded.")


def behavior(attempt):
    if attempt.get("infrastructure"):
        return "infrastructure"
    if attempt.get("passed") is True:
        return "passed"
    # Named before the story is read. An ungraded attempt carries `completed` and an empty
    # checks list, so both readings below fell through to "unclassified" and published our
    # checker's crash as a competitor failure of unknown cause -- in the report, and in the
    # evidence the model that writes the report reads.
    if _ungraded(attempt):
        return "ungraded"
    mode = (attempt.get("story") or {}).get("mode")
    return mode if mode in MODES else "unclassified"


def _ungraded(attempt):
    from wb_studio.measures import is_ungraded
    return is_ungraded(attempt)


def checked_outcome(attempt):
    if attempt.get("infrastructure"):
        return "infrastructure"
    if attempt.get("passed") is True:
        return "passed"
    if _ungraded(attempt):
        return "ungraded"
    failed = {c.get("name") or c.get("type") for c in attempt.get("checks") or [] if c.get("passed") is False}
    scope, unmet = "allowed_changes_only" in failed, bool(failed - {"allowed_changes_only"})
    if scope and unmet:
        return "scope_and_requirements"
    if scope:
        return "scope"
    if unmet:
        return "requirements"
    if attempt.get("termination") not in (None, "", "completed"):
        return "unfinished"
    return "unclassified"


def _ref(attempt, index, run):
    identity = attempt.get("run") or run
    # failure_analysis uses the original result order, independent of setup filtering.
    source_id = str(attempt.get("id") or "")
    result_index = int(source_id.removeprefix("attempt-")) - 1 if source_id.startswith("attempt-") and source_id.removeprefix("attempt-").isdigit() else index
    return {"key": f"{identity}:{result_index}", "run": identity, "index": result_index,
            "task": attempt.get("task"), "model": attempt.get("model"),
            "event_ids": list(attempt.get("event_ids") or []), "liveness": attempt.get("liveness"),
            "explanation": (attempt.get("story") or {}).get("verdict") or attempt.get("narrative") or "No detailed reading retained.",
            "termination": attempt.get("termination"), "checks": attempt.get("checks") or []}


def _column(rows, identity, name):
    selected = [r for r in rows if r[0].get("model") == identity]
    out = {"id": identity, "name": name, "total": len(selected)}
    for key, labels, classify in (("behavior", BEHAVIOR, behavior), ("checks", CHECKS, checked_outcome)):
        groups = {category: [ref for a, ref in selected if classify(a) == category] for category in labels}
        percents = _percentages([len(groups[k]) for k in labels], len(selected))
        out[key] = [{"id": category, "label": label, "count": len(groups[category]),
                     "percent": percents[i], "attempts": groups[category]}
                    for i, (category, label) in enumerate(labels.items())]
    out["historical"] = sum(ref.get("liveness") not in (None, "live") for _, ref in selected)
    return out


def patterns(attempts, setups, run=None):
    """Build setup and business-domain slices, sharing the same attempt references."""
    setups = dict(setups)
    for attempt in attempts:
        setups.setdefault(attempt['model'], attempt['model'])
    rows = [(a, _ref(a, i, run)) for i, a in enumerate(attempts)]
    domains = sorted({str(a.get("task") or "unknown").split(".")[0] for a, _ in rows})
    return {"version": 1, "denominator": DENOMINATOR,
            "behavior_basis": "Passed and infrastructure come from recorded outcomes. Other modes describe the behavior recorded in each attempt’s timeline, not proven causes.",
            "checks_basis": "Mutually exclusive combinations of retained evaluator checks and termination; separate from behavioral interpretation.",
            "setups": [_column(rows, identity, name) for identity, name in setups.items()],
            "domains": [{"id": domain, "label": CATEGORIES.get(domain, domain.replace("_", " ").title()),
                         "setups": [_column([(a, ref) for a, ref in rows if str(a.get("task") or "unknown").split(".")[0] == domain], identity, name)
                                    for identity, name in setups.items()]} for domain in domains]}


def compact(data):
    """The same computed slices for Genesis, with shared references instead of repeated prose."""
    references = {}
    def column(c):
        out = {k: c[k] for k in ("id", "name", "total", "historical")}
        for field in ("behavior", "checks"):
            out[field] = []
            for item in c[field]:
                keys = []
                for ref in item["attempts"]:
                    references[ref["key"]] = {k: ref.get(k) for k in ("run", "index", "task", "model", "event_ids", "liveness")}
                    keys.append(ref["key"])
                out[field].append({k: item[k] for k in ("id", "label", "count", "percent")} | {"attempt_keys": keys})
        return out
    result = {k: data[k] for k in ("version", "denominator", "behavior_basis", "checks_basis")}
    result["setups"] = [column(c) for c in data["setups"]]
    result["domains"] = [{"id": d["id"], "label": d["label"], "setups": [column(c) for c in d["setups"]]} for d in data["domains"]]
    result["attempts"] = references
    return result
