"""Genesis watcher: works dropped cards on its own, one at a time, with money behind the existing gates.

A card someone dropped (a link, a run id, a hypothesis) or a trigger created (a finished run, a
library source with full text) waits with work.status "queued". Every 30 s, or when notified, the
watcher takes the oldest one and asks Genesis for one free-work turn, reserved through the weekly
ledger at the per-card ceiling and counted against a daily cap. It never launches an experiment.
"""
from __future__ import annotations
import json
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from wb_results.evidence import write_json
from wb_studio.library import now_sao_paulo

TERMINAL = ('completed', 'failed', 'cancelled', 'interrupted')
FILED_LIMIT = 5000  # how many filed keys the watcher's own state carries


def _on(name):
    return os.environ.get(name, '1').lower() not in ('0', 'false', 'no', 'off')


def scripted_only(job):
    arms = job.get('settings', {}).get('arms') or [{'id': m} for m in job.get('settings', {}).get('models', [])]
    return all(a.get('kind') == 'scripted' or a.get('id') in ('oracle', 'sloppy', 'null') for a in arms)


class Watcher:
    def __init__(self, studio, genesis=None):
        self.studio = studio
        self._genesis = genesis
        self.path = studio.directory / 'genesis' / 'watcher.json'
        self.lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    @property
    def genesis(self):
        return self._genesis or self.studio.genesis

    @property
    def cap_usd(self):
        return Decimal(os.environ.get('STUDIO_GENESIS_DAILY_USD', '6.00'))

    @property
    def card_usd(self):
        return Decimal(os.environ.get('STUDIO_GENESIS_CARD_USD', '2.00'))

    def _read(self):
        try:
            return json.loads(self.path.read_text(encoding='utf8'))
        except (OSError, ValueError):
            return {}

    def _write(self, **changes):
        with self.lock:
            state = {**self._read(), **changes}
            write_json(self.path, state)
            return state

    def pause(self, flag):
        self._write(paused=bool(flag))
        self.notify()

    def notify(self):
        self._wake.set()

    def start(self, interval_s=30):
        self.interval_s = interval_s
        """One daemon thread; only the owning web process calls this. It never raises out."""
        if self._thread:
            return

        def loop():
            while not self._stop.is_set():
                self._wake.wait(interval_s)
                self._wake.clear()
                try:
                    self.wake()
                except Exception as exc:
                    self._write(last_error=type(exc).__name__ + ': ' + str(exc)[:300])
        self._thread = threading.Thread(target=loop, daemon=True, name='genesis-watcher')
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.notify()

    def today_usd(self):
        """What Genesis committed today (America/Sao_Paulo): the settled receipts of
        finished turns, the full ceiling of a running one, and the reserved maximum of
        every run it launched.

        The launches were missing (feature 024, FR-004). A run is by far the most
        expensive thing Genesis can start, so summing only its own turns meant N
        self-launched runs each saw the same untouched allowance, while the number a
        person read on the Genesis page barely moved. The reserved maximum is the right
        figure for a gate: it is what the lab is committed to before the work runs.
        """
        zone = now_sao_paulo().tzinfo
        today = now_sao_paulo().date()
        total = Decimal('0')
        for turn in self.genesis.listing('turns'):
            if datetime.fromisoformat(turn['created_at']).astimezone(zone).date() != today:
                continue
            if turn.get('status') == 'running':
                total += Decimal(str(turn['maximum_usd']))
            else:
                total += sum((Decimal(str(e.get('cost_usd') or 0)) for e in turn.get('events', []) if e.get('type') == 'usage'), Decimal('0'))
        return total + self._launched_today(zone, today)

    def _launched_today(self, zone, today) -> Decimal:
        """The reserved maximum of every run Genesis launched today, whoever pressed it.

        The activity record is the source: `_dispatch` writes one `launch` entry per
        run with the plan's ceiling, so this needs no second store and no ledger read.
        """
        total = Decimal('0')
        for entry in self.genesis.autonomy.tail(limit=1000):
            if entry.get('kind') != 'launch' or entry.get('maximum_usd') is None:
                continue
            try:
                when = datetime.fromisoformat(entry['at']).astimezone(zone).date()
                if when == today:
                    total += Decimal(str(entry['maximum_usd']))
            except (ValueError, TypeError, KeyError, InvalidOperation):
                continue   # an unreadable entry must not open the gate or close it
        return total

    def _cards(self, status):
        return [c for c in self.genesis.listing('cards') if (c.get('work') or {}).get('status') == status]

    def refusal(self):
        """Why no turn can start now, in plain words, or None."""
        from wb_studio.genesis_harness import model_routes
        ceiling = self.card_usd
        if not any(r['available'] for r in model_routes()):
            return 'Waiting: no model route is available'
        if self.today_usd() + ceiling > self.cap_usd:
            return f"Waiting: today's cap of ${self.cap_usd:.2f} is reached"
        status = self.studio.ledger.status()
        if status.blocked or status.available_usd < ceiling:
            return f'Waiting: the weekly ledger cannot cover ${ceiling:.2f}'
        ok, reason = self.genesis.allowance_allows(ceiling)
        if not ok:
            return 'Waiting: ' + reason
        return None

    def warning(self, today=None):
        """A soft warning at 80% of the day's cap or of the envelope, before anything is refused (L4).
        `today` is passed in by `status`, which already read every turn of the day."""
        today, cap = self.today_usd() if today is None else today, self.cap_usd
        if cap and today >= cap * Decimal('0.8'):
            return f"Today's allowance is {int(today / cap * 100)}% spent (${today:.2f} of ${cap:.2f})"
        allowance = self.genesis.allowance()
        if allowance and allowance['left_usd'] is not None:
            left, limit = Decimal(allowance['left_usd']), Decimal(allowance['limit_usd'])
            if limit and left <= limit * Decimal('0.2'):
                return f"The weekly allowance has ${left:.2f} of ${limit:.2f} left"
        return None

    def triggers(self):
        """Cards for finished runs and full-text library sources nobody dropped; each at most once."""
        cards = self.genesis.listing('cards')
        pointed = {(c.get('kind'), e.get('kind'), e.get('id')) for c in cards for e in c.get('evidence', []) if isinstance(e, dict)}
        pointed |= {('run', 'run', c['job']) for c in cards if c.get('job')}  # a run Genesis launched from a plan is debriefed on that card, not filed twice (R6)
        # Only what arrives after the watcher first ran: history is not re-worked at the first start.
        state = self._read()
        since = state.get('since')
        if not since:
            since = datetime.now(timezone.utc).isoformat()
            self._write(since=since)
        # What the watcher has already filed, kept in its own state. `pointed` alone is not enough:
        # it reads the card's kind and evidence, and `save_research` lets the model rewrite both, so a
        # relabelled card made the trigger file the same run again on every wake, for ever.
        filed = list(state.get('filed') or [])
        seen, opened = set(filed), len(filed)
        if _on('STUDIO_GENESIS_AUTO_RUNS'):
            for job in self.studio.jobs():
                if (job.get('finished_at') or job.get('created_at') or '') < since:
                    continue
                key = 'run:' + str(job['id'])
                if key in seen or job.get('status') not in TERMINAL or scripted_only(job) or ('run', 'run', job['id']) in pointed:
                    continue
                self.genesis.intake('run', str(job.get('title') or job['id']), job['id'], [{'kind': 'run', 'id': job['id']}])
                filed.append(key); seen.add(key)
        if _on('STUDIO_GENESIS_AUTO_SOURCES'):
            for source in self.genesis.library.records():
                if (source.get('created_at') or '') < since:
                    continue
                key = 'source:' + str(source['id'])
                if key in seen or not source.get('full_text_available') or source.get('status') != 'saved' or ('source', 'library', source['id']) in pointed:
                    continue
                self.genesis.intake('source', source['title'], source.get('url') or source['title'], [{'kind': 'library', 'id': source['id']}])
                filed.append(key); seen.add(key)
                if source.get('columns') is None and source.get('url') and not self.refusal():  # feature 022: extract its columns, one paid turn behind the same gates
                    from wb_studio import genesis_ingest
                    try:
                        genesis_ingest.ingest(self.genesis, source['id'])
                    except Exception as exc:
                        self._write(last_error='ingest ' + source['id'] + ': ' + type(exc).__name__ + ': ' + str(exc)[:200])
        if len(filed) != opened:
            # ponytail: a rolling window of the newest keys; a lab that files more than this many
            # records wants the set in the index, not in one JSON file.
            self._write(filed=filed[-FILED_LIMIT:])

    def wake(self):
        """One pass: create trigger cards, then work the oldest queued card if nothing is working and the gates allow."""
        self._write(last_wake=datetime.now(timezone.utc).isoformat(), last_error=None)
        from wb_studio.genesis_missions import reconcile
        reconcile(self.genesis)
        self.genesis.debrief()  # R2: a finished planned run re-queues its card here, not on a page load
        self.triggers()
        if self.genesis.autonomy.read()['paused']:
            self._write(reason='Paused by a person: Genesis does nothing until the switch is turned back on')
            return None
        if self.genesis.autonomy.read()['cards'] == 'off':
            self._write(reason='The Cards dial is off: Genesis only reads until a person turns it back on')
            return None
        if self._read().get('paused') or self._cards('working'):
            return None
        queue = [c for c in self._cards('queued') if c.get('auto')]
        from wb_studio import genesis_ranking
        queue = genesis_ranking.order(genesis_ranking.with_scores(self.genesis, queue))  # feature 022: best-ranked first, not oldest first
        if not queue:
            self._write(reason=None)
            return None
        card = queue[0]
        reason = self.refusal()
        if reason:
            with self.genesis.lock:
                card = self.genesis.read('cards', card['id'])
                card['work']['reason'] = reason
                write_json(self.genesis.path('cards', card['id']), card)
            if self._read().get('reason') != reason:  # R5: an attempt that was refused is in the record, once per reason
                self.genesis.autonomy.record('refused', card=card['id'], reason=reason)
            self._write(reason=reason)
            return None
        self._write(reason=None)
        return self.genesis.work(card)

    def status(self):
        state = self._read()
        working = self._cards('working')
        from wb_studio import genesis_ranking
        queue = genesis_ranking.order(genesis_ranking.with_scores(self.genesis, [c for c in self._cards('queued') if c.get('auto')]))
        today = self.today_usd()  # every turn of the day is read once here, not once more inside warning()
        return {'paused': bool(state.get('paused')) or bool(self.genesis.autonomy.read()['paused']), 'queue': [c['id'] for c in queue],
                'working': working[0]['id'] if working else None, 'today_usd': str(today), 'cap_usd': str(self.cap_usd),
                'last_wake': state.get('last_wake'), 'reason': state.get('reason'), 'last_error': state.get('last_error'), 'warning': self.warning(today),
                'interval_s': getattr(self, 'interval_s', 30)}
