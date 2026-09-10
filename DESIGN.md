---
name: AI Labs Operate
description: Private daylight workspace for task outcomes, execution evidence, and experimental setups.
colors:
  ink: "#202b35"
  muted: "#5c6975"
  paper: "#f5f7f9"
  surface: "#fff"
  line: "#dce3e8"
  accent: "#135c48"
  accent-light: "#e4f2eb"
  blue: "#356cbd"
  red: "#ac3c3c"
typography:
  body:
    fontFamily: '"Segoe UI Variable", "Segoe UI", sans-serif'
    fontSize: "16px"
  headline:
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-.035em"
  report-title:
    fontSize: "26px"
    fontWeight: 550
    letterSpacing: "-.03em"
  outcome-title:
    fontSize: "19px"
    fontWeight: 550
    lineHeight: 1.4
    letterSpacing: "-.02em"
  raw-evidence:
    fontFamily: "Consolas, monospace"
    fontSize: "12px"
    lineHeight: 1.65
rounded:
  field: "6px"
  button: "7px"
  node: "9px"
  outcome: "10px"
  workspace: "12px"
  dialog: "14px"
spacing:
  compact: "8px"
  field: "12px"
  control: "16px"
  card-gap: "18px"
  outcome: "22px"
  section: "30px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.button}"
    padding: "10px 16px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.button}"
    padding: "10px 16px"
  outcome-card:
    backgroundColor: "#fbfcfb"
    textColor: "{colors.ink}"
    rounded: "{rounded.outcome}"
    padding: "22px"
---

# Design System: AI Labs Operate

## Overview

The incumbent visual system is a daylight operating workspace: white surfaces, cool paper, dark readable text, and restrained green actions. This documents the implemented interface, rather than proposing a new visual identity. The source of truth is `monarch-benchmark/workflowbench/wb_studio/static/style.css`, with behavior in `app.js` and structure in `index.html`.

Lead with what happened to the business task. The overview presents requirement outcomes and directly labeled runner comparisons; activity and raw evidence provide progressively deeper inspection. The interface should feel composed and useful during both successful work and incomplete execution.

Key characteristics:

- Readable task findings before tool payloads.
- Quiet surfaces with visible selection and focus.
- Motion tied to activity, navigation, and changing measurements.
- Explicit distinctions between measured outcomes, interpretations, execution issues, and drafts.

## Colors

The palette uses green for action and satisfied requirements, blue for current activity and keyboard focus, and red for failed requirements or errors. Cool neutral surfaces carry most of the screen.

Primary accent appears on New run, active navigation, selected controls, evidence links, and completed outcome bars. Its pale companion marks selected reasoning choices and completion status. Blue marks ongoing execution without implying success. Red communicates a concrete problem; an execution issue can remain neutral when it is not a measured task failure.

White separates the report from the surrounding paper. Muted text supports descriptions and metadata; ink carries task titles and findings. Thin neutral borders define sections without creating a wall of equally prominent cards.

**The labeled-state rule.** Pair status color with meaningful text or an icon and text. A colored bar or dot alone does not explain the outcome.

## Typography

Use the installed Segoe UI Variable stack throughout the reading interface. No remote font dependency is required. Consolas is reserved for raw evidence, preserving the distinction between a finding and its serialized source.

Page headings are compact rather than promotional. Report headings sit below the main title, while outcome titles name the business request in ordinary language. Descriptions generally use 13-15px text with generous line height; metadata uses 11-12px. Numeric measurements use tabular figures where implemented.

Keep report introductions near the implemented 72-character measure and analysis paragraphs near 70 characters. Use sentence case. Technical identifiers belong in detail views when a readable task or action name is available.

## Layout

The desktop shell has a 76px header, a main region capped at 2000px, and a bounded workspace. The default workspace pairs a 208px run history with a flexible report. Selecting evidence opens a third column: 180px history, flexible content, and a 370px inspector. The inspector is absent until relevant.

The overview uses a short account of the run, directly labeled comparison bars, and a two-column outcome grid. Opening the inspector reduces outcome cards to one column. Activity uses horizontally scrollable runner lanes with connected action nodes. These are observed execution sequences, not an authored workflow graph.

At 1100px and below, the inspector moves under the workspace and outcome cards become one column. At 680px, the shell stacks, report padding narrows, category and search controls stack, and setup history follows the editor. At the narrower 620px breakpoint, run history becomes a horizontal list and secondary header text is removed. Keep horizontal scrolling local to dense evidence, tables, or activity lanes; do not widen the page.

The New run dialog is 880px wide with a viewport-constrained width and 90vh maximum height. Its task catalog scrolls within a 310px region. The separate Monarch setups surface is capped at 1120px, with an editor and revision history arranged side by side until the mobile breakpoint.

## Elevation & Depth

Depth comes primarily from surface changes and one-pixel borders. Small shadows distinguish active history entries, interactive nodes, and hovered outcome cards. The modal uses the strongest shadow and a dimmed backdrop because it temporarily owns interaction.

The implemented shadow vocabulary includes a light active-history shadow (`0 2px 5px #203b4810`), subtle node lift (`0 2px 4px #163d4b08`), hovered outcome lift (`0 5px 16px #19352c0d`), and modal elevation (`0 22px 70px #142c3a35`). Do not apply the modal treatment to ordinary findings.

## Shapes

Use gently rounded rectangular controls and surfaces. Fields are the tightest, followed by buttons and action nodes; outcome cards, the workspace, and dialogs increase the radius modestly. Circular dots are reserved for compact state indicators. Bars use narrow, nearly square tracks, preserving the feel of a measurement rather than an ornamental pill.

The activity surface is a plain, lightly tinted canvas. The previous dotted grid has been removed. Straight connectors express observed order without adding decorative diagram complexity.

## Components

**New run.** The primary action uses the green button treatment. The dialog starts with a run name, runner choices, and task selection by readable request and category. Reasoning levels are selectable options where supported. Prompt and execution controls sit inside an expandable section. Keep unavailable runners disabled with a visible reason; do not present a disabled capability as a working option.

**Outcome cards.** Each card presents a labeled verdict, runner identity, business task title, short finding, and a preview of requirement checks. Additional requirements are disclosed with a count. The whole card opens findings and evidence. Hover changes the surface, border, and shadow over 200ms without shifting the layout.

**Comparison bars.** Display explicit satisfied/assessed counts alongside a shared bar scale. Execution issues remain separately described. The implemented width transition lasts 700ms with `cubic-bezier(.16,1,.3,1)`; never animate invented intermediate results as if they were observations.

**Evidence inspector.** Findings is the readable default; Raw evidence reveals the exact stored detail. Structured records use labeled fields and tables. Large formatted collections disclose truncation and retain access to raw content. Selection changes must clear stale output, and live refreshes must preserve keyboard focus.

**Activity nodes.** Use short action names, supporting context, and compact timing or status metadata. Selection adds a green border and restrained shadow. Running icons rotate through a small 2-second activity cycle; the previous expanding ring is removed. Use explicit error and completion states.

**Reasoning review.** Interpretive analysis follows measured task outcomes. Findings retain evidence links, uncertainty, limitations, and analyzer identity. The current UI identifies Gemini medium for the available analysis action and explicitly states that Sol medium is not connected. Do not visually or verbally imply that model interpretation replaces task verification.

**Monarch setups.** Present an architecture selection, hypothesis, prompt change, model, step limit, reasoning choices, and parent references as editable experimental inputs. Saved revisions are visibly drafts requiring an execution adapter. The architecture diagram summarizes the intended structure; it is not proof of an executed setup. Entering this surface uses a 500ms clipped reveal and an 8px vertical movement.

**Accessibility and motion.** Interactive controls use a visible blue focus outline with offset. Disabled controls reduce opacity and change the cursor, accompanied by explanatory text where capability is unavailable. Honor `prefers-reduced-motion`: disable animations and transitions and restore automatic scrolling. Use native buttons, labeled fields, and dialog behavior; retain visible focus during streaming updates.

## Do's and Don'ts

- Do begin with the business request, observed outcome, and requirements that explain the verdict.
- Do keep evidence reachable from the finding it supports.
- Do show unavailable, unknown, pending, draft, and failed states honestly.
- Do use animation to communicate a real change or current activity.
- Do preserve readable language and inspectable details together.
- Don't label execution failure as a measured model failure.
- Don't imply that saved Monarch revisions can run before their adapter exists.
- Don't present raw API controls as native harness competitors.
- Don't imply access to hidden reasoning or causal proof from one trace.
- Don't bury the outcome under identifiers, payload dumps, decorative statistics, or repeated generic dashboard cards.


Architecture selection uses one official default, **Default Monarch Enterprise**,
and user-named custom definitions. Keep repository revisions in secondary detail;
never restore the historical benchmark-preset menu. Custom architecture editing
reveals a name and unrestricted definition field in place.


The architecture surface now uses a node palette, scrollable canvas with connection
ports, and a settings inspector. Keep Save draft distinct from Publish version.
Keyboard controls mirror pointer editing. Difficulty badges sit on the right of task
rows; count and provisional status remain visible beside the three-bar icon.


## Studio enhancement — 8 September 2026

The current refinement uses a 68px desktop header, searchable run history and a
Tasks → Approaches → Review launcher. Unavailable integrations are disclosed
separately; architectures use their saved runners. The launch action includes the
maximum spend. Evidence has an explicit close control and restores focus to the
outcome. Tabs use arrow/Home/End navigation. At narrow widths, history scrolls
horizontally and editor controls stack while dense data stays locally scrollable.
Comparison bars no longer animate width. The final shared refinements live in
wb_studio/static/graph.css after the editor styles.

Research, fixes and observed checks are recorded in
[the enhancement report](docs/STUDIO-UX-RELIABILITY-2026-09-08.md).

## Studio information hierarchy — 8 September 2026

Keep each fact in one useful place. Outcome rows show status, task and finding; requirements belong in the evidence inspector. Compare approaches visually only when multiple approaches exist. Disclose optional analysis and editor documentation. Keep spend, failures, unsaved changes and recovery visible where decisions happen. Avoid generic taglines, repeated assurances, zero-issue badges and repeated action sentences. See docs/STUDIO-DESLOP-2026-09-08.md for sources and verification.

Avoid compressed metadata sentences such as task count + approach count + spending limit, or spend + holds + weekly cap separated by dots. Keep the primary value visible; put secondary values in a labeled breakdown. Do not substitute different punctuation for information hierarchy.

Task output: concise verdict first; supporting explanations expand under essential labels. Keep full instructions available. Evidence opens in a modal without replacing the underlying findings; preserve selection and restore focus on close.
