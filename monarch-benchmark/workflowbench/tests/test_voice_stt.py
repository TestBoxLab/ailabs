"""Transcription on the lab's own terms, and reserved before it is sent.

Feature 024, stage S6. The point is not that transcription becomes possible — S3 already
does it on the device where the browser allows. The point is *whose terms* apply when it
cannot. A clip goes to the Studio's own origin, the Studio calls the provider with the
key it already holds under terms that do not train on submitted audio, and the call is
reserved and settled in the weekly ledger like every other provider call.

An unmetered path to a paid API is how a weekly ceiling stops being one, so the ledger
assertions here matter more than the transcription does.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from wb_orchestrator.budget import BudgetLedger
from wb_studio import voice_stt


class Studio:
    def __init__(self, tmp_path):
        self.directory = tmp_path
        self.ledger = BudgetLedger(tmp_path / 'budget.sqlite3')


@pytest.fixture
def studio(tmp_path):
    return Studio(tmp_path)


def transport(text='the recorded words'):
    seen = {}
    def send(url, body, content_type, key):
        seen['url'], seen['body'], seen['type'], seen['key'] = url, body, content_type, key
        return text
    send.seen = seen
    return send


ENV = {'OPENAI_API_KEY': 'sk-test'}


# --- what it refuses, before anything is reserved --------------------------------------

def test_no_key_means_there_is_nowhere_private_to_send_it(studio):
    with pytest.raises(voice_stt.Refused, match='private'):
        voice_stt.transcribe(studio, b'x', 'audio/webm', 3, env={}, transport=transport())
    assert studio.ledger.reservations() == []


def test_an_oversized_clip_is_refused_before_any_reservation(studio):
    big = b'0' * (voice_stt.MAX_BYTES + 1)
    with pytest.raises(voice_stt.Refused, match='limit'):
        voice_stt.transcribe(studio, big, 'audio/webm', 3, env=ENV, transport=transport())
    assert studio.ledger.reservations() == []


def test_a_clip_longer_than_the_cap_is_refused(studio):
    with pytest.raises(voice_stt.Refused, match='seconds'):
        voice_stt.transcribe(studio, b'x', 'audio/webm', voice_stt.MAX_SECONDS + 1,
                             env=ENV, transport=transport())
    assert studio.ledger.reservations() == []


@pytest.mark.parametrize('kind', ['video/mp4', 'text/plain', 'application/json', ''])
def test_only_audio_is_accepted(studio, kind):
    with pytest.raises(voice_stt.Refused, match='audio type'):
        voice_stt.transcribe(studio, b'x', kind, 3, env=ENV, transport=transport())
    assert studio.ledger.reservations() == []


def test_an_empty_body_is_refused(studio):
    with pytest.raises(voice_stt.Refused, match='No audio'):
        voice_stt.transcribe(studio, b'', 'audio/webm', 1, env=ENV, transport=transport())


# --- the money ------------------------------------------------------------------------

def test_the_call_is_reserved_before_it_is_sent_and_settled_after(studio):
    send = transport()
    out = voice_stt.transcribe(studio, b'audio-bytes', 'audio/webm', 30, env=ENV, transport=send)
    rows = studio.ledger.reservations()
    assert len(rows) == 1
    row = rows[0]
    assert row.maximum_usd == voice_stt.CEILING_USD
    assert row.actual_usd is not None and row.actual_usd <= voice_stt.CEILING_USD
    assert out['text'] == 'the recorded words'


def test_the_settled_cost_follows_the_length_of_the_clip(studio):
    voice_stt.transcribe(studio, b'a', 'audio/webm', 60, env=ENV, transport=transport())
    row = studio.ledger.reservations()[0]
    assert row.actual_usd == pytest.approx(Decimal('0.003'), abs=Decimal('0.0005'))


def test_a_refusal_from_the_service_owes_nothing(studio):
    def boom(url, body, content_type, key):
        raise voice_stt.Refused('the service refused it')
    with pytest.raises(voice_stt.Refused):
        voice_stt.transcribe(studio, b'a', 'audio/webm', 10, env=ENV, transport=boom)
    row = studio.ledger.reservations()[0]
    assert row.actual_usd == 0


def test_a_call_that_never_answered_keeps_its_hold(studio):
    """Unknown billing is not zero billing: the reservation stands."""
    def hang(url, body, content_type, key):
        raise TimeoutError('no answer')
    with pytest.raises(TimeoutError):
        voice_stt.transcribe(studio, b'a', 'audio/webm', 10, env=ENV, transport=hang)
    row = studio.ledger.reservations()[0]
    assert row.actual_usd is None


def test_an_exhausted_research_allowance_refuses_the_call(studio, monkeypatch):
    from wb_studio import allowances
    monkeypatch.setattr(allowances, 'allows', lambda s, kind, amount, lines=None: (False, 'nothing left this week'))
    with pytest.raises(voice_stt.Refused, match='nothing left'):
        voice_stt.transcribe(studio, b'a', 'audio/webm', 10, env=ENV, transport=transport())
    assert studio.ledger.reservations() == []


# --- what actually goes over the wire --------------------------------------------------

def test_the_key_is_sent_by_the_server_and_never_by_the_page(studio):
    send = transport()
    voice_stt.transcribe(studio, b'a', 'audio/webm', 5, env=ENV, transport=send)
    assert send.seen['key'] == 'sk-test'
    assert send.seen['url'].startswith('https://api.openai.com/')


def test_the_clip_is_posted_as_multipart_with_the_model_named(studio):
    send = transport()
    voice_stt.transcribe(studio, b'clip-bytes', 'audio/webm', 5, env=ENV, transport=send)
    assert send.seen['type'].startswith('multipart/form-data; boundary=')
    assert b'clip-bytes' in send.seen['body']
    assert voice_stt.MODEL.encode() in send.seen['body']
