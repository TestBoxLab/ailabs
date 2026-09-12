"""Typed live cards carried by the existing, durable Genesis tool event stream.

A receipt replaces the card with the same card_id within its turn. It is presentation,
not a research record, saved configuration, navigation command or benchmark verdict.
No second store or event channel is needed: the harness retains the complete receipt
in tool_completed.detail, so the browser can rebuild cards after a reconnect.
"""
from __future__ import annotations

import json
import re

from wb_studio.genesis_show import show
from wb_studio.memory import CREDENTIAL

TEMPLATES = ('research', 'thinking', 'architecture', 'configuration', 'execution', 'result', 'warning')
STATUSES = ('active', 'complete', 'blocked')
CARD_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
MAX_RECEIPT_CHARS = 5500  # safely below the harness's 6,000-character event detail cap
FIELDS = {'card_id', 'template', 'title', 'detail', 'status', 'items', 'sources', 'route', 'label'}

PROTOCOL = (
    'present(card_id, template, title, detail?, status?, items?, sources?, route?, label?): '
    'show a live card in the Genesis window at a meaningful work transition. Templates are '
    'research, thinking, architecture, configuration, execution, result and warning. The '
    'browser supplies the matching animation; never send HTML, scripts, CSS or ASCII frames. '
    'Reuse a short card_id to replace that card within this turn; every call is a complete '
    'replacement. status is active (default), complete or blocked. Keep title to 120 characters, '
    'detail to 1,200, items to six {label,value} rows and sources to six {label,ref} citations. '
    'Refs name real sources or source lines you actually read. Cards describe observable work '
    'and provisional hypotheses, never hidden reasoning, invented progress or an unmeasured '
    'benchmark win. complete means this card activity finished, not that a task passed. '
    'A route is an allowlisted Studio link; the reader controls Follow. Use show for guided '
    'navigation and edit_architecture/save_architecture or other real tools to make changes: '
    'present saves or configures nothing. Emit cards alongside useful tools, not on every '
    'log line; the UI already animates ordinary tool activity without extra model calls.'
)


def _text(value, name, maximum, *, optional=False):
    if not isinstance(value, str):
        raise ValueError(f'present {name} must be plain text.')
    # Redact before budgeting: a short token can expand to '[redacted]' in the harness.
    value = CREDENTIAL.sub('[redacted]', value.strip())
    if (not value and not optional) or len(value) > maximum:
        raise ValueError(f'present {name} needs {"0" if optional else "1"} to {maximum} characters.')
    return value


def _rows(payload, field, lengths):
    rows = payload.get(field, [])
    if not isinstance(rows, list) or len(rows) > 6:
        raise ValueError(f'present {field} must be a list of at most six rows.')
    clean = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(lengths):
            raise ValueError(f'Each present {field} row needs only ' + ', '.join(lengths) + '.')
        clean.append({key: _text(row[key], field + '.' + key, limit)
                      for key, limit in lengths.items()})
    return clean


def present(genesis, payload):
    """Validate before returning the receipt that the harness persists and streams."""
    if not isinstance(payload, dict) or set(payload) - FIELDS:
        raise ValueError('present accepts only card_id, template, title, detail, status, items, sources, route and label.')
    identity = _text(payload.get('card_id'), 'card_id', 64)
    if not CARD_ID.fullmatch(identity):
        raise ValueError('present card_id must start with a letter or digit and use only letters, digits, dash and underscore.')
    template, status = payload.get('template'), payload.get('status', 'active')
    if template not in TEMPLATES:
        raise ValueError('Choose a present template: ' + ', '.join(TEMPLATES) + '.')
    if status not in STATUSES:
        raise ValueError('present status must be active, complete or blocked.')
    receipt = {'presentation': True, 'card_id': identity, 'template': template,
               'title': _text(payload.get('title'), 'title', 120),
               'detail': _text(payload.get('detail', ''), 'detail', 1200, optional=True),
               'status': status,
               'items': _rows(payload, 'items', {'label': 80, 'value': 240}),
               'sources': _rows(payload, 'sources', {'label': 100, 'ref': 240})}
    if 'route' in payload:
        label = _text(payload.get('label', ''), 'label', 80, optional=True)
        link = show(genesis, {'route': payload['route'], 'label': label})
        receipt.update(route=link['route'], label=link['label'])
    elif 'label' in payload:
        raise ValueError('present label belongs to a route; supply the Studio route too.')
    if len(json.dumps(receipt, ensure_ascii=False)) > MAX_RECEIPT_CHARS:
        raise ValueError('This present card is too large for the saved event. Shorten detail, items or source refs.')
    return receipt


TOOLS = {'present': present}
