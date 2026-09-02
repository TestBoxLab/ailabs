"""wb: run / resume / status / doctor / grade."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from wb_orchestrator import config
from wb_orchestrator import doctor as doctor_mod
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


def _pick_or_flag(value, kind) -> Path:
    if value:
        return config.resolve_name_or_path(value, kind)
    return config.pick(kind, config.DEFAULT_CONFIG_DIR / f"{kind}s")


def _banner(rc) -> str:
    p, plan = rc.product, rc.plan
    data = "mutable data" if p.data.mutable else "read-only data"
    return "\n".join([
        f"product   {p.name} ({p.kind}, {data})",
        f"plan      {plan.name}  mode={plan.mode}  audience={plan.audience}",
        f"tasks     {len(rc.tasks)} in {plan.tasks.rstrip('/')}/   repetitions {plan.repetitions}   "
        f"competitors {len(rc.competitors)}   attempts {rc.attempts_total}",
        f"ceiling   US$ {plan.cost_ceiling_usd:.2f}   approved_by: {plan.approved_by or '—'}"])


def cmd_run(args) -> int:
    # Two error formats per contracts/cli.md: `wb run: ...` for picker and
    # name errors, `config error in <file>: <field>: <why>` for file errors.
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
    reports = doctor_mod.run_doctor(keys)
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
                             baseline_arm=args.baseline)
    except (GateError, KeyError) as e:
        print(e, file=sys.stderr)
        return 1
    print(f"wrote {paths['md']}\nwrote {paths['html']}")
    return 0


def cmd_corpus(args) -> int:
    from wb_orchestrator import corpus as corpus_mod
    if args.corpus_cmd == "import-ab":
        res = corpus_mod.import_ab(args.domains.split(","), args.dest)
        print(json.dumps(res, indent=1))
        return 0
    if args.corpus_cmd == "validate":
        v = corpus_mod.validate_corpus(args.dir)
        print(corpus_mod.format_validation(v, verbose=args.verbose))
        return 0 if v["ok"] else 1
    if args.corpus_cmd == "declare":
        from wb_orchestrator.declare import declare_dir
        r = declare_dir(args.dir, args.out, overwrite=args.overwrite)
        print(f"declared {r['declared']} tasks, {r['already_declared']} already declared, "
              f"{len(r['unmapped'])} with unmapped assertion types")
        for t, types in r["unmapped"].items():
            print(f"  ! {t}: {types}")
        return 0 if not r["unmapped"] else 1
    return 2


def cmd_legacy(args) -> int:
    from legacy.importer import import_runs
    store = _store(args)
    res = import_runs(store, args.runs_dir, limit_dirs=args.limit)
    print(json.dumps({k: v for k, v in res.items() if k != "dirs_skipped"}, indent=1))
    if res["dirs_skipped"]:
        print(f"skipped {len(res['dirs_skipped'])} dirs without summaries")
    return 0


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
    p.add_argument("--arms", default=None, help="comma list of provider keys; default: all registered")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("grade")
    p.add_argument("run_id")
    p.add_argument("--suite", default=None, help="task dir; default: the run's recorded suite_dir")
    p.set_defaults(fn=cmd_grade)

    p = sub.add_parser("report")
    p.add_argument("run_id")
    p.add_argument("--audience", default="internal", help="internal | public-rung2")
    p.add_argument("--baseline", default=None, help="baseline arm for paired stats")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("corpus")
    csub = p.add_subparsers(dest="corpus_cmd", required=True)
    ci = csub.add_parser("import-ab")
    ci.add_argument("--domains", required=True, help="comma list, e.g. simple,sales,hr")
    ci.add_argument("--dest", required=True, help="output task dir")
    cv = csub.add_parser("validate")
    cv.add_argument("dir")
    cv.add_argument("--verbose", action="store_true")
    cd = csub.add_parser("declare", help="derive expected/allowed changes from assertions")
    cd.add_argument("dir")
    cd.add_argument("--out", default=None, help="write copies here; default: in place (needs --overwrite)")
    cd.add_argument("--overwrite", action="store_true", help="rewrite tasks in place (contract hashes change)")
    p.set_defaults(fn=cmd_corpus)

    p = sub.add_parser("legacy-import")
    p.add_argument("runs_dir", help=r"e.g. C:\...\Monarch_Main\bench-host-state\runs")
    p.add_argument("--limit", type=int, default=None, help="import only the first N run dirs")
    p.set_defaults(fn=cmd_legacy)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
