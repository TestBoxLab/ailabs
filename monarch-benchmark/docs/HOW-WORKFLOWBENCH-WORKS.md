# How WorkflowBench works

A guide for anyone on the team who needs to read a benchmark round and trust the
number. It explains what the machine does, how a task is judged, and where the
judgement can still be wrong. No prior knowledge of the code is assumed.

Written 9 Sep 2026. Every claim points at the file that implements it, so the
document can be checked rather than believed.

---

## 1. What the benchmark measures

Monarch turns a plain-language request into a runnable workflow. WorkflowBench
asks Monarch and a set of competitors to carry out the *same* written request
against the *same* starting data, then checks the world afterwards to see who
actually did it.

The unit of measurement is the **attempt**: one task, one competitor, one
repetition. Everything else — a round, a report, a comparison — is attempts
added up.

An attempt passes only if **three** things hold at once
(`grader/grade.py:45`, `wb_orchestrator/orchestrator.py:456`):

1. the requested result is present,
2. nothing else changed, and
3. the run finished normally.

A timeout or an infrastructure failure cannot pass, however good the final state
looks.

---

## 2. What happens during one attempt

Six stages, always in this order (`wb_orchestrator/orchestrator.py:3-4`,
implemented in `_run_episode`):

```
PROVISION → SNAPSHOT0 → ARM_RUN (with a deadline) → SNAPSHOT1 → GRADE → RECORD
```

- **PROVISION** builds a private simulated world for this attempt alone, from the
  task's starting data, with a frozen clock (`wb_world/episode.py:229-241`).
- **SNAPSHOT0** photographs that world before anyone touches it.
- **ARM_RUN** lets the competitor work until a deadline.
- **SNAPSHOT1** photographs the world afterwards.
- **GRADE** compares the two photographs. **RECORD** writes the row.

Grading and recording always run, whatever the competitor did — including when it
crashed (`orchestrator.py:431-437`).

A retried attempt gets a **brand-new world**, so it never sees the previous
attempt's writes (`orchestrator.py:376-377`).

### Two different retries, easy to confuse

| | What it is | Where it lands |
|---|---|---|
| **Infra retry** | The harness broke (rate limit, provider down). Max 2, inside the same attempt. | Same row, `retries` column (`orchestrator.py:39`) |
| **`retry_on_fail`** | The competitor genuinely failed. A whole second attempt at the prompt. | A new row, flagged `retry` (`orchestrator.py:254-262`) |

A timeout is **never** retried, and its spend and phases still land on the row.

---

## 3. The competitors

Four kinds, all driven through the same interface (`orchestrator.py:96-147`):

| Kind | Who | How it is driven |
|---|---|---|
| **Scripted checks** | `oracle` (answer key / gabarito), `sloppy`, `null` | Python code, no model. They test the *checker*, not a competitor: the answer key must pass, `sloppy` must be caught making a forbidden side effect, `null` must fail by doing nothing. |
| **Raw models** | Claude Opus, GPT-5.6 Sol, cheaper models | The model calls three tools directly, in-process. |
| **Coding agent** | Claude Code headless | `claude -p`, API-key billing only. |
| **Monarch** | The product under test | Through its own HTTP API. |

The raw models get exactly three tools (`wb_arms/api_loop.py:29-66`):

- `api_search(query)` — find an endpoint by keyword
- `api_fetch(method, url, params, body)` — call it
- `base64_encode(text)` — required by Gmail

Budget: **50 tool turns** (`api_loop.py:24`), the same as AutomationBench's.

---

## 4. The front door: how Monarch reaches the simulated world

The raw models call the simulated world in-process. Monarch cannot — its engine
dispatches **plain HTTP** to real-looking REST APIs (`wb_arms/http_shim.py:1-2`).
So the bench stands up a small HTTP server in front of each attempt's private
world.

It serves two things:

- **The map** — an OpenAPI document per service, 47 in total, generated from the
  vendored AutomationBench schemas (`wb_world/openapi.py`).
- **The doors** — `ANY /<service>/<path>` forwards straight into that attempt's
  world (`http_shim.py:136-156`).

```
Monarch  ──HTTPS──▶  tunnel  ──▶  front door (port 9105)  ──▶  Episode.api_fetch
                                        │
                                        └─▶ front-door.jsonl (one line per request)
```

**What Monarch sees:** the API map and every endpoint on it.

**What Monarch never sees:** the task's assertions, its approval rule, the two
snapshots, or any verdict. Grading happens later, out of process, from the stored
snapshots alone (`grader/grade.py:3-5`). Nothing grades itself.

Every request is logged per attempt — method, path, status, request and response
bodies (first 500 characters), elapsed time — so a failed step can say what
actually arrived instead of only what the engine reported (`http_shim.py:47-48`).

### The tunnel is a real dependency, and a trap

There is no tunnel code anywhere in the bench; a person starts it by hand and its
hostname enters the system through two doors: the harness config
(`config/harnesses/monarch.yaml:13`) and — hardcoded — the knowledge base
(`config/products/simulated-apps.monarch-kb.yaml:52`).

That second door matters. The hostname is **inside the config hash**. Restarting
ngrok on a free plan mints a new hostname, which at once: breaks every Monarch
dispatch, requires regenerating and re-importing the knowledge base, and **moves
the config hash — making earlier runs non-resumable and non-regradable**.

This has already bitten us: on 8 Sep the tunnel was down and every dispatch got
ngrok's 404 page. `wb doctor` still does not check it (`deferred.md:86`).

---

## 5. Where the tasks come from

Two separate pools, easy to conflate:

- **10 pilot tasks** (`tasks/*.json`) with hand-written approval rules.
- **800 corpus tasks** imported from AutomationBench across seven domains
  (`tasks/tiers-manifest.yaml:12-40`): finance, hr, marketing, operations, sales,
  support (100 each) and simple (200).

### Difficulty is structural, not semantic

The score is deliberately mechanical (`wb_orchestrator/tiers.py:35-41`):

```
score = services seeded + expected changes + tools needed
```

It measures **how much machinery a task touches**, not how hard the thinking is.
A task can be conceptually subtle and still score "simple". Cut points are the
corpus terciles: **simple ≤ 10**, **medium 11–15**, **complex > 15**
(`tiers-manifest.yaml:9-11`).

### The four frozen sets

Ten prompts each, drawn with seed `20260904`, round-robin across each tier's
domains so no single domain dominates (`tiers.py:169-192`).

`random-10` is **not** a sample of the corpus — it is drawn from what the three
tiers left behind, as an independent check on the blended average
(`tiers.py:232-240`).

Every task is frozen by a hash of its prompt, starting data and approval rule
(`wb_world/episode.py:306-312`). Change any of them and old results stop being
regradable — which is why pre-registration is a rule, not a preference.

---

## 6. The two judges

This is the part worth understanding well, because it is where the benchmark can
be unfair in either direction.

A verdict is produced by two independent checks that ask different questions.

```
                    ONE ATTEMPT IS JUDGED
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌──────────────────┐            ┌──────────────────┐
    │   JUDGE A        │            │   JUDGE B        │
    │   assertions     │            │  approval rule   │
    │                  │            │                  │
    │ AutomationBench's│            │  WorkflowBench's │
    │   own checker    │            │   own diff       │
    ├──────────────────┤            ├──────────────────┤
    │ "DID THE ASKED-  │            │ "DID IT TOUCH    │
    │  FOR THING       │            │  ANYTHING ELSE?" │
    │  HAPPEN?"        │            │                  │
    │                  │            │  reads the list  │
    │ looks at CONTENT │            │  of changes      │
    └──────────────────┘            └──────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
                 passes only if BOTH approve
                    (and the run finished)
```

**Judge A** rehydrates the final snapshot into AutomationBench's own world model
and asks the vendor's own assertion handlers (`grader/grade.py:26-32`). It is
strict about content: right table, right field, right value.

**Judge B** compares the two snapshots into a flat list of changes, then applies
the task's approval rule (`grader/invariant.py:108-132`). The rule has two
halves: what **must** change (`expected_changes`) and what **may** also change
(`allowed_changes` — housekeeping a real platform does anyway, like read
markers).

Judge B fails an attempt when a required change is missing, **or** when a change
happened that no matcher accounted for.

### Why Judge B is the hard one

Judge B works from *paths* — the address of what changed:

```
salesforce.opportunities[id=006001].stage_name     ← precise
airtable.actions.createRecord[id=<minted at run time>]
```

For thirteen services (airtable, jira, trello, notion, asana, monday and others)
the simulated world stores every write in a single **action log**, and the address
of a write is an id minted *during* the run. A rule frozen beforehand cannot name
it. The derivation therefore used to fall back to `airtable.*` — "anything in
Airtable is expected" — which accepts the requested write plus any number of
writes nobody asked for.

Concretely, on `simple.airtable_find_update` before the fix of 9 Sep:

| What the competitor did | Judge A | Judge B | Verdict |
|---|---|---|---|
| Only the requested VIP contact | ✅ | ✅ | passes ✔ |
| A lead instead of the contact | ❌ | ✅ | fails ✔ |
| The right contact **plus 200 junk records** | ✅ | ✅ | **passes ✘** |

The third line is the bug. Judge A is satisfied — the asked-for thing exists.
Judge B saw all 201 changes and accepted them all, because the rule said the whole
service was fair game.

### The fix: match on content, and count

Judge B now accepts two extra clauses (`grader/invariant.py:58-68`):

```yaml
path: "airtable.actions*"
where: {params.tableName: Contacts, params.fields.Status: VIP}
count: 1
```

`where` matches a write by **what it says** rather than by an id nobody can know
in advance; `count` pins **how many** such writes were asked for. Doing the
requested thing 201 times is not doing the requested thing.

Rules that carry neither clause behave exactly as before, so no frozen task
changes its verdict because of this change.

### Two traps in the verdict

- A task with **no** `expected_changes` gets a wildcard, making Judge B vacuous —
  it cannot fail. The row records `invariant_declared: false` as the tell
  (`grade.py:40-42`). `wb corpus tiers` excludes such tasks.
- A task with **zero** assertions fails by default (`grade.py:32`).

---

## 7. Collateral damage as a number

A verdict alone hides something the report should show: a competitor that
finishes more prompts by making a bigger mess looks identical to one that takes
the safe path.

So every attempt now carries a count (`grader/grade.py`), and the report
aggregates it per competitor (`wb_report/metrics.py`):

```
collateral = changes nobody asked for + extra repetitions of the right change
```

- did the right thing, nothing else → `0`
- did the right thing plus 200 junk writes → `200`
- did nothing at all → `0` (fails, but broke nothing)

Two new columns appear in the success table: **attempts with collateral** and
**collateral changes**. Infrastructure attempts are excluded — the harness broke,
not the competitor.

This is what makes the safety-versus-completion trade-off visible. Which matters
more is a judgement per task type, not a number the bench can settle: a workflow
that files an expense report wrong is recoverable; one that emails 200 customers
is not.

---

## 8. Reading a round

`wb run --product <product> --plan <plan>` executes the matrix; `wb grade`
re-scores stored snapshots later; `wb report` renders the page.

Grading is separate from running on purpose: nothing grades itself, rules can be
fixed and past runs re-scored, and a grading crash cannot lose an attempt.
`wb grade` **refuses** to score a stored attempt whose task hash has changed
(`orchestrator.py:506-509`) — old snapshots are never scored against an edited
rule.

The report carries a technical page and an executive page, seven sections, a
source line under every table, and the exact config hash the round ran under.

### Cost

Costs are always computed by WorkflowBench from its own versioned price table,
never taken from a vendor's own figure. Monarch's token counts come from Langfuse,
but the money is ours to compute (`wb_arms/langfuse_cost.py:1-4`).

The cost ceiling is a **stop signal, not a hard cap**: up to
`concurrency × competitors` attempts can already be in flight when it trips
(`orchestrator.py:486-488`).

---

## 9. What is still weak, as of 9 Sep 2026

An honest list, so nobody over-reads a number.

1. **Two Jira tasks remain collateral-blind.** `simple.jira_auth_improvements`
   and `simple.new_lead_sf_jira`: their AutomationBench assertions carry no
   content, so there is nothing for `where` to pin. This is a data limit, not a
   code one — fixing it means editing the task, which moves its hash.
2. **`simple.invoice_airtable_slack` has a weak assertion.** It checks that an
   invoice record exists but not its vendor or amount, so a wrong invoice
   satisfies Judge A. The vendor's handler supports field checking; the task
   simply omits it.
3. **Difficulty is structural.** "Complex" means "touches a lot", not "is hard to
   reason about".
4. **The front door is a single point of failure**, and `wb doctor` does not yet
   check it.
5. **Some tasks cannot be solved through the API at all** —
   `finance.annual_budget_prep` needs a Sheets route that does not exist. Those
   measure the world, not the competitor.

---

## 10. Where to look in the code

| Question | File |
|---|---|
| What happens during an attempt | `wb_orchestrator/orchestrator.py` |
| How a verdict is computed | `grader/grade.py` |
| Judge B's matcher grammar | `grader/invariant.py` |
| How two snapshots become a change list | `wb_world/snapshot.py` |
| How an approval rule is derived | `wb_orchestrator/declare.py` |
| The HTTP front door | `wb_arms/http_shim.py`, `wb_world/openapi.py` |
| The Monarch competitor | `wb_arms/monarch.py` |
| Task tiers and the draw | `wb_orchestrator/tiers.py` |
| Report metrics | `wb_report/metrics.py` |
| The report's contract | `specs/006-html-report/contracts/report.md` |
