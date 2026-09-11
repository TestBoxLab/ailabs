# GPT-Live-1 connection, 11 September 2026

Lucas explicitly selected GPT-Live-1. Continue the existing settled design, using
the shared harness procedure; the named Superpowers skills are unavailable on this host.
Preserve the existing live-build work and unrelated working-tree changes.

## Connection slice

- [x] T001 [US2] Reproduce session admission, ownership, delegation replay and unknown billing cases in `tests/test_genesis_voice.py` before implementing `wb_studio/genesis_voice.py`.
- [x] T002 [US2] Implement server-owned GPT-Live-1 WebRTC sessions, authenticated sideband, a lifetime timer, ledger reservations, transcript context and delegation to ordinary Genesis turns; keep usage uncertainty explicit.
- [x] T003 [US2] Add authenticated voice lifecycle routes to `wb_studio/app.py`, preserving person attribution and pause/allowance gates.
- [x] T004 [US2] Add explicit start/end/mute, captions, connection recovery and interruptible WebRTC playback in `static/voice-live.js`; test with a browser fixture without paid provider calls.
- [x] T005 [US6] Carry bounded current-route and selected-artifact context into typed and spoken Genesis turns; use existing navigation, edit and save tools and receipts.
- [x] T006 [US2] Repair existing dictation authentication and microphone lifecycle regressions with targeted checks.
- [x] T007 [US2] Run focused offline and browser checks, review integration, and record verified behavior and remaining live-service gates.

This slice does not claim the remaining numeric-registry, checked source-preview,
memory or calibration stories are implemented. Voice must distinguish recorded tool
receipts from unverified generated answers; unsupported claims cannot be released
as verified results. Live provider availability and audio quality require a real
session after local checks and verified budget readiness.

## Completion evidence

The local connection tasks above pass 152 focused Python tests and 14 browser
scenarios (11 voice lifecycle, 2 real Genesis conversation/navigation, 1 open
editor/live-edit integration). Final scoped review found no remaining material
issues. See [implementation evidence](implementation-2026-09-11.md). Live audio
validation and the broader feature acceptance remain incomplete; the current-week
billing verification flag is false. No paid session or deployment was performed.
