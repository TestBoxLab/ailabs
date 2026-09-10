# Round: Gauntlet, workflow track (`achievable-50-workflow`)

Plan `config/plans/achievable-50-workflow.yaml` · product `simulated-apps` · unblock plan
of 8 Sep 2026, milestone M2 · prepared 8 Sep 2026. Status: **task set listed (50 ids) and
checked against the corpus, not frozen yet: `wb corpus slate` refuses because two of the
ids already sit in frozen tier sets (Lucas decides, see the blockers); re-freeze pending
the evalrepair.10 import (M1); Monarch harness files pending M5.** Every number here comes
from the plan file; the task list comes from `tasks/achievable-50-ids.txt`.

## What this round is

The gauntlet of the unblock plan (decisions D1 and D3) on the **workflow track, creation
plus execution**: Monarch builds a workflow for each request and runs it (`mode:
create-run`, `track: create-run`). Three selectable competitors beside the answer key:
**bare** Claude Opus 5 through the API tool loop (the baseline: no Monarch, nothing
else), **stock Monarch** (what it runs today), and **Lucas's lab version** (the same build
with the reconstructed reviewed product knowledge, the PG-Waki graph version, seeded).
Both Monarch instances run Opus 5 through the Anthropic API on Railway (D2, D7, D8). The
one-off request track is a separate round (`achievable-50-request`), on the same 50
tasks; results are never pooled across the two.

The question the round answers is pre-registered in
`research/experiments/EXP-2026-002-gauntlet-workflow/preregistration.md`: does the lab
version beat bare Opus 5 by at least 5 percentage points of strict pass rate, paired by
task? The secondary comparisons (stock against bare; lab against stock) are exploratory.

How Monarch is driven on this track: the create + run path the bench already has
(`wb_arms/monarch.py`: authoring through Monarch's API, then one run of the authored
workflow, its cost from the tracing service). A workflow that needs input from a person
stops before the run and is a failed attempt (needs_input), for both instances alike. What
the bare arm does differently from the one-off track (authoring a reusable workflow before
acting) is set by its harness when the track lands in code (M4); today the plan's `track`
field keeps the two rounds apart in the config hash and the reports.

## How the task set is chosen

The same set as the one-off request round, chosen the same way: the ApplicationBench
**achievable50** slate (the achievable universe of 595 tasks sorted by id, every 595/50-th
task; 50 tasks, eight or nine per scored domain, no `simple.*` task), listed with its rule
and source in `tasks/achievable-50-ids.txt` and frozen by `wb corpus slate` into
`tasks/achievable-50/` with `tasks/achievable-50-manifest.yaml`. See
`achievable-50-request.md`, "How the task set is chosen", for the freeze, the check of
8 Sep 2026 (all 50 in the corpus with rules and matching hashes; two already in frozen tier
sets: `operations.docusign_prospect_nda` in `tier-complex`,
`support.reamaze_cross_platform_dedup` in `random-10`), the difficulty breakdown (simple 7,
medium 22, complex 21 on the legacy measure with cut points 10 and 15) and the revision
note (corpus at 1.0.6 `4a8e106`; re-freeze after the evalrepair.10 import, M1). The two
rounds run the same frozen folder, so a change to the set is a change to both.

## Competitors

| Competitor | Harness | Provider and model id | Price, US$ per million tokens (input / cached / output) |
|---|---|---|---|
| `oracle` (answer key) | scripted | none | 0 |
| `claude-opus-5/api` (baseline) | API tool loop | Anthropic, `claude-opus-5` | 5.00 / 0.50 / 25.00 |
| `monarch-stock@<commit>` | Monarch, create + run; harness file pending M5 | Monarch on Railway, stock, Opus 5 through the Anthropic API | Opus 5 at Anthropic rates, 5.00 / 0.50 / 25.00; the price table is named in the harness file |
| `monarch-lab@<commit>+<graph hash>` | Monarch, create + run; harness file pending M5 | Monarch on Railway, the same build, the reconstructed reviewed product knowledge seeded (M6) | the same |

`claude-opus-5/claude-code` (Claude Code in a container, the second bare arm) joins when
its container passes the isolation checks (M7, D10).

## Size, time and money (per round)

| Item | Value |
|---|---|
| Prompts (tasks) | 50 |
| Attempts per prompt, for each competitor | 1, plus 1 retry if the first attempt fails (`retry_on_fail: 1`) |
| Attempts per competitor | 50 to 100 = 50 prompts × (1 + up to 1 retry) |
| Attempts in total | 200 to 400 = 4 competitors × 50 to 100, of which up to 300 paid |
| Timeout per attempt | 1800 s (authoring and run together) |
| Cost ceiling in the plan | US$ 220, reserved in the weekly ledger before the first attempt |
| Cost band | bare US$ 4 to 26 (US$ 0.07 to 0.26 per attempt); each Monarch instance US$ 75 to 150 (about US$ 1.50 per attempt, 50 to 100 attempts; authoring adds a little); total US$ 155 to 330 |
| Fit to the ceiling | the top of the band is above the ceiling, and two Monarch arms with retries are above the US$ 300 week; the levers are the retry budget (`retry_on_fail: 0` halves the band) and one track per week, set before launch (the plan calendar puts this track in the week of 29 Sep 2026, after the one-off round) |
| Approval | `approved_by` empty. Lucas approves (D5): his own launches run at once; a launch by Carlos creates an approval request and waits for his approval |

## Blockers before the round

1. **The freeze.** Two of the 50 ids sit in frozen tier sets (above). Lucas decides:
   freeze with `--allow-frozen-overlap`, which records the overlap in the manifest (the
   tier rounds have not run); or drop the two ids, after which the set is no longer the
   achievable50 record; or change the rule. Nothing is frozen until then.
2. **M1.** Re-import the corpus under 1.0.6+evalrepair.10, re-freeze the set, re-check
   the 50 approval rules.
3. **M3.** Paid dispatch and the approval flow: today `wb run` refuses every paid
   competitor, and `approved_by` is a string checked at resolve, not the approval record
   of D5.
4. **M5 and M6.** The two Monarch instances on Railway, their harness files
   (`config/harnesses/monarch-stock.yaml`, `monarch-lab.yaml`), `wb monarch setup
   --instance stock|lab` (the knowledge-base hashes per instance, drift refusal before the
   round), verification, and the graph version imported into the lab instance; until the
   artifact behind the 67 % result is tied to a file and a run record, the lab version is
   labelled "reconstructed".
5. **Pre-registration frozen** (EXP-2026-002) and its Trello card, before launch.

## Task set and requests

The same 50 tasks and request texts as the one-off request round: see
`achievable-50-request.md`, "Task set and requests" (listed from the corpus at revision
1.0.6 `4a8e106`, the files the freeze copies byte for byte). Per domain: finance 9, hr 8,
marketing 8, operations 9, sales 8, support 8. Per tier on the legacy measure: simple 7,
medium 22, complex 21. On this track Monarch is asked to build a workflow from the same
request text, byte for byte, that the bare model receives.
