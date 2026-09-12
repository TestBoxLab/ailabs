# Feature Specification: The search loop — measurement foundations for architecture search

**Feature Branch**: `024-architecture-search`

**Created**: 2026-09-11

**Status**: Draft

**Input**: Design of record [`docs/superpowers/specs/2026-09-11-architecture-search-design.md`](../../docs/superpowers/specs/2026-09-11-architecture-search-design.md), written after an eighteen-agent adversarial review of the Studio and four rounds of design questions answered by Lucas on 11 September 2026.

## Context

The lab is not running a leaderboard with an assistant attached. Lucas's decision 7 of
11 September is that **the architecture editor is the destination, not a model**: if a
composed architecture beats Monarch Enterprise on the frozen set, that composition is
the proposal — Monarch should become it. The lab therefore runs **architecture search
over Monarch's design space, scored by the benchmark**.

Search finds whatever the scorer rewards, including its flaws. This feature builds the
measurement foundations that search needs before it is allowed to run, and closes the
loop that turns a confirmed win into a proposal. It does not widen what the searcher is
allowed to do.

Per constitution §III, this feature changes the methodology's **inputs** — a new task
split, a repetitions field, a cost boundary, a confirmation gate — and does not reopen
any rule in `PLAN.md` §1.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The gates hold (Priority: P1)

Lucas leaves the lab's hosted workspace running overnight with the researcher enabled.
Nothing outside the lab can reach into a running attempt; the researcher cannot spend
past its allowance; a Pause stops every paid activity; and no paid round starts without
a named human operator on the record.

**Why this priority**: Two of these defects are live on a publicly reachable URL today.
Until they are closed, every other capability in this feature is a way to spend money
unsafely. This story is also the only one whose absence can invalidate a round that
otherwise ran correctly, because an outside write into a running attempt is scored as
the competitor failing.

**Independent Test**: Enable the researcher on a fresh workspace with provider keys,
attempt the listed reaches from outside, and confirm each is refused and recorded.
Delivers a workspace that can be left running.

**Acceptance Scenarios**:

1. **Given** a running attempt and a caller with no credentials, **When** the caller
   issues a write to the attempt's application front door, **Then** the write is
   refused and the attempt's world is unchanged.
2. **Given** a workspace with no autonomy settings saved, **When** the workspace starts
   with provider keys present, **Then** the researcher does not work cards or launch
   runs until a person enables it.
3. **Given** the researcher is paused, **When** every scheduled activity's hour arrives,
   **Then** no paid request is sent and each skipped activity is recorded with its
   reason.
4. **Given** a daily allowance and a researcher that launches runs, **When** the
   researcher launches a run, **Then** the run's reserved maximum counts against the
   same daily allowance shown to the person.
5. **Given** a reservation that settled above its maximum, **When** any paid path runs,
   **Then** the lab records the overrun and a person can clear it without editing the
   ledger by hand.
6. **Given** a run started from the workspace, **When** the reservation is written,
   **Then** it names the human operator and, above smoke scale, the approval record
   that admitted it.
7. **Given** an attempt that loops, **When** it reaches its per-attempt cap, **Then**
   it stops and the remaining tasks in the round still run.
8. **Given** a link naming a private or link-local address, **When** it is dropped for
   the researcher to read, **Then** it is refused and nothing is fetched or stored.

---

### User Story 2 - Numbers a scientist can act on (Priority: P2)

Lucas or the researcher opens a finished round and reads what happened. Every service
is named correctly, every claim about a competitor is supported by the evidence it
cites, results graded against rules that no longer exist are visibly marked, and the
report does not contradict itself within one section.

**Why this priority**: These numbers are the input to the next variant. A miscalibrated
instrument does not merely mislead a reader; it steers the search. It is second only to
the gates because a wrong conclusion is recoverable and an unsafe workspace is not.

**Independent Test**: Render the lab's existing ten-task round and check each named
defect against the stored evidence. Delivers a report whose statements can be trusted
without re-reading the raw record.

**Acceptance Scenarios**:

1. **Given** an attempt that called a non-mail service hosted under a shared provider
   domain, **When** the attempt's story is written, **Then** the service is named by
   the service actually called.
2. **Given** an attempt that ended because it ran out of turns, **When** the round's
   findings are written, **Then** no finding asserts that the competitor claimed the
   work was done, unless that claim appears in the competitor's own output rather than
   in the request text returned alongside it.
3. **Given** a stored attempt whose task definition has since changed, **When** the
   round is rendered, **Then** the attempt is marked as not comparable and is excluded
   from or visibly distinguished in every figure and headline number.
4. **Given** a set of failed attempts, **When** the round names why they failed,
   **Then** one classification is presented, and any second view of the same attempts
   agrees with it.
5. **Given** a competitor identified by model, version and reasoning setting, **When**
   the headline figure labels it, **Then** the label names the competitor, not only its
   reasoning setting.
6. **Given** a trend across rounds, **When** it is titled, **Then** the title names the
   competitors actually present in the data.
7. **Given** rounds that differ in judge, world revision, assistance or workflow
   contract, **When** results are grouped for ranking, **Then** they are not pooled, and
   any group lacking a pinned judge is marked provisional.

---

### User Story 3 - An experiment that can return a verdict (Priority: P3)

The researcher proposes a variant. The lab either runs it on the development slate with
enough repetitions to reach a conclusion, or refuses the proposal and says how many
tasks would be needed. A variant that wins on development is confirmed once on the
held-out slate, and never returns to it.

**Why this priority**: Without this, every experiment the loop runs is
uninterpretable — a variant that flips three or four tasks out of ten cannot reach
significance at any win count, so the loop reports "no result" forever while spending
money. It is third only because it is useless before the gates hold and the numbers can
be trusted.

**Independent Test**: Propose a variant against a ten-task set and confirm the refusal
names the shortfall; propose the same variant against the development slate and confirm
it runs; win on development and confirm the held-out slate accepts it once and refuses
the lineage thereafter.

**Acceptance Scenarios**:

1. **Given** the corpus, **When** the split is drawn, **Then** a development slate and a
   held-out slate are frozen by hash, each carrying the same difficulty mix and domain
   spread, with a manifest recording the measure and its version, the cut points, the
   per-slate domain counts, the seed and every task's tier, domain and hash.
2. **Given** a frozen held-out slate, **When** anyone attempts to redraw it, **Then**
   the redraw is refused.
3. **Given** a variant proposal against a task set too small to reach a conclusion,
   **When** the proposal is submitted, **Then** it is refused before any money is
   reserved, and the refusal states the number of tasks or repetitions that would be
   enough.
4. **Given** a variant test, **When** the run is configured, **Then** the development
   slate is the default task set and the number of repetitions is an explicit setting
   on the run.
5. **Given** a variant that won on development, **When** it is submitted to the
   held-out slate, **Then** it runs once.
6. **Given** a variant lineage that has already been confirmed or refused on held-out,
   **When** any descendant of that lineage is submitted to held-out again, **Then** it
   is refused with the prior result named.
7. **Given** a completed variant test, **When** it is recorded, **Then** the record
   carries the pre-registered prediction, the parent it descends from, and a verdict of
   supported, not supported or inconclusive.
8. **Given** a weekly research envelope set by a person, **When** the researcher
   proposes an experiment costing more than the envelope's remainder or more than the
   per-experiment ceiling, **Then** it is refused before any reservation and the
   refusal names the shortfall.
9. **Given** an exhausted weekly research envelope, **When** the researcher proposes
   anything paid, **Then** the loop stops until a person sets a new envelope, and it
   never draws on the remainder of the lab's weekly ceiling.
10. **Given** a variant confirmed on the held-out slate, **When** the proposal is
    produced, **Then** it is a written specification carrying the variant, the paired
    result with its uncertainty, the slate and repetitions used, and the evidence for
    why it wins.

---

### User Story 4 - The fitness function (Priority: P4)

A reader can see what it costs to configure a workflow once and what it costs to run it
each time, separately, in money and in time — and can compare that against a competitor
that pays full price on every request.

**Why this priority**: This is the measure the lab's whole argument rests on, and it is
the score the search optimises against. Scored on accuracy alone, the search will find
an architecture that wins by spending far more, which is the opposite of the claim.

**Independent Test**: Run one attempt in create-and-run mode and confirm the record
carries configure cost, execute cost, configure time and execute time separately, each
reconciling to the previously reported total.

**Acceptance Scenarios**:

1. **Given** an attempt that builds a workflow and then executes it, **When** its cost
   is settled, **Then** the record holds the cost to configure and the cost to execute
   separately, and their sum reconciles with the total.
2. **Given** the same attempt, **When** its duration is recorded, **Then** time to a
   saved workflow and time per execution are recorded separately.
3. **Given** a cost that cannot be read for one side of the boundary, **When** the
   record is written, **Then** the unreadable side is marked unknown rather than
   assumed to be zero, and the whole reservation is held.
4. **Given** a task set with known-correct saved workflows, **When** a run executes
   them repeatedly, **Then** a per-execution cost and time are produced for each.
5. **Given** costs for two competitors, **When** they are compared, **Then** the
   comparison is expressed per successful task, not per attempt.

---

### User Story 5 - The curve and the gap list (Priority: P5)

An executive opens the report and sees one argument: at how many executions the product
becomes cheaper than an agent paying full price every time, how accurate it is with
real uncertainty, and what stands between it and the frontier. Deyton opens the same
evidence and sees defects; Lucas sees a backlog.

**Why this priority**: This is the deliverable for the audience Lucas named, and it is
a rendering of evidence produced by stories 1 to 4. It cannot be built first and is
worthless if the evidence beneath it is wrong.

**Independent Test**: Open a finished round as each audience and confirm the same
underlying evidence produces three renderings with no fact present in one and absent
from another.

**Acceptance Scenarios**:

1. **Given** configure and execute costs for the product and per-request costs for a
   competitor, **When** the curve is drawn, **Then** it shows cumulative cost against
   number of executions for each, and names the crossing point or states that none
   exists in the observed range.
2. **Given** a round, **When** an executive opens it, **Then** the first thing shown is
   the curve, the accuracy comparison with its uncertainty and sample count, and the
   gap list.
3. **Given** one evidence base, **When** it is rendered for Deyton, for Lucas and for
   an executive, **Then** all three are derived from the same records and no rendering
   asserts a fact the others contradict.
4. **Given** a gap item, **When** it is shown, **Then** it names whether it rests on a
   confirmed experimental result or on a reading of code, and the two are never
   presented as peers.
5. **Given** a round with no held-out confirmation yet, **When** the gap list is shown,
   **Then** unconfirmed items are marked as such.

---

### Edge Cases

- A variant test proposed when the week's remaining budget cannot cover its maximum:
  refused before dispatch with the shortfall stated, not started and abandoned midway.
- Every pair in a comparison ties — no discordant pairs at all: the verdict is
  inconclusive with the tie count shown, never "no difference".
- The development and held-out slates drift apart in difficulty after the draw: the
  manifest records the draw rule so the imbalance is visible rather than silent.
- A person changes an approval rule after a slate is frozen: prior results on the moved
  tasks become non-comparable and must be marked, not regraded.
- The researcher proposes a variant identical to one already tested: refused with the
  prior record named, unless it declares itself a replication.
- A workflow saved in one run is executed in a later run after the product changed:
  the execution is marked against the product revision it ran on.
- Cost is readable for the configure side and unreadable for the execute side: the
  attempt reports a partial split and holds its reservation.
- Two paid activities start at the same moment against the same week: both reserve
  before dispatch and the second is refused if the week cannot cover both.

## Requirements *(mandatory)*

### Functional Requirements

**Gates (User Story 1)**

- **FR-001**: The system MUST authenticate every request before any request-handling
  path is chosen, including proxied application traffic and every write method.
- **FR-002**: The autonomous researcher MUST be disabled until a person enables it; no
  default configuration may cause paid work to begin on a fresh workspace.
- **FR-003**: A pause MUST stop every paid activity, including scheduled ones, and each
  skipped activity MUST be recorded with its reason.
- **FR-004**: A daily allowance MUST count every paid activity attributable to the
  researcher, including the reserved maximum of runs it launches.
- **FR-005**: A weekly envelope MUST count a paid activity once, at its reserved
  maximum while unsettled, regardless of who initiated it.
- **FR-006**: An overrun MUST be recoverable by a recorded human action without direct
  edits to the ledger store, and MUST NOT permanently block unrelated paid paths.
- **FR-007**: Every paid launch MUST name a human operator, and a launch above smoke
  scale MUST reference the approval record that admitted it. No agent may be the
  approver of its own round.
- **FR-008**: Every attempt MUST have a per-attempt spending cap that is strictly below
  the round's ceiling.
- **FR-009**: Fetching an address on behalf of the researcher MUST refuse private,
  loopback and link-local destinations, and MUST bound redirects.

**Instrument (User Story 2)**

- **FR-010**: An attempt's story MUST name the service actually called, distinguishing
  services that share a provider domain.
- **FR-011**: A claim that a competitor asserted completion MUST rest only on the
  competitor's own produced output, never on request text echoed back with it, and MUST
  state that it is inferred from wording wherever it is displayed.
- **FR-012**: The system MUST compare each stored attempt's task definition against the
  current corpus and mark attempts graded against definitions that no longer exist.
  Such attempts MUST NOT contribute to a headline number without that mark.
- **FR-013**: Failed attempts MUST be classified once; any second presentation of the
  same attempts MUST derive from that single classification.
- **FR-014**: A competitor label in a figure MUST identify the competitor, including
  model and version, not only a setting.
- **FR-015**: A figure's title MUST be derived from the data it draws.
- **FR-016**: Results MUST be grouped for ranking only when task definitions, track,
  judge, assistance, world revision and workflow contract agree; a group missing a
  pinned judge MUST be marked provisional.

**Experiments (User Story 3)**

- **FR-017**: The corpus MUST be split into a frozen development slate and a frozen
  held-out slate, each hashed, with a manifest recording the draw rule, the seed and
  every task's assignment.
- **FR-018**: A frozen held-out slate MUST NOT be redrawn.
- **FR-019**: A run MUST carry an explicit number of repetitions.
- **FR-020**: A variant test MUST default to the development slate.
- **FR-021**: A variant proposal MUST be refused before any reservation when the task
  count and repetitions cannot produce a conclusive paired result, and the refusal MUST
  state what would be sufficient.
- **FR-022**: A variant MUST reach the held-out slate only after winning on development,
  and each variant lineage MUST reach the held-out slate at most once.
- **FR-023**: Every experiment record MUST carry its pre-registered prediction, its
  parent lineage, and a verdict of supported, not supported or inconclusive.

**Fitness function (User Story 4)**

- **FR-024**: An attempt that builds and then runs a workflow MUST record cost to
  configure and cost to execute separately, reconciling to the total.
- **FR-025**: The same attempt MUST record time to a saved workflow and time per
  execution separately.
- **FR-026**: An unreadable cost on either side MUST be recorded as unknown, never as
  zero, and MUST hold its reservation.
- **FR-027**: The system MUST be able to execute a stored known-correct workflow
  repeatedly and record per-execution cost and time.
- **FR-028**: Cost comparisons between competitors MUST be expressed per successful
  task.

**Rendering (User Story 5)**

- **FR-029**: The system MUST present cumulative cost against number of executions for
  each competitor and name the crossing point, or state that none exists in the observed
  range.
- **FR-030**: A round MUST open with the curve, the accuracy comparison with its
  uncertainty and sample count, and the gap list.
- **FR-031**: The gap list MUST be derived from one evidence base and rendered for
  three audiences without any rendering contradicting another.
- **FR-032**: Each gap item MUST state whether it rests on a confirmed experimental
  result or a reading of code, and unconfirmed items MUST be marked.

**Decided on 11 September**

- **FR-033**: The development and held-out slates MUST be drawn **stratified by
  difficulty tier and by domain**, so that both slates carry the same mix of difficulty
  and the same domain spread. The manifest MUST record the measure used, the tier cut
  points, the domain counts per slate, the seed, and every task's tier, domain and
  hash. The measure MUST be recorded as a structural proxy, not an empirical difficulty,
  and the manifest MUST carry its version so a later classification can supersede it
  without rewriting history.
- **FR-034**: A composed architecture that beats the product on the held-out slate MUST
  become **a written specification handed to the engine team**, carrying the variant,
  the paired result with its uncertainty, the slate and repetitions it was measured on,
  and the evidence for why it wins. The lab does not hand over an executable artifact,
  so node types are not constrained to components the engine already has.
- **FR-035**: Variant tests MUST be admitted by **a standing weekly research envelope
  with a per-experiment ceiling**, which the researcher divides into experiments itself.
  The envelope MUST be set by a person, MUST be counted correctly per FR-005, and a
  proposal that would exceed the remaining envelope or the per-experiment ceiling MUST
  be refused before any reservation, naming the shortfall. Exhausting the envelope MUST
  stop the loop rather than escalate to the weekly ceiling.

### Key Entities

- **Development slate**: A frozen, hashed set of tasks the researcher may iterate on
  within its envelope. Stratified by difficulty tier and domain. Carries its manifest.
- **Held-out slate**: A frozen, hashed set of tasks reserved for confirmation, drawn
  with the same difficulty mix and domain spread as the development slate. Each variant
  lineage may reach it at most once. Never redrawn.
- **Research envelope**: A weekly amount set by a person that bounds all of the
  researcher's experiments, with a per-experiment ceiling. Separate from, and strictly
  inside, the lab's weekly ceiling. When it is exhausted the loop stops.
- **Proposal**: The written specification produced by a held-out confirmation —
  the variant, the paired result with its uncertainty, the slate and repetitions, and
  the evidence for why it wins.
- **Variant**: A proposed change to the design space — an architecture composition, a
  prompt style, a product-graph field, or a technique drawn from research. Carries the
  parent it descends from.
- **Variant lineage**: A variant and all its descendants, for the purpose of the
  once-only held-out rule.
- **Experiment record**: A pre-registered prediction, the variant, the slate used, the
  repetitions, the paired result, the verdict, and the parent link.
- **Curve point**: For one competitor, cumulative cost and time at a number of
  executions, derived from configure and execute measures.
- **Gap item**: Something standing between the product and the frontier, carrying its
  evidence and whether that evidence is a confirmed result or a reading of code.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A caller with no credentials cannot change any state in a running
  attempt's world, verified by attempting every write method against every externally
  reachable path.
- **SC-002**: A workspace started fresh with provider keys performs no paid activity
  until a person enables it, verified over a full scheduled day.
- **SC-003**: With the researcher paused, spend over a full scheduled day is zero.
- **SC-004**: The number shown to a person as the day's spend equals the total reserved
  and settled for every activity attributable to the researcher, within one cent.
- **SC-005**: Rendering the lab's existing ten-task round produces no statement
  contradicted by the stored evidence, checked item by item against the seven defects
  named in the design.
- **SC-006**: Every stored attempt whose task definition has moved is marked in every
  view that shows it; no headline number includes an unmarked one.
- **SC-007**: A variant proposal that cannot reach a conclusive result is refused before
  any money is reserved, in 100% of such cases, and the refusal states the sufficient
  task count.
- **SC-008**: A variant lineage that has reached the held-out slate cannot reach it
  again, verified by attempting it.
- **SC-009**: For an attempt that builds and runs a workflow, configure and execute
  costs sum to the previously reported total within one cent, and the same holds for
  time within one second.
- **SC-010**: A reader can determine, from the round's opening screen alone, at how many
  executions the product becomes cheaper than the compared competitor, or that it does
  not within the observed range.
- **SC-011**: The same round rendered for three audiences contains no fact asserted in
  one rendering and contradicted in another.
- **SC-012**: A full experiment — proposal, development run, verdict, held-out
  confirmation — completes end to end within the research envelope, and its record alone
  is enough for a second person to reconstruct what was tested and concluded.
- **SC-013**: The development and held-out slates differ by no more than one task per
  difficulty tier and per domain, verified from the manifest.
- **SC-014**: With the research envelope exhausted, the researcher performs no paid
  activity and does not draw on the lab's remaining weekly ceiling, verified over a full
  scheduled day.

## Assumptions

- The corpus is large enough to support two stratified slates that each reach a
  conclusive paired result. It holds 800 tasks across seven domains, and the fifty-task
  frozen set is the working reference for slate size, so this holds comfortably. If it
  ever does not, the split rule changes, never the significance requirement.
- The structural difficulty measure the existing tier draw uses — seeded services plus
  expected changes plus tools needed, computed from the task file, cut at the terciles
  of the whole corpus — is computable for every corpus task and is therefore usable for
  stratification today. The direction doc calls it a proxy; the manifest records it as
  one, with a version, so a later empirical or multidimensional classification can
  supersede it without invalidating the frozen slates.
- "Conclusive" means the paired sign test the lab already uses, at its existing
  threshold. This feature does not introduce a new statistical method; it refuses
  experiments the existing method cannot decide.
- Run-only execution of a saved workflow already exists and needs recipe data, not new
  capability. Producing that data is in scope; rebuilding the mode is not.
- The cost boundary between configuring and executing is observable from timestamps
  already recorded, because authoring completes before execution begins. If that is not
  true for some competitor, that competitor reports its split as unknown rather than
  forcing a new telemetry integration.
- Smoke scale and the weekly ceiling keep their existing definitions from the
  constitution. This feature does not change them.
- The three audiences for the gap list are the engine team, the lab, and executives, as
  decided on 11 September. Public release of any rendering remains separately
  authorized.
- Existing frozen task sets, run configurations and historical results are preserved.
  Old rows are not regraded against replacement definitions; they are marked.

## Out of Scope

- Any change to the fixed methodology in `PLAN.md` §1.
- Any widening of what the autonomous researcher may do. Its dials, allowances and
  approval path are repaired here, not extended.
- Any new reporting surface beyond the curve and the gap list.
- A second measurement stack. Measures stay computed once, server-side, from stored
  results.
- Changes to the simulated world's routes, seeds, task requests, initial data or
  assertions, which remain immutable per the 10 September decision.
