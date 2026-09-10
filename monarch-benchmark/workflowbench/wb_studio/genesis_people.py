"""People files and episodes (feature 022, design sections 4 and 10, points 5 and 6).

One Markdown file per person under `genesis/people/<name>.md`, at most 1,000 characters:
what Genesis knows about that person and how they like answers. Genesis writes it with
`person_write` and reads it with `person_read`; the person edits their own through lane
B's route. The file of the person a turn belongs to enters that turn's prompt.

Episodes: when a conversation turn finishes, one line goes into the record (kind
`episode`) — the thread when the turn has one, the turn itself until then — so a search
finds "what we discussed about X last week". Nothing here ever writes to core memory.

The identity, the keys and the roles are lane B's; this module only stores and injects.
"""
from __future__ import annotations

import re

from wb_studio.memory import scan

PERSON_BUDGET = 1000
NAME = re.compile(r'[a-z0-9][a-z0-9._-]{0,60}')
CONVERSATION = 'Genesis conversation'


def person_name(value) -> str:
    """`human:lucas`, `Lucas` and `lucas` all name the same file."""
    name = str(value or '').strip().lower()
    if ':' in name:
        name = name.split(':', 1)[1]
    if not NAME.fullmatch(name):
        raise ValueError('Name the person the way the Studio does, like lucas or human:lucas.')
    return name


def path(genesis, who):
    folder = genesis.root / 'people'
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (person_name(who) + '.md')


def read(genesis, who) -> dict:
    file = path(genesis, who)
    text = file.read_text(encoding='utf8') if file.exists() else ''
    return {'person': file.stem, 'text': text, 'size': len(text), 'budget': PERSON_BUDGET}


def write(genesis, who, text, by='genesis') -> dict:
    """The whole file, scanned like a memory entry and inside its budget."""
    file = path(genesis, who)
    text = str(text or '').replace('\r\n', '\n').strip()
    reason = scan(text)
    if reason:
        raise ValueError('The person file was refused. ' + reason)
    if len(text) > PERSON_BUDGET:
        raise ValueError(f'A person file holds at most {PERSON_BUDGET:,} characters; this one has {len(text):,}. '
                         'Merge what you know instead of adding to it.')
    file.write_text(text + ('\n' if text else ''), encoding='utf8', newline='\n')
    genesis.autonomy.record('person-file', person=file.stem, size=len(text), by=by)
    return read(genesis, file.stem)


def listing(genesis) -> list:
    folder = genesis.root / 'people'
    return [{'person': p.stem, 'size': len(p.read_text(encoding='utf8')), 'budget': PERSON_BUDGET}
            for p in sorted(folder.glob('*.md'))] if folder.exists() else []


def PROMPT(genesis, turn) -> str:
    """The file of the person this turn belongs to, or nothing."""
    who = turn.get('person') or turn.get('by')
    try:
        file = read(genesis, who)
    except ValueError:
        return ''
    if not file['text'].strip():
        return ''
    return ('\n\nWhat you know about ' + file['person'] + ' (people/' + file['person'] +
            '.md, at most ' + str(PERSON_BUDGET) + ' characters; keep it current with person_write):\n\n' + file['text'].strip())


# ---- episodes ----------------------------------------------------------------------
def _line(text, limit=200) -> str:
    return ' '.join(str(text or '').split())[:limit]


def episode(genesis, turn) -> dict | None:
    """One line for the record: the thread when the turn has one, else the turn."""
    thread = None
    if turn.get('thread'):
        try:
            thread = genesis.thread(turn['thread'])
        except (ValueError, OSError, FileNotFoundError):
            thread = None
    who = str(turn.get('by') or 'human:studio')
    if thread:
        exchanges = [t for t in thread.get('turns') or [] if t.get('message')]
        line = ' | '.join(_line(t['message'], 120) + ' -> ' + _line(t.get('answer'), 160) for t in exchanges[-6:])
        return {'kind': 'episode', 'id': thread['id'], 'updated_at': thread.get('updated_at') or turn.get('created_at'),
                'title': _line(thread.get('title') or turn['message'], 120),
                'body': who + ' talked with Genesis: ' + line}
    return {'kind': 'episode', 'id': turn['id'], 'updated_at': turn.get('created_at'),
            'title': _line(turn.get('message'), 120),
            'body': who + ' asked: ' + _line(turn.get('message'), 400) + ' -> ' + _line(turn.get('answer'), 600)}


def ON_TURN(genesis, turn):
    if turn.get('purpose') != CONVERSATION or turn.get('status') != 'completed':
        return
    row = episode(genesis, turn)
    if row:
        genesis.memory.index_records([row])


TOOLS = {'person_read': lambda genesis, payload: read(genesis, payload.get('person')),
         'person_write': lambda genesis, payload: write(genesis, payload.get('person'), payload.get('text'))}

PROTOCOL = ('You keep one file per person, at most 1,000 characters: what you know about them and how they like '
            'answers. Read it with person_read and rewrite it whole with person_write; the file of the person you '
            'are talking to is in your prompt. Write only what helps the work, never private data, and merge '
            'rather than append when the file fills. Every finished conversation also leaves one line in the '
            'record as an episode, which record_search finds; you do not write those.')
