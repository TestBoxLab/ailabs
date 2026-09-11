"""The HTML pages: one per round, and the summary over several.

This module renders a dictionary and nothing else. It never imports `Store` and
never opens the database: every statistic is computed inside `build_report`, and
a renderer that could re-query the store would be four new chances to put a
number on the page that no figure stands behind (plan design note 1, research
R7). A test asserts this module's imports.

# ponytail: one _table() helper and f-strings, not a template engine. Ceiling:
# if the page ever needs conditional layout beyond a table, revisit.
"""
from __future__ import annotations

import html as _html
import json
from pathlib import Path
from typing import Any

from wb_report.metrics import (NOT_APPLICABLE_REASON, PHASE_WORDS, is_monarch,
                               monarch_outcomes)


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


def _na(metric: dict) -> str | None:
    """The reason to show `n/a` for this competitor everywhere, or `None`.

    The scripted answer key on a task set it cannot act on has no result to
    report; a rate of 0% would read as "it tried and failed" (contract section
    1a). One helper, so no table or chart can forget the rule.
    """
    return NOT_APPLICABLE_REASON if metric.get("not_applicable") else None


def _cells(metric: dict, values: list[Any]) -> list[Any]:
    """A metric row's value cells, replaced by `n/a` with the reason on hover
    where the competitor is not applicable."""
    reason = _na(metric)
    return [("n/a", reason) for _ in values] if reason else values


def _series(metrics: list[dict], value) -> list[tuple[str, Any, Any]]:
    """A chart series where a not-applicable competitor contributes `None`,
    which every chart already draws as the text `n/a`."""
    return [(m["arm"], None, None) if _na(m) else value(m) for m in metrics]


def _table(headers: list[str], rows: list[list[str]], source_line: str = "",
           title: str = "", numeric_from: int = 1) -> str:
    """One table, in the reference's `.tablewrap > table` shell.

    A cell is a string, or a `(text, title)` pair when the visible text is an
    abbreviation of something longer. Every cell and every title is escaped
    here, so a value from a row - an error string, a change path - cannot reach
    the page as markup no matter which caller built it. `_fmt` therefore returns
    plain text and never entities.

    A header that names a competitor is shortened by `_short` and keeps the full
    name in its `title`; the source line under the table names them in full, so
    nothing is lost to the abbreviation (the page must fit a 1366px laptop).

    `numeric_from` is the first column index rendered right-aligned.
    """
    head = "".join(
        f'<th title="{_esc(h)}">{_esc(_short(h))}</th>' for h in headers)

    def cell(i: int, value: Any) -> str:
        text, title_attr = value if isinstance(value, tuple) else (value, None)
        attr = f' title="{_esc(title_attr)}"' if title_attr else ""
        klass = ' class="num"' if i >= numeric_from else ""
        return f"<td{klass}{attr}>{_esc(text)}</td>"

    body = "".join("<tr>" + "".join(cell(i, c) for i, c in enumerate(row)) + "</tr>"
                   for row in rows)
    # The source line rides on the caption as a tooltip; the visible list of
    # sources lives in the Provenance section (rule 8 of the methodology).
    src_attr = f' title="{_esc(source_line)}"' if source_line else ""
    caption = f"<caption>{_esc(title)}</caption>" if title else ""
    return (f'<div class="tablewrap"><table{src_attr}>{caption}<tr>{head}</tr>'
            f"{body}</table></div>")


# Monarch's design system, copied from local-docs/monarch-arquitetura.html:
# the same tokens, the same font links, the same class names and the same
# light/dark handling, so a report reads as a sibling of that document. The
# additions here - metric cards, bar rows, task rows - use those tokens only.
#
# The sidebar is 200px and the tables are 12.5px so the widest table fits a
# 1366px laptop without horizontal scrolling.
CROWN = "&#9819;"

# The test mode in the words Carlos uses. A round with no recorded mode says
# nothing about one rather than guessing.
MODE_WORDS = {
    "create-run": "create + run: Monarch builds the workflow (builder) and runs it (dispatch)",
    "run-only": "run-only: dispatch only, on a workflow known to be correct",
    "full-flow": "full flow: discovery, then the builder, then dispatch",
}

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,600;12..96,700'
         '&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600'
         '&family=JetBrains+Mono:wght@400;500;600&display=swap">')

CSS = """
:root {
  --paper: #FAF9F5;
  --surface: #FFFFFF;
  --ink: #23252D;
  --muted: #6A6D78;
  --line: #E4E1D8;
  --line-soft: #EEEBE2;
  --accent: #A66A1E;
  --accent-ink: #7C4F13;
  --accent-wash: #F6EEDF;
  --blue: #33628C;
  --blue-wash: #E9F0F6;
  --good: #2F7D4F;
  --good-wash: #E7F2EB;
  --crit: #B3423A;
  --crit-wash: #F7E9E8;
  --code-bg: #F2EFE7;
  --diagram-bg: #FFFFFF;
  --sidebar-bg: #F4F2EB;
  --display: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --body: "Source Serif 4", Georgia, serif;
  --mono: "JetBrains Mono", Consolas, monospace;
}
:root:not([data-theme="light"]) { color-scheme: light dark; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #15171E; --surface: #1D2029; --ink: #E9E7DF; --muted: #9A9DA8;
    --line: #2E3140; --line-soft: #262935; --accent: #D9A441;
    --accent-ink: #E4B865; --accent-wash: #2A2417; --blue: #6D9EC9;
    --blue-wash: #1B2733; --good: #6BBF8F; --good-wash: #182B20;
    --crit: #E08A83; --crit-wash: #331E1C; --code-bg: #232633;
    --diagram-bg: #1D2029; --sidebar-bg: #191B23;
  }
}
:root[data-theme="dark"] {
  --paper: #15171E; --surface: #1D2029; --ink: #E9E7DF; --muted: #9A9DA8;
  --line: #2E3140; --line-soft: #262935; --accent: #D9A441;
  --accent-ink: #E4B865; --accent-wash: #2A2417; --blue: #6D9EC9;
  --blue-wash: #1B2733; --good: #6BBF8F; --good-wash: #182B20;
  --crit: #E08A83; --crit-wash: #331E1C; --code-bg: #232633;
  --diagram-bg: #1D2029; --sidebar-bg: #191B23;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: var(--body); font-size: 16.5px; line-height: 1.65;
}
.layout { display: flex; min-height: 100vh; }

nav.toc {
  width: 200px; flex: 0 0 200px; background: var(--sidebar-bg);
  border-right: 1px solid var(--line); padding: 28px 20px 40px;
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
  font-family: var(--mono);
}
nav.toc .brand {
  font-family: var(--display); font-weight: 700; font-size: 20px;
  letter-spacing: -0.01em; margin-bottom: 2px;
}
nav.toc .brand .crown { color: var(--accent); }
nav.toc .brand-sub {
  font-size: 11px; color: var(--muted); letter-spacing: 0.08em;
  text-transform: uppercase; margin-bottom: 22px;
}
nav.toc a {
  display: block; color: var(--muted); text-decoration: none; font-size: 12.5px;
  line-height: 1.45; padding: 5px 8px; border-radius: 6px;
  border-left: 2px solid transparent;
}
nav.toc a:hover { color: var(--ink); background: var(--line-soft); }
nav.toc a.active { color: var(--accent-ink); border-left-color: var(--accent); background: var(--accent-wash); }
nav.toc a .n { color: var(--accent); font-weight: 600; margin-right: 6px; }
nav.toc a.sub { padding-left: 30px; font-size: 11.5px; }
nav.toc .focus-tag {
  display: inline-block; font-size: 9px; letter-spacing: 0.06em;
  color: var(--accent-ink); background: var(--accent-wash);
  border: 1px solid var(--accent); border-radius: 999px; padding: 0 6px;
  margin-left: 6px; vertical-align: 1px;
}

main { flex: 1; min-width: 0; padding: 0 28px 120px; }
.content { max-width: 100%; margin: 0; }
.prose { max-width: 76ch; }

header.hero { padding: 72px 0 48px; border-bottom: 1px solid var(--line); margin-bottom: 8px; }
header.hero .eyebrow {
  font-family: var(--mono); font-size: 12px; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--accent-ink); margin-bottom: 14px;
}
header.hero h1 {
  font-family: var(--display); font-weight: 700; font-size: clamp(40px, 6vw, 64px);
  line-height: 1.02; letter-spacing: -0.02em; margin: 0 0 18px; text-wrap: balance;
}
header.hero h1 .crown { color: var(--accent); }
header.hero .lede { font-size: 19px; line-height: 1.6; max-width: 62ch; color: var(--ink); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 26px; }
.chip {
  font-family: var(--mono); font-size: 11.5px; padding: 4px 12px;
  border: 1px solid var(--line); border-radius: 999px; color: var(--muted);
  background: var(--surface);
}
.chip strong { color: var(--ink); font-weight: 600; }
.chip.hot { border-color: var(--accent); color: var(--accent-ink); background: var(--accent-wash); }

section.part { padding-top: 56px; }
.part-eyebrow {
  font-family: var(--mono); font-size: 11.5px; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--accent-ink); display: flex;
  align-items: center; gap: 12px; margin-bottom: 10px;
}
.part-eyebrow::after { content: ""; height: 1px; flex: 1; background: var(--line); }
h2 {
  font-family: var(--display); font-weight: 700; font-size: 34px;
  letter-spacing: -0.015em; line-height: 1.1; margin: 0 0 6px; text-wrap: balance;
}
.h2-sub { color: var(--muted); font-size: 16px; margin: 0 0 28px; max-width: 70ch; }
h3 {
  font-family: var(--display); font-weight: 600; font-size: 22px;
  letter-spacing: -0.01em; margin: 44px 0 10px;
}
h4 { font-family: var(--display); font-weight: 600; font-size: 16.5px; margin: 30px 0 8px; }
p { margin: 0 0 14px; }
a { color: var(--blue); }
strong { font-weight: 600; }
ul, ol { margin: 0 0 16px; padding-left: 22px; }
li { margin-bottom: 6px; }

code { font-family: var(--mono); font-size: 0.82em; background: var(--code-bg); border-radius: 4px; padding: 1.5px 5px; }
pre.block {
  font-family: var(--mono); font-size: 12.5px; line-height: 1.55;
  background: var(--code-bg); border: 1px solid var(--line); border-radius: 10px;
  padding: 16px 18px; overflow-x: auto; margin: 0 0 16px;
}
pre.block code { background: none; padding: 0; }

.tablewrap { overflow-x: auto; margin: 0 0 8px; border: 1px solid var(--line); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; background: var(--surface); table-layout: auto; }
th {
  font-family: var(--mono); font-size: 10.5px; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--muted); text-align: left;
  padding: 8px 9px; border-bottom: 1px solid var(--line);
  background: var(--sidebar-bg);
  /* header cells wrap: a long competitor name must not set the column width */
  white-space: normal; word-break: break-word; max-width: 110px;
}
td { padding: 7px 9px; border-bottom: 1px solid var(--line-soft); vertical-align: top; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
td code { white-space: nowrap; }
td.num { text-align: right; }

figure.diagram { margin: 22px 0 26px; border: 1px solid var(--line); border-radius: 12px; background: var(--diagram-bg); overflow: hidden; }
figure.diagram .dg-head {
  display: flex; align-items: baseline; gap: 12px; padding: 12px 18px;
  border-bottom: 1px solid var(--line-soft); background: var(--sidebar-bg);
}
figure.diagram .dg-head .kind {
  font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--accent-ink); background: var(--accent-wash);
  border: 1px solid var(--accent); border-radius: 4px; padding: 1px 7px;
}
figure.diagram .dg-head .t { font-family: var(--display); font-weight: 600; font-size: 14.5px; }
figure.diagram .dg-body { padding: 14px; overflow-x: auto; }
svg.chart { display: block; max-width: 100%; height: auto; margin: 6px 0 4px; }
svg.chart text { font-family: var(--mono); font-size: 11.5px; fill: var(--ink); }
svg.chart .cl { fill: var(--muted); }
svg.chart .cb { fill: var(--accent); }
svg.chart .ce { fill: var(--accent); opacity: 0.28; }
figure.diagram figcaption { font-size: 13px; color: var(--muted); padding: 10px 18px 14px; border-top: 1px solid var(--line-soft); }

.prov, .source-grading { overflow-wrap: anywhere; }
.source-grading { margin-block: 1rem; }
.source-grading summary { cursor: pointer; }
.source-grading summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }

.callout {
  border: 1px solid var(--line); border-left: 3px solid var(--blue);
  background: var(--blue-wash); border-radius: 8px; padding: 14px 18px;
  margin: 0 0 18px; font-size: 14.5px; max-width: 82ch;
}
.callout.warn { border-left-color: var(--accent); background: var(--accent-wash); }
.callout.crit { border-left-color: var(--crit); background: var(--crit-wash); }
.callout.good { border-left-color: var(--good); background: var(--good-wash); }
.callout .label {
  font-family: var(--mono); font-size: 10.5px; letter-spacing: 0.1em;
  text-transform: uppercase; display: block; margin-bottom: 4px; color: var(--muted);
}

.badge { font-family: var(--mono); font-size: 10.5px; letter-spacing: 0.03em; border-radius: 4px; padding: 1px 7px; white-space: nowrap; }
.badge.good { color: var(--good); background: var(--good-wash); border: 1px solid var(--good); }
.badge.warn { color: var(--accent-ink); background: var(--accent-wash); border: 1px solid var(--accent); }
.badge.crit { color: var(--crit); background: var(--crit-wash); border: 1px solid var(--crit); }
.badge.info { color: var(--blue); background: var(--blue-wash); border: 1px solid var(--blue); }

/* --- report additions, from the same tokens --- */
.src {
  font-family: var(--mono); font-size: 11px; color: var(--muted);
  margin: 0 0 22px; word-break: break-word;
}
.cards { display: flex; flex-wrap: wrap; gap: 14px; margin: 0 0 26px; }
.mcard {
  flex: 1 1 260px; border: 1px solid var(--line); border-radius: 12px;
  background: var(--surface); padding: 16px 18px 18px;
}
.mcard .lab {
  font-family: var(--mono); font-size: 10.5px; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 12px;
}
.mcard .row { display: flex; justify-content: space-between; align-items: baseline; gap: 14px; }
.mcard .big { font-family: var(--display); font-size: 30px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.05; }
.mcard .who { font-family: var(--mono); font-size: 10.5px; color: var(--muted); margin-top: 3px; }
.mcard .big.good { color: var(--good); }
.mcard .big.crit { color: var(--crit); }
.mcard .why { font-size: 12.5px; color: var(--muted); margin: 10px 0 0; }

.bars { margin: 0 0 8px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); padding: 14px 16px; }
.brow { display: flex; align-items: center; gap: 12px; margin: 3px 0; }
.brow .nm { flex: 0 0 180px; font-family: var(--mono); font-size: 11.5px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.brow .tr { flex: 1 1 auto; height: 18px; background: var(--line-soft); border-radius: 3px; }
.brow .fl { height: 18px; border-radius: 3px; background: var(--blue); }
.brow .fl.mon { background: var(--accent); }
.brow .fl.good { background: var(--good); }
.brow .fl.crit { background: var(--crit); }
.brow .vl { flex: 0 0 118px; font-family: var(--mono); font-size: 11.5px; text-align: right; font-variant-numeric: tabular-nums; }
.brow .vl.dim { color: var(--muted); }
.brow .vl.crit { color: var(--crit); }

.taskrows { margin: 0 0 8px; }
.taskrow {
  border: 1px solid var(--line); border-radius: 12px; background: var(--surface);
  padding: 15px 18px 16px; margin: 0 0 10px;
  display: flex; align-items: flex-start; gap: 18px; flex-wrap: wrap;
}
.taskrow .body { flex: 1 1 420px; min-width: 0; }
.taskrow .req { font-size: 15px; margin: 0 0 8px; }
.taskrow .verdict { flex: 0 0 auto; }
.taskrow .exp {
  font-family: var(--mono); font-size: 11.5px; color: var(--muted);
  border-left: 2px solid var(--line); padding-left: 10px; margin: 0 0 12px;
}
.pills { display: flex; flex-wrap: wrap; gap: 5px; }
.strip { display: flex; flex-wrap: wrap; gap: 14px; margin: 0 0 8px; }
.strip .half { flex: 1 1 380px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); padding: 16px 18px; }
.strip .half .lab { font-family: var(--mono); font-size: 10.5px; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px; }
.strip .half p { margin: 0; font-size: 14.5px; }
footer.prov {
  margin-top: 72px; padding-top: 18px; border-top: 1px solid var(--line);
  font-family: var(--mono); font-size: 11.5px; color: var(--muted); line-height: 1.9;
}

@media (max-width: 1000px) {
  nav.toc { display: none; }
  main { padding: 0 20px 80px; }
}
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
"""

SPY_JS = """
(function () {
  var links = document.querySelectorAll('nav.toc a');
  var map = {};
  links.forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
  var obs = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting && map[e.target.id]) {
        links.forEach(function (a) { a.classList.remove('active'); });
        map[e.target.id].classList.add('active');
      }
    });
  }, { rootMargin: '-10% 0px -70% 0px' });
  document.querySelectorAll('section.part[id]').forEach(function (s) { obs.observe(s); });
})();
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
    if which == "monarch":
        n = sum(len(v) for v in (report.get("monarch_attempts") or {}).values())
        return (f"src: {p['suite']} - v{p['suite_version']} - {n} attempts - "
                f"phase keys authoring/execution - {report['run_id']}"
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


def _comparison_table(report: dict) -> str:
    """Contracts section 2. One competitor means nothing to compare: the page
    says so in a line rather than rendering an empty table."""
    if not report["comparisons"]:
        return ('<p class="note">Only one competitor ran this round, so there is '
                "no paired comparison to make.</p>")
    headers = ["competitor", "vs baseline", "strict pass diff (pp)", "pass rate ratio",
               "cost / passed ratio",
               "W", "L", "both", "neither", "pairs", "infra-dropped", "ungraded-dropped",
               "McNemar p", "verdict"]
    rows = []
    for c in report["comparisons"]:
        diff = c["strict_pass_diff_pp"]
        if c.get("skipped"):
            # one side had nothing to compare: every figure would be an artefact
            # of its blank rows, so the row says so and shows none of them
            rows.append([c["arm"], c["baseline"]]
                        + [("n/a", c["skipped"])] * (len(headers) - 3)
                        + [c["skipped"]])
            continue
        row = [c["arm"], c["baseline"],
               f"{diff:+.1f}" if diff is not None else "n/a",
               _fmt(c["pass_rate_ratio"], "ratio"),
               _fmt(c["cost_per_passed_ratio"], "ratio")]
        row += [_fmt(c["wins"]), _fmt(c["losses"]), _fmt(c["both"]), _fmt(c["neither"]),
                _fmt(c["pairs"]), _fmt(c["dropped_infra"]), _fmt(c.get("dropped_ungraded", 0)),
                f"{c['mcnemar']['p']:.3f}", c["verdict"]]
        rows.append(row)
    return _table(headers, rows, _source_line_for(report, "comparisons"),
                  "Comparisons against the baseline", numeric_from=2)


def _matrix_tables(report: dict) -> str:
    """Contracts section 3: the matrix, then the details table repeating every
    reason, so nothing is available only on hover (FR-008)."""
    m = report["matrix"]
    na_arms = {x["arm"] for x in report["metrics"] if _na(x)}
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
            if arm in na_arms:
                # the answer key could not act on this task set: no result
                row.append(("n/a", NOT_APPLICABLE_REASON))
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
    # task+repetition -> the attempt's last front-door error, for the Monarch
    # rows: "expected 200, got 404" says nothing about which request got it.
    last_error = {(a["task_id"], a["trial"], arm): a.get("front_door_last_error")
                  for arm, attempts in (report.get("monarch_attempts") or {}).items()
                  for a in attempts}
    rows = []
    for f in failures:
        error = f["error"] or ""
        fd = last_error.get((f["task_id"], f["trial"], f["arm"]))
        if fd:
            error += f" · last front-door error: {fd}"
        # The cell shows the first 200 characters; the whole thing stays in the
        # title, so a long stack trace is abbreviated rather than lost.
        cell = (error[:200] + "...", error) if len(error) > 200 else error
        rows.append([f["task_id"], f["arm"], _fmt(f["trial"]), f["termination"] or "",
                     cell, ", ".join(f["unexpected_change_paths"])])
    return _table(["task", "competitor", "repetition", "termination", "error",
                   "unexpected changes"], rows, _source_line_for(report, "failures"),
                  "Failures", numeric_from=2)


def _provenance_body(report: dict) -> str:
    """Contracts section 5."""
    p = report["provenance"]
    items = [("configuration hash", p["config_hash"]), ("plan", p["plan"]),
             ("product", p["product"]), ("test mode", p["mode"]),
             ("price tables", ", ".join(p["price_tables"]) or None),
             ("task set", f"{p['suite']} (v{p['suite_version']})"),
             ("task hashes", ", ".join(p["task_hashes"]) or None),
             ("run started", p["started"]), ("run finished", p["finished"]),
             ("stop reason", p["stop_reason"])]
    if p["missing_cost"]:
        items.append(("missing cost", f"{p['missing_cost']['missing']} of "
                                      f"{p['missing_cost']['total']} Monarch attempts"))
    body = "<br>".join(f"{_esc(k)}: <b>{_esc(v)}</b>" for k, v in items if v is not None)
    # Source lines stay in the markdown report and on each table's tooltip;
    # the page itself does not list them (Carlos, 4 Sep).
    return f'<p class="prov">{body}</p>'


_TECH_TOC = [("overview", "Overview"), ("success", "Success"), ("cost", "Cost"),
             ("time", "Time"), ("monarch-phases", "Monarch phases"),
             ("failures", "Failures"), ("provenance", "Provenance")]


def render_page(report: dict[str, Any]) -> str:
    """The per-round technical page, in Monarch's design system.

    Seven sections, in the order a reader asks the questions: what was compared,
    did it work, what did it cost, how long did it take, what did Monarch
    actually do, what went wrong, and where do these numbers come from. Each is
    built from the already-gated `arms` list; the renderer never reaches the
    store. The tables do not sort: they are short enough to read.
    """
    p = report["provenance"]
    has_monarch = bool(report.get("monarch_attempts"))
    toc = _toc_links([t for t in _TECH_TOC
                      if t[0] != "monarch-phases" or has_monarch])
    mode = MODE_WORDS.get(p.get("mode") or "")
    warn = ""
    hero = (f'<header class="hero"><div class="eyebrow">WorkflowBench &middot; '
            f'{_esc(p.get("plan") or "round")} &middot; '
            f'{_esc((p.get("started") or "")[:10])}</div>'
            f'<h1><span class="crown">{CROWN}</span> {_esc(report["run_id"])}</h1>'
            f'<p class="lede">{_esc(mode or "Every competitor received the same request.")} '
            f"The checker ran afterwards, from the stored snapshots.</p></header>")

    n = 5
    parts = [warn,
             _part("overview", "Part 01 - The round", "Overview",
                   "What was compared, how big the round was, and what it cost.",
                   _overview_section(report)),
             _part("success", "Part 02 - Result", "Success",
                   "How often each competitor produced the expected result and "
                   "changed nothing else.", _success_section(report)),
             _part("cost", "Part 03 - Spend", "Cost",
                   "What the round paid for, per competitor and per phase.",
                   _cost_section(report)),
             _part("time", "Part 04 - Duration", "Time",
                   "How long one attempt took, and how that splits between "
                   "builder and dispatch.", _time_section(report))]
    if has_monarch:
        parts.append(_part("monarch-phases", "Part 05 - Monarch", "Monarch phases",
                           "Each attempt in two halves: what the builder produced, "
                           "and what the engine did with it.",
                           _monarch_section(report)))
        n = 6
    parts.append(_part("failures", f"Part {n:02d} - What went wrong", "Failures",
                       "Every attempt that did not pass, with its reason.",
                       _failures_table(report) + _src(_source_line_for(report, "failures"))))
    parts.append(_part("provenance", f"Part {n + 1:02d} - Repeatability", "Provenance",
                       "What produced these numbers.", _provenance_body(report) + _grading_details(report)))
    return _shell(f"WorkflowBench {report['run_id']}", toc, hero, "".join(parts))


def _grading_details(report: dict) -> str:
    """Source verdicts stay beside the independently checked collateral result."""
    blocks = []
    for episode, item in report.get("grading_evidence", {}).items():
        if not item.get("details"):
            continue
        detail = item["details"]
        status = "ungraded" if detail.get("ungraded") else "passed" if item["passed"] else "failed"
        blocks.append(f'<details class="source-grading"><summary>{_esc(item["task_id"])} · {_esc(item["arm"])} · {status}</summary>'
                      f'<p>Completion: {_esc(item["termination"])}. Grading: {_esc(item["kind"])}.</p>'
                      f'<p class="source">Evidence: {_esc(item["uri"])}</p>'
                      f'<pre style="white-space:pre-wrap;overflow-wrap:anywhere">{_esc(json.dumps(detail, ensure_ascii=False, indent=2))}</pre></details>')
    return '<h3>Grading evidence</h3>' + ''.join(blocks) if blocks else ''


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


def render_summary_page(summary: dict[str, Any]) -> str:
    """Two to six rounds on one page, in the same design system.

    It reuses the per-round success, cost and time tables, so a number here and
    a number on a round's own page cannot disagree. No paired figure, no McNemar
    and no ratio spanning rounds is rendered - the dictionary has no field for
    one.
    """
    rounds = summary["rounds"]
    toc = _toc_links([(f"round-{i}", r["run_id"]) for i, r in enumerate(rounds, 1)]
                     + [("aggregate", "Aggregate")])
    warn = ""
    chips = "".join(
        f'<span class="chip"><strong>{_esc(r["run_id"])}</strong> {_esc(r["plan"])}</span>'
        for r in rounds)
    hero = (f'<header class="hero"><div class="eyebrow">WorkflowBench &middot; '
            f'{len(rounds)} rounds</div>'
            f'<h1><span class="crown">{CROWN}</span> Across {len(rounds)} rounds</h1>'
            f'<p class="lede">Each round keeps its own tables and its own source '
            f"line. The aggregate is a mean of per-round rates.</p>"
            f'<div class="chips">{chips}</div></header>')

    parts = [warn]
    for i, rnd in enumerate(rounds, 1):
        one = {"metrics": rnd["metrics"],
               "baseline": rnd["baseline"], "provenance": rnd["source"],
               "arms": [m["arm"] for m in rnd["metrics"]], "size": rnd["size"],
               "run_id": rnd["run_id"], "source_suffix": rnd["source_suffix"],
               "comparisons": []}
        body = (_success_table(one) + _cost_section_table(one)
                + _time_section_table(one))
        parts.append(_part(f"round-{i}", f"Round {i:02d}", rnd["run_id"],
                           f"Plan {rnd['plan']} on {rnd['suite']}.", body))
    parts.append(_part("aggregate", f"Part {len(rounds) + 1:02d} - Across rounds",
                       "Aggregate",
                       "The mean of per-round rates, over the rounds each "
                       "competitor ran. Paired figures are never pooled.",
                       _aggregate_table(summary) + _stratification_table(summary)
                       + f'<div class="callout"><span class="label">Method</span>'
                       f'{_esc(summary["statement"])}</div>'))
    return _shell("WorkflowBench summary", toc, hero, "".join(parts))


# -- Monarch's page shell -----------------------------------------------------

def _monarch_first(names: list[str]) -> list[str]:
    """Monarch first, then the rest in their existing order. Every table, chart,
    card and pill row on both pages uses this order."""
    return ([n for n in names if is_monarch(n)]
            + [n for n in names if not is_monarch(n)])


def _ordered_metrics(report: dict) -> list[dict]:
    by_arm = {m["arm"]: m for m in report["metrics"]}
    return [by_arm[a] for a in _monarch_first([m["arm"] for m in report["metrics"]])]


def _short(arm: str) -> str:
    """`monarch@797a8e5d1+feat/x` -> `monarch`, `gpt-5.6-sol/api` -> `gpt-5.6-sol`.

    Table headers use this and carry the full name in a `title`; the source line
    under the table always names competitors in full.
    """
    return arm.split("@")[0].split("/")[0]


def _shell(title: str, toc: str, hero: str, sections: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_esc(title)}</title>{FONTS}<style>{CSS}</style></head><body>"
        f'<div class="layout"><nav class="toc" aria-label="Contents">'
        f'<div class="brand"><span class="crown">{CROWN}</span> Monarch</div>'
        f'<div class="brand-sub">Benchmark report</div>{toc}</nav>'
        f'<main><div class="content">{hero}{sections}</div></main></div>'
        f"<script>{SPY_JS}</script></body></html>")


def _part(ident: str, eyebrow: str, title: str, sub: str, body: str) -> str:
    return (f'<section class="part" id="{ident}">'
            f'<div class="part-eyebrow">{_esc(eyebrow)}</div><h2>{_esc(title)}</h2>'
            f'<p class="h2-sub">{_esc(sub)}</p>{body}</section>')


def _toc_links(items) -> str:
    return "".join(f'<a href="#{i}"><span class="n">{n:02d}</span>{_esc(t)}</a>'
                   for n, (i, t) in enumerate(items, 1))


def _src(text: str) -> str:
    return ""      # source lines are listed once, in the Provenance section


def _bars(series, kind, highlight=None) -> str:
    """One row per competitor, as divs. `highlight` colours a bar by verdict."""
    usable = [v for _, v in series if v is not None]
    if not usable:
        return '<div class="bars"><p class="src">n/a</p></div>'
    top = max(usable) or 1.0
    out = ['<div class="bars">']
    for name, value in series:
        cls = (highlight or {}).get(name, "")
        if value is None:
            # An undefined figure keeps its verdict colour: n/a is a result, not
            # an absence, when a competitor passed nothing.
            vcls = "vl crit" if cls == "crit" else "vl dim"
            out.append(f'<div class="brow"><div class="nm" title="{_esc(name)}">'
                       f'{_esc(_short(name))}</div>'
                       f'<div class="tr"></div><div class="{vcls}">n/a</div></div>')
            continue
        pct = max(1.5, (value / top) * 100)
        out.append(f'<div class="brow"><div class="nm" title="{_esc(name)}">'
                   f'{_esc(_short(name))}</div>'
                   f'<div class="tr"><div class="fl {cls}" style="width:{pct:.1f}%"></div></div>'
                   f'<div class="vl">{_fmt(value, kind)}</div></div>')
    out.append("</div>")
    return "".join(out)


def _interruption(report: dict) -> str:
    """A round that stopped short says so, in the reference's callout style."""
    planned = report["size"]["per_competitor"] * report["size"]["competitors"]
    if report["size"]["total"] >= planned:
        return ""
    mon = next((m for m in report["metrics"] if is_monarch(m["arm"])), None)
    extra = ""
    if mon:
        extra = (f' Monarch ran {mon["attempts"]} of {report["size"]["per_competitor"]} '
                 "planned attempts, so its figures are single attempts, not rates.")
    return (f'<div class="callout warn"><span class="label">Interrupted round</span>'
            f'{report["size"]["total"]} of {planned} planned attempts were recorded.'
            f"{_esc(extra)}</div>")


# -- the task story rows (executive) -----------------------------------------

def _expected_change(task_id: str, tasks_dir: str | Path = "tasks") -> str:
    """The approval rule in plain words, read from the task file's own
    assertions - the same place the checker reads - so a row cannot promise
    more than is actually tested."""
    path = Path(tasks_dir) / f"{task_id}.json"
    if not path.exists():
        return "n/a"
    try:
        info = json.loads(path.read_text(encoding="utf-8"))["info"]
    except (OSError, ValueError, KeyError):
        return "n/a"
    out = []
    for a in info.get("assertions", []):
        field, value = str(a.get("field", "")).replace("_", " "), a.get("value")
        if a.get("type") == "salesforce_contact_field_equals":
            entity = f"contact {a.get('contact_id', '')}".strip()
        elif a.get("type") == "salesforce_field_equals":
            entity = (f"{str(a.get('collection', 'record')).rstrip('s')} "
                      f"{a.get('record_id', '')}").strip()
        else:
            entity = str(a.get("type", "record"))
        out.append(f"Salesforce {entity}: {field} becomes "
                   f"{value if value is not None else 'n/a'}")
    return "; ".join(out) or "n/a"


def _request_text(task_id: str, tasks_dir: str | Path = "tasks") -> str:
    """The request every competitor was given, verbatim (PLAN.md rule 1)."""
    path = Path(tasks_dir) / f"{task_id}.json"
    if not path.exists():
        return task_id
    try:
        prompt = json.loads(path.read_text(encoding="utf-8"))["prompt"]
    except (OSError, ValueError, KeyError):
        return task_id
    user = [m for m in prompt if m.get("role") == "user"]
    return user[-1]["content"] if user else task_id


def _task_rows(report: dict, tasks_dir: str | Path = "tasks") -> str:
    """One full-width row per task: the request, the expected change, and
    Monarch's verdict alone.

    The other competitors are deliberately absent here: this section answers
    "did Monarch do the job", and the whole field is two sections above.
    """
    mon = next((a for a in report["matrix"]["arms"] if is_monarch(a)), None)
    reasons = {}
    if mon:
        for attempt in report.get("monarch_attempts", {}).get(mon, []):
            reasons[attempt["task_id"]] = attempt
    rows = []
    for row in report["matrix"]["rows"]:
        cell = row["cells"].get(mon) if mon else None
        if cell is None:
            verdict = '<span class="badge">not run</span>'
        elif cell.get("on_retry") and cell["passed"]:
            # the first attempt failed and a later one passed: a different
            # result from passing outright, and worth saying so
            verdict = '<span class="badge warn">pass on retry</span>'
        elif cell["attempted"] and cell["passed"] == cell["attempted"]:
            verdict = '<span class="badge good">pass</span>'
        else:
            attempt = reasons.get(row["task_id"], {})
            if attempt.get("builder_outcome") == "needs_input":
                why = "asked for input"
            else:
                why = attempt.get("dispatch_outcome") or cell["category"]
            verdict = f'<span class="badge crit">fail &middot; {_esc(why)}</span>'
        rows.append(
            f'<div class="taskrow"><div class="body">'
            f'<p class="req">{_esc(_request_text(row["task_id"], tasks_dir))}</p>'
            f'<p class="exp">Expected: '
            f'{_esc(_expected_change(row["task_id"], tasks_dir))}</p></div>'
            f'<div class="verdict">{verdict}</div></div>')
    return f'<div class="taskrows">{"".join(rows)}</div>'


def _verdict_class(mon_value, best_value, lower_is_better: bool) -> str:
    """Monarch at or above the best model is good, below it is crit. An
    undefined figure is crit: a number we cannot compute is not a pass."""
    if mon_value is None:
        return "crit"
    if best_value is None:
        return "good"
    return ("good" if mon_value <= best_value else "crit") if lower_is_better \
        else ("good" if mon_value >= best_value else "crit")


_EXEC_TOC = [("headline", "Headline"), ("charts", "Every competitor"),
             ("tasks", "What each task asked"), ("verdict", "In one sentence")]

_RETRY_LABEL = "After one retry"

_HEADLINE = [
    ("Success, first try", lambda m: m["first_try_pass"]["mean"], "rate", False,
     "higher is better"),
    ("Success after one retry", lambda m: m["pass_after_retry"]["mean"], "rate",
     False, "higher is better"),
    ("Cost per passed attempt", lambda m: m["cost_per_passed"], "money", True,
     "lower is better"),
    ("Median time per attempt", lambda m: m["wall_clock"]["median"], "seconds",
     True, "lower is better"),
    # Completion alone flatters a competitor that finishes more prompts by
    # touching more than it was asked to. This card is the other half.
    ("Changes nobody asked for", lambda m: m["collateral_changes"], "count", True,
     "lower is better"),
]


def _has_retries(report: dict) -> bool:
    """Whether this round retried anything: a row carrying the flag, or a plan
    that asked for retries. Without one, "after retry" is "any repetition" and
    the second chart would only repeat the first on a single-attempt round."""
    if any(m["retries"]["count"] for m in report["metrics"]):
        return True
    if report["provenance"].get("retry_on_fail"):
        return True
    return report["size"]["repetitions"] > 1


def render_executive_page(report: dict[str, Any], tasks_dir: str | Path = "tasks") -> str:
    """The stakeholder page: Monarch first everywhere, the verdict in colour.

    Same dictionary and the same numbers as the technical page; it selects and
    colours, it never recomputes.
    """
    metrics = _ordered_metrics(report)
    monarch = next((m for m in metrics if is_monarch(m["arm"])), None)
    models = [m for m in metrics if not is_monarch(m["arm"]) and m["arm"] != "oracle"]
    p = report["provenance"]
    mon_name = _short(monarch["arm"]) if monarch else "monarch"
    cards, charts = [], []
    for label, get, kind, lower, hint in _HEADLINE:
        vals = [(m["arm"], get(m)) for m in models if get(m) is not None]
        best = ((min(vals, key=lambda x: x[1]) if lower else max(vals, key=lambda x: x[1]))
                if vals else ("n/a", None))
        mon_v = get(monarch) if monarch else None
        cls = _verdict_class(mon_v, best[1], lower)
        why = ('<p class="why">Monarch passed no attempt in this round, so this '
               "figure has no value to compute.</p>") if mon_v is None and monarch else ""
        cards.append(
            f'<div class="mcard"><div class="lab">{_esc(label)} &middot; {_esc(hint)}</div>'
            f'<div class="row"><div><div class="big {cls}">{_fmt(mon_v, kind)}</div>'
            f'<div class="who">{_esc(mon_name)}</div></div>'
            f'<div style="text-align:right"><div class="big">{_fmt(best[1], kind)}</div>'
            f'<div class="who">best model: {_esc(_short(best[0]))}</div></div></div>'
            f"{why}</div>")
        # a not-applicable competitor contributes no value: `_bars` draws that
        # as the text n/a, never as a zero-length bar
        charts.append(f"<h3>{_esc(label)}</h3>" + _bars(
            [(m["arm"], None if _na(m) else get(m)) for m in metrics], kind,
            {m["arm"]: (cls if is_monarch(m["arm"]) else "") for m in metrics}))

    cards.append(
        '<div class="mcard note"><div class="lab">What &ldquo;changes nobody '
        'asked for&rdquo; counts</div><p class="why">Every attempt is checked '
        'twice: did the requested result appear, and was anything else changed '
        'along the way. This figure is the second check &mdash; records written, '
        'or written more times than the request asked for, that nobody asked '
        'for. A competitor can finish more of the work and still leave more '
        'behind it, so read it next to the success rate, never instead of '
        'it.</p></div>')

    hero = (f'<header class="hero"><div class="eyebrow">Monarch benchmark</div>'
            f'<h1><span class="crown">{CROWN}</span> '
            f'{_esc(p.get("plan") or report["run_id"])}</h1>'
            f'<p class="lede">Monarch builds the workflow and runs it; the language '
            f"models get the same request and three tools and do the whole task "
            f"themselves.</p></header>")

    passing = [m for m in models if (m["strict_pass"]["mean"] or 0) == 1.0]
    cheapest = min(((m["arm"], m["cost_per_passed"]) for m in models
                    if m["cost_per_passed"] is not None), key=lambda x: x[1],
                   default=("n/a", None))
    without = (f"{len(passing)} of {len(models)} models finished every task on their "
               f"own; the rest missed at least one. The cheapest passed attempt cost "
               f"{_fmt(cheapest[1], 'money')} ({_short(cheapest[0])}).")
    rows = [a for group in (report.get("monarch_attempts") or {}).values() for a in group]
    if monarch and rows:
        built = sum(1 for a in rows if a["builder_outcome"] == "done")
        passed = sum(1 for a in rows if a["checker"] == "pass")
        ran = sum(1 for a in rows if a["dispatch_outcome"] == "success")
        asked = sum(1 for a in rows if a["builder_outcome"] == "needs_input")
        failed = [a for a in rows if a["checker"] != "pass"]
        reason = ""
        if failed:
            f0 = failed[0]
            stage = ("the builder" if f0["builder_outcome"] != "done"
                     else f"dispatch ({f0['dispatch_outcome']})" if f0["dispatch_outcome"] != "success"
                     else "the checker")
            reason = f" The first failure was at {stage}: {f0['reason'] or 'no detail'}."
        asked_text = f" {asked} asked for user input." if asked else ""
        with_text = (
            f"{len(rows)} attempt{'s' if len(rows) != 1 else ''}, {passed} passed. The builder "
            f"produced a workflow in {built} of {len(rows)}; dispatch finished in {ran} of "
            f"{len(rows)}.{asked_text}{reason}")
    else:
        with_text = "No Monarch attempt was recorded in this round."

    parts = [
        _interruption(report),
        _part("headline", "Part 01 - Headline", "Monarch against the best model",
              "Each card puts Monarch's figure beside the best language model on "
              "the same metric.", f'<div class="cards">{"".join(cards)}</div>'),
        _part("charts", "Part 02 - Every competitor", "The whole field",
              "The same three metrics, every competitor, Monarch first.",
              "".join(charts)),
        _part("tasks", "Part 03 - The work", "What each task asked",
              "The request, what the checker required, and whether Monarch "
              "delivered it.", _task_rows(report, tasks_dir)),
        _part("verdict", "Part 04 - Reading", "In one sentence",
              "The round summarised on both sides.",
              f'<div class="strip"><div class="half">'
              f'<div class="lab">Without Monarch</div><p>{_esc(without)}</p></div>'
              f'<div class="half"><div class="lab">With Monarch</div>'
              f"<p>{_esc(with_text)}</p></div></div>"),
    ]
    return _shell("Monarch benchmark", _toc_links(_EXEC_TOC), hero, "".join(parts))


def _bar_chart(series: list[tuple[str, Any, Any]], kind: str = "rate",
               width: int = 520) -> str:
    """A horizontal bar chart as inline SVG: one bar per competitor, a thin line
    for the error bar, the formatted value as the label.

    Every label is `_fmt`'s output, so the chart and the table beside it can
    never print different numbers. A missing value degrades to the text `n/a`
    rather than a zero-length bar, because a bar of length zero reads as "it
    scored nothing" instead of "we do not know".

    # ponytail: hand-written SVG, no charting library. Ceiling: one horizontal
    # bar chart with one series; a second series or an axis means revisit.
    """
    usable = [v for _, v, _ in series if v is not None]
    if not usable:
        return '<p class="note">n/a - no value to chart</p>'
    top = max(usable) or 1.0
    row_h, label_w, pad = 22, 150, 4
    height = len(series) * row_h + pad
    bar_max = width - label_w - 90
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" width="{width}" '
             f'height="{height}" role="img">']
    for i, (name, value, error) in enumerate(series):
        y = i * row_h + pad
        mid = y + row_h / 2 - 3
        # ponytail: 150 px of 11.5 px mono holds ~21 characters; longer names
        # (monarch@<commit>+<branch>) ran under the bars. Full name in the tooltip.
        short = name if len(name) <= 21 else name[:20] + "…"
        parts.append(f'<text class="cl" x="0" y="{mid + 4:.0f}"><title>{_esc(name)}</title>'
                     f'{_esc(short)}</text>')
        if value is None:
            parts.append(f'<text class="cv" x="{label_w}" y="{mid + 4:.0f}">n/a</text>')
            continue
        w = max(1.0, (value / top) * bar_max)
        parts.append(f'<rect class="cb" x="{label_w}" y="{y + 3}" width="{w:.1f}" '
                     f'height="{row_h - 9}"/>')
        end = label_w + w
        if error:
            lo = max(0.0, (value - error) / top) * bar_max + label_w
            hi = min(1.0, (value + error) / top) * bar_max + label_w
            # the uncertainty band: a faint block over the bar's end, from
            # value-error to value+error (a white whisker read as a stray line)
            parts.append(f'<rect class="ce" x="{lo:.1f}" y="{y + 3}" '
                         f'width="{max(0.0, hi - lo):.1f}" height="{row_h - 9}"/>')
            end = max(end, hi)          # the label sits past the error bar, never under it
        parts.append(f'<text class="cv" x="{end + 6:.0f}" '
                     f'y="{mid + 4:.0f}">{_fmt(value, kind)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _overview_section(report: dict) -> str:
    """Section 1: what was compared, in plain words."""
    p, size = report["provenance"], report["size"]
    totals = report["totals"]
    mode = MODE_WORDS.get(p.get("mode") or "")
    lines = []
    if mode:
        lines.append(_esc(mode))
    lines.append(_size_line(size))
    lines.append(f"total spend: {_fmt(totals['spend_usd'], 'money')}")
    lines.append("competitors: " + ", ".join(_esc(a) for a in report["arms"]))
    if p.get("plan"):
        lines.append(f"plan {_esc(p['plan'])} on {_esc(p.get('product') or 'n/a')}")
    lines.extend(_esc(note) for note in report.get("caveats", []))
    body = f'<p class="over">{"<br>".join(lines)}</p>'
    return body


def _success_table(report: dict) -> str:
    headers = ["competitor", "attempts", "passed", "strict pass", "of",
               "first try", "after retry", "retries", "pass over reps",
               "attempts with collateral", "collateral changes", "infra",
               "infra rate", "agent errors", "timeouts"]
    # The attempt counts are real for every competitor; only the results are
    # replaced by `n/a` where the answer key had nothing to act on.
    rows = [[m["arm"], _fmt(m["attempts"])]
            + _cells(m, [_fmt(m["passed"]),
                         _fmt(m["strict_pass"], "rate"),
                         _fmt(m["strict_pass_denominator"]),
                         _fmt(m["first_try_pass"], "rate"),
                         _fmt(m["pass_after_retry"], "rate"),
                         _fmt(m["retries"]["count"]),
                         _fmt(m["pass_over_repetitions"], "rate"),
                         # what it touched that nobody asked for: a competitor
                         # can pass more prompts by making a bigger mess
                         _fmt(m["collateral_attempts"]),
                         _fmt(m["collateral_changes"])])
            + [_fmt(m["infra"]), _fmt(m["infra_rate"], "rate"),
               _fmt(m["agent_errors"]), _fmt(m["timeouts"])]
            for m in report["metrics"]]
    return _table(headers, rows, _source_line_for(report, "metrics"),
                  "Strict pass rate per competitor")


def _na_note(report: dict) -> str:
    """One sentence under the success table naming every competitor shown as
    `n/a` and why (contract section 1a). Empty when none is."""
    names = [m["arm"] for m in report["metrics"] if _na(m)]
    if not names:
        return ""
    return (f'<p class="note">{_esc(", ".join(names))}: '
            f"{_esc(NOT_APPLICABLE_REASON)}, so every result below is shown as "
            "n/a rather than as a 0%.</p>")


def _success_section(report: dict) -> str:
    """Section 2: did it work. The chart, the table, the matrix, the comparison."""
    metrics = report["metrics"]
    block = lambda key: _series(
        metrics, lambda m: (m["arm"], m[key]["mean"], m[key]["sem"]))
    chart = "<h3>Strict pass rate</h3>" + _bar_chart(block("strict_pass"), kind="rate")
    chart += "<h3>First try</h3>" + _bar_chart(block("first_try_pass"), kind="rate")
    if _has_retries(report):
        chart += f"<h3>{_RETRY_LABEL}</h3>" + _bar_chart(block("pass_after_retry"),
                                                         kind="rate")
    body = (chart + _success_table(report) + _na_note(report)
            + _matrix_tables(report) + _comparison_table(report))
    return body


def _cost_section_table(report: dict) -> str:
    """The cost table, shared by the per-round page and the summary."""
    dollars = True
    metrics = report["metrics"]
    base = next((m["cost_total"] for m in metrics if m["arm"] == report["baseline"]),
                None)
    headers = (["competitor", "cost total", "cost / attempt", "cost / passed"]
               if dollars else ["competitor", "cost vs baseline"])
    headers += ["prompt tok", "cached tok", "cache write", "output tok", "cache hit"]
    phases = _phase_names(metrics)
    if dollars:
        headers += [f"{PHASE_WORDS.get(n, n)} cost" for n in phases]
    show_models = any(m["cost_per_model"] for m in metrics) and dollars
    if show_models:
        headers.append("cost by model")
    rows = []
    for m in metrics:
        if dollars:
            # what it spent is real; cost per passed attempt is a result
            row = [m["arm"], _fmt(m["cost_total"], "money"),
                   _fmt(m["cost_per_attempt"], "money")] + _cells(
                       m, [_fmt(m["cost_per_passed"], "money")])
        else:
            row = [m["arm"], _fmt((m["cost_total"] / base) if base else None, "ratio")]
        t = m["tokens"]
        row += [_fmt(t["prompt"]), _fmt(t["cached"]), _fmt(t["cache_write"]),
                _fmt(t["output"]), _fmt(m["cache_hit_rate"], "rate")]
        if dollars:
            for name in phases:
                phase = m["phases"].get(name)
                row.append(_fmt(phase["cost_usd"] if phase else None, "money"))
        if show_models:
            row.append(" - ".join(f"{n} {_fmt(c, 'money')}"
                                  for n, c in sorted(m["cost_per_model"].items()))
                       or "n/a")
        rows.append(row)
    return _table(headers, rows, _source_line_for(report, "metrics"),
                  "Cost per competitor")


def _cost_section(report: dict) -> str:
    """Section 3: what it cost, per competitor and - for Monarch - per phase and
    per model of its team."""
    series = _series(report["metrics"], lambda m: (m["arm"], m["cost_per_passed"], None))
    return _bar_chart(series, kind="money") + _cost_section_table(report)


def _time_section_table(report: dict) -> str:
    """The time table, shared by the per-round page and the summary."""
    metrics = report["metrics"]
    phases = _phase_names(metrics)
    headers = ["competitor", "wall-clock mean", "wall-clock median", "turns",
               "tool calls"]
    headers += [f"{PHASE_WORDS.get(n, n)} s" for n in phases]
    rows = []
    for m in metrics:
        row = [m["arm"], _fmt(m["wall_clock"]["mean"], "seconds"),
               _fmt(m["wall_clock"]["median"], "seconds"),
               _fmt(m["turns"]), _fmt(m["tool_calls"])]
        for name in phases:
            phase = m["phases"].get(name)
            row.append(_fmt(phase["wall_clock_s"] if phase else None, "seconds"))
        rows.append(row)
    return _table(headers, rows, _source_line_for(report, "metrics"),
                  "Time per attempt")


def _time_section(report: dict) -> str:
    """Section 4: how long an attempt took, and - for Monarch - how that split
    between the builder and dispatch."""
    series = [(m["arm"], m["wall_clock"]["median"], None) for m in report["metrics"]]
    return _bar_chart(series, kind="seconds") + _time_section_table(report)


def _builder_cell(attempt: dict):
    """The builder outcome, carrying the builder's own assumptions as a tooltip.

    The unattended builder decides for itself what the request left open, and
    those decisions explain a great many verdicts. The first three ride on the
    cell as a `title` (`_table` escapes it); the full list is in the turn log.
    """
    assumptions = attempt.get("assumptions") or []
    if not assumptions:
        return attempt["builder_outcome"]
    shown = "; ".join(assumptions[:3])
    if len(assumptions) > 3:
        shown += f" (+{len(assumptions) - 3} more)"
    return (attempt["builder_outcome"], f"assumed: {shown}")


def _monarch_section(report: dict) -> str:
    """Section 5: one row per Monarch attempt, builder and dispatch apart.

    Rendered only when a Monarch competitor is on the page. A single pass/fail
    hides the difference between a builder that declined, a builder that never
    finished, and an engine that timed out running a workflow that was written
    correctly - and that difference is the whole point of the pilot.
    """
    attempts = report.get("monarch_attempts") or {}
    if not attempts:
        return ""
    body = ""
    for arm, rows in sorted(attempts.items()):
        outcome_rows = [[o["outcome"], _fmt(o["count"]), _fmt(o["share"], "rate")]
                        for o in monarch_outcomes(rows)]
        body += _table(["outcome", "count", "share"], outcome_rows,
                       _source_line_for(report, "monarch"),
                       f"{arm}, attempts by outcome", numeric_from=1)
        table_rows = [[a["task_id"], _fmt(a["trial"]),
                       _builder_cell(a),
                       _fmt(a["questions_asked"]),
                       _fmt(a["builder_seconds"], "seconds"),
                       _fmt(a["builder_cost"], "money"), a["dispatch_outcome"],
                       _fmt(a["dispatch_seconds"], "seconds"), a["checker"],
                       _fmt(a.get("front_door_calls")),
                       _fmt(a.get("front_door_errors")),
                       (a["reason"] or "")]
                      for a in rows]
        body += _table(["task", "repetition", "builder", "questions", "builder s",
                        "builder cost", "dispatch", "dispatch s", "checker",
                        "front door", "front door errors", "reason"],
                       table_rows,
                       _source_line_for(report, "monarch"), f"{arm}, attempt by attempt",
                       numeric_from=1)
    return body
