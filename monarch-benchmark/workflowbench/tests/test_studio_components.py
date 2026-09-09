"""Versioned component selection and executable isolation contracts."""
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from wb_studio.components import Components, episode_executor, grade, run_loop


def custom_implementation(value):
    return {'custom_result': value.upper()}


@pytest.fixture
def components():
    return Components()


def test_defaults_pin_and_resolve_all_component_roles(components):
    expected = {'brain': 'agent-loop-v1', 'action_builder': 'episode-tools-v1', 'judge': 'state-checks-v1'}
    expected_implementations = {'brain': run_loop, 'action_builder': episode_executor, 'judge': grade}
    pins = components.pin()
    assert set(pins) == set(expected)
    assert components.pin({}) == pins
    for role, identity in expected.items():
        implementation = components.resolve(pins, role)
        assert implementation is expected_implementations[role]
        assert pins[role] == {'id': identity, 'sha256': hashlib.sha256(Path(inspect.getsourcefile(implementation)).read_bytes()).hexdigest()}
    assert components.catalog()['defaults'] == expected


@pytest.mark.parametrize('selection', [
    [], 'agent-loop-v1', 7, True,
    {'unknown_role': 'agent-loop-v1'},
    {'brain': 'not-installed'}, {'action_builder': 'not-installed'}, {'judge': 'not-installed'},
    {'brain': 'state-checks-v1'}, {'action_builder': 'agent-loop-v1'}, {'judge': 'episode-tools-v1'},
    {'brain': None}, {'brain': []}, {'action_builder': {}}, {'judge': 7},
])
def test_unknown_wrong_role_or_malformed_selection_is_rejected(components, selection):
    original = components.pin()
    with pytest.raises(ValueError):
        components.pin(selection)
    assert components.pin() == original


@pytest.mark.parametrize('identity', ['', None, 4, 'agent-loop-v1', 'episode-tools-v1', 'state-checks-v1'])
def test_component_identities_are_unique_nonempty_and_cannot_be_overwritten(components, identity):
    original = components.catalog()
    pins = components.pin()
    with pytest.raises(ValueError, match='unique and nonempty'):
        components.register('brain', identity, 'Replacement', custom_implementation, default=True)
    assert components.catalog() == original
    assert components.pin() == pins
    assert components.resolve(pins, 'brain') is not custom_implementation


@pytest.mark.parametrize('role', ['brain', 'action_builder', 'judge'])
def test_custom_component_can_be_selected_and_resolved_without_changing_other_roles(components, role):
    defaults = components.pin()
    components.register(role, 'custom-v2', 'Custom implementation v2', custom_implementation)
    pins = components.pin({role: 'custom-v2'})
    assert pins[role] == {'id': 'custom-v2', 'sha256': hashlib.sha256(Path(inspect.getsourcefile(custom_implementation)).read_bytes()).hexdigest()}
    assert {key: pin for key, pin in pins.items() if key != role} == {key: pin for key, pin in defaults.items() if key != role}
    assert components.pin() == defaults
    selected = components.resolve(pins, role)
    assert selected is custom_implementation
    assert selected('task') == {'custom_result': 'TASK'}


def test_changing_default_does_not_change_existing_run_pins(components):
    original = components.pin()
    old_brain = components.resolve(original, 'brain')
    components.register('brain', 'custom-v2', 'Custom implementation v2', custom_implementation, default=True)
    assert components.pin()['brain']['id'] == 'custom-v2'
    assert components.resolve(components.pin(), 'brain') is custom_implementation
    assert components.resolve(original, 'brain') is old_brain
    assert original['brain']['id'] == 'agent-loop-v1'


@pytest.mark.parametrize('role', ['brain', 'action_builder', 'judge'])
@pytest.mark.parametrize('digest', ['0' * 64, None, '', 'missing'])
def test_resolution_rejects_changed_or_empty_sha(components, role, digest):
    pins = components.pin()
    pins[role]['sha256'] = digest
    with pytest.raises(ValueError, match='unavailable or changed'):
        components.resolve(pins, role)


@pytest.mark.parametrize('role', ['brain', 'action_builder', 'judge'])
def test_resolution_rejects_missing_sha(components, role):
    pins = components.pin()
    del pins[role]['sha256']
    with pytest.raises((KeyError, ValueError)):
        components.resolve(pins, role)


@pytest.mark.parametrize('role', ['brain', 'action_builder', 'judge'])
def test_resolution_rejects_a_component_missing_from_the_installed_registry(components, role):
    components.register(role, 'custom-v2', 'Custom implementation v2', custom_implementation)
    pins = components.pin({role: 'custom-v2'})
    restarted_without_extension = Components()
    with pytest.raises(ValueError, match='unavailable or changed'):
        restarted_without_extension.resolve(pins, role)


def test_resolution_rejects_a_valid_pin_used_for_the_wrong_role(components):
    pins = components.pin()
    pins['brain'] = dict(pins['judge'])
    with pytest.raises(ValueError, match='Pinned brain implementation'):
        components.resolve(pins, 'brain')


def test_catalog_exposes_only_serializable_metadata_and_cannot_mutate_the_registry(components):
    components.register('brain', 'custom-v2', 'Custom implementation v2', custom_implementation)
    catalog = components.catalog()
    original = deepcopy(catalog)
    assert json.loads(json.dumps(catalog)) == original
    assert set(catalog) == {'defaults', 'items'}
    assert len(catalog['items']) == 4
    assert all(set(item) == {'id', 'role', 'name', 'sha256'} for item in catalog['items'])
    assert next(item for item in catalog['items'] if item['id'] == 'custom-v2') == {
        'id': 'custom-v2', 'role': 'brain', 'name': 'Custom implementation v2',
        'sha256': hashlib.sha256(Path(inspect.getsourcefile(custom_implementation)).read_bytes()).hexdigest(),
    }
    catalog['defaults']['brain'] = 'custom-v2'
    catalog['items'][0]['sha256'] = '0' * 64
    catalog['items'].clear()
    assert components.catalog() == original
    assert components.pin()['brain']['id'] == 'agent-loop-v1'
    assert components.resolve(components.pin({'brain': 'custom-v2'}), 'brain') is custom_implementation
