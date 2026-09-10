"""The weekly memory evaluation, hybrid retrieval and skills that write themselves, offline.
No model is called: every turn is a fake `genesis.chat` or a hand-built turn dict, the
embeddings client is a stub and the ledger is a mock that records its calls."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_arms import providers
from wb_arms.providers import Provider
from wb_studio import genesis_harness as harness
from wb_studio import genesis_memory_suite as suite
from wb_studio import genesis_skills
from wb_studio.genesis import Genesis

RECORDS = [{'kind': 'card', 'id': 'c1', 'updated_at': '2026-09-01', 'title': 'Retry caps', 'body': 'retry caps cut gateway failures'},
           {'kind': 'library', 'id': 's1', 'updated_at': '2026-09-02', 'title': 'Sleep-time compute', 'body': 'consolidation between sessions'},
           {'kind': 'turn', 'id': 't1', 'updated_at': '2026-09-03', 'title': 'A turn', 'body': 'the grader disagreed with the rubric'}]


@pytest.fixture
def genesis(tmp_path):
    studio = SimpleNamespace(directory=tmp_path, create=Mock(), jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=Mock())
    studio.genesis = Genesis(studio)
    studio.genesis.memory.index_records(RECORDS)
    return studio.genesis


def route(monkeypatch, available=True):
    monkeypatch.setattr(harness, 'model_routes', lambda: [{'id': 'fake-route', 'available': available}])


def fake_chat(genesis):
    calls = []

    def chat(payload):
        calls.append(payload)
        return {'id': payload.get('id', 'turn-' + str(len(calls))), 'purpose': payload.get('purpose')}
    genesis.chat = chat
    return calls


# ---- the weekly evaluation ------------------------------------------------------------
def test_the_evaluation_scores_a_fixture_of_answers_and_writes_the_week_file_and_the_trend(genesis, monkeypatch):
    route(monkeypatch)
    calls = fake_chat(genesis)
    started = suite.ask_eval(genesis)
    assert started['asked'] == 3 and calls[0]['purpose'] == 'Genesis memory eval' and calls[0]['maximum_usd'] == '0.50'
    asked = suite.questions(genesis)
    assert asked[1]['question'] == 'What did Sleep-time compute find?'   # a source is asked what it found
    assert asked[0]['question'] == 'Which run tested A turn?'            # everything else, which run tested it

    answer = json.dumps({'answers': [{'question': asked[0]['question'], 'tag': asked[0]['answer_tag']},
                                     {'question': asked[1]['question'], 'tag': '[rec:card:wrong]'}]})
    turn = {'id': started['turn'], 'purpose': 'Genesis memory eval', 'status': 'completed', 'answer': answer,
            'events': [{'type': 'usage', 'usage': {'prompt_tokens': 100, 'output_tokens': 20, 'cached_tokens': 0}}]}
    suite.ON_TURN(genesis, turn)
    written = json.loads(suite.eval_path(genesis, started['week']).read_text(encoding='utf8'))
    assert (written['asked'], written['right'], written['wrong'], written['unanswered']) == (3, 1, 1, 1)
    assert written['recall'] == 0.333 and written['tokens_per_answer'] == 40
    assert written['trend'] == [{'week': started['week'], 'asked': 3, 'recall': 0.333, 'wrong': 1, 'unanswered': 1, 'tokens_per_answer': 40}]
    assert suite.eval_status(genesis)['latest']['week'] == started['week']
    assert genesis.tool('memory_eval_status', {})['trend'] == written['trend']


def test_generated_questions_come_from_the_newest_records(genesis):
    fixed = suite.questions(genesis)
    assert len(fixed) == 3 and (genesis.memory.root / 'eval.json').exists()
    genesis.memory.index_records([{'kind': 'card', 'id': 'c9', 'updated_at': '2026-09-09', 'title': 'A newer card', 'body': 'newer'}])
    again = suite.questions(genesis)
    assert [q['answer_tag'] for q in again[:3]] == [q['answer_tag'] for q in fixed]  # the fixed file does not move
    assert again[3] == {'question': 'Which run tested A newer card?', 'answer_tag': '[rec:card:c9]'}


def test_the_evaluation_job_acts_only_on_sundays_and_only_inside_the_ledger(genesis, monkeypatch):
    route(monkeypatch)
    fake_chat(genesis)
    studio = genesis.studio
    studio.ledger.status.return_value = SimpleNamespace(available_usd='10.00')
    monday = __import__('datetime').datetime(2026, 9, 7, 5, 0)
    monkeypatch.setattr(suite, 'now_sao_paulo', lambda: monday)
    assert 'Sundays' in suite.weekly(studio)['reason']
    monkeypatch.setattr(suite, 'now_sao_paulo', lambda: monday.replace(day=13))  # a Sunday
    studio.ledger.status.return_value = SimpleNamespace(available_usd='0.10')
    assert 'cannot cover' in suite.weekly(studio)['reason']
    studio.ledger.status.return_value = SimpleNamespace(available_usd='10.00')
    assert suite.weekly(studio)['asked'] == 3
    assert suite.DAILY[0] == 'genesis-memory-eval' and suite.DAILY[1] == 5


# ---- hybrid retrieval -------------------------------------------------------------------
def test_hybrid_search_merges_two_ranked_lists_and_says_why(genesis):
    memory = genesis.memory
    memory.store_vectors([{'kind': 'card', 'id': 'c1', 'vector': [0.0, 1.0]},
                          {'kind': 'turn', 'id': 't1', 'vector': [1.0, 0.0]}])
    plain = memory.search('retry caps')
    assert [h['id'] for h in plain] == ['c1'] and 'why' not in plain[0]
    hybrid = memory.search('retry caps', mode='hybrid', vector=[1.0, 0.0])
    assert [(h['id'], h['why']) for h in hybrid] == [('c1', 'words: retry, caps'), ('t1', 'meaning')]
    # with no vector the hybrid mode is the words ranking alone
    assert [h['id'] for h in memory.search('retry caps', mode='hybrid')] == ['c1']


def test_record_search_stays_fts5_when_no_embedding_route_is_configured(genesis, monkeypatch):
    route(monkeypatch, available=False)
    assert suite.embed(genesis, ['anything']) is None
    hits = suite.record_search(genesis, {'query': 'retry caps'})
    assert [h['id'] for h in hits] == ['c1'] and 'why' not in hits[0]
    assert suite.index_vectors(genesis)['embedded'] == 0
    genesis.studio.ledger.reserve.assert_not_called()


def test_the_embedding_path_reserves_before_sending_and_settles_from_the_receipt(genesis, monkeypatch, tmp_path):
    route(monkeypatch)
    providers.register(Provider(key='fake-route', model_id='fake-embed-1', key_env='WB_FAKE_KEY', adapter='openai',
                                price_in=1.0, price_cached=0.1, price_out=2.0))
    monkeypatch.setattr(providers, 'DEFAULT_MODELS_DIR', tmp_path)
    order, sent = [], []
    genesis.studio.ledger = Mock()
    for name in ('reserve', 'claim', 'settle'):
        getattr(genesis.studio.ledger, name).side_effect = (lambda n: lambda *a, **k: order.append((n, a)))(name)

    class Client:
        embeddings = SimpleNamespace(create=lambda **kw: (sent.append(kw), SimpleNamespace(
            data=[SimpleNamespace(embedding=[1.0, 0.0]) for _ in kw['input']], usage=SimpleNamespace(prompt_tokens=1_000_000)))[1])
    monkeypatch.setattr(suite, '_client', lambda provider: Client())

    try:
        with pytest.raises(ValueError) as refused:   # no embedding price in the model file
            suite.embed(genesis, ['hello'])
        assert 'names no embedding price' in str(refused.value)
        assert order == []
        (tmp_path / 'fake-route.yaml').write_text('usd_per_million: {input: 1.0, output: 2.0, embedding: 0.02}\n', encoding='utf8')
        assert suite.embed(genesis, ['hello', 'there']) == [[1.0, 0.0], [1.0, 0.0]]
        assert [n for n, _ in order] == ['reserve', 'claim', 'settle']   # reserved before the request, settled after it
        assert sent[0]['model'] == 'fake-embed-1' and sent[0]['input'] == ['hello', 'there']
        assert float(order[2][1][1]) == 0.02                          # 1,000,000 tokens at $0.02 per million
        assert suite.index_vectors(genesis)['vectors'] == 3
    finally:
        providers.REGISTRY.pop('fake-route', None)


# ---- skills that write themselves --------------------------------------------------------
def accepted_card(genesis):
    return genesis.card({'id': 'card-1', 'title': 'Retry caps help', 'stage': 'review',
                         'review': {'status': 'done', 'verdict': 'accept', 'round': 1}})


def test_a_new_skill_is_reviewed_before_it_is_written(genesis, monkeypatch):
    route(monkeypatch)
    calls = fake_chat(genesis)
    card = accepted_card(genesis)
    suite.ON_TURN(genesis, {'id': 'w1', 'purpose': 'Genesis watcher', 'status': 'completed', 'card': card['id'], 'events': []})
    assert calls[0]['purpose'] == 'Genesis skill' and 'card-1' in calls[0]['message']
    suite.ON_TURN(genesis, {'id': 'w2', 'purpose': 'Genesis watcher', 'status': 'completed', 'card': card['id'], 'events': []})
    assert len(calls) == 1  # one question per card

    ask_turn = {'id': calls[0]['id'], 'purpose': 'Genesis skill', 'status': 'completed', 'events': [],
                'answer': json.dumps({'new': True, 'name': 'read-a-run', 'text': 'Applies: run\nRead the grader first.'})}
    suite.ON_TURN(genesis, ask_turn)
    assert (genesis.skills.root / 'pending' / 'read-a-run.md').exists()
    assert genesis.skills.listing() == []                      # nothing is a skill before the review
    assert calls[1]['purpose'] == 'Genesis skill review'

    refused = {'id': calls[1]['id'], 'purpose': 'Genesis skill review', 'status': 'completed', 'events': [],
               'answer': json.dumps({'verdict': 'revise', 'issues': [], 'reason': 'Name the record it rests on.'})}
    suite.ON_TURN(genesis, refused)
    assert genesis.skills.listing() == [] and genesis.autonomy.tail(1)[0]['kind'] == 'skill-refused'

    accept = {**refused, 'answer': json.dumps({'verdict': 'accept', 'issues': [], 'reason': 'It is a procedure.'})}
    suite.ON_TURN(genesis, accept)
    assert [s['name'] for s in genesis.skills.listing()] == ['read-a-run']
    assert not (genesis.skills.root / 'pending' / 'read-a-run.md').exists()
    written = genesis.autonomy.tail(1)[0]
    assert written['kind'] == 'skill' and written['by'] == 'genesis' and written['reviewed'] is True


def test_no_procedure_no_skill_and_an_unaccepted_card_is_never_asked(genesis, monkeypatch):
    route(monkeypatch)
    calls = fake_chat(genesis)
    plain = genesis.card({'id': 'card-2', 'title': 'No review here', 'stage': 'review'})
    genesis_skills.after_turn(genesis, {'id': 'w1', 'purpose': 'Genesis watcher', 'status': 'completed', 'card': plain['id']})
    assert calls == []
    card = accepted_card(genesis)
    genesis_skills.after_turn(genesis, {'id': 'w2', 'purpose': 'Genesis watcher', 'status': 'completed', 'card': card['id']})
    genesis_skills.after_turn(genesis, {'id': calls[0]['id'], 'purpose': 'Genesis skill', 'status': 'completed',
                                        'answer': '{"new": false}', 'events': []})
    assert len(calls) == 1 and genesis.autonomy.tail(1)[0]['kind'] == 'skill-none'
