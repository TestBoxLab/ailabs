# Feature Specification: Task Sets by Difficulty and the Scored AutomationBench Domains

**Feature Branch**: `005-task-tiers`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "Feature 005: task sets by difficulty and the scored AutomationBench domains. Single source: docs/superpowers/specs/2026-09-04-task-tiers-design.md (approved 4 Sep; do not relitigate its §3 decisions). Import the six scored domains into the corpus; define an objective, frozen difficulty measure; draw four task sets (simple, medium, complex, random) with a recorded seed; four plans, one per set, run as separate rounds against the same competitors. Offline; no model money in the feature itself. English, plain names (competitor, task set, attempt, approval rule, answer key, product under test)."

**Design of record**: `docs/superpowers/specs/2026-09-04-task-tiers-design.md`
(approved 4 Sep 2026 by Carlos). This spec restates that design as requirements;
it does not reopen the decisions in its §3.

## Why

Every Monarch-versus-models figure produced so far is one blended number over
ten easy tasks. It cannot answer the question that decides where Monarch is
worth using: **does the gap change with difficulty?** A product that maps a
platform and compiles a workflow ought to pull ahead exactly where a raw model
has to hold many steps and many services at once. That is either visible in the
data or it is a claim nobody checked.

So the benchmark gets three task sets — **simple**, **medium** and **complex** —
of ten prompts each, run as **separate rounds against the same competitors**,
plus a fourth set of ten drawn at random from the whole corpus as a self-check on
the blended average. Four numbers where there was one, each with its own error
bars, each frozen by hash before any competitor runs.

To have anything to draw from, the corpus grows first. AutomationBench's six
**scored** domains — finance, hr, marketing, operations, sales, support, one
hundred public tasks each — join the two hundred `simple` tasks already
imported, giving eight hundred tasks to classify and draw from.

AutomationBench's own way of making a hard set (the ten hardest tasks per
domain, on a private set we do not have) is deliberately not copied: it gives one
point on the difficulty curve, and we want its shape.

None of the fixed rules in `monarch-benchmark/PLAN.md` §1 change. This feature
adds inputs — six more domains in the corpus, four frozen task sets, four plans,
one manifest — and one offline command. Nothing it builds spends model money.

### What this feature does not decide

The four rounds are not run here. Each is a full round at smoke scale and needs
Carlos's approval of that specific run, stating **prompts: 10; attempts per
prompt and competitor: 2; attempts per competitor: 20 = 10 × 2; competitors: 7;
attempts in the round: 140** and a cost band.

## Vocabulary

Plain names are used throughout, in files and in this spec:

| Plain name | Meaning |
|---|---|
| competitor | one model + harness pair, or a harness alone |
| task set | a folder of task requests with their approval rules |
| prompt | one task's request text; ten per drawn task set |
| attempt | one task, one competitor, one repetition |
| repetitions | how many times each competitor does each prompt; two here |
| approval rule | what must change and what must not, checked after the attempt |
| answer key | the scripted competitor that always does the task right |
| product under test | the platform the competitors operate; here the 47 simulated apps |
| corpus | every imported task, from which the sets are drawn |
| domain | the vendor's grouping of the tasks: simple, finance, hr, marketing, operations, sales, support |
| scored domains | the six the vendor's own score counts: finance, hr, marketing, operations, sales, support |
| difficulty score | a number computed from a task's own file; see FR-008 |
| tier | simple, medium or complex — which third of the corpus a task's score falls in |
| the draw | choosing which tasks make up each task set, from a recorded seed |
| manifest | the file recording the measure, the cut points, the seed and every drawn task |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Import the six scored domains into the corpus (Priority: P1)

Carlos imports the six scored domains, derives their approval rules with the
existing machinery and the reviewed side-effect list, and validates them. The
corpus grows from two hundred tasks to eight hundred. No model is called and
nothing is spent.

**Why this priority**: There is nothing to classify or draw from until this
exists. It is the whole input to the rest of the feature.

**Independent Test**: Against a small fake dataset standing in for a scored
domain, run the import, the derivation and the validation, and confirm the task
files carry the same fields the already-imported tasks carry, each with a hash
and a derived approval rule.

**Acceptance Scenarios**:

1. **Given** the vendored task source, **When** the import runs for the six
   scored domains, **Then** each domain's tasks are written to their own folder
   with the request text, the tools needed, the starting data, the assertions and
   a hash, exactly as the already-imported tasks are.
2. **Given** imported tasks with no approval rule, **When** the derivation runs
   with the product's reviewed side-effect list, **Then** each task gains what
   must change and what must not, and its hash is rewritten to match.
3. **Given** an assertion type the derivation does not know, **When** the
   derivation runs, **Then** it says so loudly, names the task and the type, and
   leaves that task without an approval rule rather than guessing one.
4. **Given** the imported and derived tasks, **When** the validation runs,
   **Then** it reports how many have no approval rule and how many have a hash
   that does not match their content, and fails when either is unexpected.
5. **Given** the six scored domains, **When** the services their starting data
   seeds are compared with the product's list, **Then** any service not on that
   list is named, so it can be added to the product file and the side-effect list
   before anything is drawn.
6. **Given** the import command, **When** it is asked for every domain at once,
   **Then** it works on the six scored domains and the baseline one, each into
   its own folder.

---

### User Story 2 - Classify the whole corpus by difficulty, reproducibly (Priority: P1)

Carlos gets a difficulty score for every task in the corpus, computed from the
task's own file with no judgment call, and the two cut points that split the
corpus into three equal thirds. The measure, the cut points and every task's
score are written down, so anyone with the repository can reproduce the
classification exactly.

**Why this priority**: The classification is part of what the task sets are.
Agreeing it after seeing results would be the edit the constitution forbids.

**Independent Test**: On a synthetic corpus with known scores, confirm the score
of each task, the two cut points, and which tier each task lands in, including a
task sitting exactly on a cut point.

**Acceptance Scenarios**:

1. **Given** a task, **When** its difficulty is scored, **Then** the score is the
   number of services its starting data seeds, plus the number of changes its
   approval rule expects, plus the number of tools it needs — and nothing else.
2. **Given** starting data that also carries a bookkeeping entry that is not a
   service, **When** the services are counted, **Then** that entry is not counted.
3. **Given** the whole corpus, **When** the cut points are computed, **Then** they
   are the two values that split the scores into three parts as equal as the
   score distribution allows.
4. **Given** a task whose score sits exactly on a cut point, **When** it is
   classified, **Then** it lands in the lower of the two tiers, by a stated rule
   rather than by chance.
5. **Given** the classification, **When** it is written down, **Then** the record
   states the measure in words, both cut points, and every drawn task's score,
   tier and domain.

---

### User Story 3 - Draw four frozen task sets from one seed (Priority: P1)

Carlos runs the draw with a chosen seed. It writes four task sets — simple,
medium, complex and a random ten — each of ten prompts, copied from the corpus
without a single edit to any prompt, starting data or approval rule, plus the
record of how they were chosen. Running it again with the same seed produces the
same files, byte for byte.

**Why this priority**: This is the deliverable the rounds consume. Without
reproducibility the sets are not a frozen artefact and rule 5 is not met.

**Independent Test**: On a synthetic corpus, run the draw twice with one seed and
once with another; compare the folders and the record.

**Acceptance Scenarios**:

1. **Given** a corpus and a seed, **When** the draw runs, **Then** it writes four
   task sets of ten prompts each — one per tier and one drawn from the whole
   corpus — and a record of the measure, the cut points, the seed and every drawn
   task.
2. **Given** the same corpus and the same seed, **When** the draw runs again,
   **Then** every written file is identical, byte for byte.
3. **Given** a different seed, **When** the draw runs, **Then** the sets differ,
   and the record says which seed produced them.
4. **Given** a tier containing tasks from several domains, **When** its ten are
   drawn, **Then** they are spread across those domains as evenly as the
   available counts allow, and the shortfall is filled from the rest of the tier.
5. **Given** a drawn task, **When** it is written into its task set, **Then** its
   request text, starting data and approval rule are copied unchanged and its
   hash equals the hash of the corpus original.
6. **Given** a drawn task, **When** it is written, **Then** it also carries its
   tier and its domain, so a report can group by them, and carrying them does not
   change its hash.
7. **Given** a task with no approval rule, or one whose hash does not match its
   content, **When** the draw runs, **Then** it is left out of the pool and named
   in the output.
8. **Given** a tier with fewer usable tasks than the number asked for, **When**
   the draw runs, **Then** it refuses rather than writing a short task set, and
   says which tier and how many it found.

---

### User Story 4 - Run one round per task set (Priority: P2)

Carlos has four plans, one per task set, identical but for the set they name and
built from the same competitors and baseline as the create + run pilot, so the
four rounds and the pilot can be read side by side. Each states its size in the
agreed words and ships without approval, because each round is a decision Carlos
takes separately.

**Why this priority**: The plans are cheap to write and are what makes the drawn
sets usable, but nothing in this feature runs them.

**Independent Test**: Load and validate the four plans; confirm the task set,
the mode, the competitors, the baseline and the absence of an approval.

**Acceptance Scenarios**:

1. **Given** the four task sets, **When** the plans are written, **Then** there is
   exactly one plan per set, each naming that set, with the same competitors,
   baseline, mode and repetitions as the create + run pilot.
2. **Given** a plan, **When** it is read by a person, **Then** its size is stated
   as "prompts: 10; attempts per prompt and competitor: 2; attempts per
   competitor: 20 = 10 × 2", never as a bare per-competitor total.
3. **Given** a plan, **When** it ships, **Then** it carries no approval, so a
   round cannot start until Carlos approves that specific run.
4. **Given** a plan, **When** a run starts, **Then** the banner states the same
   arithmetic and the total number of attempts in the round before anything is
   spent.
5. **Given** a plan whose mode the product under test or the competitor's harness
   does not support, **When** it is validated, **Then** it fails before anything
   is spent, as today.

---

### User Story 5 - Read what changed (Priority: P3)

Anyone opening the plan of record, the project instructions or the configuration
documentation finds the new task sets, the new command, the record of the draw
and the four plans described in plain language, with the open questions and their
owners.

**Independent Test**: Read the three documents against FR-030 and FR-031.

**Acceptance Scenarios**:

1. **Given** the plan of record, **When** it is read, **Then** it carries the
   import and the draw as tracked work, the tiered rounds as a deliverable with a
   definition of done, the decisions of this feature dated, and its open
   questions with owners.
2. **Given** the project instructions and the configuration documentation,
   **When** they are read, **Then** they name this feature's folder, the four
   task sets, the record of the draw, the four plans and the new command.

---

### Edge Cases

- **A domain's tasks change under us** (the co-lead's patches to the vendored
  benchmark are not upstream). Every affected task's hash changes, old rows do
  not regrade, and any drawn set containing such a task must be redrawn. The
  draw's record makes this detectable: the recorded hash no longer matches.
- **An assertion type the derivation does not know** appears in a scored domain.
  The task gets no approval rule, is excluded from the pool, and is named. It
  does not silently enter a task set with a rule nobody checked.
- **Every task in a tier comes from one domain.** The draw takes ten from that
  domain and the record shows it, so a reader can see that this tier is not
  evidence about domains — the alternative measure in the design's decisions is
  exactly that objection.
- **A tie on a cut point.** Stated rule: the lower tier. Never a coin flip.
- **Fewer usable tasks in a tier than asked for.** The draw refuses; a short task
  set would break paired comparison against the other three.
- **The random set overlaps the tier sets.** Allowed and expected: it is drawn
  from the whole corpus. The record shows the overlap so a reader is not
  surprised, and the four are separate rounds, never pooled.
- **Someone edits a drawn task file by hand.** Its hash stops matching the record
  and the corpus original; the validation catches it and the round must not run
  until it is restored.
- **The corpus grows after a draw.** The old sets stay valid as frozen artefacts;
  a new draw is a new seed and a new set, never an edit of the old one.

## Requirements *(mandatory)*

### Functional Requirements

**Importing the scored domains**

- **FR-001**: The bench MUST be able to import each of the six scored domains of
  the vendored benchmark into the corpus, each into its own folder, using the
  same conversion the already-imported baseline domain used.
- **FR-002**: The import MUST accept a request for every domain at once, meaning
  the six scored ones and the baseline one.
- **FR-003**: Imported tasks MUST carry the request text, the tools needed, the
  starting data, the assertions and a hash of their content, and MUST NOT invent
  an approval rule the source does not state.
- **FR-004**: Approval rules for the imported tasks MUST come from the existing
  derivation and the product's existing reviewed side-effect list; no new
  derivation machinery is introduced.
- **FR-005**: An assertion type the derivation does not know MUST be reported by
  name with its task, and MUST leave that task without an approval rule.
- **FR-006**: The bench MUST report which services the scored domains' starting
  data seeds that the product under test does not list, so they can be added to
  the product file and the side-effect list before any draw. (Measured on 4 Sep
  2026: none — all forty-two are already listed.)
- **FR-007**: Importing MUST NOT call any model and MUST NOT spend money.

**The difficulty measure**

- **FR-008**: A task's difficulty score MUST be the number of services its
  starting data seeds, plus the number of changes its approval rule expects, plus
  the number of tools it needs — computed from the task's own file, with no
  judgment call and no external input.
- **FR-009**: Bookkeeping entries in the starting data that are not services MUST
  NOT be counted as services.
- **FR-010**: The three tiers MUST be the thirds of the whole corpus's scores,
  cut at the two values that split it as evenly as the distribution allows.
- **FR-011**: A task whose score sits on a cut point MUST fall in the lower tier,
  by that stated rule.
- **FR-012**: The measure, its two cut points and every drawn task's score MUST be
  written down, so the classification can be reproduced from the repository
  alone.
- **FR-013**: The measure MUST be confirmed by Carlos and the co-lead before the
  drawn task sets are frozen and committed (see Open Questions). Until then, the
  drawn sets are not pre-registered and no round may use them.

**The draw**

- **FR-014**: The bench MUST provide an offline command that draws four task sets
  from the corpus: one per tier and one from the whole corpus, of a stated size,
  ten by default.
- **FR-015**: The draw MUST take a seed, MUST record it, and MUST produce
  byte-identical output for the same seed over the same corpus.
- **FR-016**: A different seed MUST be treated as a different task set, never as
  an edit of an existing one.
- **FR-017**: Within a tier, the drawn tasks MUST be spread across the domains
  present in that tier as evenly as the available counts allow, filling any
  shortfall from the rest of the tier.
- **FR-018**: The fourth set MUST be drawn from the whole corpus with no tier
  filter and no stratification, as a check on the blended average.
- **FR-019**: Each drawn task MUST be a copy of the corpus task with its request
  text, starting data and approval rule unchanged, and its hash MUST equal the
  corpus original's (rule 5).
- **FR-020**: Each drawn task MUST also carry its tier and its domain so reports
  can group by them, and carrying them MUST NOT change its hash.
- **FR-021**: A task with no approval rule, or whose recorded hash does not match
  its content, MUST be excluded from the pool and named in the output.
- **FR-022**: When a tier has fewer usable tasks than the size asked for, the draw
  MUST refuse and say which tier and how many it found, rather than write a short
  task set.
- **FR-023**: The record of the draw MUST state the measure in words, both cut
  points, the seed, the corpus folders drawn from with their task counts, and one
  row per drawn task with its score, tier, domain and hash.
- **FR-024**: The draw MUST NOT call any model and MUST NOT spend money.
- **FR-025**: The draw MUST NOT modify anything in the corpus folders it reads.

**The plans**

- **FR-026**: There MUST be one plan per drawn task set, each naming that set,
  with the same competitors, baseline, mode and repetitions as the create + run
  pilot, an internal audience and a cost ceiling.
- **FR-027**: Every plan MUST ship without an approval, so no round can start
  before Carlos approves that specific run.
- **FR-028**: Every document, plan description and run banner stating a round's
  size MUST say "prompts: 10; attempts per prompt and competitor: 2; attempts per
  competitor: 20 = 10 × 2", and MUST NOT state only a per-competitor total.
- **FR-029**: The four rounds MUST be separate rounds; their results MUST NOT be
  pooled into one figure by anything in this feature.

**Documents**

- **FR-030**: The plan of record MUST be updated with this feature's tracked work,
  its deliverable and definition of done, its dated decisions and its open
  questions with owners.
- **FR-031**: The project instructions and the configuration documentation MUST
  name this feature's folder, the four task sets, the record of the draw, the four
  plans and the new command.

### Key Entities

- **Corpus folder**: every imported task of one domain, with derived approval
  rules and hashes.
- **Difficulty score**: one number per task, from FR-008.
- **Tier**: simple, medium or complex; which third of the corpus a score falls in.
- **Drawn task set**: ten copied tasks with their tier and domain; one of four.
- **Manifest**: the record of FR-023, the reproducibility artefact of the draw.
- **Round plan**: one of four, from FR-026.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Offline, the six scored domains import into six folders and the
  corpus reaches eight hundred tasks, every one with a hash; the count and the
  per-domain totals are printed.
- **SC-002**: Offline, the derivation gives every imported task an approval rule
  or names it as unmapped with its assertion type; the number without a rule is
  printed and is the review queue.
- **SC-003**: The services the scored domains seed are compared with the product's
  list and the difference is printed; today it is empty, and a non-empty
  difference names each missing service.
- **SC-004**: On a synthetic corpus with known scores, every task's score, both
  cut points and every task's tier match arithmetic, including a task on a cut
  point landing in the lower tier.
- **SC-005**: Two draws with the same seed produce byte-identical folders and
  record; a third with another seed differs, and the record names the seed each
  time.
- **SC-006**: Every drawn file's hash equals its corpus original's, and adding the
  tier and the domain does not move it.
- **SC-007**: In a tier holding several domains, the ten drawn cover as many
  domains as the counts allow; the record shows the per-domain counts.
- **SC-008**: A task with no approval rule and a task whose hash does not match
  are both excluded and named; a tier short of usable tasks makes the draw refuse
  with the tier and the count.
- **SC-009**: The four plans load and validate; each names its task set and the
  same competitors and baseline as the create + run pilot; none carries an
  approval; each run's banner states "prompts: 10; attempts per prompt and
  competitor: 2; attempts per competitor: 20 = 10 × 2; competitors: 7; attempts
  in the round: 140".
- **SC-010**: The full test suite stays green, offline, with no key in the
  environment, and neither the import nor the draw makes any network call.
- **SC-011**: The plan of record, the project instructions and the configuration
  documentation reflect this feature as in FR-030 and FR-031.
- **SC-012**: The drawn task sets are committed only after the measure is
  confirmed (FR-013); until then the command exists and is tested, and the folders
  are not in the repository.

## Assumptions

- The vendored benchmark's scored domains carry the same fields as the baseline
  domain: the tools needed, the starting data, the assertions and a task name,
  and no approval rule. Verified on 4 Sep 2026 across all six hundred tasks.
- The vendored benchmark carries no difficulty label of its own. Verified by
  searching the whole package.
- All forty-two services the scored domains seed are already listed by the product
  under test. Verified on 4 Sep 2026; re-checked after any patch to the vendored
  benchmark.
- The existing derivation and reviewed side-effect list are the right source of
  approval rules for the scored domains, as they were for the baseline domain.
- Task files are the only input to the difficulty score, so the score is frozen by
  the same hash that freezes the task.
- The four rounds are run later, one at a time, each with its own approval.
- Everything in this feature runs offline with no key.

## Open Questions

Recorded here and mirrored in the plan of record. Only the first blocks
committing the drawn sets; none blocks the code or its tests.

1. **Confirm the difficulty measure** — services seeded plus expected changes
   plus tools needed, with the thirds cut where the corpus falls. The alternative
   on the table is using the domain as the proxy for difficulty. This must be
   settled **before the drawn sets are frozen and committed**, because the
   classification is part of the task set and settling it afterwards would be an
   edit made after seeing results. Owner: Carlos and Lucas.
2. **The co-lead's patches to the vendored benchmark** are not upstream and may
   change scored-domain tasks. Applied after a draw, they change hashes, make old
   rows non-regradable and force a redraw. Getting them before the draw is
   cheaper. Owner: Lucas.
3. **Services beyond the product's list** — none today; re-check after those
   patches, since a patched task could seed a new service. Owner: Carlos.
4. **Unmapped assertion types in the six scored domains** — how many, and whether
   the derivation's map should be extended before the draw. Answerable offline;
   an unmapped task is excluded from the pool either way. Owner: Carlos to
   measure, Lucas to sign off on any extension.
5. **The pilot task set still carries hand-written approval rules** while the
   drawn sets carry derived ones, so a tiered round and the pilot round are not
   rule-identical until that is closed. Owner: Lucas. Carried from the plan of
   record; noted here because it now affects comparability.

## Out of Scope

The aggregate view across the four rounds (feature 006, the HTML report); running
any of the four rounds; run-only variants of the four plans (after feature 004);
extending the scripted answer key to the scored domains' assertion types; the
second product under test; and any change to a task's prompt, starting data or
approval rule.
