"""Genesis research library: sources read, their analyses, and where each technique was used.

One JSON record per source under the Genesis state directory. A record is Saved
until Genesis attaches an analysis of its full text; a source whose full text is
unavailable can never be Analyzed. "Used in" entries name the architecture
version that used the technique and are never removed by later versions.
"""
from __future__ import annotations
import json
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from wb_results.evidence import write_json

SOURCE_TYPES = ('paper', 'blog', 'repo', 'docs', 'other')
STATUSES = ('saved', 'analyzed')
IDENTITY = re.compile(r'[a-zA-Z0-9_-]{1,80}')

# One fixed list of topics. A source lands in one of them; "Other" holds what fits none.
# Genesis may move a source to a better topic with `library_reclassify`; a human may too.
TOPICS = ('Agentic memory', 'Code understanding', 'Evaluation and benchmarks', 'Agent architectures',
          'Tool use and APIs', 'Workflow automation', 'Reliability and safety', 'UI and design',
          'Cost and efficiency', 'Product knowledge', 'Other')
KEYWORDS = {
    'Agentic memory': ('memory', 'memgpt', 'letta', 'mem0', 'zep', 'graphiti', 'consolidat', 'forgetting', 'recall', 'sleep-time'),
    'Code understanding': ('codebase', 'code index', 'repo map', 'tree-sitter', 'ast', 'code graph', 'graphify', 'symbol', 'refactor', 'static analysis'),
    'Evaluation and benchmarks': ('benchmark', 'eval', 'grading', 'grader', 'judge', 'leaderboard', 'pass rate', 'metric', 'automationbench', 'swe-bench', 'tau-bench', 'τ-bench', 'appworld'),
    'Agent architectures': ('architecture', 'planner', 'planning', 'multi-agent', 'orchestrat', 'reflexion', 'react', 'scaffold', 'harness', 'reasoning'),
    'Tool use and APIs': ('tool use', 'tool call', 'function call', 'mcp', 'api', 'openapi', 'endpoint'),
    'Workflow automation': ('workflow', 'automation', 'zapier', 'trigger', 'pipeline', 'recipe', 'no-code', 'low-code'),
    'Reliability and safety': ('reliab', 'safety', 'guardrail', 'injection', 'hallucinat', 'consisten', 'pass^k', 'robust', 'verification', 'trust'),
    'UI and design': ('ui', 'ux', 'design', 'interface', 'wcag', 'accessib', 'typograph', 'color', 'colour', 'dashboard', 'chart'),
    'Cost and efficiency': ('cost', 'token', 'latency', 'cach', 'price', 'pricing', 'efficien', 'budget', 'throughput'),
    'Product knowledge': ('product graph', 'knowledge graph', 'knowledge base', 'entity', 'ontology', 'feature discovery', 'business action'),
}


def classify(*texts) -> str:
    """The topic whose keywords appear most in the given texts; "Other" when none do.
    Deterministic, so the same source always lands in the same place; Genesis can refine it."""
    title = str(texts[0] or '').lower() if texts else ''
    haystack = ' '.join(str(t or '') for t in texts).lower()
    best, hits = 'Other', 0
    for topic in TOPICS[:-1]:
        # the title counts three times: it names the subject, the rest only mentions things
        count = sum(haystack.count(word) + 2 * title.count(word) for word in KEYWORDS[topic])
        if count > hits:
            best, hits = topic, count
    return best


def topic_for(payload) -> str:
    """The payload's topic when it is one of ours, else a classification of what the payload says."""
    given = str(payload.get('topic') or '').strip()
    if given in TOPICS:
        return given
    return classify(payload.get('title'), given, payload.get('abstract'), payload.get('original'))


def now_sao_paulo():
    try:
        zone = ZoneInfo('America/Sao_Paulo')
    except ZoneInfoNotFoundError:
        zone = timezone(timedelta(hours=-3), 'America/Sao_Paulo')  # ponytail: fixed -03:00 without tzdata; Brazil has had no DST since 2019
    return datetime.now(zone)


def _day(value, field):
    """An ISO date, or None when unknown; datetimes are cut to their date."""
    if value in (None, ''):
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        raise ValueError(field + ' must be an ISO date (YYYY-MM-DD)') from None


def _within(value, low, high):
    if not low and not high:
        return True
    return value is not None and (not low or value >= low) and (not high or value <= high)


def _source_type(url):
    host = str(url).lower()
    if 'arxiv.org' in host or 'doi.org' in host or host.endswith('.pdf'):
        return 'paper'
    if 'github.com' in host or 'gitlab.com' in host:
        return 'repo'
    if '/docs' in host or 'docs.' in host or '/learn/' in host:
        return 'docs'
    if '/blog' in host or '/engineering/' in host:
        return 'blog'
    return 'other'


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.migrate_topics()

    def path(self, identity):
        if not IDENTITY.fullmatch(str(identity)):
            raise ValueError('Unknown library record')
        return self.root / (identity + '.json')

    def read(self, identity):
        path = self.path(identity)
        if not path.exists():
            raise FileNotFoundError('Unknown library record')
        return json.loads(path.read_text(encoding='utf8'))

    def records(self):
        rows = [json.loads(p.read_text(encoding='utf8')) for p in self.root.glob('*.json')]
        return sorted(rows, key=lambda r: (r.get('published_at') or '', r['discovered_at'], r['id']), reverse=True)

    def listing(self, published_from=None, published_to=None, discovered_from=None, discovered_to=None, topic=None, status=None):
        """Records newest first, each with `new_evidence`: a later source on the same topic contradicts it."""
        rows = self.records()
        contradicted = {}
        for row in rows:
            for other in row.get('contradicts', []):
                contradicted.setdefault(other, []).append(row)
        out = []
        for row in rows:
            row['new_evidence'] = any(o['topic'] == row['topic'] and (o.get('published_at') or '') > (row.get('published_at') or '')
                                      for o in contradicted.get(row['id'], []))
            if (status and row['status'] != status) or (topic and row['topic'] != topic):
                continue
            if not _within(row['published_at'], _day(published_from, 'published_from'), _day(published_to, 'published_to')):
                continue
            if not _within(row['discovered_at'], _day(discovered_from, 'discovered_from'), _day(discovered_to, 'discovered_to')):
                continue
            out.append(row)
        return out

    def _contradicts(self, value, own):
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise ValueError('contradicts lists library record IDs')
        for other in value:
            if other == own or not self.path(other).exists():
                raise ValueError('contradicts names a library record that does not exist')
        return value

    def add(self, payload):
        """Save a source. The same URL is one record: a second add returns it, keeping
        its analysis and uses, and only raises full_text_available when the newcomer has the text."""
        title = str(payload.get('title', '')).strip()
        if not title or len(title) > 300:
            raise ValueError('Give the source a title up to 300 characters')
        if payload.get('status', 'saved') != 'saved':
            raise ValueError('A source is Saved when added; Analyzed needs an analysis of its full text')
        source_type = payload.get('source_type', 'other')
        if source_type not in SOURCE_TYPES:
            raise ValueError('source_type is one of ' + ', '.join(SOURCE_TYPES))
        authors = payload.get('authors', [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(',') if a.strip()]
        if not isinstance(authors, list) or any(not isinstance(a, str) for a in authors):
            raise ValueError('authors is a list of names')
        original = payload.get('original')
        original = str(original) if original not in (None, '') else None
        url = str(payload.get('url') or '').strip() or None
        with self.lock:
            existing = next((r for r in self.records() if url and r.get('url') == url), None)
            if existing:
                if original and not existing['full_text_available']:
                    existing.update(original=original, full_text_available=True)
                elif payload.get('full_text_available') and not existing['full_text_available']:
                    existing['full_text_available'] = True
                else:
                    return existing
                write_json(self.path(existing['id']), existing)
                return existing
            identity = payload.get('id') or uuid.uuid4().hex
            path = self.path(identity)
            if path.exists():
                raise ValueError('This library record already exists')
            record = {'id': identity, 'title': title, 'authors': authors, 'source_type': source_type, 'url': url,
                      'published_at': _day(payload.get('published_at'), 'published_at'),
                      'discovered_at': _day(payload.get('discovered_at'), 'discovered_at') or now_sao_paulo().date().isoformat(),
                      'topic': topic_for(payload), 'topic_source': 'genesis' if payload.get('topic') in TOPICS and payload.get('topic_source') == 'genesis' else ('human' if payload.get('topic') in TOPICS else 'keywords'), 'status': 'saved',
                      'abstract': str(payload.get('abstract') or ''), 'full_text_available': bool(payload.get('full_text_available')) or original is not None,
                      'original': original, 'analysis': None, 'used_in': [],
                      'contradicts': self._contradicts(payload.get('contradicts', []), identity),
                      'created_at': datetime.now(timezone.utc).isoformat()}
            if payload.get('ledger'):
                record['ledger'] = payload['ledger']
            write_json(path, record)
            return record

    def analyze(self, identity, payload):
        """Attach Genesis's analysis; the only way a record becomes Analyzed."""
        with self.lock:
            record = self.read(identity)
            if not record['full_text_available']:
                raise ValueError('Full text is unavailable, so this source cannot be marked Analyzed')
            analysis = str(payload.get('analysis') or '').strip()
            if not analysis:
                raise ValueError('Attach the analysis text to mark this source Analyzed')
            if 'contradicts' in payload:
                record['contradicts'] = self._contradicts(payload['contradicts'], identity)
            if payload.get('columns') is not None:
                # feature 022: the extraction columns, each with the quote it rests on (`genesis_ingest`).
                record['columns'] = payload['columns']
            record.update(analysis=analysis, status='analyzed', analyzed_at=datetime.now(timezone.utc).isoformat())
            write_json(self.path(identity), record)
            return record

    def set_original(self, identity, text):
        """Store a source's fetched full text. The ingest path: the record stays Saved until an
        analysis of that text is attached."""
        text = str(text or '')
        if not text.strip():
            raise ValueError('There is no text to store as the original of this source')
        with self.lock:
            record = self.read(identity)
            record.update(original=text, full_text_available=True)
            write_json(self.path(identity), record)
            return record

    def reclassify(self, identity, payload):
        """Move a source to one of the fixed topics; who moved it is recorded."""
        topic = str(payload.get('topic') or '').strip()
        if topic not in TOPICS:
            raise ValueError('Choose one of the library topics: ' + ', '.join(TOPICS))
        who = payload.get('by') if payload.get('by') in ('genesis', 'human') else 'human'
        with self.lock:
            record = self.read(identity)
            record.update(topic=topic, topic_source=who)
            write_json(self.path(identity), record)
            return record

    def migrate_topics(self) -> int:
        """Sources filed before the fixed list get a topic from their own text; returns how many moved."""
        moved = 0
        with self.lock:
            for record in self.records():
                if record.get('topic') in TOPICS:
                    continue
                record.update(topic=classify(record.get('title'), record.get('topic'), record.get('abstract'), record.get('original')), topic_source='keywords')
                write_json(self.path(record['id']), record)
                moved += 1
        return moved

    def use(self, identity, payload):
        """Append a "used in" entry for the version that used this source; entries are never removed."""
        entry = {k: str(payload.get(k) or '').strip() for k in ('version_id', 'blueprint', 'where', 'why')}
        if not entry['version_id'] or not entry['blueprint']:
            raise ValueError('A use names the architecture version and its blueprint')
        experiments = payload.get('experiment_ids', [])
        if not isinstance(experiments, list) or any(not isinstance(e, str) for e in experiments):
            raise ValueError('experiment_ids is a list of run IDs')
        entry.update(experiment_ids=experiments, at=datetime.now(timezone.utc).isoformat())
        with self.lock:
            record = self.read(identity)
            record['used_in'].append(entry)
            write_json(self.path(identity), record)
            return record

    def import_ledger(self, path):
        """Turn the weekly source ledger (research/search-log.jsonl) into Saved records; never writes the ledger."""
        imported = existing = 0
        known = {r['url'] for r in self.records()}
        for line in Path(path).read_text(encoding='utf8').splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            self.add({'id': row.get('id') if IDENTITY.fullmatch(str(row.get('id', ''))) else None,
                      'title': row.get('title') or row['id'], 'url': row['url'],
                      'source_type': _source_type(row['url']), 'topic': classify(row.get('title'), row.get('finding'), row.get('url')),
                      'abstract': row.get('finding', ''), 'discovered_at': row['date'],
                      'full_text_available': row.get('access_status') == 'full_text_read',
                      'ledger': {k: row.get(k) for k in ('id', 'discovery', 'access_status', 'sections', 'next_question', 'artifact')}})
            if row['url'] in known:
                existing += 1
            else:
                imported += 1
                known.add(row['url'])
        return {'imported': imported, 'existing': existing}
