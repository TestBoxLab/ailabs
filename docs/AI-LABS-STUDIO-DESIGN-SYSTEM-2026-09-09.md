# AI Labs Studio — the visual system (9 September 2026, night)

Status: design of record for the Studio's front end, written from the built
code after the redesign of 9 Sep. Replaces the "Visual system" section of
`AI-LABS-STUDIO-DESIGN-DIRECTION-2026-09-09.md` (the sage, green and serif
choice). The methodology in `monarch-benchmark/DESIGN.md` is untouched; this
file is about how the Studio looks. Research behind it: `.tmp/research-ui.md`
(30 sources) and the front-end audit of the same night.

## The world

A Swiss technical manual. The grid, one grotesque, rules and whitespace. A
benchmark instrument reads like a technical report, not like a dashboard.
Direction chosen by the design seed `3bd8ccde` (candidate 6 of 7 grounded
candidates: booktabs paper, auditor's ledger, strip-chart recorder,
split-flap board, lab notebook, Swiss manual, mission-control console). The
contract sits as the first comment in `wb_studio/static/index.html`.

What the research said the old system was: the 2026 default. Cream ground,
serif display, sage and forest green, tracked uppercase mono labels, cards in
cards, chips, dashed empty boxes, a dark coloured bar. All of it is gone.

## Rules

**Colour.** Two grounds only: the page (`--bg`) and the raised field
(`--surface`) for inputs. Ink for text and rules. Greys for secondary text
and hairlines. One signal colour, red (`--signal`), used for exactly three
things: the current place in the navigation, the primary action on hover,
and the focus ring. Meaning colours stay in results: green is passed and
better than Bare, red is failed and worse, amber warns, blue is running.
Model families have one hue each and appear only in figures. Dark theme is
warm ink on warm paper, never pure black; elevation by lightness, never by
shadow.

**Type.** IBM Plex Sans for every sentence in the tool. Newsreader (variable,
optical size on) for the report prose a person reads at length: the verdict,
findings, caveats and terms; report headings, tables and figures stay in Sans
and Mono. IBM Plex Mono for every value the machine says: ids, hashes, counts,
money, times, the ledger line. Tabular numerals everywhere. Scale: 11, 12, 13 for the tool;
15 for reading; 18, 24, 34, 48 for headings, with real jumps. Weight carries
hierarchy; colour never does. No uppercase, no tracked labels, no eyebrow
above a title.

**Surfaces.** Rules, not boxes. Sections are separated by a 1px ink rule
(`--line-strong`) and rows by a hairline (`--line`). No card has a border
on all four sides. No radius. No shadow. No dashed box around an empty
state: an empty state is one sentence in the measure and one action.

**Tables.** Booktabs: an ink rule above and below, a hairline under the
header, no vertical rules, numbers right in mono, text left, headers in
sentence case. Hover on a row is a lighter ground.

**The grid.** Page up to 1440px, margins 48px, gutter 24px. A label column
of 200px for every fact list and form (`.facts`, `.method`, the run
details). Prose keeps a 66-character measure; figures and tables take the
width. Report sections are numbered (01, 02, …) because readers cite them.

**Status.** A word with a 7px square before it; the square carries the
colour. Running pulses. No pill, no background.

**Controls.** Buttons are ink on paper with a 1px ink border; the one
primary action is paper on ink and turns signal red on hover. Fields are a
hairline box on the raised ground; focus is an ink border, caret in signal
red. Tabs are text with a 2px ink rule under the current one.

**Motion.** None but the running pulse and the live pen. Reduced motion
turns everything off.

## Where it lives

- `wb_studio/static/tokens.css`: every colour, space, type and grid token,
  light and dark. The only file allowed to hold hex colours.
- `wb_studio/static/ui.css`: the running head, page titles, buttons, fields,
  tables, tabs, status marks, blocks, dialogs, toasts, the label column.
- View sheets (`style.css`, `workspace.css`, `graph.css`, `genesis.css`,
  `analytics.css`, `report.css`, `charts.css`, `studio-library.css`) keep
  layout only. Their old global overrides (radius 10px on everything, a
  16px root, an ink box behind the current nav item) are removed.
- `tests/test_static_csp.py` fails on any hex colour outside tokens.css,
  any inline style, any `!important`, any external resource.
- `tests/browser/suite.cjs` renders every surface in both themes and fails on
  horizontal overflow or a console error.

## Signature details

1. The running head: paper, one ink rule, the wordmark, the sections, and the
   ledger line in mono ("Week $296.95 left · Connected"). No coloured bar.
2. Report section numbers in mono before each title, and the report head with
   the title first and the run's facts as a mono byline under it.
3. Booktabs tables everywhere, including the runs list and the standings.
4. The verdict as a typeset sentence at 24px, the grade as a word with a
   square mark, never a chip.
5. Choice controls (track, steps) as ruled rows with a small square mark that
   fills in signal red when chosen.

## The operating views (pass 7, 10 Sep)

- **Lists** share one header: a search field, one or two text filter groups
  (a word with an ink rule under the current one), a small sort select, and
  Refresh and Export as text at the foot. Rows group under day rows in mono;
  the pager appears only past one page.
- **A run reads as a matrix**: tasks down, setups across, a square and a word
  in each cell, the finding under a failure, passes per setup in the foot.
  Below it, where it failed, as counts on rules. The inspector opens beside
  it; the matrix stays.
- **The ledger comes first on Budget**: the sentence, the facts, then every
  reservation of the week with who, what, ceiling and what settled. Usage by
  model follows; an empty period is one line.
- **Settings is sections with a label column**: Budget, Capacity, Providers
  (present or not, never the value), Genesis, Monarch Enterprise; the rest
  under Advanced.
- **Empty states teach**: one sentence that says what the thing is and what
  freezes it, and the one action that creates it.

## After the audit (10 Sep): surfaces and addresses

- **A detail peeks to the side of its table.** The attempt sheet sits fixed at
  the right edge, at most half the width, with no scrim; the page gives it
  that width above 1100 px so the matrix stays the map, and the current cell
  is marked in the signal colour. Full screen on a phone. The card sheet on
  the Genesis board follows the same pattern. A centred modal is for a
  confirmation, never for reading.
- **One home per kind of evidence.** An event opens in the attempt sheet on
  Trace, selected, with its input and output beside the list. There is no
  second dialog.
- **Everything has an address.** `#run/<id>/<task>/<setup>/e<event>`,
  `#report/<id>/<section>?audience=internal`, `#round/<id>/<section>`. The
  first open of a sheet is a history entry so Back closes it; stepping
  replaces it. The page title is the thing's title.
- **A form that fits one page is one page.** New run is three sections on one
  page with a sticky footer that keeps the sum; the numbers above scroll,
  they do not gate. Choices a person cannot take are shown disabled with the
  reason beside them.
- **A grade carries the certainty of its sentence.** Improvement and
  Regression need the sign test; otherwise the word is Undecided with the
  tally and the p value. Standings rank by interval overlap and show a spread.
- **Figures leave the page whole.** Every row chart is drawn again at the
  width of its column, offers Download SVG and Download CSV, and carries a
  hidden data table for assistive technology.

## Still to do

- Newsreader is vendored under `static/vendor/newsreader/` (SIL OFL 1.1, two
  variable woff2 files, 455 KB) with Lucas's approval of 9 Sep night.
- Per-view sheets still carry 400+ px font sizes and 900+ px spacings; they
  match the scale by eye, not by token. Collapse them onto tokens over time.
- Eleven parallel empty-state classes remain; they now read alike but should
  become one.
- The node editor keeps its framed viewport on purpose; its inspector still
  uses a 12px field size.
