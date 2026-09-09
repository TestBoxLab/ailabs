"""Server-only, single-dispatch Gemini API control with conservative paid admission.

Rate card checked 2026-09-08: https://ai.google.dev/gemini-api/docs/pricing
Limits: https://ai.google.dev/gemini-api/docs/latest-model
Usage: https://ai.google.dev/api/generate-content#UsageMetadata
Count: https://ai.google.dev/api/tokens
Provider usage estimates are NOT invoices. Unknown outcomes retain their full hold.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, localcontext
import hashlib
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from wb_orchestrator.budget import BudgetLedger

MODEL = 'gemini-3.7-flash'
INPUT_CEILING = 1_048_576
THINKING_CEILING = 65_536
INPUT_RATE = Decimal('0.75')
OUTPUT_RATE = Decimal('3.75')
RATE_EXPIRES = datetime(2027, 1, 1, tzinfo=timezone.utc)


PROVIDER_REASONS = frozenset({'API_KEY_INVALID', 'API_KEY_EXPIRED', 'API_KEY_SERVICE_BLOCKED',
    'SERVICE_DISABLED', 'BILLING_DISABLED', 'CONSUMER_INVALID'})

PROVIDER_STATUSES = frozenset({'INVALID_ARGUMENT', 'FAILED_PRECONDITION', 'OUT_OF_RANGE',
    'UNAUTHENTICATED', 'PERMISSION_DENIED', 'NOT_FOUND', 'ALREADY_EXISTS', 'ABORTED',
    'RESOURCE_EXHAUSTED', 'CANCELLED', 'DATA_LOSS', 'UNKNOWN', 'INTERNAL',
    'UNAVAILABLE', 'DEADLINE_EXCEEDED', 'UNIMPLEMENTED'})


class PaidGatewayError(RuntimeError):
    """A sanitized provider error; the caller must not retry an unknown dispatch."""
    def __init__(self, message, *, http_status=None, provider_status=None, provider_reason=None):
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.provider_status = provider_status if isinstance(provider_status, str) and provider_status in PROVIDER_STATUSES else None
        self.provider_reason = provider_reason if isinstance(provider_reason, str) and provider_reason in PROVIDER_REASONS else None
        detail = '' if self.http_status is None else f' (HTTP {self.http_status}' + (f' / {self.provider_status}' if self.provider_status else '') + ')'
        if self.provider_reason:
            detail += f' [{self.provider_reason}]'
        super().__init__(message + detail)


def credential_status() -> dict:
    for name in ('GEMINI_API_KEY', 'GOOGLE_API_KEY'):
        if os.environ.get(name, '').strip():
            return {'provider': 'google', 'configured': True, 'source': name}
    return {'provider': 'google', 'configured': False, 'source': None}


def _cost(prompt: int, output: int) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return ((Decimal(prompt) * INPUT_RATE + Decimal(output) * OUTPUT_RATE) / Decimal(1_000_000)).quantize(Decimal('0.000001'), rounding=ROUND_CEILING)


def _integer(value):
    return type(value) is int and 0 <= value <= 10_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PaidGateway:
    def __init__(self, ledger: BudgetLedger, model=MODEL, max_output_tokens=4096, transport=None):
        if model != MODEL:
            raise ValueError('No verified rate card and limits for this model')
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 65_536:
            raise ValueError('max_output_tokens must be between 1 and 65536')
        self.ledger = ledger
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.transport = transport or self._post
        self.thinking_level = "low"

    def _post(self, operation, payload):
        # A fixed origin, no redirects, no SDK retries, and header authentication.
        if operation not in ('countTokens', 'generateContent'):
            raise ValueError('Unsupported operation')
        status = credential_status()
        if not status['configured']:
            raise PaidGatewayError('Google API credential is not configured')
        key = os.environ[status['source']].strip()
        streaming = operation == 'generateContent' and bool(getattr(self,'on_text',None))
        endpoint = 'streamGenerateContent?alt=sse' if streaming else operation
        request = Request(
            f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:{endpoint}',
            data=json.dumps(payload, allow_nan=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'x-goog-api-key': key},
            method='POST',
        )
        try:
            with build_opener(_NoRedirect()).open(request, timeout=120) as response:
                if not streaming:
                    data = json.loads(response.read(32 * 1024 * 1024))
                else:
                    data={};parts=[];candidate={};size=0
                    for line in response:
                        size+=len(line)
                        if size>32*1024*1024: raise ValueError('Response too large')
                        if not line.startswith(b'data:'): continue
                        chunk=json.loads(line[5:].strip())
                        if chunk.get('usageMetadata'): data['usageMetadata']=chunk['usageMetadata']
                        for row in chunk.get('candidates',[]):
                            candidate.update({k:v for k,v in row.items() if k!='content'})
                            for part in row.get('content',{}).get('parts',[]):
                                parts.append(part)
                                if part.get('text') and not part.get('thought'): self.on_text(part['text'])
                    candidate['content']={'role':'model','parts':parts}
                    data['candidates']=[candidate]
            if not isinstance(data, dict):
                raise ValueError('Invalid response')
            return data
        except HTTPError as exc:
            provider_status = None
            provider_reason = None
            try:
                body = json.loads(exc.read(65536))
                provider_status = body.get('error', {}).get('status')
                for item in body.get('error', {}).get('details', []):
                    reason = item.get('reason') if isinstance(item, dict) else None
                    if isinstance(reason, str) and reason in PROVIDER_REASONS:
                        provider_reason = reason
                        break
            except Exception:
                pass
            raise PaidGatewayError('Google API request failed; no automatic retry',
                                   http_status=exc.code, provider_status=provider_status, provider_reason=provider_reason) from None
        except Exception:
            raise PaidGatewayError('Google API request failed; no automatic retry') from None

    def request(self, contents: list, system: str, tools: list, *, scope_id: str,
                scope_limit_usd: Decimal, request_id: str) -> dict:
        if self.thinking_level not in ("low", "medium", "high"):
            raise ValueError("Unsupported thinking level")
        if datetime.now(timezone.utc) >= RATE_EXPIRES:
            raise PaidGatewayError('Verified Gemini introductory pricing expired; refresh the rate card')
        if not isinstance(contents, list) or not contents or not isinstance(system, str) or not isinstance(tools, list):
            raise ValueError('Expected text conversation, system string and function tools')
        for content in contents:
            if not isinstance(content, dict) or set(content) - {'role', 'parts'} or content.get('role', 'user') not in ('user', 'model'):
                raise ValueError('Unsupported conversation content')
            if not isinstance(content.get('parts'), list) or not content['parts']:
                raise ValueError('Conversation parts are required')
            for part in content['parts']:
                if not isinstance(part, dict) or not part or set(part) - {'text', 'functionCall', 'functionResponse', 'thoughtSignature', 'thought'}:
                    raise ValueError('Only text and function conversation parts are allowed')
                if not any(k in part for k in ('text', 'functionCall', 'functionResponse')):
                    raise ValueError('Conversation part needs text or a function operation')
                if 'text' in part and not isinstance(part['text'], str):
                    raise ValueError('Text must be a string')
                for name in ('functionCall', 'functionResponse'):
                    if name in part and (not isinstance(part[name], dict) or set(part[name]) - {'id', 'name', 'args' if name == 'functionCall' else 'response'}):
                        raise ValueError('Unsupported function content')
        for tool in tools:
            if not isinstance(tool, dict) or set(tool) != {'functionDeclarations'} or not isinstance(tool['functionDeclarations'], list):
                raise ValueError('Only function declarations are allowed; no paid built-in tools')
        payload = {
            'contents': contents,
            'systemInstruction': {'parts': [{'text': system}]},
            'generationConfig': {'candidateCount': 1, 'maxOutputTokens': self.max_output_tokens,
                                 'responseModalities': ['TEXT'], 'thinkingConfig': {'thinkingLevel': self.thinking_level}},
        }
        if tools:
            payload['tools'] = tools
        # Freeze nested input before counting and hashing; mutation cannot swap prompts.
        payload = json.loads(json.dumps(payload, allow_nan=False))
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        try:
            count = self.transport('countTokens', {'generateContentRequest': {'model': f'models/{self.model}', **payload}})
            input_tokens = count.get('totalTokens')
            if not _integer(input_tokens) or input_tokens > INPUT_CEILING:
                raise ValueError('Invalid input count')
        except PaidGatewayError as exc:
            raise PaidGatewayError('Token preflight failed; generation was not dispatched',
                                   http_status=exc.http_status, provider_status=exc.provider_status, provider_reason=exc.provider_reason) from None
        except Exception:
            raise PaidGatewayError('Token preflight failed; generation was not dispatched') from None
        # CountTokens can differ from billed input, so use model hard limits, not
        # an arbitrary percentage margin. Candidate and thinking ceilings are
        # reserved separately even if the provider combines their output limit.
        maximum = _cost(INPUT_CEILING, THINKING_CEILING + self.max_output_tokens)
        metadata = {'provider': 'google', 'model': self.model, 'harness': 'api-control',
                    'request_sha256': digest, 'preflight_input_tokens': input_tokens,
                    'rate_card': 'google-gemini-3.7-flash-2026-09-08',
                    'input_rate_per_million': str(INPUT_RATE), 'output_rate_per_million': str(OUTPUT_RATE),
                    'input_token_ceiling': INPUT_CEILING, 'thinking_token_ceiling': THINKING_CEILING,
                    'candidate_token_ceiling': self.max_output_tokens}
        self.ledger.reserve(request_id, maximum, scope_id=scope_id, scope_limit_usd=scope_limit_usd, metadata=metadata)
        self.ledger.claim(request_id)
        try:
            response = self.transport('generateContent', payload)
            if not isinstance(response, dict):
                raise ValueError('Invalid response')
        except PaidGatewayError as exc:
            raise PaidGatewayError('Generation outcome unknown; reservation retained and retry disabled',
                                   http_status=exc.http_status, provider_status=exc.provider_status, provider_reason=exc.provider_reason) from None
        except Exception:
            raise PaidGatewayError('Generation outcome unknown; reservation retained and retry disabled') from None
        usage = response.get('usageMetadata')
        actual = None
        if isinstance(usage, dict):
            prompt = usage.get('promptTokenCount')
            candidates = usage.get('candidatesTokenCount')
            total = usage.get('totalTokenCount')
            # Missing thoughts is inferable only when all other totals reconcile.
            thoughts = usage.get('thoughtsTokenCount', total - prompt - candidates if all(_integer(v) for v in (total, prompt, candidates)) else None)
            if all(_integer(v) for v in (prompt, candidates, thoughts, total)) and total == prompt + candidates + thoughts and usage.get('toolUsePromptTokenCount', 0) == 0:
                actual = _cost(prompt, candidates + thoughts)
        self.ledger.settle(request_id, actual)
        return {**response, '_billing': {**metadata, 'reservation_id': request_id,
                'maximum_usd': str(maximum), 'actual_usd': None if actual is None else str(actual),
                'status': 'unknown_hold' if actual is None else 'estimated_from_usage',
                'invoice_verified': False, 'usage_receipt': usage}}
