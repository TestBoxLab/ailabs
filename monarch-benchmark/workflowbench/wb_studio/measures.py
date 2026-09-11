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
# A cohort that never passed has no cost per pass. That is a fact about the cohort,
# not a gap in the record, and the contract forbids reporting it as unknown.
NO_PASSES = Sentinel("no_passes")


def is_not_applicable(val) -> bool:
    return val is NOT_APPLICABLE or val == "not_applicable" or val == "n/a"


def is_unknown(val) -> bool:
    return val is UNKNOWN or val == "unknown"


# The whole attempt, written by the orchestrator beside whatever phases the arm
# recorded. It is the TOTAL, never a part: summing it with the parts doubles the round.
TOTAL_PHASE = "run"
# The same money cut by model rather than by phase (`wb_report.metrics`). Also never
# a part. Duplicated here rather than imported so measures stays free of wb_report.
SYNTHETIC_PHASE = "model:"
# The phases the fitness function is defined over, in the order a report reads them.
COST_PHASES = ("authoring", "execution", "discovery")
# Money the price table saw that no named phase claimed. Kept and named, never dropped.
UNATTRIBUTED = "unattributed"
CENT = 0.01
SECOND = 1.0


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


def is_ungraded(result):
    return bool(result.get("ungraded")) or "grading=ungraded" in (result.get("flags") or [])


def evaluated(rows):
    return [r for r in rows if not is_infrastructure(r) and not is_ungraded(r)]


def pass_rate(rows) -> dict:
    valid = evaluated(rows)
    passed = sum(bool(r.get("passed")) for r in valid)
    low, high = wilson(passed, len(valid))
    return {"passed": passed, "attempts": len(valid), "infrastructure": sum(is_infrastructure(r) for r in rows),
            "ungraded": sum(is_ungraded(r) for r in rows),
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


def phase_cost(result: dict, phase: str):
    """One attempt's cost for one phase: a number, UNKNOWN, or NOT_APPLICABLE.

    The three are kept apart on purpose (contract §Cost). `n/a` means this competitor
    has no such phase — a bare model never configures anything, and calling that zero
    would make it look free at the one thing Monarch charges for. `unknown` means the
    phase ran and nobody could price it; it holds its ledger reservation, and calling
    *that* zero would settle a hold against money we know was spent.
    """
    phases = result.get("phases") or {}
    if phase == TOTAL_PHASE:
        value = known_cost(result)
        return UNKNOWN if value is None else value
    if phase not in phases:
        # Absent is the arm's own statement: it records a phase in a `finally`, so a
        # phase it ran is present even when the attempt died inside it.
        return NOT_APPLICABLE
    if known_cost(result) is None:
        return UNKNOWN          # the whole read failed; no part of it is trustworthy
    value = (phases[phase] or {}).get("cost_usd")
    if value is None:
        return UNKNOWN
    try:
        value = float(value)
    except (TypeError, ValueError):
        return UNKNOWN
    return value if math.isfinite(value) and value >= 0 else UNKNOWN


def cost_by_phase(rows) -> dict:
    """FR-024. Cohort cost split at the authoring boundary, reconciled against the total.

    Configure once, execute many: this split is what the break-even curve is computed
    from, so a phase that quietly loses money would move the crossing point. Anything
    the named phases do not claim is returned as `unattributed` rather than dropped,
    and `reconciles` says whether that bucket was needed.
    """
    totals = {phase: 0.0 for phase in COST_PHASES}
    seen = {phase: False for phase in COST_PHASES}
    grand, unknown_attempts = 0.0, 0
    for r in rows:
        attempt_total = known_cost(r)
        if attempt_total is None:
            unknown_attempts += 1
            continue
        for phase in COST_PHASES:
            value = phase_cost(r, phase)
            if is_unknown(value):
                unknown_attempts += 1
                break
            if is_not_applicable(value):
                continue
            seen[phase] = True
            totals[phase] += value
        else:
            grand += attempt_total
    if unknown_attempts:
        # Same discipline as `cost`: one unreadable attempt makes the cohort's total
        # unknown rather than a sum that silently omits it.
        return {"phases": {}, "total": None, UNATTRIBUTED: None, "reconciles": False,
                "unknown_attempts": unknown_attempts, "attempts": len(rows),
                "not_applicable": [p for p in COST_PHASES if not seen[p]]}
    out = {phase: round(totals[phase], 6) for phase in COST_PHASES if seen[phase]}
    residual = round(grand - sum(out.values()), 6)
    reconciles = abs(residual) <= CENT
    if not reconciles:
        out[UNATTRIBUTED] = residual
    return {"phases": out, "total": round(grand, 6), UNATTRIBUTED: residual,
            "reconciles": reconciles, "unknown_attempts": 0, "attempts": len(rows),
            "not_applicable": [p for p in COST_PHASES if not seen[p]]}


def phase_seconds(result: dict, phase: str):
    """One attempt's wall clock for one phase. Absent phase is NOT_APPLICABLE, not zero."""
    phases = result.get("phases") or {}
    if phase == TOTAL_PHASE:
        recorded = (phases.get(TOTAL_PHASE) or {}).get("wall_clock_s")
        recorded = result.get("seconds") if recorded is None else recorded
        return UNKNOWN if recorded is None else float(recorded)
    if phase not in phases:
        return NOT_APPLICABLE
    value = (phases[phase] or {}).get("wall_clock_s")
    return UNKNOWN if value is None else float(value)


def time_by_phase(rows) -> dict:
    """FR-025. Time to a saved workflow, then time per execution.

    The clocks are already recorded — the arm stamps each phase in a `finally`, so no
    new timestamp is needed and a timed-out attempt still reports where the deadline
    passed. This reads them and checks each attempt's parts against its own total.
    """
    configure, execute, total = 0.0, 0.0, 0.0
    counted, reconciles = 0, True
    for r in evaluated(rows):
        whole = phase_seconds(r, TOTAL_PHASE)
        if is_unknown(whole):
            continue
        parts = 0.0
        for phase, bucket in (("authoring", "configure"), ("execution", "execute")):
            value = phase_seconds(r, phase)
            if isinstance(value, float):
                parts += value
                if bucket == "configure":
                    configure += value
                else:
                    execute += value
        if parts and abs(whole - parts) > SECOND:
            # The attempt spent time in neither phase. Worth seeing, not worth hiding.
            reconciles = False
        total += whole
        counted += 1
    if not counted:
        return {"configure_s": None, "execute_s": None, "total_s": None,
                "reconciles": True, "attempts": 0}
    return {"configure_s": round(configure, 4), "execute_s": round(execute, 4),
            "total_s": round(total, 4), "reconciles": reconciles, "attempts": counted}


def per_execution(rows) -> dict:
    """FR-027. What one execution of an already-saved workflow costs and takes.

    The second half of the break-even curve. In run-only mode nothing is authored —
    the recipe was configured once by `wb monarch recipes`, outside the round — so
    every attempt here is one execution, and `configure_usd` is NOT_APPLICABLE rather
    than zero: reporting zero would make the engine look free to set up.

    A task nobody could price stays unknown on its own row and blinds only the cohort
    figure, which cannot be summed without it.
    """
    tasks: dict = {}
    for r in evaluated(rows):
        task = tasks.setdefault(r["task"], {"executions": 0, "cost_usd": 0.0,
                                            "seconds": 0.0, "passed": 0})
        task["executions"] += 1
        task["passed"] += bool(r.get("passed"))
        seconds = phase_seconds(r, TOTAL_PHASE)
        task["seconds"] += 0.0 if is_unknown(seconds) else seconds
        value = known_cost(r)
        if value is None:
            task["cost_usd"] = UNKNOWN
        elif not is_unknown(task["cost_usd"]):
            task["cost_usd"] += value
    for task in tasks.values():
        if not is_unknown(task["cost_usd"]):
            task["cost_usd"] = round(task["cost_usd"], 6)
        task["seconds"] = round(task["seconds"], 4)
    executions = sum(t["executions"] for t in tasks.values())
    blind = any(is_unknown(t["cost_usd"]) for t in tasks.values())
    total = UNKNOWN if blind else sum(t["cost_usd"] for t in tasks.values())
    seconds = sum(t["seconds"] for t in tasks.values())
    return {"tasks": tasks, "executions": executions, "tasks_counted": len(tasks),
            "cost_usd": UNKNOWN if blind else (round(total / executions, 6) if executions else None),
            "seconds": round(seconds / executions, 4) if executions else None,
            # Paid once, elsewhere. Absent from this round is not free.
            "configure_usd": NOT_APPLICABLE}


def cost_per_pass(rows):
    """FR-028. Cohort cost divided by passes: a cheap competitor that fails is not cheap.

    Returns NO_PASSES rather than UNKNOWN when nothing passed — the record is complete,
    the answer is simply undefined, and a reader told "unknown" would go looking for
    missing data that does not exist.
    """
    out = cost(rows)
    if out["total"] is None:
        return UNKNOWN
    passed = sum(bool(r.get("passed")) for r in evaluated(rows))
    if not passed:
        return NO_PASSES
    return round(out["total"] / passed, 6)


def break_even(configure_usd, execute_usd, per_request_usd, max_n: int) -> dict:
    """FR-029, FR-030. Where a reusable workflow overtakes paying per request.

        product:    configure + n x execute
        comparator: n x per_request

    The crossing point is the least integer n at which the product's cumulative cost
    falls below the comparator's, **within the range of n actually observed**. No
    product in the evaluation landscape plots this, because their subjects have no
    reusable artefact; Monarch does, and the crossing is its whole value proposition.

    Three outcomes, deliberately distinct. A crossing is a measurement. `none-in-range`
    means the lines have not met inside the evidence — they may meet later, and the
    figure says so in words rather than drawing a projection. `never` means executing
    costs at least as much as a whole request, so no n can ever cross; presenting that
    as "not yet" would be a claim the data refutes.
    """
    if is_unknown(configure_usd) or is_unknown(execute_usd) or is_unknown(per_request_usd):
        return {"product": [], "comparator": [], "crossing": UNKNOWN, "reason": "unknown",
                "max_n": max_n, "note": "A cost on one side could not be read."}
    # A per-request competitor has no configure step; its curve starts at the origin.
    setup = 0.0 if is_not_applicable(configure_usd) else float(configure_usd)
    execute, per_request = float(execute_usd), float(per_request_usd)
    product = [round(setup + n * execute, 6) for n in range(1, max_n + 1)]
    comparator = [round(n * per_request, 6) for n in range(1, max_n + 1)]
    crossing = next((n for n in range(1, max_n + 1)
                     if product[n - 1] < comparator[n - 1]), None)
    if crossing is not None:
        reason, note = "crossed", f"Ahead from execution {crossing}."
    elif execute >= per_request:
        # Every extra run widens the gap; the lines diverge and never meet.
        reason = "never"
        note = ("One execution costs at least as much as one request, so the lines "
                "never meet however many times the workflow is run.")
    else:
        reason = "none-in-range"
        note = (f"Not ahead within the {max_n} executions observed. The figure does "
                "not extrapolate past them.")
    return {"product": product, "comparator": comparator, "crossing": crossing,
            "reason": reason, "max_n": max_n, "note": note}


def curve(rows, comparator_rows, max_n: int | None = None) -> dict:
    """The break-even curve of one cohort against another, priced per successful task.

    FR-028: costs are per *pass*, so a competitor that is cheap because it fails is
    not cheap. Both sides are read from stored results by the same rules as every
    other measure, and the figure carries its source line.
    """
    phases = cost_by_phase(rows)
    passes = sum(bool(r.get("passed")) for r in evaluated(rows))
    per_request = cost_per_pass(comparator_rows)

    def share(name):
        if not passes:
            return NO_PASSES
        if phases["total"] is None:
            return UNKNOWN
        if name not in phases["phases"]:
            return NOT_APPLICABLE
        return round(phases["phases"][name] / passes, 6)

    configure, execute = share("authoring"), share("execution")
    executions = max_n or max(1, len(evaluated(rows)))
    out = break_even(configure, execute, per_request, executions)
    out.update({"configure_usd": configure, "execute_usd": execute,
                "per_request_usd": per_request, "passes": passes,
                "basis": "cost per successful task",
                "source": f"{len(evaluated(rows))} attempts, {passes} passed, against "
                          f"{len(evaluated(comparator_rows))} attempts of the comparator"})
    return out


def time(rows) -> dict:
    seconds = []
    for row in evaluated(rows):
        if isinstance(row.get("seconds"), bool):
            continue
        try:
            value = float(row.get("seconds"))
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(value) and value >= 0:
            seconds.append(value)
    seconds.sort()
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


# A paired comparison is settled by `sign_test`, which drops ties, so its power depends
# on the number of tasks the two setups actually disagree on. `DEFAULT_FLIP_RATE` is the
# share of a task set a real improvement is assumed to change: conservative, stated in
# every refusal, and overridable by a caller with evidence.
DEFAULT_FLIP_RATE = 0.35


def wins_needed(pairs: int):
    """The fewest wins out of `pairs` discordant pairs that reach p < 0.05, or None.

    None means the sign test cannot conclude at this size however the run turns out —
    not even a clean sweep. That is true below six pairs, which is why a ten-task set
    cannot settle a hypothesis: an improvement that flips three or four tasks produces
    three or four discordant pairs (feature 024, FR-021).
    """
    for wins in range(int(pairs), -1, -1):
        p = sign_test(wins, int(pairs) - wins)
        if p is None or p >= 0.05:
            return wins + 1 if wins + 1 <= pairs else None
    return None


def minimum_discordant_pairs() -> int:
    """The fewest discordant pairs at which the sign test can reach p < 0.05 at all."""
    n = 1
    while n < 100:
        if wins_needed(n) is not None:
            return n
        n += 1
    raise RuntimeError("the sign test reached no significance below 100 pairs")


def settleable(tasks: int, repetitions: int = 1, flip_rate: float | None = None) -> dict:
    """Whether an experiment of this size can produce a verdict, and what would be enough.

    Checked before any money is reserved. Repetitions do not add discordant pairs — the
    pairing is per task, which is the whole point of clustering — so they raise
    confidence in each task's share, never the number of tasks that can disagree. Only
    the task count moves this.
    """
    rate = DEFAULT_FLIP_RATE if flip_rate is None else float(flip_rate)
    tasks, repetitions = int(tasks), max(1, int(repetitions))
    expected = int(tasks * rate)
    floor = minimum_discordant_pairs()
    needed = wins_needed(expected)
    sufficient = math.ceil(floor / rate) if rate > 0 else None
    floor_word = "Six" if floor == 6 else str(floor)
    if needed is None:
        return {"ok": False, "tasks": tasks, "repetitions": repetitions, "flip_rate": rate,
                "assumed_flip_rate": rate, "expected_pairs": expected, "expected_discordant_pairs": expected,
                "minimum_needed": floor, "wins_needed": None, "sufficient_tasks": sufficient,
                "reason": (f"refused: {tasks} tasks at {repetitions} repetition{'s' if repetitions != 1 else ''} "
                           f"can reach at most {expected} discordant pairs, assuming a flip rate of {rate}. "
                           f"{floor_word} are needed before any win count reaches p<0.05, so this hypothesis "
                           f"cannot be settled at this size however it turns out. "
                           f"Use at least {sufficient} tasks. Repetitions do not help: the pairing is "
                           f"per task, so they raise confidence in each task's share and never change "
                           f"how many tasks can disagree.")}
    return {"ok": True, "tasks": tasks, "repetitions": repetitions, "flip_rate": rate,
            "assumed_flip_rate": rate, "expected_pairs": expected, "expected_discordant_pairs": expected,
            "minimum_needed": floor, "wins_needed": needed, "sufficient_tasks": sufficient,
            "reason": (f"{tasks} tasks at a flip rate of {rate} give about {expected} discordant pairs; "
                       f"{needed} of them must be wins to reach p<0.05.")}


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
