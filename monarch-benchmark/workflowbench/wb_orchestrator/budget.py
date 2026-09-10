"""Durable admission control for the shared experiment budget.

All callers must use one trusted ledger path outside competitor sandboxes.
Reserve *before* dispatch and settle only from verified total billing. Missing or
partial billing is ``None`` and never releases a hold. A reservation is a durable
liability, not a dispatch lock: an idempotent reserve does not authorize executing
an already dispatched attempt twice. Call claim immediately before dispatch;
a crash after claiming cannot automatically retry or release that reservation.

Weeks start Monday 00:00 America/Sao_Paulo. Without verified per-week billing,
settled actuals conservatively charge every week from first dispatch through
settlement, inclusive. Without dispatch evidence the interval starts at reservation.
Late billing can therefore charge multiple weeks even if execution finished early;
these capacity charges are not a claim about when provider usage occurred. Never
sum weekly capacity charges as total paid spend. Unresolved reservations consume
current capacity across every rollover until verified settlement.
An actual above its reserved maximum is recorded, then permanently blocks new
admissions. Request reservations have no override, expiry, or cancellation path.
Run envelopes hold unallocated capacity before scheduling; child request holds
replace that capacity rather than adding it again. Closing an envelope prevents
further dispatch and releases only unallocated capacity, never unknown billing.
SQLite protects cooperating local processes, not hostile DB edits, separate DBs,
or provider charges that exceed the maximum promised by a caller.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MICROUSD = 1_000_000
MAX_SQLITE_INTEGER = 2**63 - 1
AUTHORIZED_WEEKLY_MICROUSD = 300 * MICROUSD
TIMEZONE = 'America/Sao_Paulo'


class BudgetExceeded(RuntimeError):
    """Admission denied; no new reservation was written."""


class ReservationConflict(ValueError):
    """An existing immutable reservation was reused with different facts."""


class BudgetConfigurationError(ValueError):
    """The shared ledger policy is unavailable or inconsistent."""


def _money(value: Any) -> int:
    # Floats are rejected: callers must obtain an exact decimal billing value.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('money must be a decimal string, Decimal, or integer USD')
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or amount > Decimal('9223372036854.775807'):
            raise ValueError('money must be finite, nonnegative, and within SQLite range')
        if amount == 0:
            return 0
        # Work directly with decimal digits: neither ambient precision nor
        # exponent underflow may silently turn a tiny positive value into zero.
        _, digits, exponent = amount.as_tuple()
        shift = exponent + 6
        if shift < 0:
            cut = len(digits) + shift
            if cut <= 0 or any(digits[cut:]):
                raise ValueError('money must have at most six fractional USD digits')
            digits = digits[:cut]
            shift = 0
        return int(''.join(map(str, digits))) * (10 ** shift)
    except InvalidOperation as exc:
        raise ValueError('invalid decimal money') from exc


def _usd(value: int) -> Decimal:
    return Decimal(f'{value // MICROUSD}.{value % MICROUSD:06d}')


def _json_keys(value: Any) -> None:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError('metadata object keys must be strings')
        for item in value.values():
            _json_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _json_keys(item)


def _identity(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    scope_id: str
    maximum_microusd: int
    actual_microusd: int | None
    week_start: str
    created_at: str
    settled_at: str | None
    metadata_json: str
    dispatched_at: str | None = None

    @property
    def maximum_usd(self) -> Decimal:
        return _usd(self.maximum_microusd)

    @property
    def actual_usd(self) -> Decimal | None:
        return None if self.actual_microusd is None else _usd(self.actual_microusd)

    @property
    def metadata(self) -> dict[str, Any]:
        return json.loads(self.metadata_json)


@dataclass(frozen=True)
class RunReservation:
    scope_id: str
    maximum_microusd: int
    week_start: str
    created_at: str
    closed_at: str | None
    metadata_json: str

    @property
    def maximum_usd(self) -> Decimal:
        return _usd(self.maximum_microusd)

    @property
    def metadata(self) -> dict[str, Any]:
        return json.loads(self.metadata_json)


@dataclass(frozen=True)
class BudgetStatus:
    """Capacity view; actual is conservative weekly liability, not billing attribution."""

    week_start: str
    weekly_limit_microusd: int
    actual_microusd: int
    held_microusd: int
    carried_held_microusd: int
    overrun_ids: tuple[str, ...]

    @property
    def committed_microusd(self) -> int:
        return self.actual_microusd + self.held_microusd

    @property
    def available_microusd(self) -> int:
        return max(0, self.weekly_limit_microusd - self.committed_microusd)

    @property
    def blocked(self) -> bool:
        return bool(self.overrun_ids) or self.committed_microusd > self.weekly_limit_microusd

    @property
    def weekly_limit_usd(self) -> Decimal:
        return _usd(self.weekly_limit_microusd)

    @property
    def actual_usd(self) -> Decimal:
        return _usd(self.actual_microusd)

    @property
    def held_usd(self) -> Decimal:
        return _usd(self.held_microusd)

    @property
    def carried_held_usd(self) -> Decimal:
        return _usd(self.carried_held_microusd)

    @property
    def committed_usd(self) -> Decimal:
        return _usd(self.committed_microusd)

    @property
    def available_usd(self) -> Decimal:
        return _usd(self.available_microusd)


class BudgetLedger:
    def __init__(self, path: str | Path, weekly_limit_usd: str | Decimal | int = '300'):
        limit = _money(weekly_limit_usd)
        if limit > AUTHORIZED_WEEKLY_MICROUSD:
            raise BudgetConfigurationError('weekly limit exceeds authorized USD 300')
        try:
            self._zone = ZoneInfo(TIMEZONE)
        except ZoneInfoNotFoundError as exc:
            raise BudgetConfigurationError('America/Sao_Paulo unavailable; install tzdata before paid dispatch') from exc
        if str(path) == ':memory:':
            raise BudgetConfigurationError('budget ledger requires a persistent file')
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS budget_policy (id INTEGER PRIMARY KEY CHECK(id=1), weekly_limit INTEGER NOT NULL, timezone TEXT NOT NULL, schema_version INTEGER NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS budget_scopes (scope_id TEXT PRIMARY KEY, maximum INTEGER CHECK(maximum >= 0))')
            connection.execute('''CREATE TABLE IF NOT EXISTS budget_reservations (
                reservation_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL REFERENCES budget_scopes(scope_id),
                maximum_microusd INTEGER NOT NULL CHECK(maximum_microusd >= 0),
                actual_microusd INTEGER CHECK(actual_microusd >= 0), week_start TEXT NOT NULL,
                created_at TEXT NOT NULL, settled_at TEXT, metadata_json TEXT NOT NULL, dispatched_at TEXT)''')
            policy = connection.execute('SELECT weekly_limit, timezone, schema_version FROM budget_policy WHERE id=1').fetchone()
            if policy is None:
                connection.execute('INSERT INTO budget_policy VALUES (1, ?, ?, 3)', (limit, TIMEZONE))
            elif tuple(policy[:2]) != (limit, TIMEZONE) or policy['schema_version'] not in (1, 2, 3):
                raise BudgetConfigurationError('shared ledger policy differs; changing limits is not an override')
            elif policy['schema_version'] == 1:
                columns = {row['name'] for row in connection.execute('PRAGMA table_info(budget_reservations)')}
                if 'dispatched_at' not in columns:
                    connection.execute('ALTER TABLE budget_reservations ADD COLUMN dispatched_at TEXT')
                # Older ledgers have no dispatch evidence; never interpret that
                # absence as permission to execute their reservations again.
                connection.execute('UPDATE budget_reservations SET dispatched_at=created_at WHERE dispatched_at IS NULL')
                connection.execute('UPDATE budget_policy SET schema_version=2 WHERE id=1')
            connection.execute("""CREATE TABLE IF NOT EXISTS budget_run_reservations (
                scope_id TEXT PRIMARY KEY REFERENCES budget_scopes(scope_id),
                maximum_microusd INTEGER NOT NULL CHECK(maximum_microusd >= 0),
                week_start TEXT NOT NULL, created_at TEXT NOT NULL, closed_at TEXT,
                metadata_json TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS budget_run_requests (
                reservation_id TEXT PRIMARY KEY REFERENCES budget_reservations(reservation_id),
                run_id TEXT NOT NULL REFERENCES budget_run_reservations(scope_id))""")
            # Older implementations must refuse this policy instead of ignoring envelopes.
            connection.execute('UPDATE budget_policy SET schema_version=3 WHERE id=1')
        self.weekly_limit_microusd = limit

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _time(self, now: datetime | None) -> tuple[str, str]:
        instant = now if now is not None else datetime.now(timezone.utc)
        if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError('now must be a timezone-aware datetime')
        local = instant.astimezone(self._zone)
        monday = local.date() - timedelta(days=local.weekday())
        return monday.isoformat(), instant.astimezone(timezone.utc).isoformat()

    def _status(self, connection: sqlite3.Connection, week: str) -> BudgetStatus:
        rows = connection.execute('SELECT * FROM budget_reservations').fetchall()
        actual = 0
        for row in rows:
            if row['actual_microusd'] is None:
                continue
            start, _ = self._time(datetime.fromisoformat(row['dispatched_at'] or row['created_at']))
            end, _ = self._time(datetime.fromisoformat(row['settled_at']))
            if start <= week <= end:
                actual += row['actual_microusd']
        # All unknown liabilities count, including prior weeks. Python sums avoid
        # SQLite SUM overflow when an unusually large verified overrun is recorded.
        held = sum(row['maximum_microusd'] for row in rows if row['actual_microusd'] is None)
        carried = sum(row['maximum_microusd'] for row in rows if row['actual_microusd'] is None and row['week_start'] < week)
        for envelope in connection.execute('SELECT * FROM budget_run_reservations WHERE closed_at IS NULL'):
            unused = max(0, envelope['maximum_microusd'] - self._run_used(connection, envelope['scope_id']))
            held += unused
            if envelope['week_start'] < week:
                carried += unused
        overruns = tuple(sorted(row['reservation_id'] for row in rows if row['actual_microusd'] is not None and row['actual_microusd'] > row['maximum_microusd']))
        return BudgetStatus(week, self.weekly_limit_microusd, actual, held, carried, overruns)

    def status(self, *, now: datetime | None = None) -> BudgetStatus:
        week, _ = self._time(now)
        with self._transaction() as connection:
            return self._status(connection, week)

    def week_of(self, instant: datetime) -> str:
        """The ledger week (Monday, ISO date) an aware instant falls in."""
        week, _ = self._time(instant)
        return week

    def reservations(self, *, scope_id: str | None = None) -> list[Reservation]:
        """Every reservation, oldest first; a read-only view for dispatch checks and reconciliation."""
        query, args = 'SELECT * FROM budget_reservations', ()
        if scope_id is not None:
            _identity(scope_id, 'scope_id')
            query, args = query + ' WHERE scope_id=?', (scope_id,)
        with self._transaction() as connection:
            rows = connection.execute(query + ' ORDER BY created_at, reservation_id', args).fetchall()
        return [Reservation(**dict(row)) for row in rows]

    def run_reservations(self) -> list[RunReservation]:
        """Every run envelope, oldest first; a read-only view for the ledger page."""
        with self._transaction() as connection:
            rows = connection.execute('SELECT * FROM budget_run_reservations ORDER BY created_at, scope_id').fetchall()
        return [RunReservation(**dict(row)) for row in rows]

    def scope_committed(self, scope_id: str) -> Decimal:
        """What a scope has committed: settled actuals plus the maximum of every open hold."""
        _identity(scope_id, 'scope_id')
        with self._transaction() as connection:
            if connection.execute('SELECT 1 FROM budget_run_reservations WHERE scope_id=?', (scope_id,)).fetchone():
                return _usd(self._run_used(connection, scope_id))
            rows = connection.execute('SELECT maximum_microusd, actual_microusd FROM budget_reservations WHERE scope_id=?',
                                      (scope_id,)).fetchall()
        return _usd(sum(row['maximum_microusd'] if row['actual_microusd'] is None else row['actual_microusd'] for row in rows))

    def _run_used(self, connection, run_id):
        rows = connection.execute("""SELECT r.maximum_microusd, r.actual_microusd
            FROM budget_reservations r JOIN budget_run_requests link USING(reservation_id)
            WHERE link.run_id=?""", (run_id,)).fetchall()
        return sum(row['maximum_microusd'] if row['actual_microusd'] is None else row['actual_microusd'] for row in rows)

    def run_reservation(self, scope_id: str) -> RunReservation | None:
        """Read an envelope, including closed envelopes; absence is never an authorization."""
        _identity(scope_id, 'scope_id')
        with self._transaction() as connection:
            row = connection.execute('SELECT * FROM budget_run_reservations WHERE scope_id=?', (scope_id,)).fetchone()
            return None if row is None else RunReservation(**dict(row))

    def reserve_run(self, scope_id: str, maximum_usd: str | Decimal | int, *,
                    now: datetime | None = None, metadata: dict[str, Any] | None = None) -> RunReservation:
        """Reserve the entire run maximum atomically, before scheduling any work.

        Identity, maximum and metadata are immutable; repeated calls do not reopen
        a closed run. Existing reservations in the exact scope can be adopted only
        when their immutable scope cap agrees. Nested scopes opt in via reserve's run_id.
        """
        _identity(scope_id, 'scope_id')
        maximum = _money(maximum_usd)
        week, timestamp = self._time(now)
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError('metadata must be a JSON object')
        try:
            _json_keys(metadata)
            metadata_json = json.dumps(metadata or {}, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('metadata must be finite JSON data with string keys') from exc
        with self._transaction() as connection:
            existing = connection.execute('SELECT * FROM budget_run_reservations WHERE scope_id=?', (scope_id,)).fetchone()
            if existing is not None:
                if (existing['maximum_microusd'], existing['metadata_json']) != (maximum, metadata_json):
                    raise ReservationConflict('run reservation is bound to different amount or metadata')
                return RunReservation(**dict(existing))
            scope = connection.execute('SELECT maximum FROM budget_scopes WHERE scope_id=?', (scope_id,)).fetchone()
            if scope is not None and scope['maximum'] != maximum:
                raise BudgetConfigurationError('scope limit differs from its immutable shared configuration')
            children = connection.execute('SELECT * FROM budget_reservations WHERE scope_id=?', (scope_id,)).fetchall()
            if any(connection.execute('SELECT 1 FROM budget_run_requests WHERE reservation_id=?', (r['reservation_id'],)).fetchone() for r in children):
                raise ReservationConflict('scope reservations already belong to another run')
            used = sum(r['maximum_microusd'] if r['actual_microusd'] is None else r['actual_microusd'] for r in children)
            if used > maximum:
                raise BudgetExceeded('run budget exhausted')
            if any(datetime.fromisoformat(timestamp) < datetime.fromisoformat(r['created_at']) for r in children):
                raise ValueError('run reservation cannot predate existing requests')
            status = self._status(connection, week)
            if status.overrun_ids:
                raise BudgetExceeded('recorded reservation overrun blocks further launches')
            if status.committed_microusd + maximum - used > self.weekly_limit_microusd:
                raise BudgetExceeded('shared weekly budget exhausted')
            if scope is None:
                connection.execute('INSERT INTO budget_scopes VALUES (?, ?)', (scope_id, maximum))
            result = RunReservation(scope_id, maximum, week, timestamp, None, metadata_json)
            connection.execute('INSERT INTO budget_run_reservations VALUES (?, ?, ?, ?, ?, ?)', tuple(result.__dict__.values()))
            connection.executemany('INSERT INTO budget_run_requests VALUES (?, ?)', [(r['reservation_id'], scope_id) for r in children])
            return result

    def finish_run(self, scope_id: str, *, now: datetime | None = None) -> RunReservation:
        """Close admissions and release only unallocated capacity; child liabilities survive.

        Call after workers have stopped. A concurrent claim either commits first
        and retains its request hold, or sees the closed envelope and cannot dispatch.
        Unknown/unclaimed requests require their own verified settlement.
        """
        _identity(scope_id, 'scope_id')
        _, timestamp = self._time(now)
        with self._transaction() as connection:
            row = connection.execute('SELECT * FROM budget_run_reservations WHERE scope_id=?', (scope_id,)).fetchone()
            if row is None:
                raise KeyError(scope_id)
            if row['closed_at'] is not None:
                return RunReservation(**dict(row))
            if datetime.fromisoformat(timestamp) < datetime.fromisoformat(row['created_at']):
                raise ValueError('run cannot finish before reservation')
            connection.execute('UPDATE budget_run_reservations SET closed_at=? WHERE scope_id=?', (timestamp, scope_id))
            row = connection.execute('SELECT * FROM budget_run_reservations WHERE scope_id=?', (scope_id,)).fetchone()
            return RunReservation(**dict(row))

    def reserve(self, reservation_id: str, maximum_usd: str | Decimal | int, *,
                scope_id: str, scope_limit_usd: str | Decimal | int | None = None,
                now: datetime | None = None, metadata: dict[str, Any] | None = None,
                run_id: str | None = None) -> Reservation:
        """Atomically reserve a maximum; reuse of the ID returns its original state.

        Include run_id, attempt_id and purpose in metadata to bind that identity.
        A scope cap, when specified on its first use, applies across all weeks.
        Omitting the cap on later uses inherits it; changing it is rejected.
        An exact matching run envelope is used automatically. Supply run_id only
        when this request belongs to a separately capped nested scope.
        """
        _identity(reservation_id, 'reservation_id')
        _identity(scope_id, 'scope_id')
        maximum = _money(maximum_usd)
        scope_limit = None if scope_limit_usd is None else _money(scope_limit_usd)
        if run_id is not None:
            _identity(run_id, 'run_id')
        week, timestamp = self._time(now)
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError('metadata must be a JSON object')
        try:
            _json_keys(metadata)
            metadata_json = json.dumps(metadata or {}, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('metadata must be finite JSON data with string keys') from exc
        with self._transaction() as connection:
            scope = connection.execute('SELECT maximum FROM budget_scopes WHERE scope_id=?', (scope_id,)).fetchone()
            if scope is not None and scope_limit is not None and scope['maximum'] != scope_limit:
                raise BudgetConfigurationError('scope limit differs from its immutable shared configuration')
            envelope = connection.execute('SELECT * FROM budget_run_reservations WHERE scope_id=?', (run_id or scope_id,)).fetchone()
            if run_id is not None and envelope is None:
                raise BudgetConfigurationError('run envelope must be reserved before its requests')
            existing = connection.execute('SELECT * FROM budget_reservations WHERE reservation_id=?', (reservation_id,)).fetchone()
            if existing is not None:
                if (existing['scope_id'], existing['maximum_microusd'], existing['metadata_json']) != (scope_id, maximum, metadata_json):
                    raise ReservationConflict('reservation ID is bound to different scope, amount, or metadata')
                link = connection.execute('SELECT run_id FROM budget_run_requests WHERE reservation_id=?', (reservation_id,)).fetchone()
                if (None if link is None else link['run_id']) != (None if envelope is None else envelope['scope_id']):
                    raise ReservationConflict('reservation belongs to a different run envelope')
                return Reservation(**dict(existing))
            if envelope is not None:
                if envelope['closed_at'] is not None:
                    raise ReservationConflict('run reservation is closed')
                if datetime.fromisoformat(timestamp) < datetime.fromisoformat(envelope['created_at']):
                    raise ValueError('request cannot be before run reservation')
                if self._run_used(connection, envelope['scope_id']) + maximum > envelope['maximum_microusd']:
                    raise BudgetExceeded('run budget exhausted')
            status = self._status(connection, week)
            if status.overrun_ids:
                raise BudgetExceeded('recorded reservation overrun blocks further launches')
            if status.committed_microusd + (0 if envelope is not None else maximum) > self.weekly_limit_microusd:
                raise BudgetExceeded('shared weekly budget exhausted')
            if scope is None:
                connection.execute('INSERT INTO budget_scopes VALUES (?, ?)', (scope_id, scope_limit))
            else:
                scope_limit = scope['maximum']
            costs = connection.execute('SELECT maximum_microusd, actual_microusd FROM budget_reservations WHERE scope_id=?', (scope_id,)).fetchall()
            used = sum(row['maximum_microusd'] if row['actual_microusd'] is None else row['actual_microusd'] for row in costs)
            if scope_limit is not None and used + maximum > scope_limit:
                raise BudgetExceeded('scope budget exhausted')
            result = Reservation(reservation_id, scope_id, maximum, None, week, timestamp, None, metadata_json)
            connection.execute('INSERT INTO budget_reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', tuple(result.__dict__.values()))
            if envelope is not None:
                connection.execute('INSERT INTO budget_run_requests VALUES (?, ?)', (reservation_id, envelope['scope_id']))
            return result

    def claim(self, reservation_id: str, *, now: datetime | None = None) -> Reservation:
        """Acquire the one-time durable right to dispatch a held reservation.

        Commit this claim before invoking the paid callable. If the process dies
        after claiming, this ID cannot execute again even if dispatch is unknown.
        The maximum remains held until verified final billing is settled.
        Recheck current-week capacity under the transaction lock, including this
        reservation's carried hold, before authorizing first dispatch.
        """
        _identity(reservation_id, 'reservation_id')
        week, timestamp = self._time(now)
        with self._transaction() as connection:
            row = connection.execute('SELECT * FROM budget_reservations WHERE reservation_id=?', (reservation_id,)).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            if row['actual_microusd'] is not None:
                raise ReservationConflict('settled reservation cannot be dispatched')
            if row['dispatched_at'] is not None:
                raise ReservationConflict('reservation was already dispatched or dispatch is unknown')
            if datetime.fromisoformat(timestamp) < datetime.fromisoformat(row['created_at']):
                raise ValueError('dispatch cannot be before reservation')
            envelope = connection.execute("""SELECT run.closed_at FROM budget_run_reservations run
                JOIN budget_run_requests link ON link.run_id=run.scope_id WHERE link.reservation_id=?""", (reservation_id,)).fetchone()
            if envelope is not None and envelope['closed_at'] is not None:
                raise ReservationConflict('run reservation is closed')
            status = self._status(connection, week)
            if status.overrun_ids:
                raise BudgetExceeded('recorded reservation overrun blocks further launches')
            if status.blocked:
                raise BudgetExceeded('shared weekly budget exhausted')
            connection.execute('UPDATE budget_reservations SET dispatched_at=? WHERE reservation_id=?', (timestamp, reservation_id))
            row = connection.execute('SELECT * FROM budget_reservations WHERE reservation_id=?', (reservation_id,)).fetchone()
            return Reservation(**dict(row))

    def settle(self, reservation_id: str, actual_usd: str | Decimal | int | None, *, now: datetime | None = None) -> Reservation:
        """Record verified final total, or keep the maximum held for unknown billing.

        This call records even an overrun; it never pretends to undo paid usage.
        A settled total is immutable. The caller must verify billing completeness
        before supplying an amount; partial/estimated totals must remain None.
        The total charges every calendar week from dispatch (reservation when
        dispatch is unknown) through this settlement, preserving rollover liability.
        """
        _identity(reservation_id, 'reservation_id')
        actual = None if actual_usd is None else _money(actual_usd)
        _, timestamp = self._time(now)
        with self._transaction() as connection:
            row = connection.execute('SELECT * FROM budget_reservations WHERE reservation_id=?', (reservation_id,)).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            if row['actual_microusd'] is not None:
                if row['actual_microusd'] != actual:
                    raise ReservationConflict('verified settlement is immutable')
                return Reservation(**dict(row))
            if actual is not None:
                if datetime.fromisoformat(timestamp) < datetime.fromisoformat(row['dispatched_at'] or row['created_at']):
                    raise ValueError('settlement cannot be before dispatch or reservation')
                connection.execute('UPDATE budget_reservations SET actual_microusd=?, settled_at=? WHERE reservation_id=?', (actual, timestamp, reservation_id))
                row = connection.execute('SELECT * FROM budget_reservations WHERE reservation_id=?', (reservation_id,)).fetchone()
            return Reservation(**dict(row))
