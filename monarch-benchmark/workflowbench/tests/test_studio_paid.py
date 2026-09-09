from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from wb_orchestrator.budget import BudgetLedger, BudgetExceeded, ReservationConflict
from wb_studio.paid import PaidGateway, PaidGatewayError, credential_status

CONTENTS = [{'role': 'user', 'parts': [{'text': 'Do the work'}]}]
USAGE = {'promptTokenCount': 100, 'candidatesTokenCount': 20, 'thoughtsTokenCount': 30, 'totalTokenCount': 150}

class Fake:
    def __init__(self, ledger, response=None, fail=False):
        self.ledger, self.calls, self.fail = ledger, [], fail
        self.response = {'usageMetadata': USAGE} if response is None else response
    def __call__(self, operation, payload):
        self.calls.append((operation, payload))
        if operation == 'countTokens':
            return {'totalTokens': 100}
        assert self.ledger.status().held_usd > 0
        if self.fail:
            raise TimeoutError('key=secret must not escape')
        return self.response

@pytest.fixture
def setup(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    fake = Fake(ledger)
    return ledger, fake, PaidGateway(ledger, transport=fake)

def run(gateway, **kw):
    return gateway.request(CONTENTS, 'Be useful', [{'functionDeclarations': [{'name': 'lookup'}]}], scope_id='run1', scope_limit_usd=Decimal('5'), request_id=kw.get('request_id', 'r1'))

def test_reserves_before_dispatch_counts_complete_request_and_thoughts(setup):
    ledger, fake, gateway = setup
    result = run(gateway)
    assert [c[0] for c in fake.calls] == ['countTokens', 'generateContent']
    counted = fake.calls[0][1]['generateContentRequest']
    assert counted['contents'] == CONTENTS
    assert counted['systemInstruction']['parts'][0]['text'] == 'Be useful'
    assert counted['tools'][0]['functionDeclarations'][0]['name'] == 'lookup'
    assert counted['generationConfig']['maxOutputTokens'] == 4096
    assert result['_billing']['actual_usd'] == '0.000263'
    assert result['_billing']['status'] == 'estimated_from_usage'
    assert ledger.status().actual_usd == Decimal('0.000263')
    assert ledger.status().held_usd == 0

def test_overbudget_never_generates(tmp_path):
    ledger = BudgetLedger(tmp_path / 'b.sqlite', weekly_limit_usd='0.01')
    fake = Fake(ledger)
    with pytest.raises(BudgetExceeded):
        run(PaidGateway(ledger, transport=fake))
    assert [c[0] for c in fake.calls] == ['countTokens']

@pytest.mark.parametrize('usage', [{}, {'usageMetadata': {'promptTokenCount':100}}, {'usageMetadata': {**USAGE, 'totalTokenCount': 140}}, {'usageMetadata': {**USAGE, 'thoughtsTokenCount': -1}}])
def test_unknown_usage_retains_maximum(setup, usage):
    ledger, fake, gateway = setup
    fake.response = usage
    result = run(gateway)
    assert result['_billing']['actual_usd'] is None
    assert result['_billing']['status'] == 'unknown_hold'
    assert ledger.status().held_usd == Decimal(result['_billing']['maximum_usd'])

def test_transport_failure_no_retry_secret_leak_or_release(setup):
    ledger, fake, gateway = setup
    fake.fail = True
    with pytest.raises(PaidGatewayError) as error:
        run(gateway)
    assert 'secret' not in str(error.value)
    assert len(fake.calls) == 2
    assert ledger.status().held_usd > 0

def test_concurrent_replay_has_one_paid_dispatch(setup):
    ledger, fake, gateway = setup
    def attempt(_):
        try:
            return run(gateway)
        except ReservationConflict:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert sum(r is not None for r in results) == 1
    assert sum(c[0] == 'generateContent' for c in fake.calls) == 1

@pytest.mark.parametrize('part', [{'inlineData': {}}, {'fileData': {}}, {'videoMetadata': {}}])
def test_rejects_multimodal_before_transport(setup, part):
    _, fake, gateway = setup
    with pytest.raises(ValueError):
        gateway.request([{'parts':[part]}], '', [], scope_id='r', scope_limit_usd=Decimal('5'), request_id='x')
    assert fake.calls == []

def test_rejects_paid_builtin_tools(setup):
    _, fake, gateway = setup
    with pytest.raises(ValueError):
        gateway.request(CONTENTS, '', [{'googleSearch':{}}], scope_id='r', scope_limit_usd=Decimal('5'), request_id='x')
    assert fake.calls == []

def test_credentials_never_expose_values(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'private-secret')
    assert credential_status() == {'provider': 'google', 'configured': True, 'source': 'GEMINI_API_KEY'}

def test_inferred_thinking_is_counted_from_total(setup):
    _, fake, gateway = setup
    fake.response = {'usageMetadata': {k:v for k,v in USAGE.items() if k != 'thoughtsTokenCount'}}
    assert run(gateway)['_billing']['actual_usd'] == '0.000263'

def test_scope_budget_blocks_generation(setup):
    _, fake, gateway = setup
    with pytest.raises(BudgetExceeded):
        gateway.request(CONTENTS, '', [], scope_id='tiny', scope_limit_usd=Decimal('0.10'), request_id='x')
    assert [c[0] for c in fake.calls] == ['countTokens']

def test_invalid_preflight_never_reserves_or_dispatches(setup):
    ledger, fake, gateway = setup
    gateway.transport = lambda op, payload: {'totalTokens': True}
    with pytest.raises(PaidGatewayError, match='preflight'):
        run(gateway)
    assert ledger.status().committed_usd == 0

def test_expired_rate_card_fails_before_transport(setup, monkeypatch):
    from datetime import datetime, timezone
    import wb_studio.paid as paid
    _, fake, gateway = setup
    monkeypatch.setattr(paid, 'RATE_EXPIRES', datetime(2020, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(PaidGatewayError, match='pricing expired'):
        run(gateway)
    assert fake.calls == []

@pytest.mark.parametrize('kwargs', [{'model':'gemini-unknown'}, {'max_output_tokens': True}, {'max_output_tokens':0}, {'max_output_tokens':65537}])
def test_invalid_model_or_output_limit_rejected(setup, kwargs):
    ledger, fake, _ = setup
    with pytest.raises(ValueError):
        PaidGateway(ledger, transport=fake, **kwargs)
    assert fake.calls == []

def test_receipt_over_reservation_blocks_future_spend(setup):
    ledger, fake, gateway = setup
    fake.response = {'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 1_000_000, 'thoughtsTokenCount': 0, 'totalTokenCount': 1_000_100}}
    result = run(gateway)
    assert Decimal(result['_billing']['actual_usd']) > Decimal(result['_billing']['maximum_usd'])
    assert ledger.status().blocked
    with pytest.raises(BudgetExceeded):
        run(gateway, request_id='next')
    assert sum(c[0] == 'generateContent' for c in fake.calls) == 1

def test_http_error_exposes_only_numeric_and_allowlisted_status(setup, monkeypatch):
    import io
    from urllib.error import HTTPError
    import wb_studio.paid as paid
    _, _, gateway = setup
    monkeypatch.setenv('GOOGLE_API_KEY', 'credential-secret')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    class Opener:
        def open(self, *args, **kwargs):
            raise HTTPError('https://secret-url?key=credential-secret', 403, 'secret-message', {}, io.BytesIO(b'{"error":{"status":"PERMISSION_DENIED","message":"credential-secret","details":[{"reason":"API_KEY_INVALID","metadata":{"key":"credential-secret"}}]}}'))
    monkeypatch.setattr(paid, 'build_opener', lambda *args: Opener())
    gateway.transport = gateway._post
    with pytest.raises(PaidGatewayError) as caught:
        run(gateway)
    assert caught.value.http_status == 403
    assert caught.value.provider_status == 'PERMISSION_DENIED'
    assert caught.value.provider_reason == 'API_KEY_INVALID'
    assert '[API_KEY_INVALID]' in str(caught.value)
    assert 'HTTP 403 / PERMISSION_DENIED' in str(caught.value)
    assert 'credential-secret' not in str(caught.value)
    assert 'secret-url' not in str(caught.value)
    assert 'secret-message' not in str(caught.value)
    assert gateway.ledger.status().committed_usd == 0

@pytest.mark.parametrize('body', [b'{"error":{"status":"private-secret","message":"private-secret","details":[{"reason":"private-secret"}]}}', b'not-json-private-secret'])
def test_http_error_discards_unrecognized_provider_status(setup, monkeypatch, body):
    import io
    from urllib.error import HTTPError
    import wb_studio.paid as paid
    _, _, gateway = setup
    monkeypatch.setenv('GOOGLE_API_KEY', 'credential-secret')
    class Opener:
        def open(self, *args, **kwargs):
            raise HTTPError('private-secret', 400, 'private-secret', {}, io.BytesIO(body))
    monkeypatch.setattr(paid, 'build_opener', lambda *args: Opener())
    with pytest.raises(PaidGatewayError) as caught:
        gateway._post('countTokens', {})
    assert caught.value.http_status == 400
    assert caught.value.provider_status is None
    assert caught.value.provider_reason is None
    assert 'private-secret' not in str(caught.value)
