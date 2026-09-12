# Phase 0 research — external benchmarks as products under test

**Feature**: [026-external-benchmark-products](spec.md) · **Date**: 2026-09-11

Every finding below carries its evidence: a file path in this repository, a fetched
page, or a command output. Nothing here is from memory. Where a fact could not be
established without running the source's own code, it is recorded as an open item with
the spike that settles it, rather than guessed.

---

## R1 — τ²-bench's licence and version

**Decision**: τ²-bench is usable. It is MIT, "Copyright (c) 2025 Sierra Research"
(fetched `raw.githubusercontent.com/sierra-research/tau2-bench/main/LICENSE`). The
package is `tau2`, installed with `uv sync`, with domains under `src/tau2/domains/`
(fetched repository README).

**Consequence for pinning**: the source's own release notes state that results produced
with versions below 1.0.1 are not comparable with 1.0.1 and later, and that affected
leaderboard entries were re-graded. The version is therefore part of the source pin
(FR-019), not an incidental detail.

**Alternatives considered**: none — the licence question had only one answer worth
having, and it came back clean.

---

## R2 — What each source's checker actually is

This is the load-bearing research item, because decision D1 runs these unchanged.

### EnterpriseOps-Gym

**Finding**: the checks are data, not code. Each dataset row carries
(fetched `huggingface.co/datasets/ServiceNow-AI/EnterpriseOps-Gym`):

| Field | Content |
|---|---|
| `task_id` | unique identifier |
| `domain` | `calendar`, `csm`, `drive`, `email`, `hr`, `hybrid`, `itsm`, `teams` |
| `system_prompt` | the agent's role and the domain's policies |
| `user_prompt` | the natural-language request |
| `selected_tools` | the tool names offered in this mode |
| `verifiers` | JSON array of `{verifier_type, name, description, validation_config}`, where the config holds a raw SQL query and an `expected_value` |
| `gym_servers_config` | JSON naming the containerized servers and a `seed_database_file`, for example `.../calendar/dbs/db_1762868439331_kf914hbmw.sql` |

**Decision**: run their verifiers by executing their SQL against the post-attempt
database and comparing to their `expected_value`. We depend on **none** of their runner
— not `evaluate.py`, not `ray_experiment_queue.py`, not `compute_score.py` (layout
fetched from the repository README). Their SQL and their expected values are the
checker, and they are used exactly as shipped.

**Why this is the right reading of D1**: "run their checker unchanged" means the check
itself is untouched. A verifier that is a SQL string plus an expected value is fully
expressed by that string and that value; re-implementing the loop that executes it
changes nothing about what is checked, and it frees us from their orchestration stack.

**Four tool-set modes exist** — `oracle`, `plus_5_tools`, `plus_10_tools`,
`plus_15_tools` — which decide how many irrelevant tools sit beside the needed ones.
This is a product-level setting, recorded in the source pin, because it changes
difficulty and therefore comparability.

**Open item OI-1**: the database engine behind the containerized servers, and how to
reach it read-only for the snapshot and for the verifier SQL. The seed is a `.sql`
file per task; the serving engine is not documented in the README. Settled by spike
**S1** below, not assumed.

### AppWorld

**Finding** (fetched `github.com/StonyBrookNLP/appworld`): a Python API, used as a
context manager.

```
AppWorld(task_id=..., experiment_name=...)   # also remote_environment_url=... against a served instance
  .execute(code)          .task_completed()          .close()
  .save_state() / .load_state(state_id)
  .task.instruction   .task.supervisor   .task.app_descriptions   .task.api_docs   .task.ground_truth
  .evaluate()  ->  { success: bool, passes: [{requirement, label}], fails: [{requirement, trace, label}] }
                   with .to_dict() and .report()
```

**This is the closest fit of the three.** Their evaluation already "takes snapshots of
database states as input (before the agent starts and after it ends), then checks that
all expected and no unexpected database changes were made". Their collateral-damage
finding and ours are the same idea computed twice, which is exactly what FR-014 asks us
to record side by side.

**Decision**: call `.evaluate()` and keep `success`, `passes` and `fails` whole.

### τ²-bench

**Finding** (fetched repository README): evaluation is driven by the task's
`evaluation_criteria`, with a `reward_basis` that gates the reward, and
`evaluation_criteria.actions` among the bases. Results land under `data/simulations/`.

**This is the one complication in the feature.** τ²'s reward is **composite and partly
path-based**: it can score the actions taken, not only the state reached. The lab's
landscape note of 9 September lists path-based grading among the things not borrowed,
and `PLAN.md` §1 makes the verdict a statement about the end state.

**Decision**: take their reward whole and unchanged, as D1 requires, and **disclose it**.
The comparability sentence for a τ² round states that the source's positive half is
composite and partly path-based, so no reader mistakes a τ² pass rate for the
end-state-only pass rate the other products report. We do not filter their reward down
to its database component: that would be editing another benchmark's answer key, which
is the one thing D1 and the constitution's upstream-immutability rule both forbid.

**Alternative considered and rejected**: score only the database-state basis and report
the rest as observed-not-scored. Rejected because it manufactures a metric τ² does not
define, it would not match their leaderboard in either direction, and it is a
methodology decision dressed as an implementation detail.

---

## R3 — Seeding a fresh world and dumping a snapshot

The target shape is fixed and generous. `wb_world/snapshot.py:14` takes two plain
dictionaries keyed by service name at the top level, skips `meta`, walks nested
dictionaries and lists, keys list items by `id` when present, and emits
`{service, op, path, before, after}`. It imports nothing from AutomationBench. **Any
world that can dump `{service_name: <plain JSON>}` feeds it unchanged.**

| World | Seed per attempt | Snapshot source |
|---|---|---|
| EnterpriseOps-Gym | the task's `gym_servers_config.seed_database_file` (a `.sql` file), loaded into a private database before the attempt | read every table of that database, one top-level key per domain server |
| AppWorld | `AppWorld(task_id=...)` resets state on construction; base databases in `data/base_dbs/*.db` with per-task differences in `data/tasks/{task_id}/dbs/` | one top-level key per app, from the app's database; their own run also writes `experiments/outputs/{experiment}/{task_id}/dbs/*.jsonl` |
| τ²-bench | the domain environment is constructed per task from its own initial data | one top-level key per domain entity collection |

**Decision**: each adapter implements one method that returns that dictionary, and
`diff_snapshots` is used with no changes at all. Row identity inside lists is already
handled: `_identity` at `wb_world/snapshot.py:22` keys on `id` when it is not null and
falls back to position, which is what a database row dump gives us.

**Decision on ordering**: a snapshot must be deterministic, or a re-dump of an unchanged
world would read as changes. Rows are sorted by primary key before dumping. This is the
adapter's job, not the differ's.

---

## R4 — Publishing each world as an interface document behind one front door

**The existing shape.** `wb_world/openapi.py:206` builds one document per service with
`servers[0].url` pointing at the shim, and `wb_arms/http_shim.py:59`
(`EpisodeHTTPShim(episode, port, public_url)`) dispatches every call back into that
attempt's own world. `wb_world/server.py` already exposes the same three tools over an
MCP server built on FastMCP. So the pattern, the shim and the document generator all
exist; what is new is where the operations come from.

| World | Where operations come from | Work |
|---|---|---|
| AppWorld | it ships `data/api_docs/openapi/` — a raw OpenAPI specification — beside `standard/` and `function_calling/` | rewrite `servers[0].url` to our front door; nothing else |
| EnterpriseOps-Gym | 512 MCP tools across eight servers | list tools over MCP and publish each as an operation |
| τ²-bench | Python tool functions per domain | publish each as an operation |

**Decision — the wrapping rule.** A tool that is not already a REST resource is
published as `POST /{service}/{tool_name}`, with the tool's own input schema as the
request body schema, its description as the operation description, and its name as the
operation id. Nothing is invented: an MCP tool already carries a name, a description and
a JSON Schema for its inputs, which is every field an operation needs.

**Is that faithful?** Yes for discovery, which is what the document is for — Monarch's
mapping step reads operations, parameters and descriptions. It is not a REST modelling
exercise and must not pretend to be: a tool called `create_incident` becomes an
operation called `create_incident`, not a guessed `POST /incidents`. Guessing resource
shapes would invent an interface the world does not have.

**`mcp>=1.0` is already a dependency** (`pyproject.toml:10`), so listing an MCP server's
tools costs no new dependency.

---

## R5 — AppWorld's content and this public repository

**Finding**: AppWorld is dual-licensed. Agent baselines, evaluation utilities, the
execution shell, tutorials and guides are plain-text Apache-2.0. App implementations,
interface code, tests, task solutions and evaluation programs ship as encrypted
`.bundle` files under Apache-2.0 **with an added requirement that public redistribution
be in encrypted form** (fetched repository README). `appworld install` unpacks them
locally.

**Decision**: AppWorld data lives outside this repository entirely. `APPWORLD_ROOT`
points at a directory the product configuration names; the directory is not inside the
repository, and its conventional location is added to `.gitignore` as a second guard.
Our task files record the AppWorld `task_id`, the split and the source pin — identifiers,
not content — and the request text is fetched from the installed package at run time.

**Consequence for the answer key.** Everything is released for train and dev; for
test-normal and test-challenge only the evaluation programs are, not the reference
solutions. The lab's answer-key competitor is the ceiling line on every figure and SC-002
requires it to pass, so **AppWorld is imported from train and dev**, where a reference
solution exists. This refines the spec's assumption: the test splits are gradeable
locally — their evaluation programs ship — but they cannot carry an answer key, so they
are out of scope for this feature rather than refused as ungradeable.

---

## R6 — A second paid participant in the ledger

**The existing shape.** `wb_orchestrator/budget.py` gives `reserve_run(scope_id,
maximum_usd)` for the round, `reserve(reservation_id, maximum_usd)` per paid request,
then `claim` and `settle(reservation_id, actual_usd)`, with `BudgetExceeded` when the
week cannot cover a maximum.

**Decision**: the simulated customer is **not** a second scope. An attempt reserves once,
for the maximum liability of every participant in it, and settles from the sum of the
receipts. Three reasons, all of them rules rather than taste:

1. FR-025 requires the per-attempt cap to count every participant's spend. Two
   independent reservations would let an attempt pass its cap while neither half did.
2. "Cost is complete" means one attempt has one cost, not a competitor cost and a
   footnote.
3. A week that cannot cover both participants must refuse the round before it starts,
   which only works if the maximum is computed for both up front.

**Decision on the configuration hash**: the simulated customer is a field of the product
configuration — its model id and its price-table version — so it enters the hash by the
path every other configuration value already takes. No new hashing rule.

---

## R7 — What is reused unchanged

Checked by reading each file. Reuse is the point: this feature earns its keep by adding
adapters, not by rewriting the machine.

| Piece | Verdict |
|---|---|
| `grader/invariant.py` | **Unchanged.** It matches on `{service, op, path, after}` and imports only `re` and `typing`. It has no idea what world it is looking at. |
| `wb_world/snapshot.py` | **Unchanged.** See R3. |
| `wb_orchestrator/slate.py`, `tiers.py` | **Unchanged in logic.** Both read task files, require a non-empty approval rule and a matching `contract_sha256`, and write manifests. Imported tasks keep that shape, so `wb corpus slate`, `tiers` and `split` work on them as they stand. |
| `wb_orchestrator/corpus.py` `write_manifest` | **Generalized.** Its world block is AutomationBench-specific (`_world_of_corpus` reads the vendored package's version). It needs to record a source pin for any source, of which AutomationBench becomes one case. |
| `wb_arms/http_shim.py` | **Generalized at the seam only.** It takes an `Episode` today; it takes the world adapter interface instead. Its request handling, size limits and access log are untouched. |
| `wb_studio/caveats.py` | **Extended.** `for_run` and `for_round` gain the comparability sentence of FR-028 and the paid-participant sentence of FR-029. |
| `grader/grade.py` | **Changed, narrowly.** Today the positive half is hard-wired to AutomationBench's registry, and a task with no assertions always fails (`assertions_passed = ... if assertion_results else False`, `grader/grade.py:32`). The positive half becomes a per-product path; the rule that no positive check means no pass is preserved deliberately (FR-012), because it is a safety property, not an accident. |
| `wb_orchestrator/orchestrator.py` | **Changed at one line's worth of meaning.** `ep = Episode(task, episode_id=eid)` at line 559 becomes a lookup of the product's adapter. Everything around it — the retry loop, the journal, `snapshot0.json`, the deadline, the evidence writer — is untouched, which is why the adapter interface is defined as exactly what the surrounding code already asks of an episode (R8). |

---

## R8 — The world-adapter interface, derived rather than designed

Read from what `wb_orchestrator/orchestrator.py` and the arms already require of an
episode, not invented: `.snapshot0`, `.snapshot()`, `.finish()`, `.attach_journal(dir)`,
`.artifacts_dir`, `.record_agent_event(entry)`, `.tool_calls`, `.events`, and the three
tools `.api_search`, `.api_fetch`, `.base64_encode`.

**Decision**: that list **is** the contract, written down in `contracts/world-adapter.md`.
The existing `Episode` already satisfies it and becomes the AutomationBench
implementation with no behavioural change. This is why the seam is cheap: it is a name
for something that already exists, not a new layer over it.

**Rejected**: a richer abstraction with lifecycle hooks, capability negotiation or a
plugin registry. Three implementations do not need it, and `wb_studio/genesis_plugins.py`
already shows what this repository does when it genuinely needs a seam.

---

## R10 — All three worlds run out of process (found during execution, 11 Sep)

**Evidence**: declaring `appworld` as an optional extra and running `uv run pytest`
fails to resolve, with uv's own message:

```
Because all versions of appworld depend on pydantic>=1.9.0,<2.0.0
and workflowbench[appworld] depends on appworld, we can conclude that
workflowbench[appworld] depends on pydantic>=1.9.0,<2.0.0.
And because your project depends on pydantic>=2.0 ... unsatisfiable.
```

**AppWorld pins pydantic below 2.0. This project needs pydantic 2 for
AutomationBench's `WorldState`.** The two cannot share an environment at all, and
declaring AppWorld even as an *optional* extra makes `uv sync` unresolvable for
everyone, including a developer who will never run AppWorld.

**Decision**: none of the three external benchmarks is a dependency of this project
in any form — not required, not optional, not an extra. Each runs **out of process**
in its own environment, and WorkflowBench talks to it over HTTP. EnterpriseOps-Gym
was always going to be containers; τ² would otherwise drag `litellm` into a
repository whose provider calls all go through `wb_arms/api_loop.py`; AppWorld now
has no choice.

**This makes R9 mostly moot and the design better.** The uniform front door already
wanted exactly this shape: a world is an HTTP endpoint plus an interface document,
whatever language or dependency set it happens to be written against. AppWorld
already ships the servers for it (`appworld serve apis` on port 9000, an environment
server that is "an HTTP interface to the AppWorld class itself", and an MCP server),
and EnterpriseOps-Gym ships MCP servers per domain. What changes is that each
adapter is an HTTP client of its source rather than an importer of it, and
`prerequisites()` checks a reachable endpoint rather than an importable module.

**Recorded because it is the kind of thing a plan asserts and an execution
discovers.** Writing the first failing test surfaced it in the first two minutes,
which is the argument for the ordering the constitution already requires.

---

## R9 — Dependencies

The constitution requires a reason for each.

| Dependency | Needed for | Reason |
|---|---|---|
| none | EnterpriseOps-Gym | `mcp>=1.0` is already present (`pyproject.toml:10`) and `sqlite3` is standard library. Their verifiers are SQL strings, their tasks are a dataset download. No new dependency. |
| `appworld` | AppWorld | The world, its interfaces and its evaluation programs are the benchmark. There is nothing to reimplement and reimplementing it would be the opposite of running their checker unchanged. |
| `tau2` | τ²-bench | Same reason. It pulls `litellm`, which this repository does not otherwise use: our provider calls go through our own four adapters in `wb_arms/api_loop.py`, and they stay that way for the competitor. `litellm` arrives only as τ²'s own transitive dependency for its simulated customer. |
| `datasets` | EnterpriseOps-Gym, at import time only | AutomationBench already pulls it (`automationbench/domains/__init__.py` imports `datasets`), so it is present. |

**Decision**: `appworld` and `tau2` are **optional extras**, not base dependencies. The
offline suite must run with neither installed (FR-032), which means every adapter is
imported lazily and its absence is a named prerequisite refusal (FR-007), never an
import error at start-up. This mirrors how the vendored AutomationBench is already
handled.

---

## Spike results — run 11 September 2026

All three ran. Two of the three answers are better than the plan assumed, and one
caught a supply-chain trap.

### S1 — EnterpriseOps-Gym: answered, and no wrapping is needed

The domain image is not an opaque MCP box. `docker image inspect` shows
`python -m uvicorn main:app --host 0.0.0.0 --port 8005`, and the running container
answers:

| Endpoint | Evidence |
|---|---|
| `GET /openapi.json` | 200, 221,943 bytes — **OpenAPI 3.1, "ITSM API", 79 paths, 108 operations** |
| `POST /api/seed-database` `{database_id, sql_content}` | `{"success":true,"message":"Database seeded successfully","database_id":"wb-probe-2"}` |
| `GET /api/database-state` + header `x-database-id` | `{success, database_id, service:"itsm", database_info{path:"./mcp_databases/itsm_<id>.sqlite", total_tables:24}, table_counts{...}, table_data:{table:[rows]}}` |
| `POST /api/sql-runner` `{query, limit}` + `x-database-id` | `{"success":true,"data":[{"n":1}],"row_count":1,...}` |
| also present | `/api/reset-database`, `/api/clone-database`, `/api/delete-database`, `/api/schema`, `/api/download-db-file`, `/api/sample-data`, `/health` |

**Four consequences.**

1. **No MCP-to-OpenAPI wrapping for this world.** It already publishes an interface
   document Monarch's discovery can map. `wb_world/tools_openapi.py` is still needed
   for τ², whose surface is Python functions, but not here. The plan over-estimated
   this work.
2. **A private world per attempt is a header.** Every call carries `x-database-id`;
   the adapter mints one per attempt, seeds it from the task's `seed_database_file`,
   and tears it down at `close()`. Databases are ordinary SQLite files, one per id.
3. **The snapshot is `table_data`,** already plain JSON with one key per table and
   rows carrying their own ids — which is what `wb_world/snapshot.py:22` keys on.
   Sorting rows by primary key before handing them over is the adapter's only job.
4. **A security requirement the plan did not have.** `/api/sql-runner`,
   `/api/seed-database`, `/api/reset-database`, `/api/delete-database`,
   `/api/clone-database`, `/api/database-state` and `/api/download-db-file` must be
   **withheld from the competitor** — both absent from the published interface
   document and refused at the front door. A competitor that reached `sql-runner`
   could write the expected result directly, or read the verifier's own target; one
   that reached `reset-database` could erase the evidence. This is now a functional
   requirement, not a nicety.

**How the source's check runs later, out of process — settled.** `positive_check` is a
class method because grading happens after the attempt, from stored state, possibly on
another day and certainly in another process. That sat awkwardly with a verifier that
is SQL against a live database: the attempt's database is torn down at `close()`, and
keeping one per attempt forever is unbounded.

`GET /api/download-db-file` with `x-database-id` answers it. Evidence: after seeding a
probe database it returned **200, 487,424 bytes**, and stdlib `sqlite3` opened the
result directly:

```
tables: ['incident', 'problem', 'organization', 'role', 'permission', 'users', ...]
probe:  [(1, 'x')]
```

So the attempt stores the SQLite file as an artifact beside its snapshots, and
`positive_check` runs each verifier's SQL against **that stored file** with stdlib
`sqlite3`. Their SQL runs exactly as shipped; grading needs no container, no network
and no live world; and a round stays regradable, which is what `wb grade` is for.
No new dependency: `sqlite3` is standard library.

**The dataset, surveyed rather than sampled.** `load_dataset('ServiceNow-AI/EnterpriseOps-Gym', 'oracle')`
— the four tool-set modes are dataset *configs*, and `oracle` holds **649 tasks**:
calendar 61, csm 103, drive 64, email 67, hr 102, hybrid 88, itsm 103, teams 61. (The
1,150 in the paper is across all four modes.) Columns are the seven the dataset card
lists plus `restricted_tools`, `mcp_endpoint`, `number_of_runs` and
`reset_database_between_runs`.

Counting every verifier and every server in all 649 tasks, rather than reading one row
and assuming:

| Fact | Count | Consequence |
|---|---|---|
| `verifier_type` | `database_state` × 3,496 — the only kind | one code path, no dispatch |
| `validation_config` keys | exactly `query`, `expected_value`, `comparison_type`, every time | the field is `query`, **not** `sql` |
| `comparison_type` | `equals` 3,346, `greater_than` 143, `contains` 6, `less_than` 1 | **four comparisons, not one.** Treating them all as equality would misgrade 150 verifiers |
| servers per task | 1 × 561, **2 × 88** | the hybrid domain spans two worlds, so an attempt holds more than one database and the snapshot has more than one service |
| server names | `gym-calendar`, `sn-csm-server`, `gym-google-drive-mcp`, `gym-email-mcp`, `sn-hr-internal`, `gym-itsm-mcp`, `gym-teams-mcp` | these are the service keys, and each verifier names its own with `gym_name` |
| `context` per server | per-server auth headers: `x-access-token`, `x-hr-user-token`, `x-itsm-user-token`, `x-user-email`, … | must be sent on every call; they are the attempt's identity |

Two details worth writing down because they are the kind that silently ruin a round:

1. **A verifier names the world it checks** (`gym_name`), so a hybrid attempt stores one
   database file per server and each verifier runs against its own. Running every
   verifier against the first database would fail 88 tasks for the wrong reason.
2. **Three of the context keys carry stray whitespace upstream** — `'x-user-email '`,
   `' x-user-email'` — and a header name with a space is not valid HTTP. The harness
   strips whitespace from the *header name* when sending and records that it did. This
   is a transport fix on our side, not an edit to their world: their data is unchanged
   and their verifiers are untouched.

### S1b — no reference solution ships, and that blocks the approval rule

**Answered, and it is the one blocker in the feature.** The dataset's columns are
`task_id`, `domain`, `system_prompt`, `user_prompt`, `selected_tools`,
`restricted_tools`, `mcp_endpoint`, `number_of_runs`,
`reset_database_between_runs`, `gym_servers_config`, `verifiers`. **There is no
solution column and no reference action list.** EnterpriseOps-Gym publishes what must
be true at the end, never how to get there.

Two things follow, and the second is a design decision, not an implementation detail.

**1. No answer-key competitor for this product, as it stands.** The answer key is the
ceiling line on every pass-rate figure and SC-002 asserts it passes everything. τ²
has one (its `DB` basis replays `evaluation_criteria.actions` on a fresh world) and
AppWorld's train and dev splits have one. EnterpriseOps-Gym does not. A round on it
draws no ceiling line and the report says why (spec FR/US2, task T041).

**2. The approval rule cannot be derived the obvious way.** The lab's rule needs
`info.expected_changes`: matchers that must each match at least one observed change.
The verifiers say what must be *true*, not what must *change*, and the two are not
interchangeable:

- Putting the verifiers' tables in `expected_changes` fails every task where a
  verifier reads a table that correctly did not change — the matcher matches nothing
  and `missing_expected` fails the attempt.
- Putting them in `allowed_changes` with a wildcard `expected` makes the collateral
  half vacuous: a wildcard matches every change, so nothing is ever unexpected.
- Leaving `expected_changes` empty is the same thing by another route, and
  `wb corpus tiers` then refuses the task as unusable, so it cannot be frozen into a
  task set at all.

**The derivation that would work**, recorded for the decision rather than built on a
guess: seed each task's world once at import time, evaluate each verifier against
that *initial* state, and treat the ones that do not yet hold as the things that must
change. Each such verifier's `WHERE` equality predicates name the table and the field
values that must appear, which is exactly the `where` matcher `grader/invariant.py`
already carries for action-log services whose ids are minted during the run.

That is WorkflowBench's own approval-rule translation — the one kind of correction
the constitution permits — and it does not touch a single one of their verifiers. But
it needs the containers running at import time and a small SQL `WHERE` reader, and it
is a design decision about how this product's rule is derived. It is not something to
settle inside an importer at half past five.

**Until it is settled, EnterpriseOps-Gym tasks can be imported but not frozen into a
task set**, because a task without an approval rule is not usable by the machinery
that freezes sets. The adapter, the grading path and the front door are done and
tested; the corpus is the part that waits.

Minor: `POST /api/delete-database` answered 405, so teardown uses the verb the
document names. Noted rather than guessed.

### S2 — AppWorld: it evaluates here, but it cannot be *driven* here

Installed, unpacked and downloaded: `appworld 0.1.3.post1` (Apache-2.0, Harsh Trivedi,
`github.com/stonybrooknlp/appworld` — checked against PyPI metadata before installing,
not assumed), `appworld install`, `appworld download data` → 178 MB under `data/`, with
`api_docs/{standard,function_calling,openapi}`, `base_dbs/`, `datasets/` and `tasks/`.

**What works on this machine.** A real dev task constructs and evaluates:

```
instruction: Give me a comma-separated list of top 4 most played r&b song titles ...
evaluate() -> TestTracker.to_dict() =
  {success: False, difficulty: 2, num_tests: 2,
   passes:   [{requirement: "Assert no model changes", label: "no_op_pass"}],
   failures: [{requirement: "assert answers match.", trace: "```python ... AssertionError"}]}
```

**Their own collateral check is right there.** `"Assert no model changes"` with label
`no_op_pass` is AppWorld's side-effect finding, and it is exactly what FR-014 wants
recorded beside the lab's approval rule. The adapter's `PositiveResult.side_effects`
is the `no_op`-labelled entries; `passed` is `success`; `detail` is the whole
dictionary, kept as returned.

**What does not work on this machine.** `AppWorld.execute(code)` raises:

```
File appworld/common/utils.py line 4097, in timeout_call
    signal.signal(signal.SIGALRM, timeout_handler)
AttributeError: module 'signal' has no attribute 'SIGALRM'
```

`SIGALRM` is POSIX-only. **AppWorld's world can be built and graded on Windows but not
driven on it**, and driving it is the half the competitor needs. Its own README
provides for this: a containerized server plus `remote_environment_url` on the
`AppWorld(...)` call. So AppWorld joins EnterpriseOps-Gym in needing a container, and
the adapter is an HTTP client of its environment server — which R10 had already
decided for a different reason.

**One Windows detail worth keeping.** Their evaluator writes its report through the
platform's default encoding and the report contains characters cp1252 cannot encode,
so the process needs `PYTHONUTF8=1`. Ours to set, not theirs to fix.

**The interface document is on disk**, at `data/api_docs/openapi/`, so the front door
publishes it rather than deriving anything.

### S2 (first pass) — installed and importable, in its own environment

`appworld 0.1.3.post1`, Apache-2.0, author Harsh Trivedi, repository
`github.com/stonybrooknlp/appworld` — checked against the PyPI metadata before
installing, not assumed. `from appworld import AppWorld` works in an isolated
Python 3.11 environment. It cannot share this project's environment (R10).

The database-location question is answered by R10's shape change: we do not read
AppWorld's files at all. It serves an environment server that is "an HTTP interface
to the `AppWorld` class itself", and the adapter is a client of that.

### S3 — τ²-bench: a supply-chain trap, then a clean answer

**`tau2` on PyPI is not this benchmark.** Installing it yields:

```
Name = tau2 | Version = 2.4.0
Summary = A package for calculating magnetic relaxation rates
Home-page = https://gitlab.com/chilton-group/tau2 | Author = Ben Atkinson
```

A different project entirely, by a different author, in a different field. Anything
that installed `tau2` from PyPI expecting Sierra's benchmark would have got a
chemistry package and a very confusing error. **τ²-bench is installed from its git
repository**, never from PyPI by that name, and this is written into the adapter's
legal note and the quickstart.

From the real clone (`github.com/sierra-research/tau2-bench`):

- **Licence confirmed**: `MIT License`, `Copyright (c) 2025 Sierra Research`.
- **Version 1.0.1**, `requires-python = ">=3.12,<3.14"` — exactly the comparability
  boundary the release notes name, so the pin matters from the first round.
- Domains present: `airline`, `banking_knowledge`, `mock`, `retail`, `telecom`.
- Evaluators: `evaluator_env.py`, `evaluator_action.py`, `evaluator_communicate.py`,
  `evaluator_nl_assertions.py`, behind `evaluator.py`.

**The library surface, read from the clone.** `tau2.registry` exposes per domain a
`get_environment(db=None, solo_mode=False) -> Environment` and `get_tasks(split)`.
`Environment` carries `domain_name`, `policy`, `get_tools() -> list[Tool]`,
`make_tool_call(tool_name, requestor, **kwargs)`, `get_info(include_tool_info=True)`,
`get_db_hash()` and `set_state(...)`. A `Tool` has `.openai_schema`, which is
`{type: function, function: {name, description, parameters}}` — the three fields
`wb_world/tools_openapi.py` needs, so the front door can publish τ²'s Python functions
as operations with no guessing. `DB.load(path)`, `.model_dump()` and `.get_hash()`
give the snapshot.

**One integration cost the plan did not price.** `EnvironmentEvaluator.calculate_reward(
environment_constructor, task, full_trajectory, ..., strict_replay=True)` takes a
**message trajectory** and replays it; it does not read a final state we hand it. So a
τ² attempt has to produce a τ²-shaped message list — assistant messages, tool calls,
tool results — out of what our episode records. That is buildable from `tool_calls`
and the arm's turn log, and it is the largest single piece of τ² work.

**R2 is confirmed and refined by their own source.** `RewardType` says: "The final
reward is the product of every component listed in `EvaluationCriteria.reward_basis`.
Components not listed are not included (they may still run for diagnostics). Default
basis is `[DB, COMMUNICATE]`, matching the original τ-bench."

Two refinements to the plan:

1. **The disclosure is per task, not per product.** Whether the positive half is
   end-state only is a property of each task's `reward_basis`, computable at import.
   A product-level `positive_half_is_end_state_only` flag is therefore a summary of
   the set, and the honest version is computed from the tasks in the frozen set and
   stated as "n of 10 tasks also score the path". The flag stays in the product file
   as the default, and the importer records the real basis per task.
2. **τ² can have an answer key.** `DB` is defined as "predicted DB end state matches
   the target. Target is the result of replaying `EvaluationCriteria.actions` on a
   fresh env" — so every task carries a reference action list. That is exactly what
   an answer-key competitor needs, and it is the one of the three worlds where
   SC-002 is certain.

---

## Spikes that must run before the work they gate

These are the honest unknowns. Each is a task in `tasks.md`, not an assumption.

- **S1 — EnterpriseOps-Gym's serving engine.** Pull one domain image, start it, and
  establish how its database is reached read-only. Gates the snapshot and the verifier
  execution for that world. If the database is not reachable from outside the container,
  the fallback is to run the verifier SQL and the snapshot dump inside it; if neither
  works, the world is unsuitable and that is a finding worth having early.
- **S2 — AppWorld's snapshot boundary.** Confirm which of `data/base_dbs`, the per-task
  `dbs/` differences and the experiment output `dbs/*.jsonl` is the right source for a
  before-and-after dump, and that two dumps of an untouched world are byte-identical.
- **S3 — τ²'s programmatic entry points.** Confirm that a domain environment, its tools
  and its evaluation can be driven as a library rather than only through `tau2 run`, and
  record the actual names. The README documents the CLI; the library surface has to be
  read from the installed package.

Each spike is time-boxed and writes its findings back into this file. None of them
spends money: all three are local, offline after the initial download.

---

## What this research changed in the specification

Two things, both recorded here rather than silently:

1. **AppWorld's test splits are gradeable**, because their evaluation programs ship; what
   they lack is a reference solution. The spec's US3 scenario 2 reads as though they
   were ungradeable. The real constraint is narrower and is captured in R5: import train
   and dev, because the answer-key competitor needs a reference solution.
2. **τ²'s positive half is partly path-based**, which the spec did not know. R2 keeps
   decision D1 intact and handles it by disclosure rather than by editing their reward.
