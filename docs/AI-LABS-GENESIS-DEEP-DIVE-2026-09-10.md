# Genesis: a deep dive, the field in 2026, and the upgrades worth making

Date: 10 September 2026, evening. Written by Claude for Lucas after a full read of the
Genesis code (twenty-five modules under `wb_studio/`, the front end, the tests), the
three design notes of 9 and 10 September, the live state directory on this machine
(thirty turns, thirteen cards, the memory files, the activity record), a look at the
Studio in the browser, and a sourced survey of Hermes Agent, OpenClaw, Claude Code and
Managed Agents, Letta, Manus, Paperclip, Google's co-scientist, Kosmos, AlphaEvolve and
Sakana's AI Scientist. Paths below are under `monarch-benchmark/workflowbench/` unless
stated.

## 1. The verdict in five lines

1. The design is right and most of it exists: cards as inputs, a watcher, bounded memory
   with a record behind it, a Reviewer chamber, hypotheses as records, an envelope, a
   configuration page, threads per person. The field has converged on the same shapes.
2. The mind is wired wrong. Every turn is a fresh Codex CLI subprocess talking through a
   loopback proxy to a single untyped tool. The model guesses argument shapes, narrates
   between calls, and dies at a hard request count with its work unsaved. This one
   choice explains the two complaints Lucas already made ("narrates instead of
   answers", turns that fail for nothing).
3. Several loops do not close. The post-run debrief fires only when someone loads the
   Genesis page. A plan the Reviewer accepts is never launched unless a second turn
   proposes it again. Built-in tool errors never reach the model.
4. The money gates are thinner than the design says. The weekly envelope is displayed,
   not enforced. The daily cap counts card turns only. A card turn can start paid
   turns from inside itself.
5. The upgrade path is short because the repo already has the missing pieces: the
   benchmark's own tool loop (`wb_arms/api_loop.py`) has four provider adapters with
   typed tools, reasoning capture and stop reasons. Genesis should run on it.

## 2. What Genesis is today

### 2.1 The parts

| Part | Module | State on disk |
|---|---|---|
| Records | `genesis.py` | one JSON per card, turn, thread; card history; analyses; Codex session folders |
| Mind | `genesis_harness.py`, `genesis_provider.py`, `genesis_mcp.py` | `sessions/<turn>/prompt.txt`, a private Codex home per turn |
| Tools | `genesis.py:506-579` plus nine plugin modules through `genesis_plugins.py` | none |
| Watcher | `genesis_watcher.py` | `watcher.json` |
| Daily jobs | `scheduler.py`: code index 04:00, sleep 03:00, ranking 03:00, memory eval Sundays 05:00, sweep Mondays 06:00 | `schedule.json` |
| Memory | `memory.py`, `genesis_sleep.py`, `genesis_memory_suite.py` | `memory/{SOUL,LAB,TRACK}.md`, `record.sqlite3` (FTS5), `history.jsonl`, notes per card |
| Code awareness | `code_index.py` | `code-index/{index.json,changes.json,MONARCH.md}` |
| Judgement | `genesis_reviewer.py`, `genesis_ranking.py`, `genesis_hypotheses.py` | reviews on cards, `ranking.json` |
| Policy | `genesis_autonomy.py`, `genesis_config.py`, `genesis_access.py` | `autonomy.json`, `config.json`, `people.json`, `activity.jsonl` |
| Skills, people, patches, ingest, channels | `genesis_skills.py`, `genesis_people.py`, `genesis_patch.py`, `genesis_ingest.py`, `genesis_channels.py` | `skills/*.md`, `people/*.md`, patch cards, library records |
| Surface | `static/genesis.js`, `genesis.css`, routes in `app.py:1030-1214` | browser |

The plugin seam (`genesis_plugins.py:21-23`) is the best-built part: a module exports
`TOOLS`, `PROTOCOL`, `PROMPT`, `ON_TURN` and a launch gate, and nothing else has to
change. Keep it.

### 2.2 How a turn runs

`Genesis.chat` (`genesis.py:442-468`) reserves the turn's ceiling in the weekly ledger
and starts `start_turn` on a thread. `start_turn` (`genesis_harness.py:105-195`):

1. Starts a loopback HTTP server, "the broker", with two routes: `/v1/responses`, an
   OpenAI Responses endpoint translated per provider by `genesis_provider.complete`,
   and `/tool`, which runs `Genesis.tool`.
2. Builds the prompt (`build_prompt`, `:80-103`): `GENESIS.md` and plugin protocol
   text, the clock line, `SOUL.md`, `LAB.md`, `MONARCH.md`, the card's notes, the
   skills for the card's kind, `TRACK.md`, the person file, the last eight exchanges
   of the thread, the request. About 16,500 characters before any history.
3. Spawns `codex exec --json --ephemeral --sandbox read-only -m genesis-scientist` with
   shell, plugins, multi-agent and web search off and one MCP server, `genesis_mcp.py`,
   which exposes one tool: `lab_action {action: enum of 35 names, payload: object}`.
4. Pipes the whole prompt on stdin as the user message. Codex's own instructions sit
   above it, so `SOUL.md` is not the first block of the prompt as `CLAUDE.md` says; it
   is the fourth block of the user message.
5. Per model request: counts to a hard limit of 24 (`:131`), estimates input as bytes
   over two plus 2,048, computes an output cap from what is left of the turn, reserves,
   calls the provider, settles from the receipt. Refuses in words below 1,024 output
   tokens.
6. The answer is every `text_delta` the model produced in the turn, concatenated
   (`genesis.py:429`). The turn ends when Codex exits, or at 600 seconds.

### 2.3 The loops

- **Watcher** (`genesis_watcher.py:166-191`): every 30 seconds, files a `run` card for
  every finished non-scripted run and a `source` card for every new full-text source,
  starts a paid extraction on a new source at once, then takes the best-ranked queued
  card if nothing is working and the route, the daily cap and the weekly ledger allow.
- **Nightly sleep** (`genesis_sleep.py:34-119`): promote and decay memory, self-check
  three Known entries, index the record, write `TRACK.md`, one consolidation turn under
  US$ 0.50 whose answer must be a JSON list of operations, then the brief card and its
  Slack post.
- **Code index** (`code_index.py:221-267`): fetch, resolve the build commit, diff since
  the previous commit, Graphify when installed, rewrite `MONARCH.md` from data, file a
  library record when something moved. Ran this morning: commit `26558c83`, 5,769 files,
  Graphify absent.
- **Debrief**: when a planned card's run reaches a terminal state, the card is re-queued
  with the verdict question. This lives inside `Genesis.state()` (`genesis.py:143-149`),
  a read.
- **Propose and launch** (`genesis.py:347-371`, `genesis_autonomy.py:81-103`): the
  Studio computes the plan lines; a plan at smoke scale inside the card and daily
  allowances, with an accepted review, launches by itself; anything else waits.
- **Reviewer** (`genesis_reviewer.py`): a separate turn with `REVIEWER.md`, accept,
  revise or reject, two rounds, and a gate that blocks any launch without an accept on
  the exact proposal digest. **Ranking**: pairwise Reviewer turns at 03:00, Elo, twelve
  pairs at most. **Patches**: one turn, `git apply --check` in a detached worktree, a
  patch card, a review.

### 2.4 Memory

Three tiers as designed, plus three files the design added later: `TRACK.md` (computed,
1,500 characters), one file per person (1,000), skills (twelve at most, 4,000 each).
Injection scan on memory files, notes, `SOUL.md`, skills and person files
(`memory.py:70-84`). Probation seven days, decay thirty, pinned never. Touches come from
tags in the answer and from tool reads. Recall is by injection for the core files and by
FTS5 word query for everything else; hybrid retrieval only when an embedding route is
configured, and none is.

### 2.5 The surface

Three columns at desktop width: a rail (new conversation, the person's threads, Board,
Library, Memory, Activity, Digest, Settings, the watcher line with Pause), the
conversation with a composer (message, "Add as a card", model, thinking), and a tracking
pane with Cards, Sources and Trace. The board, the library, the memory page, the activity
log, the weekly digest and the configuration page under Settings all exist and render.
Live steps are polled: the whole turn record is re-fetched every 650 ms and re-rendered
(`genesis.js:96-100`); the turn file is rewritten on every text delta.

## 3. What the live record shows

The state directory on Lucas's machine, not a fixture:

- Thirty turns. Eight failed. No skill written. No person listed. Every model step in
  `config.json` is null, so every turn takes the cheapest route, Gemini 3.7 Flash.
- `LAB.md` holds three Recent entries and one Pinned. Every Recent line carries its
  record tag twice (`[rec:library:e017…] [rec:library:e017…]`), so the tagger writes
  the tag and the consolidation writes it again.
- The watcher turn `22a79857` (14:46 today) is the whole problem in one file. Card:
  "Does GLM 5.3 stay inside the change scope on the Lisa Park relocation task?" The
  model made 30 tool calls in 24 requests: `task_catalog` with `filter: "Lisa"`, then
  `filter: {domain: "hr"}`; `read_run` with `run:` then with `id:`; `hypothesis_check`
  nine times, each refused with a different schema error ("Setup a's kind is
  architecture, bare or monarch"). Request 25 was refused by the 24-request rule. Cost
  US$ 0.22. Nothing written to the card. The stored answer is the concatenation of
  twenty-four sentences that begin "I will…".
- The completed watcher turn `f82377cc` looks the same from the outside: nineteen tool
  calls, four request errors, and an answer that is a list of "I will…" sentences,
  because the answer field keeps everything the model said, not the text after its last
  tool call as the protocol asks.
- Twelve pairs of duplicate run cards sit in `.tmp/duplicate-cards-2026-09-10/`: the
  watcher files a `run` card for a run Genesis launched from a plan card, so one run
  costs two turns.
- No Slack webhook in `.env`. The brief posts nowhere.

## 4. Where it breaks

Findings from the code trace, verified line by line. Grouped by what they cost.

### 4.1 The model cannot see what it needs

1. **Built-in tool errors are swallowed.** A `ValueError` from `save_research`,
   `propose_experiment`, `ask_question` or `read_run` is raised inside the broker's
   `/tool` branch (`genesis_harness.py:123-127`), caught by the generic handler, logged
   with the wrong reason ("Inspect the provider receipt and routing configuration",
   `:162`), and returned to Codex as "Lab action failed. Check its parameters"
   (`genesis_mcp.py:28-30`). Only plugin tools return `{'error': sentence}`
   (`genesis_plugins.py:49-50`). A stale card revision or a malformed goal is invisible.
2. **One untyped tool.** `lab_action(action, payload)` gives the model an enum of names
   and `additionalProperties: true`. The protocol's answer is "Use catalog to discover
   valid IDs and schemas", one extra paid request per turn, and the turn above shows it
   does not work.
3. **A cliff, not a landing.** At request 25 the turn is refused and everything is lost.
   No "you have two requests left, write your answer now", no partial note on the card.
4. **Tool results are kept at 240 characters** in the turn record
   (`genesis_harness.py:31-35`), so the Trace cannot show what the model read, and the
   model's reasoning is dropped (`genesis_provider.py:21`). The benchmark loops record
   both.
5. **The nightly turn is told to use a tool it does not have**: "Use record_search to
   read the records added since yesterday" (`genesis_sleep.py:17-18`), but
   `record_search` is a word query with no date filter, and `memory.recent()` is not a
   tool. `record_search` also misses everything from today until the 03:00 index.
6. **Extraction reads 15,800 characters** (`genesis_ingest.py:32, :148-154`) although the
   message cap was raised to 220,000; a forty-page paper is judged on its first pages
   and the columns render as verified.
7. **Skills marked "Applies: always" all enter every prompt** (`genesis_skills.py:89-93`):
   up to 48,000 characters, more than every core file together.

### 4.2 Loops that do not close

8. **The debrief is a side effect of a page load** (`genesis.py:143-149`); the watcher
   never calls `state()`.
9. **Review accept never launches.** `propose_experiment` refuses without an accepted
   review; the review is asynchronous; when it lands, `ON_TURN` writes the verdict and
   stops (`genesis_reviewer.py:154-181`). The card waits in Plan with "The Reviewer has
   not accepted this plan" and Slack says a person is needed. No route lets a person
   request a review either.
10. **A stopped turn fails twice** (`genesis.py:310-312` then `genesis_harness.py:193`),
    so `on_turn`, `finish_card` and the record summary run twice.
11. **Genesis's own turns are attributed to `human:studio`** (`genesis.py:461`), and the
    person file for "studio" is injected into watcher and nightly turns.
12. **A keyed person's threads vanish**: the rail filters on `human:studio`
    (`genesis.js:12, :56`) while the server rewrites `by` to `human:<name>`
    (`app.py:1171`).

### 4.3 Money gates thinner than the design

13. **The envelope is display only** (`genesis_access.py:9-10, :141-153`). Nothing
    bounds Genesis's spend below the shared US$ 300.
14. **The daily cap counts card turns only** (`genesis_watcher.py:113`). Nightly,
    ranking (up to US$ 2.40 a night), sweep (up to US$ 5.50 on Mondays), memory eval,
    skill asks, skill reviews and patches are outside it.
15. **Turns start turns.** `ingest_source`, `propose_patch` and `request_review` start
    new paid turns from inside a turn, each reserved on its own, so one card can fan
    out past its US$ 2.
16. **A skill ask after every debrief or accepted card** (`genesis_skills.py:138-153,
    :227-236`): US$ 0.20 plus a US$ 0.20 review, no daily bound, no switch.
17. **Gemini on cheap steps is refused by arithmetic**: the 65,536-token thinking
    allowance (`genesis_harness.py:24, :50`) is subtracted from the affordable output;
    at a US$ 0.20 ceiling the cap falls under the floor before the request starts.
18. **The Cards dial "off" does nothing** except suppress the debrief
    (`genesis_autonomy.py:26` vs `genesis.py:145`).

### 4.4 Dead, doubled or contradictory

19. `STEPS` lists `intake`, `plan`, `verdict`, `brief` that no code routes to
    (`genesis_config.py:16`); the intake step with its correction form (design §6) does
    not exist; `drop()` classifies by regex.
20. `brief_hour` and `digest_day` are stored and shown and used by nothing; the brief
    runs at 03:00.
21. Two pause flags (`watcher.json`, `autonomy.json`), two outcome systems
    (`hypothesis_outcome` and `genesis_hypotheses.settle`), duplicate ids in
    `index.html` (`memory-skills`, `genesis-digest-view`), a dead `fetch_page`.
22. `GENESIS.md` says "You have NO approve or launch capability" and "A plan at smoke
    scale within your allowances launches at once"; "No paid preparation or analysis is
    performed by this tool" while three tools spend on call.
23. The activity log is used as a database through a 500-line tail
    (`genesis_skills.py:135`, `genesis_ranking.py:156`, `genesis_channels.py:70`); past
    500 busy entries a verdict is dropped and a card can be re-posted to Slack.
24. Untrusted text enters the prompt unscanned: card bodies, library originals, tool
    results, the thread history. The scan guards only what is written to memory.

### 4.5 Performance

25. `Genesis.event` rewrites the whole turn JSON on every text delta under the lock every
    tool call needs (`genesis.py:421-430`).
26. `state()` re-reads every card and every job's analysis on every `/api/genesis` GET;
    `research_state` and `list_runs` return everything, including thirty turns with all
    their events, to the model.

Tests cover none of items 1, 8, 9, 10, 12, 13, 14, 20. The browser suite renders the
views but does not approve, decline, answer or stop.

## 5. What the field does

Dated and sourced; the full URL list is in section 9.

**Hermes Agent** (Nous Research, MIT, v0.21.1 on 7 Sep 2026). One synchronous loop that
every entry point calls. `SOUL.md` is slot one of the system prompt. `MEMORY.md` (2,200
characters) and `USER.md` (1,375) are loaded once per session as a frozen snapshot so
the prefix cache holds; a write past the limit returns an error; every memory, skill and
context-file write is scanned for injection, and since v0.21 edits to standing orders
need approval "so a prompt-injected agent cannot quietly rewrite its own standing
orders". Skills are `SKILL.md` with When to use, Procedure, Pitfalls, Verification,
loaded in three levels (names, body, reference files), created by the agent only from a
repeatable workflow, a resolved error or user feedback: "lessons, not logs". Cron jobs
run in fresh sessions with a preflight that marks a job `blocked_config` without a model
call, a failure streak nudge after three, an incident ledger keyed by error signature
with acknowledge, and `continuity` that feeds a job its own previous output. Context
compression at 50% of the window, protecting head and tail. Subagents get a fresh
context, cannot widen tools, and cannot delegate, ask, remember or schedule. Praise:
memory and skills as plain files you can read and commit. Complaints: auxiliary tasks
default to the expensive model; the learning loop needs volume.

**OpenClaw** (ex-Clawdbot). A heartbeat every 30 minutes that answers `NO_REPLY` when
nothing needs attention, in an isolated session (100K tokens down to 2 to 5K). Daily
notes promoted into `MEMORY.md` by "dreaming" with a log for review. A memory flush
before compaction. Deterministic per-agent tool policy. Its year: CVE-2026-25253, a
Control UI that trusted a URL parameter; the ClawHavoc campaign, 341 malicious skills
among 2,857 audited (later over a thousand), payloads delivered through README
"Prerequisites"; tens of thousands of exposed instances without auth. Lesson: a
marketplace scan is not control of the source, and anything the agent can write and
read back is an injection channel.

**Claude Code and Managed Agents** (Anthropic). Hooks as the enforcement layer, with a
`PreToolUse` hook that can deny a write (the harness repo's default-FAIL contract: a
results file that cannot be written unless an evidence file was opened first). Auto
memory with an index capped at 200 lines and an error on overflow. Routines that wrap
external payloads as untrusted and note that a green run "does not mean the task in your
prompt succeeded". Auto mode: a classifier judging each action, escalating to a person
after 3 consecutive or 20 total denials. Managed Agents: a per-run budget copied onto
each session, pause on `budget_reached`, deployment-run records separate from sessions,
and Dreams, a background job that reads memory plus transcripts and writes a new store
the person diffs and adopts. The March 2026 harness post: "self-grading fails because
agents confidently praise their work"; a separate evaluator is "far more tractable to
tune toward skepticism"; measure whether each component still changes outcomes and
strip it when it does not.

**Letta.** Memory blocks with character limits, editable or read-only. A sleep-time
agent owns the memory-editing tools; the working agent does not; one owner for heavy
edits or you lose updates. **Manus**: cache hit rate as the north star, mask tools
rather than remove them, keep failures in context, recite the goal by rewriting a short
plan file. **Zep/Graphiti**: bi-temporal facts, a contradiction invalidates rather than
deletes, episodes kept as the non-lossy ground truth. **Paperclip**: task checkout and
budget reservation in one atomic step, warning at 80%, pause at 100%, an immutable audit
log. **Devin**: knowledge items with a trigger description, suggested by the agent and
accepted by a person.

**Scientists.** Google's co-scientist: generation, reflection with search, an Elo
tournament from 1200 with multi-turn debates for the top and single-turn pairs below,
meta-review feeding recurring critiques back; in Nature, May 2026. Kosmos (Edison):
twelve-hour runs, a structured world model rewritten each cycle, every statement
citing a notebook or a paper; outside scientists judged 79% of statements accurate,
data analysis 86%, synthesis 58%, "conflate statistically significant results with
scientifically valuable ones". AlphaEvolve: grounded only by an evaluator the model
cannot edit. Sakana v1 edited its own timeout and filled a terabyte; v2 uses separate
models for experiment, review and citation. The NeurIPS 2026 workshop line: the
bottleneck "is no longer hypothesis generation, it is verification". ScientistOne
audits whether written claims match validated results.

## 6. The upgrades, ranked

Six tiers. Each entry says what changes, where, and why it earns its place. Effort in
agent-days. Nothing here reopens a fixed rule of `PLAN.md` §1.

### Tier 0. Repairs: make the code do what the design says (about 2 days)

| # | Change | Where |
|---|---|---|
| R1 | Catch `ValueError` in the `/tool` branch and answer `{'error': str(exc)}`, exactly as `dispatch` does for plugins. | `genesis_harness.py:123-127` |
| R2 | Move the debrief out of `state()` into `Watcher.wake()`. | `genesis.py:143-149`, `genesis_watcher.py:166` |
| R3 | When a review lands as `accept` on a card whose plan is inside the allowances, call the launch path from `ON_TURN`; add `POST /api/genesis/cards/<id>/review` so a person can request a review. | `genesis_reviewer.py:154-181`, `app.py` |
| R4 | Enforce the envelope in the broker before every reservation and in `may_launch`. | `genesis_harness.py:133`, `genesis_autonomy.py:81` |
| R5 | Count every Genesis turn in the daily cap, not only card turns; record every attempted launch and job, including refusals, in `activity.jsonl`. | `genesis_watcher.py:107-119` |
| R6 | Skip the `run` trigger card when a plan card already names the job; set `evidence` on launch. | `genesis_watcher.py:137-152` |
| R7 | Remove the 15,800 cut in extraction now that the cap is 220,000. | `genesis_ingest.py:148-154` |
| R8 | Give the nightly turn `memory_recent(since)` as a tool; index a record into FTS5 when it is written, not at 03:00. | `memory.py:406-424`, `genesis_sleep.py:17` |
| R9 | Attribute Genesis's own turns to `genesis`; rail filter by the current person's name. | `genesis.py:461`, `genesis.js:12` |
| R10 | One `failed` per stop; one pause flag; delete the dead step names, `fetch_page`, the duplicate ids; honour `brief_hour`. | listed in §4.4 |
| R11 | Apply the thinking allowance only when the ceiling can afford it, else request without thinking. | `genesis_harness.py:24, :50` |
| R12 | Fix the doubled tags in `LAB.md` writes and rewrite `GENESIS.md` so it no longer contradicts itself (one paragraph on launching, one on what spends). | `memory.py`, `GENESIS.md` |

Tests for each, especially R1, R2, R3, R4 and R5, which have none today.

### Tier 1. The mind: one loop, typed tools, a landing (3 to 4 days)

This is the upgrade that changes what Genesis is like to work with.

**M1. Run Genesis turns on the benchmark's own tool loop.** `wb_arms/api_loop.py` already
has adapters for OpenAI chat, OpenAI Responses, Gemini and Anthropic, with typed tool
lists per provider, reasoning summaries and stop reasons recorded. `genesis_provider.py`
is a second, thinner provider layer written only to feed Codex. Replace the Codex
subprocess, the loopback broker and the MCP bridge with one in-process loop over those
adapters. What goes away: Codex's own instructions above `SOUL.md`, a per-turn process
spawn and private Codex home, the Windows-only binary path, the 600-second wall, the
"I will…" narration that Codex's coding persona invites. What stays: the ledger
reservation per request, the per-turn ceiling, the event record, the plugin seam. The
protocol becomes the system prompt and `SOUL.md` really is its first block.

**M2. Typed tools.** Each action becomes its own tool with a JSON schema generated from
the registry (the plugin `TOOLS` lists already name their arguments). Thirty-five tools
is within every provider's limit; mask by card kind if the list ever weighs on the
prompt (Manus: mask, do not remove). The `catalog` round trip disappears. The failed
turn in §3 would have made its first `read_run` call correctly.

**M3. A landing instead of a cliff.** At request cap minus two, the loop appends a line:
"Two requests remain. Write your answer now, citing what you have." At cap minus one,
tools are masked so the model can only answer. The answer is the text after the last
tool call, as the protocol demands; everything before it is kept as the step list. A
turn that still runs out saves its notes to the card before failing.

**M4. Keep the evidence.** Store tool results in full in the turn record (compressed on
disk if size matters) and the reasoning summaries the adapters already return. The
Trace then shows what the model read, and the narrative can cite it.

**M5. Frozen memory per turn.** Read `SOUL`, `LAB`, `MONARCH`, `TRACK` once at turn
start and keep the prefix stable for caching; memory writes land on disk and are seen by
the next turn (Hermes). The turn record keeps the snapshot, so "what Genesis knew when it
decided" is reproducible.

**M6. Skills by name first.** Inject skill names and one-line descriptions for the card
kind; `skill_read` fetches a body on demand (Hermes's three levels). Cap the injected
text at one core file's worth.

### Tier 2. Loops that close and cost nothing when idle (2 days)

- **L1. Preflight without a model.** Before any scheduled or watcher turn: route keyed,
  ledger can cover the ceiling, envelope has room, the input exists. A failed preflight
  stamps the job `blocked` with the reason and posts once; no request is sent
  (Hermes `blocked_config`).
- **L2. Incidents by signature.** Key repeated failures (same tool, same error text) and
  stop re-spending on them; show the incident on the Activity tab with Acknowledge.
- **L3. Continuity.** The nightly brief and the weekly digest receive yesterday's brief
  and last week's digest as input; "what changed" becomes a diff, not a re-summary.
- **L4. Atomic checkout.** Taking a card and reserving its ceiling become one step under
  the lock, so two wakes can never work the same card; a soft warning at 80% of the card
  and daily ceilings on the card itself (Paperclip, Managed Agents).
- **L5. Turns do not start turns.** `ingest_source`, `request_review` and
  `propose_patch` queue work for the watcher instead of spending from inside a turn; the
  parent turn's ceiling is the only ceiling.
- **L6. Skill asks on a budget.** One skill ask a day at most, only after a card whose
  verdict was reviewed, and never from a single card (Hermes: repeatable workflow or
  resolved error; Voyager: store only after verification).
- **L7. A real Cards dial.** "Off" means the watcher does not work cards and
  `save_research` refuses stage changes; the pause copy says what pause does.

### Tier 3. Memory that a person can audit (2 days)

- **A1. The night writes `LAB.next.md`, not `LAB.md`.** Consolidation produces a new file
  and a diff card in Your review; adopt or discard (Managed Agents Dreams, OpenClaw's
  dreaming log). A bad night is reversible.
- **A2. One writer.** Card turns append Recent entries only; the nightly job owns
  replace and remove (Letta's sleep-time ownership). Removes the race between the
  watcher and the scheduler.
- **A3. Beliefs are invalidated, not deleted.** The hypothesis record and Known entries
  get `valid_from`, `valid_to` and `superseded_by`; a contradiction closes the old entry
  and links the new one (Zep). "What did we think on 8 Sep and why" becomes answerable.
- **A4. Untrusted text is wrapped.** Card bodies, library originals, tool results and
  thread history enter the prompt inside a marked block that the protocol says to treat
  as data; the same scan that guards memory runs on them and blocked spans are shown on
  the card (Hermes, Claude Code routines, OWASP).
- **A5. Standing orders need a person.** Pinned entries and skills already do through
  the interface and the Reviewer; make `LAB.md` Known entries that name a rule of
  `PLAN.md` §1 pinned by code, so no consolidation can drop them.

### Tier 4. A scientist that is hard to fool (2 to 3 days)

- **S1. Claim classes.** Every sentence of a verdict or debrief is either computed (from
  `measures`, `compare`, `report`) or interpretation. The Studio checks the tags: a
  computed sentence must cite a run and a table; an interpretation renders in a second
  style. Kosmos's 86% on data against 58% on synthesis is the reason.
- **S2. Default unverified, in code.** A verdict tool refuses unless the turn's own
  events show `read_run` or `measures` on the run it judges (the harness repo's
  default-FAIL hook, done inside `Genesis.tool` rather than a hook).
- **S3. Gate ROI.** Log whether the Reviewer, a question card or the ranking changed a
  decision (a launch blocked, a plan revised, an order changed). After a month, retire
  the gates that never did (Anthropic's harness post).
- **S4. Meta-review.** Once a week, the Reviewer's recurring issue kinds over the week's
  reviews are written as one paragraph into the protocol block Genesis sees
  (co-scientist's meta-review). Cheap, and it is how the second chamber teaches the
  first.
- **S5. Negative results as first-class.** A hypothesis settled "not supported" gets the
  same card document, digest line and library record as a supported one; the digest
  counts them. None of the surveyed scientists does this well.

### Tier 5. Form factor (2 days, some already in the audit)

- **F1. Stream, do not poll.** One SSE stream per turn for steps and answer; the card
  sheet and the watcher line subscribe. Removes the 650 ms full re-fetch and the
  per-delta file rewrite (`genesis.py:421-430`).
- **F2. The inbox is the front door when something waits.** The "Needs you" count
  already exists; when it is non-zero, open on the inbox, not the empty conversation.
- **F3. Every refusal in words, on the thing refused.** Preflight, envelope, daily cap,
  request cap, Reviewer: the reason and the recovery on the card, the job or the turn,
  never only in the activity log.
- **F4. Answer from Slack.** A bot token lets a question card be answered in the thread
  where it was posted; until then the post carries a deep link to the card.
- **F5. Phone width**: the conversation with Cards and Trace as sheets, as designed;
  test it in the browser suite.

### What not to do

- No skills marketplace or third-party skill import: ClawHavoc.
- No classifier in place of the money gates: the deterministic gates in code are the
  right design; a classifier could help only on the "runs" dial for smoke plans, and
  that is not needed yet.
- No hosted memory vendor, no second store; the 9 September note stands. Hybrid
  retrieval stays behind the embedding route and the weekly evaluation decides.
- No learned curation of skills or memory; SkillOS and friends are auditable only in
  papers.
- Genesis never gains write access to `wb grade`, the task hashes, the price table or
  the ledger (AlphaEvolve's rule, Sakana's incident).

## 7. Order and cost

| Week | Work | Days | Paid checks |
|---|---|---|---|
| 1 | Tier 0 repairs with tests; M1 to M3 (the loop, typed tools, the landing) | 5 | one dropped hypothesis worked end to end at smoke scale, under US$ 1 |
| 2 | M4 to M6; Tier 2 | 4 | the nightly job for three nights, under US$ 2 |
| 3 | Tier 3; S1 to S3 | 4 | one week of debriefs, under US$ 5 |
| 4 | S4, S5; Tier 5 | 3 | none |

Acceptance for week 1, the only one that matters for trust: the same card that failed
today (`eeae0e5d`) worked by the new loop, on the same model, finishing in under ten
requests with an answer that starts with the verdict and a card that holds the analysis.

## 8. Built the same evening (Lucas: "Adopt")

Week 1 landed on 10 September after Lucas adopted the plan, with the envelope at US$ 25,
review and patch on the strongest keyed route and everything else on the cheapest.

**The loop (M1 to M6).** `wb_studio/genesis_harness.py` is now an in-process loop over the
four adapters in `wb_arms/api_loop.py`, which gained an optional output cap and, for
Gemini, a thinking budget. `wb_studio/genesis_schemas.py` gives every lab action a typed
schema in the four provider shapes; an action without one still reaches the model with a
permissive schema. SOUL.md is the first block of the system prompt, then the protocol,
the memory files, the skills by name, the plugin blocks; the clock and the thread history
are in the first user message so the prefix caches. Each request is reserved in the
weekly ledger for an output cap the turn can still pay; Gemini's thinking gets what is
left after that, up to the API's maximum of 65,535. Tool refusals come back as sentences.
Tool results are kept in the record up to 6,000 characters, reasoning summaries up to
4,000. Two requests before the cap of 24 the model is told to answer; a turn that still
runs out on a card leaves its last text in the card's notes. A person's stop records one
failure. `genesis_mcp.py`, `genesis_provider.py` and the Codex binary path are gone.

**Repairs (R1 to R12).** Built-in tool errors reach the model. The debrief runs on the
watcher's wake (`Genesis.debrief`), never on a GET. An accepted plan launches from the
Reviewer's `ON_TURN` through `Genesis.launch_if_allowed`, and a person can ask for a
review with `POST /api/genesis/cards/<id>/review` (the card sheet has the button). The
envelope is a gate in `Genesis.chat` and in every launch. The daily cap counts every
turn; refusals are in the activity record once per reason. A run Genesis launched is not
filed a second time. Extraction reads the whole source. The nightly turn has
`memory_recent`; cards, turns and library records enter the search index when they are
written. Genesis's own turns are attributed to `genesis`; the rail filters threads by
the person the key names (`me` on `GET /api/genesis`). A memory entry names its record
once. `brief_hour` runs a `genesis-brief` job (the scheduler takes several jobs per
module and an hour read from settings). The unused steps, the dead page fetcher, the
doubled containers and the Gemini refusal-by-arithmetic are gone. `GENESIS.md` is
version 2 with no contradictions. Work now accepts a failed or stopped card.

**Acceptance.** The card that failed in the morning (`eeae0e5d`) was dropped again as
`70934e3e` and worked by the new loop on Gemini 3.7 Flash: every tool call had the right
shape, one refusal was read and corrected, the answer opens with the verdict and carries
a run tag on every claim, the analysis was written to the card, which moved to Review.
Cost US$ 0.46. It used all 24 requests, so the landing is what saved it; the target of
ten requests is not met yet and is the first thing to watch (skills by name and a
shorter protocol are the levers). Tests: `tests/test_genesis_loop.py` (10),
`tests/test_genesis_repairs.py` (10); the Studio and Genesis suites green (895); the
browser suite green (30 checks). Not built this evening: Tier 2 onward.

**Tiers 2 to 4, later the same night (Lucas: "Continue building and shipping").**
Loops: the envelope joins the watcher's preflight; a soft warning at 80% of the day's cap
or of the envelope on the watcher line; taking a card and checking that no other card is
working happen under one lock; the Cards dial off stops the watcher and Work now; a
scheduler job that fails the same way twice is a job incident in the activity record;
the nightly turn receives yesterday's brief; a skill is asked once a day and never from a
single card; a checkpoint at half the turn's requests; the protocol asks for several tool
calls per request and ten requests per card. Turns that start turns (ingest, review,
patch) are bounded by the envelope and the daily cap rather than queued (L5 by gates,
not by a queue). Memory: the night writes `LAB.next.md` and a memory card in Plan with
its operations; a person adopts (the operations apply) or declines (the file is dropped);
`memory_replace` and `memory_remove` are no longer tools of a card turn, a full LAB.md
tells the model the night makes room; a settlement that changes keeps the one before with
`valid_to` and `superseded_by`; the card body reaches the model wrapped as data and a
body that reads as an instruction is flagged. Scientist: `claim_check` counts the
sentences of a verdict that carry a number without a run tag and the card shows the
count; a verdict on a planned card is refused unless the same turn read the run with
`measures`, `failure_buckets` or `read_run` (the harness tells the tools their turn);
the digest counts what the gates did (reviews by verdict, questions, answers, defaults
taken, launches, plans held, refused turns); the Reviewer's three most flagged issue
kinds of the week enter every prompt. Form: the Genesis page opens on the board once per
session when something waits; the Memory tab shows the night's proposal with a way to the
card; a memory card reads "Adopt the changes". Live: one nightly run on the local Studio
proposed four entries in ten requests for US$ 0.20, LAB.md untouched until adopted. Tests:
`tests/test_genesis_tiers.py` (14). Not built: SSE streaming (F1), answering from Slack
(F4), the phone-width check (F5), the settlement history on the card sheet.

## 9. Decisions for Lucas

1. **Replace Codex with the in-process loop (M1)?** It removes the second provider layer
   and every symptom in §3, and the adapters are already tested by the benchmark. The
   cost is that Codex's compaction and its Responses handling go with it; the loop's
   history bound (eight exchanges, 64 KB) already stands in for compaction.
2. **Envelope default.** The design says an admin sets it; nothing is set. Propose US$ 25
   a week inside the lab's 300, with the night at 0.50 and the day at 6.00 as inner
   lines.
3. **Model per step.** All null today. Propose: chat and reading on the cheapest route;
   review, verdict and patch on a frontier route; consolidation on the cheapest route
   with the JSON-only answer.
4. **Skill creation policy (L6).** One a day, reviewed, never from a single card. Or off
   until the loop is stable.
5. **Slack.** The webhook for `#ailabs` and the public Studio host are still missing
   from `.env`; every channel item waits on them.

## 10. Sources

Hermes Agent: https://github.com/NousResearch/hermes-agent ·
https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/architecture.md ·
https://github.com/NousResearch/hermes-agent/releases ·
https://hermes-agent.nousresearch.com/docs/user-guide/features/memory ·
https://hermes-agent.nousresearch.com/docs/user-guide/features/skills ·
https://hermes-agent.nousresearch.com/docs/user-guide/features/cron ·
https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation ·
https://hermes-agent.nousresearch.com/docs/user-guide/security ·
https://hermes-agent.nousresearch.com/docs/user-guide/features/personality ·
https://hermes-agent.nousresearch.com/docs/developer-guide/context-compression-and-caching ·
https://hermes-agent.nousresearch.com/docs/user-guide/checkpoints-and-rollback ·
https://kisztof.medium.com/hermes-agent-review-nous-researchs-self-improving-ai-agent-e72bc244435a ·
https://blakecrosley.com/guides/hermes (third party; version attributions unverified)

OpenClaw: https://docs.openclaw.ai/gateway/heartbeat · https://docs.openclaw.ai/concepts/memory ·
https://docs.openclaw.ai/gateway/security · https://docs.openclaw.ai/tools/skills ·
https://docs.openclaw.ai/concepts/multi-agent · https://docs.openclaw.ai/automation/cron-jobs ·
https://adversa.ai/blog/openclaw-security-101-vulnerabilities-hardening-2026/ ·
https://www.termdock.com/en/blog/clawhub-malicious-skills-incident ·
https://businessinsights.bitdefender.com/technical-advisory-openclaw-exploitation-enterprise-networks

Anthropic: https://code.claude.com/docs/en/scheduled-tasks · https://code.claude.com/docs/en/routines ·
https://code.claude.com/docs/en/hooks · https://code.claude.com/docs/en/memory ·
https://code.claude.com/docs/en/sub-agents · https://www.anthropic.com/engineering/claude-code-auto-mode ·
https://platform.claude.com/docs/en/managed-agents/scheduled-deployments ·
https://platform.claude.com/docs/en/managed-agents/dreams ·
https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents ·
https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents ·
https://www.anthropic.com/engineering/harness-design-long-running-apps ·
https://github.com/anthropics/cwc-long-running-agents

Others: https://www.letta.com/blog/memory-blocks/ · https://docs.letta.com/guides/agents/architectures/sleeptime/ ·
https://arxiv.org/abs/2504.13171 ·
https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus ·
https://github.com/agencyenterprise/paperclip-ai · https://docs.devin.ai/product-guides/knowledge ·
https://arxiv.org/abs/2504.19413 · https://arxiv.org/pdf/2501.13956 ·
https://help.getzep.com/graphiti/getting-started/overview · https://arxiv.org/abs/2305.16291 ·
https://arxiv.org/abs/2605.06614 · https://arxiv.org/html/2605.13716v1

Scientists: https://arxiv.org/abs/2502.18864 ·
https://deepmind.google/blog/co-scientist-a-multi-agent-ai-partner-to-accelerate-research/ ·
https://arxiv.org/abs/2511.02824 · https://labs.edisonscientific.com/research/how-we-built-kosmos/ ·
https://arxiv.org/pdf/2605.18831 · https://arxiv.org/abs/2506.13131 · https://arxiv.org/pdf/2408.06292 ·
https://arxiv.org/abs/2504.08066 · https://sakana.ai/ai-scientist-nature/ ·
https://www.nature.com/articles/s41586-026-10652-y · https://arxiv.org/html/2602.15112v1 ·
https://arxiv.org/html/2607.28631 · https://arxiv.org/pdf/2605.26340 ·
https://ai4sciencecommunity.github.io/neurips26

Governance: https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html ·
https://arxiv.org/pdf/2605.23723
