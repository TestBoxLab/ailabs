"""Genesis skills: procedures Genesis writes for itself and a person can edit (feature 021).

One Markdown file per skill under `genesis/skills/`, at most 4,000 characters and
twelve skills. The first line names what it applies to: `Applies: hypothesis, run`
or `Applies: always`. Matching skills enter the prompt after the core memory, so a
procedure learned once (how to read a run, how to grade a hypothesis) is reused. Every
write is scanned like a memory entry and recorded in the activity log by the caller.

Feature 022 adds skills that write themselves: after a debrief, or after work on a card
whose review is `accept`, one short turn asks whether the work needed a procedure Genesis
did not have. A new one is written to `genesis/skills/pending/<slug>.md`, judged by the
Reviewer in its own turn, and only written into the skills folder on `accept`. Nothing
here is called by the scheduler: `genesis_memory_suite.ON_TURN` calls `after_turn`.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from wb_studio.memory import scan

SKILL_BUDGET = 4000
SKILL_LIMIT = 12
SLUG = re.compile(r'[a-z0-9][a-z0-9-]{1,60}')
KINDS = ('always', 'hypothesis', 'source', 'run', 'question', 'verdict')


class Skills:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, slug: str) -> Path:
        slug = str(slug or '').strip().lower()
        if not SLUG.fullmatch(slug):
            raise ValueError('A skill name is lowercase letters, digits and dashes, like read-a-run.')
        return self.root / (slug + '.md')

    @staticmethod
    def applies(text: str) -> tuple[str, ...]:
        first = (text.splitlines() or [''])[0]
        m = re.match(r'\s*applies\s*:\s*(.+)', first, re.I)
        if not m:
            return ('always',)
        kinds = tuple(k.strip().lower() for k in m.group(1).split(',') if k.strip())
        return tuple(k for k in kinds if k in KINDS) or ('always',)

    def listing(self) -> list[dict]:
        out = []
        for path in sorted(self.root.glob('*.md')):
            text = path.read_text(encoding='utf8')
            out.append({'name': path.stem, 'applies': list(self.applies(text)), 'size': len(text), 'budget': SKILL_BUDGET,
                        'summary': next((l.strip() for l in text.splitlines()[1:] if l.strip()), '')[:160]})
        return out

    def read(self, slug: str) -> dict:
        path = self._path(slug)
        if not path.exists():
            raise ValueError(f'No skill named {slug}.')
        text = path.read_text(encoding='utf8')
        return {'name': path.stem, 'applies': list(self.applies(text)), 'text': text, 'size': len(text), 'budget': SKILL_BUDGET}

    def write(self, slug: str, text: str) -> dict:
        path = self._path(slug)
        text = str(text or '').replace('\r\n', '\n').strip()
        if not text:
            raise ValueError('Write the skill text; the first line says what it applies to, like "Applies: run".')
        reason = scan(text)
        if reason:
            raise ValueError(reason)
        if len(text) > SKILL_BUDGET:
            raise ValueError(f'A skill holds at most {SKILL_BUDGET:,} characters; this one has {len(text):,}.')
        if not path.exists() and len(list(self.root.glob('*.md'))) >= SKILL_LIMIT:
            raise ValueError(f'At most {SKILL_LIMIT} skills; merge or remove one first.')
        path.write_text(text + '\n', encoding='utf8', newline='\n')
        return self.read(path.stem)

    def remove(self, slug: str) -> dict:
        path = self._path(slug)
        if path.exists():
            path.unlink()
        return {'name': path.stem, 'removed': True}

    def prompt_block(self, kind: str | None) -> str:
        """The skills that apply to this turn, or nothing."""
        parts = []
        for path in sorted(self.root.glob('*.md')):
            text = path.read_text(encoding='utf8').strip()
            applies = self.applies(text)
            if 'always' in applies or (kind and kind in applies):
                parts.append('Skill ' + path.stem + ':\n' + text)
        if not parts:
            return ''
        return '\n\nSkills (procedures you wrote; edit with skill_write when a step proved wrong):\n\n' + '\n\n'.join(parts)

    # ---- candidates waiting for the Reviewer (feature 022) --------------------------
    def pending_path(self, slug: str) -> Path:
        path = self._path(slug)
        folder = self.root / 'pending'
        folder.mkdir(parents=True, exist_ok=True)
        return folder / path.name

    def pending_write(self, slug: str, text: str) -> Path:
        text = str(text or '').replace('\r\n', '\n').strip()
        if not text:
            raise ValueError('Write the skill text; the first line says what it applies to, like "Applies: run".')
        reason = scan(text)
        if reason:
            raise ValueError(reason)
        if len(text) > SKILL_BUDGET:
            raise ValueError(f'A skill holds at most {SKILL_BUDGET:,} characters; this one has {len(text):,}.')
        path = self.pending_path(slug)
        path.write_text(text + '\n', encoding='utf8', newline='\n')
        return path


# ---- skills that write themselves ---------------------------------------------------
ASK_PURPOSE = 'Genesis skill'
REVIEW_PURPOSE = 'Genesis skill review'
EARNED = ('Genesis watcher', 'Genesis debrief')
ASK = ('You have just finished work on card {card}: "{title}". Did that work need a procedure you did not '
       'already have as a skill? Your skills now: {skills}. Answer with one JSON object and nothing else: '
       '{{"new": true or false, "name": "a-short-slug", "text": "Applies: <kinds>\\nthe procedure in steps"}}. '
       'Answer new false when an existing skill covered it, and never write a skill for a one-off fact.')


def cap() -> str:
    """The ceiling of the short turn that asks for a skill and of its review."""
    return os.environ.get('STUDIO_GENESIS_SKILL_USD', '0.20')


def _entry(genesis, turn_id):
    return next((e for e in genesis.autonomy.tail(500) if e.get('kind') == 'skill-candidate' and e.get('turn') == turn_id), None)


def earned(genesis, turn):
    """The card whose finished work may have taught a procedure, or None."""
    if turn.get('status') != 'completed' or turn.get('purpose') not in EARNED or not turn.get('card'):
        return None
    try:
        card = genesis.read('cards', turn['card'])
    except (ValueError, OSError, FileNotFoundError):
        return None
    review = card.get('review') or {}
    recent = genesis.autonomy.tail(300)
    if any(e.get('kind') == 'skill-asked' and e.get('card') == card['id'] for e in recent):
        return None  # one question per card
    debriefed = any(e.get('kind') == 'debrief' and e.get('card') == card['id'] for e in recent)
    if debriefed or (review.get('status') == 'done' and review.get('verdict') == 'accept'):
        return card
    return None


def ask(genesis, card) -> dict:
    from wb_studio.genesis_harness import model_routes
    route = genesis.config.route_for('reading', routes=model_routes())
    if not route:
        raise ValueError('No model route is available to ask for a skill.')
    names = ', '.join(s['name'] for s in genesis.skills.listing()) or 'none yet'
    identity = uuid.uuid4().hex
    genesis.autonomy.record('skill-asked', card=card['id'], turn=identity, by='genesis')
    return genesis.chat({'id': identity, 'message': ASK.format(card=card['id'], title=str(card.get('title'))[:120], skills=names),
                         'model': route['id'], 'maximum_usd': cap(), 'purpose': ASK_PURPOSE})


def candidate(genesis, turn) -> None:
    """The answer to the question: nothing, or a candidate stored and sent to the Reviewer."""
    from wb_studio.genesis_harness import model_routes
    from wb_studio.genesis_reviewer import OUTPUT, json_answer, protocol_text
    if turn.get('status') != 'completed':
        return
    try:
        data = json_answer(turn.get('answer'), 'The skill turn')
    except ValueError as exc:
        genesis.autonomy.record('skill-refused', turn=turn['id'], reason=str(exc), by='genesis')
        return
    if not data.get('new'):
        genesis.autonomy.record('skill-none', turn=turn['id'], by='genesis')
        return
    name = str(data.get('name') or '').strip().lower()
    try:
        genesis.skills.pending_write(name, data.get('text'))
    except ValueError as exc:
        genesis.autonomy.record('skill-refused', turn=turn['id'], name=name, reason=str(exc), by='genesis')
        return
    route = genesis.config.route_for('review', routes=model_routes())
    if not route:
        genesis.autonomy.record('skill-refused', turn=turn['id'], name=name, reason='No model route is available for the Reviewer.', by='genesis')
        return
    identity = uuid.uuid4().hex
    genesis.autonomy.record('skill-candidate', turn=identity, name=name, source=turn['id'], by='genesis')
    message = (protocol_text() + '\n\nThe artifact to judge:\n\nSubject: a new skill, a procedure Genesis wrote for itself.\n'
               'Name: ' + name + '\n\n' + genesis.skills.pending_path(name).read_text(encoding='utf8'))[:15000] + '\n\n' + OUTPUT
    genesis.chat({'id': identity, 'message': message, 'model': route['id'], 'maximum_usd': cap(), 'purpose': REVIEW_PURPOSE})


def verdict(genesis, turn) -> None:
    """The Reviewer's answer: the skill is written on accept, and left pending otherwise."""
    from wb_studio.genesis_reviewer import read_verdict
    entry = _entry(genesis, turn['id'])
    if not entry:
        return
    name = entry['name']
    try:
        if turn.get('status') != 'completed':
            raise ValueError('The skill review turn did not finish.')
        judged = read_verdict(turn.get('answer'))
    except ValueError as exc:
        genesis.autonomy.record('skill-refused', turn=turn['id'], name=name, reason=str(exc), by='genesis')
        return
    if judged['verdict'] != 'accept':
        genesis.autonomy.record('skill-refused', turn=turn['id'], name=name, verdict=judged['verdict'],
                                reason=judged['reason'] or 'The Reviewer did not accept the skill.', by='genesis')
        return
    path = genesis.skills.pending_path(name)
    try:
        out = genesis.skills.write(name, path.read_text(encoding='utf8'))
    except (ValueError, OSError) as exc:
        genesis.autonomy.record('skill-refused', turn=turn['id'], name=name, reason=str(exc), by='genesis')
        return
    path.unlink(missing_ok=True)
    genesis.autonomy.record('skill', name=out['name'], size=out['size'], turn=turn['id'], reviewed=True, by='genesis')


def after_turn(genesis, turn) -> None:
    """Called from `genesis_memory_suite.ON_TURN` for every finished turn."""
    purpose = turn.get('purpose')
    if purpose == ASK_PURPOSE:
        return candidate(genesis, turn)
    if purpose == REVIEW_PURPOSE:
        return verdict(genesis, turn)
    card = earned(genesis, turn)
    if card:
        ask(genesis, card)
