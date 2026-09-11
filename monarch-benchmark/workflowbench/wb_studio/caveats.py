"""Caveats for reports, written from data only. Each function returns plain
sentences a reader can act on; nothing here is produced by a model."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORK_NOTE = ("The tasks come from AutomationBench {version}, a repaired fork of Zapier's benchmark. Pass here means the "
             "expected result is present, nothing else changed and the attempt finished normally, so these figures are not "
             "comparable with the AutomationBench numbers Zapier or Artificial Analysis publish.")


def fork_version() -> str:
    """The vendored AutomationBench version, read from the vendored copy when
    present so the sentence never drifts from what actually ran."""
    for path in (ROOT / "vendor" / "automation-bench" / "VENDORED-FROM.txt", ROOT / "vendor" / "automation-bench" / "pyproject.toml"):
        try:
            match = re.search(r"(?:expected_version:|version\s*=)\s*\"?([0-9][\w.+-]*)", path.read_text(encoding="utf-8"))
            if match:
                return match.group(1)
        except OSError:
            continue
    match = re.search(r'automation-bench==([\w.+-]+)', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return match.group(1) if match else "unknown version"


def efforts_by_setup(job) -> dict:
    out = {}
    for arm in (job.get("settings") or {}).get("arms") or []:
        runner = arm.get("runner_override") or arm.get("runner") or {}
        effort = runner.get("effort")
        if not effort and "@" in str(arm.get("id", "")):
            effort = str(arm["id"]).split("@", 1)[1].split("-")[0]
        out[arm["id"]] = effort or None
    return out


def for_run(job, m, narrative=None, reused=None) -> list[str]:
    """Sentences about one run: what the numbers rest on and what they leave out."""
    out = [FORK_NOTE.format(version=fork_version())]
    setups = m.get("setups", {})
    names = {sid: s.get("name", sid) for sid, s in setups.items()}
    if m.get("unrecorded_attempts"):
        out.append(f"{m['unrecorded_attempts']} of {m['planned_attempts']} planned attempts have no recorded outcome; percentages use recorded attempts only.")
    infra = sum(s["pass"]["infrastructure"] for s in setups.values())
    if infra:
        out.append(f"{infra} attempt{'s' if infra != 1 else ''} stopped with an execution issue and {'are' if infra != 1 else 'is'} excluded from pass rates.")
    unknown = {names[sid]: s["cost"]["unknown_attempts"] for sid, s in setups.items() if s["cost"]["unknown_attempts"]}
    if unknown:
        out.append("Cost is unknown for " + ", ".join(f"{name} ({n} attempt{'s' if n != 1 else ''} without a settled receipt)" for name, n in unknown.items()) + "; cost figures for those setups are shown as unknown, never estimated.")
    efforts = efforts_by_setup(job)
    known_efforts = {e for e in efforts.values() if e}
    if len(known_efforts) > 1:
        out.append("Thinking settings differ across setups (" + ", ".join(f"{names.get(sid, sid)}: {e}" for sid, e in efforts.items() if e) + "); paired deltas compare setups as configured, not models at equal effort.")
    if reused:
        out.append(f"No Bare setup ran in this run. The Bare baseline is reused from the run \"{reused['title']}\" finished on {str(reused['finished_at'])[:10]}: "
                   "the same model, the same thinking setting and the same frozen tasks, recorded then and not run again.")
    elif not m.get("baseline"):
        out.append("No Bare baseline ran in this run, and no earlier run recorded one with the same model, thinking setting and tasks, so paired deltas and the grade are not available.")
    k = m.get("repetitions") or 1
    if k > 1:
        out.append(f"Each task ran {k} times per setup; the \"passed all {k} times\" column counts a task only when every try passed.")
    else:
        out.append("Each task ran once per setup, so nothing here says how consistent a setup is from one try to the next.")
    if any(s["cost"]["total"] is not None for s in setups.values()):
        out.append("Costs are settled from provider receipts at each model's recorded price table; cached and uncached tokens are priced separately.")
    if narrative:
        if narrative.get("status") == "pending":
            reason = str(narrative.get("reason") or "the analysis has not run yet.")
            # Nothing to interpret is a state, not a wait.
            out.append(("No model analysis: " if "nothing to interpret" in reason.lower() else "Analysis pending: ") + reason)
        elif narrative.get("status") == "failed":
            out.append("The model interpretation did not complete; only the recorded verdicts and counts appear here.")
        elif narrative.get("status") == "completed":
            out.append("Model findings are interpretations that cite recorded events; the deterministic verdict is authoritative.")
    return out


def for_round(cohort) -> list[str]:
    out = [FORK_NOTE.format(version=fork_version())]
    runs = cohort.get("runs", [])
    if len(runs) > 1:
        out.append(f"Figures combine {len(runs)} runs on the same frozen task set; setups that ran more than once are pooled.")
    if not cohort.get("full_benchmark"):
        out.append("This task set is not the frozen benchmark of 50 tasks, so these standings do not count for the leaderboard.")
    if not cohort.get("baseline"):
        out.append("No Bare baseline ran on this task set, so paired deltas and grades are not available.")
    return out
