# Feature Specification: A spoken colleague that builds the Studio live

**Feature Branch**: `025-genesis-voice-live-build`

**Created**: 2026-09-11

**Status**: Draft

**Input**: Design of record [`docs/superpowers/specs/2026-09-11-genesis-voice-live-build-design.md`](../../docs/superpowers/specs/2026-09-11-genesis-voice-live-build-design.md), written after a survey of public agents and repositories building the same shape and three design decisions taken by Lucas on 11 September 2026.

## Context

Genesis today is read and written. A person drops a card, Genesis works it, and the
answer arrives as a document. This feature makes Genesis a colleague a person can talk
to, that shows what it is talking about, and that can change the lab's own interface
while the conversation is happening.

Three things have to be true for that to be worth building rather than a demonstration.
Genesis must be unable to say a number it did not measure. It must still remember, in a
year, what it did this month. And it must know how often it has been right. Each of
those is a mechanism with public evidence behind it, recorded in the design of record.

The line that makes live building safe already exists in the code: Genesis reads two
checkouts, the product under test and the lab's own source. **The Studio is not the
product under test.** Changing the lab's own interface touches no frozen task, no
configuration hash, no stored run and no grading. This feature wires an apply path to
the lab's source and to nothing else.

Feature 024 owns the gates, the daily and weekly envelopes, the approval path, the task
slates and the pre-registered prediction field. This feature consumes all of them and
does not duplicate, widen or contradict any of them.

Per constitution §III, this feature changes the methodology's **inputs and interaction
surface** — a spoken interface, a checking pass, a memory format, a preview — and does
not reopen any rule in `PLAN.md` §1.

## Live workspace expansion

Lucas's 11 September direction adds rich streaming, meaningful loading states and visible
artifact alteration while preserving Studio's current style. The detailed
[live workspace plan and web inspiration](../../research/genesis-live-workspace-plan-2026-09-11.md)
extends this specification. Story 6 and FR-044–FR-059 cover application-data editing;
story 3 continues to govern checked changes to the Studio's own source. Neither makes
a draft edit equivalent to a paid run, deployment or product-under-test modification.

Ten decisions taken by Lucas on 11 September, after reading that plan against the code,
are recorded as D1–D10 in its Decisions section and are settled inputs here, not options.
The ones that bind this specification: the edited object is the architecture blueprint
`static/graph.js` already edits (D2); Follow ships on by default, reversing the
feature 024 stage S5 default (D3); Genesis builds through incremental operations that
stream to the open editor and are committed by one existing `save_architecture` (D6, D7);
each operation is validated server-side (D8); a field the person has focus in is
soft-locked and a commit is refused while the editor is dirty (D4, D5); and artifact
editing gets its own autonomy dial, shipping on (D9, D10).


## User Scenarios & Testing *(mandatory)*

### User Story 1 - A number that was not measured cannot be said (Priority: P1)

Lucas asks Genesis what the pass rate was on the last round. Genesis answers with the
figure the lab computed, and cites the run it came from. On another question Genesis
produces a number the lab never measured; the lab refuses it, and Genesis says so and
points at the record instead of stating the figure.

**Why this priority**: The lab's whole output is numbers about other people's systems.
A colleague who can misquote a run is worse than no colleague, and speech removes the
one safeguard writing has — nobody re-reads a sentence they heard. This story is also
a hard dependency: the split-honesty decision that admits story 2 *is* this gate, so
story 2 cannot be built without it. It delivers value alone, because it protects reports
and card verdicts whether or not anyone ever speaks to Genesis.

**Independent Test**: Take a finished round, ask for its results through the existing
written path, and confirm every number in the answer resolves to a recorded measurement.
Then run a deliberately fabricating fixture through the same path and confirm the output
is refused rather than emitted. Delivers a lab whose stated numbers are its measured
numbers.

**Acceptance Scenarios**:

1. **Given** a finished round, **When** its measurements are recorded, **Then** the lab
   holds every value the round produced — each condition's average, its spread, and each
   individual repetition — each addressable by the record it came from.
2. **Given** a request for a figure the lab has measured, **When** the answer is
   produced, **Then** the figure in the answer is the recorded value and names the record
   it came from.
3. **Given** a finished answer containing a number that matches no recorded measurement,
   **When** the answer is checked before release, **Then** the answer is refused and the
   unmatched number is named.
4. **Given** an answer that restates a recorded value in different words or units,
   **When** it is checked, **Then** the restatement is matched to the recorded value or
   refused; a number is never accepted because it is close to one.
5. **Given** a refused answer, **When** the person is told, **Then** they are told which
   number failed and where the supporting record is, and the unverified number is not
   repeated to them as fact.
6. **Given** a fixture that deliberately fabricates measurements, **When** it produces an
   answer, **Then** the answer is refused.
7. **Given** a source cited in the research library, **When** it is checked, **Then** it
   is classified as verified, suspicious or unfindable, and an unfindable source is
   removed from the citation rather than presented.
8. **Given** a number in a sentence of interpretation rather than of result, **When** the
   answer is checked, **Then** the same rule applies; there is no section in which an
   unverified number may appear.

---

### User Story 2 - A colleague you can talk to (Priority: P2)

Lucas opens the lab's site, starts talking, and Genesis answers out loud. He can
interrupt it. When he asks something that needs work, Genesis starts working and keeps
talking while it works, telling him what it is doing as it does it. Everything it does
while they talk is recorded under his name. The conversation costs money and that money
is counted in the same place as everything else.

**Why this priority**: This is the feature. It is second only because the honesty gate
in story 1 is what makes it safe to ship, and the two go out together as the first
slice.

**Independent Test**: Open a session on the hosted lab, ask a question answerable from
recorded evidence, and confirm the answer is spoken, correct and attributed. Ask a
question requiring work and confirm the conversation continues while the work runs and
that the work's progress is described. Close the session and confirm the recorded cost
matches its duration. Delivers a lab you can consult without typing.

**Acceptance Scenarios**:

1. **Given** a person with a key, **When** they start a spoken session, **Then** the
   session opens without the lab's provider credentials reaching their browser.
2. **Given** an open session, **When** the person interrupts mid-sentence, **Then**
   Genesis stops and responds to the interruption.
3. **Given** a question that needs work, **When** Genesis begins working, **Then** the
   conversation continues and the person is told what is happening as each step
   completes, without waiting for the work to finish.
4. **Given** a spoken answer carrying a number or a record claim, **When** it is
   produced, **Then** it came from a completed piece of work and passed the check in
   story 1 before being spoken.
5. **Given** a spoken answer of framing, opinion or conversation carrying no number and
   no record claim, **When** it is produced, **Then** it may be spoken directly.
6. **Given** an open session, **When** Genesis speaks, **Then** what it says is governed
   by the same identity file that governs its written work.
7. **Given** a session that opens, **When** it starts, **Then** its maximum cost is
   reserved before any audio flows, and on closing it is settled for the time actually
   used.
8. **Given** the day's or week's allowance is exhausted, **When** a person tries to open
   a session, **Then** it is refused before any audio flows and the refusal names the
   shortfall.
9. **Given** Genesis is paused, **When** a person tries to open a session, **Then** it is
   refused.
10. **Given** an open session, **When** Genesis takes any action, **Then** the action is
    recorded as taken by the named person holding the session.
11. **Given** the lab's site, **When** it is loaded, **Then** the spoken provider's
    connection is the only outside connection it is permitted to make, and this is
    asserted by a test.
12. **Given** a session that reaches its time or cost ceiling, **When** the ceiling is
    reached, **Then** the session ends, is settled, and the person is told why.

---

### User Story 3 - It builds the interface while you watch (Priority: P3)

Lucas says a report's table is hard to read. Genesis works out the change, builds it,
checks that the lab's own tests still pass, and the page he is looking at turns into the
new version in front of him with an accept control. He accepts and it stays; he rejects
and it goes back, with the change kept on a card.

**Why this priority**: This is the second half of what was asked, and it depends on
nothing in stories 1 or 2 — but it is riskier, because it is the only part of this
feature that changes running code, and it is worth shipping after a conversation you can
already trust.

**Independent Test**: Ask for a visible change to one page, and confirm the change is
built, checked, shown in place, accepted and present — and that a rejected change leaves
the page as it was with the work preserved. Delivers a lab that can improve its own
interface at conversational speed.

**Acceptance Scenarios**:

1. **Given** a request to change the lab's interface, **When** Genesis builds it,
   **Then** the work happens in a disposable copy and the running lab is untouched.
2. **Given** a built change, **When** it is checked, **Then** the lab runs the check
   itself from a fixed list of permitted checks, never a command a model supplied.
3. **Given** a change that does not apply cleanly, or whose check fails, **When** it is
   finished, **Then** it never reaches the page, and the person is told what failed.
4. **Given** a checked change, **When** it is shown, **Then** the page being viewed
   transitions from the current version to the new one in place, with a control to accept
   or reject.
5. **Given** a shown change that has not been accepted, **When** anyone else loads the
   lab, **Then** they see the current version, not the proposed one.
6. **Given** a rejected change, **When** it is rejected, **Then** the page returns to the
   version it had and the work is kept on a card.
7. **Given** an accepted change, **When** it is accepted, **Then** it becomes the running
   version and the record names the person who accepted it.
8. **Given** any accepted change to the lab's interface, **When** it takes effect,
   **Then** no frozen task, no configuration hash, no stored run and no grading result
   has changed, verified by comparison.
9. **Given** a proposed change to the product under test rather than to the lab, **When**
   it is produced, **Then** it remains a proposal and is never applied by this feature.
10. **Given** a conversation about a particular view, **When** Genesis refers to it,
    **Then** it can bring that view onto the screen, and doing so changes nothing and
    takes no action on the person's behalf.

---

### User Story 4 - It still knows, a year from now, what it did this month (Priority: P4)

Lucas asks Genesis about something it worked on months ago. It remembers — not because
the record was searched and something plausible came back, but because what mattered was
kept and what did not was dropped for a stated reason.

**Why this priority**: This is the part of the request that speech cannot deliver and
that decays silently if left alone. It is fourth because the decay takes months, so
nothing breaks tomorrow — but every month it is not done is a month of memory that
cannot be recovered.

**Independent Test**: Run the nightly consolidation repeatedly against a growing record
and confirm the lab's memory grows and prunes by localized change rather than being
rewritten, that entries carry their usefulness, and that nothing pinned is ever lost.
Delivers a memory that survives its own maintenance.

**Acceptance Scenarios**:

1. **Given** the lab's memory, **When** an entry is added, **Then** it carries a stable
   identifier and the record it came from.
2. **Given** an entry that has been used in answering, **When** it is used, **Then** its
   usefulness is counted.
3. **Given** the nightly consolidation, **When** it proposes changes, **Then** it
   proposes a small set of additions, edits and removals, and never replaces the whole
   memory at once.
4. **Given** memory within its budget, **When** consolidation runs, **Then** no entry is
   removed for redundancy.
5. **Given** memory over its budget, **When** consolidation runs, **Then** redundant
   entries are merged or dropped, and each removal names why.
6. **Given** an old entry that is still used, **When** consolidation runs, **Then** it is
   kept; **Given** a recent entry nothing has ever used, **Then** it is a candidate for
   removal.
7. **Given** a pinned entry, **When** consolidation runs, **Then** it is never removed or
   rewritten.
8. **Given** proposed changes, **When** they are proposed, **Then** a person adopts them,
   as they do today.
9. **Given** a consolidation that would exceed the budget, **When** it runs, **Then** it
   fails without changing anything, as today.

---

### User Story 5 - It knows how often it is right (Priority: P5)

Genesis proposes an experiment and says what it expects. The experiment runs. Afterwards
the lab records whether the expectation held. When Lucas asks how often Genesis is right
about that kind of question, the answer is a number the lab computed.

**Why this priority**: It is the difference between a confident assistant and a
colleague, and it is the cheapest of the five to build because the prediction is already
recorded by feature 024. It is last because everything above works without it.

**Independent Test**: Record a prediction, run the experiment, and confirm the lab scores
it and that the running record is visible and cited. Delivers proposals disciplined by a
measured hit rate.

**Acceptance Scenarios**:

1. **Given** a finished experiment carrying a pre-registered expectation, **When** its
   result is recorded, **Then** the lab records whether the expectation held, did not
   hold, or could not be decided.
2. **Given** a set of scored expectations, **When** the track record is requested,
   **Then** it is computed by the lab from those records and carries the records it rests
   on.
3. **Given** a track record, **When** Genesis prepares its next proposal, **Then** the
   track record is part of what it is given.
4. **Given** a question about how often Genesis has been right, **When** it answers,
   **Then** the figure is the computed one and is subject to the check in story 1.
5. **Given** too few scored expectations to say anything, **When** the track record is
   requested, **Then** it says so rather than reporting a rate.

---

### User Story 6 - Genesis builds and changes the working artifact visibly (Priority: P2)

Lucas asks Genesis, by text or voice, to create a development workflow, connect its
steps and insert their prompts. The existing workspace shows the structure and content
as they become available, distinguishes drafts from saved changes, and leaves an
inspectable artifact. The same interaction extends to research, experiment plans,
measured reports and the checked interface previews in story 3.

**Why this priority**: Genesis's work must be understandable and steerable while it
happens. A final chat response alone does not show what changed or whether it was saved.

**Independent Test**: Use a marked development fixture to create, connect, fill and save
a workflow while observing the page; reload and confirm that the same saved artifact
appears. Repeat with an interruption, a conflicting manual edit and a validation failure.

**Acceptance Scenarios**:

1. **Given** an authorized draft-edit request, **When** Genesis creates nodes, connections
   and prompts, **Then** each appears in the actual artifact as a distinct provisional
   state, and only the commit produces a saved revision.
2. **Given** an unfinished prompt or invalid connection, **When** it is displayed,
   **Then** it is labeled as a draft or problem and cannot be mistaken for an executable,
   validated result.
3. **Given** a connection interruption, **When** updates resume, **Then** each operation
   is applied exactly once, and the graph shown matches the graph an uninterrupted
   delivery would have produced.
4. **Given** a person with focus in a prompt field, **When** an operation targets that
   same field, **Then** their text is preserved, the operation waits, and it is applied
   when they leave the field.
5. **Given** a person holding unsaved edits to a draft, **When** Genesis attempts to
   commit that draft, **Then** the commit is refused with that reason and kept on a card,
   and their unsaved edits remain valid against the revision they were made on.
6. **Given** an uncommitted build, **When** the page is reloaded, **Then** the provisional
   work is gone, the turn's record still shows what was done, and nothing reports a save
   that did not happen.
7. **Given** background work, **When** the person makes any gesture, **Then** the camera
   stops following for the rest of that turn, progress remains available, and focus is
   never taken.
8. **Given** a failed or cancelled operation, **When** it stops, **Then** completed
   changes remain accurately identified and unfinished work has a clear recovery path.
9. **Given** reduced motion or keyboard-only interaction, **When** the same work occurs,
   **Then** all states, content and controls remain available without animation or dragging.
10. **Given** an ordinary draft save, **When** it completes, **Then** no paid execution,
    product-under-test change or publication follows implicitly.

---


### Edge Cases

- The spoken model produces a number before any work has returned: the number is not
  spoken, and the person hears that the answer is still coming.
- A person interrupts while work is running: the work continues; abandoning the question
  cancels it and settles what it spent.
- The network drops mid-session: the reservation is settled for the time actually used,
  not held at the ceiling indefinitely.
- Two sessions are opened at once by the same person: the second is refused or counted
  separately, and never shares the first's reservation.
- A change is accepted while another change is still being shown: the second is rebuilt
  against the accepted version or refused, never applied on top of a stale copy.
- The worker holding the checkouts is not running: a request to change the interface is
  refused with that reason, and nothing is shown as if it had been built.
- An accepted change breaks the running lab: the previous version is recoverable without
  editing files by hand.
- A recorded measurement is later regraded or its task definition moves: numbers already
  spoken are not retracted, but the record they cite carries the move, as it does today.
- Consolidation proposes removing an entry that the same night's work relied on: the
  removal names the conflict and is not adopted silently.
- An expectation is recorded for an experiment that is never run: it is neither scored
  nor counted against the track record.

## Requirements *(mandatory)*

### Functional Requirements

**Measured numbers (User Story 1)**

- **FR-001**: The system MUST record, for every completed round, each value it produced —
  per-condition averages, their spread, and each individual repetition — addressable by
  the record it came from.
- **FR-002**: Spoken output, report results and card verdicts MUST be composed only from
  recorded values.
- **FR-003**: The system MUST check every finished answer in an independent pass that
  re-reads it, extracts each numeric claim, and matches it against the recorded values;
  this pass MUST NOT be the same step that wrote the answer.
- **FR-004**: An answer containing a numeric claim that matches no recorded value MUST be
  refused rather than emitted, and the refusal MUST name the unmatched claim.
- **FR-005**: A restated or converted value MUST be matched to its recorded value or
  refused; proximity to a recorded value MUST NOT be sufficient.
- **FR-006**: On refusal the person MUST be told which claim failed and where the
  supporting record is, and the unverified value MUST NOT be presented to them as fact.
- **FR-007**: The system MUST refuse an answer produced by a deliberately fabricating
  source, demonstrated by a fixture built for that purpose.
- **FR-008**: A cited source MUST be classified as verified, suspicious or unfindable
  against public identifiers, and an unfindable source MUST be removed from the citation
  rather than presented.
- **FR-009**: The rule in FR-002 through FR-004 MUST apply to every part of an answer;
  there MUST be no section exempt from it.

**Speaking (User Story 2)**

- **FR-010**: A person holding a key MUST be able to open a spoken session with Genesis
  from the lab's site, and the lab's provider credentials MUST NOT reach their browser.
- **FR-011**: The lab, not the spoken model, MUST decide which results reach the spoken
  channel.
- **FR-012**: A spoken sentence carrying a number or a record claim MUST originate from a
  completed piece of Genesis's work and MUST have passed FR-003 before it is spoken.
- **FR-013**: A spoken sentence carrying no number and no record claim MAY be produced
  directly by the spoken layer.
- **FR-014**: The identity file MUST govern the spoken layer as it governs the written
  protocol.
- **FR-015**: While work runs, the conversation MUST continue and the person MUST be told
  what is happening as each step completes.
- **FR-016**: A person MUST be able to interrupt Genesis mid-sentence and be answered.
- **FR-017**: A session MUST reserve its maximum cost before any audio flows and MUST
  settle for the duration actually used when it closes, including when it closes
  abnormally.
- **FR-018**: A session's cost MUST be counted inside feature 024's existing daily and
  weekly allowances. This feature MUST NOT introduce a spending ceiling outside them.
- **FR-019**: A session MUST be refused, before any audio flows, when the allowance
  cannot cover it or when Genesis is paused, and the refusal MUST state which.
- **FR-020**: Every action taken during a session MUST be recorded as taken by the named
  person holding it.
- **FR-021**: A session MUST have a time and cost ceiling; reaching it MUST end and settle
  the session and tell the person why.
- **FR-022**: The spoken provider's connection MUST be the only outside connection the
  lab's site is permitted to make, and a test MUST assert the permitted set.

**Building the interface (User Story 3)**

- **FR-023**: A change to the lab's own interface MUST be built in a disposable copy,
  leaving the running lab untouched until a person accepts it.
- **FR-024**: The lab MUST run the check on a built change itself, from a fixed list of
  permitted checks; a command supplied by a model MUST NOT be run.
- **FR-025**: A change that does not apply cleanly, or whose check fails, MUST NOT be
  shown as a proposal, and the failure MUST be reported.
- **FR-026**: A checked change MUST be shown by transforming the page being viewed from
  the current version to the proposed one in place, with a control to accept or reject.
- **FR-027**: An unaccepted change MUST be visible only to the person it is being shown
  to; every other visitor MUST see the current version.
- **FR-028**: Rejecting MUST restore the current version and MUST keep the work on a card.
- **FR-029**: Accepting MUST make the change the running version and MUST record the
  person who accepted it.
- **FR-030**: Accepting a change to the lab's interface MUST NOT alter any frozen task,
  configuration hash, stored run or grading result, and this MUST be verified rather than
  assumed.
- **FR-031**: A proposed change to the product under test MUST remain a proposal and MUST
  NOT be applied by this feature under any circumstance.
- **FR-032**: An accepted change that breaks the running lab MUST be reversible by a
  recorded action, without editing files by hand.
- **FR-033**: Genesis MUST be able to bring a named view onto the screen during a
  conversation; doing so MUST change no state and MUST take no action on the person's
  behalf beyond moving the view. Whether the view moves is the reader's own setting,
  which ships on and is turnable off (FR-050); the tool itself MUST only produce a link,
  and MUST never move focus.

**Remembering (User Story 4)**

- **FR-034**: Every memory entry MUST carry a stable identifier, the record it came from,
  and a count of how often it has been useful.
- **FR-035**: The nightly consolidation MUST propose a small set of additions, edits and
  removals, and MUST NOT replace the memory as a whole.
- **FR-036**: Redundant entries MUST be merged or dropped only when the memory exceeds its
  budget, never on a schedule, and each removal MUST name its reason.
- **FR-037**: Retention MUST be decided by usefulness rather than age alone.
- **FR-038**: Pinned entries MUST never be removed or rewritten by consolidation.
- **FR-039**: A person MUST continue to adopt what the night proposes, and a consolidation
  that would exceed the budget MUST fail without changing anything.

**Knowing its own record (User Story 5)**

- **FR-040**: After an experiment carrying a pre-registered expectation completes, the
  system MUST record whether the expectation held, did not hold, or could not be decided.
  This feature MUST NOT re-specify the expectation itself, which feature 024 owns.
- **FR-041**: The track record MUST be computed by the lab from scored expectations and
  MUST carry the records it rests on.
- **FR-042**: The track record MUST be part of what Genesis is given when it prepares a
  proposal.
- **FR-043**: A stated track record MUST be subject to FR-003, and MUST say so rather than
  report a rate when too few expectations have been scored.

### Live workspace and rich progress

- **FR-044**: Genesis's authorized artifact edits MUST appear in the existing workspace
  as structure and content become available, including nodes, connections and prompt fields.
- **FR-045**: The interface MUST distinguish provisional content, saved changes,
  validation results and execution results; none may imply another.
- **FR-046**: Work MUST expose meaningful queued, active, waiting, reconnecting, failed,
  cancelling and terminal states, with known progress counts only when supported.
- **FR-047**: Reconnecting or receiving repeated updates MUST apply every operation
  exactly once, including operations immediately preceding completion.
- **FR-048**: An operation targeting the field the person currently has focus in MUST NOT
  overwrite it; it MUST wait and be applied when focus leaves the field.
- **FR-049**: While the open editor holds unsaved edits to a draft, a commit to that draft
  MUST be refused with that reason and kept on a card; the person's unsaved edits MUST
  remain valid against the revision they were made on.
- **FR-050**: Conversation and artifacts MUST share explicit selection context. Following
  MUST move the view only, never focus; MUST stop on any gesture for the remainder of the
  turn; MUST be turnable off; and MUST degrade to a link when the target is not visible.
- **FR-051**: Live surfaces MUST preserve the incumbent visual style and support narrow
  screens, keyboard interaction, reduced motion and meaningful accessible status updates.
- **FR-052**: Every enabled alteration capability MUST identify its target, pending and
  completion states, recovery behavior and evidence; an unsupported rich view MUST fall
  back to a clear receipt and object link.
- **FR-053**: Pausing visual updates, interrupting speech, cancelling work, breaking
  following and undoing an edit MUST remain distinct controls with accurate outcomes.
- **FR-054**: Rich presentation MUST NOT widen any existing authorization, spending,
  publication, frozen-data or product-under-test boundary.
- **FR-055**: The person MUST be able to inspect the affected object, discard provisional
  work before the commit, and undo after it as a recorded revision, without erasing
  history or implying external rollback.
- **FR-056**: Genesis MUST build through incremental operations — at minimum adding a
  node, connecting two nodes, and setting a prompt field — delivered on the existing turn
  stream and applied by the open editor as provisional state. An operation MUST NOT be a
  durable write, and a single existing architecture save MUST commit the build as one
  revision. Uncommitted work MAY be lost on reload, and its loss MUST NOT be reported as
  a save.
- **FR-057**: Each operation MUST be validated by the lab's own existing blueprint
  validation before it is presented as valid; a validation failure MUST be shown against
  the node or connection that caused it without discarding the rest of the build.
- **FR-058**: Artifact editing MUST be governed by its own autonomy dial, separate from
  reading, cards, runs and the engineer loop, and MUST obey the existing pause. The dial
  ships on; no other dial's meaning changes.
- **FR-059**: A tool description given to Genesis MUST state what the tool actually does
  to the person's screen. The `show` tool's description MUST be corrected before following
  is enabled by default, and the recorded rationale for the following default MUST match
  the shipped default.


### Key Entities

- **Recorded value**: One measurement a round produced — a per-condition average, a
  spread, or a single repetition — addressable by the record it came from. The only thing
  a number in an answer may be.
- **Check result**: The outcome of re-reading a finished answer against the recorded
  values: the claims found, which matched, and which did not.
- **Spoken session**: One conversation. Carries the person holding it, its reservation,
  its ceilings, and the work started during it.
- **Interface change**: A proposed change to the lab's own source. Carries the request it
  came from, the disposable copy it was built in, the check that was run and its result,
  and its state — built, shown, accepted or rejected.
- **Memory entry**: One durable fact. Carries a stable identifier, the record it came
  from, how often it has been useful, and whether it is pinned.
- **Memory delta**: A small set of proposed additions, edits and removals a person adopts,
  each naming its reason.
- **Scored expectation**: A pre-registered expectation from feature 024 paired with what
  happened, and a verdict of held, did not hold, or undecided.
- **Track record**: The rate computed from scored expectations, with the records it rests
  on and the count behind it.
- **Operation**: One described change to an artifact — a node added, two nodes connected,
  a prompt field set — carried on the turn's stream, applied by the open editor as
  provisional state, and validated on its own. It is not a write and has no revision.
- **Commit**: The single existing save that turns a build's provisional state into one
  saved revision. The only durable point in a build, and the only thing that can be
  refused for a stale or dirty draft.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across a full replay of the lab's existing rounds, every number in every
  produced answer resolves to a recorded measurement, or the answer was refused — with no
  exceptions.
- **SC-002**: A deliberately fabricating fixture is refused in 100% of attempts.
- **SC-003**: A person can ask a question of the lab out loud and receive a correct spoken
  answer without typing, on the hosted lab, from an ordinary browser.
- **SC-004**: When a spoken question requires work, the person hears what is happening
  within a few seconds and continues the conversation while the work runs, rather than
  waiting in silence for it to finish.
- **SC-005**: The recorded cost of a spoken session matches its actual duration within one
  cent, including sessions that ended abnormally.
- **SC-006**: With the allowance exhausted or Genesis paused, no session opens and no
  audio flows, verified by attempting it.
- **SC-007**: Every action taken during a spoken session names the person who held the
  session, with no action attributed to the lab itself.
- **SC-008**: A requested change to one view is built, checked, shown in place and
  accepted within a single conversation, and is present afterwards for everyone.
- **SC-009**: A rejected change leaves every page byte-identical to its prior state and
  the work retrievable from its card.
- **SC-010**: After any accepted interface change, a comparison of frozen tasks,
  configuration hashes, stored runs and grading results shows no difference.
- **SC-011**: No change to the product under test is ever applied, verified by attempting
  it.
- **SC-012**: Over a simulated year of consolidation against a growing record, the memory
  stays within budget, retains every pinned entry, and retains every entry that has been
  useful more than once — verified against a recorded baseline rather than by inspection.
- **SC-013**: A person can read, for any removed memory entry, why it was removed.
- **SC-014**: A complete cycle — expectation recorded, experiment run, expectation scored,
  track record updated and stated — completes end to end, and the stated rate equals the
  rate computed from the underlying records.
- **SC-015**: The lab's site makes no outside connection other than the spoken provider's,
  verified by the test that asserts the permitted set.

- **SC-016**: A development blueprint can be visibly created, connected, filled with
  prompts and saved from one request; reloading yields the same saved revision.
- **SC-017**: Replays containing interruptions, duplicates and completion immediately
  after an operation yield the same final artifact as uninterrupted delivery.
- **SC-018**: A prompt being typed into is never overwritten by a Genesis operation, and
  a commit attempted against an editor holding unsaved edits is refused rather than
  applied — both verified by attempting them, not by inspection.
- **SC-019**: Every enabled alteration capability has observable pending, success and
  failure states with an inspectable target and evidence record.
- **SC-020**: The workflow scenario remains operable with keyboard-only input, reduced
  motion and a narrow viewport; background updates preserve reading position and focus.
- **SC-021**: A gesture during a followed turn stops the camera and it stays stopped for
  the rest of that turn, verified by attempting it in both themes.
- **SC-022**: No number of operations produces more than one saved revision per commit,
  and a reload before the commit leaves no partially saved blueprint behind.


## Assumptions

- **Feature 024 lands first, or its gates land first.** This feature consumes 024's daily
  and weekly allowances, its pause, its approval path and its pre-registered expectation
  field. If 024 is not complete, the parts it owns are prerequisites, not scope here.
- **The hosted lab holds the conversation; a trusted local worker holds the checkouts.**
  The existing coordinator-and-worker arrangement is used as it stands. A request to
  change the interface while no worker is connected is refused with that reason.
- **Changes that touch only what the browser loads are in scope; changes that touch the
  lab's server code are deferred.** The first are the majority of what is asked for in
  conversation and need no second running copy; the second do, and can follow. A request
  that would require the deferred kind is refused with that reason, not partially built.
- **One session at a time per person**, with a default ceiling of thirty minutes and a
  cost ceiling set alongside the other Genesis ceilings. These are settings, not rules.
- **Interruption, turn-taking and speech quality are the spoken provider's
  responsibility.** This feature does not build voice activity detection, and treats the
  provider's behaviour as given.
- **The check in story 1 applies to numbers and record claims, not to every factual
  statement.** Framing, interpretation and opinion carry no number and are not gated;
  this is Lucas's split-honesty decision of 11 September, recorded in the design.
- **Existing behaviour is preserved**: the nightly consolidation still proposes and a
  person still adopts; pinned entries are still set by people; refusals still come back as
  sentences; every existing Genesis refusal still applies inside a spoken session.
- **Public release of anything produced remains separately authorized**, as today.
- **The four deferred research mechanisms** — funnel economics for proposals, evaluation
  of self-authored skills, the self-refutation gate, and publishing the minimum
  detectable effect — are recorded in the bench's deferred list with their sources, and
  are not scope here.

## Open Questions

Two decisions carry real consequence and have no safe default. Both are recorded in the
design of record and must be settled before planning.

- **Q1 — What does "accept" do about pushing?** Accepting a change means committing it,
  and the hosted lab redeploys from the repository. The constitution says pushes require
  Carlos's explicit request and the repository is public. Either Carlos gives a standing
  decision for the lab's own interface, or accepting stops at a local commit on the
  worker and deployment stays a separate, human act. The second is the conservative
  reading and is what this spec assumes until decided.
- **Q2 — Should the hosted lab hold provider credentials at all?** A spoken session is a
  live connection into a process that holds them, and the environment loader already
  reached the test suite once and was guarded. Keeping credentials only on the local
  worker is safer but means the hosted lab cannot run a turn by itself, which changes the
  architecture. This spec assumes credentials stay where they are today until decided.

## Out of Scope

- Any change to the fixed methodology in `PLAN.md` §1.
- Any change to the simulated world's routes, seeds, task requests, initial data or
  assertions, which remain immutable per the 10 September decision.
- Applying any change to the product under test. It stays proposal-only.
- Any spending ceiling outside feature 024's allowances.
- Anything feature 024 owns: the gates, the envelopes, the approval path, the task slates,
  the pre-registered expectation field.
- Changes to the lab's server code shown live; deferred to a later slice.
- Public release, Slack posting or publication of anything produced in a conversation.
- A second memory system, a second measurement stack, or a second Genesis. Voice is a
  surface on the existing one.
- Live editing of any artifact other than the architecture blueprint (D2). The generated
  workflow artifact and Monarch recipes keep their own contracts and are not edited by
  the operations this feature adds.
- Server-side pending state for an uncommitted build (D7). A build lives in one browser
  until it is committed.
