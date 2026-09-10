# AI Labs Studio: interaction audit against named products, 10 Sep 2026

Lucas, 10 Sep, on the attempt inspector: "Why is this view not a pop up
instead of a weird right drawer? This is the sort of analysis I want you to be
running for all features. Use web research to compare every feature to see
what you are doing that is just bad design."

Four auditors read the fixture Studio at 1440 and 390 pixels wide, drove it
with Playwright, read the code, and compared each feature with named products
whose documentation they fetched. Their reports are in `.tmp/audit-run-detail.md`,
`.tmp/audit-reports.md`, `.tmp/audit-config.md` and `.tmp/audit-genesis.md`
(git-ignored; the substance is here). This file records every finding, what was
built for it the same day, and what stays open. The ledger
(`AI-LABS-IMPROVEMENT-LEDGER-2026-09-09.md`, pass 8) carries the same items
by number.

## The one rule that came out of it

A feature is judged by the reader's next question, not by its chrome. For
every surface the auditors asked: what does the person need to see while they
answer it, and where does the industry put that. The recurring answers:

- A table peeks to the side and keeps the table in view (Notion, Langfuse,
  LangSmith). A centred modal hides the map.
- One home per kind of evidence (Sentry, Langfuse). Two dialogs for one event
  is a bug.
- Every address is a link (GOV.UK, HELM, W&B). A report or an attempt that
  cannot be cited is not finished.
- A grade carries the same certainty as the sentence beside it (Arena, SEAL,
  Nature).
- Choices you cannot take say why where they are (Zapier, Retool), and a form
  that fits one page is one page (GitHub's Run workflow, Postman's runner).
- The agent's state is one line, one switch, one composer (Claude Code on the
  web, Cursor, Devin).

## Run detail

Compared with Inspect AI, Braintrust, LangSmith, Langfuse, Sentry, GitHub
Actions, Vercel, Notion and Linear.

| # | Finding | Done today | Open |
|---|---|---|---|
| 1 | The attempt opened over a dimmed matrix; the page underneath was locked. | The attempt is a sheet fixed at the right edge, no scrim, the page keeps its map and gives the sheet its width above 1100 px; the current cell and results row are marked in the signal colour. | |
| 2 | Three surfaces for one kind of evidence (sheet, lane node, a second dialog for events). | An event has one home: the attempt sheet on Trace with the event selected. Evidence links under Where it failed and in the reasoning review open it there. | The lanes graph still exists behind "Inspect individual steps". |
| 3 | Opening an event threw the trace away. | Master and detail inside Trace: the list at two fifths, the event beside it, up and down move the selection. | |
| 4 | Nothing below the attempt could be linked. | `#run/<id>/<task>/<setup>/e<event>` names the event and is restored on load; a Copy link control and the `.` key; Copy copies the tab that is shown. | Check rows have no address. |
| 5 | No full page for an attempt. | | Open: an "Open as page" route for long records. |
| 6 | Browser Back left the run. | The first open pushes history, stepping replaces it, Back closes the sheet. | |
| 7 | Activity hid failures once the run was over. | Failed blocks stay open with the failed check named; passed blocks fold to a line; Inspect task opens the sheet on Trace. | |
| 8 | The lanes graph drew a list as a flowchart. | | Open, large: replace with the trace list per competitor. |
| 9 | The timeline clipped labels and ran the axis to one second. | The axis ends where the attempt ends; a 200 px label gutter with a middle ellipsis and the full text on hover. | |
| 10 | The failure list led with a passed check; a passed attempt spoke of failure. | The row carries the harm line (the change outside scope) or the failed check; the unreviewed state reads "Not reviewed yet". | |
| 11 | The header said almost nothing about the run; Cancel had no confirmation. | A facts line under the title: started, duration, cost, tasks, setups, ceiling, operator, world; Cancel asks first. | |
| 12 | Results did not scale. | Outcome filters (All, Failed, Execution issues, Passed) and a Finding column; rows mark the current attempt. | Sorting. |
| 13 | 390 px broke the sheet and the tables. | Full-screen sheet, two-line title, results as stacked rows. | Lanes at phone width. |
| 14 | Keys were half bound. | Up and down or j and k move the attempt; left and right belong to the tabs; `.` copies the link; Esc closes. | `?` listing the keys. |

## Reports

Compared with HELM, LMArena, Epoch AI, Artificial Analysis, Scale SEAL,
Braintrust, Weights & Biases, Observable, Datawrapper, GOV.UK statistics,
Nature and JAMA figure standards.

| # | Finding | Done today | Open |
|---|---|---|---|
| 1 | The grade said Improvement while the sentence said the run cannot tell them apart. | Improvement and Regression need the sign test below 0.05; otherwise the grade is Undecided with the tally and the p value in its reason. | |
| 2 | Standings ranked by point estimate; intervals were decoration. | Rank is one plus the number of setups whose whole interval sits above; a spread ("1 to 3") when intervals overlap, with the rule stated under the table. | |
| 3 | Nothing in a report could be linked or cited. | Routes `#report/<id>/<section>` and `#round/<id>/<section>`; a contents list under the header; section headings carry their address; runs and rounds are links; the page is titled by the report. | Anchors per matrix row. |
| 4 | The single-file export kept dead buttons and lost its fonts. | The export clones the article, drops the actions, turns buttons into text, and carries the fonts as data URLs. | |
| 5 | At phone width the page overflowed and charts shrank to illegibility. | Every table scrolls; each row chart is drawn again at the width of its column with a shorter label gutter. | |
| 6 | The round had no date and listed its only run as "not counted". | The title carries the task count and the date span; the exclusion table appears only on a benchmark round; the runs sit under Method. | |
| 7 | "Analysis pending" was permanent and model prose sat inside the verdict. | Nothing when nothing is planned, "Analysis due" when dispatched, a Model reading section after Findings when complete; model findings in their own list. | |
| 8 | The index led with a grade that was empty for most rounds. | A grade only when a Bare exists, else the pass sentence; benchmark rounds apart from other task sets; the Latest column and "completed" gone. | |
| 9 | The audience toggle was invisible state. | `?audience=internal` in the address; the scroll position kept; the internal band names the lab setups shown only there. | |
| 10 | Evidence links were buttons named by section. | Anchors with an address and a plain name ("See the failures table"); the target row lights for two seconds. | |
| 11 | Cost was rounded away and "unknown" stood for "no passes". | Three significant figures below a dollar; "no passes" when nothing passed. | |
| 12 | Figures could not be taken away or read by assistive technology. | Every figure carries Download SVG, Download CSV and a hidden data table. | Colliding scatter labels. |
| 13 | Findings restated the verdict. | A finding whose subject and kind the verdict already covers is dropped. | |
| 14 | Reading order and glossary. | The title precedes the meta line in the markup; terms fold away and list only the ones the report uses. | |

## Configuration: New run, Studio, product graphs, Settings

Compared with n8n, Dify, Langflow, Flowise, Zapier, Retool, Postman, GitHub
Actions, Vercel, Linear, Airtable, Notion, Stoplight, Swagger UI, BigQuery.

| # | Finding | Done today | Open |
|---|---|---|---|
| 1 | Escape anywhere in New run threw the page away. | Escape closes dialogs only; a restored draft says so and offers Start over. | |
| 2 | Three steps for a form that fits one page; blockers appeared only after Next. | One page with three sections and a sticky footer; the numbers scroll; Start run is always in reach; Run again lands on Start. | |
| 3 | Every template published a version that could not run. | Templates start on a provider with a key; keyless providers are disabled in the picker with "no key (Settings)". | Publish still allowed for definitions. |
| 4 | Nothing could be tried without paying. | | Open, large: "Test on one task" with the answer key at no cost. |
| 5 | Side effects and prompts in the wrong order. | Problems are checked before the name is asked; an empty field path is refused before any modal. | |
| 6 | The spend ceiling was a guess. | "Expected about $X from N earlier attempts" from the stored results of the same models; the default ceiling is twice that, clamped to the week. | Rate-card estimate when there is no history. |
| 7 | Review said the same thing four times. | The rule paragraph is gone; the footer keeps the sum; concurrency clamps to the host. | |
| 8 | Default run names collided. | "<setups> on <n> tasks #N". | |
| 9 | Choices you cannot take were offered. | Bare is disabled with the reason beside it; presets say the set is not on this host; keyless models say so in the list. | |
| 10 | The task catalog was a checkbox list. | A table: task, category, applications, difficulty, past runs. | Sorting and grouping. |
| 11 | The editor at 390 px was a miniature. | | Open: a vertical step list below 700 px. |
| 12 | The live graph showed raw config strings. | A sentence naming the variable and a link to Settings. | An action detail pane. |
| 13 | The fields table. | The path is checked where it is typed. | Reordering. |
| 14 | Settings was a fact sheet. | Verify is remembered with its time; the missing key names copy as .env lines. | Real controls where the server allows. |
| 15 | The version's primary action hid under More; expanded mode collided with the app bar. | Run latest version sits with Save and Publish; expanded mode hides the running head. | |

## Genesis, Runs and Budget

Compared with Linear, Trello, Notion, Asana, Devin, OpenHands, Cursor, Claude
Code on the web, ChatGPT, Claude.ai, Perplexity, Elicit, Consensus, Zotero,
Readwise, Obsidian, Anthropic and OpenAI usage pages, GitHub Actions, Vercel.

| # | Finding | Done today | Open |
|---|---|---|---|
| 1 | Approval had no decline and did not say what it spent. | "Approve, up to $X", Decline with a reason kept on the card, Ask for changes; the card stays open and names the run. | |
| 2 | Half the pipeline was off screen. | Six columns share the width; an empty column folds to its name. | A list layout. |
| 3 | Opening a card appended a page under the board. | The card is a sheet with previous and next, j and k, Esc. | |
| 4 | Genesis's state was not legible and could not be nudged. | One status line in the heading with the next wake, the day's spend and one Pause, the kill switch; Work now on a queued card. | |
| 5 | Three vocabularies for one stage; questions under the wrong heading. | One word list everywhere; questions file under Needs you. | |
| 6 | Four ways to add a card, two behaviours. | One composer with "Genesis works it" on by default; Add hypothesis is gone. | |
| 7 | The chat spent silently, could not be stopped, offered models that do not work. | A cost line under the composer; Stop while a turn runs; only routes with a key, once each, provider named; Thinking hidden when there is one level. | Turn history by day. |
| 8 | Questions had no inbox. | "Needs you" strip above the board with the answer prefilled; a count on the Genesis item in the running head. | |
| 9 | The Memory tab hid the most consequential setting. | Autonomy dials live under Settings, Genesis; pinned facts as a list with Unpin; skills fold; record hits as chips. | |
| 10 | The Library led with six filters and no search. | Search first; filters fold; the empty state names the two ways in. | |
| 11 | At 390 px the page opened on an empty chat. | Board first; the chat behind Ask Genesis as a bottom sheet; runs as stacked rows. | |
| 12 | Budget said every number twice and kept two clocks. | The facts list is gone; usage defaults to the ledger week; a person's chat turn is attributed to the Studio user; the chip refreshes after a reservation. | |
| 13 | Runs: an empty column, no row action, a CSV that did not match. | Turns hides when no run recorded any; a period filter; Run again per row; the CSV is the table; j, k and Enter. | |
| 14 | Activity was a raw log. | Plain words, a search, a kind filter, the turns' cost. | |

## Still open, in order of value

1. A free "Test on one task" with the answer key, for architectures and product graphs.
2. The lanes graph replaced by the trace list per competitor.
3. An "Open as page" route for an attempt.
4. The editor as a step list at phone width.
5. An action detail pane in the live graph.
6. A list layout for the board.
