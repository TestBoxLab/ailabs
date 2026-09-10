# Genesis for the whole team: chat first, two chambers, its own budget, a memory that proves itself — design of record

Date: 10 September 2026. Feature 022. Written by Claude for Lucas after a full read of
features 019 to 021 (code, tests, the three design notes, the 90-source research note,
the audit screenshots) and a round of fifteen design questions answered by Lucas the same
day. Supersedes the open parts of `2026-09-09-genesis-autonomy-reports-journeys-design.md`
Part 1; the report-prose and configuration-journey parts of that note stand.

Fixed rules this design respects (`PLAN.md` §1, constitution §III, decision D5): nothing
grades itself; Lucas approves paid rounds; a launch at smoke scale needs no approval
record; every paid request is reserved in the weekly ledger before it is sent; task
prompts, data and rules are frozen; facts from Monarch's code are internal-only.

## 1. Decisions taken by Lucas on 10 September

| # | Question | Decision |
|---|---|---|
| 1 | Who works with Genesis | Anyone on the Monarch team: they open the Studio, talk to Genesis, drop their thoughts. |
| 2 | Centre of gravity | Chat first. The board shows how Genesis is tracking what it was told. |
| 3 | Hypotheses | Structured records, not prose. |
| 4 | Comparisons in scope | Any setup against any setup, over any task set or subset. |
| 5 | Model policy | A configuration page where every step of Genesis's work has its own model. |
| 6 | Money | Admins set Genesis's weekly budget. |
| 7 | Autonomy | Genesis may author and publish architectures and test them, inside its own budget, which code never lets it exceed. |
| 8 | Judgement | A pair: Genesis and a second chamber that reviews and ranks, each with a configurable model. |
| 9 | Live work | Tool calls shown with their arguments and results while Genesis works. |
| 10 | Reading | Full text of sources is ingested. |
| 11 | Skills | Genesis writes them itself; people can rewrite, delete or create them in a panel. |
| 12 | Memory | Build the whole set of state-of-the-art memory features, including the evaluation. |
| 13 | Channels | Slack brief and a weekly digest page, both. |
| 14 | Layout | Claude's choice, grounded in the research. |
| 15 | Monarch patch proposals | Build them. |

## 2. Where Genesis stands today, and the first thing that changes

On 10 September the state directory shows five turns, all failed, no money spent, no
analysis, no skill, no `LAB.md`, no activity record, and one hypothesis queued for a day
with a flag the watcher skips. Every turn was refused by the lab's own ledger before a
provider was contacted: the broker reserves each request at request bytes counted as
tokens plus 16,000 output tokens at list price, which on Opus 4.8 is above the whole
allowance of a nightly turn, and the automation always chose Opus because it takes the
first available route in file-name order.

**Layer 0, landed with this document:** the broker reserves each request at a realistic
input estimate and an output cap computed from what is left of the turn's allowance, and
passes that cap to the provider, so a turn spends its allowance across as many requests
as it needs and stops with a plain reason when it is spent. Every step of Genesis's work
takes its model from a configuration file, defaulting to the cheapest available route
rather than the first. A refusal shows on the turn in words. A queued card is always a
card the watcher will take. Only after this can the pending live route check mean
anything.

## 3. The shape

Genesis becomes a colleague the whole team talks to. The conversation is the working
surface; the board, the library and the memory are what Genesis keeps in order behind
it. The research says the strong products split chat from artifact and make every
reference typed and clickable (Devin, Manus, Claude Artifacts, Perplexity Labs); the
agent products that work inside teams make the agent a delegate who reports on the
artifact while a person stays owner (Copilot's coding agent, Linear, Jira). Both hold.

### Layout (Claude's choice, decision 14)

Desktop, three columns on the page grid the Studio already uses:

- **Left rail, 240 px.** New conversation; the person's conversations, newest first;
  then Board, Library, Memory, Activity, Settings. An inbox count sits on Board when
  something waits for this person: a question asked of them, a plan an approver has to
  decide, a verdict on a card they dropped.
- **Centre, the conversation, 66-character measure for prose.** Each of Genesis's turns
  renders as prose with record chips; the work it did during the turn renders above the
  answer as a step list, one line per tool call ("read run smoke-002, task
  sf_opp_closed_won, 120 events"), each line opening to its arguments and its result.
  Steps stream while the turn runs; the answer streams under them. A card Genesis
  creates or moves appears inline as a chip that opens it on the right. The composer has
  the message box, a drop area for a link, a run id or a file, and, behind an overflow
  control, the model override for this conversation; the default model for chat is set
  on the configuration page, not per message.
- **Right pane, 400 px, "What Genesis is tracking".** Three tabs. *Cards*: the board as
  a compact list grouped by stage, cards touched by this conversation first; a card
  opens in place as a document (stage track, the hypothesis record, the review, the
  plan, the grader's results, the verdict, the conversation about it, its history).
  *Sources*: the library records cited in this conversation. *Trace*: the current or
  last turn's tool calls in full.
- **Board route.** The six-column board stays as its own view for people who want the
  overview; it is a projection of the same cards.

Mobile: the conversation, with Cards and Trace as sheets. The chat is never pushed below
the board.

The Studio's design system holds: paper and ink, one signal red for the current place,
rules instead of boxes, Plex Sans for sentences and Mono for values, no model-family hue
in chrome. The hand-written Markdown formatter is replaced by a vendored renderer
(OFL/MIT, no build step, passes `tests/test_static_csp.py`) so links, tables and nested
lists in Genesis's answers render.

### Vocabulary

One set of words everywhere, in the board columns, on the card's stage track and in the
API: Research, Hypothesis, Plan, Running, Review, Done. Column headers say the same
word as the stage track.

## 4. People

The Studio gains a people list, kept by admins on the configuration page: name, role
(member or admin), and an access key the admin hands to the person. The browser keeps
the key; every write records `by: human:<name>`. No passwords, no third-party login:
this is an internal tool on a private host. When the Studio is reached from outside the
lab machine, the same key is what the front door checks.

Roles: a member talks to Genesis, drops cards, answers questions asked of them, edits
their own person file. An admin also sets Genesis's weekly budget, the models per step,
the dials and the pause, the people list, the channels, and the skills. Approval of a
run above smoke scale is unchanged: decision D5 names the approvers, and a launch by
anyone else creates the approval request as today.

Each person has a conversation list of their own. Cards, the library, the memory and the
activity record are shared. Genesis keeps one bounded file per person, "what I know about
this person and how they like answers", written by Genesis and readable and editable by
that person (Hermes Agent's user file; the field's per-user model).

## 5. The two chambers (decision 8)

Google's co-scientist showed that a reflection step with search access "prevented the
hallucination of seemingly novel but implausible hypotheses", and that a pairwise
tournament gives a legible ranking. Genesis gets the smallest version that keeps both
properties.

- **Genesis** proposes and works: reads, writes hypotheses, plans, verdicts, skills,
  patches. Prompt `GENESIS.md`, identity `SOUL.md`.
- **The Reviewer** judges: a separate turn on its own model with its own prompt
  (`REVIEWER.md`, people-editable), the same read-only tools, and a fixed output shape
  the code validates: accept, revise or reject; a list of issues, each of one kind
  (confound, no control, task set not frozen, effect not defined, cost, arithmetic,
  citation missing, outside the methodology); a one-line reason. It never writes cards
  itself; its review is a comment on the card.

What the code enforces: a plan does not launch, by Genesis or by approval, without an
accepted review; a verdict shows "reviewed" or "unreviewed"; a skill Genesis writes is
reviewed before it enters a prompt; a patch proposal carries its review. Genesis may
revise once after a "revise"; the second answer is final (two rounds, in code). A
review turn is short, so it costs cents on a cheap model.

**Ranking.** When more than one hypothesis competes for the envelope, the Reviewer
compares pairs (which is worth testing first, given the current build, the record and
the cost of the smallest settling plan) and the code keeps an Elo score per hypothesis
(start 1200, K 32, at most twelve pairs a night). The board shows the score and "why
this first"; the watcher takes the highest-ranked queued card, not the oldest. With one
hypothesis, no ranking turn is spent.

## 6. Hypotheses as records (decisions 3 and 4)

A hypothesis card carries a record the Studio can settle:

```
claim            one sentence, directional
population       a task set id, or a filter over the catalog: tier, domain, category,
                 number of applications touched, explicit task ids
comparison       setup A against setup B; a setup is an architecture version, a Bare
                 model, or a Monarch version (stock or lab)
measure          pass rate | pass^k | cost per passed task | violations per attempt |
                 false completion | turns
direction        A higher | A lower
minimum effect   points of pass rate, or a ratio for cost
prior            Genesis's stated probability that the claim holds, 0 to 1
```

The Studio computes, never the model: which finished runs cover both setups on the
population; the measure for each side with its Wilson interval; the paired sign test
when the tasks are identical; the certainty word from the report's closed set; and, when
no run covers it, the smallest plan that would, with the task count from the minimum
effect and a cost band from the price table and past tokens per attempt. That plan is
what `propose_experiment` receives, and the plan lines a person checks are the same as
today. Outcome colour comes from written rules as today, generalised from "version
against parent" to any comparison: supported, not supported, inconclusive, untested,
invalid, each with its reason. The version-against-parent goal stays as one shape of
comparison.

Intake: a sentence dropped in the chat or the drop box becomes a structured record
through one short turn on the intake model, shown to the person as a form to correct
before it is queued (Deep Research's clarify step, the cheapest cost control there is).

## 7. Tools: the Studio's brain, the field's papers, Monarch's code

Genesis stops adding up events by hand. New read-only actions return the same JSON the
report pages read: `measures` (per run, grouped by task, setup or category), `compare`
(two runs or a run against its baseline: paired delta, interval, sign test, overlap),
`failure_buckets`, `report` (the run or round report as data), `task_catalog` (tasks
with tier, domain, category, applications, hash). Every number Genesis cites comes with
a tag naming the run and the table.

Ingest (decision 10): a dropped or searched source is fetched in full, arXiv through its
HTML rendering or PDF text, GitHub through the README and named files, documentation
pages through their text, capped per source; the text is the record's original. The
extraction model then fills a fixed set of columns, each with the quote it rests on:
claim, method, dataset, result numbers, limitations, contradictions with analysed
sources, what it means for Monarch, topic. The Library table shows the columns; the
reader shows the quotes (Elicit's cell-to-quote rule). Only then is a source Analysed.

Code (unchanged, plus one): the daily index and its tools, and `code_diff_check`, which
applies a proposed patch in a temporary checkout and reports whether it applies cleanly.
Nothing runs Monarch's code.

## 8. Money (decisions 6 and 7)

Genesis has one weekly envelope, set by an admin on the configuration page and stored
with the rest of the configuration, inside the lab's weekly limit. Everything Genesis
does on its own reserves from it: turns of both chambers, extraction, embeddings, the
nightly and weekly jobs, and the runs it launches at smoke scale. A run a person
approves reserves from the run budget as today. Per-turn and per-card caps stay as inner
limits; the daily cap becomes a pacing line the brief reports, not a gate. The gate is
the envelope, checked by the broker before every request and by `may_launch` before
every launch, and the pause switch still revokes everything. What is left of the
envelope, what is reserved and what is settled show on the configuration page and in
every daily brief, with the reset instant.

Authoring: Genesis may save and publish architectures in the lab track, tagged as its
own and internal-only, and propose experiments on them under the same envelope. It
cannot publish to the stock track.

## 9. The configuration page (decision 5)

A Settings section named Genesis, admin writes, member reads. Stored in
`genesis/config.json`; every change in the activity record with who made it.

| Block | Contents |
|---|---|
| Models per step | One row per step with model, thinking level and per-turn cap: chat, intake, reading, review, ranking, plan, verdict, consolidation, sweep, extraction, embedding, patch, brief. Defaults: the cheapest available route for intake, reading, extraction, ranking, consolidation and embedding; a frontier route for review, plan, verdict and patch. |
| Budget | The weekly envelope; left, reserved, settled, reset instant; per-turn and per-card caps. |
| Autonomy | The dials and the pause, moved here from the Memory tab. |
| Skills | The panel: list, read, rewrite, delete, create; who wrote each and when. |
| People | The list, roles, keys. |
| Channels | Slack webhook present or not (never the value) and the brief hour; the digest day. |
| Jobs | Daily and weekly jobs with last run, result and Run now. |

## 10. Memory (decision 12)

The three tiers stay. Added, from the 2026 survey and the vendors that survive
reproduction:

1. **Touches from tools.** A record cited through a tool or returned by a search counts
   as a touch, not only a tag in the final answer; probation and decay then measure use.
2. **Consolidation as data.** The nightly turn returns a list of add, replace and remove
   operations the code validates and applies within the budget, instead of free prose.
3. **Nightly self-check.** Three random Known entries are re-read against their records;
   an entry that no longer holds is dropped to the record with the reason logged.
4. **Weekly evaluation.** Twenty questions whose answers are record ids (a fixed file
   plus questions generated from the week's records), asked of Genesis on the reading
   model, scored by code, shown as a trend on the Memory tab: recall, wrong answers,
   tokens per answer. This decides whether seven and thirty days are the right numbers.
5. **People files.** One bounded file per person, as in section 4.
6. **Episodes.** One line per finished conversation, written by the intake model into the
   record, never into core, so search finds "what we discussed about X last week".
7. **Track record.** `TRACK.md`, computed by code, injected every turn: hypotheses
   proposed, supported, refuted, inconclusive; plans launched and their cost; and the
   Brier score of Genesis's priors against outcomes, so it knows how well it predicts.
8. **Hybrid retrieval.** The record search fuses FTS5 with embeddings from the embedding
   step's model, stored in the same SQLite file, results merged by reciprocal rank; each
   hit shows why it matched. This reverses the 9 September "no vector store" note on
   Lucas's decision 12; it is still no hosted memory vendor and no second store.
9. **Retrieval shows its work.** Every hit carries kind, date, status (Analysed,
   reviewed) and the tag Genesis must cite.
10. **What was forgotten.** The Memory tab shows last night's promotions, drops, stale
    marks and removals with their reasons, from the history that already exists.

## 11. Channels (decision 13)

- **Slack.** The nightly brief posts to `#ailabs` through a webhook named in `.env`, as
  facts with links to the Studio (the public host is named in `.env` too). Questions and
  plans waiting are posted when they arise. Answering from Slack is a later step that
  needs a bot token.
- **Weekly digest page.** A public-safe page in the report style, built on the digest
  day: what ran, what was learned (cards in Done), the hypotheses supported and refuted
  with their records, standings, and Genesis's calibration line. Audience rules apply
  as in every report.

## 12. Monarch patch proposals (decision 15)

A card of kind `patch`, internal-only: the failure it addresses with its evidence, the
suspected location cited as path and line from the code index at a named commit, a
unified diff, the reasoning, a suggested test, the Reviewer's review, and the result of
`code_diff_check`. Written by Genesis on the patch model when a failure bucket points at
Monarch's behaviour; a person can ask for one on any failed attempt. Never applied by the
Studio; exported as a `.patch` file. Facts from the code never reach a public report.

## 13. Presentation rules

- One vocabulary for stages, section 3.
- The card is a document: hypothesis record, review, plan, results from the grader,
  verdict with tags as chips, conversation, history.
- Every failure names its reason and the recovery: "Stopped: the turn's allowance is
  spent, $0.02 left of $0.50; raise the per-turn cap or choose a cheaper model."
- No hue in chrome; family colour only in figures.
- The Memory tab shows memory: the files, the record search, the evaluation trend, last
  night's changes. Everything that configures Genesis lives on the configuration page.
- The daily brief is a fact list with links, never ids as prose.

## 14. Phases, lanes and cost

Three lanes can run in parallel in the AILabs tree, each with its own tests and a
receipt file, each told to re-read a shared file before editing it. No lane makes a
paid request. Days are for one agent.

| Lane | Phase 1 (first) | Phase 2 | Days |
|---|---|---|---:|
| A. Evidence and hypotheses | Layer 0 (done here). Hypothesis record, coverage, settling plan, outcome rules. The measures, compare, failure_buckets, report and task_catalog tools. | Ingest and extraction with quotes; `code_diff_check`; patch cards. | 5–6 |
| B. Surface and people | Vendored Markdown. Threads per person, the three-column layout, live steps with arguments and results, the card document in the right pane, the inbox count, one vocabulary. People list and keys. | The configuration page in full; the board route; mobile sheets; digest page. | 6–7 |
| C. Minds, memory, channels | The Reviewer chamber and the two-round rule; review gate on launches; ranking with Elo. Consolidation as data; touches from tools; self-check; `TRACK.md`. | Weekly evaluation; people files; episodes; hybrid retrieval; skills auto-written after debrief; Slack brief; weekly sweep. | 6–7 |

Acceptance, offline: every lane's tests green plus the existing Genesis suites; the
browser suite renders every view in both themes with no console error. Acceptance, live,
after Lucas's permission: the pending route check through the broker on each configured
model, then one dropped hypothesis worked end to end at smoke scale with the Reviewer,
a verdict written, the brief posted.

Blocked on Lucas: a commit of the current tree if lanes are to run in separate worktrees
rather than the shared tree; the Slack webhook and the public Studio host in `.env`;
the people list; the choice of embedding model; the live checks.

## 15. Sources carried from the research notes

Hermes Agent (memory, skills, user file); Google AI co-scientist (reflection, Elo
tournament); OpenAI Deep Research (clarify before spending); Devin (plan with citations,
wait for approval); GitHub Copilot coding agent and Linear (delegate, owner, permanent
log); Manus (visible work, questions instead of guesses); Elicit (cell to quote);
FutureHouse (visible trace); Codebase-Memory and Graphify (deterministic code index);
Letta (sleep-time consolidation); the 2026 memory surveys (governed forgetting,
probation, evaluation); Feng, McDonald and Zhang (levels of autonomy); the Agent
Contracts paper (budgets in code). Links are in `.tmp/research-genesis.md` and
`docs/AI-LABS-GENESIS-CODE-AWARE-MEMORY-2026-09-09.md`.
