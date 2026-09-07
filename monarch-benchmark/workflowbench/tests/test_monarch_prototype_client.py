import time
from unittest.mock import Mock

import pytest

from wb_arms.api_loop import EpisodeTimeout, InfraError
from wb_arms.monarch_client import MonarchClient, MonarchRefused


def client():
    c = MonarchClient('http://test', 'session')
    c._call = Mock()
    return c


def test_optional_experiment_is_sent_without_changing_default_body():
    c = client()
    c._call.return_value = {'runId': 'r'}
    c.start_authoring('request', 'episode', experiment='sections-parallel')
    assert c._call.call_args.args[2] == {'goal': 'request', 'experiment': 'sections-parallel'}
    c.start_authoring('request', 'episode')
    assert c._call.call_args.args[2] == {'goal': 'request'}


def test_authoring_poll_keeps_raw_failure_evidence():
    c = client()
    raw = {'status': 'error', 'failure': {'code': None, 'message': 'Provider mystery'}}
    c._call.return_value = raw
    assert c.get_authoring('r') is raw
    assert c._call.call_args.args[:2] == ('GET', '/api/workflows/recipe/runs/r')


def test_export_waits_for_durable_terminal_and_retains_every_raw_page():
    c = client()
    pages = [
        {'runId': 'r', 'events': [{'seq': 1, 'data': {'truncated': True}}], 'nextAfterSeq': 1, 'hasMore': False, 'complete': False},
        {'runId': 'r', 'events': [{'seq': 2}], 'nextAfterSeq': 2, 'hasMore': True, 'complete': False},
        {'runId': 'r', 'events': [{'seq': 3}], 'nextAfterSeq': 3, 'hasMore': False, 'complete': True},
    ]
    c._call.side_effect = pages
    assert list(c.authoring_event_pages('r', deadline=time.monotonic() + 10, poll_interval_s=0)) == pages
    assert 'afterSeq=1' in c._call.call_args_list[1].args[1]


def test_expired_events_are_not_silently_converted_to_empty_history():
    c = client()
    c._call.side_effect = MonarchRefused('RECIPE_RUN_EVENTS_EXPIRED', 410, {'code': 'RECIPE_RUN_EVENTS_EXPIRED'})
    with pytest.raises(MonarchRefused) as exc:
        list(c.authoring_event_pages('r', deadline=time.monotonic() + 10))
    assert exc.value.status == 410


def test_invalid_event_page_cannot_claim_complete_trace():
    c = client()
    c._call.return_value = {'runId': 'r', 'events': [], 'nextAfterSeq': 0, 'hasMore': True, 'complete': True}
    with pytest.raises(InfraError):
        list(c.authoring_event_pages('r', deadline=time.monotonic() + 10))


def test_expired_deadline_makes_no_read():
    c = client()
    with pytest.raises(EpisodeTimeout):
        list(c.authoring_event_pages('r', deadline=time.monotonic() - 1))
    c._call.assert_not_called()


def test_execution_cancel_uses_existing_session_route():
    c = client()
    c.cancel_execution('engine-run')
    assert c._call.call_args.args[:3] == ('POST', '/api/engine/runs/engine-run/cancel', {})


def test_prototype_competitor_polls_and_keeps_raw_events():
    from types import SimpleNamespace
    from wb_arms.monarch import MonarchArm
    from wb_arms.api_loop import ArmResult
    c = client()
    c.start_authoring = Mock(return_value='r')
    frame = {'status': 'done', 'workflowId': 'wf', 'recipeVersion': 1, 'experiment': {'id': 'compiled'}}
    c.authoring_snapshots = Mock(return_value=iter([frame]))
    page = {'runId': 'r', 'events': [], 'nextAfterSeq': 0, 'hasMore': False, 'complete': True}
    c.authoring_event_pages = Mock(return_value=iter([page]))
    h = SimpleNamespace(authoring_mode='interactive', builder_experiment='compiled')
    competitor = MonarchArm(h, 10, None, None, {}, 'prototype')
    result, ids = ArmResult(), {}
    assert competitor._author(c, None, 'request', time.monotonic() + 10, result, ids) == 'wf'
    assert c.start_authoring.call_args.kwargs['experiment'] == 'compiled'
    assert {'frame': frame} in result.turn_log
    assert {'authoring_events': page} in result.turn_log


def test_prototype_competitor_refuses_a_silently_changed_configuration():
    from types import SimpleNamespace
    from wb_arms.monarch import MonarchArm
    from wb_arms.api_loop import ArmResult
    c = client()
    c.start_authoring = Mock(return_value='r')
    c.authoring_snapshots = Mock(return_value=iter([{'status': 'done', 'experiment': {'id': 'current'}}]))
    h = SimpleNamespace(authoring_mode='interactive', builder_experiment='compiled')
    competitor = MonarchArm(h, 10, None, None, {}, 'prototype')
    with pytest.raises(InfraError, match='Persisted builder experiment'):
        competitor._author(c, None, 'request', time.monotonic() + 10, ArmResult(), {})


def test_unknown_authoring_error_is_not_classified_by_provider_words():
    from types import SimpleNamespace
    from wb_arms.monarch import MonarchArm
    from wb_arms.api_loop import ArmResult
    c = client()
    c.start_authoring = Mock(return_value='r')
    frame = {'status': 'error', 'error': 'AWS credential unknown', 'failure': {'code': None}, 'experiment': {'id': 'compiled'}}
    c.authoring_snapshots = Mock(return_value=iter([frame]))
    c.authoring_event_pages = Mock(return_value=iter([]))
    h = SimpleNamespace(authoring_mode='interactive', builder_experiment='compiled')
    competitor = MonarchArm(h, 10, None, None, {}, 'prototype')
    result = ArmResult()
    assert competitor._author(c, None, 'request', time.monotonic() + 10, result, {}) is None
    assert competitor._infra is None
    assert {'frame': frame} in result.turn_log
