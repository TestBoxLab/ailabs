"""Signed, single-job funding transfers from the existing shared budget ledger."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from decimal import Decimal, InvalidOperation


def fingerprint(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _key(secret):
    if not isinstance(secret, str) or len(secret) < 32:
        raise ValueError('Configure a funding signing key of at least 32 characters.')
    return secret.encode()


def sign(claims, secret):
    body = base64.urlsafe_b64encode(json.dumps(claims, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).decode()
    return body + '.' + hmac.new(_key(secret), body.encode(), hashlib.sha256).hexdigest()


def verify(token, secret, *, actor, job, spec, check_expiry=True):
    if not isinstance(token, str) or len(token) > 8000:
        raise ValueError('Invalid funding authorization.')
    body, separator, signature = token.partition('.')
    expected = hmac.new(_key(secret), body.encode(), hashlib.sha256).hexdigest()
    if not separator or not hmac.compare_digest(signature, expected):
        raise ValueError('Invalid funding signature.')
    try:
        claims = json.loads(base64.b64decode(body, altchars=b'-_', validate=True))
        amount = Decimal(claims['maximum_usd'])
    except (ValueError, TypeError, KeyError, InvalidOperation):
        raise ValueError('Invalid funding claims.') from None
    if claims.get('actor') != actor or claims.get('job') != job or claims.get('spec_sha256') != fingerprint(spec):
        raise ValueError('Funding belongs to a different actor, job, or specification.')
    if claims.get('version') != 1 or not amount.is_finite() or amount <= 0:
        raise ValueError('Funding must name a positive finite reserved allowance.')
    if type(claims.get('expires')) is not int or (check_expiry and claims['expires'] <= time.time()):
        raise ValueError('Funding authorization expired; no execution may start.')
    if any(not isinstance(claims.get(k), str) or not claims[k] or len(claims[k]) > 160
           for k in ('reservation', 'scope', 'model', 'effort')):
        raise ValueError('Funding is missing its reservation or model configuration.')
    return claims
