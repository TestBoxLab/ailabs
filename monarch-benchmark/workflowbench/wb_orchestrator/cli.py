"""wb: run / resume / status / doctor / grade."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from wb_arms.monarch import monarch_version
from wb_orchestrator import config
from wb_orchestrator import doctor as doctor_mod
from wb_orchestrator import monarch_setup
from wb_orchestrator.config import ConfigError
from wb_orchestrator.orchestrator import ConfigDrift, Orchestrator, RunKilled, regrade
from wb_results.store import Store

DEFAULT_DB = "out/wb.sqlite3"
DEFAULT_OUT = "out"


def _store(args) -> Store:
    return Store(args.db)


def _print_run_report(store: Store, run_id: str) -> None:
    s = store.status(run_id)
    cfg = json.loads(store.run(run_id)["config_json"])
    what = (f"product={cfg['product']['name']} plan={cfg['plan']['name']}" if "plan" in cfg
            else f"suite={s['suite']}")
    print(f"\nrun {s['run_id']}  {what}  config={s['config_hash']}")
    print(f"episodes {s['episodes_done']}/{s['episodes_total']}  terminations={s['terminations']}")
    hdr = (f"{'arm':<28} {'pass':>6} {'strict':>7} {'infra':>6} {'cost_usd':>10} "
           f"{'cache_hit':>9} {'tokens(cached/prompt)':>24}")
    print(hdr)
    print("-" * len(hdr))
    for arm, a in sorted(s["arms"].items()):
        hit = f"{a['cache_hit_rate']:.1%}" if a["cache_hit_rate"] is not None else "n/a"
        strict = f"{a['strict_pass_rate']:.2%}" if a["strict_pass_rate"] is not None else "n/a"
        print(f"{arm:<28} {a['passed']:>3}/{a['non_infra']:<3} {strict:>7} {a['infra']:>6} "
              f"{a['cost_usd']:>10.4f} {hit:>9} {a['tokens_cached']:>12,}/{a['tokens_prompt']:<,}")
    if s["stop_reason"] == "cost_ceiling":
        print(f"stopped: cost_ceiling (spend US$ {s['spend_usd']:.2f} / "
              f"ceiling US$ {cfg.get('cost_ceiling_usd', 0):.2f})")
    elif s["stop_reason"]:
        print(f"stopped: {s['stop_reason']}")


def _pick_or_flag(value, kind) -> Path:
    if value:
        return config.resolve_name_or_path(value, kind)
    return config.pick(kind, config.DEFAULT_CONFIG_DIR / f"{kind}s")


def _monarch_line(rc) -> str | None:
    """`monarch   <name>, kb <n> apps, price table <name>@<date>` when Monarch runs."""
    h = next((c.harness for c in rc.competitors if c.harness.kind == "monarch"), None)
    if h is None:
        return None
    try:
        name = monarch_version(config.from_workflowbench(h.monarch_repo, rc.config_dir))
    except ValueError:
        name = "version unreadable"
    table = rc.price_tables.get(h.price_table)
    line = (f"monarch   {name}, kb {len(rc.monarch_kb.kb)} apps, "
            f"price table {h.price_table}@{table.prices_verified if table else '—'}")
    if rc.monarch_recipes is None:
        return line
    # contracts/cli.md: run-only says what it will execute and what left the set.
    n, excluded = len(rc.monarch_recipes.recipes), rc.excluded_tasks
    line += f", mode run-only, {n} recipe{'s' if n != 1 else ''}"
    if excluded:
        reasons = ", ".join(sorted(set(excluded.values())))
        line += (f", {len(excluded)} task{'s' if len(excluded) != 1 else ''} "
                 f"excluded ({reasons})")
    return line


def _size_line(rc) -> str:
    """The size in the agreed words, so nobody recomputes it before spending; a
    bare per-competitor total is never printed on its own (feature 005).

    With `retry_on_fail`, the count is a range: retries only happen on failures,
    so the round lands somewhere between all-pass and all-fail. The ceiling
    counts every attempt, so the upper bound is what `attempts in the round` says.
    """
    plan, n = rc.plan, len(rc.tasks)
    if not plan.retry_on_fail:
        return (f"prompts: {n}; attempts per prompt and competitor: {plan.repetitions}; "
                f"attempts per competitor: {rc.attempts_per_competitor}"
                f" = {n} x {plan.repetitions}")
    r = plan.retry_on_fail
    return (f"prompts: {n}; attempts per prompt: {plan.repetitions} plus {r} "
            f"retr{'y' if r == 1 else 'ies'} on failure; attempts per competitor: "
            f"{rc.attempts_per_competitor_min} to {rc.attempts_per_competitor}")


def _banner(rc) -> str:
    p, plan = rc.product, rc.plan
    data = "mutable data" if p.data.mutable else "read-only data"
    monarch = [line for line in [_monarch_line(rc)] if line]
    return "\n".join([
        f"product   {p.name} ({p.kind}, {data})",
        f"plan      {plan.name}  mode={plan.mode}  audience={plan.audience}",
        f"tasks     {len(rc.tasks)} in {plan.tasks.rstrip('/')}/",
        _size_line(rc),
        f"competitors: {len(rc.competitors)}; attempts in the round: {rc.attempts_total}",
        f"ceiling   US$ {plan.cost_ceiling_usd:.2f}   approved_by: {plan.approved_by or '—'}",
        *monarch])


def cmd_run(args) -> int:
    # Two error formats per contracts/cli.md: `wb run: ...` for picker and
    # name errors, `config error in <file>: <field>: <why>` for file errors.
    # Order matters: resolve (all guards) -> banner -> orchestrator; no arm is
    # built, and nothing is spent, before the config is fully validated.
    try:
        product_path = _pick_or_flag(args.product, "product")
        plan_path = _pick_or_flag(args.plan, "plan")
    except ConfigError as e:
        print(f"wb run: {e.why}", file=sys.stderr)
        return 2
    try:
        rc = config.resolve(product_path, plan_path)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    print(_banner(rc))
    store = _store(args)
    orch = Orchestrator.from_config(store, rc, args.out)
    try:
        run_id = orch.run(args.run_id)
    except RunKilled as e:
        print(e, file=sys.stderr)
        return 1
    _print_run_report(store, run_id)
    return 0


def cmd_resume(args) -> int:
    store = _store(args)
    run = store.run(args.run_id)
    if run is None:
        print(f"unknown run {args.run_id}", file=sys.stderr)
        return 1
    cfg = json.loads(run["config_json"])
    try:
        if "plan_path" in cfg:
            rc = config.resolve(cfg["product_path"], cfg["plan_path"])
            orch = Orchestrator.from_config(store, rc, args.out, provider_concurrency=args.concurrency)
        else:  # a run from before product/plan files
            orch = Orchestrator(store, cfg["suite_dir"], cfg["arms"], cfg["k"],
                                out_dir=args.out, timeout_s=cfg["timeout_s"],
                                provider_concurrency=args.concurrency or 4)
        orch.resume(args.run_id)
    except (ConfigError, ConfigDrift) as e:
        print(e, file=sys.stderr)
        return 2
    except RunKilled as e:
        print(e, file=sys.stderr)
        return 1
    _print_run_report(store, args.run_id)
    return 0


def cmd_status(args) -> int:
    store = _store(args)
    try:
        _print_run_report(store, args.run_id)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


def cmd_doctor(args) -> int:
    keys = args.arms.split(",") if args.arms else None
    reports = doctor_mod.run_doctor(keys, monarch_probe=args.monarch_probe)
    print(doctor_mod.format_report(reports))
    return 0 if all(r.get("ok") for r in reports) else 1


def cmd_grade(args) -> int:
    store = _store(args)
    run = store.run(args.run_id)
    if run is None:
        print(f"unknown run {args.run_id}", file=sys.stderr)
        return 1
    suite_dir = args.suite or json.loads(run["config_json"])["suite_dir"]
    res = regrade(store, args.run_id, suite_dir)
    print(f"regraded {res['regraded']} episodes, {res['changed']} verdicts changed")
    for k in ("contract_drift", "task_missing", "artifacts_missing"):
        if res[k]:
            print(f"WARNING: {res[k]} episodes skipped ({k.replace('_', ' ')})")
    _print_run_report(store, args.run_id)
    return 0


def cmd_report(args) -> int:
    from wb_report.report import GateError, write_report
    store = _store(args)
    try:
        paths = write_report(store, args.run_id, args.out, audience=args.audience,
                             baseline_arm=args.baseline, sortable=not args.no_sort,
                             fmt=args.format)
    except (GateError, KeyError) as e:
        print(e, file=sys.stderr)
        return 1
    print(f"wrote {paths['md']}\nwrote {paths['html']}")
    return 0


def cmd_summary(args) -> int:
    """Two to six rounds on one page (contracts/cli.md)."""
    from datetime import datetime, timezone
    from pathlib import Path

    from wb_report.report import GateError, resolve_plans, write_summary
    store = _store(args)
    if bool(args.runs) == bool(args.plans):
        print("give exactly one of --runs and --plans", file=sys.stderr)
        return 1
    try:
        if args.plans:
            picked = resolve_plans(store, [p.strip() for p in args.plans.split(",")])
            width = max(len(p) for p, _, _ in picked)
            for plan, run_id, started in picked:
                # say which round each plan resolved to: a plan that silently
                # picked yesterday's round is how a wrong number reaches a slide
                print(f"{plan.ljust(width)} -> {run_id} (started {started})")
            run_ids = [run_id for _, run_id, _ in picked]
        else:
            run_ids = [r.strip() for r in args.runs.split(",")]
        out = args.summary_out
        if not out:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            out = Path(args.out) / f"summary-{stamp}-{args.audience}.html"
        path = write_summary(store, run_ids, out, audience=args.audience,
                             baseline=args.baseline, sortable=not args.no_sort)
    except (GateError, KeyError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    print(f"wrote {path}")
    return 0


def cmd_corpus(args) -> int:
    from wb_orchestrator import corpus as corpus_mod
    if args.corpus_cmd == "import-ab":
        product = config.load_product(config.resolve_name_or_path(args.product, "product"))
        try:
            res = corpus_mod.import_ab(args.domains.split(","), args.dest,
                                       product_services=product.services)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        width = max(len(d) for d in res["by_domain"]) + 1
        for domain, n in res["by_domain"].items():
            print(f"{domain + ':':<{width}} {n['written']:>4} written, "
                  f"{n['unchanged']} unchanged")
        print(f"total: {res['written'] + res['unchanged']} tasks "
              f"in {len(res['by_domain'])} folders")
        missing = ", ".join(res["missing_services"]) or "none"
        print(f"services seeded by these domains and NOT listed by product "
              f"{product.name}: {missing}")
        return 1 if res["missing_services"] else 0
    if args.corpus_cmd == "validate":
        v = corpus_mod.validate_corpus(args.dir)
        print(corpus_mod.format_validation(v, verbose=args.verbose))
        return 0 if v["ok"] else 1
    if args.corpus_cmd == "declare":
        from wb_orchestrator import declare
        product = config.load_product(config.resolve_name_or_path(args.product, "product"))
        side_effects = config.load_side_effects(config.from_workflowbench(product.side_effects))
        r = declare.declare_dir(args.dir, args.out, overwrite=args.overwrite, side_effects=side_effects)
        print(f"declared {r['declared']} tasks, {r['already_declared']} already declared, "
              f"{len(r['unmapped'])} with unmapped assertion types")
        for t, types in r["unmapped"].items():
            print(f"  ! {t}: {types}")
        return 0 if not r["unmapped"] else 1
    if args.corpus_cmd == "tiers":
        return _corpus_tiers(args)
    return 2


def _corpus_tiers(args) -> int:
    """Draw the four frozen task sets. Offline: no key, no network, no money."""
    from pathlib import Path

    from wb_orchestrator import tiers
    dirs = [Path(d) for d in (args.corpus or sorted(Path("corpus").glob("imported-*")))]
    missing = [str(d) for d in dirs if not d.is_dir()]
    if missing or not dirs:
        print(f"corpus folder missing or empty: {missing or 'corpus/imported-*'}",
              file=sys.stderr)
        return 3
    if args.refreeze:
        if args.seed is not None:
            print("--refreeze keeps the seed the manifest already records; "
                  "pass one or the other, not both", file=sys.stderr)
            return 1
        try:
            r = tiers.refreeze(dirs, out=args.out,
                               because=args.because or tiers.DEFAULT_REFREEZE_REASON)
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 3
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        print(f"corpus: {len(dirs)} folders, {r.total} tasks, {r.usable} usable")
        print(f"refroze the four sets from the manifest's own task ids "
              f"(seed unchanged); {len(r.written)} files written")
        for name in tiers.SET_NAMES:
            print(f"  {name:<13} {len(r.sets[name])} prompts - "
                  + ", ".join(f"{d} {n}" for d, n in r.by_domain[name].items()))
        return 0
    if args.seed is None:
        print("wb corpus tiers needs --seed to draw, or --refreeze to rewrite "
              "the sets the manifest already records", file=sys.stderr)
        return 1
    try:
        r = tiers.draw(dirs, seed=args.seed, per_tier=args.per_tier, out=args.out)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 3
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"corpus: {len(dirs)} folders, {r.total} tasks, {r.usable} usable")
    if r.excluded:
        no_rule = sum(code == tiers.NO_RULE for code, _ in r.excluded.values())
        drifted = len(r.excluded) - no_rule
        parts = []
        if no_rule:
            parts.append(f"{no_rule} with no approval rule (unmapped assertion types)")
        if drifted:
            parts.append(f"{drifted} whose hash does not match its content")
        print(f"  excluded {len(r.excluded)}: {', '.join(parts)} - see the manifest")
    print("measure: services seeded + expected changes + tools needed")
    print(f"cuts: simple <= {r.cuts['low']} < medium <= {r.cuts['high']} < complex")
    print(f"draw (seed {args.seed}, {args.per_tier} per set):")
    for name in tiers.SET_NAMES:
        breakdown = ", ".join(f"{d} {n}" for d, n in r.by_domain[name].items())
        print(f"  {name:<13} {args.per_tier} prompts - {breakdown}")
    out = Path(args.out)
    print("[ok] write " + " ".join(f"{(out / n).as_posix()}/" for n in tiers.SET_NAMES))
    print(f"[ok] write {(out / 'tiers-manifest.yaml').as_posix()}")
    print(f"random-10 is drawn from the usable corpus minus the "
          f"{len(tiers.TIER_ORDER) * args.per_tier} tier tasks, so the four sets "
          f"share no task")
    print("every drawn task keeps its corpus hash; info.tier and info.domain "
          "are not hashed")
    return 0


def cmd_legacy(args) -> int:
    from legacy.importer import import_runs
    store = _store(args)
    res = import_runs(store, args.runs_dir, limit_dirs=args.limit)
    print(json.dumps({k: v for k, v in res.items() if k != "dirs_skipped"}, indent=1))
    if res["dirs_skipped"]:
        print(f"skipped {len(res['dirs_skipped'])} dirs without summaries")
    return 0


def cmd_monarch_setup(args) -> int:
    try:
        return monarch_setup.run(config.resolve_name_or_path(args.product, "product"),
                                 config.resolve_name_or_path(args.harness, "harness"),
                                 args.out, os.environ, sys.stdout,
                                 conform=not args.no_conform)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2


def cmd_monarch_conform(args) -> int:
    """Is every catalogue action TRUE against the simulated apps? (feature 008)"""
    from wb_world import conformance
    seeds_dir = Path(args.seeds)
    if not seeds_dir.is_dir():
        print(f"no seed folders at {seeds_dir}; run `wb monarch setup` first", file=sys.stderr)
        return 2
    corpus = conformance.default_corpus_dirs()
    services = [s.strip() for s in args.services.split(",") if s.strip()] if args.services else None
    report = conformance.check(seeds_dir, corpus, services)
    report.print_table(sys.stdout)
    out = seeds_dir / "conformance.json"
    report.write_json(out)
    print(f"report: {out}")
    failed = report.failed_services()
    if failed:
        print(f"mismatching services: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def cmd_monarch_recipes(args) -> int:
    from wb_orchestrator import monarch_recipes
    if bool(args.plan) == bool(args.tasks):
        print("wb monarch recipes: give exactly one of --plan and --tasks", file=sys.stderr)
        return 2
    try:
        return monarch_recipes.run(
            product_path=config.resolve_name_or_path(args.product, "product"),
            harness_path=config.resolve_name_or_path(args.harness, "harness"),
            plan_path=config.resolve_name_or_path(args.plan, "plan") if args.plan else None,
            tasks_dir=args.tasks, attempts=args.attempts, yes=args.yes,
            env=os.environ, stdout=sys.stdout)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    load_dotenv()   # keys live in workflowbench/.env (gitignored), never in code
    ap = argparse.ArgumentParser(prog="wb", description="WorkflowBench runner")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=DEFAULT_OUT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run")
    p.add_argument("--product", default=None, help="name in config/products or a path; asked if omitted")
    p.add_argument("--plan", default=None, help="name in config/plans or a path; asked if omitted")
    p.add_argument("--run-id", default=None)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("resume")
    p.add_argument("run_id")
    p.add_argument("--concurrency", type=int, default=None, help="default: the plan's (4 for old runs)")
    p.set_defaults(fn=cmd_resume)

    p = sub.add_parser("status")
    p.add_argument("run_id")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("doctor")
    p.add_argument("--arms", default=None,
                   help="comma list of provider keys, plus 'monarch' for the Monarch checks; "
                        "default: all registered providers and monarch")
    p.add_argument("--monarch-probe", action="store_true",
                   help="also start and immediately cancel one Monarch authoring run; costs model money")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("grade")
    p.add_argument("run_id")
    p.add_argument("--suite", default=None, help="task dir; default: the run's recorded suite_dir")
    p.set_defaults(fn=cmd_grade)

    p = sub.add_parser("report")
    p.add_argument("run_id")
    p.add_argument("--audience", default="internal", help="internal | public-rung2")
    p.add_argument("--baseline", default=None, help="baseline arm for paired stats")
    p.add_argument("--no-sort", action="store_true",
                   help="accepted for compatibility; the page has no sorting script")
    p.add_argument("--format", default="html", choices=("html", "executive"),
                   help="html: the seven-section technical page (default); "
                        "executive: the stakeholder page, Monarch first")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("summary", help="two to six rounds on one page")
    p.add_argument("--runs", default=None, help="comma list of run ids, in page order")
    p.add_argument("--plans", default=None,
                   help="comma list of plans; uses the most recent run of each")
    p.add_argument("--audience", default="internal", help="internal | public-rung2")
    p.add_argument("--baseline", default=None, help="baseline where a round names none")
    p.add_argument("--out", dest="summary_out", default=None,
                   help="output file; default out/summary-<timestamp>-<audience>.html")
    p.add_argument("--no-sort", action="store_true",
                   help="omit the column-sorting script")
    p.set_defaults(fn=cmd_summary)

    p = sub.add_parser("corpus")
    csub = p.add_subparsers(dest="corpus_cmd", required=True)
    ci = csub.add_parser("import-ab")
    ci.add_argument("--domains", required=True,
                    help="comma list, e.g. simple,sales,hr; or 'all' for every known domain")
    ci.add_argument("--dest", required=True,
                    help="output task dir; may contain {domain}, replaced per domain")
    ci.add_argument("--product", default="simulated-apps",
                    help="product whose service list the seeded services are checked against")
    cv = csub.add_parser("validate")
    cv.add_argument("dir")
    cv.add_argument("--verbose", action="store_true")
    cd = csub.add_parser("declare", help="derive expected/allowed changes from assertions")
    cd.add_argument("dir")
    cd.add_argument("--out", default=None, help="write copies here; default: in place (needs --overwrite)")
    cd.add_argument("--overwrite", action="store_true", help="rewrite tasks in place (contract hashes change)")
    cd.add_argument("--product", default="simulated-apps",
                    help="product whose side-effect list to use (name or path)")
    ct = csub.add_parser("tiers", help="draw four frozen task sets by difficulty")
    ct.add_argument("--seed", type=int,
                    help="recorded in the manifest; the same seed redraws the same bytes")
    ct.add_argument("--refreeze", action="store_true",
                    help="rewrite the four sets from the corpus keeping the task ids "
                         "the manifest already records; use after an approval-rule "
                         "change, when redrawing would pick a different ten")
    ct.add_argument("--because", default=None,
                    help="with --refreeze: why, recorded in the manifest")
    ct.add_argument("--per-tier", type=int, default=10, help="prompts per drawn set")
    ct.add_argument("--corpus", action="append", default=None,
                    help="repeatable; default: every corpus/imported-* folder")
    ct.add_argument("--out", default="tasks", help="where the four folders and the manifest go")
    p.set_defaults(fn=cmd_corpus)

    p = sub.add_parser("monarch", help="prepare Monarch for a product")
    msub = p.add_subparsers(dest="monarch_cmd", required=True)
    ms = msub.add_parser("setup", help="generate seeds, import them, write the knowledge-base hashes")
    ms.add_argument("--product", default="simulated-apps", help="name in config/products or a path")
    ms.add_argument("--harness", default="monarch", help="name in config/harnesses or a path")
    ms.add_argument("--out", default="out/monarch-seeds", help="where the seed folders are written")
    ms.add_argument("--no-conform", action="store_true",
                    help="import without checking that every action is true against "
                         "the simulated apps (see `wb monarch conform`)")
    ms.set_defaults(fn=cmd_monarch_setup)
    mc = msub.add_parser("conform",
                         help="execute every catalogue action against the simulated apps "
                              "and report the seeds that are not true")
    mc.add_argument("--seeds", default="out/monarch-seeds", help="the generated seed folders")
    mc.add_argument("--services", default=None,
                    help="comma list of services; default: every service in the seeds")
    mc.set_defaults(fn=cmd_monarch_conform)
    mr = msub.add_parser("recipes",
                         help="author one known-correct workflow per task and freeze it "
                              "(SPENDS MODEL MONEY)")
    mr.add_argument("--product", default="simulated-apps", help="name in config/products or a path")
    mr.add_argument("--harness", default="monarch", help="name in config/harnesses or a path")
    mr.add_argument("--plan", default=None, help="name in config/plans or a path; its task set is used")
    mr.add_argument("--tasks", default=None, help="a task folder, instead of --plan")
    mr.add_argument("--attempts", type=int, default=3, help="most authoring attempts per task")
    mr.add_argument("--yes", action="store_true", help="proceed without an approved plan")
    mr.set_defaults(fn=cmd_monarch_recipes)

    p = sub.add_parser("legacy-import")
    p.add_argument("runs_dir", help=r"e.g. C:\...\Monarch_Main\bench-host-state\runs")
    p.add_argument("--limit", type=int, default=None, help="import only the first N run dirs")
    p.set_defaults(fn=cmd_legacy)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
