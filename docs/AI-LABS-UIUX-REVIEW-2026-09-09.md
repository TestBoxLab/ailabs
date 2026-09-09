# AI Labs Studio — UI/UX review, 9 September 2026

Reviewer: Lucas Wakigawa, with Claude Code. Method: the Studio served locally
from this branch (`wb studio --port 8765`) with the eight recorded runs in
`workflowbench/out/studio`; every top-level view, the run outcomes flow, the
New run wizard, the architecture editor, dark theme and a 375 px viewport.
No paid run was launched. Backend code was not changed except one footnote
string in `wb_studio/usage.py`.

This review complements the adversarial review of the same morning
(`AI-LABS-ADVERSARIAL-REVIEW-2026-09-09.md`), which covered reliability and
decision support. This one covers convention, hierarchy and copy.

## Verdict

The shell is sound: one top bar, six sections, square ink-and-ivory styling,
real tables, a three-step wizard that ends in a proper review screen. The
problems are underneath: the same idea has six names, the same number is shown
three times on one page, every heading carries an explanatory paragraph, and a
few real defects (dark theme, page title, ghost scroll height) that a user
meets within a minute.

Copy volume before this pass, in the static shell alone:

| Pattern | Count |
|---|---:|
| `<details>` disclosures across the front end | 43 |
| Hint or help paragraphs in `index.html` | 15 |
| Middot separators (`A · B · C`) in JS and HTML | 85 |
| "A, B, and C" three-item subtitles | 11 |

## Keep

- The top bar, section order and the "New run" primary action.
- The wizard's third step: `10 tasks × 1 setup = 10 attempts`, edit links per
  block, spend cap and the "Start run · $5.00 max" button. This is the best
  screen in the product.
- The Runs table columns and the status pills.
- The architecture canvas: palette, inspector, undo/redo, fit, zoom, shortcuts.
- The evidence-first outcome structure (claim, fact tag, event link).

## Findings, ranked

### P1 — Clicking a run does not open it

The run title is the expander toggle. Outcomes are reached by expanding the
row and then pressing "Open outcomes" inside it. Every comparable tool
(LangSmith, Braintrust, Langfuse, Inspect) opens the run on click and keeps
metadata in a secondary control. Proposal: title opens outcomes; a chevron at
the row end toggles configuration. Source: `workspace.js` `renderHistory`.

### P1 — Six names for two concepts

The thing being compared is called setup (wizard), approach (run details),
architecture (Studio), runner (Results table header "Task / runner"), model
(wizard step 1) and competitor (`PLAN.md`). The kind of run is called track
(Runs filter), purpose (Studio) and evaluation (run details). Pick one word for
each and use it in every label. Suggested: **setup** for the thing compared,
**track** for the kind of run. This is a label-only change.

### P1 — Dark theme made Budget and Leaderboard unreadable (fixed)

`analytics.css` painted both panels with `var(--panel,#fff)`; `--panel` is not
defined anywhere, so the panels stayed white under light text. Replaced with
`var(--surface)`. Verified by computed style after the fix.

### P1 — One page, the same number three times

For the failed run the Overview shows "0 succeeded; 1 failed out of 1", a
100 % bar labelled "1 of 1 failed", then "Task outcomes: 0 of 1 passed"; the
Results tab repeats it as three stat tiles. Proposal: one summary strip at the
top of the run (passed / failed / cost / time) and the failure-category bars
only when there are at least two categories.

### P1 — Two surfaces for one task output

Clicking a result row fills a "Task output" panel at the bottom of the page and
opens a modal with the same content. At 1440 × 900 the bottom panel is below
the fold, so the modal is the only one the user sees. Pick one: the
conventional choice is a right-hand side panel and no modal. The Activity tab
also shows the model's markdown unrendered ("### Processed Expense Requests",
"**Alice Park**") while the modal renders it.

### P1 — Data artifacts shown as text

- The changes table shows `<object>` for any record value that is a dict or
  list (`wb_world/snapshot.py:55`). Show the JSON, or "record".
- Five checks read "gmail message sent to" with an empty recipient.
- Six identical "Event 128" buttons on one finding. Label them by what they
  show ("Airtable update", "Email to Alice") or show one link.

These are report-layer issues, not front-end ones; listed here because the
front end is where they surface.

### P2 — Ghost page height

After closing the task modal, scrolling down reveals a full blank screen. The
hidden workspace keeps its height. Reproduced on the Run outcomes view.

### P2 — New run is a dialog that behaves like a page

`#launch-dialog` is opened with `dialog.show()` and laid out in flow. Escape
does nothing, the page scrolls behind it, and "Save for later" sits where
Close belongs. It works as a page, so make it a route with a Cancel action and
drop the `<dialog>` element. The tab title said "Architecture studio" while it
was open; fixed in `workspace.js`.

### P2 — Seven toolbar controls for eight runs

Search, Status, Track, Sort, Reset, Refresh and Export CSV sit above the table.
Refresh should be automatic; Reset should appear only when a filter is active;
Export belongs in an overflow menu. On a phone this toolbar is the whole first
screen.

### P2 — Empty states with no way forward

- Leaderboard: an empty "Architecture" select with no options, a heading, an
  explanatory paragraph and then "No full benchmark runs yet". The empty state
  alone, with a "Start a 50-task run" action, is enough.
- Genesis: six boxes showing 0 and a chat pane with a "G" avatar. The only
  action is "Add hypothesis" at the top right, which opens a form below the
  fold. Put the form, or one starter prompt, in the empty board.
- Results inspector: "Open a task outcome / Read the findings first…" replaced
  with "No task selected".

### P2 — Settings shows internals

"Installed components" (brain, action builder, judge, version IDs) and a
provider-limits table with one "Default for each provider" row are developer
facts. Move them under an "Advanced" disclosure or into the docs; keep
capacity, credentials and Monarch Enterprise.

### P2 — Warnings that do not apply

Step 2 of the wizard shows "10 task/model comparisons have no recorded Bare
result…" while "Also run each model's Bare version" is unchecked. Show it only
when the box is checked.

### P3 — Small things

- Results table header "Actions" held a count; renamed "Actions taken".
- The architecture editor opens a saved v1 as "Draft revision 1" with "1
  problem before publishing" although v1 is published and has been used by
  runs. The list and the editor disagree about what exists.
- The Activity tab draws a "task brief → Result output" mini-diagram for a
  single-node run. Decoration; remove for runs with one node.
- Run expander buttons expose no accessible name in the tree; verify with a
  screen reader.
- Mobile (375 px): the nav wraps to two rows, the toolbar fills the first
  screen, the table scrolls sideways with the Status pill clipped. Internal
  tool, low priority: collapse the toolbar behind a Filter button and hide
  Track, Progress and Created below 900 px.

## Slop patterns, and what was cut

The front end had the marks of generated UI copy: a subtitle on every page
built from three nouns and a comma ("Run history, outcomes, and the versions
behind them."), a paragraph of justification under every heading, disclosure
widgets for text that should not exist, "Observed execution · select a node to
inspect", "Inside the experiment", and a design-note HTML comment (`THESIS:
… OWN-WORLD: … FINISH: …`) shipped inside the page.

Applied in this pass, 48 edits across seven files:

- `workspace.js`: page subtitles removed (Runs, Run outcomes, Budget,
  Settings, Genesis); Leaderboard keeps one line of real information ("Full
  50-task runs only."). Failure summary shortened to "X passed, Y failed, Z
  attempts." and "Failures by category. Categories describe evidence, not
  cause." Tab title bug fixed.
- `observatory.js`: "Inside the experiment" → "Live"; "Recorded workstreams" →
  "Output"; two explanatory lines removed.
- `analytics.js`, `usage.py`: "Task attempts recorded in this workspace"
  removed; the chart footnote cut from three sentences to two.
- `analytics.css`: dark-theme panel fix.
- `app.js`: wizard hints cut ("Choose models below…", "You can inspect or
  change the requests below.", "The published architecture is unchanged.");
  leaderboard eligibility phrased in four words.
- `index.html`: 29 cuts. Second heading in step 2 removed; preset cards read
  "10 tasks / Quick check", "50 tasks / Full benchmark, counts for the
  leaderboard", "Pick tasks / Browse the catalog"; "Which models should run
  it?" → "Models"; "Ready to compare" → "Review"; the advanced-settings,
  runtime, runner, Monarch, prepare-dialog, shortcuts, versions, product-graph
  and inspector paragraphs shortened or removed; the design-note comment
  deleted.
- `style.css`: empty subtitles collapse (`p:empty{display:none}`).

Not touched, because they are a style decision for the team: the 85 middot
separators in metadata lines. They read fine in dense rows ("Informed worker /
v1 · low thinking") and badly in prose. Rule of thumb: middots between values,
never inside a sentence.

## Verification

- Title, subtitles, wizard copy and the dark-theme panel colour checked in the
  browser after a server restart.
- Studio tests: 167 passed, 2 failed. Both failures predate this pass and are
  backend timing assertions in `tests/test_studio_app.py` (`cancelling` vs
  `cancelled`; `active_attempts` 1 vs 0). They do not touch the files changed
  here.

## Suggested order

1. Row click opens the run; side panel instead of bottom panel plus modal.
2. One vocabulary (setup, track) across every label.
3. One summary strip per run; failure bars only with two or more categories.
4. Report-layer artifacts: `<object>`, empty recipients, repeated event links.
5. Ghost height, wizard as a route, Bare warning only when Bare is on.
6. Empty states for Leaderboard and Genesis; Settings internals under Advanced.
