"""Transcription on the lab's own terms, when the browser will not do it on the device.

Feature 024, stage S6, and it exists only because stage S3 refuses the easy path.
Chrome's `SpeechRecognition` without `processLocally` ships every utterance to Google
under no DPA, no retention statement and no training commitment — and the request is
invisible: CSP cannot see it, no violation event fires, nothing appears in the network
tab. So S3 does on-device or nothing, and this is the fallback for a browser that cannot.

What changes here is *whose* terms. A clip goes to the Studio's own origin — so
`connect-src 'self'` is untouched and there is no API key and no ephemeral token in the
page — and the Studio calls the provider with the key it already holds, under API terms
that do not train on submitted audio. Roughly a third of a cent a minute, reserved and
settled in the weekly ledger exactly like every other provider call, because an
unmetered path to a paid API is how a budget stops being a budget.

Deliberately narrow: one clip, one call, a hard ceiling on bytes and seconds, and the
audio is dropped the moment the text comes back. Nothing is stored.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from decimal import Decimal

# A person speaking a request, not a meeting. The cap is what makes the cost predictable
# enough to reserve a fixed amount before the call.
MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 120
# gpt-4o-mini-transcribe is about US$0.003 a minute. Two minutes at that rate, rounded up,
# is the reservation; the receipt settles it.
CEILING_USD = Decimal("0.01")
MODEL = "gpt-4o-mini-transcribe"
ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
TYPES = {"audio/webm": "clip.webm", "audio/ogg": "clip.ogg", "audio/mp4": "clip.mp4",
         "audio/mpeg": "clip.mp3", "audio/wav": "clip.wav"}


class Refused(ValueError):
    """The request will not be made, and the sentence says why."""


def _key(env) -> str:
    key = (env or {}).get("OPENAI_API_KEY") or ""
    if not key.strip():
        raise Refused("No OPENAI_API_KEY on this host, so there is nowhere private to send the audio. "
                      "Type instead, or use a browser that transcribes on the device.")
    return key.strip()


def _multipart(audio: bytes, filename: str, content_type: str) -> tuple[bytes, str]:
    boundary = "----wb" + uuid.uuid4().hex
    out = []
    for name, value in (("model", MODEL), ("response_format", "text")):
        out.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    out.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
               f"Content-Type: {content_type}\r\n\r\n".encode())
    out.append(audio)
    out.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def check(audio: bytes, content_type: str, seconds) -> str:
    """The filename to send, or a Refused whose sentence a person would want to read."""
    if not audio:
        raise Refused("No audio was sent.")
    if len(audio) > MAX_BYTES:
        raise Refused(f"That clip is {len(audio) // 1024} KB; the limit is {MAX_BYTES // 1024} KB. "
                      "Say it in a shorter stretch.")
    kind = str(content_type or "").split(";")[0].strip().lower()
    if kind not in TYPES:
        raise Refused("That is not an audio type this accepts: " + ", ".join(sorted(TYPES)) + ".")
    try:
        length = float(seconds) if seconds is not None else 0.0
    except (TypeError, ValueError):
        length = 0.0
    if length > MAX_SECONDS:
        raise Refused(f"That clip is {int(length)} seconds; the limit is {MAX_SECONDS}.")
    return TYPES[kind]


def transcribe(studio, audio: bytes, content_type: str, seconds=None, env=None, transport=None, by='human:studio') -> dict:
    """One clip to text, reserved before it is sent and settled from what it cost.

    `transport` is the seam the tests use; nothing else replaces it.
    """
    import os
    env = os.environ if env is None else env
    filename = check(audio, content_type, seconds)
    key = _key(env)

    from wb_studio import allowances
    ok, reason = allowances.allows(studio, "genesis", CEILING_USD)
    if not ok:
        raise Refused(reason)

    request_id = "voice-stt-" + uuid.uuid4().hex
    # Reserved before it is sent, like every other provider call. An unmetered path to a
    # paid API is how a weekly ceiling stops being one.
    studio.ledger.reserve(request_id, str(CEILING_USD), scope_id=request_id,
                          scope_limit_usd=CEILING_USD,
                          metadata={"purpose": "Genesis voice", "model": MODEL, "by": by,
                                    "seconds": float(seconds or 0)})
    studio.ledger.claim(request_id)
    try:
        body, kind = _multipart(audio, filename, content_type.split(";")[0].strip())
        send = transport or _post
        text = send(ENDPOINT, body, kind, key)
    except Refused:
        # Nothing was billed, so nothing is owed.
        studio.ledger.settle(request_id, "0")
        raise
    except Exception:
        # The hold stands: a call that may have reached the provider is not free just
        # because the answer did not come back.
        raise
    finally:
        del audio
    # The receipt is per second of audio; below a cent the settle is the rate, not the hold.
    cost = (Decimal(str(seconds or 0)) / 60 * Decimal("0.003")).quantize(Decimal("0.000001"))
    studio.ledger.settle(request_id, str(max(cost, Decimal("0.000001"))))
    return {"text": (text or "").strip(), "model": MODEL, "cost_usd": str(cost),
            "reserved_usd": str(CEILING_USD)}


def _post(url: str, body: bytes, content_type: str, key: str) -> str:
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": content_type})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise Refused(f"The transcription service refused it ({exc.code}). {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise Refused(f"The transcription service could not be reached: {exc}") from exc
    try:                                    # response_format=text, but be tolerant
        return json.loads(raw).get("text", raw)
    except ValueError:
        return raw
