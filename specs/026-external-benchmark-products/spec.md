# Feature Specification: External benchmarks as products under test

**Feature Branch**: `026-external-benchmark-products`

**Created**: 2026-09-11

**Status**: Draft

**Input**: Brainstorming with Lucas on 11 September 2026, settled in four decisions recorded under *Decisions* below. Prompted by the request to "import other task sets from other benchmarks that are valuable to our usecase to be selectable as possible task sets".

## Context

The lab measures Monarch against models and agents on one product under test: the
simulated API set from AutomationBench. All seven of its domains are already in the
corpus (`corpus/imported-*`, about 700 tasks). There is no further task material to
import from that source.

Every other benchmark in the field brings its own world, its own tools and its own
answer key. A WorkflowBench task file today **is** an AutomationBench fixture — the
episode builds the vendor's own world object from the task's starting data, and the
positive half of grading runs through the vendor's assertion registry. So bringing a
foreign benchmark in is not a corpus import. It is a **new product under test**, which
is `PLAN.md` §1's first variable and item E in the program's queue.

Two reasons to do it now:

1. **The search loop needs an independent scorer.** Feature 024 runs architecture
   search scored by the benchmark, with a development slate and a held-out slate drawn
   from the same corpus. A held-out split of one corpus does not protect against
   overfitting to that corpus's quirks. An independent task source does.
2. **The program already wants a second product** and has reserved the shape for it:
   the product kinds in configuration already name `real-api` and `real-api-ui`
   alongside `simulated`, and nothing branches on them yet.

Per constitution §III this feature changes the methodology's **inputs** — products,
task sets, competitors' starting surface — and reopens no rule in `PLAN.md` §1. The
fixed rules are load-bearing here and are restated as requirements below, because a
foreign world is exactly where they are easiest to lose.

### The three worlds

Checked 11 September 2026.

| Source | Content | How it grades | Headroom | What it costs us |
|---|---|---|---|---|
| **EnterpriseOps-Gym** (ServiceNow AI Research / Mila / Université de Montréal, Apache-2.0, arXiv 2603.13594) | 1,150 expert-curated tasks over eight business domains — Calendar, CSM, Drive, Email, HR, ITSM, Teams, Hybrid. 164 database tables, 512 tools, 9.15 steps on average and up to 34. | SQL checks over the final environment state, about 5.3 conditions per task. State-based, no judge model. | Frontier ceiling 37.4 % task success across fourteen models. Far from saturated, so it discriminates. | Containers per domain, and the "nothing else changed" half is ours to derive. |
| **AppWorld** (Stony Brook, ACL 2024 best resource paper, arXiv 2407.18901) | 750 tasks, nine apps, 457 interfaces, about 100 fictitious people. Splits: train, dev, test-normal, test-challenge. | State-based checks that already include a collateral-damage check — the same idea as our approval rule. | Not saturated; the gap between per-task and per-scenario success is the interesting part. | Least work: it already publishes an interface description and serves itself over HTTP. Consumer-life apps, not business software, and full answer keys exist only for train and dev. |
| **τ²-bench** (Sierra Research) | Domains airline, retail, telecom, banking-knowledge, mock. Customer-service work with a simulated person on the other side. | Database end state. | Reports pass^k at k = 1…4, which is why its standard run is four repetitions. | A model plays the customer inside every attempt, so every attempt has a second paid participant. Results before version 1.0.1 are not comparable with later ones. |

Considered and rejected, recorded so the question is not reopened without new
information:

- **WorkBench** is saturated. The 2026 re-evaluation reports the best agent at 97.7 %
  with nine models above 80 %. A set that nine models clear measures nothing here.
- **CRMArena-Pro** and **WorkArena** need a real Salesforce org and a real ServiceNow
  interface. They are the program's item E — a real product under test — not task sets,
  and they carry tenant and legal work this feature does not do.
- **APIFlow-Bench**, **GBA-Bench**, **SaaSBench**, **STATE-Bench** and **DRBench** are
  the wrong shape: interface readiness, path-based grading, repository engineering,
  agent memory and deep research respectively.

### Decisions

**D1 — the source benchmark supplies "the expected result is present"; we supply "and
nothing else changed".** Each source's own checker runs unchanged over the attempt's
final state. WorkflowBench derives the collateral half by diffing its own before and
after snapshots through the approval-rule matcher, which is already world-agnostic.
This keeps the upstream rule the repository already lives by: we never edit another
benchmark's assertions. It has a consequence that must be said out loud on every round:
our task hash covers the request text and our collateral rule, but not their assertions,
so "frozen by hash before any competitor runs" holds only jointly with a pinned source
version.

**D2 — one uniform surface for competitors.** Every product, foreign or not, is fronted
by the same three tools over an HTTP front door described by an interface document,
exactly as the simulated API set is fronted today. The decisive reason is not
tidiness: that shape is the only one Monarch's discovery can map, so it is what lets
Monarch be measured on these worlds at all. A product Monarch cannot compete on would
be a model-versus-model exercise and would not serve the program.

**D3 — τ²'s simulated customer is paid, pinned and counted.** One cheap model is named
in the product's configuration, so it lands in the configuration hash; its tokens are
reserved and settled in the weekly ledger like any other spend, because "cost is
complete" is a fixed rule; and every round on that product carries a caveat saying a
model sat inside the measurement loop.

**D4 — all three worlds in this one feature**, as prioritized stories, so the seam is
validated against three real implementations instead of one plus two designs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A foreign world runs and grades under our rules (Priority: P1)

Lucas picks the EnterpriseOps-Gym product and one of its frozen task sets, and launches
a round with the scripted checks. Each attempt starts from a fresh copy of that world,
the competitor works through the same three tools it uses on the simulated API set, and
afterwards — from stored snapshots, never in-process — the source's own checks say
whether the expected result is present while our approval rule says whether anything
else changed. The round reads like any other round.

**Why this priority**: this is the whole seam. Without it the other two worlds are
configuration files with nothing behind them, and the program has no second source of
task material. It is also the story that proves the fixed rules survive contact with a
world we did not write.

**Independent Test**: import the source's tasks, freeze a ten-task set, run the answer
key and the null check offline with no provider keys present, and grade. The answer key
passes, the null check fails every task, and the round's report renders. Delivers a
second product under test end to end.

**Acceptance Scenarios**:

1. **Given** a product whose world comes from an external benchmark, **When** an attempt
   starts, **Then** the attempt works against its own private copy of that world and no
   state from a previous attempt is visible.
2. **Given** a finished attempt on an external product, **When** grading runs later from
   the stored snapshots, **Then** the verdict is a pass only when the source's own checks
   all pass **and** every observed change is covered by the task's approval rule **and**
   the attempt finished normally.
3. **Given** an attempt that produced the expected result and also changed something it
   was not asked to touch, **When** grading runs, **Then** the attempt fails and the
   extra changes are listed individually.
4. **Given** the answer key competitor, **When** it runs a frozen set on the external
   product, **Then** it passes; **given** the null competitor on the same set, **Then**
   it fails every task.
5. **Given** a task whose recorded hash no longer matches its content, **When** a round
   is prepared, **Then** the round is refused and names the task.
6. **Given** the external world's runtime is not available on this machine, **When** a
   round is prepared, **Then** preparation refuses with the missing prerequisite named,
   and no money is reserved.

---

### User Story 2 — A round on a foreign product reads honestly (Priority: P2)

Carlos opens the report of a round run on an external product. It says which benchmark
the tasks came from, which version of it was pinned, which split was used, and which
half of the verdict came from whose checker. Nothing in it invites him to compare that
pass rate with a pass rate from a different product.

**Why this priority**: the moment a second product exists, the cheapest mistake in the
lab becomes putting two incomparable numbers in one table. The lab's output is its
reports, and the rule that paired comparisons happen only on identical sets is a fixed
rule. This story is what stops the feature from producing confident nonsense.

**Independent Test**: generate a report for a round on an external product and read it;
then attempt to build a paired comparison across two products and confirm it is refused.

**Acceptance Scenarios**:

1. **Given** a finished round on an external product, **When** its report is generated,
   **Then** it carries a sentence naming the source benchmark, the pinned source
   version, the split used, and the fact that the source supplied the positive half of
   the verdict while the lab supplied the collateral half.
2. **Given** two rounds on different products, **When** anything attempts to pool or
   pair their results, **Then** it is refused and the reason names the two products.
3. **Given** a round on a product whose attempts contained a paid participant other
   than the competitor, **When** its report is generated, **Then** the report says so.
4. **Given** any figure in such a report, **When** it is rendered, **Then** it carries
   its source line, as every figure already does.

---

### User Story 3 — A second foreign world on the same seam (Priority: P3)

Lucas adds AppWorld as a product without touching the machinery built for the first
one: an importer for its tasks, a product file, frozen task sets, and a plan that
selects them. Its own collateral-damage checks are recorded beside ours rather than
replacing them.

**Why this priority**: one implementation does not prove a seam. AppWorld is the
cheapest of the three to wire and the most different in content — consumer apps rather
than business software — so it is the best test of whether the seam was shaped around
its first source. It also gives the search loop a second independent scorer.

**Independent Test**: run the same offline round shape as User Story 1 against AppWorld
and confirm nothing built for the first world had to change to accommodate it.

**Acceptance Scenarios**:

1. **Given** the seam from User Story 1, **When** AppWorld is added, **Then** the
   shared machinery is unchanged and only source-specific parts are new.
2. **Given** an AppWorld split whose full answer key is not published, **When** it is
   imported, **Then** the import refuses those tasks and says why.
3. **Given** an attempt on AppWorld, **When** grading runs, **Then** the source's own
   collateral-damage finding is recorded alongside our approval-rule finding, and a
   disagreement between the two is visible rather than silently resolved.
4. **Given** this repository is public, **When** an AppWorld task set is frozen,
   **Then** no task content that the source distributes under a no-plain-redistribution
   requirement is written into the repository.

---

### User Story 4 — A world with a paid participant inside the attempt (Priority: P4)

Lucas runs a round on τ²-bench, where a model plays the customer the competitor is
serving. Before the round starts he is told how many attempts there are and what band
they will cost, counting both participants. The ledger reserves the maximum for both
and settles from the receipts.

**Why this priority**: last because it is the only world that changes the money model,
and because its conversational core is the furthest from how Monarch is actually used.
It earns its place by being the field's reference for reliability across repetitions —
the pass^k question a buyer asks — and by proving the seam tolerates an attempt whose
cost is not just the competitor's.

**Independent Test**: prepare a τ² round offline and read the disclosed attempt count
and cost band; confirm both participants appear in the reservation, and that the round
is refused when the week cannot cover the maximum.

**Acceptance Scenarios**:

1. **Given** a product with a second paid participant, **When** a round is prepared,
   **Then** the disclosed cost band includes that participant's spend.
2. **Given** such a round, **When** it is admitted, **Then** the week's ledger has
   reserved the maximum liability of every participant, and a week that cannot cover it
   refuses the round with the shortfall named.
3. **Given** the simulated customer is pinned in the product's configuration, **When**
   that pin changes, **Then** the round's configuration hash changes.
4. **Given** an attempt reaches its per-attempt cap, **When** the cap is reached,
   **Then** the attempt stops, counting both participants' spend against the cap.

---

### Edge Cases

- **The external runtime is missing or not started.** Preparation refuses, naming the
  prerequisite. It never starts a paid round to discover this.
- **The source benchmark's version moves.** A round whose recorded source version does
  not match the installed one is refused rather than graded against a different answer
  key. Existing rows stay readable and are marked as belonging to the old pin.
- **The source's checker raises rather than returning a verdict.** The attempt is
  recorded as ungraded with the error kept, never silently passed or failed.
- **The source's checker and our approval rule disagree** — it passes a task where we
  observed changes outside the permitted scope. Both findings are kept; the verdict is
  a fail, because both halves are required.
- **A task's world cannot be snapshotted** — no before-and-after comparison is possible.
  The task is excluded at import with a recorded reason; it is never silently graded on
  the positive half alone.
- **A split with no published answer key** (AppWorld's test splits). Refused at import,
  with the reason.
- **A product is selected with a test mode it does not support.** Refused before
  anything is reserved.
- **Two products in one comparison.** Refused, naming both.
- **Offline tests.** The suite must not require containers, downloads, network access
  or provider keys, and must not reach a live provider.
- **A task set drawn from an external corpus** flows through the same freezing,
  manifest and hash machinery as the existing sets, or it is not usable.

## Requirements *(mandatory)*

### Functional Requirements

**The seam**

- **FR-001**: A product under test MUST declare which external world it uses, and the
  system MUST choose the attempt's world from that declaration rather than assuming one
  world for every product.
- **FR-002**: Each attempt MUST start from a fresh private copy of its product's world;
  no state from any previous attempt may be observable.
- **FR-003**: Every world MUST produce a before-and-after snapshot of its own state,
  keyed by service, in a single shape that the existing approval-rule matcher consumes
  without change.
- **FR-004**: Competitors MUST receive the same three tools on every product, over an
  HTTP front door described by a published interface document, so that a competitor's
  starting surface does not differ by product.
- **FR-005**: The published interface document for a product MUST describe operations
  that dispatch back into that attempt's own world, and MUST be reachable by the
  discovery step Monarch uses to map a product.
- **FR-006**: A product MUST declare which test modes it supports, and a round that asks
  for an unsupported mode MUST be refused before anything is reserved.
- **FR-007**: The system MUST refuse to prepare a round when the product's external
  runtime, dataset or version prerequisites are absent, naming the missing prerequisite,
  and MUST NOT reserve money or start attempts in that state.

**Grading**

- **FR-008**: The positive half of a verdict MUST come from the source benchmark's own
  checker, run unchanged. The system MUST NOT edit, re-derive or substitute a source's
  assertions.
- **FR-009**: The collateral half of a verdict MUST come from the lab's approval rule
  applied to the lab's own snapshot diff, for every product.
- **FR-010**: An attempt passes only when the positive half passes, the collateral half
  passes, and the attempt finished normally. Neither half alone is a pass.
- **FR-011**: Grading MUST run after the attempt, from stored snapshots, in a process
  that is not the competitor's. Nothing may grade itself.
- **FR-012**: The existing rule that a task with no positive check fails MUST be
  preserved in meaning: a product MUST declare where its positive check comes from, and
  a task with no reachable positive check MUST NOT pass.
- **FR-013**: A source checker that fails to produce a verdict MUST leave the attempt
  recorded as ungraded with the error retained, not passed and not failed.
- **FR-014**: Where a source supplies its own side-effect finding, the system MUST
  record it alongside the lab's finding and MUST make a disagreement between them
  visible rather than resolving it silently.

**Importing and freezing**

- **FR-015**: Each source MUST have an importer that writes task files carrying the
  request text, the identifiers its checker needs, the approval rule, the recorded
  source version and a content hash.
- **FR-016**: An importer MUST refuse, with a recorded reason, any task whose answer key
  is not published, whose world cannot be snapshotted, or whose checker cannot be run
  locally. It MUST NOT write a partially usable task.
- **FR-017**: Imported tasks MUST be drawable into frozen task sets by the existing
  task-set machinery, producing the same manifests and hashes as today's sets.
- **FR-018**: Every task MUST be frozen by hash before any competitor runs on it, and a
  task whose content no longer matches its hash MUST cause the round to be refused,
  naming the task.
- **FR-019**: Each imported corpus MUST record which source benchmark, which version of
  it, and which split it came from, and that record MUST be part of what a round pins.
- **FR-020**: The system MUST NOT write into this repository any source content that its
  licence forbids redistributing in plain form; such content MUST be depended on at run
  time instead.

**Selecting and running**

- **FR-021**: Each external world MUST be selectable as a product under test, and its
  frozen sets selectable as task sets, through the existing product-and-plan selection —
  no new selection mechanism.
- **FR-022**: At least one runnable plan MUST exist per external world, naming its task
  set, its competitors, its repetitions and its cost ceiling.
- **FR-023**: All competitors on a given task MUST receive identical request text.
- **FR-024**: A round's configuration hash MUST cover the product, its external source
  pin, its task set and every participant, including a participant that is not the
  competitor.

**Money**

- **FR-025**: Where an attempt has a paid participant besides the competitor, the
  disclosed attempt count and cost band before a round MUST include it, the weekly
  ledger MUST reserve the maximum liability of every participant, and the per-attempt
  cap MUST count every participant's spend.
- **FR-026**: The weekly spending gate and the human approval gate MUST apply to rounds
  on external products exactly as they do today; nothing in this feature may launch a
  paid round.
- **FR-027**: Cost recorded for an attempt MUST be complete, covering every participant,
  cached and uncached, against the versioned price table.

**Reporting**

- **FR-028**: A report for a round on an external product MUST carry a generated
  sentence naming the source benchmark, its pinned version, the split used, and which
  side supplied each half of the verdict.
- **FR-029**: A report MUST state when an attempt contained a paid participant other
  than the competitor.
- **FR-030**: Results from different products MUST NOT be pooled, paired or averaged
  together; an attempt to do so MUST be refused, naming both products.
- **FR-031**: Every figure in such a report MUST carry its source line, as figures do
  today.

**The competitor's surface is only the product's own work**

- **FR-034**: A world's administrative operations — seeding, resetting, cloning or
  deleting its data, running arbitrary queries against it, dumping its whole state,
  downloading its data file — MUST be withheld from the competitor: absent from the
  published interface document and refused at the front door. A competitor that
  reached them could write the expected result directly, read the checker's own
  target, or erase the evidence, and the round would measure nothing.
- **FR-035**: The lab's own use of those operations — seeding a private world,
  snapshotting it, running the source's checks, tearing it down — MUST go by a path
  the competitor cannot reach.

**Evidence and tests**

- **FR-032**: The offline test suite MUST cover the seam and every source adapter
  without requiring containers, downloads, network access or provider keys.
- **FR-033**: Each source MUST have a recorded check that its answer-key competitor
  passes a frozen sample and its null competitor fails it, runnable offline.

### Key Entities

- **Product under test**: what a round is run against. Names its world, its source pin,
  its services, its supported test modes, and any participant beyond the competitor.
- **World adapter**: the per-source bridge that seeds a private world for an attempt,
  serves it over the front door, snapshots it, and runs the source's checker afterwards.
- **Source pin**: the benchmark, version and split an imported corpus came from; part
  of what a round freezes.
- **Task**: request text, the identifiers the source's checker needs, the approval rule,
  the source pin, and a content hash.
- **Verdict**: the positive finding from the source, the collateral finding from the
  lab, the finish state, and the pass that requires all three.
- **Task set**: a frozen selection of tasks with a manifest, drawn by the existing
  machinery, belonging to exactly one product.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person can run a full round on any of the three external worlds by
  naming a product and a plan, with no step outside the existing selection.
- **SC-002**: On every external world, the answer-key competitor passes 100 % of a
  frozen sample and the null competitor passes 0 % of it.
- **SC-003**: An attempt that produces the right result while changing something it was
  not asked to touch is recorded as a failure on all three worlds, 100 % of the time.
- **SC-004**: Adding the second and third worlds requires no change to the shared seam;
  measured as zero edits to shared files in the changes that add them.
- **SC-005**: Every task in every external task set carries a hash that matches its
  content at the moment a round starts, or the round does not start.
- **SC-006**: Every report on an external product states its source, version, split and
  which side supplied each half of the verdict — no report is missing it.
- **SC-007**: No comparison in any output mixes results from two products.
- **SC-008**: The whole feature's tests pass offline, with no containers, no downloads,
  no network and no provider keys.
- **SC-009**: For a round with a paid participant beside the competitor, the cost stated
  before the round and the cost settled after it account for both, with no unattributed
  spend.
- **SC-010**: At least one frozen task set per world, drawn reproducibly from a recorded
  seed, exists and is selectable.

## Assumptions

- **Availability**: the machine running a round on EnterpriseOps-Gym can run its
  containers; AppWorld and τ² install through the project's package manager. Absence is
  handled by FR-007 rather than assumed away.
- **Licences**: EnterpriseOps-Gym is Apache-2.0 and τ²-bench is expected to be MIT —
  to be confirmed against the source's own licence file during planning. AppWorld is
  Apache-2.0 for its open portion, with an added requirement that its task, interface
  and answer-key content be redistributed only in the packed form it ships in. Because
  this repository is public, AppWorld content is depended on and never committed
  (FR-020). Each source gets a vendor legal note beside its adapter.
- **Freshness of source checkers**: the sources' checkers are run as libraries at their
  pinned version. A source that only offers its checker as a service is out of scope.
- **Scale**: frozen sets are drawn small — around ten tasks — by the existing machinery.
  Running the full 1,150 or 750 tasks is a budget decision for a later round, not part
  of this feature.
- **Test modes**: external products are expected to support the modes where the
  competitor is handed a request and acts; a source that cannot support a mode declares
  so (FR-006) rather than failing at run time.
- **The search loop**: these products become available to feature 024's search as
  additional scorers. The rule that a held-out slate is spent once per lineage applies
  per product; this feature does not change that rule, it only widens what can be
  drawn from.
- **Comparability with public leaderboards**: our numbers will not match the sources'
  published numbers, because our approval rule adds a collateral half and our harness
  differs. FR-028 exists so no report implies otherwise.
- **Scope boundary**: this feature adds products, adapters, importers, task sets, plans
  and the reporting that keeps them honest. It does not run a paid round, does not add
  a competitor, and does not change any rule in `PLAN.md` §1.
