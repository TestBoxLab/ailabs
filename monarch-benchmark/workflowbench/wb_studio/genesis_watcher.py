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
from decimal import Decimal
from wb_results.evidence import write_json
from wb_studio.library import now_sao_paulo

TERMINAL = ('completed', 'failed', 'cancelled', 'interrupted')


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
        """What every Genesis turn of today (America/Sao_Paulo) cost, cards or not (R5): the settled receipts of
        finished turns, the full ceiling of a running one."""
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
        if _on('STUDIO_GENESIS_AUTO_RUNS'):
            for job in self.studio.jobs():
                if (job.get('finished_at') or job.get('created_at') or '') < since:
                    continue
                if job.get('status') in TERMINAL and not scripted_only(job) and ('run', 'run', job['id']) not in pointed:
                    self.genesis.intake('run', str(job.get('title') or job['id']), job['id'], [{'kind': 'run', 'id': job['id']}])
        if _on('STUDIO_GENESIS_AUTO_SOURCES'):
            for source in self.genesis.library.records():
                if (source.get('created_at') or '') < since:
                    continue
                if source.get('full_text_available') and source.get('status') == 'saved' and ('source', 'library', source['id']) not in pointed:
                    self.genesis.intake('source', source['title'], source.get('url') or source['title'], [{'kind': 'library', 'id': source['id']}])
                    if source.get('columns') is None and source.get('url') and not self.refusal():  # feature 022: extract its columns, one paid turn behind the same gates
                        from wb_studio import genesis_ingest
                        try:
                            genesis_ingest.ingest(self.genesis, source['id'])
                        except Exception as exc:
                            self._write(last_error='ingest ' + source['id'] + ': ' + type(exc).__name__ + ': ' + str(exc)[:200])

    def wake(self):
        """One pass: create trigger cards, then work the oldest queued card if nothing is working and the gates allow."""
        self._write(last_wake=datetime.now(timezone.utc).isoformat(), last_error=None)
        self.genesis.debrief()  # R2: a finished planned run re-queues its card here, not on a page load
        self.triggers()
        if self.genesis.autonomy.read()['paused']:
            self._write(reason='Paused by a person: Genesis does nothing until the switch is turned back on')
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
        return {'paused': bool(state.get('paused')) or bool(self.genesis.autonomy.read()['paused']), 'queue': [c['id'] for c in queue],
                'working': working[0]['id'] if working else None, 'today_usd': str(self.today_usd()), 'cap_usd': str(self.cap_usd),
                'last_wake': state.get('last_wake'), 'reason': state.get('reason'), 'last_error': state.get('last_error'),
                'interval_s': getattr(self, 'interval_s', 30)}
