"""Full-text ingest and extraction with quotes, offline: every fetch and every model turn is faked,
nothing is ever sent and no page is ever requested that the source link did not name."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_ingest as ingest
from wb_studio.genesis import Genesis


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [{'id': 'cheap', 'available': True}])
    studio = SimpleNamespace(directory=tmp_path, create=Mock(), jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=Mock())
    studio.genesis = Genesis(studio)
    studio.genesis.chat = Mock(side_effect=[{'id': 't1'}, {'id': 't2'}])
    return studio.genesis


@pytest.fixture
def pages(monkeypatch):
    """The fake internet: a map of URL to page, and the list of URLs that were actually asked for."""
    store, asked = {}, []

    def read(url, timeout=20):
        asked.append(url)
        if url not in store:
            raise OSError('404 ' + url)
        return store[url]
    monkeypatch.setattr(ingest, '_read', read)
    return SimpleNamespace(store=store, asked=asked)


def html_page(title, body):
    return ('<html><head><title>' + title + '</title><style>p{color:red}</style></head><body>'
            '<script>ignore()</script><p>' + body + '</p>'
            '<a href="https://elsewhere.example/trap">a link the fetcher must not follow</a></body></html>')


# -- the three fetchers -----------------------------------------------------------

def test_an_arxiv_link_is_read_through_its_html_rendering(pages):
    pages.store['https://arxiv.org/html/2501.01234'] = html_page('Memory for agents', 'We report 62 of 100 tasks passed. ' * 20)
    out = ingest.fetch_source('https://arxiv.org/abs/2501.01234v2')
    assert out['kind'] == 'arxiv-html' and out['title'] == 'Memory for agents'
    assert '62 of 100 tasks passed' in out['text'] and 'ignore()' not in out['text']
    assert 'HTML rendering' in out['note'] and 'nothing cut' in out['note']
    assert pages.asked == ['https://arxiv.org/html/2501.01234']  # the link inside the page was never followed
    # a pdf link is the same paper
    pages.asked.clear()
    assert ingest.fetch_source('https://arxiv.org/pdf/2501.01234.pdf')['kind'] == 'arxiv-html'


def test_an_arxiv_paper_with_no_rendering_falls_back_to_the_abstract_and_says_so(pages):
    pages.store['https://arxiv.org/html/2501.09999'] = html_page('No HTML', 'No HTML is available for this paper.')
    pages.store['https://arxiv.org/abs/2501.09999'] = html_page('Old paper', 'Abstract: we measured cost per passed task. ' * 20)
    out = ingest.fetch_source('https://arxiv.org/abs/2501.09999')
    assert out['kind'] == 'arxiv-abstract' and 'cost per passed task' in out['text']
    assert 'abstract page' in out['note'] and 'not the whole paper' in out['note']
    assert pages.asked == ['https://arxiv.org/html/2501.09999', 'https://arxiv.org/abs/2501.09999']


def test_a_github_repository_is_read_through_its_readme(pages):
    pages.store['https://raw.githubusercontent.com/letta-ai/letta/master/README.md'] = '# Letta\n\nSleep-time compute.\n'
    out = ingest.fetch_source('https://github.com/letta-ai/letta')
    assert out['kind'] == 'github' and out['title'] == 'letta-ai/letta'
    assert out['text'] == '# Letta\n\nSleep-time compute.\n'  # markdown is kept as written
    assert 'README' in out['note'] and 'master' in out['note']
    assert pages.asked == ['https://raw.githubusercontent.com/letta-ai/letta/main/README.md',
                           'https://raw.githubusercontent.com/letta-ai/letta/master/README.md']


def test_a_plain_page_gives_its_visible_text_and_the_cap_cuts_and_says_so(pages, monkeypatch):
    monkeypatch.setattr(ingest, 'LIMIT', 500)
    pages.store['https://example.com/blog/agents'] = html_page('Agents at work', 'sentence about tools. ' * 200)
    out = ingest.fetch_source('https://example.com/blog/agents')
    assert out['kind'] == 'page' and len(out['text']) == 500
    assert out['note'].endswith('cut to 500 of 4,449 characters.')


def test_a_page_that_cannot_be_read_says_so_and_is_not_a_crash(pages):
    out = ingest.fetch_source('https://example.com/gone')
    assert out['text'] == '' and 'could not be read' in out['note']
    with pytest.raises(ValueError, match='http or https link'):
        ingest.fetch_source('not a link')


# -- the extraction turn ----------------------------------------------------------

TEXT = ('We evaluate MemAgent on 100 tasks and pass 62 of them, against 41 for the baseline. '
        'The method stores a summary after every episode. We did not test beyond one week.')


def saved(genesis, url='https://example.com/blog/memagent', title='MemAgent', topic=None):
    return genesis.library.add({'title': title, 'url': url, 'source_type': 'blog', 'topic': topic})


def answer(**cells):
    columns = {'claim': {'text': 'Summaries raise the pass rate.', 'quote': 'pass 62 of them, against 41 for the baseline'},
               'method': {'text': 'A summary after every episode.', 'quote': 'stores a summary after every episode'},
               'dataset': {'text': '100 tasks.', 'quote': 'We evaluate MemAgent on 100 tasks'},
               'result_numbers': {'text': '62 of 100 against 41 of 100.', 'quote': '62 of them, against 41'},
               'limitations': {'text': 'One week only.', 'quote': 'We did not test beyond one week.'},
               'contradictions': {'text': 'None found.', 'quote': ''},
               'monarch_meaning': {'text': 'Try episode summaries in the memory tier.', 'quote': 'stores a summary'},
               'topic': {'text': 'Agentic memory', 'quote': 'MemAgent'}}
    columns.update(cells)
    return '```json\n' + __import__('json').dumps({'columns': columns}) + '\n```'


def finished(turn_id, message, answer_text, status='completed'):
    return {'id': turn_id, 'purpose': ingest.PURPOSE, 'status': status, 'answer': answer_text, 'message': message,
            'card': None, 'events': [{'type': 'failed', 'message': 'The allowance is spent.'}] if status == 'failed' else []}


def ingested(genesis, pages, record, text=TEXT):
    pages.store[record['url']] = html_page(record['title'], text)
    out = ingest.ingest(genesis, record['id'])
    return out, genesis.chat.call_args.args[0]['message']


def test_ingest_stores_the_text_and_starts_one_extraction_turn_with_the_schema(genesis, pages):
    record = saved(genesis)
    out, message = ingested(genesis, pages, record)
    payload = genesis.chat.call_args.args[0]
    assert payload['purpose'] == 'Genesis extraction' and payload['model'] == 'cheap' and payload['maximum_usd'] == '0.30'
    assert len(message) <= 16000 and 'Library record: ' + record['id'] in message
    for column in ingest.COLUMNS:
        assert '"' + column + '"' in message
    assert 'Agentic memory' in message and TEXT in message
    stored = genesis.library.read(record['id'])
    assert stored['original'] == ingest._visible(pages.store[record['url']])[1] and stored['full_text_available']
    assert stored['status'] == 'saved'  # Saved until the extraction comes back
    assert out['turn'] == 't1' and out['characters'] == len(stored['original'])


def test_the_columns_are_written_with_verified_quotes_and_an_unverifiable_one_is_nulled(genesis, pages):
    record = saved(genesis)
    _, message = ingested(genesis, pages, record)
    invented = {'limitations': {'text': 'It only ran for a day.', 'quote': 'we ran the whole benchmark for a single day'}}
    ingest.ON_TURN(genesis, finished('t1', message, answer(**invented)))

    stored = genesis.library.read(record['id'])
    assert stored['status'] == 'analyzed'
    columns = stored['columns']
    assert set(columns) == set(ingest.COLUMNS)
    assert columns['claim']['quote'] == 'pass 62 of them, against 41 for the baseline'
    assert columns['limitations']['quote'] is None and columns['limitations']['note'] == ingest.NOT_FOUND
    assert columns['limitations']['text'] == 'It only ran for a day.'  # the text is kept, only the quote is dropped
    assert 'Claim: Summaries raise the pass rate.' in stored['analysis']
    assert ingest.NOT_FOUND in stored['analysis']
    logged = genesis.autonomy.tail(5)[0]
    assert logged['kind'] == 'extracted' and logged['status'] == 'done'
    assert logged['quoted'] == 6 and logged['columns'] == 8 and logged['unverified'] == ['limitations']

    read = genesis.tool('read_columns', {'library': record['id']})
    assert read['columns'] == columns and read['note'] == 'Cite a column by its quote.'


def test_a_quote_whose_whitespace_was_rewrapped_still_counts_as_found(genesis, pages):
    record = saved(genesis)
    _, message = ingested(genesis, pages, record)
    wrapped = {'claim': {'text': 'The pass rate rises.', 'quote': 'pass 62 of them,\n   against 41'}}
    ingest.ON_TURN(genesis, finished('t1', message, answer(**wrapped)))
    assert genesis.library.read(record['id'])['columns']['claim']['quote'] == 'pass 62 of them,\n   against 41'


def test_a_failed_extraction_leaves_the_source_saved_with_the_reason(genesis, pages):
    record = saved(genesis)
    _, message = ingested(genesis, pages, record)
    ingest.ON_TURN(genesis, finished('t1', message, '', status='failed'))
    stored = genesis.library.read(record['id'])
    assert stored['status'] == 'saved' and stored.get('columns') is None
    logged = genesis.autonomy.tail(5)[0]
    assert logged['kind'] == 'extracted' and logged['status'] == 'failed' and logged['reason'] == 'The allowance is spent.'

    ingest.ON_TURN(genesis, finished('t1', message, 'I could not read the paper.'))
    assert genesis.library.read(record['id'])['status'] == 'saved'
    assert genesis.autonomy.tail(5)[0]['reason'] == 'The extraction model did not answer with JSON.'


def test_the_topic_moves_when_the_model_names_one_and_stays_when_it_invents_one(genesis, pages):
    record = saved(genesis, title='A note on storage', topic='Other')
    assert record['topic'] == 'Other'
    _, message = ingested(genesis, pages, record)
    ingest.ON_TURN(genesis, finished('t1', message, answer()))
    moved = genesis.library.read(record['id'])
    assert moved['topic'] == 'Agentic memory' and moved['topic_source'] == 'genesis'
    assert genesis.autonomy.tail(6)[0]['topic'] == 'Agentic memory'

    other = saved(genesis, url='https://example.com/blog/second', title='Second note', topic='Other')
    _, second = ingested(genesis, pages, other)
    ingest.ON_TURN(genesis, finished('t2', second, answer(topic={'text': 'Prompt alchemy', 'quote': 'MemAgent'})))
    stayed = genesis.library.read(other['id'])
    assert stayed['topic'] == 'Other' and stayed['status'] == 'analyzed'
    assert stayed['columns']['topic']['note'].startswith('The topic named is not one of the library topics')


def test_a_source_with_no_link_or_no_text_is_refused_in_words(genesis, pages):
    record = genesis.library.add({'title': 'Dropped without a link'})
    with pytest.raises(ValueError, match='no link to fetch'):
        ingest.ingest(genesis, record['id'])
    empty = saved(genesis, url='https://example.com/gone')
    with pytest.raises(ValueError, match='Nothing could be read'):
        ingest.ingest(genesis, empty['id'])
    assert genesis.library.read(empty['id'])['full_text_available'] is False


def test_read_columns_tells_the_model_to_ingest_a_source_that_has_none(genesis):
    record = saved(genesis)
    out = genesis.tool('read_columns', {'library': record['id']})
    assert out['columns'] is None and 'ingest_source' in out['note']
    assert genesis.tool('read_columns', {'library': 'nosuch'})['error'].startswith('No library record')
