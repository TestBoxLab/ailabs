"""Pre-fund remote repair work once; uncertain remote charges remain reserved."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from wb_repair.grants import fingerprint, sign


def issue(ledger, *, actor, job, spec, maximum_usd, model, effort, secret):
    # Validate signer before touching budget state.
    sign({}, secret)
    maximum = Decimal(str(maximum_usd))
    if not maximum.is_finite() or maximum <= 0:
        raise ValueError('A positive repair allowance is required.')
    scope = 'remote-' + job
    reservation = scope + '-execution'
    metadata = {'purpose': 'Genesis remote repair', 'actor': actor, 'job': job,
                'spec_sha256': fingerprint(spec), 'model': model, 'effort': effort}
    run = ledger.reserve_run(scope, maximum, metadata=metadata)
    if run.closed_at is not None:
        raise ValueError('This repair funding scope is already closed.')
    held = ledger.reserve(reservation, maximum, scope_id=scope, scope_limit_usd=maximum, metadata=metadata)
    if held.dispatched_at is None:
        held = ledger.claim(reservation)
    # Re-signing the same immutable job grant reconciles an uncertain HTTP outcome.
    # It never authorizes another job or opens a closed scope.
    expires = int(datetime.fromisoformat(held.dispatched_at).timestamp()) + 3600
    claims = {**metadata, 'version': 1, 'scope': scope, 'reservation': reservation,
              'maximum_usd': str(maximum), 'expires': expires}
    return sign(claims, secret)


def reconcile(ledger, claims, result):
    """Only call with a terminal receipt obtained from the authenticated repair service."""
    if result.get('job') != claims['job'] or result.get('reservation') != claims['reservation']:
        raise ValueError('The execution receipt does not match the reserved repair.')
    if result.get('status') not in ('awaiting_review', 'failed', 'interrupted'):
        raise ValueError('Only terminal execution can settle its reservation.')
    actual = result.get('cost_usd')
    usage = result.get('usage')
    if actual is not None and (not isinstance(usage, dict) or
            any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('prompt_tokens', 'output_tokens'))):
        raise ValueError('Known charges require provider usage evidence.')
    ledger.settle(claims['reservation'], actual, usage=usage,
                  outcome='completed' if result['status'] == 'awaiting_review' else 'error')
    ledger.finish_run(claims['scope'])
