import pytest
from wb_studio.runtime import Runtime
from wb_studio.gateways import GatewayError


def test_token_capacity_is_shared_and_not_refunded_at_request_end():
    runtime=Runtime(provider_limits={'one':{'tokens_per_minute':100}})
    with runtime.provider('one',tokens=70): pass
    with pytest.raises(GatewayError,match='timed out'):
        with runtime.provider('one',tokens=31,timeout=.001): pytest.fail('Overlapping token window admitted')
    with runtime.provider('one',tokens=30): pass
    assert runtime.snapshot()['providers'][0]['tokens_per_minute']==100


def test_token_window_expires_after_sixty_seconds(monkeypatch):
    clock=[100.0]
    monkeypatch.setattr('wb_studio.runtime.time.monotonic',lambda:clock[0])
    runtime=Runtime(provider_limits={'one':{'tokens_per_minute':100}})
    with runtime.provider('one',tokens=100): pass
    clock[0]=160.0
    with runtime.provider('one',tokens=100): pass
    assert list(runtime.providers['one']['token_starts'])==[(160.0,100)]


def test_oversized_request_is_refused_before_capacity_is_consumed():
    runtime=Runtime(provider_limits={'one':{'tokens_per_minute':100}})
    with pytest.raises(GatewayError,match='exceeds'):
        with runtime.provider('one',tokens=101): pytest.fail('Oversized request admitted')
    with runtime.provider('one',tokens=100): pass


@pytest.mark.parametrize('value',[0,-1,1.5,True])
def test_invalid_token_configuration_is_refused(value):
    with pytest.raises(ValueError):Runtime(provider_limits={'one':{'tokens_per_minute':value}})
