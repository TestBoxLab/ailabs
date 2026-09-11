"""Genesis autonomy: three dials, one switch, and the activity record (feature 021).

Reading is always on. Cards is `act` (Genesis creates, moves and writes cards and
reports it) or `off`. Runs is `smoke` (Genesis launches a plan itself when it is at
smoke scale and its ceiling fits the card and daily allowances and the ledger),
`propose` (every plan waits for a person) or `off`. `paused` is the kill switch: the
watcher stops and every Genesis launch is refused until a person turns it back on.
All three limits are code, not prompt text. Every change is written to the activity
record, one JSON line per entry, which the Genesis page shows and a person can export.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from wb_orchestrator.config import SMOKE_SCALE_ATTEMPTS

CARD_LEVELS = ('act', 'off')
RUN_LEVELS = ('smoke', 'propose', 'off')
INITIATIVE_LEVELS = ('open', 'off')
ENGINEER_LEVELS = ('propose', 'off')  # there is no level at which a fix applies itself
# Every dial defaults off. An absent autonomy.json means a workspace nobody has
# configured, and such a workspace must do nothing paid: a fresh Studio with provider
# keys used to begin working cards within thirty seconds and could dispatch a run whose
# operator was `genesis:smoke` and whose approver was a model turn (feature 024, FR-002).
DEFAULTS = {'cards': 'off', 'runs': 'off', 'initiative': 'off', 'engineer': 'off', 'paused': False}
WORDS = {
    'cards': {'act': 'Genesis creates, moves and writes cards and reports it', 'off': 'Genesis only reads; a person moves every card'},
    'runs': {'smoke': f'Genesis launches plans of at most {SMOKE_SCALE_ATTEMPTS} attempts per competitor within its allowances',
             'propose': 'Every plan waits for a person, whatever its size', 'off': 'Genesis never proposes a run'},
    'initiative': {'open': "Genesis opens one card a day from the lab's open threads, and may take it to a smoke run",
                   'off': 'Genesis works only the cards people and triggers give it'},
    'engineer': {'propose': 'Once a day Genesis specs one failure and a Codex agent writes the diff; every fix waits for a person',
                 'off': 'Genesis does not write fixes'},
}


def stamp():
    return datetime.now(timezone.utc).isoformat()


class Autonomy:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'autonomy.json'
        self.log = self.root / 'activity.jsonl'
        self.lock = threading.RLock()

    # ---- dials ---------------------------------------------------------------------
    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding='utf8'))
        except (OSError, ValueError):
            data = {}
        out = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
        out['words'] = {key: WORDS[key][out[key]] for key in WORDS}
        out['smoke_attempts'] = SMOKE_SCALE_ATTEMPTS
        out['card_usd'] = os.environ.get('STUDIO_GENESIS_CARD_USD', '2.00')
        out['daily_usd'] = os.environ.get('STUDIO_GENESIS_DAILY_USD', '6.00')
        return out

    def set(self, payload: dict, by: str = 'human:studio') -> dict:
        """A person's change from the interface. Unknown keys are ignored; bad values refused."""
        changes = {}
        if 'cards' in payload:
            if payload['cards'] not in CARD_LEVELS:
                raise ValueError('Cards is act or off.')
            changes['cards'] = payload['cards']
        if 'runs' in payload:
            if payload['runs'] not in RUN_LEVELS:
                raise ValueError('Runs is smoke, propose or off.')
            changes['runs'] = payload['runs']
        if 'initiative' in payload:
            if payload['initiative'] not in INITIATIVE_LEVELS:
                raise ValueError('Initiative is open or off.')
            changes['initiative'] = payload['initiative']
        if 'engineer' in payload:
            if payload['engineer'] not in ENGINEER_LEVELS:
                raise ValueError('Engineer is propose or off.')
            changes['engineer'] = payload['engineer']
        if 'paused' in payload:
            changes['paused'] = bool(payload['paused'])
        with self.lock:
            before = self.read()
            current = {k: before[k] for k in DEFAULTS}
            current.update(changes)
            self.path.write_text(json.dumps(current, indent=1), encoding='utf8')
        for key, value in changes.items():
            if before.get(key) != value:
                self.record('autonomy', by=by, setting=key, before=before.get(key), after=value)
        return self.read()

    # ---- the gate for a launch -----------------------------------------------------
    def may_launch(self, plan: dict, today_usd: Decimal, card_usd: Decimal, daily_usd: Decimal) -> tuple[bool, str | None]:
        """Whether Genesis may launch this plan itself, and the plain reason when it may not.

        `plan` carries attempts_per_competitor and maximum_usd as the Studio computed them.
        """
        state = self.read()
        if state['paused']:
            return False, 'Genesis is paused; a person has to turn it back on.'
        if state['runs'] == 'off':
            return False, 'The Runs dial is off.'
        if state['runs'] == 'propose':
            return False, 'The Runs dial says every plan waits for a person.'
        attempts = int(plan.get('attempts_per_competitor') or 0)
        if attempts > SMOKE_SCALE_ATTEMPTS:
            return False, f'{attempts} attempts per competitor is above smoke scale ({SMOKE_SCALE_ATTEMPTS}); a person approves it.'
        maximum = Decimal(str(plan.get('maximum_usd') or '0'))
        if maximum <= 0:
            return False, 'The plan declares no spending ceiling.'
        if maximum > card_usd:
            return False, f'The ceiling ${maximum:.2f} is above the per-card allowance ${card_usd:.2f}; a person approves it.'
        if today_usd + maximum > daily_usd:
            return False, f"Today's allowance ${daily_usd:.2f} cannot cover ${maximum:.2f} more; it waits for tomorrow or a person."
        return True, None

    # ---- the activity record -------------------------------------------------------
    def record(self, kind: str, card: str | None = None, **data) -> dict:
        entry = {'at': stamp(), 'kind': kind, 'card': card, **{k: v for k, v in data.items() if v is not None}}
        with self.lock:
            with self.log.open('a', encoding='utf8', newline='\n') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        return entry

    def tail(self, limit: int = 100, card: str | None = None) -> list[dict]:
        try:
            lines = self.log.read_text(encoding='utf8').splitlines()
        except OSError:
            return []
        out = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if card and entry.get('card') != card:
                continue
            out.append(entry)
            if len(out) >= max(1, min(1000, int(limit))):
                break
        return out


def plan_lines(studio, proposal: dict) -> dict:
    """The plan as lines a person can check, with numbers computed by the Studio, never by the model.

    Refuses what the Studio would refuse at launch, so a plan that cannot run is never shown as one.
    """
    from wb_studio.runtime_registry import check_launch
    track = proposal.get('track', 'agentic-request')
    models = proposal.get('models') or []
    if not isinstance(models, list):
        raise ValueError('models is a list')
    versions = check_launch(studio, proposal.get('architectures'), models, track=track)
    tasks = proposal.get('tasks') or []
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('The plan names its tasks.')
    bare = proposal.get('bare_models') or []
    competitors = []
    for v in versions:
        if v['id'] == 'without-monarch':
            competitors += [str(m) for m in models]
        else:
            competitors.append(v['name'])
    competitors += ['Bare ' + str(b) for b in bare]
    if not competitors:
        raise ValueError('The plan names at least one competitor.')
    maximum = Decimal(str(proposal.get('maximum_usd') or '0'))
    if maximum <= 0:
        raise ValueError('The plan declares maximum_usd, its spending ceiling.')
    attempts = len(tasks)
    total = attempts * len(competitors)
    lines = [
        f'{len(tasks)} tasks, each run once by every competitor',
        f'{len(competitors)} competitors: ' + ', '.join(competitors),
        f'{attempts} attempts per competitor, {total} in all' + (' (smoke scale)' if attempts <= SMOKE_SCALE_ATTEMPTS else f' (above smoke scale, {SMOKE_SCALE_ATTEMPTS})'),
        f'Spending ceiling ${maximum:.2f}, reserved in the weekly ledger before the first request',
        'Track: ' + ('agentic requests' if track == 'agentic-request' else 'workflow building'),
    ]
    return {'lines': lines, 'attempts_per_competitor': attempts, 'attempts': total, 'competitors': competitors,
            'maximum_usd': str(maximum), 'smoke': attempts <= SMOKE_SCALE_ATTEMPTS, 'task_count': len(tasks)}


def background_wanted(autonomy) -> bool:
    """Whether any dial asks for unattended work, so the watcher and scheduler may start.

    All dials off means a workspace nobody has configured. Starting the background
    threads there costs money for work no one asked for, so the owner starts them only
    when a person has turned something on (feature 024, FR-002).
    """
    dials = autonomy.read()
    if dials.get('paused'):
        return False
    return any(dials.get(key, 'off') != 'off' for key in ('cards', 'runs', 'initiative', 'engineer'))
