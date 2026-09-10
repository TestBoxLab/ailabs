"""Genesis sleeps at 03:00: probation and decay on LAB.md, the record re-indexed, a daily
brief card written from counts (no model), and, when a model route exists and the weekly
ledger can cover the ceiling, one consolidation turn that merges the day's records into
LAB.md. Nothing here raises into the scheduler.
"""
from __future__ import annotations
import os
from datetime import timedelta, timezone
from decimal import Decimal
from wb_studio.genesis_config import cheapest
from wb_studio.genesis_harness import model_routes
from wb_studio.library import now_sao_paulo

MESSAGE = ('Nightly consolidation for {day}. Use record_search to read the records added since yesterday '
           '(turns, cards, analyses, sources). Merge what matters into LAB.md with memory_replace and memory_add, '
           'within its budget and with each entry tagged [rec:kind:id]; merge before adding when the file is near '
           'its budget. Flag contradictions between a new source or run and an Analyzed card in one short list. '
           'Move any library source filed under Other to a better topic with library_reclassify when its text makes the topic clear. '
           'Do not propose experiments.')


def _titles(items, limit=5):
    names = [str(i.get('title') or i.get('id')) for i in items]
    return '; '.join(names[:limit]) + (f' and {len(names) - limit} more' if len(names) > limit else '')


def nightly(studio):
    genesis, memory, now = studio.genesis, studio.genesis.memory, now_sao_paulo()
    day, since = now.date().isoformat(), (now - timedelta(days=1)).astimezone(timezone.utc).isoformat()
    summary = {'day': day, 'errors': []}

    def step(name, fn):
        try:
            summary[name] = fn()
        except Exception as exc:  # the job finishes and reports; it never takes the server down
            summary['errors'].append(f'{name}: {type(exc).__name__}: {exc}')
            summary[name] = None
    step('promoted', lambda: memory.promote(now))
    step('decayed', lambda: memory.decay(now))
    step('indexed', lambda: memory.index_all(studio))

    def gather():
        fresh = lambda rows, field='created_at': [r for r in rows if str(r.get(field) or '') >= since]
        cards, turns = fresh(genesis.listing('cards')), fresh(genesis.listing('turns'))
        sources = [r for r in genesis.library.records() if str(r.get('created_at') or '') >= since]
        contradicted = [r for r in genesis.library.listing() if r.get('new_evidence')]
        return {'counts': {'turns': len(turns), 'cards': len(cards), 'sources': len(sources)},
                'cards': _titles(cards), 'sources': _titles(sources), 'contradictions': _titles(contradicted)}
    step('records', gather)
    records = summary.get('records') or {'counts': {}, 'cards': '', 'sources': '', 'contradictions': ''}

    config = getattr(genesis, 'config', None)  # the nightly step's model, else the cheapest available route
    route = config.route_for('consolidation', routes=model_routes()) if config else cheapest(model_routes())
    ceiling = Decimal(os.environ.get('STUDIO_GENESIS_NIGHT_USD', '0.50'))
    turn = None
    if route:
        try:
            if studio.ledger.status(now=now).available_usd < ceiling:
                summary['errors'].append('consolidation: the weekly ledger cannot cover the night ceiling')
            else:
                turn = genesis.chat({'message': MESSAGE.format(day=day), 'model': route['id'], 'maximum_usd': str(ceiling), 'purpose': 'Genesis nightly'})
        except Exception as exc:
            summary['errors'].append(f'consolidation: {type(exc).__name__}: {exc}')
    summary['consolidation_turn'] = turn['id'] if turn else None

    def structured():
        jobs = [j for j in studio.jobs() if str(j.get('finished_at') or j.get('created_at') or '') >= since]
        cards_all = genesis.listing('cards')
        moved = [c for c in cards_all if str(c.get('updated_at') or '') >= since and c.get('kind') != 'brief']
        questions = [c for c in cards_all if c.get('kind') == 'question' and not c.get('answer')]
        waiting = [c for c in cards_all if c.get('stage') == 'approval' and c.get('plan')]
        try: ledger = studio.ledger.status(now=now); week = str(ledger.available_usd)
        except Exception: week = None
        watcher = genesis.watcher.status()
        return {'ran': [{'id': j['id'], 'title': j.get('title') or j['id'], 'status': j.get('status')} for j in jobs][:12],
                'moved': [{'id': c['id'], 'title': c['title'], 'stage': c['stage']} for c in moved][:12],
                'questions': [{'id': c['id'], 'title': c['title'], 'default': c.get('default')} for c in questions][:12],
                'waiting': [{'id': c['id'], 'title': c['title'], 'reason': c.get('waiting')} for c in waiting][:12],
                'allowance': {'today_usd': watcher.get('today_usd'), 'cap_usd': watcher.get('cap_usd'), 'week_usd': week}}
    step('structured', structured)
    counts = records['counts']
    first = f"Since yesterday: {counts.get('turns', 0)} turns, {counts.get('cards', 0)} cards and {counts.get('sources', 0)} sources"
    first += '.' if turn else ' (data only; no model route was available for consolidation).'
    sentences = [first]
    if records['cards'] or records['sources']:
        sentences.append('New: ' + '; '.join(p for p in (records['cards'], records['sources']) if p) + '.')
    if records['contradictions']:
        sentences.append('Newer evidence contradicts: ' + records['contradictions'] + '.')

    def brief():
        identity = 'brief-' + day
        payload = {'id': identity, 'title': 'Daily brief ' + day, 'kind': 'brief', 'stage': 'research', 'body': ' '.join(sentences),
                   'brief': summary.get('structured'), 'evidence': [{'turn': turn['id']}] if turn else []}
        if genesis.path('cards', identity).exists():
            payload['revision'] = genesis.read('cards', identity)['revision']
        return genesis.card(payload)['id']
    step('brief', brief)
    return summary


DAILY = ('genesis-sleep', 3, nightly)
