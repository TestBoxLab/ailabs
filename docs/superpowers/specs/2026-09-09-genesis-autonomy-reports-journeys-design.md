# Genesis as an autonomous researcher, report prose, configuration journeys — design of record

Date: 9 September 2026, night. Feature 021. Requested by Lucas: "a SOTA autonomous
researcher and Hermes-like assistant that can run experiments himself", superb
reading of reports, proper user journeys for configuration, with industry examples.
Research: `.tmp/research-genesis.md` (about 90 sources) and
`.tmp/research-reports-config.md` (about 60 sources). Visual system:
`docs/AI-LABS-STUDIO-DESIGN-SYSTEM-2026-09-09.md`.

Fixed rules this design respects (`PLAN.md` §1, constitution §III, decision D5):
nothing grades itself; Lucas approves paid rounds; a launch at smoke scale (at most
20 attempts per competitor) needs no approval record; every paid request is reserved
in the weekly ledger before it is sent; task prompts, data and rules are frozen.

## Part 1. Genesis

### What "Hermes-like" means here

Nous Research's Hermes Agent (2026): agent-curated persistent memory, self-written
skills, cron-driven initiative, a `SOUL.md` voice. Genesis already had the memory,
the identity file and a nightly job. It now has initiative within bounds (it runs
experiments at smoke scale by itself), questions (it asks instead of stalling), and
a record of everything it did.

### Autonomy: three dials and a switch

Set on the Memory tab above the identity file, stored in `genesis/autonomy.json`,
changed only by a person, every change in the activity record.

| Dial | Levels | Default |
|---|---|---|
| Reading (library, runs, evidence, code) | always on | on |
| Cards (create, move, write notes and verdicts) | act and report · off | act and report |
| Runs | smoke scale by itself · propose only · off | smoke scale |

Runs at *smoke scale*: Genesis launches a plan itself when it has at most 20
attempts per competitor (`SMOKE_SCALE_ATTEMPTS`), its ceiling fits the per-card
ceiling (`STUDIO_GENESIS_CARD_USD`) and the day's remaining allowance
(`STUDIO_GENESIS_DAILY_USD`), and the ledger can reserve it. Anything larger, or any
plan when the dial says *propose only*, waits in Approval for a person, as before.
*Pause everything* is the kill switch: the watcher stops and every Genesis launch is
refused until a person turns it back on (stop and revoke, not just stop). All three
limits are code (`wb_studio/genesis_autonomy.py`), not prompt text.

Taxonomy: Feng et al.'s levels of agent autonomy (operator to observer); "human on
the loop" for bounded runs; "a limit in the prompt is a preference; a hard limit is
code".

### The experiment card, six stages on the board that exists

The card's detail shows a stage track: Research → Hypothesis → Plan → Running →
Review → Complete, the current stage in signal red.

1. **Research** (queued): a dropped link, run id or sentence with its question.
2. **Hypothesis**: directional, with a minimum effect (a Registered Report stage 1).
   When Genesis cannot write it, it files a question card instead (the Deep
   Research clarify step).
3. **Plan**: `propose_experiment` takes a Studio launch payload; the Studio computes
   the lines a person can check (tasks, competitors, attempts per competitor and in
   all, the ceiling, the track). Genesis writes none of the numbers.
4. **Running**: a smoke plan launches at once; the card shows who launched it and
   the run id. A larger plan waits in Approval with the reason it waits (Devin's
   Wait for approval).
5. **Review**: the grader's results, never Genesis's; Genesis writes the verdict on
   the card with every sentence tagged `[rec:...]`.
6. **Complete**.

### Question cards

`ask_question` files a card of kind `question` in *Your review*: one question, a
suggested default, the card it blocks. The blocked card waits; the turn that asked
ends without marking it done. A person answers with one click on the default or
writes another answer; the blocked card is re-queued with the answer appended and
Genesis resumes it on the next wake. Questions are free: no model turn is spent to
ask or to answer.

### Activity record

`genesis/activity.jsonl`, one JSON line per entry: cards created and moved, turns
started and finished with their cost, plans, launches (by whom), plans waiting and
why, questions and answers, autonomy changes. Shown on the Activity tab, newest
first, every entry linking its card; the file is the export.

### Chat and board

The board is the workspace; the chat is the control channel. Turns started by the
watcher or the nightly job carry a purpose and stay out of the conversation.

### Five patterns borrowed

1. Clarify before spending (OpenAI Deep Research).
2. Plan with checkable lines and Wait for approval (Devin).
3. A permanent record from every result (GitHub Copilot coding agent's log link).
4. Requester cannot approve; the agent is a delegate, a person stays owner (GitHub
   Copilot, Linear): a launch is recorded with `by`, `genesis:smoke` or a person.
5. Ranked hypotheses before a run is proposed (Google AI co-scientist): deferred
   until more than one hypothesis competes for the same allowance.

### Second pass (Lucas: "you can do better")

- **The loop closes by itself.** When a run Genesis planned finishes, the card
  moves to Review and is re-queued with the question "write the verdict", so
  hypothesis → plan → run → verdict needs no person unless a plan is above
  smoke scale or a question is open. Recorded as `debrief`.
- **The card is an experiment document.** Stage track; the plan lines; the
  grader's results read from the run report (passed of attempts, rate, 95% CI,
  cost per attempt, the grade) with a link to the report; the verdict with
  every `[rec:...]` tag rendered as a chip that opens the record; the
  conversation about this card; a next action on the board card ("Answer",
  "Approve or decline", "Read the verdict").
- **The chat is scoped to a card on request.** "Ask Genesis about this card"
  puts the card in scope; the conversation shows that card's turns; the
  message carries the card so the answer lands on it.
- **Skills** (`wb_studio/genesis_skills.py`): procedures Genesis writes for
  itself, at most twelve of 4,000 characters, first line "Applies: run,
  hypothesis, source, question, verdict or always"; the matching ones enter
  the prompt after the core memory; a person edits them on the Memory tab
  (Hermes Agent's self-written skills).
- **The daily brief is data.** The nightly job files what ran, what moved,
  questions waiting, plans waiting and the allowance as a fact list, each item
  a link, beside its sentence.
- **Reports** name the register: findings written by the analysis model are
  labelled "Genesis, from the record" or "Genesis, a reading", with a note that
  their numbers come from the record.
- **Settings** opens with the budget sentence: left of the week, reserved,
  settled, the reset instant.

### Code

- `wb_studio/genesis_skills.py`: `Skills` (listing, read, write, remove,
  prompt_block); tools `skill_list`, `skill_read`, `skill_write`,
  `skill_remove`; routes `GET /api/genesis/skills[/<name>]`, `POST /api/genesis/skills`.
- `wb_studio/genesis_autonomy.py`: `Autonomy` (read, set, may_launch, record, tail)
  and `plan_lines(studio, proposal)`.
- `wb_studio/genesis.py`: `propose_experiment`, `ask_question`, `answer_question`,
  `_dispatch` (one launch path, used by a person's approval and by a smoke launch),
  `autonomy_words` in the work prompt; every state change recorded.
- `wb_studio/genesis_watcher.py`: honours the switch.
- Routes: `GET/POST /api/genesis/autonomy`, `GET /api/genesis/activity?limit=&card=`,
  `POST /api/genesis/cards/<id>/answer`.
- UI (`genesis.js`, `genesis.css`, `index.html`): the autonomy block, the Activity
  tab, the stage track, the plan block, the question block, question cards on the
  board with their suggested answer.
- Tests: `tests/test_studio_autonomy.py` (9), the watcher and Genesis suites updated.

## Part 2. Report prose

Sources: CONSORT and STROBE for the number, APA for the interval, the Cochrane
plain-language certainty words, GOV.UK's analysis-function writing rules, the
GPT-5 and Gemini system cards for method and scope caveats, Evaluation Cards
(arXiv 2606.09809) for provenance, Minto and Nielsen Norman for order.

Rules now in code (`wb_studio/report_data.py`, `reports.js`):

1. Every pass rate is count, rate and interval in one clause: "6 of 10 tasks
   (60%, 95% CI 31 to 83)". Never a bare percentage.
2. The verdict is three sentences: the outcome with its interval (and the
   baseline's), what changed that should not have or that nothing did, the
   cost. A reused Bare baseline adds one sentence naming the run it came from.
   The grade stays on the grade line, not in the prose.
3. Harms first: a competitor that changed something outside the task is finding
   number one; otherwise the verdict says it changed nothing outside the task.
4. Certainty words are a closed set chosen by code from the sign test:
   "probably passes more", "may pass more", "cannot tell them apart". The model
   never chooses the word.
5. Method names the interval once with its weakness: Wilson score, 95%, on
   attempts; it does not include task-selection variance.
6. Every figure and table carries a source line: run or task set, what the
   numbers are.
7. Caveats stay code-written, scope then consequence. No recommendations in the
   public report.
8. Prose in Newsreader at 17px on a 66-character measure; sections numbered;
   two disclosure levels only (summary, evidence).

Deferred: the model-written narrative labelled as such with fact ids per
sentence (Evaluation Cards); sidenotes for method detail on wide screens.

## Part 3. Configuration journeys

Sources: Postman's collection runner (Run Again vs New Run), GitHub Actions
re-runs and workflow_dispatch inputs, Stripe's multi-step forms with a live
summary, Vercel's detected settings with Override, Braintrust's persistent
baseline, MLflow run comparison, n8n's Execute step and pinned data, Zapier's
Setup / Configure / Test inspector, Inspect's cost, token and time limits,
Nielsen Norman on wizards and empty states, Adam Silver and Adrian Roselli on
disabled buttons.

Built now:

- **The footer says what will happen, on every step of New run**: attempts as
  tasks × setups, the smoke-scale rule (20 attempts per setup), the ceiling,
  what is left of the week after it. The review step restates the ledger
  sentence and the approval rule in one paragraph.
- **Buttons stay enabled.** A blocked step prints its reason beside the footer
  ("Choose an architecture first.", "Choose at least one task first.") instead
  of going grey.
- **Run again** on a finished run opens New run with the same tasks, setups,
  track, ceiling and concurrency, titled "… again" (Postman, GitHub).

Journeys the Studio now supports end to end:

1. *Compare Monarch with Bare on the 10-task set.* Reports → New run → Complete
   requests → architecture → tick Bare → 10 tasks preset → Review, which states
   the attempts, the ceiling, the week left and whether it runs at once → Start
   run → live view → Open report → the verdict names both pass rates with
   intervals and the harm sentence.
2. *Re-run last week's round on the new build.* Runs → open the run → Run again
   → change nothing but the title → Start.
3. *Understand why a run failed.* Runs → row → Results → the failing attempt →
   Checks (the square marks what failed) → Trace → the event → Evidence.
4. *Let Genesis test a hypothesis.* Genesis → drop a sentence → the watcher
   rewrites it as a hypothesis, plans a smoke run and launches it, or files a
   question → Activity shows every step → the card's Review stage carries the
   grader's results and Genesis's verdict.

Deferred: presets of the four frozen task sets × modes as a gallery; "Set as
baseline" on product graph versions with diffs relative to it; a Test tab per
node in the architecture inspector with pinned sample data; the budget sentence
on Settings with the reset instant.
