---
name: Genesis floating orb
description: Feature-specific voice and recorded activity instrument for AI Labs Studio.
---

# Design System: Genesis floating orb

## Overview

**Creative North Star: "The floating instrument"**

This feature extends the established paper-and-ink Studio with a floating sphere and a nonmodal activity panel. Its measurements support the product's evidence-first purpose: audio comes from existing streams and action bars come from observed events. The established site design is unchanged. This document is scoped to feature 025; the repository's root `DESIGN.md` remains benchmark methodology and is not replaced.

Lucas chose the floating ball, then removed visible captions, the control toolbar and cost copy because Genesis communicates them. The panel opens during a voice session or observed running work, and also remains available for a voice problem. An idle or completed turn without voice leaves the launcher visible.

**Key Characteristics:**

- Paper, ink, hairline rules, Newsreader and Plex continue the existing editorial direction.
- The sphere is a state symbol; charts represent measurements and recorded completions.
- Signal red identifies working or speaking; readable labels distinguish the other states.

This record extracts the implemented component from `genesis-orb.css`, `genesis-orb.js`, `index.html` and `voice-live.js`, with direction from `PRODUCT.md` and `orb-plan.md`. It does not create global tokens or a global design sidecar. Shared token values remain owned by the existing stylesheet rather than being duplicated here.

## Colors

The component consumes the existing semantic palette in both themes.

- **Primary:** signal red (`--signal`, `--signal-hover`) colors the speaking/working sphere, Genesis audio line, active action category and keyboard focus ring.
- **Neutral:** paper (`--bg`) provides the panel and label surface. Ink (`--ink`) provides text, microphone signal and completed action bars. Muted ink (`--muted`) carries secondary readings and the resting sphere highlight.
- **Rules and tracks:** `--line`, `--line-strong` and `--surface-3` separate measurements and establish bar tracks.
- **Error:** `--fail` and `--fail-text` distinguish the launcher label when attention is needed.

**The Measured Signal Rule.** A red sphere means working or audible speaking activity; it does not imply successful completion. Blocked or muted playback cannot produce the speaking state.

## Typography

The Genesis heading uses the established Newsreader prose family (`--font-prose`), normal weight (400), the existing `--text-7` size, line height (1), and slightly tightened tracking (-.02em). Labels use IBM Plex Sans (`--font-ui`); measured values use IBM Plex Mono (`--font-mono`). Body and label sizes reuse `--text-1` and `--text-2`.

The pairing gives the panel an editorial heading while keeping state labels and numeric readings compact. The component adds no new font assets or typography scale.

## Layout

The instrument is fixed at the bottom right, above the page (z-index 45). Its width is 380px, constrained to the viewport minus 32px. The bottom offset respects the safe-area inset. Only the panel and launcher receive pointer events, allowing interaction with the page around them.

The panel sits above the launcher with existing spacing tokens, scrolls internally when needed, and is capped at the dynamic viewport height minus 136px. The launcher combines a wrapping label with a sphere (72px). At the 600px breakpoint, panel padding and the right offset reduce, the sphere becomes 64px, and the label maximum width becomes 190px instead of 220px.

The audio figure is 64px high. Recorded action rows use a 90px label column, a flexible bar and a 28px count. The component is hidden in print. Browser evidence covers desktop (1440px) and phone (390px) widths in light and dark themes.

## Elevation & Depth

Depth is a local affordance for the floating instrument. The paper panel has an ink-tinted shadow (`0 12px 32px color-mix(in srgb,var(--ink) 12%,transparent)`) and the sphere has a smaller shadow (`0 5px 14px color-mix(in srgb,var(--ink) 18%,transparent)`). Radial gradients make the sphere legible as a ball. These treatments do not redefine elevation elsewhere in Studio.

## Shapes

The sphere is circular (50% radius), with a decorative meridian-and-equator SVG clipped inside. The panel and launcher label retain square corners and single-pixel rules. The SVG is hidden from assistive technology; the button and status text carry meaning.

## Components

### Orb launcher and lifecycle

The launcher is a native button with a signal-colored focus outline (2px, offset 5px). Clicking starts voice when inactive, ends voice when active, or first retries playback when autoplay was blocked. Its accessible name changes accordingly. Escape ends an active voice session. Ordinary Space retains native browser/button behavior; Ctrl+Shift+Space preserves push-to-talk, and F8 preserves mode switching outside text-entry controls.

States include idle, connecting, ending, listening, microphone off, speaking, working and needs attention. A completed observed turn changes the idle label to "Turn complete". A running tool's action can replace the generic working label. The status live region is updated only when its label changes, avoiding repeated announcements from the sampling loop.

A brief sphere rotation reacts to phase changes, audio activity or newly observed turn events. Hover lifts the sphere by 3px. Reduced motion disables rotation, transition and hover movement; it also hides the scrolling signal graph and legend while retaining numeric readings. Hidden pages skip sampling work.

### Voice and recorded activity panel

The panel is nonmodal and follows voice/work/problem state; the launcher is not an independent panel disclosure toggle. Visible content consists of the Genesis heading, status, measured audio signal and recorded actions. Captions, legacy controls and playback elements remain inside hidden compatibility markup. No caption transcript, toolbar or cost copy is presented.

Audio analyzers attach to the microphone and remote audio streams already created by the voice lifecycle. Each reading is time-domain RMS, scaled by four and clamped to one; numeric readings express that normalized value on a 0–100 scale, not decibels or confidence. Eighty samples at normal 100ms intervals provide roughly eight seconds of history. Unavailable input is labeled "Signal unavailable"; unavailable output is shown as a dash. Ending voice disconnects analyzers, closes their audio context and resets the chart.

Action bars count `tool_completed` events in the latest observed turn, classified by action name as Read, Build, Run, Report or Other. Widths are relative to the largest category count. A running `tool_started` category receives the signal accent; it does not increase a completion count. These bars are neither a percentage of task completion nor an authored workflow graph.

**The Existing Evidence Rule.** The visualizer consumes the current voice lifecycle and Genesis turn events. It makes no new service requests, captures no additional microphone stream and infers no successful writes.

### Validation record — 11 September 2026

The implementation run reports 16 passing offline browser scenarios and nine passing CSP tests. Browser coverage includes lifecycle, recorded activity, keyboard behavior, mobile, dark theme and reduced motion. Captures are retained locally under `monarch-benchmark/workflowbench/.tmp/genesis-voice-browser/`:

- `orb-idle-1440.png` and `orb-idle-390.png`.
- `orb-working-1440.png` and `orb-working-390.png`.
- `orb-dark-1440.png` and `orb-dark-390.png`.

Visual review found no layout blockers. Final verdict: **SHIP at the targeted fix scope**. Source verification resolved repeated live-region announcements and speaking while playback was blocked; this final verification was not a fresh visual audit. The regex detector ran in degraded mode and returned zero findings; it is not evidence of a full contrast audit. No full contrast audit, paid voice session, push or deployment was performed.

## Do's and Don'ts

- **Do** preserve the existing paper/ink typography and token sources.
- **Do** derive graphs from actual streams and recorded events, and label unavailable measurements.
- **Do** keep native keyboard behavior and reduced-motion numeric feedback.
- **Don't** add visible captions, a control toolbar or cost copy to this component without a new direction from Lucas.
- **Don't** present category bars as progress, successful work or a workflow DAG.
- **Don't** promote the sphere's gradients or floating shadows into global design rules.
