---
name: Genesis live stage
description: Compact 3D ASCII activity in Studio paper and ink, with expandable work and evidence.
typography:
  body:
    fontFamily: '"IBM Plex Mono", ui-monospace, Consolas, monospace'
    fontSize: "13px"
    lineHeight: 1.6
  evidence:
    fontFamily: '"IBM Plex Mono", ui-monospace, Consolas, monospace'
    fontSize: "11px"
    lineHeight: 1.55
  research:
    fontFamily: '"IBM Plex Mono", ui-monospace, Consolas, monospace'
    fontSize: "18px"
    lineHeight: 1.5
rounded:
  surface: "0"
spacing:
  compact: "8px"
  row: "12px"
  section: "16px"
  scene: "24px"
---

# Design System: Genesis live stage extension

## Overview

This records the delivered extension and Lucas's latest visual correction, dated 11 September 2026. Genesis retains the Matrix-like projected 3D geometry in a compact instrument that matches Studio's paper, ink and local fonts. A short activity summary stays visible; work cards and tool evidence expand when needed. This is a code-led surface extension with no new visual comps.

Source truth is `tokens.css`, `genesis-matrix.js`, `genesis-matrix.css`, `genesis-stage.js`, `genesis-stage.css`, `genesis-workspace.js`, `genesis-workspace.css` and `genesis-orb.css`, all under `monarch-benchmark/workflowbench/wb_studio/static/`. The typed presentation contract is `monarch-benchmark/workflowbench/wb_studio/genesis_present.py`. The surface brief in [spec.md](spec.md) and [plan.md](plan.md) owns task intent; this file does not replace the historical root design document.

## Colors

Use existing theme tokens: `--ink` for projected geometry and primary text, `--muted` for narration and captions, and `--faint` for rain at 0.18 opacity. The scene has a transparent background over Studio paper. Warning geometry uses `--warn-text`; the live indicator uses `--signal`. Rules use `--line` / `--line-strong`, and raw evidence uses `--surface-2`. Light and dark values remain in `tokens.css`; the extension has no neon palette.

## Typography

IBM Plex Sans carries actions and narration; IBM Plex Mono carries ASCII, timestamps and raw evidence. Research card detail uses Newsreader. Main narration uses an 18px heading, reducing to 15px in narrow containers and 13px in the persistent window. The character field uses unit line height, zero letter spacing and disabled ligatures to preserve its geometry. Narration wraps independently at a readable 65ch measure; card detail uses 68ch.

## Layout

The desktop conversation uses a 190px thread column, flexible center and 300px tracking column. Tracking moves below at 1100px; the shell becomes one column at 720px. The stage places compact ASCII art beside narration in a 200px illustration column; completed scenes reduce that column to 90px. A 430px container breakpoint uses a 108px illustration column, stacks card facts and moves log detail below its label. Work details and Activity stream start closed, with visible counts and preserved open state during updates. Dense evidence scrolls locally.

The persistent Genesis window renders the same recorded turn outside Genesis routes. Above 1100px, the guided layout reserves 352px beside the main content and adjusts editor grids so the activity window does not cover the feature. At 1100px and below, the activity panel joins normal document flow above the feature, with a 320px maximum height and local scrolling; only the launcher floats. Visibility changes trigger a resize so canvases can adapt. The window is 320px wide with 12px desktop panel padding and a 48px launcher sphere. Its scene uses a 94px illustration column beside the heading and tool count; the longer narration is hidden. Expanded cards scroll within 200px and logs within 116px. Finished scenes shrink. Back to conversation, Stop following / Resume following, Stop work and Hide activity retain separate meanings. Hiding activity dismisses the current turn's window; it does not stop work.

## Elevation & Depth

The ASCII field renders actual projected geometry: cached three-dimensional points and surface normals rotate in perspective, a depth buffer resolves visibility, and viewer-space lighting selects characters from a luminance ramp. This produces changing form and shading, rather than rotating a flat icon. Separately dimmed rain remains behind the foreground. Cards and evidence stay flat, divided by rules and tonal fields. The existing spherical launcher keeps its small shadow; the activity panel has none.

## Shapes

Surfaces and controls keep the incumbent square geometry. Cards are ruled rows, with labeled facts and optional source disclosures. The small square live indicator is accompanied by text. Keyboard focus uses a visible two-pixel outline with offset.

## Components

**Live scene.** Seven projected scenes cover thinking (folded brain and stem, captioned Neural field), research (orbital sphere, Signal search), architecture (connected spatial nodes, Product graph), configuration (nested cubes), execution (extruded lightning), result (solid document, Recorded result) and warning (extruded triangle with an exclamation mark, Attention). Ordinary tool events choose a scene even without a presentation card. Illustration is hidden from assistive technology; readable headings and status remain available.

**Streamed cards.** Cards sit inside the initially closed Work details disclosure; its count updates without forcing it open. The model calls `present` with plain text, one template and a stable card ID. Reusing the ID replaces that card within the turn. Cards contain at most six facts and six source references, with optional allowlisted Studio navigation. Active, complete and blocked appear as In progress, Recorded and Needs attention. A recorded card is not a verified benchmark outcome. Research emphasizes prose; configuration uses label/value rows; architecture emphasizes relationships; results emphasize values.

**Activity stream.** The stream starts closed and keeps its expansion state as events arrive. Actual stored tool starts and completions supply timestamps, action labels, payloads and responses. Native disclosures expose recorded evidence without replacing it with narration. Updates preserve open disclosures and avoid pulling a reader back to the bottom after they scroll away. The stream displays selected event types; it is a view over the existing event record, not a new evidence store.

**Guided configuration.** Cards link to Studio surfaces; `show` and the existing Follow mechanism guide navigation. Actual editing and saving remain the responsibility of existing tools. `present` only returns a persisted presentation receipt: it neither changes configuration nor launches a benchmark. Starter prompts fill the composer and select the first placeholder; the user sends the request when ready.

**Controlled motion.** The stage renders a 96-by-38 character field every 80ms while work is running, visible and unpaused. Rotation, lighting and rain evolve together; completed turns retain a still frame. Local pause, hidden tabs, offscreen stages and reduced-motion preference suppress motion. Cards enter over 420ms and guided view transitions use short fades and vertical movement. Motion never represents a measured percentage or hidden model reasoning.

## Do's and Don'ts

- Do use Studio's paper, ink and local IBM Plex fonts for the compact instrument and its surrounding evidence.
- Do pair projected scenes with readable, evidence-grounded narration and keep rain dimmer than the foreground.
- Do keep source references, raw tool evidence and user-controlled navigation reachable through disclosures without forcing them open.
- Do distinguish finished presentation, saved configuration and verified task outcome.
- Don't let presentation cards manufacture metrics, claim unseen reasoning or imply that a tool completion proves success.
- Don't introduce another runner, polling loop or event store for the persistent window.

Delivery evidence reported by the integrating task for the compact correction: desktop/mobile UI and guided-editor checks passed, all nine static CSP checks passed, and the scoped detector returned `[]`. Fresh independent live review returned Ship at 1440px and 390px in light and dark themes: no overflow or page errors, both disclosures initially closed, and user-opened disclosures retained through updates. The earlier geometry checks covered all seven scenes and measured a 0.876ms mean warm brain frame in that browser sample. These checks do not establish paid-model acceptance, a live benchmark result or independent verification of model-authored card claims.

## Genesis typography refinement

Lucas requested the same face as the ASCII artwork. Genesis now scopes its UI and prose font roles to the existing IBM Plex Mono token, including the conversation, live stage, disclosures, controls and launcher. Sizes, weight hierarchy and theme colors remain in place. The rest of Studio retains its own typography. No font assets were added. Desktop/mobile replay checks passed.

## Terminal frame refinement

The compact companion now uses a theme-aware dotted surface, a fine perimeter rule, and 14px ink registration corners. The ASCII field sits on a quiet 12px grid with horizontal hairlines. Controls and expandable evidence retain opaque surface backgrounds for reading. A subtle offset shadow separates the floating window from the workspace; no added motion or larger dimensions. Decorative corners ignore pointer events, and forced-colors mode uses native Canvas colors. Desktop/mobile replay verified.
