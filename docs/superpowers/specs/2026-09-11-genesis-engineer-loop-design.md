# Genesis as the lab's engineer: a daily diff, a weekly adversary — design of record

Date: 11 September 2026. Feature 023. Written by Claude for Lucas after an adversarial
read of features 019 to 022 — the code and, more usefully, Genesis's own runtime record in
`out/studio/genesis` — a research pass over comparable systems, and two rounds of design
questions answered by Lucas the same day. Supersedes nothing; it adds a second loop beside
the scientist built in features 019 to 022, and repairs three defects that loop is standing on.

Fixed rules this design respects (`PLAN.md` §1, constitution §III, decision D5): nothing
grades itself; a person approves paid rounds; every paid request is reserved in the weekly
ledger before it is sent; facts from Monarch's code are internal-only; the Studio never
applies a patch and never runs Monarch's code.

## 1. Decisions taken by Lucas on 11 September

| # | Question | Decision |
|---|---|---|
| 1 | What Genesis hands over | A card carrying a checked diff. The Studio never applies it. |
| 2 | Which loops | Two: failed runs → Monarch patches, and failed runs → WorkflowBench fixes. Both arrive as proposal cards. |
| 3 | What a card carries | Rich reports: the Studio's own charts, the diff with its apply-check and test output, before/after screenshot crops. |
| 4 | What starts it | A daily job at 08:00 America/São Paulo. Runs already analysed are checked off and never redone. |
| 5 | The gradient | A weekly adversary: a *different* agent reviews the lab's output against written rubrics and proposes enhancements as cards. |
| 6 | What the adversary reads | All three: the rendered pages through the browser suite, the report prose and data, and the Studio source. |
| 7 | Who writes the code | Genesis writes the spec; a Codex agent implements it, with model and thinking configurable. |

Decision 7 does not reverse the 10 September removal of the Codex subprocess. That removed
Codex as the *reasoning engine* of a Genesis turn — a second provider layer, its own
instructions above `SOUL.md`, a Windows-only binary path, a 600-second wall, and a
`--sandbox read-only` flag that made writing code impossible anyway. Codex returns here in
the opposite role: not the mind, but the hands, called once per spec, with the reasoning
already done.

## 2. What the record says today

Genesis has run. The evidence is its own state directory, not an opinion.

| | |
|---|---|
| Turns / spend | 34 / **US$ 3.87**, 11 failed (32%) |
| Model requests | 361, of which **64 were killed** (18%) with "Request stopped. Any uncertain charge remains reserved." |
| Those 64, by the tool that preceded them | `read_run` 29, `record_analysis` 17, `report` 8 — the three tools that read a run's full event log |
| `record_analysis` | **17 calls, 0 files in `analyses/`.** The guard the protocol advertises — "so unchanged evidence is not analysed twice" — has never once worked |
| `hypothesis_check` | 11 calls, **9 refused on schema** |
| Tool calls | 355, of which 54 returned an error (15%) |
| Cards | 15, of which **ten were created in 28 minutes** on 10 September, eight carrying the same title, for about US$ 3.05 of the US$ 3.87 |
| Cards reaching stage `complete` | **0** |
| Patch cards ever proposed | **0** |
| `propose_experiment` calls, all time | **1** |

**Read this table with one caveat: 30 of the 34 turns ran on the Codex subprocess that the
10 September rewrite deleted.** Only four ran on the in-process loop that ships today, and two
of those failed on lab faults (`TypeError`, `infra:harness_crash`) with nothing written to the
activity record. So most of the request failures above are evidence about a harness that no
longer exists. What carries forward is everything in §3, which is read from the code as it
stands, and the two defects Layer 0 fixes, both still live.

The 28-minute stretch is the whole failure in one trace. The watcher's trigger filed a card
for the finished run; Genesis worked it and, through `save_research`, changed the card's
`kind` from `run` to `hypothesis`; the trigger's dedupe key is built from that `kind`, so on
the next wake the run looked unfiled and got a fresh card — every 60 seconds, for 28 minutes.
Nothing stopped it except the daily cap of US$ 6.00.

The one genuinely useful output in the record cost US$ 0.456 and 24 requests: GLM 5.3 passed
`simple.email_sf_contact_city_update` in one run and failed in another through an unrequested
`mailing_state` write. That finding is real, cited and worth having. It is also the only one.

## 3. Why the present design cannot do what was asked

**No hands.** Of roughly 33 tools, every one either reads a record or writes a card. Nothing
writes a file, runs a test, or renders a page. The output ceiling is a document.

**Wrong repository.** `code_index.settings()` resolves `MONARCH_REPO`, else `../monarch`.
Genesis cannot read one line of `report_data.py`, `report.css` or `reports.js` — the files
being repaired by hand this week are outside its world entirely.

**No eyes.** `tests/browser/suite.cjs` already renders every view in both themes and writes
snapshots. No Genesis tool touches it. Separately, `wb_arms/api_loop.py` has no image
support at all: the four provider adapters send text only.

**Initiative never reads a run.** The four rules in `genesis_initiative.py` are unsettled
hypothesis, inconclusive settlement, contradicted source, unused source. Not one of them
looks at a run. The behaviour asked for — wake up and analyse the latest runs — is not in the
rule set, and the dial defaults to `off`.

**It pays to restate what is already free.** `narrative.py` writes failure modes from a fixed
list of nine, deterministically, at zero cost; `measures.py` and `failure_analysis.py`
compute the buckets. The paid turn's only marginal contribution is the causal claim and the
fix. It produces the first and cannot produce the second.

**The Reviewer is not a gradient.** A model judging a model's card, one revise allowed, never
compared against an outcome. One `request_review` call in the whole record.

## 4. What comparable systems do

**Sentry Seer** is the closest working analogue and it works because it is narrow: a typed
trigger (an issue with ten or more events and a fixability score at medium or above), a fixed
pipeline `ROOT_CAUSE → SOLUTION → CODE_CHANGES → OPEN_PR`, and — since January 2026 — a
**handoff** of the final code generation to an external coding agent rather than owning it.
Sentry runs it on their own repository and hit the second-order problem at once: more pull
requests than anyone could triage, answered with a channel and a triage routine. Their 94.5%
figure is vendor-reported, unaudited, and measures root-cause *identification*, not merge rate.

**AIDE** is the loop that compounds, and the reason is a number that goes up: tree search over
solution code, each node scored by a metric, feedback pruning the tree. Four times the medals
of the best linear agent on MLE-bench. Its documented poison is a *hallucinated* metric, which
locked the search onto a dead node and stalled it. The gradient must be computed by something
the agent cannot write.

**Visual QA agents** answer the report problem: a browser runner produces structured artifacts
— screenshots, console, network — a judge compares them to a baseline, and the diff is handed
to the agent where it already looks. The load-bearing detail is crop granularity: a full-page
screenshot will not surface a padding change; side-by-side crops will. The summary that
matters: the frontend agents that work are the ones that can inspect the *running application*,
not only the repository.

**Sakana's AI Scientist** is the cautionary tale and it is Genesis's exact shape. The
independent evaluation found 42% of experiments failing on coding errors, a median of five
citations, hallucinated numbers — and a self-reviewer that recommended rejection on **seven of
seven** of its own papers while missing every real defect the human evaluators found. An
LLM reviewing an LLM is not a gradient. Decision 5 takes the point seriously by making the
adversary a *different* agent working from *written rubrics*, and Layer 1 below keeps a free,
objective gate underneath it that no model can write.

## 5. The design

### 5.1 Layer 0 — three repairs, landed 11 September

Nothing below is safe until these are done. Each is small. The diagnoses below are the ones
that survived reading the turn records; the first two are **not** what this note said in its
first draft, and §2 now carries the caveat that made the difference.

1. **The trigger's memory of what it filed is its own, not the card's.**
   `Watcher.triggers()` deduplicated on `(card.kind, evidence.kind, evidence.id)` — and
   `save_research` lets the model rewrite both `kind` and `evidence`. A card Genesis relabelled
   from `run` to `hypothesis` fell out of the key, so the next wake filed the same run again,
   and the next, for ever. The watcher now keeps a list of filed keys in `watcher.json`, which
   no tool can touch, and checks it beside the old card scan. *(A rolling window of 5,000 keys;
   a lab that files more than that wants the set in the index, not in one JSON file.)*
2. **`read_run` names its run the way every sibling does.** `measures`, `compare`,
   `failure_buckets`, `report` and `record_analysis` all take `run`. `read_run` alone took
   `id`, and the model — reasonably — sent `run`: 28 of its 47 calls were lost. The schema now
   requires `run`; `id` stays accepted for callers written against the old name. Separately,
   `record_analysis` checks the shape of `findings` *before* it reads the run, which it used to
   page twice, the second time holding `genesis.lock`.
3. **The code index takes a repository.** `code_index.settings(studio, repo)` resolves
   `monarch` (the product under test, unchanged) or `lab` (the Studio's own checkout), and all
   five code tools take `repo`, defaulting to `monarch`. The daily job builds both;
   `MONARCH.md` and the library change record stay Monarch's. Code facts from either checkout
   keep the internal-only marker — one rule, nothing to get wrong.

Verified: the lab index builds over 2,723 tracked files and `code_search {repo: 'lab'}`
resolves `ledger_lines` to `wb_studio/usage.py:10`. Four tests in
`tests/test_genesis_repairs.py`; 260 tests green across the Genesis surface.

### 5.2 Layer 1 — two abilities Genesis has never had

4. **Eyes.** A `ui_snapshot {view, theme, selector?}` tool runs the offline fixture Studio that
   `tests/browser/suite.cjs` already starts, and returns a PNG path plus the accessibility
   tree. `suite.cjs` gains a `clip`/locator path so a crop is possible; `fullPage: true`
   stays the default. Snapshots are artifacts on disk, never pasted into a card body.
5. **Image input.** `wb_arms/api_loop.py` gains image content blocks for the Anthropic and
   Gemini adapters, behind the same shape function the tool definitions already use. Without
   this, decision 6 cannot be honoured: the adversary cannot see the page it is reviewing.

### 5.3 The daily engineer job — 08:00 America/São Paulo — built 11 September

`wb_studio/genesis_engineer.py`, offering `DAILY = ('genesis-engineer', 8, engineer)`, registered
in `scheduler.MODULES` after the 04:00 code index and the 07:00 initiative, and in
`genesis_plugins.MODULES` for its `ON_TURN`.

1. **Pick the work.** Every finished run that is not settled, newest first. A run is settled by
   the *job*, in code, never by the model: the key is the existing fingerprint
   `digest({run, results, events})`, written to `genesis/engineer/seen.json`. A regraded run's
   fingerprint moves, so it is looked at again; an unchanged one never is. Scripted-only runs
   are skipped, as the watcher already skips them.
2. **Read the free machinery first.** `failure_buckets` before any paid request. A run whose
   buckets all name the setup, the task, the harness, the budget or a cancellation is settled
   without a turn, because none of those is a defect in anyone's code.
3. **One spec per failure bucket, not per run.** The worst actionable bucket by count earns the
   spec; a bucket whose signature `<bucket id>@<run>` already has an open card is skipped.
4. **Genesis writes the spec** in one turn. The spec is a typed record, validated before
   anything runs: `failure`, `repo` (`monarch` or `lab`), `location` (`path:line`), `commit`,
   `change` (sentences, not a diff), `verify`, `reasoning`. A spec that does not validate, or
   that names a commit other than the indexed one, is refused in a sentence and no agent starts.
5. **Codex implements it** (§5.4), **the Studio runs `verify` itself**, and the card is written
   (§5.5). Only then is the run settled.

A spec turn that fails or is refused leaves the run unsettled for one more day and counts a try;
after three the run is left alone. One spec per job run, not a daily quota — a person who wants
another runs the job again from the schedule. The ceiling is `STUDIO_GENESIS_ENGINEER_USD`
(default 3.00) for the spec turn and `STUDIO_GENESIS_CODEX_USD` (default 1.00) for the agent,
both reserved in the weekly ledger. A day with no new run costs nothing.

### 5.4 The Codex handoff — built 11 September

`codex exec --json --ephemeral -C <worktree> -s workspace-write -m <model>` in a **detached git
worktree** at the spec's commit, in a temporary directory. The agent may write files and run
commands inside that worktree; it may not push and may not touch the checkout's branches.

Three things are the Studio's, not the agent's:

- **The verify command is an allowlist.** `VERIFY_ALLOWED` accepts
  `uv run --directory monarch-benchmark/workflowbench python -m pytest <path> [-q]` or
  `node tests/browser/suite.cjs`, and nothing else. A spec naming anything else is refused
  before a worktree exists. A model choosing what the lab executes is a trust boundary, and an
  allowlist is the cheapest honest gate.
- **The Studio runs it, and the Studio's exit status is the verdict.** What the agent says it
  ran is not read back. Where no test can run the diff comes back unverified and the card says so.
- **The money is fixed then settled.** `STUDIO_GENESIS_CODEX_USD` (default 1.00) is reserved and
  claimed before the agent starts; on exit `usage_of` reads Codex's JSONL for
  `input_tokens` / `cached_input_tokens` / `cache_write_input_tokens` / `output_tokens` /
  `reasoning_output_tokens` wherever they sit, preferring a `total_token_usage`, prices them with
  the route's own card and settles. Usage that cannot be read settles `None`, which is the
  ledger's rule for unverified billing: **the ceiling stays held.** Reasoning tokens are added to
  output, which can only overstate the cost — the safe direction for a budget gate.

Captured, then the worktree is removed: `git add -A` and `git diff --cached`, so a new file is in
the diff too; the verify status and its last output; the cost. Nothing is merged, pushed or applied.

`genesis_config.STEPS` gains `implement` and `critic`, both in `DEFAULT_STRONG`, and the
configuration gains an `effort` map beside `models` (`minimal`, `low`, `medium`, `high`), passed
to Codex as `-c model_reasoning_effort=`. The implement route must be one Codex can run — today
`gpt-5.6-sol` or `gpt-5.6-terra`; a route Codex rejects fails visibly with its own stderr on the
card. No Codex executable means the spec is filed without a diff and the card says why.

### 5.5 The card

Kind `patch` for a Monarch spec (internal-only, as today) and a new kind `fix` for a lab spec.
Stage `review`, `auto` false — **a card Genesis writes for itself is never worked by the
watcher**, which is Layer 0 repair 1 restated where it bites.

The body, in this order:

1. **The verdict in one sentence**, then the failure it addresses and the bucket's share.
2. **The evidence**, as the Studio's own charts: the failure buckets, the pass rate with its
   Wilson interval, the paired delta against Bare where one exists. Rendered by `charts.js`,
   numbers computed server-side, so the model cannot write them.
3. **The diff**, with whether it applies at the named commit and what `verify` said.
4. **Before and after crops** for anything that changes a view.
5. **The reasoning**, in sentences without numbers, and the record ids each fact rests on.

The turn's tool trace is not duplicated into the card; it already lives in Trace.

### 5.6 The weekly adversary — built 11 September

`wb_studio/genesis_critic.py`, a daily-shaped job at 09:00 that acts only on the lab's digest day
(`genesis_access.settings()['digest_day']`, Monday by default), on the route named by the new
`critic` step — a *different* model from `reading`. Where the lab has only one keyed route the two
collapse; the job says so in the prompt and on the record rather than pretending otherwise.

**It sees the pages.** Two things that did not exist had to be built first:

- `wb_arms/api_loop.py` gained `images_of` and an optional `images` argument on all four adapters'
  `start`, each in its provider's own content shape. `Genesis.chat` keeps at most eight paths on
  the turn; the harness hands them to `start`.
- An image is billed **by tile, not by the length of its base64**. Left in the harness's character
  estimate, one 200 KB screenshot counts as about 135,000 input tokens and reserves the whole
  turn's allowance against itself. `IMAGE_DATA` strips base64 runs out of the estimate and
  `IMAGE_TOKENS` counts each image once instead.
- `tests/browser/shot.cjs` renders one view and writes a full-page PNG, a **crop** of the element
  that matters, and a measured layout record. It is deliberately not part of `suite.cjs`: that
  writes the review snapshots, and the critic must never overwrite them.

**The measured record is the gradient.** Overflow, clipped elements, the smallest text, the lowest
contrast ratios by WCAG's own formula, the tables, the heading order — decided by the browser, not
by the critic. Rules F10 to F13 of the figures rubric are settled before the model is asked
anything, and the critic's job on those is to say what to do. This is what Sakana's reviewer never
had, and it is why the loop can compound.

**The rubrics are files a person edits**, under `wb_studio/rubrics/`: `prose.md` (Wikipedia's
*Signs of AI writing*, narrowed, plus the lab's standing corrections), `figures.md` (the design
system as fifteen rules), `accuracy.md` (`PLAN.md` §1 as eleven). `rubric_lines()` reads the ids
out of the files themselves, so a finding citing a line that does not exist is refused and files
no card. Thirty-eight ids today.

**Output:** one enhancement card per finding, at most six a week, each naming the page, the rubric
line, what the reader loses and what to do. A finding carrying a valid spec goes through the
engineer's Codex handoff — **at most one a week** (`STUDIO_GENESIS_CRITIC_FIXES`), so the review
cannot become an agent farm. A week with nothing to say costs one line in the activity record.

The adversary reviews the lab's *output*, not Genesis's cards. Underneath it, the apply-check and
`verify` of §5.4 stay the free objective gate on every diff.

*The first render already found one: 4.1:1 contrast on 11px text on the Runs page in the light
theme, against F12's 4.5:1.*

### 5.7 The dial

A fourth dial in `genesis_autonomy`: `engineer` is `propose` (the job runs, specs are written,
Codex implements, cards wait for a person) or `off`. There is no `act` level. The Pause switch
covers it like everything else, and `may_launch` is untouched — nothing here launches a run.

**It starts `off`,** like `initiative` did, because turning it on lets an agent write files on
the lab's machine. A person turns it on in Settings › Genesis, where the dial states in one line
what it will do.

### 5.8 The prompts, and why they are shaped that way

Three prompts carry this feature: the spec writer (§5.3), the Codex implementer (§5.4) and the
critic (§5.6). All three were rewritten on 11 September against the current literature on judges
and structured output. Four rules, applied to each:

**Reasoning before the verdict.** Every schema puts `analysis` first — what was read, quoted —
because a schema that asks for the conclusion first gets a conclusion and then a rationalisation
of it, and the chain of thought degenerates into decoration. The field is also named so it sorts
first alphabetically: at least one provider returns structured output with keys sorted rather than
in the order they were asked for, which silently reverses the ordering everywhere else.

**A legal way to fail, that lands somewhere.** The commonest source of confident invention is a
constraint with no way to comply: a model told to find the cause, in a run where the cause is not
in the code, will invent a location rather than disobey. So the spec writer may answer
`"found": false` — recorded as `no-cause`, which settles the run, because asking the same model the
same question about the same evidence tomorrow buys nothing. The Codex agent may make no edit and
say why; its last message is read back and shown on the card. The critic may return `"findings":
[]`, and the prompt says in as many words that an empty week is a correct answer and a good one. A
hatch that leads nowhere is worse than no hatch, so each of the three is handled in code.

**No claim without a quote.** A finding or a spec whose `analysis` is under 40 characters is
refused. This is the cheapest guard against the failure the research names directly: a model asked
for three findings and given no way to return none will produce three, including the one it
invented to fill the slot.

**The judge is told when it is marking its own homework.** `same_family` compares the provider
family, not the route id, so `claude-opus-4-8` judging `claude-opus-5`'s prose counts. Self-
preference is a measured effect of ten to twenty-five percent; where it applies, the turn is told
to hold the prose findings to the quote rule harder and to say so in the finding.

Underneath all of it, the numeric rules (figures F10–F13) and the `verify` exit status are decided
before any model is asked anything. That is the part that makes this a loop rather than a
conversation.

### 5.9 Figures in a card, and a card worth fifteen seconds — built 11 September

A card that says "contrast is 4.1 where the rule wants 4.5" is a card about a number, and a number
is faster seen than described. `wb_studio/figures.py` lets Genesis put one in, without letting it
near the drawing.

**Genesis names a kind and a run. That is all it controls.** `figure {kind, run, caption?}` returns
an id; `[figure:<id>]` on its own line in the body is where it is drawn — the same tag shape as the
`[rec:kind:id]` the record already uses. The Studio computes the figure from
`report_data.run_report`, the same numbers the report itself shows, and stores the drawing options;
`static/charts.js` draws them with the design system's own classes. A test passes the tool a forged
`chart`, forged `options` and a forged `source` alongside the caption and asserts all three are
dropped: **the model writes the caption and nothing else.**

Four kinds today, each mapping to a chart the Studio already draws: `pass_rate` (dot-whisker with
the 95% interval), `failures` (the buckets as columns), `cost_against_pass_rate` (scatter, log cost
axis), `tasks` (the matrix). The catalogue is the single source — the tool's schema enum is read
from `figures.KINDS`, so a kind added there reaches the model without a second edit. A run that
cannot carry a figure is refused in a sentence ("No setup in this run has a known cost, so cost
cannot be drawn"), never drawn empty. Every figure carries its source line, written from the run's
own record, which is rubric F6 enforced in code rather than asked for in a prompt.

**The card is shaped to be read, not waded through.** A finding's body is the claim in one
sentence, then a label column — Fails, Where, Evidence, Costs the reader, Diff — then the fix, then
the figure. Capped at 6,000 characters and asserted under 900 in the test. The prompt says it
plainly: *write for someone who reads this in fifteen seconds; if "why_it_matters" needs a
paragraph, you have not worked the finding out yet.*

Verified end to end in a browser: a seeded enhancement card renders both figures as real SVG inside
the card body, each with its source line, its caption, and the chart kit's own Download SVG / CSV
links inherited for free.

## 6. What this deliberately does not do

- It never merges, pushes, opens a pull request, or applies a diff. The Studio's hands stop at
  a card.
- It does not make the scientist loop autonomous. `initiative` stays off until someone turns
  it on.
- It does not let a model write a number. Every figure and measure in a card is computed by
  the Studio.
- It does not review its own diffs with a model. The gate on a diff is apply-check plus the
  `verify` command.
- It does not touch the methodology. `PLAN.md` §1 is unchanged; a lab fix that would change a
  grader, a task or an approval rule is refused in the spec validator and raised as a question.

## 7. Open questions

1. ~~Codex billing against the weekly ledger.~~ **Settled by Lucas, 11 September: a fixed
   reservation per spec, settled from the usage Codex reports.** Built as described in §5.4.
2. ~~Which Codex build and where.~~ Resolved in code: `STUDIO_CODEX_BIN`, else `codex` on PATH
   (`codex-cli 0.153.4` here); absent, the job files the spec without a diff and says so.
3. **Whether the critic's enhancement cards also go through Codex** — assumed yes, since the
   pipeline is the same; confirm when §5.6 is built.
4. **Crop selectors.** Who names them: the spec's author each time, or a fixed map of view to
   the selectors worth watching.
5. **The Codex spend is outside the watcher's daily cap.** `Watcher.today_usd()` counts Genesis
   *turns*; an agent run is not a turn, so only `STUDIO_GENESIS_CODEX_USD` per spec and the
   weekly ledger hold it. At one spec a day that is at most a dollar; it wants a real daily line
   before the cadence rises.

## 8. Sources

- Sentry, *Seer* product and docs; *Seer is generally available* changelog; the January 2026
  press release on local development, code review and coding-agent handoff.
- Beel, Kan & Baumgart, *Evaluating Sakana's AI Scientist* (arXiv 2502.14297, ACM SIGIR Forum).
- Jiang et al., *AIDE: AI-Driven Exploration in the Space of Code* (arXiv 2502.13138); OpenAI
  *MLE-bench*.
- *Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops*
  (arXiv 2607.07663), on loop closure and the measurement gap.
- Practitioner writing on visual QA agents and crop granularity (dev.to, Autonoma, AutonomyAI).
- Wikipedia, *Signs of AI writing*.
- Zheng et al., *Judging LLM-as-a-Judge with MT-Bench* — position, verbosity and self-preference
  bias, and the 80% judge-to-human agreement figure; plus *Judging the Judges* (arXiv 2604.23178)
  and *JudgeSense* (arXiv 2604.23478) on bias mitigation and prompt sensitivity.
- *One Token to Fool LLM-as-a-Judge* (arXiv 2507.08794), on judges swayed by superficial tokens.
- Castillo, *Structured outputs: don't put the cart before the horse*, and the Gemini cookbook
  issue on key ordering, for reasoning-before-conclusion field order.
- The escape-hatch pattern (bt2go/prompt-patterns #14) and OpenAI's GPT-5 prompting guide, for
  authorised abstention and its inverse in agentic context-gathering.
