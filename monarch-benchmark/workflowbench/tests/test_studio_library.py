"""Offline contracts for the Genesis research library: what was read, what was
analyzed, where it was used, and the weekly ledger import."""
import hashlib
import json

import pytest

from wb_studio.app import REPO, ROOT, Studio
from wb_studio.library import Library
from wb_world.episode import load_suite
from tests.test_studio_app import request, server_for


@pytest.fixture
def library(tmp_path):
    return Library(tmp_path / 'library')


def source(**changes):
    return {'title': 'Repeated-trial reliability', 'authors': ['Yao', 'Shunyu'], 'source_type': 'paper',
            'url': 'https://arxiv.org/abs/2406.12045', 'published_at': '2024-06-17', 'discovered_at': '2026-09-07',
            'topic': 'Reliability and safety', 'abstract': 'Final database-state evaluation over repeated trials.', **changes}


def test_add_saves_record_with_defaults_and_is_idempotent_by_url(library):
    record = library.add(source())
    assert record['status'] == 'saved'
    assert record['full_text_available'] is False
    assert record['original'] is None and record['analysis'] is None
    assert record['used_in'] == [] and record['contradicts'] == []
    assert record['authors'] == ['Yao', 'Shunyu']
    again = library.add(source(title='Same URL, different title'))
    assert again['id'] == record['id'] and again['title'] == 'Repeated-trial reliability'
    assert [r['id'] for r in library.listing()] == [record['id']]
    with_text = library.add(source(original='Full paper text'))
    assert with_text['id'] == record['id'] and with_text['full_text_available'] is True
    assert with_text['original'] == 'Full paper text'
    assert Library(library.root).read(record['id'])['full_text_available'] is True


@pytest.mark.parametrize('bad', [{'title': ''}, {'title': 'x' * 301}, {'source_type': 'tweet'},
                                 {'published_at': 'June 2024'}, {'status': 'analyzed'}, {'discovered_at': 'yesterday'}])
def test_add_rejects_bad_fields_and_only_saved_status(library, bad):
    with pytest.raises(ValueError):
        library.add(source(**bad))
    assert library.listing() == []


def test_saved_abstract_without_full_text_can_never_be_marked_analyzed(library):
    record = library.add(source())
    before = library.path(record['id']).read_bytes()
    with pytest.raises(ValueError, match='[Ff]ull text'):
        library.analyze(record['id'], {'analysis': 'Looks solid'})
    assert library.path(record['id']).read_bytes() == before
    assert library.read(record['id'])['status'] == 'saved'


def test_analyze_needs_text_and_moves_saved_to_analyzed_once_full_text_exists(library):
    record = library.add(source(original='Full text of the paper'))
    with pytest.raises(ValueError, match='analysis'):
        library.analyze(record['id'], {'analysis': '  '})
    assert library.read(record['id'])['status'] == 'saved'
    analyzed = library.analyze(record['id'], {'analysis': 'Pass^k needs k > 1; our runs use k = 1.'})
    assert analyzed['status'] == 'analyzed'
    assert analyzed['analysis'] == 'Pass^k needs k > 1; our runs use k = 1.'
    assert analyzed['analyzed_at']
    assert Library(library.root).read(record['id'])['status'] == 'analyzed'


@pytest.mark.parametrize('filters,expected', [
    ({}, ['old', 'new', 'undated']),
    ({'status': 'analyzed'}, ['new']),
    ({'topic': 'Evaluation and benchmarks'}, ['old', 'undated']),
    ({'published_from': '2025-01-01'}, ['new']),
    ({'published_to': '2024-12-31'}, ['old']),
    ({'published_from': '2020-01-01', 'published_to': '2024-12-31'}, ['old']),
    ({'discovered_from': '2026-09-08'}, ['new', 'undated']),
    ({'discovered_to': '2026-09-07'}, ['old']),
    ({'discovered_from': '2026-09-08', 'topic': 'Evaluation and benchmarks'}, ['undated']),
])
def test_listing_filters_by_both_dates_topic_and_status(library, filters, expected):
    library.add(source(id='old', url='https://a.example/old', published_at='2024-06-17', discovered_at='2026-09-07', topic='Evaluation and benchmarks'))
    library.add(source(id='new', url='https://a.example/new', published_at='2026-05-01', discovered_at='2026-09-08', topic='Reliability and safety', original='text'))
    library.add(source(id='undated', url='https://a.example/undated', published_at=None, discovered_at='2026-09-09', topic='Evaluation and benchmarks'))
    library.analyze('new', {'analysis': 'Recent and relevant.'})
    assert sorted(r['id'] for r in library.listing(**filters)) == sorted(expected)


def test_used_in_is_appended_to_the_historical_version_and_never_removed(library):
    record = library.add(source())
    first = library.use(record['id'], {'version_id': 'blueprint.recovery.v1', 'blueprint': 'recovery',
                                       'where': 'Worker retry loop', 'why': 'Paper shows retries recover tool errors',
                                       'experiment_ids': ['run-1']})
    assert first['used_in'][0]['version_id'] == 'blueprint.recovery.v1'
    assert first['used_in'][0]['experiment_ids'] == ['run-1']
    library.use(record['id'], {'version_id': 'blueprint.recovery.v2', 'blueprint': 'recovery',
                               'where': 'Removed', 'why': 'v2 drops the retry loop', 'experiment_ids': []})
    library.add(source(original='Full text arrives later'))
    library.analyze(record['id'], {'analysis': 'Still cited.'})
    kept = Library(library.root).read(record['id'])
    assert [u['version_id'] for u in kept['used_in']] == ['blueprint.recovery.v1', 'blueprint.recovery.v2']
    assert kept['used_in'][0]['experiment_ids'] == ['run-1']
    with pytest.raises(ValueError):
        library.use(record['id'], {'version_id': '', 'blueprint': 'recovery'})
    with pytest.raises(ValueError):
        library.use(record['id'], {'version_id': 'v3', 'blueprint': 'recovery', 'experiment_ids': 'run-1'})
    assert len(library.read(record['id'])['used_in']) == 2


def test_new_evidence_flag_when_a_later_source_on_the_same_topic_contradicts(library):
    library.add(source(id='earlier', url='https://a.example/earlier', published_at='2024-06-17', topic='Reliability and safety', original='text'))
    library.analyze('earlier', {'analysis': 'Repeated trials are stable.'})
    library.add(source(id='other-topic', url='https://a.example/other', published_at='2026-08-01', topic='UI and design', contradicts=['earlier']))
    library.add(source(id='older', url='https://a.example/older', published_at='2023-01-01', topic='Reliability and safety', contradicts=['earlier']))
    flags = {r['id']: r['new_evidence'] for r in library.listing()}
    assert flags == {'earlier': False, 'other-topic': False, 'older': False}
    library.add(source(id='later', url='https://a.example/later', published_at='2026-08-01', topic='Reliability and safety', contradicts=['earlier']))
    flags = {r['id']: r['new_evidence'] for r in library.listing()}
    assert flags['earlier'] is True and flags['later'] is False
    with pytest.raises(ValueError):
        library.add(source(id='dangling', url='https://a.example/dangling', contradicts=['missing']))


def ledger_lines():
    return [
        {'id': 'source-tau-bench-2024', 'date': '2026-09-07', 'url': 'https://arxiv.org/abs/2406.12045',
         'discovery': 'Primary-source search and abstract retrieval', 'access_status': 'abstract_read',
         'motivation': 'Repeated reliability and user interaction', 'finding': 'Repeated-trial reliability.',
         'next_question': 'Read the full methodology.'},
        {'id': 'source-keshav-2007', 'date': '2026-09-07', 'url': 'https://cs.uwaterloo.ca/keshav-paper-reading.pdf',
         'discovery': 'Slack research direction', 'access_status': 'sections_read', 'motivation': 'Establish cumulative research workflow',
         'finding': 'Use staged reading.', 'next_question': 'Which surveys?'},
        {'id': 'ui-research-2026-09-08-keshav-ui-followup', 'date': '2026-09-08', 'url': 'https://cs.uwaterloo.ca/keshav-paper-reading.pdf',
         'discovery': 'Direct retrieval', 'access_status': 'full_text_read', 'motivation': 'Design comparable architecture experiments',
         'finding': 'Three-pass reading.', 'next_question': 'Expose reading depth.', 'artifact': 'docs/AI-LABS-UI-RESEARCH-2026-09-08.md'},
        {'id': 'ui-research-2026-09-08-braintrust-comparison', 'date': '2026-09-08', 'url': 'https://www.braintrust.dev/docs/evaluate/compare-experiments',
         'discovery': 'Official documentation direct retrieval', 'access_status': 'sections_read', 'motivation': 'Design comparable architecture experiments',
         'finding': 'Persistent baseline and paired diffs.', 'next_question': 'Explicit Bare manifest.'},
    ]


def test_import_ledger_is_idempotent_by_url_and_leaves_the_ledger_untouched(library, tmp_path):
    ledger = tmp_path / 'search-log.jsonl'
    ledger.write_text(''.join(json.dumps(row) + '\n' for row in ledger_lines()) + '\n', encoding='utf8')
    before = ledger.read_bytes()
    summary = library.import_ledger(ledger)
    assert summary == {'imported': 3, 'existing': 1}
    rows = {r['id']: r for r in library.listing()}
    assert set(rows) == {'source-tau-bench-2024', 'source-keshav-2007', 'ui-research-2026-09-08-braintrust-comparison'}
    assert all(r['status'] == 'saved' for r in rows.values())
    assert rows['source-tau-bench-2024']['discovered_at'] == '2026-09-07'
    assert rows['source-tau-bench-2024']['full_text_available'] is False
    assert rows['source-tau-bench-2024']['source_type'] == 'paper'
    assert rows['source-tau-bench-2024']['topic'] == 'Reliability and safety'
    assert rows['source-tau-bench-2024']['abstract'] == 'Repeated-trial reliability.'
    assert rows['source-tau-bench-2024']['ledger']['access_status'] == 'abstract_read'
    assert rows['source-keshav-2007']['full_text_available'] is True, 'a later ledger line read the full text of the same URL'
    assert rows['source-keshav-2007']['discovered_at'] == '2026-09-07'
    assert rows['ui-research-2026-09-08-braintrust-comparison']['source_type'] == 'docs'
    assert library.import_ledger(ledger) == {'imported': 0, 'existing': 4}
    assert len(library.listing()) == 3
    assert ledger.read_bytes() == before


def test_real_ledger_imports_without_modification(library):
    ledger = REPO / 'research' / 'search-log.jsonl'
    digest = hashlib.sha256(ledger.read_bytes()).hexdigest()
    first = library.import_ledger(ledger)
    assert first['imported'] >= 1
    assert library.import_ledger(ledger) == {'imported': 0, 'existing': first['imported'] + first['existing']}
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == digest


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    def forbidden_gateway(*args, **kwargs):
        pytest.fail('An offline Studio test attempted paid dispatch')
    return Studio(tmp_path / 'studio', tasks=load_suite(ROOT / 'tasks')[:1], gateway_factory=forbidden_gateway)


def test_library_endpoints_list_read_add_analyze_use_and_import(studio):
    with server_for(studio) as port:
        write = {'X-Studio-Token': studio.token, 'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'application/json'}
        status, _, body = request(port, 'POST', '/api/genesis/library', json.dumps(source(id='abstract-only')), write)
        assert status == 201 and json.loads(body)['status'] == 'saved'
        status, _, body = request(port, 'POST', '/api/genesis/library', json.dumps(source(id='full', url='https://a.example/full', topic='Evaluation and benchmarks', published_at='2026-03-01', original='Full text')), write)
        assert status == 201
        status, _, body = request(port, 'POST', '/api/genesis/library/abstract-only/analyze', json.dumps({'analysis': 'Not allowed'}), write)
        assert status == 400 and 'ull text' in json.loads(body)['error']
        status, _, body = request(port, 'POST', '/api/genesis/library/full/analyze', json.dumps({'analysis': 'Read in full.'}), write)
        assert status == 200 and json.loads(body)['status'] == 'analyzed'
        status, _, body = request(port, 'POST', '/api/genesis/library/full/use', json.dumps({'version_id': 'blueprint.x.v1', 'blueprint': 'x', 'where': 'Judge', 'why': 'Calibration', 'experiment_ids': []}), write)
        assert status == 200 and json.loads(body)['used_in'][0]['version_id'] == 'blueprint.x.v1'
        status, _, body = request(port, 'GET', '/api/genesis/library')
        data = json.loads(body)
        assert status == 200 and {r['id'] for r in data['items']} == {'abstract-only', 'full'}
        assert data['topics'][:2] == ['Agentic memory', 'Code understanding'] and data['topics'][-1] == 'Other'
        assert all('new_evidence' in r for r in data['items'])
        status, _, body = request(port, 'GET', '/api/genesis/library?status=analyzed&published_from=2026-01-01&topic=Evaluation%20and%20benchmarks')
        assert status == 200 and [r['id'] for r in json.loads(body)['items']] == ['full']
        status, _, body = request(port, 'GET', '/api/genesis/library?status=analyzed&topic=reliability')
        assert status == 200 and json.loads(body)['items'] == []
        status, _, body = request(port, 'GET', '/api/genesis/library/full')
        assert status == 200 and json.loads(body)['analysis'] == 'Read in full.'
        assert request(port, 'GET', '/api/genesis/library/missing')[0] == 404
        status, _, body = request(port, 'POST', '/api/genesis/library/import', '{}', write)
        assert status == 201 and json.loads(body)['imported'] >= 1
        assert request(port, 'POST', '/api/genesis/library', json.dumps(source(id='no-session')), {'Content-Type': 'application/json'})[0] == 403
        assert request(port, 'GET', '/api/genesis/library/no-session')[0] == 404
