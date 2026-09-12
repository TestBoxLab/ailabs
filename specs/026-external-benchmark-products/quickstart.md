# Quickstart — validating external products

**Feature**: [026-external-benchmark-products](spec.md) · **Date**: 2026-09-11

Offline first. Everything in **Part 1** runs with no containers, no downloads, no network
and no provider keys, and it is what the suite checks on every commit. **Part 2** needs
each source installed and is run by hand when an adapter changes. **Nothing here spends
money.**

All commands run from `monarch-benchmark/workflowbench/`. Always `uv run`, never bare
Python.

---

## Part 1 — offline, no sources installed

### The whole suite

```bash
cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q
```

On Windows the full suite takes about 27 minutes; run it detached with logs and wait for
its exit. While iterating, run per file — `fake_monarch.stop()` deadlocks a full run, so
the narrower command is the reliable one:

```bash
cd monarch-benchmark/workflowbench && uv run python -m pytest tests/test_world_adapter.py tests/test_external_grading.py tests/test_external_import.py -q
```

### What it proves

| Check | Expected |
|---|---|
| The adapter contract holds for all four worlds, against recorded fixtures | pass |
| `wb_world/episode.py` satisfies the contract unchanged | pass |
| A product naming an unknown world is refused, by name | refusal |
| A product whose declared services do not match the adapter's snapshot keys is refused | refusal |
| Both halves are required: the right result plus one stray change is a failure | fail, with the stray change listed |
| A source checker that raises leaves the attempt ungraded, error kept | ungraded |
| A task whose hash no longer matches refuses the round, naming the task | refusal |
| An import that would write a half-usable task refuses it with a reason | refusal |
| `import-appworld --split test_normal` is refused, explaining the missing reference solution | refusal |
| A comparison spanning two products is refused, naming both | refusal |
| Snapshotting an untouched world twice gives identical dumps | identical |
| No source package is imported at start-up | pass with none installed |

### Readiness without the sources

```bash
uv run wb doctor --product enterprise-ops-gym
uv run wb doctor --product appworld
uv run wb doctor --product tau2
```

Expected: each names what is missing, in plain words, and starts nothing. This is the
check that matters most on a fresh machine, because it is what stops a round from
discovering a missing container after money has been reserved.

---

## Part 2 — with a source installed

Run per adapter, by hand, when that adapter changes.

### EnterpriseOps-Gym

```bash
docker pull shivakrishnareddyma225/enterpriseops-gym-mcp-itsm:latest
uv run wb doctor --product enterprise-ops-gym          # expect: ready
uv run wb corpus import-eog --domains itsm --mode oracle --out corpus-eog/imported-{domain} --limit 20
uv run wb corpus validate corpus-eog/imported-itsm
uv run wb corpus slate --ids <ids file> --out tasks/eog-itsm-10 --because "first EnterpriseOps-Gym set"
uv run wb run --product enterprise-ops-gym --plan eog-smoke
uv run wb grade <run_id>
uv run wb report <run_id>
```

Expect: the answer key passes every task, the null check passes none, and the report
carries the comparability sentence.

### AppWorld

```bash
uv run pip install appworld && appworld install && appworld download data   # into APPWORLD_ROOT, outside this repository
uv run wb doctor --product appworld
uv run wb corpus import-appworld --split dev --out corpus-appworld/imported-{split} --limit 20
uv run wb corpus import-appworld --split test_normal --out /tmp/x    # expect: refused, with the reason
uv run wb run --product appworld --plan appworld-smoke
uv run wb grade <run_id>
```

Expect additionally: AppWorld's own collateral finding recorded beside ours, and any
disagreement between the two visible in the report.

**Check before committing anything**: `git status` shows no AppWorld content. Their task,
interface and answer-key material is depended on, never redistributed in plain form from
this public repository.

### τ²-bench

```bash
uv run wb doctor --product tau2
uv run wb corpus import-tau2 --domains retail --out corpus-tau2/imported-{domain} --limit 20
uv run wb run --product tau2 --plan tau2-smoke --dry-run
```

Expect from the dry run, before anything is launched: the attempt count, a cost band
covering **both** the competitor and the simulated customer, and a ledger reservation
sized for both. A week that cannot cover the total refuses the round and names the
shortfall.

Expect in the report: the composite-reward sentence and the paid-participant sentence.

---

## The three spikes

[research.md](research.md) S1–S3 are time-boxed investigations, not features. Each runs
before the adapter it gates and writes its findings back into `research.md`:

- **S1** — how EnterpriseOps-Gym's containerized database is reached read-only. A
  negative result here means that world is unsuitable, which is worth learning on day one
  rather than in week three.
- **S2** — which of AppWorld's database locations is the right snapshot source, and that
  two dumps of an untouched world match.
- **S3** — τ²'s real library surface for constructing a domain, listing its tools and
  running its reward.

---

## What "done" means

Every box in the table in Part 1 passes offline, and Part 2 has been run at least once
per adapter with its source installed. A task is not complete on a green unit test alone
— the constitution's verification rule wants runnable evidence, and for a world adapter
that means the world actually ran.
