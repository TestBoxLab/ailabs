import copy
from collections import Counter

from wb_orchestrator.prototype_campaign import ROOT, build_manifest, paired_schedule
from wb_orchestrator.prototype_controls import qualify
from wb_world.episode import load_task_file


def test_prompt_derived_controls_do_not_read_assertions_for_answers():
    for path in ['simple.email_sf_contact_city_update.json', 'simple.sf_opp_closed_won.json']:
        task = load_task_file(ROOT/'tasks'/path)
        result = qualify(task)
        assert result['positive_control'] == 'passed'
        assert result['collateral_control'] == 'rejected'
        assert result['status'] == 'qualified'
        assert result['evidence']['positive']['calls']
        poisoned = copy.deepcopy(task)
        for assertion in poisoned['info']['assertions']:
            if 'value' in assertion:
                assertion['value'] = 'poisoned answer'
        inputs = lambda r: [(c['method'], c['url'], c['body']) for c in r['evidence']['positive']['calls']]
        assert inputs(qualify(poisoned)) == inputs(result)


def test_invoice_wrong_business_values_are_detected_as_grader_gap():
    task = load_task_file(ROOT/'tasks/tier-medium/simple.invoice_airtable_slack.json')
    result = qualify(task)
    assert result['positive_control'] == 'passed'
    assert result['semantic_counterexample'] == 'accepted'
    assert result['status'] == 'rejected'
    assert result['evidence']['wrong_invoice']['grade']['passed']


def test_paired_schedule_is_seeded_balanced_and_preserves_every_comparison():
    manifest = build_manifest()
    schedule = paired_schedule(manifest['tasks'], manifest['phases'], seed=20260907)
    assert schedule == manifest['schedule']
    assert schedule == paired_schedule(manifest['tasks'], manifest['phases'], seed=20260907)
    assert schedule != paired_schedule(manifest['tasks'], manifest['phases'], seed=20260908)
    assert len(schedule) == 66
    for phase in manifest['phases']:
        rows = [r for r in schedule if r['phase'] == phase['name']]
        n = len(phase['configurations'])
        for i in range(0,len(rows), n):
            block = rows[i:i+n]
            assert len({(r['task_id'],r['repetition']) for r in block}) == 1
            assert {r['configuration'] for r in block} == set(phase['configurations'])
        for arm in phase['configurations']:
            positions = Counter(r['position'] for r in rows if r['configuration'] == arm)
            assert max(positions.values()) - min(positions.values()) <= 1
