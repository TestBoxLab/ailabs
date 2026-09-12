---
name: Genesis recovery
description: An independent recovery surface in the AI Labs Studio visual language.
colors:
  paper: "#f4f4f1"
  surface: "#fbfbf9"
  ink: "#161616"
  muted: "#5b5b58"
  hairline: "#d6d6d0"
  signal: "#d3261e"
  signal-hover: "#b21f18"
  selection: "#e9dcd9"
  on-signal: "white"
typography:
  display:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "clamp(28px, 4vw, 42px)"
    fontWeight: 500
    lineHeight: 1.1
  headline:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 500
  title:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 500
  body:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "16px"
    lineHeight: 1.5
  label:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "14px"
  code:
    fontFamily: "Consolas, monospace"
    fontSize: "12px"
    lineHeight: 1.6
rounded:
  square: "0"
spacing:
  inline: "8px"
  compact: "16px"
  section: "24px"
  receipt: "32px"
  mobile-columns: "40px"
  desktop-columns: "64px"
components:
  button-primary:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.on-signal}"
    rounded: "{rounded.square}"
    padding: "9px 16px"
  button-primary-hover:
    backgroundColor: "{colors.signal-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    padding: "9px 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    padding: "10px 12px"
  repair-row:
    padding: "16px 0"
    rounded: "{rounded.square}"
---

# Design System: Genesis recovery

## Overview

**Creative North Star: "The Swiss technical manual"**

Genesis recovery extends the established AI Labs Studio world: paper, ink, signal red, Plex typography and hairline rules. It is a compact operational document for authenticating, requesting a repair at a pinned revision, and inspecting its receipt. It does not establish a new brand.

This record describes the local implementation reviewed on 11 September 2026. It does not establish deployment, working production credentials, worker availability or funding. The opening direction contract in `static/index.html`, `static/recovery.css` and `static/recovery.js` are the implementation sources. Desktop and mobile review captures are at repository-root `.impeccable/review/recovery/desktop.png` and `mobile.png`.

**Key Characteristics:**

- Paper and ink with a reserved signal accent.
- Visible labels, flat sections and direct state language.
- Receipts reached through deliberate selection and keyboard focus.

**The Inheritance Rule.** Extend Studio's existing visual language without changing its identity or the repository's historical methodology documents.

## Colors

Signal red identifies the primary queue action, keyboard focus, text caret and error messages. Its deeper hover variant confirms an actionable button. Selection uses a pale warm tint.

Paper is the page canvas; the lighter surface identifies fields, selected or hovered repair rows, and code output. Ink carries headings and normal text. Muted ink carries hints, timestamps and service state. Hairlines divide sections and provide quiet field boundaries. On-signal text provides the primary button contrast.

**The State Wording Rule.** State is always written in text; color alone never communicates a repair outcome or connection status.

## Typography

Plex is the locally served IBM Plex Sans face, available in regular and medium weights, with Arial and sans-serif fallbacks. The display role names the page, headline names each working section, and title introduces the receipt. Medium weight establishes hierarchy without decorative typography. Body copy stays within 72 characters where paragraph sizing applies.

Hints use the label size. Repair-row metadata and the footer are 13px. Verification output and patch previews use the code role; receipt values use tabular numerals and wrap long identifiers. This narrow surface does not introduce Studio's report-serif treatment.

## Layout

A compact header leads to the page title, explanation and access strip. Once connected, the request form sits beside the repair list and selected receipt. Main content is capped at 1320px, with 4vw side padding and a 64px desktop column gap. The access strip is capped at 720px.

At 760px and below, the header stacks, the workspace becomes one column, and the column gap becomes 40px. Reading order remains access, request, repairs, receipt. Inline field/action rows wrap, with actions allowed to grow across the available width. Long metadata wraps; code blocks scroll within their own area and are capped at 400px tall.

**The Reading Order Rule.** Responsive layout preserves the form-to-receipt sequence and keeps every action reachable without horizontal page scrolling.

## Elevation & Depth

The surface is flat. It has no shadows or animated elevation. Background tones, spacing and one-pixel rules establish grouping. A darker rule marks the receipt as the detailed evidence beneath the repair list.

## Shapes

Controls and output panels have square corners. Fields and secondary actions have hairline borders. Repair rows span their column, using a bottom rule rather than separate floating cards. Buttons have a minimum height of 44px.

## Components

### Access and service state

The access form starts with a visible password label and Connect action. Successful authentication hides the key field, label and Connect action, then shows **Connected to recovery**, Disconnect and the workspace. The key stays in tab memory and is cleared on page reload. Disconnect clears visible repair data and the request form, then focuses the key field.

Service availability in the header is separate from authentication. A healthy service response does not imply that a worker or authorized allowance is available.

### Fields and actions

Every field has a visible label. The source commit accepts a full 40-character lowercase hexadecimal revision; Use latest resolves it for the selected repository. Changing repository clears that revision. The change and verification text areas remain separate so intended behavior and acceptance conditions are explicit.

Queue repair is the sole red primary action. Secondary actions use the light surface and gain an ink border on hover. Pending actions are disabled with reduced opacity and a wait cursor. Keyboard focus uses a two-pixel signal outline with a three-pixel offset. Status messages use a polite live region; errors also use signal text.

### Repair list and receipt

The list shows the latest 50 requests, newest first. Each row presents the requested change, repository, written status and timestamp. A selected row exposes `aria-pressed=true` and the same light surface used on hover. An empty list explains where future requests will appear.

**The Receipt Focus Rule.** Selecting a repair or successfully queueing one reveals its receipt, focuses the Repair receipt heading and scrolls it into view. Refresh updates the current receipt without intentionally moving focus or scrolling to it; page reload is a separate operation that clears access.

The receipt exposes request identifier, pinned commit, update time and patch hash. Queued means saved and awaiting execution; verified means awaiting review, with the patch neither applied nor released. Verification output and patch preview use native disclosure controls. Download complete patch appears only when a patch hash is present and retrieves the complete patch separately from its preview.

## Do's and Don'ts

### Do:

- Do preserve the inherited paper, ink, signal red and square-control language.
- Do keep authentication state explicit after the access field disappears.
- Do reveal and focus the receipt after selection or queueing while leaving Refresh in place.
- Do distinguish a saved request, executed work, verification and release in visible language.

### Don't:

- Don't substitute decorative cards, shadows or a new visual identity for the flat document layout.
- Don't hide operational meaning behind color alone.
- Don't describe a local review or healthy service response as proof of credentials, funding, execution or deployment.
- Don't replace the repository-root DESIGN.md or PRODUCT.md with this scoped recovery record.
