"""Verify must not pass while the harness and the knowledge base name different doors.

On 9 Sep the knowledge base named the hosted front door while the environment
still named the tunnel. `wb monarch verify` reported five green checks -- it never
probes the front door -- and two rounds spent US$ 18.75 on attempts whose engine
called an address with nothing behind it. A green that cannot fail is worse than
no check.
"""
from __future__ import annotations

import pytest

from wb_studio.enterprise import _front_door_agrees


RAILWAY = "https://ailabs-studio-production.up.railway.app/front-door"
NGROK = "https://imputable-tracklessly-kellan.ngrok-free.dev"


def test_the_same_address_agrees():
    _front_door_agrees(RAILWAY, RAILWAY)          # no raise


def test_a_trailing_slash_is_not_a_disagreement():
    _front_door_agrees(RAILWAY + "/", RAILWAY)


def test_a_knowledge_base_naming_another_door_is_refused():
    with pytest.raises(ValueError) as caught:
        _front_door_agrees(NGROK, RAILWAY)
    message = str(caught.value)
    assert "ngrok-free.dev" in message and "railway.app" in message, message


def test_no_knowledge_base_address_is_not_a_disagreement():
    """A product taught nothing about its front door has nothing to contradict."""
    _front_door_agrees(NGROK, None)
