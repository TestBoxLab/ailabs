"""The Studio's brain as read-only tools (feature 022, design section 7).

Genesis stops adding up events by hand. Every tool here returns the same JSON the report pages
read, computed by `wb_studio.measures`, `wb_studio.report_data` and `wb_studio.failure_analysis`:
Wilson intervals, pass^k, the paired sign test and the overlap are never reimplemented here.

Every result carries `tags`, one `[rec:run:<id>]` per run it read, so a sentence Genesis writes
can cite the run it came from. Results that can name lab competitors carry `audience: internal`,
the same boundary `report_data.visible_setups` draws.
"""
from __future__ import annotations

from collections import defaultdict


def _tagged(value: dict, runs, internal: bool = False) -> dict:
    out = {**value, 'tags': ['[rec:run:' + str(r) + ']' for r in runs]}
    if internal:
        out['audience'] = 'internal'
    return out


def _job(genesis, payload, key='run'):
    identity = payload.get(key) or payload.get('id')
    if not identity:
        raise ValueError('Name the run to read, as ' + key + '.')
    try:
        return genesis.studio.job(identity)
    except (FileNotFoundError, OSError, ValueError):
        raise ValueError('No run is called ' + str(identity) + '.')


def _pass_rows(rows) -> dict:
    from wb_studio.measures import pass_rate
    return pass_rate(rows)


def _grouped(job, group) -> list:
    """Passed, attempts, rate and Wilson interval per group, from `measures.pass_rate`."""
    from wb_studio.report_data import category_of
    of = {'setup': lambda r: str(r.get('model')), 'task': lambda r: str(r.get('task')),
          'category': lambda r: category_of(r.get('task'))}[group]
    buckets = defaultdict(list)
    for row in job.get('results') or []:
        buckets[of(row)].append(row)
    return [{'group': name, **_pass_rows(rows)} for name, rows in sorted(buckets.items())]


def measures_tool(genesis, payload) -> dict:
    """Every measure of one run (`measures.run_measures`), and a tally per setup, task or category."""
    from wb_studio.measures import run_measures
    group = payload.get('group_by')
    if group is not None and group not in ('setup', 'task', 'category'):
        raise ValueError('group_by is setup, task or category, or left out.')
    job = _job(genesis, payload)
    events = genesis.studio.events(job['id'])
    out = {'run': job['id'], 'title': job.get('title'), 'status': job.get('status'),
           'measures': run_measures(job, events)}
    if group:
        out['group_by'] = group
        out['groups'] = _grouped(job, group)
    return _tagged(out, [job['id']], internal=True)


def compare_tool(genesis, payload) -> dict:
    """Two runs, or a run against its Bare baseline.

    Against the baseline: the run's own Bare setup when it has one, else the Bare rows of an
    earlier run on the same frozen tasks, model and thinking setting, exactly as
    `report_data.historical_baseline` and `with_baseline` reuse them for a report. Every
    non-baseline setup then carries the paired delta, sign test and Wilson intervals
    `measures.run_measures` computed, with `measures.overlap` across the setups.

    Against another run: the setups the two runs share, paired by `measures.paired` on the
    frozen task hashes. When the task sets differ, `measures.paired` says so in words instead
    of returning a delta; when the runs share no setup, the result says that in one sentence.
    """
    from wb_studio import measures as M
    from wb_studio.report_data import historical_baseline, with_baseline
    job = _job(genesis, payload)
    against = payload.get('against') or 'baseline'
    if against == 'baseline':
        events = genesis.studio.events(job['id'])
        reused = None
        if M.baseline_id(job) is None:
            subject = next((s for s in (job.get('settings') or {}).get('arms') or []), None)
            try:  # a run whose baseline cannot be looked up still compares its own setups
                reused = historical_baseline(genesis.studio, job, subject['id']) if subject else None
            except (AttributeError, KeyError, TypeError, ValueError, OSError):
                reused = None
            if reused:
                job = with_baseline(job, reused)
        m = M.run_measures(job, events)
        baseline = m['baseline']
        setups = [{'setup': s, 'name': m['setups'][s]['name'], 'is_baseline': s == baseline,
                   'pass': m['setups'][s]['pass'], 'cost': m['setups'][s]['cost'],
                   'paired': m['setups'][s]['paired']} for s in m['order'] if s in m['setups']]
        runs = [job['id']] + ([reused['run']] if reused else [])
        return _tagged({'run': job['id'], 'against': 'baseline', 'baseline': baseline,
                        'baseline_source': {'run': reused['run'], 'title': reused['title'],
                                            'finished_at': reused['finished_at']} if reused else None,
                        'comparable': baseline is not None,
                        'reason': None if baseline else 'This run has no Bare baseline and no earlier run reuses one on the same frozen tasks.',
                        'setups': setups, 'overlap': m['overlap']}, runs, internal=True)
    other = _job(genesis, {'run': against})
    mine, theirs = M.by_setup(job.get('results') or []), M.by_setup(other.get('results') or [])
    shared = sorted(set(mine) & set(theirs))
    if not shared:
        return _tagged({'run': job['id'], 'against': other['id'], 'comparable': False,
                        'reason': 'The two runs share no setup: ' + (', '.join(sorted(mine)) or 'none')
                                  + ' against ' + (', '.join(sorted(theirs)) or 'none') + '.',
                        'setups': []}, [job['id'], other['id']], internal=True)
    hashes, other_hashes = job.get('task_hashes') or {}, other.get('task_hashes') or {}
    setups = [{'setup': s, 'pass': _pass_rows(mine[s]), 'against_pass': _pass_rows(theirs[s]),
               'paired': M.paired(mine[s], theirs[s], hashes, other_hashes)} for s in shared]
    return _tagged({'run': job['id'], 'against': other['id'], 'comparable': True, 'reason': None,
                    'setups': setups,
                    'overlap': M.overlap({s + ' (this run)': mine[s] for s in shared}
                                         | {s + ' (' + other['id'] + ')': theirs[s] for s in shared})},
                   [job['id'], other['id']], internal=True)


def failure_buckets_tool(genesis, payload) -> dict:
    """`failure_analysis.analysis` trimmed to its buckets: counts, their denominators, and one
    recorded event id per bucket to read the evidence from."""
    from wb_studio.failure_analysis import analysis
    job = _job(genesis, payload)
    found = analysis(genesis.studio, job['id'])
    attempts = {a['id']: a for a in found['attempts']}
    buckets = []
    for bucket in found['buckets']:
        evidence = next((((attempts[i].get('earliest_supported_evidence') or {}).get('event_id')
                          or next(iter(attempts[i].get('event_ids') or []), None))
                         for i in bucket['attempt_ids'] if i in attempts), None)
        buckets.append({k: bucket[k] for k in ('id', 'label', 'count', 'percent_failed', 'percent_all')}
                       | {'attempts': len(bucket['attempt_ids']), 'evidence_event': evidence})
    return _tagged({'run': job['id'], 'summary': found['summary'], 'denominators': found['denominators'],
                    'classification_policy': found['classification_policy'], 'buckets': buckets,
                    'limitations': found['limitations']}, [job['id']], internal=True)


def report_tool(genesis, payload) -> dict:
    """The internal run report as data (`report_data.run_report`), without the model narrative:
    the grade, verdict, code findings, figures, failures, tasks, caveats and method."""
    from wb_studio.report_data import run_report
    job = _job(genesis, payload)
    found = run_report(genesis.studio, job['id'], 'internal')
    data = {k: v for k, v in found.items() if k not in ('narrative', 'model_findings')}
    runs = [job['id']] + ([found['baseline_source']['run']] if found.get('baseline_source') else [])
    return _tagged(data, runs, internal=True)


def task_catalog_tool(genesis, payload) -> dict:
    """Catalog tasks with tier, domain, category, hash and the applications they have to change
    (`genesis_hypotheses.catalog_rows`, which says where each field comes from)."""
    from wb_studio.genesis_hypotheses import _check_population, catalog_rows
    task_set, filters = payload.get('task_set'), payload.get('filter')
    if task_set or filters:
        population = _check_population({'task_set': task_set, 'filter': filters or {}})
        task_set, filters = population['task_set'], population['filter']
    rows = catalog_rows(genesis.studio, task_set or None, filters or {})
    return {'tasks': rows, 'count': len(rows),
            'fields': 'tier from info.tier or the tier-* set the task was drawn into; domain from '
                      'info.domain or the task id prefix; category from the report labels; hash is the '
                      'frozen contract hash; applications are the services info.expected_changes names.',
            'tags': ['[rec:task-catalog]']}


TOOLS = {
    'measures': measures_tool,
    'compare': compare_tool,
    'failure_buckets': failure_buckets_tool,
    'report': report_tool,
    'task_catalog': task_catalog_tool,
}

PROTOCOL = (
    'Never add up events by hand. measures {run, group_by?} returns every measure of a run with its '
    'Wilson intervals, plus a passed-and-attempted tally per setup, task or category. compare '
    '{run, against?} returns the paired delta, its interval, the sign test and the solved-task overlap, '
    'either against the run\'s Bare baseline (reusing an earlier Bare on the same frozen tasks when this '
    'run has none) or against another run on the setups they share. failure_buckets {run} returns the '
    'outcome buckets with their counts, the denominator each count is against, and one recorded event id '
    'to read per bucket. report {run} returns the internal run report as data, without the written '
    'narrative. task_catalog {task_set?, filter?} returns tasks with tier, domain, category, hash and the '
    'applications they have to change. Every result carries [rec:run:...] tags; cite them, and quote the '
    'numbers as they come back rather than recomputing them.'
)
