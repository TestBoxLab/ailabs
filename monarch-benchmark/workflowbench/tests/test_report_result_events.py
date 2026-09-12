"""Imported result notifications retain exact attempt identity across repetitions."""
from types import SimpleNamespace

from wb_studio.failure_analysis import analysis


def studio(results, events):
    return SimpleNamespace(tasks={},
        job=lambda identity: {'id': identity, 'results': results,
                              'settings': {'models': ['monarch'], 'tasks': ['simple.example']}},
        events=lambda identity: events)


def row(episode, passed=False):
    return {'task': 'simple.example', 'model': 'monarch', 'episode_id': episode,
            'passed': passed, 'termination': 'completed',
            'checks': [{'type': 'requested_result', 'passed': passed}], 'unexpected_changes': []}


def event(identity, episode, kind='result'):
    return {'id': identity, 'task': 'simple.example', 'model': 'monarch',
            'episode_id': episode, 'type': kind}


def test_reordered_repetitions_match_episode_ids_and_result_receipts_support_checks():
    found = analysis(studio([row('second', True), row('first')],
                           [event(10, 'first'), event(20, 'second'), event(30, 'first')]), 'run')['attempts']
    assert [attempt['event_ids'] for attempt in found] == [[20], [10, 30]]
    assert found[0]['observed_facts'][0]['event_ids'] == [20]
    assert found[1]['observed_facts'][0]['event_ids'] == [10, 30]
    assert found[1]['earliest_supported_evidence'] == {
        'event_id': 10, 'type': 'result', 'text': 'Recorded failure verdict.'}


def test_a_missing_episode_receipt_never_borrows_another_identified_repetition():
    found = analysis(studio([row('missing'), row('recorded')],
                           [event(10, 'recorded', 'attempt_finished')]), 'run')['attempts']
    assert found[0]['event_ids'] == []
    assert found[1]['event_ids'] == [10]


def test_native_traces_without_episode_ids_keep_completion_boundary_fallback():
    first, second = row('first'), row('second', True)
    events = [{k: v for k, v in event(identity, episode, 'attempt_finished').items() if k != 'episode_id'}
              for identity, episode in [(10, 'first'), (20, 'second')]]
    found = analysis(studio([first, second], events), 'run')['attempts']
    assert [attempt['event_ids'] for attempt in found] == [[10], [20]]
