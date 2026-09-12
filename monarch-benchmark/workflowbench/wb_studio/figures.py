"""Figures Genesis can put in a card (feature 023 §5.9).

Genesis asks for a figure by **naming a kind and a run**. It never writes a number, a colour, an
axis or a pixel. The Studio computes the figure from `report_data.run_report` — the same numbers
the report itself shows — and stores the drawing options; the Studio's own chart kit
(`static/charts.js`) draws it with the design system's classes. So a figure in a card is the same
object, computed the same way and styled the same way, as a figure in a report.

Three rules this exists to keep:

- nothing grades itself, and nothing draws itself: the model chooses *which* figure, never *what
  it says* (`PLAN.md` §1);
- every figure carries its source line (figures rubric F6), written here from the run's own record.

A card body refers to a figure as `[figure:<id>]`, the same shape as the `[rec:kind:id]` tags the
record already uses, and the card renderer replaces it with the drawing.
"""
from __future__ import annotations

import uuid

from wb_results.evidence import write_json

MAX_PER_CARD = 2


def _source(report: dict) -> str:
    """The line under every figure: which run, over what, finished when (F6)."""
    method = report.get('method') or {}
    parts = ['Run ' + str(report.get('run'))[:12]]
    if method.get('task_count'):
        parts.append(f"{method['task_count']} tasks × {len(report.get('order') or [])} setups")
    if method.get('repetitions', 1) > 1:
        parts.append(f"{method['repetitions']} repetitions")
    if report.get('finished_at'):
        parts.append('finished ' + str(report['finished_at'])[:10])
    return ' · '.join(parts) + '.'


def _pass_rate(report: dict) -> dict:
    rows = [{k: row.get(k) for k in ('label', 'value', 'low', 'high', 'detail', 'baseline')}
            for row in (report.get('hero') or [])]
    if not rows:
        raise ValueError('This run has no evaluated attempts, so there is no pass rate to draw.')
    return {'chart': 'dotWhisker', 'options': {'title': 'Pass rate, with the 95% interval',
                                               'rows': rows, 'labelWidth': 220}}


def _failures(report: dict) -> dict:
    failures = report.get('failures') or {}
    buckets = [b for b in (failures.get('buckets') or []) if b.get('count')]
    if not buckets:
        raise ValueError('Nothing failed in this run, so there are no failure buckets to draw.')
    summary = failures.get('summary') or {}
    return {'chart': 'failureColumns',
            'options': {'buckets': buckets, 'failed': summary.get('failed_attempts'),
                        'title': f"{summary.get('failed_attempts')} of {summary.get('recorded_attempts')} attempts failed"}}


def _cost(report: dict) -> dict:
    points = []
    for sid in report.get('order') or []:
        setup = (report.get('setups') or {}).get(sid) or {}
        per_attempt = (setup.get('cost') or {}).get('per_attempt')
        if not per_attempt:
            continue
        points.append({'label': setup.get('short_name') or setup.get('name'), 'x': per_attempt,
                       'y': (setup.get('pass') or {}).get('rate'), 'low': (setup.get('pass') or {}).get('low'),
                       'high': (setup.get('pass') or {}).get('high'), 'baseline': setup.get('is_baseline')})
    if not points:
        raise ValueError('No setup in this run has a known cost, so cost cannot be drawn.')
    return {'chart': 'scatter', 'options': {'title': 'Cost per attempt against pass rate', 'points': points,
                                            'xLog': True, 'pareto': len(points) > 1}}


def _tasks(report: dict) -> dict:
    if not report.get('tasks'):
        raise ValueError('This run records no tasks, so the task matrix is empty.')
    setups = [{'id': sid, 'name': ((report.get('setups') or {}).get(sid) or {}).get('short_name') or sid,
               'baseline': sid == report.get('baseline')} for sid in report.get('order') or []]
    return {'chart': 'matrix', 'options': {'tasks': report['tasks'], 'setups': setups, 'cells': report.get('matrix')}}


# kind -> (what it shows, builder). The sentence is what Genesis reads when it chooses.
KINDS = {
    'pass_rate': ('Pass rate per setup with its 95% interval — the figure a verdict rests on.', _pass_rate),
    'failures': ('How the failed attempts divide between failure buckets.', _failures),
    'cost_against_pass_rate': ('Cost per attempt against pass rate, one point per setup, log cost axis.', _cost),
    'tasks': ('Which setup solved which task, as a matrix.', _tasks),
}


def catalogue() -> list:
    return [{'kind': kind, 'shows': shows} for kind, (shows, _) in KINDS.items()]


def build(studio, kind: str, run: str, caption: str = '') -> dict:
    """Compute one figure. Raises ValueError with a sentence when the run cannot carry it."""
    if kind not in KINDS:
        raise ValueError('Figure kinds are: ' + ', '.join(KINDS) + '.')
    if not run:
        raise ValueError('Name the run the figure is drawn from, as run.')
    from wb_studio import report_data
    try:
        report = report_data.run_report(studio, str(run))
    except (ValueError, FileNotFoundError, KeyError) as exc:
        raise ValueError('Run ' + str(run) + ' cannot be read: ' + str(exc)[:160]) from None
    drawing = KINDS[kind][1](report)
    return {'id': uuid.uuid4().hex[:12], 'kind': kind, 'run': str(run),
            'caption': str(caption or '')[:200], 'source': _source(report), **drawing}


def save(genesis, figure: dict) -> dict:
    folder = genesis.root / 'figures'
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / (figure['id'] + '.json'), figure)
    return figure


def read(genesis, identity: str) -> dict:
    import json
    path = genesis.root / 'figures' / (str(identity) + '.json')
    if not str(identity).isalnum() or not path.exists():
        raise ValueError('No figure is called ' + str(identity) + '.')
    return json.loads(path.read_text(encoding='utf8'))


def tool(genesis, payload: dict) -> dict:
    figure = save(genesis, build(genesis.studio, payload.get('kind'), payload.get('run'),
                                 payload.get('caption')))
    return {'figure': figure['id'], 'kind': figure['kind'], 'source': figure['source'],
            'note': 'Write [figure:' + figure['id'] + '] on its own line in the card body where the '
                    'figure belongs. Every number in it was computed by the Studio; do not restate them in prose.'}


TOOLS = {'figure': tool}
PROTOCOL = (
    'A figure goes in a card by asking for it: `figure {kind, run, caption?}` returns an id, and '
    '`[figure:<id>]` on its own line in the body is where it is drawn. Kinds: '
    + '; '.join(k + ' — ' + s for k, (s, _) in KINDS.items()) + '. The Studio computes every number '
    'and the design system draws it, so do not restate the figure in prose and never write the '
    'numbers yourself. At most ' + str(MAX_PER_CARD) + ' figures in one card: a figure that is not '
    'the point of the card is noise.')
