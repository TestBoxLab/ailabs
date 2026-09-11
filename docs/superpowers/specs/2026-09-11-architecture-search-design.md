# The search loop: Monarch's next architecture, found by experiment — design of record

Date: 11 September 2026. Feature 024. Written by Claude for Lucas after an adversarial
review of the Studio by eighteen agents — six reviewers reading the code, six skeptics
refuting them, five researchers reading comparable products — and four rounds of design
questions answered by Lucas the same day.

Supersedes nothing. It sits above feature 022 (Genesis the scientist) and feature 023
(Genesis the engineer) and states what the two loops are *for*, then repairs the
measurement foundations both of them are standing on. Where this note and an earlier
one disagree about the purpose of the architecture editor, this note is current.

Fixed rules this design respects (`PLAN.md` §1, constitution §III, decision D5): nothing
grades itself; a person approves paid rounds; every paid request is reserved in the
weekly ledger before it is sent; task prompts, data and rules are frozen by hash before
any competitor runs; paired comparisons only on identical sets; facts from Monarch's
code are internal-only.

## 1. Decisions taken by Lucas on 11 September

| # | Question | Decision |
|---|---|---|
| 1 | Who reads the Studio | TestBox people — Deyton, Sam, executives. They read results; they never launch. |
| 2 | Who runs a round | The Railway process, unattended. The browser reads and queues. |
| 3 | What the program is for | Auto-improving Monarch: better than bare models with their harnesses, faster, and cheaper to configure and execute than a harness run per prompt. |
| 4 | The gap list | One evidence base, three renderings: Deyton as defects, Lucas as a backlog, executives as a frontier-gap narrative. |
| 5 | Genesis | Genesis is the point. The benchmark is its data source. |
| 6 | The architecture editor | Genesis's hands: how it tests new architectures, prompt styles, product-graph fields and techniques drawn from research. Genesis may ask to extend node types when the abstraction will not hold. |
| 7 | Where a win lands | **The editor is the destination, not a model.** If a composed architecture beats Monarch Enterprise on the frozen set, that composition is the proposal — Monarch should become it. |
| 8 | Cost split | Split a Monarch attempt's cost at the moment the workflow is saved: cost to configure, cost to execute. |
| 9 | What else to measure | Split time the same way; execute a saved workflow N times. |

Decision 7 is the one that reorganises everything. The lab is not running a leaderboard
with an assistant attached. It is running **architecture search over Monarch's design
space, scored by the benchmark**. Every requirement below follows from that sentence.

## 2. What the record says today

Evidence, not opinion. Measured on 11 September against the working tree.

| | |
|---|---|
| Studio | 14,479 lines of Python across 58 modules, plus ~700 KB of frontend |
| Rest of the bench | 17,442 lines (`wb_orchestrator`, `wb_arms`, `wb_report`, `wb_world`) |
| Genesis's share | 6,542 lines, 45% of the Studio; 39 of 77 API endpoints |
| Reports' share | 2 of 77 endpoints |
| Stored runs | 12 Studio jobs, 9 CLI runs; four paid rounds void |
| The headline measurement | The 50-task gauntlet has never run |
| Genesis's lifetime output | 34 turns, US$ 3.87, one paragraph comparing one pass and one fail of the same model on the same task |
| `analyses/`, `skills/`, `people/` | empty |
| `memory/LAB.md` | 801 bytes, managed by 57 KB of memory code |

Two facts from that record matter more than the rest, because the search loop is built
on them.

**The task sets cannot carry an experiment.** Every tier set is ten tasks.
`measures.sign_test` (`wb_studio/measures.py:170`) drops ties, so what decides a paired
comparison is the number of *discordant* pairs — tasks where the variant and the
baseline disagree. Computed from that function:

| Discordant pairs | Wins needed for p < 0.05 |
|---|---|
| 2–5 | impossible at any win count |
| 6 | 6 of 6 |
| 8 | 8 of 8 |
| 10 | 9 of 10 |
| 15 | 12 of 15 |

A variant that genuinely helps typically flips three or four tasks out of ten. **Three
or four discordant pairs can never reach significance, not even with a perfect sweep.**
Run on the sets that exist, the search loop returns `p_value: None` or `p > 0.05`
forever, and Genesis hill-climbs on differences the grader cannot call.

**There is no development / held-out split.** `docs/AI-LABS-DIRECTION.md` asks for one
three times — line 37, line 108, line 129 ("Keep development and held-out evaluation
separate") — and no implementation exists: no split in `workflowbench/tasks/`, no field
in any plan or product file, and no occurrence of the idea anywhere in the source.
Search against a grader finds whatever the grader rewards. Sakana's CUDA-kernel agent
posted a headline speedup that had to be withdrawn because the agent found a memory
exploit that skipped the correctness check. This lab's grader has already been wrong
once, badly enough to void four rounds. Without a held-out slate, every win Genesis
reports is unfalsifiable.

## 3. The shape

One loop, five stations, running on the Railway process.

```
research + prior results + code index
        │
        ▼
   propose a variant ───────────────► the design space:
        │                             architecture composition,
        ▼                             prompt style, product-graph
   build it in the editor             fields, technique from a paper
        │                             (node types extended on request)
        ▼
   run it PAIRED against the frozen Monarch baseline
   on the DEVELOPMENT slate, k repetitions
        │
        ▼
   record: supported / not supported / inconclusive
   with a parent link and the pre-registered prediction
        │
        ├── not supported or inconclusive ──► back to propose
        │
        ▼
   CONFIRM ONCE on the HELD-OUT slate
        │
        ▼
   the gap list → Deyton (defects), Lucas (backlog), executives (narrative)
```

The report an executive reads is a **byproduct of this ledger**, not a separate
product. It carries the curve and the gap list and nothing else.

## 4. The fitness function is the curve, not the pass rate

Score an architecture on accuracy alone and the search will find one that wins by
spending ten times as much — which is the exact thing Monarch is supposed to beat
harnesses at. Lucas's own words for the payoff are the fitness function:

> cost to configure a workflow, cost to execute a workflow < harness run with prompt

A workflow is configured once and executed many times. A harness pays full price every
time. So the comparison is a **break-even curve**:

```
Monarch:  cost_configure + N × cost_execute
Harness:  N × cost_run
```

with a crossing point at some N. That crossing point is Monarch's whole value
proposition, and no product in the evaluation landscape plots it — HELM, LMArena, Scale
SEAL, Braintrust, LangSmith, Inspect and Langfuse all report per-attempt cost, because
their subjects have no reusable artifact. Monarch does.

Three consequences.

**The cost split becomes load-bearing.** `wb_arms/monarch.py:411` `_add_cost` asks
Langfuse for one time window and returns one total. `_author` finishes before
`_start_run` begins and Langfuse generations carry timestamps, so the split is one
boundary, not a new telemetry system. No `phase_cost`, `authoring_cost` or
`cost_by_phase` exists anywhere today; "phase" appears in the Monarch path only as a UI
label on a builder frame (`wb_studio/enterprise.py:461`).

**Time splits the same way.** Time to a saved workflow, then time per execution. The
"faster" claim needs both halves; a harness has only the second.

**N has to be real.** Run-only mode is already built —
`wb_orchestrator/monarch_recipes.py` (309 lines), `config/plans/pilot-monarch-run-only.yaml`
with `mode: run-only`, and `config/products/simulated-apps.yaml:14` declaring all three
modes. `STATE-OF-THE-PROGRAM.md` still lists feature 004 as "specified, not built"; that
is stale. What is missing is data: the only recipes file in the repo is a test fixture.
One `wb monarch recipes` run produces the x-axis.

Scored per successful task, not per attempt — a cheap competitor that fails is not
cheap.

## 5. Layer 0: what the loop cannot run without

None of this is new capability. It is the calibration of an instrument that is about to
be used to make decisions.

### 5.1 A development and a held-out slate

`achievable-50` is fifty tasks, frozen on 8 September. Split the corpus into two frozen
slates drawn by the machinery that already exists (`wb corpus slate --ids FILE --out DIR
--because TEXT`, `wb_orchestrator/slate.py`):

- **development** — Genesis proposes, builds and iterates here, as often as the budget
  allows.
- **held-out** — a variant reaches it once, after it has already won on development.
  A second visit by the same variant lineage is refused by code, not by convention.

Both frozen by hash before the first variant runs; the split seed and every task's
assignment recorded in a manifest, the way `tasks/tiers-manifest.yaml` already records
the tier draw.

### 5.2 Enough statistical power, enforced before the money is spent

- A **repetitions** field, which the Studio does not have. `wb_studio/app.py:433` builds
  the whole job settings dict — `{"models", "arms", "tasks", "maximum_usd", "track",
  "architectures"}` — with no repetitions key; `app.py:435` adds only concurrency and
  components. Until it exists, a Studio-launched round cannot answer the first of the
  six reader questions in the direction doc.
- The development slate is the **default** for a variant test. Ten-task sets stay for
  smoke checks and are refused for experiments.
- An experiment whose **reachable discordant-pair count cannot produce p < 0.05 is
  refused at proposal time**, with the number in the refusal sentence. This is roughly
  twenty lines against the table in §2, and it is the difference between research and
  noise.

### 5.3 A calibrated instrument

Six defects in the numbers Genesis reads to choose its next variant. Each one, left
alone, steers the search.

| # | Defect | Where |
|---|---|---|
| 1 | Every non-Gmail Google call is labelled "Gmail" — a naked substring test on `googleapis`. The only 10-task report prints "Google ads campaign paused … by create in gmail" for a `googleads.googleapis.com` write. | `wb_studio/reports.py:52` |
| 2 | "Said the work was done when it was not" is a regex over `result["output"]`, which holds the lab's own prompt text when an agent hits its turn limit. It is promoted to a numbered finding as fact. | `wb_studio/measures.py:103`, `report_data.py:212` |
| 3 | Non-regradable attempts are drawn in every chart with no mark; nothing compares a stored task hash to the live corpus. Run `6022e89f` has 4 of 10 hashes moved and reports "20%, 95% CI 6–51". | no liveness check exists |
| 4 | Two failure classifiers run over the same attempts and disagree on 8 of 8, side by side in one report section. | `failure_analysis.py:36` vs `narrative.py:174` |
| 5 | The hero bar is labelled by reasoning level — `short_name()` strips any segment containing `@ + /`, which is the model and the version. | `report_data.py:242` |
| 6 | A chart titled "Monarch pass rate by run" is hardcoded, over cohorts containing no Monarch. | `static/reports.js:329` |

A seventh, of a different kind: the round report pools runs the leaderboard module would
refuse to pool. `report_data.py:408` keys a cohort on task hashes plus track;
`leaderboard.py:50` keys the same idea on task hashes, track, judge, assistance, world
manifest and workflow contract, and stamps unpinned cohorts provisional. The stricter
partitioning is already written and tested; the surface a person opens reimplements a
weaker one.

### 5.4 A grader that survives being attacked

Every approval rule a composed architecture can satisfy without doing the work is a
local optimum the search will find. Before Genesis runs free, run the current rules
against a deliberately lazy architecture — one that claims success and changes nothing,
and one that changes everything — and record which rules it beats. Rules it beats are
repaired under the existing procedure (`AGENTS.md`: reproduce against the unchanged
simulator, preserve prior rules, record old and new hashes in `docs/rounds/`).

## 6. The gates, which are now maximally load-bearing

If Genesis is the scientist and it launches, the money and safety gates stop being
hygiene and become the thing standing between an autonomous researcher and an
autonomous researcher that burns the week in an afternoon and then cannot run at all.

| # | Defect | Where |
|---|---|---|
| 1 | `/front-door` is an anonymous write proxy into the running attempt's world. `do_GET`/`do_POST` check it *before* `authorised()`; `do_PUT`/`do_PATCH`/`do_DELETE` never call `authorised()` at all. Anyone with the Railway URL can PATCH or DELETE a record mid-attempt, and the approval rule reads it as the competitor failing. | `app.py:899-903`, `app.py:870-889` |
| 2 | Genesis is on by default with `runs: 'smoke'`: `DEFAULTS = {'cards': 'act', 'runs': 'smoke', 'initiative': 'off', 'paused': False}`, and the watcher and scheduler start unconditionally. A fresh Studio with keys begins working cards within 30 seconds. | `genesis_autonomy.py:25`, `app.py:1316` |
| 3 | Pause is not a kill switch. `genesis.chat` — the funnel every paid turn goes through — never reads the dial. Six scheduled jobs spend through a Pause. | `genesis.py:528` |
| 4 | The US$ 6 daily allowance counts only Genesis's own turns, never the runs it launches. N self-launched runs each pass the same test. | `genesis_watcher.py:91` |
| 5 | The weekly envelope is off by orders of magnitude: person-initiated turns are attributed away from Genesis, running holds count as their settled pennies, unknown holds vanish. | `genesis.py:548`, `usage.py:23`, `genesis_access.py:146` |
| 6 | A single over-settled reservation blocks every paid path in the lab permanently; the query has no week filter and there is no override, expiry or cancellation. | `wb_orchestrator/budget.py:269` |
| 7 | `fetch_source` is an unrestricted SSRF primitive reachable from a POST and from the model — no host allowlist, no private-range block, no redirect limit. On Railway that reaches the metadata endpoint and sibling services, and the body is stored and rendered. | `genesis_ingest.py:121` |
| 8 | The Studio front door names no operator and never calls the approval module. `wb_orchestrator/approvals.py` implements decision D5 in full; nothing in `wb_studio/` imports it. | `app.py:1285` → `app.py:348` |
| 9 | No per-attempt cap: `Studio._execute` passes no run config, so `attempt_cap_usd` stays `None` and every arm gets the whole run ceiling as its scope limit. | `app.py:617` → `orchestrator.py:116` |

Defects 1 and 2 are live on a public URL today and are not gated on any decision in this
note.

## 7. What the loop costs, and therefore how fast the lab can learn

Fifty tasks × three repetitions = **150 attempts per variant**; the baseline rows are
reused rather than re-run, which `report_data.historical_baseline` (`report_data.py:356`)
already does. At US$ 0.10–0.30 an attempt that is **US$ 15–45 per experiment**, so a
US$ 300 week buys roughly **7 to 20 experiments**.

That number is the lab's research throughput, and it is the number that belongs on the
Genesis page — not `today_usd / $6.00`.

It also sets the standard for a proposal. At seven to twenty experiments a week, a
variant that has not been argued from research or from a prior result is not cheap
curiosity; it is a fifth of a week.

## 8. What this design does not build

- **No new reporting surface.** The curve and the gap list replace the round report's
  hero section; the rest of the reporting layer is unchanged.
- **No second measurement stack.** `measures.py` stays the single server-side
  calculator. The one re-implemented Wilson interval in `difficulty.py` is deleted in
  favour of it, not joined by a third.
- **No change to the methodology.** `PLAN.md` §1 is untouched. This feature changes the
  inputs — a new split, a repetitions field, a cost boundary — never the rules.
- **No autonomy expansion.** Genesis's dials, allowances and approval path are repaired,
  not widened. A variant test at fifty tasks is above smoke scale and therefore needs
  the human approval flow, which the Studio does not currently call.

## 9. Order of work

| | What | Why it is here |
|---|---|---|
| 0 | Development / held-out split, frozen with a manifest | Without it every result the loop produces is unfalsifiable |
| 1 | The six integrity defects of §5.3 | Genesis reads these numbers to choose the next variant |
| 2 | The gates of §6, starting with 1 and 2 | Genesis spends autonomously; two defects are live on a public URL |
| 3 | Repetitions field; development slate as the default; refuse under-powered experiments | 3–5 discordant pairs can never return p < 0.05 |
| 4 | Split cost and time at the authoring boundary; generate the recipes so N is real | This is the fitness function |
| 5 | Close the ledger loop; the held-out confirmation gate | Seven hypotheses proposed, zero tested |
| 6 | The curve and the gap list | Writes itself once 0–5 hold |

Stations 0 to 2 are repairs and can run in any order. Station 3 depends on 0. Station 6
depends on all of them.

## 10. Open questions

1. **Which tasks go to held-out, and who draws them?** A random split by seed is
   defensible and cheap. A stratified split by difficulty tier and domain is better and
   needs the tier scores. Either way the draw is recorded and never redrawn; redrawing
   a held-out slate after seeing results destroys it.
2. **What makes a composed architecture a Monarch proposal?** Decision 7 says the editor
   is the destination. A winning composition must therefore be expressible as something
   Monarch Enterprise could become. Whether that is a written spec for Deyton or an
   executable artifact is unsettled, and it changes what node types have to mean.
3. **Who approves a variant test?** At fifty tasks it is above smoke scale, so decision
   D5 requires a person. Seven to twenty experiments a week is seven to twenty approvals
   a week. Whether that is a per-experiment approval or a standing weekly envelope with
   a per-experiment ceiling is Lucas's call, and it is the difference between a loop
   that runs overnight and one that waits for morning.
4. **Does the gap list include findings the search cannot test?** The code index reads
   Monarch's checkout and can name what is not yet at frontier. Those are claims about
   code, not experimental results, and they must not be rendered as peers of a confirmed
   win.

---

## Appendix: the voice work, S0 to S6 (11 September 2026)

Lucas asked for "a pulsing circle that listens and answers in voice in app and navigates
through the browser as to take the user to what its changing, it shows the changes live
streaming". Six researchers read the speech APIs, voice agent design, agent-driven
navigation, live-change rendering, the privacy and money position, and the accessibility
obligations. The design that came out is recorded in `.tmp/genesis-voice.md`; what was
built is below.

**The orb became honest the moment there was real audio.** The earlier pass refused it
because a pulse on an agent doing typed tool calls claims "I can hear you" about work
happening off-screen. With a microphone the pulse is a *measurement*: it is driven by the
signal's own RMS envelope, so it fails visibly at a muted mic. It is a capture indicator
and never an activity one — the minutes Genesis spends on tool calls keep the step list.

| | Delivered | Commit |
|---|---|---|
| S0 | Five infinite animations removed; **Pause updates**; four new checks in the CSP test | `9635bb8` |
| S1 | `show` as a link, never a move | `42cb031` |
| S2 | SSE replaces the 650 ms poll; flash on arrival | `b89b7e1` |
| S3 | Hold to talk; amplitude-driven mark; on-device recognition or nothing | `72588d2` |
| S4 | Answers aloud, local voices only, off by default | `db8ebc9` |
| S5 | Follow Genesis, off by default, broken by any gesture | `a3dc93c` |
| S6 | `POST /api/voice/stt`, reserved and settled in the weekly ledger | `954676a` |

### The finding that shaped all of it

**The CSP test cannot see the privacy risk, and neither can the browser's own
machinery.** `webkitSpeechRecognition` is a built-in, so `processLocally: false` ships
every utterance to Google over a channel that raises no `securitypolicyviolation`, shows
nothing in the network tab, and leaves the check green. This screen carries provider API
keys and unreleased benchmark results.

So there is no fallback to remote recognition anywhere in the code. On-device or the
typed box; and when a browser cannot, S6 sends the clip to *our own origin* and the
Studio calls the provider with the key it already holds, reserved in the ledger. A
`network` speech error is reported to the reader as "Refused: that would have sent the
audio off this machine."

### Three rules worth keeping

- **Motion is declared inside `@media (prefers-reduced-motion: no-preference)`**, never as
  a `reduce` override. The blanket rule at the end of `ui.css` cannot stop a transform
  written from JavaScript, so an amplitude-driven indicator would have reached a
  reduced-motion reader at full swing while the sheet appeared to cover it. The check
  added in S0 now enforces the opt-in form.
- **Under `reduce` the orb is replaced, not frozen** — five discrete blocks at 2 Hz. A
  frozen orb conveys nothing and removes the only live evidence the microphone works.
  This is the path that got exercised in verification: the headless browser reports
  `reduce`.
- **`announce` never speaks a string that is not already on the page.** Such a string
  still reaches the live region, because that is text and not audio. That one rule keeps
  the whole WCAG 1.2 media family out of scope, and it is enforced in the function rather
  than asked for in review.

### Refused, with reasons

Always-on listening and wake words (two people share that room and one takes calls;
push-to-talk has no pre-roll buffer by construction). Realtime speech-to-speech (its
product is sub-second latency; a Genesis turn is minutes of slow tool calls, and a held
session bills audio input across all of it — about US$9.30 an hour against a US$6.00
daily allowance). Gemini Live from the browser (it needs a `wss://` origin, which costs
the same-origin invariant, and its free tier states submitted content may be reviewed).
Local Whisper in WebAssembly (`'wasm-unsafe-eval'` plus hundreds of megabytes of weights,
or a fetch-and-cache step, which is a build step by another name). A spotlight overlay (a
modal dialog in a costume). A synthetic cursor (theatre that tells a screen reader
nothing). Speaker identification or diarization. An API key in the page.
