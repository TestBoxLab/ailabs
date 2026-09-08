"""Atomic, local campaign reservations; this does not meter or stop model calls.

Callers must reserve before dispatch, dispatch only newly created reservations,
then reconcile the complete provider cost (or None when cost is unknown).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path


class BudgetBlocked(RuntimeError):
    pass


class ReservationConflict(RuntimeError):
    pass


def _money(value) -> int:
    if isinstance(value, bool):
        raise ValueError('Cost must be a non-negative finite amount')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError('Cost must be a non-negative finite amount')
        return int((amount * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('Invalid cost') from exc


@dataclass(frozen=True)
class Reservation:
    id: str
    category: str
    reserved_usd: float
    state: str
    created: bool


class CampaignBudget:
    def __init__(self, path: str | Path, *, total_limit_usd=1000, development_limit_usd=200):
        self.path = Path(path)
        self.total = _money(total_limit_usd)
        self.development = _money(development_limit_usd)
        if not 0 < self.total <= _money(1000) or not 0 < self.development <= _money(200):
            raise ValueError('Campaign limits cannot exceed $1000 total / $200 development')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS limits (singleton INTEGER PRIMARY KEY CHECK(singleton=1), total INTEGER NOT NULL, development INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, category TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER, state TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO limits VALUES (1, ?, ?)', (self.total, self.development))
            limits = db.execute('SELECT total, development FROM limits WHERE singleton=1').fetchone()
            if tuple(limits) != (self.total, self.development):
                raise ReservationConflict('Existing campaign limits cannot change')

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve(self, reservation_id: str, category: str, amount_usd=None) -> Reservation:
        if not isinstance(reservation_id, str) or not reservation_id.strip():
            raise ValueError('A stable reservation ID is required')
        if category not in ('development', 'measured'):
            raise ValueError('Unknown budget category')
        amount = _money(12 if amount_usd is None and category == 'measured' else amount_usd)
        if amount <= 0 or (category == 'measured' and amount != _money(12)):
            raise ValueError('Measured attempts reserve exactly $12; development reserves a positive amount')
        with self._transaction() as db:
            prior = db.execute('SELECT * FROM reservations WHERE id=?', (reservation_id,)).fetchone()
            if prior:
                if prior['category'] != category or prior['reserved'] != amount:
                    raise ReservationConflict('Reservation ID already has different terms')
                return Reservation(reservation_id, category, amount / 1_000_000, prior['state'], False)
            rows = db.execute('SELECT * FROM reservations').fetchall()
            if any(r['state'] == 'unknown' for r in rows):
                raise BudgetBlocked('Unknown usage must be reconciled before more paid work')
            if any(r['actual'] is not None and r['actual'] > r['reserved'] for r in rows):
                raise BudgetBlocked('A reservation overran its limit; campaign requires review')
            committed = sum(r['actual'] if r['actual'] is not None else r['reserved'] for r in rows)
            dev = sum(r['actual'] if r['actual'] is not None else r['reserved']
                      for r in rows if r['category'] == 'development')
            if committed + amount > self.total or (category == 'development' and dev + amount > self.development):
                raise BudgetBlocked('Campaign or development budget would be exceeded')
            db.execute('INSERT INTO reservations VALUES (?, ?, ?, NULL, ?)',
                       (reservation_id, category, amount, 'reserved'))
            return Reservation(reservation_id, category, amount / 1_000_000, 'reserved', True)

    def reconcile(self, reservation_id: str, actual_usd) -> None:
        actual = None if actual_usd is None else _money(actual_usd)
        with self._transaction() as db:
            row = db.execute('SELECT * FROM reservations WHERE id=?', (reservation_id,)).fetchone()
            if row is None:
                raise ReservationConflict('No reservation exists for this cost')
            if row['state'] == 'reconciled':
                if row['actual'] != actual:
                    raise ReservationConflict('This reservation already has a different final cost')
                return
            db.execute('UPDATE reservations SET actual=?, state=? WHERE id=?',
                       (actual, 'unknown' if actual is None else 'reconciled', reservation_id))

    def snapshot(self) -> dict:
        with self._transaction() as db:
            rows = db.execute('SELECT * FROM reservations ORDER BY id').fetchall()
            spent = sum(r['actual'] or 0 for r in rows)
            reserved = sum(r['reserved'] for r in rows if r['actual'] is None)
            return {
                'total_limit_usd': self.total / 1_000_000,
                'development_limit_usd': self.development / 1_000_000,
                'pending': [r['id'] for r in rows if r['state'] == 'reserved'],
                'spent_usd': spent / 1_000_000,
                'reserved_usd': reserved / 1_000_000,
                'committed_usd': (spent + reserved) / 1_000_000,
                'remaining_usd': (self.total - spent - reserved) / 1_000_000,
                'unknown': [r['id'] for r in rows if r['state'] == 'unknown'],
                'overruns': [r['id'] for r in rows if r['actual'] is not None and r['actual'] > r['reserved']],
            }
