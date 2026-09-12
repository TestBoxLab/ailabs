"""Report publication contracts. All model responses are deterministic fixtures."""
import copy
import json
import threading
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_results.evidence import write_json
from wb_studio import genesis_reports as reports


@pytest.fixture
def lab(tmp_path, monkeypatch):
    job = {'id': 'run1', 'status': 'completed', 'title': 'A comparison',
           'settings': {'maximum_usd': '10', 'models': ['monarch', 'bare'], 'tasks': ['t1']},
           'task_hashes': {'t1': 'frozen'}, 'results': [
               {'task': 't1', 'model': 'monarch', 'passed': False, 'termination': 'completed'},
               {'task': 't1', 'model': 'bare', 'passed': True, 'termination': 'completed'}]}
    events = [{'id': 1, 'task': 't1', 'model': 'monarch', 'type': 'attempt_finished'},
              {'id': 2, 'task': 't1', 'model': 'bare', 'type': 'attempt_finished'}]
    studio = SimpleNamespace(directory=tmp_path, job=Mock(return_value=job), events=Mock(return_value=events),
                             lock=threading.RLock(), analysis_ceiling=Decimal('1'),
                             tasks={'t1': {'prompt': [{'content': ''}, {'content': 'Create the VIP contact.'}]}},
                             ledger=Mock())
    studio.ledger.scope_committed.return_value = Decimal('0')
    studio.ledger.reservations.return_value = []
    g = SimpleNamespace(studio=studio, lock=threading.RLock(), context=threading.local(),
                        autonomy=SimpleNamespace(read=lambda: {'paused': False}, record=Mock()),
                        config=SimpleNamespace(route_for=lambda step: {'id': 'writer' if step != 'review' else 'reviewer'}, effort_for=lambda step, route=None: None),
                        allowance_allows=lambda amount: (True, None), _index=Mock(), chat=Mock())
    studio.genesis = g
    monkeypatch.setattr('wb_studio.report_budget.validate', lambda *args: {'basis': 'Fixture admission; real preflight tested separately.'})
    (tmp_path / 'run1').mkdir()
    monkeypatch.setattr(reports, 'account_for', lambda s, j, e: {'attempts': [
        {**row, 'index': i, 'event_ids': [i + 1], 'requirements': [], 'story': {}}
        for i, row in enumerate(j['results'])]})
    monkeypatch.setattr(reports, 'measures_for', lambda s, j, e: {'source': 'recorded counts'})
    return g


def active(lab):
    return lab.chat.call_args.args[0]


def finish(lab, answer='Done.', status='completed'):
    p = active(lab)
    reports.ON_TURN(lab, {**p, 'answer': answer, 'status': status})


def as_worker(lab):
    lab.context.turn = active(lab)['id']


def reading(lab, index):
    as_worker(lab)
    reports.evidence(lab, {'run': 'run1', 'attempt': index})
    return reports.record_attempt(lab, {'run': 'run1', 'index': index,
        'expected': 'A VIP contact exists.', 'observed': 'The recorded check passed.' if index else 'No VIP contact was written.',
        'explanation': 'Bare completed the write.' if index else 'Monarch stopped after reading.',
        'mechanism': 'The required write was absent.' if not index else 'Read followed by the required write.',
        'alternatives': 'No controlled intervention establishes the cause.', 'confidence': 'limited',
        'missing_evidence': 'No isolated intervention.', 'event_ids': [index + 1]})


def authored(lab):
    as_worker(lab)
    reports.read_digest(lab, {'run': 'run1'})
    reports.read_draft(lab, {'run': 'run1', 'limit': 20})
    return reports.write_draft(lab, {'run': 'run1', 'summary': 'Monarch read the record but did not complete the requested write.',
        'what_went_right': 'Bare produced the requested record.', 'what_went_wrong': 'Monarch left the request unfinished.',
        'why': 'The missing write explains the checker failure; the decision mechanism remains untested.',
        'next_experiment': 'Repeat with one controlled change to the selection instruction.',
        'limitations': 'One task cannot establish general superiority.',
        'findings': [{'title': 'Required write absent', 'explanation': 'The final event records failure.', 'kind': 'fact', 'event_ids': [1]}]})


def prepare_review(lab):
    reports.start(lab, {'run': 'run1', 'maximum_usd': '1'})
    reading(lab, 0); reading(lab, 1); finish(lab)
    authored(lab); finish(lab)


def verdict(lab, decision='accept'):
    as_worker(lab)
    reports.read_digest(lab, {'run': 'run1'})
    reports.read_draft(lab, {'run': 'run1', 'limit': 20})
    state = reports.status(lab, {'run': 'run1'})
    return json.dumps({'verdict': decision, 'issues': [] if decision == 'accept' else ['Explain the alternative.'],
                       'reason': 'Evidence and limits are explicit.', 'draft_sha256': state['draft_sha256'],
                       'evidence_sha256': state['evidence_sha256']})


def test_delegates_complete_analysis_then_reviews_and_publishes(lab):
    prepare_review(lab)
    assert [c.args[0]['purpose'].rsplit(':', 1)[-1] for c in lab.chat.call_args_list] == ['analysis', 'author', 'review']
    assert reports.published(lab.studio, 'run1') is None
    finish(lab, verdict(lab))
    saved = reports.published(lab.studio, 'run1')
    assert saved['summary'].startswith('Monarch read')
    assert [a['model'] for a in saved['attempts']] == ['monarch', 'bare']
    assert saved['review']['verdict'] == 'accept'
    assert reports.status(lab, {'run': 'run1'})['stage'] == 'published'
    assert lab.studio.ledger.reserve_run.call_count == 5
    assert sum(Decimal(c.args[1]) for c in lab.studio.ledger.reserve_run.call_args_list) == Decimal('1')


def test_missing_attempt_blocks_authoring(lab):
    reports.start(lab, {'run': 'run1'})
    reading(lab, 0); finish(lab)
    assert reports.status(lab, {'run': 'run1'})['stage'] == 'failed'
    assert 'coverage' in reports.status(lab, {'run': 'run1'})['reason'].lower()
    assert lab.chat.call_count == 1
    assert reports.published(lab.studio, 'run1') is None


def test_foreign_attempt_citation_is_rejected(lab):
    reports.start(lab, {'run': 'run1'}); reading(lab, 0)
    item = reports.read_draft(lab, {'run': 'run1'})['attempts'][0]
    with pytest.raises(ValueError, match='belong'):
        reports.record_attempt(lab, {**item, 'run': 'run1', 'event_ids': [2]})


def test_reviewer_revision_is_fixed_and_reviewed_again(lab):
    prepare_review(lab); finish(lab, verdict(lab, 'revise'))
    assert active(lab)['purpose'].endswith(':repair')
    authored(lab); finish(lab)
    assert active(lab)['purpose'].endswith(':review_again')
    finish(lab, verdict(lab))
    assert reports.published(lab.studio, 'run1')['revision'] == 2
    assert lab.chat.call_count == 5


@pytest.mark.parametrize('change', ['evidence', 'draft', 'reject', 'malformed', 'failed'])
def test_unaccepted_or_stale_work_never_publishes(lab, change):
    prepare_review(lab)
    answer = verdict(lab)
    if change == 'evidence':
        lab.studio.events.return_value.append({'id': 3, 'type': 'correction'})
    elif change == 'draft':
        answer = json.dumps({**json.loads(answer), 'draft_sha256': 'wrong'})
    elif change == 'reject': answer = verdict(lab, 'reject')
    elif change == 'malformed': answer = '{}'
    finish(lab, answer, 'failed' if change == 'failed' else 'completed')
    assert reports.published(lab.studio, 'run1') is None
    assert reports.status(lab, {'run': 'run1'})['stage'] == 'failed'


def test_duplicate_callbacks_and_start_do_not_redispatch(lab):
    reports.start(lab, {'run': 'run1'}); old = copy.deepcopy(active(lab))
    reports.start(lab, {'run': 'run1'})
    assert lab.chat.call_count == 1
    reading(lab, 0); reading(lab, 1); finish(lab)
    reports.ON_TURN(lab, {**old, 'status': 'completed', 'answer': 'Done.'})
    assert lab.chat.call_count == 2


def test_pause_or_budget_refusal_prevents_dispatch(lab):
    lab.autonomy.read = lambda: {'paused': True}
    with pytest.raises(ValueError, match='paused'): reports.start(lab, {'run': 'run1'})
    assert not lab.chat.called
    lab.autonomy.read = lambda: {'paused': False}
    lab.studio.ledger.reserve_run.side_effect = ValueError('Budget refused')
    with pytest.raises(ValueError, match='Budget'): reports.start(lab, {'run': 'run1'})
    assert not lab.chat.called


def test_empty_prose_cannot_be_submitted(lab):
    reports.start(lab, {'run': 'run1'}); reading(lab, 0); reading(lab, 1); finish(lab)
    value = authored(lab)
    with pytest.raises(ValueError, match='why'):
        reports.write_draft(lab, {**value, 'run': 'run1', 'why': ''})


def test_report_worker_cannot_launch_or_read_another_run(lab):
    from wb_studio.genesis_harness import run_tool
    reports.start(lab, {'run': 'run1'})
    turn = {**active(lab), 'status': 'running'}
    lab.read = Mock(return_value=turn)
    lab.tool = Mock()
    as_worker(lab)
    refused = run_tool(lab, 'propose_experiment', {'tasks': ['t1']}, turn['id'])
    assert 'only read' in refused['error']
    lab.tool.assert_not_called()
    with pytest.raises(ValueError, match='assigned run'):
        reports.evidence(lab, {'run': 'other'})
    with pytest.raises(ValueError, match='assigned run'):
        reports.status(lab, {'run': 'other'})


def test_reviewer_cannot_accept_an_unread_analysis(lab):
    prepare_review(lab)
    answer = verdict(lab)
    state = reports._state(lab, 'run1')
    state['digest_reads']['review']['complete'] = False
    reports._save(lab, state)
    finish(lab, answer)
    assert reports.published(lab.studio, 'run1') is None
    assert 'every page' in reports.status(lab, {'run': 'run1'})['reason']


def test_analysis_tampering_invalidates_the_review_digest(lab):
    prepare_review(lab)
    answer = verdict(lab)
    state = reports._state(lab, 'run1')
    path = reports._workdir(lab, state) / 'attempts.json'
    rows = json.loads(path.read_text())
    rows['0']['mechanism'] = 'A different explanation was inserted.'
    write_json(path, rows)
    finish(lab, answer)
    assert reports.published(lab.studio, 'run1') is None
    assert 'draft changed' in reports.status(lab, {'run': 'run1'})['reason'].lower()


def test_every_event_page_must_be_read_before_analysis(lab):
    lab.studio.events.return_value.extend([
        {'id': 3, 'task': 't1', 'model': 'monarch', 'type': 'node_started'},
        {'id': 4, 'task': 't1', 'model': 'monarch', 'type': 'node_finished'}])
    reports.start(lab, {'run': 'run1'})
    state = reports._state(lab, 'run1')
    path = reports._workdir(lab, state) / 'evidence.json'
    packet = json.loads(path.read_text())
    packet['checked']['attempts'][0]['event_ids'] = [1, 3, 4]
    write_json(path, packet)
    as_worker(lab)
    first = reports.evidence(lab, {'run': 'run1', 'attempt': 0, 'limit': 1})
    assert first['next_after'] == 1 and first['total_events'] == 3
    with pytest.raises(ValueError, match='every event page'):
        reports.record_attempt(lab, {'run': 'run1', 'index': 0})
    second = reports.evidence(lab, {'run': 'run1', 'attempt': 0, 'after': 1, 'limit': 2})
    assert [e['id'] for e in second['events']] == [3, 4]
    assert second['next_after'] is None
    assert reports._state(lab, 'run1')['reads']['0'] == [1, 3, 4]


def test_budget_admission_rolls_back_unused_holds_without_dispatch(lab):
    lab.studio.ledger.reserve_run.side_effect = [None, None, ValueError('Budget refused')]
    with pytest.raises(ValueError, match='Budget refused'):
        reports.start(lab, {'run': 'run1'})
    assert lab.chat.call_count == 0
    holds = [c.args[0] for c in lab.studio.ledger.reserve_run.call_args_list[:2]]
    assert [c.args[0] for c in lab.studio.ledger.finish_run.call_args_list] == holds


def test_finished_run_scheduler_starts_genesis_report_without_gemini_gate(lab):
    from wb_studio.app import Studio
    lab.studio.gateway_factory = None
    lab.studio.jobs = Mock(return_value=[])
    Studio.schedule_narrative(lab.studio, 'run1')
    assert active(lab)['purpose'] == 'Genesis report:run1:analysis'
    assert reports.status(lab, {'run': 'run1'})['stage'] == 'analysis'
    Studio.schedule_narrative(lab.studio, 'run1')
    assert lab.chat.call_count == 1


def test_report_procedures_are_injected_into_native_worker_prompts(lab):
    reports.start(lab, {'run': 'run1'})
    text = reports.PROMPT(lab, active(lab))
    assert 'Genesis report analysis procedure' in text
    assert 'ALL assigned attempts' in text
    assert reports.allowed_tools(active(lab)) == ('report_evidence', 'read_report_state', 'read_report_draft', 'report_status', 'read_report_batch', 'record_report_batch', 'record_report_attempt')


def test_oversized_attempt_pages_losslessly_and_requires_every_fragment(lab):
    lab.studio.events.return_value[0]['result'] = 'A' * 100000 + 'END OF RETAINED EVIDENCE'
    reports.start(lab, {'run': 'run1'}); as_worker(lab)
    first = reports.evidence(lab, {'run': 'run1', 'attempt': 0})
    assert first['part'] == 'packet' and first['next_after'] == 24000
    item = {'run': 'run1', 'index': 0, **{k: 'The record supports this statement.' for k in reports.ATTEMPT_FIELDS},
            'confidence': 'limited', 'event_ids': [1]}
    # Reading the end cannot stand in for the omitted middle.
    reports.evidence(lab, {'run': 'run1', 'attempt': 0, 'part': 'packet', 'after': 96000})
    with pytest.raises(ValueError, match='every event page'):
        reports.record_attempt(lab, item)
    fragments = [first['fragment']]
    offset = first['next_after']
    while offset is not None:
        page = reports.evidence(lab, {'run': 'run1', 'attempt': 0, 'part': 'packet', 'after': offset})
        fragments.append(page['fragment']); offset = page['next_after']
    restored = json.loads(''.join(fragments))
    assert restored['events'][0]['result'] == lab.studio.events.return_value[0]['result']
    assert reports.record_attempt(lab, item)['event_ids'] == [1]


def test_106_attempts_use_fresh_bounded_batches_before_authoring(lab):
    lab.studio.job.return_value['results'] = [
        {'task': 't1', 'model': 'bare' if i % 2 else 'monarch', 'passed': bool(i % 2), 'termination': 'completed'}
        for i in range(106)]
    lab.studio.events.return_value = [
        {'id': i + 1, 'task': 't1', 'model': 'bare' if i % 2 else 'monarch', 'type': 'attempt_finished'}
        for i in range(106)]
    reports.start(lab, {'run': 'run1', 'maximum_usd': '4'})
    first = copy.deepcopy(active(lab))
    state = reports._state(lab, 'run1')
    assert len(state['analysis_keys']) == 14
    assert lab.studio.ledger.reserve_run.call_count == 18
    assert sum(Decimal(e['maximum_usd']) for e in state['turns'].values()) == Decimal('4')
    seen = []
    for batch in range(14):
        current = active(lab)
        assert current['purpose'].endswith(':analysis')
        assert len(current['indexes']) <= 8
        seen.extend(current['indexes'])
        for index in current['indexes']:
            reading(lab, index)
        finish(lab)
        # A late callback from an earlier batch cannot advance another batch.
        if batch == 0:
            next_id = active(lab)['id']
            reports.ON_TURN(lab, {**first, 'status': 'completed', 'answer': 'Repeated delivery.'})
            assert active(lab)['id'] == next_id
    assert seen == list(range(106))
    assert active(lab)['purpose'].endswith(':author')
    assert reports.status(lab, {'run': 'run1'})['covered'] == 106
    assert len({call.args[0]['id'] for call in lab.chat.call_args_list}) == 15


def test_analyst_cannot_overwrite_another_batch(lab):
    lab.studio.job.return_value['results'] *= 5
    lab.studio.events.return_value = [
        {'id': i + 1, 'task': 't1', 'model': 'bare' if i % 2 else 'monarch', 'type': 'attempt_finished'}
        for i in range(10)]
    reports.start(lab, {'run': 'run1'}); as_worker(lab)
    reports.evidence(lab, {'run': 'run1', 'attempt': 8})
    with pytest.raises(ValueError, match='another analysis batch'):
        reports.record_attempt(lab, {'run': 'run1', 'index': 8})


def test_workers_receive_the_same_computed_chart_slices(lab):
    reports.start(lab, {'run': 'run1'})
    viewed = reports.evidence(lab, {'run': 'run1', 'section': 'patterns'})
    monarch, bare = viewed['setups']
    assert monarch['total'] == bare['total'] == 1
    assert next(s for s in bare['behavior'] if s['id'] == 'passed')['percent'] == 100
    failed = next(s for s in monarch['checks'] if s['id'] == 'unclassified')
    assert failed['count'] == 1 and failed['attempt_keys'] == ['run1:0']
    assert sum(s['percent'] for s in monarch['checks']) == 100
    assert viewed['domains'] == [{'id': 't1', 'label': 'T1'}]
    sliced = reports.evidence(lab, {'run': 'run1', 'section': 'patterns', 'domain': 't1', 'setup': 'bare'})
    assert sliced['setups'] == [bare]


def test_budget_preflight_refuses_before_any_hold_or_dispatch(lab, monkeypatch):
    def refuse(*args):
        raise ValueError('Report budget is too low; no provider request sent.')
    monkeypatch.setattr('wb_studio.report_budget.validate', refuse)
    with pytest.raises(ValueError, match='budget is too low'):
        reports.start(lab, {'run': 'run1'})
    lab.studio.ledger.reserve_run.assert_not_called()
    lab.chat.assert_not_called()


def test_long_analysis_pages_shrink_without_crediting_unreturned_attempts(lab):
    reports.start(lab, {'run': 'run1'})
    for i in range(2):
        item = reading(lab, i)
        reports.record_attempt(lab, {**item, 'run': 'run1', 'explanation': 'x' * 14000, 'mechanism': 'y' * 10000})
    finish(lab)
    draft = authored(lab)
    reports.write_draft(lab, {**draft, 'run': 'run1', 'why': 'z' * 14000, 'what_went_right': 'a' * 3000})
    finish(lab); as_worker(lab)
    first = reports.read_draft(lab, {'run': 'run1'})
    assert [a['index'] for a in first['attempts']] == [0] and first['next_after'] == 1
    assert reports._state(lab, 'run1')['draft_reads']['review'] == [0]
    last = reports.read_draft(lab, {'run': 'run1', 'after': first['next_after']})
    assert [a['index'] for a in last['attempts']] == [1] and last['next_after'] is None
    assert reports._state(lab, 'run1')['draft_reads']['review'] == [0, 1]


def test_legacy_analysis_unknown_charge_reduces_report_headroom(lab, tmp_path):
    from wb_orchestrator.budget import BudgetLedger

    ledger = BudgetLedger(tmp_path / 'legacy-budget.sqlite3')
    ledger.reserve_run('run1', '10')
    ledger.reserve('execution', '2', scope_id='run1')
    ledger.claim('execution')
    ledger.settle('execution', '2')
    ledger.finish_run('run1')
    ledger.reserve_run('run1-analysis-v1', '4')
    ledger.reserve('legacy-unknown', '3', scope_id='run1-analysis-v1')
    ledger.claim('legacy-unknown')
    ledger.settle('legacy-unknown', None, outcome='error')
    ledger.finish_run('run1-analysis-v1')
    lab.studio.ledger = ledger
    original = ledger.reservations()
    with pytest.raises(ValueError, match='remaining analysis budget'):
        reports.start(lab, {'run': 'run1', 'maximum_usd': '6'})
    assert not lab.chat.called
    assert ledger.reservations() == original
    assert len(ledger.run_reservations()) == 2
    assert ledger.status().held_usd == Decimal('3')
    reports.start(lab, {'run': 'run1', 'maximum_usd': '5'})
    assert lab.chat.call_count == 1
    assert ledger.scope_committed('run1-analysis-v1') == Decimal('3')
    assert next(r for r in ledger.reservations() if r.reservation_id == 'legacy-unknown').actual_usd is None


def test_episode_scoped_unknown_charges_reduce_report_headroom(lab, tmp_path):
    from wb_orchestrator.budget import BudgetLedger

    ledger = BudgetLedger(tmp_path / 'episode-budget.sqlite3')
    ledger.reserve('run1/episode-a/request-1', '2', scope_id='episode-a')
    ledger.settle('run1/episode-a/request-1', '2')
    ledger.reserve('run1/episode-b/request-1', '3', scope_id='episode-b')
    ledger.settle('run1/episode-b/request-1', None, outcome='error')
    ledger.reserve('run10/unrelated', '4', scope_id='episode-c')
    ledger.settle('run10/unrelated', '4')
    lab.studio.ledger = ledger
    original = ledger.reservations()
    with pytest.raises(ValueError, match='remaining analysis budget'):
        reports.start(lab, {'run': 'run1', 'maximum_usd': '6'})
    assert not lab.chat.called
    assert ledger.reservations() == original
    assert ledger.run_reservations() == []
    reports.start(lab, {'run': 'run1', 'maximum_usd': '5'})
    assert lab.chat.call_count == 1
    assert next(r for r in ledger.reservations() if r.reservation_id == 'run1/episode-b/request-1').actual_usd is None


def test_native_response_must_be_read_without_skipped_characters(lab, monkeypatch):
    raw = {'kind': 'tool', 'tool': 'api_fetch', 'arguments': {'method': 'PATCH', 'url': 'https://example.test/records/1'},
           'status': 'completed', 'result': {'body': 'retained-native-response-' * 3000, 'tail': 'exact-end'}}
    monkeypatch.setattr('wb_studio.report_trace.capture', lambda *args: [
        {'episode_id': 'first', 'status': 'available', 'source': 'first.jsonl', 'sha256': 'frozen-hash', 'events': [{'line': 3, 'record': raw}]},
        {'status': 'unavailable'}])
    reports.start(lab, {'run': 'run1'}); as_worker(lab)
    page = reports.evidence(lab, {'run': 'run1', 'attempt': 0})
    event = page['checked']['retained_trace']['events'][0]
    assert event['full_read_required'] and not event['result_preview']['complete']
    item = {'run': 'run1', 'index': 0, **{k: 'The retained evidence supports this explanation.' for k in reports.ATTEMPT_FIELDS},
            'confidence': 'limited', 'event_ids': [1]}
    with pytest.raises(ValueError, match='native_line=3'):
        reports.record_attempt(lab, item)
    end = reports.evidence(lab, {'run': 'run1', 'attempt': 0, 'native_line': 3, 'after': 60000})
    assert end['next_after'] is None
    with pytest.raises(ValueError, match='native_line=3'):
        reports.record_attempt(lab, item)
    fragments, offset = [], 0
    while offset is not None:
        full = reports.evidence(lab, {'run': 'run1', 'attempt': 0, 'native_line': 3, 'after': offset})
        fragments.append(full['fragment']); offset = full['next_after']
    assert json.loads(''.join(fragments)) == raw
    assert reports.record_attempt(lab, item)['index'] == 0
    with pytest.raises(ValueError, match='exact attempt'):
        reports.evidence(lab, {'run': 'run1', 'attempt': 1, 'native_line': 3})
