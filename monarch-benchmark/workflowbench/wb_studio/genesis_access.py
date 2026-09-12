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
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

TIMEZONE = 'America/Sao_Paulo'
LAB_WEEKLY_CEILING_USD = Decimal('300.00')


def _week_of(now: datetime | None = None) -> str:
    instant = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('now must be a timezone-aware datetime')
    local = instant.astimezone(ZoneInfo(TIMEZONE))
    monday = local.date() - timedelta(days=local.weekday())
    return monday.isoformat()

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


class Envelope:
    """The weekly research envelope (feature 024, FR-035).

    Sits at `genesis/envelope.json`.
    Absent or expired means zero, not unlimited.
    Amount must be strictly below the lab's weekly ceiling ($300.00).
    Exhaustion stops the loop; it never draws on the ceiling's remainder.
    """

    def __init__(self, root: Path | str):
        path_obj = Path(root)
        if path_obj.suffix == '.json':
            self.path = path_obj
            self.root = self.path.parent
        else:
            self.root = path_obj
            self.path = self.root / 'envelope.json'
        self.lock = threading.RLock()

    def read(self, now: datetime | None = None) -> dict:
        """The active envelope record for the week of `now`, or zero/absent."""
        current_week = _week_of(now)
        with self.lock:
            try:
                data = json.loads(self.path.read_text(encoding='utf8'))
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict) and data.get('week_start') == current_week:
                try:
                    amount = Decimal(str(data.get('amount_usd', '0.00')))
                    per_exp = Decimal(str(data.get('per_experiment_ceiling_usd', '0.00')))
                    return {
                        'week_start': current_week,
                        'amount_usd': f"{amount:.2f}",
                        'per_experiment_ceiling_usd': f"{per_exp:.2f}",
                        'set_by': str(data.get('set_by') or ''),
                        'set_at': str(data.get('set_at') or ''),
                        'is_set': True,
                    }
                except (InvalidOperation, ValueError):
                    pass
            return {
                'week_start': current_week,
                'amount_usd': '0.00',
                'per_experiment_ceiling_usd': '0.00',
                'set_by': None,
                'set_at': None,
                'is_set': False,
            }

    def set(
        self,
        amount_usd: str | int | float | Decimal,
        per_experiment_ceiling_usd: str | int | float | Decimal,
        by: str,
        now: datetime | None = None,
        weekly_ceiling_usd: Decimal = LAB_WEEKLY_CEILING_USD,
    ) -> dict:
        """Set the weekly research envelope. Strictly inside the weekly ceiling."""
        try:
            amount = Decimal(str(amount_usd))
        except (InvalidOperation, ValueError):
            raise ValueError('The envelope amount must be a number in dollars.')
        if not amount.is_finite() or amount < 0:
            raise ValueError('The envelope amount must be nonnegative.')
        if amount >= weekly_ceiling_usd:
            raise ValueError(
                f'The research envelope must be strictly below the lab weekly ceiling of ${weekly_ceiling_usd:.2f}.'
            )

        try:
            per_exp = Decimal(str(per_experiment_ceiling_usd))
        except (InvalidOperation, ValueError):
            raise ValueError('The per-experiment ceiling must be a number in dollars.')
        if not per_exp.is_finite() or per_exp < 0:
            raise ValueError('The per-experiment ceiling must be nonnegative.')
        if per_exp > amount:
            raise ValueError('The per-experiment ceiling cannot exceed the envelope amount.')

        by_str = str(by or '').strip()
        if not by_str:
            raise ValueError('The envelope must be set by a named person.')
        if not by_str.startswith('human:'):
            by_str = f'human:{by_str.lower()}'

        instant = now if now is not None else datetime.now(timezone.utc)
        week_start = _week_of(instant)
        set_at = instant.astimezone(timezone.utc).isoformat()

        record = {
            'week_start': week_start,
            'amount_usd': f'{amount:.2f}',
            'per_experiment_ceiling_usd': f'{per_exp:.2f}',
            'set_by': by_str,
            'set_at': set_at,
        }
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(record, indent=2), encoding='utf8', newline='\n')
        return record

    def clear(self) -> None:
        with self.lock:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    def _spent(
        self,
        ledger=None,
        lines=None,
        now: datetime | None = None,
        week: str | None = None,
    ) -> tuple[Decimal, Decimal]:
        if lines is not None:
            from wb_studio import allowances
            return allowances._spent(lines, 'genesis')
        if ledger is None:
            # The fixture Studio keeps its ledger beside the genesis folder; every
            # other Studio uses the shared one. Looking only beside the folder meant
            # the gate found nothing, read nothing spent, and reported the whole
            # envelope available however much of it was already held (FR-035).
            from wb_orchestrator.budget import BudgetLedger, default_ledger_path
            for candidate in (self.root.parent / 'budget.sqlite3', default_ledger_path()):
                if candidate.exists():
                    ledger = BudgetLedger(candidate)
                    break
        if ledger is not None:
            from types import SimpleNamespace
            from wb_studio.usage import ledger_lines
            from wb_studio import allowances
            studio = SimpleNamespace(
                ledger=ledger,
                jobs=lambda: [],
                budget=lambda: getattr(ledger, 'status', lambda now=None: None)(now=now),
            )
            data = ledger_lines(studio, now=now)
            return allowances._spent(data['lines'], 'genesis')
        # No ledger to read is not "nothing spent". An envelope with no accounting
        # behind it reads as fully committed, so the loop stops rather than runs blind.
        return Decimal(self.read(now=now)['amount_usd']), Decimal('0.00')

    def status(
        self,
        ledger=None,
        lines=None,
        now: datetime | None = None,
    ) -> dict:
        instant = now if now is not None else datetime.now(timezone.utc)
        current_week = _week_of(instant)
        rec = self.read(now=instant)
        amount = Decimal(rec['amount_usd'])
        per_exp = Decimal(rec['per_experiment_ceiling_usd'])
        if rec['is_set'] and amount > 0:
            held, settled = self._spent(ledger=ledger, lines=lines, now=instant, week=current_week)
            left = max(Decimal('0.00'), amount - held - settled)
        else:
            held = Decimal('0.00')
            settled = Decimal('0.00')
            left = Decimal('0.00')
        return {
            'week_start': current_week,
            'amount_usd': f'{amount:.2f}',
            'per_experiment_ceiling_usd': f'{per_exp:.2f}',
            'held_usd': f'{held:.2f}',
            'settled_usd': f'{settled:.2f}',
            'available_usd': left,
            'left_usd': f'{left:.2f}',
            'is_set': rec['is_set'],
            'set_by': rec.get('set_by'),
            'set_at': rec.get('set_at'),
        }

    def available_usd(
        self,
        ledger=None,
        lines=None,
        now: datetime | None = None,
    ) -> Decimal:
        return self.status(ledger=ledger, lines=lines, now=now)['available_usd']
