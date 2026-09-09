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
| 17 | Runs table | Turns reads "unknown" for scripted setups, which have no model turns. | P3 | Open: honest but noisy; a dash for scripted setups would read better. |
| 18 | Run page | Two headings stack: the page heading "Run outcomes" and the run title, with "Back to all runs" between them. | P3 | Open: the page heading could carry the run title. |
| 19 | Run report, cost figure | With every cost unknown or zero the log-cost scatter draws one point at the axis corner. | P3 | Open: skip the figure when no setup has a settled cost. |
| 20 | Runs table | Run titles are set in mono bold while every other title in the app is sans. | P3 | Open: design choice to revisit with the tokens. |
| 21 | Report page | The right margin reserved for sidenotes is empty on every report today. | P3 | Open: sidenotes are not written yet; the measure can widen until they are. |
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
