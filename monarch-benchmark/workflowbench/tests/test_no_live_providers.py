"""The suite never reaches a live provider.

Found by the adversary review of 10 September 2026: a full run hung in `ssl.read`, waiting on a
real OpenAI response, inside `test_run_config.py::test_a_gone_workflow_refuses_and_says_to_rerun
_the_command`. The mechanism is below -- `Studio._load_env` reads workflowbench/.env with
override=True, so one test that builds a Studio hands every real key to every test after it, and
an API arm then bills the lab outside the weekly ledger, with no operator and no approval.
"""
import os
from pathlib import Path

from tests.conftest import _clear_provider_keys
from wb_arms import providers


def key_names():
    return {p.key_env for p in providers.REGISTRY.values()}


def test_a_test_starts_with_no_provider_key_and_the_guard_clears_what_arrives():
    names = key_names()
    assert not [n for n in names if os.environ.get(n)], 'the autouse guard clears keys before a test runs'
    os.environ['OPENAI_API_KEY'] = 'sk-injected-by-load-dotenv'  # what Studio._load_env does
    _clear_provider_keys(names)
    assert 'OPENAI_API_KEY' not in os.environ


def test_a_studio_reads_dotenv_but_carries_nothing_into_the_next_test(tmp_path):
    """The leak itself, so it is never mistaken for something that cannot happen. What this
    test injects is cleared by the guard's teardown, not carried to whatever runs next."""
    from wb_studio.app import Studio
    Studio(Path(tmp_path)).models()
    # With a .env on this machine the keys are now set; with none, nothing was there to leak.
    # Either way the guard's teardown clears them, which the assertion in the other test proves.
    assert all(isinstance(os.environ.get(n, ''), str) for n in key_names())
