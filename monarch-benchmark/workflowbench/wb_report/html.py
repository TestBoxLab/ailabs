"""The HTML pages: one per round, and the summary over several.

This module renders a dictionary and nothing else. It never imports `Store` and
never opens the database: the audience gate filters competitors out inside
`build_report`, before any statistic exists, and a renderer that could re-query
the store would be four new chances to re-admit a competitor the gate removed
(plan design note 1, research R7). A test asserts this module's imports.

# ponytail: one _table() helper and f-strings, not a template engine. Ceiling:
# if the page ever needs conditional layout beyond a table, revisit.
"""
from __future__ import annotations

import html as _html
from typing import Any


def _esc(value: Any) -> str:
    """Every cell value and every `title` attribute passes through here: error
    strings and change paths come from model output (research R4)."""
    return _html.escape("" if value is None else str(value), quote=True)


def _fmt(value: Any, kind: str = "count") -> str:
    """A value as the page shows it (data-model.md section 4). `None` is `n/a`;
    no `inf`, no `nan`, no silent zero."""
    if value is None:
        return "n/a"
    if isinstance(value, dict):                    # a mean with its error bar
        if value.get("mean") is None:
            return "n/a"
        mean = _fmt(value["mean"], kind)
        sem = value.get("sem")
        return f"{mean} +/- {_fmt(sem, kind)}" if sem is not None else mean
    if kind == "rate":
        return f"{value * 100:.1f}%"
    if kind == "money":
        return f"US$ {value:.4f}"
    if kind == "ratio":
        return f"{value:.2f}x"
    if kind == "seconds":
        return f"{value:.1f} s"
    return str(value)


def _table(headers: list[str], rows: list[list[str]], source_line: str = "",
           title: str = "", numeric_from: int = 1) -> str:
    """One table with its caption and its source line.

    A cell is a string, or a `(text, title)` pair when the visible text is an
    abbreviation of something longer. Every cell and every title is escaped
    here, so a value from a row - an error string, a change path - cannot reach
    the page as markup no matter which caller built it. `_fmt` therefore returns
    plain text and never entities.

    `numeric_from` is the first column index rendered right-aligned; the leading
    columns are labels.
    """
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)

    def cell(i: int, value: Any) -> str:
        """A cell is either a string or `(text, title)`; the title carries the
        full text where the visible one is abbreviated. Both are escaped."""
        text, title = value if isinstance(value, tuple) else (value, None)
        attr = f' title="{_esc(title)}"' if title else ""
        klass = "num" if i >= numeric_from else "lbl"
        return f'<td class="{klass}"{attr}>{_esc(text)}</td>'

    body = "".join(
        "<tr>" + "".join(cell(i, c) for i, c in enumerate(row)) + "</tr>"
        for row in rows)
    caption = f"<caption>{_esc(title)}</caption>" if title else ""
    src = f'<p class="src">{_esc(source_line)}</p>' if source_line else ""
    return (f'<table>{caption}<thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table>{src}")


# The two themes render_html already switched on by audience (FR-026, FR-028).
# No external stylesheet: the page must open from disk with no network.
_BASE_CSS = """
*{box-sizing:border-box}
body{margin:0;padding:2rem;max-width:100%}
h1{font-size:1.3rem;margin:0 0 .3rem}
h2{font-size:1.05rem;margin:2rem 0 .5rem;font-weight:600}
.size,.prov{font-size:.85rem;line-height:1.7}
.warn{font-weight:700;letter-spacing:.03em;margin:.8rem 0}
.wrap{overflow-x:auto;max-width:100%}
table{border-collapse:collapse;font-size:.82rem;margin:0 0 .2rem;min-width:100%}
caption{text-align:left;font-weight:600;padding:.4rem 0;font-size:.95rem}
th,td{border:1px solid var(--line);padding:.28rem .5rem;white-space:nowrap}
th{position:sticky;top:0;background:var(--head);cursor:pointer;text-align:left}
th:hover{background:var(--headh)}
td.num{text-align:right;font-variant-numeric:tabular-nums}
td.lbl{text-align:left}
tbody tr:nth-child(even){background:var(--zebra)}
.src{font-size:.72rem;opacity:.75;margin:.15rem 0 1.2rem;font-family:monospace}
.note{font-size:.85rem;opacity:.85;margin:.3rem 0 1.2rem}
"""

_THEMES = {
    "internal": ("--line:#333a48;--head:#1e222c;--headh:#272c38;--zebra:#191c24;"
                 "background:#14161d;color:#e6e6e6;"
                 "font:14px/1.5 ui-monospace,Menlo,Consolas,monospace"),
    "public": ("--line:#d6d6d6;--head:#f2f2f0;--headh:#e8e8e6;--zebra:#fafaf9;"
               "background:#fff;color:#1a1a1a;font:15px/1.6 Georgia,serif"),
}

# ponytail: a click handler over table.rows, not a sorting library. Ceiling: it
# sorts one table by one column and forgets; that is the whole requirement.
_SORT_JS = """
document.querySelectorAll('table').forEach(function(t){
  t.querySelectorAll('th').forEach(function(th,i){
    th.addEventListener('click',function(){
      var b=t.tBodies[0],rows=Array.prototype.slice.call(b.rows);
      var dir=th.dataset.d==='1'?-1:1;th.dataset.d=dir===1?'1':'';
      var num=rows.every(function(r){var v=(r.cells[i]||{}).textContent||'';
        return v.trim()===''||!isNaN(parseFloat(v.replace(/[^0-9.eE+-]/g,'')));});
      rows.sort(function(x,y){
        var a=(x.cells[i]||{}).textContent||'',c=(y.cells[i]||{}).textContent||'';
        if(num){var f=parseFloat(a.replace(/[^0-9.eE+-]/g,''))||0,
                    g=parseFloat(c.replace(/[^0-9.eE+-]/g,''))||0;return (f-g)*dir;}
        return a.localeCompare(c)*dir;});
      rows.forEach(function(r){b.appendChild(r);});
    });
  });
});
"""


def _size_line(size: dict) -> str:
    """Contracts section 7. The total never appears alone (design section 2.4)."""
    return (f"prompts: {size['prompts']} &middot; attempts per prompt and competitor: "
            f"{size['repetitions']} &middot; per competitor: {size['per_competitor']} = "
            f"{size['prompts']} x {size['repetitions']} &middot; competitors: "
            f"{size['competitors']} &middot; attempts in total: {size['total']}")


def _source_line_for(report: dict, which: str) -> str:
    """Contracts section 6: the existing string, unchanged in shape, plus the
    wall-clock share where some attempts carry none."""
    p = report["provenance"]
    arms = "+".join(report["arms"])
    if which == "comparisons":
        # Each comparison has its own denominator; adding them would invent a
        # sample size no figure was computed on (data-model section 2.3).
        pairs = ", ".join(f"{c['arm']} n={c['pairs']}" for c in report["comparisons"])
        return (f"src: {p['suite']} - v{p['suite_version']} - pairs per competitor: "
                f"{pairs} - vs {report['baseline']} - {report['run_id']}"
                f"{report['source_suffix']}")
    if which == "failures":
        # A listing, not a statistic: it has a length, not a denominator.
        return (f"src: {p['suite']} - v{p['suite_version']} - "
                f"{len(report['failures'])} rows - {arms} - {report['run_id']}"
                f"{report['source_suffix']}")
    n = {"metrics": report["size"]["total"],
         "matrix": report["size"]["total"]}[which]
    line = (f"src: {p['suite']} - v{p['suite_version']} - n={n} - {arms} - "
            f"{report['run_id']}{report['source_suffix']}")
    if which == "metrics":
        with_wc = sum(m["wall_clock"]["n_with"] for m in report["metrics"])
        total = sum(m["wall_clock"]["n_total"] for m in report["metrics"])
        if with_wc < total:
            line += f" - wall-clock from {with_wc} of {total} attempts"
    return line


def _phase_names(metrics: list[dict]) -> list[str]:
    """The phases any competitor on this page carries, `authoring` and
    `execution` first because that is the order they happen in.

    # ponytail: read off the rows, so a phase feature 002 or 004 adds appears
    # with no change here. Ceiling: a typo in a phase name becomes a column.
    """
    names = {name for m in metrics for name in m["phases"]}
    known = [n for n in ("authoring", "execution") if n in names]
    return known + sorted(names - set(known))


def _metrics_table(report: dict, source_line: str | None = None) -> str:
    """Contracts section 1, plus the Monarch-only columns of its second table.

    Those columns exist only when a competitor on this page actually has phases
    or a Monarch counter; a page without them never shows the headers, because
    an empty column is worse than no column (FR-016).

    The summary page renders the same table per round, passing its own source
    line, so a number cannot differ between the two pages.
    """
    if source_line is None:
        source_line = _source_line_for(report, "metrics")
    metrics = report["metrics"]
    dollars = report["audience"] == "internal"
    phases = _phase_names(metrics)
    show_models = any(m["cost_per_model"] for m in metrics)
    show_questions = any(m["phases"] or m["questions_asked"] for m in metrics)
    headers = ["competitor", "attempts", "passed", "strict pass", "of",
               "pass over reps", "infra", "infra rate", "agent errors", "timeouts"]
    headers += (["cost total", "cost / attempt", "cost / passed"] if dollars
                else ["cost vs baseline"])
    headers += ["prompt tok", "cached tok", "cache write", "output tok", "cache hit",
                "wall-clock mean", "wall-clock median", "turns", "tool calls"]
    for name in phases:
        headers.append(f"{name} wall-clock")
        if dollars:
            headers.append(f"{name} cost")
    if show_models and dollars:
        headers.append("cost / model")
    if show_questions:
        headers += ["questions asked", "declined to build"]
    base_cost = next((m["cost_total"] for m in metrics if m["arm"] == report["baseline"]),
                     None)
    rows = []
    for m in metrics:
        row = [m["arm"], _fmt(m["attempts"]), _fmt(m["passed"]),
               _fmt(m["strict_pass"], "rate"),
               # the denominator beside the rate: the attempts it divides by,
               # infrastructure ones excluded (contracts section 1)
               _fmt(m["strict_pass_denominator"]),
               _fmt(m["pass_over_repetitions"], "rate"),
               _fmt(m["infra"]), _fmt(m["infra_rate"], "rate"),
               _fmt(m["agent_errors"]), _fmt(m["timeouts"])]
        if dollars:
            row += [_fmt(m["cost_total"], "money"), _fmt(m["cost_per_attempt"], "money"),
                    _fmt(m["cost_per_passed"], "money")]
        else:
            # FR-024: a non-internal audience sees ratios, never dollars.
            ratio = m["cost_total"] / base_cost if base_cost else None
            row += [_fmt(ratio, "ratio")]
        t = m["tokens"]
        row += [_fmt(t["prompt"]), _fmt(t["cached"]), _fmt(t["cache_write"]),
                _fmt(t["output"]), _fmt(m["cache_hit_rate"], "rate"),
                _fmt(m["wall_clock"]["mean"], "seconds"),
                _fmt(m["wall_clock"]["median"], "seconds"),
                _fmt(m["turns"]), _fmt(m["tool_calls"])]
        for name in phases:
            # A competitor without this phase shows n/a, never 0: a zero would
            # read as "free", not as "did not happen" (FR-016).
            phase = m["phases"].get(name)
            row.append(_fmt(phase["wall_clock_s"] if phase else None, "seconds"))
            if dollars:
                row.append(_fmt(phase["cost_usd"] if phase else None, "money"))
        if show_models and dollars:
            row.append(" - ".join(f"{name} {_fmt(cost, 'money')}"
                                  for name, cost in sorted(m["cost_per_model"].items()))
                       or "n/a")
        if show_questions:
            row += [_fmt(m["questions_asked"]), _fmt(m["declined_to_build"])]
        rows.append(row)
    return _table(headers, rows, source_line, "Competitors")


def _comparison_table(report: dict) -> str:
    """Contracts section 2. One competitor means nothing to compare: the page
    says so in a line rather than rendering an empty table."""
    if not report["comparisons"]:
        return ('<p class="note">Only one competitor ran this round, so there is '
                "no paired comparison to make.</p>")
    dollars = report["audience"] == "internal"
    headers = ["competitor", "vs baseline", "strict pass diff (pp)", "pass rate ratio"]
    if dollars:
        headers.append("cost / passed ratio")
    headers += ["W", "L", "both", "neither", "pairs", "infra-dropped", "McNemar p",
                "verdict"]
    rows = []
    for c in report["comparisons"]:
        diff = c["strict_pass_diff_pp"]
        row = [c["arm"], c["baseline"],
               f"{diff:+.1f}" if diff is not None else "n/a",
               _fmt(c["pass_rate_ratio"], "ratio")]
        if dollars:
            row.append(_fmt(c["cost_per_passed_ratio"], "ratio"))
        row += [_fmt(c["wins"]), _fmt(c["losses"]), _fmt(c["both"]), _fmt(c["neither"]),
                _fmt(c["pairs"]), _fmt(c["dropped_infra"]),
                f"{c['mcnemar']['p']:.3f}", c["verdict"]]
        rows.append(row)
    return _table(headers, rows, _source_line_for(report, "comparisons"),
                  "Comparisons against the baseline", numeric_from=2)


def _matrix_tables(report: dict) -> str:
    """Contracts section 3: the matrix, then the details table repeating every
    reason, so nothing is available only on hover (FR-008)."""
    m = report["matrix"]
    lead = ["task"] + (["domain"] if m["has_domain"] else []) + \
           (["tier"] if m["has_tier"] else [])
    headers = lead + list(m["arms"])
    rows, details = [], []
    for r in m["rows"]:
        row = [r["task_id"]]
        if m["has_domain"]:
            row.append(r["domain"] or "")
        if m["has_tier"]:
            row.append(r["tier"] or "")
        for arm in m["arms"]:
            cell = r["cells"].get(arm)
            if cell is None:
                row.append("n/a")
                continue
            text = f"{cell['passed']}/{cell['attempted']}"
            if cell["infra"]:
                text += f" (infra {cell['infra']})"
            # The reason rides on the cell as its title AND is repeated below,
            # so nothing is available only on hover (FR-008).
            reason = cell["category"]
            if cell["detail"]:
                reason += f": {cell['detail']}"
            row.append((text, reason) if cell["category"] != "passed" else text)
            if cell["category"] != "passed":
                details.append([r["task_id"], arm, _fmt(cell["trial"]),
                                cell["category"], cell["detail"] or ""])
        rows.append(row)
    matrix = _table(headers, rows, _source_line_for(report, "matrix"), "Task matrix",
                    numeric_from=len(lead))
    detail_tbl = (_table(["task", "competitor", "repetition", "reason", "detail"],
                         details, "", "Task matrix, the reason behind every cell",
                         numeric_from=2)
                  if details else
                  '<p class="note">Every competitor passed every task.</p>')
    return matrix + detail_tbl


def _failures_table(report: dict) -> str:
    """Contracts section 4. `no attempt failed` replaces the table when none did."""
    failures = report["failures"]
    if not failures:
        return '<p class="note">no attempt failed</p>'
    rows = []
    for f in failures:
        error = f["error"] or ""
        # The cell shows the first 200 characters; the whole thing stays in the
        # title, so a long stack trace is abbreviated rather than lost.
        cell = (error[:200] + "...", error) if len(error) > 200 else error
        rows.append([f["task_id"], f["arm"], _fmt(f["trial"]), f["termination"] or "",
                     cell, ", ".join(f["unexpected_change_paths"])])
    return _table(["task", "competitor", "repetition", "termination", "error",
                   "unexpected changes"], rows, _source_line_for(report, "failures"),
                  "Failures", numeric_from=2)


def _provenance_block(report: dict) -> str:
    """Contracts section 5."""
    p = report["provenance"]
    items = [("configuration hash", p["config_hash"]), ("plan", p["plan"]),
             ("product", p["product"]), ("test mode", p["mode"]),
             ("price tables", ", ".join(p["price_tables"]) or None),
             ("task set", f"{p['suite']} (v{p['suite_version']})"),
             ("task hashes", ", ".join(p["task_hashes"]) or None),
             ("run started", p["started"]), ("run finished", p["finished"]),
             ("stop reason", p["stop_reason"]), ("audience", p["audience"])]
    if p["missing_cost"]:
        items.append(("missing cost", f"{p['missing_cost']['missing']} of "
                                      f"{p['missing_cost']['total']} Monarch attempts"))
    withheld = p["withheld"]
    if withheld:
        # A non-internal audience is given the count only: even the existence of
        # a gated competitor is internal (FR-023).
        items.append(("competitors withheld",
                      ", ".join(withheld) if isinstance(withheld, list)
                      else f"{withheld} withheld"))
    body = "<br>".join(f"{_esc(k)}: <b>{_esc(v)}</b>" for k, v in items if v is not None)
    return f'<h2>Provenance</h2><p class="prov">{body}</p>'


def render_page(report: dict[str, Any], sortable: bool = True) -> str:
    """The per-round page. Takes the dictionary `build_report` returns and
    nothing else - see this module's docstring for why."""
    theme = _THEMES["internal" if report["audience"] == "internal" else "public"]
    warn = ""
    if report["audience"] == "internal" and any(a.startswith("monarch-lab")
                                                for a in report["arms"]):
        warn = '<p class="warn">INTERNAL - CONTAINS LAB ARMS - DO NOT EXPORT</p>'
    script = f"<script>{_SORT_JS}</script>" if sortable else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>WorkflowBench {_esc(report['run_id'])}</title>"
        f"<style>:root{{{theme}}}{_BASE_CSS}</style></head><body>"
        f"<h1>WorkflowBench round {_esc(report['run_id'])}</h1>"
        f'<p class="size">{_size_line(report["size"])}</p>'
        f"{warn}"
        f'<div class="wrap">{_metrics_table(report)}</div>'
        f'<div class="wrap">{_comparison_table(report)}</div>'
        f'<div class="wrap">{_matrix_tables(report)}</div>'
        f'<div class="wrap">{_failures_table(report)}</div>'
        f"{_provenance_block(report)}"
        f"{script}</body></html>")


def _round_source_line(rnd: dict) -> str:
    """One round's source line on the summary page, with its stop reason where
    it has one: a round cut short by the cost ceiling is a real partial result,
    and labelling it beats hiding it (research R9)."""
    p = rnd["source"]
    line = (f"src: {p['suite']} - v{p['suite_version']} - n={rnd['size']['total']} - "
            f"{rnd['run_id']}{rnd['source_suffix']}")
    if rnd.get("stop_reason"):
        line += f" - stopped: {rnd['stop_reason']}"
    return line


def _aggregate_table(summary: dict) -> str:
    """One row per competitor: the mean of the rounds it ran, how many those
    were, and a column per tier where the rounds carry one.

    The mean is a mean of per-round rates. It is never a recomputation over
    pooled attempts, because rounds with different task sets have different
    difficulty and pooling them would weight the biggest round highest.
    """
    tiers = sorted({t for e in summary["aggregate"] for t in e.get("per_tier", {})})
    headers = ["competitor", "mean strict pass", "rounds"] + \
              [f"tier {t}" for t in tiers]
    rows = []
    for e in summary["aggregate"]:
        row = [e["arm"], _fmt({"mean": e["mean_strict_pass"], "sem": e["sem"]}, "rate"),
               _fmt(e["n_rounds"])]
        row += [_fmt(e.get("per_tier", {}).get(t), "rate") for t in tiers]
        rows.append(row)
    return _table(headers, rows, "", "Mean over the rounds each competitor ran")


def _stratification_table(summary: dict) -> str:
    """The random draw beside the mean of the tier rounds (FR-020). Present only
    when a random-draw round is on the page."""
    if not summary.get("stratification"):
        return ""
    rows = [[e["arm"], _fmt(e["random"], "rate"), _fmt(e["tier_mean"], "rate"),
             f"{e['diff_pp']:+.1f}" if e["diff_pp"] is not None else "n/a"]
            for e in summary["stratification"]]
    return _table(["competitor", "random draw", "mean of the tier rounds",
                   "difference (pp)"], rows,
                  "", "Stratification check: does the tier mix match a random draw?")


def render_summary_page(summary: dict[str, Any], sortable: bool = True) -> str:
    """Two to six rounds on one page (contracts section 9).

    It reuses the per-round metrics table, so a number here and a number on the
    round's own page cannot disagree. No paired figure, no McNemar and no ratio
    spanning rounds is rendered - the dictionary has no field for one.
    """
    theme = _THEMES["internal" if summary["audience"] == "internal" else "public"]
    head = []
    for rnd in summary["rounds"]:
        head.append(f"<b>{_esc(rnd['run_id'])}</b> - plan {_esc(rnd['plan'])} - "
                    f"{_esc(rnd['suite'])}<br>{_size_line(rnd['size'])}")
    warn = ""
    if summary["audience"] == "internal" and any(
            a.startswith("monarch-lab") for a in summary["arms"]):
        warn = '<p class="warn">INTERNAL - CONTAINS LAB ARMS - DO NOT EXPORT</p>'

    body = []
    for rnd in summary["rounds"]:
        # each round's own metrics table, with its own source line
        one = {"metrics": rnd["metrics"], "audience": summary["audience"],
               "baseline": rnd["baseline"]}
        table = _metrics_table(one, source_line="")
        body.append(f'<h2>{_esc(rnd["run_id"])} - {_esc(rnd["plan"])}</h2>'
                    f'<div class="wrap">{table}'
                    f'<p class="src">{_esc(_round_source_line(rnd))}</p></div>')

    script = f"<script>{_SORT_JS}</script>" if sortable else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>WorkflowBench summary</title>"
        f"<style>:root{{{theme}}}{_BASE_CSS}</style></head><body>"
        f"<h1>WorkflowBench: {len(summary['rounds'])} rounds</h1>"
        f'<p class="size">{"<br>".join(head)}</p>'
        f"{warn}"
        + "".join(body) +
        f'<h2>Aggregate</h2><div class="wrap">{_aggregate_table(summary)}</div>'
        f'<div class="wrap">{_stratification_table(summary)}</div>'
        f'<p class="note">{_esc(summary["statement"])}</p>'
        f"{script}</body></html>")
