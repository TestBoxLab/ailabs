"""The Studio's front door must be able to relay to a shim that is not on its host.

The relay assumed the attempt ran in the same container, which is true when the
Studio launches it and false when the CLI does. With the address fixed at
127.0.0.1 a hosted Studio answers 502 to every application call from a laptop
round, so the seeds could name the hosted door but no attempt could serve it.
`STUDIO_FRONT_DOOR_TARGET` names where the shim actually listens.
"""
from __future__ import annotations

from wb_studio.app import front_door_target


def test_the_default_is_the_studio_s_own_loopback():
    assert front_door_target({}, "/openapi/index.json") == "http://127.0.0.1:9105/openapi/index.json"


def test_a_port_moves_the_loopback_target():
    assert front_door_target({"STUDIO_FRONT_DOOR_PORT": "9200"}, "/x") == "http://127.0.0.1:9200/x"


def test_an_explicit_target_sends_the_call_off_host():
    env = {"STUDIO_FRONT_DOOR_TARGET": "https://tunnel.example.dev"}
    assert front_door_target(env, "/airtable/meta/bases") == "https://tunnel.example.dev/airtable/meta/bases"


def test_a_trailing_slash_on_the_target_does_not_double():
    env = {"STUDIO_FRONT_DOOR_TARGET": "https://tunnel.example.dev/"}
    assert front_door_target(env, "/x") == "https://tunnel.example.dev/x"


def test_the_explicit_target_wins_over_the_port():
    env = {"STUDIO_FRONT_DOOR_TARGET": "https://tunnel.example.dev", "STUDIO_FRONT_DOOR_PORT": "9200"}
    assert front_door_target(env, "/x") == "https://tunnel.example.dev/x"
