"""Full-text ingest and extraction with quotes (feature 022, design section 7).

A source is fetched whole, not in a 600-character preview: arXiv through its HTML rendering,
GitHub through the README, anything else through its visible text, capped per source. The text
becomes the record's `original`. One extraction turn then fills a fixed set of columns, each with
the quote it rests on, and every quote is checked against the original before it is written: a
column whose quote is not in the text keeps its text and loses its quote. Only then is the source
Analyzed.

The only network call here is `_read`, and it is only ever given a URL derived from the source's
own link: a link found inside a fetched page is never followed.
"""
from __future__ import annotations

import html
import os
import re
from urllib.request import Request, urlopen

from wb_studio import library
from wb_studio.genesis_reviewer import json_answer

PURPOSE = 'Genesis extraction'
COLUMNS = ('claim', 'method', 'dataset', 'result_numbers', 'limitations', 'contradictions',
           'monarch_meaning', 'topic')
LABELS = {'claim': 'Claim', 'method': 'Method', 'dataset': 'Dataset', 'result_numbers': 'Result numbers',
          'limitations': 'Limitations', 'contradictions': 'Contradictions', 'monarch_meaning': 'What it means for Monarch',
          'topic': 'Topic'}
LIMIT = 200_000          # characters of text kept per source
MAX_BYTES = 4_000_000    # raw bytes read per request; enough HTML for LIMIT characters of text
MIN_TEXT = 200           # below this an arXiv rendering is a placeholder, not a paper
NOT_FOUND = 'This quote is not in the fetched text, so it is not carried.'
ARXIV = re.compile(r'arxiv\.org/(?:abs|pdf|html)/([\w.\-]+?)(?:v\d+)?(?:\.pdf)?/?$', re.I)
GITHUB = re.compile(r'github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$', re.I)
MARKER = re.compile(r'^Library record: ([a-zA-Z0-9_-]{1,80})$', re.M)


def cap() -> str:
    """The per-source ceiling of one extraction turn."""
    return os.environ.get('STUDIO_GENESIS_EXTRACTION_USD', '0.30')


# -- fetching ---------------------------------------------------------------------

def _read(url, timeout=20) -> str:
    """One URL as text. The only network call in this module; faked in tests."""
    with urlopen(Request(url, headers={'User-Agent': 'AILabs-Genesis/1.0 (research intake)'}), timeout=timeout) as response:
        return response.read(MAX_BYTES).decode(response.headers.get_content_charset() or 'utf8', 'replace')


def _visible(raw: str):
    """(title, all visible text) of a page, as `genesis_watcher.fetch_page` reads it but whole."""
    title = re.search(r'<title[^>]*>(.*?)</title>', raw, re.S | re.I)
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', raw, flags=re.S | re.I)
    text = html.unescape(re.sub(r'<[^>]+>', ' ', text))
    return (html.unescape(' '.join(title[1].split()))[:300] or None) if title else None, ' '.join(text.split())


def _cap(text: str):
    """The text within the per-source cap, and the words the note uses for its size."""
    whole = len(text)
    if whole <= LIMIT:
        return text, f'{whole:,} characters, nothing cut'
    return text[:LIMIT], f'cut to {LIMIT:,} of {whole:,} characters'


def _try(url, timeout):
    try:
        return _read(url, timeout)
    except Exception:  # a page that cannot be read is a fallback, not a failure
        return None


def _arxiv(identity, timeout) -> dict:
    tried = []
    for kind, url, what in (('arxiv-html', 'https://arxiv.org/html/' + identity, 'the HTML rendering'),
                            ('arxiv-abstract', 'https://arxiv.org/abs/' + identity, 'the abstract page')):
        tried.append(url)
        raw = _try(url, timeout)
        if raw is None:
            continue
        title, text = _visible(raw)
        if len(text) < MIN_TEXT:
            continue  # a paper with no rendering answers with a placeholder page
        text, size = _cap(text)
        note = 'Fetched ' + what + ' at ' + url + ': ' + size + '.'
        if kind == 'arxiv-abstract':
            note += ' The HTML rendering was not readable, so this is the abstract, not the whole paper.'
        return {'title': title, 'text': text, 'kind': kind, 'note': note}
    return {'title': None, 'text': '', 'kind': 'arxiv',
            'note': 'Neither ' + ' nor '.join(tried) + ' could be read; the PDF text is not fetched here.'}


def _github(owner, repo, timeout) -> dict:
    for branch in ('main', 'master'):
        url = 'https://raw.githubusercontent.com/' + owner + '/' + repo + '/' + branch + '/README.md'
        raw = _try(url, timeout)
        if not raw or not raw.strip():
            continue
        text, size = _cap(raw)
        return {'title': owner + '/' + repo, 'text': text, 'kind': 'github',
                'note': 'Fetched the README of ' + owner + '/' + repo + ' on ' + branch + ' at ' + url + ': ' + size + '.'}
    return {'title': owner + '/' + repo, 'text': '', 'kind': 'github',
            'note': 'No README.md was readable on main or master for ' + owner + '/' + repo + '.'}


def _page(url, timeout) -> dict:
    raw = _try(url, timeout)
    if raw is None:
        return {'title': None, 'text': '', 'kind': 'page', 'note': 'The page at ' + url + ' could not be read.'}
    title, text = _visible(raw)
    text, size = _cap(text)
    return {'title': title, 'text': text, 'kind': 'page',
            'note': 'Fetched the visible text of ' + url + ': ' + size + '.'}


def fetch_source(url, timeout=20) -> dict:
    """`{title, text, kind, note}` for one source link. arXiv abs and pdf links go to the HTML
    rendering and fall back to the abstract page; a GitHub repository goes to its README; anything
    else to its visible text. Only URLs derived from this link are ever fetched."""
    url = str(url or '').strip()
    if not re.fullmatch(r'https?://\S{1,2000}', url):
        raise ValueError('Give the source as an http or https link.')
    paper = ARXIV.search(url)
    if paper:
        return _arxiv(paper[1], timeout)
    repo = GITHUB.search(url)
    if repo:
        return _github(repo[1], repo[2], timeout)
    return _page(url, timeout)


# -- the extraction turn ----------------------------------------------------------

SCHEMA = ('Answer with one JSON object and nothing else, one entry per column, each with the quote '
          'it rests on, copied exactly from the source text:\n'
          '{"columns": {' + ', '.join('"' + c + '": {"text": "...", "quote": "..."}' for c in COLUMNS) + '}}\n'
          'text is your own sentence; quote is a passage copied word for word from the source text below, '
          'and a quote that is not in it is dropped. topic\'s text is one of: ' + ', '.join(library.TOPICS) + '.')


def _message(record, text) -> str:
    head = ('Library record: ' + record['id'] + '\n'
            'Title: ' + str(record.get('title') or '') + '\n'
            'URL: ' + str(record.get('url') or '') + '\n'
            'Read this source and fill the extraction columns.\n\n' + SCHEMA + '\n\nSource text:\n')
    return head + text[:LIMIT]  # an extraction turn takes the whole source (R7); `Genesis.chat` allows 220,000 characters for it


def ingest(genesis, library_id, card=None) -> dict:
    """Fetch a source in full, store it as the record's original, and start one extraction turn."""
    record = genesis.library.read(library_id)
    url = str(record.get('url') or '').strip()
    if not url:
        raise ValueError('Library record ' + str(library_id) + ' has no link to fetch.')
    fetched = fetch_source(url)
    if not fetched['text'].strip():
        raise ValueError('Nothing could be read from ' + url + '. ' + fetched['note'])
    record = genesis.library.set_original(library_id, fetched['text'])
    route = genesis.config.route_for('extraction')
    if not route:
        raise ValueError('No model route is available for extraction.')
    turn = genesis.chat({'message': _message(record, fetched['text']), 'model': route['id'],
                         'maximum_usd': cap(), 'purpose': PURPOSE, 'card': card})
    genesis.autonomy.record('ingested', card=card, library=library_id, turn=turn['id'],
                            source_kind=fetched['kind'], characters=len(fetched['text']), note=fetched['note'])
    return {'library': library_id, 'turn': turn['id'], 'kind': fetched['kind'],
            'characters': len(fetched['text']), 'note': fetched['note'],
            'status': 'The extraction is reading the source. Read the columns back with read_columns.'}


def _found(quote, original, flat) -> bool:
    """A quote is verified when it is in the original, either as written or with its whitespace
    rewrapped, which is how a model usually copies a passage out of a page."""
    return bool(quote) and (quote in original or ' '.join(quote.split()) in flat)


def read_columns_of(answer, original) -> dict:
    """The answer's columns, each `{text, quote}`, with every quote checked against the original."""
    data = json_answer(answer, 'The extraction model')
    given = data.get('columns') if isinstance(data.get('columns'), dict) else data
    if not isinstance(given, dict):
        raise ValueError('The extraction model did not answer with a columns object.')
    flat = ' '.join(str(original or '').split())
    out = {}
    for name in COLUMNS:
        cell = given.get(name)
        if not isinstance(cell, dict):
            cell = {'text': cell if isinstance(cell, str) else '', 'quote': None}
        text = str(cell.get('text') or '').strip()[:2000]
        quote = str(cell.get('quote') or '').strip()[:2000]
        entry = {'text': text, 'quote': quote if _found(quote, original or '', flat) else None}
        if quote and entry['quote'] is None:
            entry['note'] = NOT_FOUND
        if name == 'topic' and text not in library.TOPICS:
            entry['note'] = ('The topic named is not one of the library topics, so the source keeps the one it had.'
                             if text else 'No topic was named, so the source keeps the one it had.')
        out[name] = entry
    return out


def render(columns) -> str:
    """The columns as readable text, for the record's analysis."""
    lines = []
    for name in COLUMNS:
        cell = columns.get(name) or {}
        lines.append(LABELS[name] + ': ' + (cell.get('text') or '(not stated)'))
        if cell.get('quote'):
            lines.append('  Quote: "' + cell['quote'] + '"')
        elif cell.get('note'):
            lines.append('  ' + cell['note'])
    return '\n'.join(lines)


def _failed_reason(turn) -> str:
    return next((e.get('message') for e in reversed(turn.get('events') or []) if e.get('type') == 'failed'),
                'The extraction turn did not finish.')


def ON_TURN(genesis, turn):
    """A finished extraction becomes the record's columns and analysis. A failed turn, or an answer
    that is not usable JSON, leaves the source Saved with the reason in the activity record."""
    if turn.get('purpose') != PURPOSE:
        return
    found = MARKER.search(str(turn.get('message') or ''))
    if not found:
        return
    identity = found[1]
    try:
        record = genesis.library.read(identity)
    except (ValueError, FileNotFoundError, OSError):
        return
    if turn.get('status') != 'completed':
        genesis.autonomy.record('extracted', card=turn.get('card'), library=identity, turn=turn['id'],
                                status='failed', reason=_failed_reason(turn))
        return
    try:
        columns = read_columns_of(turn.get('answer'), record.get('original') or '')
    except ValueError as exc:
        genesis.autonomy.record('extracted', card=turn.get('card'), library=identity, turn=turn['id'],
                                status='failed', reason=str(exc))
        return
    try:
        genesis.library.analyze(identity, {'analysis': render(columns), 'columns': columns})
    except ValueError as exc:
        genesis.autonomy.record('extracted', card=turn.get('card'), library=identity, turn=turn['id'],
                                status='failed', reason=str(exc))
        return
    topic = columns['topic']['text']
    moved = None
    if topic in library.TOPICS and topic != record['topic']:
        genesis.library.reclassify(identity, {'topic': topic, 'by': 'genesis'})
        moved = topic
    unverified = [c for c in COLUMNS if columns[c].get('note') == NOT_FOUND]
    genesis.autonomy.record('extracted', card=turn.get('card'), library=identity, turn=turn['id'],
                            status='done', quoted=sum(1 for c in COLUMNS if columns[c]['quote']),
                            columns=len(COLUMNS), unverified=unverified or None, topic=moved)


# -- tools ------------------------------------------------------------------------

def _read_columns(genesis, payload) -> dict:
    identity = payload.get('library') or payload.get('id')
    if not identity:
        raise ValueError('Name the library record, as library.')
    try:
        record = genesis.library.read(str(identity))
    except (ValueError, FileNotFoundError, OSError):
        raise ValueError('No library record is called ' + str(identity) + '.') from None
    columns = record.get('columns')
    return {'library': record['id'], 'title': record['title'], 'topic': record['topic'],
            'status': record['status'], 'url': record.get('url'), 'columns': columns,
            'full_text_available': record['full_text_available'],
            'note': 'Cite a column by its quote.' if columns else
                    'This source has no columns yet. Ingest it with ingest_source before judging it.'}


TOOLS = {'ingest_source': lambda genesis, payload: ingest(genesis, payload.get('library') or payload.get('id'), payload.get('card')),
         'read_columns': _read_columns}

PROTOCOL = (
    'A source is judged on its text, never on its abstract. When read_columns {library} says a source has '
    'no columns, or library_read shows no full text, call ingest_source {library} first: it fetches the whole '
    'source (arXiv through its HTML rendering, GitHub through the README, anything else through its visible '
    'text), stores it as the record original, and runs one extraction that fills the columns claim, method, '
    'dataset, result numbers, limitations, contradictions, what it means for Monarch, and topic. Every column '
    'carries the quote it rests on, checked against the fetched text; a column whose quote is null was not '
    'verified, so do not present it as the source\'s words. Cite columns by their quotes.'
)
