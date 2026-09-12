"""Complete batch evidence receipts and all-or-nothing report analysis writes."""
import copy
import json

import pytest

from wb_studio import genesis_reports as reports
from wb_studio.report_batches import digest, encoded, packet
from wb_studio.report_trace import project
from tests.test_genesis_reports import lab, active, as_worker, finish


def prepared(lab, monkeypatch, response_size=1800):
    native = {'status': 'available', 'episode_id': 'episode-0', 'source': 'trace.jsonl',
              'sha256': 'original-file-hash', 'events': [
        {'line': 1, 'record': {'kind': 'tool', 'tool': 'api_search', 'arguments': {'query': 'contacts'},
                             'status': 'completed', 'result': {'catalogue': 'x' * 4000}}},
        {'line': 2, 'record': {'kind': 'tool', 'tool': 'api_fetch', 'arguments': {'id': 'contact-1'},
                             'status': 'error', 'result': {'error': 'denied', 'detail': 'z' * response_size}}}]}
    monkeypatch.setattr('wb_studio.report_trace.capture', lambda studio, job: [native, {'status': 'unavailable'}])
    reports.start(lab, {'run': 'run1', 'maximum_usd': '1'})
    as_worker(lab)
    return native


def analyses():
    return [{'index': index, 'expected': 'The requested contact is updated.',
        'observed': 'The recorded check ' + ('failed.' if index == 0 else 'passed.'),
        'explanation': 'The receipt records the outcome; the exact response establishes the observed tool error.',
        'mechanism': 'A tool error is observable; its upstream cause remains untested.',
        'alternatives': 'A transient failure or incorrect authorization needs a controlled comparison.',
        'confidence': 'limited', 'missing_evidence': 'No intervention isolates the cause.', 'event_ids': [index + 1]}
        for index in (0, 1)]


def saved(lab):
    state = reports._state(lab, 'run1')
    return reports._read(reports._workdir(lab, state) / 'attempts.json'), state['covered']


def test_batch_reads_required_native_records_and_records_every_attempt_once(lab, monkeypatch):
    native = prepared(lab, monkeypatch)
    page = reports.read_batch(lab, {'run': 'run1'})
    assert page['indexes'] == [0, 1] and page['next_after'] is None
    first, second = page['attempts'][0]['native']['events']
    assert first['complete'] is False and first['result_preview']['complete'] is False
    assert first['result_preview']['characters'] > len(first['result_preview']['text'])
    assert first['record']['arguments'] == {'query': 'contacts'}
    assert second['complete'] is True and second['full_read_required'] is True
    assert second['record'] == native['events'][1]['record']
    assert second['record_sha256'] == digest(native['events'][1]['record'])
    result = reports.record_batch(lab, {'run': 'run1', 'batch_sha256': page['batch_sha256'], 'attempts': analyses()})
    assert result['saved_indexes'] == [0, 1] and result['covered'] == 2
    assert 'attempts' not in result and len(encoded(result)) < 400
    rows, covered = saved(lab)
    assert covered == 2 and [rows[str(i)]['event_ids'] for i in (0, 1)] == [[1], [2]]
    finish(lab)
    assert active(lab)['purpose'].endswith(':author')


@pytest.mark.parametrize('corruption', ['missing', 'duplicate', 'foreign', 'boolean', 'citation', 'confidence', 'empty', 'nested_run', 'not_objects', 'hash'])
def test_bad_batch_never_partially_overwrites_existing_analysis(lab, monkeypatch, corruption):
    prepared(lab, monkeypatch)
    page = reports.read_batch(lab, {'run': 'run1'})
    payload = {'run': 'run1', 'batch_sha256': page['batch_sha256'], 'attempts': analyses()}
    reports.record_batch(lab, payload)
    before = copy.deepcopy(saved(lab))
    payload['attempts'][0]['explanation'] = 'A replacement that must not commit when another row is invalid.'
    if corruption == 'missing': payload['attempts'].pop()
    elif corruption == 'duplicate': payload['attempts'][1]['index'] = 0
    elif corruption == 'foreign': payload['attempts'][1]['index'] = 2
    elif corruption == 'boolean': payload['attempts'][1]['index'] = True
    elif corruption == 'citation': payload['attempts'][1]['event_ids'] = [1]
    elif corruption == 'confidence': payload['attempts'][1]['confidence'] = 'certain'
    elif corruption == 'empty': payload['attempts'][1]['mechanism'] = ' '
    elif corruption == 'nested_run': payload['attempts'][1]['run'] = 'other'
    elif corruption == 'not_objects': payload['attempts'][1] = 'invalid'
    elif corruption == 'hash': payload['batch_sha256'] = 'forged'
    with pytest.raises(ValueError):
        reports.record_batch(lab, payload)
    assert saved(lab) == before


def test_batch_paging_requires_every_character_and_credits_exact_events_only_at_completion(lab, monkeypatch):
    prepared(lab, monkeypatch, response_size=210000)
    first = reports.read_batch(lab, {'run': 'run1'})
    assert first['part'] == 'batch' and first['next_after'] == 200000
    assert first['total_characters'] > 210000
    state = reports._state(lab, 'run1')
    assert state['reads'] == {} and state.get('native_reads', {}) == {}
    payload = {'run': 'run1', 'batch_sha256': first['batch_sha256'], 'attempts': analyses()}
    tail = reports.read_batch(lab, {'run': 'run1', 'after': 200001})
    assert tail['next_after'] is None
    with pytest.raises(ValueError, match='entire assigned batch'):
        reports.record_batch(lab, payload)
    missing = reports.read_batch(lab, {'run': 'run1', 'after': 200000, 'limit': 1})
    restored = json.loads(first['fragment'] + missing['fragment'] + tail['fragment'])
    assert digest(restored) == first['batch_sha256']
    assert restored['attempts'][0]['native']['events'][1]['record']['result']['detail'] == 'z' * 210000
    reports.record_batch(lab, payload)
    state = reports._state(lab, 'run1')
    assert state['reads'] == {'0': [1], '1': [2]}
    assert state['native_reads']['0:2'][0][0] == 0
    assert saved(lab)[1] == 2


@pytest.mark.parametrize('action', ['read_batch', 'record_batch'])
@pytest.mark.parametrize('identity', ['foreign_run', 'old_worker', 'author'])
def test_batch_operations_enforce_run_current_worker_and_role(lab, monkeypatch, action, identity):
    prepared(lab, monkeypatch)
    page = reports.read_batch(lab, {'run': 'run1'})
    payload = {'run': 'run1', 'batch_sha256': page['batch_sha256'], 'attempts': analyses()}
    if identity == 'foreign_run': payload['run'] = 'different'
    elif identity == 'old_worker': lab.context.turn = 'stale-turn'
    else:
        reports.record_batch(lab, payload)
        finish(lab); as_worker(lab)
    before = copy.deepcopy(saved(lab))
    with pytest.raises(ValueError):
        getattr(reports, action)(lab, payload)
    assert saved(lab) == before


@pytest.mark.parametrize('indexes', [[1], [1, 0], [0, 0], [0, True], [0, 2], '0,1'])
def test_batch_read_cannot_select_other_or_partial_assignment(lab, monkeypatch, indexes):
    prepared(lab, monkeypatch)
    with pytest.raises(ValueError, match='complete assigned indexes'):
        reports.read_batch(lab, {'run': 'run1', 'indexes': indexes})
    assert reports._state(lab, 'run1')['reads'] == {}


def test_compact_projection_deduplicates_success_prose_and_does_not_copy_unassigned_or_host_data():
    source = {'task': 't', 'model': 'monarch@version', 'passed': False, 'termination': 'completed',
        'event_ids': [7], 'checks': [{'check_index': 0, 'title': 'Repeated successful prose', 'passed': True},
            {'check_index': 1, 'title': 'Required row missing', 'passed': False}],
        'requirements': [{'check_index': 1, 'expected': 'invoice-9', 'passed': False}],
        'story': {'went_right': ['Repeated successful prose']}, 'narrative': 'Repeated successful prose',
        'scope_respected': False, 'unexpected_changes': [{'path': 'contacts/2', 'operation': 'delete'}]}
    capture = {'checked': {'attempts': [source]}, 'briefs': {'t': 'Update invoice-9.'},
        'events': [{'id': 7, 'type': 'result', 'checks': source['checks']}, {'id': 8, 'secret': 'UNASSIGNED'}],
        'job': {'host_api_key': 'HOST-SECRET'}}
    value = packet(capture, [0])
    serialized = encoded(value)
    assert all(text not in serialized for text in ('Repeated successful prose', 'UNASSIGNED', 'HOST-SECRET'))
    row = value['attempts'][0]
    assert row['checks']['passed_indexes'] == [0]
    assert row['checks']['failed_or_unknown'] == [{'check_index': 1, 'expected': 'invoice-9', 'passed': False, 'title': 'Required row missing'}]
    assert row['unexpected_changes'] == source['unexpected_changes'] and row['termination'] == 'completed'
    assert row['events'][0]['omitted_check_fields'] == ['checks']
    assert row['events'][0]['sha256'] == digest(capture['events'][0])
    assert value['briefs']['t']['value'] == 'Update invoice-9.'


def test_summary_draft_does_not_credit_or_repeat_previous_attempts(lab, monkeypatch):
    prepared(lab, monkeypatch)
    page = reports.read_batch(lab, {'run': 'run1'})
    reports.record_batch(lab, {'run': 'run1', 'batch_sha256': page['batch_sha256'], 'attempts': analyses()})
    finish(lab); as_worker(lab)
    summary = reports.read_draft(lab, {'run': 'run1', 'summary_only': True})
    assert summary['attempts'] == [] and summary['attempts_omitted'] is True
    assert summary['total_attempts'] == 2 and summary['next_after'] is None
    assert reports._state(lab, 'run1')['draft_reads']['author'] == []

@pytest.mark.parametrize('missing', ['event', 'native'])
def test_batch_write_rechecks_exact_event_and_native_coverage(lab, monkeypatch, missing):
    prepared(lab, monkeypatch)
    page = reports.read_batch(lab, {'run': 'run1'})
    state = reports._state(lab, 'run1')
    if missing == 'event': state['reads']['1'] = []
    else: state['native_reads']['0:2'] = [[1, 200000]]
    reports._save(lab, state)
    with pytest.raises(ValueError, match='every event|full native response'):
        reports.record_batch(lab, {'run': 'run1', 'batch_sha256': page['batch_sha256'], 'attempts': analyses()})
    assert saved(lab) == ({}, 0)


def test_106_attempts_finish_as_14_batch_reads_and_writes(lab):
    job = lab.studio.job.return_value
    job['results'] = [dict(job['results'][i % 2]) for i in range(106)]
    lab.studio.events.return_value = [{'id': i + 1, 'task': 't1', 'model': row['model'], 'type': 'result'}
                                    for i, row in enumerate(job['results'])]
    reports.start(lab, {'run': 'run1', 'maximum_usd': '1'})
    batches = []
    while active(lab)['purpose'].endswith(':analysis'):
        as_worker(lab)
        reports.evidence(lab, {'run': 'run1'})
        summary = reports.read_draft(lab, {'run': 'run1', 'summary_only': True})
        assert summary['attempts'] == []
        page = reports.read_batch(lab, {'run': 'run1'})
        assert page['next_after'] is None
        batches.append(page['indexes'])
        rows = [{**analyses()[i % 2], 'index': i, 'event_ids': [i + 1]} for i in page['indexes']]
        receipt = reports.record_batch(lab, {'run': 'run1', 'batch_sha256': page['batch_sha256'], 'attempts': rows})
        assert receipt['saved_indexes'] == page['indexes']
        finish(lab)
    assert len(batches) == 14 and [i for group in batches for i in group] == list(range(106))
    rows, covered = saved(lab)
    assert covered == 106 and set(rows) == {str(i) for i in range(106)}
    assert active(lab)['purpose'].endswith(':author')
