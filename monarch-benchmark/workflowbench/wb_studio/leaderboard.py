"""Read-only rankings from immutable run records, partitioned by evaluation contract."""
from fractions import Fraction
from itertools import combinations
import hashlib
import json
import math


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def known_cost(result):
    value = result.get('cost_usd')
    if value is None or any(flag in result.get('flags', []) for flag in ('billing=unknown', 'cost_missing')):
        return None
    return float(value) if isinstance(value, (float, int)) and math.isfinite(value) and value >= 0 else None


def comparison_runner(studio, arm):
    from wb_arms import providers
    from wb_studio.gateways import resolve_effort
    runner=arm.get('runner_override') or arm.get('runner')
    if not runner and arm.get('kind')=='version':
        try:
            from wb_studio.execution import load_version
            version=load_version(studio,arm['blueprint'],arm['number'])
            values=[n['config']['runner'] for n in version['graph']['nodes'] if n['type']=='agent']
            if values and all(v==values[0] for v in values): runner=values[0]
        except (ValueError,KeyError,OSError,AttributeError,TypeError): pass
    if not runner: return None
    try:
        provider=providers.get(runner['model'])
        effort=runner.get('effort','default')
        if effort=='default': effort=resolve_effort(provider,effort) or 'default'
        return {'model':provider.model_id,'effort':effort}
    except (ValueError,KeyError): return None


def evaluation_contract(job, hashes=None) -> dict:
    """Everything that must agree before two runs may be compared as one measurement.

    The task identities, the track, the judge, how much the competitor was helped, the
    world revision, and — for a workflow round — the workflow contract. PLAN.md §1.1
    requires paired comparisons only on identical sets and a config hash per run; this
    is that rule as one function.

    It is one function because it was two. `report_data.cohorts` keyed a round on task
    hashes and track alone, so the surface a person actually opens could pool a run
    graded by one judge with a run graded by another and rank them against each other
    (feature 024, FR-016). Both partitions now come from here.
    """
    settings = job.get('settings') or {}
    if hashes is None:
        hashes = {task: (job.get('task_hashes') or {}).get(task) for task in settings.get('tasks') or []}
    from wb_world.source import product_of
    product = product_of(job)
    return {**({'product': product} if product else {}), 'task_hashes': hashes, 'track': settings.get('track', 'agentic-request'),
            'judge': (job.get('component_manifest') or {}).get('judge') or 'historical-unpinned',
            'assistance': settings.get('assistance', 'unattended'),
            'world': job.get('world_manifest', 'historical-unpinned'),
            'workflow_contract': job.get('workflow_contract', 'historical-unpinned') if settings.get('track') == 'create-and-run' else None}


def contract_note(contract) -> str:
    """What a reader must know about the partition before believing a ranking in it."""
    pinned = contract.get('judge') != 'historical-unpinned'
    return ('Same task identities and evaluation contract. '
            + ('Component identities are pinned.' if pinned
               else 'Historical records lack a pinned judge; rankings are provisional.'))


def rank_records(studio):
    cohorts = {}
    for job in studio.jobs():
        if job.get('status') not in ('completed', 'failed', 'cancelled', 'interrupted') or not job.get('task_hashes'):
            continue
        settings = job['settings']
        hashes = {task: job['task_hashes'].get(task) for task in settings['tasks']}
        if not all(hashes.values()):
            continue
        contract = evaluation_contract(job, hashes)
        key = digest(contract)
        cohort = cohorts.setdefault(key, {'id': key, 'contract': contract, 'track': contract['track'],
                                         'task_count': len(hashes), 'groups': {},
                                         'note': contract_note(contract)})
        arms = settings.get('arms') or [{'id': identity, 'name': identity, 'kind': 'runner'} for identity in settings['models']]
        for arm in arms:
            rows = [r for r in job.get('results', []) if r['model'] == arm['id']]
            # Rank only a complete task set; incomplete operational runs remain in Runs.
            if len(rows) != len(hashes) or {r['task'] for r in rows} != set(hashes):
                continue
            identity = digest({'arm': arm, 'configuration': settings.get('configuration', {}),
                               'components': job.get('component_manifest'), 'concurrency': settings.get('concurrency', 1),
                               'execution': job.get('execution_manifests', {}).get(arm['id']),
                               'runner': job.get('runner_manifests', {}).get(arm['id'])})
            runner = job.get('runner_manifests', {}).get(arm['id'], {})
            native_bare = (arm.get('kind') == 'native' and arm.get('version') == 'without-monarch'
                           and runner.get('harness') in ('codex', 'claude-code')
                           and all(runner.get(k) for k in ('model', 'harness_version', 'model_version', 'tools_sha256', 'world_sha256'))
                           and not settings.get('configuration', {}).get('prompt'))
            entry = cohort['groups'].setdefault(identity, {'id': identity, 'name': arm.get('name', arm['id']),
                   'kind': 'Bare native harness' if native_bare else 'API control' if arm.get('kind') == 'runner' else arm.get('kind', 'historical'),
                   'is_bare': bool(native_bare), 'comparison_runner': comparison_runner(studio,arm), 'runner_manifest': runner, 'passed': 0, 'attempts': 0, 'infrastructure': 0, 'cost_usd': 0.0, 'task_count': len(hashes), 'runs': []})
            entry['runs'].append(job['id'])
            entry.setdefault('_rows', []).extend(rows)
            for row in rows:
                infra = str(row.get('termination', '')).startswith('infra:')
                entry['attempts'] += 1
                entry['passed'] += int(bool(row.get('passed')) and not infra)
                entry['infrastructure'] += int(infra)
                cost = known_cost(row)
                entry['cost_usd'] = None if entry['cost_usd'] is None or cost is None else entry['cost_usd'] + cost
    output = []
    for cohort in cohorts.values():
        entries = sorted(cohort.pop('groups').values(), key=lambda r: (-Fraction(r['passed'], r['attempts']), r['name']))
        previous, rank = None, 0
        for index, entry in enumerate(entries):
            score = Fraction(entry['passed'], entry['attempts'])
            if score != previous:
                rank = index + 1
            previous = score
            entry.update(rank=rank, success_rate=float(score))
        if entries:
            rows_by_entry = {entry['id']: entry.pop('_rows') for entry in entries}
            cohort['pairings'] = pairings(rows_by_entry)
            for entry in entries:
                entry['interval'] = uncertainty(rows_by_entry[entry['id']])
                entry['matching_bare_ids']=[b['id'] for b in entries if b['is_bare'] and entry.get('comparison_runner') and b.get('comparison_runner')==entry['comparison_runner']]
            cohort['entries'] = entries
            output.append(cohort)
    return {'cohorts': sorted(output, key=lambda c: (-c['task_count'], c['id']))}


def exclusion_reason(job):
    """Why a run stays off the public leaderboard; None when it qualifies:
    a finished, server-pinned, complete matrix on the frozen 50-task benchmark."""
    if job.get('status') != 'completed': return 'not finished'
    benchmark = job.get('benchmark') or {}
    hashes = benchmark.get('task_hashes') or {}
    if benchmark.get('id') != 'catalog-50' or len(hashes) != 50 or not all(hashes.values()): return 'not the frozen 50-task benchmark'
    settings = job.get('settings', {})
    tasks = settings.get('tasks', [])
    if len(tasks) != 50 or set(tasks) != set(hashes) or job.get('task_hashes') != hashes: return 'task set differs from the benchmark'
    arms = settings.get('arms', [])
    identities = [arm.get('id') for arm in arms]
    if not identities or len(set(identities)) != len(identities): return 'no distinct setups'
    if any(a.get('kind') == 'scripted' for a in arms): return 'includes a scripted check'
    expected = {(model,task) for model in identities for task in tasks}
    rows = job.get('results', [])
    if len(rows) != len(expected) or {(r.get('model'),r.get('task')) for r in rows} != expected: return 'incomplete attempts'
    if not all(type(r.get('passed')) is bool and r.get('termination') not in (None,'','running','queued') for r in rows): return 'attempts without a verdict'
    return None


def full_benchmark_run(job):
    return exclusion_reason(job) is None


def task_shares(rows):
    """Per-task pass share over evaluated repetitions, and the largest repetition count."""
    per = {}
    for r in rows:
        if not str(r.get('termination', '')).startswith('infra:') and 'grading=ungraded' not in (r.get('flags') or []):
            per.setdefault(r['task'], []).append(bool(r.get('passed')))
    return {t: sum(v) / len(v) for t, v in per.items()}, max((len(v) for v in per.values()), default=0)


def uncertainty(rows):
    """95 % interval for a setup's pass rate. Each task run once: Wilson over
    attempts. Repetitions: a normal interval over the per-task pass shares, so
    the unit is tasks and repeated tasks do not shrink the interval.

    A sample with no variance between tasks — every task passed, every task failed,
    or every task passed the same fraction of its repetitions — has a sample standard
    error of zero, and the normal interval collapses to a point. Three tasks that all
    passed printed "100%, 95% CI 100 to 100" (feature 024, FR-016). That is not
    certainty; it is a degenerate estimator on a small sample. Where it degenerates,
    fall back to Wilson over the **task** count, which is the conservative binomial
    answer and keeps tasks as the unit, so repetitions still do not buy confidence.
    """
    from wb_studio.measures import wilson
    shares, k = task_shares(rows)
    n = len(shares)
    if k <= 1:
        passed = int(sum(shares.values()))
        low, high = wilson(passed, n)
        return {'unit': 'attempts', 'tasks': n, 'repetitions': k, 'rate': passed / n if n else None, 'low': low, 'high': high}
    if not n:
        return {'unit': 'tasks', 'tasks': 0, 'repetitions': k, 'rate': None, 'low': None, 'high': None}
    mean = sum(shares.values()) / n
    if n < 2:
        return {'unit': 'tasks', 'tasks': n, 'repetitions': k, 'rate': mean, 'low': None, 'high': None}
    se = math.sqrt(sum((v - mean) ** 2 for v in shares.values()) / (n - 1) / n)
    if se <= 0:
        low, high = wilson(round(mean * n), n)
        return {'unit': 'tasks', 'tasks': n, 'repetitions': k, 'rate': mean, 'low': low, 'high': high}
    return {'unit': 'tasks', 'tasks': n, 'repetitions': k, 'rate': mean, 'low': max(0.0, mean - 1.96 * se), 'high': min(1.0, mean + 1.96 * se)}


def pairings(groups):
    """For every pair of setups on the same tasks: wins, losses, ties by
    per-task pass share, and the tasks only one side ever solved."""
    out = []
    for a, b in combinations(sorted(groups), 2):
        sa, sb = task_shares(groups[a])[0], task_shares(groups[b])[0]
        common = sorted(set(sa) & set(sb))
        if not common:
            continue
        wins = sum(sa[t] > sb[t] for t in common)
        losses = sum(sa[t] < sb[t] for t in common)
        out.append({'a': a, 'b': b, 'tasks': len(common), 'wins': wins, 'losses': losses, 'ties': len(common) - wins - losses,
                    'unique_a': sum(sa[t] > 0 and sb[t] == 0 for t in common), 'unique_b': sum(sb[t] > 0 and sa[t] == 0 for t in common)})
    return out


def leaderboard(studio):
    from types import SimpleNamespace
    jobs = studio.jobs()
    eligible = [job for job in jobs if full_benchmark_run(job)]
    result = rank_records(SimpleNamespace(jobs=lambda: eligible,directory=getattr(studio,'directory',None)))
    for cohort in result['cohorts']:
        names=[]
        for entry in cohort['entries']:
            for identity in entry['runs']:
                job=next(j for j in eligible if j['id']==identity)
                for arm in job['settings']['arms']:
                    if arm.get('kind') in ('version','enterprise'):
                        name=arm.get('architecture_name') or arm.get('name', 'Architecture').split(' / ')[0]
                        if name not in names: names.append(name)
        cohort['architecture_name'] = ' / '.join(names) if names else 'Bare controls'
    result['excluded_runs'] = len(jobs)-len(eligible)
    result['excluded'] = [{'id': job['id'], 'title': job.get('title'), 'reason': exclusion_reason(job)} for job in jobs if not full_benchmark_run(job)]
    result['requirement'] = 'Complete the frozen 50-task benchmark for every setup. Pilots and partial runs stay in Runs.'
    return result
