"""Report builder per BUILD-SPEC §2.6. Input: store queries only — no
hand-entered numbers. Every figure carries value ± SEM, W/L where paired,
its source line {suite, suite_version, denominator, arm, run_id}, and the
contract hashes it covers.

The gate is code: audiences.yaml maps audience -> arm allowlist; a disallowed
arm in the input raises GateError, never warns. The public-rung2 audience
strips bare/* and monarch/lab@* at query level (arms are filtered before any
stat is computed, not by editing rendered output) and swaps exact dollars for
cost ratios (DESIGN descope: no external cost-per-workflow dollars).
"""
from __future__ import annotations

import fnmatch
import html as _html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from wb_results.store import Store
from wb_stats.stats import arm_summary, paired_wl, pass_hat_k

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
    if audience != "internal" and any(a.startswith("monarch/lab") for a in arms):
        raise GateError("monarch/lab@* may never render outside the internal audience")

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
        summ = arm_summary(res["rows"])
        phk = pass_hat_k(res["rows"], k)
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
            wl = paired_wl(per_arm_rows[arm], per_arm_rows[baseline])
            fig = {"kind": "paired", "arm": arm, "baseline": baseline,
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

    return {"run_id": run_id, "suite": run["suite"], "config_hash": run["config_hash"],
            "audience": audience, "arms": arms, "arms_stripped_by_gate": stripped,
            "baseline": baseline, "k": k, "figures": figures}


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
    lines = [f"# WorkflowBench report — {report['run_id']}",
             "",
             f"audience: **{report['audience']}** · suite `{report['suite']}` · "
             f"config `{report['config_hash']}` · k={report['k']}"]
    if report["audience"] == "internal" and any(a.startswith("monarch/lab") for a in report["arms"]):
        lines.append("\n> **INTERNAL — CONTAINS LAB ARMS — DO NOT EXPORT**")
    if report["arms_stripped_by_gate"]:
        if report["audience"] == "internal":
            lines.append(f"\narms stripped by audience gate: {', '.join(report['arms_stripped_by_gate'])}")
        else:
            # Public renders never name gated arms — even their existence is internal.
            lines.append(f"\n{len(report['arms_stripped_by_gate'])} arm(s) withheld by audience gate")
    lines.append("\n## Per-arm results\n")
    hdr = "| arm | strict pass ± SEM | pass^k | infra rate | cache hit |"
    div = "|---|---|---|---|---|"
    dollars = any("cost_usd" in f for f in report["figures"] if f["kind"] == "arm_summary")
    if dollars:
        hdr += " cost (USD) |"; div += "---|"
    lines += [hdr, div]
    for f in report["figures"]:
        if f["kind"] != "arm_summary":
            continue
        phk = f["pass_hat_k"]
        phk_s = _fmt_pm({"mean": phk["mean"], "sem": phk["sem"]}) if phk["mean"] is not None else "n/a"
        row = (f"| `{f['arm']}` | {_fmt_pm(f['strict_pass'])} | {phk_s} "
               f"| {f['infra_rate'] if f['infra_rate'] is not None else 'n/a'} "
               f"| {f['cache_hit_rate'] if f['cache_hit_rate'] is not None else 'n/a'} |")
        if dollars:
            row += f" {f.get('cost_usd', 'n/a')} |"
        lines.append(row)
    for f in report["figures"]:
        if f["kind"] == "arm_summary":
            lines.append(f"  \n  `{_source_line(f['source'])}` · contracts: "
                         f"{', '.join(h[:8] for h in f['contract_hashes'])}")
    paired = [f for f in report["figures"] if f["kind"] == "paired"]
    if paired:
        lines.append("\n## Paired comparisons\n")
        for f in paired:
            m = f["mcnemar"]
            lines.append(
                f"- `{f['arm']}` vs `{f['baseline']}`: **{f['wins']}W / {f['losses']}L** "
                f"(both {f['both_pass']}, neither {f['neither_pass']}, "
                f"infra-dropped {f['dropped_infra']}) · McNemar b={m['b']} c={m['c']} "
                f"p={m['p']}" +
                (f" · cost ratio {f['cost_ratio_vs_baseline']}x" if "cost_ratio_vs_baseline" in f else ""))
            lines.append(f"  `{_source_line(f['source'])}`")
    return "\n".join(lines) + "\n"


def render_html(report: dict[str, Any]) -> str:
    body = _html.escape(render_md(report)).replace("\n", "<br>\n")
    theme = ("body{background:#14161d;color:#e6e6e6;font:14px/1.5 monospace;padding:2rem}"
             if report["audience"] == "internal" else
             "body{background:#fff;color:#1a1a1a;font:15px/1.6 Georgia,serif;padding:2rem}")
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>WorkflowBench {_html.escape(report['run_id'])}</title>"
            f"<style>{theme}</style></head><body>{body}</body></html>")


def write_report(store: Store, run_id: str, out_dir: str | Path,
                 audience: str = "internal", **kw) -> dict[str, str]:
    rep = build_report(store, run_id, audience=audience, **kw)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md = out / f"report-{run_id}-{audience}.md"
    htm = out / f"report-{run_id}-{audience}.html"
    md.write_text(render_md(rep), encoding="utf-8")
    htm.write_text(render_html(rep), encoding="utf-8")
    return {"md": str(md), "html": str(htm)}
