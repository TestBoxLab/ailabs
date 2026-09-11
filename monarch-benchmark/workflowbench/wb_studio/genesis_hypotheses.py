"""Hypotheses as records the Studio can settle (feature 022, design section 6).

A hypothesis card carries a record: a claim, the population it is about, the two setups it
compares, the measure, the direction, the smallest effect worth calling real, and an optional
prior. The Studio computes every number; the model writes none of them.

Nothing here grades. Outcomes come only from the grader's recorded results, through
`wb_studio.measures` (`pass_rate`, `pass_k`, `cost`, `violations`, `false_completion`, `turns`,
`paired`, `sign_test`, `wilson`) and `wb_studio.report_data` (`certainty`, `task_set_id`).
Wilson, pass^k and the sign test are never reimplemented here.

Two vocabularies meet in `minimum_effect`, and the record says which is in force:
for the rate and count measures it is a difference in the measure's own units (a fraction of
pass rate, changes per attempt, turns per attempt); for `cost_per_pass` it is a ratio above 1,
so 1.25 means "a quarter more expensive".
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

MEASURES = ('pass_rate', 'pass_k', 'cost_per_pass', 'violations', 'false_completion', 'turns')
DIRECTIONS = ('a_higher', 'a_lower')
KINDS = ('architecture', 'bare', 'monarch')
FILTER_KEYS = ('tier', 'domain', 'category', 'applications', 'task_ids')
# A record's setup kind against the arm kinds `Studio.create` writes into `settings.arms`.
ARM_KINDS = {'architecture': ('version',), 'bare': ('native', 'runner'), 'monarch': ('enterprise',)}
RATIO_MEASURES = ('cost_per_pass',)
# Tokens per attempt when no recorded attempt carries a count; stated in the plan's basis.
DEFAULT_TOKENS = {'input': 60000, 'output': 4000}
FINISHED = ('completed', 'failed', 'cancelled', 'interrupted')


def _number(value) -> bool:
    """True for a real int or float; `True` is not a number here, as `check_goal` also rules."""
    return type(value) in (int, float) and math.isfinite(value)


# --- the record -------------------------------------------------------------------------

def check_hypothesis(record) -> dict:
    """The record, normalised, or a ValueError whose sentence a person would want to read.

    The version-against-parent goal `wb_studio.genesis.check_goal` validates is one shape of
    this record: comparison `{a: {kind: monarch, id: version}, b: {kind: monarch, id: parent}}`,
    measure `pass_rate`, direction `a_higher`, minimum effect the declared minimum gain.
    """
    if not isinstance(record, dict):
        raise ValueError('A hypothesis is an object with claim, population, comparison, measure, direction and minimum_effect.')
    claim = str(record.get('claim') or '').strip()
    if not claim or len(claim) > 300 or '\n' in claim:
        raise ValueError('The claim is one directional sentence of up to 300 characters, on one line.')
    measure = record.get('measure')
    if measure not in MEASURES:
        raise ValueError('The measure is one of: ' + ', '.join(MEASURES) + '.')
    direction = record.get('direction')
    if direction not in DIRECTIONS:
        raise ValueError('The direction is a_higher or a_lower: which side the claim says is larger.')
    effect = record.get('minimum_effect')
    if not _number(effect) or effect <= 0:
        raise ValueError('The minimum effect is a number above 0: a fraction of pass rate for rates, a count for violations and turns, a ratio for cost per passed task.')
    if measure in RATIO_MEASURES and effect <= 1:
        raise ValueError('For cost per passed task the minimum effect is a ratio above 1, for example 1.25 for a quarter more.')
    out = {'claim': claim, 'population': _check_population(record.get('population')),
           'comparison': _check_comparison(record.get('comparison')), 'measure': measure,
           'direction': direction, 'minimum_effect': float(effect)}
    prior = record.get('prior')
    if prior is not None:
        if not _number(prior) or not 0 <= prior <= 1:
            raise ValueError('The prior is a probability between 0 and 1, or left out.')
        out['prior'] = float(prior)
    return out


def _check_population(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError('The population names a task set, a filter over the catalog, or both.')
    task_set = value.get('task_set')
    if task_set is not None and (not isinstance(task_set, str) or not task_set.strip()):
        raise ValueError("The population's task_set is the id of a saved task set, or null.")
    raw = value.get('filter') or {}
    if not isinstance(raw, dict):
        raise ValueError('The population filter is an object over ' + ', '.join(FILTER_KEYS) + '.')
    unknown = sorted(set(raw) - set(FILTER_KEYS))
    if unknown:
        raise ValueError('The population filter does not know ' + ', '.join(unknown) + '; it accepts ' + ', '.join(FILTER_KEYS) + '.')
    out = {}
    for key in ('tier', 'domain', 'category'):
        if raw.get(key) is not None:
            if not isinstance(raw[key], str) or not raw[key].strip():
                raise ValueError("The population filter's " + key + ' is one word from the catalog.')
            out[key] = raw[key].strip()
    if raw.get('applications') is not None:
        apps = raw['applications']
        if not isinstance(apps, dict) or set(apps) - {'min', 'max'}:
            raise ValueError('applications is {min, max}: how many applications a task has to change.')
        bounds = {}
        for key in ('min', 'max'):
            if apps.get(key) is not None:
                if type(apps[key]) is not int or apps[key] < 0:
                    raise ValueError('applications ' + key + ' is a whole number of applications, 0 or above.')
                bounds[key] = apps[key]
        if bounds.get('min', 0) > bounds.get('max', bounds.get('min', 0)):
            raise ValueError('applications min is at most applications max.')
        if bounds:
            out['applications'] = bounds
    if raw.get('task_ids') is not None:
        ids = raw['task_ids']
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i.strip() for i in ids):
            raise ValueError('task_ids is a list of task ids from the catalog.')
        out['task_ids'] = sorted(dict.fromkeys(i.strip() for i in ids))
    if not task_set and not out:
        raise ValueError('The population names a task set or at least one filter.')
    return {'task_set': task_set.strip() if task_set else None, 'filter': out}


def _check_setup(value, side) -> dict:
    if not isinstance(value, dict):
        raise ValueError('Setup ' + side + ' is an object with kind and id.')
    if value.get('kind') not in KINDS:
        raise ValueError('Setup ' + side + "'s kind is architecture, bare or monarch.")
    identity = value.get('id')
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError('Setup ' + side + ' names the id it runs under.')
    unknown = sorted(set(value) - {'kind', 'id', 'model'})
    if unknown:
        raise ValueError('Setup ' + side + ' does not know ' + ', '.join(unknown) + '; it accepts kind, id and model.')
    out = {'kind': value['kind'], 'id': identity.strip()}
    if value.get('model') is not None:
        if not isinstance(value['model'], str) or not value['model'].strip():
            raise ValueError('Setup ' + side + "'s model is a model name from the catalog, or left out.")
        out['model'] = value['model'].strip()
    return out


def _check_comparison(value) -> dict:
    if not isinstance(value, dict) or set(value) != {'a', 'b'}:
        raise ValueError('The comparison is {a, b}: the two setups it puts against each other.')
    a, b = _check_setup(value['a'], 'a'), _check_setup(value['b'], 'b')
    if a == b:
        raise ValueError('The comparison puts two different setups against each other; a and b are the same.')
    return {'a': a, 'b': b}


# --- the catalog and the population -----------------------------------------------------

def _category(identity) -> str:
    from wb_studio.report_data import category_of
    return category_of(identity)


def _domain(task, identity) -> str:
    return str((task.get('info') or {}).get('domain') or str(identity).split('.')[0])


def _applications(task) -> list:
    """The applications a task has to change: the distinct services in `info.expected_changes`,
    the same field the grader's scope checks are written against."""
    changes = (task.get('info') or {}).get('expected_changes') or []
    return sorted({c['service'] for c in changes if isinstance(c, dict) and c.get('service')})


def catalog_rows(studio, task_set=None, task_filter=None) -> list:
    """Every catalog task the population covers, with the fields a filter reads.

    tier: `info.tier`, which only the drawn sets under `tasks/` carry, else the `tier-*` task
    set the task belongs to. domain: `info.domain`, else the task id's prefix. category: the
    report's label (`report_data.category_of`). hash: `wb_world.episode.contract_hash`, the
    same value `task_sets` freezes a set against. applications: `info.expected_changes`.
    """
    from wb_studio.app import ROOT
    from wb_studio.task_sets import task_sets
    from wb_world.episode import contract_hash
    items = task_sets(studio, ROOT)['items']
    by_id = {item['id']: item for item in items}
    tiers = {t: item['id'][len('tier-'):] for item in items if item['id'].startswith('tier-') for t in item['tasks']}
    chosen = set(studio.tasks)
    if task_set:
        if task_set not in by_id:
            raise ValueError('No task set is called ' + task_set + '. The saved sets are: ' + (', '.join(sorted(by_id)) or 'none') + '.')
        chosen = set(by_id[task_set]['tasks'])
    filters = dict(task_filter or {})
    wanted = filters.get('task_ids')
    if wanted:
        missing = sorted(set(wanted) - set(studio.tasks))
        if missing:
            raise ValueError('The catalog has no task called ' + ', '.join(missing[:5]) + '.')
        chosen &= set(wanted)
    rows = []
    for identity in sorted(chosen):
        task = studio.tasks.get(identity)
        if task is None:
            continue
        rows.append({'id': identity, 'tier': (task.get('info') or {}).get('tier') or tiers.get(identity),
                     'domain': _domain(task, identity), 'category': _category(identity),
                     'hash': contract_hash(task), 'applications': _applications(task)})
    if filters.get('tier') and not all(row['tier'] for row in rows):
        # Lucas, 10 Sep: a task that records no tier takes the tercile of its difficulty score over the
        # whole catalog, the same measure and cuts `wb corpus tiers` draws with; the row says it was computed.
        from wb_orchestrator.tiers import score_task, tier_cuts, tier_of
        scores = {identity: score_task(task) for identity, task in studio.tasks.items()}
        try:
            cuts = tier_cuts(scores.values())
        except ValueError as exc:
            raise ValueError('No task in this population records a tier, and the catalog cannot be split into terciles (' + str(exc) + ').') from None
        for row in rows:
            if not row['tier']:
                row['tier'], row['tier_source'] = tier_of(scores[row['id']], cuts), 'computed'
    for row in rows:
        row.setdefault('tier_source', 'stored' if row['tier'] else None)
    out = []
    for row in rows:
        if filters.get('tier') and str(row['tier'] or '').lower() != filters['tier'].lower():
            continue
        if filters.get('domain') and row['domain'].lower() != filters['domain'].lower():
            continue
        if filters.get('category') and row['category'].lower() != filters['category'].lower():
            continue
        bounds = filters.get('applications') or {}
        if len(row['applications']) < bounds.get('min', 0) or len(row['applications']) > bounds.get('max', len(row['applications'])):
            continue
        out.append(row)
    return out


def population_tasks(studio, record) -> list[str]:
    """The task ids a hypothesis is about, sorted; a ValueError when nothing matches."""
    record = check_hypothesis(record)
    population = record['population']
    rows = catalog_rows(studio, population['task_set'], population['filter'])
    if not rows:
        raise ValueError('No task in the catalog matches this population.')
    return [row['id'] for row in rows]


# --- runs, coverage and the settlement --------------------------------------------------

def setup_rows(job, setup) -> list:
    """The result rows of one setup in a job.

    A row names its setup in `result['model']`: the arm id, or the arm id plus `--<model>@<effort>`
    when a model comparison expanded one architecture into several arms. That is the rule the
    `tally` inside `genesis.hypothesis_outcome` uses. `settings.arms` gives each arm its kind, so
    a record's kind (architecture, bare, monarch) only ever matches the arm family it names.
    """
    setup = _check_setup(setup, 'a')
    identity, kind = setup['id'], setup['kind']
    arms = (job.get('settings') or {}).get('arms') or []
    named = [a for a in arms if str(a.get('id')) == identity or str(a.get('id')).startswith(identity + '--')]
    if named:
        wanted = {a['id'] for a in named if a.get('kind') in ARM_KINDS.get(kind, ())}
        rows = [r for r in job.get('results') or [] if r.get('model') in wanted]
    elif arms:
        rows = []  # the job records its arms and none of them is this setup
    else:
        rows = [r for r in job.get('results') or []
                if str(r.get('model')) == identity or str(r.get('model')).startswith(identity + '--')]
    model = setup.get('model')
    if model:
        by_id = {a['id']: a for a in arms}
        def uses(row):
            arm = by_id.get(str(row.get('model'))) or {}
            runner = arm.get('runner_override') or arm.get('runner') or {}
            return (str(row.get('model')).split('--')[-1].split('@')[0] == model
                    or str(arm.get('model_selection') or '').split('@')[0] == model
                    or runner.get('model') == model)
        rows = [r for r in rows if uses(r)]
    return rows


def _bare_shown(job) -> bool:
    """Bare alongside, by `hypothesis_outcome`'s rule: a native harness without Monarch."""
    arms = (job.get('settings') or {}).get('arms') or []
    return any(a.get('kind') == 'native' and a.get('version') == 'without-monarch' for a in arms)


def coverage(studio, record) -> list:
    """Finished runs that ran both setups on the population, newest first.

    Runs that did not finish normally are listed too, with their status: `settle` needs them to
    say "invalid" rather than "untested" when the only evidence is a run that broke.
    """
    from wb_studio.report_data import task_set_id
    record = check_hypothesis(record)
    tasks = set(population_tasks(studio, record))
    out = []
    for job in studio.jobs():
        if job.get('status') not in FINISHED:
            continue
        a = [r for r in setup_rows(job, record['comparison']['a']) if r.get('task') in tasks]
        b = [r for r in setup_rows(job, record['comparison']['b']) if r.get('task') in tasks]
        if not a or not b:
            continue
        a_tasks, b_tasks = {r['task'] for r in a}, {r['task'] for r in b}
        out.append({'run': job['id'], 'title': job.get('title') or job['id'],
                    'finished_at': job.get('finished_at') or job.get('created_at') or '',
                    'status': job.get('status'), 'tasks': sorted(a_tasks & b_tasks),
                    'a_attempts': len(a), 'b_attempts': len(b), 'same_tasks': a_tasks == b_tasks,
                    'task_set': task_set_id(job), 'bare_shown': _bare_shown(job)})
    out.sort(key=lambda c: c['finished_at'], reverse=True)
    return out


def _side(rows, events, measure) -> dict:
    """One side's measure with its interval, computed only by `wb_studio.measures`."""
    from wb_studio import measures as M
    if measure == 'pass_rate':
        p = M.pass_rate(rows)
        return {'measure': measure, 'value': p['rate'], 'low': p['low'], 'high': p['high'], 'detail': p}
    if measure == 'pass_k':
        k = M.pass_k(rows)
        low, high = M.wilson(k['all_passed'] or 0, k['tasks']) if k['rate'] is not None else (None, None)
        return {'measure': measure, 'value': k['rate'], 'low': low, 'high': high, 'detail': k}
    if measure == 'cost_per_pass':
        c = M.cost(rows)
        return {'measure': measure, 'value': c['per_pass'], 'low': None, 'high': None, 'detail': c}
    if measure == 'violations':
        v = M.violations(rows)
        return {'measure': measure, 'value': v['per_attempt'], 'low': None, 'high': None, 'detail': v}
    if measure == 'false_completion':
        f = M.false_completion(rows)
        low, high = M.wilson(f['count'], f['failed'])
        return {'measure': measure, 'value': f['rate'], 'low': low, 'high': high, 'detail': f}
    t = M.turns(rows, events)
    return {'measure': measure, 'value': t['turns_mean'], 'low': None, 'high': None, 'detail': t}


def _effect(a, b, measure, direction):
    """The size of the difference in the stated direction: a difference for the rate and count
    measures, a ratio for cost per passed task. None when a side has no value."""
    left, right = a['value'], b['value']
    if left is None or right is None:
        return None
    if measure in RATIO_MEASURES:
        if left <= 0 or right <= 0:
            return None
        return left / right if direction == 'a_higher' else right / left
    return left - right if direction == 'a_higher' else right - left


def _opposite(effect, measure):
    if effect is None:
        return None
    return 1 / effect if measure in RATIO_MEASURES and effect else -effect


def _certainty(paired, name) -> dict:
    """The report's closed-set sentence (`report_data.certainty`) and the word inside it:
    probably, may, or cannot tell. The sentence is the report's, never rewritten here."""
    from wb_studio.report_data import certainty
    sentence = certainty(paired, name)
    word = 'probably' if ' probably ' in sentence else 'may' if ' may ' in sentence else 'cannot tell'
    return {'word': word, 'sentence': sentence}


PASS_MEASURES = ('pass_rate', 'pass_k')


def _task_values(rows, events, measure) -> dict:
    """One value per task for a non-pass measure, averaged over its evaluated attempts, from the
    same fields `wb_studio.measures` reads (`known_cost`, `unexpected_changes`, `DONE_CLAIM`,
    `model_finished` events). A task with no known value on a side is left out of the pairing."""
    from collections import defaultdict
    from wb_studio import measures as M
    turns = defaultdict(int)
    for e in events:
        if e.get('type') == 'model_finished' and e.get('task') and e.get('model'):
            turns[(e['task'], e['model'])] += 1
    per_task = defaultdict(list)
    for r in M.evaluated(rows):
        if measure == 'cost_per_pass':
            value = M.known_cost(r)
        elif measure == 'violations':
            value = len(r.get('unexpected_changes') or [])
        elif measure == 'false_completion':
            value = None if r.get('passed') else float(M.claims_completion(r))
        else:
            value = turns.get((r.get('task'), r.get('model')), 0)
        if value is not None:
            per_task[r.get('task')].append(float(value))
    return {t: sum(v) / len(v) for t, v in per_task.items()}


def measure_certainty(a_rows, b_rows, events, measure, direction, name) -> dict:
    """Certainty for a claim about cost, turns, violations or false completion: a paired sign test
    (`measures.sign_test`) over the tasks both sides have a value for, counting a task as a win when
    its difference runs in the claimed direction. The words and thresholds are the report's
    (`report_data.certainty`): probably under 0.05, may under 0.5, else cannot tell; fewer than
    three differing tasks cannot tell. Lucas, 10 Sep: cost claims no longer ride on the pass test."""
    from wb_studio import measures as M
    mine, theirs = _task_values(a_rows, events, measure), _task_values(b_rows, events, measure)
    common = sorted(set(mine) & set(theirs))
    wins = sum((mine[t] > theirs[t]) if direction == 'a_higher' else (mine[t] < theirs[t]) for t in common)
    losses = sum((mine[t] < theirs[t]) if direction == 'a_higher' else (mine[t] > theirs[t]) for t in common)
    p_value = M.sign_test(wins, losses)
    paired = {'comparable': bool(common), 'reason': None if common else 'no task has a known value on both sides', 'tasks': len(common),
              'wins': wins, 'losses': losses, 'ties': len(common) - wins - losses, 'p_value': p_value, 'measure': measure,
              'per_task': [{'task': t, 'setup': mine[t], 'baseline': theirs[t], 'delta': mine[t] - theirs[t]} for t in common]}
    words = {'cost_per_pass': 'costs', 'violations': 'changes outside the task', 'false_completion': 'claims to be done when it is not', 'turns': 'takes model turns'}
    more = 'more' if direction == 'a_higher' else 'less'
    if not (wins or losses) or p_value is None or p_value >= 0.5 or (wins + losses) < 3:
        return {'word': 'cannot tell', 'paired': paired, 'sentence': 'These runs cannot tell the two apart on ' + words.get(measure, measure) + '.'}
    if (wins > losses) != True:
        return {'word': 'cannot tell', 'paired': paired, 'sentence': 'The tasks lean the other way on ' + words.get(measure, measure) + ', so this claim is not what the runs show.'}
    word = 'probably' if p_value < 0.05 else 'may'
    return {'word': word, 'paired': paired, 'sentence': 'It ' + word + ' ' + words.get(measure, measure) + ' ' + more + ' than ' + str(name) + ' on these tasks (' + str(wins) + ' of ' + str(len(common)) + ' tasks).'}


def settle(studio, record) -> dict:
    """Settle a hypothesis on the grader's recorded results alone.

    untested        nothing finished covers both setups on the population.
    invalid         a run being settled on did not finish normally, any attempt of either side
                    stopped on an infrastructure failure, or Bare was not shown alongside; the
                    three rules `genesis.hypothesis_outcome` already applies to a card's run.
    supported       the effect in the stated direction is at least the minimum effect and the
                    report's certainty word is "probably".
    not_supported   the effect is in the opposite direction by at least the minimum effect.
    inconclusive    everything else, with the reason it fell short.

    Covering runs are pooled only when they share the frozen task set (`report_data.task_set_id`).
    Otherwise the most recent one settles it and the others are listed under `others`.
    """
    from wb_studio import measures as M
    record = check_hypothesis(record)
    covered = coverage(studio, record)
    result = {'covered': covered, 'others': [], 'sides': {'a': None, 'b': None}, 'paired': None,
              'certainty': None, 'effect': None, 'minimum_effect': record['minimum_effect'],
              'measure': record['measure'], 'direction': record['direction'], 'tags': [],
              'basis': 'Recorded grader results only; the minimum effect is '
                       + ('a ratio' if record['measure'] in RATIO_MEASURES else "a difference in the measure's own units") + '.'}
    if not covered:
        return {**result, 'outcome': 'untested',
                'reason': 'No finished run has both setups on these tasks; nothing has tested this yet.'}
    hashes = {c['task_set'] for c in covered}
    used = covered if len(hashes) == 1 else [covered[0]]
    result['others'] = [c for c in covered if c not in used]
    result['tags'] = ['[rec:run:' + c['run'] + ']' for c in used]
    jobs = {job['id']: job for job in studio.jobs()}
    broken = next((c for c in used if c['status'] != 'completed'), None)
    if broken:
        return {**result, 'outcome': 'invalid',
                'reason': 'The run "' + broken['title'] + '" did not finish normally (' + str(broken['status']) + '), so it cannot settle anything.'}
    without_bare = next((c for c in used if not c['bare_shown']), None)
    if without_bare:
        return {**result, 'outcome': 'invalid',
                'reason': 'Bare was not shown alongside in the run "' + without_bare['title'] + '"; without it the comparison has no floor.'}
    tasks = set(population_tasks(studio, record))
    a_rows, b_rows, events = [], [], []
    for entry in used:
        job = jobs[entry['run']]
        a_rows += [r for r in setup_rows(job, record['comparison']['a']) if r.get('task') in tasks]
        b_rows += [r for r in setup_rows(job, record['comparison']['b']) if r.get('task') in tasks]
        if record['measure'] == 'turns':
            events += studio.events(entry['run'])  # the only measure that needs the event stream
    infrastructure = sum(M.is_infrastructure(r) for r in a_rows + b_rows)
    if infrastructure:
        return {**result, 'outcome': 'invalid',
                'reason': str(infrastructure) + ' attempt(s) of ' + str(len(a_rows) + len(b_rows))
                          + ' stopped on an infrastructure failure; that is not a model-quality measurement.'}
    a_side, b_side = _side(a_rows, events, record['measure']), _side(b_rows, events, record['measure'])
    if record['measure'] in PASS_MEASURES:
        paired = M.paired(a_rows, b_rows)
        certainty = _certainty(paired, record['comparison']['b']['id'])
    else:
        certainty = measure_certainty(a_rows, b_rows, events, record['measure'], record['direction'], record['comparison']['b']['id'])
        paired = certainty.pop('paired')
    effect = _effect(a_side, b_side, record['measure'], record['direction'])
    result.update(sides={'a': a_side, 'b': b_side}, paired=paired, certainty=certainty, effect=effect)
    minimum = record['minimum_effect']
    size = 'The effect is ' + ('not known for both sides' if effect is None else format(effect, '.3g')) \
           + ', against a minimum of ' + format(minimum, '.3g') + '.'
    if effect is None:
        return {**result, 'outcome': 'inconclusive', 'reason': size + ' ' + certainty['sentence']}
    if effect >= minimum and certainty['word'] == 'probably':
        return {**result, 'outcome': 'supported', 'reason': size + ' ' + certainty['sentence']}
    if _opposite(effect, record['measure']) >= minimum:
        return {**result, 'outcome': 'not_supported',
                'reason': 'The effect runs the other way, by at least the minimum. ' + size + ' ' + certainty['sentence']}
    short = 'the effect is under the minimum' if effect < minimum else 'the effect is large enough but the runs cannot separate the sides with confidence'
    return {**result, 'outcome': 'inconclusive', 'reason': size + ' Not settled because ' + short + '. ' + certainty['sentence']}


# --- the smallest plan that would settle it ----------------------------------------------

def _tokens_per_attempt(studio) -> dict:
    """Median input and output tokens of a recorded task attempt (`wb_studio.usage.usage_report`),
    or the stated default when history carries none."""
    from wb_studio import usage
    try:
        rows = usage.usage_report(studio)['rows']
    except (AttributeError, KeyError, OSError, ValueError):
        rows = []
    known = [r for r in rows if r.get('input') is not None and r.get('output') is not None]
    if not known:
        return {**DEFAULT_TOKENS, 'attempts': 0,
                'basis': 'No recorded attempt carries token counts, so 60,000 input and 4,000 output tokens per attempt are assumed.'}
    middle = lambda key: sorted(int(r[key]) for r in known)[len(known) // 2]
    return {'input': middle('input'), 'output': middle('output'), 'attempts': len(known),
            'basis': 'Median of ' + str(len(known)) + ' recorded task attempts.'}


def _provider(model):
    """The price table entry for a model, or the dearest one when the model is not named there;
    a ceiling that is too high refuses a launch, a ceiling that is too low stops one mid-run."""
    from wb_arms import providers
    registry = providers.REGISTRY
    if not registry:
        return None, 'The price table is empty.'
    found = registry.get(model) or next((p for p in registry.values() if p.model_id == model), None)
    if found:
        return found, 'Price table entry for ' + found.key + '.'
    dearest = max(registry.values(), key=lambda p: p.price_in + p.price_out)
    return dearest, 'No model is named on both setups, so the dearest rate card (' + dearest.key + ') sets the ceiling.'


def smallest_plan(studio, record) -> dict:
    """The smallest Studio launch payload that would settle this hypothesis.

    Task count n = ceil(4·p·(1−p)/d²) with p = 0.5 unless a covered side already gives a pass
    rate, and d the minimum effect (for cost, the ratio minus one). At least 10 tasks, never
    more than the population. `lines` comes from `genesis_autonomy.plan_lines` when the Studio
    would accept the plan, and `not_launchable` says why when it would not.
    """
    from decimal import Decimal, ROUND_UP
    from wb_arms import providers
    record = check_hypothesis(record)
    tasks = population_tasks(studio, record)
    covered = coverage(studio, record)
    share = 0.5
    if covered:
        settled = settle(studio, record)
        for side in ('b', 'a'):
            value = ((settled['sides'].get(side) or {}) or {}).get('value')
            if record['measure'] in ('pass_rate', 'pass_k') and value is not None:
                share = float(value)
                break
    d = record['minimum_effect'] - 1 if record['measure'] in RATIO_MEASURES else record['minimum_effect']
    count = max(10, math.ceil(4 * share * (1 - share) / (d * d))) if d > 0 else len(tasks)
    count = min(max(10, count), len(tasks))
    a, b = record['comparison']['a'], record['comparison']['b']
    architectures = [s['id'] for s in (a, b) if s['kind'] in ('architecture', 'monarch')]
    models = [s['model'] for s in (a, b) if s['kind'] in ('architecture', 'monarch') and s.get('model')]
    bare = [s['id'] for s in (a, b) if s['kind'] == 'bare']
    notes = []
    if not architectures:
        architectures = ['without-monarch']
        models = list(dict.fromkeys(models + bare))
        bare = []
    elif not bare:
        bare = sorted({s['model'] for s in (a, b) if s.get('model')})
        if not bare:
            notes.append('Neither setup names a model, so the plan carries no Bare comparison; a settlement needs one, so name the model on each setup.')
    proposal = {'title': record['claim'][:140], 'tasks': tasks[:count], 'architectures': sorted(dict.fromkeys(architectures)),
                'models': sorted(dict.fromkeys(models)), 'track': 'agentic-request'}
    if bare:
        proposal['bare_models'] = sorted(dict.fromkeys(bare))
    if (record['measure'] == 'pass_rate' and record['direction'] == 'a_higher'
            and a['kind'] in ('architecture', 'monarch') and b['kind'] in ('architecture', 'monarch')
            and 0 < record['minimum_effect'] <= 1):
        proposal['goal'] = {'version': a['id'], 'parent_version': b['id'], 'minimum_gain': record['minimum_effect']}
    competitors = len(proposal.get('bare_models') or []) + (len(proposal['models']) if 'without-monarch' in proposal['architectures'] else 0)
    competitors += sum(max(1, len(proposal['models'])) for name in proposal['architectures'] if name != 'without-monarch')
    competitors = max(2, competitors)
    tokens = _tokens_per_attempt(studio)
    provider, price_basis = _provider(next(iter(models + bare), None))
    per_attempt = providers.cost_usd(provider, tokens['input'], 0, tokens['output']) if provider else 0.0
    ceiling = Decimal(str(per_attempt * count * competitors)).quantize(Decimal('0.01'), rounding=ROUND_UP)
    proposal['maximum_usd'] = str(max(ceiling, Decimal('0.01')))
    out = {'proposal': proposal, 'tasks': count, 'population': len(tasks), 'competitors': competitors,
           'pass_rate_assumed': share, 'tokens_per_attempt': tokens, 'price_basis': price_basis,
           'notes': notes, 'covered': len(covered),
           'basis': 'n = ceil(4·p·(1−p)/d²) with p = ' + format(share, '.3g') + ' and d = ' + format(d, '.3g')
                    + '; the ceiling is ' + str(count) + ' tasks × ' + str(competitors) + ' competitors at the rate card.'}
    try:
        from wb_studio.genesis_autonomy import plan_lines
        out['lines'] = plan_lines(studio, proposal)
    except Exception as exc:  # a plan preview never fails the tool; it says why it cannot run
        out['lines'] = None
        out['not_launchable'] = 'The Studio would refuse this plan today: ' + (str(exc) or type(exc).__name__)
    return out


# --- the tools ----------------------------------------------------------------------------

def _card(genesis, identity):
    try:
        return genesis.read('cards', identity)
    except (FileNotFoundError, OSError):
        raise ValueError('No research card is called ' + str(identity) + '.')


def _record_of(genesis, payload):
    """The record from the payload, or the one written on a card."""
    if payload.get('record') is not None:
        return check_hypothesis(payload['record']), None
    identity = payload.get('card')
    if not identity:
        raise ValueError('Give the hypothesis record, or the id of the card that carries one.')
    card = _card(genesis, identity)
    if not card.get('hypothesis'):
        raise ValueError('Card ' + str(identity) + ' carries no hypothesis record. Write one with hypothesis_check first.')
    return check_hypothesis(card['hypothesis']), card


def _settle_tool(genesis, payload):
    record, card = _record_of(genesis, payload)
    result = settle(genesis.studio, record)
    if card is None:
        return result
    current = _card(genesis, card['id'])
    history = list(current.get('settlements') or [])
    before = current.get('settlement')
    if before and before.get('outcome') != result.get('outcome'):
        history.append({'outcome': before.get('outcome'), 'reason': str(before.get('reason') or '')[:300],
                        'valid_to': datetime.now(timezone.utc).isoformat(), 'superseded_by': result.get('outcome')})  # A3: a belief is invalidated, not deleted
    try:
        saved = genesis.card({**current, 'hypothesis': record, 'settlement': result, 'settlements': history})
    except ValueError as exc:
        return {**result, 'card': card['id'], 'card_written': False, 'card_reason': str(exc)}
    if saved.get('settlement') != result:
        return {**result, 'card': card['id'], 'card_written': False,
                'card_reason': 'This card has a dispatched proposal, so only its stage and body can change; the settlement was not written onto it.'}
    return {**result, 'card': card['id'], 'card_written': True, 'card_revision': saved['revision']}


def _plan_tool(genesis, payload):
    record, card = _record_of(genesis, payload)
    plan = smallest_plan(genesis.studio, record)
    return {**plan, 'card': card['id']} if card else plan


TOOLS = {
    'hypothesis_check': lambda genesis, payload: check_hypothesis(payload.get('record') if payload.get('record') is not None else payload),
    'hypothesis_settle': _settle_tool,
    'hypothesis_plan': _plan_tool,
}

PROTOCOL = (
    'Hypotheses are records, not sentences. Use hypothesis_check to turn a claim into a record '
    '(claim, population, comparison of two setups, measure, direction, minimum effect, optional prior) '
    'and to find out exactly which field is wrong before you save it on a card. Use hypothesis_settle '
    'with a card id or a record to learn whether the grader\'s recorded runs already answer it: it returns '
    'supported, not supported, inconclusive, untested or invalid, each with its reason, the interval on each '
    'side, the paired test when the tasks are identical, and a [rec:run:...] tag for every run it used. Use '
    'hypothesis_plan when nothing covers the hypothesis, to get the smallest run that would settle it, ready '
    'for propose_experiment. The Studio computes every number in these results; write none of them yourself, '
    'and cite the tags rather than adding attempts up by hand.'
)
