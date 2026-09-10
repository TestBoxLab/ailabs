"""Genesis skills: procedures Genesis writes for itself and a person can edit (feature 021).

One Markdown file per skill under `genesis/skills/`, at most 4,000 characters and
twelve skills. The first line names what it applies to: `Applies: hypothesis, run`
or `Applies: always`. Matching skills enter the prompt after the core memory, so a
procedure learned once (how to read a run, how to grade a hypothesis) is reused. Every
write is scanned like a memory entry and recorded in the activity log by the caller.
"""
from __future__ import annotations

import re
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
