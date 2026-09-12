"""`wb monarch recipes`: make one known-correct workflow per task, once.

Known-correct means a workflow Monarch itself authored that passed the bench's
own checker on a snapshot the bench took (FR-002, rule 3). Nothing else counts:
a recipe a person wrote is not the product's work.

Per task, up to `--attempts` times on a fresh world: run the create + run attempt,
snapshot, grade. The first workflow that passes is kept and recorded; every other
attempt's workflow is deleted. A task that never passes gets a `missing` row with
the last attempt's reason, and `wb run` excludes it from every competitor's task
set (feature 004, FR-029).

This is the only path of feature 004 that spends model money, so it refuses to
start without an explicit yes, and it is idempotent: a task that already has a
recipe for the current knowledge base costs nothing.

`# ponytail: it drives the create + run arm as-is rather than factoring out an
"author one workflow" helper; the ceiling is that a change to that lifecycle is
felt here too, which is the intent (research R2).`
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import yaml

from grader.grade import grade
from wb_arms.api_loop import EpisodeTimeout, InfraError
from wb_orchestrator import config
from wb_orchestrator.orchestrator import build_arm_for
from wb_world.episode import Episode, load_suite

# What one create + run attempt cost in the smoke runs, used for the band only.
USD_PER_ATTEMPT_LOW = 0.07
USD_PER_ATTEMPT_HIGH = 0.22

DEFAULT_ATTEMPTS = 3


class RecipeOutcome:
    """One task's verdict, printed and then folded into the file (data-model §6)."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.passed = False
        self.workflow_id: str | None = None
        self.recipe_version: int | None = None
        self.attempts_used = 0
        self.reason: str | None = None
        self.detail = ""
        self.cost_usd = 0.0
        self.deleted: list[str] = []
        self.skipped = False        # already had a recipe for this knowledge base


def kb_file_sha(kb_path: Path) -> str:
    """The fingerprint recorded in the recipes file: sha256 of the kb file's bytes."""
    return hashlib.sha256(Path(kb_path).read_bytes()).hexdigest()


def run(product_path, harness_path, tasks_dir=None, plan_path=None, attempts=DEFAULT_ATTEMPTS,
        yes=False, env=None, stdout=None, out_path=None, timeout_s=900.0) -> int:
    """Exit codes per contracts/cli.md: 0 all covered, 1 some missing, 5 not
    approved, 6 the knowledge-base file is missing."""
    import sys
    stdout = stdout or sys.stdout
    env = env if env is not None else {}
    product_path, harness_path = Path(product_path), Path(harness_path)

    def say(mark: str, text: str) -> None:
        print(f"[{mark}] {text}", file=stdout)

    product = config.load_product(product_path)
    plan = config.load_plan(plan_path) if plan_path else None
    # The file records the task set by the NAME a plan writes, because that is
    # what `load_monarch_recipes` compares a run's plan against -- an absolute
    # path here makes the file the loader refuses.
    # A plan writes this field with forward slashes whatever the platform, and the
    # loader compares the two strings, so `--tasks` is normalised the same way.
    tasks_name = plan.tasks if plan else Path(tasks_dir).as_posix().rstrip("/")
    tasks_dir = Path(tasks_dir) if tasks_dir else config.from_workflowbench(
        plan.tasks, product_path.parent.parent)
    tasks = load_suite(tasks_dir)

    kb_path = product_path.with_name(f"{product.name}.monarch-kb.yaml")
    if not kb_path.is_file():
        say("stop", f"the knowledge-base file {kb_path} is missing; "
                    "run `wb monarch setup` first")
        return 6
    kb_sha = kb_file_sha(kb_path)

    out_path = Path(out_path) if out_path else product_path.with_name(
        f"{product.name}.monarch-recipes.yaml")
    old = _read_existing(out_path, product.name, kb_sha)
    covered = {t["task"] for t in tasks if t["task"] in old.get("recipes", {})}

    # The gate. Printed before anything else, and before any request is made.
    print(f"wb monarch recipes: {len(tasks)} tasks, up to {attempts} authoring attempts "
          f"each (max {len(tasks) * attempts} attempts)", file=stdout)
    todo = len(tasks) - len(covered)
    print(f"cost band: US$ {todo * attempts * USD_PER_ATTEMPT_LOW:.0f} – "
          f"US$ {todo * attempts * USD_PER_ATTEMPT_HIGH:.0f} "
          f"(create + run pilot measured US$ {USD_PER_ATTEMPT_HIGH:.2f} per attempt)",
          file=stdout)
    print(f"tasks already covered for this knowledge base: {len(covered)}", file=stdout)
    # `approved_by` in a plan file approves nothing since decision D5 (8 Sep 2026):
    # approvals are records in the results store. Only an explicit --yes proceeds.
    if not yes:
        say("stop", "this command spends model money; rerun with --yes")
        return 5

    return _make(product_path, harness_path, tasks, tasks_name, kb_path, kb_sha, out_path,
                 old, attempts, env, stdout, say, product, timeout_s)


def _read_existing(out_path: Path, product_name: str, kb_sha: str) -> dict:
    """The recipes already on disk, or an empty file when there are none.

    A file made against a different knowledge base is dropped whole (FR-010): a
    recipe authored against other actions is not a recipe for this run.
    """
    if not out_path.is_file():
        return {}
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8")) or {}
    if doc.get("product") != product_name or doc.get("kb_hash_file_sha") != kb_sha:
        return {}
    return doc


def _make(product_path, harness_path, tasks, tasks_name, kb_path, kb_sha, out_path,
          old, attempts, env, stdout, say, product, timeout_s) -> int:
    arm = _arm(product_path, harness_path, env, timeout_s)
    outcomes = []
    for task in tasks:
        outcomes.append(_one_task(arm, task, old, attempts, stdout, say))
    path, changed = _write(out_path, product.name, tasks_name, kb_sha, arm.name, old, outcomes)

    kept = [o for o in outcomes if o.passed]
    missing = [o for o in outcomes if not o.passed]
    used = sum(o.attempts_used for o in outcomes)
    spent = sum(o.cost_usd for o in outcomes)
    say("ok", f"write: {path} ({'changed' if changed else 'unchanged'})")
    print(f"     {len(kept)} recipes, {len(missing)} missing, {used} attempts, "
          f"US$ {spent:.2f}", file=stdout)
    if kept:
        # research R5: Monarch's workflow patch route ignores a `name`, so the
        # bench-side name is recorded here and nowhere else. Printing "renamed"
        # for a call the backend drops would be a lie in the log.
        print("     names are recorded here only; Monarch has no route to rename a "
              "workflow today:", file=stdout)
        for o in kept:
            print(f"       {o.workflow_id} -> bench:{o.task_id}", file=stdout)
    return 0 if not missing else 1


def _arm(product_path, harness_path, env, timeout_s=900.0):
    """The create + run Monarch arm this command drives, built from a throwaway plan."""
    harness = config.load_harness(harness_path)
    product = config.load_product(product_path)
    config_dir = product_path.parent.parent
    price_path = config_dir / "models" / f"{harness.price_table}.yaml"
    plan = config.Plan(name="monarch-recipes", tasks="tasks", mode="create-run",
                       repetitions=1, timeout_s=timeout_s, concurrency=1,
                       competitors=[config.CompetitorSpec(model=None, harness=harness.name)],
                       baseline=harness.name, cost_ceiling_usd=0.0,
                       approved_by=None)
    rc = config.RunConfig(
        product=product, plan=plan,
        competitors=[config.Competitor(harness.name, None, harness)], tasks=[],
        product_path=str(product_path), plan_path="", models={},
        harnesses={harness.name: harness}, tasks_dir="",
        monarch_kb=config.load_monarch_kb(
            product_path.with_name(f"{product.name}.monarch-kb.yaml"), product),
        price_tables={harness.price_table: config.load_price_table(price_path)},
        config_dir=str(config_dir))
    arm = build_arm_for(rc.competitors[0], rc)
    arm.env = env
    arm.keep_workflows = True   # the checker decides keep-or-delete, not the attempt
    return arm


def _one_task(arm, task, old, attempts, stdout, say) -> RecipeOutcome:
    """Author, run, snapshot and grade until one passes or the attempts run out."""
    task_id = task["task"]
    out = RecipeOutcome(task_id)
    have = (old.get("recipes") or {}).get(task_id)
    if have:
        out.passed = out.skipped = True
        out.workflow_id, out.recipe_version = have["workflow_id"], have["recipe_version"]
        out.attempts_used = have.get("attempts_used", 1)
        say("ok", f"{task_id}: kept wf {out.workflow_id} v{out.recipe_version} "
                  "(already covered, no model call)")
        return out

    for n in range(1, attempts + 1):
        ep = Episode(task, episode_id=f"recipes/{task_id}/{arm.name}/t{n - 1}")
        reason, detail, workflow_id, version, result = _attempt(arm, ep)
        if result is not None:
            out.cost_usd += result.cost_usd or 0.0
        if reason == "infra":
            # An infrastructure failure is not the workflow's fault, so it does
            # not consume an attempt (FR-011's rule, applied here too).
            print(f"[..] {task_id} attempt {n}/{attempts}: infrastructure: {detail}",
                  file=stdout)
            out.reason, out.detail = reason, detail
            break
        out.attempts_used = n
        if reason is None:
            # The bench's own snapshot, graded by the bench's own checker.
            g = grade(task, ep.snapshot0, ep.finish())
            if g["passed"]:
                print(f"[..] {task_id} attempt {n}/{attempts}: authored wf {workflow_id} "
                      f"v{version}, run succeeded", file=stdout)
                out.passed = True
                out.workflow_id, out.recipe_version = workflow_id, version
                say("ok", f"{task_id}: kept wf {workflow_id} v{version} "
                          f"({n} attempt{'s' if n != 1 else ''}, US$ {out.cost_usd:.2f})")
                return out
            reason, detail = "checker_failed", _why(g)
        print(f"[..] {task_id} attempt {n}/{attempts}: {detail}", file=stdout)
        out.reason, out.detail = reason, detail
        if workflow_id:                       # this one did not pass, so it goes
            arm.delete_workflow(workflow_id)
            out.deleted.append(workflow_id)

    say("!!", f"{task_id}: no passing recipe after {out.attempts_used} attempts "
              f"({out.reason})")
    return out


def _attempt(arm, ep):
    """One create + run attempt. Returns (reason|None, detail, workflow_id, version, result)."""
    import time
    try:
        result = arm.run(ep, deadline=time.monotonic() + arm.timeout_s)
    except EpisodeTimeout as e:
        partial = getattr(e, "partial", None)
        return "timeout", str(e)[:200], _wf(partial), _ver(partial), partial
    except InfraError as e:
        partial = getattr(e, "partial", None)
        return "infra", str(e)[:200], _wf(partial), _ver(partial), partial
    if result.termination != "completed":
        reason = "authoring_error" if (result.error or "").startswith(
            ("authoring_error", "no_workflow", "account_requested", "stream_closed")) \
            else "run_error"
        return reason, (result.error or result.termination)[:200], \
            _wf(result), _ver(result), result
    return None, "", _wf(result), _ver(result), result


def _ids(result) -> dict:
    if result is None:
        return {}
    return next((t["monarch"] for t in result.turn_log if "monarch" in t), {})


def _wf(result):
    return _ids(result).get("workflowId")


def _ver(result):
    return _ids(result).get("recipeVersion")


def _why(g: dict) -> str:
    """The checker's verdict in one line, for the missing row's detail."""
    if not g["invariant"]["passed"]:
        paths = ", ".join(c.get("path", "") for c in g["invariant"]["unexpected_changes"])
        return f"invariant failed: {paths} changed"
    failed = [r["type"] for r in g["assertion_results"] if not r["passed"]]
    return f"assertion failed: {', '.join(failed) or 'unknown'}"


def _write(out_path: Path, product_name: str, tasks_name: str, kb_sha: str, monarch: str,
           old: dict, outcomes: list[RecipeOutcome]) -> tuple[Path, bool]:
    """Write the file, keeping the rows an earlier run already earned."""
    recipes = dict(old.get("recipes") or {})
    missing = dict(old.get("missing") or {})
    for o in outcomes:
        if o.passed:
            missing.pop(o.task_id, None)
            recipes[o.task_id] = {"workflow_id": o.workflow_id,
                                  "recipe_version": o.recipe_version,
                                  "authored_at": recipes.get(o.task_id, {}).get("authored_at")
                                  or _now(),
                                  "attempts_used": o.attempts_used}
        else:
            recipes.pop(o.task_id, None)
            missing[o.task_id] = {"reason": o.reason or "infra",
                                  "attempts_used": o.attempts_used,
                                  "detail": o.detail}
    doc = {"product": product_name, "tasks": tasks_name, "generated_at": "",
           "kb_hash_file_sha": kb_sha, "monarch": monarch,
           "recipes": dict(sorted(recipes.items())), "missing": dict(sorted(missing.items()))}
    was = yaml.safe_load(out_path.read_text(encoding="utf-8")) if out_path.is_file() else None
    same = isinstance(was, dict) and {k: v for k, v in was.items() if k != "generated_at"} == \
        {k: v for k, v in doc.items() if k != "generated_at"}
    doc["generated_at"] = str(was["generated_at"]) if same else _now()
    text = yaml.safe_dump(doc, sort_keys=True, default_flow_style=False)
    changed = not out_path.is_file() or out_path.read_text(encoding="utf-8") != text
    if changed:
        out_path.write_text(text, encoding="utf-8")
    return out_path, changed


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
