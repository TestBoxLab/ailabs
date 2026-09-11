# Genesis as a spoken colleague that builds the Studio live — design of record

**Date**: 2026-09-11
**Present**: Lucas (decisions), Claude (research and design)
**Feature**: `specs/025-genesis-voice-live-build/`

## What was asked

Lucas asked for a Genesis he can talk to on the website, that answers like a person,
that has full access to the AI Labs code, that changes the site live while they talk,
and that knows everything it has done — its research, its runs, its analyses — while
carrying the best of the public state of the art.

This document records what the landscape pass found, the three decisions Lucas made,
the architecture those decisions produce, and what was deliberately left out.

## The landscape pass

A survey of public agents and repositories building the same shape, on 11 September
2026. The full source list is in the feature's `research.md`; the mechanisms this
design adopts are named below with their evidence.

The closest structural twin is **Hermes Agent** (Nous Research, open source, February
2026), which converged independently on the same memory design the Studio already has:
always-loaded identity and memory files, a SQLite FTS5 fact store rather than vectors,
skills as markdown the agent writes for itself, and a cron for unattended work. That
convergence is treated here as validation, not as a thing to copy.

Three mechanisms from elsewhere are adopted because each closes a hole this feature
would otherwise open. They are described in "The three mechanisms" below.

Four further mechanisms were identified and deliberately deferred: funnel economics for
proposals (ScholarLoop), evaluation-gated skill authoring (SkillAxe, against the
SkillsBench finding that model-authored skills show no measurable gain), the
self-refutation gate (ARA Research Artifact Protocol), and publishing the harness
minimum detectable effect (Miller, *Adding Error Bars to Evals*). They are recorded in
`monarch-benchmark/workflowbench/deferred.md` with their sources.

## The two facts that decided the architecture

**One.** `gpt-live-1` is not a brain. It is a full-duplex voice model that delegates
reasoning and tool use to a backend, and its design point is that the conversation
continues while background work runs. It offers two delegation modes, and the second —
client delegation, documented as the mode for "when your application needs to control
backend execution, context, or which results reach GPT-Live" — puts the Studio in
charge of what may be spoken. That is the honesty gate, supported by the vendor rather
than worked around. The model supports function calling and streaming but not
structured outputs, so the gate has to live on the Studio's side regardless.

**Two.** The hosted-versus-local problem is already solved in the repository.
`wb_studio/coordinator.py` and `wb_studio/worker.py` implement a durable coordinator
with trusted remote workers: the coordinator keeps the database, a worker receives one
job's inputs and uploads its evidence. So the hosted Studio can hold the voice session,
the ledger and the interface, while a local worker holds the checkouts, the coding
agent and the worktrees. Nothing new is needed for that split.

## Lucas's decisions

**D1 — Preview, not apply.** When Genesis changes the site, the change is shown in
place as a transition from before to after with an accept control. Nothing reaches the
running Studio until a person accepts. Rejecting restores the page and leaves the diff
on the card.

**D2 — Split honesty.** The voice may talk freely for conversation, framing and
opinion. Any sentence carrying a number or a record claim must come back from a Genesis
turn and pass the verified registry gate before it is spoken. A number that does not
verify is never said aloud; the voice says so and points at the card.

**D3 — Hosted.** The voice session runs on the hosted Studio, using the existing
coordinator and worker split for the code work.

## The architecture these produce

```
Browser (WebRTC)            Hosted Studio (coordinator)        Local worker
  audio tracks      <---->    voice session, ask_genesis         monarch + lab checkouts
  data channel                Genesis turn loop                  coding agent, worktrees
  preview swap                registry gate, ledger, SQLite       allowlisted verify
                                     |____ job in / evidence out ____|
```

The voice layer exposes essentially one tool. `ask_genesis` starts an ordinary turn
through the existing harness, on whatever model the Genesis configuration routed to,
and the voice narrates that turn's events from the durable event stream while it runs.
The identity file still governs; the protocol still governs; every refusal Genesis
already has still applies. Voice is a surface, not a second Genesis.

### What already exists

The turn loop with its typed tools and per-request ledger reservations; the durable,
reconnectable event stream; the engineer loop that builds a diff in a throwaway worktree
and has the Studio — not the model — run a verify command from an allowlist; the patch
pipeline with its detached worktree and apply check; the hash-routed interface; the
weekly ledger with reserve-then-settle; people and keys with attribution on every write;
figures computed on the server so a forged chart is dropped.

### What is new

A voice session and its cost line; the numeric registry and its independent checking
pass; an apply path for the lab's own code, behind a preview and a person's accept;
a small set of navigation tools so Genesis can show what it is talking about; the
memory change; and the calibration record.

### The line that makes it safe

The Studio is not the product under test. Changing the lab's own code touches no frozen
task, no configuration hash, no stored run and no grading. Monarch stays proposal-only
and is never applied by this feature. That distinction already exists in the code as the
two checkouts Genesis can read; this feature wires an apply path to one of them and to
neither other thing.

## The three mechanisms

### Verified numeric registry

From AutoResearchClaw. Two halves, both required. Execution builds a whitelist of every
value a run produced — per-condition means, standard deviations, individual measurements
per repetition — and any text or speech may only be built from those values. Then an
independent pass re-reads the finished answer, re-extracts every numeric claim, and
matches it against the whitelist; an unverifiable number in a strict section refuses the
output instead of emitting it. The second half is the part usually missed, and it is the
one that catches a model paraphrasing a real number into a new one.

The Studio already does exactly this for figures: they are computed on the server from
the report data, and a forged chart, options or source in the payload is dropped. The
registry is that same discipline for single numbers, and then for speech.

The test that proves it works is a deliberately fabricating fixture, modelled on
ScholarLoop's bundled cheater engine, whose only purpose is to produce false numbers and
be refused.

The same discipline extends to sources: a four-layer citation check classifying each
reference as verified, suspicious or hallucinated, and stripping the hallucinated ones.

### Delta updates for the lab memory

From ACE. The failure it prevents is measured: a context collapsed from 18,282 tokens to
122 in a single step, with accuracy falling from 66.7% to 57.1%, caused by a bounded
context being rewritten whole by a model. That is precisely the Studio's nightly
consolidation of a 2,500-character file.

The fix is structural. Every entry carries a stable identifier and counters for how
often it has been helpful or harmful. The night emits a small delta — candidate entries —
which is integrated as localized edits, never a whole-file rewrite. Redundancy is pruned
lazily, only when the budget is actually exceeded, not on a schedule. The helpfulness
counter replaces the current thirty-day decay guess, because an entry nothing ever
retrieves is the one to drop regardless of its age. Pinned entries stay exempt and a
person still adopts what the night proposes.

Without this, "Genesis knows everything it did" stops being true within months. Voice
alone cannot deliver that part of the ask.

### Calibration record

From ScholarLoop. Feature 024 already requires every experiment record to carry a
pre-registered prediction and a verdict. The missing half is scoring: after the run, the
Studio compares what was predicted against what happened, keeps the running track record
as a tagged record, and injects it into Genesis's prompt.

Two things follow. Proposals are disciplined by a measured hit rate rather than
confidence. And Lucas can ask out loud how often Genesis is right about something and
get an answer the Studio computed, not one the model asserted. That is more of what
"talks like a colleague" means than the voice is.

## Boundary with feature 024

Feature 024 owns the gates, the daily and weekly envelopes, the approval path, the
development and held-out slates, and the pre-registered prediction field. This feature
consumes all of them and may not duplicate, widen or contradict any. The voice session's
cost is a line inside 024's envelope, never a new ceiling.

Per constitution §III this feature changes the methodology's inputs and its interaction
surface. It reopens no rule in `PLAN.md` §1.

## Open risks recorded at design time

**The push rule.** Accepting a change means committing it, and the hosted Studio
redeploys from the repository. The constitution says pushes require Carlos's explicit
request and the repository is public. Accepting a live change therefore either needs a
standing decision from Carlos or must stop at a local commit. This is carried into the
spec as an open question rather than assumed.

**Keys and the voice session.** A voice session is a live wire into a process that holds
provider keys, and the environment loader already leaked into the test suite once, in
September, and was guarded. Whether the hosted coordinator should hold provider keys at
all, or whether they should live only on the worker, changes the architecture and is
carried into the spec as an open question.

**The content policy.** The interface currently permits no external connection, and a
test asserts it. Permitting the voice provider's origin is a deliberate loosening that
must be the only one added and must stay covered by that test.

## Deferred

Diffs that touch server code, which need a second process to preview, are out of the
first slice; static changes are the majority case and need no second process. The four
research mechanisms named above are deferred with their sources. Public release of
anything rendered remains separately authorized.

## Live workspace expansion

The [live workspace plan](../../../research/genesis-live-workspace-plan-2026-09-11.md)
adds the rich streaming and visible alteration direction requested by Lucas on
11 September. It preserves the current Studio token system and extends the existing
event stream and graph editor. Feature 025 story 6 defines the product acceptance
criteria. Implement the event foundation and workflow demonstration before attaching
voice; then extend the same surfaces to research, experiments and checked interface
previews. Application-data editing and source-code preview keep their distinct
authorization and persistence boundaries.
