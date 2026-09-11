# Genesis opens its own card: the daily initiative job — design of record

Date: 10 September 2026. Written by Claude for Lucas after the adversary review of the
`genesis-loop` branch, which traced why Genesis never starts work on its own. Extends
feature 021 (autonomy) and the loop of `AI-LABS-GENESIS-DEEP-DIVE-2026-09-10.md`.

Fixed rules this design respects (`PLAN.md` §1, constitution §III, decision D5): nothing
grades itself; a launch at smoke scale needs no approval record but anything larger does;
every paid request is reserved in the weekly ledger before it is sent; task prompts, data
and rules are frozen; facts from Monarch's code are internal-only.

## 1. The problem

Genesis is reactive and cannot be otherwise. A card reaches its queue from exactly four
places — `Genesis.intake` called by a person's drop, `Watcher.triggers` on a finished
non-scripted run or a new full-text source, `Genesis.debrief` re-queueing a planned run's
card, and a question card resuming when a person answers. `triggers` further counts only
what arrived after `watcher.json`'s `since` stamp, so history is never re-worked.

On a lab where nothing new lands, the watcher wakes every 30 s, finds an empty queue and
does nothing, for ever. The dials are already permissive (`cards: act`, `runs: smoke`,
not paused); the money gates would allow a $2.00 smoke run today. What is missing is not
permission. It is that nothing ever puts a question in front of Genesis.

## 2. The two decisions Lucas took on 10 September

| # | Question | Decision |
|---|---|---|
| 1 | Which switch governs it | A fourth dial, `initiative`, off by default. `cards: act` keeps meaning "works what it is given"; opening its own card is a separate, explicit act. |
| 2 | How far an initiative card may go | All the way to a paid run. It takes the same path as any other card: the Reviewer accepts, and a plan at smoke scale inside the allowances launches by itself. |

Decision 2 means Genesis both chooses the question and pays to answer it, with no person
in the loop for that round. Everything that already bounds a Genesis launch still binds:
≤ 20 attempts per competitor, ≤ $2.00 per card, ≤ $6.00 a day across every Genesis turn,
the weekly envelope, the weekly ledger, an accepted Reviewer verdict on that exact plan,
and `check_launch`, which refuses any architecture that is not published and launchable.

## 3. The shape: code picks the question, not a model

A daily job `genesis-initiative` runs after its hour on the São Paulo clock, through the
seam the scheduler already offers (`DAILY = (name, hour, fn)`, `wb_studio.scheduler`).
It reads the lab's own records, applies an ordered list of rules, and either queues **one**
card or does nothing.

**It never spends a model request to decide what to ask.** The rules are code over stored
records; when nothing matches, the job costs nothing. This is the same principle the loop
commit set (`d22b459`, "loops that cost nothing when idle"): an autonomous lab that bills
a model every morning to discover it has nothing to do is a lab that bills for silence.

### The rules, in order

The first rule that matches wins. Each names the record it reads, the card it opens and
the question it asks. The card carries the evidence pointer, so the existing tools answer
it without a search.

| # | Signal | Source | Card | Question |
|---|--------|--------|------|----------|
| 1 | A card holds a hypothesis record and no settlement | `listing('cards')`: `card['hypothesis']` set, `card['settlement']` absent | kind `hypothesis`, evidence the card | "Do the runs already recorded settle this? Call `hypothesis_settle`; if they do not, call `hypothesis_plan` and propose the smallest run that would." |
| 2 | A settlement says `inconclusive` and no plan followed it | `card['settlement']['outcome'] == 'inconclusive'`, no later card whose `parent` is this card | kind `hypothesis`, evidence the card | "This came back inconclusive. What is the smallest run that would settle it? Propose it." |
| 3 | A source is Analyzed, a newer source on its topic contradicts it, and nothing has said so | `library.listing()`: `status == 'analyzed'` and `new_evidence` true, no card already pointing at it | kind `source`, evidence the source | "A newer source on this topic disagrees with this one. Which of the two holds on our evidence, and does it change a hypothesis we carry?" |
| 4 | A source is Analyzed and never used | `library.records()`: `status == 'analyzed'`, `used_in` empty, discovered more than 7 days ago | kind `source`, evidence the source | "This has been read and never used. Does it support or contradict a hypothesis we carry, or should it be filed as background?" |

Four rules is the first release. The list is meant to grow; each new rule is one row here,
one branch in code and one test. A rule that cannot name the record it reads does not go
in — an initiative that invents its own prompt is an initiative nobody can audit.

### When the job does nothing

It queues nothing, and records nothing but its stamp, when any of these holds:

- the `initiative` dial is `off` (the default), or `paused` is set
- an auto card is already queued or working — Genesis finishes what it has first
- an initiative card was already opened today (one a day, on the São Paulo clock, the
  same day rule `genesis_skills.earned` uses after this review's fix)
- no rule matches

## 4. The dial

`wb_studio/genesis_autonomy.py` gains a fourth setting beside `cards`, `runs` and `paused`:

```python
INITIATIVE_LEVELS = ('open', 'off')
DEFAULTS = {'cards': 'act', 'runs': 'smoke', 'initiative': 'off', 'paused': False}
WORDS['initiative'] = {
    'open': 'Genesis opens one card a day from the lab\'s open threads, and may take it to a smoke run',
    'off': 'Genesis works only the cards people and triggers give it',
}
```

Off by default, so merging this changes nothing in any running lab until someone turns it
on. `Autonomy.set` validates it like the others and writes the change to the activity
record. It appears on the Genesis configuration page under Settings beside the existing
two, with its sentence, and in `autonomy_words()` so Genesis is told what it is allowed
to do.

## 5. The path an initiative card takes

Nothing new after the card exists. It is an ordinary queued card:

1. `genesis-initiative` queues it (`intake`, `auto: True`, its own `question`).
2. `Watcher.wake` finds it, checks `paused`, `cards`, nothing else working, and
   `refusal()` — the weekly ledger, Genesis's envelope, the daily cap.
3. `Genesis.work` opens one turn under `STUDIO_GENESIS_CARD_USD`.
4. Genesis reads, analyses, writes the analysis back with `save_research`.
5. If the evidence supports an experiment it calls `propose_experiment`, then
   `request_review`; the Reviewer's accept fires `launch_if_allowed` from `ON_TURN`.
6. `may_launch`, the envelope and `gate_launch` decide. Smoke scale inside the
   allowances launches; anything else waits in Approval for a person.
7. The run finishes, `debrief` re-queues the card, Genesis writes the verdict — which,
   since this review, is refused unless the turn has read the run it judges.

Every one of these gates already exists and is tested. This design adds a source of
cards, not a new path for them.

## 6. What it never does

- It never opens more than one card a day, and never while another is queued or working.
- It never asks a question it cannot point at a record for.
- It never runs while `paused`, and never while `initiative` is `off`.
- It never spends a model request to decide what to ask.
- It does not change any money gate. An initiative card is worth exactly what any other
  card is worth: $2.00, inside $6.00 a day, inside the weekly envelope.

## 7. Files

| File | Change |
|---|---|
| `wb_studio/genesis_initiative.py` | New. The rules, `open_threads(genesis)` returning the matches in order, `initiative(studio)` the job, and `DAILY = ('genesis-initiative', 7, initiative)`. |
| `wb_studio/scheduler.py` | Add the module to `MODULES`, after `genesis_sleep` so the night's records are in before the morning reads them. |
| `wb_studio/genesis_autonomy.py` | The `initiative` dial: `INITIATIVE_LEVELS`, `DEFAULTS`, `WORDS`, validation in `set`, the sentence in `autonomy_words`. |
| `wb_studio/static/genesis.js` | The dial in the autonomy block of the configuration page. |
| `wb_studio/genesis_channels.py` | One line in the weekly digest's `gates`: how many cards Genesis opened for itself. |
| `wb_studio/GENESIS.md` | One paragraph: what an initiative card is, so Genesis knows a card may be its own. |

## 8. The tests that must exist

- The job queues nothing and costs nothing when the dial is off, when paused, when a card
  is already queued or working, when one was opened today, and when no rule matches.
- Each of the four rules, on a record that matches and one that does not.
- The first matching rule wins and only one card is queued.
- The card it opens is `auto`, carries its evidence pointer and its own question, and the
  watcher takes it on the next wake.
- The day rule is the São Paulo day, not the UTC prefix (the bug this review fixed in
  `genesis_skills.earned`; the same shape must not come back here).
- An initiative card reaches a smoke launch through the ordinary gates, and is refused by
  `may_launch` when its plan is above smoke scale.

## 9. Rejected

**A model turn each morning that reads the board and chooses.** More flexible, and it
spends money every day to discover the lab is quiet. It also puts the choice of what to
investigate somewhere nobody can audit; a rule list is a thing Lucas can read and argue
with. If the rule list proves too rigid, the upgrade is a model turn *ranking* rules that
already matched — still bounded, still auditable.

**Reusing the `cards` dial.** Smallest diff, but it silently widens what `act` means for a
lab already running with it on. The trust boundary is the whole point of the feature.

**More than one card a day.** The watcher works one card at a time; a queue Genesis fills
faster than it empties is a backlog, not initiative.

## 10. Open for Lucas

- The hour. 7 São Paulo is proposed: after the 03:00 night and the 04:00 code index, so
  the morning reads a settled record; before the 08:00 brief, so what it opened shows up
  in the brief.
- Rule 4's seven-day wait before an unused source counts as an open thread.
- Whether an initiative card should be marked as such on the board (`kind` stays
  `hypothesis` or `source` so the existing skills and questions keep working; a separate
  `by: 'genesis:initiative'` on the card would let the board show it without a new kind).
