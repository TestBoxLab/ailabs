"""wb: run / resume / status / doctor / grade / budget / approvals."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from wb_arms.monarch import monarch_version
from wb_orchestrator import approvals
from wb_orchestrator import config
from wb_orchestrator import doctor as doctor_mod
from wb_orchestrator import monarch_setup
from wb_orchestrator.approvals import ApprovalError
from wb_orchestrator.config import ConfigError
from wb_orchestrator.orchestrator import ConfigDrift, Orchestrator, RoundAdmissionError, RunKilled, regrade
from wb_results.store import Store

DEFAULT_DB = "out/wb.sqlite3"
DEFAULT_OUT = "out"
# The one shared weekly ledger every paid launcher (CLI and Studio) reserves in.
DEFAULT_LEDGER = str(Path(__file__).resolve().parents[3] / "research" / "budget.sqlite3")


def _store(args) -> Store:
    return Store(args.db)


def _ledger(args):
    from wb_orchestrator.budget import BudgetLedger
    return BudgetLedger(args.ledger)


def _refuse(reasons: list[str]) -> int:
    """A paid launch that may not happen today: every reason, exit 2, nothing created."""
    for reason in reasons:
        print(f"paid launch refused: {reason}", file=sys.stderr)
    return 2


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
        name = monarch_version(config.from_workflowbench(h.monarch_repo, rc.config_dir), os.environ.get("MONARCH_BUILD"))
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
        f"plan      {plan.name}  mode={plan.mode}",
        f"tasks     {len(rc.tasks)} in {plan.tasks.rstrip('/')}/",
        _size_line(rc),
        f"competitors: {len(rc.competitors)}; attempts in the round: {rc.attempts_total}",
        f"ceiling   US$ {plan.cost_ceiling_usd:.2f}   attempt cap US$ {plan.attempt_cap_usd:.2f}",
        *monarch])


def _approved_by_notice(rc, plan_path) -> None:
    """`approved_by` in a plan file approves nothing since decision D5; say so once."""
    if rc.plan.approved_by:
        print(f"note: approved_by: {rc.plan.approved_by!r} in {plan_path} is ignored; an approval is a "
              "record in the results store now (wb approvals)")


def cmd_studio(args) -> int:
    from wb_studio.app import main
    main(["--port", str(args.port)])
    return 0


def cmd_genesis_index(args) -> int:
    from wb_studio.app import Studio
    from wb_studio.code_index import refresh
    print(json.dumps(refresh(Studio()), indent=2, default=str))
    return 0


def _experiment_studio(args):
    from wb_studio.app import Studio
    return Studio(args.out) if getattr(args, "out", None) else Studio()


def _experiment_record(args) -> dict:
    """The args as the record `genesis_hypotheses` already validates. No new shape."""
    return {"claim": args.claim, "measure": args.measure, "direction": args.direction,
            "minimum_effect": float(args.minimum_effect),
            "population": {"task_set": args.task_set},
            "slate": args.slate, "repetitions": int(args.repetitions),
            "id": args.id, "parent": args.parent,
            "comparison": {"a": {"kind": "architecture", "id": args.a, **({"model": args.model} if args.model else {})},
                           "b": {"kind": "architecture", "id": args.b, **({"model": args.model} if args.model else {})}}}


def cmd_experiment_propose(args) -> int:
    """Size an experiment against the test that settles it, and refuse what cannot conclude.

    Offline. Nothing is reserved here: a proposal the paired sign test could not decide at
    the size asked for is refused before any money is committed (feature 024, FR-021).
    """
    from wb_studio import genesis_hypotheses as H
    try:
        record = H.check_hypothesis(_experiment_record(args))
        plan = H.smallest_plan(_experiment_studio(args), record)
    except (ValueError, KeyError) as exc:
        print(f"experiment: {exc}", file=sys.stderr)
        return 2
    power = plan.get("power") or {}
    if not power.get("ok", True):
        # The reason already opens with "refused"; do not say it twice.
        reason = str(power.get("reason") or "")
        print(reason if reason.lower().startswith("refused") else f"refused: {reason}", file=sys.stderr)
        return 2
    print(f"admitted  lineage {record.get('lineage') or '(new)'}  slate {record['slate']}")
    print(f"  {plan['tasks']} tasks of {plan['population']}, {record['repetitions']} "
          f"repetition{'s' if record['repetitions'] != 1 else ''}, {plan['competitors']} competitors")
    print(f"  expected {power.get('expected_pairs')} discordant pairs; "
          f"{power.get('wins_needed')} must be wins to reach p<0.05")
    print(f"  maximum ${plan['proposal']['maximum_usd']}")
    print(f"  {plan['basis']}")
    if plan.get("not_launchable"):
        print(f"  not launchable yet: {plan['not_launchable']}")
    return 0


def cmd_experiment_confirm(args) -> int:
    """Whether a lineage may run on the held-out slate. Refuses; never launches."""
    from wb_studio import genesis_hypotheses as H
    try:
        studio = _experiment_studio(args)
        ok, why = H.may_confirm(studio.genesis, args.lineage)
    except (ValueError, KeyError, OSError) as exc:
        print(f"experiment: {exc}", file=sys.stderr)
        return 2
    if not ok:
        print(f"refused: {why}", file=sys.stderr)
        return 2
    print(f"lineage {args.lineage} may be confirmed once on the held-out slate.")
    print("  Run it with `wb run --product <p> --plan <held-out plan>`; the result settles the lineage either way.")
    return 0


def cmd_budget_acknowledge(args) -> int:
    """A named person answers for one recorded overrun so admissions resume.

    The overrun stays on the record and its money is unchanged; what this replaces is
    editing research/budget.sqlite3 by hand, which was the only recovery before
    (feature 024, FR-006).
    """
    from wb_orchestrator.budget import BudgetLedger, BudgetConfigurationError
    path = args.ledger
    operator = args.by or os.environ.get("WB_OPERATOR") or ""
    try:
        ledger = BudgetLedger(path)
        row = ledger.acknowledge_overrun(args.reservation_id, by=operator, reason=args.reason)
    except (BudgetConfigurationError, ValueError) as exc:
        print(f"budget: {exc}", file=sys.stderr)
        return 2
    note = row.metadata["overrun_acknowledged"]
    print(f"acknowledged {row.reservation_id}: reserved ${row.maximum_usd}, settled ${row.actual_usd}")
    print(f"  by {note['by']} at {note['at']}: {note['reason']}")
    remaining = ledger.status().overrun_ids
    print("  overruns still blocking: " + (", ".join(remaining) if remaining else "none"))
    return 0


def cmd_budget_release(args) -> int:
    """A named person releases one hold whose cost the provider never reported.

    The unknown stays on the record and reconciles against the provider's own export;
    what it stops doing is occupying capacity in this week and every week after it
    (feature 024 US4; found by ailabs-9c, 11 Sep 2026).
    """
    from wb_orchestrator.budget import BudgetLedger, BudgetConfigurationError
    path = args.ledger
    operator = args.by or os.environ.get("WB_OPERATOR") or ""
    try:
        ledger = BudgetLedger(path)
        row = ledger.release_hold(args.reservation_id, by=operator, reason=args.because)
    except (BudgetConfigurationError, ValueError) as exc:
        print(f"budget: {exc}", file=sys.stderr)
        return 2
    note = row.metadata["hold_released"]
    print(f"released {row.reservation_id}: ${row.maximum_usd} no longer held; its cost is still unknown")
    print(f"  by {note['by']} at {note['at']}: {note['reason']}")
    status = ledger.status()
    print(f"  week of {status.week_start}: ${status.available_usd} available; "
          + (f"holds still unknown: {', '.join(status.unknown_ids)}" if status.unknown_ids else "no unknown holds left"))
    return 0


def cmd_budget_status(args) -> int:
    from wb_orchestrator import reconcile
    from wb_orchestrator.budget import BudgetLedger, BudgetConfigurationError
    path = args.status_ledger or args.ledger
    try:
        ledger = BudgetLedger(path)
        status = ledger.status()
    except (BudgetConfigurationError, ValueError) as exc:
        print(f"budget: {exc}", file=sys.stderr)
        return 2
    weeks = reconcile.summaries(reconcile.default_dir(ledger))
    capabilities = approvals.capabilities()
    print(json.dumps({
        "ledger": str(Path(path).resolve()), "week_start": status.week_start,
        "timezone": "America/Sao_Paulo",
        **{name + "_usd": str(getattr(status, name + "_usd"))
           for name in ("weekly_limit", "actual", "held", "carried_held", "released", "committed", "available")},
        "blocked": status.blocked, "overrun_ids": status.overrun_ids,
        "unknown_hold_ids": status.unknown_ids,
        "historical_billing_verified": weeks.get(status.week_start, {}).get("historical_billing_verified", False),
        "reconciliation": weeks,
        "paid_launch_enabled": {kind: reason is None for kind, reason in capabilities.items()},
        "capability_scope": "At least one configured harness of this kind is verified. Each launch still checks its exact competitor, operator, configuration and budget.",
        "paid_launch_reasons": {kind: reason for kind, reason in capabilities.items() if reason},
        "note": "Only recorded liabilities are shown. held_usd is capacity occupied by unknown_hold_ids — attempts whose cost no provider has reported — not money spent; released_usd is what a person released with `wb budget release`, still unknown and still reconciled. Weekly actual_usd conservatively occupies capacity across dispatch-to-settlement weeks; it is not invoice attribution. historical_billing_verified is per week, set by `wb budget reconcile` from the providers' own usage exports."
    }, indent=2))
    return 0


def cmd_budget_reconcile(args) -> int:
    from wb_orchestrator import reconcile
    from wb_orchestrator.budget import BudgetLedger, BudgetConfigurationError
    try:
        ledger = BudgetLedger(args.ledger)
        state = reconcile.reconcile(ledger, args.week, args.provider, args.csv, out_dir=args.reconcile_out)
    except (BudgetConfigurationError, ValueError, OSError) as e:
        print(f"wb budget reconcile: {e}", file=sys.stderr)
        return 2
    print(reconcile.format_result(state))
    return 0


def _experiments_this_week(genesis_dir: Path, week_start: str) -> tuple[int, int]:
    from wb_studio.genesis_access import _week_of
    counted_cards = set()
    admitted = 0
    refused = 0
    activity_file = genesis_dir / "activity.jsonl"
    if activity_file.exists():
        for line in activity_file.read_text(encoding="utf8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                at = entry.get("at")
                if at:
                    inst = datetime.fromisoformat(at)
                    if _week_of(inst) != week_start:
                        continue
                card_id = entry.get("card")
                if card_id and card_id in counted_cards:
                    continue
                if entry.get("kind") == "experiment-admitted":
                    admitted += 1
                    if card_id:
                        counted_cards.add(card_id)
                elif entry.get("kind") in ("experiment-refused", "experiment-rejected"):
                    refused += 1
                    if card_id:
                        counted_cards.add(card_id)
            except Exception:
                pass
    cards_dir = genesis_dir / "cards"
    if cards_dir.exists():
        for p in cards_dir.glob("*.json"):
            try:
                c = json.loads(p.read_text(encoding="utf8"))
                if not c.get("hypothesis") or c.get("id") in counted_cards:
                    continue
                created = c.get("created_at")
                if created:
                    inst = datetime.fromisoformat(created)
                    if _week_of(inst) != week_start:
                        continue
                if c.get("not_launchable") or (c.get("waiting") and "refused" in str(c.get("waiting"))):
                    refused += 1
                    counted_cards.add(c.get("id"))
                elif c.get("stage") in ("running", "approval", "review", "complete"):
                    admitted += 1
                    counted_cards.add(c.get("id"))
            except Exception:
                pass
    return admitted, refused


def cmd_budget_envelope(args) -> int:
    from decimal import Decimal
    from wb_studio.genesis_access import Envelope
    from wb_orchestrator.budget import BudgetLedger

    genesis_dir = Path(args.genesis_dir) if getattr(args, "genesis_dir", None) else None
    if genesis_dir is None:
        # The envelope file decides, not the folder. `or cand.exists()` made the first
        # test dead, so an empty `genesis/` beside the real one reported "$0.00 (not set)".
        candidates = [Path("genesis"), Path("out/studio/genesis"),
                      Path(__file__).resolve().parents[1] / "out" / "studio" / "genesis"]
        genesis_dir = next((c for c in candidates if (c / "envelope.json").exists()),
                           next((c for c in candidates if c.is_dir()), Path("genesis")))

    env = Envelope(genesis_dir)

    # Handle --set
    if getattr(args, "envelope_set", None) is not None:
        if not getattr(args, "per_experiment", None) or not getattr(args, "by", None):
            print("wb budget envelope: --set, --per-experiment and --by are all required", file=sys.stderr)
            return 2
        try:
            saved = env.set(
                amount_usd=args.envelope_set,
                per_experiment_ceiling_usd=args.per_experiment,
                by=args.by,
            )
            who = saved["set_by"].removeprefix("human:").capitalize()
            print(f"research envelope set to ${Decimal(saved['amount_usd']):.2f} "
                  f"(per-experiment ceiling ${Decimal(saved['per_experiment_ceiling_usd']):.2f}) "
                  f"by {who} for week of {saved['week_start']}.")
            return 0
        except ValueError as e:
            print(f"wb budget envelope: {e}", file=sys.stderr)
            return 2

    # Status
    ledger_path = getattr(args, "envelope_ledger", None) or getattr(args, "ledger", None) or DEFAULT_LEDGER
    try:
        ledger = BudgetLedger(ledger_path)
    except Exception:
        ledger = None

    status = env.status(ledger=ledger)
    week = status["week_start"]
    print(f"week of {week} (America/Sao_Paulo)")

    amount = Decimal(status["amount_usd"])
    held = Decimal(status["held_usd"])
    settled = Decimal(status["settled_usd"])
    left = Decimal(status["left_usd"])

    if status["is_set"]:
        who = str(status.get("set_by") or "").removeprefix("human:").capitalize()
        env_col = f"research envelope   ${amount:.2f} set by {who}"
    else:
        env_col = "research envelope   $0.00 (not set)"

    env_col = f"{env_col:<44}"
    print(f"{env_col}reserved ${held:.2f}   settled ${settled:.2f}   left ${left:.2f}")

    if ledger is not None:
        try:
            led_st = ledger.status()
            lab_limit = led_st.weekly_limit_usd
            lab_held = led_st.held_usd
            lab_settled = led_st.actual_usd
            lab_left = led_st.available_usd
            lab_col = f"lab weekly ceiling  ${lab_limit:.2f}"
            lab_col = f"{lab_col:<44}"
            print(f"{lab_col}reserved ${lab_held:.2f}   settled ${lab_settled:.2f}   left ${lab_left:.2f}")
        except Exception as exc:
            # A budget command that silently drops the lab ceiling reads as "no ceiling".
            print(f"lab weekly ceiling  unavailable ({type(exc).__name__}: {exc})")

    admitted, refused = _experiments_this_week(genesis_dir, week)
    print(f"experiments this week: {admitted} admitted, {refused} refused")
    return 0



def _paid_gate(rc, args):
    """The ledger a paid run config reserves in, or an exit code when it may not launch today."""
    reasons = approvals.launch_readiness(rc, os.environ)
    if reasons:
        return _refuse(reasons)
    from wb_orchestrator.budget import BudgetConfigurationError
    try:
        return _ledger(args)
    except (BudgetConfigurationError, ValueError) as e:
        print(f"budget: {e}", file=sys.stderr)
        return 2


def cmd_run(args) -> int:
    # Two error formats per contracts/cli.md: `wb run: ...` for picker and
    # name errors, `config error in <file>: <field>: <why>` for file errors.
    # Order matters: resolve (all guards) -> readiness and ledger -> banner ->
    # approval record -> orchestrator; no arm is built, and nothing is spent,
    # before the config is fully validated and the launch admitted.
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
    if getattr(args, "repetitions", None) is not None:
        if args.repetitions < 1:
            print("wb run: repetitions must be at least 1", file=sys.stderr)
            return 2
        rc.plan.repetitions = args.repetitions
    ledger = launch = None
    if approvals.is_paid(rc):
        ledger = _paid_gate(rc, args)
        if isinstance(ledger, int):
            return ledger
    _approved_by_notice(rc, plan_path)
    print(_banner(rc))
    store = _store(args)
    if ledger is not None:
        try:
            launch = approvals.admit_launch(store, rc, os.environ, request_id=args.request)
        except ApprovalError as e:
            print(e, file=sys.stderr)
            return 2
        print(launch.message)
        if not launch.run:
            return 0
    orch = Orchestrator.from_config(store, rc, args.out, ledger=ledger,
                                    operator=approvals.operator(os.environ))
    orch.approval_request_id = launch.request_id if launch else None
    run_id = args.run_id or f"run-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    try:
        orch.run(run_id)
    except RoundAdmissionError as e:
        print(e, file=sys.stderr)
        return 2
    except RunKilled as e:
        _bind_request(store, launch, run_id)   # the run exists and resumes under this request
        print(e, file=sys.stderr)
        return 1
    _bind_request(store, launch, run_id)
    _print_run_report(store, run_id)
    return 0


def _bind_request(store, launch, run_id: str) -> None:
    if launch is not None and launch.request_id:
        store.bind_approval_run(launch.request_id, run_id)


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
            ledger = None
            if approvals.is_paid(rc):
                ledger = _paid_gate(rc, args)
                if isinstance(ledger, int):
                    return ledger
            orch = Orchestrator.from_config(store, rc, args.out, provider_concurrency=args.concurrency,
                                            ledger=ledger, operator=approvals.operator(os.environ))
        else:  # a run from before product/plan files
            if any(key not in ("oracle", "sloppy", "null") for key in cfg["arms"]):
                return _refuse([f"run {args.run_id} was recorded before product and plan files; a paid "
                                "competitor cannot resume without a plan, an operator and the weekly "
                                "ledger. Start it again with wb run --product ... --plan ..."])
            orch = Orchestrator(store, cfg["suite_dir"], cfg["arms"], cfg["k"],
                                out_dir=args.out, timeout_s=cfg["timeout_s"],
                                provider_concurrency=args.concurrency or 4)
        orch.resume(args.run_id)
    except (ConfigError, ConfigDrift, RoundAdmissionError) as e:
        print(e, file=sys.stderr)
        return 2
    except RunKilled as e:
        print(e, file=sys.stderr)
        return 1
    _print_run_report(store, args.run_id)
    return 0


def cmd_approve(args) -> int:
    return _decide(args, "approved")


def cmd_deny(args) -> int:
    return _decide(args, "denied")


def _decide(args, decision: str) -> int:
    store = _store(args)
    try:
        record = approvals.decide(store, args.request_id, decision, os.environ)
    except ApprovalError as e:
        print(e, file=sys.stderr)
        return 2
    print(f"{record['id']} {record['status']} by {record['decided_by']} at {record['decided_at']}: "
          f"plan {record['plan_name']}, {record['attempts_total']} attempts, ceiling US$ "
          f"{record['ceiling_usd']:.2f}, config {record['config_hash']}, requested by {record['requested_by']}")
    if decision == "approved":
        print(f"run it with: wb run --product {record['product_path']} --plan {record['plan_path']} "
              f"--request {record['id']}")
    return 0


def cmd_approvals(args) -> int:
    rows = _store(args).approval_requests()
    if not rows:
        print("no approval requests")
        return 0
    header = (f"{'id':<14} {'status':<9} {'plan':<26} {'attempts':>8} {'ceiling':>10}  "
              f"{'requested by':<13} {'requested at':<20} {'decided by':<11} run")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['id']:<14} {r['status']:<9} {r['plan_name']:<26} {r['attempts_total']:>8} "
              f"US$ {r['ceiling_usd']:>6.2f}  {r['requested_by']:<13} {r['requested_at'][:19]:<20} "
              f"{r['decided_by'] or '-':<11} {r['run_id'] or '-'}")
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
    # The Monarch authoring probe is a paid Monarch launch: refused until M5.
    if args.monarch_probe:
        return _refuse([f"--monarch-probe: {approvals.MONARCH_REASON}"])
    # Provider probes spend cents: they need the operator and go through the
    # ledger, one reservation per request. `--arms monarch` alone is free.
    ledger = operator = None
    if keys != ["monarch"]:
        operator = approvals.operator(os.environ)
        if operator is None:
            return _refuse([approvals.NO_OPERATOR])
        from wb_orchestrator.budget import BudgetConfigurationError
        try:
            ledger = _ledger(args)
        except (BudgetConfigurationError, ValueError) as e:
            print(f"budget: {e}", file=sys.stderr)
            return 2
    reports = doctor_mod.run_doctor(keys, monarch_probe=False, ledger=ledger, operator=operator)
    print(doctor_mod.format_report(reports))
    return 0 if all(r.get("ok") for r in reports) else 1


def cmd_grade(args) -> int:
    store = _store(args)
    run = store.run(args.run_id)
    if run is None:
        print(f"unknown run {args.run_id}", file=sys.stderr)
        return 1
    config = json.loads(run["config_json"])
    suite_dir = args.suite or config["suite_dir"]
    # The product's own world supplies the source half of the verdict. A run
    # recorded before feature 026 names no world, which is the world it ran on.
    from wb_world import registry
    res = regrade(store, args.run_id, suite_dir,
                  world=registry.resolve((config.get("product") or {}).get("world")))
    print(f"regraded {res['regraded']} episodes, {res['changed']} verdicts changed")
    for k in ("contract_drift", "task_missing", "artifacts_missing", "evidence_invalid"):
        if res[k]:
            print(f"WARNING: {res[k]} episodes skipped ({k.replace('_', ' ')})")
    _print_run_report(store, args.run_id)
    return 0


def cmd_report(args) -> int:
    from wb_report.report import GateError, write_report
    store = _store(args)
    try:
        paths = write_report(store, args.run_id, args.out,
                             baseline_arm=args.baseline, fmt=args.format)
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
            out = Path(args.out) / f"summary-{stamp}.html"
        path = write_summary(store, run_ids, out, baseline=args.baseline)
    except (GateError, KeyError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    print(f"wrote {path}")
    return 0


def cmd_corpus(args) -> int:
    from wb_orchestrator import corpus as corpus_mod
    if args.corpus_cmd in ("import-eog", "import-appworld", "import-tau2"):
        try:
            rules = json.loads(Path(args.reviewed_rules).read_text(encoding="utf-8")) if args.reviewed_rules else None
            if args.corpus_cmd == "import-eog":
                from wb_worlds.enterprise_ops.importer import import_eog
                result = import_eog(args.domains.split(","), args.out, mode=args.mode, limit=args.limit, reviewed_rules=rules)
            elif args.corpus_cmd == "import-appworld":
                from wb_worlds.appworld.importer import import_tasks
                result = {"tasks":[task["task"] for task in import_tasks(args.split, args.out, args.limit, reviewed_rules=rules)]}
            else:
                from wb_worlds.tau2.importer import import_tau2
                result = import_tau2(args.domains.split(","), args.out, split=args.split, limit=args.limit, rules=rules)
            print(json.dumps(result, indent=2, default=str))
            return 0
        except (ValueError, OSError, RuntimeError) as exc:
            print(f"{args.corpus_cmd}: {exc}", file=sys.stderr)
            return 2
    if args.corpus_cmd == "import-ab":
        product = config.load_product(config.resolve_name_or_path(args.product, "product"))
        if args.dest and args.out:
            print("give --out DIR (the folder holding imported-<domain>/) or --dest "
                  "(a pattern with {domain}), not both", file=sys.stderr)
            return 2
        # --out names the folder that holds one imported-<domain>/ per domain;
        # with neither flag the folders land under corpus/, as they always did.
        dest = args.dest or f"{args.out or 'corpus'}/imported-{{domain}}"
        try:
            res = corpus_mod.import_ab(args.domains.split(","), dest,
                                       product_services=product.services,
                                       revision=args.revision)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        width = max(len(d) for d in res["by_domain"]) + 1
        for domain, n in res["by_domain"].items():
            print(f"{domain + ':':<{width}} {n['written']:>4} written, "
                  f"{n['unchanged']} unchanged")
        print(f"total: {res['written'] + res['unchanged']} tasks "
              f"in {len(res['by_domain'])} folders")
        if res["revision"]:
            print(f"revision: {res['revision']} (automation-bench {res['world_version']})"
                  + (f"; manifest: {Path(res['manifest']).as_posix()}" if res["manifest"] else ""))
        missing = ", ".join(res["missing_services"]) or "none"
        print(f"services seeded by these domains and NOT listed by product "
              f"{product.name}: {missing}")
        return 1 if res["missing_services"] else 0
    if args.corpus_cmd == "manifest":
        try:
            m = corpus_mod.write_manifest(args.root)
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 1
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        print(corpus_mod.format_manifest(args.root, m))
        return 0
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
    if args.corpus_cmd == "slate":
        return _corpus_slate(args)
    if args.corpus_cmd == "split":
        return _corpus_split(args)
    return 2


def _corpus_split(args) -> int:
    """Draw development and held-out slates stratified by tier and domain (FR-017, FR-018, FR-033)."""
    from pathlib import Path

    from wb_orchestrator import slate

    dirs: list[Path] = []
    if args.corpus:
        for c in args.corpus:
            for part in c.split(","):
                part = part.strip()
                p = Path(part)
                if "*" in part:
                    matched = sorted(p.parent.glob(p.name)) if p.parent.exists() else []
                    dirs.extend(matched)
                else:
                    dirs.append(p)
    else:
        dirs = sorted(Path("corpus").glob("imported-*"))

    dirs = sorted(set(dirs))
    missing = [str(d) for d in dirs if not d.is_dir()]
    if missing or not dirs:
        print(f"corpus folder missing or empty: {missing or 'corpus/imported-*'}",
              file=sys.stderr)
        return 3

    try:
        r = slate.split(
            dirs=dirs,
            size=args.size,
            seed=args.seed,
            dev_out=args.dev_out,
            heldout_out=args.heldout_out,
            manifest=args.manifest,
            because=args.because,
        )
    except slate.Refusal as e:
        print(str(e), file=sys.stderr)
        return 2
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(slate.format_split_summary(r))
    return 0


def _corpus_slate(args) -> int:
    """Freeze a task set listed by id (unblock plan M2). Offline: no key, no network, no money."""
    from pathlib import Path

    from wb_orchestrator import slate
    dirs = [Path(d) for d in (args.corpus or sorted(Path("corpus").glob("imported-*")))]
    missing = [str(d) for d in dirs if not d.is_dir()]
    if missing or not dirs:
        print(f"corpus folder missing or empty: {missing or 'corpus/imported-*'}",
              file=sys.stderr)
        return 3
    if not args.refreeze and not args.ids:
        print("wb corpus slate needs --ids FILE to freeze a set, or --refreeze to rewrite "
              "the set its manifest already records", file=sys.stderr)
        return 2
    try:
        r = slate.freeze(args.ids, args.out, because=args.because, dirs=dirs,
                         refreeze=args.refreeze,
                         allow_frozen_overlap=args.allow_frozen_overlap)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 3
    except slate.Refusal as e:
        print(str(e), file=sys.stderr)
        return 2
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    text = slate.summary(r)
    if r.refrozen:
        text += f" Refrozen because: {args.because}"
    print(text)
    print(f"[ok] write {r.out.as_posix()}/ ({r.count} files)")
    print(f"[ok] write {r.manifest.as_posix()}")
    return 0


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
                                 conform=not args.no_conform,
                                 knowledge=args.knowledge, knowledge_map=args.map,
                                 tasks=getattr(args, "tasks", None))
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2


def cmd_monarch_verify(args) -> int:
    """Check the Monarch instance the harness names and record it for the launchers (M5)."""
    from wb_studio import enterprise
    from wb_studio.app import Studio
    studio = Studio(tasks=[])
    studio.enterprise_product = getattr(args, "product", "simulated-apps")
    studio.enterprise_harness = getattr(args, "harness", "monarch")
    record = enterprise.verify(studio)
    for check in record["checks"]:
        print(f"[{'OK ' if check['ok'] else 'NO '}] {check['name']}: {check['detail']}")
    print(f"served build: {record.get('version') or 'unknown'}   front door: {record.get('front_door') or 'n/a'}")
    print(f"record: {enterprise.probe_path(studio)}")
    if record["ok"]:
        print("Monarch competitors may launch against this instance for the next two hours.")
        return 0
    print("Monarch competitors stay refused until every check passes.", file=sys.stderr)
    return 1


def cmd_monarch_knowledge(args) -> int:
    """The lab seeds: stock seeds plus a knowledge catalog's descriptions; imports nothing."""
    try:
        return monarch_setup.lab_seeds(config.resolve_name_or_path(args.product, "product"),
                                       config.resolve_name_or_path(args.harness, "harness"),
                                       args.out, os.environ, sys.stdout,
                                       knowledge_path=args.knowledge, map_path=args.map,
                                       front_door=args.front_door)
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
    out = seeds_dir.parent / "monarch-conformance.json"   # outside the seed folder: the deploy script scans every *.json in it
    report.write_json(out)
    print(f"report: {out}")
    failed = report.failed_services()
    if failed:
        print(f"mismatching services: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def cmd_monarch_recipes(args) -> int:
    if bool(args.plan) == bool(args.tasks):
        print("wb monarch recipes: give exactly one of --plan and --tasks", file=sys.stderr)
        return 2
    # Authoring recipes is a paid Monarch launch: refused until M5 verifies an instance.
    return _refuse([f"wb monarch recipes: {approvals.MONARCH_REASON}"])




def cmd_telemetry(args) -> int:
    from wb_orchestrator import langfuse_export as export
    paths = {"ledger": args.ledger, "results": args.db}
    if args.telemetry_cmd == "backfill":
        if Path(args.ledger).exists():
            _ledger(args).backfill_telemetry()
        if Path(args.db).exists():
            store = _store(args)
            try:
                store.backfill_telemetry()
            finally:
                store.close()
    if args.telemetry_cmd == "flush":
        export.drain()
        result = {name: export.flush(path) for name, path in paths.items()}
    elif args.telemetry_cmd == "reconcile":
        export.drain()
        result = {name: export.reconcile(path) for name, path in paths.items()}
    else:
        result = {name: export.status(path) for name, path in paths.items()}
    print(json.dumps(result, sort_keys=True))
    return int(any(row.get("errors") or row.get("pending") is None for row in result.values()))


def main(argv: list[str] | None = None) -> int:
    load_dotenv()   # keys live in workflowbench/.env (gitignored), never in code
    config.derive_langfuse_keys(os.environ)
    ap = argparse.ArgumentParser(prog="wb", description="WorkflowBench runner")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--ledger", default=DEFAULT_LEDGER,
                    help="the shared weekly ledger every paid request is reserved in "
                         "(default: research/budget.sqlite3 at the repo root)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("telemetry", help="inspect, retry or backfill Langfuse history; no model calls")
    p.add_argument("telemetry_cmd", choices=("status", "flush", "backfill", "reconcile"),
                   help="flush sends up to 100 pending records per database; backfill queues saved history")
    p.set_defaults(fn=cmd_telemetry)

    p = sub.add_parser("budget", help="inspect and reconcile the shared weekly experiment ledger")
    bsub = p.add_subparsers(dest="budget_cmd", required=True)
    bs = bsub.add_parser("status")
    bs.add_argument("--ledger", dest="status_ledger", default=None,
                    help="ledger to inspect; default: the top-level --ledger")
    bs.set_defaults(fn=cmd_budget_status)
    br = bsub.add_parser("reconcile",
                         help="compare one week's provider usage export with the ledger's settled total")
    br.add_argument("--week", required=True, help="the week's Monday, YYYY-MM-DD (America/Sao_Paulo)")
    br.add_argument("--provider", action="append", required=True,
                    help="repeatable: a billing account named in the rows (anthropic, openai, "
                         "fireworks, google, moonshot, zai, monarch)")
    br.add_argument("--csv", action="append", required=True,
                    help="repeatable: normalized usage rows `date,provider,usd` (see config/README.md)")
    br.add_argument("--out", dest="reconcile_out", default=None,
                    help="folder for <week>.md and <week>.json; default: research/reconciliation/ "
                         "next to the ledger")
    br.set_defaults(fn=cmd_budget_reconcile)
    ba = bsub.add_parser("acknowledge",
                         help="answer for one recorded overrun so admissions resume; the overrun stays on the record")
    ba.add_argument("reservation_id")
    ba.add_argument("--reason", required=True, help="why this overrun is understood; kept with the reservation")
    ba.add_argument("--by", default=None, help="the person acknowledging; default: WB_OPERATOR")
    ba.set_defaults(fn=cmd_budget_acknowledge)
    brl = bsub.add_parser("release",
                          help="release one hold whose cost no provider ever reported; the unknown stays on the record")
    brl.add_argument("reservation_id")
    brl.add_argument("--because", required=True,
                     help="why this hold can be released; kept with the reservation")
    brl.add_argument("--by", default=None, help="the person releasing it; default: WB_OPERATOR")
    brl.set_defaults(fn=cmd_budget_release)
    be = bsub.add_parser("envelope", help="sets and shows the weekly research envelope")
    be.add_argument("envelope_action", nargs="?", choices=("status",), default=None,
                    help="status (optional)")
    be.add_argument("--set", dest="envelope_set", default=None,
                    help="set the weekly envelope amount in USD")
    be.add_argument("--per-experiment", dest="per_experiment", default=None,
                    help="per-experiment ceiling in USD")
    be.add_argument("--by", dest="by", default=None,
                    help="the person setting the envelope (e.g. Lucas)")
    be.add_argument("--ledger", dest="envelope_ledger", default=None,
                    help="ledger to inspect; default: the top-level --ledger")
    be.add_argument("--genesis-dir", dest="genesis_dir", default=None,
                    help="genesis directory (optional)")
    be.set_defaults(fn=cmd_budget_envelope)

    p = sub.add_parser("experiment",
                       help="size and gate a hypothesis: the record Genesis already keeps, from a terminal")
    esub = p.add_subparsers(dest="experiment_cmd", required=True)
    ep = esub.add_parser("propose", help="size it against the sign test that settles it; refuses what cannot conclude")
    ep.add_argument("--claim", required=True)
    ep.add_argument("--measure", default="pass_rate")
    ep.add_argument("--direction", default="a_higher", choices=["a_higher", "a_lower"])
    ep.add_argument("--minimum-effect", dest="minimum_effect", required=True, type=float,
                    help="the smallest difference worth calling real; also the share of tasks expected to flip")
    ep.add_argument("--task-set", dest="task_set", required=True)
    ep.add_argument("--a", required=True, help="the version under test")
    ep.add_argument("--b", required=True, help="what it is compared against")
    ep.add_argument("--model", default=None)
    ep.add_argument("--repetitions", type=int, default=1)
    ep.add_argument("--slate", default="development", choices=["development", "held-out"])
    ep.add_argument("--id", default=None)
    ep.add_argument("--parent", default=None, help="the record this descends from; it keeps that lineage")
    ep.set_defaults(fn=cmd_experiment_propose)
    ec = esub.add_parser("confirm", help="whether a lineage may reach the held-out slate; it reaches it once")
    ec.add_argument("lineage")
    ec.set_defaults(fn=cmd_experiment_confirm)

    p = sub.add_parser("run")
    p.add_argument("--product", default=None, help="name in config/products or a path; asked if omitted")
    p.add_argument("--plan", default=None, help="name in config/plans or a path; asked if omitted")
    p.add_argument("--run-id", default=None)
    p.add_argument("--repetitions", type=int, default=None,
                   help="planned attempts per prompt and competitor; default 1 (FR-019)")
    p.add_argument("--request", default=None,
                   help="run an approved approval request (wb approvals); the config hash must still match")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("approve", help="approve a pending launch request (approvers only)")
    p.add_argument("request_id")
    p.set_defaults(fn=cmd_approve)

    p = sub.add_parser("deny", help="deny a pending launch request (approvers only)")
    p.add_argument("request_id")
    p.set_defaults(fn=cmd_deny)

    p = sub.add_parser("approvals", help="list the launch requests and their state")
    p.set_defaults(fn=cmd_approvals)

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
    p.add_argument("--baseline", default=None, help="baseline arm for paired stats")
    p.add_argument("--format", default="html", choices=("html", "executive"),
                   help="html: the seven-section technical page (default); "
                        "executive: the stakeholder page, Monarch first")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("summary", help="two to six rounds on one page")
    p.add_argument("--runs", default=None, help="comma list of run ids, in page order")
    p.add_argument("--plans", default=None,
                   help="comma list of plans; uses the most recent run of each")
    p.add_argument("--baseline", default=None, help="baseline where a round names none")
    p.add_argument("--out", dest="summary_out", default=None,
                   help="output file; default out/summary-<timestamp>.html")
    p.set_defaults(fn=cmd_summary)

    p = sub.add_parser("corpus")
    csub = p.add_subparsers(dest="corpus_cmd", required=True)
    for name in ("import-eog", "import-appworld", "import-tau2"):
        external = csub.add_parser(name, help="Import pinned source tasks without altering upstream checks")
        external.add_argument("--out", required=True)
        external.add_argument("--limit", type=int)
        external.add_argument("--reviewed-rules", help="JSON reviewed task-specific permitted-change rules")
        if name != "import-appworld":
            external.add_argument("--domains", required=True)
        if name == "import-eog":
            external.add_argument("--mode", default="oracle")
        else:
            external.add_argument("--split", default="dev" if name == "import-appworld" else "base")
    ci = csub.add_parser("import-ab")
    ci.add_argument("--domains", required=True,
                    help="comma list, e.g. simple,sales,hr; or 'all' for every known domain")
    ci.add_argument("--dest", default=None,
                    help="output task dir; may contain {domain}, replaced per domain "
                         "(default: <--out>/imported-{domain})")
    ci.add_argument("--out", default=None,
                    help="the folder holding one imported-<domain>/ per domain "
                         "(default: corpus); not with --dest")
    ci.add_argument("--revision", default=None,
                    help="label of the world revision the tasks are imported under, e.g. "
                         "evalrepair10; stamps every task with info.world and writes "
                         "<out>/MANIFEST.yaml. Required unless the installed package is "
                         "the upstream 1.0.6")
    ci.add_argument("--product", default="simulated-apps",
                    help="product whose service list the seeded services are checked against")
    cm = csub.add_parser("manifest",
                         help="rewrite ROOT/MANIFEST.yaml from the imported-* folders under ROOT")
    cm.add_argument("root", help="the folder holding imported-<domain>/, e.g. corpus-evalrepair10")
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
    cs = csub.add_parser("slate", help="freeze a task set listed by id, with its manifest")
    cs.add_argument("--ids", default=None,
                    help="file with one task id per line; # comments and blank lines allowed; "
                         "the comment lines become the manifest's selection rule")
    cs.add_argument("--out", required=True,
                    help="the set's folder, e.g. tasks/achievable-50; the manifest is written "
                         "beside it as <name>-manifest.yaml")
    cs.add_argument("--because", required=True,
                    help="why the set exists (or, with --refreeze, why it is rewritten); "
                         "recorded in the manifest")
    cs.add_argument("--refreeze", action="store_true",
                    help="rewrite the set from the corpus keeping the ids its manifest "
                         "records; use after an approval-rule change or a corpus re-import")
    cs.add_argument("--allow-frozen-overlap", action="store_true",
                    help="let an id that already sits in another frozen set in; the overlap "
                         "is recorded in the manifest (a refusal otherwise)")
    cs.add_argument("--corpus", action="append", default=None,
                    help="repeatable; default: every corpus/imported-* folder")
    csp = csub.add_parser("split",
                          help="draw development and held-out slates stratified by difficulty tier and domain")
    csp.add_argument("--corpus", action="append", default=None,
                     help="repeatable; default: every corpus/imported-* folder")
    csp.add_argument("--size", type=int, required=True,
                     help="tasks per slate (both slates get this count)")
    csp.add_argument("--seed", type=int, required=True,
                     help="seed for the stratified draw, recorded in the manifest")
    csp.add_argument("--dev-out", required=True,
                     help="folder where the development slate is written")
    csp.add_argument("--heldout-out", required=True,
                     help="folder where the held-out slate is written")
    csp.add_argument("--manifest", required=True,
                     help="file where the split manifest is written")
    csp.add_argument("--because", required=True,
                     help="why the split exists, recorded in the manifest")
    p.set_defaults(fn=cmd_corpus)

    p = sub.add_parser("monarch", help="prepare Monarch for a product")
    msub = p.add_subparsers(dest="monarch_cmd", required=True)
    ms = msub.add_parser("setup", help="generate seeds, import them, write the knowledge-base hashes")
    ms.add_argument("--product", default="simulated-apps", help="name in config/products or a path")
    ms.add_argument("--harness", default="monarch", help="name in config/harnesses or a path")
    ms.add_argument("--out", default="out/monarch-seeds", help="where the seed folders are written")
    ms.add_argument("--tasks", default=None,
                    help="frozen task directory; required for external source products")
    ms.add_argument("--no-conform", action="store_true",
                    help="import without checking that every action is true against "
                         "the simulated apps (see `wb monarch conform`)")
    ms.add_argument("--knowledge", default=None,
                    help="a reviewed knowledge catalog (JSON): teach the instance the lab "
                         "seeds instead of the stock ones (see `wb monarch knowledge`)")
    ms.add_argument("--map", default=None,
                    help="the catalog-to-action table; default: <product>.knowledge-map.yaml "
                         "next to the product file")
    ms.set_defaults(fn=cmd_monarch_setup)
    mv = msub.add_parser("verify", help="check the Monarch instance (backend, session, knowledge base, "
                                        "Langfuse) and record it; a passing record admits Monarch competitors "
                                        "for two hours")
    mv.add_argument("--product", default="simulated-apps", help="name in config/products or a path")
    mv.add_argument("--harness", default="monarch", help="name in config/harnesses or a path")
    mv.set_defaults(fn=cmd_monarch_verify)
    mk = msub.add_parser("knowledge",
                         help="write the lab seeds: the stock seeds with action descriptions "
                              "from a reviewed knowledge catalog, plus KNOWLEDGE-MAPPING.yaml "
                              "(offline; imports nothing)")
    mk.add_argument("--knowledge", required=True, help="the knowledge catalog (JSON)")
    mk.add_argument("--product", default="simulated-apps", help="name in config/products or a path")
    mk.add_argument("--harness", default="monarch", help="name in config/harnesses or a path")
    mk.add_argument("--map", default=None,
                    help="the catalog-to-action table; default: <product>.knowledge-map.yaml "
                         "next to the product file")
    mk.add_argument("--out", default="out/monarch-seeds-lab", help="where the seed folders are written")
    mk.add_argument("--front-door", default=None,
                    help="the front-door URL the seeds point at; default: from the harness")
    mk.set_defaults(fn=cmd_monarch_knowledge)
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

    p = sub.add_parser("genesis", help="Genesis, the lab scientist: its code index of the Monarch checkout")
    gsub = p.add_subparsers(dest="genesis_cmd", required=True)
    gi = gsub.add_parser("index", help="rebuild the Monarch code index now (free; the daily job does the same at 04:00)")
    gi.set_defaults(fn=cmd_genesis_index)

    p = sub.add_parser("studio", help="private live comparison UI with bounded paid API controls")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT") or os.environ.get("STUDIO_PORT") or 8765),
                   help="listening port; PORT or STUDIO_PORT in the environment sets the default (8765)")
    p.set_defaults(fn=cmd_studio)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
