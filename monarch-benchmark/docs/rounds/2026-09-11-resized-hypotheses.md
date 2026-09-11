# The queued hypotheses, re-sized against the test that settles them

Date: 11 September 2026. Feature 024, FR-021 (task T074).

`genesis_hypotheses.smallest_plan` sized an experiment with `n = ceil(4·p·(1−p)/d²)`
floored at ten tasks — the textbook size for comparing two **independent** proportions.
`settle` decides the same hypothesis with `measures.paired` → `measures.sign_test`, a
two-sided sign test that pairs by task and drops ties. Those are different statistics,
and below six discordant pairs the sign test cannot reach p < 0.05 at any win count.

The rule is now `n = ceil(6/d)`: a declared minimum effect is the share of tasks a real
difference is expected to flip, so it is the expected discordant-pair rate. This record
re-sizes what was queued when the rule changed, and states which of it could never have
been settled.

## What was actually queued

`memory/TRACK.md` reports "Hypotheses: 7 proposed; 0 supported, 0 not supported, 0
inconclusive, 7 untested". That count is of **cards whose kind is `hypothesis`**, not of
hypothesis records. Only one of the seven carries a record:

| Card | Stage | Record | Title |
|---|---|---|---|
| `70934e3e` | review | **yes** | Does GLM 5.3 stay inside the change scope on the Lisa Park relocation task |
| `eeae0e5d` | research | no | the same question, filed twice |
| `505124a7` | hypothesis | no | Monarch fails more often on tasks that touch two applications |
| `2e99c71e` | approval | no | "Experiment" |
| `6d837f15`, `7694274c`, `b2436725` | review | no | "E2E smoke: one task, GLM 5.3 on Fireworks", three of the duplicates the watcher loop created on 10 September |

So the track record overstates the lab's hypothesis count by a factor of seven. It is
computed by the Studio, not written by Genesis, and it counts card kind. Worth correcting
separately; noted here because "7 untested" reads as a backlog of science and is not one.

## The one real record, re-sized

```
claim            GLM 5.3 stays inside permitted change scope without violations on the
                 Lisa Park relocation task compared to baseline.
measure          violations        direction  a_lower        minimum_effect  0.5
population       filter: task_ids = ["simple.email_sf_contact_city_update"]
```

| | Tasks | Can it be settled? |
|---|---|---|
| Old rule, `max(10, ceil(4·0.25/d²))` | 10 | **No** — 10 × 0.5 = 5 expected discordant pairs, below the floor of 6 |
| New rule, `ceil(6/d)` | 12 | Yes, in principle — 6 pairs, needing a clean sweep of 6 wins |
| **This record's actual population** | **1** | **No, at any size** |

The population is a filter naming a single task id. A paired test compares setups
task by task, so one task yields at most one discordant pair, and six are needed. This
hypothesis cannot be settled as written however many times it is run or however much is
spent on it.

It is not a bad question — "does this setup stay inside the permitted change scope" is
exactly the kind of thing the lab should ask. It is a question asked of a population
that cannot answer it. Re-written against a slate of at least twelve tasks it becomes
settleable, and `smallest_plan` now says so before any money is reserved instead of
returning a plan and letting the run discover it.

## What changed in code

- `measures.wins_needed(pairs)` — the fewest wins that reach p < 0.05, or `None` when no
  win count can. Derived from `sign_test`, not from a table.
- `measures.minimum_discordant_pairs()` — six.
- `measures.settleable(tasks, repetitions, flip_rate)` — whether an experiment of this
  size can produce a verdict, with the assumed flip rate stated in the sentence and the
  sufficient task count named in the refusal.
- `genesis_hypotheses.smallest_plan` — sizes with `ceil(6/d)`, carries a `power` block on
  the plan, and **refuses rather than trims**. Capping silently at the population is how
  an experiment that could never conclude reached a launch.

Repetitions deliberately do not enter the sizing. They raise confidence in each task's
pass share and never change how many tasks can disagree, which is what the sign test
counts. `AI-LABS-DIRECTION.md:132` asks for exactly that separation.

## Pinned expectations this moved

`tests/test_genesis_hypotheses_record.py` asserted the old formula outright
(`(0.5, 10), (0.25, 16), (0.1, 20)`). Under the new rule, against that fixture's
twenty-task population:

| Minimum effect | Tasks | Verdict |
|---|---|---|
| 1.0 | 6 | settleable |
| 0.75 | 8 | settleable |
| 0.5 | 12 | settleable |
| 0.25 | 24 → refused | population of 20 gives 5 pairs |
| 0.1 | 60 → refused | population of 20 gives 2 pairs |

The tests now encode the new rule and the refusal, with the reason inline.
