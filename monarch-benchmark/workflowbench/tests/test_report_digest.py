"""Editorial digests cover every row; citations still require exact full analyses."""
import copy
import json

import pytest

from wb_studio import genesis_reports as reports
from wb_studio.report_digest import packet
from wb_studio.report_batches import digest
from tests.test_genesis_reports import lab, as_worker, finish, reading


def draft():
    return {'run': 'run1', 'summary': 'The recorded Monarch attempt failed.',
        'what_went_right': 'The comparison passed.', 'what_went_wrong': 'Monarch failed its check.',
        'why': 'The record establishes the outcome, with causal uncertainty.',
        'next_experiment': 'Repeat with one controlled change.', 'limitations': 'No intervention was recorded.',
        'findings': [{'title': 'Recorded failure', 'explanation': 'The exact attempt receipt failed.',
                      'kind': 'fact', 'event_ids': [1]}]}


def ready(lab):
    reports.start(lab, {'run': 'run1', 'maximum_usd': '1'})
    reading(lab, 0); reading(lab, 1); finish(lab); as_worker(lab)


def author(lab):
    reports.read_digest(lab, {'run': 'run1'})
    reports.read_draft(lab, {'run': 'run1', 'indexes': [0], 'include_draft': False})
    reports.write_draft(lab, draft())
    finish(lab); as_worker(lab)


def verdict(lab):
    state = reports._state(lab, 'run1')
    return json.dumps({'verdict': 'accept', 'issues': [], 'reason': 'Claims and qualifications match the inspected record.',
        'draft_sha256': state['draft_sha256'], 'evidence_sha256': state['evidence_sha256']})


def test_digest_marks_every_clipped_field_and_keeps_original_analysis_unchanged():
    rows = {'0': {'index': 0, 'task': 't', 'model': 'monarch', 'passed': False, 'confidence': 'limited',
        'event_ids': [7], 'expected': 'full expected', 'observed': 'full observed',
        'explanation': 'e' * 300, 'mechanism': 'm' * 300, 'alternatives': 'a' * 300, 'missing_evidence': 'x' * 300}}
    before = copy.deepcopy(rows)
    value = packet(rows, {'patterns': {}})
    row = dict(zip(value['columns'], value['rows'][0]))
    assert row['clipped_fields'] == ['explanation', 'mechanism', 'alternatives', 'missing_evidence']
    assert [len(row[k]) for k in row['clipped_fields']] == [120, 100, 80, 80]
    assert row['event_ids'] == [7] and value['full_analysis_sha256'] == digest(rows)
    assert rows == before


def test_author_requires_complete_digest_and_full_cited_rows_but_not_unrelated_full_rows(lab):
    ready(lab)
    with pytest.raises(ValueError, match='analysis digest'):
        reports.write_draft(lab, draft())
    first = reports.read_digest(lab, {'run': 'run1', 'limit': 20})
    assert first['next_after'] == 20
    with pytest.raises(ValueError, match='analysis digest'):
        reports.write_draft(lab, draft())
    reports.read_digest(lab, {'run': 'run1'})
    with pytest.raises(ValueError, match='every cited attempt'):
        reports.write_draft(lab, draft())
    reports.read_draft(lab, {'run': 'run1', 'indexes': [0], 'include_draft': False})
    reports.write_draft(lab, draft())
    state = reports._state(lab, 'run1')
    assert state['draft_reads']['author'] == [0] and state['revision'] == 1


def test_review_reads_exact_draft_digest_and_all_citations_then_publishes_complete_details(lab):
    ready(lab); author(lab)
    digest_page = reports.read_digest(lab, {'run': 'run1'})
    assert digest_page['cited_indexes'] == [0] and digest_page['attempt_count'] == 2
    reports.read_draft(lab, {'run': 'run1', 'summary_only': True})
    full = reports.read_draft(lab, {'run': 'run1', 'indexes': [0], 'include_draft': False})
    assert full['draft'] is None and full['attempts'][0]['index'] == 0
    finish(lab, verdict(lab))
    result = reports.published(lab.studio, 'run1')
    assert [a['index'] for a in result['attempts']] == [0, 1]
    assert result['attempts'][0]['expected'] == 'A VIP contact exists.'
    assert result['attempts'][1]['missing_evidence'] == 'No isolated intervention.'


@pytest.mark.parametrize('missing', ['digest', 'draft', 'citation', 'stale_digest', 'stale_row'])
def test_review_cannot_accept_missing_or_changed_digest_draft_or_cited_row(lab, missing):
    ready(lab); author(lab)
    if missing != 'digest': reports.read_digest(lab, {'run': 'run1'})
    if missing != 'draft': reports.read_draft(lab, {'run': 'run1', 'summary_only': True})
    if missing != 'citation': reports.read_draft(lab, {'run': 'run1', 'indexes': [0], 'include_draft': False})
    state = reports._state(lab, 'run1')
    if missing == 'stale_digest': state['digest_reads']['review']['analysis_sha256'] = 'stale'
    if missing == 'stale_row': state['full_row_reads']['review']['0'] = 'stale'
    reports._save(lab, state)
    finish(lab, verdict(lab))
    assert reports.published(lab.studio, 'run1') is None
    assert reports.status(lab, {'run': 'run1'})['stage'] == 'failed'


@pytest.mark.parametrize('indexes', [[True], [0, 0], [2], [], '0'])
def test_targeted_analysis_read_rejects_invalid_or_ambiguous_indexes(lab, indexes):
    ready(lab)
    with pytest.raises(ValueError, match='unique recorded indexes'):
        reports.read_draft(lab, {'run': 'run1', 'indexes': indexes, 'include_draft': False})
