"""Offline acceptance checks for the requested Genesis default and identity upgrade."""
import json
from pathlib import Path
import pytest
from wb_studio.genesis_config import Config
from wb_studio import memory
from wb_orchestrator.config import load_model

ROUTES = [{'id': 'gpt-6-astra', 'available': True}, {'id': 'other', 'available': True}]

@pytest.mark.parametrize('step', ['chat', 'reading'])
def test_default_partner_uses_astra_medium(tmp_path, step):
    config = Config(tmp_path)
    assert config.route_for(step, ROUTES)['id'] == 'gpt-6-astra'
    assert config.effort_for(step) == 'medium'

@pytest.mark.parametrize('step', ['chat', 'reading'])
def test_missing_astra_does_not_silently_substitute(tmp_path, step):
    assert Config(tmp_path).route_for(step, ROUTES[1:]) is None

def test_explicit_specialist_settings_survive(tmp_path):
    config = Config(tmp_path)
    config.set({'models': {'reading': 'other'}, 'effort': {'reading': 'low'}}, ROUTES)
    assert Config(tmp_path).route_for('reading', ROUTES)['id'] == 'other'
    assert Config(tmp_path).effort_for('reading') == 'low'
    assert Config(tmp_path).effort_for('chat') == 'medium'

def test_legacy_shipped_soul_migrates_once_with_history(tmp_path):
    legacy = memory.SOUL_LEGACY_DEFAULT
    (tmp_path / 'SOUL.md').write_bytes(legacy.encode('utf8'))
    store = memory.Memory(tmp_path)
    assert store.read()['soul'] == memory.SOUL_DEFAULT
    row, = store.history_tail()
    assert row['before'] == legacy
    assert row['after'] == memory.SOUL_DEFAULT
    assert row['op'] == 'soul-default-upgrade'
    memory.Memory(tmp_path)
    assert len(store.history_tail()) == 1

@pytest.mark.parametrize('suffix', ['\n', '\nHuman custom guidance.\n'])
def test_nonexact_soul_is_preserved(tmp_path, suffix):
    custom = memory.SOUL_LEGACY_DEFAULT + suffix
    (tmp_path / 'SOUL.md').write_bytes(custom.encode('utf8'))
    store = memory.Memory(tmp_path)
    assert store.read()['soul'] == custom
    assert store.history_tail() == []

def test_new_identity_is_valid_and_within_budget(tmp_path):
    store = memory.Memory(tmp_path)
    assert store.read()['soul'] == memory.SOUL_DEFAULT
    assert len(memory.SOUL_DEFAULT) <= memory.SOUL_BUDGET
    assert memory.scan(memory.SOUL_DEFAULT) is None

def test_astra_model_uses_responses_and_verified_standard_prices():
    model = load_model(Path(__file__).parents[1] / 'config/models/gpt-6-astra.yaml')
    assert (model.model, model.effort, model.adapter) == ('gpt-6-astra', 'medium', 'openai_responses')
    assert (model.usd_per_million.input, model.usd_per_million.cached,
            model.usd_per_million.cache_write, model.usd_per_million.output) == (10, 1, 12.5, 50)
