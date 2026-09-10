# AI Labs Studio — improvement ledger

Started 9 September 2026, afternoon, after the seven-phase plan landed
(`AI-LABS-IMPLEMENTATION-PLAN-2026-09-09.md`). The ledger is the running list
of what a visual pass found, what was fixed, and what is still open. The
standard is the morning review (`AI-LABS-UIUX-REVIEW-2026-09-09.md`): one name
per concept, one number per fact, no explanatory paragraph under a heading, no
motion that is not an observed event, every screen checked in the browser in
both themes before it is called done.

Method for each pass: `node .tmp/qa.cjs <fixture url>` renders every surface
against the fixture Studio (`tests/browser/server.py --live` adds a run left
mid-stream so the live views can be looked at), writes one screenshot per
surface, measures where the side panel lands after a scroll, and lists repeated
lines on the live page. Screenshots are read, not diffed.

## Pass 1 — 9 Sep, afternoon

| # | Surface | Finding | Severity | Status |
|---|---|---|---|---|
| 1 | Run page, side panel | The panel was not sticky: `.workspace` had `overflow:hidden`, which cancels `position:sticky`, so opening a step from the bottom of the page put the panel at the top, out of view. | P1 | Fixed: overflow removed; the panel now lands at 72 px from the top after a scroll of 555 px (measured). |
| 2 | Run page, side panel | Sticky offset of 16 px sat under the 56 px top bar, hiding the panel title. | P2 | Fixed: offset 72 px, height bounded to the viewport. |
| 3 | Live run, "Inspect individual steps" | The task brief repeated the selected task title word for word; a step node repeated the model's output that the node below already showed. | P1 | Fixed: brief hidden when identical; step nodes show status only. |
| 4 | Live run, workstream blocks | Blocks, header strip and progress read once; no repeated lines found by the repeated-line check at 1440 and 1024 px. | — | Verified. |
| 5 | Run report | Verdict rendered in mono instead of the serif prose of the rest of the report. | P2 | Fixed. |
| 6 | Run report | Header meta read "RUN FIXTURE- · 1 SETUPS": id cut at eight characters, plural without a count. | P2 | Fixed: twelve characters, counted plurals; same for the round header ("1 RUNS"). |
| 7 | Run report | With a single setup the first finding said "had the highest pass rate". | P2 | Fixed: one setup reads "passed 0 of 2". |
| 8 | Round report | The frozen-benchmark rule appeared three times: note under Standings, Excluded table, caveat. | P3 | Fixed: the note is gone; the table and the caveat remain. |
| 9 | Run page, Checks tab | "Observed" column broke words ("Obser ved", "Not record ed"). | P3 | Fixed: headers do not wrap, cells keep whole words. |
| 10 | Studio, list-first library | Opening the Studio while its data was still loading switched the screen back to the list after the user had already opened the editor (a race in the open wrapper). | P1 | Fixed: the wrapper only refreshes the list when the list is still showing. |
| 11 | Studio | A caught error "Cannot read properties of null (reading 'items')" toasted on every open: the Genesis library's `renderLibrary` shadowed the architecture library's function of the same name. | P1 | Fixed: renamed; the catch now logs to the console so the browser suite sees it. |
| 12 | Genesis, chat | Empty chat showed a large "G" emblem and the word Genesis, a chatbot placeholder. | P3 | Fixed: one sentence. |
| 13 | Budget | An empty usage table rendered its header row with no rows above the empty-state sentence. | P3 | Fixed: the sentence alone. |
| 14 | New run | The page heading drew a focus ring when focused by script. | P3 | Fixed: script-focused headings draw no ring. |
| 15 | Product graph, Graph view | Action keys wrapped mid-word in the card meta line. | P3 | Fixed: key moved to the card tooltip. |
| 16 | Product graph, Graph view | The draft bar (Save draft, Prepare version) showed above the live Monarch graph. | P3 | Fixed: hidden in the Graph view. |
| 17 | Runs table | Turns reads "unknown" for scripted setups, which have no model turns. | P3 | Fixed (pass 4): a dash. |
| 18 | Run page | Two headings stack: the page heading "Run outcomes" and the run title, with "Back to all runs" between them. | P3 | Fixed (pass 4): the run page has no separate page heading; the run title leads and the browser tab carries it. |
| 19 | Run report, cost figure | With every cost unknown or zero the log-cost scatter draws one point at the axis corner. | P3 | Fixed (pass 4): the figure is drawn only for setups with a settled cost above zero. |
| 20 | Runs table | Run titles are set in mono bold while every other title in the app is sans. | P3 | Fixed (pass 4): run titles in the UI face like every other title. |
| 21 | Report page | The right margin reserved for sidenotes is empty on every report today. | P3 | Fixed (pass 4): sections span the page; prose keeps its 68-character measure, figures and tables take the width, figures capped at 880 px. |
| 31 | Studio, Architectures list | "New architecture" opened the template menu, but choosing a template only set the draft; the list-first library never switched to the editor, so nothing appeared to happen. | P1 | Fixed: a chosen template opens the editor; a cancelled choice keeps the list. Browser check added. |

## Pass 2 — 9 Sep, late afternoon: the report through five readers

Lucas asked whether the report reads as a technical mess. Each sentence of the
run report was read as five people:

| Reader | What they need | What stopped them before this pass |
|---|---|---|
| Someone with no technical background, sent the link | Who was tested, who did better, is that good, and what the words mean | "95% interval 0–66%", "sign test p = 0.12", "pass^k", "Wilson", "Δ +20 points", "task matrix sorted by disagreement", "Caveats", "Method" |
| A go-to-market lead (Sam) | The one-line answer, the cost, how sure we are | The grade reason was a tally of wins and losses; cost sat in a table called "Unknown" and "Median time" |
| An engineer on Monarch (Deyton) | The method, the hashes, the judge, a link to every piece of evidence | Nothing missing; the Method table already carries it |
| A scientist (Lucas) | Intervals, the paired design, the test, pre-registration | Nothing missing, but the terms were never defined once |
| The program owner (Carlos) | The comparison against Bare in words, why it failed, what to fix next | "Not comparable" whenever Bare was not in the same run, even when an earlier run had recorded the same Bare |

What changed:

| # | Finding | Status |
|---|---|---|
| 22 | A run without a Bare setup was "Not comparable" even when an earlier finished run had recorded Bare with the same model, thinking setting and frozen tasks. | Fixed: the newest matching Bare run is reused as the baseline, never re-run; the header, the verdict and a caveat name that run and its date. `report_data.historical_baseline`, tested. |
| 23 | The interval was a bare "95% interval 0–66%". | Fixed: "If the same tasks ran again, its pass rate would most likely fall between 0% and 66%." |
| 24 | The sign test was "p = 0.12". | Fixed: "A gap this size would come up by chance about 12 times in 100"; under 1 in 100 and "as often as not" have their own sentences. |
| 25 | Grade reasons were tallies ("won 3, lost 1, tied 0 tasks against Bare"). | Fixed: "better than Bare on 3 tasks, worse on 1, the same on 0"; Tradeoff says which way the cost went. |
| 26 | "reported the work as done" and "failure category". | Fixed: "said the work was done when it was not"; "the most common reason for failing". |
| 27 | Section names "Caveats" and "Method". | Fixed: "What to keep in mind" and "How it was measured". |
| 28 | Terms were never defined: setup, Bare, task, attempt, pass, interval, paired comparison, grade, thinking setting, violation. | Fixed: a "Terms" section closes every report, ten entries, one sentence or two each. |
| 29 | Figure source lines and table headers used jargon: "Wilson intervals", "sorted by disagreement", "(log)", "Unknown", "Median time", "pass^2". | Fixed: "whiskers show the 95% interval", "tasks the setups disagree on come first", "(log scale)", "Unpriced attempts", "Typical time", "Passed all 2 times". |
| 30 | The caveat about repetitions mentioned pass^k and the consistency grid. | Fixed: "nothing here says how consistent a setup is from one try to the next". |

Still open from this reading: the Method table stays technical by design (it is
the engineer's and the scientist's section); the narrative paragraph, when a
run has one, is written by the analysis model and is not covered by this pass.

## Pass 3 — 9 Sep, evening: Genesis as an autonomous scientist (feature 019)

| # | Finding | Status |
|---|---|---|
| 32 | The board was a record: nothing happened unless someone typed in the chat. | Fixed: a drop box turns a link, a run id or a sentence into a card with a question; a watcher works queued cards one at a time under per-card and daily ceilings, never launching anything; every card shows Queued, Working, Done, Failed or the reason it waits. |
| 33 | At its first start the watcher backfilled a card for every historical run and source and spent the daily cap on four of them before anything useful happened. | Fixed: the watcher stamps when it first ran and only takes runs and sources that arrive after that; the backfilled cards were removed. |
| 34 | The per-card ceiling of US$ 0.50 could not cover one model request (the broker reserves the whole output bound), so every automatic turn failed with a budget error and no analysis. | Fixed: US$ 2.00 per card and US$ 6.00 per day by default; the daily tally counts settled receipts, not ceilings. |
| 35 | The board's columns were a fixed three-wide grid; cards could not move. | Fixed: columns scroll sideways, cards drag between stages and reorder, each stage a person may set has an inline add; moves that the server forbids (a dispatched card out of review, anything into Running) are refused before the drop. |
| 36 | Library topics were whatever text the source came with (a ledger's motivation sentence became a topic). | Fixed: one fixed list of eleven topics with Other last; a source is filed by its title first, then its text; Genesis or a person can move it; old free-text topics were migrated. |
| 37 | Genesis had no memory beyond the last eight exchanges and no idea what Monarch looked like today. | Fixed: LAB.md and MONARCH.md in every turn, notes per card, an FTS5 record, a nightly consolidation job, and a daily Monarch code index with read-only code tools; a Memory tab shows the files, their budgets and the daily jobs. |
| 38 | MONARCH.md was written by the code index into one folder and read by the memory from another, so the Memory tab showed it empty. | Fixed: one path. |
| 39 | Test suite on Windows | Deep evidence folders under pytest's temp root passed the 260-character path limit, so runs in tests failed with "file not found" or "name too long" depending on the test's name length; ten tests failed for this reason alone. | P1 | Fixed: evidence writes and the attempt journal use the Windows extended-path prefix past 230 characters, and pytest gets a short per-process temp root on Windows. |
| 40 | Evidence tree on Windows | The evidence path repeats the run id (`studio/<id>/evidence/<id>/episodes/...`) and, with a long setup name, reaches the 260-character limit even under `out/studio` on this machine; the worker's evidence upload walks that tree without the extended prefix and would miss deep files. | P2 | Open: shorten the tree (drop the repeated run id) in a change that keeps old runs readable, or walk with the prefix everywhere. Not a pre-registration change. |

## Pass 4 — 9 Sep, night: every view against the design direction

Method: every screenshot of the browser suite in both themes, then the live Studio with real cards and runs, read against `AI-LABS-STUDIO-DESIGN-DIRECTION-2026-09-09.md` (prose measure, figures full width, one component sheet, no duplication).

| # | Finding | Status |
|---|---|---|
| 41 | Report pages | Every section sat in the 68-character prose column, so charts and tables were half the page and the margin stayed empty. | Fixed: sections span the page; prose keeps its measure; figures and tables use the width. Closes 21. |
| 42 | Run report, cost | The log-scale cost figure drew a point at the axis corner for setups whose every attempt cost US$ 0.00. | Fixed: only settled costs above zero are drawn. Closes 19. |
| 43 | Run page | "Run outcomes" stacked above the run title with "Back to all runs" between them. | Fixed: no page heading on the run page; the browser tab shows the run title. Closes 18. |
| 44 | Runs table | Turns read "unknown" for scripted setups; titles were mono bold. | Fixed: a dash and the UI face. Closes 17 and 20. |
| 45 | Settings | Two hairlines stacked between Runtime capacity and Monarch Enterprise. | Fixed: one rule. |
| 46 | Live view | A collapsed block stretched to the height of the tallest expanded one, leaving a card of empty space. | Fixed: blocks keep their own height. |
| 47 | Genesis board | The empty state was a 170-pixel box at the left of an empty board. | Fixed: it spans the board. |
| 48 | Genesis board | A dropped sentence became both the card's title and its body, so every card read twice. | Fixed: the body is shown only when it says more than the title. |
| 49 | Genesis chat | Turns started by the watcher and the nightly job appeared in the conversation as if a person had typed them, and the next message chained off them. | Fixed: every turn records its purpose; the conversation shows only a person's turns. |
| 50 | Budget | Two empty charts held 250 pixels each to say nothing. | Fixed: an empty column chart is short. |
| 51 | Charts | Point labels on the cost scatter were struck through by the Pareto line. | Fixed: labels carry a halo in the surface colour. |
| 52 | Round report | "Excluded from the leaderboard" and "not the frozen 50-task benchmark" in a public report. | Fixed: "Not counted in the standings"; the caveat says "the frozen benchmark of 50 tasks". |
| 53 | Inspector, Checks | The record key under a check wrapped over four lines in the narrow first column. | Fixed: one truncated line with the full key on hover. |
| 54 | New run | The heading kept a green focus box after the page moved focus to it. | Fixed: the launch panel's focus rule skips script-focused headings. |
| 55 | Design system | Ten views re-declared input, select and text area styling with three heights, two border colours and three font sizes. | Fixed: views keep layout only; `ui.css` styles the controls once. |
| 56 | Budget, empty | Three sentences on one page say usage is empty (under each chart, the scope note, the table's empty state). | Open, P3: one sentence when the period is empty. |
| 57 | Launch | "Models" then "Add a model" stack as two labels for one field. | Open, P3. |
| 58 | Run overview | Failure-category bars alternated blue and amber, colours the design reserves for model families and warnings. | Fixed: the fail colour, as in the report. |
| 59 | Run page | The browser tab read "Your next run" until the page was reloaded. | Fixed: the tab title follows the run title. |

## Pass 5 — 9 Sep, night: the redesign

Lucas: "All the UI still looks like terrible AI slop, change the game." Web research (30 sources, `.tmp/research-ui.md`) found the incumbent system was the 2026 default itself: cream ground, serif display, sage and green, tracked mono labels. A front-end audit found 70 four-sided boxes, 16 card-in-card chains, 13 chip classes, 6 stat trios, 19 uppercase mono labels, a 10px radius leaking from `style.css` over the token, and global overrides in `analytics.css`. The direction is recorded in `docs/AI-LABS-STUDIO-DESIGN-SYSTEM-2026-09-09.md`.

| # | Finding | Status |
|---|---|---|
| 60 | Whole system | Sage, green and Plex Serif were the 2026 default; every screen read as generated. | Replaced: paper and ink, one signal red, Plex Sans and Mono, rules not boxes. |
| 61 | `style.css` | A `:root` block in the views layer set `--radius:10px` and a 16px root over the tokens, so nothing was square. | Removed. |
| 62 | `analytics.css` | Global rules put a radius on every element, an ink box behind the current nav item and a green hover on every primary button. | Removed. |
| 63 | `genesis.css` | Nineteen rules sat outside every layer and outranked everything. | Wrapped into the views layer. |
| 64 | Top bar | An ink bar with a green underline and green primary button. | A paper running head with one ink rule, the ledger line in mono, the current section in signal red. |
| 65 | Tables | Uppercase mono headers on a grey band. | Booktabs: ink rules above and below, hairline under sentence-case headers. |
| 66 | Status chips | Uppercase mono pills with tinted backgrounds. | A word with a square mark. |
| 67 | Panels | Seven of ten routes sat in a bordered box; Genesis columns, cards, the chat, the launch wizard, the studio and the budget were boxes in boxes. | All on the page, separated by rules. |
| 68 | Report | Mono uppercase section labels, a kicker above the title, a boxed grade. | Numbered sections, title first with a mono byline, the grade as a word with a mark. |
| 69 | Chrome in green | 100+ uses of the pass colour for selection, links, checkboxes and wires. | Chrome is ink; the current place is signal red; green means passed only. |
| 70 | Empty states | A dashed box around nothing. | One sentence in the measure. |
| 71 | Launch | Boxed choice tiles, numbered step circles, a white sticky footer, a green focus ring on the heading. | Ruled rows with a square mark, mono step numbers, a ruled footer, no ring. |
| 72 | Inspector | The checks table overflowed the side panel after the box went. | A rule and a gutter, fixed table layout. |
| 73 | Narrow screens | The running head overflowed by 51px at 390px. | It wraps: wordmark and actions, then the sections. |
| 74 | Stat trios | Four KPI rows in 22 to 30px. | Quiet mono values on a rule; the layout stays. Open, P3: fold into fact lists. |
| 75 | Type scale | 463 px font sizes across view sheets. | Open, P3: collapse onto the token scale. |
| 76 | Finish review | A fresh reviewer (the finish-review playbook, no build context) scored the redesign twice: 18 findings, then 11 resolved, 5 partial, 2 unresolved, 3 new; a last batch closed the stray square on the report verdict, the mono table headers, the metric row, the missing source lines and the switch on the title rule. | Reviews in `.impeccable/review/finish-review.md` and `finish-verdict.md`. Still open from them: the family-colour square before a model name in the Genesis chat, the loading text without a slot, the centred placeholder in an empty chart, the sticky head in one full-page fixture capture, and the wrapped step label at 390px. |

## Pass 6 — 9 Sep, late night: reports as text, Genesis with initiative, configuration journeys

Lucas: focus on the textual presentation of reports, a SOTA autonomous researcher that can run experiments himself, and the configuration journeys, with industry examples. Two research reports (`.tmp/research-genesis.md`, `.tmp/research-reports-config.md`) and the design of record `docs/superpowers/specs/2026-09-09-genesis-autonomy-reports-journeys-design.md`.

| # | Finding | Status |
|---|---|---|
| 77 | Genesis | It could only propose; every experiment waited for a person, and it stalled instead of asking. | Built: autonomy dials and a kill switch in code; smoke-scale plans launch by themselves within the per-card and daily allowances; question cards with a suggested default; an activity record with a tab; a stage track and plan lines on the card. |
| 78 | Report verdict | Five sentences, a bare percentage, the grade repeated in prose, the comparison buried. | Rewritten: outcome with count, rate and 95% CI; the harm sentence; the cost. Findings put harms first and end comparisons with a certainty word chosen by code. Method names the interval and its weakness. |
| 79 | New run | Buttons went grey with no reason; the footer said nothing about cost or approval. | The footer says attempts, smoke scale, ceiling and the week left; blocked steps print their reason; Review restates the ledger and the approval rule. |
| 80 | Run page | No way to repeat a run. | Run again opens New run with the same tasks and setups. |
| 81 | Browser suite | Six stale fixture servers sat on port 8766 answering with old code; a check failed on a route that existed. | The suite refuses a port that already answers, and names failing API urls in its errors. |
| 82 | Reports | Model-written narrative is not yet labelled with fact ids per sentence. | Open, P2. |
| 83 | Configuration | Task-set presets as a gallery, Set as baseline on product graph versions, a Test tab per node. | Open, P2, listed in the design of record. The budget sentence on Settings is built. |
| 84 | Genesis, second pass | A planned run's card stopped at Review with nothing written; the card showed no results; `[rec:...]` tags were plain text; the chat could not be about one card; the brief was a paragraph of ids; Genesis had no skills. | Built: the post-run debrief re-queues the card for its verdict; results from the grader on the card with a link to the report; rec chips open their record; card-scoped chat; the brief as a fact list with links; skills with a prompt injection by kind and an editor on the Memory tab. |

## Pass 7 — 10 Sep, morning: the operating views

Lucas: "Other features could look better and need a revamp just like you did." Research on runs lists, run detail, usage pages, settings and catalog browsers in `.tmp/research-views.md` (GitHub Actions, Vercel, Linear, W&B, Braintrust, LangSmith, Inspect, OpenAI and Anthropic usage, AWS Cost Explorer, Railway, Postman, Backstage, Stoplight). A fresh reviewer read the snapshots afterwards.

| # | Finding | Status |
|---|---|---|
| 85 | Runs | Three dropdowns and three boxed buttons over a table; a pager for three rows; no path from a run to its report. | One search field, status and track as text filters, sort as a small select; runs grouped under day rows with counts; the row names its setups and task count; Passed carries a square; a Report link at the right edge for finished runs; the pager appears only past one page; Refresh and Export as text at the foot. |
| 86 | Run Overview | Six outcome cards for three tasks, a percent bar for one failure category, "What happened" repeated. | A task-by-setup matrix (rows tasks, columns setups, cells a square and a word with the finding under a failure, passes per setup in the foot) that opens the inspector on the checks; "Where it failed" as a ruled list of counts that filter the attempts; the reasoning review with its state in mono. |
| 87 | Activity | A boxed "Task brief ——— Agent" diagram in every block and a red sentence hanging under it. | Blocks read as a log: square, setup, task, output, a knowledge line only when knowledge was attached, the verdict as one word. |
| 88 | Budget | Three empty notices for one fact; no ledger although the weekly ledger is the reason the page exists. | The sentence, five facts in the label column, then the week's Ledger (when, what, who, ceiling, settled, requests, state) from a new read-only `GET /api/budget/ledger`, then Usage by model with the period as text filters and one line when there is nothing. |
| 89 | Settings | Capacity facts only; nothing said which provider keys exist or what Monarch is pinned to. | Sections Budget, Capacity, Providers (key present or not, never the value, with the .env name to add), Genesis (a link to the dials), Monarch Enterprise (source commit and verification state as facts). Provider limits and components stay under Advanced. |
| 90 | Studio | "Architecture studio" with two New architecture buttons on an empty list; nothing about what an architecture is used in. | "Studio"; an empty state that says what an architecture or a product graph is, with one action; rows show the latest version, Used in N runs with the last date, and a Run action for a published version. |
| 91 | Chart kit matrix | Pass and fail cells were filled colour blocks. | A square and a word, as everywhere else. |
| 92 | Review, 10 Sep morning | A fresh reviewer read the six views and said fix: the Studio nav item went grey while its list loaded (the button is disabled during the fetch and the base rule dims disabled buttons); Monarch Enterprise painted empty until its fetch resolved; "No key" in red; middots in the provider rows and the activity heads; the run title off the grid at 18px; instruction sentences under the matrix and the failure list; the full budget sentence repeated on Settings; Draft and Versions tabs on the live graph; three alignments on the usage toolbar; a duplicated square in the checks table. | All applied: nav buttons keep their colour while busy; Monarch facts in the HTML at once; key presence as an ink or amber square with the note beside it; activity heads in sans; the run title at 34px on the margin; the sentences cut; Settings shows one budget line with a link to the ledger; the live graph hides Draft and Versions; period filters beside Refresh; one mark per checks row; the failure rows carry the evidence line, not the prompt. |
| 93 | Mobile | The Runs page overflowed by 408px at 390px wide: the table's screen-reader caption is positioned absolutely and escaped the scroll container's clip, widening the page. | `.table-scroll` is positioned, so absolutely positioned descendants clip with it. All five revamped views measure zero overflow at 390px. |
| 94 | Attempt detail | Lucas: the inspector was "a weird right drawer". It squeezed the page to a 440px column, reflowed the matrix, truncated the checks, needed an Expand button to become the dialog it should have been, and opened a second dialog for an event. | The attempt is a sheet over the matrix (Inspect AI's sample dialog, Braintrust's trace panel): verdict, task, setup, the four tabs, previous and next attempt with j and k, Copy, Esc; a trace event opens inside the sheet with Back; the route carries the open attempt (`#run/<id>/<task>/<setup>`) so it can be linked; full screen at phone width. The side column and Expand are gone. |
| 95 | Audit, 10 Sep | Lucas: "this is the sort of analysis I want you to be running for all features"; four auditors compared every feature with named products (`docs/AI-LABS-DESIGN-AUDIT-2026-09-10.md`, 57 findings). | Built the same day: the attempt as a side sheet that keeps the matrix (current cell marked, one home for every event, master and detail on Trace, Back closes it, the event in the address); the grade gated by the sign test and standings ranked by interval; reports with a contents list, section addresses, audience in the address, a clean single-file export with its fonts, charts drawn again at the column width with SVG and CSV downloads and a hidden data table; New run as one page with an expected cost, numbered names and reasons beside every choice a person cannot take; templates that start on a keyed provider; Genesis with Approve up to $X and Decline, a Needs you strip, one status line and one Pause, Work now, a card sheet with its own composer, the dials under Settings, pinned facts with Unpin, search-first Library; Runs with a period filter, Run again per row and keys; Budget on the ledger week. Open items in the audit file. |
| 96 | Genesis, feature 022 lane B, phase 1 | Handed over by the ModDev_Scheduler session on Lucas's instruction (design of record `docs/superpowers/specs/2026-09-10-genesis-team-scientist-design.md`, brief `.tmp/genesis-lane-b-brief.md`). | Built: chat first in three columns (rail with the person's conversations and the views, the conversation at the measure, the tracking pane with Cards, Sources and Trace); threads per person (`genesis/threads/`, `GET /api/genesis/threads[/<id>]`); one stage vocabulary (Research, Hypothesis, Plan, Running, Review, Done); live tool steps above the answer from the turn's events; the card as a document in the pane with history (`GET /api/genesis/cards/<id>/history`); the inbox count on Board; "Stopped: <reason>" with the recovery. Receipt `.tmp/genesis-lane-b-receipt.md`. Then, with Lucas's authorisation, `marked` 18.0.12 vendored and wired behind a whitelist sanitizer. Phase 2, after Lucas's "Proceed": people and keys (`genesis_access.py`, `genesis/people.json`, `X-Person-Key` beside the Studio token, `by: human:<name>` on every write, admin-only writes for config, autonomy, settings, people and skills), the configuration page under Settings › Genesis (models per step, the weekly envelope with what is left, the dials and Pause, skills, people with keys shown once, channels' presence, jobs with Run now; Memory keeps what last night changed and the track record), the digest page `#genesis/digest` in the report style, the library's extracted columns, the patch download. Also deduplicated the definitions and routes that patch reruns had appended, and the runs page's Period filter that a rerun had left four times. |
| 97 | Open | Filters in the URL, a Compare selection across runs on the same task set, a daily spend chart, a Reconcile action per week, an About section with the declared build. | Open, P2, from the research rules; none needed for the fixture data. |

## How to run the pass again

```bash
cd monarch-benchmark/workflowbench && set -a && . ./.env && set +a && uv run python tests/browser/server.py --port 8790 --keep --live
```

```bash
node .tmp/qa.cjs http://127.0.0.1:8790
```

Screenshots land in `.tmp/qa/`; `notes.json` holds the measurements. Stale
fixture servers answer with old code and hold the port: kill every Python
listener on ports 8766 to 8799 before a pass.
