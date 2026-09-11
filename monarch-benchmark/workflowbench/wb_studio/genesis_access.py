"""People, keys and the lab's Genesis settings (feature 022, lane B, design sections 4, 8, 9 and 11).

One JSON file, `genesis/people.json`: the people list (name, role member or admin, the
hash of their key, who added them and when), the brief hour and the digest day. No
passwords and no third-party login: an admin hands a person a key, the browser keeps it,
and every write carries it. Until the first person exists, the Studio token alone opens
every write, so a fresh workspace can be set up.

Genesis's weekly spending gate is no longer here: it is one of the named allowances in
`wb_studio/allowances.py`, which budgets every kind of work the same way. The value a
person set as the envelope migrates on first read.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

NAME = re.compile(r'[a-z0-9][a-z0-9._-]{0,60}')
ROLES = ('member', 'admin')
WEBHOOK = 'SLACK_WEBHOOK_AILABS'
PUBLIC_URL = 'STUDIO_PUBLIC_URL'


def _hash(key: str) -> str:
    return hashlib.sha256(str(key).encode('utf8')).hexdigest()


class Access:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'people.json'
        self.lock = threading.RLock()

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding='utf8'))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault('people', [])
        data.setdefault('brief_hour', 8)
        data.setdefault('digest_day', 'monday')
        return data

    def _write(self, data: dict) -> None:
        with self.lock:
            self.path.write_text(json.dumps(data, indent=1), encoding='utf8', newline='\n')

    # ---- people and keys --------------------------------------------------------------
    def people(self) -> list:
        """The list without the key hashes: name, role, who added them and when."""
        return [{k: v for k, v in p.items() if k != 'key_hash'} for p in self._read()['people']]

    def add(self, name: str, role: str = 'member', by: str = 'human:studio') -> dict:
        """A new person and the key they are handed, once; the file keeps only its hash."""
        name = str(name or '').strip().lower()
        if not NAME.fullmatch(name):
            raise ValueError('Name the person with lowercase letters, digits, dots or dashes, like lucas.')
        if role not in ROLES:
            raise ValueError('A role is member or admin.')
        data = self._read()
        if any(p['name'] == name for p in data['people']):
            raise ValueError(f'{name} is already on the list; remove them first to hand out a new key.')
        key = 'ail_' + secrets.token_urlsafe(24)
        data['people'].append({'name': name, 'role': role, 'key_hash': _hash(key), 'added_by': by,
                               'added_at': datetime.now(timezone.utc).isoformat()})
        self._write(data)
        return {'name': name, 'role': role, 'key': key}

    def remove(self, name: str) -> dict:
        data = self._read()
        before = len(data['people'])
        data['people'] = [p for p in data['people'] if p['name'] != name]
        if len(data['people']) == before:
            raise ValueError(f'No person named {name}.')
        self._write(data)
        return {'name': name, 'removed': True}

    def person_for_key(self, key: str | None) -> dict | None:
        """The person a key belongs to, or None. A missing or wrong key names nobody."""
        if not key:
            return None
        digest = _hash(key)
        for p in self._read()['people']:
            if secrets.compare_digest(p.get('key_hash', ''), digest):
                return {'name': p['name'], 'role': p['role']}
        return None

    def anyone(self) -> bool:
        return bool(self._read()['people'])

    def may_write(self, person: dict | None, admin_only: bool = False) -> tuple[bool, str | None]:
        """Whether this write is allowed: before anyone is listed the token is enough; afterwards a key
        names the person, and admin writes need an admin."""
        if not self.anyone():
            return True, None
        if person is None:
            return False, 'This write needs your access key; paste it under Settings, Genesis, People.'
        if admin_only and person['role'] != 'admin':
            return False, f"{person['name']} is a member; an admin changes this."
        return True, None

    # ---- the lab's settings and the channels -----------------------------------------------------
    def settings(self) -> dict:
        data = self._read()
        return {'brief_hour': int(data['brief_hour']), 'digest_day': str(data['digest_day'])}

    def set_settings(self, payload: dict) -> dict:
        data = self._read()
        if 'brief_hour' in payload:
            hour = int(payload['brief_hour'])
            if not 0 <= hour <= 23:
                raise ValueError('The brief hour is 0 to 23, São Paulo time.')
            data['brief_hour'] = hour
        if 'digest_day' in payload:
            day = str(payload['digest_day']).lower()
            if day not in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'):
                raise ValueError('Name a day of the week for the digest.')
            data['digest_day'] = day
        self._write(data)
        return self.settings()

    @staticmethod
    def channels() -> dict:
        """Which channels are configured on the host, never their values."""
        return {'slack_webhook': bool(os.environ.get(WEBHOOK, '').strip()), 'public_url': bool(os.environ.get(PUBLIC_URL, '').strip()),
                'webhook_env': WEBHOOK, 'public_url_env': PUBLIC_URL}
