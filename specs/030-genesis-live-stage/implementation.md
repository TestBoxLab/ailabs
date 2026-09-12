# Implementation evidence — 11 September 2026

Genesis now renders recorded work as a live stage in the conversation and a
persistent activity window on other Studio pages. Seven ASCII scenes distinguish
thinking, research, architecture, configuration, execution, results and warnings.
The typed `present` tool produces bounded, redacted receipts through the existing
tool stream; stable card IDs replace previous snapshots. Cards have source refs,
facts and validated Studio links. Tool events expose their recorded payloads and
responses. No new transport, service, dependency or presentation database.

The starting prompts cover architecture research, run investigation and visible
configuration. They populate a draft; they do not submit or buy a run. Guided
navigation uses the existing Follow preference, respects gestures, and guards
unsaved architecture edits. Real edit_architecture receipts still update the
actual editor as provisional work. Presenting a card itself changes no setup.

The architecture audit is
[Product Graph Fast Path](../../research/architectures/2026-09-11-product-graph-fast-path.md).
It reviews recovered historical families and current WorkflowBench limitations,
then proposes a falsifiable candidate and ablations. It explicitly distinguishes
the currently expressible blueprint from future runtime selection, caching and
binding changes. No completion or speed advantage has been established.

## Verification

- `uv run python -m pytest tests/test_genesis_present.py tests/test_genesis_show.py tests/test_genesis_loop.py tests/test_genesis_stream_contract.py tests/test_static_csp.py -q`: **73 passed**, 1.57 seconds.
- `node tests/browser/genesis-missions.cjs`: **4 scenarios passed**.
- `node tests/browser/genesis-voice.cjs`: **17 scenarios passed**.
- [UI verification](verify-ui.cjs): actual local Studio at 1440 and 390 pixels;
  starter draft, keyed replacement, escaped content, source expansion, real frame
  changes, pause, reduced motion, retained off-page completion, dismissal, zero
  document overflow and zero page errors all passed. Input events were explicitly
  labeled UI replays, with no provider requests.
- [Guided editor verification](verify-guidance.cjs): created a temporary fixture
  draft, followed its real route, replayed an executor prompt edit, observed
  provisional/dirty state, and verified navigation could not discard it. Passed.
- Scoped Impeccable detector on the four new stage/workspace files: `[]`.
- Earlier finish review, before the latest compact correction: **Ship** for desktop/phone stage and activity window. The guided editor review found inspector overlap; dedicated desktop space and stacked mobile layout fixed it. The reviewer scored that fix **Resolved. Ship.** The UI and editor replays passed again; final syntax and 9 CSP checks passed.

Browser captures and machine-readable replay results are in
`.impeccable/review/genesis-stage-*`, `genesis-window-*`,
`genesis-guided-editor.png` and `genesis-stage-verification.json`.
Run the retained scripts from the repository root with the offline fixture server
on port 8768 (`uv run python tests/browser/server.py --port 8768 --live`, from
workflowbench). They use the installed local Playwright runtime and Chrome.

## Scope and limitations

Local implementation only; not deployed or pushed. No paid benchmark or model
request ran. The full suite was not run for this presentation change. Existing
mission, voice, report and repair edits were preserved. Source/configuration
access and current billing readiness remain separate live acceptance conditions.
Upstream AutomationBench code, assertions, tasks and frozen versions were not
changed. Graphify is absent per current project instructions; the audit uses code
and available records. Windows sandbox file helpers failed; authorized local
PowerShell operations and browser screenshots supplied the verification evidence.

## Current 3D and compact presentation

The current renderer, `genesis-matrix.js`, uses cached 3D geometry, perspective
projection, per-character depth buffering, surface-normal lighting and a
luminance glyph ramp. Separate dim rain preserves each foreground silhouette.
Seven geometries render at 96 by 38 characters every 80ms while visible and
running. Pause, offscreen suspension and reduced motion remain supported.

Lucas's latest correction keeps that renderer while matching the site and using
less screen space. `genesis-matrix.css` uses existing paper/ink theme tokens,
with no black/neon surface. Geometry sits beside concise narration. Work details
and Activity stream start closed, preserve their open state during updates, and
keep cards, source references, payloads and results expandable.

The persistent window is 320px wide, with 12px desktop padding and a 48px
launcher sphere. Guided desktop pages reserve 352px beside the feature. At
1100px and below the panel stays in document flow above the feature, bounded to
320px high with scrolling. Only the launcher floats. Expanded window cards
scroll within 200px; longer scene narration is hidden in this compact view.

Verification reported by the integrating task for this correction: desktop/mobile
UI and guided-editor checks passed, all nine static CSP checks passed, and the
scoped detector returned `[]`. Fresh independent live Chrome review returned
**Ship** at 1440px and 390px in light and dark themes: no document overflow or
page errors; both disclosures initially closed; user-opened disclosures persisted
through sync. Measured title/count contrast was 16.42/6.18 in light mode and
16.17/8.31 in dark mode. Empty voice-state space is hidden while actual messages
remain visible.
Earlier renderer checks covered all seven scenes, actual frame changes, pause
and reduced motion, with a 0.876ms mean warm brain frame in that browser sample.
The earlier black/green WebM preview demonstrates renderer motion but is
superseded as evidence of the current palette and layout. It is not a benchmark
run or a recording of model reasoning.
Typography refinement: scoped Genesis UI and prose to IBM Plex Mono, the existing ASCII font. Preserved compact dimensions, theme colors and non-Genesis typography. Desktop/mobile presentation replay passed.

Frame refinement: added theme-token dot paper, ink corner marks, a faint grid behind the ASCII art, and a restrained offset shadow. Kept the compact footprint and controls. Desktop/mobile replay passed.
The scoped detector reports one advisory for the grid background. This is intentional within the projected ASCII illustration to answer the requested terminal-style background; the surrounding website has no added grid.
