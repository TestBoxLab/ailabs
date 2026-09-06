"""Report builder per BUILD-SPEC §2.6. Input: store queries only — no
hand-entered numbers. Every figure carries value ± SEM, W/L where paired,
its source line {suite, suite_version, denominator, arm, run_id}, and the
contract hashes it covers.

The gate is code: audiences.yaml maps audience -> arm allowlist; a disallowed
arm in the input raises GateError, never warns. The public-rung2 audience
strips everything but `monarch` at query level (arms are filtered before any
stat is computed, not by editing rendered output) and swaps exact dollars for
cost ratios (DESIGN descope: no external cost-per-workflow dollars).
"""
from __future__ import annotations

import fnmatch
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from wb_report.metrics import (NOT_APPLICABLE_REASON, comparison,
                               competitor_metrics, is_monarch, is_not_applicable,
                               monarch_attempts, round_totals)
from wb_results.store import Store
from wb_stats.stats import _is_infra, arm_summary, paired_wl, pass_hat_k
from wb_stats.stats import sem as stats_sem

_AUDIENCES_FILE = Path(__file__).parent / "audiences.yaml"


class GateError(Exception):
    pass


def load_audiences(path: str | Path = _AUDIENCES_FILE) -> dict[str, list[str]]:
    """Parse the trivial `audience:\n  - pattern` YAML subset (stdlib only)."""
    audiences: dict[str, list[str]] = {}
    current: str | None = None
    for raw in Path(path).read_text().splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current = line[:-1].strip()
            audiences[current] = []
        elif line.strip().startswith("- ") and current:
            audiences[current].append(line.strip()[2:].strip().strip('"').strip("'"))
        else:
            raise ValueError(f"unparseable audiences.yaml line: {raw!r}")
    return audiences


def is_lab(name: str) -> bool:
    """Lab competitors are watermarked in internal and never rendered elsewhere."""
    return name.startswith("monarch-lab")


def _allowed(arm: str, allowlist: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(arm, pat) for pat in allowlist)


def gate_arms(arms: list[str], audience: str,
              audiences: dict[str, list[str]] | None = None) -> list[str]:
    audiences = audiences or load_audiences()
    if audience not in audiences:
        raise GateError(f"unknown audience {audience!r}; known: {sorted(audiences)}")
    allowlist = audiences[audience]
    kept = [a for a in arms if _allowed(a, allowlist)]
    return kept


# Tier names in difficulty order, so the matrix reads easy to hard. A tier this
# does not know sorts after every known one (feature 005 owns the definition).
_TIER_ORDER = {"simple": 0, "medium": 1, "complex": 2}


def _name_of(value: Any) -> Any:
    """A plan or a product is recorded either as its identifier or as the whole
    mapping the run resolved. The page wants the identifier: dumping the mapping
    puts a few thousand characters of configuration on the screen."""
    return value.get("name") if isinstance(value, dict) else value


def _cell(rows: list[dict]) -> dict[str, Any]:
    """One task-and-competitor cell of the matrix (contracts section 3).
    Infrastructure attempts are named and excluded from the denominator, so
    `0/0 (infra 2)` is a legitimate cell, not a bug."""
    ok = [r for r in rows if not _is_infra(r)]
    failing = [r for r in sorted(rows, key=lambda r: r["trial"]) if not r["passed"]]
    category, detail, trial = "passed", None, None
    if failing:
        first = failing[0]
        trial = first["trial"]      # which repetition the reason was taken from
        if _is_infra(first):
            category, detail = "infra", first.get("termination")
        elif first.get("unexpected_changes"):
            category = "unexpected change"
            detail = ", ".join(c.get("path", "") for c in first["unexpected_changes"])
        elif not first.get("assertions_passed"):
            category = "assertion failed"
        elif str(first.get("error") or "").startswith("needs_input:"):
            category, detail = "needs_input", first["error"]
        elif first.get("error"):
            category, detail = "error", first["error"]
        else:
            category, detail = "error", first.get("termination")
    ordered = sorted(ok, key=lambda r: r["trial"])
    # "pass on retry": the first attempt failed and a later one passed. That is
    # a different result from passing outright, and the page says so.
    on_retry = bool(ordered) and not ordered[0]["passed"] and any(
        r["passed"] for r in ordered[1:])
    return {"passed": sum(1 for r in ok if r["passed"]), "attempted": len(ok),
            "infra": len(rows) - len(ok), "category": category, "detail": detail,
            "trial": trial, "on_retry": on_retry}


def _build_matrix(arms: list[str], per_arm_rows: dict[str, list[dict]],
                  task_info: dict[str, dict]) -> dict[str, Any]:
    """One row per task, one cell per competitor. The `domain` and `tier`
    columns exist only when a task carries them (research R8: none does today).
    """
    by_task: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for arm in arms:
        for row in per_arm_rows[arm]:
            by_task[row["task_id"]][arm].append(row)
    info = lambda task, field: (task_info.get(task) or {}).get(field)
    rows = [{"task_id": task, "domain": info(task, "domain"), "tier": info(task, "tier"),
             "cells": {arm: _cell(cells[arm]) for arm in arms if cells.get(arm)}}
            for task, cells in by_task.items()]
    # by tier where one exists, then by task id (contracts section 3). Tiers are
    # ordered by difficulty, not alphabetically; an unrecognised tier sorts last
    # rather than into the middle of the known ones.
    rows.sort(key=lambda r: (_TIER_ORDER.get(r["tier"], len(_TIER_ORDER)), r["task_id"]))
    return {"arms": arms,
            "has_domain": any(r["domain"] is not None for r in rows),
            "has_tier": any(r["tier"] is not None for r in rows),
            "rows": rows}


def _build_failures(arms: list[str], per_arm_rows: dict[str, list[dict]]) -> list[dict]:
    """Every failed attempt, infrastructure ones included, ordered by task, then
    competitor, then repetition (contracts section 4)."""
    failures = [{"task_id": r["task_id"], "arm": arm, "trial": r["trial"],
                 "termination": r.get("termination"), "error": r.get("error"),
                 "unexpected_change_paths": [c.get("path", "")
                                             for c in (r.get("unexpected_changes") or [])]}
                for arm in arms for r in per_arm_rows[arm] if not r["passed"]]
    failures.sort(key=lambda f: (f["task_id"], f["arm"], f["trial"]))
    return failures


def _build_provenance(run: dict, config: dict, audience: str, stripped: list[str],
                      per_arm_rows: dict[str, list[dict]]) -> dict[str, Any]:
    """Contracts section 5. A non-internal audience gets the count of withheld
    competitors, never their names: their existence is internal (FR-023)."""
    monarch_rows = [r for arm, rows in per_arm_rows.items() if arm.startswith("monarch")
                    for r in rows]
    missing_cost = None
    if monarch_rows:
        missing_cost = {"missing": sum(1 for r in monarch_rows
                                       if "cost_missing" in (r.get("flags") or [])),
                        "total": len(monarch_rows)}
    return {
        "config_hash": run["config_hash"],
        "plan": _name_of(config.get("plan")), "product": _name_of(config.get("product")),
        "mode": config.get("mode"),
        "price_tables": [f"{t['name']}@{t['prices_verified']}"
                         for _, t in sorted((config.get("price_tables") or {}).items())],
        "missing_cost": missing_cost,
        "suite": run["suite"], "suite_version": run["suite"].split("@")[-1],
        "task_hashes": sorted({(r.get("contract_sha256") or "")[:8]
                               for rows in per_arm_rows.values() for r in rows
                               if r.get("contract_sha256")}),
        "started": run.get("started"), "finished": run.get("finished"),
        "stop_reason": run.get("stop_reason"), "audience": audience,
        "withheld": stripped if audience == "internal" else len(stripped),
    }


def build_report(store: Store, run_id: str, audience: str = "internal",
                 baseline_arm: str | None = None, k: int | None = None,
                 audiences_path: str | Path = _AUDIENCES_FILE) -> dict[str, Any]:
    audiences = load_audiences(audiences_path)
    if audience not in audiences:
        raise GateError(f"unknown audience {audience!r}; known: {sorted(audiences)}")
    allowlist = audiences[audience]

    run = store.run(run_id)
    if run is None:
        raise KeyError(f"unknown run {run_id!r}")
    config = json.loads(run["config_json"])
    all_arms = sorted(store.episodes(run=run_id)["source"]["arm"] or [])
    arms = [a for a in all_arms if _allowed(a, allowlist)]
    stripped = [a for a in all_arms if a not in arms]
    if not arms:
        raise GateError(
            f"audience {audience!r} allows none of the run's arms {all_arms}; "
            "nothing to render")
    if audience != "internal" and any(is_lab(a) for a in arms):
        raise GateError("monarch-lab* may never render outside the internal audience")

    k = k or config.get("k") or 1
    show_dollars = audience == "internal"
    figures: list[dict[str, Any]] = []
    per_arm_rows: dict[str, list[dict]] = {}
    for arm in arms:
        res = store.episodes(run=run_id, arm=arm)
        suites = {r["suite"] for r in res["rows"]}
        if len(suites) > 1 or (suites and suites != {run["suite"]}):
            # Legacy rows live beside new rows in one store but never pool
            # into one headline (BUILD-SPEC §2.9 acceptance).
            raise GateError(f"refusing to pool suites {sorted(suites)} into one figure")
        per_arm_rows[arm] = res["rows"]
        # Attempts the scripted answer key could not act on are not results: they
        # leave every rate here exactly as they leave the metrics block.
        scored = [r for r in res["rows"] if not is_not_applicable(r)]
        not_applicable = bool(res["rows"]) and not scored
        summ = arm_summary(scored)
        phk = pass_hat_k(scored, k)
        contract_hashes = sorted({r.get("contract_sha256") for r in res["rows"] if r.get("contract_sha256")})
        fig: dict[str, Any] = {
            "kind": "arm_summary", "arm": arm,
            "strict_pass": summ["strict_pass"],
            "pass_hat_k": {"k": phk["k"], "mean": phk["mean"], "sem": phk["sem"]},
            "infra_rate": summ["infra_rate"],
            "cache_hit_rate": summ["cache_hit_rate"],
            "source": res["source"],
            "contract_hashes": contract_hashes,
        }
        if not_applicable:
            fig["not_applicable"] = NOT_APPLICABLE_REASON
        if show_dollars:
            fig["cost_usd"] = summ["cost_usd"]
            fig["cost_per_episode"] = summ["cost_per_episode"]
        figures.append(fig)

    baseline = baseline_arm if baseline_arm in arms else (arms[0] if len(arms) > 1 else None)
    if baseline:
        base_cost = sum(r.get("cost_usd") or 0.0 for r in per_arm_rows[baseline])
        for arm in arms:
            if arm == baseline:
                continue
            na = next((f.get("not_applicable") for f in figures
                       if f["kind"] == "arm_summary" and f["arm"] in (arm, baseline)
                       and f.get("not_applicable")), None)
            wl = paired_wl(per_arm_rows[arm], per_arm_rows[baseline])
            fig = {"kind": "paired", "arm": arm, "baseline": baseline,
                   "not_applicable": na,
                   "wins": wl["wins"], "losses": wl["losses"],
                   "both_pass": wl["both_pass"], "neither_pass": wl["neither_pass"],
                   "dropped_infra": wl["dropped_infra"],
                   "mcnemar": wl["mcnemar"],
                   "source": {"suite": run["suite"], "suite_version": run["suite"].split("@")[-1],
                              "denominator": wl["pairs"], "arm": [arm, baseline],
                              "run_id": run_id}}
            if not show_dollars and base_cost:
                arm_cost = sum(r.get("cost_usd") or 0.0 for r in per_arm_rows[arm])
                fig["cost_ratio_vs_baseline"] = round(arm_cost / base_cost, 3)
            figures.append(fig)

    metrics = [competitor_metrics(per_arm_rows[arm], k) for arm in arms]
    by_arm = {m["arm"]: m for m in metrics}
    comparisons = [comparison(by_arm[arm], by_arm[baseline],
                              per_arm_rows[arm], per_arm_rows[baseline],
                              source={"suite": run["suite"],
                                      "suite_version": run["suite"].split("@")[-1],
                                      "run_id": run_id})
                   for arm in arms if baseline and arm != baseline]
    tasks = sorted({r["task_id"] for rows in per_arm_rows.values() for r in rows})

    return {"run_id": run_id, "suite": run["suite"], "config_hash": run["config_hash"],
            "size": {"prompts": len(tasks), "repetitions": k,
                     "per_competitor": len(tasks) * k, "competitors": len(arms),
                     "total": sum(len(per_arm_rows[a]) for a in arms)},
            "metrics": metrics, "comparisons": comparisons,
            "totals": round_totals(metrics),
            # one entry per Monarch attempt, per Monarch competitor; empty when
            # none ran, and the page omits the section entirely
            "monarch_attempts": {arm: monarch_attempts(per_arm_rows[arm])
                                 for arm in arms if is_monarch(arm)},
            "matrix": _build_matrix(arms, per_arm_rows, config.get("task_info") or {}),
            "failures": _build_failures(arms, per_arm_rows),
            "provenance": _build_provenance(run, config, audience, stripped, per_arm_rows),
            "source_suffix": _source_suffix(config, per_arm_rows),
            "audience": audience, "arms": arms, "arms_stripped_by_gate": stripped,
            "baseline": baseline, "k": k, "stop_reason": run.get("stop_reason"),
            "figures": figures}


def _source_suffix(config: dict, per_arm_rows: dict[str, list[dict]]) -> str:
    """PLAN.md §1 rule 8 / FR-023: the price table a Monarch run billed against and
    how many of its attempts had no cost. One suffix per run, appended to every
    source line; empty (line unchanged) when neither applies."""
    parts = [f"price table {t['name']}@{t['prices_verified']}"
             for _, t in sorted((config.get("price_tables") or {}).items())]
    monarch_rows = [r for arm, rows in per_arm_rows.items() if arm.startswith("monarch")
                    for r in rows]
    if monarch_rows:
        missing = sum(1 for r in monarch_rows if "cost_missing" in (r.get("flags") or []))
        parts.append(f"cost missing on {missing}/{len(monarch_rows)} attempts")
    if config.get("mode") == "run-only":
        # FR-030: how many tasks left the comparison, and what run-only actually
        # compares -- an engine on a frozen recipe against whole-task attempts.
        excluded = config.get("excluded_tasks") or {}
        if excluded:
            reasons = ", ".join(sorted(set(excluded.values())))
            parts.append(f"{len(excluded)} task{'s' if len(excluded) != 1 else ''} "
                         f"excluded ({reasons})")
        parts.append("Monarch executed a fixed known-correct workflow; the other competitors "
                     "did the whole task from the request text.")
    return "".join(f" · {p}" for p in parts)


def _fmt_pm(block: dict, pct: bool = True) -> str:
    if block is None or block.get("mean") is None:
        return "n/a"
    m = block["mean"]
    s = block.get("sem")
    if pct:
        return f"{m:.1%} ± {s:.1%}" if s is not None else f"{m:.1%}"
    return f"{m:.4f} ± {s:.4f}" if s is not None else f"{m:.4f}"


def _source_line(src: dict) -> str:
    arm = src["arm"]
    arm = "+".join(arm) if isinstance(arm, list) else arm
    run = src["run_id"]
    run = "+".join(run) if isinstance(run, list) else run
    sv = src["suite_version"]
    sv = "+".join(sv) if isinstance(sv, list) else sv
    return f"src: {src['suite']} · v{sv} · n={src['denominator']} · {arm} · {run}"


def render_md(report: dict[str, Any]) -> str:
    suffix = report["source_suffix"]
    lines = [f"# WorkflowBench report — {report['run_id']}",
             "",
             f"audience: **{report['audience']}** · suite `{report['suite']}` · "
             f"config `{report['config_hash']}` · k={report['k']}"]
    if report.get("stop_reason"):
        lines.append(f"\nstopped: {report['stop_reason']}")
    if report["audience"] == "internal" and any(is_lab(a) for a in report["arms"]):
        lines.append("\n> **INTERNAL — CONTAINS LAB ARMS — DO NOT EXPORT**")
    if report["arms_stripped_by_gate"]:
        if report["audience"] == "internal":
            lines.append(f"\narms stripped by audience gate: {', '.join(report['arms_stripped_by_gate'])}")
        else:
            # Public renders never name gated arms — even their existence is internal.
            lines.append(f"\n{len(report['arms_stripped_by_gate'])} arm(s) withheld by audience gate")
    lines.append("\n## Per-arm results\n")
    hdr = ("| arm | strict pass ± SEM | first try | after retry | retries "
           "| pass^k | infra rate | cache hit |")
    div = "|---|---|---|---|---|---|---|---|"
    # the three retry figures come from the metrics block, matched by arm
    by_arm = {m["arm"]: m for m in report.get("metrics", [])}
    dollars = any("cost_usd" in f for f in report["figures"] if f["kind"] == "arm_summary")
    if dollars:
        hdr += " cost (USD) |"; div += "---|"
    lines += [hdr, div]
    for f in report["figures"]:
        if f["kind"] != "arm_summary":
            continue
        phk = f["pass_hat_k"]
        phk_s = _fmt_pm({"mean": phk["mean"], "sem": phk["sem"]}) if phk["mean"] is not None else "n/a"
        m = by_arm.get(f["arm"], {})
        strict = _fmt_pm(f["strict_pass"])
        if f.get("not_applicable") or m.get("not_applicable"):
            # the answer key on a task set it cannot act on: no result, not a 0%
            strict = phk_s = first = after = retries = "n/a"
        else:
            first = _fmt_pm(m.get("first_try_pass")) if m else "n/a"
            after = _fmt_pm(m.get("pass_after_retry")) if m else "n/a"
            retries = m.get("retries", {}).get("count", "n/a") if m else "n/a"
        row = (f"| `{f['arm']}` | {strict} | {first} | {after} "
               f"| {retries} | {phk_s} "
               f"| {f['infra_rate'] if f['infra_rate'] is not None else 'n/a'} "
               f"| {f['cache_hit_rate'] if f['cache_hit_rate'] is not None else 'n/a'} |")
        if dollars:
            row += f" {f.get('cost_usd', 'n/a')} |"
        lines.append(row)
    for f in report["figures"]:
        if f["kind"] == "arm_summary":
            lines.append(f"  \n  `{_source_line(f['source'])}{suffix}` · contracts: "
                         f"{', '.join(h[:8] for h in f['contract_hashes'])}")
    paired = [f for f in report["figures"] if f["kind"] == "paired"]
    if paired:
        lines.append("\n## Paired comparisons\n")
        for f in paired:
            if f.get("not_applicable"):
                lines.append(f"- `{f['arm']}` vs `{f['baseline']}`: not compared - "
                             f"{f['not_applicable']}")
                lines.append(f"  `{_source_line(f['source'])}{suffix}`")
                continue
            m = f["mcnemar"]
            lines.append(
                f"- `{f['arm']}` vs `{f['baseline']}`: **{f['wins']}W / {f['losses']}L** "
                f"(both {f['both_pass']}, neither {f['neither_pass']}, "
                f"infra-dropped {f['dropped_infra']}) · McNemar b={m['b']} c={m['c']} "
                f"p={m['p']}" +
                (f" · cost ratio {f['cost_ratio_vs_baseline']}x" if "cost_ratio_vs_baseline" in f else ""))
            lines.append(f"  `{_source_line(f['source'])}{suffix}`")
    return "\n".join(lines) + "\n"


def render_html(report: dict[str, Any], sortable: bool = True) -> str:
    """The page of contracts/report.md, no longer the escaped markdown blob.
    The signature is unchanged bar `sortable`, which `wb report --no-sort` sets.
    """
    from wb_report.html import render_page
    return render_page(report, sortable=sortable)


def render_executive(report: dict[str, Any], tasks_dir: str | Path = "tasks") -> str:
    """The stakeholder page: the same dictionary, selected and coloured."""
    from wb_report.html import render_executive_page
    return render_executive_page(report, tasks_dir=tasks_dir)


def write_report(store: Store, run_id: str, out_dir: str | Path,
                 audience: str = "internal", sortable: bool = True,
                 fmt: str = "html", tasks_dir: str | Path = "tasks",
                 **kw) -> dict[str, str]:
    """Write the markdown report and one HTML page.

    `fmt` picks which page: `html` is the seven-section technical page (the
    default, what a round's own report is), `executive` the stakeholder one.
    Both are built from the same `build_report` dictionary, so the gate and
    every number are identical; only the selection and the dress differ.
    """
    rep = build_report(store, run_id, audience=audience, **kw)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md = out / f"report-{run_id}-{audience}.md"
    md.write_text(render_md(rep), encoding="utf-8")
    if fmt == "executive":
        htm = out / f"report-{run_id}-{audience}-executive.html"
        htm.write_text(render_executive(rep, tasks_dir=tasks_dir), encoding="utf-8")
    else:
        htm = out / f"report-{run_id}-{audience}.html"
        htm.write_text(render_html(rep, sortable=sortable), encoding="utf-8")
    return {"md": str(md), "html": str(htm)}

# The one sentence the summary page always carries (contracts section 9). A
# paired figure is only meaningful on one round's identical task set; pooling
# them across rounds would compare competitors on tasks they never both ran.
NEVER_POOLED = ("Paired comparisons are computed per round, on that round's "
                "identical task set, and are never pooled across rounds.")


def build_summary(store: Store, run_ids: list[str], audience: str = "internal",
                  baseline: str | None = None,
                  audiences_path: str | Path = _AUDIENCES_FILE) -> dict[str, Any]:
    """Two to six rounds on one page (data-model.md section 3).

    Each round is built by `build_report`, so the audience gate, the suite check
    and every metric are exactly what the per-round page shows. The aggregate is
    a mean of per-round rates, never a recomputation over pooled attempts, and
    this dictionary has no field for a paired figure spanning rounds.
    """
    if not 2 <= len(run_ids) <= 6:
        raise ValueError(f"a summary covers two to six rounds; got {len(run_ids)}. "
                         "Use `wb report` for a single round.")
    rounds = []
    for run_id in run_ids:
        rep = build_report(store, run_id, audience=audience, baseline_arm=baseline,
                           audiences_path=audiences_path)
        rounds.append({"run_id": run_id, "plan": rep["provenance"]["plan"],
                       "suite": rep["suite"], "size": rep["size"],
                       "metrics": rep["metrics"], "source": rep["provenance"],
                       "source_suffix": rep["source_suffix"],
                       "baseline": rep["baseline"],
                       "stop_reason": rep["stop_reason"],
                       "tier": rep["provenance"].get("tier")})

    arms = sorted({m["arm"] for r in rounds for m in r["metrics"]})
    aggregate = []
    for arm in arms:
        # Only the rounds this competitor actually ran (FR-019): a round it sat
        # out is not a zero, it is not a data point.
        rates = [m["strict_pass"]["mean"] for r in rounds for m in r["metrics"]
                 if m["arm"] == arm and m["strict_pass"]["mean"] is not None]
        entry = {"arm": arm, "n_rounds": len(rates),
                 "mean_strict_pass": round(sum(rates) / len(rates), 6) if rates else None,
                 "sem": round(stats_sem(rates), 6) if len(rates) > 1 else None}
        per_tier = {r["tier"]: m["strict_pass"]["mean"]
                    for r in rounds if r["tier"] for m in r["metrics"]
                    if m["arm"] == arm and m["strict_pass"]["mean"] is not None}
        if per_tier:
            entry["per_tier"] = per_tier
        aggregate.append(entry)

    summary = {"rounds": rounds, "arms": arms, "aggregate": aggregate,
               "audience": audience, "statement": NEVER_POOLED}
    stratification = _stratification(rounds, arms)
    if stratification:
        summary["stratification"] = stratification
    return summary


def _stratification(rounds: list[dict], arms: list[str]) -> list[dict] | None:
    """The random draw beside the mean of the tier rounds (FR-020).

    A round counts as the random draw when its plan name contains `random`.
    Absent one, the block is omitted rather than guessed: comparing a stratified
    mean against nothing would invite reading it as a random-draw rate.
    """
    random_rounds = [r for r in rounds if "random" in str(r["plan"]).lower()]
    tier_rounds = [r for r in rounds if r not in random_rounds]
    if not random_rounds or not tier_rounds:
        return None
    draw = random_rounds[0]
    out = []
    for arm in arms:
        rate = next((m["strict_pass"]["mean"] for m in draw["metrics"]
                     if m["arm"] == arm), None)
        tier_rates = [m["strict_pass"]["mean"] for r in tier_rounds for m in r["metrics"]
                      if m["arm"] == arm and m["strict_pass"]["mean"] is not None]
        tier_mean = sum(tier_rates) / len(tier_rates) if tier_rates else None
        out.append({"arm": arm, "random": rate, "tier_mean": tier_mean,
                    "diff_pp": (rate - tier_mean) * 100
                    if rate is not None and tier_mean is not None else None})
    return out


def resolve_plans(store: Store, plans: list[str]) -> list[tuple[str, str, str]]:
    """The most recent run of each named plan, as (plan, run_id, started).

    `wb summary --plans` prints what it picked: a plan that silently resolved to
    yesterday's round is how the wrong number reaches a slide.
    """
    picked = []
    for plan in plans:
        matches = []
        for run in store.runs():
            config = json.loads(run["config_json"])
            name = _name_of(config.get("plan"))
            if name == plan:
                matches.append(run)
        if not matches:
            raise KeyError(f"no run found for plan {plan!r}")
        latest = max(matches, key=lambda r: r["started"])
        picked.append((plan, latest["run_id"], latest["started"]))
    return picked


def render_summary_html(summary: dict[str, Any], sortable: bool = True) -> str:
    """The summary page. Like render_html, it delegates to the renderer that
    cannot reach the store."""
    from wb_report.html import render_summary_page
    return render_summary_page(summary, sortable=sortable)


def write_summary(store: Store, run_ids: list[str], out: str | Path,
                  audience: str = "internal", baseline: str | None = None,
                  sortable: bool = True) -> str:
    from wb_report.html import render_summary_page
    summary = build_summary(store, run_ids, audience=audience, baseline=baseline)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_summary_page(summary, sortable=sortable), encoding="utf-8")
    return str(path)
