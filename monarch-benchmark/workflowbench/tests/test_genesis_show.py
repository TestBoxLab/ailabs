"""Genesis points at what it changed; Lucas decides whether to go there.

Feature 024 voice work, stage S1. WCAG's glossary puts a change of viewport squarely on
the change-of-context list, and 3.2.5 allows one "only by user request, or a mechanism
is available to turn off such changes". A real `<a href="#run/x">` is a user request by
definition — and it also gives middle-click-to-a-new-tab, copy link, the back button,
and an address Carlos can be sent. So the server never navigates anything. It validates
a route, records the act as a tool call like every other lab action, and returns a
receipt the client renders as a link.

The validation is the security half: the route is written by a model, reaches the
client, and is put in an href. Anything that is not a known in-app hash is refused.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_show


def genesis(tmp_path):
    studio = SimpleNamespace(directory=tmp_path, jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=Mock())
    from wb_studio.genesis import Genesis
    return Genesis(studio)


def show(tmp_path, **payload):
    return genesis_show.TOOLS['show'](genesis(tmp_path), payload)


# --- what it accepts -------------------------------------------------------------------

@pytest.mark.parametrize('route', [
    '#run/6022e89f', '#report/6022e89f', '#round/f95c937ddf90', '#budget',
    '#genesis/board', '#runtime', '#studio', '#runs', '#reports',
    '#run/6022e89f/simple.task/setup-a/e12',
])
def test_a_known_in_app_route_is_accepted(tmp_path, route):
    out = show(tmp_path, route=route, label='Open it', why='because')
    assert out['route'] == route and out['label'] == 'Open it'


def test_the_receipt_carries_why_so_the_page_can_say_it(tmp_path):
    out = show(tmp_path, route='#budget', label='Open the budget',
               why='the weekly research allowance is nearly spent')
    assert 'weekly research allowance' in out['why']


def test_a_missing_label_gets_one_from_the_route(tmp_path):
    assert show(tmp_path, route='#budget')['label']


# --- what it refuses -------------------------------------------------------------------

@pytest.mark.parametrize('route', [
    'https://evil.example/steal', '//evil.example', 'javascript:alert(1)',
    'data:text/html,<script>', '#javascript:alert(1)', '/api/state', '../../etc/passwd',
    '#unknown-view', '#run', '', None, 123, '#run/../../admin',
])
def test_anything_that_is_not_a_known_route_is_refused(tmp_path, route):
    with pytest.raises(ValueError):
        show(tmp_path, route=route, label='x')


def test_a_route_with_a_quote_cannot_break_out_of_an_attribute(tmp_path):
    for route in ('#run/a"onmouseover="alert(1)', "#run/a'>", '#run/a<script>'):
        with pytest.raises(ValueError):
            show(tmp_path, route=route)


def test_a_very_long_route_is_refused(tmp_path):
    with pytest.raises(ValueError):
        show(tmp_path, route='#run/' + 'a' * 400)


# --- how it reaches Genesis ------------------------------------------------------------

def test_the_tool_is_registered_through_the_plugin_seam():
    from wb_studio import genesis_plugins
    assert 'wb_studio.genesis_show' in genesis_plugins.MODULES
    assert 'show' in genesis_plugins.actions()


def test_the_model_is_told_what_the_tool_does():
    from wb_studio.genesis_schemas import SCHEMAS
    sentence, params = SCHEMAS['show']
    assert 'route' in params['properties'] and 'route' in params['required']
    assert sentence and sentence[0].isupper()


def test_the_protocol_says_it_does_not_move_the_screen():
    """The model must not believe it is navigating; it is offering a link."""
    assert 'link' in genesis_show.PROTOCOL.lower()
