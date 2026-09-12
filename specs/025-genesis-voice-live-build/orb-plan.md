# Floating Genesis activity, 11 September 2026

Lucas requested replacing the global voice strip with an animated floating ball,
modern graphs, and states driven by Genesis actions. He explicitly chose a floating
ball on screen. This extends feature 025; the site's editorial identity is retained.

## Design and acceptance

A bottom-right ink sphere opens a nonmodal paper panel. Newsreader, Plex, hairline
rules and the existing signal red carry the site's identity. Lucas then explicitly
removed captions, the control toolbar and cost copy: the agent communicates them.
Clicking the ball starts voice; clicking again or Escape ends it. If autoplay is
blocked, the ball first retries playback. Graphs appear during voice or observed work.
Phone layouts fit the viewport; reduced motion suppresses the sphere animation and
scrolling signal chart while keeping numeric signal readings.

Audio graphs show measured input/output envelopes only; unavailable audio is labeled.
Action bars count recorded tool events in the current observed turn, never fabricated
progress. The sphere's labeled states distinguish idle, connection, listening, muted,
speaking, working, completion and errors. Use the existing turn stream and WebRTC
streams without new service connections, dependencies, or benchmark changes.

## Tasks

- [x] T008 Implement floating panel, sphere, real signal charts and recorded action bars.
- [x] T009 Connect existing voice lifecycle and Genesis turn rendering to the visualizer.
- [x] T010 Verify offline lifecycle, activity, keyboard, mobile, dark and reduced motion;
  capture browser evidence, review and document the implemented component.

The installed Superpowers skills and Graphify are unavailable, as already recorded
in this feature. Follow the shared procedures with native tools and scoped review.

## Completion evidence — 11 September 2026

T008 and T009 are implemented in `genesis-orb.css`, `genesis-orb.js`,
`index.html` and `voice-live.js`: the floating instrument follows existing voice
and turn events, samples actual audio RMS, and counts completed tools in the
latest observed turn. It introduces no new service requests. The sphere uses
signal red during working/speaking. Lucas's corrected presentation is preserved:
no visible captions, toolbar or cost copy. Orb click starts/ends voice or retries
blocked playback; Escape ends voice, native Space behavior remains intact, and
Ctrl+Shift+Space push-to-talk remains available.

T010 completed with 16 passing offline browser scenarios and nine passing CSP
tests. Desktop (1440px) and phone (390px), light/dark captures are retained at
`monarch-benchmark/workflowbench/.tmp/genesis-voice-browser/orb-*.png`.
The component is documented in [orb-design.md](orb-design.md), without changing
the global design or the repository's methodology `DESIGN.md`.

Visual review found no layout blockers. Final verdict: **SHIP at the targeted
fix scope**. Source verification resolved repeated status announcements and the
speaking state during blocked playback; that final verification was not a fresh
visual audit. The degraded regex detector returned zero findings; no full
contrast audit was performed. No paid voice session, push or deployment was
performed.
