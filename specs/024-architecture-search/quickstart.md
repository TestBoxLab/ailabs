# Quickstart: verifying the search loop

**Feature**: 024-architecture-search | **Date**: 2026-09-11

How to prove each story works. Every check below is runnable. Details of fields and
commands live in [contracts/](./contracts/) and [data-model.md](./data-model.md); this
file is the run guide.

## Prerequisites

```bash
cd monarch-benchmark/workflowbench && uv sync
```

Offline unless a step says **paid**. `wb run`, `wb monarch recipes` and
`wb experiment confirm` are paid execution, never free validation.

Full suite baseline before starting. Measured 11 Sep 2026: **2237 passed, 1 failed
(`test_run_page.py`, pre-existing), 3 skipped, 15 minutes**. STATE-OF-THE-PROGRAM.md
still says 1091; it is stale. On Windows run it detached and wait for its exit:

```bash
cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q
```

During development run per file. A whole-suite run deadlocks on `fake_monarch.stop()`.

---

## Story 1 — The gates hold

**The front door.** Start a Studio and attempt the reaches from outside, with no
credentials. Every one must be refused, and the attempt's world unchanged.

```bash
curl -i -X DELETE http://localhost:9104/front-door/airtable/v0/app1/Tasks/rec1
curl -i -X PATCH  http://localhost:9104/front-door/airtable/v0/app1/Tasks/rec1 -d '{}'
curl -i          http://localhost:9104/front-door/airtable/v0/app1/Tasks
```

Expected: `401` or `404` on all three, no relay, nothing in the world's access log.
With the current run's secret segment present, the same calls succeed. Check
`wb monarch verify` still passes afterwards — the repair must not change what Monarch
has to send.

**Default autonomy.** Point a Studio at an empty state directory with provider keys
present, leave it for a full scheduled day, and confirm zero paid activity and no cards
worked.

**Pause.** Enable the researcher, pause it, then advance past every scheduled hour.
Expected: spend zero, and each skipped job recorded with its reason.

```bash
uv run wb budget status          # unchanged across the paused day
```

**Allowance and envelope.** Launch a run from the researcher and confirm its reserved
maximum appears in the day's spend and in the weekly envelope before it settles.

```bash
uv run wb budget envelope status
```

**Overrun.** Force a reservation to settle above its maximum, then confirm an unrelated
paid path still runs, the overrun is recorded, and a person can clear it without editing
`research/budget.sqlite3` by hand.

**Operator and approval.** Launch from the Studio and inspect the record.

```bash
uv run wb approvals
```

Expected: the operator is a person; above smoke scale an approval record exists and is
referenced; no launch is approved by an agent.

**Attempt cap.** Run a task with a competitor that loops. Expected: it stops at its
per-attempt cap and the remaining tasks still run.

**Fetch.** Drop each of these for the researcher to read. All must be refused with
nothing fetched or stored.

```
http://169.254.169.254/latest/meta-data/
http://127.0.0.1:9105/openapi/index.json
http://10.0.0.1/
```

---

## Story 2 — Numbers a scientist can act on

Render the lab's existing ten-task run and check each defect against stored evidence.

```bash
uv run wb report --run 6022e89fbb974c7483716f85a5e3c4fe
```

| Check | Expected |
|---|---|
| Google services | `googleads.googleapis.com` reads as Google Ads, not Gmail |
| False completion | No finding asserts a completion claim for an attempt that ran out of turns; where the signal does appear it says it is inferred from wording |
| Liveness | The four attempts on moved hashes are marked and excluded from the headline; the headline states the denominator it actually scored |
| Failure classes | One classification; the bar chart and the per-attempt folds agree |
| Labels | The hero bar names model and version, not "low reasoning" |
| Titles | The trend title names the competitors present in the data |
| Cohorts | Runs with no pinned judge are not pooled with pinned ones; provisional is stated |
| Intervals | No zero-width 95% interval anywhere; rank and interval share an estimator |

---

## Story 3 — An experiment that can return a verdict

**Draw the split** (offline):

```bash
uv run wb corpus split --corpus 'corpus/imported-*' --size 50 --seed 20260911 \
  --dev-out tasks/dev-50 --heldout-out tasks/heldout-50 \
  --manifest tasks/split-manifest.yaml \
  --because 'architecture search needs a development slate and an untouched confirmation slate'
```

Expected: both slates frozen with hashes; the manifest shows tier and domain counts
differing by at most one; re-running against the frozen held-out slate is refused.

**Power refusal** (offline, before any reservation):

```bash
uv run wb experiment propose --variant demo --predict 'x helps' --slate development --repetitions 1
```

Against a ten-task set this must refuse and name the sufficient count. Against the
50-task development slate at 3 repetitions it must admit, showing the expected
discordant-pair count and the minimum wins needed.

**Envelope refusal** (offline): set an envelope smaller than the experiment's maximum and
confirm the refusal names the shortfall and does not fall through to the weekly ceiling.

**Lineage** (paid): confirm a supported variant on held-out, then attempt any descendant
of that lineage on held-out again. The second must be refused, naming the prior result.

---

## Story 4 — The fitness function

**Paid.** One Monarch attempt in create-and-run mode:

```bash
uv run wb run --product simulated-apps --plan pilot-monarch-single
```

Then inspect the stored row:

| Field | Expected |
|---|---|
| `cost_by_phase` | `authoring` and `execution` present; sum reconciles with `cost_usd` within one cent |
| `authoring_ended_at` | present |
| `configure_s` + `execute_s` | reconcile with `duration_s` within one second |
| a raw-model competitor | `authoring` is `n/a`, not `0` and not `unknown` |

**Recipes** (paid) — the curve's x-axis:

```bash
uv run wb monarch recipes --product simulated-apps --tasks tasks/dev-50
uv run wb run --product simulated-apps --plan pilot-monarch-run-only
```

Expected: a per-execution cost and time for each task.

---

## Story 5 — The curve and the gap list

```bash
uv run wb report --round <id> --for executive
uv run wb report --round <id> --for lab
uv run wb report --round <id> --for engine-team
```

| Check | Expected |
|---|---|
| Opening | Curve, accuracy with uncertainty and sample count, gap list |
| Crossing point | Named, or "no crossing within the observed range" in words — never extrapolated |
| Cost basis | Per successful task |
| Three renderings | Same evidence base; no fact asserted in one and contradicted in another |
| Gap items | Each states `confirmed-result` or `code-reading`; unconfirmed are marked; code readings stay internal |

---

## Before calling it done

```bash
cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q
node tests/browser/suite.cjs
```

The browser suite currently resolves Playwright from a hard-coded path on one machine, so
it runs for Lucas and not for Carlos, and not in CI. That is out of scope here — but a
frontend change in stories 2 and 5 has no automated guard, and the review should say so
rather than imply coverage.

Then refresh the Graphify graph, and correct `STATE-OF-THE-PROGRAM.md` §3, which lists
feature 004 as "specified, not built" when `wb_orchestrator/monarch_recipes.py` is
complete.
