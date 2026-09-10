"""Offline contracts for shared Studio capacity, cancellation, and admission."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import wb_studio.runtime as runtime_module
from wb_studio.gateways import GatewayError
from wb_studio.runtime import AdmittedGateway, Runtime, single_host_owner


@pytest.fixture(autouse=True)
def isolated_runtime_environment(monkeypatch):
    for name in ('STUDIO_MAX_AGENTS', 'STUDIO_MAX_RUNS', 'STUDIO_PROVIDER_LIMITS'):
        monkeypatch.delenv(name, raising=False)


def test_agent_capacity_is_shared_and_released(monkeypatch):
    runtime = Runtime(max_agents=2)
    cancel = threading.Event()
    blocked = threading.Event()
    acquire = runtime.agents.acquire

    def observe_acquire(**kwargs):
        acquired = acquire(**kwargs)
        if not acquired:
            blocked.set()
        return acquired

    monkeypatch.setattr(runtime.agents, 'acquire', observe_acquire)

    def next_client():
        with runtime.agent(cancel) as admitted:
            return admitted, runtime.snapshot()['active_agents']

    with ThreadPoolExecutor(max_workers=1) as pool:
        with ExitStack() as holders:
            first = holders.enter_context(ExitStack())
            assert first.enter_context(runtime.agent(cancel))
            assert holders.enter_context(runtime.agent(cancel))
            future = pool.submit(next_client)
            assert blocked.wait(3), 'Third client never encountered the shared bound'
            assert not future.done()
            assert runtime.snapshot()['active_agents'] == 2
            first.close()
            assert future.result(timeout=3) == (True, 2)
    assert runtime.snapshot()['active_agents'] == 0
    with runtime.agent(cancel) as admitted:
        assert admitted


def test_cancelled_agent_waiter_does_not_consume_capacity(monkeypatch):
    runtime = Runtime(max_agents=1)
    cancel = threading.Event()
    blocked = threading.Event()
    acquire = runtime.agents.acquire

    def observe_acquire(**kwargs):
        acquired = acquire(**kwargs)
        if not acquired:
            blocked.set()
        return acquired

    monkeypatch.setattr(runtime.agents, 'acquire', observe_acquire)

    def waiting_client():
        with runtime.agent(cancel) as admitted:
            return admitted

    with ThreadPoolExecutor(max_workers=1) as pool:
        with runtime.agent(threading.Event()):
            future = pool.submit(waiting_client)
            try:
                assert blocked.wait(3)
            finally:
                cancel.set()
            assert future.result(timeout=3) is False
            assert runtime.snapshot()['active_agents'] == 1
    assert runtime.snapshot()['active_agents'] == 0


def test_provider_concurrency_is_shared_but_other_providers_can_progress(monkeypatch):
    runtime = Runtime(provider_limits={'alpha': {'concurrency': 2}})
    waiting = threading.Event()
    wait = runtime.condition.wait

    def observe_wait(timeout):
        waiting.set()
        return wait(timeout)

    monkeypatch.setattr(runtime.condition, 'wait', observe_wait)

    def next_client():
        with runtime.provider('alpha', timeout=3):
            return runtime.providers['alpha']['active']

    with ThreadPoolExecutor(max_workers=1) as pool:
        with ExitStack() as holders:
            first = holders.enter_context(ExitStack())
            first.enter_context(runtime.provider('alpha'))
            holders.enter_context(runtime.provider('alpha'))
            future = pool.submit(next_client)
            assert waiting.wait(3)
            assert not future.done()
            with runtime.provider('beta'):
                assert runtime.providers['alpha']['active'] == 2
                assert runtime.providers['beta']['active'] == 1
            first.close()
            assert future.result(timeout=3) == 2
    assert {name: state['active'] for name, state in runtime.providers.items()} == {'alpha': 0, 'beta': 0}


def test_cancelled_provider_waiter_never_dispatches(monkeypatch):
    runtime = Runtime(provider_limits={'alpha': {'concurrency': 1}})
    cancel = threading.Event()
    gateway = Mock()
    admitted = AdmittedGateway(gateway, runtime, 'alpha', lambda scope: cancel)
    waiting = threading.Event()
    wait = runtime.condition.wait

    def observe_wait(timeout):
        waiting.set()
        return wait(timeout)

    monkeypatch.setattr(runtime.condition, 'wait', observe_wait)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with runtime.provider('alpha'):
            future = pool.submit(admitted.turn, [], scope_id='run-b', timeout=3)
            try:
                assert waiting.wait(3)
            finally:
                cancel.set()
            with pytest.raises(GatewayError, match='Cancelled') as error:
                future.result(timeout=3)
            assert error.value.kind == 'infra:cancelled'
            gateway.turn.assert_not_called()
            assert runtime.providers['alpha']['active'] == 1
    assert runtime.providers['alpha']['active'] == 0


@pytest.mark.parametrize('arrival, waits', [(159.999, 1), (160.0, 0), (160.001, 0)])
def test_provider_rpm_expires_at_exact_sixty_second_boundary(monkeypatch, arrival, waits):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(runtime_module, 'time', SimpleNamespace(monotonic=lambda: clock.now))
    runtime = Runtime(provider_limits={'alpha': {'requests_per_minute': 2}})
    with runtime.provider('alpha'):
        pass
    clock.now = 101.0
    with runtime.provider('alpha'):
        pass
    clock.now = arrival
    observed_waits = []

    def advance_to_boundary(timeout):
        observed_waits.append(timeout)
        clock.now = 160.0
        assert len(observed_waits) == 1, 'An expired request still blocks admission'

    monkeypatch.setattr(runtime.condition, 'wait', advance_to_boundary)
    with runtime.provider('alpha', timeout=5) as remaining:
        assert remaining == pytest.approx(5 - max(0, 160 - arrival))
        assert runtime.providers['alpha']['active'] == 1
        assert list(runtime.providers['alpha']['starts']) == [101.0, max(160.0, arrival)]
    assert len(observed_waits) == waits
    assert runtime.providers['alpha']['active'] == 0


def test_provider_timeout_never_dispatches_or_consumes_a_request(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(runtime_module, 'time', SimpleNamespace(monotonic=lambda: clock.now))
    runtime = Runtime(provider_limits={'alpha': {'concurrency': 1}})
    gateway = Mock()
    admitted = AdmittedGateway(gateway, runtime, 'alpha', lambda scope: threading.Event())

    def advance_to_deadline(timeout):
        clock.now = 105.0

    monkeypatch.setattr(runtime.condition, 'wait', advance_to_deadline)
    with runtime.provider('alpha'):
        with pytest.raises(GatewayError, match='no request sent') as error:
            admitted.turn([], scope_id='run-b', timeout=5)
        assert error.value.kind == 'infra:timeout'
        gateway.turn.assert_not_called()
        assert runtime.providers['alpha']['active'] == 1
        assert list(runtime.providers['alpha']['starts']) == [100.0]
    assert runtime.providers['alpha']['active'] == 0


@pytest.mark.parametrize('config', [
    {'max_agents': 0}, {'max_agents': 65}, {'max_agents': True}, {'max_agents': '2'},
    {'max_runs': 0}, {'max_runs': 33}, {'max_runs': 1.5},
    {'provider_limits': []}, {'provider_limits': {'alpha': []}},
    {'provider_limits': {'alpha': {'unknown': 2}}},
    {'provider_limits': {'alpha': {'concurrency': 0}}},
    {'provider_limits': {'alpha': {'concurrency': 65}}},
    {'provider_limits': {'alpha': {'concurrency': False}}},
    {'provider_limits': {'alpha': {'requests_per_minute': 0}}},
    {'provider_limits': {'alpha': {'requests_per_minute': 100001}}},
    {'provider_limits': {'alpha': {'requests_per_minute': '30'}}},
])
def test_invalid_runtime_config_is_rejected(config):
    with pytest.raises(ValueError):
        Runtime(**config)


@pytest.mark.parametrize('agents, runs, concurrency, rpm', [(1, 1, 1, 1), (64, 32, 64, 100000)])
def test_runtime_config_accepts_capacity_boundaries(agents, runs, concurrency, rpm):
    runtime = Runtime(max_agents=agents, max_runs=runs,
                      provider_limits={'alpha': {'concurrency': concurrency, 'requests_per_minute': rpm}})
    snapshot = runtime.snapshot()
    assert (snapshot['max_agents'], snapshot['max_runs']) == (agents, runs)
    assert snapshot['providers'] == [{'provider': 'alpha', 'concurrency': concurrency,
                                      'requests_per_minute': rpm, 'tokens_per_minute': None, 'active': 0}]


def test_admitted_gateway_preserves_budget_arguments_and_reduces_timeout(monkeypatch):
    ticks = iter([100.0, 100.0, 102.5])
    monkeypatch.setattr(runtime_module, 'time', SimpleNamespace(monotonic=lambda: next(ticks)))
    runtime = Runtime()
    cancel = threading.Event()
    cancel_for = Mock(return_value=cancel)
    gateway = Mock()
    gateway.turn.return_value = {'text': 'answer', '_billing': {'request_id': 'request-7'}}
    admitted = AdmittedGateway(gateway, runtime, 'alpha', cancel_for)
    messages = [{'role': 'user', 'content': 'Classify this task'}]
    result = admitted.turn(messages, scope_id='run-3', scope_limit_usd=Decimal('2.75'),
                           request_id='request-7', timeout=10)
    cancel_for.assert_called_once_with('run-3')
    gateway.turn.assert_called_once_with(messages, scope_id='run-3', scope_limit_usd=Decimal('2.75'),
                                         request_id='request-7', timeout=7.5)
    assert result == {'text': 'answer', '_billing': {'request_id': 'request-7'}}
    assert runtime.providers['alpha']['active'] == 0


def test_admitted_gateway_releases_capacity_after_gateway_exception():
    runtime = Runtime(provider_limits={'alpha': {'concurrency': 1}})
    gateway = Mock()
    gateway.turn.side_effect = [ValueError('provider failed'), {'text': 'recovered'}]
    admitted = AdmittedGateway(gateway, runtime, 'alpha', lambda scope: threading.Event())
    kwargs = {'scope_id': 'run-3', 'scope_limit_usd': Decimal('2.75'), 'request_id': 'request-7'}
    with pytest.raises(ValueError, match='provider failed'):
        admitted.turn([], **kwargs)
    assert runtime.providers['alpha']['active'] == 0
    assert admitted.turn([], **{**kwargs, 'request_id': 'request-8'}, timeout=1) == {'text': 'recovered'}
    assert gateway.turn.call_count == 2
    assert runtime.providers['alpha']['active'] == 0
    assert len(runtime.providers['alpha']['starts']) == 2
    assert 'timeout' not in gateway.turn.call_args_list[0].kwargs


def test_single_host_owner_excludes_other_process_and_releases_lock(tmp_path):
    script = """
import sys
from pathlib import Path
from wb_studio.runtime import single_host_owner
try:
    with single_host_owner(Path(sys.argv[1])):
        print('acquired')
except RuntimeError as error:
    print(str(error))
    sys.exit(23)
"""
    command = [sys.executable, '-c', script, str(tmp_path / 'studio')]
    with single_host_owner(tmp_path / 'studio'):
        contender = subprocess.run(command, text=True, capture_output=True, timeout=10)
        assert contender.returncode == 23, contender.stderr
        assert contender.stdout.strip() == 'Another Studio process owns this data directory'
    successor = subprocess.run(command, text=True, capture_output=True, timeout=10)
    assert successor.returncode == 0, successor.stderr
    assert successor.stdout.strip() == 'acquired'
